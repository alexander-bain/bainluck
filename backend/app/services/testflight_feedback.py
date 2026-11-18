"""TestFlight feedback becomes a "[Bug Report]" issue (decision 220-A, Nov 17).

App Store Connect calls our webhook when a tester sends screenshot or crash
feedback. The receiver checks Apple's signature, fetches the submission with
the App Store Connect key, and stores it as an ordinary ``BugReport`` row, so
the issue is filed by the same task, with the same labels, routing and dedup,
as a shake report. Nothing runs on a schedule.

It is switched off until every setting below is present; while off the route
answers 404 and touches nothing.

    TESTFLIGHT_WEBHOOK_SECRET   the secret typed into the webhook in App Store Connect
    ASC_API_ISSUER_ID           the key's issuer id
    ASC_API_KEY_ID              the key's id
    ASC_API_PRIVATE_KEY         the key's .p8 contents (PEM)

No value is ever logged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import jwt

logger = logging.getLogger(__name__)

ASC_API = "https://api.appstoreconnect.apple.com"
SIGNATURE_HEADER = "X-Apple-SIGNATURE"
#: A webhook body is a small JSON envelope; anything larger is not Apple's.
MAX_BODY_BYTES = 64 * 1024
#: Same ceiling the shake route enforces on its screenshot field.
MAX_SCREENSHOT_BASE64 = 2_000_000
#: Kept on the report for whoever triages the crash; the full log stays in App Store Connect.
MAX_CRASH_LOG_CHARS = 20_000
#: App Store Connect accepts tokens that live at most 20 minutes.
TOKEN_LIFETIME_SECONDS = 15 * 60

SCREENSHOT = "betaFeedbackScreenshotSubmissions"
CRASH = "betaFeedbackCrashSubmissions"
KINDS = (SCREENSHOT, CRASH)


@dataclass(frozen=True)
class TestFlightWebhookConfig:
    secret: str
    issuer_id: str
    key_id: str
    private_key: str

    def __repr__(self) -> str:  # never print the secret or the key
        return "TestFlightWebhookConfig(<redacted>)"


def config_from_env(env: Mapping[str, str]) -> Optional[TestFlightWebhookConfig]:
    """The receiver's settings, or None (switched off) if any is missing or malformed."""
    secret = (env.get("TESTFLIGHT_WEBHOOK_SECRET") or "").strip()
    issuer = (env.get("ASC_API_ISSUER_ID") or "").strip()
    key_id = (env.get("ASC_API_KEY_ID") or "").strip()
    pem = (env.get("ASC_API_PRIVATE_KEY") or "").strip().replace("\\n", "\n")
    if not (len(secret) >= 16 and issuer and re.fullmatch(r"[A-Z0-9]{10}", key_id)
            and "PRIVATE KEY" in pem and len(pem) <= 16_384):
        return None
    return TestFlightWebhookConfig(secret, issuer, key_id, pem)


def verify_signature(secret: str, body: bytes, header: Optional[str]) -> bool:
    """HMAC-SHA256 of the raw body with the webhook's secret, hex encoded.

    Apple sends it as ``hmacsha256=<hex>``; a bare hex digest is accepted too.
    Compared in constant time."""
    if not secret or not header:
        return False
    value = header.strip()
    if "=" in value:
        scheme, _, value = value.partition("=")
        if scheme.strip().lower() != "hmacsha256":
            return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, value.strip().lower())


@dataclass(frozen=True)
class FeedbackEvent:
    kind: str           # SCREENSHOT or CRASH
    submission_id: str


def parse_event(payload: Any) -> Optional[FeedbackEvent] | str:
    """The submission a delivery is about; "ping" for Apple's test delivery;
    None for any other event (accepted and ignored)."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    event_type = str(data.get("type") or "")
    if "ping" in event_type.lower():
        return "ping"
    instance = ((data.get("relationships") or {}).get("instance") or {}).get("data") or {}
    kind = instance.get("type") if isinstance(instance, dict) else None
    submission_id = instance.get("id") if isinstance(instance, dict) else None
    if kind not in KINDS:
        lowered = event_type.lower()
        kind = SCREENSHOT if "screenshot" in lowered else CRASH if "crash" in lowered else None
    if kind is None or not isinstance(submission_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", submission_id):
        return None
    return FeedbackEvent(kind, submission_id)


def session_key(event: FeedbackEvent) -> str:
    """Stored in ``BugReport.session_id`` so a repeated delivery files nothing new."""
    prefix = "tf-shot" if event.kind == SCREENSHOT else "tf-crash"
    return f"{prefix}:{event.submission_id}"[:100]


def api_token(config: TestFlightWebhookConfig, now: Optional[datetime] = None) -> str:
    issued = int((now or datetime.now(timezone.utc)).timestamp())
    return jwt.encode(
        {"iss": config.issuer_id, "iat": issued, "exp": issued + TOKEN_LIFETIME_SECONDS,
         "aud": "appstoreconnect-v1"},
        config.private_key,
        algorithm="ES256",
        headers={"kid": config.key_id, "typ": "JWT"},
    )


async def fetch_submission(config: TestFlightWebhookConfig, event: FeedbackEvent, client) -> dict:
    """The submission's attributes, its first screenshot (base64) and, for a
    crash, the start of the crash log. ``client`` is an ``httpx.AsyncClient``."""
    headers = {"Authorization": f"Bearer {api_token(config)}"}
    resp = await client.get(f"{ASC_API}/v1/{event.kind}/{event.submission_id}", headers=headers)
    resp.raise_for_status()
    attributes = (resp.json().get("data") or {}).get("attributes") or {}
    screenshot_b64 = None
    for shot in attributes.get("screenshots") or []:
        url = shot.get("url") if isinstance(shot, dict) else None
        if not url or not str(url).startswith("https://"):
            continue
        image = await client.get(url)
        if image.status_code == 200 and (image.content[:4] == b"\x89PNG" or image.content[:3] == b"\xff\xd8\xff"):
            encoded = base64.b64encode(image.content).decode()
            screenshot_b64 = encoded if len(encoded) <= MAX_SCREENSHOT_BASE64 else None
        break
    crash_log = None
    if event.kind == CRASH:
        log = await client.get(f"{ASC_API}/v1/{event.kind}/{event.submission_id}/crashLog", headers=headers)
        if log.status_code == 200:
            text = ((log.json().get("data") or {}).get("attributes") or {}).get("logText") or ""
            crash_log = text[:MAX_CRASH_LOG_CHARS] or None
    return {"attributes": attributes, "screenshot_base64": screenshot_b64, "crash_log": crash_log}


def bug_report_fields(event: FeedbackEvent, fetched: dict) -> dict:
    """The ``BugReport`` columns for one TestFlight submission."""
    a = fetched.get("attributes") or {}
    comment = (a.get("comment") or "").strip()
    if event.kind == CRASH:
        description = f"TestFlight crash: {comment}" if comment else "TestFlight crash (no comment)"
    else:
        description = comment or None
    platform = a.get("devicePlatform") or a.get("appPlatform") or "iOS"
    app_state = {
        "source": "testflight",
        "testflight_kind": "crash" if event.kind == CRASH else "screenshot",
        "testflight_submission_id": event.submission_id,
        "platform": f"{platform} (TestFlight)",
        "device_model": a.get("deviceModel") or "?",
        "os_version": a.get("osVersion") or "?",
        "current_page": "TestFlight feedback",
        "network": a.get("connectionType") or "?",
        "submitted_at": a.get("createdDate"),
        "locale": a.get("locale"),
        "app_uptime_ms": a.get("appUptimeInMilliseconds"),
        "paired_apple_watch": a.get("pairedAppleWatch"),
    }
    if fetched.get("crash_log"):
        app_state["crash_log"] = fetched["crash_log"]
    return {
        "user_email": (a.get("email") or None),
        "session_id": session_key(event),
        "description": description[:5000] if description else None,
        "screenshot_base64": fetched.get("screenshot_base64"),
        "app_state": {k: v for k, v in app_state.items() if v is not None},
        "category": "ios",
    }
