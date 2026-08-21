"""Morning Digest task (Queue #200, Item 2) — the PRD notifications v1.

Once daily (~7 AM PT), select the 3-5 most interesting probabilities and push a
single digest to opted-in device tokens. Content selection reuses the Discover
interestingness scores already cached in Redis by ``precompute_interestingness``
— one content brain, and a cheap read path (no LLM, no scoring on the send
path; gotcha #39: Redis access is routed through the bounded ``get_redis_client``).

Opt-in model: a device's user must have ``push_preferences["morning_digest"] is
True`` (explicit opt-in — unlike daily_challenge/big_moves which are opt-out).
This keeps v1 a dogfood surface (Alex first) rather than a broadcast.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select, update as sa_update

from app.models.models import DeviceToken, FuturesMarket, FuturesOutcome, User
from app.utils.feed_market_quality import classify_market_quality
from app.utils.morning_digest import (
    DEFAULT_DIGEST_LIMIT,
    DigestCandidate,
    render_digest_payload,
    select_digest_candidates,
)

logger = logging.getLogger(__name__)

# Cheap upper bound on the candidate query — we rank the highest-volume open
# markets by their cached interestingness. A once-daily bounded sort.
CANDIDATE_POOL_SIZE = 400

# The only token kind FCM can actually send to (Queue 311 A1 / #1159).
SENDABLE_TOKEN_KIND = "fcm"


def token_kind_of(device_token_row) -> str:
    """The row's token kind, with absence resolved to ``"apns"``.

    Absence is not ambiguity here: every row written before Queue 311 was a raw
    APNS hex, so an unset kind has exactly one correct reading. Resolving it to
    the UNSENDABLE value is also the safe direction — mislabelling an APNS row
    as ``fcm`` hands garbage to the sender, while the reverse merely skips it.

    Read via ``__dict__`` rather than ``getattr``: on a partially-loaded ORM row
    ``getattr`` would trigger a lazy load, which raises in an async context
    (the ORM-lazy-load trap this codebase has hit before).
    """
    return device_token_row.__dict__.get("token_kind") or "apns"


def is_sendable_via_fcm(device_token_row) -> bool:
    """Whether this row holds a token ``messaging.send()`` can accept."""
    return token_kind_of(device_token_row) == SENDABLE_TOKEN_KIND


def digest_recipients(rows) -> list[tuple[int | None, str]]:
    """Resolve ``(device_row_id, token)`` recipients from ``(DeviceToken, User)`` rows.

    Two independent gates, both required:

    1. **Sendability** — the row must hold an FCM registration token. The
       broadcast query already filters this server-side; repeating it here is
       deliberate defense in depth, because the failure mode is not a missing
       notification. ``_send_fcm_message`` raises ``_InvalidTokenError`` on an
       APNS hex, and the caller's handler responds by setting ``is_active =
       False`` — so a broadcast that leaked APNS rows would walk the table
       deactivating real devices. That is destructive enough to be worth
       checking twice, and this half is the half a unit test can reach.
    2. **Opt-in** — the device's user must have explicitly opted in.
    """
    out: list[tuple[int | None, str]] = []
    for device_token, user in rows:
        if not is_sendable_via_fcm(device_token):
            continue
        prefs = user.push_preferences if (user and isinstance(user.push_preferences, dict)) else {}
        if prefs.get("morning_digest", False) is True:
            out.append((device_token.id, device_token.device_token))
    return out


def admin_digest_tokens(rows) -> set[str]:
    """Which of those recipient tokens belong to an admin (#2060 item 6).

    ── A SEPARATE FUNCTION RATHER THAN A THIRD TUPLE SLOT ───────────────────────

    ``digest_recipients`` could have returned ``(id, token, is_admin)``, and that
    would have changed the arity of a function whose both-directions tests are the
    guard on a DESTRUCTIVE path — an APNS hex reaching FCM makes the caller
    deactivate real devices. Widening it would have rewritten six assertions on
    that guard to add a field none of them are about. This composes instead, and
    those tests keep asserting exactly what they asserted before.

    ** THE ADMIN SET IS THE SAME ONE THE ADMIN ROUTES USE. ** Imported from
    ``admin_utils`` rather than re-read from the environment here: a second
    reading of ``ADMIN_USER_IDS`` is a second definition of who Alex is, and the
    one that decides who gets told to go labelling would be free to drift from
    the one that decides who is allowed to.
    """
    from app.routes.admin_utils import _admin_user_emails, _admin_user_ids

    admin_ids = _admin_user_ids()
    admin_emails = _admin_user_emails()

    tokens: set[str] = set()
    for device_token, user in rows:
        if user is None:
            continue
        if user.id in admin_ids or (user.email or "").lower() in admin_emails:
            tokens.add(device_token.device_token)
    return tokens


async def _gather_digest_candidates(session, redis, *, pool_size=CANDIDATE_POOL_SIZE) -> list[DigestCandidate]:
    """Cheap read: top-volume feed-eligible markets + their cached interestingness."""
    now = datetime.now(timezone.utc)
    from sqlalchemy.orm import load_only, selectinload

    result = await session.execute(
        select(FuturesMarket)
        .options(
            load_only(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.llm_sport_category,
                FuturesMarket.canonical_market_key,
                FuturesMarket.group_id,
                FuturesMarket.volume_24h,
                FuturesMarket.external_id,
            ),
            selectinload(FuturesMarket.outcomes).load_only(
                FuturesOutcome.name,
                FuturesOutcome.current_probability,
            ),
        )
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now,
            ),
            FuturesMarket.volume_24h.isnot(None),
        )
        .order_by(FuturesMarket.volume_24h.desc())
        .limit(pool_size)
    )
    markets = result.scalars().unique().all()
    if not markets:
        return []

    # Batch-read cached interestingness scores (one MGET, no per-market round trips).
    keys = [f"interestingness:{m.id}" for m in markets]
    scores: dict[int, float] = {}
    try:
        raws = redis.mget(keys)
        for m, raw in zip(markets, raws):
            if not raw:
                continue
            try:
                scores[m.id] = float(json.loads(raw).get("score", 0.0))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    except Exception:
        logger.warning("Digest interestingness MGET failed — ranking by volume only", exc_info=True)

    candidates: list[DigestCandidate] = []
    for m in markets:
        # Full feed-parity quality gate: the digest must never surface a market
        # the Discover feed itself would suppress (boring ladders/buckets, social
        # filler, margin/turnout, weak explanation cards). Mirror feed.py's
        # ``classify_market_quality`` call and drop the ``suppress`` class. Status
        # is always "open" here (guaranteed by the query WHERE) — R6 resolved-sports
        # suppression is a no-op but we pass it for exact parity.
        quality = classify_market_quality(
            market_name=m.name,
            sport_category=m.llm_sport_category,
            outcome_names=[o.name for o in m.outcomes if o.name],
            external_id=m.external_id,
            status="open",
        )
        if quality.quality_class == "suppress":
            continue

        leader_name = None
        leader_prob = None
        for o in m.outcomes:
            if o.current_probability is None:
                continue
            prob = float(o.current_probability)
            if leader_prob is None or prob > leader_prob:
                leader_prob = prob
                leader_name = o.name
        if leader_name is None or leader_prob is None:
            continue
        candidates.append(
            DigestCandidate(
                market_id=m.id,
                name=m.name,
                leader_name=leader_name,
                leader_prob=leader_prob,
                interestingness=scores.get(m.id, 0.0),
                volume_24h=float(m.volume_24h) if m.volume_24h is not None else None,
                category=m.llm_sport_category,
                dedup_key=m.canonical_market_key or m.group_id or m.name,
            )
        )
    return candidates


async def _run_morning_digest(
    *,
    dry_run: bool = False,
    target_token: str | None = None,
    limit: int = DEFAULT_DIGEST_LIMIT,
) -> dict:
    """Build the digest and send it to opted-in tokens.

    - ``dry_run=True``: build + return payload, send nothing (admin preview).
    - ``target_token`` set: send only to that token, bypassing opt-in
      (dogfood/test send for a specific device).
    - otherwise: send to every active token whose user opted in via
      ``push_preferences["morning_digest"] is True``.
    """
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    redis = get_redis_client()

    async with get_task_session() as db:
        candidates = await _gather_digest_candidates(db, redis)
        # Pass now so the feed's dated-bucket/quality suppression runs — a market
        # whose title implies a past month (Kalshi settlement lands in the next
        # month, gotcha #883) must never rank into today's digest.
        now = datetime.now(timezone.utc)
        selected = select_digest_candidates(candidates, limit=limit, now=now)
        # Campaign id for the digest funnel (measurement_spec.md §2): one per daily
        # send, carried in the deep link (utm_campaign) + FCM data.payload_id so
        # push_opened/card_engaged join back to the server-side push_sent.
        payload_id = f"digest-{now:%Y%m%d}"
        payload = render_digest_payload(selected, payload_id=payload_id)

        summary: dict = {
            "status": "ok",
            "dry_run": dry_run,
            "candidates": len(candidates),
            "selected": len(selected),
            "title": payload.title,
            "body": payload.body,
            "items": payload.items,
        }

        if dry_run:
            return summary

        if not selected:
            summary["status"] = "no_content"
            summary["sent"] = 0
            return summary

        # Resolve the recipient token set. `admin_tokens` is initialised here
        # rather than in the broadcast branch: the `target_token` path skips that
        # branch entirely, and a name bound in only one arm of an if/else is an
        # UnboundLocalError on the other (gotcha #7's shape).
        admin_tokens: set[str] = set()
        if target_token:
            recipient_tokens = [(None, target_token)]  # (device_row_id, token)
        else:
            # `token_kind == "fcm"` is load-bearing, not hygiene (Queue 311 A1 /
            # #1159). Every row predating the FCM client is a raw APNS hex that
            # `_send_fcm_message` rejects with `_InvalidTokenError` — and the
            # handler below deactivates the row on that error. So an unfiltered
            # broadcast would not merely be noisy: it would walk the table
            # switching off real devices. Broadcast must never hand an APNS hex
            # to FCM.
            rows = await db.execute(
                select(DeviceToken, User)
                .outerjoin(User, DeviceToken.user_id == User.id)
                .where(DeviceToken.is_active.is_(True))
                .where(DeviceToken.token_kind == SENDABLE_TOKEN_KIND)
            )
            fetched = rows.all()
            recipient_tokens = digest_recipients(fetched)
            admin_tokens = admin_digest_tokens(fetched)

        # ── THE ADMIN VARIANT (#2060 item 6) ─────────────────────────────────
        #
        # Built ONCE, outside the loop, and selected per recipient. The digest is
        # a broadcast of a single payload, so the labelling nudge has to be a
        # second payload or it goes to everybody.
        #
        # `target_token` deliberately does NOT get it: that path is a dogfood
        # send to a named device and bypasses opt-in entirely, so it has no user
        # attached to check. Sending the admin variant there would be guessing.
        admin_payload = (
            render_digest_payload(selected, payload_id=payload_id, labeling_reminder=True)
            if admin_tokens
            else payload
        )
        summary["admin_recipients"] = len(admin_tokens)

        sent, failed = 0, 0
        from app.tasks.push_notifications import _InvalidTokenError, _send_fcm_message

        for device_row_id, token in recipient_tokens:
            outgoing = admin_payload if token in admin_tokens else payload
            try:
                _send_fcm_message(
                    token=token,
                    title=outgoing.title,
                    body=outgoing.body,
                    data=outgoing.data,
                )
                sent += 1
            except _InvalidTokenError:
                if device_row_id is not None:
                    await db.execute(
                        sa_update(DeviceToken)
                        .where(DeviceToken.id == device_row_id)
                        .values(is_active=False)
                    )
                failed += 1
            except Exception as exc:
                logger.warning("Morning digest send failed to %s...: %s", token[:8], exc)
                failed += 1

        summary["recipients"] = len(recipient_tokens)
        summary["sent"] = sent
        summary["failed"] = failed
        summary["payload_id"] = payload_id

        # Digest funnel step 1 (measurement_spec.md §2): emit push_sent server-side
        # so the 7:05 send is measurable from day one. Best-effort — never blocks
        # or fails the send if GA is slow / the MP secret isn't set yet.
        if sent > 0:
            from app.utils.measurement import emit_ga4_event

            summary["push_sent_emitted"] = await emit_ga4_event(
                "push_sent",
                {
                    "payload_id": payload_id,
                    "surface": "digest",
                    "recipients": sent,
                    "items": len(selected),
                    "top_market_id": str(selected[0].market_id) if selected else "",
                },
            )

    logger.info(
        "Morning digest (%s): candidates=%d selected=%d sent=%d failed=%d",
        "dry_run" if dry_run else ("target" if target_token else "broadcast"),
        len(candidates),
        len(selected),
        summary.get("sent", 0),
        summary.get("failed", 0),
    )
    return summary
