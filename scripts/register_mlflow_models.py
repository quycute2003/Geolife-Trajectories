"""Register both GeoLife algorithms and verify every user in the packaged snapshot."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib


ROOT = Path(__file__).resolve().parents[1]
MODELS = {"heuristic-v1": "geolife-inference-blue", "dbscan-v1": "geolife-inference-green"}
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR", "false")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "30")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1")


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_dependencies():
    from packaging.requirements import Requirement

    dependencies = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    for text in [*dependencies, "mlflow>=3,<4"]:
        requirement = Requirement(text)
        installed = version(requirement.name)
        if installed not in requirement.specifier:
            raise ValueError(f"Found {requirement.name}=={installed}; need {text}. Stop MLflow, then run: "
                             f"uv pip install --python '{sys.executable}' -r pyproject.toml 'mlflow>=3,<4'")
    return [f"{Requirement(text).name}=={version(Requirement(text).name)}" for text in dependencies] + [f"mlflow=={version('mlflow')}"]


def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True, encoding="utf-8", stderr=subprocess.PIPE,
                                   timeout=15).strip()


def verify_model(uri, tracking_uri, expected_root, users, snapshot_id, model_version):
    import mlflow
    import pandas as pd

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_registry_uri(tracking_uri)
    model = mlflow.pyfunc.load_model(uri)
    # This import must resolve from code_paths downloaded with the model in a fresh process.
    from geolife_inference.config import Config

    config_path = Path(sys.modules[Config.__module__].__file__)
    if config_path.parent.parent.name != "code":
        raise ValueError("Inference code was imported outside the saved model bundle.")
    rows = model.predict(pd.DataFrame({"user_id": users}))
    if len(rows) != len(users):
        raise ValueError("The model returned an unexpected number of predictions.")
    summaries = []
    for user_id, row in zip(users, rows.to_dict("records"), strict=True):
        expected = json.loads((expected_root / model_version / f"{user_id}-{model_version}.json").read_text(encoding="utf-8"))
        for key, value in Config(**expected["config"]).version_metadata().items():
            expected.setdefault(key, value)
        expected["data_snapshot_id"] = snapshot_id
        actual = json.loads(row["prediction_json"])
        differences = sorted(key for key in actual.keys() | expected.keys() if actual.get(key) != expected.get(key))
        if differences or row["user_id"] != user_id or row["model_version"] != model_version:
            raise ValueError(f"CLI parity failed: {model_version}, user={user_id}, fields={differences}")
        summaries.append({"user_id": user_id, "input_points": actual["diagnostics"]["input_points"],
                          "stays": actual["diagnostics"]["stay_events"], "locations": len(actual["locations"]),
                          "home": actual["home"]["status"], "office": actual["office"]["status"]})
    from mlflow.exceptions import MlflowException

    for invalid in [101, "", "x" * 65, "registry-absent-user"]:
        try:
            model.predict(pd.DataFrame({"user_id": [invalid]}))
        except (ValueError, MlflowException):
            continue
        raise ValueError(f"The model accepted invalid or absent user_id={invalid!r}")
    return {"full_cli_match": True, "bundled_code_loaded": True,
            "users": summaries, "invalid_id_checks": "passed"}


def verify_in_fresh_process(uri, args, users, snapshot_id, model_version):
    with TemporaryDirectory(prefix="geolife-registry-verify-") as directory:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
             "--verify-model-uri", uri, "--tracking-uri", args.tracking_uri,
             "--expected-root", str(args.expected_root), "--verify-users", *users,
             "--verify-snapshot", snapshot_id, "--verify-version", model_version],
            cwd=directory, text=True, encoding="utf-8", capture_output=True, timeout=180,
        )
    if result.returncode:
        raise ValueError(f"Loading and testing the saved model failed:\n{result.stderr}\n{result.stdout}")
    return json.loads(result.stdout)


def register(args, requirements):
    import mlflow
    import pandas as pd
    from mlflow import MlflowClient
    from mlflow.models import ModelSignature
    from mlflow.types.schema import ColSpec, Schema

    sys.path.insert(0, str(ROOT / "src"))
    from geolife_inference import __version__
    from geolife_inference.config import Config

    with closing(sqlite3.connect(args.snapshot.as_uri() + "?mode=ro", uri=True)) as connection:
        snapshot_row = connection.execute("SELECT id FROM snapshot").fetchone()
        if not snapshot_row or not snapshot_row[0]:
            raise ValueError("The SQLite snapshot ID is missing.")
        snapshot_id = snapshot_row[0]
        counts = dict(connection.execute("SELECT user_id, count(*) FROM gps_points GROUP BY user_id ORDER BY user_id"))
    if not counts:
        raise ValueError("The SQLite snapshot contains no GPS points.")
    users = list(counts)
    config = Config()
    expected_hashes = {}
    for model_version in MODELS:
        for user_id in users:
            path = args.expected_root / model_version / f"{user_id}-{model_version}.json"
            expected = json.loads(path.read_text(encoding="utf-8"))
            if (expected["user_id"] != user_id or expected["model_version"] != model_version
                    or expected["config"] != config.to_dict() or expected["pipeline_version"] != __version__):
                raise ValueError(f"CLI metadata does not match this release: {path}")
            expected_hashes[f"{model_version}/{path.name}"] = file_sha256(path)

    image_id = None
    if not args.skip_image_inspect:
        image_id = command("docker", "image", "inspect", args.image, "--format", "{{.Id}}")
    source_files = {str(path.relative_to(ROOT)).replace("\\", "/"): file_sha256(path)
                    for path in sorted((ROOT / "src" / "geolife_inference").glob("*.py"))}
    for relative in ["scripts/mlflow_geolife_model.py", "scripts/register_mlflow_models.py", "pyproject.toml", "uv.lock"]:
        source_files[relative] = file_sha256(ROOT / relative)
    common = {
        "pipeline_version": __version__, "config": config.to_dict(), **config.version_metadata(),
        "data_snapshot_id": snapshot_id, "snapshot_sha256": file_sha256(args.snapshot),
        "snapshot_user_points": counts, "expected_cli_sha256": expected_hashes,
        "git_commit": command("git", "rev-parse", "HEAD"),
        "git_dirty": bool(command("git", "status", "--porcelain")),
        "source_files_sha256": source_files, "source_sha256": json_sha256(source_files),
        "image": args.image, "image_id": image_id,
        "deployment_binding": "declared; cluster and image contents have not been inspected for source parity",
        "pip_requirements": requirements,
    }
    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_registry_uri(args.tracking_uri)
    mlflow.set_experiment(args.experiment)
    client = MlflowClient()
    signature = ModelSignature(inputs=Schema([ColSpec("string", "user_id")]),
                               outputs=Schema([ColSpec("string", name) for name in ("user_id", "model_version", "prediction_json")]))
    report = {"tracking_uri": args.tracking_uri, "registered_model": args.name,
              "created_at": datetime.now(timezone.utc).isoformat(), "models": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Verifying all {len(users)} users / {sum(counts.values())} GPS points in snapshot {snapshot_id}.", flush=True)
    existing = list(client.search_model_versions(f"name = '{args.name}'"))
    with TemporaryDirectory(prefix="geolife-registry-") as directory:
        work = Path(directory)
        package = work / "geolife_inference"
        shutil.copytree(ROOT / "src" / "geolife_inference", package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for model_version, revision in MODELS.items():
            manifest = {**common, "model_version": model_version, "knative_revision": revision}
            fingerprint = json_sha256(manifest)
            tags = {key: str(manifest[key]) for key in ("model_version", "pipeline_version", "config_version", "config_sha256",
                                                       "data_snapshot_id", "snapshot_sha256", "git_commit", "source_sha256",
                                                       "knative_revision", "git_dirty", "image")}
            tags.update(bundle_sha256=fingerprint, deployment_binding="declared", parity_scope="all users in packaged SQLite snapshot")
            if image_id:
                tags["image_id"] = image_id
            reused = next((item for item in existing if item.tags.get("bundle_sha256") == fingerprint
                           and item.tags.get("cli_parity") == "passed" and item.status == "READY"), None)
            if reused:
                registered = reused
                uri = f"models:/{args.name}/{registered.version}"
                parity = verify_in_fresh_process(uri, args, users, snapshot_id, model_version)
                run_id = registered.run_id
            else:
                with mlflow.start_run(run_name=model_version, tags=tags) as run:
                    run_id = run.info.run_id
                    mlflow.log_params({"model_version": model_version, **config.to_dict()})
                    mlflow.log_dict(manifest, "release/manifest.json")
                    for user_id in users:
                        mlflow.log_artifact(str(args.expected_root / model_version / f"{user_id}-{model_version}.json"), "reference_cli")
                    manifest_path = work / f"{model_version}.json"
                    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                    logged = mlflow.pyfunc.log_model(
                        name="inference", python_model=str(ROOT / "scripts" / "mlflow_geolife_model.py"),
                        code_paths=[str(package)], artifacts={"history": str(args.snapshot), "manifest": str(manifest_path)},
                        signature=signature, input_example=pd.DataFrame({"user_id": [users[0]]}),
                        pip_requirements=requirements, metadata={"model_version": model_version, "bundle_sha256": fingerprint},
                    )
                    # Only publish a registry version after the logged bundle passes CLI parity.
                    parity = verify_in_fresh_process(logged.model_uri, args, users, snapshot_id, model_version)
                    mlflow.log_dict(parity, "validation/logged_bundle_parity.json")
                    registered = mlflow.register_model(logged.model_uri, args.name, tags=tags)
                    uri = f"models:/{args.name}/{registered.version}"
                    parity = verify_in_fresh_process(uri, args, users, snapshot_id, model_version)
                    mlflow.log_dict(parity, "validation/registered_model_parity.json")
                    mlflow.log_metrics({"cli_parity_users": len(users), "cli_parity_points": sum(counts.values()), "cli_parity_passed": 1})
                    client.set_model_version_tag(args.name, registered.version, "cli_parity", "passed")
            client.set_registered_model_alias(args.name, model_version, registered.version)
            entry = {"algorithm": model_version, "registry_version": registered.version, "model_uri": uri,
                     "alias_uri": f"models:/{args.name}@{model_version}", "run_id": run_id,
                     "reused": bool(reused), "manifest": manifest, "validation": parity}
            report["models"].append(entry)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"PASS {model_version}: registry version={registered.version}, {len(users)}/{len(users)} full CLI matches"
                  f"{' (reused)' if reused else ''}.", flush=True)
    print(f"Saved {args.output}\nOpen MLflow > Models > {args.name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-uri", default="http://127.0.0.1:5000")
    parser.add_argument("--name", default="geolife-home-office")
    parser.add_argument("--experiment", default="geolife-cp2")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "artifacts/cp2/sqlite/geolife.sqlite3")
    parser.add_argument("--expected-root", type=Path, default=ROOT / "artifacts/pipeline")
    parser.add_argument("--image", default="dev.local/geolife-api:0.2.0-sqlite-demo")
    parser.add_argument("--skip-image-inspect", action="store_true", help="Allow registry-only checks without Docker; image ID stays unset")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/cp2/mlflow/registration.json")
    parser.add_argument("--verify-model-uri", help=argparse.SUPPRESS)
    parser.add_argument("--verify-users", nargs="+", help=argparse.SUPPRESS)
    parser.add_argument("--verify-snapshot", help=argparse.SUPPRESS)
    parser.add_argument("--verify-version", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.name):
        parser.error("--name may contain letters, digits, dots, underscores and hyphens.")
    args.snapshot = args.snapshot.resolve()
    args.expected_root = args.expected_root.resolve()
    args.output = args.output.resolve()
    try:
        requirements = check_dependencies()
        if args.verify_model_uri:
            print(json.dumps(verify_model(args.verify_model_uri, args.tracking_uri, args.expected_root,
                                          args.verify_users, args.verify_snapshot, args.verify_version)))
        else:
            register(args, requirements)
    except (ValueError, OSError, PackageNotFoundError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
