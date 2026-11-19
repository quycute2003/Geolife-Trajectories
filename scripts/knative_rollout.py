"""Stage, measure, promote, or roll back the local GeoLife Knative release."""

import argparse
import json
import math
import subprocess
from time import monotonic, sleep
from urllib.parse import urlsplit

from check_local_api import call_api
from geolife_inference.api import HISTORY_INFER_PATH


NAMESPACE = "geolife-knative"
SERVICE = "geolife-inference"
MODELS = {"blue": "heuristic-v1", "green": "dbscan-v1"}
SNAPSHOT = "geolife-1.3-demo-v1"


def traffic_targets(weights):
    return [{"tag": track, "revisionName": f"{SERVICE}-{track}", "percent": percent}
            for track, percent in weights.items()]


def traffic_signature(targets):
    return {(target.get("tag"), target["revisionName"]): target.get("percent", 0) for target in targets}


def wait_for_traffic(kubectl, targets):
    expected = traffic_signature(targets)
    deadline = monotonic() + 120
    while monotonic() < deadline:
        route = json.loads(kubectl("get", "route", SERVICE, "-o", "json", "--request-timeout=10s"))
        status = route.get("status", {})
        ready = any(c["type"] == "Ready" and c["status"] == "True" for c in status.get("conditions", []))
        if ready and traffic_signature(status.get("traffic", [])) == expected:
            return status
        sleep(1)
    raise SystemExit("Knative Route did not become ready with the requested traffic weights.")


def sample(status, port, count, warmup=0, *, snapshot=SNAPSHOT):
    host = urlsplit(status["url"]).netloc
    expected = {MODELS[target["tag"]]: target["percent"] for target in status["traffic"] if target.get("percent", 0)}
    timings = {model: [] for model in expected}
    failures = 0
    for index in range(warmup + count):
        started = monotonic()
        try:
            code, _, result = call_api(port, HISTORY_INFER_PATH, {"user_id": "101"}, host_header=host)
            model = result.get("model_version")
            if code != 200 or model not in timings or result.get("data_snapshot_id") != snapshot:
                raise ValueError(f"unexpected response (HTTP {code}, model {model})")
        except (OSError, ValueError) as error:
            if index < warmup:
                raise SystemExit(f"Warmup failed: {error}") from error
            failures += 1
            if failures == 1:
                print(f"First request failure: {error}", flush=True)
        else:
            duration = (monotonic() - started) * 1000
            if index < warmup:
                print(f"Warmup {index + 1}/{warmup}: {model}, {duration:.0f} ms (excluded)", flush=True)
            else:
                timings[model].append(duration)

    print(f"{count} requests to {host}, {failures} failures")
    for model, durations in timings.items():
        observed = len(durations)
        latency = f", p95 {sorted(durations)[math.ceil(0.95 * observed) - 1]:.0f} ms" if observed else ""
        print(f"{model}: {observed}/{count} ({observed / count:.1%}), configured {expected[model]}%{latency}")
    if failures or not all(timings.values()):
        raise SystemExit("The sample had failures or did not reach every revision with nonzero traffic.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "canary", "promote", "rollback", "sample"))
    parser.add_argument("--context", default="docker-desktop")
    parser.add_argument("--namespace", default=NAMESPACE, help="Namespace of the GeoLife Knative Service")
    parser.add_argument("--port", type=int, default=18080, help="Local Kourier port-forward port")
    parser.add_argument("--requests", type=int, default=100, help="Number of requests for sample")
    parser.add_argument("--track", choices=("live", "blue", "green"), default="live",
                        help="Sample the live route or a tagged revision")
    parser.add_argument("--warmup", type=int, default=0, help="Successful requests to exclude before measuring")
    parser.add_argument("--snapshot", default=SNAPSHOT, help="Expected data snapshot ID for sample")
    args = parser.parse_args()
    if args.requests < 1:
        parser.error("--requests must be positive")
    if args.warmup < 0:
        parser.error("--warmup must be nonnegative")

    def kubectl(*command):
        return subprocess.run(["kubectl", "--context", args.context, "-n", args.namespace, *command],
                              stdout=subprocess.PIPE, text=True, encoding="utf-8", check=True).stdout

    def patch(spec):
        kubectl("patch", "ksvc", SERVICE, "--type", "merge", "--patch", json.dumps({"spec": spec}))

    def wait_for_revision(track):
        revision = f"revision/{SERVICE}-{track}"
        kubectl("wait", "--for=create", revision, "--timeout=120s")
        kubectl("wait", "--for=condition=Ready", revision, "--timeout=180s")

    service = json.loads(kubectl("get", "ksvc", SERVICE, "-o", "json"))
    if args.action == "sample":
        status = wait_for_traffic(kubectl, service["spec"]["traffic"])
        if args.track != "live":
            target = next((t for t in status["traffic"] if t.get("tag") == args.track), None)
            if target is None:
                raise SystemExit(f"No {args.track} tag. Run stage to restore both preview URLs.")
            status = {"url": target["url"], "traffic": [{**target, "percent": 100}]}
        sample(status, args.port, args.requests, args.warmup, snapshot=args.snapshot)
        return

    if args.action == "stage":
        template = service["spec"]["template"]
        containers = template["spec"]["containers"]
        for env in containers[0]["env"]:
            if env["name"] == "MODEL_VERSION":
                env["value"] = MODELS["green"]
        patch({"template": {"metadata": {"name": f"{SERVICE}-green"}, "spec": {"containers": containers}}})
    wait_for_revision("blue" if args.action == "rollback" else "green")
    weights = {"stage": {"blue": 100, "green": 0}, "canary": {"blue": 90, "green": 10},
               "promote": {"blue": 0, "green": 100}, "rollback": {"blue": 100}}[args.action]
    targets = traffic_targets(weights)
    started = monotonic()
    patch({"traffic": targets})
    status = wait_for_traffic(kubectl, targets)
    print(f"{status['url']} ready after {monotonic() - started:.1f}s")
    for target in status["traffic"]:
        print(f"{target['tag']}: {target.get('percent', 0)}% ({target['url']})")


if __name__ == "__main__":
    main()
