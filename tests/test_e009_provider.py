"""Synthetic credentials and transports only; never contacts the configured gateway."""
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import format_datetime
import hashlib
import json
from pathlib import Path
import ssl
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from research.e009_broker import frame
from research.e009_provider import HTTPSProvider, ProviderFailure, retry_delay
from research.e009_replay import audit_transport

SYNTHETIC_KEY = "SYNTHETIC-provider-key-not-a-real-credential"


def success(**changes):
    return {"model": "fixture-model", "status": "completed", "output": [
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "{}"}]}],
        "usage": {"input_tokens": 11, "output_tokens": 7}, **changes}


def request():
    return {"model": "fixture-model", "store": False, "input": [{"role": "user", "content": "synthetic"}]}


class FakeClock:
    def __init__(self):
        self.value = 1000.0
        self.callback = None

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds
        if self.callback:
            self.callback()

    @contextmanager
    def installed(self):
        with patch("research.e009_provider.time.monotonic", self.now), patch(
                "research.e009_provider.time.time", self.now), patch(
                "research.e009_provider.time.sleep", self.sleep), patch(
                "research.e009_provider.random.uniform", return_value=0):
            yield self


class QueueProvider(HTTPSProvider):
    fixture = True

    def __init__(self, directory, events, **kwargs):
        self.events = deque(events)
        self.calls = []
        super().__init__("https://fixture.invalid/v1", "fixture-model", directory,
                         authorize=True, **kwargs)

    def _attempt(self, body, timeout, observation):
        self.calls.append({"body": json.loads(body), "timeout": timeout})
        event = self.events.popleft()
        observation["request_may_have_been_sent"] = event.get("sent", True)
        if "error" in event:
            raise event["error"]
        status = event.get("status", 200)
        raw = event.get("raw")
        if raw is None:
            raw = frame(event.get("response", success()))
        observation.update(http_status=status, response_body_bytes_observed=len(raw), response_complete=True)
        return status, event.get("retry_after"), raw


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.key_patch = patch.dict("os.environ", {"API_KEY": SYNTHETIC_KEY})
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def provider(self, events, name="ledger", **kwargs):
        return QueueProvider(self.root / name, events, **kwargs)

    def test_retry_after_never_shortens_backoff(self):
        self.assertEqual(retry_delay("7", 2, 0), 7)
        self.assertEqual(retry_delay("1", 2, 0), 2)

    def test_retry_after_date_invalid_and_nonfinite(self):
        date = format_datetime(datetime.fromtimestamp(1020, timezone.utc), usegmt=True)
        self.assertEqual(retry_delay(date, 2, 1000), 20)
        for value in ("garbage", "nan", "inf", "-2", None):
            self.assertEqual(retry_delay(value, 2, 0), 2)

    def test_default_deny_and_missing_key(self):
        with self.assertRaisesRegex(ProviderFailure, "authorization_required"):
            HTTPSProvider("https://fixture.invalid/v1", "fixture-model", self.root / "denied")
        self.assertFalse((self.root / "denied").exists())
        with patch.dict("os.environ", {"API_KEY": ""}):
            with self.assertRaisesRegex(ProviderFailure, "credential_unavailable"):
                HTTPSProvider("https://fixture.invalid/v1", "fixture-model", self.root / "missing", authorize=True)

    def test_invalid_endpoint_rejected(self):
        for url in ("http://fixture.invalid/v1", "https://user:pass@fixture.invalid/v1",
                    "https://fixture.invalid/v1?x=1", "https://fixture.invalid/v2",
                    "https://fixture.invalid\n/v1"):
            with self.subTest(url=url), self.assertRaises(ProviderFailure):
                HTTPSProvider(url, "fixture-model", self.root / "invalid", authorize=True)

    def test_success_records_usage_and_rejects_duplicate(self):
        provider = self.provider([{}])
        self.assertEqual(provider.respond("context", request()), success())
        records = provider.ledger.records()
        self.assertEqual(records[0]["usage"], {"input_tokens": 11, "output_tokens": 7})
        with self.assertRaisesRegex(ProviderFailure, "duplicate_request"):
            provider.respond("context", request())
        self.assertEqual(records, provider.ledger.records())

    def test_503_429_backoff_and_retry_after(self):
        provider = self.provider([{"status": 503, "response": {}},
                                  {"status": 429, "retry_after": "7", "response": {}}, {}])
        with FakeClock().installed():
            provider.respond("context", request())
        records = provider.ledger.records()
        self.assertEqual(len(records), 3)
        self.assertEqual([r.get("retry_delay") for r in records], [2, 7, None])
        self.assertGreaterEqual(records[2]["started"] - records[1]["finished"], 7)

    def test_connection_refusal_and_partial_send_remain_distinct(self):
        provider = self.provider([{"error": ConnectionRefusedError(), "sent": False},
                                  {"error": TimeoutError(), "sent": True}, {}])
        with FakeClock().installed():
            provider.respond("context", request())
        self.assertEqual([r["usage_state"] for r in provider.ledger.records()], ["not_sent", "unknown", "reported"])

    def test_html_502_is_retried(self):
        provider = self.provider([{"status": 502, "raw": b"<html>unavailable</html>"}, {}])
        with FakeClock().installed():
            provider.respond("context", request())
        self.assertEqual(len(provider.calls), 2)

    def test_permanent_quota_and_auth_not_retried(self):
        for status, body in ((429, {"error": {"code": "insufficient_quota"}}), (401, {}), (403, {})):
            provider = self.provider([{"status": status, "response": body}], name=str(status))
            with self.assertRaises(ProviderFailure):
                provider.respond("context", request())
            self.assertEqual(len(provider.calls), 1)

    def test_redirect_not_followed(self):
        provider = self.provider([{"status": 302, "response": {}}])
        with self.assertRaises(ProviderFailure):
            provider.respond("context", request())
        self.assertEqual(len(provider.calls), 1)

    def test_tls_failure_not_retried(self):
        provider = self.provider([{"error": ssl.SSLCertVerificationError("synthetic"), "sent": False}])
        with self.assertRaisesRegex(ProviderFailure, "tls_failure"):
            provider.respond("context", request())
        self.assertEqual(provider.ledger.records()[0]["usage_state"], "not_sent")

    def test_reported_model_mismatch_retains_identity_and_usage(self):
        provider = self.provider([{"response": success(model="different-model")}])
        with self.assertRaisesRegex(ProviderFailure, "reported_model_mismatch"):
            provider.respond("context", request())
        record = provider.ledger.records()[0]
        self.assertEqual(record["reported_model"], "different-model")
        self.assertEqual(record["usage"]["output_tokens"], 7)

    def test_incomplete_response_not_retried_but_usage_retained(self):
        provider = self.provider([{"response": success(status="incomplete")}])
        with self.assertRaisesRegex(ProviderFailure, "invalid_response"):
            provider.respond("context", request())
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.ledger.records()[0]["usage"]["input_tokens"], 11)

    def test_missing_usage_is_unknown_not_zero(self):
        provider = self.provider([{"response": success(usage=None)}])
        provider.respond("context", request())
        record = provider.ledger.records()[0]
        self.assertEqual(record["usage_state"], "unknown")
        self.assertIsNone(record["usage"])
        self.assertIsNone(record["cost_usd"])

    def test_credential_echo_plain_and_json_escaped_never_persisted(self):
        plain = frame(success(extra=SYNTHETIC_KEY))
        escaped = plain.replace(SYNTHETIC_KEY.encode(), "".join("\\u%04x" % ord(c) for c in SYNTHETIC_KEY).encode())
        for name, raw in (("plain", plain), ("escaped", escaped)):
            provider = self.provider([{"raw": raw}], name=name)
            with self.assertRaisesRegex(ProviderFailure, "credential_echo"):
                provider.respond("context", request())
            self.assertNotIn(SYNTHETIC_KEY.encode(), provider.ledger.path.read_bytes())

    def test_credential_in_context_not_written_to_ledger(self):
        provider = self.provider([{}])
        with self.assertRaisesRegex(ProviderFailure, "unsafe_context"):
            provider.respond(SYNTHETIC_KEY, request())
        self.assertNotIn(SYNTHETIC_KEY.encode(), provider.ledger.path.read_bytes())

    def test_stop_before_call_makes_no_attempt(self):
        provider = self.provider([{}])
        provider.stop_path.write_text("stop")
        with self.assertRaisesRegex(ProviderFailure, "operator_stop"):
            provider.respond("context", request())
        self.assertEqual(provider.ledger.records(), [])

    def test_stop_interrupts_backoff_without_second_attempt(self):
        provider = self.provider([{"status": 503, "response": {}}, {}])
        clock = FakeClock()
        clock.callback = lambda: provider.stop_path.write_text("stop")
        with clock.installed(), self.assertRaisesRegex(ProviderFailure, "operator_stop"):
            provider.respond("context", request())
        self.assertEqual(len(provider.calls), 1)

    def test_retry_after_exceeds_deadline_and_blocks_next_request(self):
        provider = self.provider([{"status": 429, "retry_after": "1000", "response": {}}, {}])
        clock = FakeClock()
        with clock.installed():
            with self.assertRaisesRegex(ProviderFailure, "retry_wait_exceeds_deadline"):
                provider.respond("first", request(), timeout=10)
            with self.assertRaisesRegex(ProviderFailure, "retry_wait_exceeds_deadline"):
                provider.respond("second", request(), timeout=10)
            self.assertEqual(len(provider.calls), 1)
            clock.value += 1001
            provider.respond("third", request(), timeout=10)
        self.assertEqual(len(provider.calls), 2)

    def test_pending_orphan_blocks_reopen(self):
        provider = self.provider([])
        provider.ledger.begin("orphan", "a" * 64)
        reopened = self.provider([{}])
        with self.assertRaisesRegex(ProviderFailure, "pending_or_orphan_request"):
            reopened.respond("new", request())

    def test_crash_leaves_pending_attempt_without_silent_retry(self):
        provider = self.provider([{"error": KeyboardInterrupt(), "sent": True}])
        with self.assertRaises(KeyboardInterrupt):
            provider.respond("context", request())
        self.assertEqual(provider.ledger.records()[0]["status"], "pending")
        self.assertEqual(provider.accounting("context")["submitted_or_uncertain"], 1)
        self.assertEqual(provider.accounting("context")["unknown_usage_attempts"], 1)
        reopened = self.provider([{}])
        with self.assertRaisesRegex(ProviderFailure, "pending_or_orphan_request"):
            reopened.respond("new", request())

    def test_terminal_attempt_cannot_be_overwritten(self):
        provider = self.provider([{}])
        provider.respond("context", request())
        record = provider.ledger.records()[0]
        with self.assertRaisesRegex(ProviderFailure, "attempt_already_terminal"):
            provider.ledger.finish_attempt(record["id"], {"reason": "changed"})

    def transport_artifact(self):
        provider = self.provider([{}])
        response = provider.respond("context", request())
        directory = self.root / "raw"
        (directory / "provider").mkdir(parents=True)
        (directory / "provider/001-request.json").write_bytes(frame(request()))
        (directory / "provider/001-response.json").write_bytes(frame(response))
        (directory / "provider-attempts.json").write_bytes(frame(provider.ledger.records("context")))
        terminal = {"status": "completed", "responses": 1, "provider_accounting": provider.accounting("context")}
        binding = {"fixture": True, "provider_model": provider.model}
        return directory, terminal, binding

    def test_transport_replay_recomputes_usage(self):
        directory, terminal, binding = self.transport_artifact()
        result = audit_transport(directory, terminal, binding)
        self.assertEqual(result["reported_input_tokens"], 11)
        self.assertEqual(result["transport_attempts"], 1)

    def test_transport_replay_rejects_forged_usage_total(self):
        directory, terminal, binding = self.transport_artifact()
        terminal["provider_accounting"]["reported_input_tokens"] = 123456
        with self.assertRaisesRegex(ValueError, "accounting not equal"):
            audit_transport(directory, terminal, binding)

    def test_transport_replay_rejects_changed_model_with_rehashed_response(self):
        directory, terminal, binding = self.transport_artifact()
        response = success(model="different-model")
        (directory / "provider/001-response.json").write_bytes(frame(response))
        attempts = json.loads((directory / "provider-attempts.json").read_text())
        attempts[0]["response_json_sha256"] = hashlib.sha256(frame(response)).hexdigest()
        attempts[0]["reported_model"] = "different-model"
        (directory / "provider-attempts.json").write_bytes(frame(attempts))
        with self.assertRaisesRegex(ValueError, "response model differs"):
            audit_transport(directory, terminal, binding)

    def test_transport_replay_rejects_duplicate_attempt_identity(self):
        directory, terminal, binding = self.transport_artifact()
        attempts = json.loads((directory / "provider-attempts.json").read_text())
        (directory / "provider-attempts.json").write_bytes(frame(attempts + attempts))
        with self.assertRaisesRegex(ValueError, "duplicate attempt"):
            audit_transport(directory, terminal, binding)

    def test_transport_replay_rejects_boolean_usage(self):
        directory, terminal, binding = self.transport_artifact()
        attempts = json.loads((directory / "provider-attempts.json").read_text())
        attempts[0]["usage"]["input_tokens"] = True
        (directory / "provider-attempts.json").write_bytes(frame(attempts))
        with self.assertRaisesRegex(ValueError, "invalid reported usage"):
            audit_transport(directory, terminal, binding)

    def test_quota_type_without_code_not_retried(self):
        provider = self.provider([{"status": 429, "response": {"error": {"type": "insufficient_quota"}}}])
        with self.assertRaisesRegex(ProviderFailure, "quota_action_required"):
            provider.respond("context", request())
        self.assertEqual(len(provider.calls), 1)

    def test_four_attempts_not_unbounded(self):
        provider = self.provider([{"status": 503, "response": {}}] * 4)
        with FakeClock().installed(), self.assertRaises(ProviderFailure):
            provider.respond("context", request())
        self.assertEqual(len(provider.calls), 4)

    def test_request_rejects_cross_context_ids_and_key_payload(self):
        for extra in ({"previous_response_id": "old"}, {"conversation": "old"},
                      {"model": "different"}, {"store": True}, {"input": SYNTHETIC_KEY}):
            provider = self.provider([], name=hashlib.sha256(frame(extra)).hexdigest())
            with self.assertRaises(ProviderFailure):
                provider.respond("context", {**request(), **extra})
            self.assertEqual(provider.ledger.records(), [])

    def test_real_transport_uses_verified_tls_fixed_post_and_no_redirect_logic(self):
        import httpx2 as httpx
        received = []
        async def handle(req):
            received.append(req)
            return httpx.Response(200, stream=httpx.ByteStream(frame(success())))
        provider = HTTPSProvider("https://fixture.invalid/v1", "fixture-model", self.root / "real-method", authorize=True)
        with patch("research.e009_provider.httpx.AsyncHTTPTransport",
                   return_value=httpx.MockTransport(handle)) as factory:
            provider.respond("context", request())
        context = factory.call_args.kwargs["verify"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertIs(factory.call_args.kwargs["trust_env"], False)
        self.assertEqual(factory.call_args.kwargs["retries"], 0)
        self.assertEqual((received[0].method, str(received[0].url)),
                         ("POST", "https://fixture.invalid/v1/responses"))

    def test_stop_interrupts_blocking_transport(self):
        import asyncio
        import httpx2 as httpx
        cancelled = threading.Event()
        async def handle(_):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        provider = HTTPSProvider("https://fixture.invalid/v1", "fixture-model", self.root / "blocking", authorize=True)
        timer = threading.Timer(0.1, lambda: provider.stop_path.write_text("stop"))
        timer.start()
        started = time.monotonic()
        try:
            with patch("research.e009_provider.httpx.AsyncHTTPTransport",
                       return_value=httpx.MockTransport(handle)):
                with self.assertRaisesRegex(ProviderFailure, "operator_stop"):
                    provider.respond("context", request(), timeout=3)
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - started, 1)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(provider.ledger.records()[0]["usage_state"], "unknown")

    def test_attempt_deadline_cancels_and_joins_blocked_transport(self):
        import asyncio
        import httpx2 as httpx
        cancelled = threading.Event()
        async def handle(_):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        provider = HTTPSProvider("https://fixture.invalid/v1", "fixture-model", self.root / "deadline", authorize=True)
        with patch("research.e009_provider.httpx.AsyncHTTPTransport",
                   return_value=httpx.MockTransport(handle)):
            with self.assertRaisesRegex(ProviderFailure, "retry_wait_exceeds_deadline"):
                provider.respond("context", request(), timeout=0.15)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(len(provider.ledger.records()), 1)
        self.assertEqual(provider.ledger.records()[0]["reason"], "attempt_deadline")

    def test_nested_tls_context_is_not_retried_as_network_failure(self):
        import httpx2 as httpx
        async def handle(_):
            try:
                raise ssl.SSLCertVerificationError("synthetic untrusted certificate")
            except ssl.SSLError:
                raise httpx.ConnectError("synthetic wrapper") from None
        provider = HTTPSProvider("https://fixture.invalid/v1", "fixture-model", self.root / "tls-context", authorize=True)
        with patch("research.e009_provider.httpx.AsyncHTTPTransport",
                   return_value=httpx.MockTransport(handle)):
            with self.assertRaisesRegex(ProviderFailure, "tls_failure"):
                provider.respond("context", request())
        self.assertEqual(len(provider.ledger.records()), 1)
        self.assertIs(provider.ledger.records()[0]["request_may_have_been_sent"], False)


if __name__ == "__main__":
    unittest.main()
