"""Narrow E009 capabilities over binary, byte-accounted Continuum MCP."""
import base64
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from .common import PROJECT, server_env
from .e009_revision import memory_envelope
from .e009_sources import verifier_notices

MAX_FRAME = 262144


def frame(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def parse_frame(raw):
    if not raw or len(raw) > MAX_FRAME or not raw.endswith(b"\n"):
        raise ValueError("missing, oversized or unterminated frame")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON number")
    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite JSON number")
        return parsed
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=constant, parse_float=number)


def read_envelope(memory, stage, digest, origin):
    return {"memory": deepcopy(memory), "stage": stage, "sha256": digest,
            "origin": deepcopy(origin), "trust": "unverified_author_assertion"}


def read_size(value):
    # Exactly the bytes delivered on worker stdin, including wrapper and LF.
    return len(frame({"result": value}))


class BinaryMCP:
    """One private MCP subprocess. The worker cannot address this transport."""
    def __init__(self, db, actor, run_id, directory, model="deterministic-fixture"):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        self.log = (directory / "wire.jsonl").open("xb")
        self.stderr = (directory / "stderr.bin").open("xb")
        self.counts = {"stdin": 0, "stdout": 0}
        self.counter = 0
        self.process = subprocess.Popen(
            [sys.executable, "-m", "continuum.mcp_server"], cwd=PROJECT,
            env=server_env(db, actor, run_id, model),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr)
        self.inbox = queue.Queue(maxsize=32)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                   "clientInfo": {"name": "e009-binary-broker", "version": "1"}})
            self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            self.rpc("tools/list", {})
        except BaseException:
            self.close()
            raise

    def _read(self):
        while True:
            raw = self.process.stdout.readline(MAX_FRAME + 1)
            try:
                self.inbox.put(raw, timeout=35)
            except queue.Full:
                return
            if not raw or len(raw) > MAX_FRAME:
                return

    def record(self, direction, raw):
        self.counts[direction] += len(raw)
        self.log.write(frame({"direction": direction, "bytes": len(raw),
                              "base64": base64.b64encode(raw).decode("ascii"),
                              "monotonic_ns": time.monotonic_ns()}))
        self.log.flush()

    def send(self, value):
        raw = frame(value)
        if len(raw) > MAX_FRAME:
            raise ValueError("MCP request too large")
        self.process.stdin.write(raw)
        self.process.stdin.flush()
        self.record("stdin", raw)

    def rpc(self, method, params):
        self.counter += 1
        self.send({"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params})
        deadline = time.monotonic() + 30
        while True:
            raw = self.inbox.get(timeout=max(0.001, deadline - time.monotonic()))
            self.record("stdout", raw)
            value = parse_frame(raw)
            if value.get("id") != self.counter:
                if time.monotonic() >= deadline:
                    raise TimeoutError("MCP reply deadline")
                continue
            if "error" in value or value.get("result", {}).get("isError"):
                raise RuntimeError("MCP rejected request; see private binary trace")
            return value["result"]

    def tool(self, name, **arguments):
        value = self.rpc("tools/call", {"name": "continuum_" + name, "arguments": arguments})
        if "structuredContent" in value:
            return value["structuredContent"]
        return json.loads(value["content"][0]["text"])

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.reader.join(timeout=2)
        while not self.inbox.empty():
            raw = self.inbox.get_nowait()
            if raw:
                self.record("stdout", raw)
        self.process.stdin.close()
        self.process.stdout.close()
        self.stderr.close()
        self.log.close()


class MemoryBroker:
    """One assigned stage, no arbitrary hashes, filesystem, shell or private score reads."""
    def __init__(self, transport, stage, condition, actor, registry, *,
                 task_id=None, seed=None, budget=8192):
        if stage not in tuple("ABCDE") or condition not in {"F0", "F1", "S0", "S1", "C0"}:
            raise ValueError("unsupported broker assignment")
        if type(budget) is not int or not 1 <= budget <= 8192:
            raise ValueError("invalid read limit")
        self.transport, self.stage, self.condition = transport, stage, condition
        self.actor, self.registry, self.budget = actor, registry, budget
        self.reads = self.attempts = self.verifications = 0
        self.committed = False
        if task_id is None:
            if stage != "A":
                raise ValueError("successor requires existing task identity")
            self.task = transport.tool("create_task", title="E009 isolated episode",
                objective="Preserve author assertions, not verified truth",
                next_step="A", request_key=actor)
            index = {}
        else:
            self.task = transport.tool("get_task", task_id=task_id)
            index = json.loads(self.task["result"]) if self.task["result"] else {}
        if stage == "A" and index:
            raise ValueError("A cannot overwrite an existing episode")
        previous = chr(ord(stage) - 1) if stage != "A" else None
        if previous and index.get("stage") != previous:
            raise ValueError("missing, repeated or out-of-order checkpoint")
        if index and index.get("condition") != condition:
            raise ValueError("condition differs from existing assignment")
        self.index = index
        if condition == "C0":
            self.previous = read_envelope(None, None, None, None)
        elif previous:
            obj, packet = self.get(index["memory_sha256"])
            if packet["stage"] != previous or packet["actor"] != obj["origin"]["actor"]:
                raise ValueError("predecessor binding mismatch")
            self.previous = read_envelope(packet["memory"], previous, index["memory_sha256"], obj["origin"])
        else:
            self.previous = read_envelope(seed, None, None, {"actor": "registered-input-history"} if seed else None)
        if read_size(self.previous) > budget:
            raise ValueError("assigned read envelope exceeds limit")

    def get(self, digest):
        obj = self.transport.tool("get_object", sha256=digest)
        raw = base64.b64decode(obj["content_base64"], validate=True)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("object integrity mismatch")
        return obj, parse_frame(raw)

    def put(self, value):
        raw = frame(value)
        if len(raw) > 65536:
            raise ValueError("private or public object exceeds storage limit")
        digest = hashlib.sha256(raw).hexdigest()
        obj = self.transport.tool("put_object", content_base64=base64.b64encode(raw).decode("ascii"),
                                  sha256=digest, media_type="application/json")
        # Use metadata returned by the actual server, never client-declared provenance.
        if obj["origin"]["actor"] != self.actor:
            raise ValueError("object author differs from assigned instance")
        return digest, obj

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        if name == "read_memory" and not arguments:
            if self.reads:
                raise PermissionError("one memory read per context")
            self.reads += 1
            return deepcopy(self.previous)
        if name == "verify_source" and set(arguments) == {"record"} and isinstance(arguments["record"], dict):
            if self.verifications >= 3:
                raise PermissionError("verification quota")
            self.verifications += 1
            return {"valid": self.registry.verify_source(arguments["record"], self.stage)}
        if (name == "verify_references" and self.condition in {"F1", "S1"}
                and set(arguments) == {"claims"} and isinstance(arguments["claims"], list)):
            if self.verifications >= 3:
                raise PermissionError("verification quota")
            self.verifications += 1
            return {"notices": verifier_notices(arguments["claims"], self.registry.view(self.stage))}
        if name == "publish" and set(arguments) == {"published_memory", "measurement"}:
            return self.publish(arguments["published_memory"], arguments["measurement"])
        raise PermissionError("outside assigned capabilities")

    def publish(self, memory, measurement):
        if self.stage == "E" or not self.reads or self.committed or self.attempts >= 2:
            raise PermissionError("invalid publication transition")
        self.attempts += 1
        if (not isinstance(memory, dict) or set(memory) != {"format", "payload"}
                or not isinstance(measurement, dict)):
            raise ValueError("explicit public memory and separate private measurement required")
        representation = "S" if self.condition.startswith("S") else "F"
        if memory["format"] != representation:
            raise ValueError("assigned memory representation required")
        memory_envelope(memory["payload"], representation, limit=self.budget)
        packet = {"schema": "e009-public-memory-v1", "stage": self.stage,
                  "actor": self.actor, "memory": memory}
        # Validate both objects before starting a durable write.
        private = {"stage": self.stage, "actor": self.actor, "measurement": measurement}
        if len(frame(private)) > 65536:
            raise ValueError("measurement storage limit")
        digest, obj = self.put(packet)
        size = read_size(read_envelope(memory, self.stage, digest, obj["origin"]))
        if size > self.budget:
            # Immutable orphan remains traceable; no checkpoint pointer is changed.
            return {"saved": False, "reason": "complete_read_envelope_limit",
                    "read_bytes": size, "budget": self.budget, "attempts_left": 2 - self.attempts}
        private_digest, _ = self.put(private)
        task = self.transport.tool("claim_task", task_id=self.task["id"],
                                   expected_revision=self.task["revision"], lease_seconds=120)
        index = {"stage": self.stage, "condition": self.condition,
                 "memory_sha256": digest, "measurement_sha256": private_digest,
                 "parent_memory_sha256": self.index.get("memory_sha256")}
        self.task = self.transport.tool("checkpoint_task", task_id=task["id"],
            expected_revision=task["revision"], release=True,
            result=frame(index).decode().strip(), next_step=chr(ord(self.stage) + 1))
        self.index, self.committed = index, True
        return {"saved": True, "stage": self.stage, "sha256": digest, "read_bytes": size}
