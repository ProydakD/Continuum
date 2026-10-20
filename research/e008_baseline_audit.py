"""Read-only E006/E007 C1 audit; never reruns or rewrites either experiment."""
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import statistics

from .common import ROOT, digest
from .e003 import job_id
from .e005_audit import audit as audit_e006
from .e005_protocol import reader_prompt, writer_prompt
from .e007_audit import audit as audit_e007, score
from .e007_protocol import prompt


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def inspect_study(study, experiment):
    inputs = read_json(study / "oracle.json")
    registration = read_json(study / "registration.json")
    published = read_json(study / "report.json")
    worlds = inputs["worlds"] if experiment == "E006" else inputs["splits"]["test"]
    by_world = {w["id"]: w for w in worlds}
    jobs = [r["job"] for r in published["rows"] if r["job"]["condition"] == "C1"
            and r["job"].get("budget") == 32 and r["job"]["world"] in by_world
            and r["job"].get("phase", "test") == "test"]
    network = [json.loads(s) for s in (study / "provider.jsonl").read_text(encoding="utf-8").splitlines()]
    rows, prompt_examples, fingerprint = [], {}, {}
    for job in jobs:
        identity = job_id(job) if experiment == "E006" else job["id"]
        run = study / "units" / identity
        stage, world = job["stage"], by_world[job["world"]]
        result_path = run / "result.json"
        result = read_json(result_path)
        fingerprint[str(result_path)] = digest(result_path)
        row = {"id": identity, "world": world["id"], "stage": stage, "status": result["status"]}
        if result["status"] == "skipped_dependency":
            row["lineage_verified"] = False
            row["executed"] = False
            rows.append(row)
            continue
        stored_prompt = read_json(run / "workers" / stage / "repo/PROMPT.txt")["prompt"]
        want = (writer_prompt(world, "C1", 32) if stage == "A" else reader_prompt(world)) if experiment == "E006" else prompt(job, world)
        if stored_prompt != want:
            raise ValueError("Frozen prompt differs from historical builder: " + identity)
        prompt_examples.setdefault(stage, stored_prompt)
        audited = audit_e006(run, world, job, network) if experiment == "E006" else audit_e007(study, job, "gpt-6-sol", network)
        if not audited["pass"]:
            raise ValueError("Historical lineage failed: " + identity + ": " + json.dumps(audited))
        row.update(lineage_verified=True, executed=True)
        if stage == "A":
            row.update(memory=audited.get("memory"), attempts=result["save_attempts"], saved=result["saved"],
                       bytes=audited.get("bytes", audited.get("memory_bytes", 0)))
        else:
            checked = audited if experiment == "E006" else score(result["answer"], world)
            row.update(rule_correct=checked["rule_correct"], answer=result["answer"])
            row["fields"] = checked["fields"] if experiment == "E006" else {
                "correct": checked["correct_fields"], "unknown": checked["null_fields"], "wrong": checked["wrong_fields"]}
        rows.append(row)
    writers, readers = ([r for r in rows if r["stage"] == s] for s in ("A", "C"))
    saved = [r for r in writers if r["saved"]]
    requests = [e for e in network if e.get("worker") in {r["id"] for r in rows} and e["event"] == "request_started"]
    calls = Counter(tuple(t["name"] for t in r["payload"]["tools"]) for r in requests)
    identities = {json.dumps(w["rule"], sort_keys=True) for w in worlds}
    provenance = {str(study / n): digest(study / n) for n in ("oracle.json", "report.json", "registration.json", "provider.jsonl")}
    provenance.update(fingerprint)
    return {
        "study": str(study), "worlds": len(worlds), "lineage_verified": sum(r["lineage_verified"] for r in rows),
        "assigned_positions": len(rows), "status_counts": dict(Counter(r["status"] for r in rows)),
        "writers_saved": len(saved), "second_attempts": sum(r["attempts"] == 2 for r in writers),
        "rule_correct": sum(r.get("rule_correct", False) for r in readers),
        "fields_executed_readers": {k: sum(r.get("fields", {}).get(k, 0) for r in readers) for k in ("correct", "unknown", "wrong")},
        "mean_accepted_bytes": statistics.mean(r["bytes"] for r in saved),
        "max_output_tokens_observed": sorted({r["payload"]["max_output_tokens"] for r in requests}),
        "tool_schemas_observed": [{"names": list(k), "requests": v} for k, v in calls.items()],
        "limits": registration["limits"], "prompt_examples": prompt_examples, "rows": rows,
        "files_sha256": provenance, "rule_identities": sorted(identities),
    }


def audit():
    results = {e: inspect_study(ROOT / "runs" / p, e)
               for e, p in (("E006", "e006-series-002"), ("E007", "e007-series-001"))}
    overlap = set(results["E006"]["rule_identities"]) & set(results["E007"]["rule_identities"])
    # Normalize only the task-specific values, retaining every instruction word.
    template = {"rule": {"TARGET_RULE": 0}, "queries": ["TARGET_QUERIES"]}
    normalized = {
        "writer": [writer_prompt(template, "C1", 32), prompt({"role": "writer", "budget": 32}, template)],
        "reader": [reader_prompt(template), prompt({"role": "reader", "budget": 32}, template)],
    }
    differences = {role: "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                    fromfile="E006-C1-" + role, tofile="E007-C1-" + role))
                   for role, (a, b) in normalized.items()}
    return {
        "pass": True, "scope": "Descriptive historical audit, not a randomized causal contrast or new model series.",
        "historical_studies_read_only": True, "E008_model_requests": 0,
        "full_rule_overlap": len(overlap), "studies": results, "normalized_prompts": normalized,
        "literal_instruction_diffs": differences,
        "causal_explanation_identified": False,
        "conclusion": "Different disjoint worlds, changed writer/reader instructions, added parameter domains, tools and inference budget are confounded. Observed content loss is not evidence that one particular change caused the accuracy drop.",
    }


if __name__ == "__main__":
    import sys
    result = audit()
    destination = Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({e: {k: v for k, v in r.items() if k in (
        "worlds", "lineage_verified", "assigned_positions", "status_counts", "writers_saved",
        "second_attempts", "rule_correct", "fields_executed_readers", "mean_accepted_bytes",
        "max_output_tokens_observed", "tool_schemas_observed")} for e, r in result["studies"].items()}, ensure_ascii=False))
    print(json.dumps({"full_rule_overlap": result["full_rule_overlap"], "audit_sha256": digest(destination),
                      "causal_explanation_identified": False}))
