"""Offline ordered-batch/retention integration, with real isolated workers and no model calls."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
from unittest.mock import patch

from .common import digest
from .e009_broker import frame
from .e009_controller_gate import ScriptedProvider
from .e009_episode import make_episode
from .e009_episode_eval import reference_chain
from .e009_execute import run_chain
from .e009_oracle import Oracle
from .e009_provider import HTTPSProvider
from .e009_raw import write_once
from .e009_replay import replay
from .e009_scm import models


class BatchFixture(HTTPSProvider):
    fixture = True

    def __init__(self, directory, trace, mode):
        self.script = ScriptedProvider(trace, "admission" if mode == "admission" else "positive")
        for stage, script in self.script.scripts.items():
            combined = deepcopy(script[0])
            combined["output"] = [item for response in script[:-1] for item in response["output"]]
            if mode == "duplicate":
                combined["output"].append(deepcopy(next(i for i in combined["output"] if i["type"] == "function_call")))
            self.script.scripts[stage] = [combined, script[-1]]
        super().__init__("https://fixture.invalid/v1", self.script.model, directory, authorize=True)

    def _attempt(self, body, timeout, observation):
        request = json.loads(body)
        stage = json.loads(request["input"][0]["content"])["stage"]
        response = self.script.respond(stage, request, timeout=timeout)
        raw = frame(response)
        observation.update(request_may_have_been_sent=False, http_status=200,
                           response_body_bytes_observed=len(raw), response_complete=True)
        return 200, None, raw


def run(directory, image):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    episode = make_episode(43, "e009-batch-development-43")
    oracle = Oracle(models())
    results = []
    for mode, condition in [("positive", "F1"), ("admission", "F0"), ("duplicate", "F1"), ("budget", "F1")]:
        trace = reference_chain(episode, oracle, "F")
        with patch.dict("os.environ", {"API_KEY": "SYNTHETIC-batch-gate-not-a-credential"}):
            provider = BatchFixture(directory / (mode + "-transport"), trace, mode)
        limits = {"stage_seconds": 120, "request_seconds": 45, "responses": 24,
                  "output_tokens": 16000, "tool_calls": 2 if mode == "budget" else 24}
        observed = run_chain(directory / mode, episode, condition, "controlled", provider, image, limits=limits)
        result = replay(observed["directory"], observed["manifest_sha256"], oracle)
        expected = 1 if mode in {"positive", "admission"} else 0
        assert result["score"]["bri"] == expected, result
        assert observed["statuses"] == (["completed"] * 5 if expected else
                                        ["tool_limit" if mode == "budget" else "failed"] + ["upstream_missing"] * 4)
        if mode == "duplicate":
            attempts = json.loads((Path(observed["directory"]) / "A/provider-attempts.json").read_text())
            assert attempts[0]["validation_error"] == "duplicate function call identity"
            assert (Path(observed["directory"]) / "A/provider-bodies/000001.json").exists()
        if expected:
            assert [r["response_calls"] for r in result["resources"]] == [2] * 5
        write_once(directory / (mode + "-replay.json"), result)
        summary = {**observed, "bri": result["score"]["bri"], "raw_files": result["raw_files_verified"],
                   "tool_calls": [r["tool_calls"] for r in result["resources"]], "raw_unchanged": result["raw_unchanged"]}
        results.append(summary)
        print(json.dumps(summary), flush=True)
    # Rebinding a copied manifest cannot conceal altered retained response bytes.
    tampered = directory / "tampered-body"
    shutil.copytree(directory / "positive", tampered)
    body = tampered / "A/provider-bodies/000001.json"
    body.write_bytes(body.read_bytes() + b" ")
    manifest = {p.relative_to(tampered).as_posix(): digest(p) for p in sorted(tampered.rglob("*"))
                if p.is_file() and p.name != "MANIFEST.json"}
    (tampered / "MANIFEST.json").write_bytes(frame(manifest))
    try:
        replay(tampered, digest(tampered / "MANIFEST.json"), oracle)
    except ValueError as error:
        assert str(error) == "retained response bytes differ from transport"
        tamper = {"rejected": True, "reason": str(error), "manifest_rebound": True}
    else:
        raise AssertionError("retained body mutation accepted")
    summary = {"pass": True, "cases": results, "tamper": tamper, "model_calls": 0,
               "scope": "synthetic provider; real Docker/MCP worker and independent raw replay"}
    write_once(directory / "SUMMARY.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    run(args.output, args.image)
