"""Fresh Responses history inside network-none Docker; provider access is host-only."""
import json
from pathlib import Path
import socket
import sys


def send(value):
    sys.stdout.buffer.write((json.dumps(value, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":"), allow_nan=False) + "\n").encode())
    sys.stdout.buffer.flush()


def receive():
    raw = sys.stdin.buffer.readline(262145)
    if not raw or len(raw) > 262144:
        raise RuntimeError("missing or oversized controller frame")
    return raw, json.loads(raw)


def main():
    config = json.loads(Path("/workspace/PROMPT.txt").read_text())
    history = config["history"]
    send({"channel": "hello", "hostname": socket.gethostname()})
    while True:
        send({"channel": "responses", "history": history})
        _, reply = receive()
        response = reply["result"]
        output = response["output"]
        history.extend(output)
        calls = [i for i in output if i.get("type") == "function_call"]
        if calls:
            for call in calls:
                send({"channel": "tool", "name": call["name"], "call_id": call["call_id"],
                      "arguments": json.loads(call["arguments"])})
                raw, _ = receive()
                history.append({"type": "function_call_output", "call_id": call["call_id"],
                                "output": raw.decode("utf-8")})
            continue
        messages = [i for i in output if i.get("type") == "message" and i.get("role") == "assistant"]
        text = "".join(p.get("text", "") for p in messages[-1].get("content", [])
                       if p.get("type") == "output_text")
        send({"channel": "final", "text": text})
        return


if __name__ == "__main__":
    main()
