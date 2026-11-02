"""Linear anchor scan; observed last in-radius timestamp is the stay end."""
from math import asin, cos, sin, sqrt

import numpy as np
import pandas as pd

from .config import Config
from .geo import EARTH_RADIUS_M, representative

STAY_COLUMNS = ["user_id", "trajectory_id", "latitude", "longitude", "start_time", "end_time",
                "duration_minutes", "point_count"]


def detect_stays(points: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, dict]:
    """Requires preprocessed points. A failed candidate resets at the first violating fix.

    Each accepted fix is <= distance_m from the fixed first fix; this is not a
    pairwise diameter bound. Gaps > max_gap reset even at identical coordinates.
    """
    events: list[dict] = []
    for (user, trajectory), frame in points.groupby(["user_id", "trajectory_id"], sort=True):
        frame = frame.sort_values("timestamp", kind="stable")
        coords = frame[["latitude", "longitude"]].to_numpy(dtype=float)
        times = frame.timestamp.tolist()
        rad = np.radians(coords)
        anchor = 0

        def emit(end: int) -> None:
            duration = (times[end] - times[anchor]).total_seconds() / 60
            if end > anchor and duration >= config.min_stay_minutes:
                lat, lon = representative(coords[anchor:end + 1])
                events.append(dict(user_id=user, trajectory_id=trajectory, latitude=lat, longitude=lon,
                                   start_time=times[anchor], end_time=times[end],
                                   duration_minutes=duration, point_count=end - anchor + 1))

        for j in range(1, len(frame)):
            a = (sin((rad[j, 0] - rad[anchor, 0]) / 2) ** 2
                 + cos(rad[anchor, 0]) * cos(rad[j, 0]) * sin((rad[j, 1] - rad[anchor, 1]) / 2) ** 2)
            distance = 2 * EARTH_RADIUS_M * asin(sqrt(min(1.0, max(0.0, a))))
            gap = (times[j] - times[j - 1]).total_seconds() / 60
            if gap > config.max_gap_minutes or gap <= 0 or distance > config.distance_m:
                emit(j - 1)
                anchor = j
        if len(frame):
            emit(len(frame) - 1)
    stays = pd.DataFrame(events, columns=STAY_COLUMNS)
    # Different trajectory files can overlap. Do not claim simultaneous dwell at
    # different places: first chronological event wins, later intersecting event drops.
    accepted, dropped = [], 0
    if not stays.empty:
        for _, frame in stays.groupby("user_id", sort=True):
            last_end = None
            for row in frame.sort_values(["start_time", "trajectory_id"], kind="stable").to_dict("records"):
                if last_end is not None and row["start_time"] < last_end:
                    dropped += 1
                    continue
                accepted.append(row)
                last_end = row["end_time"]
    return pd.DataFrame(accepted, columns=STAY_COLUMNS), {"overlapping_stays_removed": dropped}
