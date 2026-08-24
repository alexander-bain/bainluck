"""API endpoints for ranking judgments (Discover feed review)."""

import csv
import hashlib
import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import FuturesMarket, FuturesOutcome, RankingJudgment, Sport
from app.routes.admin_utils import (
    _check_admin_auth,
    _check_admin_destructive,
    _check_admin_secret,
    _resolve_admin_email,
    resolve_bearer_user_email,
)
from app.services import get_db, get_db_rw
from app.utils.card_integrity import display_scale, field_coherence, is_unlabelable
from app.utils.sport_keys import NON_SPORT_LLM_CATEGORIES
from app.utils.discover_reason_tags import canonical_reason_tags
from app.utils.graded_card import (
    ABSENT_UNBOUND,
    FLIP_WINDOW_DAYS,
    NATIVE_SERVED_OUTCOMES,
    OMITTED,
    card_fingerprint,
    drift_outcome,
    flip_readiness,
    rendered_card_percents,
)
from app.utils.feed_market_quality import classify_market_quality, editorial_archetype
from app.utils.kalshi_display_names import apply_name_repairs, repair_truncated_names
from app.utils.gold_label_store import (
    ORIGIN_KEY,
    gold_label_row,
    label_origin,
    normalize_card_snapshot as _normalize_card_snapshot,
    structured_label_metadata as _structured_label_metadata,
)
from app.utils.gold_progress import gold_progress
from app.utils.labeling_queue import load_reviewed_ranking_keys
from app.utils.reviewer_tier import TIER_ALEX

#: Alex's timezone. The gold-set day boundary, and the only place it is written.
GOLD_PROGRESS_TIMEZONE = "America/Los_Angeles"

router = APIRouter(prefix="/admin/ranking-judgments", tags=["admin-judgments"])
logger = logging.getLogger(__name__)


class RankingJudgmentCreate(BaseModel):
    secret: str | None = None
    # The opaque digest `/candidates` stamped on the card this judgment grades
    # (#1933). The client never computes it — it round-trips the string. Its
    # ABSENCE is meaningful and distinct from a null: `model_dump(exclude_unset=
    # True)` is what lets the route tell "an app build that predates the gate"
    # from "a gate-aware client that sent nothing", and those two get different
    # answers. See `graded_card.ABSENT_UNBOUND`.
    card_fingerprint: str | None = None
    surface: str | None = None
    rank_seen: int | None = None
    item_type: str | None = None
    market_id: int | None = None
    event_id: int | None = None
    market_name: str | None = None
    label: str | None = None
    reason_tags: list[str] | str | None = None
    better_than: str | None = None
    worse_than: str | None = None
    notes: str | None = None
    score_at_review: float | None = None
    category_at_review: str | None = None
    archetype_at_review: str | None = None
    quality_class_at_review: str | None = None
    headline_at_review: str | None = None
    feed_request_id: str | None = None
    card_snapshot: dict[str, Any] | None = None
    label_metadata: dict[str, Any] | None = None
    would_be_interesting_if: str | None = None
    fixable_interest_score: int | None = None
    fix_type: str | None = None
    desired_entity_or_variant: str | None = None
    current_entity_or_variant: str | None = None
    create_issue_candidate: bool | None = None
    fixable_interesting: bool | None = None
    repair_type: str | None = None
    repair_target_entity: str | None = None
    repair_note: str | None = None
    reviewer: str | None = None


class FixableInterestClusterTriage(BaseModel):
    secret: str | None = None
    status: str
    github_issue_url: str | None = None
    github_issue_number: int | None = None
    experiment_key: str | None = None
    notes: str | None = None
    owner: str | None = None


DEFAULT_LABELING_STRATA = [
    "top_feed_like",
    "fresh_public_story",
    "stale_fixable",
    "weather",
    "finance_ladder",
    "low_confidence",
    "duplicate_group",
    "explanation_image_gap",
    "movement_boundary",
    "low_volume_editorial",
]

PUBLIC_STORY_CATEGORIES = (
    "politics",
    "geopolitics",
    "economics",
    "tech",
    "entertainment",
    "culture",
    "health",
    "weather",
)


def _parse_candidate_strata(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_LABELING_STRATA)
    requested = [part.strip() for part in value.split(",") if part.strip()]
    allowed = set(DEFAULT_LABELING_STRATA)
    return [stratum for stratum in requested if stratum in allowed] or list(
        DEFAULT_LABELING_STRATA
    )


#: How old a market's newest PRICE may be and still be worth judging for taste.
#: Seven days: long enough to keep genuinely slow-moving long-horizon markets
#: (2028 election, World Cup) in the pool, short enough to exclude the 14 rows
#: in the measured draw that were 30+ days cold.
_MAX_TASTE_PRICE_AGE = timedelta(days=7)

#: The strata that ask "is this an interesting card?". `stale_fixable` is
#: deliberately absent — staleness is its subject, not its defect.
_PRICE_FRESH_STRATA = frozenset(
    {
        "top_feed_like",
        "fresh_public_story",
        "weather",
        "finance_ladder",
        "low_confidence",
        "movement_boundary",
    }
)


# ── A GAME THAT HAS FINISHED IS NOT A LABELLING CANDIDATE (#2075) ────────────
#
# Both date fields the sampler trusts can be false at once for a settled Kalshi
# game. `status` stays `'open'` forever because regular polling only fetches open
# markets, so nothing ever moves it once the market settles upstream (gotcha #33),
# and `resolution_date` is Kalshi's CLOSE time rather than the start (gotcha #14).
# Market 59183794, `Los Angeles D vs Colorado`, was served to Alex on 2026-08-21
# for a game that started on the 18th: both fields looked future-ish while the
# game itself was history.
#
# ** IT IS INVISIBLE TO EVERY EXISTING GUARD, BY CONSTRUCTION. ** The strata admit
# "live, unresolved" markets BY `status`, and `status` is the field that has gone
# stale — so the card passes the admission test *because* of the defect.
#
# ** WHY THIS COSTS SOMETHING. ** Labelling volume is the scarce input: ruling 016
# is blocked on it, and #1873 exists because Alex was grading cards Discover no
# longer serves. This is the same waste by a different route — #1873 was a stale
# snapshot of a live market, this is a live-looking snapshot of a dead one.
#
# ── THE THREE CONDITIONS, AND WHY IT IS NOT JUST "commence_time IS PAST" ──────
#
# MEASURED on production 2026-08-21. Of the 52,615 markets the sampler admits,
# **42,046 (80%) have a commence_time in the past** — the blanket rule would gut
# the pool, because for a season future or a non-sport question that column is not
# a kickoff at all. So all three conditions are load-bearing:
#
#   1. HEAD-TO-HEAD SHAPE. `X vs Y` / `X @ Y`. 32,488 admissible markets match.
#   2. A SPORT CATEGORY. 99% of the matched cohort is sport, but ~340 rows are
#      entertainment/tech/economics/politics questions that merely contain "vs".
#      `commence_time` means kickoff only where the market is a contest.
#   3. STARTED MORE THAN 12 HOURS AGO.
#
# ** THE 12 HOURS IS A DURATION BOUND, NOT A MEASURED GAP, AND THAT IS STATED
# RATHER THAN DRESSED UP. ** The hours-since-start histogram is CONTINUOUS — 245
# rows at 0-3h, 207 at 3-6h, 129 at 6-9h, 222 at 9-12h, 729 at 12-18h — so unlike
# #2060's [0.99, 1.01] band there is no empty middle to derive a threshold from.
# 12h is chosen because every game form we carry (an extra-innings baseball game,
# a five-set match, a BO5 esports series, a Hundred fixture) is over well inside
# it, so beyond 12h the market is certainly describing a finished game. Every one
# of the 13 already-played games in the live 100-card sample was 17h or older.
#
# ** THE RESIDUAL IS DELIBERATE. ** A game that finished two hours ago is still
# served, because at that range a finished game and a live one are indistinguishable
# without a trustworthy `status` — and `status` being untrustworthy is the whole
# issue. Refusing the certainly-dead is worth more than a threshold that also
# refuses live games, which are legitimate cards.
#
# ** THIS IS THE CHEAP HALF OF #2075. ** The durable fix is reconciling `status`
# for game markets whose start has passed, which lives in the settled-events
# backfill and not in a read path. That half stays open on the issue.
_GAME_CERTAINLY_OVER = timedelta(hours=12)

#: `X vs Y`, `X vs. Y`, `X @ Y`, `X at Y` — the head-to-head naming shape. Applied
#: with a sport category, never alone (see condition 2 above).
_HEAD_TO_HEAD_NAME_RE = r"(^| )(vs\.?|@) |[ ](vs\.?|at) "

#: The Python arm of the same predicate. Python's `re` and Postgres' `~*` agree on
#: this pattern — it uses no syntax where the two dialects differ.
_HEAD_TO_HEAD_PY_RE = re.compile(_HEAD_TO_HEAD_NAME_RE, re.IGNORECASE)


def is_finished_contest(
    *,
    name: str | None,
    llm_sport_category: str | None,
    commence_time: datetime | None,
    now: datetime,
) -> bool:
    """Is this market a sport contest that has certainly already been played?

    ** THE POLICY, AS OPPOSED TO THE QUERY. ** The stratum SQL above applies the
    same three conditions, and it has to, because ordering by `volume_24h DESC`
    puts just-finished games at the top of the budget. But a filter expressed only
    as a WHERE clause cannot be driven through cases, cannot be counted, and
    reports nothing when it stops matching. This function is the one the endpoint
    refuses with and the one the tests exercise; the SQL is an optimisation over
    it. Both are built from the SAME three constants, so they cannot drift without
    someone editing a constant that moves both.

    Returns False for anything it cannot be sure about — an unclassified market, a
    market with no start time, a non-sport question that merely contains "vs".
    Refusing a live card costs Alex a label he wanted; serving a dead one costs him
    a label he did not. Neither is free, and only one of them is silent.
    """
    if commence_time is None or name is None:
        return False
    if now - commence_time <= _GAME_CERTAINLY_OVER:
        return False
    category = (llm_sport_category or "").strip().lower()
    if not category or category in NON_SPORT_LLM_CATEGORIES:
        return False
    return bool(_HEAD_TO_HEAD_PY_RE.search(name))


def _labeling_stratum_query(stratum: str, *, now: datetime, limit: int):
    base_filters = [
        FuturesMarket.status == "open",
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date > now,
        ),
        # #2075 — refuse a sport contest that has certainly already been played.
        # Filtered in SQL rather than after the fetch on purpose: `top_feed_like`
        # orders by `volume_24h DESC`, and a game that JUST finished carries high
        # 24h volume, so the dead rows crowd the top of the very stratum the
        # sampler spends its budget on. Dropping them post-fetch would shrink the
        # served page instead of improving it.
        or_(
            FuturesMarket.commence_time.is_(None),
            FuturesMarket.commence_time > now - _GAME_CERTAINLY_OVER,
            FuturesMarket.llm_sport_category.is_(None),
            # SORTED, not `tuple(frozenset)`. Set iteration order varies per
            # process under string hash randomisation, so the unsorted form emits
            # a DIFFERENT SQL string on every worker — which fragments the
            # `pg_stat_statements` entry for this query across restarts and makes
            # the compiled text untestable for anything but membership.
            FuturesMarket.llm_sport_category.in_(sorted(NON_SPORT_LLM_CATEGORIES)),
            ~FuturesMarket.name.op("~*")(_HEAD_TO_HEAD_NAME_RE),
        ),
    ]

    if stratum == "top_feed_like":
        filters = base_filters
        ordering = [
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.market_tier.asc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        ]
    elif stratum == "fresh_public_story":
        filters = [
            *base_filters,
            FuturesMarket.llm_sport_category.in_(PUBLIC_STORY_CATEGORIES),
            FuturesMarket.created_at >= now - timedelta(days=14),
        ]
        ordering = [
            FuturesMarket.created_at.desc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "stale_fixable":
        filters = [
            *base_filters,
            or_(
                FuturesMarket.hook_generated_at < now - timedelta(days=10),
                FuturesMarket.updated_at < now - timedelta(days=14),
            ),
            or_(
                FuturesMarket.hook_description.isnot(None),
                FuturesMarket.image_url.isnot(None),
            ),
        ]
        ordering = [
            FuturesMarket.updated_at.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "weather":
        filters = [
            *base_filters,
            FuturesMarket.name.op("~*")(
                r"\m(weather|temperature|hurricane|rain|rainfall|precipitation|"
                r"snow|tornado|wildfire|heat)\M"
            ),
        ]
        ordering = [
            FuturesMarket.resolution_date.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "finance_ladder":
        filters = [
            *base_filters,
            or_(
                FuturesMarket.name.ilike("%S&P%"),
                FuturesMarket.name.ilike("%SPX%"),
                FuturesMarket.name.ilike("%Nasdaq%"),
                FuturesMarket.name.ilike("%WTI%"),
                FuturesMarket.name.ilike("%oil%"),
                FuturesMarket.name.ilike("%CPI%"),
                FuturesMarket.name.ilike("%Fed%"),
                FuturesMarket.name.ilike("%rate%"),
            ),
        ]
        ordering = [
            FuturesMarket.resolution_date.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "low_confidence":
        # Markets near the ranking boundary (score ~30-50 proxy): moderate
        # volume but not top-tier, with some enrichment. These sit at the
        # edge of feed inclusion and are the most valuable for calibrating
        # the scoring function.
        filters = [
            *base_filters,
            FuturesMarket.volume_24h.isnot(None),
            FuturesMarket.volume_24h > 0,
            FuturesMarket.volume_24h < 5000,
            or_(
                FuturesMarket.hook_description.isnot(None),
                FuturesMarket.image_url.isnot(None),
            ),
            FuturesMarket.llm_sport_category.isnot(None),
        ]
        ordering = [
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.max_movement_24h.desc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        ]
    elif stratum == "duplicate_group":
        filters = [*base_filters, FuturesMarket.group_id.isnot(None)]
        ordering = [
            FuturesMarket.group_id.asc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    elif stratum == "explanation_image_gap":
        filters = [
            *base_filters,
            or_(
                FuturesMarket.hook_description.is_(None),
                FuturesMarket.image_url.is_(None),
            ),
        ]
        ordering = [
            FuturesMarket.volume_24h.desc().nulls_last(),
            FuturesMarket.updated_at.desc().nulls_last(),
        ]
    elif stratum == "movement_boundary":
        filters = [
            *base_filters,
            FuturesMarket.max_movement_24h.isnot(None),
            FuturesMarket.max_movement_24h > 0,
        ]
        ordering = [
            FuturesMarket.max_movement_24h.desc().nulls_last(),
            FuturesMarket.volume_24h.desc().nulls_last(),
        ]
    else:
        filters = [
            *base_filters,
            or_(
                FuturesMarket.hook_description.isnot(None),
                FuturesMarket.image_url.isnot(None),
            ),
            or_(FuturesMarket.volume_24h.is_(None), FuturesMarket.volume_24h < 1000),
        ]
        ordering = [
            FuturesMarket.updated_at.desc().nulls_last(),
            FuturesMarket.created_at.desc().nulls_last(),
        ]

    # #2019 — A PRICE-FRESHNESS FLOOR ON THE TASTE STRATA.
    #
    # Measured 2026-08-19 on a live 40-card draw (all of it `top_feed_like`):
    # **19 of 40 carried prices 7+ days old, 14 of them 30+ days**, topping out
    # at 119 days. Both cards Alex labelled `bad` that session were 111 and 63
    # days stale. Judging "is this interesting" against a three-month-old price
    # is not taste, it is archaeology.
    #
    # The trap this avoids: `FuturesMarket.updated_at` LOOKS like the freshness
    # signal and is not one. It read `5h ago` on all three refused specimens —
    # identical to the microsecond across unrelated markets, i.e. a bulk write —
    # while their outcomes had not moved since May and June. Several of these
    # strata already ORDER BY it, which is why a stale card can sort to the top
    # of a "recently updated" list. Freshness therefore keys on the OUTCOME.
    #
    # Scoped to the taste strata on purpose. `stale_fixable` exists to surface
    # stale cards SO THEY CAN BE FIXED — applying the floor there would delete
    # the stratum's entire reason for existing.
    # ── #2024: THE FLOOR NOW KEYS ON `price_changed_at`, WITH A NULL POLICY ──
    #
    # `last_updated` is bumped on EVERY poll whether or not the price moved, so
    # as a freshness signal it separates ABANDONED markets (nothing writes them
    # any more, so the stamp goes stale) from everything else — but NOT an
    # actively-polled market whose price has sat still for three months, which
    # is precisely the specimen #2019 was opened on. `price_changed_at` answers
    # the question the floor is actually asking: when did this price last MOVE.
    #
    # ** THE NULL POLICY IS THE WHOLE RISK, AND IT IS FAIL-OPEN ON PURPOSE. **
    #
    # `price_changed_at` is new. Every row in production is NULL until its next
    # price change, and a row whose price never moves again stays NULL forever.
    # Read as `price_changed_at >= cutoff`, the floor would exclude every one of
    # them and empty the taste strata on the day it deployed — a labeling queue
    # that silently serves nothing, which is worse than the staleness it fixes.
    #
    # So NULL means UNKNOWN, never STALE (gotcha #53: an empty is not an
    # absence). A row with no stamp falls back to `last_updated`, i.e. to
    # exactly today's behaviour, and a row WITH a stamp is judged on it. The
    # floor can therefore only get sharper as the column fills; it cannot get
    # emptier. That also makes the deploy a no-op on day one, which is the
    # property that lets the reader ship before the writer's backfill exists.
    #
    # ** THIS IS AN INTERIM AND CARRIES ITS EXPIRY (ruling 061). ** The fallback
    # arm is deleted — not loosened — once `price_changed_at` coverage on
    # actively-polled outcomes is high enough that NULL means "genuinely never
    # observed to move" rather than "not stamped yet". Until then, deleting it
    # is the change that empties the queue.
    if stratum in _PRICE_FRESH_STRATA:
        cutoff = now - _MAX_TASTE_PRICE_AGE
        filters = [
            *filters,
            select(FuturesOutcome.id)
            .where(
                FuturesOutcome.market_id == FuturesMarket.id,
                or_(
                    FuturesOutcome.price_changed_at >= cutoff,
                    and_(
                        FuturesOutcome.price_changed_at.is_(None),
                        FuturesOutcome.last_updated >= cutoff,
                    ),
                ),
            )
            .exists(),
        ]

    return (
        select(FuturesMarket)
        .options(
            selectinload(FuturesMarket.outcomes).load_only(
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesOutcome.current_probability,
                FuturesOutcome.probability_change_24h,
                FuturesOutcome.rank,
            ),
            selectinload(FuturesMarket.sport).load_only(Sport.key, Sport.name),
        )
        .where(*filters)
        .order_by(*ordering)
        .limit(limit)
    )


def _scaled(prob, scale: float):
    """Apply the card's single display scale to one probability (or None).

    Mirrors `_scale_display_probability` in `app/routes/feed.py`; the shared
    POLICY lives in `card_integrity.display_scale`, and
    `test_labeling_sampler_serves_renderable_2019.py` asserts the two agree
    band-for-band so they cannot drift apart again.
    """
    if prob is None or scale == 1.0:
        return prob
    return round(float(prob) / scale, 4)


def _serialize_labeling_candidate(
    market: FuturesMarket,
    *,
    rank: int,
    stratum: str,
) -> dict[str, Any]:
    outcomes = sorted(
        market.outcomes or [],
        key=lambda outcome: (
            float(outcome.current_probability)
            if outcome.current_probability is not None
            else 0.0
        ),
        reverse=True,
    )
    # `NATIVE_SERVED_OUTCOMES` names this slice. The constant and the slice below
    # are pinned to each other by `test_graded_card_contract.py`: a fingerprint
    # taken over more rows than the surface renders refuses verdicts for changes
    # nobody could have seen, and one taken over fewer is blind to a change they
    # could.
    top_outcomes = [
        {
            "id": outcome.id,
            "name": outcome.name,
            "probability": (
                float(outcome.current_probability)
                if outcome.current_probability is not None
                else None
            ),
            "movement": (
                float(outcome.probability_change_24h)
                if outcome.probability_change_24h is not None
                else None
            ),
            "rank": outcome.rank,
        }
        for outcome in outcomes[:NATIVE_SERVED_OUTCOMES]
    ]
    # #1933 / queue 363. Alex graded on the NATIVE surface and saw the precise
    # defect #1873 fixed — because #1873 landed in `admin_label_pass.py` only,
    # and native comes through here. Without this gate the card renders
    # `top_outcomes[0]` as the probability even when the field cannot be
    # coherent (independent Kalshi binaries routinely sum well past 100% —
    # gotcha #23), i.e. it prints a number that cannot be true. Honest-empty,
    # ruling 027: withhold the field and say why.
    #
    # The gate is the SAME `field_coherence` the web pass uses. That is the
    # point — the two surfaces diverged because the fix was scoped to the
    # endpoint that carried the bug report rather than to the class.
    all_probs = [
        float(outcome.current_probability)
        if outcome.current_probability is not None
        else None
        for outcome in outcomes
    ]
    coherence = field_coherence(all_probs)

    # THE SAMPLER NOW RENDERS THE WAY THE SERVED FEED RENDERS (#2019).
    #
    # Withholding on `coherence["coherent"]` alone blanked the probability on
    # 21 of 40 sampled cards — measured 2026-08-19, ranks #1/#2/#3 among them,
    # which is exactly the "first three cards had no probabilities" Alex hit.
    # Every one of the 21 sat in the sum > 2.0 band, which is the band the feed
    # renders RAW because those outcomes are cumulative thresholds meaningful on
    # their own ("Ballon d'Or Winner 2026", sum 59.0, is 59 independent "will X
    # win?" binaries and Discover shows it fine).
    #
    # So the field is scaled the way the card would be scaled on the page, and
    # the probability is withheld only when NOTHING honest can be shown.
    scale = display_scale(all_probs, displayed_count=len(top_outcomes))
    unlabelable = is_unlabelable(
        outcome_names=[o.name for o in outcomes],
        outcome_probabilities=all_probs,
        market_name=market.name,
    )
    if unlabelable:
        display_outcomes = None
        withheld_reason = unlabelable
    else:
        display_outcomes = [
            {**o, "probability": _scaled(o.get("probability"), scale)}
            for o in top_outcomes
        ]
        withheld_reason = None

    # ── #2060 items 1 + 3: RENDER THE CARD, THEN FINGERPRINT WHAT WAS RENDERED ──
    #
    # Item 3. Kalshi ships `Los Angeles D`; the ticker ships `LAD`. The repair is
    # derived from the TICKER (gotcha #16) and never from `event_id`, whose link is
    # known broken for exactly this cohort (#2057 — the exemplar's event is the
    # 08-18 game while the market resolves 08-22). Unresolvable names ship
    # unchanged, and the source text is kept beside the repair rather than replaced.
    #
    # `getattr` rather than attribute access, matching `_live_features`. These are
    # OPTIONAL DISPLAY inputs: absent means "no repair" and "no when", which are
    # both fine cards. Reading them directly would turn a partially-hydrated row
    # — a `load_only` query, a test double — into an AttributeError inside a
    # route, taking down the entire labeling queue over a field whose absence the
    # card already knows how to render.
    name_repairs = repair_truncated_names(
        getattr(market, "external_id", None), [o.get("name") for o in top_outcomes]
    )
    display_name = apply_name_repairs(market.name, name_repairs)

    # Item 1. One card-level decision for the whole field, so the two sides of one
    # question cannot be rounded twice and printed as 101.
    if display_outcomes is not None:
        percents = rendered_card_percents(
            [o.get("probability") for o in display_outcomes]
        )
        display_outcomes = [
            {
                **o,
                "name": name_repairs.get(o.get("name"), o.get("name")),
                "name_at_source": o.get("name"),
                # SERVED, not left to each client to re-derive. The server already
                # has to compute this for the fingerprint; serving it is what makes
                # "all surfaces agree" true by construction rather than by three
                # implementations happening to match.
                "rendered_percent": percents[i],
            }
            for i, o in enumerate(display_outcomes)
        ]

    category = (
        market.llm_sport_category
        or (market.sport.name if market.sport else None)
        or "?"
    )
    quality = classify_market_quality(
        market_name=market.name,
        sport_category=category,
        outcome_names=[outcome["name"] for outcome in top_outcomes if outcome.get("name")],
    )
    return {
        "rank": rank,
        "type": "futures",
        "item_type": "futures",
        "id": market.id,
        "market_id": market.id,
        # ANNOTATED — queue 333, C272/B4 zero-read census (#1620).
        # Admin/labeling surface: a source-stable handle that survives re-ingest, so a
        # recorded judgment still points at the same question after the row is rebuilt.
        # 📌 CENSUS CORRECTION: B4 counted this as "declared in a native model", but iOS
        # `stableId` (Models/DiscoverLabelingModels.swift:69) is a COMPUTED property —
        # the app derives its own and never decodes this one. The native leg of B4's
        # four-part intersection is a false positive for this field; only the web side
        # ever declared it. The zero-read finding still holds, on weaker evidence.
        "stable_id": f"futures:{market.id}",
        "name": display_name,
        #: What the source actually shipped. Kept because a repair that silently
        #: replaces its input leaves no way to audit the repair (same reason
        #: `snapshot_at_write` is kept beside the live card).
        "name_at_source": market.name,
        "category": category,
        "archetype": editorial_archetype(market.name, category),
        "source": market.source,
        "stratum": stratum,
        "selection_reason": f"labeling:{stratum}",
        "candidate_source": "labeling_sampler_v1",
        "score": 0.0,
        "headline": None,
        "reason": None,
        "context": market.description,
        "hook_description": market.hook_description,
        "image_url": market.image_url,
        "group_id": market.group_id,
        "quality_class": quality.quality_class,
        "family_key": quality.family_key,
        "story_key": quality.story_key,
        "ladder": quality.is_ladder_or_bucket,
        "reasons": quality.reasons,
        "top_outcomes": display_outcomes,
        "rendered_probability": (
            display_outcomes[0]["probability"] if display_outcomes else None
        ),
        "field_coherent": coherence["coherent"],
        "field_sum": coherence["sum"],
        # `field_coherent` still reports whether this is a DISTRIBUTION; that is
        # a true and useful fact. It is no longer the admission test — see the
        # display-scale block above for why withholding on it emptied half the
        # queue of the cards Discover renders best.
        "field_withheld_reason": withheld_reason,
        "display_scale": scale,
        # Set when the card cannot be rendered honestly at all. The sampler
        # drops these; it is carried on the row so a debug read can see WHAT
        # was dropped and why rather than just a smaller list (no silent caps).
        "unrenderable_reason": unlabelable,
        "resolution_date": (
            market.resolution_date.isoformat() if market.resolution_date else None
        ),
        # ── #2060 item 2: WHEN ──────────────────────────────────────────────────
        #
        # "A probability is ungradeable without a when." The card served
        # `resolution_date` and nothing else, and for a Kalshi game market that is
        # the CLOSE time, not the start (gotcha #14) — so the one temporal fact on
        # the card was the wrong one.
        #
        # The data was already there: measured 2026-08-21, **50,776 of 50,779**
        # open markets carry `commence_time` (99.994%). This was a serve-side
        # omission, not a gap.
        #
        # It is worth knowing what this exposes. The exemplar card (59183794)
        # commences 2026-08-18 and was still being served as a labelling candidate
        # on 08-21 — a three-day-old game, open only because Kalshi stops returning
        # settled markets and our status goes stale (gotcha #33). Alex could not
        # have seen that before, and now cannot miss it.
        "commence_time": (
            _commence_time.isoformat()
            if (_commence_time := getattr(market, "commence_time", None))
            else None
        ),
        "created_at": market.created_at.isoformat() if market.created_at else None,
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
        # ── THE BINDING BETWEEN THIS READ AND THE JUDGMENT THAT FOLLOWS IT ────
        #
        # #1933's still-open acceptance bullet: "a card that went stale between
        # sampling and grading is refused on BOTH surfaces with the same typed
        # conflict." Stamped HERE, inside the serializer, rather than in the
        # route — so `_native_card_fingerprint` below can re-derive it at verdict
        # time by calling this same function, and the two can never be two
        # derivations that merely agree (doctrine clause 5).
        #
        # `rank` and `stratum` are deliberately NOT in it: they describe where
        # the card sat in a sampling run, not what it says. A card re-sampled at
        # a different rank tomorrow is the same card, and refusing a verdict over
        # its position would be a refusal nobody could explain by looking at the
        # screen. Pinned by a test that fingerprints one market at two ranks.
        # `display_name`, not `market.name` — the digest is over what is RENDERED,
        # which is this module's whole promise, and after #2060 the rendered title
        # is the repaired one. Fingerprinting the source text would refuse a verdict
        # whenever a repair became newly available, for a change nobody could see.
        "card_fingerprint": card_fingerprint(
            title=display_name,
            # Native does not PRINT status, so including it looks like a
            # violation of "fingerprint what is rendered". It is not: the
            # sampler's strata admit only live, unresolved markets, so status is
            # what put the card on screen at all. A market that settled between
            # sampling and grading is not a card whose picture moved — it is a
            # card that would not be served now, and native has no lifecycle gate
            # of its own to catch that. Status changes are rare and one-way, so
            # this buys the lifecycle case without the spurious-refusal cost that
            # fingerprinting raw floats would carry.
            status=market.status,
            resolution_date=(
                market.resolution_date.isoformat() if market.resolution_date else None
            ),
            field_coherent=coherence["coherent"],
            outcomes=display_outcomes,
            served_outcomes=NATIVE_SERVED_OUTCOMES,
        ),
    }


def _native_card_fingerprint(market: FuturesMarket) -> str:
    """The live fingerprint of the card native renders for this market.

    One line, and that is the point: it re-runs the SERIALIZER, so the value the
    verdict compares against is produced by the same code that produced the value
    the client was given. A second hand-written derivation here would be a second
    policy, which is exactly how the label-pass fix missed native in the first
    place (#1933).

    ``rank``/``stratum`` are placeholders — see the serializer for why they cannot
    reach the digest.
    """
    return _serialize_labeling_candidate(market, rank=0, stratum="")["card_fingerprint"]


def _merged_value(
    body: dict[str, Any],
    key: str,
    query_value: Any,
    default: Any = None,
) -> Any:
    if query_value is not None:
        return query_value
    if key in body:
        return body[key]
    return default


async def _authorize_admin(secret_value: str | None, request, db) -> bool:
    """Admin auth for the judgment write endpoints.

    Accepts EITHER the ADMIN_TOKEN via the Authorization: Bearer header OR an
    admin identity (Firebase Bearer token whose user is allowlisted). Queue #252:
    the ?secret= query/body path is no longer honored by ``_check_admin_secret``
    (it header-checks), so a request with only ?secret= is rejected in prod.
    ``_check_admin_secret`` raises on mismatch, so guard it before falling back
    to the identity-aware check.
    """
    try:
        if _check_admin_secret(secret_value, request=request):
            return True
    except Exception:
        pass
    return await _check_admin_auth(secret_value, request, db)


def _normalize_reason_tags(value: list[str] | str | None) -> list[str]:
    return canonical_reason_tags(value)


def _serialize_judgment(judgment: RankingJudgment) -> dict[str, Any]:
    metadata = judgment.label_metadata or {}
    return {
        "id": judgment.id,
        "date": str(judgment.date) if judgment.date else None,
        "surface": judgment.surface,
        "rank_seen": judgment.rank_seen,
        "item_type": judgment.item_type,
        "market_id": judgment.market_id,
        "event_id": judgment.event_id,
        "market_name": judgment.market_name,
        "label": judgment.label,
        "reason_tags": canonical_reason_tags(judgment.reason_tags),
        "better_than": judgment.better_than,
        "worse_than": judgment.worse_than,
        "notes": judgment.notes,
        "score_at_review": judgment.score_at_review,
        "category_at_review": judgment.category_at_review,
        "archetype_at_review": judgment.archetype_at_review,
        "quality_class_at_review": judgment.quality_class_at_review,
        "headline_at_review": judgment.headline_at_review,
        "feed_request_id": judgment.feed_request_id,
        "label_metadata": metadata,
        "card_snapshot": metadata.get("card_snapshot") if isinstance(metadata, dict) else None,
        "fixable_interesting": judgment.fixable_interesting,
        "repair_type": judgment.repair_type,
        "repair_target_entity": judgment.repair_target_entity,
        "repair_note": judgment.repair_note,
        "reviewer": judgment.reviewer,
        "created_at": judgment.created_at.isoformat() if judgment.created_at else None,
    }


def _metadata_dict(judgment: RankingJudgment) -> dict[str, Any]:
    return judgment.label_metadata if isinstance(judgment.label_metadata, dict) else {}


def _fixable_interest(metadata: dict[str, Any]) -> dict[str, Any]:
    fixable = metadata.get("fixable_interest")
    return fixable if isinstance(fixable, dict) else {}


def _card_snapshot(metadata: dict[str, Any]) -> dict[str, Any]:
    snapshot = metadata.get("card_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _has_fixable_interest(fixable: dict[str, Any]) -> bool:
    return any(
        fixable.get(key) not in (None, "", False)
        for key in (
            "would_be_interesting_if",
            "fixable_interest_score",
            "fix_type",
            "desired_entity_or_variant",
            "current_entity_or_variant",
            "create_issue_candidate",
        )
    )


def _cluster_identity(judgment: RankingJudgment) -> dict[str, str]:
    metadata = _metadata_dict(judgment)
    fixable = _fixable_interest(metadata)
    snapshot = _card_snapshot(metadata)
    item_key = (
        snapshot.get("group_id")
        or snapshot.get("story_key")
        or snapshot.get("family_key")
        or f"{judgment.item_type}:{judgment.market_id or judgment.event_id or judgment.id}"
    )
    return {
        "fix_type": str(fixable.get("fix_type") or "unspecified"),
        "item_key": str(item_key or "unknown"),
        "desired_entity_or_variant": str(fixable.get("desired_entity_or_variant") or ""),
        "current_entity_or_variant": str(fixable.get("current_entity_or_variant") or ""),
    }


def _cluster_id(identity: dict[str, str]) -> str:
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "fix_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _triage_status(fixable: dict[str, Any]) -> str:
    triage = fixable.get("triage")
    if isinstance(triage, dict) and triage.get("status"):
        return str(triage["status"])
    return "open"


def _serialize_fixable_cluster(cluster_id: str, rows: list[RankingJudgment]) -> dict[str, Any]:
    rows = sorted(rows, key=lambda row: row.created_at or row.date, reverse=True)
    representative = rows[0]
    metadata = _metadata_dict(representative)
    fixable = _fixable_interest(metadata)
    snapshot = _card_snapshot(metadata)
    identity = _cluster_identity(representative)

    status_counts: dict[str, int] = {}
    categories: set[str] = set()
    labels: set[str] = set()
    market_ids: set[int] = set()
    affected_ranks: list[int] = []
    issue_candidates = 0
    max_score: int | None = None
    latest_triage: dict[str, Any] | None = None

    for row in rows:
        row_metadata = _metadata_dict(row)
        row_fixable = _fixable_interest(row_metadata)
        status = _triage_status(row_fixable)
        status_counts[status] = status_counts.get(status, 0) + 1
        row_snapshot = _card_snapshot(row_metadata)
        if row.category_at_review:
            categories.add(row.category_at_review)
        elif row_snapshot.get("category"):
            categories.add(str(row_snapshot["category"]))
        if row.label:
            labels.add(row.label)
        if row.market_id is not None:
            market_ids.add(row.market_id)
        if row.rank_seen is not None:
            affected_ranks.append(row.rank_seen)
        if row_fixable.get("create_issue_candidate"):
            issue_candidates += 1
        try:
            score = int(row_fixable.get("fixable_interest_score"))
            max_score = score if max_score is None else max(max_score, score)
        except (TypeError, ValueError):
            pass
        triage = row_fixable.get("triage")
        if isinstance(triage, dict) and triage.get("status") != "open":
            latest_triage = triage

    if status_counts and status_counts.get("open", 0) == len(rows):
        status = "open"
    elif "linked" in status_counts:
        status = "linked"
    elif "experiment" in status_counts:
        status = "experiment"
    elif "dismissed" in status_counts and status_counts["dismissed"] == len(rows):
        status = "dismissed"
    else:
        status = max(status_counts.items(), key=lambda item: item[1])[0]

    return {
        "cluster_id": cluster_id,
        "status": status,
        "triage": latest_triage or {},
        "triage_counts": status_counts,
        "fix_type": identity["fix_type"],
        "item_key": identity["item_key"],
        "story_key": snapshot.get("story_key"),
        "family_key": snapshot.get("family_key"),
        "group_id": snapshot.get("group_id"),
        "desired_entity_or_variant": fixable.get("desired_entity_or_variant") or "",
        "current_entity_or_variant": fixable.get("current_entity_or_variant") or "",
        "would_be_interesting_if": fixable.get("would_be_interesting_if") or "",
        "count": len(rows),
        "issue_candidate_count": issue_candidates,
        "max_fixable_interest_score": max_score,
        "latest_created_at": representative.created_at.isoformat() if representative.created_at else None,
        "categories": sorted(categories),
        "labels": sorted(labels),
        "affected_ranks": sorted(set(affected_ranks)),
        "market_ids": sorted(market_ids),
        "examples": [_serialize_fixable_example(row) for row in rows[:3]],
    }


def _serialize_fixable_example(judgment: RankingJudgment) -> dict[str, Any]:
    metadata = _metadata_dict(judgment)
    fixable = _fixable_interest(metadata)
    snapshot = _card_snapshot(metadata)
    return {
        "judgment_id": judgment.id,
        "created_at": judgment.created_at.isoformat() if judgment.created_at else None,
        "market_id": judgment.market_id,
        "event_id": judgment.event_id,
        "market_name": judgment.market_name,
        "snapshot_name": snapshot.get("name"),
        "label": judgment.label,
        "rank_seen": judgment.rank_seen,
        "score_at_review": judgment.score_at_review,
        "would_be_interesting_if": fixable.get("would_be_interesting_if") or "",
        "notes": judgment.notes,
        "card_snapshot": snapshot,
    }


def _build_fixable_clusters(rows: list[RankingJudgment]) -> list[dict[str, Any]]:
    grouped: dict[str, list[RankingJudgment]] = {}
    for row in rows:
        metadata = _metadata_dict(row)
        fixable = _fixable_interest(metadata)
        if not _has_fixable_interest(fixable):
            continue
        cluster_id = _cluster_id(_cluster_identity(row))
        grouped.setdefault(cluster_id, []).append(row)
    clusters = [
        _serialize_fixable_cluster(cluster_id, cluster_rows)
        for cluster_id, cluster_rows in grouped.items()
    ]
    clusters.sort(
        key=lambda cluster: (
            cluster["status"] != "open",
            -(cluster["max_fixable_interest_score"] or 0),
            -cluster["issue_candidate_count"],
            -cluster["count"],
            cluster["latest_created_at"] or "",
        )
    )
    return clusters


@router.post("")
async def create_judgment(
    request: Request,
    payload: RankingJudgmentCreate | None = Body(None),
    db: AsyncSession = Depends(get_db_rw),
    secret: str | None = Query(None),
    surface: str | None = Query(None),
    rank_seen: int | None = Query(None),
    item_type: str | None = Query(None),
    market_id: int | None = Query(None),
    event_id: int | None = Query(None),
    market_name: str | None = Query(None),
    label: str | None = Query(None),
    reason_tags: str | None = Query(None),
    better_than: str | None = Query(None),
    worse_than: str | None = Query(None),
    notes: str | None = Query(None),
    score_at_review: float | None = Query(None),
    category_at_review: str | None = Query(None),
    archetype_at_review: str | None = Query(None),
    quality_class_at_review: str | None = Query(None),
    headline_at_review: str | None = Query(None),
    feed_request_id: str | None = Query(None),
    fixable_interesting: bool | None = Query(None),
    repair_type: str | None = Query(None),
    repair_target_entity: str | None = Query(None),
    repair_note: str | None = Query(None),
    reviewer: str | None = Query(None),
    card_fingerprint_posted: str | None = Query(None, alias="card_fingerprint"),
):
    """Record one native ranking judgment, gated against card drift (#1933).

    ── THE GATE, AND WHY IT IS THE SAME ONE THE WEB PASS USES ───────────────────

    #1873 taught the label-pass surface to derive the graded card from live
    state, and UX-P110 bound that card to the verdict with a fingerprint checked
    inside the write transaction. Both landed in ``admin_label_pass.py``. Native
    writes ``RankingJudgment`` through this module, so it received neither, and
    Alex — who #1933 records as preferring this surface — kept grading unbound.

    So the decision is imported, not re-implemented: ``graded_card.drift_outcome``
    is the one policy, and the card is re-derived here from live rows by calling
    the same serializer ``/candidates`` serves from.

    ** WHAT THIS DOES NOT CLAIM. ** The market row is re-read inside this
    session before anything is added, and a refusal writes nothing — but the row
    is not locked. Locking a market and all its outcomes on every label would
    contend with the two-minute live poller for no real gain: the poller commits
    per outcome, so the only thing a lock buys is a sub-millisecond torn read
    that the next POST catches anyway. The web pass locks its PROPOSAL row and
    has exactly the same property on outcomes, so this is parity, not a shortcut.
    """
    body = payload.model_dump(exclude_unset=True) if payload else {}
    secret_value = _merged_value(body, "secret", secret)
    if not await _authorize_admin(secret_value, request, db):
        raise HTTPException(status_code=403, detail="Admin access required")

    label_value = _merged_value(body, "label", label)
    if not label_value:
        raise HTTPException(status_code=400, detail="label is required")

    # Presence, not truthiness. `_merged_value` cannot express this: it collapses
    # "absent" and "null" onto one default, and telling those apart is the whole
    # of the unbound policy.
    if card_fingerprint_posted is not None:
        posted_fingerprint: Any = card_fingerprint_posted
    elif "card_fingerprint" in body:
        posted_fingerprint = body["card_fingerprint"]
    else:
        posted_fingerprint = OMITTED

    market_target = _merged_value(body, "market_id", market_id)
    item_type_value = _merged_value(body, "item_type", item_type, "futures")

    live_market = None
    if market_target is not None and item_type_value == "futures":
        live_market = (
            await db.execute(
                select(FuturesMarket)
                .options(
                    # Same eager loads as `_labeling_stratum_query`. Without
                    # them the serializer lazy-loads inside an async session and
                    # raises rather than fingerprinting.
                    selectinload(FuturesMarket.outcomes).load_only(
                        FuturesOutcome.id,
                        FuturesOutcome.name,
                        FuturesOutcome.current_probability,
                        FuturesOutcome.probability_change_24h,
                        FuturesOutcome.rank,
                    ),
                    selectinload(FuturesMarket.sport).load_only(Sport.key, Sport.name),
                )
                .where(FuturesMarket.id == int(market_target))
            )
        ).scalar_one_or_none()

    if live_market is not None:
        live_fingerprint = _native_card_fingerprint(live_market)
        live_row = _serialize_labeling_candidate(live_market, rank=0, stratum="")
        gate = drift_outcome(
            posted_fingerprint,
            live_fingerprint,
            live_card={
                "title": live_row.get("name"),
                "status": live_market.status,
                "probability": live_row.get("rendered_probability"),
                "field_coherent": live_row.get("field_coherent"),
            },
            on_absent=ABSENT_UNBOUND,
        )
    else:
        # No market to re-derive: an event judgment, or a target that no longer
        # exists. Never silently "bound" — an ungradeable target is a fact about
        # this row and it is recorded as one (ruling 086).
        live_fingerprint = None
        live_row = None
        gate = {
            "status": "unbound",
            "reason": (
                "no_market_target"
                if market_target is None
                else "market_missing"
            ),
        }

    if gate["status"] == "conflict":
        raise HTTPException(status_code=409, detail=gate)

    # Resolve reviewer identity: when the caller passes "native" (iOS default)
    # and is authenticated via Bearer token, persist the admin user's email so
    # server-side reviewed-state is per-user rather than a shared pool.
    reviewer_value = _merged_value(body, "reviewer", reviewer, "alex")
    if reviewer_value == "native":
        admin_email = await _resolve_admin_email(request, db)
        if admin_email:
            reviewer_value = admin_email

    surface_value = _merged_value(body, "surface", surface, "discover")
    reason_tags_value = _normalize_reason_tags(
        _merged_value(body, "reason_tags", reason_tags)
    )

    judgment = gold_label_row(
        surface=surface_value,
        rank_seen=_merged_value(body, "rank_seen", rank_seen),
        item_type=_merged_value(body, "item_type", item_type, "futures"),
        market_id=_merged_value(body, "market_id", market_id),
        event_id=_merged_value(body, "event_id", event_id),
        # The title actually graded, from the live row where there is one — the
        # same correction UX-P110 made to `item_name` on the web verdict. This
        # column feeds `_cluster_identity`, so a stale copy silently forks one
        # question into two clusters. The posted spelling is kept under
        # `card_snapshot.name_at_post` when it differs.
        market_name=(
            (live_row or {}).get("name")
            or _merged_value(body, "market_name", market_name)
        ),
        label=label_value,
        reason_tags=reason_tags_value,
        better_than=_merged_value(body, "better_than", better_than),
        worse_than=_merged_value(body, "worse_than", worse_than),
        notes=_merged_value(body, "notes", notes),
        score_at_review=_merged_value(body, "score_at_review", score_at_review),
        category_at_review=_merged_value(body, "category_at_review", category_at_review),
        archetype_at_review=_merged_value(
            body, "archetype_at_review", archetype_at_review
        ),
        quality_class_at_review=_merged_value(
            body, "quality_class_at_review", quality_class_at_review
        ),
        headline_at_review=_merged_value(body, "headline_at_review", headline_at_review),
        feed_request_id=_merged_value(body, "feed_request_id", feed_request_id),
        # Every write carries a tier (Queue 311 B1 / #1170). This admin surface
        # is Alex's, so it writes `alex` — the kid surface gets its own route
        # with no code path that can write anything but `kid`, rather than a
        # flag on this one that a caller has to remember to set.
        tier=TIER_ALEX,
        metadata=_structured_label_metadata(
            body,
            _merged_value(body, "label_metadata", None),
            gate=gate,
            live_card=live_row,
            # ONE derivation, hoisted above this call and passed to both
            # consumers (doctrine clause 5). Re-normalising the tags here would
            # be a second derivation that merely agrees — and the one that
            # decides the defect route would be free to drift from the one
            # actually stored on the row.
            label=label_value,
            reason_tags=reason_tags_value,
        ),
        # This surface elicits the gold label itself — Alex taps love/fine/bad/
        # kill on the card. Nothing is inferred, and the row says so, because the
        # label pass's converged rows sit in the same table and theirs is.
        origin=label_origin(surface=surface_value, mapping="direct"),
        fixable_interesting=bool(
            _merged_value(body, "fixable_interesting", fixable_interesting, False)
        ),
        repair_type=_merged_value(body, "repair_type", repair_type),
        repair_target_entity=_merged_value(
            body, "repair_target_entity", repair_target_entity
        ),
        repair_note=_merged_value(body, "repair_note", repair_note),
        reviewer=reviewer_value,
    )
    db.add(judgment)
    await db.commit()
    await db.refresh(judgment)
    return {
        "status": "ok",
        "id": judgment.id,
        "label": judgment.label,
        # Reported, not merely stored. A client that posted unbound should be
        # able to see that it did without reading the database — otherwise the
        # only way to discover a whole build's worth of ungated labels is to go
        # looking for them.
        "drift_gate": {"bound": gate["status"] == "bound", "reason": gate.get("reason")},
    }


#: Reviewer values that name a surface or a default, not a person. Production
#: carries all of these today; the list is documentation, not the test —
#: ``_judgment_owner`` requires an address, so a surface name added tomorrow is
#: unattributed by construction rather than by remembering to list it here.
_UNATTRIBUTED_REVIEWERS = {"native", "alex", "kid", "web", ""}


async def _resolve_reviewer_identity(request, db) -> str | None:
    """Who is asking, as a reviewer rather than as an administrator.

    Thin on purpose: the resolution lives in ``admin_utils`` next to its admin
    twin so the two cannot drift on which token forms they accept, and this
    wrapper exists so the delete route has one seam to authorize against.
    """
    return await resolve_bearer_user_email(request, db)


def _judgment_owner(judgment) -> str:
    """The identity a judgment is attributable to, or ``""`` for none.

    ``reviewer`` holds one of two very different things. When a judgment is
    POSTed with an identity, ``create_judgment`` resolves ``"native"`` to that
    reviewer's own email and stamps it — that is an OWNER. When it is POSTed
    with ADMIN_TOKEN there is no identity to resolve, so the literal
    ``"native"``/``"alex"`` stays on the row — that is a LABEL, and nobody owns
    it. Returning ``""`` for the second case is what keeps "signed in as Alex"
    from silently meaning "may delete every row a script ever wrote".

    The test is "is this an address", not "is this on a list of surface names".
    The list would have to grow every time a surface is added, and the failure
    mode of forgetting is the dangerous direction: a new literal that nobody
    listed would be treated as an owner, and would then be deletable by whoever
    managed to resolve to that same string.
    """
    value = (getattr(judgment, "reviewer", None) or "").strip().lower()
    if value in _UNATTRIBUTED_REVIEWERS:
        return ""
    if "@" not in value:
        return ""
    return value


@router.delete("/{judgment_id}")
async def delete_judgment(
    judgment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_rw),
    secret: str | None = Query(None),
):
    """Delete a single ranking judgment — the Rapid-mode "undo last" safety net.

    Read-your-writes: the row is removed and the transaction committed before
    returning, so an immediate re-list/summary no longer counts it. This backs
    the ReviewTab "undo last" (``u``) shortcut and the native labeling view's
    undo, so fast one-tap grading is fearless — a mis-tap is one action to
    reverse instead of a permanent bad row polluting Alex's gold-set batches.

    ## Two doors, and the reason there are two (UX-P125 item 3a)

    This route used to have exactly one: ``_check_admin_destructive``, the
    ADMIN_TOKEN + ADMIN_TOKEN_DESTRUCTIVE header pair. Meanwhile ``POST`` on the
    same resource authorizes through ``_authorize_admin``, which ALSO accepts a
    Firebase/session identity, and stamps that reviewer's own email onto the
    row. So the write and the un-write disagreed about who the caller was: Alex
    could grade all evening from his phone and every undo came back 403, which
    the client renders as "Admin access required to undo." The surface whose
    whole promise is that a mis-tap costs one tap could not take one back.

    Undo is not an attended destructive operation on someone else's data. It is
    a reviewer retracting a sentence they just wrote, and it is authorized by
    OWNERSHIP:

    * **owner** — the caller's resolved identity equals the row's ``reviewer``.
      No admin credential is involved, requested, or checked.
    * **operator** — anyone else, including a reviewer reaching for a row that
      is not theirs, and any row with no owner at all. That is still the strong
      attended gate, unchanged.

    The refusal for a non-owner says *why*. "Invalid admin secret" is what sent
    the report off looking for a missing token when the real answer was that the
    row belonged to someone else — a true statement about the credential, and a
    misleading one about the situation.
    """
    identity = await _resolve_reviewer_identity(request, db)

    judgment = (
        await db.execute(
            select(RankingJudgment).where(RankingJudgment.id == judgment_id)
        )
    ).scalar_one_or_none()

    owner = _judgment_owner(judgment) if judgment is not None else ""
    authorized_as = "owner" if (identity and owner and owner == identity) else None

    if authorized_as is None:
        try:
            _check_admin_destructive(secret, request=request)
            authorized_as = "operator"
        except HTTPException:
            # An identified caller who simply does not own this row gets a
            # sentence they can act on; an anonymous one gets the credential
            # error, which for them is the accurate description.
            #
            # The refusal is the same 403 whether or not the row exists. A
            # caller who may not delete it may not learn it is there either,
            # and answering 404 here would turn this route into an id oracle.
            if identity:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "This judgment was recorded by another reviewer, or is "
                        "not yours to remove. You can undo your own judgments; "
                        "removing another reviewer's is an attended operator "
                        "action."
                    ),
                ) from None
            raise

    if judgment is None:
        raise HTTPException(status_code=404, detail="Judgment not found")

    deleted_label = judgment.label
    await db.delete(judgment)
    await db.commit()
    logger.info(
        "Deleted ranking judgment id=%s label=%s via=%s",
        judgment_id,
        deleted_label,
        authorized_as,
    )
    return {"status": "deleted", "id": judgment_id, "label": deleted_label}


@router.get("/candidates")
async def list_labeling_candidates(
    request: Request,
    secret: str | None = Query(None),
    reviewer: str | None = Query("native"),
    reviewed_surface: str | None = Query("native_discover"),
    strata: str | None = Query(
        None,
        description="Comma-separated labeling strata. Defaults to all supported strata.",
    ),
    limit: int = Query(40, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    if not await _authorize_admin(secret, request, db):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Resolve reviewer: when "native" and authenticated via Bearer token,
    # use the admin's email for per-user reviewed state.
    effective_reviewer = reviewer
    if reviewer == "native":
        admin_email = await _resolve_admin_email(request, db)
        if admin_email:
            effective_reviewer = admin_email

    now = datetime.now(timezone.utc)
    selected_strata = _parse_candidate_strata(strata)
    per_stratum_limit = min(100, max(limit * 2, 40))
    reviewed_keys = await load_reviewed_ranking_keys(
        db,
        reviewer=effective_reviewer,
        surface=reviewed_surface,
    )

    sampled: list[tuple[str, FuturesMarket]] = []
    seen_market_ids: set[int] = set()
    stratum_counts: dict[str, int] = {}
    for stratum in selected_strata:
        result = await db.execute(
            _labeling_stratum_query(
                stratum,
                now=now,
                limit=per_stratum_limit,
            )
        )
        rows = result.scalars().unique().all()
        stratum_counts[stratum] = len(rows)
        for market in rows:
            if market.id in seen_market_ids:
                continue
            seen_market_ids.add(market.id)
            sampled.append((stratum, market))

    candidates: list[dict[str, Any]] = []
    filtered_reviewed = 0
    filtered_finished_contest = 0
    filtered_unrenderable: dict[str, int] = {}
    for stratum, market in sampled:
        if ("futures", market.id) in reviewed_keys:
            filtered_reviewed += 1
            continue
        # #2075 — a game that has already been played is not a labelling
        # candidate, however renderable its card is. Counted separately from
        # `filtered_unrenderable` because it is a different claim: that card can
        # be drawn perfectly, it is simply about a game whose result is known.
        # This should be near zero once the SQL filter has done its work; a
        # non-zero count means the query arm regressed and this one caught it.
        # getattr-with-default, NOT a bare attribute read. This loop is fed
        # duck-typed market objects by several tests and by the trace tooling, and
        # a hard read raises `AttributeError` on any of them — which is how this
        # landed four unrelated red tests in `test_admin_judgments.py` on its first
        # full-suite run. Same idiom as `_live_features`, which already reads
        # `commence_time` this way, and as the feed serializer's `market_type`.
        # Absent reads as None, which `is_finished_contest` treats as "unknown, do
        # not refuse" — the direction that cannot silently empty the queue.
        if is_finished_contest(
            name=getattr(market, "name", None),
            llm_sport_category=getattr(market, "llm_sport_category", None),
            commence_time=getattr(market, "commence_time", None),
            now=now,
        ):
            filtered_finished_contest += 1
            continue
        row = _serialize_labeling_candidate(
            market,
            rank=len(candidates) + 1,
            stratum=stratum,
        )
        # #2019 — a card nobody can read is not a label, it is a coin flip
        # recorded as taste. Labels train ranking on what users can SEE, so the
        # sampler serves the renderable population (ruling 098's logic applied
        # to the labeling window: name the window, and make it the served one).
        #
        # This is a REFUSAL, not a blank: the previous behaviour served the card
        # with an empty probability, so Alex spent three cards discovering there
        # was nothing to judge.
        if row.get("unrenderable_reason"):
            reason = row["unrenderable_reason"]
            filtered_unrenderable[reason] = filtered_unrenderable.get(reason, 0) + 1
            continue
        candidates.append(row)

    return {
        "items": candidates[:limit],
        "total_available": len(candidates),
        "limit": limit,
        "offset": 0,
        "has_more": len(candidates) > limit,
        "candidate_source": "labeling_sampler_v1",
        "strata": selected_strata,
        "stratum_sample_counts": stratum_counts,
        "reviewed_filter": {
            "enabled": True,
            "reviewer": effective_reviewer,
            "surface": reviewed_surface,
            "reviewed_key_count": len(reviewed_keys),
            "filtered_count": filtered_reviewed,
        },
        # #2019. Named rather than silent — a smaller list with no explanation
        # reads as "there wasn't much today".
        "renderable_filter": {
            "enabled": True,
            "filtered_count": sum(filtered_unrenderable.values()),
            "by_reason": filtered_unrenderable,
        },
        # #2075. Reported for the same reason, and with the threshold in the
        # payload rather than only in the source: this refusal turns on a
        # judgement call ("a game is certainly over after 12 hours"), and a
        # judgement call that is not visible where its effect is visible is one
        # nobody can revise. `filtered_count` is expected to be ~0 because the
        # stratum query already excluded these; a non-zero value means the SQL
        # arm regressed and the policy arm caught it.
        "finished_contest_filter": {
            "enabled": True,
            "filtered_count": filtered_finished_contest,
            "certainly_over_after_hours": _GAME_CERTAINLY_OVER.total_seconds() / 3600,
        },
    }


@router.get("")
async def list_judgments(
    request: Request,
    db: AsyncSession = Depends(get_db), secret: str = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    label: str | None = Query(None),
    surface: str | None = Query(None),
):
    _check_admin_secret(secret, request=request)

    q = select(RankingJudgment).order_by(desc(RankingJudgment.created_at))
    count_q = select(func.count(RankingJudgment.id))

    if label:
        q = q.where(RankingJudgment.label == label)
        count_q = count_q.where(RankingJudgment.label == label)
    if surface:
        q = q.where(RankingJudgment.surface == surface)
        count_q = count_q.where(RankingJudgment.surface == surface)

    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()

    summary_q = select(
        RankingJudgment.label,
        func.count(RankingJudgment.id),
    ).group_by(RankingJudgment.label)
    summary_rows = (await db.execute(summary_q)).all()
    summary = {row[0]: row[1] for row in summary_rows}

    return {
        "total": total,
        "summary": summary,
        "judgments": [_serialize_judgment(judgment) for judgment in rows],
    }


@router.get("/progress")
async def labeling_progress(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str | None = Query(None),
    reviewer: str | None = Query(None),
):
    """The gold-set progress meter the labelling surfaces show (#2060 item 4).

    ── WHY THIS IS NOT A FIELD ON ``/coverage`` ─────────────────────────────────

    ``/coverage`` answers a different question and pays a different price: it
    pulls every ``RankingJudgment`` row into Python and then runs
    ``_labeling_stratum_query`` once per stratum at ``limit=200`` each, plus a
    second full scan for the flip window. That is correct for a dashboard someone
    opens occasionally and wrong for a header that redraws after every vote —
    twenty times a session, on a phone, between taps.

    This is two grouped aggregates that never leave the database, so the meter
    costs the same at 88 rows and at 250.

    ── THE DAY BUCKET IS PACIFIC, IN SQL, ON PURPOSE ────────────────────────────

    ``AT TIME ZONE 'America/Los_Angeles'`` rather than a UTC bucket the server
    re-labels afterwards. Alex labels in the evening; a UTC day rolls over at 5pm
    PT, so his 8pm session would land on tomorrow, "today" would read zero on a
    night he actually worked, and the streak would break. Postgres owns the
    DST-aware arithmetic and the app does not re-derive it.
    """
    if not await _authorize_admin(secret, request, db):
        raise HTTPException(status_code=403, detail="Admin access required")

    pacific_day = func.to_char(
        func.timezone(GOLD_PROGRESS_TIMEZONE, RankingJudgment.created_at),
        "YYYY-MM-DD",
    )

    day_query = select(pacific_day.label("day"), func.count(RankingJudgment.id))
    total_query = select(func.count(RankingJudgment.id))
    if reviewer:
        day_query = day_query.where(RankingJudgment.reviewer == reviewer)
        total_query = total_query.where(RankingJudgment.reviewer == reviewer)

    day_rows = (await db.execute(day_query.group_by(pacific_day))).all()
    total = (await db.execute(total_query)).scalar_one()

    counts = {row[0]: row[1] for row in day_rows if row[0]}
    today = datetime.now(ZoneInfo(GOLD_PROGRESS_TIMEZONE)).date()

    progress = gold_progress(
        total=int(total or 0),
        today_count=int(counts.get(today.isoformat(), 0)),
        days=counts.keys(),
        today=today,
    )
    progress["timezone"] = GOLD_PROGRESS_TIMEZONE
    progress["reviewer"] = reviewer
    return progress


@router.get("/coverage")
async def labeling_coverage(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str | None = Query(None),
    window: str = Query(
        "all",
        description="Time window: 24h, 7d, 30d, or all",
    ),
):
    """Coverage dashboard for labeling effort.

    Returns reviewed counts grouped by stratum, verdict, category, and
    reviewer (hashed), plus queue health showing unreviewed candidates
    per stratum.
    """
    if not await _authorize_admin(secret, request, db):
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    window_map = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    base_filters: list = []
    if window in window_map:
        cutoff = now - window_map[window]
        base_filters.append(RankingJudgment.created_at >= cutoff)

    judgment_q = select(RankingJudgment)
    for f in base_filters:
        judgment_q = judgment_q.where(f)

    stratum_rows = (await db.execute(judgment_q)).scalars().all()

    by_stratum: dict[str, dict[str, int]] = {}
    by_verdict: dict[str, int] = {}
    by_category: dict[str, dict[str, int]] = {}
    by_reviewer: dict[str, int] = {}
    reviewer_daily: dict[str, dict[str, int]] = {}
    # ── THE MANIFEST HALF OF THE GATE (#1933) ────────────────────────────────
    #
    # The gate can only bind a client that declares it, so the store will hold
    # both kinds of row for as long as an old build is in the field. A coverage
    # dashboard that reports a single "reviewed" number over a mixed population
    # is the failure this whole queue is about, one level up: it would let an
    # entire build's worth of ungated labels read as gated ones. Three keys,
    # every row counted into exactly one, so "zero unbound" is a measurement
    # rather than a silence.
    drift_gate_tally: dict[str, int] = {"bound": 0, "unbound": 0, "unrecorded": 0}
    unbound_reasons: dict[str, int] = {}
    # #1933 bullet 2. The converged store holds labels the human picked directly
    # and labels inferred from a verdict on someone else's proposal. Both belong
    # here; a reader who cannot tell them apart does not have a gold set, so the
    # count is reported next to the total rather than hidden inside it.
    by_origin: dict[str, dict[str, int]] = {}
    total_reviewed = 0
    today_str = now.strftime("%Y-%m-%d")
    week_ago = now - timedelta(days=7)

    for j in stratum_rows:
        total_reviewed += 1
        metadata = j.label_metadata if isinstance(j.label_metadata, dict) else {}
        snapshot = metadata.get("card_snapshot") if isinstance(metadata, dict) else {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        stratum = snapshot.get("stratum") or ""
        if not stratum:
            selection_reason = snapshot.get("selection_reason") or ""
            if selection_reason.startswith("labeling:"):
                stratum = selection_reason[len("labeling:"):]
        if not stratum:
            stratum = "unknown"

        label = j.label or "unknown"
        category = j.category_at_review or snapshot.get("category") or "uncategorized"
        reviewer_h = _reviewer_hash(j.reviewer)

        gate_row = metadata.get("drift_gate")
        if not isinstance(gate_row, dict):
            # Written before the gate shipped. NOT "unbound" — that is a claim
            # about a client, and about these rows nothing was ever asked.
            drift_gate_tally["unrecorded"] += 1
        elif gate_row.get("bound"):
            drift_gate_tally["bound"] += 1
        else:
            drift_gate_tally["unbound"] += 1
            reason = gate_row.get("reason") or "unspecified"
            unbound_reasons[reason] = unbound_reasons.get(reason, 0) + 1

        origin = metadata.get(ORIGIN_KEY)
        if not isinstance(origin, dict):
            # Written before the store converged. `direct` is the correct
            # reading — every pre-convergence row in this table came from a
            # surface where Alex picked the label himself — but it is stated as
            # a legacy reading rather than silently merged into the new one.
            origin_surface, origin_mapping = (j.surface or "unknown"), "legacy_direct"
        else:
            origin_surface = origin.get("surface") or (j.surface or "unknown")
            origin_mapping = origin.get("mapping") or "unspecified"
        by_origin.setdefault(origin_surface, {})
        by_origin[origin_surface][origin_mapping] = (
            by_origin[origin_surface].get(origin_mapping, 0) + 1
        )

        by_stratum.setdefault(stratum, {})
        by_stratum[stratum][label] = by_stratum[stratum].get(label, 0) + 1

        by_verdict[label] = by_verdict.get(label, 0) + 1

        by_category.setdefault(category, {})
        by_category[category][label] = by_category[category].get(label, 0) + 1

        by_reviewer[reviewer_h] = by_reviewer.get(reviewer_h, 0) + 1

        if j.created_at:
            day_key = j.created_at.strftime("%Y-%m-%d")
            reviewer_daily.setdefault(reviewer_h, {})
            reviewer_daily[reviewer_h][day_key] = (
                reviewer_daily[reviewer_h].get(day_key, 0) + 1
            )

    stratum_heatmap = []
    for stratum, verdicts in sorted(by_stratum.items()):
        stratum_total = sum(verdicts.values())
        stratum_heatmap.append({
            "stratum": stratum,
            "verdicts": verdicts,
            "total": stratum_total,
            "sufficient": stratum_total >= 50,
        })

    reviewer_progress = []
    for rh, count in sorted(by_reviewer.items(), key=lambda x: -x[1]):
        daily = reviewer_daily.get(rh, {})
        today_count = daily.get(today_str, 0)
        week_count = sum(
            c for d, c in daily.items()
            if d >= week_ago.strftime("%Y-%m-%d")
        )
        reviewer_progress.append({
            "reviewer_hash": rh,
            "total": count,
            "today": today_count,
            "this_week": week_count,
        })

    reviewed_keys = await load_reviewed_ranking_keys(db, reviewer=None, surface=None)
    queue_health = []
    for stratum in DEFAULT_LABELING_STRATA:
        result = await db.execute(
            _labeling_stratum_query(stratum, now=now, limit=200)
        )
        markets = result.scalars().unique().all()
        unreviewed = sum(
            1 for m in markets
            if ("futures", m.id) not in reviewed_keys
        )
        reviewed_count = len(markets) - unreviewed
        queue_health.append({
            "stratum": stratum,
            "total_candidates": len(markets),
            "reviewed": reviewed_count,
            "unreviewed": unreviewed,
            "exhausted": unreviewed == 0 and len(markets) > 0,
        })

    insufficient_strata = [
        s["stratum"] for s in stratum_heatmap if not s["sufficient"]
    ]

    # ── THE FAIL-CLOSED FLIP CRITERION, COMPUTED (#1933, UX-P112) ────────────
    #
    # Over its OWN fixed window, deliberately not the caller's `window` param.
    # A criterion whose window is a query string is a criterion anyone can pass
    # by asking for a shorter one, and the point of writing it down was to stop
    # the flip being a debate.
    flip_cutoff = now - timedelta(days=FLIP_WINDOW_DAYS)
    flip_rows = (
        (
            await db.execute(
                select(RankingJudgment).where(RankingJudgment.created_at >= flip_cutoff)
            )
        )
        .scalars()
        .all()
    )
    flip_bound = 0
    flip_unbound = 0
    flip_unbound_reasons: dict[str, int] = {}
    flip_days: set[str] = set()
    for j in flip_rows:
        meta = j.label_metadata if isinstance(j.label_metadata, dict) else {}
        gate_row = meta.get("drift_gate")
        if not isinstance(gate_row, dict):
            continue
        if gate_row.get("bound"):
            flip_bound += 1
            if j.created_at:
                flip_days.add(j.created_at.strftime("%Y-%m-%d"))
        else:
            flip_unbound += 1
            reason = gate_row.get("reason") or "unspecified"
            flip_unbound_reasons[reason] = flip_unbound_reasons.get(reason, 0) + 1
    flip = flip_readiness(
        bound=flip_bound,
        unbound=flip_unbound,
        distinct_days=len(flip_days),
    )
    flip["unbound_reasons"] = flip_unbound_reasons

    return {
        "window": window,
        "total_reviewed": total_reviewed,
        "by_stratum": stratum_heatmap,
        "by_verdict": by_verdict,
        "by_category": by_category,
        "reviewer_progress": reviewer_progress,
        "queue_health": queue_health,
        "insufficient_strata": insufficient_strata,
        # #1933. How much of this corpus is bound to the card it graded.
        "drift_gate": {
            **drift_gate_tally,
            "unbound_reasons": unbound_reasons,
            "note": (
                "bound = the card was re-derived and matched at write time. "
                "unbound = written by a client that does not declare the gate "
                "(see unbound_reasons). unrecorded = written before the gate "
                "existed; nothing was asked of those rows, so they are neither."
            ),
        },
        # #1933 bullet 2 — one store, and it can say where each label came from.
        "by_origin": by_origin,
        # #1933 item 3 — the flip from capability-bind to fail-closed is a check.
        "flip_readiness": flip,
        "generated_at": now.isoformat(),
    }


@router.get("/summary")
async def judgment_summary(request: Request, db: AsyncSession = Depends(get_db), secret: str = Query(None)):
    _check_admin_secret(secret, request=request)

    label_q = select(
        RankingJudgment.label,
        func.count(RankingJudgment.id),
    ).group_by(RankingJudgment.label)
    label_rows = (await db.execute(label_q)).all()

    cat_q = select(
        RankingJudgment.category_at_review,
        RankingJudgment.label,
        func.count(RankingJudgment.id),
    ).group_by(RankingJudgment.category_at_review, RankingJudgment.label)
    cat_rows = (await db.execute(cat_q)).all()

    score_q = (
        select(
            RankingJudgment.label,
            func.avg(RankingJudgment.score_at_review),
            func.min(RankingJudgment.score_at_review),
            func.max(RankingJudgment.score_at_review),
            func.count(RankingJudgment.id),
        )
        .where(RankingJudgment.score_at_review.isnot(None))
        .group_by(RankingJudgment.label)
    )
    score_rows = (await db.execute(score_q)).all()

    pairwise_count = (
        await db.execute(
            select(func.count(RankingJudgment.id)).where(
                (RankingJudgment.better_than.isnot(None))
                | (RankingJudgment.worse_than.isnot(None))
            )
        )
    ).scalar() or 0

    by_category: dict[str, dict[str, int]] = {}
    for category, row_label, count in cat_rows:
        category_key = category or "uncategorized"
        by_category.setdefault(category_key, {})[row_label] = count

    return {
        "total": sum(row[1] for row in label_rows),
        "labels": {row[0]: row[1] for row in label_rows},
        "pairwise_count": pairwise_count,
        "score_by_label": [
            {
                "label": row[0],
                "avg_score": round(row[1], 1) if row[1] is not None else None,
                "min_score": round(row[2], 1) if row[2] is not None else None,
                "max_score": round(row[3], 1) if row[3] is not None else None,
                "count": row[4],
            }
            for row in score_rows
        ],
        "by_category": by_category,
    }


@router.get("/fixable-interest/clusters")
async def fixable_interest_clusters(
    request: Request,
    db: AsyncSession = Depends(get_db), secret: str = Query(None),
    status: str = Query("open"),
    limit: int = Query(50),
    row_limit: int = Query(1000),
):
    _check_admin_secret(secret, request=request)

    rows = (
        await db.execute(
            select(RankingJudgment)
            .where(RankingJudgment.label_metadata.isnot(None))
            .order_by(desc(RankingJudgment.created_at))
            .limit(row_limit)
        )
    ).scalars().all()
    clusters = _build_fixable_clusters(list(rows))
    if status != "all":
        clusters = [cluster for cluster in clusters if cluster["status"] == status]
    return {
        "status": status,
        "total": len(clusters),
        "clusters": clusters[:limit],
    }


@router.get("/repair-clusters")
async def repair_clusters(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Cluster fixable-interest judgments by repair_type, category, and entity.

    Groups judgments where ``fixable_interesting=True`` using the first-class
    ``repair_type`` column, ``category_at_review``, and ``repair_target_entity``.
    Returns clusters sorted by count (most common first), each with sample
    market IDs and reviewer count.
    """
    if not await _authorize_admin(secret, request, db):
        raise HTTPException(status_code=403, detail="Admin access required")

    rows = (
        await db.execute(
            select(RankingJudgment)
            .where(RankingJudgment.fixable_interesting.is_(True))
            .order_by(desc(RankingJudgment.created_at))
            .limit(2000)
        )
    ).scalars().all()

    grouped: dict[str, list[RankingJudgment]] = {}
    for row in rows:
        key = (
            f"{row.repair_type or 'unspecified'}"
            f"::{row.category_at_review or 'uncategorized'}"
            f"::{row.repair_target_entity or ''}"
        )
        grouped.setdefault(key, []).append(row)

    clusters: list[dict[str, Any]] = []
    for key, cluster_rows in grouped.items():
        parts = key.split("::", 2)
        repair_type = parts[0]
        category = parts[1]
        entity = parts[2] if len(parts) > 2 else ""

        market_ids: list[int] = []
        reviewers: set[str] = set()
        for row in cluster_rows:
            if row.market_id is not None and row.market_id not in market_ids:
                market_ids.append(row.market_id)
            if row.reviewer:
                reviewers.add(row.reviewer)

        clusters.append({
            "repair_type": repair_type,
            "category": category,
            "entity": entity,
            "count": len(cluster_rows),
            "reviewer_count": len(reviewers),
            "sample_market_ids": market_ids[:10],
            "latest_created_at": (
                cluster_rows[0].created_at.isoformat()
                if cluster_rows[0].created_at
                else None
            ),
        })

    clusters.sort(key=lambda c: -c["count"])
    return {
        "total": len(clusters),
        "clusters": clusters[:limit],
    }


@router.post("/fixable-interest/clusters/{cluster_id}/triage")
async def triage_fixable_interest_cluster(
    cluster_id: str,
    request: Request,
    payload: FixableInterestClusterTriage | None = Body(None),
    db: AsyncSession = Depends(get_db_rw),
    secret: str | None = Query(None),
):
    body = payload.model_dump(exclude_unset=True) if payload else {}
    secret_value = _merged_value(body, "secret", secret)
    if not await _authorize_admin(secret_value, request, db):
        raise HTTPException(status_code=403, detail="Admin access required")

    status = str(body.get("status") or "").strip()
    if status not in {"open", "dismissed", "linked", "experiment"}:
        raise HTTPException(status_code=400, detail="Unsupported triage status")

    rows = (
        await db.execute(
            select(RankingJudgment)
            .where(RankingJudgment.label_metadata.isnot(None))
            .order_by(desc(RankingJudgment.created_at))
            .limit(5000)
        )
    ).scalars().all()
    matched: list[RankingJudgment] = []
    triage = {
        "status": status,
        "github_issue_url": body.get("github_issue_url"),
        "github_issue_number": body.get("github_issue_number"),
        "experiment_key": body.get("experiment_key"),
        "notes": body.get("notes"),
        "owner": body.get("owner"),
    }
    triage = {key: value for key, value in triage.items() if value not in (None, "")}

    for row in rows:
        metadata = _metadata_dict(row)
        fixable = _fixable_interest(metadata)
        if not _has_fixable_interest(fixable):
            continue
        if _cluster_id(_cluster_identity(row)) != cluster_id:
            continue
        next_metadata = dict(metadata)
        next_fixable = dict(fixable)
        next_fixable["triage"] = triage
        next_metadata["fixable_interest"] = next_fixable
        row.label_metadata = next_metadata
        matched.append(row)

    if not matched:
        raise HTTPException(status_code=404, detail="Fixable-interest cluster not found")

    await db.commit()
    return {
        "status": "ok",
        "cluster_id": cluster_id,
        "updated_count": len(matched),
        "triage_status": status,
    }


@router.get("/export")
async def export_judgments(request: Request, db: AsyncSession = Depends(get_db), secret: str = Query(None)):
    _check_admin_secret(secret, request=request)

    rows = (
        await db.execute(
            select(RankingJudgment).order_by(RankingJudgment.created_at)
        )
    ).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "date", "surface", "rank_seen", "item_type", "market_id",
        "market_name", "label", "reason_tags", "better_than", "worse_than",
        "notes", "score_at_review", "category_at_review", "archetype_at_review",
        "quality_class_at_review", "headline_at_review", "feed_request_id",
        "label_metadata", "card_snapshot", "reviewer",
    ])
    for j in rows:
        writer.writerow([
            j.date, j.surface, j.rank_seen, j.item_type, j.market_id,
            j.market_name, j.label, ",".join(canonical_reason_tags(j.reason_tags)),
            j.better_than, j.worse_than, j.notes, j.score_at_review,
            j.category_at_review, j.archetype_at_review, j.quality_class_at_review,
            j.headline_at_review, j.feed_request_id,
            json.dumps(j.label_metadata or {}, sort_keys=True),
            json.dumps((j.label_metadata or {}).get("card_snapshot") or {}, sort_keys=True),
            j.reviewer,
        ])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ranking_judgments.csv"},
    )


# ---------------------------------------------------------------------------
# Eval-ready labeled dataset export
# ---------------------------------------------------------------------------

_SPLIT_SALT = "bainluck-discover-labels-v1"


def _reviewer_hash(reviewer: str | None) -> str:
    """Deterministic pseudonymous reviewer ID (no PII in export)."""
    raw = str(reviewer or "anonymous")
    return hashlib.sha256(f"{_SPLIT_SALT}:{raw}".encode("utf-8")).hexdigest()[:12]


def _dataset_split(market_id: int | None, event_id: int | None) -> str:
    """Deterministic train/dev/test split based on market_id hash.

    80/10/10 split. Hash-based on item id for reproducibility —
    the same market always lands in the same split.
    """
    item_key = str(market_id or event_id or 0)
    digest = hashlib.md5(
        f"{_SPLIT_SALT}:{item_key}".encode("utf-8")
    ).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


def _eval_row_from_judgment(judgment: RankingJudgment) -> dict[str, Any]:
    """Build one eval-ready row from a RankingJudgment, with no PII."""
    metadata = judgment.label_metadata if isinstance(judgment.label_metadata, dict) else {}
    snapshot = metadata.get("card_snapshot") if isinstance(metadata, dict) else {}
    if not isinstance(snapshot, dict):
        snapshot = {}

    return {
        "market_id": judgment.market_id,
        "event_id": judgment.event_id,
        "market_name": judgment.market_name or "",
        "reviewer_hash": _reviewer_hash(judgment.reviewer),
        "label": judgment.label,
        "timestamp": judgment.created_at.isoformat() if judgment.created_at else None,
        "split": _dataset_split(judgment.market_id, judgment.event_id),
        "category": judgment.category_at_review or snapshot.get("category") or "",
        "source": snapshot.get("source") or "",
        "archetype": judgment.archetype_at_review or snapshot.get("archetype") or "",
        "quality_class": judgment.quality_class_at_review or snapshot.get("quality_class") or "",
        "score_at_review": judgment.score_at_review,
        "rank_seen": judgment.rank_seen,
        "rendered_probability": snapshot.get("rendered_probability"),
        "story_key": snapshot.get("story_key") or "",
        "family_key": snapshot.get("family_key") or "",
        "group_id": snapshot.get("group_id") or "",
        "has_hook": bool(snapshot.get("hook_description")),
        "has_image": bool(snapshot.get("image_url")),
        "reason_tags": canonical_reason_tags(judgment.reason_tags),
        "surface": judgment.surface or "discover",
        "item_type": judgment.item_type or "futures",
    }


@router.get("/eval-export")
async def export_eval_dataset(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str | None = Query(None),
    fmt: str = Query("json", description="Output format: json or csv"),
    days: int = Query(90, ge=1, le=365),
    split: str | None = Query(None, description="Filter to train/dev/test split"),
    label: str | None = Query(None, description="Filter by label"),
    surface: str | None = Query(None),
    limit: int = Query(10000, ge=1, le=50000),
):
    """Export eval-ready labeled dataset with hashed reviewers and train/dev/test splits.

    Returns JSON by default. Set fmt=csv for CSV download.
    No PII is included — reviewer emails are hashed.
    """
    if not await _authorize_admin(secret, request, db):
        raise HTTPException(status_code=403, detail="Admin access required")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = (
        select(RankingJudgment)
        .where(RankingJudgment.created_at >= cutoff)
        .order_by(RankingJudgment.created_at.desc())
        .limit(limit)
    )
    if surface:
        query = query.where(RankingJudgment.surface == surface)
    if label:
        query = query.where(RankingJudgment.label == label)

    result = await db.execute(query)
    all_rows = [_eval_row_from_judgment(j) for j in result.scalars().all()]

    if split:
        all_rows = [r for r in all_rows if r["split"] == split]

    split_counts = {}
    label_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for row in all_rows:
        split_counts[row["split"]] = split_counts.get(row["split"], 0) + 1
        label_counts[row["label"]] = label_counts.get(row["label"], 0) + 1
        category_counts[row["category"] or "unknown"] = (
            category_counts.get(row["category"] or "unknown", 0) + 1
        )

    if fmt == "csv":
        output = io.StringIO()
        if all_rows:
            writer = csv.DictWriter(output, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            for row in all_rows:
                csv_row = dict(row)
                csv_row["reason_tags"] = ",".join(csv_row.get("reason_tags") or [])
                writer.writerow(csv_row)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=discover_labels_eval.csv"
            },
        )

    return {
        "total": len(all_rows),
        "split_counts": split_counts,
        "label_counts": label_counts,
        "category_counts": category_counts,
        "rows": all_rows,
    }


# ── Curation Signals (iOS Share Sheet / quick curator input) ──


class CurationSignalInput(BaseModel):
    url: str
    signal: str = "boost"
    notes: str | None = None
    source_device: str | None = None


@router.post("/curation-signal")
async def create_curation_signal(
    request: Request,
    body: CurationSignalInput, secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Record a boost/demote signal from the curator.

    Designed for fast input from iOS Share Sheet shortcut.
    Parses Kalshi/Polymarket URLs to extract market identifiers.
    """
    _check_admin_secret(secret, request=request)

    import re
    from app.models.models import CurationSignal, FuturesMarket
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    url = body.url.strip()
    signal = body.signal.lower()
    if signal not in ("boost", "demote"):
        raise HTTPException(status_code=400, detail="signal must be 'boost' or 'demote'")

    # Parse platform and ticker from URL
    source_platform = None
    market_ticker = None

    # Strip query params and fragments before parsing
    clean_url = url.split("?")[0].split("#")[0]

    if "kalshi.com" in url:
        source_platform = "kalshi"
        parts = clean_url.rstrip("/").split("/")
        market_ticker = parts[-1].upper() if parts else None
    elif "polymarket.com" in url:
        source_platform = "polymarket"
        m = re.search(r"/event/([^?#/]+)", clean_url)
        if m:
            market_ticker = m.group(1)
    elif url.startswith("bainluck://"):
        source_platform = "internal"
        m = re.search(r"bainluck://(?:futures|tournament)/(\d+)", url)
        if m:
            market_ticker = m.group(1)

    # Try to find the market in our DB and get rich context
    market_id = None
    market_name = None
    market_score = None
    market_category = None
    outcome_count = 0
    db_status = "not_found"

    if market_ticker:
        from app.models.models import FuturesOutcome
        from app.utils.futures_highlights import compute_futures_highlight

        if source_platform == "kalshi":
            result = await db.execute(
                select(FuturesMarket).where(
                    FuturesMarket.source == "kalshi",
                    FuturesMarket.external_id == market_ticker,
                ).limit(1)
            )
            market = result.scalar_one_or_none()
        elif source_platform == "polymarket":
            result = await db.execute(
                select(FuturesMarket).where(
                    FuturesMarket.source == "polymarket",
                    FuturesMarket.external_id.ilike(f"%{market_ticker}%"),
                ).limit(1)
            )
            market = result.scalar_one_or_none()
        elif source_platform == "internal":
            result = await db.execute(
                select(FuturesMarket).where(
                    FuturesMarket.id == int(market_ticker),
                ).limit(1)
            )
            market = result.scalar_one_or_none()
        else:
            market = None

        if market:
            market_id = market.id
            market_name = market.name
            market_category = market.llm_sport_category or market.category
            db_status = market.status or "open"

            oc_result = await db.execute(
                select(func.count()).where(FuturesOutcome.market_id == market.id)
            )
            outcome_count = oc_result.scalar() or 0

            highlight = compute_futures_highlight(
                market_name=market.name,
                sport_category=market.llm_sport_category,
                market_tier=market.market_tier,
            )
            market_score = round(highlight.score)

    cs = CurationSignal(
        url=url,
        source_platform=source_platform,
        market_ticker=market_ticker,
        signal=signal,
        notes=body.notes,
        source_device=body.source_device or "unknown",
        market_id=market_id,
        processed=True,
    )
    db.add(cs)

    # Apply score adjustment directly to the market
    BOOST_ADJ = 15
    DEMOTE_ADJ = -25
    adj = BOOST_ADJ if signal == "boost" else DEMOTE_ADJ
    if market_id:
        from sqlalchemy import text as sa_text
        await db.execute(
            sa_text("""
                UPDATE futures_markets
                SET curation_score_adj = COALESCE(curation_score_adj, 0) + :adj
                WHERE id = :mid
            """),
            {"adj": adj, "mid": market_id},
        )

    await db.commit()

    # Build a human-readable summary for the shortcut notification
    icon = "👍" if signal == "boost" else "👎"
    if market_name:
        short_name = market_name[:50] + ("..." if len(market_name) > 50 else "")
        summary = f"{icon} {short_name} — score {market_score}, {outcome_count} outcomes, {db_status}"
    else:
        summary = f"{icon} Recorded — market not in DB yet (will be ingested on next poll)"

    return {
        "status": "recorded",
        "signal": signal,
        "summary": summary,
        "platform": source_platform,
        "ticker": market_ticker,
        "market_id": market_id,
        "market_name": market_name,
        "market_score": market_score,
        "market_category": market_category,
        "outcome_count": outcome_count,
        "db_status": db_status,
    }


@router.get("/curation-signals")
async def list_curation_signals(
    request: Request, secret: str = Query(None),
    processed: bool | None = Query(None),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    """List curation signals, optionally filtered by processed status."""
    _check_admin_secret(secret, request=request)

    from app.models.models import CurationSignal

    query = select(CurationSignal).order_by(desc(CurationSignal.created_at)).limit(limit)
    if processed is not None:
        query = query.where(CurationSignal.processed == processed)

    result = await db.execute(query)
    signals = result.scalars().all()

    return {
        "total": len(signals),
        "signals": [
            {
                "id": s.id,
                "url": s.url,
                "platform": s.source_platform,
                "ticker": s.market_ticker,
                "signal": s.signal,
                "notes": s.notes,
                "device": s.source_device,
                "processed": s.processed,
                "market_id": s.market_id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in signals
        ],
    }
