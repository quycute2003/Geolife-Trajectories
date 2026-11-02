"""One-user offline pipeline; shared input/output across model versions."""
from dataclasses import dataclass
import hashlib
import json
import logging
from uuid import NAMESPACE_URL, uuid5

import pandas as pd

from .clustering import MODEL_VERSIONS, group_locations
from .config import Config
from .features import cluster_features, observation_coverage
from .inference import infer_locations
from .preprocessing import preprocess
from .stays import detect_stays

logger = logging.getLogger(__name__)


@dataclass
class PipelineRun:
    result: dict
    points: pd.DataFrame
    stays: pd.DataFrame


def run_pipeline(points: pd.DataFrame, user_id: str, config: Config | None = None,
                 model_version: str = "dbscan-v1") -> PipelineRun:
    config = config or Config()
    if not user_id or len(user_id) > 64:
        raise ValueError("user_id must have 1..64 characters")
    if model_version not in MODEL_VERSIONS:
        raise ValueError("Unsupported model_version")
    if not points.empty and set(points.user_id.astype(str)) != {user_id}:
        raise ValueError("Exactly the requested user's points must be provided")
    clean, audit = preprocess(points, config)
    stays, stay_audit = detect_stays(clean, config)
    grouped = group_locations(stays, config, model_version)
    coverage = observation_coverage(clean, config)
    locations = cluster_features(grouped, coverage, config)
    prediction = infer_locations(locations, coverage, config)
    warnings = ["timezone_is_user_selected_assumption", "evidence_score_is_not_probability"]
    if coverage["observed_days"] < config.min_role_days:
        warnings.append("sparse_observation_days")
    if audit["high_speed_segments"]:
        warnings.append("high_speed_segments_retained")
    if any(loc["radius_max_m"] > 2 * config.eps_m for loc in locations):
        warnings.append("extended_location_clusters")
    if stay_audit["overlapping_stays_removed"]:
        warnings.append("overlapping_trajectory_stays_removed")
    digest = hashlib.sha256(pd.util.hash_pandas_object(clean, index=False).to_numpy().tobytes()).hexdigest()
    identity = json.dumps([user_id, digest, config.to_dict(), model_version], sort_keys=True)
    result = {"inference_id": str(uuid5(NAMESPACE_URL, identity)), "user_id": user_id,
              "model_version": model_version, "pipeline_version": "0.1.0", "status": "completed",
              "timezone": config.timezone, "config": config.to_dict(),
              "score_semantics": "Uncalibrated heuristic evidence score in [0,1]; not a probability.",
              **prediction, "locations": locations, "coverage": coverage,
              "diagnostics": {**audit, **stay_audit, "stay_events": len(grouped),
                              "location_clusters": len(locations),
                              "noise_stays": int((grouped.cluster_id == -1).sum()),
                              "noise_proportion": float((grouped.cluster_id == -1).mean()) if len(grouped) else 0.0},
              "warnings": warnings}
    logger.info("Inference completed: points=%d stays=%d clusters=%d", len(clean), len(grouped), len(locations))
    return PipelineRun(result, clean, grouped)
