"""Real isolated/MCP protocol lifecycle with scripted proposals; not model discovery."""
import argparse
import base64
import copy
import json
from pathlib import Path
import time

from .common import ROOT, digest, write_json
from .e003 import Jobs, implementation_hashes
from .e008_assessment import build_gold
from .e008_audit import snapshot
from .e008_development import development_input, training_projection
from .e008_development_audit import audit
from .e008_execute import execute, ledger_key, ledger_record, make_unit
from .e008_memory import KnowledgeArchive
from .sandbox import image_id


class Provider:
    fixture = True
    model = "scripted-fixture"

    def __init__(self, study, jobs):
        self.study, self.jobs, self.attempt = study, {j["id"]: j for j in jobs}, 0

    def respond(self, worker, history, tools, timeout=30, max_output_tokens=8192):
        self.attempt += 1
        job = self.jobs[worker]
        calls = [c for c in history if c.get("type") == "function_call"]
        outputs = [json.loads(r["output"]) for r in history if r.get("type") == "function_call_output"]
        if not calls:
            name, arguments = "read_development", {}
        elif not outputs[-1].get("saved") and len(calls) < 3:
            if job["role"] == "critic":
                name, arguments = "publish_review", {"content": "Keep competing explanations and earlier authors when revising dependencies."}
            else:
                body = "No required JSON schema. Preserve exact evidence and attributed revisions in a compact notation."
                if job.get("reject_twice") or job.get("repair_once") and len(calls) == 1:
                    body = "x" * 8193
                encoding = "base64" if job.get("binary") else "utf8"
                name, arguments = "publish_protocol", {
                    "body": base64.b64encode(body.encode()).decode() if encoding == "base64" else body,
                    "encoding": encoding, "reason": "Scripted lifecycle test, not a model-developed scientific result."}
        else:
            name = None
            final = {"save_status": "saved" if outputs[-1].get("saved") else "not_saved", "summary": "Fixture only."}
        output = ([{"type": "function_call", "name": name, "arguments": json.dumps(arguments),
                    "call_id": "development-fixture-" + str(self.attempt)}] if name else
                  [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(final)}]}])
        response = {"status": "completed", "model": self.model, "output": output,
                    "usage": {"input_tokens": 0, "output_tokens": 0}, "fixture": True}
        payload = {"model": self.model, "input": history, "tools": tools, "store": False,
                   "parallel_tool_calls": False, "max_output_tokens": max_output_tokens}
        with (self.study / "provider.jsonl").open("a", encoding="utf-8") as stream:
            for event in ({"event": "request_started", "attempt": self.attempt, "worker": worker, "payload": payload},
                          {"event": "response", "attempt": self.attempt, "worker": worker, "response": response, "seconds": 0}):
                stream.write(json.dumps(event) + "\n")
        return response


def fixture(identity, corpus):
    if not identity.startswith("e008-development-fixture-") or not all(c.isalnum() or c == "-" for c in identity):
        raise ValueError("fixture identity required")
    study = ROOT / "runs" / identity
    study.mkdir(exist_ok=False)
    world = json.loads(Path(corpus).read_text())["worlds"][0]
    training = [training_projection(dict(world, split="training"), build_gold(world), "training-01")]
    jobs = []
    for role, lineage, version, mode in (("designer", "L1", 1, "repair_once"), ("critic", "L1", 1, None),
                                       ("designer", "L1", 2, "binary"), ("designer", "L2", 1, None),
                                       ("designer", "L1", 3, "reject_twice")):
        job = {"id": f"dev{len(jobs) + 1:03}", "stage": "A" if role == "designer" else "B",
               "role": role, "condition": "T2", "lineage": lineage, "version": version, "budget": 2048}
        if mode:
            job[mode] = True
        jobs.append(job)
    registration = {"fixture": True, "image": image_id("python:3.11-slim-bookworm"),
                    "implementation_hashes": implementation_hashes(), "schedule": jobs,
                    "limits": {"investigator_seconds": 180, "request_seconds": 90,
                               "output_tokens": 8192, "responses_per_context": 10}}
    write_json(study / "registration.json", registration)
    ledger, provider = Jobs(study / "jobs.sqlite3", [ledger_record(j) for j in jobs]), Provider(study, jobs)
    published, results = {}, []
    started = time.monotonic()
    for job in jobs:
        assert implementation_hashes() == registration["implementation_hashes"], "source changed while fixture active"
        prior_version = job["version"] - (job["role"] == "designer")
        key = f'{job["lineage"]}-v{prior_version}'
        supplied = development_input(job, training, 2048, protocol=published.get("protocol:" + key),
                                      review=published.get("review:" + key),
                                      feedback={"version": key, "note": "Scripted feedback, no validation model series."} if prior_version else None)
        run = study / "units" / job["id"]
        make_unit(run)
        ledger.claim(ledger_key(job))
        with (run / "supervisor/seed.jsonl").open("x", encoding="utf-8") as log:
            bridge = KnowledgeArchive(run, "host", [], log, "registered-development-controller")
            try:
                bridge.put("development_input", supplied)
            finally:
                bridge.close()
        result = execute(study, registration, job, None, provider)
        ledger.finish(ledger_key(job), result)
        checked = audit(study, job, supplied, provider.model)
        write_json(run / "audit.json", checked)
        assert checked["pass"], checked
        _, index, objects = snapshot(run / "state/continuum.sqlite3")
        for slot in index:
            if slot != "development_input":
                published[slot] = json.loads(objects[index[slot]]["content"])
        forged = copy.deepcopy(supplied)
        forged["lineage"] = "L2" if job["lineage"] == "L1" else "L1"
        assert not audit(study, job, forged, provider.model)["pass"]
        results.append({"job": job, "status": result["status"], "verified": True,
                        "wrong_lineage_input_rejected": True})
    assert [r["status"] for r in results] == ["completed"] * 4 + ["budget_rejected"]
    assert "protocol:L1-v3" not in published and published["protocol:L1-v2"]["encoding"] == "base64"
    output = {"pass": True, "fixture": True, "model_API_requests": 0, "positions": len(jobs),
              "seconds": time.monotonic() - started, "rows": results}
    write_json(study / "fixture-result.json", output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity")
    parser.add_argument("--corpus", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(fixture(args.identity, args.corpus)))
