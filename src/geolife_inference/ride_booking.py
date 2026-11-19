"""Local GeoLife ride simulator using the PostgreSQL inference API."""
import argparse
from base64 import b64decode
from binascii import Error as Base64Error
from contextlib import ExitStack, closing, contextmanager
import errno
from http import HTTPStatus
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import shutil
import socket
from socketserver import ThreadingMixIn
import subprocess
from time import monotonic, sleep
from urllib.parse import parse_qs, urlencode
import webbrowser
from wsgiref.simple_server import WSGIServer, make_server

from .api import DEFAULT_MODEL_VERSION, HEALTH_PATH, HISTORY_INFER_PATH, MAX_BODY_BYTES, VERSION_PATH, create_app
from .clustering import MODEL_VERSIONS
from .postgres import DEFAULT_SNAPSHOT, HistoryUnavailable, PostgresHistory


ROOT = Path(__file__).resolve().parents[2]
LOCAL_SNAPSHOT = ROOT / "artifacts/cp2/postgres-local"
RESTORED_POSTGRES = ROOT / "artifacts/cp2/postgres-knative-rehearsal"
RESTORE_LOG = ROOT / "artifacts/cp2/knative-postgres-restored.log"
LOCAL_DSN = "host=127.0.0.1 port=55433 dbname=postgres user=geolife"
FULL_SNAPSHOT = "geolife-1.3-full-v1"
REGISTRY_NAME = "geolife-home-office"
REGISTRY_DIR = ROOT / "artifacts/cp2/mlflow"
INFERENCE_METHODS = {HISTORY_INFER_PATH: "POST", HEALTH_PATH: "GET", VERSION_PATH: "GET"}
ASSETS = {
    "/": ("index.html", "text/html"),
    "/styles.css": ("styles.css", "text/css"),
    "/fixtures.js": ("fixtures.js", "text/javascript"),
    "/map.js": ("map.js", "text/javascript"),
    "/booking.js": ("booking.js", "text/javascript"),
}


class LocalServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def request_json(port, method, path, *, body=None, headers=None, timeout=60):
    with closing(HTTPConnection("127.0.0.1", port, timeout=timeout)) as connection:
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        raw = response.read(MAX_BODY_BYTES + 1)
        if len(raw) > MAX_BODY_BYTES:
            raise ValueError("Upstream response too large")
        payload = json.loads(raw) if response.headers.get_content_type() == "application/json" else None
        return response.status, payload


def forward_inference(environ, path, port, route_host, snapshot):
    method = environ["REQUEST_METHOD"]
    expected = INFERENCE_METHODS[path]
    if method != expected:
        return 405, {"error": {"code": "method_not_allowed"}}, [("Allow", expected)]
    headers = {"Host": route_host}
    body = None
    if method == "POST":
        try:
            length = int(environ.get("CONTENT_LENGTH", ""))
            if length < 0:
                raise ValueError
        except ValueError:
            return 400, {"error": {"code": "malformed_payload"}}, []
        if length > MAX_BODY_BYTES:
            return 413, {"error": {"code": "payload_too_large"}}, []
        body = environ["wsgi.input"].read(length)
        if len(body) != length:
            return 400, {"error": {"code": "malformed_payload"}}, []
        headers["Content-Type"] = environ.get("CONTENT_TYPE", "")
        headers["Content-Encoding"] = environ.get("HTTP_CONTENT_ENCODING", "identity")
    try:
        status, result = request_json(port, method, path, body=body, headers=headers)
        if 400 <= status <= 599:
            return status, result if isinstance(result, dict) else {"error": {"code": "knative_http_error"}}, []
        if status == 200 and isinstance(result, dict):
            if path == HISTORY_INFER_PATH and result.get("data_snapshot_id") != snapshot:
                return 502, {"error": {"code": "snapshot_mismatch"}}, []
            return status, result, []
    except (OSError, HTTPException, ValueError):
        pass
    return 502, {"error": {"code": "kourier_unavailable"}}, []


def read_registry(alias, port):
    params = urlencode({"name": REGISTRY_NAME, "alias": alias})
    try:
        status, response = request_json(port, "GET", f"/api/2.0/mlflow/registered-models/alias?{params}", timeout=3)
        if status == 200:
            version = response["model_version"]
            tags = {tag["key"]: tag["value"] for tag in version.get("tags", [])}
            return {"version": version["version"], "status": version["status"], "tags": tags, "source": "api"}
        if status == 404:
            return None
    except (OSError, HTTPException, ValueError, TypeError, KeyError):
        pass

    # Read through the installed MLflow client when the local registry HTTP service is off.
    client_python = ROOT / ".venv-registry/Scripts/python.exe"
    registry_db = REGISTRY_DIR / "mlflow.db"
    if not client_python.is_file() or not registry_db.is_file():
        return None
    program = (
        "import json,sys; from mlflow import MlflowClient; "
        "v=MlflowClient(registry_uri=sys.argv[1]).get_model_version_by_alias(*sys.argv[2:]); "
        "print(json.dumps(dict(version=v.version,status=v.status,tags=v.tags,source='store')))"
    )
    try:
        result = subprocess.run(
            [str(client_python), "-X", "utf8", "-c", program, f"sqlite:///{registry_db.as_posix()}", REGISTRY_NAME, alias],
            capture_output=True, encoding="utf-8", check=True, timeout=15,
        )
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def create_booking_app(history, *, model_version=DEFAULT_MODEL_VERSION, knative=None, registry_port=5001, user_ids=None):
    inference_api = None if knative else create_app(
        ROOT / "openapi.yaml", history, model_version=model_version, enable_inline=False,
    )
    assets = {path: (ROOT / "ride-booking" / name, media_type)
              for path, (name, media_type) in ASSETS.items()}
    startup_users = tuple(user_ids) if user_ids is not None else None

    def respond(start_response, status, body, media_type="application/json", headers=()):
        start_response(status, [
            ("Content-Type", f"{media_type}; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            *headers,
        ])
        return [body]

    def respond_json(start_response, status, body, headers=()):
        try:
            reason = HTTPStatus(status).phrase
        except ValueError:
            reason = "Upstream Error"
        return respond(start_response, f"{status} {reason}", json.dumps(body).encode(), headers=headers)

    def app(environ, start_response):
        # Keep GPS results on the loopback origin, including when a browser supplies a custom Host.
        host = environ.get("HTTP_HOST", "").lower()
        accepted_hosts = {name for host_name in ("localhost", "127.0.0.1")
                          for name in (host_name, f'{host_name}:{environ["SERVER_PORT"]}')}
        path = environ.get("PATH_INFO", "")
        if host not in accepted_hosts or (path not in assets and environ.get("HTTP_SEC_FETCH_SITE") == "cross-site"):
            return respond(start_response, "403 Forbidden", b'{"error":"local_access_only"}')

        if path in INFERENCE_METHODS:
            if knative:
                status, body, headers = forward_inference(environ, path, *knative, history.snapshot_id)
                return respond_json(start_response, status, body, [*headers, ("X-GeoLife-Serving", "knative")])

            def local_response(status, headers):
                return start_response(status, [*headers, ("X-GeoLife-Serving", "local")])

            return inference_api(environ, local_response)
        if path not in assets and path not in ("/booking/users", "/booking/registry"):
            return respond(start_response, "404 Not Found", b'{"error":"not_found"}')
        if environ["REQUEST_METHOD"] != "GET":
            return respond(start_response, "405 Method Not Allowed", b'{"error":"method_not_allowed"}',
                           headers=[("Allow", "GET")])
        if path in assets:
            file, media_type = assets[path]
            return respond(start_response, "200 OK", file.read_bytes(), media_type)
        if path == "/booking/registry":
            alias = parse_qs(environ.get("QUERY_STRING", "")).get("algorithm", [""])[0]
            if alias not in MODEL_VERSIONS:
                return respond_json(start_response, 400, {"error": "unknown_model"})
            entry = read_registry(alias, registry_port)
            if not entry:
                return respond_json(start_response, 503, {"error": "registry_unavailable"})
            tags = entry["tags"]
            return respond_json(start_response, 200, {
                "name": REGISTRY_NAME, "version": entry["version"], "status": entry["status"], "source": entry["source"],
                "algorithm": tags.get("model_version"), "snapshot": tags.get("data_snapshot_id"),
                "config_sha256": tags.get("config_sha256"), "pipeline_version": tags.get("pipeline_version"),
            })
        try:
            users = startup_users if startup_users is not None else history.list_users()
        except HistoryUnavailable:
            return respond(start_response, "503 Service Unavailable", b'{"error":"history_unavailable"}')
        return respond_json(start_response, 200, {"user_ids": users, "serving": "knative" if knative else "local"})

    return app


def postgres_port_in_use():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(("127.0.0.1", 55433))
    except OSError as error:
        if error.errno == errno.EADDRINUSE or getattr(error, "winerror", None) == 10048:
            return True
        raise
    return False


@contextmanager
def managed_postgres(data, log):
    version = (data / "PG_VERSION").read_text(encoding="ascii").strip()
    windows_pg_ctl = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PostgreSQL" / version / "bin/pg_ctl.exe"
    pg_ctl = str(windows_pg_ctl) if windows_pg_ctl.is_file() else shutil.which("pg_ctl")
    if pg_ctl is None:
        raise RuntimeError("pg_ctl not found. Start PostgreSQL and set GEOLIFE_POSTGRES_DSN.")

    command = [pg_ctl, "-D", str(data)]
    status = subprocess.run([*command, "status"], capture_output=True, check=False).returncode
    if status not in (0, 3):
        raise RuntimeError("Could not check the local PostgreSQL cluster status.")
    started_here = status == 3
    if started_here and postgres_port_in_use():
        if not (data / "postmaster.pid").is_file():
            raise RuntimeError("Port 55433 is already in use. Check which PostgreSQL instance owns it.")
        # Some Windows sessions cannot see a postmaster started in another session. Avoid starting it twice.
        started_here = False
    if started_here:
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            subprocess.run([*command, "-l", str(log), "-o",
                            "-h 127.0.0.1 -p 55433 -c unix_socket_directories= -c default_transaction_read_only=on",
                            "-w", "start"], check=True, creationflags=flags)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"Could not start the GeoLife PostgreSQL database. See {log}.") from error
    try:
        yield
    finally:
        if started_here:
            subprocess.run([*command, "-m", "fast", "-w", "stop"], check=False)


@contextmanager
def local_history(default_snapshot=DEFAULT_SNAPSHOT):
    from psycopg.conninfo import make_conninfo

    dsn = os.environ.get("GEOLIFE_POSTGRES_DSN")
    snapshot = os.environ.get("GEOLIFE_SNAPSHOT_ID")
    if dsn:
        yield PostgresHistory(dsn, snapshot or default_snapshot)
        return

    data, passfile = LOCAL_SNAPSHOT / "data", LOCAL_SNAPSHOT / "pgpass.conf"
    if not (data / "PG_VERSION").is_file() or not passfile.is_file():
        raise RuntimeError("Set GEOLIFE_POSTGRES_DSN and GEOLIFE_SNAPSHOT_ID for an imported GeoLife database.")
    with managed_postgres(data, LOCAL_SNAPSHOT / "booking-postgres.log"):
        # libpq opens the passfile without sending its contents to app logs or browser responses.
        yield PostgresHistory(make_conninfo(LOCAL_DSN, passfile=str(passfile)), snapshot or FULL_SNAPSHOT)


@contextmanager
def knative_history(context, namespace):
    from psycopg import ProgrammingError
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    snapshot = os.environ.get("GEOLIFE_SNAPSHOT_ID") or FULL_SNAPSHOT
    dsn = os.environ.get("GEOLIFE_POSTGRES_DSN")
    if dsn:
        yield PostgresHistory(dsn, snapshot)
        return

    try:
        secret = subprocess.run([
            "kubectl", "--context", context, "--namespace", namespace, "get", "secret", "geolife-postgres",
            "-o", "jsonpath={.data.dsn}", "--request-timeout=5s",
        ], capture_output=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            f"Could not read the PostgreSQL Secret in {namespace}. Set GEOLIFE_POSTGRES_DSN for the database serving Knative."
        ) from error

    try:
        settings = conninfo_to_dict(b64decode(secret, validate=True).decode())
    except (Base64Error, UnicodeError, ValueError, ProgrammingError):
        settings = {}
    if not settings.get("host"):
        raise RuntimeError("The Knative PostgreSQL Secret has no usable DSN. Set GEOLIFE_POSTGRES_DSN for the booking app.")
    if settings["host"] == "host.docker.internal":
        settings["host"] = "127.0.0.1"
        settings.pop("hostaddr", None)
    history = PostgresHistory(make_conninfo(**settings), snapshot)
    restored_data = RESTORED_POSTGRES / "data"
    if (settings["host"], settings.get("port")) == ("127.0.0.1", "55433") and (restored_data / "PG_VERSION").is_file():
        if not RESTORE_LOG.is_file() or "PostgreSQL import and read-only access established." not in RESTORE_LOG.read_text(
                encoding="utf-8", errors="replace"):
            raise RuntimeError(f"The Knative PostgreSQL restore has not finished. Progress: {RESTORE_LOG}")
        with managed_postgres(restored_data, RESTORED_POSTGRES / "booking-postgres.log"):
            yield history
        return
    yield history


@contextmanager
def kourier_forward(context, port):
    def listening():
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            return False

    if listening():
        yield
        return
    with subprocess.Popen([
        "kubectl", "--context", context, "-n", "kourier-system", "port-forward", "service/kourier-internal",
        f"{port}:80", "--address", "127.0.0.1",
    ], cwd=ROOT) as process:
        try:
            deadline = monotonic() + 15
            while process.poll() is None and monotonic() < deadline:
                if listening():
                    break
                sleep(0.25)
            else:
                raise RuntimeError("Kourier port-forward failed. Check the Kubernetes context and Kourier service.")
            yield
        finally:
            if process.poll() is None:
                process.terminate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the local demo in the default browser.")
    parser.add_argument("--knative", action="store_true", help="Send inference requests to Kourier's live Knative Route.")
    parser.add_argument("--context", default="docker-desktop", help="Kubernetes context for Kourier port-forward")
    parser.add_argument("--namespace", default="geolife-knative-postgres", help="Knative inference namespace")
    parser.add_argument("--kourier-port", type=int, default=18081)
    parser.add_argument("--mlflow-port", type=int, default=5001)
    args = parser.parse_args()
    try:
        with ExitStack() as stack:
            knative = None
            if args.knative:
                history = stack.enter_context(knative_history(args.context, args.namespace))
                stack.enter_context(kourier_forward(args.context, args.kourier_port))
                knative = (args.kourier_port, f"geolife-inference.{args.namespace}.svc.cluster.local")
            else:
                history = stack.enter_context(local_history())
            users = history.list_users()
            if not users:
                raise RuntimeError(f"No GeoLife users in snapshot {history.snapshot_id!r}.")
            app = create_booking_app(history, model_version=os.environ.get("MODEL_VERSION", DEFAULT_MODEL_VERSION),
                                     knative=knative, registry_port=args.mlflow_port, user_ids=users)
            with make_server("127.0.0.1", args.port, app, server_class=LocalServer) as server:
                url = f"http://127.0.0.1:{server.server_port}/"
                print(f"GeoLife: {url} ({len(users)} PostgreSQL users)", flush=True)
                if knative:
                    print(f"Inference: Kourier at 127.0.0.1:{knative[0]} -> {knative[1]}", flush=True)
                if args.open:
                    webbrowser.open(url)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
    except HistoryUnavailable:
        parser.exit(1, "Could not read the GeoLife PostgreSQL snapshot. Check the local connection and the imported schema.\n")
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
