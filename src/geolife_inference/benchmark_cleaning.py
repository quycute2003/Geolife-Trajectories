"""B3 cleaning sensitivity on real GPS. Isolated from the production policies."""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from .benchmark_synthetic import Budget, file_hash, write_json
from .config import load_config
from .data import GeoLifeSource, parse_plt
from .geo import haversine_m
from .preprocessing import (AUDIT_COUNTS, POINT_KEYS, TIME_KEYS, PreprocessingResult,
    _normalize, _basic_masks, _diameter, _mean_coordinate, _choose_conflict, _motion_columns)
from .stays import detect_stays, split_overlapping_stays

POLICIES = ('vote20', 'vote10', 'vote50', 'mean20', 'no_merge', 'duplicate_altitude')
REVISION = 'b3-cleaning-v1.1'
DIFF_COLUMNS = ['kind','baseline_events','variant_events','baseline_keys','variant_keys',
    'start_delta_seconds','end_delta_seconds','center_delta_m','dwell_delta_minutes',
    'membership_changed','point_count_changed']


def _concat_events(frames):
    """Empty trajectories carry schema but must not participate in dtype inference."""
    nonempty = [frame for frame in frames if not frame.empty]
    if nonempty:
        return pd.concat(nonempty, ignore_index=True)
    if not frames:
        raise ValueError('A processed user must contain at least one trajectory')
    return frames[0].iloc[:0].copy()


def clean_variant(raw, config, policy):
    """Same validity rules as core; physical row IDs survive all variants.

    duplicate_altitude adds parsed altitude to the duplicate key. Conflicting
    altitudes at identical coordinates are averaged, with all contributors kept.
    """
    if policy not in POLICIES:
        raise ValueError(policy)
    df = _normalize(raw)
    if 'record_id' not in df:
        df['record_id'] = np.arange(len(df), dtype=np.int64)
    if not df.record_id.is_unique:
        raise ValueError('Nonunique raw row IDs')
    bad_xy, bad_t, duplicate = _basic_masks(df)
    valid = ~(bad_xy | bad_t)
    if policy == 'duplicate_altitude':
        duplicate.loc[valid] = df.loc[valid].duplicated(POINT_KEYS + ['altitude_m'], keep='first')
    audit = dict.fromkeys(AUDIT_COUNTS, 0)
    audit.update(input_points=len(df), invalid_coordinates=int(bad_xy.sum()),
        invalid_timestamps=int(bad_t.sum()), invalid_rows_removed=int((bad_xy | bad_t).sum()),
        invalid_altitudes=int((~np.isfinite(df.altitude_m)).sum()),
        duplicate_records_removed=int(duplicate.sum()))
    removed = df.loc[bad_xy | bad_t | duplicate].copy()
    removed['reason'] = np.where((bad_xy | bad_t).loc[removed.index], 'invalid', 'duplicate')
    distinct = df.loc[valid & ~duplicate].copy()
    duplicate_time = distinct.duplicated(TIME_KEYS, keep=False)
    ordinary = distinct.loc[~duplicate_time].copy()
    ordinary['source_point_count'] = 1
    pieces, traces, unresolved = [ordinary], [], []
    threshold = {'vote10': 10., 'vote50': 50.}.get(policy, 20.)
    cfg = replace(config, conflict_merge_threshold_m=threshold)
    for timestamp, group in distinct.loc[duplicate_time].groupby('timestamp', sort=True):
        spread = _diameter(group)
        audit['conflict_groups'] += 1
        audit['conflict_positions'] += len(group)
        if policy == 'no_merge':
            selected, method = None, 'quarantined_no_merge'
        elif policy == 'mean20':
            selected, method = (group, 'mean_within20') if spread <= 20 else (None, 'quarantined_far')
        elif spread <= threshold:
            selected, method = group, 'spatial_vote'
        else:
            selected, method = _choose_conflict(group, distinct, cfg)
        trace = group.copy()
        trace['spread_m'] = spread
        trace['output_record_id'] = pd.NA
        trace['accepted_contributor'] = False
        if selected is None:
            trace['decision'] = method
            unresolved.append(timestamp.value)
            audit['unresolved_conflict_groups'] += 1
            audit['unresolved_conflict_rows'] += len(group)
        else:
            n = len(selected)
            out = selected.loc[[selected.record_id.idxmin()]].copy()
            out['latitude'], out['longitude'] = _mean_coordinate(selected)
            out['altitude_m'] = selected.altitude_m.where(np.isfinite(selected.altitude_m)).mean()
            out['source_point_count'] = n
            pieces.append(out)
            accepted = trace.record_id.isin(selected.record_id)
            trace['decision'] = 'rejected_by_vote'
            trace.loc[accepted, 'decision'] = method
            trace.loc[accepted, 'accepted_contributor'] = True
            trace.loc[accepted, 'output_record_id'] = int(out.record_id.iloc[0])
            audit['resolved_conflict_groups'] += 1
            audit['context_resolved_groups'] += int(method == 'context_vote')
            audit['merged_conflict_groups'] += int(n > 1)
            audit['merged_source_points'] += n if n > 1 else 0
            audit['merged_extra_points'] += n - 1
            audit['outlier_conflict_rows'] += len(group) - n
            audit['unresolved_conflict_rows'] += len(group) - n
        traces.append(trace)
    clean = _motion_columns(pd.concat(pieces, ignore_index=True), config)
    clean.loc[~np.isfinite(clean.altitude_m), 'altitude_m'] = np.nan
    breaks = np.zeros(len(clean), dtype=bool)
    if len(clean) and unresolved:
        counts = np.searchsorted(np.sort(unresolved), clean.timestamp.astype('int64').to_numpy())
        breaks = np.diff(counts, prepend=counts[0]) > 0
    clean['segment_break_due_to_conflict'] = breaks
    clean['observation_segment'] = (clean.gap_seconds.isna() | clean.gap_over_limit
        | clean.gap_seconds.le(0) | breaks).cumsum().astype(int)
    audit.update(output_points=len(clean), missing_altitude_after=int(clean.altitude_m.isna().sum()),
        gaps_over_limit=int(clean.gap_over_limit.sum()), high_speed_segments=int(clean.high_speed_flag.sum()),
        breaks_due_to_conflict=int(breaks.sum()))
    trace = pd.concat(traces, ignore_index=True) if traces else pd.DataFrame()
    assert len(raw) == len(clean) + len(removed) + audit['merged_extra_points'] + audit['unresolved_conflict_rows']
    assert len(raw) == int(clean.source_point_count.sum()) + len(removed) + audit['unresolved_conflict_rows']
    assert not clean.duplicated(TIME_KEYS).any()
    return PreprocessingResult(clean, removed, trace, audit)


def event_provenance(run, config):
    events, _ = detect_stays(run.points, config)
    contributors = {}
    if len(run.conflict_points):
        accepted = run.conflict_points.loc[run.conflict_points.accepted_contributor]
        contributors = {int(k): sorted(g.record_id.astype(int).tolist())
            for k, g in accepted.groupby('output_record_id')}
    hashes = []
    for event in events.itertuples():
        mask = (run.points.timestamp.ge(event.start_time) & run.points.timestamp.le(event.end_time)
                & run.points.observation_segment.eq(event.observation_segment))
        ids = sorted(i for key in run.points.loc[mask, 'record_id']
                     for i in contributors.get(int(key), [int(key)]))
        h = hashlib.sha256()
        for rid in ids:
            h.update(f'{event.user_id}/{event.trajectory_id}/{rid}\n'.encode())
        hashes.append(h.hexdigest())
    events['membership_sha256'] = hashes
    return events


def stay_diff(baseline, variant):
    """Connected overlap graph, no spatial gate and no forced 1-to-1 assignment.

    Edges require same source trajectory and strictly positive temporal overlap.
    Membership SHA is compared for the 1-to-1 components. Endpoints merely
    touching do not form an edge. All event keys remain source/time based.
    """
    left, right = list(baseline.itertuples()), list(variant.itertuples())
    adjacency = {('b', i): set() for i in range(len(left))}
    adjacency.update({('v', j): set() for j in range(len(right))})
    for i, x in enumerate(left):
        for j, y in enumerate(right):
            if (x.trajectory_id == y.trajectory_id and x.start_time < y.end_time
                    and y.start_time < x.end_time):
                adjacency['b', i].add(('v', j)); adjacency['v', j].add(('b', i))
    seen, rows = set(), []
    def key(e):
        return f'{e.user_id}/{e.trajectory_id}@{e.start_time.isoformat()}/{e.end_time.isoformat()}'
    for node in adjacency:
        if node in seen:
            continue
        stack, component = [node], set()
        while stack:
            v = stack.pop()
            if v in component:
                continue
            component.add(v); stack.extend(adjacency[v] - component)
        seen.update(component)
        bs = [left[i] for kind, i in sorted(component) if kind == 'b']
        vs = [right[i] for kind, i in sorted(component) if kind == 'v']
        kind = ('new' if not bs else 'lost' if not vs else 'split' if len(bs)==1 and len(vs)>1
                else 'merge' if len(bs)>1 and len(vs)==1 else 'complex' if len(bs)>1 else 'changed')
        row = dict(kind=kind, baseline_events=len(bs), variant_events=len(vs),
            baseline_keys=json.dumps([key(e) for e in bs]), variant_keys=json.dumps([key(e) for e in vs]))
        if len(bs)==len(vs)==1:
            x, y = bs[0], vs[0]
            delta = float(haversine_m(x.latitude, x.longitude, y.latitude, y.longitude))
            row.update(start_delta_seconds=(y.start_time-x.start_time).total_seconds(),
                end_delta_seconds=(y.end_time-x.end_time).total_seconds(), center_delta_m=delta,
                dwell_delta_minutes=y.duration_minutes-x.duration_minutes,
                membership_changed=x.membership_sha256 != y.membership_sha256,
                point_count_changed=x.point_count != y.point_count)
            if (row['start_delta_seconds']==0 and row['end_delta_seconds']==0 and delta<=1e-6
                    and abs(row['dwell_delta_minutes'])<=1e-9 and not row['membership_changed']
                    and not row['point_count_changed']):
                row['kind'] = 'unchanged'
        rows.append(row)
    return pd.DataFrame(rows, columns=DIFF_COLUMNS)


def run(root, output, used_seconds):
    root, output = Path(root), Path(output)
    if output.exists():
        raise FileExistsError(f'{output}: đọc audit, không ghi đè')
    # Import resource callbacks without changing the frozen B2 implementation.
    from .benchmark_synthetic import memory_usage, available_memory
    budget = Budget(used_seconds, memory_usage, available_memory)
    source = GeoLifeSource(root/'data/Geolife Trajectories 1.3')
    config = load_config(root/'configs/baseline.toml')
    prep = json.loads((root/'artifacts/preprocessing/audit.json').read_text(encoding='utf-8'))
    expected = sorted(str(u) for u in prep['expected_users'])
    if sorted(source.by_user) != expected or len(source.names) != prep['expected_trajectory_files']:
        raise ValueError('Raw source inventory không khớp baseline')
    baseline = pd.read_csv(root/'artifacts/stays/stays.csv', dtype={'user_id':str,'trajectory_id':str})
    for name in ['start_time','end_time']:
        baseline[name] = pd.to_datetime(baseline[name], utc=True)
    output.mkdir(parents=True)
    protocol_path=root/'reports/cp1/cleaning_protocol.md'
    (output/'cleaning_protocol.md').write_bytes(protocol_path.read_bytes())
    audit = dict(status='running', revision=REVISION, policies=list(POLICIES), completed_users=[],
        processed_trajectories=0, raw_points=0, source_manifest=[], config=config.to_dict(),
        implementation_sha256=file_hash(Path(__file__)), baseline_parity_users=[],
        protocol_sha256=file_hash(output/'cleaning_protocol.md'),
        provenance='record_id is the zero-based physical data row in each PLT; file hash in manifest',
        graph='same user/trajectory, positive time overlap; no spatial gate; connected components',
        tolerances=dict(center_m=1e-6,dwell_minutes=1e-9,endpoint_seconds=0),
        baseline_files={name:file_hash(root/name) for name in
            ['artifacts/preprocessing/audit.json','artifacts/stays/stays.csv','configs/baseline.toml']})
    audit['core_hashes']={p.name:file_hash(p) for p in (root/'src/geolife_inference').glob('*.py')}
    write_json(output/'audit.json', audit)
    try:
        for policy in POLICIES:
            (output/policy).mkdir()
        summaries = []
        for user in expected:
            budget.check()
            counts_rows = []
            collected = {k:[] for k in POLICIES}
            for relative in source.by_user[user]:
                budget.check()
                path = source.path/relative
                before = path.stat()
                data = path.read_bytes()
                frame = parse_plt(io.StringIO(data.decode('utf-8-sig')), user, path.stem)
                # GeoLife raw order is monotone (B1); explicitly reject reordered IDs.
                if len(frame):
                    original_times = pd.read_csv(io.BytesIO(data), skiprows=6, header=None, usecols=[5,6],dtype=str)
                    raw_times = pd.to_datetime(original_times[5]+' '+original_times[6],
                        format='%Y-%m-%d %H:%M:%S',utc=True,errors='coerce')
                    order = pd.Series(np.arange(len(frame)), index=raw_times).sort_index(kind='stable',na_position='last').to_numpy()
                else:
                    order = np.empty(0,dtype=int)
                frame['record_id'] = order
                budget.check()
                audit['source_manifest'].append(dict(path=relative, bytes=before.st_size,
                    mtime_ns=before.st_mtime_ns, sha256=hashlib.sha256(data).hexdigest()))
                if path.stat().st_mtime_ns != before.st_mtime_ns:
                    raise ValueError('Raw input changed')
                base = clean_variant(frame, config, 'vote20')
                budget.check()
                base_events = event_provenance(base, config)
                invalid_xy,invalid_t,dup = _basic_masks(_normalize(frame))
                distinct = frame.loc[~(invalid_xy|invalid_t|dup)]
                has_conflict = distinct.duplicated(TIME_KEYS).any()
                all_key_dup = frame.loc[~(invalid_xy|invalid_t)].duplicated(POINT_KEYS+['altitude_m']).sum()
                contrast_changed = int(dup.sum()) != int(all_key_dup)
                for policy in POLICIES:
                    reuse = policy=='vote20' or (not contrast_changed if policy=='duplicate_altitude' else not has_conflict)
                    result = base if reuse else clean_variant(frame, config, policy)
                    budget.check()
                    events = base_events if reuse else event_provenance(result, config)
                    collected[policy].append(events)
                    counts_rows.append(dict(user_id=user,trajectory_id=path.stem,policy=policy,
                        reused_vote20=reuse,**result.audit))
                    if not reuse and len(result.conflict_points):
                        trace = result.conflict_points.copy();trace['policy']=policy
                        dest=output/policy/'conflict_provenance.csv.gz'
                        trace.to_csv(dest,index=False,mode='a',header=not dest.exists(),compression='gzip')
                    if policy=='vote20' and len(base.conflict_points):
                        dest=output/policy/'conflict_provenance.csv.gz'
                        base.conflict_points.to_csv(dest,index=False,mode='a',header=not dest.exists(),compression='gzip')
                    if len(result.removed_points) and (policy=='vote20' or not reuse):
                        dest=output/policy/'removed.csv.gz'
                        result.removed_points.to_csv(dest,index=False,mode='a',header=not dest.exists(),compression='gzip')
                audit['raw_points']+=len(frame);audit['processed_trajectories']+=1
            ready = {}
            for policy in POLICIES:
                events = _concat_events(collected[policy])
                ready[policy], rejected = split_overlapping_stays(events)
                ready[policy].to_csv(output/policy/f'{user}_stays.csv',index=False)
                if len(rejected):rejected.to_csv(output/policy/f'{user}_overlap_excluded.csv',index=False)
            own = baseline.loc[baseline.user_id.eq(user)].sort_values(['trajectory_id','start_time']).reset_index(drop=True)
            calculated = ready['vote20'].sort_values(['trajectory_id','start_time']).reset_index(drop=True)
            if len(own)!=len(calculated):raise ValueError(f'{user}: baseline stay count parity failed')
            for col in ['trajectory_id','start_time','end_time','point_count']:
                if own[col].tolist()!=calculated[col].tolist():raise ValueError(f'{user}: baseline {col} parity failed')
            for col in ['latitude','longitude','duration_minutes']:
                if not np.allclose(own[col].to_numpy(float),calculated[col].to_numpy(float),rtol=0,atol=1e-9):
                    raise ValueError(f'{user}: baseline {col} parity failed')
            baseline_counts = pd.DataFrame([r for r in counts_rows if r['user_id']==user and r['policy']=='vote20'])[AUDIT_COUNTS].sum()
            ref = next(x for x in prep['per_user'] if str(x['user_id'])==user)
            for name in AUDIT_COUNTS:
                if name in ref and int(baseline_counts[name])!=int(ref[name]):
                    raise ValueError(f'{user}: preprocessing parity failed: {name}')
            audit['baseline_parity_users'].append(user)
            for policy in POLICIES:
                diff = stay_diff(ready['vote20'],ready[policy]);diff['user_id']=user;diff['policy']=policy
                dest=output/'stay_diff.csv'
                diff.to_csv(dest,index=False,mode='a',header=not dest.exists())
                kinds=diff.kind.value_counts().to_dict() if len(diff) else {}
                summaries.append(dict(user_id=user,policy=policy,baseline_stays=len(ready['vote20']),
                    variant_stays=len(ready[policy]),baseline_dwell_minutes=float(ready['vote20'].duration_minutes.sum()),
                    variant_dwell_minutes=float(ready[policy].duration_minutes.sum()),
                    **{k:int(kinds.get(k,0)) for k in ['unchanged','changed','lost','new','split','merge','complex']}))
            audit['completed_users'].append(user);audit.update(budget.summary())
            dest=output/'counts_per_trajectory.csv'
            pd.DataFrame(counts_rows).to_csv(dest,index=False,mode='a',header=not dest.exists())
            pd.DataFrame(summaries).to_csv(output/'stay_diff_per_user.csv',index=False)
            write_json(output/'audit.json',audit)
            print(user,'done; vote20 stays=',len(ready['vote20']),flush=True)
        if audit['raw_points']!=prep['totals']['input_points'] or audit['processed_trajectories']!=prep['expected_trajectory_files']:
            raise ValueError('Incomplete dataset')
        counts=pd.read_csv(output/'counts_per_trajectory.csv',dtype={'user_id':str,'trajectory_id':str})
        counts.groupby(['policy','user_id'])[AUDIT_COUNTS].sum().to_csv(output/'counts_per_user.csv')
        counts.groupby('policy')[AUDIT_COUNTS].sum().to_csv(output/'counts_totals.csv')
        audit['output_sha256']={str(p.relative_to(output)):file_hash(p) for p in output.rglob('*')
            if p.is_file() and p.name!='audit.json'}
        for entry in audit['source_manifest']:
            stat=(source.path/entry['path']).stat()
            if (stat.st_size,stat.st_mtime_ns)!=(entry['bytes'],entry['mtime_ns']):
                raise ValueError('Raw source changed during run')
        for name,h in audit['baseline_files'].items():
            if file_hash(root/name)!=h:raise ValueError('Baseline changed during run')
        for name,h in audit['core_hashes'].items():
            if file_hash(root/'src/geolife_inference'/name)!=h:raise ValueError('Code changed during run')
        audit.update(status='completed',decision='keep_vote20; differences are not accuracy evidence',**budget.summary())
        budget.check();write_json(output/'audit.json',audit)
        return audit
    except BaseException as error:
        audit.update(status='failed',error=f'{type(error).__name__}: {error}',**budget.summary())
        write_json(output/'audit.json',audit)
        raise
