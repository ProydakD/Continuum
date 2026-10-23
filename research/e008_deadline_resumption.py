"""A007: one authorized +72h extension; original clock, quotas and outcomes stay intact."""
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from .common import PROJECT, digest
from .e003 import implementation_hashes
from .e008_locks import read, write_once
from .e008_resources import SeriesStopped
from . import e008_http408_followup as prior
from . import e008_resumption as base
from . import e008_minute_resumption as minute

IDENTITY = "E008-A007"
RESUMPTION = "docs/research/E008-DEADLINE-EXTENSION.json"
PRIOR_SHA = "2f570a386dff6b72096cf856a2b8ed91de368819070439e5b26a0bcbb7f5b1fd"
STOP_SHA = "f8b367e70c404f391f50e3ab0793fb188f54d428aa8cfb6fdf6dcb87a2ae41c2"
AUTHORIZATION_SHA = "a9df42e23cdc75fab41e30fc08a37b5d7636a426e7fde45c4285110fdac2e6fc"
AUTHORIZATION = "Да, продлить на 72 часа и продолжить без повторов"
CUTOVER, FAILURE, NEXT = 2858, "j02858", "j02859"
CLOCK = {"original_started": 1792487989.4194686, "original_deadline": 1792747189.4194686,
         "additional_seconds": 259200, "extended_deadline": 1793006389.4194686}
PLAN = {"resume_existing_recovery": FAILURE, "catalogue_slots": [1, 2, 3],
        "delays_seconds": [30, 120, 300], "maximum_new_Responses": 0,
        "future_HTTP502": {"attempts": 10, "delay_seconds": 60, "method": "GET"}}
MUTABLE_SOURCE = {"research/e008_deadline_resumption.py", "tests/test_e008_deadline_resumption.py",
                  "tests/test_e008_direct_resumption.py", "tests/test_e008_minute_resumption.py",
                  "research/e008_http408_followup.py", "research/e008_resumption.py",
                  "research/e008_live.py", "research/e008_resources.py", "research/e008_transition.py"}


def root(study):
    return Path(study) / "amendments" / IDENTITY


def parent():
    path = PROJECT / prior.RESUMPTION
    if digest(path) != PRIOR_SHA:
        raise PermissionError("immutable A006-R1 changed")
    return read(path)


def verify_scope(registration, amendment, value, current):
    previous = parent()
    prior.verify_scope(registration, amendment, previous, previous["implementation_hashes"])
    changed = {n for n in set(current) | set(previous["implementation_hashes"])
               if current.get(n) != previous["implementation_hashes"].get(n)}
    if (value.get("amendment_id") != IDENTITY or value.get("status") != "approved_for_execution"
            or value.get("preregistered") is not True
            or value.get("human_authorization") != AUTHORIZATION
            or value.get("authorization_sha256") != AUTHORIZATION_SHA
            or value.get("prior_resumption_sha256") != PRIOR_SHA or value.get("stop_sha256") != STOP_SHA
            or value.get("model_amendment_sha256") != base.MODEL_AMENDMENT_SHA
            or value.get("cutover_after_ordinal") != CUTOVER or value.get("first_pending_id") != NEXT
            or registration["schedule"][CUTOVER - 1]["id"] != FAILURE
            or registration["schedule"][CUTOVER]["id"] != NEXT
            or value.get("models") != previous["models"] or value.get("invariants") != previous["invariants"]
            or value.get("clock_extension") != CLOCK or value.get("recovery_plan") != PLAN
            or value.get("base_implementation_hashes") != previous["implementation_hashes"]
            or value.get("implementation_hashes") != current
            or not set(previous["implementation_hashes"]) <= set(current) or not changed <= MUTABLE_SOURCE):
        raise PermissionError("A007 only adds the authorized72h after2858; models and other limits are fixed")


def verify_preserved(study, value):
    from .e008_live import network_bytes
    study = Path(study)
    prior.verify_preserved(study, parent())
    path = Path(value["stop_path"])
    if digest(path) != STOP_SHA:
        raise PermissionError("deadline stop evidence changed")
    stop = read(path)
    if not stop["pass"] or stop["sealed_positions"] != CUTOVER or stop["offline_resume_result"] != "registered series deadline":
        raise PermissionError("wrong deadline stop boundary")
    for name, sha in stop["raw_manifest"].items():
        if name not in base.MUTABLE_STUDY and name != "provider.jsonl" and digest(study / name) != sha:
            raise PermissionError("pre-extension evidence changed: " + name)
    prefix = value["provider_prefix"]
    raw = network_bytes(SimpleNamespace(log=study / "provider.jsonl"), 0, prefix["bytes"])
    if hashlib.sha256(raw).hexdigest() != prefix["sha256"] or prefix["sha256"] != stop["raw_manifest"]["provider.jsonl"]:
        raise PermissionError("pre-extension network prefix changed")
    ledger = Path(value["preserved_ledger_path"])
    rows = read(ledger)
    if digest(ledger) != value["preserved_ledger_sha256"] or len(rows) != CUTOVER or base.ledger_rows(study)[:CUTOVER] != rows:
        raise PermissionError("pre-extension contexts rewritten or replayed")
    authorization = Path(value["authorization_path"])
    if digest(authorization) != AUTHORIZATION_SHA or read(authorization)["answer"] != AUTHORIZATION:
        raise PermissionError("actual human deadline authorization changed")
    return stop


def require_prepared(study, value):
    admitted = read(root(study) / "admission.json")
    if (read(PROJECT / RESUMPTION) != value or admitted["resumption_sha256"] != digest(PROJECT / RESUMPTION)
            or admitted["prior_resumption_sha256"] != PRIOR_SHA or admitted["clock_extension"] != CLOCK
            or admitted["new_network_requests_before_gate"] != 0):
        raise PermissionError("A007 admission binding changed")
    return admitted


def load_resumption(study, path, amendment):
    from .e008_live import git_bytes
    from .e008_transition import verify_clock, verify_git_files
    study, path = Path(study).resolve(strict=True), Path(path).resolve(strict=True)
    if path != (PROJECT / RESUMPTION).resolve(strict=True):
        raise PermissionError("explicit committed A007 required")
    value = read(path)
    verify_scope(read(study / "registration.json"), amendment, value, implementation_hashes())
    if Path(value["study"]).resolve() != study:
        raise PermissionError("A007 study changed")
    prior.load_resumption(study, PROJECT / prior.RESUMPTION, amendment, _historical=True)
    verify_clock(study, read(study / "registration.json"), amendment)
    verify_preserved(study, value)
    head = git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip()
    verify_git_files(head, {**value["implementation_hashes"], RESUMPTION: digest(path)}, working=True)
    gate_path = Path(value["offline_gate_path"])
    gate = read(gate_path)
    if (digest(gate_path) != value["offline_gate_sha256"] or gate.get("pass") is not True
            or gate["implementation_hashes"] != value["implementation_hashes"]
            or set(gate["checks"]) != {"unit", "source_scope", "preservation", "no_replay"}):
        raise PermissionError("A007 requires source-bound offline evidence")
    for check in gate["checks"].values():
        if check.get("pass") is not True or not check.get("evidence"):
            raise PermissionError("missing A007 offline evidence")
        for entry in check["evidence"]:
            if digest(entry["path"]) != entry["sha256"]:
                raise PermissionError("A007 offline evidence changed")
    if (root(study) / "admission.json").exists():
        admitted = require_prepared(study, value)
        verify_git_files(admitted["commit"], {**value["implementation_hashes"], RESUMPTION: digest(path)})
        git_bytes(PROJECT, "merge-base", "--is-ancestor", admitted["commit"], head)
    return value


def prepare_admission(study, value):
    from .e008_live import git_bytes
    if (root(study) / "admission.json").exists():
        return require_prepared(study, value)
    rows = base.ledger_rows(study)
    if (len(rows) != 3426 or any(r["status"] != "pending" or r["started"] is not None for r in rows[CUTOVER:])
            or any((Path(study) / "units" / f"j{n:05d}").exists() for n in range(CUTOVER + 1, 3427))):
        raise SeriesStopped("prospective context exists before A007 admission")
    verify_preserved(study, value)
    at = time.time()
    if not read(Path(value["authorization_path"]))["at"] <= at < CLOCK["extended_deadline"]:
        raise SeriesStopped("A007 admission is outside its authorized absolute deadline")
    return write_once(root(study) / "admission.json", {
        "commit": git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip(),
        "resumption_sha256": digest(PROJECT / RESUMPTION), "prior_resumption_sha256": PRIOR_SHA,
        "clock_extension": CLOCK, "prepared_at": at, "new_network_requests_before_gate": 0})


def deadline_allowance(study, policy, value):
    from .e008_integrity import table
    require_prepared(study, value)
    rows = table(Path(study) / "provider-ledger.sqlite3", "runtime_policy")
    if (value.get("clock_extension") != CLOCK or value.get("amendment_id") != IDENTITY
            or len(rows) != 1 or rows[0]["started"] != CLOCK["original_started"]
            or json.loads(rows[0]["value"]) != policy
            or policy["series_seconds"] != CLOCK["original_deadline"] - CLOCK["original_started"]):
        raise PermissionError("A007 cannot reset the original start or alter the registered policy")
    return CLOCK["additional_seconds"]


def recovery_gate(study, value, provider):
    from .e008_live import recover
    require_prepared(study, value)
    if (value["recovery_plan"] != PLAN or provider.model != value["models"]["primary"]
            or provider.ledger.study != Path(study).resolve() or provider.log != Path(study) / "provider.jsonl"
            or provider.ledger.deadline_extension_seconds != CLOCK["additional_seconds"]):
        raise PermissionError("A007 recovery must use the same model and explicitly extended original ledger")
    # Slot1 was waiting, not sent. Continue that exact slot without rewriting its start.
    return recover(study, FAILURE, provider)


def require_recovered(study, value):
    from .e008_live import load_network_result
    require_prepared(study, value)
    provider = SimpleNamespace(log=Path(study) / "provider.jsonl")
    folder = Path(study) / "recovery" / FAILURE
    for number in PLAN["catalogue_slots"]:
        result = load_network_result(folder / f"{number}-result.json", provider)
        if result["available"]:
            expected = {"pass": True, "attempts": number, "model": value["models"]["primary"]}
            if read(folder / "complete.json") != expected:
                raise PermissionError("A007 resumed recovery completion changed")
            return expected
        if result["action"] == "stop":
            raise SeriesStopped("A007 recovery stopped; no extra probes")
    raise SeriesStopped("A007 recovery exhausted; no extra probes")


def reconciles(study, job, result, value):
    if job["id"] != FAILURE:
        return prior.reconciles(study, job, result, parent())
    require_recovered(study, value)
    stop = read(Path(value["stop_path"]))
    path = Path(study) / "units" / FAILURE / "outcome.json"
    if digest(path) != stop["failed_outcome_sha256"] or read(path)["result"] != result:
        raise PermissionError("A007 cannot rewrite the retained deadline-bound timeout")
    return True


def recover_failure(study, job, result, provider, value):
    require_recovered(study, value)
    if int(job["id"][1:]) <= CUTOVER:
        return prior.recover_failure(study, job, result, provider, parent())
    minute.verify_future_failure(study, job, result, value)
    if provider.model != value["models"][job["model_role"]]:
        raise PermissionError("A007 future provider changed the assigned model")
    return minute.minute.recover(study, job["id"], provider)


def execution_binding(study, job, amendment, value):
    binding = prior.execution_binding(study, job, amendment, parent())
    if int(job["id"][1:]) > CUTOVER:
        admitted = require_prepared(study, value)
        binding.update(commit=admitted["commit"], resumption_sha256=admitted["resumption_sha256"],
                       prior_resumption_sha256=PRIOR_SHA)
    return binding


def audit_clock(study, value, timeline):
    """Do not retroactively reclassify the last retained timeout as within72h."""
    admitted = require_prepared(study, value)
    rows = read(Path(value["preserved_ledger_path"]))
    for identity, row in timeline.items():
        ordinal = int(identity[1:])
        if ordinal <= CUTOVER:
            old = rows[ordinal - 1]
            if row["started"] != old["started"] or row["finished"] != old["finished"]:
                raise PermissionError("A007 changed a pre-extension context time")
        elif not admitted["prepared_at"] <= row["started"] <= row["finished"] <= CLOCK["extended_deadline"]:
            raise PermissionError("context outside authorized A007 clock")
    return {"pass": True, **CLOCK, "retained_last_completion": rows[-1]["finished"],
            "retained_last_completion_overrun_seconds": max(0, rows[-1]["finished"] - CLOCK["original_deadline"])}


def audit_resumption(study, value, timeline):
    from .e008_live import load_network_result, network_bytes
    from .e008_measurements import api_measurements
    historical = {k: v for k, v in timeline.items() if int(k[1:]) <= CUTOVER}
    previous = prior.audit_resumption(study, parent(), historical)
    admitted, complete = require_prepared(study, value), require_recovered(study, value)
    if not timeline[FAILURE]["finished"] <= admitted["prepared_at"] <= timeline[NEXT]["started"]:
        raise PermissionError("A007 admission chronology changed")
    events = []
    folder = Path(study) / "recovery" / FAILURE
    provider = SimpleNamespace(log=Path(study) / "provider.jsonl")
    for number in range(1, complete["attempts"] + 1):
        started, sending = read(folder / f"{number}-started.json"), read(folder / f"{number}-sending.json")
        if (sending["at"] < max(started["at"] + PLAN["delays_seconds"][number - 1], admitted["prepared_at"])
                or sending["at"] > timeline[NEXT]["started"]):
            raise PermissionError("A007 GET chronology changed")
        path = folder / f"{number}-result.json"
        load_network_result(path, provider)
        proof = read(path.with_suffix(".evidence.json"))
        batch = [json.loads(line) for line in network_bytes(provider, proof["offset"], proof["length"]).splitlines()]
        transports = [e for e in batch if e.get("event") == "transport_bytes"]
        if len(transports) != 1 or transports[0].get("method") != "GET":
            raise PermissionError("A007 resumes metadata only, not a Responses replay")
        events.extend(batch)
    future_episodes = []
    for identity, timing in timeline.items():
        if int(identity[1:]) <= CUTOVER:
            continue
        outcome = read(Path(study) / "units" / identity / "outcome.json")
        result = outcome["result"]
        if result.get("failure") != "provider HTTP status 502; no retry or redirect":
            continue
        job = outcome["job"]
        minute.verify_future_failure(study, job, result, value)
        following = timeline.get(f"j{int(identity[1:]) + 1:05d}", {}).get("started", float("inf"))
        recovery, batch = minute.audit_episode(study, identity, value["models"][job["model_role"]], timing["finished"], following)
        events.extend(batch)
        future_episodes.append({"job": identity, "attempts": recovery["attempts"]})
    verify_preserved(study, value)
    return {"pass": True, "cutover_after_ordinal": CUTOVER, "first_pending_id": NEXT,
            "prepared_commit": admitted["commit"], "resumption_sha256": admitted["resumption_sha256"],
            "prior_operational_resumption": previous, "clock_extension": audit_clock(study, value, timeline),
            "same_models": value["models"], "future_http502_recoveries": future_episodes,
            "overhead_already_in_main_ledger": api_measurements(events),
            "interpretation": "Authorized prospective +72h after an actual deadline stop; preserved original clock and all2858 outcomes; no scientific retuning."}
