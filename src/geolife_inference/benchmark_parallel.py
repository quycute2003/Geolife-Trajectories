"""B4 execution-only extension: spawn users in parallel, retain the frozen v1 science.

The original jobs/detectors/evaluation modules and lock remain immutable. Only the
coordinator commits checkpoints. Workers own disjoint user files, never audit.json.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import gzip
import json
import multiprocessing as mp
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from . import benchmark_jobs as jobs
from .benchmark_detectors import detect
from .benchmark_evaluation import empty_accumulator,accumulate,finalize
from .benchmark_synthetic import file_hash,digest,memory_usage

REVISION='b4-parallel-users-v1'
_WORKER=None


def atomic_json(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(tmp,path)


def execution_lock(root,out):
    root,out=Path(root),Path(out);original=jobs.validate_lock(root,out)
    path=out/'parallel_execution_lock.json'
    code=root/'src/geolife_inference/benchmark_parallel.py'
    if path.exists():
        lock=jobs.readj(path)
        if digest({k:v for k,v in lock.items() if k!='execution_hash'})!=lock['execution_hash']:
            raise ValueError('Parallel execution lock mutated')
        if lock['parent_lock_hash']!=original['lock_hash'] or lock['runner_sha256']!=file_hash(code):
            raise ValueError('Parallel runner/parent lock changed: new execution version required')
        return lock
    lock=dict(revision=REVISION,parent_lock_hash=original['lock_hash'],runner_sha256=file_hash(code),
        permitted_workers=[1,2,3],science='Frozen v1 algorithms, inputs, grid, matching, gates unchanged',
        ledger='Cumulative wall time; per-config detector seconds summed across workers/attempts',
        timing='Parallel synthetic wall timing is descriptive; gate (d) retains serial real timing')
    lock['execution_hash']=digest(lock);atomic_json(path,lock)
    return lock


@contextmanager
def _coordinator_lease(out):
    """An OS-released lock prevents two parallel coordinators sharing outputs."""
    path=Path(out)/'parallel_coordinator.guard';handle=path.open('a+b')
    try:
        if not path.stat().st_size:handle.write(b'0');handle.flush()
        handle.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close();raise RuntimeError('Another B4 parallel coordinator is active') from None
    try:yield
    finally:handle.close()


def _process_ws(pid):
    """Read working set without adding a process-monitoring dependency."""
    if not pid:return 0
    if os.name!='nt':
        try:return int(Path(f'/proc/{pid}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
        except (OSError,IndexError):return 0
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(k,ctypes.c_size_t) for k in
            ['peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile']]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
    handle=kernel.OpenProcess(0x1000|0x0010,False,int(pid))
    if not handle:return 0
    try:
        c=Counters();c.cb=ctypes.sizeof(c)
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(c),c.cb):raise ctypes.WinError(ctypes.get_last_error())
        return int(c.ws)
    finally:kernel.CloseHandle(handle)


def _tree_ws(pids):
    return memory_usage()[0]+sum(_process_ws(pid) for pid in pids if pid)


def _initialize(cancel,counters,pids,slot_counter,nconfigs):
    global _WORKER
    # Ctrl+C belongs to the coordinator; children stop cooperatively via Event.
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    with slot_counter.get_lock():
        slot=slot_counter.value;slot_counter.value+=1
    pids[slot]=os.getpid()
    _WORKER=dict(cancel=cancel,counters=counters,slot=slot,nconfigs=nconfigs)


class WorkerClock:
    def __init__(self,ids):
        self.ids=ids;self.index={c:i for i,c in enumerate(ids)};self.current=None
        self.mark=0.;self.last=0.;self.total={c:0. for c in ids}
        base=_WORKER['slot']*len(ids)
        self.shared_base=[_WORKER['counters'][base+i] for i in range(len(ids))]

    def publish(self):
        if self.current is not None:
            i=self.index[self.current];base=_WORKER['slot']*len(self.ids)
            _WORKER['counters'][base+i]=self.shared_base[i]+self.total[self.current]+time.perf_counter()-self.mark

    def check(self):
        if _WORKER['cancel'].is_set():raise InterruptedError('Parallel stop requested')
        now=time.perf_counter()
        if now-self.last>=.5:self.publish();self.last=now

    @contextmanager
    def detector(self,cid):
        self.current=cid;self.mark=time.perf_counter()
        try:self.check();yield
        finally:
            self.publish();self.total[cid]+=time.perf_counter()-self.mark;self.current=None


def _run_user(payload):
    """Same arrays, ordering, scoring and output schema as frozen jobs.run_synthetic."""
    root,out,user,split,config_records,execution_hash=payload
    root,out=Path(root),Path(out)
    lock=execution_lock(root,out)
    if lock['execution_hash']!=execution_hash:raise ValueError('Worker execution lock mismatch')
    configs=[jobs.DetectorConfig(**{k:v for k,v in r.items() if k!='config_id'}) for r in config_records]
    clock=WorkerClock([c.config_id for c in configs]);clock.check()
    directory=out/('synthetic_'+split);corpus=root/f'artifacts/benchmark/b2/{split}_v1'
    prepared=jobs.readj(root/'artifacts/benchmark/b2/prepared_v1/protocol.json')
    ca=jobs.readj(corpus/'generation_audit.json');matrix=jobs.readj(corpus/'matrix.json')
    metadata={c['cell_id']:c for c in matrix}
    for sub,suffix in [('observations','csv.gz'),('truth','jsonl.gz')]:
        path=corpus/sub/f'{user}.{suffix}'
        if file_hash(path)!=ca['output_sha256'][str(path.relative_to(corpus))]:raise ValueError('Corpus hash mismatch')
    truths=jobs._truth_records(corpus/'truth'/f'{user}.jsonl.gz')
    if len(truths)!=len(matrix)*5 or any(v['source_user_id']!=user for v in truths.values()):
        raise ValueError('Truth user/case quota mismatch')
    for v in truths.values():
        if any(v.get(k)!=value for k,value in metadata[v['cell_id']].items()):raise ValueError('Truth metadata mismatch')
    states={(c.config_id,k):empty_accumulator() for c in configs for k in metadata}
    timing={c.config_id:0. for c in configs};seen=set()
    pred_path=directory/f'{user}_predictions.csv.gz'
    with gzip.open(pred_path,'wt',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['case_id','config_id','event_id','start','end','latitude','longitude','point_count'])
        writer.writeheader()
        def evaluate(cid,frame):
            clock.check();record=truths[cid]
            t=(pd.to_datetime(frame.timestamp,utc=True).astype('int64').to_numpy()/1e9 if len(frame) else np.empty(0))
            xy=frame[['latitude','longitude']].to_numpy(float) if len(frame) else np.empty((0,2))
            seg=frame.observation_segment.to_numpy() if len(frame) else np.empty(0,int)
            if len(frame)!=record['diagnostics']['observed_fixes']:raise ValueError('Case observation count mismatch')
            shift=int(digest(cid)[:8],16)%len(configs)
            for c in configs[shift:]+configs[:shift]:
                start=time.perf_counter()
                with clock.detector(c.config_id):pred=detect(t,xy,seg,c,clock.check)
                timing[c.config_id]+=time.perf_counter()-start
                accumulate(states[c.config_id,record['cell_id']],record,pred,t)
                writer.writerows(dict(case_id=cid,config_id=c.config_id,event_id=i,**e) for i,e in enumerate(pred))
        for cid,frame in jobs._iter_cases(corpus/'observations'/f'{user}.csv.gz'):
            if cid not in truths or cid in seen:raise ValueError('Unknown or noncontiguous case')
            evaluate(cid,frame);seen.add(cid)
        for cid in sorted(set(truths)-seen):
            if truths[cid]['diagnostics']['observed_fixes']!=0:raise ValueError('Missing nonempty case')
            evaluate(cid,pd.DataFrame());seen.add(cid)
    profiles=pd.read_csv(root/'artifacts/benchmark/b1/profiles_v1/profiles_per_user.csv',dtype={'user_id':str}).set_index('user_id')
    rows=[]
    for c in configs:
        for cell in matrix:
            state=states[c.config_id,cell['cell_id']]
            if state['cases']!=5:raise ValueError('Not five seeds per cell/config')
            rows.append(dict(user_id=user,independence_group=prepared['independence_groups'][user],
                cadence_median_seconds=float(profiles.loc[user,'dt_observed_seconds_p50']),**c.record(),**cell,**finalize(state)))
    metric_path=directory/f'{user}_metrics.csv.gz';pd.DataFrame(rows).to_csv(metric_path,index=False)
    timing_path=directory/f'{user}_timing.csv'
    pd.DataFrame([dict(user_id=user,config_id=k,detector_seconds=v,cases=len(truths),
        observations=sum(x['diagnostics']['observed_fixes'] for x in truths.values()),
        execution_mode='parallel_users',worker_pid=os.getpid()) for k,v in timing.items()]).to_csv(timing_path,index=False)
    return dict(user=user,files=[p.name for p in [metric_path,timing_path,pred_path]],pid=os.getpid())


class ParallelBudget(jobs.JobBudget):
    def __init__(self,used,previous,historical,shared,pids,ids,workers):
        super().__init__(used,previous,historical)
        self.previous=dict(previous);self.shared=shared;self.pids=pids;self.ids=ids;self.workers=workers
        self.aggregate_peak=0

    def update_counters(self):
        for i,cid in enumerate(self.ids):
            self.config_seconds[cid]=self.previous.get(cid,0)+sum(self.shared[w*len(self.ids)+i] for w in range(self.workers))

    def check(self):
        self.update_counters();super().check()
        ws=_tree_ws(self.pids);self.aggregate_peak=max(self.aggregate_peak,ws)
        if ws>self.cap:raise MemoryError(f'Coordinator + workers working set {ws} > RAM budget {self.cap}')
        if any(v+self.historical.get(cid,0)>43200 for cid,v in self.config_seconds.items()):
            raise TimeoutError('Parallel cumulative detector compute exceeded 12 hours/config')

    def summary(self):
        self.update_counters()
        return dict(**super().summary(),aggregate_peak_working_set_bytes=self.aggregate_peak)


def _commit(directory,audit,budget,result):
    user=result['user']
    if user in audit['completed_users']:raise ValueError('User was submitted twice')
    for name in result['files']:audit['output_hashes'][name]=file_hash(directory/name)
    audit['completed_users']=sorted(audit['completed_users']+[user])
    audit.update(budget.summary())
    atomic_json(directory/'audit.json',audit)
    print(f'synthetic parallel: {len(audit["completed_users"])} users completed ({user})',flush=True)


def request_stop(out):
    """Ask the active parallel attempt to stop at its next budget check."""
    out=Path(out);audit=jobs.readj(out/'synthetic_selection/audit.json')
    atomic_json(out/'parallel_stop.json',dict(attempt_id=audit.get('parallel_attempt_id')))


def status(out):
    """Small notebook-friendly snapshot; all time values here are execution time."""
    out=Path(out);path=out/'synthetic_selection/audit.json'
    if not path.exists():return dict(status='not_started')
    a=jobs.readj(path);started=a.get('active_user_started_epoch',{})
    return dict(status=a['status'],completed_users=len(a['completed_users']),
        active_users={u:round((time.time()-t)/60,1) for u,t in started.items()},
        workers=a.get('workers',1),worker_pids=a.get('worker_pids',[]),
        aggregate_peak_mib=round(a.get('aggregate_peak_working_set_bytes',0)/1024**2,1),
        compute_used_hours=round(a.get('compute_used_after_seconds',0)/3600,3),error=a.get('error'))


def run_synthetic(root,out,split='selection',resume=False,workers=3):
    root,out=Path(root),Path(out)
    if split!='selection':raise ValueError('Final remains on the frozen serial runner')
    if workers not in (1,2,3):raise ValueError('Workers must be 1, 2 or 3')
    with _coordinator_lease(out):
        return _coordinate(root,out,split,resume,workers)


def _coordinate(root,out,split,resume,workers):
    # Do not attach to a running v1 notebook or another coordinator.
    directory=out/('synthetic_'+split)
    if (directory/'audit.json').exists() and jobs.readj(directory/'audit.json')['status']=='running':
        raise RuntimeError('Existing B4 job still running; interrupt it before parallel resume')
    execution=execution_lock(root,out)
    lock,directory,audit,original_budget=jobs._start(root,out,'synthetic_'+split,resume)
    ctx=mp.get_context('spawn');configs=jobs._cfgs(lock);ids=[c.config_id for c in configs]
    cancel=ctx.Event();counters=ctx.Array('d',workers*len(ids));pids=ctx.Array('i',workers);slots=ctx.Value('i',0)
    budget=ParallelBudget(original_budget.used,original_budget.config_seconds,original_budget.historical,
        counters,pids,ids,workers)
    # Charge coordinator preparation once, starting from the already-created attempt.
    budget.start=original_budget.start;budget.cap=original_budget.cap
    budget.config_peak=original_budget.config_peak
    budget.aggregate_peak=audit.get('aggregate_peak_working_set_bytes',0)
    audit['parallel_attempt_id']=digest([os.getpid(),time.time_ns()])
    audit['execution_mode']='parallel_users';audit['workers']=workers;audit['coordinator_pid']=os.getpid()
    audit['parallel_execution_hash']=execution['execution_hash'];audit['active_users']=[]
    audit['attempts'][-1].update(execution_mode='parallel_users',workers=workers,execution_hash=execution['execution_hash'])
    # Preserve original sequential timings and identify inherited vs new users.
    audit.setdefault('inherited_serial_users',list(audit['completed_users']))
    pool=None;active={};started={};failed=None;completed_futures=set()
    try:
        prep=jobs.readj(root/'artifacts/benchmark/b2/prepared_v1/protocol.json')
        expected=sorted(u for u,s in prep['split'].items() if s==split)
        corpus=root/'artifacts/benchmark/b2/selection_v1';ca=jobs.readj(corpus/'generation_audit.json')
        matrix=jobs.readj(corpus/'matrix.json')
        if ca['status']!='completed' or ca['protocol_hash']!=lock['b2_protocol_hash']:
            raise ValueError('Invalid frozen corpus')
        if len({c['cell_id'] for c in matrix})!=len(matrix) or ca['cases']!=len(expected)*len(matrix)*5:
            raise ValueError('Synthetic matrix/case quota mismatch')
        if not set(audit['completed_users'])<=set(expected):raise ValueError('Unknown completed user')
        pending=iter(u for u in expected if u not in audit['completed_users'])
        pool=ProcessPoolExecutor(max_workers=workers,mp_context=ctx,initializer=_initialize,
            initargs=(cancel,counters,pids,slots,len(ids)))
        def submit():
            user=next(pending,None)
            if user is not None:
                future=pool.submit(_run_user,(str(root),str(out),user,split,lock['all_configs'],execution['execution_hash']))
                active[future]=user
                started[user]=time.time()
                print(f'Assigned user {user} ({len(active)}/{workers} slots)',flush=True)
        for _ in range(workers):submit()
        while active:
            budget.check()
            stop=out/'parallel_stop.json'
            if stop.exists() and jobs.readj(stop).get('attempt_id')==audit['parallel_attempt_id']:
                raise InterruptedError('User requested stop')
            audit['active_users']=sorted(active.values());audit['worker_pids']=[p for p in pids if p]
            audit['active_user_started_epoch']={u:started[u] for u in active.values()}
            audit.update(budget.summary());atomic_json(directory/'audit.json',audit)
            ready,_=wait(active,timeout=1,return_when=FIRST_COMPLETED)
            for future in ready:
                result=future.result();completed_futures.add(future)
                _commit(directory,audit,budget,result);active.pop(future);submit()
        if audit['completed_users']!=expected:raise ValueError('Missing completed users')
        timing=pd.concat([pd.read_csv(directory/f'{u}_timing.csv') for u in expected],ignore_index=True)
        for cid,g in timing.groupby('config_id'):
            if g.cases.sum()!=ca['cases'] or g.observations.sum()!=ca['points']:
                raise ValueError(f'{cid}: global case/point quota mismatch')
        audit.update(configs=len(configs),users=len(expected),cells=len(matrix),cases_per_config=ca['cases'],
            observations_per_config=ca['points'],timing_scope='mixed serial/parallel synthetic detector wall time; descriptive only')
        budget.check()
    except BaseException as error:
        failed=error;cancel.set()
    finally:
        if pool is not None:
            if failed:cancel.set()
            pool.shutdown(wait=True,cancel_futures=True)
            # Accept complete worker outputs even when the coordinator was interrupted.
            for future in list(active):
                if future.done() and not future.cancelled() and future.exception() is None and future not in completed_futures:
                    _commit(directory,audit,budget,future.result())
        audit['active_users']=[];audit['worker_pids']=[];audit['active_user_started_epoch']={}
        stats=budget.summary();status='failed' if failed else 'completed'
        audit.update(status=status,**stats)
        audit['attempts'][-1].update(status=status,**stats)
        if failed:audit['error']=f'{type(failed).__name__}: {failed}'
        else:audit.pop('error',None)
        atomic_json(directory/'audit.json',audit)
    if failed:raise failed
    return audit


def launch(root,out,workers=3,resume=True):
    """Start a hidden independent coordinator; notebook kernels need not stay busy."""
    root,out=Path(root),Path(out);jobs.validate_lock(root,out)
    audit=jobs.readj(out/'synthetic_selection/audit.json') if (out/'synthetic_selection/audit.json').exists() else {}
    if audit.get('status')=='running':
        if audit.get('execution_mode')=='parallel_users':return dict(status='already_running',pid=audit.get('coordinator_pid'))
        raise RuntimeError('Interrupt the existing sequential job first')
    if audit.get('status')=='completed':return dict(status='completed')
    execution_lock(root,out)
    log=out/'parallel_resume.log';errors=out/'parallel_resume.stderr.log'
    env=os.environ.copy();env['PYTHONPATH']=str(root/'src')+os.pathsep+env.get('PYTHONPATH','')
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
        env[name]='1'
    args=[sys.executable,'-u','-m','geolife_inference.benchmark_parallel','--root',str(root),'--out',str(out),'--workers',str(workers)]
    if resume:args.append('--resume')
    with log.open('ab') as stdout,errors.open('ab') as stderr:
        proc=subprocess.Popen(args,cwd=root,env=env,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    return dict(status='launched',pid=proc.pid,workers=workers,log=str(log))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    run_synthetic(args.root,args.out,resume=args.resume,workers=args.workers)


if __name__=='__main__':
    mp.freeze_support();main()
