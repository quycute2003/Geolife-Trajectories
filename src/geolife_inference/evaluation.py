"""Data diagnostics and private, offline plots for human review."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

from .config import Config
from .features import observation_coverage
from .pipeline import PipelineRun
from .preprocessing import preprocess


def quantiles(values: pd.Series) -> dict:
    finite = values[np.isfinite(values)]
    if finite.empty:
        return {key: None for key in ("min", "p25", "p50", "p95", "p99", "max")}
    return dict(zip(("min", "p25", "p50", "p95", "p99", "max"),
                    map(float, finite.quantile([0, .25, .5, .95, .99, 1]))))


def describe_user(points: pd.DataFrame, config: Config) -> dict:
    clean, audit = preprocess(points, config)
    return {"user_id": str(points.user_id.iloc[0]) if len(points) else None,
            "trajectory_count": int(points.trajectory_id.nunique()), **audit,
            "coverage": observation_coverage(clean, config),
            "sampling_seconds": quantiles(clean.gap_seconds.dropna()),
            "consecutive_distance_m": quantiles(clean.distance_m.dropna()),
            "speed_mps": quantiles(clean.speed_mps.dropna()),
            "stationary_segments": int((clean.distance_m == 0).sum())}


def write_json(path: str | Path, value: dict | list) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def review_plot(run: PipelineRun, output: str | Path) -> None:
    # No remote tiles or external geocoding: GPS histories remain local.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    points, stays = run.points, run.stays
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    for ax in axes:
        ax.set_xlabel("Longitude (degrees)")
        ax.set_ylabel("Latitude (degrees)")
        ax.grid(alpha=.15)
    if not points.empty:
        # Deterministic subsampling for plotting only; inference always uses all points.
        sample = points.iloc[::max(1, len(points) // 15000)]
        axes[0].scatter(sample.longitude, sample.latitude, s=1, c="#94a3b8", alpha=.4, label="GPS samples")
    if not stays.empty:
        noise = stays.cluster_id == -1
        axes[0].scatter(stays.loc[noise, "longitude"], stays.loc[noise, "latitude"], s=8, marker="x", c="#64748b", label="Noise stays")
        clustered = stays.loc[~noise]
        axes[0].scatter(clustered.longitude, clustered.latitude, c=clustered.cluster_id, cmap="tab20", s=12, label="Clustered stays")
    locations = run.result["locations"]
    for loc in locations:
        axes[1].scatter(loc["longitude"], loc["latitude"], s=25 + min(loc["visit_count"], 50) * 2, color="#2563eb", alpha=.6)
    # Label only the top 12 locations to keep the plot readable.
    top = sorted(locations, key=lambda c: (-c["unique_visit_days"], -c["total_dwell_minutes"]))[:12]
    for loc in top:
        axes[1].annotate(str(loc["cluster_id"]), (loc["longitude"], loc["latitude"]), xytext=(4, 4), textcoords="offset points", fontsize=8)
    for role, color, marker in (("home", "#16a34a", "*"), ("office", "#e11d48", "P")):
        candidate = run.result[role]["candidate"]
        if candidate:
            axes[1].scatter(candidate["longitude"], candidate["latitude"], s=180, c=color, marker=marker, label=role.title())
    axes[0].set_title("Observed GPS / stay overview (no basemap)")
    # Travel can dominate percentile bounds. Focus explicitly on +/-3km around
    # the inferred Home or most recurrent cluster, retaining all travel in overview.
    focus = run.result["home"]["candidate"] or (top[0] if top else None)
    if focus:
        dlat = 3000 / 111195
        dlon = dlat / max(.1, np.cos(np.radians(focus["latitude"])))
        axes[1].set_xlim(focus["longitude"] - dlon, focus["longitude"] + dlon)
        axes[1].set_ylim(focus["latitude"] - dlat, focus["latitude"] + dlat)
    axes[1].set_title("Location centers: 3km focus around Home / top cluster")
    if not locations:
        axes[1].set_axis_off()
        axes[1].text(.5, .5, "No location clusters\nHome / Office: unknown",
                     transform=axes[1].transAxes, ha="center", va="center", fontsize=15, color="#64748b")
    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=8)
        if not points.empty:
            ax.set_aspect(1 / max(.1, np.cos(np.radians(points.latitude.median()))))
        ax.ticklabel_format(useOffset=False, style="plain", axis="both")
    fig.suptitle(f"Private review: user {run.result['user_id']} / {run.result['model_version']}")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=140)
    plt.close(fig)
