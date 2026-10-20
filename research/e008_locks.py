"""Immutable E008 outcomes and split-restricted calibration/development decisions.

The live runner must independently audit and score a context before sealing it.
These integrity locks are not substitutes for the final raw-trace re-audit.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
from contextlib import closing
import copy
import time

from .common import digest
from .e008_audit import snapshot
from .e008_design import select_budget, select_protocol, signature
from .e008_development import development_input, training_projection

TERMINAL = {"completed", "budget_rejected", "failed", "failed_controller",
            "skipped_dependency", "secondary_unavailable", "injected_crash_after_commit"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_once(path, value):
    """Idempotent verification, never silent replacement of an existing decision."""
    value = json.loads(json.dumps(value, allow_nan=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise PermissionError("immutable E008 record changed: " + path.name)
        return value
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return value


def unit_path(study, identity):
    if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", identity):
        raise ValueError("simple registered position ID required")
    return study / "units" / identity


def file_manifest(run):
    if run.is_symlink() or getattr(run, "is_junction", lambda: False)():
        raise PermissionError("redirected unit root")
    files = {}
    for path in sorted(run.rglob("*")):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise PermissionError("redirected unit input/output")
        if path.is_file() and path != run / "outcome.json":
            files[path.relative_to(run).as_posix()] = digest(path)
    return files


def seal_outcome(study, job, audit, score=None):
    run = unit_path(study, job["id"])
    result = read(run / "result.json")
    if result.get("job") != job or result.get("status") not in TERMINAL:
        raise ValueError("only the actual assigned terminal result can be sealed")
    if result["status"] in {"completed", "budget_rejected", "injected_crash_after_commit"} and audit.get("pass") is not True:
        raise PermissionError("successful execution failed independent lineage audit")
    write_once(run / "audit.json", audit)
    write_once(run / "assessment.json", score)
    value = {"job": job, "status": result["status"], "audit": audit, "score": score,
             "result": result, "files": file_manifest(run)}
    return write_once(run / "outcome.json", value)


def load_outcome(study, identity):
    run = unit_path(study, identity)
    value = read(run / "outcome.json")
    if (value["files"] != file_manifest(run) or value["result"] != read(run / "result.json")
            or value["audit"] != read(run / "audit.json") or value["score"] != read(run / "assessment.json")
            or value["job"] != value["result"].get("job") or value["job"]["id"] != identity
            or value["status"] != value["result"].get("status") or value["status"] not in TERMINAL):
        raise PermissionError("sealed context evidence changed")
    return value


def validate_assignment(job, value):
    resolved = value["job"]
    dynamic = {"budget", "protocol_version", "bulletin", "verification_disabled", "crash_after_commit"}
    if any(resolved.get(k) != v for k, v in job.items() if k not in dynamic):
        raise PermissionError("outcome not bound to its assigned condition/split/lineage")
    if set(resolved) - set(job) - dynamic:
        raise PermissionError("unregistered input in resolved position")
    for key in ("budget", "protocol_version"):
        if job.get(key) is not None and resolved.get(key) != job[key]:
            raise PermissionError("fixed assignment changed")
    return value


class EvidenceSnapshot:
    """Process-local verified terminal prefix, never persisted as a trust cache.

    Selection uses copies of these already verified values, not re-read mutable
    files. Archive copying and prior-chain scoring still verify consumed bytes.
    Every raw file and ledger row is rechecked on resume and batch exit.
    """

    def __init__(self, study, jobs):
        from .e003 import Jobs
        from .e008_execute import ledger_key
        self.study, self.jobs = Path(study), copy.deepcopy(list(jobs))
        self.assignments = {j["id"]: j for j in self.jobs}
        self.binding = signature(jobs)
        self.outcomes, self.seals, self.unit_sizes = {}, {}, {}
        self.active = None
        states = Jobs(self.study / "jobs.sqlite3").state()
        if set(states) != {ledger_key(j) for j in jobs}:
            raise PermissionError("snapshot ledger differs from registered assignments")
        pending = False
        for ordinal, job in enumerate(jobs):
            state = states[ledger_key(job)]
            if state["ordinal"] != ordinal or state["status"] == "running":
                raise PermissionError("wrong order or running/orphan context")
            if state["status"] == "pending":
                pending = True
            elif pending:
                raise PermissionError("terminal position after an unfinished assignment")
            else:
                self.record(job["id"])
        self.verify_all()
        self.frozen_input_sizes = {}
        gold = self.study / "gold"
        if gold.exists():
            from .e008_resources import directory_bytes
            self.frozen_input_sizes["gold"] = directory_bytes(gold)
        self.input_manifest = {name: digest(self.study / name) for name in
                               ("registration.json", "oracle.json", "gold/manifest.json")
                               if (self.study / name).exists()}
        if gold.exists():
            from .common import source_hashes
            self.input_manifest.update({"gold/" + name: sha for name, sha in source_hashes(gold).items()})

    def record(self, identity):
        from .e008_execute import ledger_key
        from .e008_resources import directory_bytes
        if len(self.outcomes) >= len(self.jobs) or self.jobs[len(self.outcomes)]["id"] != identity:
            raise PermissionError("only next assigned terminal outcome can enter snapshot")
        job = self.jobs[len(self.outcomes)]
        value = validate_assignment(job, load_outcome(self.study, identity))
        with closing(sqlite3.connect(self.study / "jobs.sqlite3")) as db:
            row = db.execute("SELECT status,report FROM jobs WHERE id=?", (ledger_key(job),)).fetchone()
        if not row or row[0] != value["status"] or json.loads(row[1]) != value["result"]:
            raise PermissionError("snapshot outcome and job ledger disagree")
        self.outcomes[identity] = value
        self.seals[identity] = digest(unit_path(self.study, identity) / "outcome.json")
        self.unit_sizes[identity] = directory_bytes(unit_path(self.study, identity))
        self.active = None

    def get(self, job):
        if self.assignments.get(job["id"]) != job:
            raise PermissionError("snapshot assignments changed")
        if job["id"] not in self.outcomes:
            raise PermissionError("unverified or unfinished selection source")
        return validate_assignment(job, copy.deepcopy(self.outcomes[job["id"]]))

    def next_job(self):
        from .e008_execute import ledger_key
        if signature(self.jobs) != self.binding:
            raise PermissionError("snapshot schedule changed")
        with closing(sqlite3.connect(self.study / "jobs.sqlite3")) as db:
            if (db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] != len(self.jobs)
                    or db.execute("SELECT 1 FROM jobs WHERE status='running' LIMIT 1").fetchone()):
                raise PermissionError("changed ledger or live/orphan context")
            if len(self.outcomes) == len(self.jobs):
                return None
            job = self.jobs[len(self.outcomes)]
            row = db.execute("SELECT id,status FROM jobs WHERE ordinal=?", (len(self.outcomes),)).fetchone()
        if row != (ledger_key(job), "pending"):
            raise PermissionError("snapshot cursor differs from next pending assignment")
        return job

    def verify_all(self):
        from .e003 import Jobs
        from .e008_execute import ledger_key
        states = Jobs(self.study / "jobs.sqlite3").state()
        if set(states) != {ledger_key(j) for j in self.jobs}:
            raise PermissionError("snapshot exit ledger assignment changed")
        actual_units = self.study / "units"
        if actual_units.is_symlink() or getattr(actual_units, "is_junction", lambda: False)():
            raise PermissionError("redirected units root")
        present = {p.name for p in actual_units.iterdir()} if actual_units.exists() else set()
        if present != set(self.outcomes):
            raise PermissionError("unsealed/orphan/foreign unit at snapshot boundary")
        for ordinal, job in enumerate(self.jobs):
            row = states[ledger_key(job)]
            if row["ordinal"] != ordinal:
                raise PermissionError("snapshot ledger ordinal changed")
            if job["id"] in self.outcomes:
                value = load_outcome(self.study, job["id"])
                if (value != self.outcomes[job["id"]] or row["report"] != value["result"]
                        or row["status"] != value["status"]
                        or digest(unit_path(self.study, job["id"]) / "outcome.json") != self.seals[job["id"]]):
                    raise PermissionError("original verified prefix changed")
            elif row["status"] != "pending" or row["report"] is not None:
                raise PermissionError("unrecorded terminal/orphan position")
        for name, sha in getattr(self, "input_manifest", {}).items():
            if digest(self.study / name) != sha:
                raise PermissionError("frozen snapshot input changed")

def publication_value(study, row):
    job = row["job"]
    if row["status"] != "completed" or row["audit"].get("pass") is not True or not row["result"].get("saved"):
        return None
    slot = ("protocol:" if job["role"] == "designer" else "review:") + f'{job["lineage"]}-v{job["version"]}'
    _, index, objects = snapshot(unit_path(study, job["id"]) / "state/continuum.sqlite3")
    if len(row["audit"]["accepted"]) != 1 or row["audit"]["accepted"][0]["slot"] != slot:
        raise PermissionError("publication audit not bound to selected protocol")
    sha = index[slot]
    if row["audit"]["accepted"][0]["sha256"] != sha:
        raise PermissionError("publication audit bytes changed")
    value = json.loads(objects[sha]["content"])
    if value["version"] != f'{job["lineage"]}-v{job["version"]}':
        raise PermissionError("wrong protocol identity in published content")
    return value


class DecisionStore:
    """Construct decisions only from their registered earlier splits/lineages."""

    def __init__(self, study, worlds, jobs):
        self.study = Path(study)
        self.worlds = {w["id"]: w for w in worlds}
        self.jobs = list(jobs)
        if len(self.worlds) != len(worlds) or len({j["id"] for j in jobs}) != len(jobs):
            raise ValueError("unique registered worlds and positions required")
        if read(self.study / "registration.json")["schedule"] != jobs:
            raise PermissionError("schedule differs from registration")
        if read(self.study / "oracle.json")["worlds"] != worlds:
            raise PermissionError("worlds differ from frozen corpus")
        self.binding = {"registration_sha256": digest(self.study / "registration.json"),
                        "corpus_sha256": digest(self.study / "oracle.json"), "schedule_sha256": signature(jobs)}
        self.worlds_signature = signature(worlds)

    def _check_binding(self):
        if (digest(self.study / "registration.json") != self.binding["registration_sha256"]
                or digest(self.study / "oracle.json") != self.binding["corpus_sha256"]
                or signature(self.jobs) != self.binding["schedule_sha256"]
                or signature(list(self.worlds.values())) != self.worlds_signature):
            raise PermissionError("registered decision inputs changed")

    def _outcome(self, job):
        self._check_binding()
        return validate_assignment(job, load_outcome(self.study, job["id"]))

    def _sources(self, jobs):
        for job in jobs:
            self._outcome(job)
        return {j["id"]: digest(unit_path(self.study, j["id"]) / "outcome.json") for j in jobs}

    def _seal(self, name, decision, sources):
        self._check_binding()
        path = self.study / "locks" / (name + ".json")
        value = json.loads(json.dumps({"binding": self.binding, "decision": decision, "sources": sources},
                                      allow_nan=False))
        if path.exists():
            old = read(path)
            if {k: old[k] for k in value} != value:
                raise PermissionError("decision or its source evidence changed after locking")
            return old
        return write_once(path, dict(value, created_at=time.time()))

    @staticmethod
    def count(row):
        if row["status"] != "completed" or row["audit"].get("pass") is not True:
            return 0
        score = row["score"]
        value = score["new_target_correct"]
        if type(value) is not int or not 0 <= value <= 10 or score["new_total"] != 10:
            raise ValueError("ten common-target questions required for selection")
        return value

    def calibration_lock(self):
        selected = [j for j in self.jobs if j["phase"] == "calibration"]
        sources = self._sources(selected)
        worlds = [w for w in self.worlds.values() if w["split"] == "calibration"]
        records = {}
        for job in selected:
            if job["stage"] != "D" or job["condition"] not in ("C1", "T1"):
                continue
            world = self.worlds[job["world"]]
            if world["split"] != "calibration":
                raise PermissionError("non-calibration world used for budget selection")
            unknown = set(world["design_audit"]["unidentifiable_question_ids"])
            identified = {q["id"] for q in world["successor"]} - unknown
            row = self._outcome(job)
            correct = 0
            if row["status"] == "completed" and row["audit"].get("pass") is True:
                self.count(row)
                answers = {r["id"]: r for r in row["score"]["questions"] if r["id"].startswith("Q")}
                if set(answers) != {q["id"] for q in world["successor"]}:
                    raise ValueError("missing or foreign calibration questions")
                correct = sum(answers[q]["target_correct"] is True for q in identified)
            key = (job["world"], job["condition"], job["budget"])
            if key in records:
                raise ValueError("duplicate calibration cell")
            records[key] = {"identified_correct": correct, "identified_total": len(identified)}
        decision = select_budget(records, [w["id"] for w in worlds])
        return self._seal("calibration", decision, sources)

    def publication(self, lineage, version, role="designer"):
        jobs = [j for j in self.jobs if j["phase"] == "development" and j["role"] == role
                and j["lineage"] == lineage and j["version"] == version]
        if len(jobs) != 1:
            raise ValueError("unique registered publication position required")
        return publication_value(self.study, self._outcome(jobs[0]))

    def validation_feedback(self, lineage, version):
        jobs = [j for j in self.jobs if j["phase"] == "validation" and j["lineage"] == lineage and j["version"] == version]
        sources = self._sources(jobs)
        worlds = [w for w in self.worlds.values() if w["split"] == "validation"]
        successors = [j for j in jobs if j["stage"] == "D"]
        if {j["world"] for j in successors} != {w["id"] for w in worlds} or len(successors) != len(worlds):
            raise ValueError("all assigned validation worlds, including failures, required")
        cases = []
        for ordinal, world in enumerate(worlds, 1):
            job = next(j for j in successors if j["world"] == world["id"])
            row = self._outcome(job)
            case = {"example_id": f"validation-{ordinal:02}", "status": row["status"],
                    "new_target_correct": self.count(row), "new_total": 10}
            if row["status"] == "completed" and row["audit"].get("pass") is True:
                answers = [r for r in row["score"]["questions"] if r["id"].startswith("Q")]
                case["evaluation"] = [{"id": r["id"], "target": r["target_expected"],
                                       "correct": r["target_correct"]} for r in answers]
            # Only public validation tables/questions, not true family/SCM/private metadata.
            case.update(evidence=world["evidence"], questions=world["successor"])
            cases.append(case)
        feedback = {"version": f"{lineage}-v{version}", "scope": "released_validation_only", "cases": cases}
        sealed = self._seal(f"feedback-{lineage}-v{version}", feedback, sources)
        return sealed["decision"]

    def development_bundle(self, job, training_gold):
        if job not in self.jobs or job["phase"] != "development":
            raise PermissionError("unregistered development assignment")
        calibration = self.calibration_lock()
        training_worlds = [w for w in self.worlds.values() if w["split"] == "training"]
        if set(training_gold) != {w["id"] for w in training_worlds}:
            raise PermissionError("training-only reference set required")
        training = [training_projection(w, training_gold[w["id"]], f"training-{i:02}")
                    for i, w in enumerate(training_worlds, 1)]
        version = job["version"] - (job["role"] == "designer")
        protocol = review = feedback = None
        if version:
            protocol = self.publication(job["lineage"], version)
            feedback = self.validation_feedback(job["lineage"], version)
            if job["role"] == "designer":
                review = self.publication(job["lineage"], version, "critic")
        supplied = development_input(job, training, calibration["decision"]["budget"],
                                     protocol=protocol, review=review, feedback=feedback)
        if len(json.dumps(supplied).encode()) > 120000:
            raise ValueError("registered development input envelope exceeded; no silent truncation")
        return supplied

    def protocol_lock(self):
        calibration = self.calibration_lock()
        earlier = [j for j in self.jobs if j["phase"] in ("development", "validation")]
        sources = self._sources(earlier)
        world_ids = [w["id"] for w in self.worlds.values() if w["split"] == "validation"]
        selected = {}
        for lineage in ("L1", "L2"):
            proposals = {v: self.publication(lineage, v) for v in (1, 2, 3)}
            records = {}
            for job in earlier:
                if job["phase"] == "validation" and job["stage"] == "D" and job["lineage"] == lineage:
                    key = (job["version"], job["world"])
                    if key in records:
                        raise ValueError("duplicate validation selection cell")
                    records[key] = self.count(self._outcome(job))
            choice = select_protocol(records, world_ids, available_versions=[v for v, p in proposals.items() if p is not None])
            selected[lineage] = {**choice, "protocol": proposals.get(choice["version"])}
        return self._seal("protocol", {"lineages": selected, "memory_budget": calibration["decision"]["budget"],
                                      "calibration_lock_sha256": digest(self.study / "locks/calibration.json")}, sources)


class SnapshotDecisions(DecisionStore):
    """Immutable selection values for one verified controller batch only."""

    def __init__(self, study, worlds, jobs, evidence):
        super().__init__(study, worlds, jobs)
        if evidence.study != self.study or evidence.jobs != self.jobs:
            raise PermissionError("decision snapshot belongs to another study")
        self.evidence, self.memo = evidence, {}

    def _outcome(self, job):
        return self.evidence.get(job)

    def _sources(self, jobs):
        for job in jobs:
            self._outcome(job)
        return {j["id"]: self.evidence.seals[j["id"]] for j in jobs}

    def _cached(self, key, create):
        self._check_binding()
        if key not in self.memo:
            value = create()
            proof = {p.name: digest(p) for p in (self.study / "locks").glob("*.json")}
            self.memo[key] = (copy.deepcopy(value), proof)
        value, proof = self.memo[key]
        if any(digest(self.study / "locks" / name) != sha for name, sha in proof.items()):
            raise PermissionError("locked selection changed during controller batch")
        return copy.deepcopy(value)

    def calibration_lock(self):
        return self._cached(("calibration",), super().calibration_lock)

    def publication(self, lineage, version, role="designer"):
        return self._cached(("publication", lineage, version, role),
                            lambda: super(SnapshotDecisions, self).publication(lineage, version, role))

    def validation_feedback(self, lineage, version):
        return self._cached(("feedback", lineage, version),
                            lambda: super(SnapshotDecisions, self).validation_feedback(lineage, version))

    def protocol_lock(self):
        return self._cached(("protocol",), super().protocol_lock)
