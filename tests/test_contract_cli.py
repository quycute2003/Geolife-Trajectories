from copy import deepcopy
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
from io import BytesIO
import json

import pandas as pd
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

from geolife_inference.api import HISTORY_INFER_PATH, INFER_PATH, create_app
from geolife_inference.cli import main
from geolife_inference.config import load_config
from geolife_inference.geo import haversine_m
from geolife_inference.pipeline import run_pipeline
from geolife_inference.postgres import HistoryTooLarge
from geolife_inference.sqlite_history import SQLiteHistory
from scripts import export_sqlite_snapshot

ROOT = Path(__file__).resolve().parents[1]


def validator(name):
    spec = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    schema = {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_openapi_and_embedded_request_error_examples_valid():
    spec = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    validate(spec)
    post = spec["paths"]["/v1/locations/infer"]["post"]
    for example in post["requestBody"]["content"]["application/json"]["examples"].values():
        validator("InferenceRequest").validate(example["value"])
    for response in post["responses"].values():
        media = response["content"]["application/json"]
        example = media.get("example")
        if example:
            validator("ErrorResponse").validate(example)
        for example in media.get("examples", {}).values():
            validator("InferenceResponse").validate(example["value"])


@pytest.mark.parametrize("mutation", [
    {"latitude": 91}, {"longitude": -181}, {"timestamp": "2024-01-01T00:00:00"},
    {"timestamp": "2024-01-01T08:00:00+08:00"}, {"timestamp": "2024-13-01T00:00:00Z"},
    {"latitude": True}, {"extra": 1},
])
def test_contract_rejects_bad_points(mutation):
    point = {"trajectory_id": "t", "latitude": 0, "longitude": 0, "timestamp": "2024-01-01T00:00:00Z"}
    point.update(mutation)
    assert list(validator("InferenceRequest").iter_errors({"user_id": "u", "points": [point]}))


def test_contract_rejects_unsupported_model_and_config():
    for extra in ({"model_version": "other"}, {"config": {"eps_m": -1}}, {"config": {"unknown": 1}}):
        assert list(validator("InferenceRequest").iter_errors({"user_id": "u", "points": [], **extra}))


def test_history_inference_preserves_leading_zeroes_and_enforces_its_contract(make_points):
    class History:
        snapshot_id = "synthetic"

        def load_user(self, user_id):
            if user_id == "001":
                return make_points([0, 5, 10], user=user_id)
            if user_id == "002":
                raise HistoryTooLarge
            return None

    app = create_app(ROOT / "openapi.yaml", history=History())

    def post(payload):
        body = json.dumps(payload).encode()
        environ = {"PATH_INFO": HISTORY_INFER_PATH, "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": str(len(body)), "wsgi.input": BytesIO(body)}
        statuses = []
        result = app(environ, lambda status, headers: statuses.append(int(status.split()[0])))
        return statuses[0], json.loads(b"".join(result))

    status, result = post({"user_id": "001"})
    assert status == 200
    assert result["user_id"] == "001"
    assert result["data_snapshot_id"] == "synthetic"
    assert result["home"]["status"] == result["office"]["status"] == "unknown"
    validator("HistoryInferenceResponse").validate(result)

    for payload, expected_status, code in [
        ({"user_id": "002"}, 422, "history_too_large"),
        ({"user_id": "999"}, 404, "user_not_found"),
        ({"user_id": 1}, 422, "validation_error"),
        ({"user_id": "001", "points": []}, 422, "validation_error"),
    ]:
        status, error = post(payload)
        assert (status, error["error"]["code"]) == (expected_status, code)
        validator("ErrorResponse").validate(error)


@pytest.mark.parametrize("model", ["heuristic-v1", "dbscan-v1"])
def test_sqlite_full_snapshot_serves_long_history_without_truncation(tmp_path, monkeypatch, model):
    dataset = tmp_path / "dataset"
    for user, point_count in (("001", 3), ("002", 1)):
        trajectory = dataset / user / "Trajectory" / "t.plt"
        trajectory.parent.mkdir(parents=True)
        rows = [f"39.9,116.3,0,100,0,2024-01-01,00:{minute:02d}:00\n" for minute in (0, 5, 10)[:point_count]]
        trajectory.write_text("header\n" * 6 + "".join(rows), encoding="utf-8")
    cli = tmp_path / "cli"
    for version in ("heuristic-v1", "dbscan-v1"):
        assert main(["infer", "--dataset", str(dataset), "--model", version, "--output", str(cli / version)]) == 0
    monkeypatch.setattr(export_sqlite_snapshot, "HISTORY_POINT_LIMIT", 2)
    monkeypatch.setattr("geolife_inference.sqlite_history.HISTORY_POINT_LIMIT", 2)
    snapshot = tmp_path / "full.sqlite3"
    source = export_sqlite_snapshot.GeoLifeSource(dataset)
    export_sqlite_snapshot.export_snapshot(source, source.by_user, "full-test", snapshot, cli_results=cli)
    history = SQLiteHistory(snapshot)
    with pytest.raises(HistoryTooLarge):
        history.load_user("001")
    assert history.load_precomputed("001", model, "stale-config") is None
    app = create_app(ROOT / "openapi.yaml", history=history, model_version=model)
    for user in ("001", "002"):
        request = json.dumps({"user_id": user}).encode()
        environ = {"PATH_INFO": HISTORY_INFER_PATH, "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": str(len(request)), "wsgi.input": BytesIO(request)}
        statuses = []
        response = app(environ, lambda status, headers: statuses.append(int(status.split()[0])))
        expected = json.loads((cli / model / f"{user}-{model}.json").read_text(encoding="utf-8"))
        assert statuses == [200]
        result = json.loads(b"".join(response))
        assert result == {**expected, "data_snapshot_id": "full-test"}
        validator("HistoryInferenceResponse").validate(result)


@pytest.mark.parametrize("model", ["heuristic-v1", "dbscan-v1"])
@pytest.mark.parametrize("case", ["home-and-office", "home-only", "short-history"])
def test_release_location_expectations(make_points, model, case):
    home = (39.9000, 116.3000)
    office = (39.9300, 116.3400)
    tolerance_m = 25
    local_zone = ZoneInfo("Asia/Shanghai")
    days = (1, 2, 3, 8, 9)
    expected = {"home": home if case != "short-history" else None,
                "office": office if case == "home-and-office" else None}
    frames = []
    for role, coords in expected.items():
        if coords is None:
            continue
        hour = 22 if role == "home" else 9
        frames.extend(make_points(range(0, 121, 5), *coords, user="901", trajectory=f"{role}-{day}",
                                  start=datetime(2024, 1, day, hour, 30, tzinfo=local_zone))
                      for day in days)
    if case == "short-history":
        frames.append(make_points([0, 5, 10], *home, user="901", trajectory="short",
                                  start=datetime(2024, 1, 1, 22, 30, tzinfo=local_zone)))
    points = [
        {"trajectory_id": row.trajectory_id, "latitude": row.latitude, "longitude": row.longitude,
         "altitude_m": row.altitude_m, "timestamp": row.timestamp.tz_convert("UTC").isoformat()}
        for row in pd.concat(frames).itertuples(index=False)
    ]
    body = json.dumps({"user_id": "901", "model_version": model, "config_version": "baseline-v1",
                       "points": points}).encode()
    app = create_app(ROOT / "openapi.yaml")
    environ = {"PATH_INFO": INFER_PATH, "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": str(len(body)), "wsgi.input": BytesIO(body)}
    statuses = []
    response = app(environ, lambda status, headers: statuses.append(int(status.split()[0])))
    assert statuses == [200]
    result = json.loads(b"".join(response))
    validator("InferenceResponse").validate(result)
    assert result["model_version"] == model
    assert result["config_version"] == "baseline-v1"
    for role, coords in expected.items():
        decision = result[role]
        if coords is None:
            assert decision["status"] == "unknown" and decision["candidate"] is None
        else:
            assert decision["status"] == "predicted"
            candidate = decision["candidate"]
            assert haversine_m(*coords, candidate["latitude"], candidate["longitude"]) <= tolerance_m


def test_http_config_versions_select_the_expected_stay_radius():
    app = create_app(ROOT / "openapi.yaml")
    points = [
        {"trajectory_id": "t", "latitude": 39.9, "longitude": longitude,
         "timestamp": f"2024-01-01T00:{minute:02}:00Z"}
        for minute, longitude in [(0, 116.3), (5, 116.3014), (10, 116.3014)]
    ]

    def post(**options):
        body = json.dumps({"user_id": "u", "points": points, **options}).encode()
        environ = {"PATH_INFO": INFER_PATH, "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": str(len(body)), "wsgi.input": BytesIO(body)}
        statuses = []
        result = app(environ, lambda status, headers: statuses.append(int(status.split()[0])))
        return statuses[0], json.loads(b"".join(result))

    status, baseline = post()
    assert status == 200
    assert post(config_version="baseline-v1") == (200, baseline)
    assert baseline["config_version"] == "baseline-v1"
    assert baseline["config"] == load_config(ROOT / "configs/baseline.toml").to_dict()
    assert baseline["config_sha256"] == "a1e6ce4aac7398df9df9f66d768fcafee50cea241f94bc48654e4717ea5dc6ea"
    assert baseline["diagnostics"]["stay_events"] == 0

    status, experiment = post(config_version="stay150-experiment-v1")
    assert status == 200
    assert experiment["config_version"] == "stay150-experiment-v1"
    assert experiment["config"] == {**baseline["config"], "distance_m": 150.0}
    assert experiment["config_sha256"] == "1c8ede55ab36c46879007f1fbbffe2fa84b01b2e559c031f9cd692dfd73570fb"
    assert experiment["diagnostics"]["stay_events"] == 1
    assert experiment["inference_id"] != baseline["inference_id"]
    assert post(config={"distance_m": 150.0}) == (200, experiment)
    assert post(config={"distance_m": 150})[1]["config_sha256"] == experiment["config_sha256"]
    for result in (baseline, experiment):
        validator("InferenceResponse").validate(result)

    status, custom = post(config={"distance_m": 125})
    assert status == 200 and custom["config_version"] == "custom"
    assert custom["config_sha256"] not in {baseline["config_sha256"], experiment["config_sha256"]}
    validator("InferenceResponse").validate(custom)

    for options in ({"config_version": "custom"}, {"config_version": "baseline-v1", "config": {}}):
        status, body = post(**options)
        assert status == 422
        validator("ErrorResponse").validate(body)


@pytest.mark.parametrize("model", ["dbscan-v1", "heuristic-v1"])
def test_actual_outputs_match_contract_and_serialize(make_points, model):
    frames = [make_points(list(range(0, 121, 5)), trajectory=f"t{day}",
                         start=datetime(2024, 1, day, 0, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc))
              for day in (1, 2, 3, 8, 9)]
    for points in (make_points([]), make_points([0, 5, 10]), pd.concat(frames)):
        result = run_pipeline(points, "000", model_version=model).result
        validator("InferenceResponse").validate(result)
        assert json.loads(json.dumps(result, allow_nan=False)) == result
        if result["home"]["status"] == "predicted":
            bad = deepcopy(result)
            bad["home"]["candidate"] = None
            assert list(validator("InferenceResponse").iter_errors(bad))


def test_cli_end_to_end_on_synthetic_directory(tmp_path, capsys):
    source = tmp_path / "Data/000/Trajectory"
    source.mkdir(parents=True)
    text = "header\n" * 6
    text += "39,116,0,-777,0,2024-01-01,00:00:00\n39,116,0,100,0,2024-01-01,00:05:00\n39,116,0,100,0,2024-01-01,00:10:00\n"
    (source / "t.plt").write_text(text, encoding="utf-8")
    output = tmp_path / "out"
    assert main(["infer", "--dataset", str(tmp_path / "Data"), "--users", "000", "--output", str(output)]) == 0
    result = json.loads((output / "000-dbscan-v1.json").read_text(encoding="utf-8"))
    assert result["diagnostics"]["stay_events"] == 1
    assert result["home"]["status"] == "unknown"
    validator("InferenceResponse").validate(result)

    experiment_dir = tmp_path / "experiment"
    assert main(["infer", "--dataset", str(tmp_path / "Data"), "--output", str(experiment_dir),
                 "--config-version", "stay150-experiment-v1"]) == 0
    experiment = json.loads((experiment_dir / "000-dbscan-v1.json").read_text(encoding="utf-8"))
    audit = json.loads((experiment_dir / "run-audit.json").read_text(encoding="utf-8"))
    assert experiment["config_version"] == "stay150-experiment-v1"
    assert experiment["config"]["distance_m"] == 150.0
    for key in ("model_version", "pipeline_version", "config_version", "config_sha256", "config"):
        assert audit[key] == experiment[key]
    validator("InferenceResponse").validate(experiment)
    with pytest.raises(SystemExit) as exc:
        main(["infer", "--dataset", str(tmp_path / "Data"), "--users", "missing"])
    assert exc.value.code == 2


def test_cli_defaults_to_all_users_and_exports_audit(tmp_path):
    for user in ["000", "001"]:
        source = tmp_path / "Data" / user / "Trajectory"
        source.mkdir(parents=True)
        text = "header\n" * 6
        text += "39,116,0,100,0,2024-01-01,00:00:00\n"
        text += "39.00001,116,0,100,0,2024-01-01,00:00:00\n"
        text += "39,116,0,100,0,2024-01-01,00:05:00\n39,116,0,100,0,2024-01-01,00:10:00\n"
        (source / "t.plt").write_text(text, encoding="utf-8")
    output = tmp_path / "out"
    assert main(["infer", "--dataset", str(tmp_path / "Data"), "--output", str(output), "--audit-points"]) == 0
    audit = json.loads((output / "run-audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "completed" and audit["scope"] == "full_dataset"
    assert audit["completed_users"] == audit["expected_users"] == ["000", "001"]
    assert audit["processed_trajectory_files"] == audit["expected_trajectory_files"] == 2
    assert audit["input_points"] == 8 and audit["output_points"] == 6
    for user in audit["completed_users"]:
        result = json.loads((output / f"{user}-dbscan-v1.json").read_text(encoding="utf-8"))
        assert result["diagnostics"]["conflict_policy"] == "spatial_vote_context_v2"
        assert result["diagnostics"]["merged_extra_points"] == 1
        trace = pd.read_csv(output / f"{user}-dbscan-v1-conflicts.csv")
        assert len(trace) == 2 and trace["decision"].eq("mean_merged").all()
        assert (output / f"{user}-dbscan-v1-removed.csv").is_file()
        validator("InferenceResponse").validate(result)


def test_cli_failure_does_not_report_full_dataset_completed(tmp_path):
    for user, content in [("000", "39,116,0,100,0,2024-01-01,00:00:00\n"), ("001", "bad,field,count\n")]:
        source = tmp_path / "Data" / user / "Trajectory"
        source.mkdir(parents=True)
        (source / "t.plt").write_text("header\n" * 6 + content, encoding="utf-8")
    output = tmp_path / "out"
    with pytest.raises(SystemExit):
        main(["infer", "--dataset", str(tmp_path / "Data"), "--output", str(output)])
    audit = json.loads((output / "run-audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "failed" and audit["completed_users"] == ["000"]
    assert audit["processed_trajectory_files"] < audit["expected_trajectory_files"]


def test_cli_internal_failure_updates_run_audit(tmp_path, monkeypatch):
    source = tmp_path / "Data/000/Trajectory"
    source.mkdir(parents=True)
    (source / "t.plt").write_text("header\n" * 6 + "39,116,0,100,0,2024-01-01,00:00:00\n", encoding="utf-8")
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic internal failure")
    monkeypatch.setattr("geolife_inference.cli.run_pipeline", fail)
    output = tmp_path / "out"
    with pytest.raises(RuntimeError, match="synthetic internal failure"):
        main(["infer", "--dataset", str(tmp_path / "Data"), "--output", str(output)])
    audit = json.loads((output / "run-audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "failed" and audit["completed_users"] == []
