"""A002: explicit, prospective operational recovery of one retained transport stop.

No model, scientific protocol, selected memory, outcome or resource policy changes.
Only the unused catalogue slots 2/3 are available; old slot 1 stays a fatal result.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

from .common import PROJECT, digest
from .e003 import implementation_hashes
from .e008_locks import read, write_once
from .e008_resources import SeriesStopped, provider_failure_action

BASE_RESUMPTION = "docs/research/E008-OPERATIONAL-RESUMPTION.json"
RESUMPTION = "docs/research/E008-OPERATIONAL-RESUMPTION-R1.json"
BASE_RESUMPTION_SHA = "d942d5377b09554b73c104326a11aa9f072dcf5a5687a1f5f5cd531cdb80124f"
CUTOVER = 1281
FAILURE = "j01281"
NEXT = "j01282"
STOP_SHA = "04842517f97b675bf176833e36e5b969a7678a60fb1df3f2ecc7255d1b623d04"
MODEL_AMENDMENT_SHA = "8f5086cf6d830076d7cc51394fae50c24b6236eec5a0561644b35b0500256756"
MUTABLE_SOURCE = {
    "research/e008_resumption.py", "tests/test_e008_resumption.py",
    "research/e008_live.py", "research/e008_transition.py", "research/e008_controller.py",
    "research/e008_integrity.py", "research/e008_evaluate.py",
}
MUTABLE_STUDY = {"jobs.sqlite3", "provider-ledger.sqlite3",
                 "amendments/E008-A001/provider-ledger.sqlite3"}
PLAN = {"remaining_catalogue_slots": [2, 3], "delays_seconds": [120, 300],
        "maximum_new_Responses": 0, "same_original_ledger": True,
        "no_replay": True, "no_clock_reset": True}


def root(study):
    return Path(study) / "amendments/E008-A002"


def verify_scope(registration, amendment, resumption, current):
    if resumption and resumption.get("amendment_id") == "E008-A005":
        from . import e008_direct_resumption
        return e008_direct_resumption.verify_scope(registration, amendment, resumption, current)
    if resumption and resumption.get("amendment_id") == "E008-A004":
        from . import e008_minute_resumption
        return e008_minute_resumption.verify_scope(registration, amendment, resumption, current)
    if resumption and resumption.get("amendment_id") == "E008-A003":
        from . import e008_http408
        return e008_http408.verify_scope(registration, amendment, resumption, current)
    if (resumption.get("amendment_id") != "E008-A002"
            or resumption.get("status") != "approved_for_execution"
            or resumption.get("preregistered") is not True
            or resumption.get("human_authorization") != "Да, оформить отдельное возобновление без повторов"
            or resumption.get("cutover_after_ordinal") != CUTOVER
            or resumption.get("first_pending_id") != NEXT
            or registration["schedule"][CUTOVER - 1]["id"] != FAILURE
            or registration["schedule"][CUTOVER]["id"] != NEXT
            or resumption.get("models") != amendment["proposed_models"]
            or resumption.get("invariants") != amendment["invariants"]
            or resumption.get("recovery_plan") != PLAN
            or resumption.get("model_amendment_sha256") != MODEL_AMENDMENT_SHA
            or resumption.get("stop_sha256") != STOP_SHA):
        raise PermissionError("operational resumption changed authorized scope, models or limits")
    original = amendment["implementation_hashes"]
    changed = {name for name in set(original) | set(current) if original.get(name) != current.get(name)}
    if (resumption.get("base_implementation_hashes") != original
            or resumption.get("implementation_hashes") != current
            or not changed <= MUTABLE_SOURCE or not set(original) <= set(current)):
        raise PermissionError("resumption changed scientific/model-facing source or unregistered bytes")


def ledger_rows(study):
    with closing(sqlite3.connect((Path(study) / "jobs.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY ordinal")]


def verify_revision(prior, value, current):
    """R1 fixes the path type before any new context; the admitted GET is reused."""
    unchanged = {"amendment_id", "study", "human_authorization", "cutover_after_ordinal", "first_pending_id",
                 "models", "invariants", "recovery_plan", "model_amendment_sha256", "stop_path", "stop_sha256",
                 "provider_prefix", "preserved_ledger_path", "preserved_ledger_sha256", "base_execution_commit"}
    changed = {name for name in set(prior["implementation_hashes"]) | set(current)
               if prior["implementation_hashes"].get(name) != current.get(name)}
    if (value.get("revision") != 1 or value.get("prior_revision_sha256") != BASE_RESUMPTION_SHA
            or any(value.get(name) != prior.get(name) for name in unchanged)
            or value.get("prior_implementation_hashes") != prior["implementation_hashes"]
            or not set(prior["implementation_hashes"]) <= set(current)
            or not changed <= {"research/e008_resumption.py", "tests/test_e008_resumption.py"}):
        raise PermissionError("R1 cannot change the admitted recovery or unrelated source")


def verify_operational_prefix(study, value):
    expected = {"admission.json", "recovery/2-started.json", "recovery/2-sending.json",
                "recovery/2-result.json", "recovery/2-result.evidence.json", "recovery/complete.json"}
    if set(value["preserved_operational_hashes"]) != expected:
        raise PermissionError("R1 must retain the exact admitted slot-two catalogue result")
    for name, sha in value["preserved_operational_hashes"].items():
        if digest(root(study) / name) != sha:
            raise PermissionError("original A002 admission or successful GET changed")


def verify_preserved(study, resumption):
    if resumption and resumption.get("amendment_id") == "E008-A005":
        from . import e008_direct_resumption
        return e008_direct_resumption.verify_preserved(study, resumption)
    if resumption and resumption.get("amendment_id") == "E008-A004":
        from . import e008_minute_resumption
        return e008_minute_resumption.verify_preserved(study, resumption)
    if resumption and resumption.get("amendment_id") == "E008-A003":
        from . import e008_http408
        return e008_http408.verify_preserved(study, resumption)
    from .e008_live import load_network_result, network_bytes
    study = Path(study)
    stop_path = Path(resumption["stop_path"])
    if digest(stop_path) != STOP_SHA:
        raise PermissionError("independent stopped-prefix evidence changed")
    stop = read(stop_path)
    if not stop["pass"] or stop["sealed_positions"] != CUTOVER:
        raise PermissionError("incorrect operational cutover evidence")
    for name, expected in stop["raw_manifest"].items():
        if name in MUTABLE_STUDY or name == "provider.jsonl":
            continue
        if digest(study / name) != expected:
            raise PermissionError("preserved raw evidence changed: " + name)
    prefix = resumption["provider_prefix"]
    raw = network_bytes(SimpleNamespace(log=study / "provider.jsonl"), 0, prefix["bytes"])
    if (hashlib.sha256(raw).hexdigest() != prefix["sha256"]
            or prefix["sha256"] != stop["raw_manifest"]["provider.jsonl"]):
        raise PermissionError("pre-resumption network journal changed")
    ledger_path = Path(resumption["preserved_ledger_path"])
    if digest(ledger_path) != resumption["preserved_ledger_sha256"]:
        raise PermissionError("preserved timeline manifest changed")
    prior = read(ledger_path)
    if len(prior) != CUTOVER or ledger_rows(study)[:CUTOVER] != prior:
        raise PermissionError("a completed context was replayed or rewritten")
    provider = SimpleNamespace(log=study / "provider.jsonl")
    failure = study / "recovery" / FAILURE
    if {p.name for p in failure.iterdir()} != {"1-started.json", "1-sending.json",
                                             "1-result.json", "1-result.evidence.json"}:
        raise PermissionError("original stopped recovery was extended or replaced")
    result = load_network_result(failure / "1-result.json", provider)
    if result != {"available": False, "failure_type": "OSError", "http_status": None, "action": "stop"}:
        raise PermissionError("only the recorded unsent catalogue OSError is eligible")
    proof = read(failure / "1-result.evidence.json")
    events = [json.loads(line) for line in network_bytes(provider, proof["offset"], proof["length"]).splitlines()]
    if (len(events) != 1 or events[0].get("event") != "transport_bytes"
            or events[0].get("method") != "GET" or events[0].get("request_sent") is not False
            or events[0].get("response_complete") is not False or events[0].get("http_status") is not None):
        raise PermissionError("resumption cannot exempt a sent HTTP/auth/quota/TLS failure")
    return stop


def load_resumption(study, path, amendment, *, _historical=False):
    from .e008_live import git_bytes
    from .e008_transition import AMENDMENT, verify_clock, verify_git_files
    from . import e008_http408
    from . import e008_minute_resumption, e008_direct_resumption
    if Path(path).resolve() == (PROJECT / e008_direct_resumption.RESUMPTION).resolve():
        if _historical:
            raise PermissionError("A005 has no historical child admission")
        return e008_direct_resumption.load_resumption(study, path, amendment)
    if Path(path).resolve() == (PROJECT / e008_minute_resumption.RESUMPTION).resolve():
        return e008_minute_resumption.load_resumption(study, path, amendment, _historical=_historical)
    if Path(path).resolve() == (PROJECT / e008_http408.RESUMPTION).resolve():
        return e008_http408.load_resumption(study, path, amendment, _historical=_historical)
    study, path = Path(study).resolve(strict=True), Path(path).resolve(strict=True)
    if path != (PROJECT / RESUMPTION).resolve(strict=True):
        raise PermissionError("explicit committed operational resumption required")
    value = read(path)
    prior_path = PROJECT / BASE_RESUMPTION
    if digest(prior_path) != BASE_RESUMPTION_SHA:
        raise PermissionError("original A002 revision changed")
    prior = read(prior_path)
    current = value["implementation_hashes"] if _historical else implementation_hashes()
    verify_revision(prior, value, current)
    verify_operational_prefix(study, value)
    if Path(value["study"]).resolve() != study or digest(PROJECT / AMENDMENT) != MODEL_AMENDMENT_SHA:
        raise PermissionError("resumption study or immutable A001 changed")
    registration = read(study / "registration.json")
    verify_scope(registration, amendment, value, current)
    verify_clock(study, registration, amendment)
    verify_preserved(study, value)
    head = git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip()
    original_operational = read(root(study) / "admission.json")
    if original_operational["resumption_sha256"] != BASE_RESUMPTION_SHA:
        raise PermissionError("original operational admission changed")
    verify_git_files(original_operational["commit"], {**prior["implementation_hashes"],
                                                     BASE_RESUMPTION: BASE_RESUMPTION_SHA})
    git_bytes(PROJECT, "merge-base", "--is-ancestor", original_operational["commit"], head)
    old = read(study / "amendments/E008-A001/admission.json")
    if old["commit"] != value["base_execution_commit"]:
        raise PermissionError("A001 execution revision changed")
    git_bytes(PROJECT, "merge-base", "--is-ancestor", old["commit"], head)
    source_commit = require_prepared(study, value)["commit"] if _historical else head
    verify_git_files(source_commit, {**value["implementation_hashes"], RESUMPTION: digest(path)}, working=not _historical)
    gate_path = Path(value["offline_gate_path"])
    gate = read(gate_path)
    if (digest(gate_path) != value["offline_gate_sha256"] or gate.get("pass") is not True
            or gate["implementation_hashes"] != value["implementation_hashes"]
            or set(gate["checks"]) != {"unit", "source_scope", "preservation", "no_replay"}):
        raise PermissionError("resumption requires its own source-bound offline gate")
    for check in gate["checks"].values():
        if check.get("pass") is not True or not check.get("evidence"):
            raise PermissionError("missing operational offline evidence")
        for entry in check["evidence"]:
            if digest(entry["path"]) != entry["sha256"]:
                raise PermissionError("operational offline evidence changed")
    if (root(study) / "admission-r1.json").exists():
        admitted = require_prepared(study, value)
        verify_git_files(admitted["commit"], {**value["implementation_hashes"], RESUMPTION: digest(path)})
        git_bytes(PROJECT, "merge-base", "--is-ancestor", admitted["commit"], head)
    return value


def require_prepared(study, value):
    if value and value.get("amendment_id") == "E008-A005":
        from . import e008_direct_resumption
        return e008_direct_resumption.require_prepared(study, value)
    if value and value.get("amendment_id") == "E008-A004":
        from . import e008_minute_resumption
        return e008_minute_resumption.require_prepared(study, value)
    if value and value.get("amendment_id") == "E008-A003":
        from . import e008_http408
        return e008_http408.require_prepared(study, value)
    path = PROJECT / RESUMPTION
    admitted = read(root(study) / "admission-r1.json")
    if (read(path) != value or admitted["resumption_sha256"] != digest(path)
            or admitted["model_amendment_sha256"] != MODEL_AMENDMENT_SHA
            or admitted["new_network_requests_before_gate"] != 0):
        raise PermissionError("operational admission binding changed")
    return admitted


def prepare_admission(study, value):
    if value and value.get("amendment_id") == "E008-A005":
        from . import e008_direct_resumption
        return e008_direct_resumption.prepare_admission(study, value)
    if value and value.get("amendment_id") == "E008-A004":
        from . import e008_minute_resumption
        return e008_minute_resumption.prepare_admission(study, value)
    if value and value.get("amendment_id") == "E008-A003":
        from . import e008_http408
        return e008_http408.prepare_admission(study, value)
    from .e008_live import git_bytes
    if (root(study) / "admission-r1.json").exists():
        return require_prepared(study, value)
    verify_operational_prefix(study, value)
    rows = ledger_rows(study)
    if (len(rows) != 3426 or any(row["status"] != "pending" or row["started"] is not None
                                for row in rows[CUTOVER:])
            or any((Path(study) / "units" / f"j{n:05d}").exists() for n in range(CUTOVER + 1, 3427))):
        raise SeriesStopped("prospective context exists before operational admission")
    return write_once(root(study) / "admission-r1.json", {
        "commit": git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip(),
        "resumption_sha256": digest(PROJECT / RESUMPTION), "model_amendment_sha256": MODEL_AMENDMENT_SHA,
        "prepared_at": time.time(), "new_network_requests_before_gate": 0})


def recovery_gate(study, value, provider):
    """Use only unused slots 2/3, with the original guard and journal; never POST."""
    if value and value.get("amendment_id") == "E008-A005":
        from . import e008_direct_resumption
        return e008_direct_resumption.recovery_gate(study, value, provider)
    if value and value.get("amendment_id") == "E008-A004":
        from . import e008_minute_resumption
        return e008_minute_resumption.recovery_gate(study, value, provider)
    if value and value.get("amendment_id") == "E008-A003":
        from . import e008_http408
        return e008_http408.recovery_gate(study, value, provider)
    from .e008_live import event_offset, last_http_status, load_network_result, save_network_result, wait_until
    if provider.model != value["models"]["primary"] or value["recovery_plan"] != PLAN:
        raise PermissionError("operational model or recovery plan changed")
    if provider.ledger.study != Path(study).resolve() or provider.log != Path(study) / "provider.jsonl":
        raise PermissionError("operational recovery must share the original guard and journal")
    recovery = root(study) / "recovery"
    for number, delay in zip(PLAN["remaining_catalogue_slots"], PLAN["delays_seconds"]):
        started, result_path = recovery / f"{number}-started.json", recovery / f"{number}-result.json"
        if result_path.exists():
            result = load_network_result(result_path, provider)
        else:
            if started.exists():
                attempt = read(started)
                if (recovery / f"{number}-sending.json").exists():
                    raise SeriesStopped("orphan operational HTTP; never replay")
            else:
                attempt = write_once(started, {"at": time.time(), "delay": delay, "model": provider.model})
            if attempt["delay"] != delay or attempt["model"] != provider.model:
                raise PermissionError("operational recovery assignment changed")
            wait_until(attempt["at"] + delay, provider.ledger)
            provider.ledger.check_context()
            offset = event_offset(provider)
            write_once(recovery / f"{number}-sending.json", {"at": time.time()})
            try:
                available = provider.model in provider.models()
                result = {"available": available, "action": "continue" if available else "recover_next_position"}
            except Exception as exc:
                status = last_http_status(provider, offset)
                result = {"available": False, "failure_type": type(exc).__name__, "http_status": status,
                          "action": provider_failure_action(type(exc).__name__, status)}
            save_network_result(result_path, provider, offset, result)
        if result["available"]:
            return write_once(recovery / "complete.json", {"pass": True, "slot": number, "model": provider.model})
        if result["action"] == "stop":
            raise SeriesStopped("operational recovery stopped; no extra probes")
    raise SeriesStopped("remaining operational recovery exhausted; no extra probes")


def require_recovered(study, value):
    """Offline re-read, not an attestation based on complete.json alone."""
    if value and value.get("amendment_id") == "E008-A005":
        from . import e008_direct_resumption
        return e008_direct_resumption.require_recovered(study, value)
    if value and value.get("amendment_id") == "E008-A004":
        from . import e008_minute_resumption
        return e008_minute_resumption.require_recovered(study, value)
    if value and value.get("amendment_id") == "E008-A003":
        from . import e008_http408
        return e008_http408.require_recovered(study, value)
    from .e008_live import load_network_result
    require_prepared(study, value)
    provider = SimpleNamespace(log=Path(study) / "provider.jsonl")
    recovery = root(study) / "recovery"
    for number in PLAN["remaining_catalogue_slots"]:
        result = load_network_result(recovery / f"{number}-result.json", provider)
        if result["available"]:
            expected = {"pass": True, "slot": number, "model": value["models"]["primary"]}
            if read(recovery / "complete.json") != expected:
                raise PermissionError("operational recovery completion changed")
            return expected
        if result["action"] == "stop":
            raise SeriesStopped("operational recovery stopped; no extra probes")
    raise SeriesStopped("remaining operational recovery exhausted; no extra probes")


def reconciles(study, job, result, value):
    if value and value.get("amendment_id") == "E008-A005":
        from . import e008_direct_resumption
        return e008_direct_resumption.reconciles(study, job, result, value)
    if value and value.get("amendment_id") == "E008-A004":
        from . import e008_minute_resumption
        return e008_minute_resumption.reconciles(study, job, result, value)
    if value and value.get("amendment_id") == "E008-A003":
        from . import e008_http408
        return e008_http408.reconciles(study, job, result, value)
    if job["id"] != FAILURE:
        return False
    require_recovered(study, value)
    stop = read(Path(value["stop_path"]))
    path = Path(study) / "units" / FAILURE / "outcome.json"
    if digest(path) != stop["failed_outcome_sha256"] or read(path)["result"] != result:
        raise PermissionError("operational exception cannot change the retained timeout")
    return True


def execution_binding(study, job, amendment, value):
    if value and value.get("amendment_id") == "E008-A005":
        from . import e008_direct_resumption
        return e008_direct_resumption.execution_binding(study, job, amendment, value)
    if value and value.get("amendment_id") == "E008-A004":
        from . import e008_minute_resumption
        return e008_minute_resumption.execution_binding(study, job, amendment, value)
    if value and value.get("amendment_id") == "E008-A003":
        from . import e008_http408
        return e008_http408.execution_binding(study, job, amendment, value)
    from .e008_transition import require_prepared as original_admission
    original = original_admission(study, amendment)
    binding = {"job": job["id"], "model": amendment["proposed_models"][job["model_role"]],
               "commit": original["commit"], "amendment_sha256": original["amendment_sha256"]}
    if value and int(job["id"][1:]) > CUTOVER:
        admitted = require_prepared(study, value)
        binding.update(commit=admitted["commit"], resumption_sha256=admitted["resumption_sha256"])
    return binding


def audit_resumption(study, value, timeline):
    if value and value.get("amendment_id") == "E008-A005":
        from . import e008_direct_resumption
        return e008_direct_resumption.audit_resumption(study, value, timeline)
    if value and value.get("amendment_id") == "E008-A004":
        from . import e008_minute_resumption
        return e008_minute_resumption.audit_resumption(study, value, timeline)
    if value and value.get("amendment_id") == "E008-A003":
        from . import e008_http408
        return e008_http408.audit_resumption(study, value, timeline)
    from .e008_live import load_network_result, network_bytes
    from .e008_measurements import api_measurements
    admitted = require_prepared(study, value)
    complete = require_recovered(study, value)
    events = []
    original_admission = read(root(study) / "admission.json")
    previous = original_admission["prepared_at"]
    if not previous <= admitted["prepared_at"] <= timeline[NEXT]["started"]:
        raise PermissionError("corrective revision was not admitted before its first context")
    if timeline[FAILURE]["finished"] > previous:
        raise PermissionError("operational admission preceded stopped outcome")
    for number in range(2, complete["slot"] + 1):
        base = root(study) / "recovery"
        started, sending = read(base / f"{number}-started.json"), read(base / f"{number}-sending.json")
        if (started["at"] < previous or sending["at"] < started["at"] + PLAN["delays_seconds"][number - 2]
                or sending["at"] > timeline[NEXT]["started"]):
            raise PermissionError("operational GET chronology changed")
        result_path = base / f"{number}-result.json"
        load_network_result(result_path, SimpleNamespace(log=Path(study) / "provider.jsonl"))
        proof = read(result_path.with_suffix(".evidence.json"))
        batch = [json.loads(line) for line in network_bytes(
            SimpleNamespace(log=Path(study) / "provider.jsonl"), proof["offset"], proof["length"]).splitlines()]
        transports = [event for event in batch if event.get("event") == "transport_bytes"]
        if len(transports) != 1 or transports[0].get("method") != "GET":
            raise PermissionError("operational recovery must contain one GET and no Responses")
        events.extend(batch)
        previous = sending["at"]
    verify_preserved(study, value)
    verify_operational_prefix(study, value)
    return {"pass": True, "cutover_after_ordinal": CUTOVER, "first_pending_id": NEXT,
            "prepared_commit": admitted["commit"], "resumption_sha256": admitted["resumption_sha256"],
            "catalogue_execution_commit": original_admission["commit"],
            "original_operational_sha256": original_admission["resumption_sha256"],
            "remaining_slot_used": complete["slot"], "same_models": value["models"],
            "overhead_already_in_main_ledger": api_measurements(events),
            "interpretation": "Authorized operational protocol deviation after heldout observations; no scientific retuning."}
