"""Exercise the actual E008 HTTPS transport against a loopback-only fault server."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import ssl
import subprocess
import threading
from unittest.mock import patch

from .common import ROOT, digest, write_json
from .e008_resources import BoundedProvider, SeriesLedger, SeriesStopped, provider_failure_action, resource_policy


def fixture(identity, openssl):
    if not identity.startswith("e008-transport-fixture-") or not all(c.isalnum() or c == "-" for c in identity):
        raise ValueError("new transport fixture identity required")
    study = ROOT / "runs" / identity
    study.mkdir(exist_ok=False)
    certificate, private_key = study / "localhost-cert.pem", study / "localhost-key.pem"
    command = [str(Path(openssl).resolve(strict=True)), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
               "-days", "1", "-keyout", str(private_key), "-out", str(certificate),
               "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"]
    generated = subprocess.run(command, capture_output=True, text=True, timeout=30)
    write_json(study / "certificate-command.json", {"command": command, "exit_status": generated.returncode,
                                                  "stdout": generated.stdout, "stderr": generated.stderr})
    if generated.returncode:
        raise RuntimeError("local test certificate generation failed")
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certificate, private_key)
    # Trust just this ephemeral test certificate in this process; never disable
    # verification, change system trust, or connect to the paid gateway.
    client_context = ssl.create_default_context(cafile=str(certificate))
    events, handler_errors = [], []
    request_done, release_timeout = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Default access logs are replaced by structured path/status events.

        def do_GET(self):
            assert self.path == "/v1/models"
            body = json.dumps({"data": [{"id": "fixture-transport"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            events.append({"method": "GET", "path": self.path, "status": 200})

        def do_POST(self):
            try:
                assert self.path == "/v1/responses"
                assert self.headers["Authorization"] == "Bearer fixture-only"
                body = self.rfile.read(int(self.headers["Content-Length"]))
                payload = json.loads(body)
                assert payload["store"] is False and payload["parallel_tool_calls"] is False
                mode = self.server.mode
                status = mode if type(mode) is int else 200
                response = {"status": "completed", "model": "wrong-model" if mode == "wrong-model" else "fixture-transport",
                            "output": [], "usage": {"input_tokens": 1, "output_tokens": 1}}
                raw = b"x" * (4194304 + 1) if mode == "oversized" else json.dumps(response).encode()
                if mode == "timeout":
                    release_timeout.wait(3)
                events.append({"method": "POST", "path": self.path, "status": status,
                               "request_bytes": len(body), "intended_response_bytes": len(raw), "mode": mode})
                try:
                    self.send_response(status)
                    if status == 302:
                        self.send_header("Location", "/should-not-follow")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ssl.SSLError) as exc:
                    if mode not in ("timeout", "oversized"):
                        raise
                    events[-1]["expected_peer_closure"] = type(exc).__name__
            except Exception as exc:
                handler_errors.append(type(exc).__name__)
                raise
            finally:
                request_done.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cases = [(200, None, "stop"), (429, "RuntimeError", "recover_next_position"),
             (503, "RuntimeError", "recover_next_position"), (401, "RuntimeError", "stop"),
             (302, "RuntimeError", "stop"), ("wrong-model", "ValueError", "stop"),
             ("oversized", "ValueError", "stop"), ("timeout", "TimeoutError", "recover_next_position")]
    jobs = [{"id": f"http{i}"} for i in range(len(cases))] + [{"id": "untrusted-tls"}, {"id": "after-stop"}]
    guard = SeriesLedger(study, resource_policy(jobs))
    guard.start()
    provider = BoundedProvider(f"https://127.0.0.1:{server.server_port}/v1", "fixture-transport", guard,
                               study / "provider.jsonl", authorize=True, key="fixture-only")
    outcomes = []
    try:
        for i, (mode, expected_error, expected_action) in enumerate(cases):
            server.mode = mode
            request_done.clear()
            error = None
            with patch("research.e007_provider.ssl.create_default_context", return_value=client_context):
                try:
                    provider.respond(f"http{i}", [], [], timeout=.2 if mode == "timeout" else 5)
                except Exception as exc:
                    error = type(exc).__name__
                finally:
                    if mode == "timeout":
                        release_timeout.set()
            if not request_done.wait(5):
                raise AssertionError("local HTTP handler did not finish")
            assert not handler_errors, handler_errors
            assert error == expected_error, (mode, error, expected_error)
            records = [json.loads(line) for line in (study / "provider.jsonl").read_text().splitlines()]
            measured = next(r for r in reversed(records) if r["event"] == "transport_bytes" and r["worker"] == f"http{i}")
            action = provider_failure_action(error, measured["http_status"])
            assert action == expected_action
            outcomes.append({"mode": mode, "observed_error": error, "action_if_failed": action,
                             "transport": measured, "pass": True})
        try:
            provider.respond("untrusted-tls", [], [], timeout=5)
        except ssl.SSLCertVerificationError:
            outcomes.append({"mode": "untrusted-tls", "observed_error": "SSLCertVerificationError", "pass": True})
        else:
            raise AssertionError("untrusted TLS unexpectedly accepted")
        with patch("research.e007_provider.ssl.create_default_context", return_value=client_context):
            assert provider.models() == ["fixture-transport"]
        count = len(events)
        (study / "STOP").touch()
        try:
            provider.respond("after-stop", [], [])
        except SeriesStopped:
            pass
        else:
            raise AssertionError("STOP did not close network admission")
        assert len(events) == count
    finally:
        release_timeout.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    with closing(sqlite3.connect(guard.path)) as db:
        attempts = db.execute("SELECT worker,outcome FROM attempts ORDER BY id").fetchall()
        metadata = db.execute("SELECT outcome FROM metadata_attempts").fetchall()
    assert len(attempts) == 9 and all(status != "pending" for _, status in attempts)
    assert attempts[0][1] == "completed" and all(status == "failed_or_unknown" for _, status in attempts[1:])
    assert metadata == [("completed",)]
    assert len(events) == 9 and all(e["path"] in ("/v1/models", "/v1/responses") for e in events)
    report = {"pass": True, "model_API_requests": 0, "local_HTTPS_response_attempts": len(attempts),
              "metadata_attempts": len(metadata), "no_redirect_followed": True, "no_request_retried": True,
              "STOP_sent_no_request": True, "system_TLS_settings_changed": False,
              "certificate_sha256": digest(certificate), "private_key": "ephemeral local fixture only; outside Git",
              "cases": outcomes, "server_events": events, "attempts": attempts}
    write_json(study / "fixture-result.json", report)
    return {"pass": True, "cases": len(outcomes), "model_API_requests": 0, "study": str(study)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity")
    parser.add_argument("--openssl", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(fixture(args.identity, args.openssl)))
