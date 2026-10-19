"""Synthetic boundary checks; never reads real private file contents."""
import json
import os
from pathlib import Path
import shutil
import socket
import sys

checks = {}
checks["non_root"] = os.getuid() == 65534
status = Path("/proc/self/status").read_text()
checks["capabilities_dropped"] = "CapEff:\t0000000000000000" in status
checks["no_new_privileges"] = "NoNewPrivs:\t1" in status
checks["network_namespace"] = set(os.listdir("/sys/class/net")) == {"lo"}
denied_paths = ["/host-private", "/supervisor", "/evaluator", "/state", "/var/run/docker.sock",
                "/root/.codex", "/root/.mempalace", "/mnt/c/Users", "/run/desktop/mnt/host"]
def inaccessible(path):
    try:
        return not Path(path).exists()
    except PermissionError:
        return True


checks["forbidden_paths_inaccessible"] = all(inaccessible(p) for p in denied_paths)
checks["clean_environment"] = not any(k in os.environ for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CONTINUUM_DB"])
checks["fresh_home"] = not any((Path("/codex-home") / p).exists() for p in
                             ["sessions", "history.jsonl", "memories", "hooks", "rules", "auth.json"])
for label, path in [("root_readonly", "/forbidden"), ("instructions_readonly", "/workspace/AGENTS.md"),
                    ("config_readonly", "/codex-home/config.toml"), ("runtime_readonly", "/runtime/proxy.py")]:
    try:
        with open(path, "ab") as file:
            file.write(b"")
        checks[label] = False
    except OSError:
        checks[label] = True
for label, address in [("host_memory_denied", ("host.docker.internal", 8765)),
                       ("host_ide_denied", ("host.docker.internal", 64542)),
                       ("external_network_denied", ("1.1.1.1", 443)),
                       ("old_memory_loopback_denied", ("127.0.0.1", 8765))]:
    try:
        with socket.create_connection(address, timeout=1):
            checks[label] = False
    except OSError:
        checks[label] = True
print(json.dumps({"pass": all(checks.values()), "checks": checks, "python": sys.version,
                  "codex_present": bool(shutil.which("codex")), "ollama_present": bool(shutil.which("ollama"))}))
sys.exit(0 if all(checks.values()) else 2)
