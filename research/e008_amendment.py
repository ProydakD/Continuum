"""Explicit model-boundary validation; a draft never authorizes execution.

This module does not alter registration, ledgers, outcomes or decision locks.
Live admission must additionally bind the final amendment, implementation and
offline evidence to a commit before any new network request.
"""
from .common import digest
from .e008_design import signature
from .e008_locks import load_outcome


def validate_scope(registration, amendment):
    """Preserve the scientific design while declaring a model change."""
    jobs = registration["schedule"]
    after = amendment["cutover_after_ordinal"]
    if type(after) is not int or not 0 < after < len(jobs):
        raise PermissionError("model boundary must follow a nonempty terminal prefix")
    if amendment["first_pending_id"] != jobs[after]["id"]:
        raise PermissionError("amendment does not resume the first pending assignment")
    if any(job["phase"] in ("test", "robustness") for job in jobs[:after]):
        raise PermissionError("model amendment cannot change conditions after held-out observations")
    if amendment["old_models"] != registration["models"]:
        raise PermissionError("original model identities changed")
    models = amendment["proposed_models"]
    if (set(models) != {"primary", "secondary"}
            or any(not isinstance(value, str) or not value.strip() for value in models.values())
            or models["primary"] == models["secondary"]):
        raise PermissionError("two distinct prospective model identities required")
    invariants = amendment["invariants"]
    expected = {
        "schedule_sha256": signature(jobs),
        "oracle_sha256": registration["oracle_sha256"],
        "gold_manifest_sha256": registration["gold_manifest_sha256"],
        "analysis_sha256": signature(registration["analysis"]),
        "limits": registration["limits"],
        "original_resources": registration["resources"],
    }
    if any(invariants.get(name) != value for name, value in expected.items()):
        raise PermissionError("amendment changed frozen scientific or resource criteria")
    required = ("no_test_or_robustness_started", "no_completed_context_replays",
                "no_model_protocol_content_edits", "old_registration_and_admission_files_unchanged")
    if any(invariants.get(name) is not True for name in required):
        raise PermissionError("amendment does not preserve the original research evidence")
    if set(amendment["preserved_outcome_hashes"]) != {job["id"] for job in jobs[:after]}:
        raise PermissionError("amendment omitted or added a preserved assignment")
    stopped = amendment["reconciled_failure"]
    if (stopped["id"] != jobs[after - 1]["id"]
            or stopped["sha256"] != amendment["preserved_outcome_hashes"][stopped["id"]]
            or stopped.get("failure_and_exhausted_recovery_remain_unchanged") is not True):
        raise PermissionError("only the exact final retained failure may be reconciled")


def model_for(registration, job, amendment=None):
    """Resolve expected provenance, not permission to send a request."""
    matches = [(ordinal, assigned) for ordinal, assigned in enumerate(registration["schedule"])
               if assigned["id"] == job["id"]]
    if len(matches) != 1 or matches[0][1]["model_role"] != job["model_role"]:
        raise PermissionError("foreign or role-substituted model assignment")
    if amendment is None:
        return registration["models"][job["model_role"]]
    validate_scope(registration, amendment)
    models = (registration["models"] if matches[0][0] < amendment["cutover_after_ordinal"]
              else amendment["proposed_models"])
    return models[job["model_role"]]


def verify_preserved_prefix(study, registration, amendment):
    """Reopen every original outcome rather than relabelling it for the new model."""
    validate_scope(registration, amendment)
    if digest(study / "registration.json") != amendment["base_registration_sha256"]:
        raise PermissionError("original registration bytes changed")
    outcomes = {}
    for identity, expected in amendment["preserved_outcome_hashes"].items():
        if digest(study / "units" / identity / "outcome.json") != expected:
            raise PermissionError("preserved outcome bytes changed")
        outcomes[identity] = load_outcome(study, identity)
    stopped = outcomes[amendment["reconciled_failure"]["id"]]
    if (stopped["status"] != "failed" or stopped["result"].get("failure_origin") != "provider"
            or stopped["result"].get("failure") != "provider HTTP status 502; no retry or redirect"):
        raise PermissionError("reconciled outcome is not the recorded provider outage")
    lock = study / "locks/calibration.json"
    if digest(lock) != amendment["invariants"]["calibration_lock_sha256"]:
        raise PermissionError("calibration choice changed during model transition")
    return outcomes


def require_execution_record(amendment):
    """Necessary but not sufficient: committed admission remains a separate gate."""
    if (amendment.get("preregistered") is not True
            or amendment.get("status") != "approved_for_execution"
            or not amendment.get("implementation_hashes")
            or not amendment.get("offline_gate_sha256")):
        raise PermissionError("draft amendment cannot authorize model execution")
