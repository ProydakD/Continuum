"""Engineering coordination through real MCP in its own research-only database."""
import argparse
import asyncio
from mcp import Client
from mcp.client.stdio import StdioServerParameters
import sys
from .common import PROJECT, ROOT, server_env, write_json
from .preflight import content


async def coordinate(finish=False):
    state = ROOT / "state"
    state.mkdir(exist_ok=True)
    params = StdioServerParameters(command=sys.executable, args=["-m", "continuum.mcp_server"], cwd=PROJECT,
        env=server_env(state / "engineering.sqlite3", "engineering-v02", "implementation-v02", role="engineering"))
    records = []
    async with Client(params, read_timeout_seconds=15) as client:
        await client.list_tools()

        async def call(name, **kwargs):
            result = await client.call_tool("continuum_"+name, kwargs)
            records.append({"tool": name, "input": kwargs, "result": result.model_dump(by_alias=True, mode="json")})
            return content(result)

        await call("bootstrap")
        task = await call("create_task", title="Continuum v0.2 Research Harness",
                          objective="Implement isolated harness and local verification; no model sessions",
                          next_step="implement_and_verify_locally", request_key="v02-harness")
        task = await call("get_task", task_id=task["id"])
        task = await call("claim_task", task_id=task["id"], expected_revision=task["revision"], lease_seconds=7200)
        if finish:
            claim = await call("add_claim", subject="v0.2", predicate="local_infrastructure", object="verified_model_unproven")
            await call("add_evidence", claim_id=claim["id"], expected_revision=claim["revision"], stance="supports",
                       reference=str(ROOT / "artifacts" / "VERIFICATION.txt"),
                       note="Local commands and literal results in verification ledger. Model pilot not run.")
            await call("finish_task", task_id=task["id"], expected_revision=task["revision"],
                       result="Implementation and local tests complete; model pilot requires approved offline runtime and separate authorization.")
        else:
            await call("checkpoint_task", task_id=task["id"], expected_revision=task["revision"], release=True,
                       result="Isolated source copy, lease/revision fixes and deterministic Docker/MCP A-B-C observed.",
                       next_step="finish_negative_controls_runtime_lock_verification_artifacts")
    write_json(state / ("engineering-finished.json" if finish else "engineering-checkpoint.json"), records)
    print("Engineering MCP finish: PASS" if finish else "Engineering MCP checkpoint: PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--finish", action="store_true")
    asyncio.run(coordinate(parser.parse_args().finish))
