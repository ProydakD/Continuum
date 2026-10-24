"""Only synthetic leak detectors; no real secret contents are read or printed."""
import json
import os
from pathlib import Path
import subprocess
import sys

prior = subprocess.run([sys.executable, "/runtime/probe.py"], capture_output=True, text=True, timeout=20)
observed = json.loads(prior.stdout)
checks = dict(observed["checks"])
checks["api_key_absent"] = "API_KEY" not in os.environ
checks["e009_gold_absent"] = not Path("/evaluator/gold.txt").exists()
checks["e009_catalog_absent"] = not Path("/private/catalog.json").exists()
try:
    with open("/e009-runtime/worker.py", "ab") as handle:
        handle.write(b"")
    checks["e009_runtime_readonly"] = False
except OSError:
    checks["e009_runtime_readonly"] = True
print(json.dumps({"pass": all(checks.values()), "checks": checks,
                  "python": sys.version, "prior_exit_status": prior.returncode}))
sys.exit(0 if all(checks.values()) else 2)
