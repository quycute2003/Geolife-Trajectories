"""Synthetic filesystem fixtures exercise the complete B4 flow and interruption rules."""
import csv
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from geolife_inference import benchmark_jobs as jobs
from geolife_inference.benchmark_decisions import decide,generate_final,_gate_c
from geolife_inference.benchmark_synthetic import digest,file_hash,write_json,cells,make_case
from geolife_inference.config import Config
from geolife_inference.stays import detect_stays
from geolife_inference.benchmark_detectors import configurations,BASELINE_ID


@pytest.fixture
def b4_fixture(tmp_path,monkeypatch):
    root=tmp_path/'root';out=root/'artifacts/benchmark/b4/run_v1'
    for folder in ['reports/cp1','src/geolife_inference','artifacts/benchmark/b2/prepared_v1',
        'artifacts/benchmark/b2/selection_v1/observations','artifacts/benchmark/b2/selection_v1/truth',
        'artifacts/benchmark/b3/cleaning_v1','artifacts/preprocessing','artifacts/stays',
        'artifacts/benchmark/b1/profiles_v1']:
        (root/folder).mkdir(parents=True)
    for n in jobs.MODULES:
        (root/'src/geolife_inference'/n).write_bytes((Path(jobs.__file__).parent/n).read_bytes())
    (root/'reports/cp1/detector_protocol.md').write_text('Fixture protocol',encoding='utf-8')
    (root/'PLAN.md').write_text('## Bổ sung CP1\nFixture\n## Lộ trình 6 tuần',encoding='utf-8')
    p=dict(split={'000':'selection','001':'selection','002':'final'},
        independence_groups={u:u for u in ['000','001','002']},mode='selection_confirmation_cohort_pending')
    p['protocol_hash']=digest(p)
    write_json(root/'artifacts/benchmark/b2/prepared_v1/protocol.json',p)
    matrix=[c for c in cells(100) if
        (c['group']=='main' and (c['duration_group'],c['rms'],c['family']) in [(1,15,'drift'),(2,30,'outlier')])
        or (c['group']=='negative' and c['negative_kind']=='pure_move') or c['group']=='unobservable']
    assert len(matrix)==4
    corpus=root/'artifacts/benchmark/b2/selection_v1';write_json(corpus/'matrix.json',matrix)
    total_points=0
    for u in ['000','001']:
        t=1200000000+np.arange(0,601,120)
        xy=np.column_stack([np.full(len(t),39.+int(u)*.01),116.+np.arange(len(t))*.003])
        with (gzip.open(corpus/'observations'/f'{u}.csv.gz','wt',encoding='utf-8',newline='') as obs,
              gzip.open(corpus/'truth'/f'{u}.jsonl.gz','wt',encoding='utf-8') as truth):
            w=csv.writer(obs);w.writerow(['case_id','source_user_id','timestamp','latitude','longitude','observation_segment'])
            for cell in matrix:
                for seed in range(100000,100005):
                    a=make_case(t,xy,cell,seed,[]);cid=f'{u}_{cell["cell_id"]}_{seed}'
                    rec=dict(case_id=cid,source_user_id=u,seed=seed,**cell,events=a['truth'],diagnostics=a['metrics'])
                    truth.write(json.dumps(rec)+'\n')
                    for time,coord,seg in zip(a['times'],a['coords'],a['segments']):
                        w.writerow([cid,u,pd.Timestamp(time,unit='s',tz='UTC').isoformat(),*coord,int(seg)])
                    total_points+=len(a['times'])
    outputs={str(p.relative_to(corpus)):file_hash(p) for sub in ['observations','truth'] for p in (corpus/sub).iterdir()}
    write_json(corpus/'generation_audit.json',dict(status='completed',protocol_hash=p['protocol_hash'],
        cases=40,points=total_points,output_sha256=outputs))
    write_json(root/'artifacts/benchmark/b3/cleaning_v1/audit.json',dict(status='completed',compute_used_after_seconds=100))
    frames=[];stays=[]
    for u in ['000','001','002']:
        t=np.arange(41)*30.+1200000000
        frame=pd.DataFrame(dict(user_id=u,trajectory_id='t',timestamp=pd.to_datetime(t,unit='s',utc=True),
            latitude=39.+int(u)*.01,longitude=116.,observation_segment=1))
        frames.append(frame);stays.append(detect_stays(frame,Config())[0])
    clean=root/'artifacts/preprocessing/cleaned_points.csv.gz';pd.concat(frames).to_csv(clean,index=False)
    pd.concat(stays).to_csv(root/'artifacts/stays/stays.csv',index=False)
    write_json(root/'artifacts/preprocessing/audit.json',dict(expected_users=['000','001','002'],
        expected_trajectory_files=3,totals=dict(output_points=123)))
    b1=root/'artifacts/benchmark/b1/profiles_v1'
    pd.DataFrame([dict(user_id=u,dt_observed_seconds_p50=30) for u in ['000','001','002']]).to_csv(b1/'profiles_per_user.csv',index=False)
    write_json(b1/'profile_audit.json',dict(cleaned_bytes=clean.stat().st_size,cleaned_mtime_ns=clean.stat().st_mtime_ns))
    monkeypatch.setattr(jobs,'memory_usage',lambda:(100,100))
    monkeypatch.setattr(jobs,'available_memory',lambda:10**9)
    jobs.register(root,out)
    return root,out


def test_jobs_resume_score_real_and_keep_final_closed(b4_fixture,monkeypatch):
    root,out=b4_fixture
    checkpoint=jobs._checkpoint
    def fail_after_user(*args,**kwargs):
        checkpoint(*args,**kwargs)
        raise RuntimeError('Constructed interruption after checkpoint')
    monkeypatch.setattr(jobs,'_checkpoint',fail_after_user)
    with pytest.raises(RuntimeError):jobs.run_synthetic(root,out)
    audit=jobs.readj(out/'synthetic_selection/audit.json')
    assert audit['status']=='failed' and audit['completed_users']==['000']
    preserved=dict(audit['output_hashes'])
    monkeypatch.setattr(jobs,'_checkpoint',checkpoint)
    audit=jobs.run_synthetic(root,out,resume=True)
    assert audit['status']=='completed' and audit['configs']==48 and len(audit['attempts'])==2
    assert all(audit['output_hashes'][k]==v for k,v in preserved.items())
    summary=jobs.summarize(root,out)
    assert len(summary)==48*4 and summary.users.eq(2).all()
    assert summary.loc[summary['group']=='negative','f1'].isna().all()
    real=jobs.run_real(root,out)
    assert real['status']=='completed' and real['baseline_parity_users']==3
    desc,plateau=jobs.describe_real(root,out)
    assert len(desc)==40 and desc.users.eq(2).all()
    assert len(plateau)==50
    gates,winner=decide(root,out)
    assert len(gates)==19 and winner['status']=='keep_baseline'
    with pytest.raises(ValueError):generate_final(root,out)
    assert not (root/'artifacts/benchmark/b2/final_v1').exists()
    with pytest.raises(FileExistsError):jobs.run_synthetic(root,out,resume=True)


def test_lock_rejects_changed_code(b4_fixture):
    root,out=b4_fixture
    (root/'src/geolife_inference/benchmark_detectors.py').write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError,match='code changed'):jobs.validate_lock(root,out)


def test_stability_requires_same_cohort_across_both_edges():
    real=pd.DataFrame([dict(user_id=str(i),config_id=cid,labeled_stay_seconds=100,r_motor=0.)
                      for i in range(30) for cid in ['fixed_anchor_r100_d10','median_updated_r100_d10']])
    rows=[]
    for method in ['fixed_anchor','median_updated']:
        for edge,users in [('r100_to_50_d10',range(20)),('r100_to_200_d10',range(10,30))]:
            rows.extend(dict(user_id=str(i),method=method,edge=edge,n_left=5,n_right=5,jaccard=1.,
                count_relative_change=0.,dwell_relative_change=0.) for i in users)
    passed,failures,details=_gate_c(real,pd.DataFrame(rows),'median_updated_r100_d10','median_updated',[str(i) for i in range(30)])
    assert not passed and len(details['stability_common_user_ids'])==10
    assert any('fewer than 15' in f for f in failures)


def test_budget_config_limit_accumulates_across_stages(monkeypatch):
    monkeypatch.setattr(jobs,'memory_usage',lambda:(100,100))
    monkeypatch.setattr(jobs,'available_memory',lambda:10**9)
    budget=jobs.JobBudget(100,historical={BASELINE_ID:43201})
    with pytest.raises(TimeoutError,match='12 hours'):
        with budget.detector(BASELINE_ID):pass


def test_winner_requires_completed_decision_and_immutable_gates(b4_fixture):
    root,out=b4_fixture;lock=jobs.validate_lock(root,out)
    folder=out/'decision_selection';folder.mkdir()
    (folder/'gates.csv').write_text('fixture',encoding='utf-8')
    write_json(folder/'winner.json',dict(status='selected',config_id='median_updated_r100_d10',
        lock_hash=lock['lock_hash'],gates_sha256=file_hash(folder/'gates.csv')))
    write_json(folder/'audit.json',dict(status='failed',winner_sha256=file_hash(folder/'winner.json')))
    with pytest.raises(ValueError,match='not completed'):jobs.validate_winner(out,lock)
    write_json(folder/'audit.json',dict(status='completed',winner_sha256=file_hash(folder/'winner.json')))
    assert jobs.validate_winner(out,lock)['status']=='selected'
    (folder/'gates.csv').write_text('mutated',encoding='utf-8')
    with pytest.raises(ValueError,match='gates changed'):jobs.validate_winner(out,lock)


def test_all_plot_panels_on_fabricated_metrics(b4_fixture):
    import matplotlib
    matplotlib.use('Agg')
    from geolife_inference.benchmark_plots import render
    root,out=b4_fixture;folder=out/'summary_selection';folder.mkdir()
    rows=[]
    for cfg in configurations():
        for cell in cells(100):
            rows.append(dict(**cfg.record(),**cell,f1=.7,f1_ci_low=.6,f1_ci_high=.8,
                fp_per_hour=.01,cadence_median_seconds=5,user_id='000'))
    data=pd.DataFrame(rows)
    data.to_csv(folder/'macro_by_cell.csv',index=False)
    data.to_csv(folder/'per_user.csv.gz',index=False)
    pd.DataFrame([dict(user_id='000',config_id=c.config_id,detector_seconds=1.) for c in configurations()]).to_csv(
        folder/'timing_per_user.csv',index=False)
    write_json(folder/'audit.json',dict(status='completed',output_hashes={
        p.name:file_hash(p) for p in folder.iterdir()}))
    paths=render(root,out)
    assert len(paths)==19 and all(p.stat().st_size>1000 for p in paths)
    audit=jobs.readj(out/'plots_selection/audit.json')
    assert len(audit['files'])==21 and audit['status']=='completed'
    assert all(file_hash(out/'plots_selection'/n)==h for n,h in audit['files'].items())


def test_final_runs_only_locked_pair_with_mocked_gate_evidence(b4_fixture,monkeypatch):
    """Exercise plumbing, not scientific gate validity, using deliberately mocked evidence."""
    from geolife_inference import benchmark_decisions as decisions
    root,out=b4_fixture
    jobs.run_synthetic(root,out);jobs.summarize(root,out);jobs.run_real(root,out)
    audit=jobs.readj(out/'real/audit.json')
    for user in audit['completed_users']:
        path=out/'real'/f'{user}_metrics.csv';frame=pd.read_csv(path,dtype={'user_id':str})
        frame['detector_seconds']=1.;frame.to_csv(path,index=False)
        audit['output_hashes'][path.name]=file_hash(path)
    write_json(out/'real/audit.json',audit)
    monkeypatch.setattr(decisions,'_gate_a',lambda *args:(True,[]))
    monkeypatch.setattr(decisions,'_gate_b',lambda *args:(True,[],[]))
    monkeypatch.setattr(decisions,'_gate_c',lambda *args:(True,[],{}))
    _,winner=decisions.decide(root,out)
    assert winner['status']=='selected'
    selection=root/'artifacts/benchmark/b2/selection_v1';final=selection.with_name('final_v1')
    (final/'observations').mkdir(parents=True);(final/'truth').mkdir()
    write_json(final/'matrix.json',jobs.readj(selection/'matrix.json'))
    with gzip.open(selection/'observations/000.csv.gz','rt',encoding='utf-8') as f:
        text=f.read().replace('000_', '002_').replace(',000,',',002,')
    with gzip.open(final/'observations/002.csv.gz','wt',encoding='utf-8') as f:f.write(text)
    points=0
    with gzip.open(selection/'truth/000.jsonl.gz','rt',encoding='utf-8') as source, \
         gzip.open(final/'truth/002.jsonl.gz','wt',encoding='utf-8') as target:
        for line in source:
            row=json.loads(line);row['source_user_id']='002';row['case_id']=row['case_id'].replace('000_','002_')
            target.write(json.dumps(row)+'\n');points+=row['diagnostics']['observed_fixes']
    write_json(final/'generation_audit.json',dict(status='completed',cases=20,points=points,
        protocol_hash=jobs.readj(out/'lock.json')['b2_protocol_hash'],output_sha256={
        str(p.relative_to(final)):file_hash(p) for sub in ['observations','truth'] for p in (final/sub).iterdir()}))
    final_audit=jobs.run_synthetic(root,out,split='final')
    assert final_audit['configs']==2 and final_audit['users']==1
    summary=jobs.summarize(root,out,split='final')
    assert set(summary.config_id)=={BASELINE_ID,winner['config_id']}
    gates,decision=decisions.decide(root,out,split='final')
    assert len(gates)==1 and decision['status']=='confirmed'
    with pytest.raises(FileExistsError):decisions.decide(root,out,split='final')
