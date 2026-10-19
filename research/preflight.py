import asyncio
import hashlib
import json
from pathlib import Path
import sys
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from .common import PROJECT, command, server_env, write_json
from .profiles import load_manifest
from .sandbox import isolation_probe, container_command


def content(result):
    payload = result.model_dump(by_alias=True, mode="json")
    if payload.get("isError"):
        raise RuntimeError(payload)
    return payload.get("structuredContent") or json.loads(payload["content"][0]["text"])


async def mcp_check(run):
    params = StdioServerParameters(command=sys.executable, args=["-m", "continuum.mcp_server"],
        cwd=PROJECT, env=server_env(run / "supervisor" / "preflight.sqlite3", "preflight", run.name, role="preflight"))
    transcript = []
    async with Client(params, read_timeout_seconds=15) as client:
        catalog = (await client.list_tools()).model_dump(by_alias=True, mode="json")
        write_json(run / "supervisor" / "tool-catalog.json", catalog)

        async def call(name, **kwargs):
            result = await client.call_tool("continuum_" + name, kwargs)
            transcript.append({"tool": name, "input": kwargs, "output": result.model_dump(by_alias=True, mode="json")})
            return result

        initial = content(await call("bootstrap"))
        task = content(await call("create_task", title="Preflight", objective="Verify MCP access",
                                  next_step="checkpoint", request_key="preflight-task"))
        task = content(await call("get_task", task_id=task["id"]))
        if task["status"] == "done":
            raise RuntimeError("preflight DB already used; do not reuse a previous PASS")
        leased = content(await call("claim_task", task_id=task["id"], expected_revision=task["revision"], lease_seconds=7200))
        renewed = content(await call("renew_lease", task_id=task["id"], expected_revision=leased["revision"], lease_seconds=600))
        if renewed["lease_until"] < leased["lease_until"]:
            raise RuntimeError("lease shortened")
        denied = await call("bootstrap", workspace="private")
        stale = await call("finish_task", task_id=task["id"], result="invalid", expected_revision=leased["revision"])
        if not (denied.is_error and stale.is_error):
            raise RuntimeError("scope/revision negative check failed")
        claim = content(await call("add_claim", subject="transport", predicate="works", object="local"))
        evidence = content(await call("add_evidence", claim_id=claim["id"], expected_revision=claim["revision"],
                        stance="supports", reference="test://preflight/transport", note="Observed through SDK subprocess"))
        if evidence["evidence"][0]["actor"] != "preflight":
            raise RuntimeError("provenance mismatch")
        content(await call("finish_task", task_id=task["id"], result="SDK initialize/list/bootstrap/claim/renew/scope/revision PASS",
                           expected_revision=renewed["revision"]))
    write_json(run / "supervisor" / "mcp-preflight.json", transcript)
    return {"pass": True, "initial_cursor": initial["cursor"], "schema_sha256": hashlib.sha256(
        json.dumps(catalog, sort_keys=True).encode()).hexdigest()}


def preflight(run):
    run = Path(run).resolve()
    manifest = load_manifest(run)
    report = {"infrastructure_pass": False, "model_runtime_present": False,
              "code_hashes": manifest["code_hashes"], "model_sessions_started": 0,
              "image": manifest["image"]}
    try:
        probe = isolation_probe(manifest["image"], run / "workers" / "A", run / "supervisor" / "isolation.json")
        report["isolation_pass"] = probe["isolation_pass"]
        observations = probe["observations"]
        report["model_runtime_present"] = observations.get("codex_present", False) and observations.get("ollama_present", False)
        report["mcp"] = asyncio.run(mcp_check(run))
        report["infrastructure_pass"] = report["isolation_pass"] and report["mcp"]["pass"]
        name = "continuum-runtime-" + run.name
        try:
            runtime = command(container_command(manifest["image"], name, run / "workers" / "A",
                ["/runtime/runtime_probe.py", "--model", manifest["model_declared"]], live=True), timeout=45)
        except Exception:
            command(["docker", "rm", "-f", name])
            raise
        write_json(run / "supervisor" / "runtime-probe.json", runtime)
        observed = json.loads(runtime["stdout"]) if runtime["stdout"].strip() else {}
        report["model_runtime_ready"] = runtime["exit_status"] == 0 and observed.get("ready") is True
        report["live_experiment_ready"] = report["infrastructure_pass"] and report["model_runtime_ready"]
        report["authorization"] = "Not granted by preflight; separate explicit model-run authorization required"
        report["live_blockers"] = [] if report["model_runtime_ready"] else [observed.get("blocker", "runtime probe failed")]
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    write_json(run / "supervisor" / "preflight.json", report)
    return report
