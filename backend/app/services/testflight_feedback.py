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
import io
import logging
import os
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

#: Ruling 249-A: one vision description per TestFlight report, capped per UTC day.
MAX_DAILY_SCREENSHOT_SUMMARIES = 25
SCREENSHOT_SUMMARY_DAILY_CAP_ENV = "TESTFLIGHT_SCREENSHOT_SUMMARY_DAILY_CAP"
SCREENSHOT_SUMMARY_TIMEOUT_SECONDS = 8.0
SCREENSHOT_SUMMARY_MAX_OUTPUT_TOKENS = 220
SCREENSHOT_SUMMARY_MAX_EDGE = 1024
SCREENSHOT_SUMMARY_MAX_CHARS = 1200
_SUMMARY_CAP_KEY_PREFIX = "bainluck:tf_screenshot_summary"
_SUMMARY_CAP_TTL_S = 48 * 3600

_CLAIM_DAILY_SLOT_LUA = """
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
if cur >= tonumber(ARGV[1]) then
  return 0
end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_MENTION_RE = re.compile(r"@(?=[A-Za-z0-9])")
_PHONE_RE = re.compile(
    r"(?<!\w)(?:"
    r"\+\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]\d{3,4}[\s.-]\d{3,4}"
    r"|\(\d{3}\)[\s.-]?\d{3}[\s.-]\d{4}"
    r"|\b1?[\s.-]?\d{3}[\s.-]\d{3}[\s.-]\d{4}\b"
    r")(?!\w)"
)

_SCREENSHOT_SUMMARY_SYSTEM_PROMPT = (
    "You describe screenshots of the Bain Luck iOS app for engineering bug reports. "
    "Describe ONLY the Bain Luck interface: "
    "(1) which screen or tab is open, "
    "(2) visible team names, market titles, scores, probabilities, and column headers inside Bain Luck, and "
    "(3) any visible layout, formatting, clipping, overlap, color, or data defects. "
    "Never mention anything outside the Bain Luck interface: ignore the iOS Lock Screen wallpaper, "
    "notifications, status bar (time, carrier, Wi-Fi, battery), system indicators, keyboard, "
    "and any personal details (names, email addresses, phone numbers, social handles). "
    "Keep it factual and concise: at most 5 short bullet points, plain English."
)

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


def compress_screenshot_if_needed(
    raw_bytes: bytes,
    *,
    max_b64_len: int = MAX_SCREENSHOT_BASE64,
) -> Optional[str]:
    """Encode a PNG or JPEG screenshot within ``max_b64_len`` base64 characters.

    Valid screenshots that already fit keep their original bytes. Oversized
    PNG/JPEG screenshots (such as full-resolution 3x Retina PNGs from TestFlight)
    are re-encoded to JPEG with stepped max-edge/quality ceilings rather than
    silently dropped.
    """
    if not raw_bytes or not (raw_bytes[:4] == b"\x89PNG" or raw_bytes[:3] == b"\xff\xd8\xff"):
        return None
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    if len(encoded) <= max_b64_len:
        return encoded

    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.warning("Pillow unavailable; dropping oversized TestFlight screenshot (%d b64 chars)", len(encoded))
        return None

    try:
        with Image.open(io.BytesIO(raw_bytes)) as opened:
            base_img = ImageOps.exif_transpose(opened).convert("RGB")
    except Exception as exc:
        logger.warning("Failed to decode oversized TestFlight screenshot: %s", exc)
        return None

    for max_edge, quality in ((1600, 82), (1280, 75), (1024, 68), (800, 58)):
        candidate = base_img.copy()
        candidate.thumbnail((max_edge, max_edge))
        buf = io.BytesIO()
        candidate.save(buf, format="JPEG", quality=quality, optimize=True)
        jpeg_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        if len(jpeg_b64) <= max_b64_len:
            logger.info(
                "Compressed oversized TestFlight screenshot (%d -> %d b64 chars, max_edge=%d, q=%d)",
                len(encoded), len(jpeg_b64), max_edge, quality,
            )
            return jpeg_b64

    logger.warning("TestFlight screenshot still exceeds %d b64 chars after compression", max_b64_len)
    return None


def strip_emails_and_phones(text: str) -> str:
    """Remove email addresses and phone numbers, and break GitHub @mentions (249-A)."""
    if not text:
        return ""
    cleaned = _EMAIL_RE.sub("[redacted email]", text)
    cleaned = _PHONE_RE.sub("[redacted phone]", cleaned)
    cleaned = _MENTION_RE.sub("@ ", cleaned)
    return cleaned.strip()


def _prepare_vision_jpeg_b64(screenshot_b64: str) -> Optional[str]:
    """Downscale a stored screenshot to a compact JPEG for fast, bounded vision calls."""
    try:
        raw = base64.b64decode(screenshot_b64)
    except Exception:
        return None
    if not (raw[:4] == b"\x89PNG" or raw[:3] == b"\xff\xd8\xff"):
        return None
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(raw)) as opened:
            img = ImageOps.exif_transpose(opened).convert("RGB")
        img.thumbnail((SCREENSHOT_SUMMARY_MAX_EDGE, SCREENSHOT_SUMMARY_MAX_EDGE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=72, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:
        logger.warning("Failed to resize screenshot for vision summary: %s", exc)
        return None


def _daily_summary_cap(explicit: Optional[int] = None) -> int:
    if explicit is not None:
        return max(0, min(int(explicit), 100))
    raw = os.getenv(SCREENSHOT_SUMMARY_DAILY_CAP_ENV)
    if raw is None or not raw.strip():
        return MAX_DAILY_SCREENSHOT_SUMMARIES
    try:
        return max(0, min(int(raw.strip()), 100))
    except ValueError:
        return MAX_DAILY_SCREENSHOT_SUMMARIES


def _claim_daily_summary_slot(day: str, cap: int, redis_client: Any = None) -> bool:
    """Atomically claim one slot against the per-day TestFlight screenshot summary cap."""
    if cap <= 0:
        return False
    try:
        client = redis_client
        if client is None:
            from app.tasks.redis_state import get_redis_client
            client = get_redis_client()
        key = f"{_SUMMARY_CAP_KEY_PREFIX}:{day}"
        script = client.register_script(_CLAIM_DAILY_SLOT_LUA)
        return bool(script(keys=[key], args=[cap, _SUMMARY_CAP_TTL_S], client=client))
    except Exception as exc:
        logger.warning("TestFlight screenshot summary daily cap check failed (skipping): %s", exc)
        return False


def summarize_testflight_screenshot(
    screenshot_b64: Optional[str],
    *,
    report_id: int,
    client: Any = None,
    redis_client: Any = None,
    daily_cap: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Describe the Bain Luck screen in a TestFlight screenshot (ruling 249-A).

    - Uses ``complete_chat_detailed("testflight_screenshot_summary", ...)`` so the
      model, request shape, pricing, and shared budget come solely from
      ``app.services.llm_models`` / ``app.services.llm_request``.
    - Enforces one call per report and a per-UTC-day cap (default 25/day).
    - Strips emails and phone numbers in code after the model returns.
    - Logs the model and USD cost of every completed call.
    - Returns ``None`` on any failure, timeout, refusal, or cap hit so issue
      filing never waits or fails.
    """
    if not screenshot_b64:
        return None

    try:
        if client is None:
            api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
            if not api_key:
                logger.info("OPENAI_API_KEY unset — skipping screenshot summary for report #%d", report_id)
                return None

        cap = _daily_summary_cap(daily_cap)
        day = (now or datetime.now(timezone.utc)).date().isoformat()
        if not _claim_daily_summary_slot(day, cap, redis_client=redis_client):
            logger.info(
                "TestFlight screenshot summary daily cap (%d) reached or unavailable — skipping report #%d",
                cap, report_id,
            )
            return None

        vision_b64 = _prepare_vision_jpeg_b64(screenshot_b64)
        if not vision_b64:
            return None

        if client is None:
            import openai
            client = openai.OpenAI(
                api_key=api_key,
                timeout=SCREENSHOT_SUMMARY_TIMEOUT_SECONDS,
                max_retries=0,
            )

        from app.services.llm_request import complete_chat_detailed

        messages = [
            {"role": "system", "content": _SCREENSHOT_SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe only the Bain Luck screen, its visible names/numbers, and any visible defects.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{vision_b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ]

        result = complete_chat_detailed(
            "testflight_screenshot_summary",
            client,
            messages=messages,
            max_output_tokens=SCREENSHOT_SUMMARY_MAX_OUTPUT_TOKENS,
            temperature=0.0,
            max_retries=0,
        )
        cost_str = f"${result.cost_usd:.6f}" if result.cost_usd is not None else "unknown"
        logger.info(
            "TestFlight screenshot summary completed for report #%d (model=%s cost_usd=%s)",
            report_id, result.model, cost_str,
        )
        choices = getattr(result.response, "choices", None) or []
        raw_text = getattr(getattr(choices[0], "message", None), "content", None) if choices else None
        if not isinstance(raw_text, str):
            return None
        cleaned = strip_emails_and_phones(raw_text)
        if not cleaned:
            return None
        return cleaned[:SCREENSHOT_SUMMARY_MAX_CHARS]
    except Exception as exc:
        logger.warning("TestFlight screenshot summary skipped for report #%d: %s", report_id, exc)
        return None


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
        if image.status_code == 200:
            screenshot_b64 = compress_screenshot_if_needed(image.content)
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
