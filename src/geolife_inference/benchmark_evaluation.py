"""Shared event scoring and uncertainty for all B4 methods."""
from __future__ import annotations

import json
from collections import defaultdict, Counter

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from .geo import haversine_m


def events_from_truth(record):
    return [dict(start=e['start_epoch_seconds'],end=e['end_epoch_seconds'],
        latitude=e['latitude'],longitude=e['longitude']) for e in record['events']]


def overlap_arrays(truth, predictions):
    iou = np.zeros((len(truth),len(predictions)))
    distance = np.zeros_like(iou)
    overlap = np.zeros_like(iou)
    for i, x in enumerate(truth):
        for j, y in enumerate(predictions):
            shared = max(0.,min(x['end'],y['end'])-max(x['start'],y['start']))
            overlap[i,j] = shared
            iou[i,j] = shared/(max(x['end'],y['end'])-min(x['start'],y['start'])) if shared else 0.
            distance[i,j] = haversine_m(x['latitude'],x['longitude'],y['latitude'],y['longitude'])
    return iou, distance, overlap


def _best_sum(weights):
    if not weights.size:
        return 0.
    a,b = linear_sum_assignment(weights, maximize=True)
    return float(weights[a,b].sum())


def match_events(truth, predictions):
    """Max total IoU; ties lexicographic by sorted truth then prediction index.

    Dummy unmatched columns permit FN. Ties within 1e-12 IoU sum are numerical
    ties. No spatial/radius-specific matching advantage is given to any method.
    """
    iou, distance, overlap = overlap_arrays(truth,predictions)
    valid = (iou>=.5)&(distance<=100.)
    weights = np.where(valid,iou,0.)
    remaining = list(range(len(predictions)))
    target = _best_sum(weights)
    matches = []
    for i in range(len(truth)):
        options = [j for j in remaining if valid[i,j]] + [None]
        for j in options:
            columns = [k for k in remaining if k!=j]
            gain = 0. if j is None else float(weights[i,j])
            value = gain+_best_sum(weights[i+1:,columns])
            if abs(value-target)<=1e-12:
                if j is not None:
                    matches.append((i,j,float(iou[i,j]),float(distance[i,j])))
                    remaining.remove(j)
                target -= gain
                break
        else:
            raise ArithmeticError('Unable to resolve event assignment')
    graph = (overlap>0)&(distance<=100.)
    return matches, int((graph.sum(axis=1)>=2).sum()), int((graph.sum(axis=0)>=2).sum())


def empty_accumulator():
    return dict(cases=0,truth=0,predictions=0,tp=0,fp=0,fn=0,split_events=0,merge_events=0,
        latent_moving_hours=0.,observed_hours=0.,start_errors=[],end_errors=[],center_errors=[],ious=[])


def accumulate(state, record, predictions, t):
    truth = events_from_truth(record)
    matches, split, merge = match_events(truth,predictions)
    state['cases']+=1;state['truth']+=len(truth);state['predictions']+=len(predictions)
    state['tp']+=len(matches);state['fp']+=len(predictions)-len(matches);state['fn']+=len(truth)-len(matches)
    state['split_events']+=split;state['merge_events']+=merge
    state['latent_moving_hours']+=record['diagnostics']['latent_moving_seconds']/3600
    dt = np.diff(t)
    state['observed_hours']+=float(dt[(dt>0)&(dt<=300)].sum())/3600
    for i,j,iou,d in matches:
        state['start_errors'].append(abs(predictions[j]['start']-truth[i]['start']))
        state['end_errors'].append(abs(predictions[j]['end']-truth[i]['end']))
        state['center_errors'].append(d);state['ious'].append(iou)


def finalize(state):
    out = {k:v for k,v in state.items() if not isinstance(v,list)}
    nt,npred,tp = out['truth'],out['predictions'],out['tp']
    out['precision'] = tp/npred if npred else np.nan
    out['recall'] = tp/nt if nt else np.nan
    out['f1'] = 2*tp/(nt+npred) if nt else np.nan  # negative-only: FP/h, never an F1
    out['split_rate'] = out['split_events']/nt if nt else np.nan
    out['merge_rate'] = out['merge_events']/npred if npred else np.nan
    out['fp_per_hour'] = out['fp']/out['latent_moving_hours'] if out['latent_moving_hours'] else np.nan
    out['matched_fraction'] = out['recall']
    for name,field in [('start_error_seconds','start_errors'),('end_error_seconds','end_errors'),
                       ('center_error_m','center_errors'),('temporal_iou','ious')]:
        values = state[field]
        out[name+'_median'] = float(np.median(values)) if values else np.nan
        out[name+'_p95'] = float(np.quantile(values,.95)) if values else np.nan
    return out


METRICS = ['precision','recall','f1','split_rate','merge_rate','fp_per_hour','matched_fraction',
    'start_error_seconds_median','end_error_seconds_median','center_error_m_median',
    'start_error_seconds_p95','end_error_seconds_p95','center_error_m_p95','temporal_iou_median']


def cluster_bootstrap(values, groups, repetitions=1000, seed=20261105, coverage=.95):
    values = np.asarray(values,float);groups = np.asarray(groups,str)
    valid = np.isfinite(values);values=values[valid];groups=groups[valid]
    if not len(values):return np.nan,np.nan,0
    unique,inverse = np.unique(groups,return_inverse=True)
    if len(unique)<2:return np.nan,np.nan,len(unique)
    sums=np.bincount(inverse,weights=values);counts=np.bincount(inverse)
    draws=np.random.default_rng(seed).integers(0,len(unique),size=(repetitions,len(unique)))
    means=sums[draws].sum(axis=1)/counts[draws].sum(axis=1)
    low=(1-coverage)/2
    return float(np.quantile(means,low)),float(np.quantile(means,1-low)),len(unique)


def summarize_users(table):
    rows=[]
    for (config,cell),g in table.groupby(['config_id','cell_id'],sort=True):
        row=g.iloc[0][['config_id','method','radius_m','dwell_minutes','eps_time_seconds','min_points',
                      'cell_id','group','duration_group','rms','family','modifier']].to_dict()
        for optional in ['negative_kind','separation_m','connector_seconds']:
            if optional in g:row[optional]=g[optional].iloc[0]
        row.update(users=len(g),independent_groups=g.independence_group.nunique(),
            truth=int(g.truth.sum()),predictions=int(g.predictions.sum()),
            latent_moving_hours=float(g.latent_moving_hours.sum()),cases=int(g.cases.sum()))
        for metric in METRICS:
            values=g[metric]
            row[metric]=(float(values.median()) if metric.endswith('_median') else float(values.mean())) if values.notna().any() else np.nan
            row[metric+'_users']=int(values.notna().sum())
        lo,hi,n=cluster_bootstrap(g.f1,g.independence_group)
        row.update(f1_ci_low=lo,f1_ci_high=hi,f1_ci_groups=n)
        rows.append(row)
    return pd.DataFrame(rows)


def temporal_stability(left, right):
    matches,_,_=match_events(left,right)
    union=len(left)+len(right)-len(matches)
    return dict(jaccard=len(matches)/union if union else np.nan,
        matched_temporal_iou=float(np.median([x[2] for x in matches])) if matches else np.nan,
        matched=len(matches),n_left=len(left),n_right=len(right))


def load_label_masks(root):
    """Sweep line; contradictory mode overlaps excluded, same-mode union retained."""
    result={}
    for path in sorted((root/'data/Geolife Trajectories 1.3/Data').glob('*/labels.txt')):
        df=pd.read_csv(path,sep='\t');changes=defaultdict(Counter)
        for a,b,mode in df.itertuples(index=False,name=None):
            a=pd.to_datetime(a,utc=True,errors='coerce');b=pd.to_datetime(b,utc=True,errors='coerce')
            if pd.isna(a) or pd.isna(b) or b<=a:continue
            key=str(mode).strip().lower()
            changes[a.value/1e9][key]+=1;changes[b.value/1e9][key]-=1
        active=Counter();intervals=[];edges=sorted(changes)
        for i,a in enumerate(edges[:-1]):
            active.update(changes[a]);modes=[k for k,n in active.items() if n>0]
            b=edges[i+1]
            if len(modes)==1:
                if intervals and intervals[-1][1]==a and intervals[-1][2]==modes[0]:
                    intervals[-1]=(intervals[-1][0],b,modes[0])
                else:intervals.append((a,b,modes[0]))
        result[path.parent.name]=intervals
    return result


def motor_exposure(events, masks):
    denom=motor=0.
    per_mode=defaultdict(float)
    motor_modes={'car','taxi','bus','train','subway'}
    for e in events:
        for a,b,mode in masks:
            if a>=e['end']:break
            if b<=e['start']:continue
            length=max(0.,min(b,e['end'])-max(a,e['start']))
            denom+=length
            per_mode[mode]+=length
            if mode in motor_modes:motor+=length
    return dict(labeled_stay_seconds=denom,motor_stay_seconds=motor,r_motor=motor/denom if denom else np.nan,
        mode_exposure_seconds=json.dumps(dict(sorted(per_mode.items()))))


