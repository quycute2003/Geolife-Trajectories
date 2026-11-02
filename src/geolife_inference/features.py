"""Exact elapsed-time overlap with local calendar windows; union avoids double counts."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Iterable

import numpy as np
import pandas as pd

from .config import Config
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


def observation_coverage(points: pd.DataFrame, config: Config) -> dict:
    intervals = []
    for _, frame in points.groupby(["user_id", "trajectory_id"], sort=False):
        times = frame.sort_values("timestamp").timestamp.tolist()
        intervals.extend((s, e) for s, e in zip(times, times[1:])
                         if 0 < (e - s).total_seconds() <= config.max_gap_minutes * 60)
    summary = temporal_summary(intervals, config)
    if points.empty:
        return {"observed_minutes": 0.0, "observed_days": 0, "calendar_span_days": 0,
                "observed_day_fraction": 0.0, "observed_time_fraction": 0.0,
                "night_observed_days": 0, "work_observed_days": 0,
                "first_timestamp": None, "last_timestamp": None}
    times = points.timestamp
    zone = ZoneInfo(config.timezone)
    days = set(times.dt.tz_convert(zone).dt.date)
    span = (max(days) - min(days)).days + 1
    span_minutes = (times.max() - times.min()).total_seconds() / 60
    return {"observed_minutes": summary["total_dwell_minutes"], "observed_days": len(days),
            "calendar_span_days": span, "observed_day_fraction": len(days) / span,
            "observed_time_fraction": summary["total_dwell_minutes"] / span_minutes if span_minutes else 0.0,
            "night_observed_days": summary["night_visit_days"],
            "work_observed_days": summary["weekday_daytime_visit_days"],
            "first_timestamp": times.min().isoformat(), "last_timestamp": times.max().isoformat()}


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
