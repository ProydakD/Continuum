"""Docker is an OS boundary; CODEX_HOME is only state separation."""
import json
import re
import uuid
from pathlib import Path
from .common import PROJECT, command, write_json


def image_id(image):
    result = command(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
    value = result["stdout"].strip()
    if result["exit_status"] or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise RuntimeError("Local pinned image unavailable; no automatic pulls: " + result["stderr"])
    return value


def mount(source, target, readonly=False):
    source = Path(source).resolve(strict=True)
    if "," in str(source) or source.is_symlink():
        raise ValueError("unsafe mount source")
    return ["--mount", f"type=bind,src={source},dst={target}" + (",readonly" if readonly else "")]


def container_command(image, name, worker, argv, *, live=False):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("immutable image ID required")
    worker = Path(worker).resolve()
    args = ["docker", "run", "--rm", "--pull", "never", "-i", "--name", name,
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "--pids-limit", "128", "--memory", "8g" if live else "256m", "--cpus", "2" if live else "1",
            "--tmpfs", "/tmp:rw,nosuid,size=128m", "--tmpfs", "/home/research:rw,nosuid,size=64m",
            "--workdir", "/workspace", "--env", "HOME=/home/research", "--env", "CODEX_HOME=/codex-home",
            "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONUNBUFFERED=1",
            "--env", "PYTHONNOUSERSITE=1", "--env", "OLLAMA_HOST=127.0.0.1:11434",
            "--env", "OLLAMA_MODELS=/models", "--entrypoint", "python"]
    args += mount(worker / "repo", "/workspace")
    args += mount(worker / "codex-home", "/codex-home")
    args += mount(worker / "codex-home" / "config.toml", "/codex-home/config.toml", True)
    args += mount(worker / "repo" / "AGENTS.md", "/workspace/AGENTS.md", True)
    args += mount(worker / "skills", "/workspace/.agents/skills", True)
    args += mount(PROJECT / "research" / "worker_runtime", "/runtime", True)
    return args + [image] + argv


def isolation_probe(image, worker, output):
    name = "continuum-probe-" + uuid.uuid4().hex[:12]
    argv = container_command(image, name, worker, ["/runtime/probe.py"])
    try:
        result = command(argv, timeout=30)
    except Exception:
        command(["docker", "rm", "-f", name])
        raise
    try:
        observations = json.loads(result["stdout"])
    except ValueError:
        observations = {}
    result["observations"] = observations
    result["isolation_pass"] = result["exit_status"] == 0 and observations.get("pass") is True
    write_json(output, result)
    return result
