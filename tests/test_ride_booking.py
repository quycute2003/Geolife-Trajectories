from base64 import b64encode
from contextlib import contextmanager
from io import BytesIO
import json
from types import SimpleNamespace
from wsgiref.util import setup_testing_defaults

import pytest

from geolife_inference import ride_booking


def call(app, path, *, method="GET", body=b""):
    environ = {}
    setup_testing_defaults(environ)
    path, _, query = path.partition("?")
    environ.update(HTTP_HOST="127.0.0.1", PATH_INFO=path, QUERY_STRING=query, REQUEST_METHOD=method,
                   CONTENT_TYPE="application/json", CONTENT_LENGTH=str(len(body)))
    environ["wsgi.input"] = BytesIO(body)
    response = {}

    def start_response(status, headers):
        response.update(status=int(status.split()[0]), headers=dict(headers))

    response["body"] = json.loads(b"".join(app(environ, start_response)))
    return response


@pytest.mark.parametrize("model", ["heuristic-v1", "dbscan-v1"])
def test_inference_keeps_the_kourier_live_host_and_actual_model(monkeypatch, model):
    host = "geolife-inference.geolife-knative-postgres.svc.cluster.local"
    data = b'{"user_id":"101"}'
    snapshot = ride_booking.FULL_SNAPSHOT

    def request(port, method, path, *, body, headers):
        assert (port, method, path, body) == (18081, "POST", "/v2/locations/infer", data)
        assert headers["Host"] == host
        return 200, {"model_version": model, "data_snapshot_id": snapshot}

    monkeypatch.setattr(ride_booking, "request_json", request)
    app = ride_booking.create_booking_app(SimpleNamespace(snapshot_id=snapshot), knative=(18081, host))
    result = call(app, "/v2/locations/infer", method="POST", body=data)
    assert result["status"] == 200
    assert result["body"]["model_version"] == model
    assert result["headers"]["X-GeoLife-Serving"] == "knative"


@pytest.mark.parametrize(("reply", "status", "code"), [
    ((503, None), 503, "knative_http_error"),
    ((200, {"data_snapshot_id": "old-snapshot"}), 502, "snapshot_mismatch"),
])
def test_knative_error_or_wrong_snapshot_does_not_trigger_local_inference(monkeypatch, reply, status, code):
    monkeypatch.setattr(ride_booking, "request_json", lambda *args, **kwargs: reply)
    history = SimpleNamespace(snapshot_id=ride_booking.FULL_SNAPSHOT)
    app = ride_booking.create_booking_app(history, knative=(18081, "inference.svc.cluster.local"))
    result = call(app, "/v2/locations/infer", method="POST", body=b'{"user_id":"101"}')
    assert result["status"] == status
    assert result["body"]["error"]["code"] == code


def test_registry_queries_the_served_model_alias_without_exposing_registry_artifact_location(monkeypatch):
    def request(port, method, path, *, timeout):
        assert (port, method, timeout) == (5001, "GET", 3)
        assert path == "/api/2.0/mlflow/registered-models/alias?name=geolife-home-office&alias=dbscan-v1"
        return 200, {"model_version": {"version": "2", "status": "READY", "source": "private-source-location",
                                       "tags": [{"key": "model_version", "value": "dbscan-v1"},
                                                {"key": "data_snapshot_id", "value": "geolife-1.3-demo-v1"}]}}

    monkeypatch.setattr(ride_booking, "request_json", request)
    app = ride_booking.create_booking_app(SimpleNamespace(snapshot_id=ride_booking.FULL_SNAPSHOT),
                                          knative=(18081, "inference.svc.cluster.local"))
    result = call(app, "/booking/registry?algorithm=dbscan-v1")
    assert result["status"] == 200
    assert result["body"]["version"] == "2"
    assert result["body"]["snapshot"] == "geolife-1.3-demo-v1"
    assert result["body"]["source"] == "api"


def test_knative_reuses_its_restored_database_and_waits_for_import(monkeypatch, tmp_path):
    from psycopg.conninfo import conninfo_to_dict

    monkeypatch.delenv("GEOLIFE_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("GEOLIFE_SNAPSHOT_ID", raising=False)
    database = tmp_path / "data"
    database.mkdir()
    (database / "PG_VERSION").write_text("18")
    log = tmp_path / "restore.log"
    log.write_text("Copied 140/182 users.\n", encoding="utf-8")
    monkeypatch.setattr(ride_booking, "RESTORED_POSTGRES", tmp_path)
    monkeypatch.setattr(ride_booking, "RESTORE_LOG", log)

    def read_secret(command, **options):
        assert command[:7] == ["kubectl", "--context", "docker-desktop", "--namespace", "demo", "get", "secret"]
        assert options["capture_output"]
        return SimpleNamespace(stdout=b64encode(b"host=host.docker.internal port=55433 dbname=postgres user=reader"))

    started = []

    @contextmanager
    def managed(data, _):
        started.append(data)
        yield

    monkeypatch.setattr(ride_booking.subprocess, "run", read_secret)
    monkeypatch.setattr(ride_booking, "managed_postgres", managed)
    with pytest.raises(RuntimeError, match="restore has not finished"), ride_booking.knative_history("docker-desktop", "demo"):
        pass
    assert not started

    log.write_text("PostgreSQL import and read-only access established.\n", encoding="utf-8")
    with ride_booking.knative_history("docker-desktop", "demo") as history:
        settings = conninfo_to_dict(history.dsn)
        assert (settings["host"], settings["port"], settings["user"]) == ("127.0.0.1", "55433", "reader")
        assert history.snapshot_id == ride_booking.FULL_SNAPSHOT
    assert started == [database]


@pytest.mark.parametrize("has_pid", [False, True])
def test_launcher_never_starts_or_stops_postgres_if_port_is_already_in_use(monkeypatch, tmp_path, has_pid):
    (tmp_path / "PG_VERSION").write_text("18", encoding="ascii")
    if has_pid:
        (tmp_path / "postmaster.pid").touch()

    def pg_ctl(command, **options):
        assert command[-1] == "status"
        return SimpleNamespace(returncode=3)

    monkeypatch.setattr(ride_booking.subprocess, "run", pg_ctl)
    monkeypatch.setattr(ride_booking.shutil, "which", lambda name: name)
    monkeypatch.setattr(ride_booking, "postgres_port_in_use", lambda: True)
    if has_pid:
        with ride_booking.managed_postgres(tmp_path, tmp_path / "postgres.log"):
            pass
    else:
        with pytest.raises(RuntimeError, match="Port 55433"), ride_booking.managed_postgres(tmp_path, tmp_path / "postgres.log"):
            pass


def test_launcher_serves_the_verified_user_list_without_requerying_postgres():
    history = SimpleNamespace(snapshot_id=ride_booking.FULL_SNAPSHOT)
    app = ride_booking.create_booking_app(history, knative=(18081, "inference.svc.cluster.local"), user_ids=["001", "101"])
    result = call(app, "/booking/users")
    assert result["status"] == 200
    assert result["body"] == {"user_ids": ["001", "101"], "serving": "knative"}
