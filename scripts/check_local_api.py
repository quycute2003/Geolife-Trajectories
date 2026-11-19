"""Verify the local API, CLI parity, and PostgreSQL history edge cases."""
import argparse
from functools import partial
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4
from wsgiref.simple_server import make_server

import pandas as pd

from geolife_inference.api import HEALTH_PATH, HISTORY_INFER_PATH, INFER_PATH, VERSION_PATH, create_app
from geolife_inference.config import Config
from geolife_inference.data import GeoLifeSource
from geolife_inference.postgres import DEFAULT_SNAPSHOT, HISTORY_POINT_LIMIT, PostgresHistory


LAMBDA_INVOCATION_PATH = "/2015-03-31/functions/function/invocations"


def call_api(port, path, data=None, *, base_path="", host_header=None):
    request = Request(f"http://127.0.0.1:{port}{base_path}{path}")
    if host_header:
        request.add_header("Host", host_header)
    if data is not None:
        request.data = json.dumps(data, allow_nan=False).encode("utf-8")
        request.add_header("Content-Type", "application/json")
    try:
        response = build_opener(ProxyHandler({})).open(request, timeout=60)
    except HTTPError as error:
        response = error
    with response:
        cache_control = ",".join(response.headers.get_all("Cache-Control", []))
        return response.status, cache_control, json.load(response)


def has_no_store(cache_control):
    return any(directive.strip().lower() == "no-store" for directive in (cache_control or "").split(","))


def call_lambda(port, path, data=None):
    event = {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"http": {"method": "GET" if data is None else "POST"}},
        "isBase64Encoded": False,
    }
    if data is not None:
        event["headers"] = {"content-type": "application/json"}
        event["body"] = json.dumps(data, allow_nan=False)
    status, _, result = call_api(port, LAMBDA_INVOCATION_PATH, event)
    if status != 200 or "statusCode" not in result:
        raise SystemExit(f"Lambda runtime invocation failed (HTTP {status}): {result.get('errorMessage', 'no proxy response')}")
    return result["statusCode"], result["headers"].get("cache-control"), json.loads(result["body"])


def check_postgres_edge_cases(dsn, dataset, expected):
    snapshot = f"local-edge-check-{uuid4().hex}"
    history = PostgresHistory(dsn, snapshot)
    source = GeoLifeSource(dataset)
    user_id = expected["user_id"]
    point_count = expected["diagnostics"]["input_points"]
    count_sql = "SELECT count(*) FROM geolife_gps_points WHERE snapshot_id = %s AND user_id = %s"
    short_user, long_user = "001", "998"

    with history.driver.connect(dsn, connect_timeout=5, autocommit=True) as connection:
        first_import = history.import_user(source, user_id)
        try:
            first_count = connection.execute(count_sql, (snapshot, user_id)).fetchone()[0]
            repeat_import = history.import_user(source, user_id)
            repeat_count = connection.execute(count_sql, (snapshot, user_id)).fetchone()[0]
            if (first_import != (point_count, True) or repeat_import != (point_count, False)
                    or first_count != point_count or repeat_count != point_count):
                raise SystemExit(f"Repeat import check failed: {first_import=}, {repeat_import=}, "
                                 f"{first_count=}, {repeat_count=}.")
            print(f"PASS repeat import: user={user_id}, PostgreSQL rows={first_count} -> {repeat_count}.")

            with TemporaryDirectory(prefix="geolife-short-history-") as directory:
                trajectory = Path(directory) / short_user / "Trajectory" / "short.plt"
                trajectory.parent.mkdir(parents=True)
                trajectory.write_text("header\n" * 6 + "39.9,116.3,0,-777,0,2024-01-01,00:00:00\n",
                                      encoding="utf-8")
                history.import_user(GeoLifeSource(directory), short_user)

            with connection.transaction():
                connection.execute("INSERT INTO geolife_histories VALUES (%s, %s, %s)",
                                   (snapshot, long_user, "synthetic-limit-check"))
                connection.execute("""
                    INSERT INTO geolife_gps_points
                        (snapshot_id, user_id, trajectory_id, source_row, latitude, longitude, altitude_m, recorded_at)
                    SELECT %s, %s, 'synthetic', source_row, 39.9, 116.3, 0,
                           TIMESTAMPTZ '2024-01-01T00:00:00Z' + source_row * INTERVAL '1 second'
                    FROM generate_series(1, %s) AS fixture(source_row)
                    """, (snapshot, long_user, HISTORY_POINT_LIMIT + 1))

            with make_server("127.0.0.1", 0, create_app(history=history)) as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    status, _, short = call_api(server.server_port, HISTORY_INFER_PATH, {"user_id": short_user})
                    if status != 200 or short.get("user_id") != short_user or short.get("data_snapshot_id") != snapshot:
                        raise SystemExit(f"Leading-zero user ID check failed (HTTP {status}).")
                    print(f"PASS leading-zero user ID: HTTP 200, user_id={short['user_id']!r}.")
                    if (short["diagnostics"]["input_points"] != 1
                            or short["home"]["status"] != "unknown" or short["office"]["status"] != "unknown"):
                        raise SystemExit("Short history check failed: expected one point and unknown roles.")
                    print("PASS short history: 1 point, home=unknown, office=unknown.")

                    status, _, long = call_api(server.server_port, HISTORY_INFER_PATH, {"user_id": long_user})
                    if status != 422 or long.get("error", {}).get("code") != "history_too_large":
                        raise SystemExit(f"History limit check failed (HTTP {status}).")
                    print(f"PASS history limit: {HISTORY_POINT_LIMIT + 1} points, HTTP 422 history_too_large.")
                finally:
                    server.shutdown()
                    worker.join()
        finally:
            with connection.transaction():
                connection.execute("DELETE FROM geolife_gps_points WHERE snapshot_id = %s", (snapshot,))
                connection.execute("DELETE FROM geolife_histories WHERE snapshot_id = %s", (snapshot,))
    print("All PostgreSQL edge cases passed. Test snapshot removed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int)
    parser.add_argument("--base-path", default="", help="HTTP prefix, for example a Kubernetes Service proxy path")
    parser.add_argument("--host-header", help="HTTP Host header for a local virtual host")
    parser.add_argument("--dataset", type=Path, default=Path("data/Geolife Trajectories 1.3/Data"))
    parser.add_argument("--expected", type=Path, default=Path("artifacts/pipeline/dbscan-v1/101-dbscan-v1.json"))
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--history", "--postgres", dest="history", action="store_true",
                       help="Verify v2 with a user_id-only request")
    modes.add_argument("--lambda-runtime", action="store_true", help="Verify v2 through the Lambda Runtime Interface Emulator")
    modes.add_argument("--postgres-edge-cases", action="store_true",
                       help="Test repeated import, leading-zero ID, short history, and the point limit")
    parser.add_argument("--snapshot", default=os.environ.get("GEOLIFE_SNAPSHOT_ID", DEFAULT_SNAPSHOT))
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    if args.postgres_edge_cases:
        dsn = os.environ.get("GEOLIFE_POSTGRES_DSN")
        if not dsn:
            parser.error("Set GEOLIFE_POSTGRES_DSN before running PostgreSQL edge checks.")
        check_postgres_edge_cases(dsn, args.dataset, expected)
        return

    user_id = expected["user_id"]
    port = args.port if args.port is not None else (9000 if args.lambda_runtime else 8000)
    call = (partial(call_lambda, port) if args.lambda_runtime else
            partial(call_api, port, base_path=args.base_path.rstrip("/"), host_header=args.host_header))
    history_api = args.history or args.lambda_runtime

    status, _, health = call(HEALTH_PATH)
    if status != 200 or health != {"status": "ok"}:
        raise SystemExit(f"Health check failed (HTTP {status}).")
    print("HTTP 200, /health: ok.")

    status, cache, version = call(VERSION_PATH)
    version_keys = ("model_version", "pipeline_version", "config_version", "config_sha256")
    if status != 200 or not has_no_store(cache) or version.keys() != set(version_keys):
        raise SystemExit(f"Version metadata check failed (HTTP {status}).")

    payload = {"user_id": user_id}
    if history_api:
        path = HISTORY_INFER_PATH
    else:
        path = INFER_PATH
        source = GeoLifeSource(args.dataset).load_user(user_id)
        points = [
            {"trajectory_id": row.trajectory_id, "latitude": row.latitude, "longitude": row.longitude,
             "altitude_m": None if pd.isna(row.altitude_m) else row.altitude_m, "timestamp": row.timestamp.isoformat()}
            for row in source.itertuples(index=False)
        ]
        payload.update(model_version=expected["model_version"], config=expected["config"], points=points)
    status, cache, actual = call(path, payload)
    if status != 200 or not has_no_store(cache):
        raise SystemExit(f"{path} expected 200 and no-store, received {status} and {cache}: {actual.get('error')}")
    default_status, default_result = 200, actual
    if not history_api:
        default_status, _, default_result = call(INFER_PATH, {"user_id": "synthetic-user", "points": []})
    if default_status != 200 or version != {key: default_result[key] for key in version_keys}:
        raise SystemExit(f"Version metadata did not match default inference (HTTP {default_status}).")
    print(f"HTTP 200, /version: {version['model_version']}, pipeline {version['pipeline_version']}, "
          f"config {version['config_version']} matches default inference.")

    if history_api and actual.pop("data_snapshot_id", None) != args.snapshot:
        raise SystemExit("The response did not use the expected GPS snapshot.")
    # CP1 snapshots predate these fields. Compare all original fields, including the UUID.
    for key, value in Config(**expected["config"]).version_metadata().items():
        expected.setdefault(key, value)
    different = sorted(key for key in actual.keys() | expected.keys() if actual.get(key) != expected.get(key))
    if actual != expected:
        raise SystemExit(f"HTTP and CLI results differ in top-level fields: {', '.join(different)}")
    print(f"HTTP 200, full CLI match: user={user_id}, points={actual['diagnostics']['input_points']}, "
          f"stays={actual['diagnostics']['stay_events']}, locations={len(actual['locations'])}, "
          f"home={actual['home']['status']}, office={actual['office']['status']}.")
    if history_api:
        for invalid, expected_status, code in [
            ({"user_id": "999"}, 404, "user_not_found"),
            ({"user_id": int(user_id)}, 422, "validation_error"),
        ]:
            status, _, body = call(path, invalid)
            if status != expected_status or body.get("error", {}).get("code") != code:
                raise SystemExit(f"Expected HTTP {expected_status} ({code}), received {status}.")
        print("HTTP checks passed for absent user and numeric user_id.")
        return

    # The last two fixes are about 119 m from the first, so only the 150 m preset yields a stay.
    synthetic_points = [
        {"trajectory_id": "t", "latitude": 39.9, "longitude": longitude,
         "timestamp": f"2024-01-01T00:{minute:02}:00Z"}
        for minute, longitude in [(0, 116.3), (5, 116.3014), (10, 116.3014)]
    ]
    for preset, radius, stays in [("baseline-v1", 100.0, 0), ("stay150-experiment-v1", 150.0, 1)]:
        status, cache, body = call(INFER_PATH, {"user_id": "synthetic-user", "points": synthetic_points,
                                               "config_version": preset})
        if (status != 200 or not has_no_store(cache) or body.get("config_version") != preset
                or body["config"]["distance_m"] != radius or body["diagnostics"]["stay_events"] != stays):
            raise SystemExit(f"{preset} expected HTTP 200, radius={radius} and stays={stays}; received HTTP {status}.")
        print(f"HTTP 200, {preset}: radius={radius} m, stays={stays}.")

    invalid_point = points[0].copy()
    del invalid_point["latitude"]
    status, cache, body = call(INFER_PATH, {"user_id": user_id, "points": [invalid_point]})
    error = body.get("error", {})
    if (status != 422 or not has_no_store(cache) or error.get("code") != "validation_error"
            or "/points/0/latitude" not in {item["path"] for item in error.get("details", [])}):
        raise SystemExit(f"Missing latitude did not produce the expected validation error (HTTP {status}).")
    print("HTTP 422, validation_error at /points/0/latitude.")


if __name__ == "__main__":
    main()
