"""Import one GeoLife user or migrate a complete SQLite snapshot into PostgreSQL."""
import argparse
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import sqlite3

from geolife_inference import __version__
from geolife_inference.clustering import MODEL_VERSIONS
from geolife_inference.config import load_config
from geolife_inference.data import GeoLifeSource
from geolife_inference.postgres import DEFAULT_SNAPSHOT, HISTORY_POINT_LIMIT, SCHEMA, PostgresHistory


IMPORT_SCHEMA = """
CREATE TABLE IF NOT EXISTS geolife_snapshot_imports (
    snapshot_id text PRIMARY KEY,
    sqlite_sha256 text NOT NULL,
    user_count integer NOT NULL,
    point_count bigint NOT NULL,
    precomputed_count integer NOT NULL
);
"""

COPY_POINTS = """
COPY geolife_gps_points
    (snapshot_id, user_id, trajectory_id, source_row, latitude, longitude, altitude_m, recorded_at)
FROM STDIN WITH (FORMAT CSV)
"""


def read_snapshot_data(source):
    ids = source.execute("SELECT id FROM snapshot").fetchall()
    if len(ids) != 1 or not ids[0][0]:
        raise ValueError("Expected exactly one SQLite snapshot ID.")
    counts = source.execute(
        "SELECT user_id, count(*) FROM gps_points GROUP BY user_id ORDER BY user_id"
    ).fetchall()
    if not counts:
        raise ValueError("SQLite snapshot contains no GPS points.")
    has_precomputed = source.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'precomputed_inference'"
    ).fetchone()
    predictions = source.execute("""
        SELECT user_id, model_version, pipeline_version, config_sha256, result_json
        FROM precomputed_inference
        """).fetchall() if has_precomputed else []
    baseline = load_config()
    metadata = baseline.version_metadata()
    long_users = {user: count for user, count in counts if count > HISTORY_POINT_LIMIT}
    expected = {(user, model) for user in long_users for model in MODEL_VERSIONS}
    if {(row[0], row[1]) for row in predictions} != expected or len(predictions) != len(expected):
        raise ValueError("SQLite snapshot must contain both baseline results for every long history.")
    for user, model, pipeline, config_hash, encoded in predictions:
        result = json.loads(encoded)
        if (pipeline != __version__ or config_hash != metadata["config_sha256"]
                or result.get("user_id") != user or result.get("model_version") != model
                or result.get("pipeline_version") != pipeline or result.get("config") != baseline.to_dict()
                or result.get("status") != "completed"
                or result.get("diagnostics", {}).get("input_points") != long_users[user]
                or any(result.get(key) != value for key, value in metadata.items())):
            raise ValueError(f"SQLite result metadata does not match the baseline: {user}/{model}.")
    return ids[0][0], counts, predictions


def copy_user(source, destination, snapshot_id, user_id):
    result = source.execute("""
        SELECT trajectory_id, source_row, latitude, longitude, altitude_m, recorded_at_ns
        FROM gps_points WHERE user_id = ? ORDER BY trajectory_id, source_row
        """, (user_id,))
    copied = 0
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    with destination.copy(COPY_POINTS) as copy:
        while rows := result.fetchmany(16_384):
            for trajectory, source_row, lat, lon, altitude, ns in rows:
                recorded_at = None
                if ns is not None:
                    seconds, remainder = divmod(ns, 1_000_000_000)
                    if remainder % 1_000:
                        raise ValueError(f"Timestamp for {user_id}/{trajectory} exceeds PostgreSQL microsecond precision.")
                    recorded_at = datetime.fromtimestamp(seconds, timezone.utc).replace(microsecond=remainder // 1_000)
                writer.writerow((snapshot_id, user_id, trajectory, source_row, lat, lon, altitude, recorded_at))
            copy.write(buffer.getvalue())
            buffer.seek(0)
            buffer.truncate()
            copied += len(rows)
    return copied


def import_sqlite_snapshot(dsn, path):
    with path.open("rb") as stream:
        fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        source.execute("BEGIN")
        snapshot_id, counts, predictions = read_snapshot_data(source)
        history = PostgresHistory(dsn, snapshot_id)
        points = sum(count for _, count in counts)
        metadata = (fingerprint, len(counts), points, len(predictions))
        with history.driver.connect(dsn, connect_timeout=5) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('geolife_gps_points'))")
            cursor.execute(SCHEMA)
            cursor.execute(IMPORT_SCHEMA)
            cursor.execute("""
                SELECT sqlite_sha256, user_count, point_count, precomputed_count
                FROM geolife_snapshot_imports WHERE snapshot_id = %s
                """, (snapshot_id,))
            existing = cursor.fetchone()
            if existing is not None:
                if existing != metadata:
                    raise ValueError("Snapshot ID already belongs to a different SQLite file.")
                return snapshot_id, len(counts), points, len(predictions), False
            cursor.execute("SELECT 1 FROM geolife_histories WHERE snapshot_id = %s LIMIT 1", (snapshot_id,))
            if cursor.fetchone() is not None:
                raise ValueError("Snapshot ID already belongs to histories imported separately.")
            cursor.executemany("INSERT INTO geolife_histories VALUES (%s, %s, %s)", [
                (snapshot_id, user, fingerprint) for user, _ in counts
            ])
            for index, (user, count) in enumerate(counts, 1):
                if copy_user(source, cursor, snapshot_id, user) != count:
                    raise ValueError(f"Point count changed during import for {user}.")
                if index % 20 == 0 or index == len(counts):
                    print(f"Copied {index}/{len(counts)} users.", flush=True)
            cursor.executemany("""
                INSERT INTO geolife_precomputed_inference
                    (snapshot_id, user_id, model_version, pipeline_version, config_sha256, result_json)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """, [(snapshot_id, *row) for row in predictions])
            cursor.execute("INSERT INTO geolife_snapshot_imports VALUES (%s, %s, %s, %s, %s)",
                           (snapshot_id, *metadata))
    return snapshot_id, len(counts), points, len(predictions), True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/Geolife Trajectories 1.3/Data"))
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--user-id")
    selection.add_argument("--sqlite", type=Path, help="Migrate an exported SQLite snapshot and its precomputed results.")
    parser.add_argument("--snapshot", help="Override the snapshot ID for a single-user import.")
    args = parser.parse_args()
    dsn = os.environ.get("GEOLIFE_POSTGRES_DSN")
    if not dsn:
        parser.error("Set GEOLIFE_POSTGRES_DSN to the PostgreSQL connection string.")
    if args.sqlite is not None:
        if args.snapshot is not None:
            parser.error("--sqlite uses the snapshot ID stored in the file.")
        snapshot, users, points, precomputed, imported = import_sqlite_snapshot(dsn, args.sqlite)
        action = "Imported" if imported else "Already imported"
        print(f"{action}: snapshot={snapshot}, users={users}, points={points}, precomputed_results={precomputed}.")
        return
    if not re.fullmatch(r"[0-9]{3}", args.user_id):
        parser.error("user_id must be a three-digit GeoLife ID.")

    snapshot = args.snapshot or os.environ.get("GEOLIFE_SNAPSHOT_ID", DEFAULT_SNAPSHOT)
    history = PostgresHistory(dsn, snapshot)
    count, imported = history.import_user(GeoLifeSource(args.dataset), args.user_id)
    action = "Imported" if imported else "Already imported"
    print(f"{action}: snapshot={snapshot}, user_id={args.user_id}, points={count}.")


if __name__ == "__main__":
    main()
