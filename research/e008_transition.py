"""Prospective A001 admission; the original registration and failed prefix stay intact."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .common import PROJECT, digest
from .e003 import Jobs, implementation_hashes
from .e008_amendment import require_execution_record, validate_scope, verify_preserved_prefix
from .e008_locks import read, write_once
from .e008_resources import BoundedProvider, SeriesLedger, SeriesStopped, provider_failure_action

AMENDMENT = "docs/research/E008-MODEL-AMENDMENT.json"
GATE_CHECKS = {"unit", "transition", "preserved_prefix", "source_scope"}
# Model-facing mechanisms, gold, REF and statistical methods may not change here.
MUTABLE_SOURCE = {
    "research/e008_amendment.py", "research/e008_transition.py",
    "research/e008_live.py", "research/e008_controller.py",
    "research/e008_integrity.py", "research/e008_evaluate.py",
    "tests/test_e008_amendment.py", "tests/test_e008_transition.py",
}


def root(study):
    return Path(study) / "amendments/E008-A001"


def verify_source_scope(registration, amendment, current):
    original = registration["implementation_hashes"]
    if amendment["base_implementation_hashes"] != original or amendment["implementation_hashes"] != current:
        raise PermissionError("amended source set differs from its recorded implementation")
    changed = {name for name in set(original) | set(current) if original.get(name) != current.get(name)}
    if not changed <= MUTABLE_SOURCE or any(name not in current for name in original):
        raise PermissionError("amendment changed model-facing, scientific or historical source")


def verify_clock(study, registration, amendment):
    with closing(sqlite3.connect((Path(study) / "provider-ledger.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("SELECT value,started FROM runtime_policy").fetchall()
    invariant = amendment["invariants"]
    if (len(rows) != 1 or json.loads(rows[0][0]) != registration["resources"]
            or rows[0][1] != invariant["original_clock_started"]
            or rows[0][1] + registration["resources"]["series_seconds"] != invariant["original_deadline"]):
        raise PermissionError("original policy, clock or deadline changed")


def verify_plan(registration, amendment):
    plan = amendment["prospective_admission"]
    expected = {"maximum_additional_Responses_attempts": 1, "maximum_additional_catalogue_GETs": 1,
                "no_retry_or_new_smoke_after_failure": True, "original_series_ledger_policy_not_reset": True,
                "additional_setup_cost_charged_in_final_report": True,
                "aggregate_Response_ceiling": registration["resources"]["maximum_response_attempts"] + 1}
    if any(plan.get(key) != value for key, value in expected.items()):
        raise PermissionError("transition network plan changed")
    reused = plan["reuse_existing_same_model_compatibility"]
    if reused["model"] != amendment["proposed_models"]["primary"] or reused["new_Response_for_this_model"] is not False:
        raise PermissionError("primary compatibility cannot be replayed or relabelled")


def verify_original_controls(study, amendment):
    """Retain exhausted recovery and compatibility, including unassigned GET traces."""
    fixed = {"manifest.json", "live-gate.json", "network-start.json"}
    for directory in ("compatibility", "recovery/" + amendment["reconciled_failure"]["id"]):
        fixed.update(p.relative_to(study).as_posix() for p in (study / directory).rglob("*") if p.is_file())
    if set(amendment["preserved_control_hashes"]) != fixed:
        raise PermissionError("original admission/recovery control set changed")
    for name, expected in amendment["preserved_control_hashes"].items():
        if digest(study / name) != expected:
            raise PermissionError("original admission/recovery bytes changed")
    prefix = amendment["original_provider_prefix"]
    with (study / "provider.jsonl").open("rb") as stream:
        raw = stream.read(prefix["bytes"])
    if len(raw) != prefix["bytes"] or hashlib.sha256(raw).hexdigest() != prefix["sha256"]:
        raise PermissionError("original provider trace prefix changed")


def verify_git_files(commit, hashes, *, working=False):
    from .e008_live import git_bytes
    for name, expected in hashes.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or ":" in name or "\\" in name:
            raise PermissionError("unsafe amended repository path")
        raw = git_bytes(PROJECT, "show", commit + ":" + name)
        if hashlib.sha256(raw).hexdigest() != expected or (working and digest(PROJECT / name) != expected):
            raise PermissionError("amendment source/record is not committed: " + name)


def load_amendment(study, path, *, resumption_path=None):
    """Read-only verification of both original and prospective source admissions."""
    from .e008_live import REGISTRATION, git_bytes
    study, path = Path(study).resolve(strict=True), Path(path).resolve(strict=True)
    if path != (PROJECT / AMENDMENT).resolve(strict=True):
        raise PermissionError("only the explicit committed amendment record is accepted")
    amendment, registration = read(path), read(study / "registration.json")
    require_execution_record(amendment)
    if amendment["amendment_id"] != "E008-A001" or Path(amendment["study"]).resolve() != study:
        raise PermissionError("amendment belongs to another study")
    verify_preserved_prefix(study, registration, amendment)
    if resumption_path:
        from .e008_resumption import load_resumption
        load_resumption(study, resumption_path, amendment)
    verify_source_scope(registration, amendment,
                        amendment["implementation_hashes"] if resumption_path else implementation_hashes())
    verify_clock(study, registration, amendment)
    verify_plan(registration, amendment)
    verify_original_controls(study, amendment)
    old = read(study / "live-gate.json")
    if old["commit"] != amendment["base_prepared_commit"]:
        raise PermissionError("original prepared commit changed")
    verify_git_files(old["commit"], {**registration["implementation_hashes"],
                                    REGISTRATION: amendment["base_registration_sha256"]})
    commit = git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip()
    git_bytes(PROJECT, "merge-base", "--is-ancestor", old["commit"], commit)
    source_commit = read(root(study) / "admission.json")["commit"] if resumption_path else commit
    verify_git_files(source_commit, {**amendment["implementation_hashes"], AMENDMENT: digest(path)},
                     working=not resumption_path)
    gate_path = Path(amendment["offline_gate_path"])
    gate = read(gate_path)
    if (digest(gate_path) != amendment["offline_gate_sha256"] or gate.get("pass") is not True
            or gate["implementation_hashes"] != amendment["implementation_hashes"]
            or set(gate["checks"]) != GATE_CHECKS):
        raise PermissionError("amendment requires its own complete offline gate")
    for check in gate["checks"].values():
        if check.get("pass") is not True or not check.get("evidence"):
            raise PermissionError("missing amendment offline evidence")
        for entry in check["evidence"]:
            if digest(entry["path"]) != entry["sha256"]:
                raise PermissionError("amendment offline evidence changed")
    if (root(study) / "admission.json").exists():
        admitted = require_prepared(study, amendment)
        verify_git_files(admitted["commit"], {**amendment["implementation_hashes"], AMENDMENT: digest(path)})
        git_bytes(PROJECT, "merge-base", "--is-ancestor", admitted["commit"], commit)
    return amendment


def require_prepared(study, amendment):
    """Cheap per-dispatch binding; full Git/prefix checks occur at load and exit."""
    require_execution_record(amendment)
    path = PROJECT / AMENDMENT
    if read(path) != amendment:
        raise PermissionError("amendment no longer matches its registered bytes")
    admission = read(root(study) / "admission.json")
    if (admission["amendment_sha256"] != digest(path)
            or admission["base_registration_sha256"] != digest(Path(study) / "registration.json")
            or admission["model_API_requests_before_gate"] != 0):
        raise PermissionError("amendment admission binding changed")
    return admission


def prepare_admission(study, amendment):
    from .e008_live import git_bytes
    from .e008_execute import ledger_key
    if (root(study) / "admission.json").exists():
        return require_prepared(study, amendment)
    if root(study).exists():
        raise SeriesStopped("orphan transition directory; do not recreate admission")
    registration = read(Path(study) / "registration.json")
    states = Jobs(Path(study) / "jobs.sqlite3").state()
    for job in registration["schedule"][amendment["cutover_after_ordinal"]:]:
        if states[ledger_key(job)]["status"] != "pending" or (Path(study) / "units" / job["id"]).exists():
            raise SeriesStopped("prospective context exists before amendment admission")
    # Caller holds the original OS controller lock and has just loaded the amendment.
    return write_once(root(study) / "admission.json", {
        "commit": git_bytes(PROJECT, "rev-parse", "HEAD").decode().strip(),
        "amendment_sha256": digest(PROJECT / AMENDMENT),
        "base_registration_sha256": digest(Path(study) / "registration.json"),
        "prepared_at": time.time(), "model_API_requests_before_gate": 0})


def reconciles(study, job, result, amendment):
    """Exempt only the exact retained 502, never future or model/tool failures."""
    if amendment is None or job["id"] != amendment["reconciled_failure"]["id"]:
        return False
    require_prepared(study, amendment)
    path = Path(study) / "units" / job["id"] / "outcome.json"
    if digest(path) != amendment["reconciled_failure"]["sha256"] or read(path)["result"] != result:
        raise PermissionError("reconciled failure bytes changed")
    if (result.get("failure_origin") != "provider"
            or result.get("failure") != "provider HTTP status 502; no retry or redirect"):
        raise PermissionError("amendment cannot reconcile a different failure")
    return True


def gate_policy(registration):
    return {**registration["resources"], "workers": {"smoke-secondary": 1},
            "maximum_response_attempts": 1, "maximum_metadata_attempts": 1}


class TransitionLedger(SeriesLedger):
    """Separate one-use overhead ledger, also bounded by the ORIGINAL clock/STOP."""

    def __init__(self, study, registration, parent):
        self.parent = parent
        if parent.study != Path(study).resolve() or parent.limits != registration["resources"]:
            raise PermissionError("transition lacks original resource guard")
        super().__init__(root(study), gate_policy(registration))

    def remaining(self):
        return min(self.parent.remaining(), super().remaining())

    def check_context(self):
        self.parent.check_context()
        return super().check_context()


def compatibility(study, amendment, provider, original_log):
    """ONE shared catalogue GET and at most ONE secondary smoke; no retry."""
    from .e008_live import (SMOKE_HISTORY, SMOKE_TOOLS, event_offset, last_http_status,
                            load_network_result, save_network_result)
    from types import SimpleNamespace
    reused = amendment["prospective_admission"]["reuse_existing_same_model_compatibility"]
    path = Path(study) / "compatibility/secondary/result.json"
    if (Path(reused["path"]).resolve() != path.resolve() or digest(path) != reused["sha256"]
            or digest(path.with_suffix(".evidence.json")) != reused["evidence_sha256"]):
        raise PermissionError("reused primary compatibility bytes changed")
    old = load_network_result(path, SimpleNamespace(log=original_log))
    models = amendment["proposed_models"]
    if old["model"] != models["primary"] or old.get("pass") is not True or provider.model != models["secondary"]:
        raise PermissionError("compatibility reuse requires the exact previously successful model")
    result_path = root(study) / "compatibility/result.json"
    if result_path.exists():
        value = load_network_result(result_path, provider)
        if value["models"] != models or value["reused_primary_sha256"] != reused["sha256"]:
            raise PermissionError("transition compatibility identity changed")
        return value
    if result_path.parent.exists():
        raise SeriesStopped("orphan transition compatibility; never replay")
    provider.ledger.check_context()
    write_once(result_path.parent / "started.json", {"at": time.time(), "models": models})
    result = {"models": models, "reused_primary_sha256": reused["sha256"], "pass": False,
              "primary_available": False, "secondary_available": False, "action": "stop",
              "scientific_sample": False}
    start = offset = event_offset(provider)
    worker = None
    try:
        available = provider.models()
        result["primary_available"] = models["primary"] in available
        result["secondary_available"] = models["secondary"] in available
        if not result["primary_available"]:
            result["reason"] = "primary_not_in_catalog"
        elif not result["secondary_available"]:
            result.update({"pass": True, "action": "unavailable", "reason": "secondary_not_in_catalog"})
        else:
            worker, offset = "smoke-secondary", event_offset(provider)
            response = provider.respond(worker, SMOKE_HISTORY, SMOKE_TOOLS, timeout=120, max_output_tokens=256)
            calls = [item for item in response["output"] if item.get("type") == "function_call"]
            if (len(calls) != 1 or calls[0].get("name") != "echo"
                    or not isinstance(calls[0].get("call_id"), str) or not calls[0]["call_id"]
                    or json.loads(calls[0]["arguments"]) != {"value": 17}):
                raise ValueError("incompatible function call")
            result.update({"pass": True, "action": "continue", "reason": "single_response_tool_protocol"})
    except Exception as exc:
        status = last_http_status(provider, offset, worker)
        action = provider_failure_action(type(exc).__name__, status)
        unavailable = worker is not None and action == "recover_next_position"
        result.update(failure_type=type(exc).__name__, http_status=status,
                      action="unavailable" if unavailable else "stop", **{"pass": unavailable})
    return save_network_result(result_path, provider, start, result)


def check_gate(study, registration, amendment, original_guard):
    prepare_admission(study, amendment)
    guard = TransitionLedger(study, registration, original_guard)
    guard.start()
    provider = BoundedProvider(registration["provider"], amendment["proposed_models"]["secondary"],
                               guard, root(study) / "provider.jsonl", authorize=True)
    value = compatibility(study, amendment, provider, Path(study) / "provider.jsonl")
    if not value["pass"]:
        raise SeriesStopped("amendment compatibility failed; no repeat or model substitution")
    return value


def audit_transition(study, registration, amendment, timeline, *, resumption=None):
    """Read-only final chronology, overhead and per-position revision attribution."""
    from .e008_integrity import network_ledger
    from .e008_live import load_network_result
    from .e008_measurements import api_measurements
    from .e008_network import NetworkIndex
    from types import SimpleNamespace
    admitted = require_prepared(study, amendment)
    trace = NetworkIndex(root(study) / "provider.jsonl")
    value = load_network_result(root(study) / "compatibility/result.json", SimpleNamespace(log=trace.path))
    if not value["pass"] or value["models"] != amendment["proposed_models"]:
        raise PermissionError("missing successful prospective compatibility")
    proof = network_ledger(root(study), {"schedule": [], "resources": gate_policy(registration)}, trace)
    after = amendment["cutover_after_ordinal"]
    prior = [timeline[j["id"]]["finished"] for j in registration["schedule"][:after]]
    future = [timeline[j["id"]]["started"] for j in registration["schedule"][after:]]
    if not max(prior) <= admitted["prepared_at"] <= proof["first_reservation"] <= min(future):
        raise PermissionError("transition admission/network is not between original and prospective positions")
    for job in registration["schedule"][after:]:
        binding = read(Path(study) / "units" / job["id"] / "execution-binding.json")
        expected = {"job": job["id"], "model": amendment["proposed_models"][job["model_role"]],
                    "commit": admitted["commit"], "amendment_sha256": admitted["amendment_sha256"]}
        if resumption:
            from .e008_resumption import execution_binding
            expected = execution_binding(study, job, amendment, resumption)
        if binding != expected:
            raise PermissionError("prospective position lacks its exact model/source admission binding")
    trace.verify()
    for row in timeline.values():
        if row["finished"] > amendment["invariants"]["original_deadline"]:
            raise PermissionError("context exceeded original series deadline")
    return {"pass": True, **proof, "prepared_commit": admitted["commit"],
            "cutover_after_ordinal": after, "first_pending_id": amendment["first_pending_id"],
            "models_before": registration["models"], "models_after": amendment["proposed_models"],
            "source_before": amendment["base_prepared_commit"], "source_after": admitted["commit"],
            "interpretation": amendment["interpretation"], "operational_overhead": api_measurements(trace.all())}


def charge_overhead(resources, transition):
    """Keep one-time transition costs outside competitors, but inside study totals."""
    from .e008_measurements import combine
    extra = transition["operational_overhead"]
    resources["experiment_overhead"]["model_transition"] = extra
    original = resources["network"]
    workers = list(original["workers"].values()) + list(extra["workers"].values())
    resources["network_including_transition"] = {
        "response_attempts": original["attempts"] + extra["attempts"],
        "metadata_requests": original["metadata_requests"] + extra["metadata_requests"],
        "failed_or_unknown": sum(w["failed_or_unknown"] for w in workers),
        **{key: combine(w[key] for w in workers) for key in
           ("api_body_bytes", "api_seconds", "input_tokens", "output_tokens",
            "cached_input_tokens", "reasoning_output_tokens")},
        "metadata_api_body_bytes": combine([original["metadata_api_body_bytes"], extra["metadata_api_body_bytes"]]),
        "scope": "Additional compatibility is experiment overhead, not a new scientific sample or T2 setup cost."}
