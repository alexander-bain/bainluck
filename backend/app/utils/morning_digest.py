"""Morning Digest content selection + rendering (pure, DB-free, testable).

Queue #200, Item 2. The digest is the PRD's ratified notifications v1: a single
daily push naming the 3-5 most *interesting* probabilities of the day. It reuses
the Discover interestingness scores as the content brain — this module only
ranks, dedups, and renders candidate rows that the task layer has already
gathered (so it stays a pure function with no DB/Redis/network deps and can be
unit-tested directly).

Deliberately out of v1 scope (Alex's ruling): streaks, movers, resolutions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.utils.market_staleness import is_title_implied_stale


# Max digest items in a single push. iOS shows ~4-5 lines expanded.
DEFAULT_DIGEST_LIMIT = 5
# No more than this many items from one category, so a busy category (e.g. a
# politics-heavy day) can't crowd out the rest of the world.
MAX_PER_CATEGORY = 2
# A near-certain leader (e.g. "Spain 100% to reach the final") is the opposite of
# interesting — usually an illiquid single-source extreme. Drop it from a digest
# whose whole promise is "the most interesting odds".
MAX_LEADER_PROB = 0.97


@dataclass
class DigestCandidate:
    """One rankable probability for the digest.

    ``interestingness`` is the cached Discover interestingness score (0-100);
    rows with no cached score arrive as 0.0 and sort to the bottom.
    """

    market_id: int
    name: str
    leader_name: str
    leader_prob: float  # 0-1 scale
    interestingness: float = 0.0
    volume_24h: float | None = None
    category: str | None = None
    dedup_key: str | None = None  # canonical_market_key / group_id / falls back to name


@dataclass
class DigestPayload:
    """Rendered push payload + the items it was built from (for admin preview)."""

    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)
    items: list[dict] = field(default_factory=list)


def is_stale_dated_bucket(
    candidate: DigestCandidate, now: datetime
) -> str | None:
    """Reuse the feed's staleness classifier to reject a stale-dated bucket.

    Returns a stale-reason string if the market's *title* implies its real-world
    window has already passed, else ``None``. This is the digest's guard against
    featuring what the feed itself drops — the "one content brain" rule — and it
    reuses (never forks) ``is_title_implied_stale``, the same helper the feed
    applies at serving time (``routes/feed.py``).

    It closes the exact self-caught gap: "a May-dated bucket can never rank into
    a July digest." The candidate SQL pool only drops a *past
    ``resolution_date``*, but Kalshi's settlement date for a month-named market
    lands ~2 weeks INTO the next month (gotcha #883), so a stale month-bucket
    ("… in May 2026") slips through the query with a future ``resolution_date``
    and must be caught here by title inference.
    """
    return is_title_implied_stale(candidate.name, candidate.category, now)


def select_digest_candidates(
    candidates: list[DigestCandidate],
    *,
    limit: int = DEFAULT_DIGEST_LIMIT,
    max_per_category: int = MAX_PER_CATEGORY,
    max_leader_prob: float = MAX_LEADER_PROB,
    category_affinities: dict[str, float] | None = None,
    now: datetime | None = None,
) -> list[DigestCandidate]:
    """Rank candidates by interestingness, dedup, and cap per category.

    ``category_affinities`` (optional) is a small per-user boost map, e.g.
    ``{"politics": 0.3}`` — applied as a multiplicative uplift to the
    interestingness score so a signed-in user's leanings tilt selection without
    a separate content pipeline (one content brain). Absent → global ranking,
    which is the v1 dogfood path.

    ``now`` (optional) turns on the feed's dated-bucket staleness suppression via
    :func:`is_stale_dated_bucket`. The task layer always passes the current time;
    pure unit tests can pass a fixed ``now`` or omit it. When omitted, no
    time-dependent filtering runs (kept opt-in so the ranker stays pure).
    """
    affinities = category_affinities or {}

    def _rank(c: DigestCandidate) -> float:
        score = c.interestingness
        if c.category and c.category in affinities:
            # Bounded uplift: affinity in roughly [-1, 1] nudges by up to ~30%.
            score *= 1.0 + max(-0.5, min(0.5, affinities[c.category])) * 0.6
        return score

    eligible = [
        c
        for c in candidates
        if c.leader_prob < max_leader_prob
        and not (now is not None and is_stale_dated_bucket(c, now))
    ]
    ordered = sorted(
        eligible,
        key=lambda c: (_rank(c), c.volume_24h or 0.0),
        reverse=True,
    )

    picked: list[DigestCandidate] = []
    seen_keys: set[str] = set()
    per_category: dict[str, int] = {}
    for c in ordered:
        key = c.dedup_key or c.name
        if key in seen_keys:
            continue
        # Cap only real categories — uncategorized items are not one bucket and
        # must not be starved out of the digest.
        if c.category and per_category.get(c.category, 0) >= max_per_category:
            continue
        seen_keys.add(key)
        if c.category:
            per_category[c.category] = per_category.get(c.category, 0) + 1
        picked.append(c)
        if len(picked) >= limit:
            break
    return picked


def _shorten(text: str, max_len: int = 70) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _pct(prob: float) -> int:
    return int(round(max(0.0, min(1.0, prob)) * 100))


def render_digest_payload(items: list[DigestCandidate]) -> DigestPayload:
    """Render selected candidates into an APNS/FCM push payload.

    Title is a fixed brand hook; body lists each probability as
    ``Leader NN% — question`` on its own line. Data carries a deep link to the
    top item so a tap lands somewhere useful.
    """
    title = "\U0001f340 Today's most interesting odds"
    lines: list[str] = []
    rendered_items: list[dict] = []
    for c in items:
        pct = _pct(c.leader_prob)
        leader = _shorten(c.leader_name, 24)
        question = _shorten(c.name, 60)
        lines.append(f"{leader} {pct}% — {question}")
        rendered_items.append(
            {
                "market_id": c.market_id,
                "name": c.name,
                "leader": c.leader_name,
                "probability": round(c.leader_prob, 4),
                "interestingness": round(c.interestingness, 1),
                "category": c.category,
            }
        )

    body = "\n".join(lines) if lines else "No standout probabilities today."
    data: dict[str, str] = {"type": "morning_digest", "url": "/discover"}
    if items:
        data["market_id"] = str(items[0].market_id)
        data["url"] = f"/futures/{items[0].market_id}"

    return DigestPayload(title=title, body=body, data=data, items=rendered_items)
