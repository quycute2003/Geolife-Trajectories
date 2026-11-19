"""Build, verify, and deploy the GeoLife SQLite demo with Blue serving traffic."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from geolife_inference.config import Config


ROOT = Path(__file__).resolve().parents[1]
REGION = "ap-southeast-2"
STACK = "geolife-sqlite-demo"
FUNCTION = f"{STACK}-infer"
IMAGE = "geolife-lambda:sqlite-demo"
SNAPSHOT = "geolife-1.3-demo-v1"
INFER_PATH = "/v2/locations/infer"
BLUE = "heuristic-v1"
GREEN = "dbscan-v1"


def run(*command, capture=False, input_text=None, absent_error=None, env=None):
    result = subprocess.run(
        command, cwd=ROOT, text=True, encoding="utf-8", errors="replace",
        input=input_text, capture_output=capture, check=False, env=env,
    )
    if result.returncode:
        if absent_error and re.search(absent_error, result.stderr, re.IGNORECASE):
            return None
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"{command[0]} {command[1]} failed (exit {result.returncode}).")
    return result.stdout.strip() if capture else None


def expected_path(model):
    return ROOT / "artifacts" / "pipeline" / model / f"101-{model}.json"


def verify_inference(actual, model):
    expected = json.loads(expected_path(model).read_text(encoding="utf-8"))
    if actual.pop("data_snapshot_id", None) != SNAPSHOT:
        raise SystemExit(f"{model}: unexpected deployed GPS snapshot.")
    for key, value in Config(**expected["config"]).version_metadata().items():
        expected.setdefault(key, value)
    differences = sorted(key for key in actual.keys() | expected.keys() if actual.get(key) != expected.get(key))
    if actual != expected:
        raise SystemExit(f"{model}: response differs from CLI in {', '.join(differences)}.")


def build_and_verify(reuse_image=False):
    if run("docker", "info", "--format", "{{.OSType}}", capture=True) != "linux":
        raise SystemExit("Docker Desktop must use Linux containers.")
    for path in (expected_path(BLUE), expected_path(GREEN)):
        if not path.is_file():
            raise SystemExit(f"Missing {path.relative_to(ROOT)}.")
    if reuse_image:
        print("Checking the existing SQLite image", flush=True)
        platform = run("docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", IMAGE, capture=True)
        if platform != "linux/amd64":
            raise SystemExit(f"{IMAGE} must be built for linux/amd64.")
    else:
        print("Building and checking the SQLite image", flush=True)
        snapshot_file = ROOT / "artifacts/cp2/sqlite/geolife.sqlite3"
        if not snapshot_file.is_file():
            raise SystemExit(f"Missing {snapshot_file.relative_to(ROOT)}.")
        run("docker", "buildx", "build", "--platform", "linux/amd64", "--provenance=false", "--load",
            "--target", "sqlite-demo", "--build-context", "demo_snapshot=artifacts/cp2/sqlite",
            "-f", "Dockerfile.lambda", "-t", IMAGE, ".")
    for model in (BLUE, GREEN):
        container = run("docker", "run", "-d", "--rm", "-p", "127.0.0.1::8080",
                        "-e", f"MODEL_VERSION={model}", IMAGE, capture=True)
        try:
            address = run("docker", "port", container, "8080/tcp", capture=True)
            port = address.rsplit(":", 1)[1]
            run(sys.executable, "-X", "utf8", "scripts/check_local_api.py", "--lambda-runtime",
                "--port", port, "--snapshot", SNAPSHOT, "--expected", str(expected_path(model)))
        finally:
            run("docker", "stop", container, capture=True)


def push_image(aws, account, existing_stack):
    registry = f"{account}.dkr.ecr.{REGION}.amazonaws.com"
    repository = f"{registry}/{STACK}"
    image_id = run("docker", "image", "inspect", "--format", "{{.Id}}", IMAGE, capture=True)
    tag = f"build-{image_id.removeprefix('sha256:')}"
    existing_repo = aws("ecr", "describe-repositories", "--repository-names", STACK,
                        absent_error=r"RepositoryNotFoundException")
    if not existing_repo:
        aws("ecr", "create-repository", "--repository-name", STACK, "--image-tag-mutability", "IMMUTABLE")

    def uploaded_digest():
        return aws("ecr", "describe-images", "--repository-name", STACK,
                   "--image-ids", f"imageTag={tag}", "--query", "imageDetails[0].imageDigest", "--output", "text",
                   absent_error=r"ImageNotFoundException")

    digest = uploaded_digest()
    if existing_stack and f"{repository}@{digest}" != existing_stack["ImageUri"]:
        raise SystemExit(f"{STACK} already uses a different image. This script bootstraps a single release.")
    if not digest:
        print("Pushing to private ECR", flush=True)
        token = aws("ecr", "get-authorization-token", "--query", "authorizationData[0].authorizationToken",
                    "--output", "text")
        if not token or token == "None":
            raise SystemExit("ECR did not return a registry authorization token.")
        host = run("docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}", capture=True)
        image_tag = f"{repository}:{tag}"
        run("docker", "tag", IMAGE, image_tag)
        docker_env = os.environ.copy()
        docker_env.pop("DOCKER_CONTEXT", None)
        with TemporaryDirectory(prefix="geolife-ecr-") as docker_config:
            config = {"auths": {registry: {"auth": token}}}
            Path(docker_config, "config.json").write_text(json.dumps(config), encoding="utf-8")
            run("docker", "--config", docker_config, "--host", host, "push", image_tag, env=docker_env)
        digest = uploaded_digest()
    if not digest or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise SystemExit("ECR did not return a valid image digest.")
    return f"{repository}@{digest}"


def ensure_ecr_lambda_access(aws):
    policy = aws("ecr", "get-repository-policy", "--repository-name", STACK,
                 absent_error=r"RepositoryPolicyNotFoundException")
    if policy is not None:
        return

    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "LambdaECRImageRetrievalPolicy",
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
        }],
    }
    with TemporaryDirectory(prefix="geolife-ecr-policy-") as tmp:
        path = Path(tmp) / "policy.json"
        path.write_text(json.dumps(policy), encoding="utf-8")
        aws("ecr", "set-repository-policy", "--repository-name", STACK, "--policy-text", f"file://{path}")
    print("Granted Lambda read access to the private ECR repository", flush=True)


def invoke_version(aws, version, model):
    payload = {"version": "2.0", "rawPath": INFER_PATH, "requestContext": {"http": {"method": "POST"}},
               "headers": {"content-type": "application/json"}, "body": json.dumps({"user_id": "101"})}
    with TemporaryDirectory(prefix="geolife-invoke-") as tmp:
        event = Path(tmp) / "event.json"
        response = Path(tmp) / "response.json"
        event.write_text(json.dumps(payload), encoding="utf-8")
        metadata = json.loads(aws("lambda", "invoke", "--function-name", FUNCTION, "--qualifier", version,
                                  "--payload", f"fileb://{event}", str(response)))
        result = json.loads(response.read_text(encoding="utf-8"))
    if metadata.get("FunctionError") or metadata.get("ExecutedVersion") != version or result.get("statusCode") != 200:
        raise SystemExit(f"Lambda {version} failed the {model} invocation check.")
    verify_inference(json.loads(result["body"]), model)
    print(f"Lambda {version} ({model}): HTTP 200, full CLI match", flush=True)


def verify_endpoint(aws, endpoint, traffic):
    if not re.fullmatch(r"https://[a-z0-9]+\.execute-api\.ap-southeast-2\.amazonaws\.com/?", endpoint):
        raise SystemExit("CloudFormation did not return the expected HTTP API endpoint.")
    url = endpoint.rstrip("/") + INFER_PATH
    payload = json.dumps({"user_id": "101"})
    curl = ("curl.exe" if sys.platform == "win32" else "curl", "--silent", "--show-error", "--max-time", "20",
            "--header", "content-type: application/json", "--data-binary", payload, "--write-out", "\n%{http_code}")
    unsigned = run(*curl, url, capture=True)
    if unsigned.rsplit("\n", 1)[-1] not in {"401", "403"}:
        raise SystemExit("API Gateway did not reject an unsigned request.")
    credentials = json.loads(aws("configure", "export-credentials", "--format", "process"))
    config = "user = " + json.dumps(f"{credentials['AccessKeyId']}:{credentials['SecretAccessKey']}") + "\n"
    if credentials.get("SessionToken"):
        config += "header = " + json.dumps(f"x-amz-security-token: {credentials['SessionToken']}") + "\n"
    signed = run(*curl, "--aws-sigv4", f"aws:amz:{REGION}:execute-api", "--config", "-", url,
                 input_text=config, capture=True)
    body, _, status = signed.rpartition("\n")
    if status != "200":
        raise SystemExit(f"The signed API Gateway request returned HTTP {status}.")
    actual = json.loads(body)
    model = actual.get("model_version")
    allowed = {"blue": {BLUE}, "green": {GREEN}, "canary": {BLUE, GREEN}}[traffic]
    if model not in allowed:
        raise SystemExit("API Gateway returned an unexpected model version.")
    verify_inference(actual, model)
    print(f"API Gateway ({model}): HTTP 200, full CLI match. Unsigned request rejected.", flush=True)


def deploy(aws, image_uri, stack):
    def update(model, blue=""):
        try:
            aws("cloudformation", "deploy", "--stack-name", STACK, "--template-file", "infra/geolife-demo.yaml",
                "--capabilities", "CAPABILITY_IAM", "--no-fail-on-empty-changeset",
                "--parameter-overrides", f"ImageUri={image_uri}", f"LatestModel={model}", f"BlueVersion={blue}",
                "Traffic=blue", stream=True)
        except SystemExit:
            try:
                events = aws("cloudformation", "describe-stack-events", "--stack-name", STACK, "--max-items", "40",
                             "--query", "StackEvents[?ends_with(ResourceStatus, 'FAILED')].[LogicalResourceId,ResourceStatusReason] | [:5]",
                             "--output", "json")
                print(events, file=sys.stderr)
            except SystemExit as error:
                print(f"Could not read failure events: {error}", file=sys.stderr)
            raise
        aws("lambda", "wait", "function-updated-v2", "--function-name", FUNCTION)

    def publish(model, latest):
        description = f"{model} {image_uri.split('@')[1]}"
        versions = json.loads(aws("lambda", "list-versions-by-function", "--function-name", FUNCTION))["Versions"]
        version = next((v["Version"] for v in versions if v["Version"] != "$LATEST" and v["Description"] == description), None)
        if version is None:
            if latest != model:
                raise SystemExit(f"No published {model} version and $LATEST contains {latest}.")
            version = aws("lambda", "publish-version", "--function-name", FUNCTION, "--description", description,
                          "--query", "Version", "--output", "text")
        aws("lambda", "wait", "function-active-v2", "--function-name", FUNCTION, "--qualifier", version)
        invoke_version(aws, version, model)
        return version

    if stack is None:
        print("Creating the Lambda stack", flush=True)
        update(BLUE)
        stack = {"LatestModel": BLUE, "BlueVersion": ""}
    blue = publish(BLUE, stack["LatestModel"])
    latest = stack["LatestModel"]
    if not stack["BlueVersion"]:
        print("Creating the API and setting prod to Blue", flush=True)
        update(GREEN, blue)
        latest = GREEN
    elif stack["BlueVersion"] != blue:
        raise SystemExit("The existing stack points to a different Blue version.")
    green = publish(GREEN, latest)
    endpoint = aws("cloudformation", "describe-stacks", "--stack-name", STACK,
                   "--query", "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue | [0]", "--output", "text")
    print(f"Endpoint: {endpoint}\nBlue: {blue}\nGreen: {green}\nImage: {image_uri}", flush=True)
    verify_endpoint(aws, endpoint, stack.get("Traffic", "blue"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="geolife-new")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--reuse-image", action="store_true", help=f"Check and deploy the existing {IMAGE} image")
    parser.add_argument("--retry-rolled-back", action="store_true", help="Replace the rolled-back initial demo stack")
    args = parser.parse_args()

    def aws(*command, absent_error=None, stream=False):
        return run("aws", *command, "--profile", args.profile, "--region", REGION, "--no-cli-pager",
                   capture=not stream, absent_error=absent_error)

    account = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text")
    if not re.fullmatch(r"[0-9]{12}", account) or account != args.account_id:
        raise SystemExit("The selected AWS profile does not match the expected account.")
    aws("cloudformation", "validate-template", "--template-body", "file://infra/geolife-demo.yaml")
    description = aws("cloudformation", "describe-stacks", "--stack-name", STACK,
                      absent_error=r"ValidationError.*does not exist")
    stack = None
    rolled_back_id = None
    if description:
        current = json.loads(description)["Stacks"][0]
        status = current["StackStatus"]
        stack = {p["ParameterKey"]: p["ParameterValue"] for p in current["Parameters"]}
        if status == "ROLLBACK_COMPLETE" and args.retry_rolled_back:
            if stack.get("LatestModel") != BLUE or stack.get("BlueVersion") != "":
                raise SystemExit(f"{STACK} is not the initial Blue deployment.")
            rolled_back_id = current["StackId"]
        elif status not in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"}:
            raise SystemExit(f"{STACK} is in {status}.")
    build_and_verify(args.reuse_image)
    image_uri = push_image(aws, account, stack)
    ensure_ecr_lambda_access(aws)
    if rolled_back_id:
        print("Removing the rolled-back CloudFormation stack before retrying", flush=True)
        aws("cloudformation", "delete-stack", "--stack-name", rolled_back_id)
        aws("cloudformation", "wait", "stack-delete-complete", "--stack-name", rolled_back_id)
        stack = None
    deploy(aws, image_uri, stack)


if __name__ == "__main__":
    main()
