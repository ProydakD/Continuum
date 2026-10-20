"""Real offline controller continuation; saved earlier fixture data, no model API."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import time

from .common import ROOT, digest, write_json
from .e003 import Jobs, implementation_hashes
from .e008_controller import run_next
from .e008_execute import ledger_key, ledger_record
from .e008_fixture import FixtureProvider
from .e008_locks import DecisionStore, EvidenceSnapshot, SnapshotDecisions, load_outcome, read, write_once
from .e008_resources import SeriesLedger, SeriesStopped, directory_bytes, resource_policy


def fixture(identity, original, *, snapshot=False):
    if not identity.startswith("e008-controller-fixture-") or not all(c.isalnum() or c == "-" for c in identity):
        raise ValueError("new controller fixture identity required")
    original = Path(original).resolve(strict=True)
    original_files = {p.relative_to(original).as_posix(): digest(p) for p in original.rglob("*") if p.is_file()}
    original_registration = read(original / "registration.json")
    if original_registration["fixture"] is not True:
        raise PermissionError("offline fixture corpus only")
    world = dict(read(original / "oracle.json")["worlds"][0], split="calibration")
    gold = {world["id"]: read(original / "gold.json")}
    jobs = []
    for mode in ("ordinary", "reject_twice"):
        previous = None
        for stage in "ABCD":
            job = {"id": f"j{len(jobs) + 1:05}", "world": world["id"], "stage": stage, "source": previous,
                   "condition": "C1", "role": "investigator", "phase": "calibration", "model_role": "primary",
                   "budget": 8192, "protocol_version": None, "control": None}
            if mode == "reject_twice" and stage == "A":
                job["fixture_mode"] = mode
            jobs.append(job)
            previous = job["id"]
    study = ROOT / "runs" / identity
    study.mkdir(exist_ok=False)
    registration = {"fixture": True, "schedule": jobs, "image": original_registration["image"],
                    "implementation_hashes": implementation_hashes(),
                    "models": {"primary": "scripted-fixture", "secondary": "scripted-fixture"},
                    "limits": {"investigator_seconds": 180, "request_seconds": 90,
                               "output_tokens": 8192, "responses_per_context": 10},
                    "scope": "Reduced orchestration fixture, 8192-byte scripted payloads; not the scientific calibration."}
    write_once(study / "registration.json", registration)
    write_once(study / "oracle.json", {"worlds": [world]})
    write_once(study / "gold.json", gold)
    Jobs(study / "jobs.sqlite3", [ledger_record(j) for j in jobs])
    evidence = EvidenceSnapshot(study, jobs) if snapshot else None
    store = SnapshotDecisions(study, [world], jobs, evidence) if snapshot else DecisionStore(study, [world], jobs)
    guard = SeriesLedger(study, resource_policy(jobs))
    if evidence is not None:
        guard.use_evidence(evidence)
    guard.start()
    provider = FixtureProvider(study, jobs)
    started = time.monotonic()
    results = [run_next(study, registration, store, gold, provider, guard=guard, evidence=evidence)]
    assert results[0]["status"] == "completed"
    first = digest(study / "units" / jobs[0]["id"] / "outcome.json")
    state_before_stop = copy.deepcopy(Jobs(study / "jobs.sqlite3").state())
    write_once(study / "STOP", {"fixture_injected_operator_stop": True})
    try:
        run_next(study, registration, store, gold, provider, guard=guard, evidence=evidence)
    except SeriesStopped:
        pass
    else:
        raise AssertionError("STOP allowed a new context")
    assert Jobs(study / "jobs.sqlite3").state() == state_before_stop
    (study / "STOP").unlink()
    # Reconstruct controller, provider and resource ledger; no prior Python state.
    if evidence is not None:
        evidence.verify_all()
        evidence = EvidenceSnapshot(study, jobs)
    store = (SnapshotDecisions(study, [world], jobs, evidence) if snapshot else
             DecisionStore(study, read(study / "oracle.json")["worlds"], read(study / "registration.json")["schedule"]))
    guard = SeriesLedger(study, resource_policy(jobs))
    if evidence is not None:
        guard.use_evidence(evidence)
    prior_attempt = provider.attempt
    provider = FixtureProvider(study, jobs)
    provider.attempt = prior_attempt  # Scripted event IDs only, never a model context/history.
    while True:
        result = run_next(study, registration, store, gold, provider, guard=guard, evidence=evidence)
        if result is None:
            break
        results.append(result)
        print(json.dumps({"job": result["job"]["id"], "status": result["status"]}), flush=True)
    assert len(results) == len(jobs)
    assert dict(Counter(r["status"] for r in results)) == {"completed": 4, "budget_rejected": 1, "skipped_dependency": 3}
    assert digest(study / "units" / jobs[0]["id"] / "outcome.json") == first
    completed_network = digest(study / "provider.jsonl")
    assert run_next(study, registration, store, gold, provider, guard=guard, evidence=evidence) is None
    assert digest(study / "provider.jsonl") == completed_network
    outcomes = {j["id"]: load_outcome(study, j["id"]) for j in jobs}
    assert outcomes[jobs[3]["id"]]["score"]["new_target_correct"] == 10
    assert all(Jobs(study / "jobs.sqlite3").state()[ledger_key(j)]["status"] != "pending" for j in jobs)
    assert {p.relative_to(original).as_posix(): digest(p) for p in original.rglob("*") if p.is_file()} == original_files
    if evidence is not None:
        evidence.verify_all()
        assert directory_bytes(study, evidence=evidence) == directory_bytes(study)
    report = {"pass": True, "fixture": True, "model_API_requests": 0, "positions": len(jobs),
              "verified_snapshot": snapshot, "space_exact_at_completion": snapshot,
              "executed_contexts": 5, "dependent_skips": 3, "stop_before_next_claim": True,
              "first_context_unchanged_after_resume": True, "terminal_dispatch_does_not_repeat_network": True,
              "all_outcomes_sealed": True, "source_fixture_files_unchanged": len(original_files),
              "seconds": time.monotonic() - started, "statuses": dict(Counter(r["status"] for r in results))}
    write_json(study / "fixture-result.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity")
    parser.add_argument("--original-fixture", type=Path, required=True)
    parser.add_argument("--snapshot", action="store_true")
    args = parser.parse_args()
    print(json.dumps(fixture(args.identity, args.original_fixture, snapshot=args.snapshot)))
