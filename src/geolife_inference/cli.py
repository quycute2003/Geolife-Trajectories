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
    parser.add_argument("--users", nargs="+", help="Explicit user IDs, for example 000 001 002")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--model", choices=MODEL_VERSIONS, default="dbscan-v1")
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument("--plot", action="store_true", help="Write private offline PNG review plots")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        source = GeoLifeSource(args.dataset)
        config = load_config(args.config)
        if args.command == "inventory":
            write_json(args.output / "inventory.json", source.inventory())
            return 0
        if not args.users or len(set(args.users)) != len(args.users):
            raise ValueError("Supply distinct --users for eda/infer")
        if not set(args.users) <= set(source.by_user):
            raise ValueError("One or more requested users do not exist")
        summaries = []
        for user in args.users:
            points = source.load_user(user)
            if args.command == "eda":
                summaries.append(describe_user(points, config))
            else:
                run = run_pipeline(points, user, config, args.model)
                write_json(args.output / f"{user}-{args.model}.json", run.result)
                run.stays.to_csv(args.output / f"{user}-{args.model}-stays.csv", index=False)
                if args.plot:
                    review_plot(run, args.output / f"{user}-{args.model}.png")
        if args.command == "eda":
            write_json(args.output / "eda.json", summaries)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Error: {error}\n")
    return 0
