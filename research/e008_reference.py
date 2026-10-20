"""Isolated cold REF execution and independent answer/resource verification."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from .common import PROJECT, ROOT, command, digest, source_hashes, write_json
from .e008_locks import read, write_once
from .profiles import create_worker
from .sandbox import container_command, image_id

PROGRAMS = ("e008_reference_worker.py", "e008_scm.py")


def public_reference_input(world):
    return {"evidence": world["evidence"], "questions": world["panel"] + world["successor"]}


def audit_reference(run, image, world, gold):
    worker = run / "worker"
    manifest = read(run / "manifest.json")
    execution = read(run / "execution.json")
    if source_hashes(worker) != manifest["worker_hashes"]:
        raise PermissionError("REF worker files changed")
    if read(worker / "repo/input.json") != public_reference_input(world):
        raise PermissionError("REF received more/different evidence or questions")
    for name in PROGRAMS:
        if digest(worker / "repo" / name) != digest(PROJECT / "research" / name):
            raise PermissionError("REF solver differs from frozen source")
    expected = container_command(image, manifest["container_name"], worker, ["e008_reference_worker.py"])
    if execution["command"] != expected:
        raise PermissionError("REF isolation/mounts differ from assigned container")
    if execution["exit_status"] != 0:
        return {"pass": False, "execution_failed": True, "new_correct": 0, "new_total": 10}
    answer = json.loads(execution["stdout"])
    questions = world["panel"] + world["successor"]
    if len(answer["answers"]) != len(questions):
        raise ValueError("REF answer count differs")
    rows = []
    for question, actual in zip(questions, answer["answers"]):
        expected = gold["subsets"]["EA+EB+EC"]["questions"][question["id"]]
        correct = (actual["id"] == question["id"] and type(actual["value"]) is type(expected["expected"])
                   and actual["value"] == expected["expected"] and actual["identified"] == expected["identified"])
        rows.append({"id": question["id"], "correct": correct})
    new = [row for row in rows if row["id"].startswith("Q")]
    if len(new) != 10:
        raise ValueError("registered ten successor questions required")
    metrics = answer["resources"]
    if (set(metrics) != {"solve_wall_seconds", "process_cpu_seconds", "peak_resident_bytes"}
            or any(type(v) not in (int, float) or v < 0 for v in metrics.values())
            or not 0 < metrics["peak_resident_bytes"] <= 256 * 1024 ** 2):
        raise ValueError("invalid cold reference measurements")
    return {"pass": all(r["correct"] for r in rows), "new_correct": sum(r["correct"] for r in new),
            "new_total": len(new), "answers": rows, "cold_process_per_world": True,
            "resources": {**metrics, "container_wall_seconds": execution["wall_seconds"],
                          "input_bytes": (worker / "repo/input.json").stat().st_size,
                          "program_bytes": sum((worker / "repo" / n).stat().st_size for n in PROGRAMS),
                          "stdout_bytes": len(execution["stdout"].encode()), "model_API_requests": 0,
                          "cost_USD": None,
                          "scope": "CPU/RSS of local solver; not comparable to unobserved provider GPU/CPU memory"}}


def run_reference(study, image, world, gold):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", world["id"]):
        raise ValueError("simple reference world identity required")
    run = Path(study) / "references" / world["id"]
    if run.exists():
        # A completed cold baseline is reused, not re-run to improve timing.
        if not (run / "audit.json").exists():
            raise RuntimeError("orphan/incomplete REF; inspect actual process, never relaunch")
        result = audit_reference(run, image, world, gold)
        if result != read(run / "audit.json"):
            raise PermissionError("archived REF measurement/assessment changed")
        return result
    run.mkdir(parents=True)
    worker = run / "worker"
    create_worker(worker, "A", "none")
    (worker / "repo/PROMPT.txt").write_text("Deterministic REF reads only input.json; no model or MCP requests.\n",
                                          encoding="utf-8")
    for name in PROGRAMS:
        (worker / "repo" / name).write_bytes((PROJECT / "research" / name).read_bytes())
    write_json(worker / "repo/input.json", public_reference_input(world))
    name = "continuum-" + Path(study).name + "-ref-" + world["id"]
    write_once(run / "manifest.json", {"container_name": name, "worker_hashes": source_hashes(worker),
                                      "input_sha256": digest(worker / "repo/input.json")})
    argv = container_command(image, name, worker, ["e008_reference_worker.py"])
    started = time.monotonic()
    try:
        execution = command(argv, timeout=120)
    except subprocess.TimeoutExpired as exc:
        stopped = command(["docker", "rm", "-f", name], timeout=15)
        write_json(run / "timeout-cleanup.json", stopped)
        text = lambda value: value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
        execution = {"command": argv, "cwd": str(PROJECT), "stdout": text(exc.stdout), "stderr": text(exc.stderr),
                     "exit_status": None, "failure_type": "TimeoutExpired"}
    execution["wall_seconds"] = time.monotonic() - started
    write_once(run / "execution.json", execution)
    verified = audit_reference(run, image, world, gold)
    write_once(run / "audit.json", verified)
    return verified


def fixture(identity, original):
    if not identity.startswith("e008-reference-fixture-") or not all(c.isalnum() or c == "-" for c in identity):
        raise ValueError("new REF fixture identity required")
    original = Path(original).resolve(strict=True)
    world = read(original / "oracle.json")["worlds"][0]
    gold = read(original / "gold.json")
    study = ROOT / "runs" / identity
    study.mkdir(exist_ok=False)
    image = image_id("python:3.11-slim-bookworm")
    first = run_reference(study, image, world, gold)
    assert first["pass"] and first["new_correct"] == 10
    before = {str(p): digest(p) for p in study.rglob("*") if p.is_file()}
    assert run_reference(study, image, world, gold) == first
    assert {str(p): digest(p) for p in study.rglob("*") if p.is_file()} == before
    report = {"pass": True, "fixture": True, "model_API_requests": 0, "cold_executions": 1,
              "terminal_resume_reused": True, "original_world": world["id"], "result": first}
    write_once(study / "fixture-result.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity")
    parser.add_argument("--original-fixture", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(fixture(args.identity, args.original_fixture)))
