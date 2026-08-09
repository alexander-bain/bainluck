"""Freshness policy for the external-curator (social) ground-truth corpus.

Pure logic — no I/O, no DB, no imports from ``app.routes``/``app.tasks`` — so both
the Discover recall lane (``routes/feed.py``) and the admin status endpoint
(``routes/admin_engagement.py``) can state the SAME policy instead of each
deciding for itself what "stale" means.

Why this file exists (UX-P028, from the UX-P027 consumption census):

The accepted rows in ``external_curator_ground_truth_items`` feed a live Discover
lane — ``_external_curator_recall_market_ids`` — which both seeds the candidate
pool AND grants matched markets ``_EXTERNAL_CURATOR_RECALL_SCORE_BONUS`` (+25) on
the ranking score. The lane had no age bound at all: it ordered by
``imported_at desc`` and used whatever it found, forever.

That is the failure class this codebase keeps re-learning — a mechanism that is
perfectly healthy while the signal behind it is gone, and nothing says so. The
producing pipeline stopped, and the lane went on boosting Discover rank from a
corpus that had stopped aging months earlier, silently.

So staleness is a STATED policy here, not an accident of whatever rows happen to
be in the table:

* a corpus fresher than ``RECALL_MAX_AGE_DAYS`` is ``current`` and is used;
* an older one is ``stale`` and is NOT used — no recall, no rank bonus;
* no rows at all is ``empty``; an unreadable/absent timestamp is ``unknown``.

``stale``/``empty``/``unknown`` all fail CLOSED (the lane contributes nothing and
the pool is simply smaller). That was already the de-facto behaviour for an empty
table; making it the deliberate answer for a stale one is the point.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Two weeks. The producer's cadence is daily, so this absorbs a long outage
# without ever letting a months-old corpus steer today's landing page. It is
# deliberately generous: the bound exists to catch a DEAD producer, not to
# punish a slow one.
RECALL_MAX_AGE_DAYS = 14

CORPUS_CURRENT = "current"
CORPUS_STALE = "stale"
CORPUS_EMPTY = "empty"
CORPUS_UNKNOWN = "unknown"


def recall_cutoff(now: datetime, *, max_age_days: int = RECALL_MAX_AGE_DAYS) -> datetime:
    """The oldest ``imported_at`` the recall lane may still use."""
    return now - timedelta(days=max_age_days)


def _as_utc(value: Any) -> Optional[datetime]:
    """Coerce a timestamp to tz-aware UTC, or ``None`` if it isn't one.

    Naive datetimes are read as UTC: every writer of this column stores UTC, and
    treating a naive value as local time would shift the age by the reader's
    offset — the same class of bug as gotcha #44.
    """
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def corpus_age_days(latest_imported_at: Any, now: datetime) -> Optional[float]:
    """Age in days of the newest imported row, or ``None`` if unknowable."""
    latest = _as_utc(latest_imported_at)
    if latest is None:
        return None
    return (now - latest).total_seconds() / 86400.0


def classify_corpus(
    latest_imported_at: Any,
    now: datetime,
    *,
    row_count: Optional[int] = None,
    max_age_days: int = RECALL_MAX_AGE_DAYS,
) -> dict[str, Any]:
    """Classify the corpus as current / stale / empty / unknown.

    Returns the shape the admin status endpoint publishes, so an operator can
    tell "the lane is healthy" from "the lane is quietly running on a fossil"
    without reading the code.
    """
    if row_count is not None and row_count <= 0:
        return {
            "state": CORPUS_EMPTY,
            "usable": False,
            "age_days": None,
            "latest_imported_at": None,
            "max_age_days": max_age_days,
            "reason": "No reviewed external-curator rows are present.",
        }

    age_days = corpus_age_days(latest_imported_at, now)
    if age_days is None:
        return {
            "state": CORPUS_UNKNOWN,
            "usable": False,
            "age_days": None,
            "latest_imported_at": None,
            "max_age_days": max_age_days,
            "reason": "No usable import timestamp; the corpus age cannot be established.",
        }

    latest = _as_utc(latest_imported_at)
    stale = age_days > max_age_days
    return {
        "state": CORPUS_STALE if stale else CORPUS_CURRENT,
        "usable": not stale,
        "age_days": round(age_days, 2),
        "latest_imported_at": latest.isoformat() if latest else None,
        "max_age_days": max_age_days,
        "reason": (
            f"Newest reviewed row is {age_days:.1f} days old, past the "
            f"{max_age_days}-day recall bound; the lane is contributing nothing."
            if stale
            else f"Newest reviewed row is {age_days:.1f} days old."
        ),
    }
