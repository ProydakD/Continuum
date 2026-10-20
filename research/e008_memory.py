"""Actual append-only Continuum state; narrow public tools, no oracle access."""
import base64
import hashlib
import json

from .e002_memory import MemoryBridge
from .e008_protocol import canonical, read_bytes, read_result, snapshot_value, source_ids


class KnowledgeArchive(MemoryBridge):
    def index(self):
        tasks = self.tool("bootstrap")["open_tasks"]
        if not tasks:
            return None, {}
        if len(tasks) != 1:
            raise ValueError("ambiguous E008 knowledge archive")
        task = self.tool("get_task", task_id=tasks[0]["id"])
        return task, json.loads(task["result"]) if task["result"] else {}

    def get(self, key):
        _, index = self.index()
        if key not in index:
            return None
        sha = index[key]
        obj = self.tool("get_object", sha256=sha)
        raw = base64.b64decode(obj["content_base64"], validate=True)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("knowledge object digest mismatch")
        return json.loads(raw)

    def put(self, key, value, *, model_memory=False):
        task, index = self.index()
        if key in index:
            raise ValueError("immutable knowledge slot already exists")
        if task is None:
            task = self.tool("create_task", title="E008 causal knowledge archive",
                objective="Preserve attributed evidence and immutable hypotheses; model claims are not verified facts.",
                next_step="registered fresh investigator", request_key="e008-archive")
        task = self.tool("claim_task", task_id=task["id"], expected_revision=task["revision"], lease_seconds=600)
        raw = canonical(value)
        sha = hashlib.sha256(raw).hexdigest()
        self.tool("put_object", content_base64=base64.b64encode(raw).decode(), sha256=sha, media_type="application/json")
        if model_memory:
            claim = self.tool("add_claim", subject=sha, predicate="model_authored_causal_knowledge", object=value["stage"],
                              request_key="e008-state-" + value["stage"])
            self.tool("add_evidence", claim_id=claim["id"], expected_revision=claim["revision"], stance="supports",
                      reference="sha256:" + sha, sha256=sha,
                      note="Provenance of model-authored bytes only, NOT independent confirmation of causal claims.")
        index[key] = sha
        self.tool("checkpoint_task", task_id=task["id"], expected_revision=task["revision"], release=True,
                  result=json.dumps(index, sort_keys=True), next_step="registered fresh investigator")
        return sha


class InvestigatorBridge(KnowledgeArchive):
    def configure(self, job):
        self.job = job
        self.read_counts = {"read_protocol": 0, "read_memory": 0}
        self.attempts = self.verifications = 0
        self.saved = False
        self.previous_stage = {"B": "A", "C": "B", "D": "C"}.get(job["stage"])
        if job["condition"] in ("C0", "FULL-JOURNAL", "SINGLE-A", "SINGLE-B"):
            self.previous_stage = None
        _, self.initial_index = self.index()
        if "state:" + job["stage"] in self.initial_index:
            raise ValueError("context stage already committed; never repeat")
        if self.previous_stage and "state:" + self.previous_stage not in self.initial_index:
            raise ValueError("required predecessor snapshot missing")
        self.parent_sha = self.initial_index.get("state:" + self.previous_stage) if self.previous_stage else None

    def bounded_read(self, name):
        if self.read_counts[name] >= 2:
            raise ValueError("read quota exceeded")
        self.read_counts[name] += 1

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        if name == "read_protocol" and arguments == {}:
            self.bounded_read(name)
            value = self.get("protocol") if self.job.get("protocol_version") else None
            if self.job.get("protocol_version") and (value is None or value["version"] != self.job["protocol_version"]):
                raise ValueError("wrong or unavailable assigned agreement")
            return {"protocol": value}
        if name == "read_memory" and arguments == {}:
            self.bounded_read(name)
            previous = self.get("state:" + self.previous_stage) if self.previous_stage else None
            result = read_result(previous)
            if result["sha256"] != self.parent_sha:
                raise ValueError("frozen predecessor reference changed")
            if previous is not None and (previous["stage"] != self.previous_stage or len(read_bytes(previous)) > self.job["budget"]):
                raise ValueError("predecessor stage/byte ceiling mismatch")
            return result
        if name == "verify_evidence" and set(arguments) == {"record"} and isinstance(arguments["record"], dict):
            if self.verifications >= 3:
                raise ValueError("source authentication quota exceeded")
            self.verifications += 1
            identity = arguments["record"].get("id")
            if not isinstance(identity, str) or identity not in source_ids(self.job):
                return {"reference": identity if isinstance(identity, str) else None, "available": False, "valid": None}
            if self.job.get("verification_disabled"):
                return {"reference": identity, "available": False, "valid": None}
            actual = self.get("source:" + identity)
            if actual is None:
                raise ValueError("registered authorized source missing")
            # No corrective table, hypothesis, hidden truth or gold answer returned.
            return {"reference": identity, "available": True, "valid": canonical(actual) == canonical(arguments["record"])}
        if (name == "save_memory" and self.job["stage"] != "D" and set(arguments) == {"content", "encoding"}
                and isinstance(arguments["content"], str) and arguments["encoding"] in ("utf8", "base64")):
            if not all(self.read_counts.values()) or self.saved or self.attempts >= 2:
                raise ValueError("invalid checkpoint transition")
            self.attempts += 1
            try:
                value = snapshot_value(arguments["content"], arguments["encoding"], self.job["stage"], self.actor, self.parent_sha)
            except ValueError:
                return {"saved": False, "reason": "invalid_encoding_or_empty", "bytes": None, "budget": self.job["budget"],
                        "attempts_left": 2 - self.attempts}
            size = len(read_bytes(value))
            if size > self.job["budget"]:
                return {"saved": False, "reason": "byte_ceiling", "bytes": size, "budget": self.job["budget"],
                        "attempts_left": 2 - self.attempts}
            sha = self.put("state:" + self.job["stage"], value, model_memory=True)
            self.saved = True
            return {"saved": True, "bytes": size, "sha256": sha}
        raise PermissionError("tool outside investigator capability")

    def finish(self, answer):
        if not all(self.read_counts.values()):
            raise ValueError("investigator did not retrieve assigned state")
        expected = "not_applicable" if self.job["stage"] == "D" else "saved" if self.saved else "not_saved"
        if not isinstance(answer, dict) or answer.get("save_status") != expected:
            raise ValueError("final save_status not bound to MCP state")
        if self.job["stage"] != "D" and self.attempts == 0:
            raise ValueError("investigator never attempted a checkpoint")
