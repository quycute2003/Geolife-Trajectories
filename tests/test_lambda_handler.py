import base64
import json
from pathlib import Path

import pytest

from geolife_inference import lambda_handler
from geolife_inference.api import HEALTH_PATH, HISTORY_INFER_PATH, INFER_PATH, VERSION_PATH
from geolife_inference.config import load_config
from geolife_inference.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("model,clusters", [("heuristic-v1", 1), ("dbscan-v1", 0)])
def test_lambda_handler_uses_model_config_and_user_id(make_points, monkeypatch, model, clusters):
    points = make_points([0, 5, 10], user="101")

    class History:
        snapshot_id = "fixture"

        def load_user(self, user_id):
            return points if user_id == "101" else None

    def open_history(dsn, snapshot_id):
        assert dsn == "dbname=fixture" and snapshot_id == History.snapshot_id
        return History()

    monkeypatch.setenv("LAMBDA_TASK_ROOT", str(ROOT))
    monkeypatch.setenv("MODEL_VERSION", model)
    monkeypatch.setenv("GEOLIFE_SNAPSHOT_ID", History.snapshot_id)
    monkeypatch.setenv("GEOLIFE_POSTGRES_DSN", "dbname=fixture")
    monkeypatch.setattr(lambda_handler, "PostgresHistory", open_history)
    monkeypatch.setattr(lambda_handler, "configured_handler", lambda_handler.configured_handler.__wrapped__)

    def invoke(path, payload=None, *, encoded=False, version="2.0"):
        event = {"version": version, "rawPath": path, "requestContext": {
            "http": {"method": "GET" if payload is None else "POST"}}}
        if payload is not None:
            body = json.dumps(payload).encode()
            event.update(headers={"Content-Type": "application/json"},
                         body=(base64.b64encode(body) if encoded else body).decode(),
                         isBase64Encoded=encoded)
        result = lambda_handler.handler(event, None)
        assert result["headers"]["cache-control"] == "no-store"
        assert result["isBase64Encoded"] is False
        return result["statusCode"], json.loads(result["body"])

    assert invoke(HEALTH_PATH) == (200, {"status": "ok"})
    status, version = invoke(VERSION_PATH)
    assert status == 200 and version["model_version"] == model
    config = load_config()
    assert version["config_sha256"] == config.version_metadata()["config_sha256"]
    status, result = invoke(HISTORY_INFER_PATH, {"user_id": "101"}, encoded=True)
    assert status == 200 and result.pop("data_snapshot_id") == History.snapshot_id
    assert result == run_pipeline(points, "101", config, model).result
    assert len(result["locations"]) == clusters
    assert invoke(HISTORY_INFER_PATH, {"user_id": "999"})[0] == 404
    assert invoke(HISTORY_INFER_PATH, {"user_id": "101", "model_version": model})[0] == 422
    assert invoke(INFER_PATH, {"user_id": "101", "points": []})[0] == 404
    assert invoke(HISTORY_INFER_PATH, {"user_id": "101"}, version="1.0")[0] == 400
