"""Per-user spatial grouping of stay events; label -1 remains noise."""
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from .config import Config
from .geo import EARTH_RADIUS_M, haversine_m

MODEL_VERSIONS = ("heuristic-v1", "dbscan-v1")


def group_locations(stays: pd.DataFrame, config: Config, model_version: str) -> pd.DataFrame:
    if model_version not in MODEL_VERSIONS:
        raise ValueError(f"Unsupported model_version: {model_version}")
    result = stays.copy()
    result["cluster_id"] = -1
    for _, frame in result.groupby("user_id", sort=True):
        frame = frame.sort_values(["start_time", "trajectory_id"], kind="stable")
        coords = frame[["latitude", "longitude"]].to_numpy()
        if model_version == "dbscan-v1":
            labels = DBSCAN(eps=config.eps_m / EARTH_RADIUS_M, min_samples=config.min_samples,
                            metric="haversine", algorithm="ball_tree", n_jobs=1).fit_predict(np.radians(coords))
        else:
            # Greedy nearest fixed-anchor assignment; anchor never moves, no density requirement.
            anchors: list[np.ndarray] = []
            labels = []
            for coordinate in coords:
                distances = [float(haversine_m(*coordinate, *anchor)) for anchor in anchors]
                nearest = int(np.argmin(distances)) if distances else -1
                if nearest < 0 or distances[nearest] > config.eps_m:
                    anchors.append(coordinate)
                    nearest = len(anchors) - 1
                labels.append(nearest)
        result.loc[frame.index, "cluster_id"] = labels
    result["cluster_id"] = result.cluster_id.astype(int)
    return result
