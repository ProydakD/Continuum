"""Read-only E008 raw-trace reconstruction and integrated descriptive report.

No model execution, retries, repaired outcomes, changed locks or source writes.
Fixture reports explicitly cannot supply scientific H1-H6 evidence.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from .common import digest
from .e003 import Jobs, implementation_hashes
from .e008_analysis import summarize
from .e008_assessment import assess, inherited_claims
from .e008_audit import audit
from .e008_controller import resolve_job
from .e008_design import schedule, signature
from .e008_development_audit import audit as audit_development
from .e008_execute import ledger_key
from .e008_live import verified_gold
from .e008_locks import DecisionStore, load_outcome, read, unit_path, validate_assignment, write_once
from .e008_measurements import resource_report
from .e008_network import NetworkIndex
from .e008_protocol import source_ids
from .e008_revision import aggregate_revision, revision_metrics, uncertainty_metrics, world_interval


class ReadOnlyDecisions(DecisionStore):
    """Use a fully rehashed snapshot, then rehash all inputs before report return."""

    def __init__(self, study, worlds, jobs, outcomes):
        super().__init__(study, worlds, jobs)
        self.outcomes = outcomes

    def _outcome(self, job):
        self._check_binding()
        return validate_assignment(job, self.outcomes[job["id"]])

    def _seal(self, name, decision, sources):
        value = read(self.study / "locks" / (name + ".json"))
        expected = json.loads(json.dumps({"binding": self.binding, "decision": decision, "sources": sources}))
        if {k: value[k] for k in expected} != expected:
            raise PermissionError("independent reconstruction differs from frozen decision")
        return value


def chain(job, outcomes):
    result, seen = [], {job["id"]}
    identity = job.get("source")
    while identity:
        if identity in seen or identity not in outcomes:
            raise PermissionError("invalid predecessor path")
        seen.add(identity)
        row = outcomes[identity]
        # Failed/unverified outputs are not treated as observed model beliefs.
        result.insert(0, {"job": row["job"], "result": row["result"] if row["audit"].get("pass") else {}})
        identity = row["job"].get("source")
    if job.get("bulletin"):
        result.append({"job": job, "result": {}})
    return result


def control_report(records, worlds, *, draws=10000):
    """Descriptive paired world differences; not additional uncorrected p-values."""
    families = {w["id"]: w["truth"]["family"] for w in worlds}
    main = {}
    key = lambda j: (j["world"], j["condition"], j.get("lineage"), j["replicate"])
    for row in records:
        job = row["job"]
        if job["phase"] == "test" and job["stage"] == "D":
            if key(job) in main:
                raise ValueError("duplicate main-control match")
            main[key(job)] = row
    groups = defaultdict(list)
    for row in records:
        job = row["job"]
        if job["phase"] == "robustness" and job["stage"] == "D":
            groups[(job["condition"], job["control"])].append(row)

    def rate(row):
        if row["status"] != "completed" or not row["audit"].get("pass"):
            return 0.0
        if row["score"]["new_total"] != 10:
            raise ValueError("ten assigned new questions required")
        return row["score"]["new_target_correct"] / 10

    result = {}
    for (condition, control), group in sorted(groups.items()):
        per_world = defaultdict(list)
        unavailable = 0
        for row in group:
            job = row["job"]
            if key(job) not in main:
                raise ValueError("no assigned main comparator for control")
            if row["status"] == "secondary_unavailable":
                unavailable += 1
                continue
            per_world[job["world"]].append(rate(row) - rate(main[key(job)]))
        result[condition + "|" + control] = {
            "assigned_contexts": len(group), "unavailable_secondary": unavailable,
            "statuses": dict(Counter(r["status"] for r in group)),
            "paired_control_minus_main": world_interval(
                {w: sum(v) / len(v) for w, v in per_world.items()}, families, draws=draws),
            "scope": "Failures retain zero task scores; unavailable secondary is explicitly not evidence "
                     "of cross-model success or failure. Conditional descriptive world interval only."}
    return result


def evaluate(study, gold, *, bootstrap_samples=10000):
    """Caller binds gold to the independent, hash-checked complete cache."""
    study = Path(study).resolve(strict=True)
    registration, corpus = read(study / "registration.json"), read(study / "oracle.json")
    jobs, worlds = registration["schedule"], corpus["worlds"]
    world_index = {w["id"]: w for w in worlds}
    if set(gold) != set(world_index) or len(world_index) != len(worlds):
        raise ValueError("one independent gold record per registered world required")
    if not registration["fixture"] and jobs != schedule(worlds):
        raise PermissionError("live scientific schedule differs from fixed design")
    binding = {"registration": digest(study / "registration.json"),
               "corpus": digest(study / "oracle.json"), "gold": signature(gold),
               "job_ledger": digest(study / "jobs.sqlite3"),
               "locks": {p.name: digest(p) for p in (study / "locks").glob("*.json")}}
    states = Jobs(study / "jobs.sqlite3").state()
    if set(states) != {ledger_key(j) for j in jobs}:
        raise PermissionError("assignment ledger differs")
    if any(r["status"] in ("pending", "running") for r in states.values()):
        raise ValueError("unfinished series: pending/orphan positions are not zero-scored failures")
    outcomes = {j["id"]: load_outcome(study, j["id"]) for j in jobs}
    store = ReadOnlyDecisions(study, worlds, jobs, outcomes)
    network = NetworkIndex(study / "provider.jsonl")
    verified = {}
    for job in jobs:
        identity = job["id"]
        row = validate_assignment(job, outcomes[identity])
        if states[ledger_key(job)]["report"] != row["result"] or states[ledger_key(job)]["status"] != row["status"]:
            raise PermissionError("ledger and sealed result differ")
        resolved, _ = resolve_job(store, job)
        if resolved != row["job"]:
            raise PermissionError("resolved assignment differs from frozen choices")
        model = registration["models"][job["model_role"]]
        events = list(network.worker(identity))
        if job["role"] in ("designer", "critic"):
            # A controller may fail before making any development input.
            supplied = store.development_bundle(
                job, {w["id"]: gold[w["id"]] for w in worlds if w["split"] == "training"})
            checked = audit_development(study, resolved, supplied, model, network=events)
            score = None
        else:
            world = world_index[job["world"]]
            checked = audit(study, resolved, world, model, network=events)
            history = chain(resolved, outcomes)
            questions = world["panel"] + (world["successor"] if job["stage"] == "D" else [])
            score = (assess(row["result"].get("answer"), questions, gold[world["id"]], source_ids(resolved),
                            inherited_answers=inherited_claims(history, gold[world["id"]]))
                     if checked.get("pass") else None)
        # Failed/skipped audit reason strings are not lineage claims.
        if (bool(checked.get("pass")) != bool(row["audit"].get("pass"))
                or checked.get("pass") and checked != row["audit"] or score != row["score"]):
            raise PermissionError("independent raw audit/score differs from sealed outcome: " + identity)
        verified[identity] = {"job": resolved, "status": row["status"], "audit": checked, "score": score}
        if job["role"] == "investigator":
            subset = gold[world["id"]]["subsets"]["+".join(sorted(source_ids(resolved)))]
            verified[identity].update(
                revision=revision_metrics(resolved, score, history, world, gold[world["id"]]),
                uncertainty=uncertainty_metrics(
                    score, assigned_questions=len(questions),
                    identified_questions=sum(subset["questions"][q["id"]]["identified"] for q in questions)))
    # Recompute locks even when no held-out context happens to consume T2.
    store.protocol_lock()
    primary = None
    if not registration["fixture"]:
        primary = summarize(worlds, jobs, {j["id"]: verified[j["id"]] for j in jobs
                                          if j["phase"] == "test" and j["stage"] == "D"},
                            bootstrap_samples=bootstrap_samples)
    resources = resource_report(study, registration, verified, network.all())
    report = {
        "fixture": registration["fixture"], "research_complete": False,
        "scientific_inference": False, "primary_analysis_available": not registration["fixture"],
        "binding": binding, "provider_sha256": network.sha256,
        "execution_implementation_hashes": registration["implementation_hashes"],
        "evaluator_implementation_hashes": implementation_hashes(),
        "evaluated_positions": len(verified), "statuses": dict(Counter(r["status"] for r in verified.values())),
        "primary": primary,
        "revision_and_uncertainty": aggregate_revision(list(verified.values()), worlds, draws=bootstrap_samples),
        "robustness": control_report(list(verified.values()), worlds, draws=bootstrap_samples),
        "resources": resources,
        "remaining_final_gate": ["independent cold REF binding", "pre-API Git/lock time and ledger audit",
                                 "registered H1-H6 decision synthesis and resource paired uncertainty"],
        "scope": "Reconstructed raw traces and scores; not private reasoning. Fixture primary significance "
                 "is deliberately omitted, not computed from a reduced denominator.",
    }
    # Frozen cached outcomes are only used within this read-only evaluation.
    # Reopen every raw manifest after computation, not just stat metadata.
    for identity, row in outcomes.items():
        if load_outcome(study, identity) != row:
            raise PermissionError("outcome changed during independent evaluation")
    network.verify()
    after = {"registration": digest(study / "registration.json"),
             "corpus": digest(study / "oracle.json"), "gold": signature(gold),
             "job_ledger": digest(study / "jobs.sqlite3"),
             "locks": {p.name: digest(p) for p in (study / "locks").glob("*.json")}}
    if after != binding:
        raise PermissionError("study changed during evaluation")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--gold-cache", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus = read(args.corpus)
    _, gold = verified_gold(args.gold_cache, corpus, implementation_hashes())
    actual = read(args.study / "oracle.json")["worlds"]
    known = {w["id"]: w for w in corpus["worlds"]}
    if any(known.get(w["id"]) != w for w in actual):
        raise PermissionError("study worlds differ from independently verified corpus")
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(args.study.resolve()):
        raise ValueError("fresh report outside immutable study required")
    report = evaluate(args.study, {w["id"]: gold[w["id"]] for w in actual})
    write_once(output, report)
    if read(output) != report:
        raise OSError("report reopen differs")
    print(json.dumps({"output": str(output), "sha256": digest(output),
                      "positions": report["evaluated_positions"], "statuses": report["statuses"],
                      "fixture": report["fixture"], "research_complete": False}))


if __name__ == "__main__":
    main()
