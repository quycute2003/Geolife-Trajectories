"""Spawn-process parity and preserved-checkpoint tests; no real GeoLife run."""
import gzip
import multiprocessing as mp
from pathlib import Path

import pandas as pd
import pytest

from test_b4_jobs import b4_fixture
from geolife_inference import benchmark_jobs as jobs,benchmark_parallel as parallel
from geolife_inference.benchmark_synthetic import file_hash,write_json


def prepare(root,out,monkeypatch):
    source=Path(parallel.__file__)
    (root/'src/geolife_inference/benchmark_parallel.py').write_bytes(source.read_bytes())
    monkeypatch.setattr(parallel,'_tree_ws',lambda pids:100)
    return root,out


def test_three_worker_spawn_matches_frozen_serial_and_retains_science(b4_fixture,monkeypatch):
    root,serial=b4_fixture;prepare(root,serial,monkeypatch)
    jobs.run_synthetic(root,serial)
    out=serial.with_name('parallel_v1');jobs.register(root,out)
    before=file_hash(serial/'lock.json')
    audit=parallel.run_synthetic(root,out,workers=3)
    assert audit['status']=='completed' and audit['workers']==3
    assert audit['completed_users']==['000','001'] and file_hash(serial/'lock.json')==before
    pids=set()
    for user in audit['completed_users']:
        pd.testing.assert_frame_equal(pd.read_csv(serial/'synthetic_selection'/f'{user}_metrics.csv.gz'),
            pd.read_csv(out/'synthetic_selection'/f'{user}_metrics.csv.gz'),check_exact=True)
        with gzip.open(serial/'synthetic_selection'/f'{user}_predictions.csv.gz','rb') as a, \
             gzip.open(out/'synthetic_selection'/f'{user}_predictions.csv.gz','rb') as b:
            assert a.read()==b.read()
        timing=pd.read_csv(out/'synthetic_selection'/f'{user}_timing.csv')
        pids.update(timing.worker_pid)
        assert timing.execution_mode.eq('parallel_users').all()
    assert len(pids)==2
    summary=jobs.summarize(root,out)
    assert len(summary)==48*4


def test_interrupt_resume_preserves_committed_files(b4_fixture,monkeypatch):
    root,out=prepare(*b4_fixture,monkeypatch)
    commit=parallel._commit;raised=False
    def interrupt_once(*args):
        nonlocal raised
        commit(*args)
        if not raised:raised=True;raise KeyboardInterrupt('Constructed stop after checkpoint')
    monkeypatch.setattr(parallel,'_commit',interrupt_once)
    with pytest.raises(KeyboardInterrupt):parallel.run_synthetic(root,out,workers=3)
    audit=jobs.readj(out/'synthetic_selection/audit.json')
    assert audit['status']=='failed' and len(audit['completed_users'])>=1
    hashes=dict(audit['output_hashes']);used=audit['compute_used_after_seconds']
    monkeypatch.setattr(parallel,'_commit',commit)
    resumed=parallel.run_synthetic(root,out,workers=3,resume=True)
    assert resumed['status']=='completed' and len(resumed['attempts'])==2
    assert resumed['compute_used_after_seconds']>used
    assert all(resumed['output_hashes'][name]==expected for name,expected in hashes.items())
    with pytest.raises(FileExistsError):parallel.run_synthetic(root,out,workers=3,resume=True)


def test_existing_serial_checkpoints_migrate_without_rewrite(b4_fixture,monkeypatch):
    root,out=prepare(*b4_fixture,monkeypatch)
    checkpoint=jobs._checkpoint
    def stop(*args):
        checkpoint(*args);raise KeyboardInterrupt('Stop serial fixture')
    monkeypatch.setattr(jobs,'_checkpoint',stop)
    with pytest.raises(KeyboardInterrupt):jobs.run_synthetic(root,out)
    audit=jobs.readj(out/'synthetic_selection/audit.json');hashes=dict(audit['output_hashes'])
    original=file_hash(out/'lock.json')
    resumed=parallel.run_synthetic(root,out,workers=3,resume=True)
    assert resumed['status']=='completed' and resumed['inherited_serial_users']==['000']
    assert file_hash(out/'lock.json')==original
    assert all(resumed['output_hashes'][name]==expected for name,expected in hashes.items())


def test_parallel_lease_and_runner_lock_reject_conflicts(b4_fixture,monkeypatch):
    root,out=prepare(*b4_fixture,monkeypatch)
    with parallel._coordinator_lease(out):
        with pytest.raises(RuntimeError,match='coordinator'):parallel.run_synthetic(root,out)
    parallel.execution_lock(root,out)
    (root/'src/geolife_inference/benchmark_parallel.py').write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError,match='runner/parent lock changed'):parallel.execution_lock(root,out)


def test_budget_sums_all_workers_and_enforces_aggregate_ram(b4_fixture,monkeypatch):
    prepare(*b4_fixture,monkeypatch)
    ctx=mp.get_context('spawn');counters=ctx.Array('d',[2.,3.,4.]);pids=ctx.Array('i',3)
    budget=parallel.ParallelBudget(100,{'x':10},{'x':20},counters,pids,['x'],3)
    budget.check();assert budget.config_seconds['x']==19
    assert budget.summary()['aggregate_peak_working_set_bytes']==100
    budget.historical['x']=43200
    with pytest.raises(TimeoutError):budget.check()
    budget.historical['x']=0
    monkeypatch.setattr(parallel,'_tree_ws',lambda pids:budget.cap+1)
    with pytest.raises(MemoryError):budget.check()
