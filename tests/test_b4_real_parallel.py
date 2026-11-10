"""Real-data parallel execution must match the immutable serial implementation."""
import gzip
from pathlib import Path

import pandas as pd
import pytest

from test_b4_jobs import b4_fixture
from geolife_inference import benchmark_jobs as jobs, benchmark_parallel as engine
from geolife_inference import benchmark_real_parallel as real
from geolife_inference.benchmark_synthetic import file_hash, iter_trajectories


def prepare(root, out, monkeypatch):
    for module in [engine, real]:
        source = Path(module.__file__)
        (root / 'src/geolife_inference' / source.name).write_bytes(source.read_bytes())
    monkeypatch.setattr(engine, '_tree_ws', lambda pids: 100)
    return root, out


def test_real_parallel_cache_and_metrics_match_serial_exactly(b4_fixture, monkeypatch):
    root, serial = prepare(*b4_fixture, monkeypatch)
    jobs.run_real(root, serial)
    out = serial.with_name('real_parallel_fixture')
    jobs.register(root, out)
    original = {n: file_hash(root / 'src/geolife_inference' / n) for n in jobs.MODULES}
    audit = real.run_real(root, out, workers=5)
    assert audit['status'] == 'completed' and audit['configs'] == 40
    assert audit['completed_users'] == ['000', '001', '002']
    assert audit['gate_d_timing_eligible'] is False
    cached = [frame for user in audit['completed_users']
              for frame in real._frames(out / 'real_parallel_inputs' / f'{user}.pkl.gz')]
    source = list(iter_trajectories(root / 'artifacts/preprocessing/cleaned_points.csv.gz'))
    for a, b in zip(source, cached):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    for user in audit['completed_users']:
        a = pd.read_csv(serial / 'real' / f'{user}_metrics.csv').drop(columns='detector_seconds')
        b = pd.read_csv(out / 'real' / f'{user}_metrics.csv').drop(columns='detector_seconds')
        pd.testing.assert_frame_equal(a, b, check_exact=True)
        pd.testing.assert_frame_equal(pd.read_csv(serial / 'real' / f'{user}_edges.csv'),
                                      pd.read_csv(out / 'real' / f'{user}_edges.csv'), check_exact=True)
        with gzip.open(serial / 'real' / f'{user}_events.csv.gz', 'rb') as a, \
                gzip.open(out / 'real' / f'{user}_events.csv.gz', 'rb') as b:
            assert a.read() == b.read()
    assert original == {n: file_hash(root / 'src/geolife_inference' / n) for n in jobs.MODULES}
    jobs.describe_real(root, out)


def test_real_serial_resume_preserves_checkpoints_and_ledger(b4_fixture, monkeypatch):
    root, out = prepare(*b4_fixture, monkeypatch)
    checkpoint = jobs._checkpoint

    def stop(*args):
        checkpoint(*args)
        raise KeyboardInterrupt('Fixture interruption')

    monkeypatch.setattr(jobs, '_checkpoint', stop)
    with pytest.raises(KeyboardInterrupt):
        jobs.run_real(root, out)
    audit = jobs.readj(out / 'real/audit.json')
    hashes = dict(audit['output_hashes'])
    used = audit['compute_used_after_seconds']
    resumed = real.run_real(root, out, workers=10, resume=True)
    assert resumed['status'] == 'completed' and resumed['inherited_serial_users'] == ['000']
    assert resumed['compute_used_after_seconds'] > used and len(resumed['attempts']) == 2
    assert all(resumed['output_hashes'][name] == h for name, h in hashes.items())
    with pytest.raises(FileExistsError):
        real.run_real(root, out, workers=10, resume=True)


def test_real_parallel_rejects_invalid_capacity_and_duplicate_writer(b4_fixture, monkeypatch):
    root, out = prepare(*b4_fixture, monkeypatch)
    with pytest.raises(ValueError):
        real.run_real(root, out, workers=11)
    with engine._coordinator_lease(out):
        with pytest.raises(RuntimeError):
            real.run_real(root, out, workers=5)
