"""Deterministic integration driver, deliberately NOT a model capability test."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

proxy = subprocess.Popen([sys.executable, "/runtime/proxy.py"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, text=True, encoding="utf-8")
counter = 0


def rpc(method, params):
    global counter
    counter += 1
    proxy.stdin.write(json.dumps({"jsonrpc": "2.0", "id": counter, "method": method, "params": params}) + "\n")
    proxy.stdin.flush()
    while True:
        line = proxy.stdout.readline()
        if not line:
            raise RuntimeError("MCP disconnected")
        response = json.loads(line)
        if response.get("id") == counter:
            if "error" in response:
                raise RuntimeError(response["error"])
            return response["result"]


def tool(name, **arguments):
    result = rpc("tools/call", {"name": "continuum_" + name, "arguments": arguments})
    if result.get("isError"):
        raise RuntimeError(result)
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


try:
    rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "continuum-fixture", "version": "0.2.0"}})
    proxy.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
    proxy.stdin.flush()
    tools = rpc("tools/list", {})
    state = tool("bootstrap")
    stage = sys.argv[1]
    if stage == "A":
        values = json.loads(Path("/workspace/input.json").read_text())["values"]
        task = tool("create_task", title="Square sum", objective="Independently recompute sum of squares",
                    next_step="measure", request_key="square-sum")
    else:
        tasks = state["open_tasks"]
        if len(tasks) != 1:
            print(json.dumps({"status": "needs_context", "stage": stage, "inherited": False}))
            sys.exit(0)
        task = tool("get_task", task_id=tasks[0]["id"])
        try:
            checkpoint = json.loads(task["result"])
            if checkpoint["stage"] != ("A" if stage == "B" else "B"):
                raise ValueError("wrong predecessor")
            obj = tool("get_object", sha256=checkpoint["object_sha256"])
            payload = base64.b64decode(obj["content_base64"], validate=True)
            if hashlib.sha256(payload).hexdigest() != obj["sha256"]:
                raise ValueError("hash mismatch")
            values = json.loads(payload)["values"]
        except (ValueError, KeyError, TypeError):
            print(json.dumps({"status": "needs_context", "stage": stage, "inherited": False}))
            sys.exit(0)
    leased = tool("claim_task", task_id=task["id"], expected_revision=task["revision"], lease_seconds=600)
    leased = tool("renew_lease", task_id=task["id"], expected_revision=leased["revision"], lease_seconds=7200)
    content = json.dumps({"values": values}, sort_keys=True).encode()
    sha = hashlib.sha256(content).hexdigest()
    tool("put_object", content_base64=base64.b64encode(content).decode(), sha256=sha, media_type="application/json")
    total = sum(v*v for v in values)
    claim = tool("add_claim", subject=sha, predicate="sum_of_squares", object=str(total), request_key="sum-claim")
    claim = tool("get_claim", claim_id=claim["id"])
    tool("add_evidence", claim_id=claim["id"], expected_revision=claim["revision"], stance="supports",
         reference="sha256:" + sha, sha256=sha, note=f"{stage}: deterministic recomputation, not model evidence")
    result = json.dumps({"stage": stage, "total": total, "object_sha256": sha, "claim_id": claim["id"]})
    leased = tool("get_task", task_id=task["id"])
    if stage == "C":
        tool("finish_task", task_id=task["id"], result=result, expected_revision=leased["revision"])
    else:
        tool("checkpoint_task", task_id=task["id"], next_step="verify_b" if stage == "A" else "verify_c",
             result=result, expected_revision=leased["revision"], release=True)
    print(json.dumps({"status": "completed_stage", "stage": stage, "total": total, "inherited": stage != "A"}))
finally:
    proxy.terminate()
    proxy.wait(timeout=5)
