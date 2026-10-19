from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
SKILLS = PROJECT / "engineering" / "codex-home" / "skills"
MAX_LINE = 262144


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def source_hashes(directory=PROJECT):
    directory = Path(directory).resolve(strict=True)
    hashes = {}
    for path in sorted(directory.rglob("*")):
        if any(part in {"__pycache__", ".git"} for part in path.relative_to(directory).parts):
            continue
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)() or not path.resolve().is_relative_to(directory):
            raise ValueError("linked paths are not allowed in an experimental snapshot")
        if path.is_file():
            hashes[path.relative_to(directory).as_posix()] = digest(path)
    return hashes


def clean_env(**extra):
    env = {k: os.environ[k] for k in ("SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP")
           if k in os.environ}
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1",
               HOME=str(ROOT / "runtime" / "broker-home"), USERPROFILE=str(ROOT / "runtime" / "broker-home"))
    env.update({k: str(v) for k, v in extra.items()})
    return env


def server_env(db, actor, run_id, model="deterministic-fixture", role="worker"):
    return clean_env(CONTINUUM_DB=Path(db).resolve(), CONTINUUM_ACTOR=actor,
                     CONTINUUM_WORKSPACE="lab", CONTINUUM_RUN_ID=run_id,
                     CONTINUUM_MODEL=model, CONTINUUM_ROLE=role)


def command(argv, *, cwd=PROJECT, timeout=60, env=None, input=None):
    result = subprocess.run(argv, cwd=cwd, env=env, input=input, text=True,
                            encoding="utf-8", errors="replace", capture_output=True, timeout=timeout)
    return {"command": list(map(str, argv)), "cwd": str(cwd), "stdout": result.stdout,
            "stderr": result.stderr, "exit_status": result.returncode}


def runtime_identity():
    return {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
            "mcp": importlib.metadata.version("mcp"), "model_actual": "not_run"}
