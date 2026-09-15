"""#6256 — a leg that prints no number may not date the prices beside it.

## The defect, in one sentence

`displayed_price_stamp` ignored a printed leg with no readable STAMP but not one
with no readable PRICE, so a row the card renders as an em dash supplied the
`MIN` and stamped two minutes-old prices with a date from May.

## The measurement that filed it, re-verified before this file was written

Production `/api/feed?limit=40`, 2026-09-15 ~04:05Z. Market `112903`, "Which
party will win the House in 2026?", Polymarket, tier 2, position 35:

```
Democratic Party   87%
Republican Party   14%
Other               —
                                    125d ago
```

`db-query` in the same pass — both printed prices stamped
`2026-09-15 02:52:56.299697Z`, about an hour old; the seven unpriced legs
(`Other`, `Party A`–`Party F`, `current_probability NULL`) stamped
`2026-05-12 17:15:00.484580Z`, which is the served `price_observed_at` to the
microsecond.

The prices had MOVED since the issue was filed (`0.875` → `0.865`) while the
mark had not. So this is not a frozen card wearing a stale date, which would be
a caching story; it is a refreshing card wearing a date from a row that prints
nothing. The mark is not disclosing a defect — it is inventing one on top of
good data, which is the direction that costs a reader trust in the numbers that
are right.

Reach (production `db-query`, open markets only): **521** markets carry ≥3
outcomes with 1–2 of them priced and an unpriced leg ≥6h older than the newest
priced one — the window in which `PriceAgeMark` draws at all.

## Why `_top_price_observed_at`'s existing defence cannot cover it

That fold sorts an unreadable probability to `-1.0` so it is "the first thing
pushed out of the top-N window". A market with fewer than `leg_count` priced
legs has nothing to push it out WITH, so the guard is structurally unreachable
on exactly the population it exists to protect — and the futures card does not
go through that fold at all, because both serializers hand their already
filtered selection straight to `displayed_price_stamp`.

## What this file proves, and why each section is here

1. **The specimen reproduces through the REAL serializer** — not the fold alone.
   A fold-only file would pass while the serializer handed over a different set,
   which is the split `test_card_displayed_price_age_5809.py` exists to cover and
   the reason its harness is reused here.
2. **The fix did not grow.** A card whose printed legs are ALL priced is dated
   exactly as #5809 left it — the oldest of them. The mutant that deletes this
   rule is "date by the newest printed leg", and it is a strictly different fix
   wearing this one's name.
3. **Both shapes of "prints no number"** — a `NULL` price (the House specimen)
   and a stored `0.000000` (the Premier Lacrosse League specimen, whose legs are
   finalized at Kalshi) — because the issue names both and a fix that closed only
   the first would leave 128 of the 649 measured markets lying.
4. **Absent still means absent.** A card no printed leg can date serves `None`,
   never a fabricated recent stamp: gotcha #53, and #5809's "null is checked and
   we do not know" semantics.
5. **The printed number and the fold's test are ONE decision.** This is the
   anti-drift half and the reason the fix is shaped as a shared function rather
   than a second expression: the serializers used to own a private copy of
   `float(o.current_probability) if o.current_probability else None`, and a fold
   that answered "does this leg print?" with its own copy would be one edit from
   disagreeing with the card it is describing.
6. **The concept path is unharmed**, including the `__slots__` carrier that can
   read neither a price nor a stamp and must degrade rather than raise.

## What this file deliberately does NOT do

It does not fix, assert, or depend on **#6195** — the truthiness test on a
probability that is why a stored `0.000000` prints an em dash instead of `0%`.
`displayed_probability` reproduces that truthiness on purpose: its contract is
"what the card prints", not "what the price is". When #6195 lands it lands in
that one function and the age fold follows it with no second edit, which is the
whole point of the shape. Section 5 is what will go red if the two are ever
split again.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils import futures_market_snapshot as fms
from app.utils.personalization import PersonalizationContext

UTC = timezone.utc

#: The specimen's real instants, to the microsecond, from the production read
#: quoted in the module docstring.
PRICED_AT = datetime(2026, 9, 15, 2, 52, 56, 299697, tzinfo=UTC)
UNPRICED_AT = datetime(2026, 5, 12, 17, 15, 0, 484580, tzinfo=UTC)

#: What those instants look like COMING BACK OUT of the fold. The per-leg wire
#: carrier is `price_observed_epoch` — whole UTC seconds — so every stamp the
#: folds return has lost its microseconds, on the cached path and the build path
#: alike. The fixtures keep the true production instants (they are the evidence)
#: and the assertions name the truncated form, rather than quietly rounding the
#: specimen to make the arithmetic come out.
PRICED_SECOND = PRICED_AT.replace(microsecond=0)
UNPRICED_SECOND = UNPRICED_AT.replace(microsecond=0)

NOW = datetime(2026, 9, 15, 4, 5, tzinfo=UTC)
# NOT named `CANONICAL_KEY`, and the reason is worth the line: gitleaks'
# `generic-api-key` rule matched that spelling of this constant in CI (entropy
# 3.72, "leaks found: 1") purely because the NAME ends in `_KEY` and the value
# is long and hyphenated. Nothing secret was ever here, so there was nothing to
# rotate — but a red secret scan on a test fixture costs the next reader the
# twenty minutes it cost this one. The sibling
# `test_card_displayed_price_age_5809.py` uses that name and does NOT trip the
# rule, because its slug is shorter; copying it as a template is how you meet
# this.
CANONICAL_MARKET = "price-age-6256"


# ══════════════════════════════════════════════════════════════════════════
# fixtures — real instance dicts, because the folds read `__dict__` (gotcha #42)
# ══════════════════════════════════════════════════════════════════════════


class _Leg:
    """A duck-typed outcome row with a real instance dict.

    `getattr` on a deferred mapped column lazy-loads and raises `MissingGreenlet`
    inside the per-item serializer, so the folds read `__dict__` and a fixture
    that was not dict-readable would exercise a path production never takes.
    """

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
        # keeps the leg. A fixture whose legs were phantom-dropped would serve an
        # empty card and pass this file vacuously.
        base = float(probability) if probability else 0.5
        self.current_yes_bid = max(0.01, base - 0.02)
        self.current_yes_ask = min(0.99, base + 0.02)
        self.last_updated = last_updated


class _SlotsLeg:
    """`tennis_population.OutcomeRow`'s shape — a price, and no stamp column.

    It can be read for neither `__dict__` key, so both folds must reach "we do
    not know" by degrading rather than by raising.
    """

    __slots__ = ("name", "current_probability", "is_winner")

    def __init__(self, name, probability):
        self.name = name
        self.current_probability = probability
        self.is_winner = False


class _Market:
    """A real object, so the `__dict__.get(...)` reads the folds use work."""

    def __init__(self, id, name, outcomes):
        self.id = id
        self.name = name
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = "politics"
        self.llm_sport_category = "politics"
        self.market_tier = 2
        self.market_type = "outright"
        self.canonical_market_key = CANONICAL_MARKET
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
        self.resolution_date = NOW + timedelta(days=49)
        self.status = "open"
        self.created_at = NOW - timedelta(days=130)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes


def _house_market(third_leg_probability):
    """Market `112903`'s shape: two refreshing prices and a dead third row.

    `third_leg_probability` is the one axis — `None` is the House specimen's
    stored `NULL`, `Decimal("0.000000")` is the Premier Lacrosse League
    specimen's finalized leg. Both render an em dash; both must date nothing.
    """
    return _Market(
        6256_01,
        "Which party will win the House in 2026?",
        [
            _Leg(1, "Democratic Party", Decimal("0.865000"), PRICED_AT),
            _Leg(2, "Republican Party", Decimal("0.135000"), PRICED_AT),
            _Leg(3, "Other", third_leg_probability, UNPRICED_AT),
        ],
    )


# ── running the real scorer (harness shared with #5809) ─────────────────────


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


async def _served_card(market):
    """The one futures item the scorer produced, or a failure that says why.

    The eligible denominator, stated every time: a fixture the pipeline drops is
    the classic way a guard on a served value passes having proved nothing.
    """
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={CANONICAL_MARKET: 2}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_futures(
            _mock_db([market]), NOW, None, PersonalizationContext()
        )
    futures = [i for i in items if i["type"] == "futures"]
    assert len(futures) == 1, f"the fixture card was not served: {items}"
    return futures[0]["data"]


# ══════════════════════════════════════════════════════════════════════════
# 1. THE SHIP — the em-dash row stops dating the prices above it
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "third_leg_probability, id_",
    [
        pytest.param(None, "house-null-leg", id="house-null-leg"),
        pytest.param(Decimal("0.000000"), "pll-zero-leg", id="pll-zero-leg"),
    ],
)
async def test_ship_an_unpriced_printed_leg_does_not_date_the_card(
    third_leg_probability, id_
):
    """SHIP: red against the parent, on both shapes of "prints no number".

    The parent serves `2026-05-12T17:15:00+00:00` here — 125 days — under two
    prices stamped an hour earlier.
    """
    card = await _served_card(_house_market(third_leg_probability))

    printed = card["top_outcomes"]

    # THE DENOMINATOR, ASSERTED RATHER THAN ASSUMED. If a filter drops the
    # unpriced leg this fixture proves nothing at all, and it would prove it
    # silently: the served stamp would be right for the wrong reason.
    assert [o["name"] for o in printed] == [
        "Democratic Party",
        "Republican Party",
        "Other",
    ], f"the unpriced leg must be PRINTED for this test to mean anything: {printed}"
    assert printed[2]["probability"] is None
    assert printed[2]["rendered_percent"] is None, (
        "the third row must render no number — if it prints one, it is a price "
        "fact and this whole test is aimed at the wrong leg"
    )

    assert card["price_observed_at"] == PRICED_SECOND.isoformat(), (
        "the mark must be the age of the two prices the reader can see, not of "
        "the row rendering an em dash"
    )
    assert UNPRICED_SECOND.isoformat() != card["price_observed_at"]


@pytest.mark.asyncio
async def test_ship_the_mark_the_reader_sees_is_minutes_not_months():
    """The reader-visible half, stated as the reader experiences it.

    `PriceAgeMark` draws off the served instant, so the assertion that matters is
    not which row won the fold but how old the card claims to be. 125 days vs
    ~72 minutes is the defect; asserting the string alone would pass a fix that
    swapped one wrong stamp for another.
    """
    card = await _served_card(_house_market(None))

    age = NOW - datetime.fromisoformat(card["price_observed_at"])
    assert age < timedelta(hours=2), f"card claims to be {age.days}d old"
    assert age > timedelta(minutes=30), (
        "and it must still be OLD ENOUGH TO DRAW — a fix that served `now` would "
        "silence the disclosure instead of correcting it, which is the failure "
        "mode #5809 was filed on"
    )


# ══════════════════════════════════════════════════════════════════════════
# 2. THE NON-WIDENING CONTROL — #5809's rule is untouched
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_control_a_fully_priced_card_is_still_dated_by_its_OLDEST_leg():
    """CONTROL: this fix must not become "date by the newest printed leg".

    Three printed probabilities are three facts and the oldest is the only claim
    all three support (#5809). The mutant this kills substitutes `max` for `min`,
    or gates on freshness rather than on printedness — both pass section 1 and
    both re-open the defect #5809 closed, wearing this fix's name.
    """
    market = _Market(
        6256_02,
        "Which party will win the Senate in 2026?",
        [
            _Leg(11, "Democratic Party", Decimal("0.520000"), PRICED_AT),
            _Leg(12, "Republican Party", Decimal("0.480000"), UNPRICED_AT),
            _Leg(13, "Other", Decimal("0.010000"), PRICED_AT),
        ],
    )

    card = await _served_card(market)

    assert len(card["top_outcomes"]) == 3
    assert all(
        o["probability"] is not None for o in card["top_outcomes"]
    ), "every leg here is PRICED — that is the point of the control"
    assert card["price_observed_at"] == UNPRICED_SECOND.isoformat(), (
        "an OLD leg that prints a number is a price fact and still dates the "
        "card; only a leg printing nothing was ever the problem"
    )


def test_control_the_fold_ignores_a_stamp_less_leg_without_blanking_the_mark():
    """CONTROL: #5809's other pre-existing rule, unchanged.

    A printed leg with a price but no observation contributes nothing and the
    other two still date the card. A fix that conflated "no price" with "no
    stamp" — or that turned either into "the whole card is undatable" — deletes
    a disclosure that is currently correct.
    """
    legs = [
        _Leg(21, "Democratic Party", Decimal("0.865000"), PRICED_AT),
        _Leg(22, "Republican Party", Decimal("0.135000"), PRICED_AT),
        _Leg(23, "Green Party", Decimal("0.010000"), None),
    ]

    assert fms.displayed_price_stamp(legs) == PRICED_SECOND


def test_control_a_card_no_printed_leg_can_date_serves_none_not_now():
    """CONTROL: absent stays absent (gotcha #53).

    `None` is "checked, and we do not know", which every consumer reads as
    not-fresh. The tempting wrong answer here is to fall back to the unpriced
    legs "because there is nothing else", which is the defect restated as a
    fallback.
    """
    legs = [
        _Leg(31, "Other", None, UNPRICED_AT),
        _Leg(32, "Party A", Decimal("0.000000"), UNPRICED_AT),
    ]

    assert fms.displayed_price_stamp(legs) is None


# ══════════════════════════════════════════════════════════════════════════
# 3. THE ANTI-DRIFT HALF — the printed number and the fold are ONE decision
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "stored",
    [None, Decimal("0.000000"), 0.0, Decimal("0.865000"), 0.5, 1.0, Decimal("1")],
)
def test_the_fold_ignores_a_leg_EXACTLY_WHEN_the_card_prints_no_number(stored):
    """The binding this fix is shaped around, over the stored value's full range.

    Not two expressions asserted to agree — one expression, asserted to be the
    one BOTH readers take. The serializer's `top_outcomes[].probability` and the
    age fold's "is this a price fact?" are the same call, so the only way they
    can disagree is if someone re-inlines one of them, which is what the source
    scan below catches.

    `Decimal` is in the matrix because that is what the `Numeric(7, 6)` column
    actually hands over; a float-only matrix would miss a fix that worked on the
    test's types and not on production's.
    """
    printed_value = fms.displayed_probability(_Leg(41, "leg", stored, PRICED_AT))

    prices_nothing = printed_value is None
    fold_ignored_it = (
        fms.displayed_price_stamp([_Leg(41, "leg", stored, PRICED_AT)]) is None
    )

    assert prices_nothing == fold_ignored_it, (
        f"stored={stored!r} prints {printed_value!r} but the fold "
        f"{'ignored' if fold_ignored_it else 'used'} it"
    )


def test_the_printed_value_is_unchanged_from_the_expression_it_replaced():
    """The refactor moved no number on the wire — asserted, not asserted-by-hope.

    `displayed_probability` was lifted verbatim out of the two serializers. If it
    is not byte-identical to what they computed, this ship silently re-prices
    every futures card in the feed, which is a far larger blast radius than the
    defect it fixes.
    """
    for stored in [None, Decimal("0.000000"), 0.0, Decimal("0.865000"), 0.5, 1.0]:
        leg = _Leg(51, "leg", stored, PRICED_AT)
        expected = float(leg.current_probability) if leg.current_probability else None
        assert fms.displayed_probability(leg) == expected, stored


def test_neither_serializer_keeps_a_private_copy_of_the_printed_value():
    """SOURCE SCAN: the two serializers must not re-inline the decision.

    They have drifted from each other before — `_card_price_observed_at`'s own
    docstring names #1698, CERT-622 and #2088, each a column that landed on one
    serializer and missed the other. This asserts the MECHANISM (one shared call)
    rather than today's output, because the output agrees right up until the
    moment someone edits one copy.
    """
    source = Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
    text = source.read_text()

    # KEYED ON THE PRINTED-LEGS COMPREHENSION, NOT ON THE EXPRESSION ALONE.
    # `feed.py` computes that same truthiness eleven other times and every one of
    # them answers a DIFFERENT question on a field that carries no age mark: the
    # `display_rank_order` / `ladder_treatment_collapsed` /
    # `drop_incoherent_ladder_outcomes` comparators and the top-10 `outcomes_data`
    # loop decide how to ORDER and FILTER the pool, and `matched_outcomes_list`
    # is the my-teams personalization rail. A bare substring count goes red for
    # eleven reasons that are not this defect and invites whoever meets it to
    # widen a one-card ship into four ordering helpers.
    #
    # `"rank": position` is the discriminator: only the two comprehensions that
    # build the legs the card PRINTS number their rows by display position (the
    # personalization rail carries the stored `o.rank`). Asserting the PAIRING
    # rather than a fixed count of two is what makes this guard outlive the
    # serializer split — a third printed-legs list would have to take the shared
    # decision too, or arrive here red.
    flat = " ".join(text.split())

    printed_leg_lists = flat.count('"rank": position,')
    taking_the_decision = flat.count(
        '"probability": _displayed_probability(o), "rank": position,'
    )

    assert printed_leg_lists >= 2, (
        "the two futures serializers' printed-leg comprehensions were not found "
        "at all — this guard has stopped measuring anything"
    )
    assert taking_the_decision == printed_leg_lists, (
        f"{printed_leg_lists - taking_the_decision} of {printed_leg_lists} "
        "printed-leg list(s) still compute the probability privately; the age "
        "fold cannot see that decision, which is #6256"
    )
    assert text.count('"probability": _displayed_probability(o)') == 2, (
        "both futures serializers must take the shared decision — a card that "
        "discloses correctly on Discover and not on the MORE X rail is the "
        "defect, not half a fix"
    )


# ══════════════════════════════════════════════════════════════════════════
# 4. THE CONCEPT PATH — unharmed, and the carrier that can read neither
# ══════════════════════════════════════════════════════════════════════════


def test_the_concept_fold_also_stops_dating_by_a_leg_that_prints_nothing():
    """The sibling surface, closed by the same fold rather than left behind.

    `_top_price_observed_at` sorts unreadable probabilities out of the top-N
    window, but a concept card showing two legs of which only one is priced has
    nothing to push the unpriced one out with — the same structural hole, on the
    surface a guard pinned to the futures serializer would have missed.
    """
    outcomes = [
        _Leg(61, "Jannik Sinner", Decimal("0.640000"), PRICED_AT),
        _Leg(62, "Qualifier", None, UNPRICED_AT),
    ]

    assert fms._top_price_observed_at(outcomes, 2) == PRICED_SECOND


def test_the_slots_carrier_still_degrades_and_does_not_raise():
    """CONTROL: the third carrier is unchanged, and unchanged means `None`.

    A `__slots__` row has no instance dict, so it can be read for neither a price
    nor a stamp. It contributed nothing before this ship and contributes nothing
    after it — the assertion is here so that "the fold now reads a second field"
    cannot become a `MissingGreenlet` or an `AttributeError` on the one carrier
    that has neither field.
    """
    rows = [_SlotsLeg("Player A", 0.6), _SlotsLeg("Player B", 0.4)]

    assert fms.displayed_probability(rows[0]) is None
    assert fms.displayed_price_stamp(rows) is None
    assert fms._top_price_observed_at(rows, 2) is None
