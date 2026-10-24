"""Reproducible E009 offline foundation gate. Never imports an API provider."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time

from .common import PROJECT, clean_env, write_json
from .e009_oracle import Oracle, solve
from .e009_planning import planning_report
from .e009_revision import canonical, reference_revision, score_revision
from .e009_scm import NAMES, development_corpus, distribution, models


def handoff(output):
    parent = None
    outcomes = []
    for stage in "ABCDE":
        spec = {"db": str(output / "handoff.sqlite3"), "actor": "e009-fixture-" + stage,
                "parent_sha256": parent, "crash_after_commit": stage == "C",
                "event": {"stage": stage, "status": "undetermined" if stage in "CDE" else "supported",
                          "scope": "scripted transport fixture; not model inference"}}
        input_path = output / f"{stage}-input.json"
        result_path = output / f"{stage}-result.json"
        write_json(input_path, spec)
        command = [sys.executable, "-m", "research.e009_handoff", "--input", str(input_path), "--output", str(result_path)]
        started = time.monotonic()
        run = subprocess.run(command, cwd=PROJECT, env=clean_env(), capture_output=True,
                             text=True, encoding="utf-8", timeout=90)
        record = {"command": command, "cwd": str(PROJECT), "stdin": "",
                  "stdout": run.stdout, "stderr": run.stderr, "exit_status": run.returncode,
                  "elapsed_seconds": time.monotonic() - started}
        write_json(output / f"{stage}-command.json", record)
        assert run.returncode == (17 if stage == "C" else 0), record
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert len(result["payload"]["events"]) == len(outcomes) + 1
        if outcomes:
            assert result["parent_actor"] == outcomes[-1]["actor"]
        parent = result["sha256"]
        outcomes.append(result)
    assert not outcomes[2]["acknowledged"] and outcomes[3]["parent_actor"] == "e009-fixture-C"
    assert len({r["pid"] for r in outcomes}) == 5
    return {"processes": 5, "stages": "ABCDE", "C_exit": 17, "D_reads_C_committed_object": True,
            "model_calls": 0, "payload_bytes": sum(r["payload_bytes"] for r in outcomes),
            "decoded_sdk_json_bytes": sum(r["decoded_sdk_json_bytes"] for r in outcomes),
            "wire_overhead_measured": False, "filesystem_sandbox_verified": False}


def execute(output, simulations=1000):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    source_paths = sorted(PROJECT.glob("research/e009_*.py")) + [PROJECT / name for name in
        ("continuum/store.py", "continuum/mcp_server.py", "research/common.py", "research/preflight.py",
         "tests/test_e009.py", "docs/research/E009-PREREGISTRATION.json")]
    hashes = {}
    for path in source_paths:
        relative = path.relative_to(PROJECT)
        raw = path.read_bytes()
        destination = output / "source" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        hashes[relative.as_posix()] = hashlib.sha256(raw).hexdigest()
    write_json(output / "PROVENANCE.json", {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
        "dirty_status": subprocess.check_output(["git", "status", "--short"], cwd=PROJECT, text=True),
        "source_hashes": hashes, "python": sys.version, "executable": sys.executable,
        "mcp_version": importlib.metadata.version("mcp"), "host_model": "not_exposed",
        "experimental_model": "deterministic-fixture; no LLM", "command_argv": sys.argv,
        "instructions": "E009 draft-001; user request 2026-10-24; source-hashed offline gate",
        "simulations": simulations})
    corpus = development_corpus()
    write_json(output / "DEVELOPMENT-CORPUS.json", corpus)
    oracle = Oracle(models())
    digest = hashlib.sha256()
    interventions = [()] + [((name, value),) for name in NAMES for value in (0, 1)]
    interventions.append((("X", 1), ("Y", 0)))
    checked = 0
    for index, model in enumerate(models()):
        for do in interventions:
            forward, independent = distribution(index, do), solve(model, do)
            assert forward == independent, (index, do)
            digest.update(canonical([index, do, independent]))
            checked += 1
    outcomes = []
    for world in corpus["worlds"]:
        current, history, answer = reference_revision(world, oracle)
        score = score_revision(world, current, history, answer, oracle)
        assert score["bri"] == 1
        before = oracle.compatible(world["evidence"][:1])
        after = oracle.compatible(world["evidence"][:2])
        p = {k: world["withdrawal"][k] for k in ("query", "value")}
        withdrawal = [oracle.status(after, p), oracle.status(before, p)]
        assert withdrawal == ["supported", "undetermined"]
        outcomes.append({"world": world["id"], "reference": score, "withdrawal": withdrawal,
                         "candidate_counts": world["candidate_counts"]})
    write_json(output / "ORACLE-AUDIT.json", {"pass": True, "distributions_compared": checked,
                                              "stream_sha256": digest.hexdigest(), "worlds": outcomes})
    plan = planning_report(simulations)
    write_json(output / "POWER-COST.json", plan)
    transport = handoff(output)
    report = {"pass": True, "scope": "offline foundation only; Phase 2 incomplete",
              "worlds": len(corpus["worlds"]), "model_parameterizations": len(models()),
              "distributions_compared": checked, "stream_sha256": digest.hexdigest(),
              "controlled_refutation_opportunities": len(outcomes),
              "source_withdrawal_opportunities": len(outcomes),
              "scripted_reference_BRI_passes": len(outcomes), "LLM_BRI": None,
              "handoff": transport, "model_requests": 0, "heldout_created": False,
              "elapsed_seconds": time.monotonic() - started,
              "remaining": ["diverse dependency graph generator and adversarial corpus",
                            "natural-track measurement and full A-E BRI evaluator",
                            "sandboxed model worker, immutable evidence versions and raw replay",
                            "full MCP wire-byte accounting and live controller/retry/STOP gates",
                            "T2 two-line development, pilot lock, calibration, final preregistration"]}
    write_json(output / "SUMMARY.json", report)
    assert all(hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() == digest
               for name, digest in hashes.items()), "source changed during offline gate"
    manifest = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in output.rglob("*") if p.is_file()}
    write_json(output / "MANIFEST.json", manifest)
    print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--simulations", type=int, default=1000)
    args = parser.parse_args()
    execute(args.output, args.simulations)
