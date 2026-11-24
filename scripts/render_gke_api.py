"""Render Knative manifests for the internal GeoLife deployment on GKE."""

import argparse
from pathlib import Path
import re

import yaml


BASE_MANIFEST = Path(__file__).resolve().parents[1] / "infra/knative/geolife-postgres.yaml"
GHCR_IMAGE = re.compile(r"ghcr\.io/[a-z0-9][a-z0-9_.-]*/geolife-inference@sha256:[a-f0-9]{64}")


def api_manifest(image):
    if not GHCR_IMAGE.fullmatch(image):
        raise ValueError("Use ghcr.io/<owner>/geolife-inference@sha256:<64 lowercase hex digits>.")
    resources = list(yaml.safe_load_all(BASE_MANIFEST.read_text(encoding="utf-8")))
    service = next(resource for resource in resources if resource["kind"] == "Service")
    template_spec = service["spec"]["template"]["spec"]
    api = next(container for container in template_spec["containers"] if container["name"] == "api")
    api["image"] = image
    template_spec["imagePullSecrets"] = [{"name": "geolife-ghcr"}]
    return resources


def internal_kourier_manifest(path):
    resources = [resource for resource in yaml.safe_load_all(path.read_text(encoding="utf-8")) if resource]
    services = {
        resource["metadata"]["name"]: resource["spec"]
        for resource in resources
        if resource["kind"] == "Service" and resource["metadata"].get("namespace") == "kourier-system"
    }
    if (services.get("kourier", {}).get("type") not in {"LoadBalancer", "ClusterIP"}
            or services.get("kourier-internal", {}).get("type") != "ClusterIP"):
        raise ValueError("Expected a Kourier release manifest with kourier and kourier-internal Services.")
    services["kourier"]["type"] = "ClusterIP"
    return resources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", help="Immutable GHCR image reference")
    source.add_argument("--kourier-manifest", type=Path, help="Kourier release YAML to configure for internal access")
    args = parser.parse_args()
    try:
        resources = api_manifest(args.image) if args.image else internal_kourier_manifest(args.kourier_manifest)
    except (ValueError, OSError, yaml.YAMLError) as error:
        parser.error(str(error))
    print(yaml.safe_dump_all(resources, sort_keys=False), end="")


if __name__ == "__main__":
    main()
