"""Cold-process deterministic MCP transport fixture, NOT a model/security experiment."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from .common import PROJECT, server_env
from .preflight import content
from .e009_revision import canonical


async def worker(input_path, output_path):
    spec = json.loads(Path(input_path).read_text(encoding="utf-8"))
    records = []
    params = StdioServerParameters(command=sys.executable, args=["-m", "continuum.mcp_server"], cwd=PROJECT,
                                  env=server_env(spec["db"], spec["actor"], "e009-offline-handoff"))
    async with Client(params, read_timeout_seconds=30) as client:
        async def call(name, **args):
            response = await client.call_tool("continuum_" + name, args)
            result = content(response)
            records.append({"tool": "continuum_" + name, "input": args,
                            "sdk_response": response.model_dump(mode="json", by_alias=True)})
            if response.is_error:
                raise RuntimeError(result)
            return result

        await call("bootstrap")
        task = await call("create_task", title="E009 deterministic storage fixture " + spec["actor"],
                          objective="Transport state only; not a model knowledge result",
                          next_step="publish one immutable object", request_key=spec["actor"])
        task = await call("get_task", task_id=task["id"])
        task = await call("claim_task", task_id=task["id"], expected_revision=task["revision"], lease_seconds=60)
        previous, parent_actor = {"events": []}, None
        if spec["parent_sha256"]:
            stored = await call("get_object", sha256=spec["parent_sha256"])
            raw = base64.b64decode(stored["content_base64"], validate=True)
            assert hashlib.sha256(raw).hexdigest() == spec["parent_sha256"]
            previous = json.loads(raw)
            parent_actor = stored["origin"]["actor"]
        value = {"events": previous["events"] + [spec["event"]], "parent_sha256": spec["parent_sha256"]}
        raw = canonical(value)
        digest = hashlib.sha256(raw).hexdigest()
        stored = await call("put_object", content_base64=base64.b64encode(raw).decode(), sha256=digest,
                            media_type="application/json")
        assert stored["origin"]["actor"] == spec["actor"]
        if not spec["crash_after_commit"]:
            await call("finish_task", task_id=task["id"], expected_revision=task["revision"],
                       result="Stored deterministic fixture object " + digest)
        result = {"actor": spec["actor"], "pid": os.getpid(), "sha256": digest, "payload": value,
                  "parent_actor": parent_actor, "committed": True,
                  "acknowledged": not spec["crash_after_commit"], "records": records,
                  "decoded_sdk_json_bytes": sum(len(canonical(r)) for r in records),
                  "payload_bytes": len(raw), "model_calls": 0,
                  "isolation": "fresh host process; NOT filesystem/network sandbox certification"}
        # Output exists before nonzero exit: models/queue must not be retried just because ack is absent.
        with Path(output_path).open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(json.dumps({k: result[k] for k in ("actor", "pid", "sha256", "committed", "acknowledged")}), flush=True)
    return 17 if spec["crash_after_commit"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(worker(args.input, args.output)))
