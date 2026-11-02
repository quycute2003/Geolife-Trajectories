"""Transparent invalid/duplicate handling; speeds are diagnostic, not filters."""
import numpy as np
import pandas as pd

from .config import Config
from .data import POINT_COLUMNS
from .geo import haversine_m


def preprocess(points: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, dict]:
    missing = set(POINT_COLUMNS) - set(points.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    df = points.copy()
    for name in ("user_id", "trajectory_id"):
        if df[name].isna().any() or df[name].astype(str).str.strip().eq("").any():
            raise ValueError("Nonempty user_id and trajectory_id required")
        df[name] = df[name].astype(str)
    for name in ("latitude", "longitude", "altitude_m"):
        df[name] = pd.to_numeric(df[name], errors="coerce")
    # Public Python interface requires aware UTC; never guess the zone of naive input.
    def utc_timestamp(value):
        try:
            ts = pd.Timestamp(value)
            if ts.tzinfo is None or ts.utcoffset().total_seconds() != 0:
                return pd.NaT
            return ts.tz_convert("UTC")
        except (ValueError, TypeError, OverflowError):
            return pd.NaT
    if not isinstance(df.timestamp.dtype, pd.DatetimeTZDtype) or str(df.timestamp.dt.tz) != "UTC":
        df["timestamp"] = pd.to_datetime(df.timestamp.map(utc_timestamp), utc=True)
    invalid_coords = (~np.isfinite(df.latitude) | ~np.isfinite(df.longitude)
                      | ~df.latitude.between(-90, 90) | ~df.longitude.between(-180, 180))
    invalid_time = df.timestamp.isna()
    audit = {"input_points": len(df), "invalid_coordinates": int(invalid_coords.sum()),
             "invalid_timestamps": int(invalid_time.sum()),
             "invalid_rows_removed": int((invalid_coords | invalid_time).sum()),
             "invalid_altitudes": int((~np.isfinite(df.altitude_m)).sum())}
    df = df.loc[~(invalid_coords | invalid_time)].copy()
    df.loc[~np.isfinite(df.altitude_m), "altitude_m"] = np.nan
    keys = ["user_id", "trajectory_id", "timestamp", "latitude", "longitude"]
    audit["duplicate_records_removed"] = int(df.duplicated(keys).sum())
    df = df.drop_duplicates(keys).sort_values(
        ["user_id", "trajectory_id", "timestamp", "latitude", "longitude"], kind="stable")
    # One coordinate per trajectory timestamp: deterministic lexicographic tie break.
    conflicts = df.duplicated(["user_id", "trajectory_id", "timestamp"])
    audit["conflicting_timestamps_removed"] = int(conflicts.sum())
    df = df.loc[~conflicts].reset_index(drop=True)
    prev = df.groupby(["user_id", "trajectory_id"], sort=False).shift(1)
    df["gap_seconds"] = (df.timestamp - prev.timestamp).dt.total_seconds()
    df["distance_m"] = haversine_m(df.latitude.to_numpy(), df.longitude.to_numpy(),
                                     prev.latitude.to_numpy(), prev.longitude.to_numpy())
    df["speed_mps"] = df.distance_m / df.gap_seconds.where(df.gap_seconds > 0)
    audit["gaps_over_limit"] = int((df.gap_seconds > config.max_gap_minutes * 60).sum())
    audit["high_speed_segments"] = int((df.speed_mps > config.speed_warning_mps).sum())
    audit["output_points"] = len(df)
    return df, audit
