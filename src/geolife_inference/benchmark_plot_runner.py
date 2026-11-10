"""Run the frozen B4 renderer outside the notebook, with prompt figure cleanup."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import gc
import os
from pathlib import Path
import subprocess
import sys


@contextmanager
def _lease(out, phase='plots_selection'):
    handle = (out / f'{phase}.guard').open('a+b')
    try:
        if not handle.tell():
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def _prepare(out, phase='plots_selection'):
    from .benchmark_jobs import readj
    from .benchmark_synthetic import file_hash

    destination = out / phase
    if not destination.exists():
        return False
    audit = readj(destination / 'audit.json')
    if audit['status'] == 'completed':
        for name, expected in audit['files'].items():
            if file_hash(destination / name) != expected:
                raise ValueError(f'Plot changed: {name}')
        return True
    if audit['status'] != 'failed':
        raise RuntimeError('Plot attempt is not failed; inspect before retrying')
    # Keep the failed audit directly under OUT so ledger() still charges its time.
    archive = out / (phase + '_failed_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if destination.resolve().parent != out.resolve() or archive.resolve().parent != out.resolve():
        raise ValueError('Plot archive must remain inside the B4 run directory')
    destination.rename(archive)
    print(f'Preserved failed plot attempt: {archive.name}', flush=True)
    return False


def _render(root, out, phase='plots_selection'):
    import matplotlib
    matplotlib.use('Agg', force=True)
    import matplotlib.pyplot as plt
    from . import benchmark_jobs as jobs
    from . import benchmark_plots as plots
    from .benchmark_synthetic import file_hash, write_json

    jobs.validate_lock(root, out)
    with _lease(out, phase):
        if _prepare(out, phase):
            print(f'{phase}: completed; output hashes verified', flush=True)
            return
        original_close = plt.close

        def close_and_collect(fig=None):
            original_close(fig)
            if isinstance(fig, matplotlib.figure.Figure):
                # savefig has finished. Release artists and Agg's pixel buffer even
                # while the frozen renderer still holds its local Figure reference.
                fig.clear()
                if hasattr(fig.canvas, 'renderer'):
                    fig.canvas.renderer = None
            gc.collect()

        plt.close = close_and_collect
        try:
            if phase == 'plots_real_selection':
                plots.render_real(root, out)
            else:
                plots.render(root, out)
        finally:
            plt.close = original_close
            path = out / phase / 'audit.json'
            if path.exists():
                audit = jobs.readj(path)
                audit['execution'] = dict(
                    runner_sha256=file_hash(Path(__file__)), backend='Agg',
                    isolated_process=True, cleanup='clear artists, release renderer, collect after close',
                    scientific_code_changed=False)
                write_json(path, audit)


def render(root, out, *, phase='plots_selection'):
    """Wait for an isolated plot job; reuse completed output or archive a failed attempt."""
    root, out = Path(root).resolve(), Path(out).resolve()
    if phase not in ['plots_selection', 'plots_real_selection']:
        raise ValueError(f'Unknown plot phase: {phase}')
    env = os.environ.copy()
    env['PYTHONPATH'] = str(root / 'src') + os.pathsep + env.get('PYTHONPATH', '')
    env['MPLBACKEND'] = 'Agg'
    for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
        env[name] = '1'
    log = out / ('plot_render.log' if phase == 'plots_selection' else 'plot_render_real.log')
    with log.open('a', encoding='utf-8') as stream:
        result = subprocess.run(
            [sys.executable, '-u', '-m', 'geolife_inference.benchmark_plot_runner',
             '--root', str(root), '--out', str(out), '--phase', phase], cwd=root, env=env,
            stdout=stream, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        tail = log.read_text(encoding='utf-8', errors='replace')[-2500:]
        raise RuntimeError(f'Plot job failed; see {log}\n{tail}')
    from .benchmark_jobs import readj
    audit = readj(out / phase / 'audit.json')
    return [out / phase / name for name in audit['files'] if name.endswith('.png')]


def render_real(root, out):
    return render(root, out, phase='plots_real_selection')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--phase', choices=['plots_selection', 'plots_real_selection'], default='plots_selection')
    args = parser.parse_args()
    _render(args.root, args.out, args.phase)
