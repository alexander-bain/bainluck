"""Decision 220-A: TestFlight feedback files itself as a "[Bug Report]" issue.

The pure half of the receiver: switched off until configured, Apple's
signature, the event envelope, the App Store Connect token, the fetch and the
BugReport columns. The route lives in tests/integration/test_route_testflight_webhook.py.
"""

import base64
import hashlib
import hmac

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.services import testflight_feedback as tf
from app.tasks.bug_report_github import compute_fingerprint, format_issue_body

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _pem():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return key, pem


def _env(pem, **over):
    env = {"TESTFLIGHT_WEBHOOK_SECRET": "s" * 32, "ASC_API_ISSUER_ID": "issuer-1",
           "ASC_API_KEY_ID": "ABCDE12345", "ASC_API_PRIVATE_KEY": pem}
    env.update(over)
    return env


def test_switched_off_until_every_setting_is_present():
    _, pem = _pem()
    assert tf.config_from_env(_env(pem)) is not None
    for missing in ("TESTFLIGHT_WEBHOOK_SECRET", "ASC_API_ISSUER_ID", "ASC_API_KEY_ID", "ASC_API_PRIVATE_KEY"):
        assert tf.config_from_env(_env(pem, **{missing: ""})) is None, missing
    assert tf.config_from_env(_env(pem, TESTFLIGHT_WEBHOOK_SECRET="short")) is None
    assert tf.config_from_env(_env(pem, ASC_API_KEY_ID="bad id")) is None
    assert "s" * 32 not in repr(tf.config_from_env(_env(pem)))


def test_a_pem_pasted_with_escaped_newlines_still_loads():
    _, pem = _pem()
    config = tf.config_from_env(_env(pem.replace("\n", "\\n")))
    assert config is not None and "\n" in config.private_key


@pytest.mark.parametrize("form", ["multi-line", "multi-line CRLF", "literal backslash-n", "newlines as spaces"])
def test_the_key_signs_in_every_form_the_heroku_config_vars_box_can_hold(form):
    """Fable, Nov 17: Alex pastes the .p8 into the dashboard's Config Vars box, either
    as the file's lines or as one line with literal \\n. Each must sign a token App
    Store Connect can verify, not only parse."""
    key, pem = _pem()
    lines = pem.strip().splitlines()
    value = {
        "multi-line": pem,
        "multi-line CRLF": "\r\n".join(lines) + "\r\n",
        "literal backslash-n": "\\n".join(lines),
        "newlines as spaces": " ".join(lines),
    }[form]
    config = tf.config_from_env(_env(value))
    assert config is not None, form
    claims = jwt.decode(tf.api_token(config), key.public_key(), algorithms=["ES256"],
                        audience="appstoreconnect-v1")
    assert claims["iss"] == "issuer-1"


def test_only_apples_hmac_of_the_exact_body_passes():
    secret, body = "s" * 32, b'{"data":{}}'
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert tf.verify_signature(secret, body, f"hmacsha256={digest}")
    assert tf.verify_signature(secret, body, digest)
    assert not tf.verify_signature(secret, body + b" ", f"hmacsha256={digest}")
    assert not tf.verify_signature("x" * 32, body, f"hmacsha256={digest}")
    assert not tf.verify_signature(secret, body, f"sha1={digest}")
    assert not tf.verify_signature(secret, body, None)


def _payload(event_type, kind, sid):
    return {"data": {"type": event_type, "id": "evt", "version": 1,
                     "relationships": {"instance": {"data": {"type": kind, "id": sid}}}}}


def test_the_envelope_names_the_submission():
    assert tf.parse_event(_payload("betaFeedbackScreenshotSubmissionCreated", tf.SCREENSHOT, "AbC-1")) == \
        tf.FeedbackEvent(tf.SCREENSHOT, "AbC-1")
    assert tf.parse_event(_payload("betaFeedbackCrashSubmissionCreated", tf.CRASH, "x2")) == tf.FeedbackEvent(tf.CRASH, "x2")
    # The type alone is enough when the instance type is absent.
    assert tf.parse_event(_payload("betaFeedbackCrashSubmissionCreated", None, "x3")) == tf.FeedbackEvent(tf.CRASH, "x3")
    assert tf.parse_event({"data": {"type": "webhookPingCreated"}}) == "ping"
    assert tf.parse_event(_payload("buildUploadStateUpdated", "buildUploads", "b1")) is None
    assert tf.parse_event(_payload("betaFeedbackCrashSubmissionCreated", tf.CRASH, "../etc")) is None
    assert tf.parse_event([]) is None


def test_the_token_is_what_app_store_connect_expects():
    key, pem = _pem()
    config = tf.config_from_env(_env(pem))
    token = tf.api_token(config)
    header = jwt.get_unverified_header(token)
    assert header["kid"] == "ABCDE12345" and header["alg"] == "ES256"
    claims = jwt.decode(token, key.public_key(), algorithms=["ES256"], audience="appstoreconnect-v1")
    assert claims["iss"] == "issuer-1"
    assert 0 < claims["exp"] - claims["iat"] <= 20 * 60


def _client(routes):
    def handler(request):
        for prefix, response in routes.items():
            if str(request.url).startswith(prefix):
                return response(request) if callable(response) else response
        return httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_a_screenshot_submission_is_fetched_with_the_key():
    _, pem = _pem()
    config = tf.config_from_env(_env(pem))
    seen = {}

    def submission(request):
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"data": {"attributes": {
            "comment": "Headline cut off", "email": "tester@example.com", "deviceModel": "iPhone17,1",
            "osVersion": "27.1", "createdDate": "2001-01-01T00:00:00Z",
            "screenshots": [{"url": "https://shots.example/1.png"}]}}})

    async with _client({f"{tf.ASC_API}/v1/{tf.SCREENSHOT}/s1": submission,
                        "https://shots.example/1.png": httpx.Response(200, content=PNG)}) as client:
        fetched = await tf.fetch_submission(config, tf.FeedbackEvent(tf.SCREENSHOT, "s1"), client)
    assert seen["auth"].startswith("Bearer ")
    assert base64.b64decode(fetched["screenshot_base64"]) == PNG
    assert fetched["crash_log"] is None

    fields = tf.bug_report_fields(tf.FeedbackEvent(tf.SCREENSHOT, "s1"), fetched)
    assert fields["description"] == "Headline cut off"
    assert fields["session_id"] == "tf-shot:s1"
    assert fields["category"] == "ios"
    assert fields["user_email"] == "tester@example.com"
    assert fields["app_state"]["source"] == "testflight"
    assert fields["app_state"]["device_model"] == "iPhone17,1"


@pytest.mark.asyncio
async def test_a_crash_brings_the_start_of_its_log_and_no_error_page_becomes_a_screenshot():
    _, pem = _pem()
    config = tf.config_from_env(_env(pem))
    log = "\n".join(f"frame {n}" for n in range(5000))
    async with _client({
        f"{tf.ASC_API}/v1/{tf.CRASH}/c1/crashLog": httpx.Response(200, json={"data": {"attributes": {"logText": log}}}),
        f"{tf.ASC_API}/v1/{tf.CRASH}/c1": httpx.Response(200, json={"data": {"attributes": {
            "comment": "", "screenshots": [{"url": "https://shots.example/x"}]}}}),
        "https://shots.example/x": httpx.Response(200, content=b"<html>"),
    }) as client:
        fetched = await tf.fetch_submission(config, tf.FeedbackEvent(tf.CRASH, "c1"), client)
    assert fetched["screenshot_base64"] is None
    assert fetched["crash_log"].startswith("frame 0") and len(fetched["crash_log"]) <= tf.MAX_CRASH_LOG_CHARS
    fields = tf.bug_report_fields(tf.FeedbackEvent(tf.CRASH, "c1"), fetched)
    assert fields["description"] == "TestFlight crash (no comment)"
    assert fields["session_id"] == "tf-crash:c1"


@pytest.mark.asyncio
async def test_a_failed_fetch_raises_so_apple_delivers_again():
    _, pem = _pem()
    config = tf.config_from_env(_env(pem))
    async with _client({f"{tf.ASC_API}/v1/{tf.SCREENSHOT}/s9": httpx.Response(403)}) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await tf.fetch_submission(config, tf.FeedbackEvent(tf.SCREENSHOT, "s9"), client)


def test_two_testflight_reports_never_fold_into_one_issue():
    a = {"source": "testflight", "testflight_submission_id": "one", "current_page": "TestFlight feedback"}
    b = {"source": "testflight", "testflight_submission_id": "two", "current_page": "TestFlight feedback"}
    assert compute_fingerprint(a, "ios", "chart is wrong") != compute_fingerprint(b, "ios", "chart is wrong")
    # Shake reports keep the page + category + diagnosis fingerprint.
    shake = {"current_page": "/discover"}
    assert compute_fingerprint(shake, "ios", "chart is wrong") == compute_fingerprint(dict(shake), "ios", "chart axis wrong")


def test_the_issue_says_it_came_from_testflight_and_shows_the_crash_start():
    state = {"source": "testflight", "testflight_kind": "crash", "testflight_submission_id": "c1",
             "platform": "IOS (TestFlight)", "crash_log": "Thread 0 Crashed:\n0 Bain Luck 0x1"}
    body = format_issue_body(5, "TestFlight crash: froze", "ios", state, has_screenshot=False)
    assert "Auto-created from TestFlight crash feedback (report #5)" in body
    assert "Thread 0 Crashed:" in body
    assert "/admin/bug-reports?id=5" in body
    shake = format_issue_body(6, "x", "ios", {"crash_log": "nope"}, has_screenshot=False)
    assert "Auto-created from rage shake" in shake and "nope" not in shake


def _make_png_bytes(width: int, height: int) -> bytes:
    import io
    import random
    from PIL import Image

    rng = random.Random(42)
    img = Image.frombytes("RGB", (width, height), rng.randbytes(width * height * 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_oversized_png_is_reencoded_to_jpeg_instead_of_dropped():
    big_png = _make_png_bytes(400, 400)
    raw_b64 = base64.b64encode(big_png).decode("ascii")
    ceiling = len(raw_b64) // 2  # force compression path
    assert ceiling > 100_000
    result = tf.compress_screenshot_if_needed(big_png, max_b64_len=ceiling)
    assert result is not None
    assert len(result) <= ceiling
    decoded = base64.b64decode(result)
    assert decoded[:3] == b"\xff\xd8\xff"


def test_strip_emails_and_phones_redacts_pii_without_touching_scores_or_dates():
    text = (
        "- Game page: Houston 78-74 Florida, Now 61.4% vs 38.6% on 2001-01-01 at 5:02 PM.\n"
        "- Contact tester@example.com or +1 (555) 234-5678 / 555-867-5309."
    )
    cleaned = tf.strip_emails_and_phones(text)
    assert "Houston 78-74 Florida" in cleaned
    assert "61.4%" in cleaned
    assert "2001-01-01" in cleaned
    assert "5:02 PM" in cleaned
    assert "tester@example.com" not in cleaned
    assert "234-5678" not in cleaned
    assert "867-5309" not in cleaned
    assert "[redacted email]" in cleaned
    assert "[redacted phone]" in cleaned


def test_issue_body_includes_model_label_and_direct_admin_link():
    state = {"source": "testflight", "testflight_kind": "screenshot", "testflight_submission_id": "s42"}
    body = format_issue_body(
        42,
        "Score header cut off",
        "ios",
        state,
        has_screenshot=True,
        screenshot_summary="- Live Activity card shows 'Scor' / 'e' header wrap.",
    )
    assert "### Screenshot description" in body
    assert "Written by a model from the screenshot" in body
    assert "Live Activity card shows 'Scor' / 'e' header wrap." in body
    assert "/admin/bug-reports?id=42" in body
    assert "data:image" not in body

    without_summary = format_issue_body(43, "Blank screen", "ios", state, has_screenshot=True)
    assert "### Screenshot description" not in without_summary
    assert "/admin/bug-reports?id=43" in without_summary


def test_summarize_testflight_screenshot_respects_registry_cap_pii_and_cost_logging(monkeypatch, caplog):
    import logging
    from types import SimpleNamespace
    from app.services import llm_request

    class _FakeRedis:
        def __init__(self):
            self.counts = {}

        def register_script(self, _lua):
            def _run(keys, args, client=None):
                key = keys[0]
                cap = int(args[0])
                cur = self.counts.get(key, 0)
                if cur >= cap:
                    return 0
                self.counts[key] = cur + 1
                return 1
            return _run

    class _FakeLedger:
        def reserve(self, day, task, micros, cap_micros):
            return True

        def adjust(self, day, task, delta):
            return None

    calls = []

    class _FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="- Discover feed: Houston 61.4% vs Florida 38.6%; email leaked@example.com, call 555-321-7654."
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=900, completion_tokens=45),
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions()))
    fake_redis = _FakeRedis()
    monkeypatch.setattr(llm_request, "_get_ledger", lambda: _FakeLedger())

    small_png_b64 = base64.b64encode(_make_png_bytes(120, 200)).decode("ascii")

    with caplog.at_level(logging.INFO, logger="app.services.testflight_feedback"):
        first = tf.summarize_testflight_screenshot(
            small_png_b64,
            report_id=77,
            client=fake_client,
            redis_client=fake_redis,
            daily_cap=1,
        )
        second = tf.summarize_testflight_screenshot(
            small_png_b64,
            report_id=78,
            client=fake_client,
            redis_client=fake_redis,
            daily_cap=1,
        )

    assert first is not None
    assert "Houston 61.4% vs Florida 38.6%" in first
    assert "leaked@example.com" not in first
    assert "321-7654" not in first
    assert second is None  # daily cap of 1 enforced without a second model call
    assert len(calls) == 1
    assert any("cost_usd=$" in rec.message and "report #77" in rec.message for rec in caplog.records)


def test_summarize_testflight_screenshot_returns_none_on_model_error(monkeypatch):
    from types import SimpleNamespace
    from app.services import llm_request

    class _FakeRedis:
        def register_script(self, _lua):
            return lambda keys, args, client=None: 1

    class _FakeLedger:
        def reserve(self, day, task, micros, cap_micros):
            return True

        def adjust(self, day, task, delta):
            return None

    class _BrokenCompletions:
        def create(self, **kwargs):
            raise TimeoutError("slow provider")

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=_BrokenCompletions()))
    monkeypatch.setattr(llm_request, "_get_ledger", lambda: _FakeLedger())
    small_png_b64 = base64.b64encode(_make_png_bytes(64, 64)).decode("ascii")

    assert (
        tf.summarize_testflight_screenshot(
            small_png_b64,
            report_id=99,
            client=fake_client,
            redis_client=_FakeRedis(),
            daily_cap=5,
        )
        is None
    )
