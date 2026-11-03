"""Exact elapsed-time overlap with local calendar windows; union avoids double counts."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Iterable

import numpy as np
import pandas as pd

from .config import Config
from .data import iter_cleaned_timelines
from .geo import haversine_m, representative

Interval = tuple[datetime, datetime]


def union_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    merged: list[list[datetime]] = []
    normalized = ((s.astimezone(timezone.utc), e.astimezone(timezone.utc)) for s, e in intervals)
    for start, end in sorted((s, e) for s, e in normalized if e > s):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def temporal_summary(intervals: Iterable[Interval], config: Config) -> dict:
    intervals = union_intervals(intervals)
    zone = ZoneInfo(config.timezone)
    totals = dict(total_dwell_minutes=0.0, night_dwell_minutes=0.0, weekday_dwell_minutes=0.0,
                  weekday_daytime_dwell_minutes=0.0, weekend_dwell_minutes=0.0)
    days, weeks, night_days, work_days, work_weeks = set(), set(), set(), set(), set()
    for start, end in intervals:
        day = start.astimezone(zone).date()
        while datetime.combine(day, time.min, zone).astimezone(timezone.utc) < end:
            midnight = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
            next_midnight = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)

            def overlap(left: datetime, right: datetime) -> float:
                return max(0.0, (min(end, right) - max(start, left)).total_seconds() / 60)

            def window(hour: int) -> datetime:
                return datetime.combine(day, time(hour), zone).astimezone(timezone.utc)

            dwell = overlap(midnight, next_midnight)
            night = overlap(midnight, window(config.night_end_hour)) + overlap(window(config.night_start_hour), next_midnight)
            work = overlap(window(config.work_start_hour), window(config.work_end_hour)) if day.weekday() < 5 else 0.0
            totals["total_dwell_minutes"] += dwell
            totals["night_dwell_minutes"] += night
            totals["weekday_daytime_dwell_minutes"] += work
            totals["weekday_dwell_minutes" if day.weekday() < 5 else "weekend_dwell_minutes"] += dwell
            week = day.isocalendar()[:2]
            if dwell > 0:
                days.add(day)
                weeks.add(week)
            if night > 0:
                night_days.add(day)
            if work > 0:
                work_days.add(day)
                work_weeks.add(week)
            day += timedelta(days=1)
    return {**totals, "visit_count": len(intervals), "unique_visit_days": len(days),
            "distinct_weeks": len(weeks), "night_visit_days": len(night_days),
            "weekday_daytime_visit_days": len(work_days), "weekday_daytime_weeks": len(work_weeks),
            "mean_visit_duration": totals["total_dwell_minutes"] / len(intervals) if intervals else 0.0}


def _observation_runs(frame: pd.DataFrame, config: Config) -> list[Interval]:
    """Compress adjacent valid pairs without filling gaps or segment breaks."""
    frame = frame.sort_values("timestamp", kind="stable")
    if frame.empty:
        return []
    times = frame.timestamp.reset_index(drop=True)
    gap = times.diff().dt.total_seconds()
    breaks = gap.isna() | gap.le(0) | gap.gt(config.max_gap_minutes * 60)
    if "observation_segment" in frame:
        segments = frame.observation_segment.reset_index(drop=True)
        breaks |= segments.ne(segments.shift())
    starts = np.flatnonzero(breaks.to_numpy())
    ends = np.r_[starts[1:] - 1, len(times) - 1]
    return [(times.iloc[start], times.iloc[end]) for start, end in zip(starts, ends) if end > start]


def _coverage_summary(intervals: Iterable[Interval], days: set, first, last, config: Config) -> dict:
    summary = temporal_summary(intervals, config)
    if first is None:
        return {"observed_minutes": 0.0, "observed_days": 0, "calendar_span_days": 0,
                "observed_day_fraction": 0.0, "observed_time_fraction": 0.0,
                "night_observed_days": 0, "work_observed_days": 0,
                "first_timestamp": None, "last_timestamp": None}
    span = (max(days) - min(days)).days + 1
    span_minutes = (last - first).total_seconds() / 60
    return {"observed_minutes": summary["total_dwell_minutes"], "observed_days": len(days),
            "calendar_span_days": span, "observed_day_fraction": len(days) / span,
            "observed_time_fraction": summary["total_dwell_minutes"] / span_minutes if span_minutes else 0.0,
            "night_observed_days": summary["night_visit_days"],
            "work_observed_days": summary["weekday_daytime_visit_days"],
            "first_timestamp": first.isoformat(), "last_timestamp": last.isoformat()}


def observation_coverage(points: pd.DataFrame, config: Config) -> dict:
    intervals = []
    for _, frame in points.groupby(["user_id", "trajectory_id"], sort=False):
        intervals.extend(_observation_runs(frame, config))
    times = points.timestamp
    days = set(times.dt.tz_convert(config.timezone).dt.date) if len(times) else set()
    return _coverage_summary(intervals, days, times.min() if len(times) else None,
                             times.max() if len(times) else None, config)


def stream_observation_coverage(path, config: Config, chunksize: int = 100_000) -> Iterable[dict]:
    """Yield exact per-user coverage over all cleaned GPS, not only stay points.

    Memory holds one trajectory plus compressed observed intervals for one user.
    Union across overlapping files avoids double-counting; chunk boundaries do not
    cut intervals, while NB02 observation_segment boundaries always do.
    """
    user, intervals, days, first, last = None, [], set(), None, None
    trajectories, finished_users, count = set(), set(), 0

    def finish():
        return {"user_id": user, "processed_points": count, "processed_trajectories": len(trajectories),
                **_coverage_summary(intervals, days, first, last, config)}

    for frame in iter_cleaned_timelines(path, chunksize):
        current = str(frame.user_id.iloc[0])
        if current != user:
            if current in finished_users:
                raise ValueError(f"User is not contiguous in cleaned CSV: {current}")
            if user is not None:
                yield finish()
                finished_users.add(user)
            user, intervals, days, first, last = current, [], set(), None, None
            trajectories, count = set(), 0
        trajectory = str(frame.trajectory_id.iloc[0])
        if trajectory in trajectories:
            raise ValueError(f"Trajectory is not contiguous: {current}/{trajectory}")
        if not frame.timestamp.is_monotonic_increasing or frame.timestamp.duplicated().any():
            raise ValueError("Cleaned trajectory timestamps must strictly increase")
        if not frame.observation_segment.is_monotonic_increasing:
            raise ValueError("Cleaned observation segments must be increasing")
        trajectories.add(trajectory)
        count += len(frame)
        intervals.extend(_observation_runs(frame, config))
        days.update(frame.timestamp.dt.tz_convert(config.timezone).dt.date)
        earliest, latest = frame.timestamp.min(), frame.timestamp.max()
        first = earliest if first is None else min(first, earliest)
        last = latest if last is None else max(last, latest)
    if user is not None:
        yield finish()


def cluster_features(stays: pd.DataFrame, coverage: dict, config: Config) -> list[dict]:
    features = []
    for (user, cluster_id), frame in stays.loc[stays.cluster_id >= 0].groupby(["user_id", "cluster_id"], sort=True):
        lat, lon = representative(frame[["latitude", "longitude"]].to_numpy())
        distances = haversine_m(lat, lon, frame.latitude.to_numpy(), frame.longitude.to_numpy())
        temporal = temporal_summary(zip(frame.start_time, frame.end_time), config)
        features.append({"user_id": str(user), "cluster_id": int(cluster_id), "latitude": lat, "longitude": lon,
                         "stay_event_count": len(frame), **temporal,
                         "radius_max_m": float(np.max(distances)), "radius_p95_m": float(np.quantile(distances, .95)),
                         "observation_coverage": temporal["unique_visit_days"] / max(1, coverage["observed_days"])})
    return features
