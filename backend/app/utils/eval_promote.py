"""Eval-promote (#222): the bounded, kill-switchable, expiring human steer that an
Accept/Reject verdict applies to Discover ranking.

This is the first time a human tap moves live ranking, so every knob is a safety
knob:

* **Bounded** — the applied ± term is clamped to ``EVAL_ADJ_CAP`` (blend-cap
  pattern), applied to BOTH the display score and the ordering ``_rank_score``.
* **Expiring** — verdicts older than ``EVAL_PROMOTE_TTL_DAYS`` decay: a stale
  judgment stops steering ranking (``ttl_cutoff``).
* **Kill-switchable** — the Redis flag ``EVAL_PROMOTE_ENABLED_KEY`` zeroes ALL
  applied terms at once. It fails **open** (absent/unreadable => enabled) so a
  Redis blip never silently drops human steers; it only disengages on an
  explicit off token.

Kept import-light on purpose (no app imports) so it is safe to import from
``routes/feed.py``, the admin endpoints, and the cockpit alike.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Redis kill switch. Fail-open: only an explicit off token disables applying.
EVAL_PROMOTE_ENABLED_KEY = "eval_promote:enabled"

# Bounded magnitudes (blend-cap pattern). Preserve the historical nudge sizes
# that shipped before #222 so this change is behavior-preserving when enabled.
EVAL_PROMOTE_ADJ = 8  # accepted_promote (exact scope)
EVAL_DOWNRANK_EXACT = 18  # accepted_downrank (exact scope)
EVAL_DOWNRANK_FAMILY = 12  # accepted_downrank (family scope)

# Hard cap: the applied |adjustment| may never exceed this, no matter what a
# per-row stored magnitude claims. The human-in-the-ranking-loop guardrail.
EVAL_ADJ_CAP = 20

# 14-day TTL: verdicts older than this stop steering ranking.
EVAL_PROMOTE_TTL_DAYS = 14

# The verdict rows that carry a live applied boost (what the feed consumes and
# the cockpit counts).
APPLIED_DECISIONS = ("accepted_promote", "accepted_downrank")

_DISABLED_TOKENS = {"0", "false", "off", "no", "disabled"}


def _coerce(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode()
        except Exception:
            return ""
    return str(raw).strip().lower()


def is_enabled_value(raw) -> bool:
    """Interpret a raw Redis flag value. Fail-open: enabled unless an explicit
    off token (``0``/``false``/``off``/``no``/``disabled``)."""
    return _coerce(raw) not in _DISABLED_TOKENS


def clamp_adj(adj: float) -> float:
    """Clamp an adjustment to ``±EVAL_ADJ_CAP``."""
    if adj > EVAL_ADJ_CAP:
        return float(EVAL_ADJ_CAP)
    if adj < -EVAL_ADJ_CAP:
        return float(-EVAL_ADJ_CAP)
    return float(adj)


def ttl_cutoff(now: datetime | None = None) -> datetime:
    """The oldest ``created_at`` a verdict may have and still steer ranking."""
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=EVAL_PROMOTE_TTL_DAYS)
