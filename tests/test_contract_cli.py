from copy import deepcopy
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
import json

import pandas as pd
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

from geolife_inference.cli import main
from geolife_inference.pipeline import run_pipeline

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
    with pytest.raises(SystemExit) as exc:
        main(["infer", "--dataset", str(tmp_path / "Data"), "--users", "missing"])
    assert exc.value.code == 2
