"""Exact B4 event detectors. Input arrays contain observations only, never truth."""
from __future__ import annotations

from bisect import insort
from collections import deque
from dataclasses import asdict, dataclass

import numpy as np

from .geo import haversine_m, representative

METHODS = ('fixed_anchor', 'median_updated', 'medoid_updated', 'max_neighbor_updated', 'st_dbscan')
RADII = (50, 100, 150, 200)
DURATIONS = (10, 20)
REVISION = 'b4-detectors-v1'
EVENT_COLUMNS = ['start', 'end', 'latitude', 'longitude', 'point_count']


@dataclass(frozen=True)
class DetectorConfig:
    method: str
    radius_m: int = 100
    dwell_minutes: int = 10
    eps_time_seconds: int = 300
    min_points: int = 3
    max_gap_seconds: int = 300

    @property
    def config_id(self):
        key = f'{self.method}_r{self.radius_m}_d{self.dwell_minutes}'
        if self.method == 'st_dbscan':
            key += f'_t{self.eps_time_seconds}_n{self.min_points}'
        return key

    def record(self):
        return dict(config_id=self.config_id, **asdict(self))


def configurations(include_sweep=True):
    grid = [DetectorConfig(m, r, d) for d in DURATIONS for r in RADII for m in METHODS]
    if include_sweep:
        grid += [DetectorConfig('st_dbscan', 100, 10, t, n)
                 for t in (60, 180, 300) for n in (3, 5, 10) if (t, n) != (300, 3)]
    return grid


BASELINE_ID = DetectorConfig('fixed_anchor').config_id


def _median_sorted(values):
    n = len(values)
    return values[n//2] if n % 2 else (values[n//2-1] + values[n//2])/2


def _scan(t, xy, cfg, check):
    result = []
    first = 0
    unwrapped = np.degrees(np.unwrap(np.radians(xy[:,1]))) if cfg.method == 'median_updated' else None
    sums = np.empty(len(t)) if cfg.method == 'medoid_updated' else None
    while first < len(t):
        check()
        center = xy[first].copy()
        bound = 0.
        latitude = [float(xy[first, 0])]
        longitude = [float(unwrapped[first])] if unwrapped is not None else []
        # Coordinate medians use a continuous longitude sequence, as the core does.
        if sums is not None:sums[0]=0.
        winner = first
        accepted_center = center.copy()
        end = first + 1
        while end < len(t):
            if end % 128 == 0:
                check()
            candidate_center = center
            if cfg.method == 'fixed_anchor':
                valid = float(haversine_m(*center, *xy[end])) <= cfg.radius_m
            elif cfg.method == 'median_updated':
                insort(latitude, float(xy[end, 0])); insort(longitude, float(unwrapped[end]))
                candidate_center = np.array([_median_sorted(latitude), (_median_sorted(longitude)+180)%360-180])
                movement = float(haversine_m(*center, *candidate_center))
                bound = max(bound + movement, float(haversine_m(*candidate_center, *xy[end])))
                if bound <= cfg.radius_m:
                    valid = True
                else:
                    bound = float(np.max(haversine_m(candidate_center[0], candidate_center[1],
                        xy[first:end+1, 0], xy[first:end+1, 1])))
                    valid = bound <= cfg.radius_m
            elif cfg.method == 'medoid_updated':
                distance = haversine_m(xy[end, 0], xy[end, 1], xy[first:end, 0], xy[first:end, 1])
                count = end-first
                sums[:count] += distance
                sums[count] = distance.sum()
                # argmin chooses the earliest physical fix on exact ties.
                index = first + int(np.argmin(sums[:count+1]))
                candidate_center = xy[index]
                bound = max(bound + float(haversine_m(*center, *candidate_center)),
                    float(haversine_m(*candidate_center, *xy[end])))
                if bound <= cfg.radius_m:
                    valid = True
                else:
                    bound = float(np.max(haversine_m(candidate_center[0], candidate_center[1],
                        xy[first:end+1, 0], xy[first:end+1, 1])))
                    valid = bound <= cfg.radius_m
            else:
                # A center that failed full coverage can never regain it as this
                # prefix grows. The earliest viable center is the count-max tie winner.
                valid = float(haversine_m(*xy[winner], *xy[end])) <= cfg.radius_m
                if not valid:
                    for index in range(winner+1, end+1):
                        if index % 128 == 0:
                            check()
                        if np.all(haversine_m(xy[index, 0], xy[index, 1],
                                xy[first:end+1, 0], xy[first:end+1, 1]) <= cfg.radius_m):
                            winner, valid = index, True
                            break
                candidate_center = xy[winner]
            if not valid:
                break
            center = np.asarray(candidate_center).copy()
            accepted_center = center.copy()
            end += 1
        last = end-1
        if last > first and t[last]-t[first] >= cfg.dwell_minutes*60:
            coord = (representative(xy[first:end]) if cfg.method == 'fixed_anchor'
                     else tuple(accepted_center))
            result.append(dict(start=float(t[first]), end=float(t[last]), latitude=float(coord[0]),
                longitude=float(coord[1]), point_count=end-first))
        first = end
    return result


def _density(t, xy, cfg, check):
    n = len(t)
    visited, queued = np.zeros(n, bool), np.zeros(n, bool)
    labels = np.full(n, -1, dtype=int)
    def neighbors(i):
        lo = int(np.searchsorted(t, t[i]-cfg.eps_time_seconds, side='left'))
        hi = int(np.searchsorted(t, t[i]+cfg.eps_time_seconds, side='right'))
        d = haversine_m(xy[i,0], xy[i,1], xy[lo:hi,0], xy[lo:hi,1])
        return np.flatnonzero(d <= cfg.radius_m)+lo
    cluster = 0
    for i in range(n):
        if i % 128 == 0:
            check()
        if visited[i]:
            continue
        visited[i] = True
        near = neighbors(i)
        if len(near) < cfg.min_points:
            continue
        labels[i] = cluster
        queue = deque(near.tolist())
        queued[near] = True
        while queue:
            j = queue.popleft()
            if not visited[j]:
                visited[j] = True
                if j % 128 == 0:
                    check()
                more = neighbors(j)
                if len(more) >= cfg.min_points:
                    new = more[~queued[more]]
                    queued[new] = True; queue.extend(new.tolist())
            if labels[j] < 0:
                labels[j] = cluster
        cluster += 1
    result = []
    for label in range(cluster):
        indices = np.flatnonzero(labels == label)
        a, b = indices[0], indices[-1]
        if t[b]-t[a] < cfg.dwell_minutes*60:
            continue
        lat, lon = representative(xy[indices])
        result.append(dict(start=float(t[a]), end=float(t[b]), latitude=lat, longitude=lon,
            point_count=len(indices)))
    return result


def detect(t, coords, segments, config, check=lambda: None):
    """Independent case/trajectory; input order is preserved, ties are not reordered."""
    t, coords, segments = np.asarray(t, float), np.asarray(coords, float), np.asarray(segments)
    if config.method not in METHODS:
        raise ValueError(config.method)
    if config.radius_m <= 0 or config.dwell_minutes <= 0 or config.eps_time_seconds <= 0 or config.min_points < 1:
        raise ValueError('Nonpositive detector parameter')
    if len(t) != len(coords) or len(t) != len(segments):
        raise ValueError('Input length mismatch')
    if not len(t):
        return []
    if (coords.shape != (len(t), 2) or not np.isfinite(coords).all() or not np.isfinite(t).all()
            or np.any(np.diff(t) <= 0) or np.any(np.abs(coords[:,0])>90) or np.any(np.abs(coords[:,1])>180)):
        raise ValueError('Invalid observation arrays')
    cuts = np.flatnonzero(np.r_[True, (np.diff(t)>config.max_gap_seconds) | (segments[1:]!=segments[:-1])])
    ends = np.r_[cuts[1:], len(t)]
    events = []
    for a, b in zip(cuts, ends):
        if b-a < 2 or t[b-1]-t[a] < config.dwell_minutes*60:
            continue
        events.extend((_density if config.method=='st_dbscan' else _scan)(t[a:b], coords[a:b], config, check))
    return sorted(events, key=lambda e: (e['start'],e['end'],e['latitude'],e['longitude']))
