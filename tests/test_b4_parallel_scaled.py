"""Execution-capacity extension retains the frozen engine and its checkpoints."""
from pathlib import Path
import gzip
import json

import pandas as pd
import pytest

from test_b4_jobs import b4_fixture
from geolife_inference import benchmark_jobs as jobs,benchmark_parallel as engine,benchmark_parallel_scaled as scaled
from geolife_inference.benchmark_synthetic import digest,file_hash,write_json


def test_ten_user_capacity_uses_unchanged_engine(b4_fixture,monkeypatch):
    root,original=b4_fixture
    for module in [engine,scaled]:
        (root/'src/geolife_inference'/Path(module.__file__).name).write_bytes(Path(module.__file__).read_bytes())
    corpus=root/'artifacts/benchmark/b2/selection_v1'
    prep_path=root/'artifacts/benchmark/b2/prepared_v1/protocol.json';prep=jobs.readj(prep_path)
    profiles_path=root/'artifacts/benchmark/b1/profiles_v1/profiles_per_user.csv'
    profiles=pd.read_csv(profiles_path,dtype={'user_id':str})
    for user in [f'{i:03d}' for i in range(10,18)]:
        prep['split'][user]='selection';prep['independence_groups'][user]='000'
        with gzip.open(corpus/'observations/000.csv.gz','rt',encoding='utf-8') as f:text=f.read()
        text=text.replace('000_',user+'_').replace(',000,',','+user+',')
        with gzip.open(corpus/'observations'/f'{user}.csv.gz','wt',encoding='utf-8') as f:f.write(text)
        with gzip.open(corpus/'truth/000.jsonl.gz','rt',encoding='utf-8') as src, \
             gzip.open(corpus/'truth'/f'{user}.jsonl.gz','wt',encoding='utf-8') as dst:
            for line in src:
                row=json.loads(line);row['source_user_id']=user;row['case_id']=row['case_id'].replace('000_',user+'_')
                dst.write(json.dumps(row)+'\n')
        profiles=pd.concat([profiles,pd.DataFrame([dict(user_id=user,dt_observed_seconds_p50=30)])],ignore_index=True)
    profiles.to_csv(profiles_path,index=False)
    prep['protocol_hash']=digest({k:v for k,v in prep.items() if k!='protocol_hash'});write_json(prep_path,prep)
    audit=jobs.readj(corpus/'generation_audit.json');audit['protocol_hash']=prep['protocol_hash']
    audit['cases']=200;audit['points']=0
    for path in (corpus/'truth').glob('*.jsonl.gz'):
        with gzip.open(path,'rt',encoding='utf-8') as f:
            audit['points']+=sum(json.loads(line)['diagnostics']['observed_fixes'] for line in f)
    audit['output_sha256']={str(p.relative_to(corpus)):file_hash(p) for sub in ['observations','truth'] for p in (corpus/sub).iterdir()}
    write_json(corpus/'generation_audit.json',audit)
    out=original.with_name('scaled_v1');jobs.register(root,out)
    monkeypatch.setattr(engine,'_tree_ws',lambda pids:100)
    frozen=file_hash(root/'src/geolife_inference/benchmark_parallel.py')
    result=scaled.run_synthetic(root,out,workers=10)
    assert result['status']=='completed' and result['workers']==10 and len(result['completed_users'])==10
    assert result['scaling_execution_hash']==scaled.execution_lock(root,out)['scaling_hash']
    assert file_hash(root/'src/geolife_inference/benchmark_parallel.py')==frozen
    for name in result['output_hashes']:assert file_hash(out/'synthetic_selection'/name)==result['output_hashes'][name]
    with pytest.raises(ValueError):scaled.run_synthetic(root,out,workers=11)
