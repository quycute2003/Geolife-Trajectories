"""Parallel real-data execution with exact per-user checkpoints and shared budgets.

Frozen algorithms and metrics stay unchanged. Parallel detector timings are
descriptive and must not replace the protocol's controlled serial timing gate.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import gzip
import itertools
import multiprocessing as mp
import os
from pathlib import Path
import pickle
import subprocess
import sys
import time

import numpy as np
import pandas as pd

from . import benchmark_jobs as jobs
from . import benchmark_parallel as engine
from .benchmark_synthetic import digest, file_hash, iter_trajectories, memory_usage, available_memory


REVISION = 'b4-real-parallel-v1'


def execution_lock(root, out):
    root, out = Path(root), Path(out)
    original = jobs.validate_lock(root, out)
    source = root / 'src/geolife_inference/benchmark_real_parallel.py'
    policy = dict(revision=REVISION, parent_lock_hash=original['lock_hash'],
                  runner_sha256=file_hash(source),
                  engine_sha256=file_hash(root / 'src/geolife_inference/benchmark_parallel.py'),
                  permitted_workers=list(range(1, 11)),
                  timing='Mixed serial/parallel real timings are descriptive; gate (d) unconfirmed',
                  inputs='Pickled original iterator frames preserve float64 values and row order')
    policy['execution_hash'] = digest(policy)
    path = out / 'real_parallel_execution_lock.json'
    if path.exists():
        if jobs.readj(path) != policy:
            raise ValueError('Real parallel execution changed; a new version is required')
    else:
        engine.atomic_json(path, policy)
    return policy


def prepare_inputs(root, out):
    """One shared CSV pass, lossless per-trajectory cache. No preprocessing."""
    root, out = Path(root), Path(out)
    lock = jobs.validate_lock(root, out)
    directory = out / 'real_parallel_inputs'
    source = root / 'artifacts/preprocessing/cleaned_points.csv.gz'
    st = source.stat()
    profile = jobs.readj(root / 'artifacts/benchmark/b1/profiles_v1/profile_audit.json')
    if (st.st_size, st.st_mtime_ns) != (profile['cleaned_bytes'], profile['cleaned_mtime_ns']):
        raise ValueError('Cleaned input changed')
    path = directory / 'audit.json'
    if path.exists():
        audit = jobs.readj(path)
        if audit['status'] != 'completed':
            raise ValueError('Incomplete input cache; inspect before rebuilding')
        if audit['lock_hash'] != lock['lock_hash']:
            raise ValueError('Input cache lock mismatch')
        return audit
    directory.mkdir()
    budget = jobs.JobBudget(jobs.ledger(root, out))
    audit = dict(status='running', lock_hash=lock['lock_hash'], users={},
                 cleaned_bytes=st.st_size, cleaned_mtime_ns=st.st_mtime_ns)
    engine.atomic_json(path, audit)
    try:
        prep = jobs.readj(root / 'artifacts/preprocessing/audit.json')
        seen_points = seen_trajs = 0
        for user, frames in itertools.groupby(iter_trajectories(source), key=lambda f: str(f.user_id.iloc[0])):
            points = trajectories = max_frame_bytes = max_frame_points = 0
            cache = directory / f'{user}.pkl.gz'
            with gzip.open(cache, 'wb', compresslevel=1) as stream:
                for frame in frames:
                    budget.check()
                    pickle.dump(frame, stream, protocol=5)
                    points += len(frame)
                    trajectories += 1
                    max_frame_bytes = max(max_frame_bytes, int(frame.memory_usage(deep=True).sum()))
                    max_frame_points = max(max_frame_points, len(frame))
            own = next((v for v in prep.get('per_user', []) if str(v['user_id']) == user), None)
            if own and (points, trajectories) != (own['output_points'], own['trajectory_files']):
                raise ValueError(f'{user}: input cache quota mismatch')
            audit['users'][user] = dict(points=points, trajectories=trajectories,
                                       max_frame_bytes=max_frame_bytes, max_frame_points=max_frame_points,
                                       sha256=file_hash(cache))
            seen_points += points
            seen_trajs += trajectories
            print(f'Input cache: {len(audit["users"])}/{len(prep["expected_users"])} users ({user})', flush=True)
        if (sorted(audit['users']) != sorted(prep['expected_users']) or
                seen_points != prep['totals']['output_points'] or seen_trajs != prep['expected_trajectory_files']):
            raise ValueError('Incomplete cached input scope')
        if (source.stat().st_size, source.stat().st_mtime_ns) != (st.st_size, st.st_mtime_ns):
            raise ValueError('Input changed while caching')
        audit.update(status='completed', points=seen_points, trajectories=seen_trajs, **budget.summary())
        engine.atomic_json(path, audit)
        return audit
    except BaseException as error:
        audit.update(status='failed', error=f'{type(error).__name__}: {error}', **budget.summary())
        engine.atomic_json(path, audit)
        raise


def _frames(path):
    # Only read the locally generated, hash-checked trusted cache.
    with gzip.open(path, 'rb') as stream:
        while True:
            try:
                yield pickle.load(stream)
            except EOFError:
                return


def _run_user(payload):
    root, out, user, records, expected, execution_hash = payload
    root, out = Path(root), Path(out)
    policy = execution_lock(root, out)
    if policy['execution_hash'] != execution_hash:
        raise ValueError('Worker execution mismatch')
    cache = out / 'real_parallel_inputs' / f'{user}.pkl.gz'
    if file_hash(cache) != expected['sha256']:
        raise ValueError('Cached user input changed')
    configs = [jobs.DetectorConfig(**{k: v for k, v in r.items() if k != 'config_id'}) for r in records]
    clock = engine.WorkerClock([c.config_id for c in configs])
    masks = jobs.load_label_masks(root)
    baseline = pd.read_csv(root / 'artifacts/stays/stays.csv', dtype={'user_id': str, 'trajectory_id': str})
    baseline = baseline.loc[baseline.user_id.eq(user)].copy()
    for name in ['start_time', 'end_time']:
        baseline[name] = pd.to_datetime(baseline[name], utc=True).astype('int64') / 1e9
    events = {c.config_id: {} for c in configs}
    timing = {c.config_id: 0. for c in configs}
    points = trajectories = 0
    for frame in _frames(cache):
        clock.check()
        if not frame.user_id.eq(user).all():
            raise ValueError('Wrong user in cache')
        points += len(frame)
        trajectories += 1
        key = str(frame.trajectory_id.iloc[0])
        t = pd.to_datetime(frame.timestamp, utc=True).astype('int64').to_numpy() / 1e9
        xy = frame[['latitude', 'longitude']].to_numpy(float)
        seg = frame.observation_segment.to_numpy()
        shift = int(digest([user, key])[:8], 16) % len(configs)
        for c in configs[shift:] + configs[:shift]:
            start = time.perf_counter()
            with clock.detector(c.config_id):
                pred = jobs.detect(t, xy, seg, c, clock.check)
            timing[c.config_id] += time.perf_counter() - start
            events[c.config_id][key] = pred
    if (points, trajectories) != (expected['points'], expected['trajectories']):
        raise ValueError('Cached real workload quota mismatch')
    rows, flat = [], []
    for c in configs:
        e = [dict(trajectory_id=k, **v) for k, values in events[c.config_id].items() for v in values]
        dwell = sum(v['end'] - v['start'] for v in e)
        rows.append(dict(user_id=user, **c.record(), stays=len(e), stay_dwell_minutes=dwell / 60,
                         detector_seconds=timing[c.config_id], processed_points=points,
                         processed_trajectories=trajectories, **jobs.motor_exposure(e, masks.get(user, []))))
        flat.extend(dict(config_id=c.config_id, **v) for v in e)
    own = baseline.sort_values(['trajectory_id', 'start_time', 'end_time'])
    actual = sorted([dict(trajectory_id=k, **e) for k, values in events[jobs.BASELINE_ID].items() for e in values],
                    key=lambda e: (e['trajectory_id'], e['start'], e['end']))
    if len(own) != len(actual):
        raise ValueError(f'{user}: baseline count mismatch')
    for x, y in zip(own.itertuples(), actual):
        if (x.trajectory_id != y['trajectory_id'] or x.start_time != y['start'] or x.end_time != y['end'] or
                x.point_count != y['point_count'] or not np.allclose([x.latitude, x.longitude],
                    [y['latitude'], y['longitude']], rtol=0, atol=1e-9)):
            raise ValueError(f'{user}: baseline event mismatch')
    edges = []
    for method in jobs.METHODS:
        for dwell in jobs.DURATIONS:
            for radius in (50, 150, 200):
                clock.check()
                left = jobs.DetectorConfig(method, 100, dwell).config_id
                right = jobs.DetectorConfig(method, radius, dwell).config_id
                edges.append(dict(user_id=user, method=method, edge=f'r100_to_{radius}_d{dwell}',
                                  **jobs._stability(events[left], events[right])))
        for radius in jobs.RADII:
            clock.check()
            left = jobs.DetectorConfig(method, radius, 10).config_id
            right = jobs.DetectorConfig(method, radius, 20).config_id
            edges.append(dict(user_id=user, method=method, edge=f'd10_to_20_r{radius}',
                              **jobs._stability(events[left], events[right])))
    directory = out / 'real'
    event_path = directory / f'{user}_events.csv.gz'
    metric_path = directory / f'{user}_metrics.csv'
    edge_path = directory / f'{user}_edges.csv'
    pd.DataFrame(flat, columns=['config_id', 'trajectory_id', 'start', 'end', 'latitude', 'longitude', 'point_count']).to_csv(event_path, index=False)
    pd.DataFrame(rows).to_csv(metric_path, index=False)
    pd.DataFrame(edges).to_csv(edge_path, index=False)
    return dict(user=user, files=[p.name for p in [event_path, metric_path, edge_path]],
                pid=os.getpid(), points=points, trajectories=trajectories)


def run_real(root, out, workers=10, resume=True):
    root, out = Path(root), Path(out)
    if workers not in range(1, 11):
        raise ValueError('Workers must be between 1 and 10')
    with engine._coordinator_lease(out):
        if (out / 'real/audit.json').exists() and jobs.readj(out / 'real/audit.json')['status'] == 'running':
            raise RuntimeError('Stop the current real job before parallel resume')
        policy = execution_lock(root, out)
        cache = prepare_inputs(root, out)
        lock, directory, audit, original = jobs._start(root, out, 'real', resume)
        records = lock['main_configs']
        ids = [r['config_id'] for r in records]
        ctx = mp.get_context('spawn')
        cancel = ctx.Event()
        counters = ctx.Array('d', workers * len(ids))
        pids = ctx.Array('i', workers)
        slots = ctx.Value('i', 0)
        budget = engine.ParallelBudget(original.used, original.config_seconds, original.historical,
                                       counters, pids, ids, workers)
        budget.start, budget.cap = original.start, original.cap
        budget.config_peak = original.config_peak
        expected = sorted(cache['users'])
        if not set(audit['completed_users']) <= set(expected):
            raise ValueError('Unknown completed real user')
        inherited = audit.setdefault('inherited_serial_users', list(audit['completed_users']))
        audit.update(execution_mode='parallel_users', workers=workers, coordinator_pid=os.getpid(),
                     real_parallel_execution_hash=policy['execution_hash'],
                     parallel_attempt_id=digest([os.getpid(), time.time_ns()]),
                     timing_scope='mixed serial/parallel real detector wall time; descriptive only',
                     gate_d_timing_eligible=False)
        audit['attempts'][-1].update(execution_mode='parallel_users', workers=workers,
                                     real_parallel_execution_hash=policy['execution_hash'])
        if audit.get('error'):
            audit['previous_attempt_error'] = audit.pop('error')
        pending = iter(u for u in expected if u not in audit['completed_users'])
        active, started, finished = {}, {}, set()
        failed = None
        pool = None

        def commit(result):
            user = result['user']
            if user in audit['completed_users']:
                raise ValueError('Duplicate real checkpoint')
            for name in result['files']:
                audit['output_hashes'][name] = file_hash(directory / name)
            audit['completed_users'] = sorted(audit['completed_users'] + [user])
            audit.update(budget.summary())
            engine.atomic_json(directory / 'audit.json', audit)
            print(f'Real parallel: {len(audit["completed_users"])}/{len(expected)} users completed ({user})', flush=True)

        def submit():
            user = next(pending, None)
            if user is not None:
                future = pool.submit(_run_user, (str(root), str(out), user, records,
                                                 cache['users'][user], policy['execution_hash']))
                active[future], started[user] = user, time.time()

        try:
            pool = ProcessPoolExecutor(max_workers=workers, mp_context=ctx, initializer=engine._initialize,
                                       initargs=(cancel, counters, pids, slots, len(ids)))
            for _ in range(workers):
                submit()
            while active:
                budget.check()
                stop = out / 'real_parallel_stop.json'
                if stop.exists() and jobs.readj(stop).get('attempt_id') == audit['parallel_attempt_id']:
                    raise InterruptedError('User requested stop')
                audit.update(active_users=sorted(active.values()), worker_pids=[p for p in pids if p],
                             active_user_started_epoch={u: started[u] for u in active.values()},
                             **budget.summary())
                engine.atomic_json(directory / 'audit.json', audit)
                ready, _ = wait(active, timeout=1, return_when=FIRST_COMPLETED)
                for future in ready:
                    result = future.result()
                    finished.add(future)
                    commit(result)
                    active.pop(future)
                    submit()
            if audit['completed_users'] != expected:
                raise ValueError('Missing real user checkpoints')
            totals = {u: pd.read_csv(directory / f'{u}_metrics.csv').iloc[0] for u in expected}
            points = sum(int(t.processed_points) for t in totals.values())
            trajectories = sum(int(t.processed_trajectories) for t in totals.values())
            if (points, trajectories) != (cache['points'], cache['trajectories']):
                raise ValueError('Real global quota mismatch')
            audit.update(users=len(expected), configs=len(records), processed_points=points,
                         processed_trajectories=trajectories, baseline_parity_users=len(expected))
            budget.check()
        except BaseException as error:
            failed = error
            cancel.set()
        finally:
            if pool is not None:
                if failed:
                    cancel.set()
                pool.shutdown(wait=True, cancel_futures=True)
                for future in list(active):
                    if future.done() and not future.cancelled() and future.exception() is None and future not in finished:
                        commit(future.result())
            stats = budget.summary()
            state = 'failed' if failed else 'completed'
            audit.update(status=state, active_users=[], worker_pids=[], active_user_started_epoch={}, **stats)
            audit['attempts'][-1].update(status=state, **stats)
            if failed:
                audit['error'] = f'{type(failed).__name__}: {failed}'
            engine.atomic_json(directory / 'audit.json', audit)
        if failed:
            raise failed
        return audit


def launch(root, out, workers=10, resume=True):
    root, out = Path(root).resolve(), Path(out).resolve()
    if workers not in range(1, 11):
        raise ValueError('Workers must be between 1 and 10')
    jobs.validate_lock(root, out)
    path = out / 'real/audit.json'
    audit = jobs.readj(path) if path.exists() else {}
    if audit.get('status') == 'running':
        return dict(status='already_running', pid=audit.get('coordinator_pid'), workers=audit.get('workers', 1))
    if audit.get('status') == 'completed':
        return dict(status='completed')
    env = os.environ.copy()
    env['PYTHONPATH'] = str(root / 'src') + os.pathsep + env.get('PYTHONPATH', '')
    for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
        env[name] = '1'
    args = [sys.executable, '-u', '-m', 'geolife_inference.benchmark_real_parallel',
            '--root', str(root), '--out', str(out), '--workers', str(workers)]
    if resume:
        args.append('--resume')
    with (out / 'real_parallel.log').open('ab') as stdout, (out / 'real_parallel.stderr.log').open('ab') as stderr:
        process = subprocess.Popen(args, cwd=root, env=env, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    return dict(status='launched', pid=process.pid, workers=workers)


def request_stop(out):
    out = Path(out)
    audit = jobs.readj(out / 'real/audit.json')
    engine.atomic_json(out / 'real_parallel_stop.json', dict(attempt_id=audit.get('parallel_attempt_id')))


def status(out):
    out = Path(out)
    path = out / 'real/audit.json'
    if not path.exists():
        return dict(status='not_started')
    audit = jobs.readj(path)
    return dict(status=audit['status'], completed_users=len(audit['completed_users']),
                active_users=audit.get('active_users', []), workers=audit.get('workers', 1),
                worker_pids=audit.get('worker_pids', []),
                aggregate_peak_mib=round(audit.get('aggregate_peak_working_set_bytes', 0) / 1024**2, 1),
                ram_cap_mib=round(audit.get('ram_cap_bytes', 0) / 1024**2, 1),
                compute_used_hours=round(audit.get('compute_used_after_seconds', 0) / 3600, 3),
                error=audit.get('error'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=10)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    mp.freeze_support()
    run_real(args.root, args.out, args.workers, args.resume)
