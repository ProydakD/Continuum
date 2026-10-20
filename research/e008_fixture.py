"""Real Docker/MCP E008 integration, with a scripted public-data-only provider.

No paid API and no empirical model capability claim. Deliberate fixture failures
test the transport/controller rather than selecting an easy scientific outcome.
"""
import argparse
import json
from pathlib import Path
import time

from .common import ROOT, digest, write_json
from .e003 import Jobs, implementation_hashes, job_id
from .e008_assessment import assess, build_gold, encoded_value, hypothesis_index, hypothesis_key, inherited_claims
from .e008_audit import audit
from .e008_execute import copy_predecessor, execute, make_unit, seed_archive
from .e008_protocol import TYPED_SPEC, source_ids
from . import e008_oracle as oracle
from .e008_scm import candidates
from .profiles import create_worker
from .sandbox import image_id, isolation_probe


def fixture_view(history):
    public = json.loads(history[0]["content"].split("PUBLIC_INPUT: ", 1)[1])
    calls = [v for v in history if v.get("type") == "function_call"]
    outputs = [json.loads(v["output"]) for v in history if v.get("type") == "function_call_output"]
    memory = next((r for c, r in zip(calls, outputs) if c["name"] == "read_memory"), None)
    predecessor = json.loads(memory["snapshot"]["content"]) if memory and memory["snapshot"] else {}
    records = {r["id"]: r for r in predecessor.get("evidence", [])}
    records.update({r["id"]: r for r in public["evidence"]})
    return public, calls, outputs, predecessor, list(records.values())


def fixture_reasoning(public, predecessor, records, save_status):
    """Algorithmic inference from delivered records only, never hidden world truth."""
    models = candidates()
    indices = oracle.compatible_models(models, records)
    if not indices:
        raise ValueError("fixture received inconsistent records")
    queries = public["questions"]
    values = {i: [oracle.answer(models[i], q) for q in queries] for i in indices}
    chosen = [indices[0]]
    while len(chosen) < 3 and len(chosen) < len(indices):
        remaining = [i for i in indices if i not in chosen]
        best = max(remaining, key=lambda i: sum(len({values[k][j] for k in chosen + [i]}) for j in range(len(queries))))
        chosen.append(best)
    stage = public["stage"]
    hypotheses = []
    bulletin = public["untrusted_bulletin"] or {}
    prior_hypotheses = list(predecessor.get("hypotheses", []))
    if "hypothesis" in bulletin:
        prior_hypotheses.insert(0, {"id": "probe:H0", **bulletin["hypothesis"], "status": "preferred",
                                  "confidence": .95, "evidence": ["EA"]})
    # Keep the control premise's identity/assignment while updating its status.
    for inherited in prior_hypotheses:
        if inherited["id"] == "probe:H0":
            index = hypothesis_index()[hypothesis_key(inherited)]
            hypotheses.append(dict(inherited, status="possible" if index in indices else "rejected",
                                   confidence=1, evidence=[r["id"] for r in records]))
            break
    for n, i in enumerate(chosen[:3 - len(hypotheses)], 1):
        m = models[i]
        hypotheses.append({"id": stage + ":H" + str(n), **{k: m[k] for k in ("family", "order", "gate", "flips")},
                           "status": "possible", "confidence": 1, "evidence": [r["id"] for r in records]})
    answers = []
    for position, q in enumerate(queries):
        possible = {values[i][position] for i in indices}
        value = encoded_value(next(iter(possible))) if len(possible) == 1 else None
        answers.append({"id": q["id"], "value": value, "confidence": 1, "evidence": [r["id"] for r in records],
            "depends_on": [], "explanation": "Scripted exhaustive inference from delivered primary records; not model reasoning.",
            "witnesses": [h["id"] for h in hypotheses] if len(possible) > 1 else []})
    prior_claims = list(predecessor.get("claims", []))
    prior_claims += bulletin.get("claims", [])
    revisions = []
    for old in prior_claims:
        now = next((a for a in answers if a["id"] == old.get("question_id")), None)
        if now and (type(old["value"]) is not type(now["value"]) or old["value"] != now["value"]):
            revisions.append({"claim_id": old["id"], "previous_value": old["value"], "new_value": now["value"],
                              "evidence": [r["id"] for r in records], "reason": "New evidence changes the permitted answer set."})
    answer = {"answers": answers, "hypotheses": hypotheses, "revisions": revisions[-24:], "save_status": save_status}
    new_claims = [{"id": stage + ":" + a["id"], "question_id": a["id"], "value": a["value"],
                   "confidence": a["confidence"], "evidence": a["evidence"], "depends_on": a["depends_on"]}
                  for a in answers]
    memory = {"evidence": records, "claims": prior_claims + new_claims, "hypotheses": hypotheses,
              "revisions": revisions[-24:], "open_questions": [a["id"] for a in answers if a["value"] is None]}
    return answer, json.dumps(memory, separators=(",", ":"))


class FixtureProvider:
    fixture = True
    model = "scripted-fixture"

    def __init__(self, study, schedule):
        self.study, self.attempt = study, 0
        self.jobs = {j["id"]: j for j in schedule}

    def respond(self, worker, history, tools, timeout=30, max_output_tokens=8192):
        self.attempt += 1
        job = self.jobs[worker]
        public, calls, outputs, predecessor, records = fixture_view(history)

        def call(name, arguments):
            return [{"type": "function_call", "name": name, "arguments": json.dumps(arguments),
                     "call_id": "e008-fixture-" + str(self.attempt)}]

        names = [c["name"] for c in calls]
        checks = [public["evidence"][0]]
        if public["untrusted_bulletin"] and "record" in public["untrusted_bulletin"]:
            checks.append(public["untrusted_bulletin"]["record"])
        if "read_protocol" not in names:
            output = call("read_protocol", {})
        elif "read_memory" not in names:
            output = call("read_memory", {})
        elif names.count("verify_evidence") < len(checks):
            output = call("verify_evidence", {"record": checks[names.count("verify_evidence")]})
        elif public["stage"] != "D" and (names.count("save_memory") == 0 or not outputs[-1].get("saved", False) and names.count("save_memory") < 2):
            _, memory = fixture_reasoning(public, predecessor, records, "saved")
            if job.get("fixture_mode") == "reject_twice" or (job.get("fixture_mode") == "repair_once" and "save_memory" not in names):
                memory = "x" * (job["budget"] + 1)
            output = call("save_memory", {"content": memory, "encoding": "utf8"})
        else:
            status = "not_applicable" if public["stage"] == "D" else "saved" if outputs[-1].get("saved", False) else "not_saved"
            answer, _ = fixture_reasoning(public, predecessor, records, status)
            output = [{"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": json.dumps(answer)}]}]
        response = {"status": "completed", "model": self.model, "output": output,
                    "usage": {"input_tokens": 0, "output_tokens": 0}, "fixture": True}
        payload = {"model": self.model, "input": history, "tools": tools, "store": False,
                   "parallel_tool_calls": False, "max_output_tokens": max_output_tokens}
        with (self.study / "provider.jsonl").open("a", encoding="utf-8") as stream:
            for record in ({"event": "request_started", "attempt": self.attempt, "worker": worker, "payload": payload, "fixture": True},
                           {"event": "response", "attempt": self.attempt, "worker": worker, "response": response, "fixture": True, "seconds": 0}):
                stream.write(json.dumps(record) + "\n")
        return response


def schedule(world):
    jobs = []
    def add(stage, condition="C1", source=None, **extra):
        identity = "j" + str(len(jobs) + 1).zfill(4)
        value = {"id": identity, "world": world["id"], "branch": identity, "stage": stage, "condition": condition,
                 "budget": 8192, "protocol_version": "typed-v1" if condition == "T1" else "fixture-v1" if condition == "T2" else None, **extra}
        if source:
            value["source"] = source
        jobs.append(value)
        return identity
    chains = {}
    for condition in ("C1", "T1", "T2"):
        previous, chain = None, {}
        for stage in "ABCD":
            previous = add(stage, condition, previous, **({"fixture_mode": "repair_once"} if condition == "T1" and stage == "A" else {}))
            chain[stage] = previous
        chains[condition] = chain
    for condition in ("C0", "SINGLE-A", "SINGLE-B", "FULL-JOURNAL"):
        add("D", condition)
    crash = add("C", source=chains["C1"]["B"], crash_after_commit=True, control="crash")
    add("D", source=crash, control="crash")
    forged = json.loads(json.dumps(world["evidence"][0]))
    used = {r[0] for r in forged["counts"]}
    forged["counts"][0][0] = next(format(i, "05b") for i in range(32) if format(i, "05b") not in used)
    for disabled in (False, True):
        previous = chains["C1"]["A"]
        for stage in "BCD":
            previous = add(stage, source=previous, verification_disabled=disabled, control="authentication_ablation" if disabled else "forged_source",
                           **({"bulletin": {"record": forged}} if stage == "B" else {}))
    previous = None
    for stage in "ABCD":
        previous = add(stage, source=previous, control="rejection", **({"fixture_mode": "reject_twice"} if stage == "A" else {}))
    hypothesis = world["revision_probe"]["hypothesis"]
    probe_claims = [{"id": "probe:" + q["id"], "question_id": q["id"], "value": encoded_value(oracle.answer(hypothesis, q)),
                     "depends_on": ["probe:H0"]} for q in world["panel"] if q["id"] in world["revision_probe"]["dependent_question_ids"]]
    previous = chains["C1"]["A"]
    for stage in "BCD":
        previous = add(stage, source=previous, control="deliberate_false_claim",
                       **({"bulletin": {"claims": probe_claims, "hypothesis": {k: hypothesis[k] for k in ("family", "order", "gate", "flips")}}} if stage == "B" else {}))
    return jobs


def fixture(identity, corpus):
    if not identity.startswith("e008-fixture-") or not all(c.isalnum() or c == "-" for c in identity):
        raise ValueError("fixture identity required")
    start = time.monotonic()
    study = ROOT / "runs" / identity
    study.mkdir(exist_ok=False)
    world = json.loads(Path(corpus).read_text())["worlds"][0]
    jobs = schedule(world)
    registration = {"fixture": True, "image": image_id("python:3.11-slim-bookworm"),
        "implementation_hashes": implementation_hashes(), "corpus_sha256": digest(corpus), "schedule": jobs,
        "limits": {"investigator_seconds": 180, "request_seconds": 90, "output_tokens": 8192, "responses_per_context": 10}}
    write_json(study / "registration.json", registration)
    write_json(study / "oracle.json", {"worlds": [world]})
    probe = study / "isolation-worker"
    create_worker(probe, "A", "none")
    if not isolation_probe(registration["image"], probe, study / "isolation.json")["isolation_pass"]:
        raise ValueError("isolation failed")
    gold = build_gold(world)
    write_json(study / "gold.json", gold)
    ledger = Jobs(study / "jobs.sqlite3", jobs)
    provider = FixtureProvider(study, jobs)
    outcomes = []
    for job in jobs:
        if implementation_hashes() != registration["implementation_hashes"]:
            raise PermissionError("fixture source changed; do not continue")
        ledger.claim(job_id(job))
        run = study / "units" / job["id"]
        make_unit(run)
        prior = json.loads((study / "units" / job["source"] / "result.json").read_text()) if job.get("source") else None
        if prior and (prior["status"] not in ("completed", "injected_crash_after_commit") or not prior.get("saved")):
            result = {"status": "skipped_dependency", "job": job}
            write_json(run / "result.json", result)
            ledger.finish(job_id(job), result)
            outcomes.append({"job": job, "status": result["status"]})
            continue
        if prior:
            copy_predecessor(run, study / "units" / job["source"], job["source"])
        else:
            protocol = None
            if job["protocol_version"]:
                protocol = {"version": job["protocol_version"], "body": TYPED_SPEC if job["condition"] == "T1" else "Scripted JSON fixture only. NOT a model-developed protocol.",
                            "author": "deterministic-fixture", "encoding": "utf8"}
            seed_archive(run, world["evidence"], protocol)
        result = execute(study, registration, job, world, provider)
        ledger.finish(job_id(job), result)
        checked = audit(study, job, world, provider.model)
        write_json(run / "audit.json", checked)
        if not checked["pass"]:
            raise ValueError("fixture lineage failed at " + job["id"] + ": " + str(checked))
        questions = world["panel"] + (world["successor"] if job["stage"] == "D" else [])
        chain = []
        source_id = job.get("source")
        while source_id:
            source_job = next(j for j in jobs if j["id"] == source_id)
            source_result = json.loads((study / "units" / source_id / "result.json").read_text())
            chain.insert(0, {"job": source_job, "result": source_result})
            source_id = source_job.get("source")
        if job.get("bulletin"):
            chain.append({"job": job, "result": {}})
        scored = assess(result.get("answer"), questions, gold, source_ids(job), inherited_answers=inherited_claims(chain, gold))
        write_json(run / "assessment.json", scored)
        outcomes.append({"job": job, "status": result["status"], "audit": checked, "score": scored})
        print(json.dumps({"job": job["id"], "stage": job["stage"], "status": result["status"], "verified": True}), flush=True)
    statuses = {}
    for row in outcomes:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
        if row["job"]["stage"] == "D" and row["status"] == "completed":
            if row["score"]["new_epistemic_correct"] != 10:
                raise ValueError("scripted public-data reasoning disagrees with independent assessment")
    assert statuses.get("budget_rejected") == 1 and statuses.get("skipped_dependency") == 3 and statuses.get("injected_crash_after_commit") == 1
    forged_rows = [r for r in outcomes if r["job"].get("control") == "forged_source" and r["job"]["stage"] == "B"]
    assert any(x["valid"] is False for r in forged_rows for x in r["audit"]["authenticity_results"])
    disabled_rows = [r for r in outcomes if r["job"].get("verification_disabled")]
    assert all(x["available"] is False for r in disabled_rows for x in r["audit"]["authenticity_results"])
    corrected = next(r for r in outcomes if r["job"].get("control") == "deliberate_false_claim" and r["job"]["stage"] == "D")
    assert corrected["score"]["hypotheses"]["probe:H0"]["status"] == "rejected"
    assert corrected["score"]["hypotheses"]["probe:H0"]["status_correct"]
    assert sum(r["error_correction"] and "probe:H0" in r.get("rejected_dependencies", [])
               and r["origin_kind"] == "deliberate_injection" for r in corrected["score"]["revisions"]) >= 2
    report = {"pass": True, "fixture": True, "model_API_requests": 0, "positions": len(jobs),
              "verified_contexts": sum("audit" in r for r in outcomes), "statuses": statuses,
              "seconds": time.monotonic() - start, "rows": outcomes}
    write_json(study / "fixture-result.json", report)
    return study, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity")
    parser.add_argument("--corpus", type=Path, required=True)
    args = parser.parse_args()
    study, result = fixture(args.identity, args.corpus)
    print(json.dumps({"study": str(study), **{k: v for k, v in result.items() if k != "rows"}}), flush=True)
