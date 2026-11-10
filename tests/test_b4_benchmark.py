"""B4 tests use constructed observations only, never the GeoLife dataset."""
import itertools

import numpy as np
import pandas as pd
import pytest
from sklearn.cluster import DBSCAN

from geolife_inference.benchmark_detectors import DetectorConfig,detect,configurations,METHODS
from geolife_inference.benchmark_evaluation import (match_events,accumulate,empty_accumulator,
    finalize,cluster_bootstrap,motor_exposure,load_label_masks)
from geolife_inference.geo import haversine_m,representative
from geolife_inference.config import Config
from geolife_inference.stays import detect_stays


def _brute(t,xy,method,radius,dwell):
    events=[];first=0
    while first<len(t):
        last=first;center=xy[first]
        for end in range(first+1,len(t)):
            subset=xy[first:end+1]
            if method=='median_updated':c=np.array(representative(subset))
            else:
                distance=haversine_m(subset[:,0,None],subset[:,1,None],subset[None,:,0],subset[None,:,1])
                scores=distance.sum(axis=1) if method=='medoid_updated' else -(distance<=radius).sum(axis=1)
                c=subset[int(np.argmin(scores))]
            if np.any(haversine_m(c[0],c[1],subset[:,0],subset[:,1])>radius):break
            last=end;center=c
        if last>first and t[last]-t[first]>=dwell*60:
            events.append(dict(start=float(t[first]),end=float(t[last]),latitude=float(center[0]),
                longitude=float(center[1]),point_count=last-first+1))
        first=last+1
    return events


def _equal(a,b):
    assert len(a)==len(b)
    for x,y in zip(a,b):
        for key in ['start','end','point_count']:assert x[key]==y[key]
        assert haversine_m(x['latitude'],x['longitude'],y['latitude'],y['longitude'])<1e-6


def test_common_and_private_grids():
    main=configurations(False);all_configs=configurations(True)
    assert len(main)==40 and len(all_configs)==48
    assert len({c.config_id for c in all_configs})==48
    assert all(sum(c.method==m for c in main)==8 for m in METHODS)
    assert {c.dwell_minutes for c in main}=={10,20}


@pytest.mark.parametrize('method',['median_updated','medoid_updated','max_neighbor_updated'])
def test_optimized_center_scans_match_brute(method):
    for seed in range(20):
        rng=np.random.default_rng(seed)
        xy=np.array([39.,116.])+rng.normal(size=(35,2))*.0004
        t=np.arange(len(xy))*30.
        cfg=DetectorConfig(method,80,1)
        _equal(detect(t,xy,np.zeros(len(t)),cfg),_brute(t,xy,method,80,1))


@pytest.mark.parametrize('radius',[50,100,150,200])
@pytest.mark.parametrize('dwell',[10,20])
def test_fixed_anchor_matches_production(radius,dwell):
    rng=np.random.default_rng(9)
    xy=np.repeat([[39.,116.],[39.01,116.01],[39.,116.]],100,axis=0)+rng.normal(0,.0001,(300,2))
    t=np.arange(len(xy))*30.+1200000000
    t[150:]+=900
    seg=np.zeros(len(t),int);seg[230:]=1
    frame=pd.DataFrame(dict(user_id='000',trajectory_id='t',latitude=xy[:,0],longitude=xy[:,1],
        timestamp=pd.to_datetime(t,unit='s',utc=True),observation_segment=seg))
    expected,_=detect_stays(frame,Config(distance_m=radius,min_stay_minutes=dwell))
    result=detect(t,xy,seg,DetectorConfig('fixed_anchor',radius,dwell))
    assert len(result)==len(expected)
    for x,y in zip(result,expected.itertuples()):
        assert x['start']==y.start_time.timestamp() and x['end']==y.end_time.timestamp()
        assert x['point_count']==y.point_count
        assert haversine_m(x['latitude'],x['longitude'],y.latitude,y.longitude)<1e-6


@pytest.mark.parametrize('eps_time',[60,180,300])
@pytest.mark.parametrize('min_points',[3,5,10])
def test_stdbscan_matches_precomputed_neighborhood_reference(eps_time,min_points):
    rng=np.random.default_rng(6)
    xy=np.array([39.,116.])+rng.normal(size=(80,2))*.0006
    t=np.arange(len(xy))*30.
    d=haversine_m(xy[:,0,None],xy[:,1,None],xy[None,:,0],xy[None,:,1])
    adjacency=(d<=75)&(np.abs(t[:,None]-t[None,:])<=eps_time)
    labels=DBSCAN(eps=1,min_samples=min_points,metric='precomputed').fit_predict(np.where(adjacency,0.,2.))
    expected=[]
    for label in sorted(set(labels)-{-1}):
        indices=np.flatnonzero(labels==label)
        if t[indices[-1]]-t[indices[0]]<60:continue
        lat,lon=representative(xy[indices])
        expected.append(dict(start=t[indices[0]],end=t[indices[-1]],latitude=lat,longitude=lon,point_count=len(indices)))
    _equal(detect(t,xy,np.zeros(len(t)),DetectorConfig('st_dbscan',75,1,eps_time,min_points)),expected)


@pytest.mark.parametrize('method',METHODS)
def test_segments_and_empty_inputs(method):
    cfg=DetectorConfig(method,100,10)
    assert detect([],np.empty((0,2)),[],cfg)==[]
    xy=np.tile([39.,116.],(22,1));t=np.arange(22)*60.
    seg=np.r_[np.zeros(11),np.ones(11)]
    events=detect(t,xy,seg,cfg)
    assert [(e['start'],e['end']) for e in events]==[(0.,600.),(660.,1260.)]
    assert all(e['point_count']==11 for e in events)


def _e(start,end,lat=39.,lon=116.):
    return dict(start=start,end=end,latitude=lat,longitude=lon)


def test_matching_duplicate_predictions_split_merge_and_ties():
    truth=[_e(0,1200)]
    pred=[_e(0,600),_e(600,1200)]
    matches,split,merge=match_events(truth,pred)
    assert [(x[0],x[1]) for x in matches]==[(0,0)]
    assert split==1 and merge==0
    matches,split,merge=match_events(pred,truth)
    assert len(matches)==1 and split==0 and merge==1
    assert not match_events(truth,[_e(0,1200,lat=40.)])[0]


def test_matching_global_optimum_not_greedy():
    truth=[_e(0,1200),_e(300,1500)]
    pred=[_e(100,1400),_e(0,900)]
    matches,_,_=match_events(truth,pred)
    assert {(i,j) for i,j,_,_ in matches}=={(0,1),(1,0)}


def test_unobserved_event_is_fn_and_negative_f1_is_na():
    record=dict(events=[dict(start_epoch_seconds=0,end_epoch_seconds=1200,latitude=39.,longitude=116.)],
        diagnostics=dict(latent_moving_seconds=600))
    state=empty_accumulator();accumulate(state,record,[],np.empty(0));out=finalize(state)
    assert out['fn']==1 and out['f1']==0 and out['recall']==0 and np.isnan(out['precision'])
    record['events']=[];state=empty_accumulator();accumulate(state,record,[_e(0,600)],np.arange(10))
    out=finalize(state);assert np.isnan(out['f1']) and out['fp_per_hour']==6


def test_group_bootstrap_replays_and_respects_identical_groups():
    a=cluster_bootstrap([1.,1.,0.],['a','a','b'],repetitions=100)
    assert a==cluster_bootstrap([1.,1.,0.],['a','a','b'],repetitions=100)
    assert a[2]==2
    assert np.isnan(cluster_bootstrap([1,0],['a','a'])[0])


def test_contradictory_labels_are_excluded(tmp_path):
    folder=tmp_path/'data/Geolife Trajectories 1.3/Data/000';folder.mkdir(parents=True)
    (folder/'labels.txt').write_text('Start Time\tEnd Time\tTransportation Mode\n'
        '2020/01/01 00:00:00\t2020/01/01 00:20:00\tcar\n'
        '2020/01/01 00:10:00\t2020/01/01 00:30:00\twalk\n')
    masks=load_label_masks(tmp_path)['000'];assert len(masks)==2
    start=pd.Timestamp('2020-01-01',tz='UTC').timestamp()
    exposure=motor_exposure([_e(start,start+1800)],masks)
    assert exposure['labeled_stay_seconds']==1200 and exposure['motor_stay_seconds']==600
