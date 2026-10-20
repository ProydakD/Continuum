"""One durable E008 position at a time, using existing Jobs/MCP/Supervisor.

No model-facing CLI or preregistration is supplied by this module. The final
study runner must freeze the complete protocol, pass live authorization, and
handle recovery/compatibility gates before dispatching these positions.
"""
import copy
import json
from pathlib import Path

from .common import digest
from .e003 import Jobs, implementation_hashes
from .e008_assessment import assess, encoded_value, inherited_claims
from .e008_audit import audit, snapshot
from .e008_development_audit import audit as audit_development
from .e008_execute import copy_predecessor, execute, ledger_key, make_unit, seed_archive
from .e008_locks import DecisionStore, load_outcome, read, seal_outcome, unit_path, write_once
from .e008_memory import KnowledgeArchive
from .e008_network import context_span
from . import e008_oracle as oracle
from .e008_protocol import TYPED_SPEC, source_ids
from .e008_resources import SeriesLedger, SeriesStopped, resource_policy


def resolve_job(store, job):
    resolved = copy.deepcopy(job)
    if job["phase"] in ("test", "robustness"):
        locked = store.protocol_lock()["decision"]
    else:
        locked = None
    if job.get("budget") is None:
        resolved["budget"] = (locked["memory_budget"] if locked else
                              store.calibration_lock()["decision"]["budget"])
    protocol = None
    if job["condition"] == "T1":
        protocol = {"version": "typed-v1", "body": TYPED_SPEC, "encoding": "utf8",
                    "author": "registered-human-fixed"}
    elif job["condition"] == "T2" and job["role"] == "investigator":
        protocol = (locked["lineages"][job["lineage"]]["protocol"] if locked else
                    store.publication(job["lineage"], job["version"]))
        if job.get("protocol_version") is not None:
            if protocol is not None and protocol["version"] != job["protocol_version"]:
                raise PermissionError("publication differs from fixed assigned version")
            # An unavailable proposal is still the assigned version. Preserve it
            # in dependent skips so feedback can verify the frozen assignment.
        else:
            resolved["protocol_version"] = protocol["version"] if protocol else None
    control = job.get("control")
    if control == "crash" and job["stage"] == "C":
        resolved["crash_after_commit"] = True
    if control == "authentication_ablation":
        resolved["verification_disabled"] = True
    if job["stage"] == "B" and control in ("forged_source", "authentication_ablation", "deliberate_false_claim"):
        world = store.worlds[job["world"]]
        if control == "deliberate_false_claim":
            hypothesis = world["revision_probe"]["hypothesis"]
            claims = [{"id": "probe:" + q["id"], "question_id": q["id"],
                       "value": encoded_value(oracle.answer(hypothesis, q)), "depends_on": ["probe:H0"]}
                      for q in world["panel"] if q["id"] in world["revision_probe"]["dependent_question_ids"]]
            resolved["bulletin"] = {"claims": claims,
                                   "hypothesis": {k: hypothesis[k] for k in ("family", "order", "gate", "flips")}}
        else:
            forged = copy.deepcopy(world["evidence"][0])
            used = {r[0] for r in forged["counts"]}
            forged["counts"][0][0] = next(format(i, "05b") for i in range(32) if format(i, "05b") not in used)
            resolved["bulletin"] = {"record": forged}
    return resolved, protocol


def prior_chain(study, job):
    chain = []
    seen = {job["id"]}
    identity = job.get("source")
    while identity:
        if identity in seen:
            raise PermissionError("cyclic predecessor lineage")
        seen.add(identity)
        row = load_outcome(study, identity)
        if row["audit"].get("pass") is not True:
            raise PermissionError("unverified ancestor in scoring history")
        chain.insert(0, {"job": row["job"], "result": row["result"]})
        identity = row["job"].get("source")
    if job.get("bulletin"):
        chain.append({"job": job, "result": {}})
    return chain


def protocol_in_archive(run):
    _, index, objects = snapshot(run / "state/continuum.sqlite3")
    return json.loads(objects[index["protocol"]]["content"]) if "protocol" in index else None


def run_next(study, registration, store, gold, provider, *, guard, authorize_api=False):
    """Dispatch only the first pending assignment, or return None if terminal.

    A controller error becomes a retained terminal failure and stops the caller.
    A live/orphan context, unsealed terminal result or changed input is never
    resolved by replaying a worker.
    """
    study = Path(study)
    if store.study != study or read(study / "registration.json") != registration:
        raise PermissionError("wrong registered study binding")
    store._check_binding()
    if registration["implementation_hashes"] != implementation_hashes():
        raise PermissionError("frozen implementation changed")
    if not isinstance(guard, SeriesLedger) or guard.study != study.resolve():
        raise PermissionError("study-wide durable resource guard required")
    if guard.limits != resource_policy(registration["schedule"]):
        raise PermissionError("guard differs from registered complete schedule")
    fixture = registration["fixture"]
    if fixture != bool(provider and getattr(provider, "fixture", False)):
        if provider is not None:
            raise PermissionError("fixture/live provider mismatch")
    if not fixture:
        if not authorize_api or read(study / "live-gate.json").get("registration_sha256") != digest(study / "registration.json"):
            raise PermissionError("explicit authorization and final pre-API gate required")
        if provider is not None and provider.ledger is not guard:
            raise PermissionError("provider does not share the registered resource guard")
    ledger = Jobs(study / "jobs.sqlite3")
    states = ledger.state()
    if set(states) != {ledger_key(j) for j in registration["schedule"]}:
        raise PermissionError("job ledger differs from registration")
    if any(row["status"] == "running" for row in states.values()):
        raise SeriesStopped("running/orphan context; inspect actual handle, never relaunch")
    for assigned in registration["schedule"]:
        state = states[ledger_key(assigned)]
        if state["status"] == "pending":
            job = assigned
            break
        prior = load_outcome(study, assigned["id"])
        if prior["result"] != state["report"] or prior["status"] != state["status"]:
            raise PermissionError("terminal job ledger and sealed evidence disagree")
    else:
        return None
    guard.check_context()
    resolved, protocol = resolve_job(store, job)
    run = unit_path(study, job["id"])
    if run.exists():
        raise SeriesStopped("pending context already materialized; inspect orphan, never relaunch")
    if provider is not None and provider.model != registration["models"][job["model_role"]]:
        raise PermissionError("provider model differs from assigned role")
    ledger.claim(ledger_key(job))
    make_unit(run)
    try:
        reason = None
        if provider is None:
            if job.get("control") != "cross_model":
                raise PermissionError("only cross-model control may have an unavailable secondary")
            status, reason = "secondary_unavailable", "registered secondary compatibility gate unavailable"
        elif job["condition"] == "T2" and job["role"] == "investigator" and protocol is None:
            status, reason = "skipped_dependency", "assigned protocol proposal unavailable; no replacement"
        elif job.get("source"):
            prior = load_outcome(study, job["source"])
            accepted = "injected_crash_after_commit" if job.get("control") == "crash" and job["stage"] == "D" else "completed"
            if prior["status"] != accepted or prior["audit"].get("pass") is not True or not prior["result"].get("saved"):
                status, reason = "skipped_dependency", "predecessor lacks the assigned durable successful state"
        if reason:
            result = {"status": status, "job": resolved, "reason": reason}
            write_once(run / "result.json", result)
            seal_outcome(study, resolved, {"pass": False, "executed_successfully": False, "reason": reason})
            ledger.finish(ledger_key(job), result)
            return result
        world = store.worlds[job["world"]] if job.get("world") else None
        supplied = None
        if job["role"] in ("designer", "critic"):
            training_gold = {w["id"]: gold[w["id"]] for w in store.worlds.values() if w["split"] == "training"}
            supplied = store.development_bundle(job, training_gold)
            write_once(run / "development-input.json", supplied)
            with (run / "supervisor/seed.jsonl").open("x", encoding="utf-8") as log:
                archive = KnowledgeArchive(run, "host", [], log, "registered-development-controller")
                try:
                    archive.put("development_input", supplied)
                finally:
                    archive.close()
        elif job.get("source"):
            copy_predecessor(run, unit_path(study, job["source"]), job["source"])
        else:
            seed_archive(run, world["evidence"], protocol)
        if job["role"] == "investigator" and protocol_in_archive(run) != protocol:
            raise PermissionError("archive protocol differs from the selected immutable publication")
        # The remaining series deadline also bounds an idle/blocked worker.
        execution_registration = copy.deepcopy(registration)
        execution_registration["limits"]["investigator_seconds"] = min(
            registration["limits"]["investigator_seconds"], guard.remaining())
        provider_log = study / "provider.jsonl"
        network_start = provider_log.stat().st_size if provider_log.exists() else 0
        result = execute(study, execution_registration, resolved, world, provider)
        write_once(run / "provider-span.json", context_span(provider_log, network_start, job["id"]))
        score = None
        if job["role"] in ("designer", "critic"):
            verified = audit_development(study, resolved, supplied, provider.model)
        else:
            verified = audit(study, resolved, world, provider.model)
            if verified["pass"]:
                world_gold = gold[world["id"]]
                questions = world["panel"] + (world["successor"] if job["stage"] == "D" else [])
                score = assess(result.get("answer"), questions, world_gold, source_ids(resolved),
                               inherited_answers=inherited_claims(prior_chain(study, resolved), world_gold))
        seal_outcome(study, resolved, verified, score)
        ledger.finish(ledger_key(job), result)
        return result
    except Exception:
        # Do not rewrite an actual execution result or conceal its raw trace.
        # A failure after execution needs explicit reconciliation, not a replay.
        if not (run / "result.json").exists():
            result = {"status": "failed_controller", "job": resolved, "failure_origin": "controller"}
            write_once(run / "result.json", result)
            seal_outcome(study, resolved, {"pass": False, "executed_successfully": False})
            ledger.finish(ledger_key(job), result)
        raise
