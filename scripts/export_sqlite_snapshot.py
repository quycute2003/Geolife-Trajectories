import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

import pandas as pd

from geolife_inference import __version__
from geolife_inference.clustering import MODEL_VERSIONS
from geolife_inference.config import load_config
from geolife_inference.data import GeoLifeSource
from geolife_inference.postgres import HISTORY_POINT_LIMIT
from geolife_inference.sqlite_history import LOOKUP_INDEX, POINTS_SCHEMA, PRECOMPUTED_SCHEMA


def validate_cli_audits(source, root, config):
    for model in MODEL_VERSIONS:
        path = root / model / "run-audit.json"
        audit = json.loads(path.read_text(encoding="utf-8"))
        if (audit.get("status") != "completed" or audit.get("scope") != "full_dataset"
                or sorted(audit.get("completed_users", [])) != sorted(source.by_user)
                or audit.get("processed_trajectory_files") != len(source.names)
                or audit.get("model_version") != model or audit.get("config") != config):
            raise ValueError(f"Expected a completed baseline CLI run for this dataset: {path}")


def read_cli_result(root, user_id, model, point_count, config, metadata):
    path = root / model / f"{user_id}-{model}.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    if (result.get("user_id") != user_id or result.get("model_version") != model
            or result.get("pipeline_version") != __version__ or result.get("status") != "completed"
            or result.get("config") != config or result.get("diagnostics", {}).get("input_points") != point_count
            or any(result.get(key, value) != value for key, value in metadata.items())):
        raise ValueError(f"Saved CLI result does not match the source count or baseline: {path}")
    return {**result, **metadata}


def sqlite_rows(points):
    for row in points.itertuples(index=False):
        yield (row.user_id, row.trajectory_id, row.source_row, row.latitude, row.longitude,
               row.altitude_m, None if pd.isna(row.timestamp) else row.timestamp.value)


def export_snapshot(source, users, snapshot_id, output, *, cli_results=None):
    if not snapshot_id.strip() or len(snapshot_id) > 128:
        raise ValueError("Snapshot ID must contain 1 to 128 characters")
    users = sorted(set(users))
    baseline = load_config()
    config, metadata = baseline.to_dict(), baseline.version_metadata()
    if cli_results is not None:
        validate_cli_audits(source, cli_results, config)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as directory:
        database = Path(directory) / output.name
        with closing(sqlite3.connect(database)) as connection, connection:
            # The temporary database is only published after a successful commit.
            connection.execute("PRAGMA journal_mode = OFF")
            connection.executescript(POINTS_SCHEMA)
            if cli_results is not None:
                connection.executescript(PRECOMPUTED_SCHEMA)
            connection.execute("INSERT INTO snapshot VALUES (?)", (snapshot_id,))
            total_points = precomputed_users = 0
            for user_id in users:
                count = 0
                for points in source.trajectories(user_id, include_source_row=True):
                    connection.executemany("INSERT INTO gps_points VALUES (?, ?, ?, ?, ?, ?, ?)", sqlite_rows(points))
                    count += len(points)
                if count == 0:
                    raise ValueError(f"User {user_id} has no GPS points")
                needs_precomputed = count > HISTORY_POINT_LIMIT
                if needs_precomputed and cli_results is None:
                    raise ValueError(f"User {user_id} has {count} points. Supply --cli-results to serve long histories.")
                if cli_results is not None:
                    for model in MODEL_VERSIONS:
                        result = read_cli_result(cli_results, user_id, model, count, config, metadata)
                        if needs_precomputed:
                            connection.execute("INSERT INTO precomputed_inference VALUES (?, ?, ?, ?, ?)", (
                                user_id, model, __version__, metadata["config_sha256"], json.dumps(result, allow_nan=False),
                            ))
                precomputed_users += needs_precomputed
                total_points += count
                print(f"{user_id}: {count} points" + (" (precomputed inference)" if needs_precomputed else ""), flush=True)
            print("Building GPS history index...", flush=True)
            connection.execute(LOOKUP_INDEX)
        database.replace(output)
    print(f"Exported {len(users)} users, {total_points} points, {precomputed_users} users with precomputed inference.", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("data/Geolife Trajectories 1.3/Data"))
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--users", nargs="+")
    selection.add_argument("--all-users", action="store_true", help="Export every user under --dataset")
    parser.add_argument("--cli-results", type=Path, help="Baseline CLI run directories, e.g. artifacts/pipeline")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/cp2/sqlite/geolife.sqlite3"))
    args = parser.parse_args()
    if args.all_users and args.cli_results is None:
        parser.error("--all-users requires --cli-results for complete API coverage")
    if args.all_users and args.output.resolve() == Path("artifacts/cp2/sqlite/geolife.sqlite3").resolve():
        parser.error("--all-users requires a separate --output path")
    source = GeoLifeSource(args.dataset)
    users = source.by_user if args.all_users else args.users
    export_snapshot(source, users, args.snapshot, args.output, cli_results=args.cli_results)
    print(args.output)


if __name__ == "__main__":
    main()
