"""Version/config/model-inventory check only; never performs inference or pulls."""
import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--model", default="")
args = parser.parse_args()
report = {"ready": False, "inference_requests": 0, "commands": []}
missing = [name for name in ["codex", "ollama"] if not shutil.which(name)]
provider = None
try:
    if missing:
        raise RuntimeError("missing runtime binaries: " + ", ".join(missing))
    for argv in [["codex", "--version"], ["codex", "mcp", "list", "--json"], ["ollama", "--version"]]:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        report["commands"].append({"argv": argv, "stdout": result.stdout, "stderr": result.stderr, "exit_status": result.returncode})
        if result.returncode:
            raise RuntimeError("runtime command failed")
    if report["commands"][0]["stdout"].strip() != "codex-cli 0.163.0":
        raise RuntimeError("Codex version differs from pinned CLI 0.163.0")
    servers = json.loads(report["commands"][1]["stdout"])
    if not isinstance(servers, list) or [server["name"] for server in servers] != ["continuum"]:
        raise RuntimeError("unexpected MCP configuration")
    provider = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for attempt in range(50):
        if provider.poll() is not None:
            raise RuntimeError("local provider exited")
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1) as response:
                report["models"] = json.load(response)["models"]
            break
        except OSError:
            time.sleep(0.1)
    if args.model not in [model["name"] for model in report.get("models", [])]:
        raise RuntimeError("requested local model is not preloaded")
    report["ready"] = True
except Exception as exc:
    report["blocker"] = str(exc)
finally:
    if provider:
        provider.terminate()
        provider.wait(timeout=5)
print(json.dumps(report))
raise SystemExit(0 if report["ready"] else 2)
