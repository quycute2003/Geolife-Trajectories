"""Predeclared B4 gates; selection and confirmation use identical thresholds."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .benchmark_detectors import BASELINE_ID,DetectorConfig,METHODS
from .benchmark_evaluation import cluster_bootstrap
from .benchmark_jobs import readj,validate_lock,JobBudget,ledger,validate_winner
from .benchmark_synthetic import write_json,file_hash,digest


def _finite(value):
    return bool(np.isfinite(value))


def _gate_a(table,baseline,candidate,ids):
    details=[];passed=True
    for cell in ids:
        left=table[(table.config_id==baseline)&(table.cell_id==cell)]
        right=table[(table.config_id==candidate)&(table.cell_id==cell)]
        g=left[['user_id','f1','independence_group']].merge(right[['user_id','f1']],on='user_id',suffixes=('_b','_c'),validate='one_to_one')
        delta=g.f1_c-g.f1_b
        lo,hi,groups=cluster_bootstrap(delta,g.independence_group,repetitions=5000,coverage=.975)
        change=float(delta.mean()) if len(delta) else np.nan
        ok=len(g)>=10 and groups>=10 and _finite(change) and change>=.03-1e-12 and _finite(lo) and lo>0
        details.append(dict(cell_id=cell,delta_f1=change,ci_low=lo,ci_high=hi,users=len(g),groups=groups,passed=ok))
        passed &= ok
    return bool(passed),details


def _gate_b(macro,candidate,baseline,source):
    failures=[];na_notes=[]
    b=macro[macro.config_id==baseline].set_index('cell_id')
    c=macro[macro.config_id==candidate].set_index('cell_id')
    if set(b.index)!=set(c.index):return False,['missing cells'],[]
    for cell,x in b.iterrows():
        y=c.loc[cell]
        if min(x['users'],y['users'],x.independent_groups,y.independent_groups)<10:
            failures.append(f'{cell}: insufficient source quota');continue
        if x['group']=='negative':
            if not _finite(y.fp_per_hour) or y.fp_per_hour-x.fp_per_hour>.05+1e-12:
                failures.append(f'{cell}: FP/hour increase >0.05')
            if x.get('negative_kind')=='pure_move':
                if y.fp_per_hour>.1+1e-12 or y.latent_moving_hours<10:
                    failures.append(f'{cell}: pure moving guardrail')
            continue
        for metric in ['precision','recall','f1']:
            xv,yv=x[metric],y[metric]
            if not _finite(xv) or not _finite(yv):
                if metric=='precision' and x.predictions==0 and y.predictions==0:
                    na_notes.append(f'{cell}: both have no predictions; compare recall/F1/FN')
                elif metric=='precision' and x.predictions==0 and y.predictions>0:
                    na_notes.append(f'{cell}: baseline precision NA; compare recall/F1 and FP')
                else:failures.append(f'{cell}: {metric} unconfirmed')
            elif yv<xv-.02-1e-12:failures.append(f'{cell}: {metric} decrease >0.02')
        for metric,limit in [('start_error_seconds_median',60),('end_error_seconds_median',60),('center_error_m_median',10)]:
            if _finite(x[metric]) and _finite(y[metric]):
                if y[metric]-x[metric]>limit+1e-12:failures.append(f'{cell}: {metric} worsened')
            else:na_notes.append(f'{cell}: {metric} NA, no matched-event improvement claimed')
        for metric in ['split_rate','merge_rate']:
            if _finite(x[metric]) and _finite(y[metric]):
                if y[metric]-x[metric]>.02+1e-12:failures.append(f'{cell}: {metric} increase >0.02')
            elif metric=='merge_rate' and x.predictions==0 and y.predictions==0:
                na_notes.append(f'{cell}: merge rate NA for both; zero predictions')
            else:na_notes.append(f'{cell}: {metric} NA; see event counts')
    return not failures,failures,na_notes


def _gate_c(real,edges,candidate,method,cohort):
    failures=[];details={}
    b=real[(real.config_id==BASELINE_ID)&real.user_id.isin(cohort)]
    c=real[(real.config_id==candidate)&real.user_id.isin(cohort)]
    joined=b[['user_id','labeled_stay_seconds','r_motor']].merge(
        c[['user_id','labeled_stay_seconds','r_motor']],on='user_id',suffixes=('_b','_c'),validate='one_to_one')
    common=joined[(joined.labeled_stay_seconds_b>0)&(joined.labeled_stay_seconds_c>0)]
    details['motor_users']=len(common)
    details['motor_baseline_only_users']=joined.loc[(joined.labeled_stay_seconds_b>0)&(joined.labeled_stay_seconds_c<=0),'user_id'].tolist()
    if not len(common):failures.append('motorized check: no common positive denominator')
    else:
        rb=float(common.r_motor_b.mean());rc=float(common.r_motor_c.mean())
        details.update(r_motor_baseline=rb,r_motor_candidate=rc)
        if rc>.01+1e-12 or rc-rb>.001+1e-12:failures.append('motorized overlap guardrail')
    required=['r100_to_50_d10','r100_to_200_d10']
    common_stability=set(cohort)
    for edge in required:
        for name in ['fixed_anchor',method]:
            eligible=edges[(edges.method==name)&(edges.edge==edge)&(edges.n_left>=5)&(edges.n_right>=5)]
            common_stability &= set(eligible.user_id)
    details['stability_common_user_ids']=sorted(common_stability)
    for edge in required:
        x=edges[(edges.method=='fixed_anchor')&(edges.edge==edge)&edges.user_id.isin(cohort)]
        y=edges[(edges.method==method)&(edges.edge==edge)&edges.user_id.isin(cohort)]
        z=x.merge(y,on='user_id',suffixes=('_b','_c'),validate='one_to_one')
        z=z[(z.n_left_b>=5)&(z.n_right_b>=5)&(z.n_left_c>=5)&(z.n_right_c>=5)]
        z=z[z.user_id.isin(common_stability)]
        info=dict(users=len(z))
        if len(z)<15:failures.append(edge+': fewer than 15 common users')
        else:
            jb=float(z.jaccard_b.median());jc=float(z.jaccard_c.median())
            tb=float(((z.count_relative_change_b>.5)|(z.dwell_relative_change_b>.5)).mean())
            tc=float(((z.count_relative_change_c>.5)|(z.dwell_relative_change_c>.5)).mean())
            info.update(jaccard_baseline=jb,jaccard_candidate=jc,tail_baseline=tb,tail_candidate=tc)
            if not _finite(jc) or jc<jb-.05-1e-12:failures.append(edge+': stability Jaccard worsened')
            if tc-tb>.05+1e-12:failures.append(edge+': unstable-user fraction worsened')
        details[edge]=info
    return not failures,failures,details


def decide(root,out,split='selection'):
    root,out=Path(root),Path(out);lock=validate_lock(root,out)
    summary_dir=out/('summary_'+split)
    for path in [summary_dir/'audit.json',out/'real/audit.json']:
        if readj(path)['status']!='completed':raise ValueError('Required B4 job incomplete; keep baseline')
    directory=out/('decision_'+split)
    if directory.exists():raise FileExistsError(directory)
    directory.mkdir();budget=JobBudget(ledger(root,out))
    try:
        table=pd.read_csv(summary_dir/'per_user.csv.gz',dtype={'user_id':str,'independence_group':str})
        for base in [summary_dir,out/'real']:
            for n,h in readj(base/'audit.json')['output_hashes'].items():
                if file_hash(base/n)!=h:raise ValueError(f'Evaluation output changed: {base/n}')
        macro=pd.read_csv(summary_dir/'macro_by_cell.csv')
        prep=readj(root/'artifacts/benchmark/b2/prepared_v1/protocol.json')
        cohort=[u for u,s in prep['split'].items() if s==split]
        real=pd.concat([pd.read_csv(out/'real'/f'{u}_metrics.csv',dtype={'user_id':str}) for u in readj(out/'real/audit.json')['completed_users']],ignore_index=True)
        edges=pd.concat([pd.read_csv(out/'real'/f'{u}_edges.csv',dtype={'user_id':str}) for u in readj(out/'real/audit.json')['completed_users']],ignore_index=True)
        ids=[]
        for d,r,f in [(1,15,'drift'),(2,30,'outlier')]:
            found=macro[(macro['group']=='main')&(macro.duration_group==d)&(macro.rms==r)&(macro.family==f)].cell_id.unique()
            if len(found)!=1:raise ValueError('Gate cell missing or ambiguous')
            ids.append(found[0])
        records=[r for r in lock['main_configs'] if r['dwell_minutes']==10 and r['config_id']!=BASELINE_ID]
        if split=='final':
            winner=validate_winner(out,lock)
            if winner['status']!='selected' or winner['lock_hash']!=lock['lock_hash']:raise ValueError('No selected winner')
            records=[r for r in records if r['config_id']==winner['config_id']]
        results=[];real_audit=readj(out/'real/audit.json')
        for cfg in records:
            budget.check();cid=cfg['config_id']
            ga,ad=_gate_a(table,BASELINE_ID,cid,ids)
            gb,bf,bn=_gate_b(macro,cid,BASELINE_ID,table)
            gc,cf,cd=_gate_c(real,edges,cid,cfg['method'],cohort)
            rb=real[(real.config_id==BASELINE_ID)&real.user_id.isin(cohort)].detector_seconds.sum()
            rc=real[(real.config_id==cid)&real.user_id.isin(cohort)].detector_seconds.sum()
            ratio=float(rc/rb) if rb>0 else np.inf
            peak=real_audit.get('config_process_ws_peak',{}).get(cid,np.inf)
            gd=ratio<=1.5 and peak<=real_audit['ram_cap_bytes'] and budget.used<=86400
            results.append(dict(config_id=cid,method=cfg['method'],radius_m=cfg['radius_m'],
                a=bool(ga),b=bool(gb),c=bool(gc),d=bool(gd),passed=bool(ga and gb and gc and gd),
                a_details=json.dumps(ad,allow_nan=True),b_failures=json.dumps(bf),b_na_notes=json.dumps(bn),
                c_failures=json.dumps(cf),c_details=json.dumps(cd,allow_nan=True),runtime_ratio=ratio,
                candidate_detector_seconds=float(rc),baseline_detector_seconds=float(rb)))
        table_result=pd.DataFrame(results);table_result.to_csv(directory/'gates.csv',index=False)
        passing=[r for r in results if r['passed']]
        passing.sort(key=lambda r:(METHODS.index(r['method']),abs(r['radius_m']-100),r['candidate_detector_seconds'],r['config_id']))
        mode=prep['mode']
        if mode=='descriptive':passing=[]
        chosen=passing[0]['config_id'] if passing else None
        result=dict(status=('selected' if chosen else 'keep_baseline') if split=='selection'
            else ('confirmed' if chosen else 'keep_baseline'),config_id=chosen or BASELINE_ID,
            lock_hash=lock['lock_hash'],mode=mode,gate_cells=ids,
            note='No final opened unless selected; no second candidate after failed confirmation',
            gates_sha256=file_hash(directory/'gates.csv'))
        write_json(directory/'winner.json',result)
        budget.check();write_json(directory/'audit.json',dict(status='completed',lock_hash=lock['lock_hash'],
            winner_sha256=file_hash(directory/'winner.json'),**budget.summary()))
        return table_result,result
    except BaseException as error:
        write_json(directory/'audit.json',dict(status='failed',error=str(error),lock_hash=lock['lock_hash'],**budget.summary()));raise


def generate_final(root,out):
    """Explicit final action, gated by a single locked selection winner."""
    root,out=Path(root),Path(out);lock=validate_lock(root,out)
    winner=validate_winner(out,lock)
    if winner['status']!='selected' or winner['lock_hash']!=lock['lock_hash']:
        raise ValueError('No selected candidate: final must remain closed')
    from .benchmark_synthetic import generate,Budget,memory_usage,available_memory
    destination=root/'artifacts/benchmark/b2/final_v1'
    result=generate(root/'artifacts/benchmark/b2/prepared_v1',destination,'final',
        Budget(ledger(root,out),memory_usage,available_memory))
    # Charge final generation, including failed attempts (generator writes its own audit).
    return result
