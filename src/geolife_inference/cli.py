"""Offline commands only; deliberately no HTTP server."""
import argparse
import logging
from pathlib import Path

from .clustering import MODEL_VERSIONS
from .config import load_config
from .data import GeoLifeSource
from .evaluation import describe_user, review_plot, write_json
from .pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "eda", "infer"])
    parser.add_argument("--dataset", type=Path, required=True, help="Local GeoLife ZIP or directory")
    parser.add_argument("--users", nargs="+", help="Optional explicit user IDs; default: every user in the dataset")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--model", choices=MODEL_VERSIONS, default="dbscan-v1")
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument("--plot", action="store_true", help="Write private offline PNG review plots")
    parser.add_argument("--audit-points", action="store_true", help="Export invalid/duplicate and conflict provenance CSVs")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = None
    try:
        source = GeoLifeSource(args.dataset)
        config = load_config(args.config)
        if args.command == "inventory":
            write_json(args.output / "inventory.json", source.inventory())
            return 0
        users = args.users if args.users is not None else sorted(source.by_user)
        if len(set(users)) != len(users):
            raise ValueError("Supply distinct --users")
        if not set(users) <= set(source.by_user):
            raise ValueError("One or more requested users do not exist")
        if args.command == "infer":
            report = {"status": "running", "scope": "full_dataset" if set(users) == set(source.by_user) else "selected_users",
                      "model_version": args.model, "config": config.to_dict(), "expected_users": users,
                      "completed_users": [], "expected_trajectory_files": sum(len(source.by_user[u]) for u in users),
                      "processed_trajectory_files": 0, "input_points": 0, "output_points": 0}
            write_json(args.output / "run-audit.json", report)
        summaries = []
        for user in users:
            points = source.load_user(user)
            if args.command == "eda":
                summaries.append(describe_user(points, config))
            else:
                run = run_pipeline(points, user, config, args.model)
                write_json(args.output / f"{user}-{args.model}.json", run.result)
                run.stays.to_csv(args.output / f"{user}-{args.model}-stays.csv", index=False)
                if args.audit_points:
                    run.removed_points.to_csv(args.output / f"{user}-{args.model}-removed.csv", index=False)
                    run.conflict_points.to_csv(args.output / f"{user}-{args.model}-conflicts.csv", index=False)
                if args.plot:
                    review_plot(run, args.output / f"{user}-{args.model}.png")
                report["completed_users"].append(user)
                report["processed_trajectory_files"] += len(source.by_user[user])
                for key in ("input_points", "output_points"):
                    report[key] += run.result["diagnostics"][key]
                write_json(args.output / "run-audit.json", report)
        if args.command == "eda":
            write_json(args.output / "eda.json", summaries)
        elif report is not None:
            report["status"] = "completed"
            write_json(args.output / "run-audit.json", report)
    except Exception as error:
        if report is not None:
            report.update(status="failed", error=f"{type(error).__name__}: {error}")
            write_json(args.output / "run-audit.json", report)
        if isinstance(error, (ValueError, OSError)):
            parser.exit(2, f"Error: {error}\n")
        raise
    return 0
