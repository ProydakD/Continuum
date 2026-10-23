"""A005: reuse the separately authorized direct Responses success, no new probe.

The ten missing-catalogue checks remain negative observations, not proof that
Responses is unavailable. Future HTTP502 episodes retain A004's bounded policy.
"""
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from .common import PROJECT, digest
from .e003 import implementation_hashes
from .e008_locks import read, write_once
from .e008_resources import SeriesStopped
from . import e008_minute_resumption as prior
from . import e008_resumption as base
from . import e008_minute_recovery as minute

RESUMPTION = "docs/research/E008-DIRECT-RESUMPTION.json"
PRIOR_SHA = "a0e695df85e82e7d0a70d3116e872b5abb668733cbbbba74cbb52486c9d4699b"
STOP_SHA = "33b2599e5d622348b6e2ee4fb5b5654d07653f360e82ce428fcb6b2586f472de"
CUTOVER, FAILURE, NEXT = 2139, "j02139", "j02140"
IDENTITY = "E008-A005"
AUTHORIZATION = "Да, продолжить по успешному прямому тесту"
AUTHORIZATION_SHA = "7ef247a0621afab7f6c70f65773199345c81867aedb7600b410edcbb46569224"
DIAGNOSTIC_SHA = "97ce760f38477da812d34a36a7af74271ab5fc544e21cff9695ea38af734c593"
PLAN = {"initial_gate": "reuse one authorized completed direct Responses diagnostic",
        "maximum_new_network_requests_for_initial_gate": 0,
        "future_HTTP502": {"attempts": 10, "delay_seconds": 60, "method": "GET"},
        "same_original_ledger": True, "no_replay": True, "no_clock_reset": True}
MUTABLE_SOURCE = {"research/e008_resumption.py", "research/e008_minute_resumption.py",
                  "research/e008_live.py", "research/e008_direct_resumption.py",
                  "tests/test_e008_direct_resumption.py", "tests/test_e008_minute_resumption.py"}


def root(study):
    return Path(study) / "amendments" / IDENTITY


def parent():
    path = PROJECT / prior.RESUMPTION
    if digest(path) != PRIOR_SHA:
        raise PermissionError("immutable A004 changed")
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
            or value.get("authorization_scope") != "preserve2139; firstj02140; reuse successful direct probe; same models; no repeats"
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
        raise PermissionError("A005 changed authorized failure, source, models, clock or limits")


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
        raise PermissionError("pre-A005 network prefix changed")
    ledger = Path(value["preserved_ledger_path"])
    rows = read(ledger)
    if digest(ledger) != value["preserved_ledger_sha256"] or len(rows) != CUTOVER or base.ledger_rows(study)[:CUTOVER] != rows:
        raise PermissionError("preserved contexts were rewritten or replayed")
    failed = study / "units" / FAILURE / "outcome.json"
    result = read(failed)["result"]
    if (digest(failed) != stop["failed_outcome_sha256"] or result != stop["failed_result"]
            or result.get("failure_origin") != "provider" or result.get("failure_type") != "RuntimeError"
            or result.get("failure") != "provider HTTP status 502; no retry or redirect"):
        raise PermissionError("A005 only exempts exact retained provider HTTP502")
    prior.verify_failed_transport(study)
    if digest(Path(value["authorization_path"])) != AUTHORIZATION_SHA:
        raise PermissionError("actual human authorization evidence changed")
    old_recovery = study / "recovery" / prior.IDENTITY
    if {p.name: digest(p) for p in old_recovery.iterdir()} != stop["recovery"]["files"]:
        raise PermissionError("retained ten catalogue checks changed")
    verify_diagnostic(value)
    return stop


def load_resumption(study, path, amendment, *, _historical=False):
    from .e008_live import git_bytes
    from .e008_transition import verify_git_files, verify_clock
    study, path = Path(study).resolve(strict=True), Path(path).resolve(strict=True)
    if path != (PROJECT / RESUMPTION).resolve(strict=True):
        raise PermissionError("explicit committed A005 required")
    value = read(path)
    current = value["implementation_hashes"] if _historical else implementation_hashes()
    verify_scope(read(study / "registration.json"), amendment, value, current)
    if Path(value["study"]).resolve() != study:
        raise PermissionError("A005 study changed")
    # The exhausted A004 remains its original committed source and evidence.
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
        raise PermissionError("A005 requires source-bound offline evidence")
    for check in gate["checks"].values():
        if check.get("pass") is not True or not check.get("evidence"):
            raise PermissionError("missing A005 offline evidence")
        for entry in check["evidence"]:
            if digest(entry["path"]) != entry["sha256"]:
                raise PermissionError("A005 offline evidence changed")
    if (root(study) / "admission.json").exists():
        admitted = require_prepared(study, value)
        verify_git_files(admitted["commit"], {**value["implementation_hashes"], RESUMPTION: digest(path)})
        git_bytes(PROJECT, "merge-base", "--is-ancestor", admitted["commit"], head)
    return value


def require_prepared(study, value):
    admitted = read(root(study) / "admission.json")
    if (read(PROJECT / RESUMPTION) != value or admitted["resumption_sha256"] != digest(PROJECT / RESUMPTION)
            or admitted["prior_resumption_sha256"] != PRIOR_SHA or admitted["new_network_requests_before_gate"] != 0):
        raise PermissionError("A005 admission binding changed")
    return admitted


def prepare_admission(study, value):
    from .e008_live import git_bytes
    if (root(study) / "admission.json").exists():
        return require_prepared(study, value)
    rows = base.ledger_rows(study)
    if (len(rows) != 3426 or any(r["status"] != "pending" or r["started"] is not None for r in rows[CUTOVER:])
            or any((Path(study) / "units" / f"j{n:05d}").exists() for n in range(CUTOVER + 1, 3427))):
        raise SeriesStopped("prospective context exists before A005 admission")
    return write_once(root(study) / "admission.json", {
        "commit": git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip(),
        "resumption_sha256": digest(PROJECT / RESUMPTION), "prior_resumption_sha256": PRIOR_SHA,
        "prepared_at": time.time(), "new_network_requests_before_gate": 0})


def verify_diagnostic(value):
    """Reopen the already completed one-shot request, never create network."""
    path = Path(value["diagnostic_path"])
    if digest(path) != DIAGNOSTIC_SHA or value["diagnostic_sha256"] != DIAGNOSTIC_SHA:
        raise PermissionError("authorized direct diagnostic changed")
    result = read(path)
    if (result["requested_model"] != value["models"]["primary"]
            or result["returned_model"] != value["models"]["primary"]
            or result["http_status"] != 200 or result["response_status"] != "completed"
            or result["output_text"] != "OK" or result["exception_type"] is not None
            or not result["request_sent"] or not result["response_complete"]
            or result["POST_attempts"] != 1 or result["GET_attempts"] != 0 or result["retry_attempts"] != 0):
        raise PermissionError("direct diagnostic does not demonstrate the unchanged model")
    log = path.parent / "provider.jsonl"
    if digest(log) != result["provider_log_sha256"]:
        raise PermissionError("direct diagnostic trace changed")
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    requests = [e for e in events if e["event"] == "request_started"]
    transports = [e for e in events if e["event"] == "transport_bytes"]
    replies = [e for e in events if e["event"] == "response"]
    if (len(requests) != 1 or len(transports) != 1 or len(replies) != 1
            or requests[0]["payload"]["model"] != value["models"]["primary"]
            or requests[0]["payload"]["input"] != [{"role": "user", "content": [{"type": "input_text", "text": "Reply exactly OK."}]}]
            or requests[0]["payload"]["tools"] != [] or requests[0]["payload"]["max_output_tokens"] != 256
            or transports[0]["method"] != "POST" or transports[0]["http_status"] != 200
            or not transports[0]["request_sent"] or not transports[0]["response_complete"]
            or replies[0]["response"]["model"] != value["models"]["primary"]
            or replies[0]["response"]["status"] != "completed"
            or replies[0]["response"].get("usage") != result["usage"]):
        raise PermissionError("direct diagnostic request/response proof changed")
    return result, events


def gate_value(value):
    result, _ = verify_diagnostic(value)
    return {"pass": True, "model": value["models"]["primary"], "diagnostic_sha256": DIAGNOSTIC_SHA,
            "diagnostic_finished_at": result["at"], "new_network_requests": 0}


def recovery_gate(study, value, provider):
    admitted = require_prepared(study, value)
    if provider.model != value["models"]["primary"] or value["recovery_plan"] != PLAN:
        raise PermissionError("A005 cannot replace model or recovery plan")
    if provider.ledger.study != Path(study).resolve() or provider.log != Path(study) / "provider.jsonl":
        raise PermissionError("A005 retains the original clock and journal")
    provider.ledger.check_context()
    expected = gate_value(value)
    if expected["diagnostic_finished_at"] > admitted["prepared_at"]:
        raise PermissionError("direct evidence must precede A005 admission")
    return write_once(root(study) / "direct-gate.json", expected)


def require_recovered(study, value):
    admitted = require_prepared(study, value)
    expected = gate_value(value)
    if (expected["diagnostic_finished_at"] > admitted["prepared_at"]
            or read(root(study) / "direct-gate.json") != expected):
        raise PermissionError("A005 direct gate binding changed")
    return expected


def recover_failure(study, job, result, provider, value):
    require_recovered(study, value)
    prior.verify_future_failure(study, job, result, value)
    if provider.model != value["models"][job["model_role"]]:
        raise PermissionError("A005 future provider changed the assigned model")
    return minute.recover(study, job["id"], provider)


def reconciles(study, job, result, value):
    if job["id"] != FAILURE:
        return prior.reconciles(study, job, result, parent())
    require_recovered(study, value)
    stop = read(Path(value["stop_path"]))
    path = Path(study) / "units" / FAILURE / "outcome.json"
    if digest(path) != stop["failed_outcome_sha256"] or read(path)["result"] != result:
        raise PermissionError("A005 cannot change the retained HTTP502")
    return True


def execution_binding(study, job, amendment, value):
    binding = prior.execution_binding(study, job, amendment, parent())
    if int(job["id"][1:]) > CUTOVER:
        admitted = require_prepared(study, value)
        binding.update(commit=admitted["commit"], resumption_sha256=admitted["resumption_sha256"],
                       prior_resumption_sha256=PRIOR_SHA)
    return binding


def audit_resumption(study, value, timeline):
    from .e008_live import load_network_result, network_bytes
    from .e008_measurements import api_measurements
    # A004 initial gate exhausted; do not falsely mark it recovered. Audit its
    # parent A003 and retained negative catalogue observations separately.
    previous = prior.prior.audit_resumption(study, prior.parent(), timeline)
    admitted = require_prepared(study, value)
    gate = require_recovered(study, value)
    if not timeline[FAILURE]["finished"] <= admitted["prepared_at"] <= timeline[NEXT]["started"]:
        raise PermissionError("A005 admission chronology changed")
    diagnostic, diagnostic_events = verify_diagnostic(value)
    stop = verify_preserved(study, value)
    provider = SimpleNamespace(log=Path(study) / "provider.jsonl")
    events = []
    for number in range(1, 11):
        path = prior.recovery_root(study) / f"{number}-result.json"
        load_network_result(path, provider)
        proof = read(path.with_suffix(".evidence.json"))
        events.extend(json.loads(line) for line in network_bytes(provider, proof["offset"], proof["length"]).splitlines())
    future = []
    for identity, timing in timeline.items():
        if int(identity[1:]) <= CUTOVER:
            continue
        outcome = read(Path(study) / "units" / identity / "outcome.json")
        if not prior.is_http502(outcome["result"]):
            continue
        job, result = outcome["job"], outcome["result"]
        prior.verify_future_failure(study, job, result, value)
        next_id = f"j{int(identity[1:]) + 1:05d}"
        latest = timeline[next_id]["started"] if next_id in timeline else float("inf")
        recovered, overhead = prior.audit_episode(study, identity, value["models"][job["model_role"]],
                                                 timing["finished"], latest)
        events.extend(overhead)
        future.append({"job": identity, **recovered})
    return {"pass": True, "cutover_after_ordinal": CUTOVER, "first_pending_id": NEXT,
            "prepared_commit": admitted["commit"], "resumption_sha256": admitted["resumption_sha256"],
            "prior_operational_resumption": previous, "same_models": value["models"],
            "retained_A004_exhaustion": stop["exhausted"], "direct_gate": gate,
            "future_http502_recoveries": future,
            "overhead_already_in_main_ledger": api_measurements(events),
            "external_diagnostic_overhead": api_measurements(diagnostic_events),
            "external_diagnostic_finished_at": diagnostic["at"],
            "interpretation": "Catalogue absence was not Responses unavailability; reuse authorized successful direct evidence, no replay."}
