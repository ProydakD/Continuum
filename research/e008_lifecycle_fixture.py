"""Real reduced calibration -> development -> validation -> locked handoff.

Scripted providers and four previously generated worlds; not a model result,
not scientific calibration, and never a replacement for the full live schedule.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import time

from .common import ROOT, digest
from .e003 import Jobs, implementation_hashes
from .e008_controller import run_next
from .e008_design import schedule
from .e008_development_fixture import Provider as DevelopmentProvider
from .e008_execute import ledger_record
from .e008_fixture import fixture_reasoning, fixture_view
from .e008_live import controller_lock, verified_gold
from .e008_locks import DecisionStore, load_outcome, read, unit_path, write_once
from .e008_resources import SeriesLedger, SeriesStopped, resource_policy
from .sandbox import image_id


class LifecycleProvider(DevelopmentProvider):
    """Public-input-only inference with compact evidence, plus existing authors."""

    def respond(self, worker, history, tools, timeout=30, max_output_tokens=8192):
        job = self.jobs[worker]
        if job["role"] in ("designer", "critic"):
            return super().respond(worker, history, tools, timeout, max_output_tokens)
        self.attempt += 1
        public, calls, outputs, predecessor, records = fixture_view(history)
        names = [c["name"] for c in calls]
        name, arguments = None, None
        if "read_protocol" not in names:
            name, arguments = "read_protocol", {}
        elif "read_memory" not in names:
            name, arguments = "read_memory", {}
        elif "verify_evidence" not in names:
            name, arguments = "verify_evidence", {"record": public["evidence"][0]}
        elif public["stage"] != "D" and (names.count("save_memory") == 0 or
                not outputs[-1].get("saved", False) and names.count("save_memory") < 2):
            # A scripted test payload, not compliance evidence for the T1 prompt.
            name, arguments = "save_memory", {
                "content": json.dumps({"evidence": records}, separators=(",", ":")), "encoding": "utf8"}
        else:
            status = ("not_applicable" if public["stage"] == "D" else
                      "saved" if outputs[-1].get("saved", False) else "not_saved")
            answer, _ = fixture_reasoning(public, predecessor, records, status)
        output = ([{"type": "function_call", "name": name, "arguments": json.dumps(arguments),
                    "call_id": "lifecycle-fixture-" + str(self.attempt)}] if name else
                  [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(answer)}]}])
        response = {"status": "completed", "model": self.model, "output": output, "fixture": True,
                    "usage": {"input_tokens": 0, "output_tokens": 0}}
        payload = {"model": self.model, "input": history, "tools": tools, "store": False,
                   "parallel_tool_calls": False, "max_output_tokens": max_output_tokens}
        with (self.study / "provider.jsonl").open("a", encoding="utf-8") as stream:
            for row in ({"event": "request_started", "attempt": self.attempt, "worker": worker, "payload": payload},
                        {"event": "response", "attempt": self.attempt, "worker": worker,
                         "response": response, "seconds": 0}):
                stream.write(json.dumps(row) + "\n")
        return response


def fixture(identity, corpus_path, gold_cache):
    if not re_valid(identity):
        raise ValueError("new lifecycle fixture identity required")
    original_hash = digest(corpus_path)
    corpus = read(corpus_path)
    _, all_gold = verified_gold(gold_cache, corpus, implementation_hashes())
    worlds = [next(w for w in corpus["worlds"] if w["split"] == split)
              for split in ("training", "calibration", "validation", "test")]
    gold = {w["id"]: all_gold[w["id"]] for w in worlds}
    jobs = [j for j in schedule(worlds) if j["phase"] != "robustness"
            and (j["phase"] != "test" or j["replicate"] == 1)]
    # Preserve the failed publication and all its dependent skips in selection.
    rejected = next(j for j in jobs if j["role"] == "designer" and j["lineage"] == "L2" and j["version"] == 2)
    rejected["reject_twice"] = True
    study = ROOT / "runs" / identity
    study.mkdir(exist_ok=False)
    reg = {"fixture": True, "image": image_id("python:3.11-slim-bookworm"), "schedule": jobs,
           "implementation_hashes": implementation_hashes(),
           "models": {"primary": "scripted-fixture", "secondary": "scripted-fixture"},
           "limits": {"investigator_seconds": 180, "request_seconds": 90,
                      "output_tokens": 8192, "responses_per_context": 10},
           "scope": "Four-world scripted fixture, one test repetition, no robustness; not the scientific series."}
    write_once(study / "registration.json", reg)
    write_once(study / "oracle.json", {"worlds": worlds})
    write_once(study / "gold.json", gold)
    Jobs(study / "jobs.sqlite3", [ledger_record(j) for j in jobs])
    store = DecisionStore(study, worlds, jobs)
    guard = SeriesLedger(study, resource_policy(jobs))
    guard.start()
    provider = LifecycleProvider(study, jobs)
    results, locked_before_test = [], None
    started = time.monotonic()
    with controller_lock(study):
        for assigned in jobs:
            if assigned["phase"] == "test" and locked_before_test is None:
                lock = store.protocol_lock()
                locked_before_test = digest(study / "locks/protocol.json")
                assert lock["decision"]["lineages"]["L2"]["version"] != 2
                before = copy.deepcopy(Jobs(study / "jobs.sqlite3").state())
                (study / "STOP").write_text("scripted stop before first test\n", encoding="utf-8", newline="\n")
                try:
                    run_next(study, reg, store, gold, provider, guard=guard)
                except SeriesStopped:
                    pass
                else:
                    raise AssertionError("STOP did not prevent held-out dispatch")
                assert Jobs(study / "jobs.sqlite3").state() == before
                (study / "STOP").unlink()
                # Recreate controller and provider. Only scripted event IDs persist.
                store = DecisionStore(study, read(study / "oracle.json")["worlds"], read(study / "registration.json")["schedule"])
                guard = SeriesLedger(study, resource_policy(jobs))
                attempt = provider.attempt
                provider = LifecycleProvider(study, jobs)
                provider.attempt = attempt
            result = run_next(study, reg, store, gold, provider, guard=guard)
            assert result["job"]["id"] == assigned["id"]
            results.append(result)
            print(json.dumps({"job": assigned["id"], "phase": assigned["phase"], "status": result["status"]}), flush=True)
        assert run_next(study, reg, store, gold, provider, guard=guard) is None
    assert locked_before_test == digest(study / "locks/protocol.json")
    assert store.publication("L2", 2) is None
    assert all(load_outcome(study, j["id"])["status"] == "skipped_dependency" for j in jobs
               if j["phase"] == "validation" and j["lineage"] == "L2" and j["version"] == 2)
    for j in jobs:
        if j["role"] in ("designer", "critic"):
            bundle = read(unit_path(study, j["id"]) / "development-input.json")
            assert "truth" not in json.dumps(bundle) and worlds[-1]["id"] not in json.dumps(bundle)
            assert bundle["lineage"] == j["lineage"]
            if j["role"] == "designer" and j["version"] > 1:
                assert bundle["validation_feedback"]["version"] == f'{j["lineage"]}-v{j["version"] - 1}'
    assert digest(corpus_path) == original_hash
    report = {"pass": True, "fixture": True, "model_API_requests": 0, "positions": len(jobs),
              "statuses": dict(Counter(r["status"] for r in results)), "seconds": time.monotonic() - started,
              "calibration_budget": store.calibration_lock()["decision"]["budget"],
              "protocol_lock_sha256": locked_before_test, "protocol_locked_before_first_test": True,
              "failed_proposal_not_replaced": True, "own_lineage_prior_feedback_only": True,
              "STOP_and_resume_before_test": True, "source_corpus_unchanged": True}
    write_once(study / "fixture-result.json", report)
    return report


def re_valid(identity):
    return identity.startswith("e008-lifecycle-fixture-") and all(c.isalnum() or c == "-" for c in identity)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--gold-cache", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(fixture(args.identity, args.corpus, args.gold_cache)))
