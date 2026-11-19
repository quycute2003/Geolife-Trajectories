import base64
from functools import cache
from io import BytesIO
import json
import os
from pathlib import Path

from .api import create_app, error_body
from .postgres import DEFAULT_SNAPSHOT, PostgresHistory
from .sqlite_history import SQLiteHistory


def create_handler(history, model_version, contract_path=Path("openapi.yaml")):
    app = create_app(contract_path, history, model_version=model_version, enable_inline=False)

    def invoke(event, context):
        try:
            if event["version"] != "2.0":
                raise ValueError("Expected payload format 2.0")
            method = event["requestContext"]["http"]["method"]
            path = event["rawPath"]
            headers = {key.lower(): value for key, value in (event.get("headers") or {}).items()}
            body = event.get("body")
            encoded = event.get("isBase64Encoded", False)
            if (not isinstance(method, str) or not isinstance(path, str)
                    or not isinstance(encoded, bool) or (body is not None and not isinstance(body, str))):
                raise ValueError("Invalid HTTP event")
            raw = base64.b64decode(body or "", validate=True) if encoded else (body or "").encode("utf-8")
        except (AttributeError, KeyError, TypeError, ValueError):
            return {
                "statusCode": 400,
                "headers": {"content-type": "application/json", "cache-control": "no-store"},
                "body": json.dumps(error_body("malformed_payload", "Expected an HTTP API payload format 2.0 event.")),
                "isBase64Encoded": False,
            }

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "CONTENT_TYPE": headers.get("content-type", ""),
            "HTTP_CONTENT_ENCODING": headers.get("content-encoding", "identity"),
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": BytesIO(raw),
        }
        response = {}

        def start_response(status, response_headers):
            response["statusCode"] = int(status.split()[0])
            response["headers"] = {name.lower(): value for name, value in response_headers
                                   if name.lower() != "content-length"}

        response["body"] = b"".join(app(environ, start_response)).decode("utf-8")
        response["isBase64Encoded"] = False
        return response

    return invoke


@cache
def configured_handler():
    dsn = os.environ.get("GEOLIFE_POSTGRES_DSN")
    sqlite_path = os.environ.get("GEOLIFE_SQLITE_PATH")
    if bool(dsn) == bool(sqlite_path):
        raise RuntimeError("Set exactly one of GEOLIFE_POSTGRES_DSN or GEOLIFE_SQLITE_PATH")
    model_version = os.environ.get("MODEL_VERSION")
    if not model_version:
        raise RuntimeError("MODEL_VERSION is required")
    history = (SQLiteHistory(Path(sqlite_path)) if sqlite_path
               else PostgresHistory(dsn, os.environ.get("GEOLIFE_SNAPSHOT_ID", DEFAULT_SNAPSHOT)))
    contract_path = Path(os.environ.get("LAMBDA_TASK_ROOT", ".")) / "openapi.yaml"
    return create_handler(history, model_version, contract_path)


def handler(event, context):
    return configured_handler()(event, context)
