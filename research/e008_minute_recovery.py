"""A004 recovery primitive: ten spaced GETs, never a repeated worker/Responses.

Not an execution admission. The prospective A004 controller must validate the
authorized source, cutover and model before invoking this primitive.
"""
from pathlib import Path
import re
import time

from .e008_live import event_offset, last_http_status, load_network_result, save_network_result, wait_until
from .e008_locks import read, write_once
from .e008_resources import SeriesStopped, provider_failure_action

ATTEMPTS = 10
DELAY_SECONDS = 60
CUTOVER = 2139


def recovery_root(study, identity):
    if identity != "E008-A004" and not (
            re.fullmatch(r"j[0-9]{5}", identity) and CUTOVER < int(identity[1:]) <= 3426):
        raise PermissionError("minute recovery cannot extend a retained pre-A004 episode")
    return Path(study) / "recovery" / identity


def check_files(base):
    allowed = {f"{n}-{suffix}.json" for n in range(1, ATTEMPTS + 1)
               for suffix in ("started", "sending", "result", "result.evidence")}
    allowed.update(("complete.json", "exhausted.json"))
    if base.exists() and any(p.name not in allowed or not p.is_file() for p in base.iterdir()):
        raise PermissionError("unexpected minute-recovery attempt or file")
    if (base / "complete.json").exists() and not (base / "1-result.json").exists():
        raise PermissionError("completion without recorded attempts")
    if (base / "exhausted.json").exists() and any(
            not (base / f"{n}-result.json").exists() for n in range(1, ATTEMPTS + 1)):
        raise PermissionError("exhaustion without ten recorded attempts")
    for number in range(1, ATTEMPTS + 1):
        existing = list(base.glob(f"{number}-*.json"))
        if existing and (not (base / f"{number}-started.json").exists() or (
                number > 1 and not (base / f"{number - 1}-result.json").exists())):
            raise PermissionError("noncontiguous minute-recovery attempts")


def exhaustion(results, model):
    return {"attempts": ATTEMPTS, "model": model, "ask_user": True,
            "http502_responses": sum(r.get("http_status") == 502 for r in results),
            "catalogue_model_absent": sum(not r["available"] and "failure_type" not in r for r in results)}


def recover(study, identity, provider):
    """Only pending successor admission; old outcomes and old episodes stay intact."""
    study = Path(study)
    if provider.ledger.study != study.resolve() or provider.log != study / "provider.jsonl":
        raise PermissionError("minute recovery must retain the original clock, guard and journal")
    base = recovery_root(study, identity)
    check_files(base)
    results = []
    for number in range(1, ATTEMPTS + 1):
        started, result_path = base / f"{number}-started.json", base / f"{number}-result.json"
        sending = base / f"{number}-sending.json"
        if result_path.exists():
            attempt = read(started)
            if attempt["model"] != provider.model or attempt["delay"] != DELAY_SECONDS:
                raise PermissionError("cached minute-recovery assignment changed")
            if not sending.exists():
                raise PermissionError("recovery result without a sending record")
            result = load_network_result(result_path, provider)
        else:
            if started.exists():
                attempt = read(started)
                if sending.exists():
                    raise SeriesStopped("orphan minute-recovery HTTP; never replay")
            else:
                provider.ledger.check_context()
                attempt = write_once(started, {"at": time.time(), "delay": DELAY_SECONDS,
                                               "model": provider.model})
            if attempt["model"] != provider.model or attempt["delay"] != DELAY_SECONDS:
                raise PermissionError("minute-recovery assignment changed")
            wait_until(attempt["at"] + DELAY_SECONDS, provider.ledger)
            provider.ledger.check_context()
            offset = event_offset(provider)
            write_once(sending, {"at": time.time()})
            try:
                available = provider.model in provider.models()
                result = {"available": available, "action": "continue" if available else "recover_next_position"}
            except Exception as exc:
                status = last_http_status(provider, offset)
                result = {"available": False, "failure_type": type(exc).__name__, "http_status": status,
                          "action": provider_failure_action(type(exc).__name__, status)}
            save_network_result(result_path, provider, offset, result)
        results.append(result)
        if result["available"]:
            if (base / "exhausted.json").exists():
                raise PermissionError("exhausted minute recovery cannot become successful")
            if any(any(base.glob(f"{later}-*.json")) for later in range(number + 1, ATTEMPTS + 1)):
                raise PermissionError("unexpected attempts after successful recovery")
            return write_once(base / "complete.json", {"pass": True, "attempts": number, "model": provider.model})
        if result["action"] == "stop":
            raise SeriesStopped("non-transient failure in minute recovery; ask user")
    summary = exhaustion(results, provider.model)
    write_once(base / "exhausted.json", summary)
    raise SeriesStopped("minute recovery exhausted after 10 attempts; ask user: "
                        f"HTTP502={summary['http502_responses']}, model_absent={summary['catalogue_model_absent']}")
