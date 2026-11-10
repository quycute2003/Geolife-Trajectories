"""B4 registration, resumable user checkpoints, synthetic and real workloads."""
from __future__ import annotations

import csv
import gzip
import itertools
import json
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from .benchmark_synthetic import (digest,file_hash,write_json,iter_trajectories,memory_usage,available_memory)
from .benchmark_detectors import DetectorConfig,configurations,detect,BASELINE_ID,METHODS,RADII,DURATIONS
from .benchmark_evaluation import (empty_accumulator,accumulate,finalize,load_label_masks,motor_exposure,
    match_events,summarize_users)

REVISION='b4-jobs-v1'
MODULES=['benchmark_detectors.py','benchmark_evaluation.py','benchmark_jobs.py',
         'benchmark_decisions.py','benchmark_plots.py','geo.py','benchmark_synthetic.py']


def readj(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def ledger(root,out):
    values=[readj(root/'artifacts/benchmark/b3/cleaning_v1/audit.json')['compute_used_after_seconds']]
    if (Path(out)/'lock.json').exists():values.append(readj(Path(out)/'lock.json').get('compute_used_after_seconds',0))
    for path in Path(out).glob('*/audit.json'):
        a=readj(path)
        if 'compute_used_after_seconds' in a:values.append(a['compute_used_after_seconds'])
    final=root/'artifacts/benchmark/b2/final_v1/generation_audit.json'
    if final.exists() and 'compute_used_after_seconds' in readj(final):values.append(readj(final)['compute_used_after_seconds'])
    return max(values)


def register(root,out):
    root,out=Path(root),Path(out)
    if (out/'lock.json').exists():
        return validate_lock(root,out)
    if out.exists():raise FileExistsError('B4 namespace exists without lock; inspect before using a new version')
    start=time.perf_counter()
    prep=root/'artifacts/benchmark/b2/prepared_v1';corpus=root/'artifacts/benchmark/b2/selection_v1'
    p=readj(prep/'protocol.json');a=readj(corpus/'generation_audit.json')
    b3=readj(root/'artifacts/benchmark/b3/cleaning_v1/audit.json')
    if a['status']!='completed' or b3['status']!='completed':raise ValueError('B2/B3 not completed')
    if p['protocol_hash']!=a['protocol_hash']:raise ValueError('B2 protocol mismatch')
    if digest({k:v for k,v in p.items() if k!='protocol_hash'})!=p['protocol_hash']:raise ValueError('B2 protocol mutated')
    if (root/'artifacts/benchmark/b2/final_v1').exists():
        raise ValueError('Final corpus already exists before B4 registration; inspect exposure first')
    out.mkdir(parents=True)
    text=(root/'PLAN.md').read_text(encoding='utf-8')
    block='## Bổ sung CP1'+text.split('## Bổ sung CP1',1)[1].split('## Lộ trình 6 tuần',1)[0]
    (out/'plan_cp1.md').write_text(block,encoding='utf-8')
    doc=root/'reports/cp1/detector_protocol.md'
    (out/'detector_protocol.md').write_bytes(doc.read_bytes())
    lock=dict(revision=REVISION,b2_protocol_hash=p['protocol_hash'],mode=p['mode'],
        main_configs=[c.record() for c in configurations(False)],
        all_configs=[c.record() for c in configurations(True)],
        code_hashes={n:file_hash(root/'src/geolife_inference'/n) for n in MODULES},
        snapshot_hashes={n:file_hash(out/n) for n in ['plan_cp1.md','detector_protocol.md']},
        source_hashes={n:file_hash(root/n) for n in ['artifacts/benchmark/b2/prepared_v1/protocol.json',
            'artifacts/benchmark/b2/selection_v1/generation_audit.json',
            'artifacts/benchmark/b2/selection_v1/matrix.json',
            'artifacts/benchmark/b3/cleaning_v1/audit.json','artifacts/stays/stays.csv',
            'artifacts/preprocessing/audit.json','artifacts/benchmark/b1/profiles_v1/profiles_per_user.csv']},
        label_hashes={str(p.relative_to(root)):file_hash(p) for p in
            sorted((root/'data/Geolife Trajectories 1.3/Data').glob('*/labels.txt'))},
        matching=dict(iou_min=.5,center_m=100,assignment='max total IoU; lexical numerical ties 1e-12'),
        plotting_bootstrap=dict(repetitions=1000,coverage=.95,seed=20261105),
        gate_bootstrap=dict(repetitions=5000,coverage=.975,seed=20261105),
        note='B4 addendum before detector results; frozen B2 generator/corpus unchanged')
    lock['compute_used_after_seconds']=ledger(root,out)+time.perf_counter()-start
    lock['lock_hash']=digest(lock)
    write_json(out/'lock.json',lock)
    return lock


def validate_lock(root,out):
    root,out=Path(root),Path(out);p=readj(out/'lock.json')
    if digest({k:v for k,v in p.items() if k!='lock_hash'})!=p['lock_hash']:raise ValueError('B4 lock mutated')
    for n,h in p['code_hashes'].items():
        if file_hash(root/'src/geolife_inference'/n)!=h:raise ValueError(f'B4 code changed: {n}; new namespace required')
    for n,h in p['snapshot_hashes'].items():
        if file_hash(out/n)!=h:raise ValueError(f'Frozen B4 document changed: {n}')
    for n,h in {**p['source_hashes'],**p['label_hashes']}.items():
        if file_hash(root/n)!=h:raise ValueError(f'B4 dependency changed: {n}')
    return p


class JobBudget:
    def __init__(self,used,previous=None,historical=None):
        if not 0<=used<86400:raise ValueError('No compute left in the cumulative 24-hour budget')
        self.start=time.perf_counter();self.used=used;self.limit=86400-used
        self.cap=min(8*1024**3,available_memory()//2);self.peak=0
        self.config_seconds=dict(previous or {});self.config_peak={};self.current=None;self.mark=None
        self.historical=dict(historical or {})

    def check(self):
        ws,_=memory_usage();self.peak=max(self.peak,ws)
        if self.current:self.config_peak[self.current]=max(self.config_peak.get(self.current,0),ws)
        if ws>self.cap:raise MemoryError(f'Working set {ws} > soft budget {self.cap}')
        if time.perf_counter()-self.start>self.limit:raise TimeoutError('B4 cumulative compute budget exhausted')
        if self.current and self.historical.get(self.current,0)+self.config_seconds.get(self.current,0)+time.perf_counter()-self.mark>43200:
            raise TimeoutError(f'{self.current}: detector compute exceeded 12 hours')

    @contextmanager
    def detector(self,cid):
        self.current=cid;self.mark=time.perf_counter()
        try:
            self.check();yield
        finally:
            self.config_seconds[cid]=self.config_seconds.get(cid,0)+time.perf_counter()-self.mark
            self.current=None;self.mark=None

    def summary(self):
        elapsed=time.perf_counter()-self.start
        return dict(attempt_elapsed_seconds=elapsed,compute_used_after_seconds=self.used+elapsed,
            sampled_peak_working_set_bytes=self.peak,ram_cap_bytes=self.cap,
            config_compute_seconds=self.config_seconds,config_process_ws_peak=self.config_peak)


def _start(root,out,phase,resume):
    lock=validate_lock(root,out);directory=out/phase
    if directory.exists():
        if not resume:raise FileExistsError(f'{directory}: set RESUME=True only for an incomplete job')
        audit=readj(directory/'audit.json')
        if audit['status']=='completed':raise FileExistsError('Completed job must be reused, never rerun silently')
        if audit['lock_hash']!=lock['lock_hash']:raise ValueError('Resume lock mismatch')
        for name,h in audit['output_hashes'].items():
            if file_hash(directory/name)!=h:raise ValueError(f'Checkpoint changed: {name}')
    else:
        directory.mkdir();audit=dict(status='prepared',phase=phase,lock_hash=lock['lock_hash'],
            completed_users=[],output_hashes={},attempts=[],config_compute_seconds={})
    historical={}
    for path in out.glob('*/audit.json'):
        if path.parent==directory:continue
        for cid,seconds in readj(path).get('config_compute_seconds',{}).items():
            historical[cid]=historical.get(cid,0)+seconds
    budget=JobBudget(ledger(root,out),audit['config_compute_seconds'],historical)
    budget.config_peak=dict(audit.get('config_process_ws_peak',{}))
    audit['status']='running';audit['attempts'].append(dict(status='running',used_before_seconds=budget.used))
    write_json(directory/'audit.json',audit)
    return lock,directory,audit,budget


def _checkpoint(directory,audit,budget,user,files):
    budget.check()
    for path in files:audit['output_hashes'][str(path.relative_to(directory))]=file_hash(path)
    audit['completed_users'].append(user);audit.update(budget.summary())
    write_json(directory/'audit.json',audit)
    print(f'{audit["phase"]}: {len(audit["completed_users"])} users completed ({user})',flush=True)


def _finish(directory,audit,budget,error=None):
    stats=budget.summary();status='failed' if error else 'completed'
    audit.update(status=status,**stats)
    audit['attempts'][-1].update(status=status,**stats)
    if error:audit['error']=f'{type(error).__name__}: {error}'
    else:audit.pop('error',None)
    write_json(directory/'audit.json',audit)


def _iter_cases(path,chunksize=100000):
    carry=None
    for frame in pd.read_csv(path,chunksize=chunksize,dtype={'case_id':str,'source_user_id':str}):
        if carry is not None:frame=pd.concat([carry,frame],ignore_index=True)
        cuts=np.flatnonzero(frame.case_id.ne(frame.case_id.shift()).to_numpy())
        for a,b in zip(cuts[:-1],cuts[1:]):yield frame.case_id.iloc[a],frame.iloc[a:b]
        carry=frame.iloc[cuts[-1]:].copy()
    if carry is not None and len(carry):yield carry.case_id.iloc[0],carry


def _truth_records(path):
    result={}
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream:
            record=json.loads(line)
            # Latent knots and source provenance stay outside detector execution.
            item={k:v for k,v in record.items() if k not in ['latent_knots_epoch','latent_knots_xy_m','origin','source_id']}
            if item['case_id'] in result:raise ValueError('Duplicate case ID')
            result[item['case_id']]=item
    return result


def _cfgs(lock,final=False,out=None):
    records=lock['all_configs']
    if final:
        winner=validate_winner(out,lock)
        if winner['lock_hash']!=lock['lock_hash'] or winner['status']!='selected':raise ValueError('No locked winner')
        records=[r for r in lock['main_configs'] if r['config_id'] in [BASELINE_ID,winner['config_id']]]
    return [DetectorConfig(**{k:v for k,v in r.items() if k!='config_id'}) for r in records]


def validate_winner(out,lock):
    directory=Path(out)/'decision_selection';audit=readj(directory/'audit.json')
    if audit['status']!='completed':raise ValueError('Selection decision not completed')
    if audit['winner_sha256']!=file_hash(directory/'winner.json'):raise ValueError('Locked winner changed')
    winner=readj(directory/'winner.json')
    if winner['lock_hash']!=lock['lock_hash'] or winner['status']!='selected':raise ValueError('No locked selection winner')
    if winner['gates_sha256']!=file_hash(directory/'gates.csv'):raise ValueError('Selection gates changed')
    return winner


def run_synthetic(root,out,split='selection',resume=False):
    root,out=Path(root),Path(out)
    if split not in ['selection','final']:raise ValueError(split)
    lock,directory,audit,budget=_start(root,out,'synthetic_'+split,resume)
    try:
        configs=_cfgs(lock,split=='final',out)
        prepared=readj(root/'artifacts/benchmark/b2/prepared_v1/protocol.json')
        if split=='final' and prepared['mode']=='descriptive':raise ValueError('Final forbidden by cohort mode')
        corpus=root/f'artifacts/benchmark/b2/{split}_v1'
        ca=readj(corpus/'generation_audit.json')
        if ca['status']!='completed' or ca['protocol_hash']!=lock['b2_protocol_hash']:raise ValueError('Invalid synthetic corpus')
        matrix=readj(corpus/'matrix.json');metadata={c['cell_id']:c for c in matrix}
        expected=sorted(u for u,s in prepared['split'].items() if s==split)
        if matrix!=readj(root/'artifacts/benchmark/b2/selection_v1/matrix.json'):
            raise ValueError('Synthetic scenario matrix changed between splits')
        if len(metadata)!=len(matrix) or ca['cases']!=len(expected)*len(matrix)*5:
            raise ValueError('Synthetic matrix/case quota mismatch')
        profiles=pd.read_csv(root/'artifacts/benchmark/b1/profiles_v1/profiles_per_user.csv',dtype={'user_id':str}).set_index('user_id')
        for user in expected:
            if user in audit['completed_users']:continue
            budget.check()
            for sub,suffix in [('observations','csv.gz'),('truth','jsonl.gz')]:
                path=corpus/sub/f'{user}.{suffix}'
                key=str(path.relative_to(corpus))
                if file_hash(path)!=ca['output_sha256'][key]:raise ValueError(f'Corpus hash mismatch: {key}')
            truths=_truth_records(corpus/'truth'/f'{user}.jsonl.gz')
            if len(truths)!=len(matrix)*5 or any(v['source_user_id']!=user for v in truths.values()):
                raise ValueError('Truth user/case quota mismatch')
            for v in truths.values():
                if any(v.get(k)!=value for k,value in metadata[v['cell_id']].items()):
                    raise ValueError('Truth cell metadata differs from matrix')
            states={(c.config_id,k):empty_accumulator() for c in configs for k in metadata}
            timing={c.config_id:0. for c in configs};seen=set()
            pred_path=directory/f'{user}_predictions.csv.gz'
            with gzip.open(pred_path,'wt',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=['case_id','config_id','event_id','start','end','latitude','longitude','point_count'])
                writer.writeheader()
                def evaluate(cid,frame):
                    record=truths[cid]
                    t=(pd.to_datetime(frame.timestamp,utc=True).astype('int64').to_numpy()/1e9
                       if len(frame) else np.empty(0))
                    xy=frame[['latitude','longitude']].to_numpy(float) if len(frame) else np.empty((0,2))
                    seg=frame.observation_segment.to_numpy() if len(frame) else np.empty(0,int)
                    if len(frame)!=record['diagnostics']['observed_fixes']:raise ValueError('Case observation count mismatch')
                    # Counterbalance invocation order deterministically, never by score.
                    shift=int(digest(cid)[:8],16)%len(configs)
                    for c in configs[shift:]+configs[:shift]:
                        start=time.perf_counter()
                        with budget.detector(c.config_id):pred=detect(t,xy,seg,c,budget.check)
                        timing[c.config_id]+=time.perf_counter()-start
                        accumulate(states[c.config_id,record['cell_id']],record,pred,t)
                        writer.writerows(dict(case_id=cid,config_id=c.config_id,event_id=i,**e) for i,e in enumerate(pred))
                for cid,frame in _iter_cases(corpus/'observations'/f'{user}.csv.gz'):
                    if cid not in truths or cid in seen:raise ValueError('Unknown or noncontiguous case')
                    evaluate(cid,frame);seen.add(cid)
                for cid in sorted(set(truths)-seen):
                    if truths[cid]['diagnostics']['observed_fixes']!=0:raise ValueError('Missing nonempty case')
                    evaluate(cid,pd.DataFrame());seen.add(cid)
            rows=[]
            for c in configs:
                for cell in matrix:
                    state=states[c.config_id,cell['cell_id']]
                    if state['cases']!=5:raise ValueError('Not five seeds per user/cell/config')
                    rows.append(dict(user_id=user,independence_group=prepared['independence_groups'][user],
                        cadence_median_seconds=float(profiles.loc[user,'dt_observed_seconds_p50']),
                        **c.record(),**cell,**finalize(state)))
            metric_path=directory/f'{user}_metrics.csv.gz';pd.DataFrame(rows).to_csv(metric_path,index=False)
            timing_path=directory/f'{user}_timing.csv';pd.DataFrame([dict(user_id=user,config_id=k,detector_seconds=v,
                cases=len(truths),observations=sum(x['diagnostics']['observed_fixes'] for x in truths.values()))
                for k,v in timing.items()]).to_csv(timing_path,index=False)
            _checkpoint(directory,audit,budget,user,[metric_path,timing_path,pred_path])
        if audit['completed_users']!=expected:raise ValueError('Incomplete source users')
        timing_all=pd.concat([pd.read_csv(directory/f'{u}_timing.csv') for u in expected],ignore_index=True)
        for cid,g in timing_all.groupby('config_id'):
            if g.cases.sum()!=ca['cases'] or g.observations.sum()!=ca['points']:
                raise ValueError(f'{cid}: synthetic global case/point quota mismatch')
        audit.update(configs=len(configs),users=len(expected),cells=len(matrix),cases_per_config=ca['cases'],
            observations_per_config=ca['points'],timing_scope='detector only, shared observations, rotated call order')
        budget.check();_finish(directory,audit,budget)
        return audit
    except BaseException as error:
        _finish(directory,audit,budget,error);raise


def _event_list(frame):
    return frame[['start','end','latitude','longitude','point_count']].to_dict('records')


def _stability(left,right):
    count=0;ious=[];splits=merges=0
    for key in sorted(set(left)|set(right)):
        matches,sp,me=match_events(left.get(key,[]),right.get(key,[]));splits+=sp;merges+=me
        count+=len(matches);ious.extend(x[2] for x in matches)
    nl=sum(map(len,left.values()));nr=sum(map(len,right.values()))
    dl=sum(e['end']-e['start'] for g in left.values() for e in g)
    dr=sum(e['end']-e['start'] for g in right.values() for e in g)
    return dict(n_left=nl,n_right=nr,split_events=splits,merge_events=merges,jaccard=count/(nl+nr-count) if nl+nr-count else np.nan,
        matched_temporal_iou=float(np.median(ious)) if ious else np.nan,
        count_relative_change=abs(nr-nl)/nl if nl else np.nan,
        dwell_relative_change=abs(dr-dl)/dl if dl else np.nan)


def run_real(root,out,resume=False):
    root,out=Path(root),Path(out)
    lock,directory,audit,budget=_start(root,out,'real',resume)
    try:
        cfgs=[DetectorConfig(**{k:v for k,v in r.items() if k!='config_id'}) for r in lock['main_configs']]
        prep=readj(root/'artifacts/preprocessing/audit.json');expected=sorted(prep['expected_users'])
        profile=readj(root/'artifacts/benchmark/b1/profiles_v1/profile_audit.json')
        clean=root/'artifacts/preprocessing/cleaned_points.csv.gz';stat=clean.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(profile['cleaned_bytes'],profile['cleaned_mtime_ns']):raise ValueError('Cleaned input changed')
        baseline=pd.read_csv(root/'artifacts/stays/stays.csv',dtype={'user_id':str,'trajectory_id':str})
        for name in ['start_time','end_time']:baseline[name]=pd.to_datetime(baseline[name],utc=True).astype('int64')/1e9
        masks=load_label_masks(root);seen_points=seen_trajs=0;seen_users=[]
        for user,group in itertools.groupby(iter_trajectories(clean),key=lambda x:str(x.user_id.iloc[0])):
            if user in seen_users:raise ValueError('Noncontiguous user')
            seen_users.append(user)
            if user in audit['completed_users']:
                for f in group:seen_points+=len(f);seen_trajs+=1
                continue
            events={c.config_id:{} for c in cfgs};timing={c.config_id:0. for c in cfgs}
            user_points=user_trajs=0
            for frame in group:
                budget.check();seen_points+=len(frame);seen_trajs+=1;user_points+=len(frame);user_trajs+=1
                key=str(frame.trajectory_id.iloc[0]);t=pd.to_datetime(frame.timestamp,utc=True).astype('int64').to_numpy()/1e9
                xy=frame[['latitude','longitude']].to_numpy(float);seg=frame.observation_segment.to_numpy()
                shift=int(digest([user,key])[:8],16)%len(cfgs)
                for c in cfgs[shift:]+cfgs[:shift]:
                    start=time.perf_counter()
                    with budget.detector(c.config_id):pred=detect(t,xy,seg,c,budget.check)
                    timing[c.config_id]+=time.perf_counter()-start
                    events[c.config_id][key]=pred
            rows=[];flat=[]
            own_counts=next((v for v in prep.get('per_user',[]) if str(v['user_id'])==user),None)
            if own_counts and (user_points!=own_counts['output_points'] or user_trajs!=own_counts['trajectory_files']):
                raise ValueError(f'{user}: real point/trajectory quota mismatch')
            for c in cfgs:
                e=[dict(trajectory_id=k,**v) for k,values in events[c.config_id].items() for v in values]
                dwell=sum(v['end']-v['start'] for v in e)
                rows.append(dict(user_id=user,**c.record(),stays=len(e),stay_dwell_minutes=dwell/60,
                    detector_seconds=timing[c.config_id],processed_points=user_points,processed_trajectories=user_trajs,
                    **motor_exposure(e,masks.get(user,[]))))
                flat.extend(dict(config_id=c.config_id,**v) for v in e)
            own=baseline.loc[baseline.user_id.eq(user)].sort_values(['trajectory_id','start_time','end_time'])
            actual=sorted([dict(trajectory_id=k,**e) for k,v in events[BASELINE_ID].items() for e in v],
                          key=lambda e:(e['trajectory_id'],e['start'],e['end']))
            if len(own)!=len(actual):raise ValueError(f'{user}: fixed-anchor baseline count mismatch')
            for x,y in zip(own.itertuples(),actual):
                if (x.trajectory_id!=y['trajectory_id'] or x.start_time!=y['start'] or x.end_time!=y['end']
                    or x.point_count!=y['point_count'] or not np.allclose([x.latitude,x.longitude],
                        [y['latitude'],y['longitude']],rtol=0,atol=1e-9)):
                    raise ValueError(f'{user}: fixed-anchor baseline event mismatch')
            edge_rows=[]
            for method in METHODS:
                for dwell in DURATIONS:
                    for radius in (50,150,200):
                        budget.check()
                        l=DetectorConfig(method,100,dwell).config_id;r=DetectorConfig(method,radius,dwell).config_id
                        edge_rows.append(dict(user_id=user,method=method,edge=f'r100_to_{radius}_d{dwell}',
                            **_stability(events[l],events[r])))
                for radius in RADII:
                    budget.check()
                    l=DetectorConfig(method,radius,10).config_id;r=DetectorConfig(method,radius,20).config_id
                    edge_rows.append(dict(user_id=user,method=method,edge=f'd10_to_20_r{radius}',
                        **_stability(events[l],events[r])))
            event_path=directory/f'{user}_events.csv.gz'
            pd.DataFrame(flat,columns=['config_id','trajectory_id','start','end','latitude','longitude','point_count']).to_csv(event_path,index=False)
            metric_path=directory/f'{user}_metrics.csv';pd.DataFrame(rows).to_csv(metric_path,index=False)
            edge_path=directory/f'{user}_edges.csv';pd.DataFrame(edge_rows).to_csv(edge_path,index=False)
            _checkpoint(directory,audit,budget,user,[event_path,metric_path,edge_path])
        if seen_users!=expected or seen_points!=prep['totals']['output_points'] or seen_trajs!=prep['expected_trajectory_files']:
            raise ValueError('Real workload incomplete')
        if audit['completed_users']!=expected:raise ValueError('Missing real user checkpoints')
        if (clean.stat().st_size,clean.stat().st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):raise ValueError('Input changed during job')
        audit.update(users=len(expected),configs=len(cfgs),processed_points=seen_points,processed_trajectories=seen_trajs,
            baseline_parity_users=len(expected),timing_scope='detector only; no preprocessing/CSV scoring; call order rotated')
        budget.check();_finish(directory,audit,budget)
        return audit
    except BaseException as error:
        _finish(directory,audit,budget,error);raise


def summarize(root,out,split='selection'):
    root,out=Path(root),Path(out);lock=validate_lock(root,out)
    phase=out/('synthetic_'+split);audit=readj(phase/'audit.json')
    if audit['status']!='completed':raise ValueError('Synthetic job incomplete: no full comparison plots')
    for n,h in audit['output_hashes'].items():
        if file_hash(phase/n)!=h:raise ValueError(f'Checkpoint changed: {n}')
    directory=out/('summary_'+split)
    if directory.exists():raise FileExistsError(directory)
    directory.mkdir();budget=JobBudget(ledger(root,out))
    try:
        table=pd.concat([pd.read_csv(phase/f'{u}_metrics.csv.gz',dtype={'user_id':str,'independence_group':str})
            for u in audit['completed_users']],ignore_index=True)
        expected=audit['users']*audit['configs']*audit['cells']
        if len(table)!=expected or table.duplicated(['user_id','config_id','cell_id']).any():raise ValueError('Metric quota mismatch')
        rows=[]
        # Budget checks between cells/configs also bound bootstrap work.
        for _,part in table.groupby('config_id',sort=True):
            budget.check();rows.append(summarize_users(part))
        summary=pd.concat(rows,ignore_index=True)
        table.to_csv(directory/'per_user.csv.gz',index=False);summary.to_csv(directory/'macro_by_cell.csv',index=False)
        timing=pd.concat([pd.read_csv(phase/f'{u}_timing.csv',dtype={'user_id':str}) for u in audit['completed_users']],ignore_index=True)
        timing.to_csv(directory/'timing_per_user.csv',index=False)
        budget.check();write_json(directory/'audit.json',dict(status='completed',lock_hash=lock['lock_hash'],
            rows=len(summary),users=audit['users'],configurations=audit['configs'],
            output_hashes={n:file_hash(directory/n) for n in ['per_user.csv.gz','macro_by_cell.csv','timing_per_user.csv']},
            **budget.summary()))
        return summary
    except BaseException as error:
        write_json(directory/'audit.json',dict(status='failed',error=str(error),lock_hash=lock['lock_hash'],**budget.summary()));raise


def describe_real(root,out,split='selection'):
    root,out=Path(root),Path(out);lock=validate_lock(root,out)
    source=out/'real';audit=readj(source/'audit.json')
    if audit['status']!='completed':raise ValueError('Real-data job incomplete')
    directory=out/('real_description_'+split)
    if directory.exists():raise FileExistsError(directory)
    directory.mkdir();budget=JobBudget(ledger(root,out))
    try:
        for n,h in audit['output_hashes'].items():
            if file_hash(source/n)!=h:raise ValueError(f'Real checkpoint changed: {n}')
        p=readj(root/'artifacts/benchmark/b2/prepared_v1/protocol.json')
        users=sorted(u for u,s in p['split'].items() if s==split)
        table=pd.concat([pd.read_csv(source/f'{u}_metrics.csv',dtype={'user_id':str}) for u in users],ignore_index=True)
        edges=pd.concat([pd.read_csv(source/f'{u}_edges.csv',dtype={'user_id':str}) for u in users],ignore_index=True)
        if split=='final':
            winner=validate_winner(out,lock)
            table=table[table.config_id.isin([BASELINE_ID,winner['config_id']])]
            method=next(r['method'] for r in lock['main_configs'] if r['config_id']==winner['config_id'])
            edges=edges[edges.method.isin(['fixed_anchor',method])]
        rows=[]
        for cid,g in table.groupby('config_id'):
            first=g.iloc[0]
            rows.append(dict(config_id=cid,method=first.method,radius_m=first.radius_m,dwell_minutes=first.dwell_minutes,
                users=len(g),stays_total=int(g.stays.sum()),stays_user_median=float(g.stays.median()),
                dwell_total_hours=float(g.stay_dwell_minutes.sum()/60),dwell_user_median_hours=float(g.stay_dwell_minutes.median()/60),
                r_motor_user_macro=float(g.r_motor.mean()) if g.r_motor.notna().any() else np.nan,
                r_motor_pooled=float(g.motor_stay_seconds.sum()/g.labeled_stay_seconds.sum()) if g.labeled_stay_seconds.sum()>0 else np.nan,
                motor_denominator_users=int((g.labeled_stay_seconds>0).sum()),
                labeled_stay_hours=float(g.labeled_stay_seconds.sum()/3600),
                labeled_fraction=float(g.labeled_stay_seconds.sum()/(g.stay_dwell_minutes.sum()*60)) if g.stay_dwell_minutes.sum()>0 else np.nan,
                detector_seconds=float(g.detector_seconds.sum())))
        plateau=[]
        for (method,edge),g in edges.groupby(['method','edge']):
            eligible=g[(g.n_left>=5)&(g.n_right>=5)]
            share=float(((eligible.count_relative_change<=.1)&(eligible.dwell_relative_change<=.1)&(eligible.jaccard>=.8)).mean()) if len(eligible) else np.nan
            plateau.append(dict(method=method,edge=edge,users=len(g),eligible_users=len(eligible),
                plateau_share=share,plateau=bool(len(eligible)>0 and share>=.8),
                jaccard_median=float(eligible.jaccard.median()) if len(eligible) else np.nan))
        pd.DataFrame(rows).to_csv(directory/'counts_motor_runtime.csv',index=False)
        pd.DataFrame(plateau).to_csv(directory/'plateau.csv',index=False)
        edges.to_csv(directory/'edges_per_user.csv',index=False)
        modes=[]
        for row in table.itertuples():
            for mode,seconds in json.loads(row.mode_exposure_seconds).items():
                modes.append(dict(user_id=row.user_id,config_id=row.config_id,mode=mode,stay_seconds=seconds,
                    labeled_stay_seconds=row.labeled_stay_seconds))
        pd.DataFrame(modes,columns=['user_id','config_id','mode','stay_seconds','labeled_stay_seconds']).to_csv(
            directory/'mode_exposure_per_user.csv',index=False)
        budget.check();write_json(directory/'audit.json',dict(status='completed',lock_hash=lock['lock_hash'],scope=split,
            users=users,output_hashes={p.name:file_hash(p) for p in directory.glob('*.csv')},**budget.summary()))
        return pd.DataFrame(rows),pd.DataFrame(plateau)
    except BaseException as error:
        write_json(directory/'audit.json',dict(status='failed',error=str(error),**budget.summary()));raise
