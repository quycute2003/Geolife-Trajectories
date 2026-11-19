"""HTTP adapter for the GeoLife inference pipeline."""
import argparse
from http import HTTPStatus
from itertools import islice
import json
import logging
import math
import os
from pathlib import Path
from wsgiref.simple_server import make_server

from jsonschema import Draft202012Validator, FormatChecker
import pandas as pd
import yaml

from . import __version__
from .clustering import MODEL_VERSIONS
from .config import BASELINE_CONFIG_VERSION, CONFIG_PRESETS, Config
from .data import POINT_COLUMNS
from .pipeline import run_pipeline
from .postgres import DEFAULT_SNAPSHOT, HISTORY_POINT_LIMIT, HistoryTooLarge, HistoryUnavailable, PostgresHistory
from .sqlite_history import SQLiteHistory


INFER_PATH = "/v1/locations/infer"
HISTORY_INFER_PATH = "/v2/locations/infer"
HEALTH_PATH = "/health"
VERSION_PATH = "/version"
DEFAULT_MODEL_VERSION = "dbscan-v1"
MAX_BODY_BYTES = 20 * 1024 * 1024
logger = logging.getLogger(__name__)


def error_body(code, message, details=()):
    return {"error": {"code": code, "message": message, "details": list(details)}}


def validation_details(errors):
    for error in errors:
        path = list(error.absolute_path)
        if error.validator == "required":
            # jsonschema emits one error per missing field, all at the parent path.
            missing = [name for name in error.validator_value if name not in error.instance]
            for name in missing:
                yield {"path": json_pointer([*path, name]), "issue": "Required field is missing."}
        elif error.validator == "not" and not path:
            yield {"path": "/config", "issue": "Send either config or config_version."}
        else:
            yield {"path": json_pointer(path), "issue": f"Invalid value ({error.validator})."}


def json_pointer(path):
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in path)


def finite_number(parser, value):
    number = parser(value)
    if not math.isfinite(number):
        raise ValueError("Expected a finite number")
    return number


def reject_constant(_):
    raise ValueError("Invalid JSON constant")


def create_app(contract_path=Path("openapi.yaml"), history=None, *,
               model_version=DEFAULT_MODEL_VERSION, enable_inline=True):
    if model_version not in MODEL_VERSIONS:
        raise ValueError("Unsupported MODEL_VERSION")
    spec = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    request_schemas = {HISTORY_INFER_PATH: "HistoryInferenceRequest"}
    if enable_inline:
        request_schemas[INFER_PATH] = "InferenceRequest"
    validators = {
        path: Draft202012Validator({"$ref": f"#/components/schemas/{schema}", "components": spec["components"]},
                                   format_checker=FormatChecker())
        for path, schema in request_schemas.items()
    }
    max_points = spec["components"]["schemas"]["InferenceRequest"]["properties"]["points"]["maxItems"]
    integer_fields = {name for name, value in Config().to_dict().items() if type(value) is int}
    history_config = CONFIG_PRESETS[BASELINE_CONFIG_VERSION]
    history_config_metadata = history_config.version_metadata()
    status_responses = {
        HEALTH_PATH: {"status": "ok"},
        VERSION_PATH: {"model_version": model_version, "pipeline_version": __version__,
                       **history_config_metadata},
    }
    allowed_methods = {**dict.fromkeys(validators, "POST"), HEALTH_PATH: "GET", VERSION_PATH: "GET"}

    def handle(environ, path):
        content_type = environ.get("CONTENT_TYPE", "").partition(";")[0].strip().lower()
        if content_type != "application/json" or environ.get("HTTP_CONTENT_ENCODING", "identity").lower() != "identity":
            return 415, error_body("unsupported_media_type", "Send an uncompressed application/json body.")
        try:
            length = int(environ.get("CONTENT_LENGTH", ""))
            if length < 0:
                raise ValueError("Negative Content-Length")
        except ValueError:
            return 400, error_body("malformed_payload", "A valid Content-Length is required.")
        if length > MAX_BODY_BYTES:
            return 413, error_body("payload_too_large", "The request body exceeds 20 MiB.")
        try:
            raw = environ["wsgi.input"].read(length)
            if len(raw) != length:
                raise ValueError("Incomplete body")
            payload = json.loads(raw.decode("utf-8"), parse_constant=reject_constant,
                                 parse_int=lambda value: finite_number(int, value),
                                 parse_float=lambda value: finite_number(float, value))
        except (ValueError, OverflowError, RecursionError):
            return 400, error_body("malformed_payload", "Expected valid UTF-8 JSON with finite numbers.")

        points = payload.get("points") if isinstance(payload, dict) else None
        if path == INFER_PATH and isinstance(points, list) and len(points) > max_points:
            return 413, error_body("payload_too_large", f"The request exceeds {max_points} points.")
        errors = list(islice(validators[path].iter_errors(payload), 100))
        if errors:
            details = islice(validation_details(errors), 100)
            unique = {(item["path"], item["issue"]): item for item in details}
            return 422, error_body("validation_error", "The request does not match the schema.", unique.values())

        if path == HISTORY_INFER_PATH:
            user_id = payload["user_id"]
            if history is None:
                return 503, error_body("history_unavailable", "GPS history is not configured.")
            try:
                if isinstance(history, (SQLiteHistory, PostgresHistory)):
                    data = history.load_for_inference(user_id, model_version, history_config_metadata["config_sha256"])
                else:
                    data = history.load_user(user_id)
            except HistoryUnavailable:
                return 503, error_body("history_unavailable", "GPS history is temporarily unavailable.")
            except HistoryTooLarge:
                return 422, error_body("history_too_large", f"The GPS history exceeds {HISTORY_POINT_LIMIT} points.")
            if data is None:
                return 404, error_body("user_not_found", "No GPS history for this user in the configured snapshot.")
            result = data if isinstance(data, dict) else run_pipeline(data, user_id, history_config, model_version).result
            return 200, {**result, "data_snapshot_id": history.snapshot_id}

        if "config" in payload:
            values = {name: int(value) if name in integer_fields else value
                      for name, value in payload["config"].items()}
            try:
                config = Config(**values)
            except ValueError as error:
                return 422, error_body("validation_error", "Invalid inference configuration.",
                                       [{"path": "/config", "issue": str(error)}])
        else:
            config = CONFIG_PRESETS[payload.get("config_version", BASELINE_CONFIG_VERSION)]
        frame = pd.DataFrame(points, columns=POINT_COLUMNS)
        frame["user_id"] = payload["user_id"]
        for name in ("latitude", "longitude", "altitude_m"):
            frame[name] = frame[name].astype(float)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], format="ISO8601", utc=True, errors="coerce")
        if frame["timestamp"].isna().any():
            index = frame["timestamp"].isna().idxmax()
            return 422, error_body("validation_error", "Unsupported timestamp.",
                                   [{"path": f"/points/{index}/timestamp", "issue": "Timestamp is outside the supported range."}])
        run = run_pipeline(frame, payload["user_id"], config, payload.get("model_version", model_version))
        return 200, run.result

    def app(environ, start_response):
        headers = [("Content-Type", "application/json"), ("Cache-Control", "no-store")]
        try:
            path = environ.get("PATH_INFO")
            method = allowed_methods.get(path)
            if method is None:
                status, body = 404, {"detail": "Endpoint not found."}
            elif environ.get("REQUEST_METHOD") != method:
                status, body = 405, {"detail": f"Use {method} for this endpoint."}
                headers.append(("Allow", method))
            elif path in validators:
                status, body = handle(environ, path)
            else:
                status, body = 200, status_responses[path]
            encoded = json.dumps(body, allow_nan=False).encode("utf-8")
        except Exception as error:
            logger.error("Local inference request failed (%s)", type(error).__name__)
            status = 500
            encoded = json.dumps(error_body("internal_error", "Inference failed.")).encode("utf-8")
        headers.append(("Content-Length", str(len(encoded))))
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [encoded]

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1",
                        help="Listen on all container interfaces with 0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--contract", type=Path, default=Path("openapi.yaml"))
    args = parser.parse_args()
    dsn = os.environ.get("GEOLIFE_POSTGRES_DSN")
    sqlite_path = os.environ.get("GEOLIFE_SQLITE_PATH")
    if dsn and sqlite_path:
        parser.error("Configure only one of GEOLIFE_POSTGRES_DSN and GEOLIFE_SQLITE_PATH.")
    history = None
    if dsn:
        history = PostgresHistory(dsn, os.environ.get("GEOLIFE_SNAPSHOT_ID", DEFAULT_SNAPSHOT))
    elif sqlite_path:
        history = SQLiteHistory(Path(sqlite_path))
    model_version = os.environ.get("MODEL_VERSION", DEFAULT_MODEL_VERSION)
    with make_server(args.host, args.port, create_app(args.contract, history, model_version=model_version)) as server:
        print(f"Inference API listening at http://{args.host}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
