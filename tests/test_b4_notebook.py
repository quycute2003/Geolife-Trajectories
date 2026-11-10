"""Exercise independent NB09 cells on temporary data; never open the real final set."""
import json
from pathlib import Path

import pytest

from test_b4_jobs import b4_fixture
from geolife_inference import benchmark_jobs as jobs
from geolife_inference import benchmark_plot_runner as plot_runner
from geolife_inference.benchmark_synthetic import file_hash


NOTEBOOK = Path(__file__).parents[1] / 'notebooks/09_cp1_b4_detectors.ipynb'


def run_cell(cell_id, root, out, **flags):
    notebook = json.loads(NOTEBOOK.read_text(encoding='utf-8'))
    source = ''.join(next(c for c in notebook['cells'] if c['id'] == cell_id)['source'])
    namespace = dict(ROOT=root, OUT=out, **flags)
    exec(compile(source, str(NOTEBOOK), 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('cell_id', ['b4-10', 'b4-12', 'b4-14', 'b4-16'])
def test_independent_cells_default_to_no_jobs(b4_fixture, cell_id):
    root, out = b4_fixture
    before = sorted(str(p.relative_to(root)) for p in root.rglob('*'))
    namespace = run_cell(cell_id, root, out)
    # The user may explicitly enable RUN_REAL in section 5's source cell.
    # Missing prerequisites must still prevent a launch in a fresh namespace.
    if cell_id != 'b4-12':
        assert namespace['RUN_REAL'] is False
    assert namespace['RUN_DECIDE'] is False
    assert namespace['RUN_FINAL'] is False
    assert sorted(str(p.relative_to(root)) for p in root.rglob('*')) == before


def test_enabled_cells_wait_for_missing_dependencies(b4_fixture, capsys):
    root, out = b4_fixture
    for cell_id, flag in [('b4-12', 'RUN_REAL'), ('b4-14', 'RUN_DECIDE'), ('b4-16', 'RUN_FINAL')]:
        run_cell(cell_id, root, out, **{flag: True})
    assert 'completed' in capsys.readouterr().out
    assert not (out / 'real').exists()
    assert not (out / 'decision_selection').exists()
    assert not (root / 'artifacts/benchmark/b2/final_v1').exists()


def test_parallel_real_timing_cannot_select_a_winner(b4_fixture, capsys):
    from geolife_inference.benchmark_synthetic import write_json
    root, out = b4_fixture
    (out / 'real').mkdir()
    write_json(out / 'real/audit.json', dict(status='completed', gate_d_timing_eligible=False))
    run_cell('b4-14', root, out, RUN_DECIDE=True)
    assert 'Cổng (d) chưa xác nhận' in capsys.readouterr().out
    assert not (out / 'decision_selection').exists()


def test_notebook_real_decision_and_final_guard_on_tiny_fixture(b4_fixture, capsys):
    root, out = b4_fixture
    jobs.run_synthetic(root, out)
    jobs.summarize(root, out)
    run_cell('b4-12', root, out, RUN_REAL=True, RUN_PLOTS=False, REAL_WORKERS=1)
    assert jobs.readj(out / 'real/audit.json')['status'] == 'completed'
    run_cell('b4-14', root, out, RUN_DECIDE=True)
    assert jobs.readj(out / 'decision_selection/winner.json')['status'] == 'keep_baseline'
    run_cell('b4-16', root, out, RUN_FINAL=True)
    assert 'Selection giữ baseline' in capsys.readouterr().out
    assert not (root / 'artifacts/benchmark/b2/final_v1').exists()

    # Use the low-memory wrapper with the actual frozen real-plot renderer.
    plot_runner._render(root, out, 'plots_real_selection')
    audit_path = out / 'plots_real_selection/audit.json'
    audit = jobs.readj(audit_path)
    assert audit['status'] == 'completed' and len(audit['files']) == 3
    for name, expected in audit['files'].items():
        assert file_hash(audit_path.parent / name) == expected
    before = file_hash(audit_path)
    plot_runner._render(root, out, 'plots_real_selection')
    assert file_hash(audit_path) == before
    assert jobs.validate_lock(root, out)
