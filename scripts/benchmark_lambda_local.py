import argparse
import csv
import json
import math
import os
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

from geolife_inference import api
from geolife_inference.data import GeoLifeSource
from geolife_inference.evaluation import write_json
from geolife_inference.lambda_handler import create_handler
from geolife_inference.postgres import DEFAULT_SNAPSHOT, HISTORY_POINT_LIMIT, PostgresHistory


MODELS = ("heuristic-v1", "dbscan-v1")
CPU_LIMIT = "2"
MEMORY_LIMIT = "2g"
TIMINGS = ("db_ms", "inference_ms", "handler_ms")
HOST_DSN = "host=127.0.0.1 port=55432 dbname=postgres user=geolife"
CONTAINER_DSN = "host=host.docker.internal port=55432 dbname=postgres user=geolife"


def choose_profiles(path):
    with path.open(encoding="utf-8", newline="") as stream:
        rows = [(int(row["input_points"]), row["user_id"]) for row in csv.DictReader(stream)]
    eligible = sorted((count, user_id) for count, user_id in rows if 0 < count <= HISTORY_POINT_LIMIT)
    if not eligible:
        raise ValueError("No saved histories within the serving limit")
    profiles = []
    for label, percentile in (("short", .10), ("typical", .50), ("long", 1.0)):
        count, user_id = eligible[math.ceil(percentile * len(eligible)) - 1]
        profiles.append({"profile": label, "user_id": user_id, "points": count})
    if len({case["user_id"] for case in profiles}) != len(profiles):
        raise ValueError("Three distinct history sizes are required")
    return len(rows), len(eligible), profiles


def measure(history, model, user_id, expected_points, repeats):
    timings = {}
    run_pipeline = api.run_pipeline

    class MeasuredHistory:
        snapshot_id = history.snapshot_id

        def load_user(self, requested_id):
            start = perf_counter()
            points = history.load_user(requested_id)
            timings["db_ms"] = (perf_counter() - start) * 1000
            return points

    def infer(*args, **kwargs):
        start = perf_counter()
        result = run_pipeline(*args, **kwargs)
        timings["inference_ms"] = (perf_counter() - start) * 1000
        return result

    contract_path = Path(os.environ.get("LAMBDA_TASK_ROOT", ".")) / "openapi.yaml"
    invoke = create_handler(MeasuredHistory(), model, contract_path)
    event = {
        "version": "2.0",
        "rawPath": api.HISTORY_INFER_PATH,
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"user_id": user_id}),
    }
    samples = []
    with patch.object(api, "run_pipeline", infer):
        for index in range(repeats + 1):
            timings.clear()
            start = perf_counter()
            response = invoke(event, None)
            timings["handler_ms"] = (perf_counter() - start) * 1000
            body = json.loads(response["body"])
            if response["statusCode"] != 200:
                raise RuntimeError(f"Inference returned HTTP {response['statusCode']}: {body.get('error')}")
            if (body["model_version"] != model or body["config_version"] != "baseline-v1"
                    or body["user_id"] != user_id or body["data_snapshot_id"] != history.snapshot_id
                    or body["diagnostics"]["input_points"] != expected_points):
                raise RuntimeError("Unexpected model, snapshot, or input point count")
            if index:
                samples.append(timings.copy())
    return {"samples": samples, "config_sha256": body["config_sha256"], "pipeline_version": body["pipeline_version"],
            "stays": body["diagnostics"]["stay_events"], "clusters": len(body["locations"]),
            **{f"{field.removesuffix('_ms')}_p50_ms": median(sample[field] for sample in samples)
               for field in TIMINGS}, "handler_max_ms": max(sample["handler_ms"] for sample in samples)}


def worker(model, user_id, point_count, repeats):
    from resource import RUSAGE_SELF, getrusage

    snapshot = os.environ.get("GEOLIFE_SNAPSHOT_ID", DEFAULT_SNAPSHOT)
    history = PostgresHistory(os.environ["GEOLIFE_POSTGRES_DSN"], snapshot)
    result = measure(history, model, user_id, int(point_count), int(repeats))
    result["peak_rss_mib"] = getrusage(RUSAGE_SELF).ru_maxrss / 1024
    print(json.dumps(result, allow_nan=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="geolife-lambda:local")
    parser.add_argument("--dataset", type=Path, default=Path("data/Geolife Trajectories 1.3/Data"))
    parser.add_argument("--metrics", type=Path, default=Path("artifacts/cp2/model-comparison/user-metrics.csv"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/cp2/lambda-local-benchmark.json"))
    parser.add_argument("--snapshot", default=os.environ.get("GEOLIFE_SNAPSHOT_ID", DEFAULT_SNAPSHOT))
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")

    image_id = subprocess.check_output(["docker", "image", "inspect", args.image, "--format", "{{.Id}}"],
                                       text=True).strip()
    population, eligible, profiles = choose_profiles(args.metrics)
    source = GeoLifeSource(args.dataset)
    history = PostgresHistory(os.environ.get("GEOLIFE_POSTGRES_DSN", HOST_DSN), args.snapshot)
    for case in profiles:
        count, _ = history.import_user(source, case["user_id"])
        if count != case["points"]:
            raise RuntimeError(f"Saved CLI and imported point counts differ for user {case['user_id']}")

    container_env = {**os.environ, "GEOLIFE_SNAPSHOT_ID": args.snapshot,
                     "GEOLIFE_POSTGRES_DSN": os.environ.get("GEOLIFE_CONTAINER_POSTGRES_DSN", CONTAINER_DSN)}
    worker_source = Path(__file__).read_text(encoding="utf-8")
    rows = []
    for case in profiles:
        for model in MODELS:
            print(f"Measuring {case['profile']} | user={case['user_id']} | {case['points']} points | {model}",
                  flush=True)
            command = ["docker", "run", "--rm", "-i", "--platform", "linux/amd64", "--cpus", CPU_LIMIT,
                       "--memory", MEMORY_LIMIT, "-e", "GEOLIFE_POSTGRES_DSN", "-e", "GEOLIFE_SNAPSHOT_ID",
                       "--entrypoint", "/var/lang/bin/python3.12", image_id, "-", "--worker", model,
                       case["user_id"], str(case["points"]), str(args.repeats)]
            completed = subprocess.run(command, env=container_env, input=worker_source,
                                       encoding="utf-8", stdout=subprocess.PIPE, check=True)
            result = json.loads(completed.stdout)
            rows.append({**case, "model_version": model, **result})
            print(f"  p50 DB={result['db_p50_ms']:.1f} ms, inference={result['inference_p50_ms']:.1f} ms, "
                  f"handler={result['handler_p50_ms']:.1f} ms, peak RSS={result['peak_rss_mib']:.1f} MiB",
                  flush=True)
    write_json(args.output, {"image_id": image_id, "snapshot": args.snapshot, "cpus": int(CPU_LIMIT),
                             "memory_limit": MEMORY_LIMIT, "warmups": 1, "repeats": args.repeats,
                             "population_users": population, "eligible_users": eligible, "results": rows})
    print(f"Saved {args.output}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--worker"]:
        worker(*sys.argv[2:])
    else:
        main()
