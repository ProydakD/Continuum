"""Container entrypoint: multiplex stdio MCP without giving workers host networking."""
import argparse
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

MAX_LINE = 262144
output_lock = threading.Lock()
connections = {}


def emit(value):
    with output_lock:
        print(json.dumps(value), flush=True)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        identity = uuid.uuid4().hex
        connections[identity] = self.request
        try:
            while line := self.rfile.readline(MAX_LINE + 1):
                if len(line) > MAX_LINE:
                    return
                emit({"channel": "mcp", "connection": identity, "message": json.loads(line)})
        finally:
            connections.pop(identity, None)


def receive():
    for line in sys.stdin:
        message = json.loads(line)
        sock = connections.get(message["connection"])
        if sock:
            sock.sendall((json.dumps(message["message"]) + "\n").encode())


parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["fixture", "codex"], required=True)
parser.add_argument("--stage", choices=list("ABC"), required=True)
parser.add_argument("--model", default="")
args = parser.parse_args()
server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
server.daemon_threads = True
threading.Thread(target=server.serve_forever, daemon=True).start()
threading.Thread(target=receive, daemon=True).start()
env = dict(os.environ, CONTINUUM_BRIDGE_PORT=str(server.server_address[1]))
provider = None
try:
    if args.mode == "fixture":
        argv = [sys.executable, "/runtime/fixture.py", args.stage]
    else:
        # No credentials or external provider: an operator-built pinned image must
        # already contain the requested model. Never pull a model automatically.
        provider = subprocess.Popen(["ollama", "serve"], env=env, stdout=sys.stderr, stderr=sys.stderr)
        available = []
        for attempt in range(50):
            if provider.poll() is not None:
                raise RuntimeError("local provider exited")
            try:
                with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1) as response:
                    available = [m["name"] for m in json.load(response)["models"]]
                break
            except OSError:
                time.sleep(0.1)
        if args.model not in available:
            raise RuntimeError("requested model is not preloaded; no automatic downloads")
        argv = ["codex", "--strict-config", "exec", "--oss", "--local-provider", "ollama",
                "--model", args.model, "--ephemeral", "--ignore-rules", "--skip-git-repo-check",
                "--sandbox", "workspace-write", "--json", "-"]
    prompt = Path("/workspace/PROMPT.txt").read_text() if args.mode == "codex" else ""
    child = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=sys.stderr, text=True, encoding="utf-8")
    child.stdin.write(prompt)
    child.stdin.close()
    for line in child.stdout:
        if len(line) > MAX_LINE:
            child.kill()
            raise ValueError("worker output line too large")
        emit({"channel": "worker", "line": line.rstrip("\n")})
    sys.exit(child.wait())
finally:
    if provider:
        provider.terminate()
    server.shutdown()
