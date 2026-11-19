import argparse
from csv import reader
import json
from pathlib import Path

import pandas as pd

from geolife_inference import __version__
from geolife_inference.benchmark_roles import MATCH_METERS, ROLES, compare
from geolife_inference.config import BASELINE_CONFIG_VERSION, CONFIG_PRESETS
from geolife_inference.evaluation import write_json


MODELS = ("heuristic-v1", "dbscan-v1")
BASELINE = CONFIG_PRESETS[BASELINE_CONFIG_VERSION]
GROUPING_FIELDS = {"location_clusters", "noise_stays", "noise_proportion"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_audit(directory, model):
    audit = read_json(directory / "run-audit.json")
    users = audit["expected_users"]
    if (audit["status"] != "completed" or audit["scope"] != "full_dataset"
            or audit["model_version"] != model or audit["config"] != BASELINE.to_dict()
            or not users or len(users) != len(set(users)) or audit["completed_users"] != users
            or audit["processed_trajectory_files"] != audit["expected_trajectory_files"]):
        raise ValueError(f"Invalid full baseline audit for {model}")
    return audit


def load_result(directory, user_id, model):
    result = read_json(directory / f"{user_id}-{model}.json")
    if (result["status"] != "completed" or result["user_id"] != user_id
            or result["model_version"] != model or result["pipeline_version"] != __version__
            or result["config"] != BASELINE.to_dict()):
        raise ValueError(f"Invalid baseline result for {user_id}/{model}")
    return result


def read_stays(directory, user_id, model):
    with (directory / f"{user_id}-{model}-stays.csv").open(encoding="utf-8", newline="") as stream:
        rows = reader(stream)
        if next(rows)[-1] != "cluster_id":
            raise ValueError(f"Missing cluster labels for {user_id}/{model}")
        return [row[:-1] for row in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", type=Path, default=Path("artifacts/pipeline"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/cp2/model-comparison"))
    args = parser.parse_args()
    directories = [args.pipeline / model for model in MODELS]
    left_audit, right_audit = [load_audit(directory, model) for directory, model in zip(directories, MODELS)]
    audit_fields = ("expected_users", "expected_trajectory_files", "input_points", "output_points")
    if any(left_audit[key] != right_audit[key] for key in audit_fields):
        raise ValueError("The model runs cover different input scopes")

    users = left_audit["expected_users"]
    roles = [[], []]
    metrics = []
    for user_id in users:
        results = [load_result(directory, user_id, model) for directory, model in zip(directories, MODELS)]
        left, right = results
        shared_diagnostics = [{key: value for key, value in result["diagnostics"].items() if key not in GROUPING_FIELDS}
                              for result in results]
        stays = [read_stays(directory, user_id, model) for directory, model in zip(directories, MODELS)]
        if (shared_diagnostics[0] != shared_diagnostics[1] or left["coverage"] != right["coverage"]
                or stays[0] != stays[1] or len(stays[0]) != left["diagnostics"]["stay_events"]):
            raise ValueError(f"Input diagnostics, coverage, or stays differ for {user_id}")

        row = {"user_id": user_id, "input_points": left["diagnostics"]["input_points"],
               "cleaned_points": left["diagnostics"]["output_points"], "stays": len(stays[0])}
        for model, result, model_roles in zip(MODELS, results, roles):
            row[f"{model}_clusters"] = len(result["locations"])
            row[f"{model}_noise_stays"] = result["diagnostics"]["noise_stays"]
            row[f"{model}_pois"] = len(result["pois"])
            for role in ROLES:
                decision = result[role]
                candidate = decision["candidate"] or {}
                model_roles.append(dict(user_id=user_id, role=role, status=decision["status"],
                                        reason=decision["reason"], latitude=candidate.get("latitude"),
                                        longitude=candidate.get("longitude")))
        metrics.append(row)

    metrics = pd.DataFrame(metrics)
    if (int(metrics.input_points.sum()) != left_audit["input_points"]
            or int(metrics.cleaned_points.sum()) != left_audit["output_points"]):
        raise ValueError("Per-user point counts do not match the run audits")
    paired = compare(*(pd.DataFrame(model_roles) for model_roles in roles))
    summary = {
        **BASELINE.version_metadata(),
        "pipeline_version": __version__,
        "users": len(users),
        "trajectory_files": left_audit["expected_trajectory_files"],
        "input_points": left_audit["input_points"],
        "cleaned_points": left_audit["output_points"],
        "shared_stays": int(metrics.stays.sum()),
        "agreement_distance_m": MATCH_METERS,
        "models": {
            model: {
                "clusters": int(metrics[f"{model}_clusters"].sum()),
                "noise_stays": int(metrics[f"{model}_noise_stays"].sum()),
                "pois": int(metrics[f"{model}_pois"].sum()),
            } for model in MODELS
        },
        "roles": {},
    }
    for role, rows in paired.groupby("role"):
        both = rows.distance_m.dropna()
        summary["roles"][role] = {
            f"{MODELS[0]}_predicted": int(rows.status_left.eq("predicted").sum()),
            f"{MODELS[1]}_predicted": int(rows.status_right.eq("predicted").sum()),
            "both_predicted": len(both),
            "both_unknown": int((rows.status_left.eq("unknown") & rows.status_right.eq("unknown")).sum()),
            "predicted_to_unknown": int((rows.status_left.eq("predicted") & rows.status_right.eq("unknown")).sum()),
            "unknown_to_predicted": int((rows.status_left.eq("unknown") & rows.status_right.eq("predicted")).sum()),
            "within_agreement_distance": int(rows.same_place.sum()),
            "median_distance_m": float(both.median()) if not both.empty else None,
        }
    write_json(args.output / "summary.json", summary)
    metrics.to_csv(args.output / "user-metrics.csv", index=False)
    paired.drop(columns=["latitude_left", "longitude_left", "latitude_right", "longitude_right"]).to_csv(
        args.output / "user-role-comparison.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
