"""Reviewer tiers for ``ranking_judgments`` (Queue 311 Item B1 / #1170, #1542).

WHY THIS EXISTS
---------------
``ranking_judgments`` rows are not inert opinions. They feed the daily eval beat
that computes ``tapworthy_at_k`` / ``boring_rate_at_k`` / ``bad_image_rate_at_k``,
they feed the holdout export, and through the eval-promote path they steer LIVE
Discover ranking. Every row in the table today is Alex's.

``/play`` is about to hand a labelling surface to an 8-year-old and a 13-year-old.
Without a tier, their taps would land in the same pool and be indistinguishable
from the curator's — and the pool is small enough that this is not a rounding
error: the labelled corpus is ~24 rows with a single positive. A handful of kid
rows would not skew those metrics, they would dominate them. The gate is not
proportionate to the kids' volume; it is proportionate to the corpus's smallness.

THE TWO RULES
-------------
1. **Absent means ``alex``.** Existing rows carry no tier key and are all the
   curator's, so absence has exactly one correct reading. It is encoded here,
   once, rather than at each of the eight call sites — the version of this that
   gets re-derived per consumer is the version where one consumer gets it wrong.

2. **Consumers deny by default.** Every reader defaults to the gold tier and has
   to ASK for anything wider. The filters this replaces were all shaped
   ``reviewer: str | None = None`` → no filter when None, which is the same
   fail-open shape as the analytics consent gate one queue earlier: a filter
   that exists, is correct when used, and is off unless someone remembers.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_

from app.models.models import RankingJudgment

#: The curator. The only tier that counts toward gold metrics.
TIER_ALEX = "alex"
#: A kid-facing ``/play`` task. Quarantined: never counts toward gold metrics.
TIER_KID = "kid"
#: A machine proposal. Advisory until a human promotes it.
TIER_LLM = "llm"

VALID_TIERS = frozenset({TIER_ALEX, TIER_KID, TIER_LLM})

#: Absence resolves here. See rule 1 above.
DEFAULT_TIER = TIER_ALEX

#: The tiers that may move a published metric.
GOLD_TIERS = frozenset({TIER_ALEX})

#: The JSONB key inside ``RankingJudgment.label_metadata``.
TIER_KEY = "reviewer_tier"


def tier_of(judgment: Any) -> str:
    """The tier of a judgment row (or of a raw ``label_metadata`` dict).

    Anything unrecognized — a missing key, a null, a typo, a non-dict metadata
    blob — resolves to :data:`DEFAULT_TIER`. That is safe in exactly one
    direction and this is that direction: an unknown row read as ``alex`` is a
    real curator row treated as real. Reading it as ``kid`` would silently drop
    genuine labels out of a 24-row corpus.
    """
    metadata = getattr(judgment, "label_metadata", judgment)
    if not isinstance(metadata, dict):
        return DEFAULT_TIER
    value = metadata.get(TIER_KEY)
    return value if value in VALID_TIERS else DEFAULT_TIER


def is_gold(judgment: Any) -> bool:
    """Whether this row may move a published metric."""
    return tier_of(judgment) in GOLD_TIERS


def with_tier(metadata: dict | None, tier: str) -> dict:
    """Stamp a tier onto a ``label_metadata`` blob for a WRITE.

    Raises on an unknown tier rather than defaulting. A write site knows which
    tier it is; a typo there should stop the write, not quietly produce a gold
    row — which is precisely what defaulting would do.
    """
    if tier not in VALID_TIERS:
        raise ValueError(f"unknown reviewer_tier {tier!r}; expected one of {sorted(VALID_TIERS)}")
    base = dict(metadata) if isinstance(metadata, dict) else {}
    base[TIER_KEY] = tier
    return base


def tier_filter(tiers: frozenset[str] | set[str] = GOLD_TIERS):
    """A SQLAlchemy predicate selecting rows in ``tiers``.

    The ``alex`` case must also match rows where the key is absent or the whole
    ``label_metadata`` is NULL — every pre-B1 row looks like that, and a filter
    that missed them would empty the corpus rather than gate it.
    """
    unknown = set(tiers) - VALID_TIERS
    if unknown:
        raise ValueError(f"unknown reviewer_tier(s) {sorted(unknown)}")

    key = RankingJudgment.label_metadata[TIER_KEY].astext
    clauses = [key == tier for tier in sorted(tiers)]
    if DEFAULT_TIER in tiers:
        # Untagged rows ARE the default tier.
        clauses.append(key.is_(None))
        clauses.append(RankingJudgment.label_metadata.is_(None))
    return or_(*clauses)


def gold_filter():
    """The predicate every metric consumer should use unless told otherwise."""
    return tier_filter(GOLD_TIERS)


def resolve_tiers(tiers: frozenset[str] | set[str] | None) -> frozenset[str]:
    """Normalize a caller's tier request, defaulting to gold.

    ``None`` means "the caller did not think about tiers", and the whole point
    of B1 is that this resolves to the SAFE set rather than to everything.
    """
    if tiers is None:
        return GOLD_TIERS
    return frozenset(tiers)
