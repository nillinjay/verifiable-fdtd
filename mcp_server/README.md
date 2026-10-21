# torchfdtd-platform-mcp

An MCP server for the **torchfdtd-platform**. It exposes six tools over stdio
(local clients) and streamable HTTP (remote clients):

| tool | returns |
|---|---|
| `list_configs()` | config/driver pairs recorded in `runs/ledger.jsonl`, with a one-line purpose |
| `describe_run(config)` | driver, solver role, and the criteria quoted from the leg's `plan.md` section |
| `validate_config(config)` | `{ok, errors[]}` from the project's own `checks/pre_environment.py` gate |
| `submit_run(config, dry_run=True)` | the exact command and pre-flight verdict, or the run's `{ok, exit_status, run_id, ledger_row, stderr_tail}` |
| `read_ledger(limit)` | the last N ledger rows, in file order |
| `explain_exit(code)` | the shared exit vocabulary; unknown codes stay unknown |

```bash
pip install -e .                 # installs torchfdtd-platform-mcp
torchfdtd-platform-mcp           # stdio
torchfdtd-platform-mcp --http --host 0.0.0.0 --port 8787   # HTTP at /mcp
```

The design rule is one sentence: **the model proposes, the harness disposes.**
No tool calls a model. `submit_run` executes only `tools/run.sh`, and `ok` is
derived from the process exit status. Exit `57` is a lawful finding and comes
back as `ok: false, kind: "finding"`, never as success.
