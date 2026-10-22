"""A004: authorized minute recovery after retained j02139 and prospective HTTP502.

Ten catalogue GETs at 60-second intervals, never a replay of failed workers.
All A001/A002-R1/A003 admissions remain immutable historical source identities.
"""
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from .common import PROJECT, digest
from .e003 import implementation_hashes
from .e008_locks import read, validate_assignment, write_once
from .e008_resources import SeriesStopped
from . import e008_http408 as prior
from . import e008_resumption as base
from . import e008_minute_recovery as minute

RESUMPTION = "docs/research/E008-MINUTE-RECOVERY.json"
PRIOR_SHA = "cda8270848744209f537518b2bd8d4a42c4aed2ed3e57d776c6ef1b610cc75c7"
STOP_SHA = "3bd2c1ec746b45e732f902947118971358cc6970946f104da11240bd3cb8dada"
CUTOVER, FAILURE, NEXT = 2139, "j02139", "j02140"
IDENTITY = "E008-A004"
AUTHORIZATION = "Сохранить. В дальнейшем делать попытки раз в минуту. Если после 10 попыток 502 - спрашивать пользователя"
AUTHORIZATION_SHA = "8846bdc2d345fee8d2ca157289998cff3afd09020673bcc56c8d41e649ac0957"
PLAN = {"catalogue_slots": list(range(1, 11)), "delays_seconds": [60] * 10,
        "future_scope": "HTTP502 after cutover only; other classification unchanged",
        "exhaustion": "ask user; HTTP502 and missing model counted separately",
        "maximum_new_Responses": 0, "same_original_ledger": True,
        "no_replay": True, "no_clock_reset": True}
MUTABLE_SOURCE = {"research/e008_resumption.py", "research/e008_http408.py", "research/e008_live.py",
                  "research/e008_minute_recovery.py", "tests/test_e008_minute_recovery.py",
                  "research/e008_minute_resumption.py", "tests/test_e008_minute_resumption.py"}


def root(study):
    return Path(study) / "amendments" / IDENTITY


def recovery_root(study):
    return Path(study) / "recovery" / IDENTITY


def parent():
    path = PROJECT / prior.RESUMPTION
    if digest(path) != PRIOR_SHA:
        raise PermissionError("immutable A003 changed")
    return read(path)


def verify_scope(registration, amendment, value, current):
    previous = parent()
    prior.verify_scope(registration, amendment, previous, previous["implementation_hashes"])
    changed = {name for name in set(current) | set(previous["implementation_hashes"])
               if current.get(name) != previous["implementation_hashes"].get(name)}
    if (value.get("amendment_id") != IDENTITY or value.get("status") != "approved_for_execution"
            or value.get("preregistered") is not True
            or value.get("human_authorization") != AUTHORIZATION
            or value.get("authorization_sha256") != AUTHORIZATION_SHA
            or value.get("authorization_scope") != "preserve2139; firstj02140; same models; future502 60s/10; no repeats"
            or value.get("prior_resumption_sha256") != PRIOR_SHA
            or value.get("stop_sha256") != STOP_SHA
            or value.get("model_amendment_sha256") != base.MODEL_AMENDMENT_SHA
            or value.get("cutover_after_ordinal") != CUTOVER or value.get("first_pending_id") != NEXT
            or registration["schedule"][CUTOVER - 1]["id"] != FAILURE
            or registration["schedule"][CUTOVER]["id"] != NEXT
            or value.get("models") != previous["models"] or value.get("invariants") != previous["invariants"]
            or value.get("recovery_plan") != PLAN
            or value.get("base_implementation_hashes") != previous["implementation_hashes"]
            or value.get("implementation_hashes") != current
            or not set(previous["implementation_hashes"]) <= set(current) or not changed <= MUTABLE_SOURCE):
        raise PermissionError("A004 changed authorized failure, source, models, clock or limits")


def verify_failed_transport(study):
    """Read only the sealed context, never the concurrently appended journal tail."""
    from .e008_network import span_events
    study = Path(study)
    span = read(study / "units" / FAILURE / "provider-span.json")
    events = span_events(study / "provider.jsonl", span, FAILURE)
    transports = [e for e in events if e.get("event") == "transport_bytes"]
    if ([e.get("http_status") for e in transports] != [200, 200, 502]
            or any(e.get("method") != "POST" or e.get("worker") != FAILURE
                   or e.get("request_sent") is not True or e.get("response_complete") is not True
                   for e in transports)):
        raise PermissionError("A004 requires the exact sent and complete HTTP502 transport")


def verify_preserved(study, value):
    from .e008_live import network_bytes
    study = Path(study)
    prior.verify_preserved(study, parent())
    path = Path(value["stop_path"])
    if digest(path) != STOP_SHA:
        raise PermissionError("HTTP502 stop evidence changed")
    stop = read(path)
    if not stop["pass"] or stop["sealed_positions"] != CUTOVER:
        raise PermissionError("wrong HTTP502 cutover evidence")
    for name, sha in stop["raw_manifest"].items():
        if name not in base.MUTABLE_STUDY and name != "provider.jsonl" and digest(study / name) != sha:
            raise PermissionError("preserved raw evidence changed: " + name)
    provider = SimpleNamespace(log=study / "provider.jsonl")
    prefix = value["provider_prefix"]
    raw = network_bytes(provider, 0, prefix["bytes"])
    if hashlib.sha256(raw).hexdigest() != prefix["sha256"] or prefix["sha256"] != stop["raw_manifest"]["provider.jsonl"]:
        raise PermissionError("pre-A004 network prefix changed")
    ledger = Path(value["preserved_ledger_path"])
    rows = read(ledger)
    if digest(ledger) != value["preserved_ledger_sha256"] or len(rows) != CUTOVER or base.ledger_rows(study)[:CUTOVER] != rows:
        raise PermissionError("preserved contexts were rewritten or replayed")
    failed = study / "units" / FAILURE / "outcome.json"
    result = read(failed)["result"]
    if (digest(failed) != stop["failed_outcome_sha256"] or result != stop["failed_result"]
            or result.get("failure_origin") != "provider" or result.get("failure_type") != "RuntimeError"
            or result.get("failure") != "provider HTTP status 502; no retry or redirect"):
        raise PermissionError("A004 only exempts exact retained provider HTTP502")
    verify_failed_transport(study)
    if digest(Path(value["authorization_path"])) != AUTHORIZATION_SHA:
        raise PermissionError("actual human authorization evidence changed")
    old_recovery = study / "recovery" / FAILURE
    if {p.name: digest(p) for p in old_recovery.iterdir()} != stop["recovery"]["files"]:
        raise PermissionError("original three stopped recovery attempts changed")
    return stop


def load_resumption(study, path, amendment, *, _historical=False):
    from .e008_live import git_bytes
    from .e008_transition import verify_git_files, verify_clock
    study, path = Path(study).resolve(strict=True), Path(path).resolve(strict=True)
    if path != (PROJECT / RESUMPTION).resolve(strict=True):
        raise PermissionError("explicit committed A004 required")
    value = read(path)
    current = value["implementation_hashes"] if _historical else implementation_hashes()
    verify_scope(read(study / "registration.json"), amendment, value, current)
    if Path(value["study"]).resolve() != study:
        raise PermissionError("A004 study changed")
    # Validate the immutable A003 commit, not current bytes posing as its source.
    prior.load_resumption(study, PROJECT / prior.RESUMPTION, amendment, _historical=True)
    verify_clock(study, read(study / "registration.json"), amendment)
    verify_preserved(study, value)
    head = git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip()
    source_commit = require_prepared(study, value)["commit"] if _historical else head
    verify_git_files(source_commit, {**value["implementation_hashes"], RESUMPTION: digest(path)}, working=not _historical)
    gate_path = Path(value["offline_gate_path"])
    gate = read(gate_path)
    if (digest(gate_path) != value["offline_gate_sha256"] or gate.get("pass") is not True
            or gate["implementation_hashes"] != value["implementation_hashes"]
            or set(gate["checks"]) != {"unit", "source_scope", "preservation", "no_replay"}):
        raise PermissionError("A004 requires source-bound offline evidence")
    for check in gate["checks"].values():
        if check.get("pass") is not True or not check.get("evidence"):
            raise PermissionError("missing A004 offline evidence")
        for entry in check["evidence"]:
            if digest(entry["path"]) != entry["sha256"]:
                raise PermissionError("A004 offline evidence changed")
    if (root(study) / "admission.json").exists():
        admitted = require_prepared(study, value)
        verify_git_files(admitted["commit"], {**value["implementation_hashes"], RESUMPTION: digest(path)})
        git_bytes(PROJECT, "merge-base", "--is-ancestor", admitted["commit"], head)
    return value


def require_prepared(study, value):
    admitted = read(root(study) / "admission.json")
    if (read(PROJECT / RESUMPTION) != value or admitted["resumption_sha256"] != digest(PROJECT / RESUMPTION)
            or admitted["prior_resumption_sha256"] != PRIOR_SHA or admitted["new_network_requests_before_gate"] != 0):
        raise PermissionError("A004 admission binding changed")
    return admitted


def prepare_admission(study, value):
    from .e008_live import git_bytes
    if (root(study) / "admission.json").exists():
        return require_prepared(study, value)
    rows = base.ledger_rows(study)
    if (len(rows) != 3426 or any(r["status"] != "pending" or r["started"] is not None for r in rows[CUTOVER:])
            or any((Path(study) / "units" / f"j{n:05d}").exists() for n in range(CUTOVER + 1, 3427))):
        raise SeriesStopped("prospective context exists before A004 admission")
    return write_once(root(study) / "admission.json", {
        "commit": git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip(),
        "resumption_sha256": digest(PROJECT / RESUMPTION), "prior_resumption_sha256": PRIOR_SHA,
        "prepared_at": time.time(), "new_network_requests_before_gate": 0})


def recovery_gate(study, value, provider):
    require_prepared(study, value)
    if (provider.model != value["models"]["primary"] or value["recovery_plan"] != PLAN
            or minute.ATTEMPTS != 10 or minute.DELAY_SECONDS != 60 or minute.CUTOVER != CUTOVER):
        raise PermissionError("A004 must retain the approved model and minute/ten plan")
    return minute.recover(study, IDENTITY, provider)


def read_completion(study, identity, model):
    from .e008_live import load_network_result
    directory = minute.recovery_root(study, identity)
    minute.check_files(directory)
    provider = SimpleNamespace(log=Path(study) / "provider.jsonl")
    for number in PLAN["catalogue_slots"]:
        started = read(directory / f"{number}-started.json")
        sending = read(directory / f"{number}-sending.json")
        if (started["model"] != model or started["delay"] != 60
                or sending["at"] < started["at"] + 60):
            raise PermissionError("A004 cached recovery assignment or wait changed")
        result = load_network_result(directory / f"{number}-result.json", provider)
        if result["available"]:
            expected = {"pass": True, "attempts": number, "model": model}
            if (read(directory / "complete.json") != expected or (directory / "exhausted.json").exists()
                    or any(any(directory.glob(f"{later}-*.json")) for later in range(number + 1, 11))):
                raise PermissionError("A004 recovery completion changed")
            return expected
        if result["action"] == "stop":
            raise SeriesStopped("A004 recovery stopped; ask user")
    raise SeriesStopped("A004 ten attempts exhausted; ask user")


def require_recovered(study, value):
    require_prepared(study, value)
    return read_completion(study, IDENTITY, value["models"]["primary"])


def is_http502(result):
    return (result.get("failure_origin") == "provider" and result.get("failure_type") == "RuntimeError"
            and result.get("failure") == "provider HTTP status 502; no retry or redirect")


def verify_future_failure(study, job, result, value):
    from .e008_network import span_events
    from .e008_transition import AMENDMENT
    identity = job["id"]
    if not CUTOVER < int(identity[1:]) <= 3426 or not is_http502(result):
        raise PermissionError("A004 future recovery is only for prospective HTTP502")
    unit = Path(study) / "units" / identity
    outcome = validate_assignment(job, read(unit / "outcome.json"))
    events = span_events(Path(study) / "provider.jsonl", read(unit / "provider-span.json"), identity)
    transports = [event for event in events if event.get("event") == "transport_bytes"]
    if (outcome["result"] != result or outcome["status"] != "failed"
            or not transports or transports[-1].get("http_status") != 502
            or any(event.get("method") != "POST" or event.get("request_sent") is not True
                   or event.get("response_complete") is not True for event in transports)
            or any(event.get("http_status") != 200 for event in transports[:-1])
            or read(unit / "execution-binding.json") != base.execution_binding(study, job, read(PROJECT / AMENDMENT), value)):
        raise PermissionError("A004 future failure, transport or source binding changed")


def recover_failure(study, job, result, provider, value):
    require_recovered(study, value)
    verify_future_failure(study, job, result, value)
    if provider.model != value["models"][job["model_role"]]:
        raise PermissionError("A004 future provider changed the assigned model")
    return minute.recover(study, job["id"], provider)


def reconciles(study, job, result, value):
    if job["id"] != FAILURE:
        return prior.reconciles(study, job, result, parent())
    require_recovered(study, value)
    stop = read(Path(value["stop_path"]))
    path = Path(study) / "units" / FAILURE / "outcome.json"
    if digest(path) != stop["failed_outcome_sha256"] or read(path)["result"] != result:
        raise PermissionError("A004 cannot change the retained HTTP502")
    return True


def execution_binding(study, job, amendment, value):
    binding = prior.execution_binding(study, job, amendment, parent())
    if int(job["id"][1:]) > CUTOVER:
        admitted = require_prepared(study, value)
        binding.update(commit=admitted["commit"], resumption_sha256=admitted["resumption_sha256"],
                       prior_resumption_sha256=PRIOR_SHA)
    return binding


def audit_episode(study, identity, model, earliest, latest):
    from .e008_live import load_network_result, network_bytes
    complete = read_completion(study, identity, model)
    provider = SimpleNamespace(log=Path(study) / "provider.jsonl")
    directory = minute.recovery_root(study, identity)
    events, previous = [], earliest
    for number in range(1, complete["attempts"] + 1):
        started, sending = read(directory / f"{number}-started.json"), read(directory / f"{number}-sending.json")
        if (started["at"] < previous or sending["at"] < started["at"] + 60 or sending["at"] > latest):
            raise PermissionError("A004 recovery chronology changed")
        path = directory / f"{number}-result.json"
        load_network_result(path, provider)
        proof = read(path.with_suffix(".evidence.json"))
        batch = [json.loads(line) for line in network_bytes(provider, proof["offset"], proof["length"]).splitlines()]
        transport = [event for event in batch if event.get("event") == "transport_bytes"]
        if len(transport) != 1 or transport[0].get("method") != "GET":
            raise PermissionError("A004 recovery requires exactly one GET per attempt, no Responses")
        events.extend(batch)
        previous = sending["at"]
    return complete, events


def audit_resumption(study, value, timeline):
    from .e008_measurements import api_measurements
    previous = prior.audit_resumption(study, parent(), timeline)
    admitted = require_prepared(study, value)
    if not timeline[FAILURE]["finished"] <= admitted["prepared_at"] <= timeline[NEXT]["started"]:
        raise PermissionError("A004 admission chronology changed")
    complete, events = audit_episode(study, IDENTITY, value["models"]["primary"],
                                     admitted["prepared_at"], timeline[NEXT]["started"])
    future = []
    for identity, timing in timeline.items():
        if int(identity[1:]) <= CUTOVER:
            continue
        outcome = read(Path(study) / "units" / identity / "outcome.json")
        if not is_http502(outcome["result"]):
            continue
        job, result = outcome["job"], outcome["result"]
        verify_future_failure(study, job, result, value)
        next_id = f"j{int(identity[1:]) + 1:05d}"
        latest = timeline[next_id]["started"] if next_id in timeline else float("inf")
        recovered, overhead = audit_episode(study, identity, value["models"][job["model_role"]],
                                            timing["finished"], latest)
        events.extend(overhead)
        future.append({"job": identity, **recovered})
    verify_preserved(study, value)
    return {"pass": True, "cutover_after_ordinal": CUTOVER, "first_pending_id": NEXT,
            "prepared_commit": admitted["commit"], "resumption_sha256": admitted["resumption_sha256"],
            "prior_operational_resumption": previous, "same_models": value["models"],
            "catalogue_slot_used": complete["attempts"], "future_http502_recoveries": future,
            "overhead_already_in_main_ledger": api_measurements(events),
            "interpretation": "Explicit minute/ten operational deviation, unchanged models; no replay or retuning."}
