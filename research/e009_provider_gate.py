"""Real controller + HTTPS adapter with a synthetic in-process HTTP transport."""
import argparse
import json
import os
from pathlib import Path
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

SYNTHETIC_KEY = "SYNTHETIC-gate-key-not-a-real-credential"


class AdapterFixture(HTTPSProvider):
    fixture = True

    def __init__(self, directory, stop, trace, mode):
        self.script = ScriptedProvider(trace)
        self.mode = mode
        self.calls = 0
        super().__init__("https://fixture.invalid/v1", self.script.model, directory,
                         authorize=True, stop_path=stop)

    def _attempt(self, body, timeout, observation):
        self.calls += 1
        observation["request_may_have_been_sent"] = True
        if self.calls <= 2:
            status = 503 if self.calls == 1 else 429
            raw = b"<html>synthetic unavailable</html>" if status == 503 else b"{}"
            observation.update(http_status=status, response_complete=True, response_body_bytes_observed=len(raw))
            if self.mode == "stop":
                self.stop_path.write_text("synthetic stop during provider request\n", encoding="utf-8")
            return status, "0.1", raw
        request = json.loads(body)
        stage = json.loads(request["input"][0]["content"])["stage"]
        response = self.script.respond(stage, request, timeout=timeout)
        raw = frame(response)
        observation.update(http_status=200, response_complete=True, response_body_bytes_observed=len(raw))
        return 200, None, raw


def run(directory, image):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    episode = make_episode(43, "e009-provider-development-43")
    oracle = Oracle(models())
    results = []
    with patch.dict(os.environ, {"API_KEY": SYNTHETIC_KEY}):
        for mode in ("retry", "stop"):
            destination = directory / mode
            provider = AdapterFixture(directory / (mode + "-ledger"), destination / "STOP",
                                      reference_chain(episode, oracle, "F"), mode)
            observed = run_chain(destination, episode, "F1", "controlled", provider, image)
            result = replay(destination, observed["manifest_sha256"], oracle)
            records = provider.ledger.records()
            expected = 1 if mode == "retry" else 0
            assert result["score"]["bri"] == expected
            if mode == "retry":
                assert observed["statuses"] == ["completed"] * 5 and len(records) == 20
                assert records[0]["reason"] == records[1]["reason"] == "http_status"
                assert records[1]["started"] - records[0]["finished"] >= records[0]["retry_delay"]
            else:
                assert observed["statuses"] == ["stopped"] * 5 and len(records) == 1
                assert records[0]["reason"] == "operator_stop"
            for path in directory.rglob("*"):
                if path.is_file():
                    assert SYNTHETIC_KEY.encode() not in path.read_bytes(), path
            write_once(directory / (mode + "-replay.json"), result)
            write_once(directory / (mode + "-attempts.json"), records)
            record = {**observed, "bri": result["score"]["bri"], "attempts": len(records),
                      "ledger_sha256": digest(provider.ledger.path),
                      "raw_files_verified": result["raw_files_verified"], "real_network_calls": 0}
            results.append(record)
            print(json.dumps(record), flush=True)
    write_once(directory / "SUMMARY.json", {"pass": True, "cases": results,
        "model_api_calls": 0, "scope": "Actual adapter retry waits and Docker/MCP; simulated HTTP peer only"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    run(args.output, args.image)
