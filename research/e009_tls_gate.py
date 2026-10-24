"""Loopback-only TLS integration; synthetic credentials/certificate, no model gateway."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import threading
import time
from unittest.mock import patch

from .common import command, digest
from .e009_broker import frame
from .e009_provider import HTTPSProvider, ProviderFailure
from .e009_raw import write_once

SYNTHETIC_KEY = "SYNTHETIC-loopback-key-not-a-real-credential"


class LoopbackProvider(HTTPSProvider):
    fixture = True


def run(directory, openssl):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    certificate, private_key = directory / "synthetic-cert.pem", directory / "synthetic-key.pem"
    generated = command([openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-noenc",
        "-keyout", str(private_key), "-out", str(certificate), "-days", "2", "-subj", "/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], timeout=30)
    write_once(directory / "certificate-command.json", generated)
    if generated["exit_status"]:
        raise RuntimeError("synthetic certificate generation failed")
    state = {"mode": None, "posts": []}
    received, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            mode = state["mode"]
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            state["posts"].append({"body_sha256": hashlib.sha256(raw).hexdigest(),
                "body_bytes": len(raw), "at": time.time(), "path": self.path,
                "auth_correct": self.headers.get("Authorization") == "Bearer " + SYNTHETIC_KEY})
            if mode not in {"stop_body", "deadline_body"}:
                received.set()
            number = len(state["posts"])
            if mode == "stop":
                release.wait(5)
            status = 503 if mode == "retry" and number == 1 else (
                429 if mode == "retry" and number == 2 else 302 if mode == "redirect" else 200)
            payload = b"<html>synthetic outage</html>" if status == 503 else frame({
                "model": "fixture-model", "status": "completed",
                "output": [{"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": "{}"}]}],
                "usage": {"input_tokens": 22, "output_tokens": 8}})
            try:
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                if status == 429:
                    self.send_header("Retry-After", "1")
                if status == 302:
                    self.send_header("Location", "https://must-not-contact.invalid/v1/responses")
                self.end_headers()
                if mode in {"stop_body", "deadline_body"}:
                    self.wfile.write(payload[:1])
                    self.wfile.flush()
                    received.set()
                    release.wait(5)
                    payload = payload[1:]
                self.wfile.write(payload)
            except OSError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, private_key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_context = ssl.create_default_context

    def trusted_context():
        context = original_context()
        context.load_verify_locations(cafile=str(certificate))
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        return context

    cases = []
    request = {"model": "fixture-model", "store": False, "input": [{"role": "user", "content": "synthetic only"}]}
    try:
        with patch.dict(os.environ, {"API_KEY": SYNTHETIC_KEY}):
            for mode in ("untrusted", "retry", "redirect", "stop", "stop_body", "deadline_body"):
                state["mode"], state["posts"] = mode, []
                received.clear(); release.clear()
                provider = LoopbackProvider(f"https://127.0.0.1:{port}/v1", "fixture-model",
                                            directory / mode, authorize=True)
                stopper = None
                if mode in {"stop", "stop_body"}:
                    def stop_after_receive():
                        if received.wait(5):
                            if mode == "stop_body":
                                time.sleep(0.1)
                            provider.stop_path.write_text("synthetic operator stop\n", encoding="utf-8")
                    stopper = threading.Thread(target=stop_after_receive, daemon=True)
                    stopper.start()
                started = time.monotonic()
                outcome = "completed"
                try:
                    if mode == "untrusted":
                        provider.respond(mode, request, timeout=20)
                    else:
                        with patch("research.e009_provider.ssl.create_default_context", trusted_context):
                            provider.respond(mode, request, timeout=0.4 if mode == "deadline_body" else 20)
                except ProviderFailure as error:
                    outcome = error.reason
                finally:
                    release.set()
                    if stopper:
                        stopper.join(timeout=2)
                records = provider.ledger.records()
                if mode in {"stop", "stop_body"}:
                    latency = time.time() - provider.stop_path.stat().st_mtime
                    write_once(directory / (mode + "-latency.json"), {"seconds": latency, "maximum_seconds": 1})
                    assert latency < 1, ("STOP did not interrupt blocked HTTPS promptly", latency)
                expected = {"untrusted": "tls_failure", "retry": "completed",
                             "redirect": "http_status", "stop": "operator_stop", "stop_body": "operator_stop",
                             "deadline_body": "retry_wait_exceeds_deadline"}[mode]
                assert outcome == expected, (mode, outcome)
                assert len(state["posts"]) == {"untrusted": 0, "retry": 3, "redirect": 1, "stop": 1,
                                               "stop_body": 1, "deadline_body": 1}[mode]
                assert all(p["auth_correct"] and p["path"] == "/v1/responses" for p in state["posts"])
                assert all(p["body_sha256"] == records[-1]["request_sha256"] for p in state["posts"])
                if mode == "retry":
                    assert records[1]["started"] - records[0]["finished"] >= records[0]["retry_delay"]
                    assert records[2]["started"] - records[1]["finished"] >= records[1]["retry_delay"]
                if mode in {"stop_body", "deadline_body"}:
                    assert records[0]["http_status"] == 200 and records[0]["response_body_bytes_observed"] == 1
                    assert not records[0]["response_complete"]
                    assert time.monotonic() - started < 1
                record = {"mode": mode, "outcome": outcome, "posts": list(state["posts"]),
                          "attempts": records, "seconds": time.monotonic() - started,
                          "ledger_sha256": digest(provider.ledger.path), "model_api_calls": 0}
                write_once(directory / (mode + "-RESULT.json"), record)
                cases.append(record)
                print(json.dumps({"mode": mode, "outcome": outcome, "posts": len(state["posts"]),
                                  "attempts": len(records)}), flush=True)
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
        raise AssertionError("loopback server still listening")
    except OSError:
        pass
    for path in directory.rglob("*"):
        if path.is_file():
            assert SYNTHETIC_KEY.encode() not in path.read_bytes(), path
    write_once(directory / "SUMMARY.json", {"pass": True, "cases": cases, "server_closed": True,
        "model_api_calls": 0, "scope": "Actual localhost TCP/TLS and HTTP, not external gateway/model verification"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--openssl", required=True)
    args = parser.parse_args()
    run(args.output, args.openssl)
