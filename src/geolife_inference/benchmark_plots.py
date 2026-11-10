"""B4 figures: shared config panels, never a single pooled scenario F1."""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .benchmark_detectors import METHODS,RADII,DURATIONS,DetectorConfig
from .benchmark_jobs import readj,validate_lock,JobBudget,ledger
from .benchmark_synthetic import write_json,file_hash

LABELS={'fixed_anchor':'Fixed anchor','median_updated':'Median updated','medoid_updated':'Medoid updated',
        'max_neighbor_updated':'Max neighbor','st_dbscan':'ST-DBSCAN'}
COLORS=dict(zip(METHODS,plt.get_cmap('tab10').colors[:5]))
DWELL_LABELS=['3–<10 min','10–<20 min','20–60 min','>60 min']


def _curve(ax,g,method,x,metric='f1',ci=True):
    if not len(g):raise ValueError(f'Missing plot data: {method}')
    g=g.sort_values(x)
    y=g[metric].to_numpy(float)
    if ci:
        lo=g.f1_ci_low.to_numpy(float);hi=g.f1_ci_high.to_numpy(float)
        errors=np.stack([np.maximum(0,y-lo),np.maximum(0,hi-y)])
        ax.errorbar(g[x],y,yerr=errors,label=LABELS[method],color=COLORS[method],marker='o',capsize=2,lw=1)
    else:ax.plot(g[x],y,label=LABELS[method],color=COLORS[method],marker='o',lw=1)


def render(root,out):
    root,out=Path(root),Path(out);lock=validate_lock(root,out)
    summary=out/'summary_selection'
    if readj(summary/'audit.json')['status']!='completed':raise ValueError('No completed selection summary')
    for n,h in readj(summary/'audit.json')['output_hashes'].items():
        if file_hash(summary/n)!=h:raise ValueError(f'Summary changed: {n}')
    destination=out/'plots_selection'
    if destination.exists():raise FileExistsError(destination)
    destination.mkdir();budget=JobBudget(ledger(root,out));paths=[]
    data=pd.read_csv(summary/'macro_by_cell.csv')
    def save(fig,name):
        fig.savefig(destination/name,dpi=150,bbox_inches='tight');plt.close(fig);paths.append(name);budget.check()
    try:
        for dwell in DURATIONS:
            for radius in RADII:
                budget.check()
                ids=[DetectorConfig(m,radius,dwell).config_id for m in METHODS]
                sub=data[data.config_id.isin(ids)]
                if sub.config_id.nunique()!=5:raise ValueError('Incomplete five-method comparison')
                fig,axes=plt.subplots(4,3,figsize=(15,14),sharey=True)
                for d in range(4):
                    for col,family in enumerate(['gaussian','drift','outlier']):
                        ax=axes[d,col]
                        part=sub[sub['group'].isin(['main','stress'])&(sub.duration_group==d)&(sub.family==family)]
                        for method in METHODS:_curve(ax,part[part.method==method],method,'rms')
                        ax.set(title=f'{DWELL_LABELS[d]} | {family}',ylim=(-.03,1.03),
                            xlabel='Noise RMS (m)',ylabel='Event F1 (user macro)')
                        ax.set_xticks(sorted(part.rms.unique()));ax.grid(alpha=.2)
                handles,labels=axes[0,0].get_legend_handles_labels()
                fig.legend(handles,labels,loc='lower center',ncol=5,bbox_to_anchor=(.5,0))
                fig.suptitle(f'Selection, exploratory | radius={radius} m, min dwell={dwell} min\n95% source-group bootstrap intervals')
                fig.tight_layout(rect=(0,.025,1,.95));save(fig,f'config_r{radius}_d{dwell}_f1.png')
                fig,axes=plt.subplots(3,2,figsize=(15,12))
                for d,ax in enumerate(axes.flat[:4]):
                    part=sub[(sub['group']=='dropout')&(sub.duration_group==d)].copy()
                    order={'drop_empirical':0,'drop25':1,'drop50':2};part['x']=part.modifier.map(order)
                    for method in METHODS:_curve(ax,part[part.method==method],method,'x')
                    ax.set(title='Dropout | '+DWELL_LABELS[d],ylim=(-.03,1.03),ylabel='Event F1')
                    ax.set_xticks([0,1,2],['Empirical gap','25% missing','50% missing'])
                ax=axes[2,0];part=sub[sub['group']=='two_stops'].copy()
                order={(d,t):i for i,(d,t) in enumerate((d,t) for d in [25,75,150] for t in [120,600])}
                part['x']=[order[d,t] for d,t in zip(part.separation_m,part.connector_seconds)]
                for method in METHODS:_curve(ax,part[part.method==method],method,'x')
                ax.set(title='Two distinct stops',ylim=(-.03,1.03),ylabel='Event F1')
                ax.set_xticks(range(6),[f'{d}m/{t//60}min' for d,t in order],rotation=25)
                ax=axes[2,1];part=sub[sub['group']=='negative'].copy()
                kinds=['pure_move','slow','creeping','red_light'];part['x']=part.negative_kind.map(dict(zip(kinds,range(4))))
                for method in METHODS:_curve(ax,part[part.method==method],method,'x','fp_per_hour',False)
                ax.set(title='Hard negatives',ylabel='False events / latent moving hour')
                ax.set_xticks(range(4),kinds,rotation=20);ax.set_ylim(bottom=0)
                handles,labels=axes[0,0].get_legend_handles_labels()
                fig.legend(handles,labels,loc='lower center',ncol=5,bbox_to_anchor=(.5,0))
                fig.suptitle(f'Selection | radius={radius} m, min dwell={dwell} min | supplementary scenarios')
                fig.tight_layout(rect=(0,.035,1,.96));save(fig,f'config_r{radius}_d{dwell}_extras.png')
        # Separate ST-DBSCAN tuning plots at the fixed comparison radius/duration.
        sub=data[(data.method=='st_dbscan')&(data.radius_m==100)&(data.dwell_minutes==10)]
        fig,axes=plt.subplots(2,2,figsize=(10,8))
        for d,ax in enumerate(axes.flat):
            part=sub[(sub['group']=='main')&(sub.duration_group==d)&(sub.rms==15)&(sub.family=='drift')]
            pivot=part.pivot(index='eps_time_seconds',columns='min_points',values='f1').reindex(index=[60,180,300],columns=[3,5,10])
            if pivot.isna().any().any():raise ValueError('ST sweep incomplete')
            im=ax.imshow(pivot.to_numpy(),vmin=0,vmax=1,cmap='viridis')
            for i in range(3):
                for j in range(3):ax.text(j,i,f'{pivot.iloc[i,j]:.3f}',ha='center',va='center',color='white' if pivot.iloc[i,j]<.5 else 'black')
            ax.set(title=f'{DWELL_LABELS[d]} | drift 15 m',xlabel='MinPts',ylabel='Temporal eps (seconds)')
            ax.set_xticks(range(3),[3,5,10]);ax.set_yticks(range(3),[60,180,300])
            fig.colorbar(im,ax=ax,label='Event F1, user macro')
        fig.suptitle('ST-DBSCAN parameter sensitivity | selection only, radius=100 m, dwell=10 min')
        fig.tight_layout();save(fig,'st_sweep_f1.png')
        fig,axes=plt.subplots(1,4,figsize=(16,4))
        for kind,ax in zip(['pure_move','slow','creeping','red_light'],axes):
            part=sub[(sub['group']=='negative')&(sub.negative_kind==kind)]
            pivot=part.pivot(index='eps_time_seconds',columns='min_points',values='fp_per_hour').reindex(index=[60,180,300],columns=[3,5,10])
            im=ax.imshow(pivot.to_numpy(),vmin=0,cmap='magma')
            ax.set(title=kind,xlabel='MinPts',ylabel='Temporal eps (seconds)')
            ax.set_xticks(range(3),[3,5,10]);ax.set_yticks(range(3),[60,180,300])
            fig.colorbar(im,ax=ax,label='FP/hour')
        fig.tight_layout();save(fig,'st_sweep_negatives.png')
        timing=pd.read_csv(summary/'timing_per_user.csv').groupby('config_id').detector_seconds.sum()
        table=pd.DataFrame({LABELS[m]:[timing[DetectorConfig(m,r,d).config_id] for d in DURATIONS for r in RADII] for m in METHODS},
            index=[f'{r}m/{d}min' for d in DURATIONS for r in RADII])
        fig,ax=plt.subplots(figsize=(13,5));table.plot.bar(ax=ax,logy=True)
        ax.set(title='Selection detector compute | same observations, shared I/O excluded',ylabel='Seconds (log scale)',xlabel='Common configuration')
        fig.tight_layout();save(fig,'runtime_common.png')
        sweep_users=pd.read_csv(summary/'per_user.csv.gz',dtype={'user_id':str})
        sweep_users=sweep_users[(sweep_users.method=='st_dbscan')&(sweep_users.radius_m==100)&(sweep_users.dwell_minutes==10)].copy()
        sweep_users['cadence_tier']=np.select([sweep_users.cadence_median_seconds<=5,sweep_users.cadence_median_seconds<=30],['<=5s','5–30s'],default='>30s')
        sweep_users.groupby(['config_id','cell_id','cadence_tier'],dropna=False)[['f1','fp_per_hour']].mean().to_csv(destination/'st_sweep_cadence.csv')
        data[data['group']=='unobservable'].to_csv(destination/'unobservable_cells.csv',index=False)
        budget.check();write_json(destination/'audit.json',dict(status='completed',lock_hash=lock['lock_hash'],
            files={p.name:file_hash(p) for p in destination.iterdir() if p.suffix in ['.png','.csv']},**budget.summary()))
        return [destination/n for n in paths]
    except BaseException as error:
        plt.close('all');write_json(destination/'audit.json',dict(status='failed',error=str(error),**budget.summary()));raise


def render_real(root,out):
    root,out=Path(root),Path(out);lock=validate_lock(root,out)
    source=out/'real_description_selection';audit=readj(source/'audit.json')
    if audit['status']!='completed':raise ValueError('No completed real selection description')
    for n,h in audit['output_hashes'].items():
        if file_hash(source/n)!=h:raise ValueError('Real summary changed')
    destination=out/'plots_real_selection'
    if destination.exists():raise FileExistsError(destination)
    destination.mkdir();budget=JobBudget(ledger(root,out));data=pd.read_csv(source/'counts_motor_runtime.csv')
    paths=[]
    try:
        for metric,label in [('stays_user_median','Median event count per user'),
                             ('dwell_user_median_hours','Median dwell hours per user'),
                             ('r_motor_user_macro','Motor-label overlap (user macro)')]:
            fig,axes=plt.subplots(1,2,figsize=(12,4))
            for dwell,ax in zip(DURATIONS,axes):
                for method in METHODS:
                    g=data[(data.method==method)&(data.dwell_minutes==dwell)].sort_values('radius_m')
                    ax.plot(g.radius_m,g[metric],marker='o',label=LABELS[method],color=COLORS[method])
                ax.set(title=f'Min dwell={dwell} min',xlabel='Radius parameter (m)',ylabel=label)
                ax.set_xticks(RADII);ax.grid(alpha=.2)
                if metric=='r_motor_user_macro':ax.axhline(.01,ls='--',color='gray',label='1% investigation threshold')
            axes[0].legend(fontsize=8)
            fig.suptitle('Real GPS | selection-source users only | sensitivity, not accuracy')
            fig.tight_layout();name=metric+'.png';fig.savefig(destination/name,dpi=150);plt.close(fig);paths.append(name);budget.check()
        write_json(destination/'audit.json',dict(status='completed',lock_hash=lock['lock_hash'],
            files={n:file_hash(destination/n) for n in paths},**budget.summary()))
        return [destination/n for n in paths]
    except BaseException as error:
        plt.close('all');write_json(destination/'audit.json',dict(status='failed',error=str(error),**budget.summary()));raise
