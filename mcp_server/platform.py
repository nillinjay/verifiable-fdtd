"""The six tools' platform logic.

Only ``submit_run`` starts a process, and the only program it starts is
``tools/run.sh``.  The exit status of that process is returned unchanged; ``ok``
is derived from it, never from the presence of a result file.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

from . import exits, paths, validation
from .plan import criteria_for


_RUN_ID = re.compile(r"\[run\.sh\] run_id=(\S+)")
_TAIL_LINES = 20
_TAIL_CHARS = 4000


def _ledger_path(root):
    return root / "runs" / "ledger.jsonl"


def _ledger_rows(root):
    path = _ledger_path(root)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"raw": line})
    return rows


def _purpose(config):
    task = config.get("purpose") or config.get("task") or ""
    if not isinstance(task, str):
        return ""
    one_line = " ".join(task.split())
    sentence = re.split(r"(?<=[.!?])\s+", one_line, maxsplit=1)[0]
    return sentence[:240]


def _config_for(root, name):
    path, error = paths.resolve_config(name, root)
    if error:
        return None, None, error
    try:
        data = paths.read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return path, None, f"config is not readable JSON: {exc}"
    if not isinstance(data, dict):
        return path, None, "config must be a JSON object"
    return path, data, None


def solver_status(root=None):
    root = (root or paths.project_root()).resolve()
    role = os.environ.get("PARITY_SOLVER_ROLE", "fork")
    try:
        pin = paths.read_json(root / "configs" / "baseline-pin.json")
    except (OSError, json.JSONDecodeError):
        pin = {}
    if role == "upstream":
        declared = (pin.get("upstream", {}) or {}).get("solver_root", "src/torchfdtd_upstream")
    else:
        declared = pin.get("solver_root", "src/torchfdtd")
    solver = root / declared
    return {
        "role": role,
        "root": declared,
        "available": (solver / "torchfdtd").is_dir(),
        "python_package_seen": (solver / "torchfdtd" / "__init__.py").is_file(),
    }


def _driver_from_config(root, config):
    for key in ("driver", "script"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            candidate = (root / value).resolve()
            return {
                "driver": value,
                "driver_source": f"config field `{key}`",
                "driver_exists": paths.inside_root(candidate, root) and candidate.is_file(),
            }
    return None


def _driver_from_ledger(root, config_path):
    target = config_path.resolve()
    found = None
    for row in _ledger_rows(root):
        recorded = row.get("config")
        script = row.get("script")
        if not isinstance(recorded, str) or not isinstance(script, str):
            continue
        try:
            candidate = (root / recorded).resolve()
        except OSError:
            continue
        if candidate == target and paths.inside_root(root / script, root):
            found = script
    if found is None:
        return None
    return {
        "driver": found,
        "driver_source": "runs/ledger.jsonl",
        "driver_exists": (root / found).is_file(),
    }


def driver_for(root, config_path, config):
    return _driver_from_config(root, config) or _driver_from_ledger(root, config_path)


def _command(root, config_path, driver):
    config_arg = paths.relative_to_root(config_path, root)
    argv = [str(root / "tools" / "run.sh"), config_arg, driver]
    return argv, shlex.join(argv)


def _known_command(root):
    return str(root / "tools" / "run.sh")


def list_configs():
    root = paths.project_root().resolve()
    pairs = {}
    for row in _ledger_rows(root):
        config, script = row.get("config"), row.get("script")
        if isinstance(config, str) and isinstance(script, str):
            pairs[(config, script)] = True

    configs = []
    for config, script in sorted(pairs):
        path = root / config
        if not path.is_file():
            continue
        try:
            data = paths.read_json(path)
        except (OSError, json.JSONDecodeError):
            data = {}
        configs.append(
            {
                "config": config,
                "driver": script,
                "driver_exists": (root / script).is_file(),
                "purpose": _purpose(data) if isinstance(data, dict) else "",
            }
        )

    paired = {config for config, _ in pairs}
    unpaired = []
    for path in sorted((root / "configs").glob("*.json")):
        rel = paths.relative_to_root(path, root)
        if rel in paired:
            continue
        try:
            data = paths.read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not data.get("task") or not data.get("kind"):
            continue
        unpaired.append(
            {
                "config": rel,
                "purpose": _purpose(data),
                "reason": "no ledger row records a driver for this config; none is invented",
            }
        )

    return {
        "ok": True,
        "configs": configs,
        "unpaired_configs": unpaired,
        "source": "runs/ledger.jsonl (config -> driver), configs/*.json (purpose)",
    }


def describe_run(config):
    root = paths.project_root().resolve()
    config_path, data, error = _config_for(root, config)
    if error:
        return {"ok": False, "kind": "config_unknown", "errors": [error], "config": str(config)}

    driver = driver_for(root, config_path, data)
    validation_result = validation.validate_config(config_path, root)
    criteria = criteria_for(config_path, root / "plan.md")
    solver = solver_status(root)
    issues = []
    if driver is None:
        issues.append("no driver is recorded for this config; none was invented")
    elif not driver["driver_exists"]:
        issues.append(f"recorded driver does not exist: {driver['driver']}")
    if not validation_result["ok"]:
        issues.extend(validation_result["errors"])

    argv = None
    command = None
    if driver and driver["driver_exists"]:
        argv, command = _command(root, config_path, driver["driver"])

    result = {
        "ok": not issues,
        "config": paths.relative_to_root(config_path, root),
        "driver": driver["driver"] if driver else None,
        "driver_source": driver["driver_source"] if driver else None,
        "driver_exists": driver["driver_exists"] if driver else False,
        "solver": solver,
        "criteria": criteria["criteria"],
        "criteria_text": criteria["criteria_text"],
        "criteria_source": criteria["criteria_source"],
        "criteria_note": criteria["criteria_note"],
        "validation": validation_result,
        "command": command,
        "argv": argv,
    }
    if issues:
        result["kind"] = "unusable_config"
        result["errors"] = issues
    return result


def _tail(text):
    if not text:
        return ""
    lines = text.strip().splitlines()
    tail = "\n".join(lines[-_TAIL_LINES:])
    return tail[-_TAIL_CHARS:]


def _ledger_row_for(root, run_id):
    if not run_id:
        return None
    for row in reversed(_ledger_rows(root)):
        if row.get("run_id") == run_id:
            return row
    return None


def submit_run(config, dry_run=True):
    root = paths.project_root().resolve()
    config_path, data, error = _config_for(root, config)
    if error:
        return {
            "ok": False,
            "dry_run": bool(dry_run),
            "executed": False,
            "kind": "invalid_config",
            "errors": [error],
            "config": str(config),
            "exit_status": None,
            "run_id": None,
            "ledger_row": None,
            "stderr_tail": "",
        }

    validation_result = validation.validate_config(config_path, root)
    if not validation_result["ok"]:
        return {
            "ok": False,
            "dry_run": bool(dry_run),
            "executed": False,
            "kind": "invalid_config",
            "errors": validation_result["errors"],
            "config": paths.relative_to_root(config_path, root),
            "validation": validation_result,
            "exit_status": None,
            "run_id": None,
            "ledger_row": None,
            "stderr_tail": "",
        }

    driver = driver_for(root, config_path, data)
    if driver is None:
        return {
            "ok": False,
            "dry_run": bool(dry_run),
            "executed": False,
            "kind": "driver_unknown",
            "errors": ["no driver is recorded for this config; none was invented"],
            "config": paths.relative_to_root(config_path, root),
            "exit_status": None,
            "run_id": None,
            "ledger_row": None,
            "stderr_tail": "",
        }
    if not driver["driver_exists"]:
        return {
            "ok": False,
            "dry_run": bool(dry_run),
            "executed": False,
            "kind": "driver_missing",
            "errors": [f"recorded driver does not exist: {driver['driver']}"],
            "config": paths.relative_to_root(config_path, root),
            "driver": driver["driver"],
            "exit_status": None,
            "run_id": None,
            "ledger_row": None,
            "stderr_tail": "",
        }

    solver = solver_status(root)
    argv, command = _command(root, config_path, driver["driver"])
    launcher_exists = (root / "tools" / "run.sh").is_file()
    preflight_errors = []
    if not launcher_exists:
        preflight_errors.append(f"launcher does not exist: {root / 'tools' / 'run.sh'}")
    if not solver["available"]:
        preflight_errors.append(
            f"solver is unavailable at {solver['root']}; run tools/bootstrap_solver.sh first"
        )
    preflight = {
        "ok": not preflight_errors,
        "errors": preflight_errors,
        "validation": validation_result,
        "solver": solver,
        "launcher_exists": launcher_exists,
        "note": (
            "this is the config-level verdict; tools/run.sh runs its own "
            "checks/pre_environment.py when a real run starts"
        ),
    }

    if dry_run:
        return {
            "ok": preflight["ok"],
            "dry_run": True,
            "executed": False,
            "kind": (
                "dry_run"
                if preflight["ok"]
                else "launcher_missing"
                if not launcher_exists
                else "solver_unavailable"
            ),
            "config": paths.relative_to_root(config_path, root),
            "driver": driver["driver"],
            "command": command,
            "argv": argv,
            "preflight": preflight,
            "exit_status": None,
            "run_id": None,
            "ledger_row": None,
            "stderr_tail": "",
        }

    if not solver["available"]:
        return {
            "ok": False,
            "dry_run": False,
            "executed": False,
            "kind": "solver_unavailable",
            "errors": preflight["errors"],
            "config": paths.relative_to_root(config_path, root),
            "driver": driver["driver"],
            "command": command,
            "argv": argv,
            "preflight": preflight,
            "exit_status": None,
            "run_id": None,
            "ledger_row": None,
            "stderr_tail": "",
        }

    run_sh = _known_command(root)
    if not Path(run_sh).is_file():
        return {
            "ok": False,
            "dry_run": False,
            "executed": False,
            "kind": "launcher_missing",
            "errors": [f"launcher does not exist: {run_sh}"],
            "config": paths.relative_to_root(config_path, root),
            "exit_status": None,
            "run_id": None,
            "ledger_row": None,
            "stderr_tail": "",
        }

    try:
        completed = subprocess.run(
            argv,
            cwd=str(root),
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return {
            "ok": False,
            "dry_run": False,
            "executed": False,
            "kind": "launcher_error",
            "errors": [f"could not start tools/run.sh: {exc}"],
            "config": paths.relative_to_root(config_path, root),
            "driver": driver["driver"],
            "command": command,
            "exit_status": None,
            "run_id": None,
            "ledger_row": None,
            "stderr_tail": "",
        }

    exit_status = completed.returncode
    match = _RUN_ID.search(completed.stdout or "")
    run_id = match.group(1) if match else None
    ledger_row = _ledger_row_for(root, run_id)
    has_stderr = bool((completed.stderr or "").strip())
    return {
        "ok": exit_status == 0,
        "dry_run": False,
        "process_started": True,
        "executed": exit_status not in exits.NOT_EXECUTED,
        "kind": exits.kind(exit_status),
        "exit_status": exit_status,
        "run_id": run_id,
        "ledger_row": ledger_row,
        "config": paths.relative_to_root(config_path, root),
        "driver": driver["driver"],
        "command": command,
        "stderr_tail": _tail(completed.stderr) or _tail(completed.stdout),
        "tail_source": "stderr" if has_stderr else "stdout",
        "stdout_tail": _tail(completed.stdout),
        "meaning": exits.explain(exit_status)["meaning"],
    }


def read_ledger(limit=20):
    root = paths.project_root().resolve()
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return {"ok": False, "kind": "bad_request", "errors": ["limit must be an integer"], "rows": []}
    if limit < 0:
        return {"ok": False, "kind": "bad_request", "errors": ["limit must be >= 0"], "rows": []}
    rows = _ledger_rows(root)
    selected = rows[-limit:] if limit else []
    return {
        "ok": True,
        "rows": selected,
        "count": len(selected),
        "total": len(rows),
        "ledger": paths.relative_to_root(_ledger_path(root), root),
    }


def explain_exit(code):
    return exits.explain(code)
