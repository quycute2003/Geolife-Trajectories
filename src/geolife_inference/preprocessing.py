"""NB02 spatial/context voting, point provenance and observation boundaries."""
from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd

from .config import Config
from .data import POINT_COLUMNS
from .geo import haversine_m

CONFLICT_POLICY = "spatial_vote_context_v2"
TIME_KEYS = ["user_id", "trajectory_id", "timestamp"]
POINT_KEYS = [*TIME_KEYS, "latitude", "longitude"]
AUDIT_COUNTS = [
    "input_points", "invalid_coordinates", "invalid_timestamps", "invalid_rows_removed",
    "invalid_altitudes", "duplicate_records_removed", "conflict_groups", "conflict_positions",
    "merged_conflict_groups", "merged_source_points", "merged_extra_points",
    "unresolved_conflict_groups", "unresolved_conflict_rows", "resolved_conflict_groups",
    "context_resolved_groups", "outlier_conflict_rows", "output_points", "missing_altitude_after",
    "gaps_over_limit", "high_speed_segments", "breaks_due_to_conflict",
]
TRACE_COLUMNS = [*POINT_COLUMNS, "record_id", "conflict_group_id", "spread_m", "decision", "output_record_id"]


@dataclass
class PreprocessingResult:
    points: pd.DataFrame
    removed_points: pd.DataFrame
    conflict_points: pd.DataFrame
    audit: dict


def _normalize(points: pd.DataFrame) -> pd.DataFrame:
    missing = set(POINT_COLUMNS) - set(points.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    df = points.copy().reset_index(drop=True)
    for name in ("user_id", "trajectory_id"):
        if df[name].isna().any() or df[name].astype(str).str.strip().eq("").any():
            raise ValueError("Nonempty user_id and trajectory_id required")
        df[name] = df[name].astype(str)
    for name in ("latitude", "longitude", "altitude_m"):
        df[name] = pd.to_numeric(df[name], errors="coerce")

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
    return df


def _basic_masks(df: pd.DataFrame):
    bad_coordinate = (~np.isfinite(df.latitude) | ~np.isfinite(df.longitude)
                      | ~df.latitude.between(-90, 90) | ~df.longitude.between(-180, 180))
    bad_timestamp = df.timestamp.isna()
    valid = ~(bad_coordinate | bad_timestamp)
    duplicate = pd.Series(False, index=df.index)
    duplicate.loc[valid] = df.loc[valid].duplicated(POINT_KEYS, keep="first")
    return bad_coordinate, bad_timestamp, duplicate


def _motion_columns(points: pd.DataFrame, config: Config) -> pd.DataFrame:
    df = points.sort_values([*TIME_KEYS, "latitude", "longitude"], kind="stable").reset_index(drop=True)
    prev = df.groupby(["user_id", "trajectory_id"], sort=False).shift(1)
    df["gap_seconds"] = (df.timestamp - prev.timestamp).dt.total_seconds()
    df["distance_m"] = haversine_m(df.latitude.to_numpy(), df.longitude.to_numpy(),
                                     prev.latitude.to_numpy(), prev.longitude.to_numpy())
    df["speed_mps"] = df.distance_m / df.gap_seconds.where(df.gap_seconds > 0)
    df["gap_over_limit"] = df.gap_seconds.gt(config.max_gap_minutes * 60)
    df["high_speed_flag"] = df.speed_mps.gt(config.speed_warning_mps)
    return df


def diagnose_resolved_points(points: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, dict]:
    """NB02 bridge: already-resolved fixes; preserve mean provenance, never vote twice.

    Unlike the old core this helper refuses unresolved equal timestamps. It is not
    the raw-input pipeline entry point; use preprocess/preprocess_with_trace there.
    """
    df = _normalize(points)
    bad_coordinate, bad_timestamp, duplicate = _basic_masks(df)
    audit = dict(input_points=len(df), invalid_coordinates=int(bad_coordinate.sum()),
                 invalid_timestamps=int(bad_timestamp.sum()),
                 invalid_rows_removed=int((bad_coordinate | bad_timestamp).sum()),
                 invalid_altitudes=int((~np.isfinite(df.altitude_m)).sum()),
                 duplicate_records_removed=int(duplicate.sum()), conflicting_timestamps_removed=0)
    df = df.loc[~(bad_coordinate | bad_timestamp | duplicate)].copy()
    if df.duplicated(TIME_KEYS).any():
        raise ValueError("Equal-timestamp conflicts must be resolved before motion diagnostics")
    df.loc[~np.isfinite(df.altitude_m), "altitude_m"] = np.nan
    df = _motion_columns(df, config)
    audit.update(output_points=len(df), gaps_over_limit=int(df.gap_over_limit.sum()),
                 high_speed_segments=int(df.high_speed_flag.sum()))
    return df, audit


def _diameter(group: pd.DataFrame) -> float:
    coords = group[["latitude", "longitude"]].to_numpy(dtype=float)
    maximum = 0.0
    for i in range(len(coords) - 1):
        distances = haversine_m(coords[i, 0], coords[i, 1], coords[i + 1:, 0], coords[i + 1:, 1])
        maximum = max(maximum, float(np.max(distances)))
    return maximum


def _mean_coordinate(group: pd.DataFrame) -> tuple[float, float]:
    base = float(group.longitude.iloc[0])
    unwrapped = base + ((group.longitude.to_numpy() - base + 180) % 360 - 180)
    return float(group.latitude.mean()), float((unwrapped.mean() + 180) % 360 - 180)


def _choose_conflict(group: pd.DataFrame, distinct: pd.DataFrame, config: Config):
    threshold = config.conflict_merge_threshold_m
    coords = group[["latitude", "longitude"]].to_numpy(dtype=float)
    distances = haversine_m(coords[:, 0, None], coords[:, 1, None], coords[None, :, 0], coords[None, :, 1])
    close = distances <= threshold
    for size in range(int(close.sum(axis=1).max()), 0, -1):
        leaders = [list(indices) for indices in combinations(range(len(group)), size)
                   if close[np.ix_(indices, indices)].all()]
        if leaders:
            break
    if len(leaders) == 1:
        return group.iloc[leaders[0]], "spatial_vote"
    timestamp = group.timestamp.iloc[0]
    # distinct is ONLY this user/trajectory; other files cannot cast votes.
    context = distinct.loc[distinct.timestamp.ne(timestamp)
                           & (distinct.timestamp - timestamp).abs().le(pd.Timedelta(minutes=config.max_gap_minutes))
                           & ~distinct.duplicated(TIME_KEYS, keep=False)]
    if context.empty:
        return None, "unresolved_tie"
    centers = [_mean_coordinate(group.iloc[c]) for c in leaders]
    d = np.column_stack([haversine_m(context.latitude.to_numpy(), context.longitude.to_numpy(), lat, lon)
                         for lat, lon in centers])
    nearest, minimum = d.argmin(axis=1), d.min(axis=1)
    unique_nearest = np.isclose(d, minimum[:, None], atol=1e-6, rtol=0).sum(axis=1) == 1
    eligible = unique_nearest & (minimum <= threshold)
    votes = np.bincount(nearest[eligible], minlength=len(leaders))
    winners = np.flatnonzero(votes == votes.max())
    if votes.max() == 0 or len(winners) != 1:
        return None, "unresolved_tie"
    return group.iloc[leaders[int(winners[0])]], "context_vote"


def _resolve_trajectory(distinct: pd.DataFrame, config: Config, audit: dict):
    mask = distinct.duplicated(TIME_KEYS, keep=False)
    ordinary = distinct.loc[~mask].copy()
    ordinary["coordinate_merged"], ordinary["source_point_count"] = False, 1
    pieces, traces, unresolved_times = [ordinary], [], []
    for timestamp, group in distinct.loc[mask].groupby("timestamp", sort=True):
        spread = _diameter(group)
        audit["conflict_groups"] += 1
        audit["conflict_positions"] += len(group)
        selected, method = ((group, "spatial_vote") if spread <= config.conflict_merge_threshold_m
                            else _choose_conflict(group, distinct, config))
        trace = group.copy()
        first = group.iloc[0]
        trace["conflict_group_id"] = f"{first.user_id}/{first.trajectory_id}@{timestamp.isoformat()}"
        trace["spread_m"], trace["output_record_id"] = spread, pd.NA
        if selected is None:
            trace["decision"] = "unresolved_tie"
            unresolved_times.append(timestamp.value)
            audit["unresolved_conflict_groups"] += 1
            audit["unresolved_conflict_rows"] += len(group)
        else:
            n = len(selected)
            output = selected.loc[[selected.record_id.idxmin()]].copy()
            output["latitude"], output["longitude"] = _mean_coordinate(selected)
            output["altitude_m"] = selected.altitude_m.where(np.isfinite(selected.altitude_m)).mean()
            output["coordinate_merged"], output["source_point_count"] = n > 1, n
            pieces.append(output)
            accepted = trace.record_id.isin(selected.record_id)
            trace["decision"] = "rejected_by_vote"
            trace.loc[accepted, "decision"] = "mean_merged" if n > 1 else "selected_by_context"
            trace.loc[accepted, "output_record_id"] = int(output.record_id.iloc[0])
            audit["resolved_conflict_groups"] += 1
            audit["context_resolved_groups"] += int(method == "context_vote")
            audit["merged_conflict_groups"] += int(n > 1)
            audit["merged_source_points"] += n if n > 1 else 0
            audit["merged_extra_points"] += n - 1
            audit["outlier_conflict_rows"] += len(group) - n
            # NB02 compatibility: all conflict fixes excluded from cleaned output,
            # including rejected minorities, not only wholly unresolved groups.
            audit["unresolved_conflict_rows"] += len(group) - n
        traces.append(trace)
    nonempty = [piece for piece in pieces if not piece.empty]
    ready = pd.concat(nonempty, ignore_index=True) if nonempty else ordinary
    clean = _motion_columns(ready, config)
    clean.loc[~np.isfinite(clean.altitude_m), "altitude_m"] = np.nan
    breaks = np.zeros(len(clean), dtype=bool)
    if len(clean) and unresolved_times:
        counts = np.searchsorted(np.sort(np.asarray(unresolved_times, dtype=np.int64)),
                                 clean.timestamp.astype("int64").to_numpy())
        breaks = np.diff(counts, prepend=counts[0]) > 0
    if "segment_break_due_to_conflict" in clean:
        breaks |= clean.segment_break_due_to_conflict.eq(True).to_numpy()
    inherited_starts = (clean.observation_segment.ne(clean.observation_segment.shift())
                        if "observation_segment" in clean else False)
    clean["segment_break_due_to_conflict"] = breaks
    starts = clean.gap_seconds.isna() | clean.gap_over_limit | clean.gap_seconds.le(0) | breaks | inherited_starts
    clean["observation_segment"] = starts.cumsum().astype(int)
    audit["breaks_due_to_conflict"] += int(breaks.sum())
    return clean, traces


def preprocess_with_trace(points: pd.DataFrame, config: Config) -> PreprocessingResult:
    """Raw GPS -> resolved points plus every removed/conflicting input fix.

    The invariant matches NB02: input = output + invalid + duplicates + merged
    extras + separated conflict rows. Mean contributors remain in conflict trace.
    Existing record_id is accepted for notebook provenance; no other derived
    columns affect decisions. Observation segments restart for each trajectory.
    """
    df = _normalize(points)
    if "record_id" not in df:
        df["record_id"] = np.arange(len(df), dtype=np.int64)
    else:
        ids = pd.to_numeric(df.record_id, errors="coerce")
        if ids.isna().any() or not np.isfinite(ids).all() or ids.lt(0).any() or ids.mod(1).ne(0).any() or ids.duplicated().any():
            raise ValueError("record_id must be a unique nonnegative integer")
        df["record_id"] = ids.astype("int64")
    bad_coordinate, bad_timestamp, duplicate = _basic_masks(df)
    audit = dict.fromkeys(AUDIT_COUNTS, 0)
    audit.update(input_points=len(df), invalid_coordinates=int(bad_coordinate.sum()),
                 invalid_timestamps=int(bad_timestamp.sum()),
                 invalid_rows_removed=int((bad_coordinate | bad_timestamp).sum()),
                 invalid_altitudes=int((~np.isfinite(df.altitude_m)).sum()),
                 duplicate_records_removed=int(duplicate.sum()))
    reasons = pd.Series(np.select([bad_coordinate & bad_timestamp, bad_coordinate, bad_timestamp, duplicate],
                                   ["invalid_coordinate_and_timestamp", "invalid_coordinate", "invalid_timestamp", "duplicate_point"],
                                   default=""), index=df.index)
    removed = df.loc[reasons.ne("")].copy()
    removed["reason"] = reasons.loc[removed.index]
    distinct = df.loc[~(bad_coordinate | bad_timestamp | duplicate)].copy()
    cleaned, traces = [], []
    for _, frame in distinct.groupby(["user_id", "trajectory_id"], sort=True):
        clean, trace = _resolve_trajectory(frame, config, audit)
        cleaned.append(clean)
        traces.extend(trace)
    if cleaned:
        clean = pd.concat(cleaned, ignore_index=True)
    else:
        empty = distinct.copy()
        empty["coordinate_merged"] = pd.Series(dtype=bool)
        empty["source_point_count"] = pd.Series(dtype="int64")
        clean, _ = _resolve_trajectory(empty, config, audit)
    provenance = pd.concat(traces, ignore_index=True) if traces else pd.DataFrame(columns=TRACE_COLUMNS)
    audit.update(output_points=len(clean), missing_altitude_after=int(clean.altitude_m.isna().sum()),
                 gaps_over_limit=int(clean.gap_over_limit.sum()), high_speed_segments=int(clean.high_speed_flag.sum()),
                 conflicting_timestamps_removed=audit["merged_extra_points"] + audit["unresolved_conflict_rows"],
                 conflict_policy=CONFLICT_POLICY)
    assert len(df) == len(clean) + len(removed) + audit["merged_extra_points"] + audit["unresolved_conflict_rows"]
    assert len(df) == int(clean.source_point_count.sum()) + len(removed) + audit["unresolved_conflict_rows"]
    assert len(provenance) == audit["conflict_positions"]
    assert clean.record_id.is_unique and not clean.duplicated(TIME_KEYS).any()
    return PreprocessingResult(clean, removed, provenance, audit)


def preprocess(points: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, dict]:
    run = preprocess_with_trace(points, config)
    return run.points, run.audit
