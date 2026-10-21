"""The MCP surface: exactly six tools, over stdio or streamable HTTP.

No tool calls a model.  No tool decides acceptance.  ``submit_run`` starts
``tools/run.sh`` and returns its process exit status unchanged.
"""
from mcp.server.fastmcp import FastMCP

from . import platform


INSTRUCTIONS = """\
This server drives the torchfdtd-platform. The model proposes; the harness disposes.
Use list_configs to see what can run, validate_config before asking for a run, and
submit_run with dry_run=True first. submit_run executes only tools/run.sh and reports
the process exit status. ok is true only for exit 0: 53/54/55/56/57/58/59 are lawful
scientific outcomes but not successes, and 57 is a finding, not a crash. No tool calls
a model and no tool grants acceptance.
"""


def build_server(host="127.0.0.1", port=8787):
    server = FastMCP(
        "torchfdtd-platform-mcp",
        instructions=INSTRUCTIONS,
        host=host,
        port=port,
        log_level="WARNING",
    )

    @server.tool()
    def list_configs() -> dict:
        """The config/driver pairs that exist, each with a one-line purpose.

        Pairs come from the tracked run ledger. Configs with no recorded driver
        are listed separately; no path is invented.
        """
        return platform.list_configs()

    @server.tool()
    def describe_run(config: str) -> dict:
        """What a config would run: driver, solver role, and the leg's criteria.

        Criteria are quoted from the matching LEG section of plan.md, with the
        line number they came from. If no section is found, none are claimed.
        """
        return platform.describe_run(config)

    @server.tool()
    def validate_config(config: str) -> dict:
        """Run the project's existing config gate and return {ok, errors[]}.

        This calls checks/pre_environment.py; it does not restate its rules and
        runs nothing. Machine probes (git, CUDA) are stubbed, because validation
        is about the config.
        """
        return platform.validation.validate_config(config)

    @server.tool()
    async def submit_run(config: str, dry_run: bool = True) -> dict:
        """Run a config, or show the exact command and pre-flight verdict.

        dry_run=True starts nothing. dry_run=False executes only tools/run.sh and
        returns {ok, exit_status, run_id, ledger_row, stderr_tail}. ok is derived
        from the exit status: 57 is ok false, kind "finding". stderr_tail falls
        back to the stdout tail when stderr is empty, because the launcher logs
        there; tail_source names which stream was used.
        """
        import anyio

        return await anyio.to_thread.run_sync(platform.submit_run, config, dry_run)

    @server.tool()
    def read_ledger(limit: int = 20) -> dict:
        """The last N rows of runs/ledger.jsonl, verbatim and in file order."""
        return platform.read_ledger(limit)

    @server.tool()
    def explain_exit(code: int) -> dict:
        """The shared exit-code vocabulary, including "finding, not a crash".

        An unknown code is reported as unknown; this tool does not guess.
        """
        return platform.explain_exit(code)

    return server
