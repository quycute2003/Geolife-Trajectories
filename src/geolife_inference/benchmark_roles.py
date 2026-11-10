"""B5: paired role-rule comparisons using immutable B4 stay checkpoints.

Full-data jobs are explicitly started from NB10. No detector, preprocessing,
baseline artifact or B4 selection/final decision is changed by this module.
"""
from __future__ import annotations

from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import gzip
from importlib.metadata import version
import itertools
import json
import os
from pathlib import Path
import pickle
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import benchmark_jobs as jobs
from .benchmark_synthetic import digest, file_hash, write_json
from .clustering import MODEL_VERSIONS, group_locations
from .config import Config
from .features import (_coverage_summary, _observation_runs, cluster_features,
                       temporal_summary, union_intervals)
from .geo import haversine_m, representative
from .inference import role_candidates, rank_role

REVISION = 'b5-roles-v1'
RADII = (100, 150)
RULES = ('score', 'simple')
ROLES = ('home', 'office')
UTC = timezone.utc
MATCH_METERS = 200.0
MODULES = ('benchmark_roles.py', 'clustering.py', 'config.py', 'features.py',
           'inference.py', 'geo.py', 'benchmark_jobs.py', 'benchmark_synthetic.py')


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _csv(path):
    return pd.read_csv(path, dtype={'user_id': str, 'trajectory_id': str})


def _used(root, out):
    values = [jobs.ledger(root, root / 'artifacts/benchmark/b4/run_v1')]
    if (out / 'lock.json').exists():
        values.append(_read(out / 'lock.json')['compute_used_after_seconds'])
    for path in out.glob('*/audit.json'):
        values.append(_read(path).get('compute_used_after_seconds', 0))
    return max(values)


def _check_files(directory, hashes):
    for name, expected in hashes.items():
        if file_hash(directory / name) != expected:
            raise ValueError(f'Input/checkpoint đã đổi: {directory / name}')


def register(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if (out / 'lock.json').exists():
        return validate(root, out)
    if out.exists():
        raise FileExistsError('B5 namespace có sẵn nhưng thiếu lock; không ghi đè.')
    start = time.perf_counter()
    b4 = root / 'artifacts/benchmark/b4/run_v1'
    jobs.validate_lock(root, b4)
    real, prep = _read(b4 / 'real/audit.json'), _read(root / 'artifacts/preprocessing/audit.json')
    nb5 = _read(root / 'artifacts/inference/audit.json')
    cov = _read(root / 'artifacts/inference/coverage_audit.json')
    cache = _read(b4 / 'real_parallel_inputs/audit.json')
    users = sorted(prep['expected_users'])
    if (real['status'] != 'completed' or sorted(real['completed_users']) != users
            or real.get('baseline_parity_users') != len(users)
            or nb5['status'] != 'completed' or cov['status'] != 'completed'
            or cache['status'] != 'completed' or sorted(cache['users']) != users):
        raise ValueError('Cần B4 real, cache GPS và NB05 completed đủ manifest.')
    if file_hash(root / 'artifacts/inference/coverage.csv') != cov['coverage_sha256']:
        raise ValueError('NB05 coverage checksum không khớp.')
    stat = (root / 'artifacts/preprocessing/cleaned_points.csv.gz').stat()
    if {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns} != nb5['input_fingerprints']['cleaned_gps']:
        raise ValueError('Cleaned GPS khác nguồn NB05.')
    for relative, expected in nb5['input_fingerprints']['tables'].items():
        if file_hash(root / relative.replace('\\', '/')) != expected:
            raise ValueError(f'Nguồn NB05 đã đổi: {relative}')
    if cov['key']['temporal_config'] != {k: nb5['config'][k] for k in cov['key']['temporal_config']}:
        raise ValueError('Coverage và config NB05 khác nhau.')
    if cov['processed_users'] != len(users) or nb5['processed_users'] != len(users):
        raise ValueError('NB05 thiếu user.')
    names = ['artifacts/preprocessing/audit.json', 'artifacts/inference/audit.json',
             'artifacts/inference/coverage_audit.json', 'artifacts/inference/coverage.csv',
             'artifacts/inference/decisions.csv', 'artifacts/locations/audit.json',
             'artifacts/benchmark/b4/run_v1/real/audit.json',
             'artifacts/benchmark/b4/run_v1/real_parallel_inputs/audit.json',
             'reports/cp1/role_protocol.md']
    lock = dict(revision=REVISION, users=users, b4_lock_hash=real['lock_hash'],
                config=nb5['config'], methods=list(MODEL_VERSIONS), radii=list(RADII),
                rules=list(RULES), source_hashes={n: file_hash(root / n) for n in names},
                code_hashes={n: file_hash(root / 'src/geolife_inference' / n) for n in MODULES},
                versions={n: version(n) for n in ['pandas', 'numpy', 'scikit-learn',
                                                 'timezonefinder', 'timezonefinder-data', 'tzdata']},
                real_hashes=real['output_hashes'], cache_hashes=cache['users'],
                expected_points=real['processed_points'], expected_trajectories=real['processed_trajectories'],
                choice='User chose r150/d10 for exploratory B5 comparison with r100/d10; not a B4 winner.',
                compute_used_after_seconds=_used(root, out) + time.perf_counter() - start)
    if lock['compute_used_after_seconds'] >= 86400:
        raise TimeoutError('Đã hết trần compute 24 giờ.')
    lock['lock_hash'] = digest(lock)
    out.mkdir(parents=True)
    write_json(out / 'lock.json', lock)
    return lock


def validate(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    lock = _read(out / 'lock.json')
    if digest({k: v for k, v in lock.items() if k != 'lock_hash'}) != lock['lock_hash']:
        raise ValueError('B5 lock đã đổi.')
    _check_files(root, lock['source_hashes'])
    _check_files(root / 'src/geolife_inference', lock['code_hashes'])
    for name, expected in lock['versions'].items():
        if version(name) != expected:
            raise ValueError(f'Phiên bản {name} đã đổi; cần namespace mới.')
    return lock


@contextmanager
def _writer_lease(out):
    handle = (Path(out) / '.writer.lock').open('a+b')
    try:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('Một job B5 khác đang chạy; không khởi chạy trùng.') from None
    try:
        yield
    finally:
        handle.close()  # OS releases the lease on close or process exit.


def _stage(root, out, name, action, resume=True):
    with _writer_lease(out):
        return _run_stage(root, out, name, action, resume)


def _run_stage(root, out, name, action, resume=True):
    root, out = Path(root).resolve(), Path(out).resolve()
    lock = validate(root, out)
    directory = out / name
    path = directory / 'audit.json'
    audit = _read(path) if path.exists() else dict(status='prepared', lock_hash=lock['lock_hash'],
               completed_users=[], output_hashes={}, attempts=[], config_compute_seconds={})
    if audit['lock_hash'] != lock['lock_hash']:
        raise ValueError('Checkpoint thuộc B5 lock khác.')
    _check_files(directory, audit['output_hashes'])
    if audit['status'] == 'completed':
        print(f'{name}: tái dùng completed, checksum khớp', flush=True)
        return audit
    if directory.exists() and not resume:
        raise FileExistsError('Stage chưa hoàn tất; đặt RESUME=True để tiếp tục.')
    directory.mkdir(exist_ok=True)
    historical = {}
    for a in out.glob('*/audit.json'):
        if a == path:
            continue
        for key, seconds in _read(a).get('config_compute_seconds', {}).items():
            historical[key] = historical.get(key, 0) + seconds
    budget = jobs.JobBudget(_used(root, out), audit.get('config_compute_seconds'), historical)
    audit['attempts'].append(dict(status='running', used_before_seconds=budget.used))
    audit['status'] = 'running'
    audit.pop('error', None)
    write_json(path, audit)
    try:
        action(lock, directory, audit, budget)
        if sorted(audit['completed_users']) != lock['users']:
            raise ValueError('Stage chưa đủ user manifest.')
        budget.check()
        audit['status'] = 'completed'
        audit['attempts'][-1]['status'] = 'completed'
    except BaseException as error:
        audit['status'] = 'incomplete'
        audit['error'] = f'{type(error).__name__}: {error}'
        audit['attempts'][-1]['status'] = 'incomplete'
        raise
    finally:
        audit.update(budget.summary())
        write_json(path, audit)
    return audit


def _checkpoint(directory, audit, budget, user, names):
    budget.check()
    for name in names:
        audit['output_hashes'][name] = file_hash(directory / name)
    audit['completed_users'].append(user)
    audit.update(budget.summary())
    write_json(directory / 'audit.json', audit)
    print(f'{directory.name}: {len(audit["completed_users"])}/{audit["total_users"]} user ({user})', flush=True)


def _atomic_csv(table, path):
    temporary = path.with_suffix(path.suffix + '.partial')
    table.to_csv(temporary, index=False)
    temporary.replace(path)


def simple_role(locations, coverage, config, role):
    """Same eligibility; lexicographic days/dwell, no score/share/margin gate."""
    eligible = [c for c in role_candidates(locations, coverage, config, role) if c['eligible']]
    eligible.sort(key=lambda c: (-c['role_visit_days'], -c['role_dwell_minutes']))
    if not eligible:
        return dict(status='unknown', reason='insufficient_evidence', candidate=None)
    best = eligible[0]
    if (len(eligible) > 1 and eligible[1]['role_visit_days'] == best['role_visit_days']
            and abs(eligible[1]['role_dwell_minutes'] - best['role_dwell_minutes']) <= 1e-8):
        return dict(status='unknown', reason='tied_days_and_dwell', candidate=None)
    return dict(status='predicted', reason='unique_days_dwell_top', candidate=best)


def _stays(root, lock, user):
    source = root / 'artifacts/benchmark/b4/run_v1/real'
    name = f'{user}_events.csv.gz'
    _check_files(source, {name: lock['real_hashes'][name]})
    data = _csv(source / name)
    result = {}
    for radius in RADII:
        g = data.loc[data.config_id.eq(f'fixed_anchor_r{radius}_d10')].copy()
        g['user_id'] = user
        for name, epoch in [('start_time', 'start'), ('end_time', 'end')]:
            g[name] = pd.to_datetime(g[epoch], unit='s', utc=True)
        g['duration_minutes'] = (g.end - g.start) / 60
        g['stay_id'] = [digest([user, r.trajectory_id, r.start, r.end])[:24] for r in g.itertuples()]
        if g.stay_id.duplicated().any() or (g.duration_minutes < 10).any():
            raise ValueError('Stay IDs/dwell không hợp lệ.')
        result[radius] = g.drop(columns=['config_id', 'start', 'end'])
    return result


def _coverage_rows(root):
    coverage = _csv(root / 'artifacts/inference/coverage.csv').set_index('user_id')
    if not coverage.index.is_unique:
        raise ValueError('Coverage user trùng.')
    return coverage


def _decisions(stays, coverage, config, radius, method, scenario, finder=None):
    grouped = group_locations(stays, config, method)
    if finder is None:
        locations = cluster_features(grouped, coverage, config)
    else:
        locations = []
        for _, frame in grouped.loc[grouped.cluster_id.ge(0)].groupby('cluster_id'):
            lat, lon = representative(frame[['latitude', 'longitude']].to_numpy())
            zone = finder.timezone_at(lng=float(lon), lat=float(lat)) or config.timezone
            locations.extend(cluster_features(frame, coverage, replace(config, timezone=zone)))
    features = {int(c['cluster_id']): c for c in locations}
    membership = {int(k): set(g.stay_id) for k, g in grouped.groupby('cluster_id') if int(k) >= 0}
    context = 'no_stays' if stays.empty else 'no_non_noise_cluster' if not locations else 'has_clusters'
    rows = []
    for rule, role in itertools.product(RULES, ROLES):
        decision = (rank_role if rule == 'score' else simple_role)(locations, coverage, config, role)
        candidate = decision['candidate']
        row = dict(scenario=scenario, radius_m=radius, method=method, rule=rule, role=role,
                   status=decision['status'], reason=decision['reason'], input_context=context,
                   stays=len(stays), clusters=len(locations), noise_stays=int(grouped.cluster_id.eq(-1).sum()),
                   observed_days=int(coverage['observed_days']), observed_minutes=float(coverage['observed_minutes']),
                   role_observed_days=int(coverage['night_observed_days' if role == 'home' else 'work_observed_days']),
                   role_observed_minutes=coverage.get('night_observed_minutes' if role == 'home' else 'work_observed_minutes'),
                   eligible_candidates=sum(c['eligible'] for c in role_candidates(locations, coverage, config, role)),
                   cluster_id=None, latitude=None, longitude=None, evidence_score=None,
                   role_dwell_minutes=None, role_visit_days=None, member_keys='[]')
        if candidate:
            row.update({k: candidate[k] for k in ['cluster_id', 'latitude', 'longitude', 'evidence_score',
                                                  'role_dwell_minutes', 'role_visit_days']})
            row['member_keys'] = json.dumps(sorted(membership[int(candidate['cluster_id'])]))
        rows.append(row)
    return rows, grouped, list(features.values())


def _baseline_parity(rows, expected):
    for row in rows:
        if row['radius_m'] != 100 or row['rule'] != 'score':
            continue
        match = expected.loc[expected.method.eq(row['method']) & expected.role.eq(row['role'])]
        if len(match) != 1:
            raise ValueError('NB05 baseline thiếu/trùng quyết định.')
        saved = match.iloc[0]
        for key in ['status', 'reason', 'input_context']:
            if row[key] != saved[key]:
                raise ValueError(f'Baseline NB05 parity khác {key}.')
        if row['status'] == 'predicted':
            for key in ['latitude', 'longitude', 'evidence_score', 'role_dwell_minutes', 'role_visit_days']:
                if not np.isclose(row[key], float(saved[key]), rtol=1e-10, atol=1e-8):
                    raise ValueError(f'Baseline NB05 parity khác {key}.')


def run_main(root, out, resume=True):
    root = Path(root).resolve()
    coverage = _coverage_rows(root)
    expected = _csv(root / 'artifacts/inference/decisions.csv')

    def action(lock, directory, audit, budget):
        audit['total_users'] = len(lock['users'])
        if set(coverage.index) != set(lock['users']):
            raise ValueError('Coverage không đủ user manifest.')
        config = Config(**lock['config'])
        for user in lock['users']:
            if user in audit['completed_users']:
                continue
            stays = _stays(root, lock, user)
            rows, assignments, features = [], [], []
            for radius, method in itertools.product(RADII, MODEL_VERSIONS):
                with budget.detector(f'b5_r{radius}_{method}'):
                    r, grouped, locs = _decisions(stays[radius], coverage.loc[user].to_dict(),
                                                config, radius, method, 'main')
                rows.extend(dict(user_id=user, **x) for x in r)
                assignments.append(grouped.assign(radius_m=radius, method=method))
                features.extend(dict(loc, radius_m=radius, method=method) for loc in locs)
            _baseline_parity(rows, expected.loc[expected.user_id.eq(user)])
            names = [f'{user}_decisions.csv', f'{user}_assignments.csv', f'{user}_features.json']
            _atomic_csv(pd.DataFrame(rows), directory / names[0])
            _atomic_csv(pd.concat(assignments, ignore_index=True), directory / names[1])
            write_json(directory / names[2], features)
            _checkpoint(directory, audit, budget, user, names)
        audit['baseline_parity_users'] = len(audit['completed_users'])
        audit['scope'] = 'full_dataset_exploratory_not_B4_final_confirmation'
    return _stage(root, Path(out), 'main', action, resume)


def _calendar_dates(intervals, zone_name):
    zone = ZoneInfo(zone_name)
    days = set()
    for start, end in intervals:
        day = start.astimezone(zone).date()
        while datetime.combine(day, datetime.min.time(), zone).astimezone(UTC) < end:
            midnight = datetime.combine(day, datetime.min.time(), zone).astimezone(UTC)
            next_midnight = datetime.combine(day + timedelta(days=1), datetime.min.time(), zone).astimezone(UTC)
            if min(end, next_midnight) > max(start, midnight):
                days.add(day)
            day += timedelta(days=1)
    return days


def _role_dates(intervals, config, role):
    zone = ZoneInfo(config.timezone)
    result = set()
    for start, end in intervals:
        day = start.astimezone(zone).date()
        while datetime.combine(day, datetime.min.time(), zone).astimezone(UTC) < end:
            def at(hour, date=day):
                return datetime.combine(date, datetime.min.time().replace(hour=hour), zone).astimezone(UTC)
            windows = ([(at(0), at(config.night_end_hour)),
                        (at(config.night_start_hour), at(0, day + timedelta(days=1)))]
                       if role == 'home' else [(at(config.work_start_hour), at(config.work_end_hour))]
                       if day.weekday() < 5 else [])
            if any(min(end, b) > max(start, a) for a, b in windows):
                result.add(day)
            day += timedelta(days=1)
    return result


def _cov(intervals, days, first, last, config):
    value = _coverage_summary(intervals, days, first, last, config)
    summary = temporal_summary(intervals, config)
    value.update(night_observed_minutes=summary['night_dwell_minutes'],
                 work_observed_minutes=summary['weekday_daytime_dwell_minutes'])
    return value


def _clip(intervals, start, end):
    return [(max(a, start), min(b, end)) for a, b in intervals if min(b, end) > max(a, start)]


def period_stays(stays, start, end):
    """Exclude boundary events whose centers may depend on out-of-block fixes."""
    part = stays.loc[stays.start_time.ge(start) & stays.end_time.lt(end)].copy()
    excluded = int(((stays.end_time > start) & (stays.start_time < end)).sum() - len(part))
    return part, excluded


def _frames(path):
    with gzip.open(path, 'rb') as stream:
        while True:
            try:
                yield pickle.load(stream)  # Only locally generated, hash-verified B4 input caches.
            except EOFError:
                return


def _finder():
    from timezonefinder import TimezoneFinder
    return TimezoneFinder(in_memory=False)


def _context(frames, config, finder, check=lambda: None, period_origin=None):
    """One GPS-cache pass; no stay detection. Pair zones use the left observed fix."""
    intervals, days, zoned_intervals, zoned_days = [], set(), {}, {}
    period_days = [set(), set()]
    period_first, period_last = [None, None], [None, None]
    first = last = None
    origin = period_origin
    points = trajectories = unknown = boundary_pairs = 0
    boundary_seconds = 0.0
    zone_counts = {}
    for frame in frames:
        check()
        if frame.empty:
            continue
        frame = frame.sort_values('timestamp', kind='stable').copy()
        times = pd.to_datetime(frame.timestamp, utc=True)
        frame['timestamp'] = times
        left, right = times.iloc[0].to_pydatetime(), times.iloc[-1].to_pydatetime()
        if origin is None:
            origin = datetime.combine(left.astimezone(ZoneInfo(config.timezone)).date(),
                                      datetime.min.time(), ZoneInfo(config.timezone)).astimezone(UTC)
        first, last = min(first, left) if first else left, max(last, right) if last else right
        points += len(frame); trajectories += 1
        days.update(times.dt.tz_convert(config.timezone).dt.date)
        runs = _observation_runs(frame, config)
        intervals.extend(runs)
        for i in range(2):
            start, end = origin + timedelta(days=28*i), origin + timedelta(days=28*(i+1))
            selected = times[(times >= start) & (times < end)]
            if len(selected):
                period_days[i].update(selected.dt.tz_convert(config.timezone).dt.date)
                a, b = selected.iloc[0].to_pydatetime(), selected.iloc[-1].to_pydatetime()
                period_first[i] = min(period_first[i], a) if period_first[i] else a
                period_last[i] = max(period_last[i], b) if period_last[i] else b
        # Batch lookup every observed fix; no dominant-zone assignment to a traveling user.
        zones = []
        for start in range(0, len(frame), 20000):
            check()
            part = frame.iloc[start:start+20000]
            zones.extend(finder.timezone_names_at(lngs=part.longitude.to_numpy(), lats=part.latitude.to_numpy()))
        unknown += sum(z is None for z in zones)
        zones = np.asarray([z or config.timezone for z in zones], dtype=object)
        for z in set(zones):
            mask = zones == z
            zone_counts[z] = zone_counts.get(z, 0) + int(mask.sum())
            zoned_days.setdefault(z, set()).update(times[mask].dt.tz_convert(z).dt.date)
        epochs = times.astype('int64').to_numpy() / 1e9
        dt = np.diff(epochs)
        segments = frame.observation_segment.to_numpy()
        valid = (dt > 0) & (dt <= config.max_gap_minutes*60) & (segments[1:] == segments[:-1])
        crosses = valid & (zones[1:] != zones[:-1])
        boundary_pairs += int(crosses.sum()); boundary_seconds += float(dt[crosses].sum())
        # Compress adjacent valid pairs with the same assigned (left-fix) zone.
        indices = np.flatnonzero(valid)
        if len(indices):
            cuts = np.r_[0, np.flatnonzero((np.diff(indices) != 1) |
                                           (zones[indices[1:]] != zones[indices[:-1]])) + 1, len(indices)]
            for a, b in zip(cuts[:-1], cuts[1:]):
                i, j = indices[a], indices[b-1] + 1
                zoned_intervals.setdefault(str(zones[i]), []).append(
                    (times.iloc[i].to_pydatetime(), times.iloc[j].to_pydatetime()))
    intervals = union_intervals(intervals)
    baseline = _cov(intervals, days, first, last, config)
    shifts = {str(shift): _cov(intervals, days, first, last, replace(config,
                night_start_hour=config.night_start_hour+shift, night_end_hour=config.night_end_hour+shift,
                work_start_hour=config.work_start_hour+shift, work_end_hour=config.work_end_hour+shift))
              for shift in [-1, 1]}
    periods = []
    for i in range(2):
        if origin is None:
            periods.append(dict(start=None, end=None, coverage=_cov([], set(), None, None, config)))
        else:
            start, end = origin + timedelta(days=28*i), origin + timedelta(days=28*(i+1))
            periods.append(dict(start=start.isoformat(), end=end.isoformat(),
                coverage=_cov(_clip(intervals, start, end), period_days[i], period_first[i], period_last[i], config)))
    localized = dict(baseline)
    localized_days, localized_nights, localized_work = set(), set(), set()
    night_minutes = work_minutes = 0.0
    for z, runs in zoned_intervals.items():
        runs = union_intervals(runs)
        cfg = replace(config, timezone=z)
        summary = temporal_summary(runs, cfg)
        localized_nights.update(_role_dates(runs, cfg, 'home'))
        localized_work.update(_role_dates(runs, cfg, 'office'))
        night_minutes += summary['night_dwell_minutes']; work_minutes += summary['weekday_daytime_dwell_minutes']
    for value in zoned_days.values():
        localized_days.update(value)
    localized.update(observed_days=len(localized_days), night_observed_days=len(localized_nights),
                     work_observed_days=len(localized_work), night_observed_minutes=night_minutes,
                     work_observed_minutes=work_minutes)
    if localized_days:
        localized['calendar_span_days'] = (max(localized_days)-min(localized_days)).days + 1
        localized['observed_day_fraction'] = len(localized_days) / localized['calendar_span_days']
    return dict(baseline=baseline, shifts=shifts, periods=periods, localized=localized,
                points=points, trajectories=trajectories, zone_counts=zone_counts,
                unknown_zone_points=unknown, cross_zone_pairs=boundary_pairs,
                cross_zone_pair_seconds=boundary_seconds,
                affected=unknown > 0 or any(z != config.timezone for z in zone_counts))


def run_context(root, out, resume=True):
    root = Path(root).resolve()
    saved = _coverage_rows(root)
    finder = _finder()

    def action(lock, directory, audit, budget):
        audit['total_users'] = len(lock['users'])
        config = Config(**lock['config'])
        source = root / 'artifacts/benchmark/b4/run_v1/real_parallel_inputs'
        for user in lock['users']:
            if user in audit['completed_users']:
                continue
            name = f'{user}.pkl.gz'
            _check_files(source, {name: lock['cache_hashes'][user]['sha256']})
            print(f'context: đang đọc GPS user {user}', flush=True)
            expected = saved.loc[user]
            first = pd.Timestamp(expected.first_timestamp)
            origin = (datetime.combine(first.to_pydatetime().astimezone(ZoneInfo(config.timezone)).date(),
                                       datetime.min.time(), ZoneInfo(config.timezone)).astimezone(UTC)
                      if not pd.isna(first) else None)
            data = _context(_frames(source / name), config, finder, budget.check, period_origin=origin)
            for key in ['observed_minutes', 'observed_days', 'night_observed_days', 'work_observed_days']:
                if not np.isclose(data['baseline'][key], expected[key], rtol=1e-10, atol=1e-7):
                    raise ValueError(f'{user}: coverage cache parity khác {key}.')
            for key, col in [('points', 'processed_points'), ('trajectories', 'processed_trajectories')]:
                if data[key] != int(expected[col]):
                    raise ValueError(f'{user}: scope GPS cache khác {col}.')
            name = f'{user}.json'
            write_json(directory / name, data)
            _checkpoint(directory, audit, budget, user, [name])
        all_data = [_read(directory / f'{u}.json') for u in lock['users']]
        if sum(d['points'] for d in all_data) != lock['expected_points'] or sum(d['trajectories'] for d in all_data) != lock['expected_trajectories']:
            raise ValueError('GPS context không đủ scope.')
        audit.update(processed_points=lock['expected_points'], processed_trajectories=lock['expected_trajectories'],
                     affected_users=[u for u, d in zip(lock['users'], all_data) if d['affected']],
                     unknown_zone_points=sum(d['unknown_zone_points'] for d in all_data))
    try:
        return _stage(root, Path(out), 'context', action, resume)
    finally:
        close = getattr(finder, 'close', None)
        if close:
            close()


def run_ablations(root, out, resume=True):
    root, out = Path(root).resolve(), Path(out).resolve()
    lock = validate(root, out)
    for stage in ['main', 'context']:
        audit = _read(out / stage / 'audit.json')
        if audit['status'] != 'completed':
            raise ValueError(f'Cần {stage} completed.')
        _check_files(out / stage, audit['output_hashes'])
    finder = _finder()

    def action(lock, directory, audit, budget):
        audit['total_users'] = len(lock['users'])
        config = Config(**lock['config'])
        for user in lock['users']:
            if user in audit['completed_users']:
                continue
            context = _read(out / 'context' / f'{user}.json')
            stays = _stays(root, lock, user)
            rows = []
            for radius, method in itertools.product(RADII, MODEL_VERSIONS):
                for shift in [-1, 1]:
                    cfg = replace(config, night_start_hour=config.night_start_hour+shift,
                                  night_end_hour=config.night_end_hour+shift,
                                  work_start_hour=config.work_start_hour+shift, work_end_hour=config.work_end_hour+shift)
                    with budget.detector(f'b5_r{radius}_{method}'):
                        r, _, _ = _decisions(stays[radius], context['shifts'][str(shift)], cfg,
                                             radius, method, f'shift_{shift:+d}')
                    rows.extend(r)
                with budget.detector(f'b5_r{radius}_{method}'):
                    r, _, _ = _decisions(stays[radius], context['localized'], config, radius, method,
                                         'timezone', finder=finder)
                for row in r:
                    row['timezone_affected_user'] = context['affected']
                    row['unknown_zone_points'] = context['unknown_zone_points']
                rows.extend(r)
                for i, period in enumerate(context['periods']):
                    part = stays[radius].iloc[:0].copy()
                    excluded = 0
                    if period['start'] is not None:
                        start, end = pd.Timestamp(period['start']), pd.Timestamp(period['end'])
                        # No centers/endpoints computed using fixes outside this block.
                        part, excluded = period_stays(stays[radius], start, end)
                    with budget.detector(f'b5_r{radius}_{method}'):
                        r, _, _ = _decisions(part, period['coverage'], config, radius, method, f'period_{i+1}')
                    for row in r:
                        coverage_minutes = period['coverage']['night_observed_minutes' if row['role'] == 'home' else 'work_observed_minutes']
                        row.update(period_start=period['start'], period_end=period['end'],
                                   boundary_stays_excluded=excluded,
                                   period_eligible=period['coverage']['observed_days'] >= 7 and coverage_minutes >= 60)
                    rows.extend(r)
            name = f'{user}_decisions.csv'
            _atomic_csv(pd.DataFrame([dict(user_id=user, **r) for r in rows]), directory / name)
            _checkpoint(directory, audit, budget, user, [name])
    try:
        return _stage(root, out, 'ablations', action, resume)
    finally:
        close = getattr(finder, 'close', None)
        if close:
            close()


def compare(left, right):
    """Compare on identical users; local cluster IDs never establish agreement."""
    key = ['user_id', 'role']
    if left.duplicated(key).any() or right.duplicated(key).any():
        raise ValueError('Comparison phải có một hàng mỗi user/role.')
    if set(map(tuple, left[key].to_numpy())) != set(map(tuple, right[key].to_numpy())):
        raise ValueError('Comparison thiếu user/role ở một phía.')
    merged = left.merge(right, on=key, suffixes=('_left', '_right'), validate='one_to_one')
    a, b = merged.status_left.eq('predicted'), merged.status_right.eq('predicted')
    both = a & b
    distances = np.full(len(merged), np.nan)
    if both.any():
        g = merged.loc[both]
        distances[both] = haversine_m(g.latitude_left.to_numpy(float), g.longitude_left.to_numpy(float),
                                     g.latitude_right.to_numpy(float), g.longitude_right.to_numpy(float))
    merged['distance_m'] = distances
    merged['same_place'] = both & (distances <= MATCH_METERS)
    merged['transition'] = merged.status_left + '→' + merged.status_right
    return merged


def _comparison_summary(data):
    both = data.status_left.eq('predicted') & data.status_right.eq('predicted')
    n, paired = len(data), int(both.sum())
    left_rate = float(data.status_left.eq('predicted').mean()) if n else np.nan
    right_rate = float(data.status_right.eq('predicted').mean()) if n else np.nan
    changed = int((data.loc[both, 'distance_m'] > MATCH_METERS).sum())
    return dict(users=n, both_predicted=paired, same_place=int(data.same_place.sum()),
                place_agreement= float(data.same_place.sum()/paired) if paired else np.nan,
                changed_over_200m=changed, changed_place_share=changed/paired if paired else np.nan,
                distance_median=float(data.loc[both, 'distance_m'].median()) if paired else np.nan,
                predicted_to_unknown=int(data.transition.eq('predicted→unknown').sum()),
                unknown_to_predicted=int(data.transition.eq('unknown→predicted').sum()),
                predicted_rate_left=left_rate, predicted_rate_right=right_rate,
                prediction_rate_delta_pp=100*(right_rate-left_rate),
                investigation_flag=bool((paired and changed/paired > .1) or abs(right_rate-left_rate) > .05))


def summarize(root, out, include_ablations=True, resume=True):
    root, out = Path(root).resolve(), Path(out).resolve()
    name = 'summary' if include_ablations else 'summary_main'

    def action(lock, directory, audit, budget):
        stages = ['main', 'ablations'] if include_ablations else ['main']
        tables = []
        for stage in stages:
            source = out / stage
            source_audit = _read(source / 'audit.json')
            if source_audit['status'] != 'completed' or sorted(source_audit['completed_users']) != lock['users']:
                raise ValueError(f'{stage} chưa completed đủ manifest.')
            _check_files(source, source_audit['output_hashes'])
            tables.extend(_csv(source / f'{u}_decisions.csv') for u in lock['users'])
        data = pd.concat(tables, ignore_index=True)
        keys = ['scenario', 'radius_m', 'method', 'rule', 'role']
        if data.duplicated(keys + ['user_id']).any():
            raise ValueError('Decision rows bị trùng.')
        rows = []
        for key, g in data.groupby(keys, sort=True):
            if set(g.user_id) != set(lock['users']):
                raise ValueError('Decision table thiếu user.')
            rows.append(dict(zip(keys, key), users=len(g), predicted=int(g.status.eq('predicted').sum()),
                             unknown=int(g.status.eq('unknown').sum()), prediction_rate=float(g.status.eq('predicted').mean())))
        _atomic_csv(pd.DataFrame(rows), directory / 'rates.csv')
        _atomic_csv(data.groupby(keys+['input_context', 'reason']).size().rename('users').reset_index(), directory / 'reasons.csv')
        data['coverage_tier'] = pd.cut(data.role_observed_days, [-1, 0, 2, 6, np.inf],
                                       labels=['0 ngày', '1–2 ngày', '3–6 ngày', '≥7 ngày'])
        strata = data.assign(predicted=data.status.eq('predicted')).groupby(
            keys+['coverage_tier'], observed=True).agg(users=('user_id', 'size'), predicted=('predicted', 'sum')).reset_index()
        strata['prediction_rate'] = strata.predicted / strata.users
        _atomic_csv(strata, directory / 'coverage_strata.csv')
        comparisons, details = [], []
        main = data[data.scenario.eq('main')]
        def add(left, right, labels, temporal=False):
            for role in ROLES:
                a, b = left[left.role.eq(role)], right[right.role.eq(role)]
                if temporal:
                    # Eligibility depends on GPS coverage, never on predicted status.
                    eligible = set(a.loc[a.period_eligible.eq(True), 'user_id']) & set(b.loc[b.period_eligible.eq(True), 'user_id'])
                    a, b = a[a.user_id.isin(eligible)], b[b.user_id.isin(eligible)]
                result = compare(a, b)
                label = dict(**labels, role=role)
                summary = _comparison_summary(result)
                summary['assessment'] = 'insufficient_cohort' if temporal and summary['users'] < 15 else 'descriptive'
                comparisons.append(dict(**label, **summary))
                if len(result):
                    details.append(result.assign(**labels))
        for radius, method in itertools.product(RADII, MODEL_VERSIONS):
            g = main[main.radius_m.eq(radius)&main.method.eq(method)]
            add(g[g.rule.eq('score')], g[g.rule.eq('simple')], dict(comparison='rule', radius_m=radius, method=method, rule='score→simple', scenario='main'))
        for method, rule in itertools.product(MODEL_VERSIONS, RULES):
            g = main[main.method.eq(method)&main.rule.eq(rule)]
            add(g[g.radius_m.eq(100)], g[g.radius_m.eq(150)], dict(comparison='radius', radius_m=150, method=method, rule=rule, scenario='100→150'))
        if include_ablations:
            for radius, method, rule in itertools.product(RADII, MODEL_VERSIONS, RULES):
                g = data[data.radius_m.eq(radius)&data.method.eq(method)&data.rule.eq(rule)]
                for scenario in ['shift_-1', 'shift_+1', 'timezone']:
                    add(g[g.scenario.eq('main')], g[g.scenario.eq(scenario)], dict(comparison=scenario, radius_m=radius, method=method, rule=rule, scenario=scenario))
                add(g[g.scenario.eq('period_1')], g[g.scenario.eq('period_2')],
                    dict(comparison='temporal', radius_m=radius, method=method, rule=rule, scenario='period_1→period_2'), temporal=True)
            inventory = []
            for user in lock['users']:
                c = _read(out / 'context' / f'{user}.json')
                inventory.append(dict(user_id=user, affected=c['affected'], points=c['points'],
                    zones=json.dumps(c['zone_counts'], sort_keys=True), unknown_zone_points=c['unknown_zone_points'],
                    cross_zone_pairs=c['cross_zone_pairs'], cross_zone_pair_seconds=c['cross_zone_pair_seconds']))
            _atomic_csv(pd.DataFrame(inventory), directory / 'timezone_inventory.csv')
            affected = {r['user_id'] for r in inventory if r['affected']}
            for radius, method, rule in itertools.product(RADII, MODEL_VERSIONS, RULES):
                g = data[data.radius_m.eq(radius)&data.method.eq(method)&data.rule.eq(rule)&data.user_id.isin(affected)]
                add(g[g.scenario.eq('main')], g[g.scenario.eq('timezone')],
                    dict(comparison='timezone_affected', radius_m=radius, method=method, rule=rule, scenario='timezone'))
        _atomic_csv(pd.DataFrame(comparisons), directory / 'comparisons.csv')
        _atomic_csv(pd.concat(details, ignore_index=True), directory / 'transitions.csv')
        _atomic_csv(data, directory / 'decisions.csv')
        names = ['rates.csv', 'reasons.csv', 'comparisons.csv', 'transitions.csv', 'decisions.csv', 'coverage_strata.csv']
        if include_ablations:
            names.append('timezone_inventory.csv')
        for n in names:
            audit['output_hashes'][n] = file_hash(directory / n)
        audit['completed_users'] = list(lock['users'])
        audit.update(total_users=len(lock['users']), decision_rows=len(data),
                     no_ground_truth=True, include_ablations=include_ablations)
    return _stage(root, out, name, action, resume)


def render(root, out, include_ablations=True, resume=True):
    root, out = Path(root).resolve(), Path(out).resolve()
    name = 'plots' if include_ablations else 'plots_main'

    def action(lock, directory, audit, budget):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        source = out / ('summary' if include_ablations else 'summary_main')
        a = _read(source / 'audit.json')
        if a['status'] != 'completed':
            raise ValueError('Summary chưa completed.')
        _check_files(source, a['output_hashes'])
        rates = pd.read_csv(source / 'rates.csv')
        comparisons = pd.read_csv(source / 'comparisons.csv')
        colors = {100: '#3465A4', 150: '#14968C'}
        names = []
        def save(fig, name):
            try:
                fig.tight_layout()
                fig.savefig(directory / name, dpi=130, bbox_inches='tight')
            finally:
                plt.close(fig)
            names.append(name); budget.check()
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharey=True)
        for i, method in enumerate(MODEL_VERSIONS):
            for j, role in enumerate(ROLES):
                ax = axes[i, j]
                g = rates[(rates.scenario=='main')&(rates.method==method)&(rates.role==role)]
                for radius in RADII:
                    values = [float(g[(g.radius_m==radius)&(g.rule==r)].prediction_rate.iloc[0])*100 for r in RULES]
                    x = np.arange(2) + (-.18 if radius==100 else .18)
                    bars = ax.bar(x, values, width=.35, label=f'{radius} m / 10 phút', color=colors[radius])
                    ax.bar_label(bars, fmt='%.1f%%', padding=3, fontsize=10)
                ax.set_xticks([0, 1], ['Score hiện tại', 'Rule đơn giản'])
                ax.set(title=f'{method} · {"Home" if role=="home" else "Office"}', ylabel='User được gán vai trò (%)', ylim=(0, 105))
                ax.legend(fontsize=9); ax.grid(axis='y', alpha=.2)
        fig.suptitle('B5 · Tỷ lệ gán Home/Office trên đủ user\nNhiều dự đoán hơn chưa đồng nghĩa đúng hơn', fontsize=15)
        save(fig, '01_ty_le_du_doan.png')
        for comparison, filename, title in [('rule', '02_so_rule.png', 'Đổi score sang rule đơn giản'),
                                             ('radius', '03_so_ban_kinh.png', 'Đổi bán kính stay 100 → 150 m')]:
            g = comparisons[comparisons.comparison.eq(comparison)].copy()
            g['label'] = g.apply(lambda r: f'{r.method}\n{r.radius_m} m · {r.rule} · {r.role}', axis=1)
            fig, axes = plt.subplots(1, 2, figsize=(14, 6))
            for ax, col, label in [(axes[0], 'changed_place_share', 'Đổi nơi >200 m / user cùng có dự đoán (%)'),
                                   (axes[1], 'prediction_rate_delta_pp', 'Thay đổi tỷ lệ dự đoán (điểm %)')]:
                val = g[col]*100 if col=='changed_place_share' else g[col]
                ax.barh(np.arange(len(g)), val, color='#3465A4')
                ax.set_yticks(np.arange(len(g)), g.label, fontsize=9)
                ax.set_xlabel(label); ax.grid(axis='x', alpha=.2)
            fig.suptitle(f'B5 · {title}\nMẫu số và predicted↔unknown xem bảng comparisons', fontsize=14)
            save(fig, filename)
        if include_ablations:
            g = comparisons[comparisons.comparison.isin(['shift_-1','shift_+1','timezone_affected'])].copy()
            fig, axes = plt.subplots(1, 3, figsize=(18, 10), sharex=True)
            for ax, scenario, title in zip(axes, ['shift_-1','shift_+1','timezone_affected'], ['Khung giờ −1 giờ','Khung giờ +1 giờ','Timezone · riêng user bị ảnh hưởng']):
                part = g[g.comparison.eq(scenario)]
                labels = part.apply(lambda r: f'{r.radius_m} m · {r.method}\n{r.rule} · {r.role}', axis=1)
                ax.barh(np.arange(len(part)), part.prediction_rate_delta_pp, color='#14968C')
                ax.set_yticks(np.arange(len(part)), labels, fontsize=9)
                ax.set(title=title, xlabel='Thay đổi tỷ lệ dự đoán (điểm %)'); ax.grid(axis='x', alpha=.2)
                if not part.users.gt(0).any():
                    ax.text(.5, .5, 'Không có user bị ảnh hưởng\nNo-op', transform=ax.transAxes, ha='center')
            fig.suptitle('B5 · Độ nhạy với giờ và timezone · Không đo accuracy', fontsize=15)
            save(fig, '04_do_nhay_gio_timezone.png')
            part = comparisons[comparisons.comparison.eq('temporal')]
            labels = part.apply(lambda r: f'{r.radius_m} m · {r.method} · {r.rule} · {r.role}', axis=1)
            fig, ax = plt.subplots(figsize=(12, 8))
            ax.barh(np.arange(len(part)), part.users, color='#3465A4')
            ax.set_yticks(np.arange(len(part)), labels, fontsize=10)
            ax.axvline(15, ls='--', color='#B56212', label='Cần ít nhất 15 user/role để tổng hợp')
            ax.set(title='B5 · Có đủ dữ liệu để so hai khối 28 ngày không?', xlabel='User có đủ coverage ở cả hai khối')
            ax.legend(); ax.grid(axis='x', alpha=.2)
            save(fig, '05_cohort_theo_thoi_gian.png')
        for n in names:
            audit['output_hashes'][n] = file_hash(directory / n)
        audit['completed_users'] = list(lock['users'])
        audit['total_users'] = len(lock['users'])
    return _stage(root, out, name, action, resume)
