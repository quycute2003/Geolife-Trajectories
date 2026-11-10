"""Small independent fixtures only; never run GeoLife jobs or open B4 final."""
from dataclasses import replace
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import pickle
import shutil

import numpy as np
import pandas as pd
import pytest

from geolife_inference import benchmark_roles as b5
from geolife_inference.clustering import MODEL_VERSIONS, group_locations
from geolife_inference.config import Config
from geolife_inference.features import cluster_features, observation_coverage
from geolife_inference.inference import rank_role


class Finder:
    def timezone_names_at(self, *, lngs, lats):
        return ['Asia/Shanghai' if x > 110 else 'Asia/Bangkok' for x in lngs]

    def timezone_at(self, *, lng, lat):
        return 'Asia/Shanghai' if lng > 110 else 'Asia/Bangkok'


def location(cluster_id, days, dwell):
    return dict(cluster_id=cluster_id, latitude=40., longitude=116.,
                night_visit_days=days, night_dwell_minutes=dwell,
                weekday_daytime_visit_days=days, weekday_daytime_dwell_minutes=dwell,
                weekday_daytime_weeks=2)


def coverage():
    return dict(observed_minutes=1440., observed_days=10, night_observed_days=10, work_observed_days=10)


def test_simple_rule_uses_days_then_dwell_and_abstains_on_tie():
    cfg = Config()
    a, b = location(7, 4, 90), location(2, 3, 1000)
    assert b5.simple_role([a, b], coverage(), cfg, 'home')['candidate']['cluster_id'] == 7
    a, b = location(7, 3, 90), location(2, 3, 100)
    assert b5.simple_role([a, b], coverage(), cfg, 'home')['candidate']['cluster_id'] == 2
    a['night_dwell_minutes'] = 100
    assert b5.simple_role([a, b], coverage(), cfg, 'home')['reason'] == 'tied_days_and_dwell'
    # Cluster-ID order must not resolve a tie.
    assert b5.simple_role([b, a], coverage(), cfg, 'home')['status'] == 'unknown'


def test_simple_rule_preserves_eligibility_but_has_no_share_gate():
    cfg = Config()
    assert b5.simple_role([location(1, 2, 1000)], coverage(), cfg, 'home')['status'] == 'unknown'
    a, b = location(1, 4, 100), location(2, 3, 1000)
    assert b5.simple_role([a, b], coverage(), cfg, 'home')['candidate']['cluster_id'] == 1
    a['weekday_daytime_weeks'] = 1
    assert b5.simple_role([a], coverage(), cfg, 'office')['status'] == 'unknown'


def test_comparison_uses_coordinates_not_local_cluster_ids():
    a = pd.DataFrame([dict(user_id='000', role='home', status='predicted', cluster_id=1, latitude=40., longitude=116.)])
    b = a.assign(cluster_id=99, latitude=40.00001)
    result = b5.compare(a, b)
    assert result.same_place.iloc[0]
    b = a.assign(latitude=41.)
    assert not b5.compare(a, b).same_place.iloc[0]
    with pytest.raises(ValueError, match='thiếu user'):
        b5.compare(a, b.assign(user_id='001'))


def test_context_parity_gap_and_mixed_timezone_preserve_utc_elapsed():
    cfg = Config()
    # UTC 14:00 = 22:00 Shanghai; 21:00 Bangkok. No elapsed-time conversion.
    times = pd.to_datetime(['2008-01-01T14:00Z','2008-01-01T14:05Z',
                            '2008-01-01T14:10Z','2008-01-01T15:00Z'])
    frame = pd.DataFrame(dict(user_id='000', trajectory_id='a', timestamp=times,
                             latitude=40., longitude=[116., 116., 105., 105.], observation_segment=[0,0,0,1]))
    result = b5._context([frame], cfg, Finder())
    expected = observation_coverage(frame, cfg)
    for name in ['observed_minutes','observed_days','night_observed_days','work_observed_days']:
        assert result['baseline'][name] == expected[name]
    assert result['baseline']['observed_minutes'] == 10
    assert result['localized']['observed_minutes'] == 10
    assert result['affected']
    assert result['cross_zone_pairs'] == 1
    assert result['cross_zone_pair_seconds'] == 300
    # Moving night start to 23:00 removes this ten-minute GPS coverage from night.
    assert result['shifts']['1']['night_observed_days'] == 0
    assert result['shifts']['-1']['night_observed_days'] == 1


def test_context_includes_isolated_fix_days_and_observed_days_in_periods():
    cfg = Config()
    frame = pd.DataFrame(dict(user_id='000', trajectory_id='a',
        timestamp=pd.to_datetime(['2008-01-01T00:00Z','2008-01-02T00:00Z']),
        latitude=40., longitude=116., observation_segment=[0,1]))
    value = b5._context([frame], cfg, Finder())
    assert value['baseline']['observed_days'] == 2
    assert value['baseline']['observed_minutes'] == 0
    assert value['periods'][0]['coverage']['observed_days'] == 2
    assert value['periods'][1]['coverage']['observed_days'] == 0


@pytest.fixture
def role_fixture(tmp_path, monkeypatch):
    root, out = tmp_path, tmp_path / 'artifacts/benchmark/b5/roles_v1'
    project = Path(__file__).parents[1]
    for n in b5.MODULES:
        target = root / 'src/geolife_inference' / n
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project / 'src/geolife_inference' / n, target)
    protocol = root / 'reports/cp1/role_protocol.md'
    protocol.parent.mkdir(parents=True)
    protocol.write_text('fixture protocol')
    cfg = Config()
    users = ['000','001']
    source = root / 'artifacts/benchmark/b4/run_v1'
    for d in ['real','real_parallel_inputs']:
        (source / d).mkdir(parents=True)
    cache_users, hashes, coverages, decisions = {}, {}, [], []
    total_points = 0
    for user in users:
        frames, events, raw_stays = [], [], []
        for i in range(3):
            start = pd.Timestamp('2008-01-01T15:00Z') + pd.Timedelta(days=i)
            times = pd.date_range(start, periods=7, freq='5min')
            frame = pd.DataFrame(dict(user_id=user, trajectory_id=str(i), timestamp=times,
                latitude=40., longitude=116., observation_segment=0))
            frames.append(frame)
            if user == '000':
                raw_stays.append(dict(user_id=user, trajectory_id=str(i), start_time=times[0], end_time=times[-1],
                    latitude=40., longitude=116., point_count=7, duration_minutes=30., stay_id=str(i)))
                for radius in b5.RADII:
                    events.append(dict(config_id=f'fixed_anchor_r{radius}_d10', trajectory_id=str(i),
                        start=times[0].timestamp(), end=times[-1].timestamp(), latitude=40., longitude=116., point_count=7))
        name = f'{user}_events.csv.gz'
        pd.DataFrame(events, columns=['config_id','trajectory_id','start','end','latitude','longitude','point_count']).to_csv(source/'real'/name,index=False)
        hashes[name] = b5.file_hash(source/'real'/name)
        cache = source/'real_parallel_inputs'/f'{user}.pkl.gz'
        with gzip.open(cache,'wb') as stream:
            for frame in frames:pickle.dump(frame,stream)
        cache_users[user] = dict(sha256=b5.file_hash(cache))
        full = pd.concat(frames,ignore_index=True)
        total_points += len(full)
        cov = observation_coverage(full,cfg)
        coverages.append(dict(user_id=user,processed_points=len(full),processed_trajectories=3,**cov))
        stays = pd.DataFrame(raw_stays,columns=['user_id','trajectory_id','start_time','end_time','latitude','longitude','point_count','duration_minutes','stay_id'])
        for method in MODEL_VERSIONS:
            grouped = group_locations(stays,cfg,method)
            locs = cluster_features(grouped,cov,cfg)
            for role in b5.ROLES:
                d = rank_role(locs,cov,cfg,role)
                c = d['candidate']
                decisions.append(dict(user_id=user,method=method,role=role,status=d['status'],reason=d['reason'],
                    input_context='has_clusters' if locs else 'no_stays',
                    **{k:c[k] if c else None for k in ['latitude','longitude','evidence_score','role_dwell_minutes','role_visit_days']}))
    def put(relative, data):
        path = root / relative
        path.parent.mkdir(parents=True,exist_ok=True)
        b5.write_json(path,data)
    prep = dict(status='completed',expected_users=users)
    put('artifacts/preprocessing/audit.json',prep)
    cleaned = root/'artifacts/preprocessing/cleaned_points.csv.gz';cleaned.write_bytes(b'fixture')
    fp = dict(bytes=cleaned.stat().st_size,mtime_ns=cleaned.stat().st_mtime_ns)
    put('artifacts/locations/audit.json',dict(status='completed'))
    inference = root/'artifacts/inference';inference.mkdir()
    pd.DataFrame(coverages).to_csv(inference/'coverage.csv',index=False)
    pd.DataFrame(decisions).to_csv(inference/'decisions.csv',index=False)
    put('artifacts/inference/audit.json',dict(status='completed',config=cfg.to_dict(),processed_users=2,
        input_fingerprints=dict(cleaned_gps=fp,tables={'artifacts/preprocessing/audit.json':b5.file_hash(root/'artifacts/preprocessing/audit.json')})))
    keys=['timezone','max_gap_minutes','night_start_hour','night_end_hour','work_start_hour','work_end_hour']
    put('artifacts/inference/coverage_audit.json',dict(status='completed',processed_users=2,
        coverage_sha256=b5.file_hash(inference/'coverage.csv'),key=dict(temporal_config={k:cfg.to_dict()[k] for k in keys})))
    put('artifacts/benchmark/b4/run_v1/real/audit.json',dict(status='completed',completed_users=users,
        baseline_parity_users=2,lock_hash='fixture',processed_points=total_points,processed_trajectories=6,output_hashes=hashes))
    put('artifacts/benchmark/b4/run_v1/real_parallel_inputs/audit.json',dict(status='completed',users=cache_users))
    monkeypatch.setattr(b5.jobs,'validate_lock',lambda *args: {})
    monkeypatch.setattr(b5.jobs,'ledger',lambda *args:0.)
    monkeypatch.setattr(b5,'_finder',Finder)
    return root,out


def test_all_stages_on_fixture_scope_parity_resume_and_source_integrity(role_fixture):
    root,out=role_fixture
    source=root/'artifacts/inference/decisions.csv';original=b5.file_hash(source)
    lock=b5.register(root,out)
    assert lock['users']==['000','001']
    main=b5.run_main(root,out)
    assert main['baseline_parity_users']==2
    saved=b5.file_hash(out/'main/audit.json')
    b5.run_main(root,out)
    assert b5.file_hash(out/'main/audit.json')==saved
    b5.summarize(root,out,include_ablations=False)
    context=b5.run_context(root,out)
    assert context['processed_points']==42
    assert context['affected_users']==[]
    b5.run_ablations(root,out)
    summary=b5.summarize(root,out)
    assert summary['decision_rows']==2*2*2*2*2*6
    comparisons=pd.read_csv(out/'summary/comparisons.csv')
    temporal=comparisons[comparisons.comparison.eq('temporal')]
    assert temporal.assessment.eq('insufficient_cohort').all()
    tz=comparisons[comparisons.comparison.eq('timezone')]
    assert tz.prediction_rate_delta_pp.eq(0).all()
    assert tz.changed_over_200m.eq(0).all()
    plots=b5.render(root,out)
    assert len(plots['output_hashes'])==5
    for name,checksum in plots['output_hashes'].items():
        assert b5.file_hash(out/'plots'/name)==checksum
    print('B5 test plot directory:',out/'plots')
    assert b5.file_hash(source)==original
    # No final corpus or existing pipeline artifacts are created/rewritten.
    assert not (root/'artifacts/benchmark/b2/final_v1').exists()
    (out/'main/000_decisions.csv').write_text('tampered')
    with pytest.raises(ValueError,match='đã đổi'):
        b5.run_main(root,out)


def test_temporal_grouping_never_reuses_whole_timeline_clusters(role_fixture, monkeypatch):
    root,out=role_fixture
    b5.register(root,out);b5.run_main(root,out);b5.run_context(root,out)
    calls=[]
    original=b5._decisions
    def record(stays,coverage,config,radius,method,scenario,**kwargs):
        if scenario.startswith('period_'):
            calls.append((scenario,len(stays)))
        return original(stays,coverage,config,radius,method,scenario,**kwargs)
    monkeypatch.setattr(b5,'_decisions',record)
    b5.run_ablations(root,out)
    assert calls
    assert all(count==0 for scenario,count in calls if scenario=='period_2')


def test_context_uses_explicit_origin_even_if_trajectories_arrive_out_of_order():
    cfg=Config()
    def frame(day):
        return pd.DataFrame(dict(user_id='000',trajectory_id=str(day),
            timestamp=pd.date_range(pd.Timestamp('2008-01-01T15:00Z')+pd.Timedelta(days=day),periods=2,freq='5min'),
            latitude=40.,longitude=116.,observation_segment=0))
    origin=datetime(2007,12,31,16,tzinfo=timezone.utc)
    c=b5._context([frame(30),frame(0)],cfg,Finder(),period_origin=origin)
    assert c['periods'][0]['coverage']['observed_days']==1
    assert c['periods'][1]['coverage']['observed_days']==1


def test_notebook_cells_are_valid_and_all_plot_files_are_displayed():
    notebook=Path(__file__).parents[1]/'notebooks/10_cp1_b5_roles.ipynb'
    nb=json.loads(notebook.read_text(encoding='utf-8'))
    for cell in nb['cells']:
        if cell['cell_type']=='code':
            compile(''.join(cell['source']),str(notebook),'exec')
    display_cell=''.join(nb['cells'][12]['source'])
    assert 'display(Image(filename=' in display_cell
    assert "['output_hashes']" in display_cell


def test_period_boundary_events_do_not_leak_future_fixes():
    start,end=pd.Timestamp('2008-01-01T00:00Z'),pd.Timestamp('2008-01-29T00:00Z')
    stays=pd.DataFrame(dict(
        start_time=pd.to_datetime(['2007-12-31T23:55Z','2008-01-02T00:00Z','2008-01-28T23:55Z','2008-01-29T01:00Z']),
        end_time=pd.to_datetime(['2008-01-01T00:05Z','2008-01-02T01:00Z','2008-01-29T00:05Z','2008-01-29T02:00Z']),
        marker=['past_boundary','inside','future_boundary','outside']))
    selected,excluded=b5.period_stays(stays,start,end)
    assert selected.marker.tolist()==['inside']
    assert excluded==2


def test_single_writer_prevents_concurrent_stages(role_fixture):
    root,out=role_fixture
    b5.register(root,out)
    with b5._writer_lease(out):
        with pytest.raises(RuntimeError,match='job B5 khác'):
            b5.run_main(root,out)
    assert not (out/'main/audit.json').exists()


def test_interrupted_job_resumes_without_rewriting_completed_user(role_fixture, monkeypatch):
    root,out=role_fixture
    b5.register(root,out)
    original=b5._checkpoint
    def interrupt_after_checkpoint(directory,audit,budget,user,names):
        original(directory,audit,budget,user,names)
        if user=='000':
            raise KeyboardInterrupt()
    monkeypatch.setattr(b5,'_checkpoint',interrupt_after_checkpoint)
    with pytest.raises(KeyboardInterrupt):
        b5.run_main(root,out)
    assert b5._read(out/'main/audit.json')['status']=='incomplete'
    checksum=b5.file_hash(out/'main/000_decisions.csv')
    monkeypatch.setattr(b5,'_checkpoint',original)
    result=b5.run_main(root,out)
    assert result['completed_users']==['000','001']
    assert b5.file_hash(out/'main/000_decisions.csv')==checksum
    assert [a['status'] for a in result['attempts']]==['incomplete','completed']
