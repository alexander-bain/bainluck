"""#5809 completed — the age mark dates the legs the card ACTUALLY PRINTS.

## What was left open, and by whom

#5809's first half narrowed `price_observed_at` from `MAX` over every leg of a
market to `MIN` over its top three BY PROBABILITY, and shipped saying so:

    Top-N-by-probability is a close PROXY for "displayed", not an identity.
    `feed.py` applies `_strip_mixed_binary_meta` and
    `drop_dominant_field_outcomes` before its slice, so on a card whose filters
    drop a high-probability leg the two sets diverge by one row and the fold can
    read a leg the card does not print.

That is this file. The printed legs are the top three of a list that has been
through `drop_duplicate_legs`, the expired-rung gate, the fabricated-book gate,
`display_rank_order`, `drop_incoherent_ladder_outcomes`,
`_strip_mixed_binary_meta` and `drop_dominant_field_outcomes` — and the two
futures serializers do not even apply the same chain as each other. One of those
filters reads the REQUEST's clock. So no rule evaluated at snapshot-build time
can name the set a given card will print, which is why the carrier changed
(`price_observed_epoch`, one derived int per outcome) rather than the fold being
made cleverer.

## WHY THIS FILE IS SEPARATE FROM `test_card_price_age_fold_5809.py`

They fail for different reasons, and one cannot cover the other:

* that file fails when the FOLD is wrong about a set it was handed;
* this one fails when the SET IS WRONG — when the fold is handed legs the reader
  cannot see, or not handed ones they can.

A unit test of the fold cannot see the second class at all, which is exactly how
the residue survived the first half with 72 assertions green over it. So every
assertion here runs the REAL `_score_futures` and reads the served dict — the
same rule `test_score_futures_serves_no_diagnostic_headline_4160` states: a ban
on a producer is not a ban on a surface, and a guard has to stand where the
surface is.

## THE SPECIMEN, AND WHY IT IS MANUFACTURED

Stated rather than papered over. The defect needs a market that is BOTH filtered
AND non-uniformly stamped, and the live slate at 2026-09-13 05:00Z has no such
card — the non-uniform population is real (oldest-2,000 open markets: Kalshi
14.3%, Polymarket 64.7%) but concentrated away from the filtered shapes. The
production evidence for the CLASS is #5809's own measurement (1 of 38 served
cards dated by an invisible leg; 890 of 26,971 open markets carry a leader more
than an hour behind their market max); the evidence for the FILTER half is the
two issues that created the filters, #235 item 2 and UX-P163, both of which
record a live card whose printed list differed from its probability order.

    SHIP     red against the parent. This is the change.
    GUARD    green against the parent, red against a named mutant.
    CONTROL  green against both.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils import futures_market_snapshot as fms
from app.utils.personalization import PersonalizationContext

UTC = timezone.utc

#: The two instants every fixture here is built from. `STALE` is the age of the
#: specimen in #5809's own measurement — 23 hours — and `FRESH` is inside
#: `PriceAgeMark`'s thirty-minute silence, so the difference between the two
#: rules is the difference between a mark and no mark.
NOW = datetime(2026, 9, 13, 4, 0, tzinfo=UTC)
STALE = NOW - timedelta(hours=23)
FRESH = NOW - timedelta(minutes=4)

CANONICAL_KEY = "displayed-price-age-5809"


class _Outcome:
    def __init__(self, id, name, probability, last_updated):
        self.id = id
        self.name = name
        self.external_id = f"leg-{id}"
        self.current_probability = probability
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.opening_captured_at = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        # A readable two-sided book, so the fabricated-midpoint gate (UX-P011)
        # keeps every leg. A fixture whose legs were all phantom-dropped would
        # serve an empty card and pass this file vacuously.
        self.current_yes_bid = max(0.01, (probability or 0.5) - 0.02)
        self.current_yes_ask = min(0.99, (probability or 0.5) + 0.02)
        self.last_updated = last_updated


class _Market:
    """A real object, so the `__dict__.get(...)` reads the folds use work."""

    def __init__(self, id, name, outcomes, *, category="politics"):
        self.id = id
        self.name = name
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = category
        self.llm_sport_category = category
        self.market_tier = 1
        self.market_type = "outright"
        self.canonical_market_key = CANONICAL_KEY
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.image_width = None
        self.image_height = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250_000
        self.updated_at = NOW
        self.commence_time = NOW - timedelta(days=1)
        self.resolution_date = NOW + timedelta(days=90)
        self.status = "open"
        self.created_at = NOW - timedelta(days=30)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes


# ── the three shapes whose PRINTED list is not their probability order ──────


def _mixed_binary_market():
    """#235 item 2: a Yes/No parent binary merged into a nominee field.

    The generic pair OUT-PRICES every nominee and is stripped before the slice,
    so the printed legs are the three nominees — and the third of them ranks
    FIFTH on raw probability, which is what makes the two rules disagree.

    THE STAMPS ARE ARRANGED IN THE HARMFUL DIRECTION, deliberately: everything
    in the raw top three is FRESH and the promoted nominees are a day old. So
    the parent rule serves a stamp inside `PriceAgeMark`'s thirty-minute silence
    while the card prints prices that are 23 hours old, and the disclosure goes
    out on exactly the card it exists for. Reversing this (stale hidden legs,
    fresh printed ones) would make the parent merely over-cautious, which is a
    cosmetic defect and not the one #5809 was filed on.
    """
    return _Market(
        5809_01,
        "Who will Taylor Swift's bridesmaids be?",
        [
            _Outcome(1, "No", 0.645, FRESH),
            _Outcome(2, "Yes", 0.355, FRESH),
            _Outcome(3, "Gigi Hadid", 0.31, FRESH),
            _Outcome(4, "Selena Gomez", 0.22, STALE),
            _Outcome(5, "Blake Lively", 0.18, STALE),
            _Outcome(6, "Karlie Kloss", 0.04, FRESH),
        ],
    )


def _dominant_field_market():
    """UX-P163 / market 112903: a ~100% field row inside a three-row card.

    `display_rank_order` demotes that row to the end and
    `drop_dominant_field_outcomes` then removes it outright; on a four-row
    market either alone keeps it off the card, and this fixture does not claim
    to separate them — UX-P163's own three-row specimen is what needs the drop,
    and `test_other_at_100_leaves_the_top_n` owns that boundary. What it does
    establish is the thing this file is about: the row ranked FOURTH is printed
    while the row ranked FIRST is not, so a fold over the raw top three reads a
    set the reader never sees.

    Same arrangement as above and for the same reason: the raw top three are all
    fresh, the promoted leg is a day old, and the parent rule therefore draws
    nothing.
    """
    return _Market(
        5809_02,
        "Which party will win the House in 2026?",
        [
            _Outcome(11, "Other", 1.0, FRESH),
            _Outcome(12, "Democratic Party", 0.60, FRESH),
            _Outcome(13, "Republican Party", 0.30, FRESH),
            _Outcome(14, "Independent", 0.10, STALE),
        ],
    )


def _duplicate_leg_market():
    """Q480: one condition, one leg. The duplicate is dropped BEFORE the sort.

    A third filter, and a different mechanism from the two above — this one
    de-duplicates by `external_id` rather than by name or price — so a fix that
    happened to special-case the other two would still be caught.
    """
    duplicated = _Outcome(21, "Yes", 0.62, FRESH)
    twin = _Outcome(22, "Yes", 0.62, FRESH)
    twin.external_id = duplicated.external_id
    return _Market(
        5809_03,
        "Will the bill pass before December?",
        [
            duplicated,
            twin,
            _Outcome(23, "Amended and passed", 0.24, FRESH),
            _Outcome(24, "Withdrawn", 0.14, STALE),
        ],
    )


# ── running the real scorer ─────────────────────────────────────────────────


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _serve(markets):
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={CANONICAL_KEY: 2}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        return await _score_futures(
            _mock_db(markets), NOW, None, PersonalizationContext()
        )


async def _served_card(market):
    """The one futures item the scorer produced, or a failure that says why.

    The eligible denominator, stated every time: a fixture the pipeline drops is
    the classic way a guard on a served value passes having proved nothing.
    """
    items = await _serve([market])
    futures = [i for i in items if i["type"] == "futures"]
    assert len(futures) == 1, f"the fixture card was not served: {items}"
    # `futures_data` is nested under `data`; the scorer wraps every item in a
    # ranking envelope. Reaching in here rather than at each call site so a
    # later shape change is one edit, not fourteen.
    return futures[0]["data"]


def _printed_names(card) -> list[str]:
    return [o["name"] for o in card["top_outcomes"]]


def _observations_of(market, names) -> list[datetime]:
    """The `last_updated` of the market's legs whose names the card printed.

    By NAME, off the card, rather than by reconstructing the filter chain here —
    a helper that re-derived the printed set would be the same proxy this file
    exists to refuse, and it would agree with a broken serializer.
    """
    by_name = {o.name: o.last_updated for o in market.outcomes}
    return [by_name[name] for name in names if name in by_name]


# ══════════════════════════════════════════════════════════════════════════
# 1. THE SHIP — a filtered card is dated by what it shows
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "build, hidden_leader",
    [
        pytest.param(_mixed_binary_market, "No", id="mixed-binary-parent"),
        pytest.param(_dominant_field_market, "Other", id="dominant-field-row"),
        pytest.param(_duplicate_leg_market, None, id="duplicate-leg"),
    ],
)
async def test_ship_the_served_age_is_the_age_of_the_printed_legs(
    build, hidden_leader
):
    """SHIP: red against the parent, on all three filter shapes.

    The parent folds the top three by probability at build time, which on each
    of these markets includes at least one leg the filters remove — and those
    removed legs are the FRESH ones, so the parent serves `FRESH` and the mark
    goes silent over prices that are a day old.
    """
    market = build()
    card = await _served_card(market)
    printed = _printed_names(card)

    assert printed, "the card printed no legs — the fixture proves nothing"
    if hidden_leader is not None:
        assert hidden_leader not in printed, (
            f"{hidden_leader!r} was supposed to be filtered off this card; the "
            "fixture no longer discriminates between the two rules"
        )

    expected = min(_observations_of(market, printed))
    assert card["price_observed_at"] == expected.isoformat()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "build",
    [_mixed_binary_market, _dominant_field_market, _duplicate_leg_market],
)
async def test_control_the_parent_rule_would_have_served_the_hidden_stamp(build):
    """CONTROL: the specimen actually discriminates, computed not asserted.

    Without this, all three fixtures above could be markets on which the old and
    new rules agree, and the suite would be green on the parent. The old rule is
    recomputed here from the market — MIN over the top three BY PROBABILITY —
    and the assertion is that it DIFFERS from what the card now serves.
    """
    market = build()
    card = await _served_card(market)

    by_probability = sorted(
        market.outcomes,
        key=lambda o: o.current_probability or -1.0,
        reverse=True,
    )[: fms.CARD_PRICE_AGE_LEG_COUNT]
    parent_rule = min(o.last_updated for o in by_probability)

    assert card["price_observed_at"] != parent_rule.isoformat()
    assert parent_rule == FRESH


@pytest.mark.asyncio
async def test_ship_the_mark_is_drawn_where_the_parent_suppressed_it():
    """The reader-visible consequence, as a threshold rather than a vibe.

    `PriceAgeMark` draws nothing below thirty minutes. That is the whole defect:
    not a wrong number printed, a true disclosure withheld.
    """
    market = _mixed_binary_market()
    card = await _served_card(market)

    served_age = NOW - datetime.fromisoformat(card["price_observed_at"])

    assert served_age > timedelta(minutes=30)
    assert NOW - FRESH < timedelta(minutes=30)


# ══════════════════════════════════════════════════════════════════════════
# 2. THE INVARIANT — true of every card, not just the specimens
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "build",
    [_mixed_binary_market, _dominant_field_market, _duplicate_leg_market],
)
async def test_guard_the_stamp_is_supported_by_every_printed_price(build):
    """GUARD: the mark may never be NEWER than a price the card prints.

    The invariant stated in the direction that matters. Over-stating the age is
    a cosmetic loss; under-stating it is the lie, because a reader takes the
    mark as vouching for every number above it.

    Mutant: `max` for `min` in `displayed_price_stamp`. The three tests above
    would still pass on the mixed-binary fixture (its printed legs share one
    stamp); this one fails the moment any card prints two different ages.
    """
    market = build()
    card = await _served_card(market)
    served = datetime.fromisoformat(card["price_observed_at"])

    for stamp in _observations_of(market, _printed_names(card)):
        assert served <= stamp, (
            "the served age is newer than a price on the card, so the mark "
            "vouches for a number it cannot support"
        )


@pytest.mark.asyncio
async def test_guard_a_leg_the_card_shows_and_nobody_polled_is_ignored():
    """GUARD: an unstamped printed leg is not evidence about the stamped ones.

    This module's rule everywhere, and the direction is deliberate — `None` here
    would delete a disclosure that the other two legs fully support.

    Mutant: return `None` when ANY printed leg is unstamped.
    """
    market = _Market(
        5809_04,
        "Who wins the nomination?",
        [
            _Outcome(31, "Front-runner", 0.44, STALE),
            _Outcome(32, "Never polled", 0.33, None),
            _Outcome(33, "Third", 0.23, STALE),
        ],
    )

    card = await _served_card(market)

    assert card["price_observed_at"] == STALE.isoformat()


@pytest.mark.asyncio
async def test_guard_a_card_nobody_polled_at_all_serves_none_not_now():
    """GUARD: `None`, never a substituted "now".

    Mutant: `or datetime.now(timezone.utc)` on this path. Every other test here
    supplies a stamp and stays green, while a market we have never observed
    starts telling readers it was priced this second — the one failure a
    freshness disclosure cannot have (`lib/sourceAge`: ABSENT IS NOT ZERO).
    """
    market = _Market(
        5809_05,
        "Who wins the nomination?",
        [
            _Outcome(41, "Front-runner", 0.44, None),
            _Outcome(42, "Second", 0.33, None),
            _Outcome(43, "Third", 0.23, None),
        ],
    )

    card = await _served_card(market)

    assert card["price_observed_at"] is None
    # Served as a null rather than omitted — #2088's rule: null is "checked and
    # there is no stamp", absence is "a payload from before this shipped", and
    # the client keys its fallback on the difference.
    assert "price_observed_at" in card


# ══════════════════════════════════════════════════════════════════════════
# 3. THE CACHED FEED IS THE SAME FEED
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "build",
    [_mixed_binary_market, _dominant_field_market, _duplicate_leg_market],
)
async def test_guard_the_snapshot_carrier_serves_the_identical_string(build):
    """GUARD: the shared artifact is a cheaper feed, never a different one.

    Discover's flagship path serves rehydrated rows, whose outcomes do not carry
    `last_updated` at all. Before the completion the answer for them came off a
    market-level column folded at build time; now each leg carries its own
    derived second, so the same filters applied to the same market must produce
    the same string on both carriers — through the REAL serializer, over a
    round-tripped payload, not by comparing two folds.

    Mutant: read `last_updated` off the legs instead of the derived second.
    Every ORM-carrier test above stays green and every cached card loses its
    mark, which is the half of the feed that matters most.
    """
    direct_card = await _served_card(build())
    rebuilt = fms.from_plain(fms.to_plain([build()]))[0]
    cached_card = await _served_card(rebuilt)

    assert cached_card["price_observed_at"] == direct_card["price_observed_at"]
    assert _printed_names(cached_card) == _printed_names(direct_card)


@pytest.mark.asyncio
async def test_control_the_rebuilt_legs_really_have_lost_the_raw_column():
    """CONTROL: the test above is not passing because nothing was dropped.

    If a rebuilt outcome still carried `last_updated`, the parity assertion
    would hold for the wrong reason and the derived column could be removed
    without a single red. This is the assertion that makes it load-bearing.
    """
    rebuilt = fms.from_plain(fms.to_plain([_mixed_binary_market()]))[0]

    for leg in rebuilt.outcomes:
        assert not hasattr(leg, "last_updated")
    assert any(leg.price_observed_epoch is not None for leg in rebuilt.outcomes)
