# ---------------------------------------------------------------------------
# COPIED, not invented. Source: the reference project 20261010_torchfdtd-lumerical-parity
#   tools/launch.py
#   at commit 9b0f61a41b026342420422b7d208a046d7b6e45b
#   sha256(source) = 9de57d5b675d389166caa8fa1ed2fce7b7a13d24b57c03b12d9ded7ae99cff7b
#   copied 2026-10-18 by leg 1 (F0+F8). This project owns this copy now.
# ---------------------------------------------------------------------------
"""Resource-exclusive, snapshot-based simulation launcher.

Cross-platform note: the Linux path is unchanged. The POSIX-only pieces
(``fcntl``, ``os.killpg``, ``start_new_session``) are isolated behind
``os.name`` guards so the same launcher runs on Windows. Set the environment
variable ``PARITY_SOLVER_ROOT`` to point at the pinned solver clone when
``src/torchfdtd_upstream`` is not a symlink (for example on Windows).
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import platform

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

ROOT = Path(__file__).resolve().parents[1]


def ledger_row(manifest):
    """The ledger is tracked in git, so it must not carry machine-specific paths.

    CHANGED from the copy: `config` and `python` are stored relative to the project
    root. The full manifest, absolute paths included, stays in the untracked run
    directory next to its snapshot.
    """
    row = dict(manifest)
    for key in ('config', 'python'):
        value = row.get(key)
        if not isinstance(value, str):
            continue
        for candidate in (Path(value), Path(value).resolve()):
            try:
                row[key] = str(candidate.relative_to(ROOT))
                break
            except ValueError:
                continue
        else:
            row[key] = Path(value).name
    return row


def lock_exclusive(handle):
    """Non-blocking exclusive lock. Raises BlockingIOError when already held."""
    if fcntl is not None:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write('\0')
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as error:
        raise BlockingIOError(str(error)) from error


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')

def main():
    config = Path(sys.argv[1])
    if not config.is_file():
        config = ROOT / 'configs' / sys.argv[1]
    script = ROOT / sys.argv[2]
    if not config.is_file() or not script.is_file():
        raise SystemExit('Config or script missing')
    script_relative = script.resolve().relative_to(ROOT)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PARITY_CONFIG=str(config.resolve()))
    (ROOT / 'runs').mkdir(exist_ok=True)
    with (ROOT / 'runs/.lock').open('w') as lock:
        try:
            lock_exclusive(lock)
        except BlockingIOError:
            raise SystemExit('Another run holds the project lock')
        now = datetime.datetime.now(datetime.timezone.utc)
        rid = now.strftime('%Y%m%dT%H%M%SZ') + '-' + str(os.getpid())
        run = ROOT / 'runs' / rid
        run.mkdir()
        snapshot = run / 'snapshot'
        snapshot.mkdir()
        for folder in ('src', 'checks', 'tools', 'configs'):
            shutil.copytree(ROOT / folder, snapshot / folder,
                            ignore=shutil.ignore_patterns('__pycache__', '.git', 'web', '*.pyc',
                                                          'torchfdtd_upstream', 'torchfdtd'))
        # Solver role (plan.md v2.0): 'fork' is our working solver and the default;
        # 'upstream' is the frozen provenance used to reproduce pre-v2.0 evidence.
        solver_role = os.environ.get('PARITY_SOLVER_ROLE', 'fork')
        solver_override = os.environ.get('PARITY_SOLVER_ROOT')
        if solver_override:
            solver = Path(solver_override)
        else:
            solver = ROOT / ('src/torchfdtd' if solver_role == 'fork' else 'src/torchfdtd_upstream')
        shutil.copytree(solver / 'torchfdtd', snapshot / 'src/solver/torchfdtd',
                        ignore=shutil.ignore_patterns('__pycache__', 'web', '*.pyc'))
        for name in ('LICENSE', 'THIRD_PARTY_NOTICES.txt', 'pyproject.toml'):
            shutil.copy2(solver / name, snapshot / 'src/solver' / name)
        for name in ('plan.md', 'README.md', 'AGENTS.md'):
            shutil.copy2(ROOT / name, snapshot / name)
        shutil.copy2(config, run / 'config.input.json')
        hashes = {str(p.relative_to(snapshot)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in snapshot.rglob('*') if p.is_file()}
        dump(run / 'snapshot-sha256.json', hashes)
        def _solver_commit(path):
            return command(['git', '-C', str(path), 'rev-parse', 'HEAD'])

        def _solver_dirty_lines(path):
            out = command(['git', '-C', str(path), 'status', '--porcelain'])
            return len([line for line in out.splitlines() if line.strip()])

        def command(args):
            result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
            return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
        pin = json.loads((ROOT / 'configs/baseline-pin.json').read_text())
        manifest = dict(run_id=rid, status='started', exit_code=None,
                        started_utc=now.isoformat(), project_git_head=command(['git', 'rev-parse', 'HEAD']),
                        config=str(config.resolve()), script=sys.argv[2], args=sys.argv[3:],
                        python=sys.executable, solver_role=solver_role,
                        solver_commit=_solver_commit(solver),
                        solver_dirty_lines=_solver_dirty_lines(solver),
                        upstream_commit=pin['upstream']['solver_commit'],
                        cpu_platform=platform.platform(), cpu_count=os.cpu_count(),
                        snapshot_files=len(hashes), gpu=command(['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader']))
        dump(run / 'manifest.json', manifest)
        (run / 'status').write_text('started\n')
        (run / 'diff.patch').write_text(command(['git', 'diff', 'HEAD']))
        (run / 'pip-freeze.txt').write_text(command([sys.executable, '-m', 'pip', 'freeze']))
        (run / 'task.txt').write_text(json.loads(config.read_text()).get('task', 'Unspecified step') + '\n')
        env.update(RUN_DIR_ABS=str(run), EFFECTIVE_JSON=str(run / 'effective.json'),
                   PARITY_CONFIG=str(run / 'config.input.json'), PARITY_SNAPSHOT=str(snapshot),
                   PARITY_SOLVER_ROLE=solver_role)
        print(f'[run.sh] run_id={rid}', flush=True)
        # Rejected attempts need the same provenance as executed runs. This is
        # unresolved configuration, never a claim that a simulation ran.
        effective=dict(config=json.loads(config.read_text()),solver_pin=pin,
                       stage='preflight',resolved_cases=[],simulation_executed=False)
        if effective['config'].get('reference'):
            reference=ROOT/effective['config']['reference']
            if reference.is_file():
                effective['reference_sha256']=hashlib.sha256(reference.read_bytes()).hexdigest()
        dump(run/'effective.json',effective)
        with (run/'stdout.log').open('w') as log:
            for check in sorted((ROOT/'checks').glob('pre_*.py')):
                result=subprocess.run([sys.executable,'-B',str(check)],env=env,
                                      stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                log.write(result.stdout);log.flush()
                print(result.stdout,end='',flush=True)
                if result.returncode:
                    status=f'failed:preflight={check.name}'
                    message=f'[run.sh] preflight failed: {check.name}'
                    log.write(message+'\n');print(message,flush=True)
                    manifest.update(status=status,exit_code=65,preflight_exit_code=result.returncode,
                                    finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
                    dump(run/'manifest.json',manifest)
                    (run/'status').write_text(status+'\n')
                    with (ROOT/'runs/ledger.jsonl').open('a') as ledger:
                        ledger.write(json.dumps(ledger_row(manifest),ensure_ascii=False)+'\n')
                    print(f'[run.sh] exit=65 status={status} run_dir={run}',flush=True)
                    return 65
        proc = subprocess.Popen([sys.executable, '-B', '-u', str(snapshot / script_relative), *sys.argv[3:]],
                                cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                start_new_session=(os.name == 'posix'))
        interrupted = []
        if os.name == 'posix':
            def stop(signum, frame):
                interrupted.append(signum)
                os.killpg(proc.pid, signum)
        else:
            def stop(signum, frame):
                interrupted.append(signum)
                proc.terminate()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, stop)
        with (run / 'stdout.log').open('a') as log:
            for line in proc.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
        rc = proc.wait()
        status = ('interrupted:' + signal.Signals(interrupted[0]).name if interrupted else
                  f'failed:exit={rc}' if rc else
                  'incomplete:no-effective-json' if not (run / 'effective.json').is_file() else 'completed')
        manifest.update(status=status, exit_code=rc,
                        finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        dump(run / 'manifest.json', manifest)
        (run / 'status').write_text(status + '\n')
        with (ROOT / 'runs/ledger.jsonl').open('a') as ledger:
            ledger.write(json.dumps(ledger_row(manifest), ensure_ascii=False) + '\n')
        print(f'[run.sh] exit={rc} status={status} run_dir={run}', flush=True)
        return rc if rc else (0 if status == 'completed' else 70)

if __name__ == '__main__':
    sys.exit(main())
