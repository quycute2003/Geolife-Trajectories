"""Reproduce CP1 diagnostics locally; never uploads GPS data or downloads datasets."""
import argparse
from dataclasses import replace
import hashlib
import time
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from geolife_inference.config import Config
from geolife_inference.data import GeoLifeSource
from geolife_inference.evaluation import describe_user, review_plot, write_json
from geolife_inference.pipeline import run_pipeline


def summary(result: dict, seconds: float, experiment: str) -> dict:
    return {"user_id": result["user_id"], "experiment": experiment, "model_version": result["model_version"],
            "config": result["config"], "elapsed_seconds": seconds, **result["diagnostics"],
            "coverage": result["coverage"], "home_status": result["home"]["status"],
            "home_reason": result["home"]["reason"], "office_status": result["office"]["status"],
            "office_reason": result["office"]["reason"], "poi_count": len(result["pois"]),
            "max_cluster_radius_m": max((loc["radius_max_m"] for loc in result["locations"]), default=0),
            "home_cluster_id": result["home"]["candidate"]["cluster_id"] if result["home"]["candidate"] else None,
            "office_cluster_id": result["office"]["candidate"]["cluster_id"] if result["office"]["candidate"] else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation"))
    parser.add_argument("--users", nargs="+", default=["000", "001", "002"])
    parser.add_argument("--scan-inventory", action="store_true")
    args = parser.parse_args()
    source = GeoLifeSource(args.dataset)
    inventory = source.inventory()
    if args.scan_inventory:
        if not source.is_zip:
            parser.error("--scan-inventory currently requires a ZIP")
        digest = hashlib.sha256()
        with args.dataset.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        inventory["archive_sha256"] = digest.hexdigest()
        with ZipFile(args.dataset) as z:
            counts = {}
            for user, names in source.by_user.items():
                count = 0
                for name in names:
                    with z.open(name) as stream:
                        for _ in range(6):
                            stream.readline()
                        count += sum(bool(line.strip()) for line in stream)
                counts[user] = count
            inventory["record_lines_per_user"] = counts
            inventory["total_record_lines"] = sum(counts.values())
            inventory["label_file_count"] = sum(n.endswith("labels.txt") for n in z.namelist())
    write_json(args.output / "inventory.json", inventory)
    # Add one real sparse user, chosen by lowest trajectory count then user ID.
    sparse = min(source.by_user, key=lambda u: (len(source.by_user[u]), u))
    users = list(dict.fromkeys([*args.users, sparse]))
    base = Config()
    experiments = [("baseline", "dbscan-v1", base), ("baseline", "heuristic-v1", base),
                   ("distance-50m", "dbscan-v1", replace(base, distance_m=50)),
                   ("distance-200m", "dbscan-v1", replace(base, distance_m=200)),
                   ("stay-20min", "dbscan-v1", replace(base, min_stay_minutes=20)),
                   ("gap-1min", "dbscan-v1", replace(base, max_gap_minutes=1)),
                   ("eps-200m", "dbscan-v1", replace(base, eps_m=200)),
                   ("min-samples-5", "dbscan-v1", replace(base, min_samples=5))]
    eda, summaries, review_rows = [], [], []
    for user in users:
        points = source.load_user(user)
        eda.append(describe_user(points, base))
        for name, model, config in experiments:
            started = time.perf_counter()
            run = run_pipeline(points, user, config, model)
            summaries.append(summary(run.result, time.perf_counter() - started, name))
            if name == "baseline":
                prefix = args.output / f"{user}-{model}"
                write_json(prefix.with_suffix(".json"), run.result)
                run.stays.to_csv(str(prefix) + "-stays.csv", index=False)
                review_plot(run, prefix.with_suffix(".png"))
                for location in run.result["locations"]:
                    review_rows.append({"user_id": user, "model_version": model, "cluster_id": location["cluster_id"],
                                        "latitude": location["latitude"], "longitude": location["longitude"],
                                        "algorithm_home": location["cluster_id"] == summaries[-1]["home_cluster_id"],
                                        "algorithm_office": location["cluster_id"] == summaries[-1]["office_cluster_id"],
                                        "manual_proxy_label": "", "reviewer": "", "uncertainty": "", "notes": ""})
            print(f"Completed {user} {model} {name}: {len(run.stays)} stays", flush=True)
            write_json(args.output / "experiments.json", summaries)
        write_json(args.output / "eda.json", eda)
    pd.DataFrame(review_rows).to_csv(args.output / "manual-review-template.csv", index=False)


if __name__ == "__main__":
    main()
