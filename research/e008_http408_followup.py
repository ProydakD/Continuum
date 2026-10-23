"""A006: exact j02697 HTTP408 exception with prior outcomes and clocks intact.

A fresh bounded catalogue gate authorizes only the next pending context.
Future HTTP502 episodes retain A004/A005 ten-attempt minute recovery.
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
from . import e008_direct_resumption as prior
from . import e008_resumption as base
from . import e008_minute_resumption as minute

RESUMPTION = "docs/research/E008-HTTP408-FOLLOWUP.json"
PRIOR_SHA = "f626fb0038c93033bc9586e944d41cf32f214cee384b80b9c6a3f89c61d03bf4"
STOP_SHA = "5b9b428a75e123f0b933dc901c4b632ba14a82fe7121e438dd10ad6868a41859"
CUTOVER, FAILURE, NEXT = 2697, "j02697", "j02698"
IDENTITY = "E008-A006"
AUTHORIZATION = "Да, оформить отдельное возобновление без повторов"
AUTHORIZATION_SHA = "0c4a3442e8b240d227d09239544b3794bc2d399cd43670e5854334d148d8864a"
PLAN = {"catalogue_slots": [1, 2, 3], "delays_seconds": [30, 120, 300],
        "maximum_new_Responses": 0, "same_original_ledger": True,
        "no_replay": True, "no_clock_reset": True,
        "future_HTTP502": {"attempts": 10, "delay_seconds": 60, "method": "GET"}}
MUTABLE_SOURCE = {"research/e008_resumption.py", "research/e008_direct_resumption.py",
                  "research/e008_live.py", "research/e008_http408_followup.py",
                  "tests/test_e008_http408_followup.py", "tests/test_e008_direct_resumption.py",
                  "tests/test_e008_minute_resumption.py"}


def root(study):
    return Path(study) / "amendments" / IDENTITY


def recovery_root(study):
    return Path(study) / "recovery" / IDENTITY


def parent():
    path = PROJECT / prior.RESUMPTION
    if digest(path) != PRIOR_SHA:
        raise PermissionError("immutable A005 changed")
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
            or value.get("authorization_scope") != "exact j02697 HTTP408; preserve2697; firstj02698; same models; no repeats"
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
        raise PermissionError("A006 changed authorized failure, source, models, clock or limits")


def verify_failed_transport(study):
    """Read only the sealed context, never the concurrently appended journal tail."""
    from .e008_network import span_events
    study = Path(study)
    span = read(study / "units" / FAILURE / "provider-span.json")
    events = span_events(study / "provider.jsonl", span, FAILURE)
    transports = [e for e in events if e.get("event") == "transport_bytes"]
    if ([e.get("http_status") for e in transports] != [200, 408]
            or any(e.get("method") != "POST" or e.get("worker") != FAILURE
                   or e.get("request_sent") is not True or e.get("response_complete") is not True
                   for e in transports)):
        raise PermissionError("A006 requires the exact sent and complete HTTP408 transport")


def verify_preserved(study, value):
    from .e008_live import network_bytes
    study = Path(study)
    prior.verify_preserved(study, parent())
    path = Path(value["stop_path"])
    if digest(path) != STOP_SHA:
        raise PermissionError("HTTP408 stop evidence changed")
    stop = read(path)
    if not stop["pass"] or stop["sealed_positions"] != CUTOVER:
        raise PermissionError("wrong HTTP408 cutover evidence")
    for name, sha in stop["raw_manifest"].items():
        if name not in base.MUTABLE_STUDY and name != "provider.jsonl" and digest(study / name) != sha:
            raise PermissionError("preserved raw evidence changed: " + name)
    provider = SimpleNamespace(log=study / "provider.jsonl")
    prefix = value["provider_prefix"]
    raw = network_bytes(provider, 0, prefix["bytes"])
    if hashlib.sha256(raw).hexdigest() != prefix["sha256"] or prefix["sha256"] != stop["raw_manifest"]["provider.jsonl"]:
        raise PermissionError("pre-A006 network prefix changed")
    ledger = Path(value["preserved_ledger_path"])
    rows = read(ledger)
    if digest(ledger) != value["preserved_ledger_sha256"] or len(rows) != CUTOVER or base.ledger_rows(study)[:CUTOVER] != rows:
        raise PermissionError("preserved contexts were rewritten or replayed")
    failed = study / "units" / FAILURE / "outcome.json"
    result = read(failed)["result"]
    if (digest(failed) != stop["failed_outcome_sha256"] or result != stop["failed_result"]
            or result.get("failure_origin") != "provider" or result.get("failure_type") != "RuntimeError"
            or result.get("failure") != "provider HTTP status 408; no retry or redirect"):
        raise PermissionError("A006 only exempts exact retained provider HTTP408")
    verify_failed_transport(study)
    authorization = Path(value["authorization_path"])
    if digest(authorization) != AUTHORIZATION_SHA:
        raise PermissionError("actual human authorization evidence changed")
    old_recovery = study / "recovery" / FAILURE
    if old_recovery.exists() and any(old_recovery.iterdir()):
        raise PermissionError("original stopped recovery was extended")
    return stop


def load_resumption(study, path, amendment):
    from .e008_live import git_bytes
    from .e008_transition import verify_git_files, verify_clock
    study, path = Path(study).resolve(strict=True), Path(path).resolve(strict=True)
    if path != (PROJECT / RESUMPTION).resolve(strict=True):
        raise PermissionError("explicit committed A006 required")
    value = read(path)
    current = implementation_hashes()
    verify_scope(read(study / "registration.json"), amendment, value, current)
    if Path(value["study"]).resolve() != study:
        raise PermissionError("A006 study changed")
    # Historical A005 keeps its admitted source; it is not reissued as A006.
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
        raise PermissionError("A006 requires source-bound offline evidence")
    for check in gate["checks"].values():
        if check.get("pass") is not True or not check.get("evidence"):
            raise PermissionError("missing A006 offline evidence")
        for entry in check["evidence"]:
            if digest(entry["path"]) != entry["sha256"]:
                raise PermissionError("A006 offline evidence changed")
    if (root(study) / "admission.json").exists():
        admitted = require_prepared(study, value)
        verify_git_files(admitted["commit"], {**value["implementation_hashes"], RESUMPTION: digest(path)})
        git_bytes(PROJECT, "merge-base", "--is-ancestor", admitted["commit"], head)
    return value


def require_prepared(study, value):
    admitted = read(root(study) / "admission.json")
    if (read(PROJECT / RESUMPTION) != value or admitted["resumption_sha256"] != digest(PROJECT / RESUMPTION)
            or admitted["prior_resumption_sha256"] != PRIOR_SHA or admitted["new_network_requests_before_gate"] != 0):
        raise PermissionError("A006 admission binding changed")
    return admitted


def prepare_admission(study, value):
    from .e008_live import git_bytes
    if (root(study) / "admission.json").exists():
        return require_prepared(study, value)
    rows = base.ledger_rows(study)
    if (len(rows) != 3426 or any(r["status"] != "pending" or r["started"] is not None for r in rows[CUTOVER:])
            or any((Path(study) / "units" / f"j{n:05d}").exists() for n in range(CUTOVER + 1, 3427))):
        raise SeriesStopped("prospective context exists before A006 admission")
    return write_once(root(study) / "admission.json", {
        "commit": git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip(),
        "resumption_sha256": digest(PROJECT / RESUMPTION), "prior_resumption_sha256": PRIOR_SHA,
        "prepared_at": time.time(), "new_network_requests_before_gate": 0})


def recovery_gate(study, value, provider):
    from .e008_live import recover, RECOVERY_DELAYS
    require_prepared(study, value)
    if (provider.model != value["models"]["primary"] or value["recovery_plan"] != PLAN
            or list(RECOVERY_DELAYS) != PLAN["delays_seconds"]
            or provider.ledger.study != Path(study).resolve() or provider.log != Path(study) / "provider.jsonl"):
        raise PermissionError("A006 must retain model, recovery policy and original guard/journal")
    return recover(study, IDENTITY, provider)


def require_recovered(study, value):
    from .e008_live import load_network_result
    require_prepared(study, value)
    provider = SimpleNamespace(log=Path(study) / "provider.jsonl")
    for number in PLAN["catalogue_slots"]:
        result = load_network_result(recovery_root(study) / f"{number}-result.json", provider)
        if result["available"]:
            expected = {"pass": True, "attempts": number, "model": value["models"]["primary"]}
            if read(recovery_root(study) / "complete.json") != expected:
                raise PermissionError("A006 recovery completion changed")
            return expected
        if result["action"] == "stop":
            raise SeriesStopped("A006 recovery stopped; no extra probes")
    raise SeriesStopped("A006 recovery exhausted; no extra probes")


def recover_failure(study, job, result, provider, value):
    require_recovered(study, value)
    if int(job["id"][1:]) <= CUTOVER:
        return prior.recover_failure(study, job, result, provider, parent())
    minute.verify_future_failure(study, job, result, value)
    if provider.model != value["models"][job["model_role"]]:
        raise PermissionError("A006 future provider changed the assigned model")
    return minute.minute.recover(study, job["id"], provider)


def reconciles(study, job, result, value):
    if job["id"] != FAILURE:
        return prior.reconciles(study, job, result, parent())
    require_recovered(study, value)
    stop = read(Path(value["stop_path"]))
    path = Path(study) / "units" / FAILURE / "outcome.json"
    if digest(path) != stop["failed_outcome_sha256"] or read(path)["result"] != result:
        raise PermissionError("A006 cannot change the retained HTTP408")
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
    historical = {key: timing for key, timing in timeline.items() if int(key[1:]) <= CUTOVER}
    previous = prior.audit_resumption(study, parent(), historical)
    admitted, complete = require_prepared(study, value), require_recovered(study, value)
    at = admitted["prepared_at"]
    if not timeline[FAILURE]["finished"] <= at <= timeline[NEXT]["started"]:
        raise PermissionError("A006 admission chronology changed")
    events = []
    provider = SimpleNamespace(log=Path(study) / "provider.jsonl")
    for number in range(1, complete["attempts"] + 1):
        base = recovery_root(study)
        started, sending = read(base / f"{number}-started.json"), read(base / f"{number}-sending.json")
        if (started["at"] < at or sending["at"] < started["at"] + PLAN["delays_seconds"][number - 1]
                or sending["at"] > timeline[NEXT]["started"]):
            raise PermissionError("A006 GET chronology changed")
        path = base / f"{number}-result.json"
        load_network_result(path, provider)
        proof = read(path.with_suffix(".evidence.json"))
        batch = [json.loads(line) for line in network_bytes(provider, proof["offset"], proof["length"]).splitlines()]
        transport = [e for e in batch if e.get("event") == "transport_bytes"]
        if len(transport) != 1 or transport[0].get("method") != "GET":
            raise PermissionError("A006 recovery requires one GET, no Responses")
        events.extend(batch)
        at = sending["at"]
    future = []
    for identity, timing in timeline.items():
        if int(identity[1:]) <= CUTOVER:
            continue
        outcome = read(Path(study) / "units" / identity / "outcome.json")
        if not minute.is_http502(outcome["result"]):
            continue
        job, result = outcome["job"], outcome["result"]
        minute.verify_future_failure(study, job, result, value)
        next_id = f"j{int(identity[1:]) + 1:05d}"
        latest = timeline[next_id]["started"] if next_id in timeline else float("inf")
        recovered, overhead = minute.audit_episode(study, identity, value["models"][job["model_role"]],
                                                   timing["finished"], latest)
        events.extend(overhead)
        future.append({"job": identity, **recovered})
    verify_preserved(study, value)
    return {"pass": True, "cutover_after_ordinal": CUTOVER, "first_pending_id": NEXT,
            "prepared_commit": admitted["commit"], "resumption_sha256": admitted["resumption_sha256"],
            "prior_operational_resumption": previous, "same_models": value["models"],
            "catalogue_slot_used": complete["attempts"], "future_http502_recoveries": future,
            "overhead_already_in_main_ledger": api_measurements(events),
            "interpretation": "Explicit exact-HTTP408 operational deviation after heldout observations; no retuning."}
