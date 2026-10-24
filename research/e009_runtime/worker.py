"""Deterministic infrastructure fixture; no model or causal oracle."""
import json
import os
from pathlib import Path
import socket
import sys
import uuid


def exchange(name, arguments):
    print(json.dumps({"channel": "tool", "name": name, "arguments": arguments}), flush=True)
    raw = sys.stdin.buffer.readline(262145)
    if not raw or len(raw) > 262144:
        raise RuntimeError("bad broker frame")
    return json.loads(raw)


def main():
    config = json.loads(Path("/workspace/PROMPT.txt").read_text())
    stage, condition = config["stage"], config["condition"]
    print(json.dumps({"channel": "hello", "hostname": socket.gethostname(), "pid": os.getpid()}), flush=True)
    for name, arguments in [
            ("get_object", {"sha256": "0" * 64}),
            ("read_memory", {"sha256": "0" * 64}),
            ("shell", {"command": config["untrusted_text"]})]:
        assert exchange(name, arguments) == {"error": "capability_rejected"}
    previous = exchange("read_memory", {})["result"]
    assert exchange("read_memory", {}) == {"error": "capability_rejected"}
    memory = previous["memory"]
    events = ([] if memory is None else memory["payload"] if memory["format"] == "S"
              else json.loads(memory["payload"]))
    inherited = [item["stage"] for item in events]
    if stage == "E":
        assert exchange("publish", {"published_memory": {"format": "F", "payload": "forbidden"},
                                    "measurement": {}}) == {"error": "capability_rejected"}
    else:
        events.append({"stage": stage, "literal_data": config["untrusted_text"]})
        representation = "S" if condition.startswith("S") else "F"
        published = {"format": representation,
                     "payload": events if representation == "S" else json.dumps(events)}
        result = exchange("publish", {"published_memory": published,
            "measurement": {"private_canary": uuid.uuid4().hex, "not_model_claims": True}})
        assert result["result"]["saved"] is True
    assert not Path("/workspace/INJECTION_EXECUTED").exists()
    print(json.dumps({"channel": "finished", "stage": stage, "inherited": inherited,
                      "model_calls": 0, "injection_executed": False}), flush=True)


if __name__ == "__main__":
    main()
