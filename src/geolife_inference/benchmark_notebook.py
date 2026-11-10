"""Read-only setup and verified stage reuse for independent NB09 cells."""
from pathlib import Path


def prepare(namespace):
    import importlib
    import pandas as pd
    from IPython.display import display, Image
    from . import benchmark_jobs as jobs
    from . import benchmark_decisions as decisions
    from . import benchmark_plot_runner as plot_runner
    from . import benchmark_real_parallel as real_parallel
    from .benchmark_synthetic import file_hash

    # An already-open kernel may still cache the earlier execution wrapper,
    # which did not expose render_real. Reload only this unfrozen helper.
    plot_runner = importlib.reload(plot_runner)

    root = Path(namespace.get('ROOT', Path.cwd())).resolve()
    if not (root / 'src/geolife_inference').is_dir():
        root = root.parent
    if not (root / 'src/geolife_inference').is_dir():
        raise ValueError('Mở notebook từ thư mục dự án hoặc notebooks')
    out = Path(namespace.get('OUT', root / 'artifacts/benchmark/b4/run_v1'))
    # Never enable a detector job or final access merely by running setup.
    for name, default in [('RUN_REAL', False), ('RUN_DECIDE', False), ('RUN_FINAL', False),
                          ('RUN_SUMMARIZE', True), ('RUN_PLOTS', True), ('RESUME', True),
                          ('REAL_WORKERS', 10)]:
        namespace.setdefault(name, default)

    def completed(phase):
        path = out / phase / 'audit.json'
        return path.exists() and jobs.readj(path).get('status') == 'completed'

    def stage(name, action):
        jobs.validate_lock(root, out)
        directory = out / name
        if completed(name):
            audit = jobs.readj(directory / 'audit.json')
            for key in ['output_hashes', 'files']:
                for path, expected in audit.get(key, {}).items():
                    if file_hash(directory / path) != expected:
                        raise ValueError(f'Output đổi: {name}/{path}')
            if 'winner_sha256' in audit:
                if file_hash(directory / 'winner.json') != audit['winner_sha256']:
                    raise ValueError('Winner đổi')
                winner = jobs.readj(directory / 'winner.json')
                if file_hash(directory / 'gates.csv') != winner['gates_sha256']:
                    raise ValueError('Gates đổi')
            print(f'{name}: tái dùng completed, hashes khớp')
            return audit
        return action()

    def show_budget():
        used = jobs.ledger(root, out)
        print(f'Compute tích lũy: {used/3600:.3f}/24 giờ; còn {(86400-used)/3600:.3f} giờ')
        print('Ledger gồm khoản dự trữ lịch sử 3.600 giây từ B2, không phải toàn bộ là runtime đã đo.')

    lock = jobs.validate_lock(root, out)
    namespace.update(ROOT=root, OUT=out, lock=lock, jobs=jobs, decisions=decisions,
                     plot_runner=plot_runner, pd=pd, display=display, Image=Image,
                     real_parallel=real_parallel,
                     stage=stage, show_budget=show_budget, completed=completed,
                     synthetic_done=completed('synthetic_selection'),
                     summary_done=completed('summary_selection'))
    return lock
