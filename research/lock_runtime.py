"""Copy only declared installed Python dependencies into a local offline venv.

This snapshots installed bytes, not provenance of a PyPI wheel. No network/install,
global settings, credentials, sessions or user repositories are copied.
"""
import argparse
from importlib.metadata import distribution
import json
from pathlib import Path
import shutil
import sys
import sysconfig
import venv
from packaging.requirements import Requirement
from .common import PROJECT, ROOT, digest, write_json


def freeze(complete_existing=False):
    target = ROOT / "runtime" / "venv"
    if target.exists() and not complete_existing:
        raise FileExistsError("Runtime snapshot already exists; use it, do not overwrite")
    requirements, copied = {}, {}
    processed = set()
    pending = ["mcp", "setuptools", "packaging"]
    while pending:
        requested = Requirement(pending.pop())
        name = requested.name.lower().replace("_", "-")
        key = (name, frozenset(requested.extras))
        if key in processed:
            continue
        processed.add(key)
        dist = distribution(name)
        requirements[name] = dist.version
        for raw in dist.requires or []:
            dep = Requirement(raw)
            if not dep.marker or any(dep.marker.evaluate({"extra": extra}) for extra in ["", *requested.extras]):
                pending.append(str(dep))
    if not target.exists():
        venv.EnvBuilder(with_pip=False).create(target)
    dest_site = target / ("Lib/site-packages" if sys.platform == "win32" else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")
    if complete_existing:
        inventory = json.loads((ROOT / "runtime" / "installed-files.json").read_text())
        for rel, sha in inventory.items():
            if digest(dest_site / rel) != sha:
                raise ValueError("existing runtime changed; refusing repair")
    for name in requirements:
        dist = distribution(name)
        base = Path(dist.locate_file("")).resolve()
        for relative in dist.files or []:
            source = Path(dist.locate_file(relative)).resolve()
            if not source.is_relative_to(base) or not source.is_file() or "__pycache__" in source.parts:
                continue
            rel = source.relative_to(base)
            dest = dest_site / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and digest(source) != digest(dest):
                raise ValueError("refusing to overwrite different runtime bytes")
            if not dest.exists():
                shutil.copyfile(source, dest)
            copied[rel.as_posix()] = digest(dest)
    write_json(ROOT / "runtime" / "installed-files.json", copied)
    write_json(PROJECT / "runtime-lock.json", {"python": sys.version, "base_executable": sys.executable,
        "dependencies": requirements, "installed_files_sha256": digest(ROOT / "runtime" / "installed-files.json"),
        "reconstruction": "offline copy of installed distribution files; wheel provenance not independently verified"})
    (PROJECT / "requirements.lock").write_text("\n".join(f"{k}=={v}" for k,v in sorted(requirements.items()))+"\n", encoding="utf-8")
    print(json.dumps({"runtime": str(target), "distributions": len(requirements), "files": len(copied)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--complete-existing", action="store_true")
    freeze(parser.parse_args().complete_existing)
