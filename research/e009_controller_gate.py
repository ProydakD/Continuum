"""Offline Responses provider fixture and isolated controller/replay acceptance cases."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil

from .common import digest
from .e009_episode import make_episode
from .e009_episode_eval import reference_chain
from .e009_execute import run_chain
from .e009_oracle import Oracle
from .e009_raw import write_once
from .e009_replay import replay
from .e009_revision import canonical
from .e009_scm import models


class ScriptedProvider:
    """Private positive/negative test double, NOT a model or a causal learner."""
    model = "deterministic-responses-fixture"
    fixture = True

    def __init__(self, trace, mode="positive"):
        self.trace = deepcopy(trace)
        self.mode = mode
        self.steps = {}
        self.scripts = {}
        if mode == "wrong-B":
            self.trace[1]["claims"][0]["status"] = "supported"
            memory = self.trace[1]["published_memory"]
            memory["payload"] = (deepcopy(self.trace[1]["claims"]) if memory["format"] == "S"
                                 else canonical(self.trace[1]["claims"]).decode())
        for record in self.trace:
            stage = record["stage"]
            calls = [("read_memory", {})]
            if mode == "admission" and stage == "A":
                calls += [("get_object", {"sha256": "0" * 64}),
                          ("publish", {"published_memory": {"format": "F", "payload": "x" * 8000},
                                       "measurement": {"claims": []}})]
            if stage != "E":
                calls += [("hash_claims", {"claims": [{"id": "public-calculation", "version": 1}]}),
                          ("publish", {"published_memory": record["published_memory"],
                                       "measurement": {"claims": record["claims"]}})]
            script = []
            for index, (name, arguments) in enumerate(calls):
                script.append({"id": f"fixture-{stage}-{index}", "model": self.model, "status": "completed",
                    "output": [{"type": "reasoning", "id": f"r-{stage}-{index}", "summary": [],
                                "encrypted_content": "synthetic-not-real-reasoning"},
                               {"type": "function_call", "call_id": f"{stage}-{index}", "name": name,
                                "arguments": canonical(arguments).decode()}],
                    "usage": {"input_tokens": 0, "output_tokens": 0}})
            final = ({"answer": record["answer"], "basis": record["basis"]}
                     if stage == "E" else {"status": "published"})
            script.append({"id": f"fixture-{stage}-final", "model": self.model, "status": "completed",
                "output": [{"type": "message", "role": "assistant", "phase": "final_answer",
                            "content": [{"type": "output_text", "text": canonical(final).decode()}]}],
                "usage": {"input_tokens": 0, "output_tokens": 0}})
            self.scripts[stage] = script

    def respond(self, context_id, request, *, timeout):
        del timeout
        stage = json.loads(request["input"][0]["content"])["stage"]
        if self.mode == "provider-failure-C" and stage == "C":
            raise TimeoutError("synthetic provider failure")
        index = self.steps.get(context_id, 0)
        self.steps[context_id] = index + 1
        response = deepcopy(self.scripts[stage][index])
        if self.mode == "incomplete-C" and stage == "C":
            response["status"] = "incomplete"
        return response


def tamper_check(source, directory, oracle: Oracle):
    shutil.copytree(source, directory)
    terminal = json.loads((directory / "E/terminal.json").read_text())
    terminal["final"]["answer"] = 999
    (directory / "E/terminal.json").write_bytes(canonical(terminal) + b"\n")
    all_records = json.loads((directory / "terminal.json").read_text())
    all_records[-1] = terminal
    (directory / "terminal.json").write_bytes(canonical(all_records) + b"\n")
    manifest = {p.relative_to(directory).as_posix(): digest(p) for p in sorted(directory.rglob("*"))
                if p.is_file() and p.name != "MANIFEST.json"}
    (directory / "MANIFEST.json").write_bytes(canonical(manifest) + b"\n")
    try:
        replay(directory, digest(directory / "MANIFEST.json"), oracle)
    except ValueError as error:
        return {"rejected": True, "reason": str(error), "manifest_rebound": True}
    raise AssertionError("forged terminal answer accepted despite contradictory provider bytes")


def run(directory, image, cases):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    episode = make_episode(43, "e009-controller-development-43")
    oracle = Oracle(models())
    results = []
    for condition, mode in cases:
        representation = "S" if condition.startswith("S") else "F"
        trace = reference_chain(episode, oracle, representation)
        provider = ScriptedProvider(trace, mode)
        name = condition.lower() + "-" + mode.lower()
        spec = {"condition": condition, "mode": mode, "script": provider.scripts, "fixture_only": True}
        write_once(directory / (name + "-script.json"), spec)
        observed = run_chain(directory / name, episode, condition, "controlled", provider, image,
                             crash_stage="C" if mode == "crash-C" else None,
                             stop_before="B" if mode == "stop-B" else None)
        result = replay(observed["directory"], observed["manifest_sha256"], oracle)
        expected = None if condition == "C0" else 0 if mode in {
            "wrong-B", "crash-C", "stop-B", "provider-failure-C", "incomplete-C"} else 1
        write_once(directory / (name + "-replay.json"), result)
        assert result["score"]["bri"] == expected, (name, result["score"])
        if mode in {"positive", "admission", "wrong-B"}:
            assert observed["statuses"] == ["completed"] * 5, observed
        elif mode == "crash-C":
            assert observed["statuses"] == ["completed", "completed", "injected_crash_after_commit", "completed", "completed"]
        elif mode == "stop-B":
            assert observed["statuses"] == ["completed"] + ["stopped"] * 4
        else:
            assert observed["statuses"] == ["completed", "completed", "failed", "upstream_missing", "upstream_missing"]
        if condition == "FULL-JOURNAL":
            assert max(r["read_envelope_bytes"] for r in result["resources"]) > 8192
        summary = {**observed, "expected_bri": expected, "observed_bri": result["score"]["bri"],
                   "raw_files_verified": result["raw_files_verified"]}
        results.append(summary)
        write_once(directory / (name + "-RESULT.json"), summary)
        print(json.dumps(summary), flush=True)
    positive = next((r for r in results if r["expected_bri"] == 1), None)
    tamper = tamper_check(Path(positive["directory"]), directory / "tampered-terminal", oracle) if positive else None
    summary = {"pass": True, "cases": results, "tamper": tamper, "model_api_calls": 0,
               "scope": "Deterministic Responses integration; no empirical model conclusions"}
    write_once(directory / "SUMMARY.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    cases = [("S1", "positive")] if args.smoke else [
        *[(c, "positive") for c in ("F0", "F1", "S0", "S1", "C0", "FULL-JOURNAL")],
        ("F1", "admission"), ("S1", "wrong-B"), ("S1", "crash-C"),
        ("S1", "stop-B"), ("S1", "provider-failure-C"), ("S1", "incomplete-C")]
    run(args.output, args.image, cases)
