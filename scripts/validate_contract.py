"""Validate OpenAPI, examples, and optionally real offline JSON responses; no HTTP."""
import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate
import yaml


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, help="Directory with <user>-<model>.json responses")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    spec = yaml.safe_load((root / "openapi.yaml").read_text(encoding="utf-8"))
    validate(spec)

    def check(name: str, value: dict) -> None:
        schema = {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)

    post = spec["paths"]["/v1/locations/infer"]["post"]
    count = 0
    for item in post["requestBody"]["content"]["application/json"]["examples"].values():
        check("InferenceRequest", item["value"])
        count += 1
    for code, response in post["responses"].items():
        media = response["content"]["application/json"]
        schema = "InferenceResponse" if code == "200" else "ErrorResponse"
        for item in media.get("examples", {}).values():
            check(schema, item["value"])
            count += 1
        if "example" in media:
            check(schema, media["example"])
            count += 1
    if args.results:
        for model in ("dbscan-v1", "heuristic-v1"):
            for path in args.results.glob(f"*-{model}.json"):
                check("InferenceResponse", json.loads(path.read_text(encoding="utf-8")))
                count += 1
    print(f"OpenAPI 3.1 valid; {count} examples/responses passed JSON Schema + format checks.")


if __name__ == "__main__":
    main()
