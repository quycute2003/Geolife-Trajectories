"""Execution-policy extension: reuse the frozen parallel engine with up to 10 users.

This module does not modify the live v1 engine or scientific code. A separate
policy lock records permission to exceed its original three-worker wrapper.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys

from . import benchmark_parallel as engine
from . import benchmark_jobs as jobs
from .benchmark_synthetic import digest,file_hash

REVISION='b4-parallel-scaled-v1'


def execution_lock(root,out):
    root,out=Path(root),Path(out)
    original=engine.execution_lock(root,out)
    code=root/'src/geolife_inference/benchmark_parallel_scaled.py'
    path=out/'parallel_scaling_lock.json'
    if path.exists():
        policy=jobs.readj(path)
        if digest({k:v for k,v in policy.items() if k!='scaling_hash'})!=policy['scaling_hash']:
            raise ValueError('Parallel scaling policy mutated')
        if policy['engine_execution_hash']!=original['execution_hash'] or policy['runner_sha256']!=file_hash(code):
            raise ValueError('Scaling runner/engine changed; a new version is required')
        return policy
    policy=dict(revision=REVISION,engine_execution_hash=original['execution_hash'],
        runner_sha256=file_hash(code),permitted_workers=list(range(1,11)),
        note='Execution capacity only. Frozen engine/science/checkpoints and global budgets unchanged.')
    policy['scaling_hash']=digest(policy);engine.atomic_json(path,policy)
    return policy


def run_synthetic(root,out,resume=False,workers=10):
    root,out=Path(root),Path(out)
    if workers not in range(1,11):raise ValueError('Workers must be between 1 and 10')
    policy=execution_lock(root,out)
    with engine._coordinator_lease(out):
        audit_path=out/'synthetic_selection/audit.json'
        if audit_path.exists():
            audit=jobs.readj(audit_path)
            if audit['status']=='running':raise RuntimeError('Existing B4 job still running; stop it before scaling')
            audit['scaling_execution_hash']=policy['scaling_hash']
            if audit.get('error'):audit['previous_attempt_error']=audit.pop('error')
            engine.atomic_json(audit_path,audit)
        # The original engine allocates counters, PID slots and the pool from this
        # argument; only its public v1 wrapper had a three-worker policy limit.
        try:
            engine._coordinate(root,out,'selection',resume,workers)
        finally:
            if audit_path.exists():
                audit=jobs.readj(audit_path)
                audit['scaling_execution_hash']=policy['scaling_hash']
                audit['attempts'][-1]['scaling_execution_hash']=policy['scaling_hash']
                engine.atomic_json(audit_path,audit)
        return audit


def launch(root,out,workers=10,resume=True):
    root,out=Path(root),Path(out)
    if workers not in range(1,11):raise ValueError('Workers must be between 1 and 10')
    jobs.validate_lock(root,out)
    audit=jobs.readj(out/'synthetic_selection/audit.json') if (out/'synthetic_selection/audit.json').exists() else {}
    if audit.get('status')=='running':
        return dict(status='already_running',pid=audit.get('coordinator_pid'),workers=audit.get('workers',1),
            requested_workers=workers,note='Current active job was kept; stop/resume is required to change capacity')
    if audit.get('status')=='completed':return dict(status='completed')
    execution_lock(root,out)
    env=os.environ.copy();env['PYTHONPATH']=str(root/'src')+os.pathsep+env.get('PYTHONPATH','')
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
        env[name]='1'
    args=[sys.executable,'-u','-m','geolife_inference.benchmark_parallel_scaled','--root',str(root),
        '--out',str(out),'--workers',str(workers)]
    if resume:args.append('--resume')
    log=out/'parallel_resume.log';errors=out/'parallel_resume.stderr.log'
    with log.open('ab') as stdout,errors.open('ab') as stderr:
        process=subprocess.Popen(args,cwd=root,env=env,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    return dict(status='launched',pid=process.pid,workers=workers,log=str(log))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--workers',type=int,default=10)
    parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    run_synthetic(args.root,args.out,resume=args.resume,workers=args.workers)


if __name__=='__main__':
    mp.freeze_support();main()
