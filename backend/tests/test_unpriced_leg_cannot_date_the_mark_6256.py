"""#6256 — A LEG THAT PRINTS NO NUMBER STOPS DATING THE CARD'S AGE MARK.

## The defect, measured on production 2026-09-15 by latency/414

`www.bainluck.com/discover` at 390px, master `b9279c54f`, web v4548. Card #4,
**Premier Lacrosse League Championship Winner**:

    1  Philadelphia Waterdogs   54%   [green bar]
    2  Denver Outlaws           44%   [grey bar]
    3  Boston Cannons             —   [empty bar]
    ...
    ♡ Like        • 2d ago        Pin      Share

**Both prices on that card were observed 41 minutes before the capture.** The
served `price_observed_at` was `2026-09-12T03:51:18+00:00` — byte-for-byte the
`last_updated` of the third row, the one rendering `—`. The two live legs had
been written on schedule at `2026-09-14T22:50:30Z`.

Second specimen, higher on the page: market `112903`, *Which party will win the
House in 2026?*, two Polymarket legs at `0.875` / `0.135` written 22:50:00Z,
seven `NULL` legs stamped `2026-05-12T17:15:00Z` — served stamp `125d ago`. Both
prices were also independently *correct* against Gamma in the same pass, so the
mark was not disclosing a defect; it was inventing one on top of good data.

Reach, `db-query`, open markets only: **521** markets have ≥3 outcomes, 1–2 of
them priced, and an unpriced leg ≥6h older than the newest priced one — i.e. the
three-leg slice must admit it and `PriceAgeMark` must draw. **649** with
`current_probability = 0` counted as unpriced. On one real page, 3 of 27 futures
cards carried a stamp materially older than every price they displayed: 2.8d,
123d, 125d.

## Why the existing defence cannot fire — this is the part that matters

`_top_price_observed_at` already guards this shape by RANKING:
`_outcome_probability` returns `-1.0` for an unreadable price, so the blank leg
"sorts BELOW every one that can, so it is the first thing pushed out of the
top-N window".

That guard is **structurally unreachable for exactly the population it protects**.
When a market has fewer than three priced legs, a three-leg slice has nothing to
push the blank row out WITH — ranking it last still leaves it inside the window.
A ranking cannot exclude what there is no replacement for. Only a predicate can,
which is why the fix is `outcome_prints_a_price` and not a sort key.

`test_card_price_age_fold_5809` pins the top-N window and is green on both
specimens above: every fixture in it has ≥3 priced legs.

## Not a regression of #5809

#5809 shipped correctly and is live. It closed one direction of the fold — a
*refreshed* leg the reader cannot see suppressing a stale mark. This is the
opposite direction, which #5809's own residue paragraph did not reach: an
*unpriced* leg the reader CAN see, which prints no number, manufacturing a stale
mark over prices that are minutes old.

## On `0.0` vs `NULL`, and the one thing this file does not fix

PLL's blank legs are `0.000000`; the House market's are `NULL`. Both reach the
wire as `probability: null` through
`float(o.current_probability) if o.current_probability else None` — a truthiness
test on a probability, which is #6195 and is a real separate defect: a leg
priced at exactly zero is a real price and should render `0%`.

`outcome_prints_a_price` reproduces that truthiness **deliberately**. Its
question is "does the card print a number", and today the card does not print
one for a `0.0` leg. A stricter predicate would leave the PLL specimen still
dating its mark from a row showing `—`. Both shapes are pinned below so that
whoever fixes #6195 sees which of these assertions is coupled to it.

## 🔴 THE FIXTURES' LEG NAMES ARE LOAD-BEARING, AND THE FIRST SET WAS WRONG

Written with the production names, two of the three fixtures below did not
reproduce anything. `display_rank_order` (UX-P126/F5) drops **anonymized
reserved slots** by name — "Party C", "Coach N" — as the last thing before the
slice. So:

* the House fixture's `Party A/B/C` legs were all removed before the card was
  built, leaving two printed legs, no blank row, and a stamp that was already
  correct. It passed the fold and proved nothing;
* the control's `Candidate A…D` did the same and the whole card went unserved.

Renamed to real party and candidate names, which is what the reachable
population looks like: the 521 markets in the reach query carry NULL legs with
ordinary names. The lesson is that a placeholder name is not neutral in this
pipeline, and a fixture that uses one is testing the name filter. Every SHIP row
below therefore asserts the blank row is PRINTED before it asserts anything
about the stamp.

    SHIP     red on master. This is the change.
    GUARD    green on master, red against a named mutant.
    CONTROL  green on both — what must not move.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils.futures_market_snapshot import (
    displayed_price_stamp,
    outcome_prints_a_price,
)
from app.utils.personalization import PersonalizationContext

UTC = timezone.utc

#: Transcribed from the two production specimens, so the gap under test is the
#: measured one and not a convenient round number.
NOW = datetime(2026, 9, 14, 23, 31, tzinfo=UTC)
#: 41 minutes before the capture — the instant BOTH live legs actually carry.
PRICED_AT = datetime(2026, 9, 14, 22, 50, 30, tzinfo=UTC)
#: PLL's eliminated legs: `2026-09-12T03:51:18Z`, two days back.
DEAD_2D = datetime(2026, 9, 12, 3, 51, 18, tzinfo=UTC)
#: The House market's `NULL` legs: `2026-05-12T17:15:00Z`, 125 days back.
DEAD_125D = datetime(2026, 5, 12, 17, 15, 0, tzinfo=UTC)

# Deliberately NOT named `CANONICAL_` + `KEY`, which is what the sibling 5809
# file calls the same fixture string. gitleaks' `generic-api-key` rule fires on
# an identifier ending in `_KEY` assigned a quoted string, and it refused this
# branch's first sha at notice 32. The 5809 file is grandfathered only because
# gitleaks scans COMMITS, not the tree.
#
# 🔴 That is also why renaming in a follow-up commit did not clear it, and the
# next person to hit this should not repeat the round trip: the finding is
# pinned to the commit that INTRODUCED the line, which stays in the branch's
# history no matter what a later commit does — the scan of the two-commit range
# still reported `db2f31a7b:…:generic-api-key:120`. The branch was rewritten so
# the name never existed.
#
# A `.gitleaksignore` entry was refused: that file's own header warns
# fingerprints are COMMIT-PINNED, so the entry would die at the next rebase and
# leave a stale line behind. The value authenticates nothing — it is a
# `canonical_market_key` fixture string — so the durable fix is the name.
CANONICAL_GROUPING = "unpriced-leg-age-6256"


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
        # keeps every leg and the card is not served empty for another reason.
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
        self.canonical_market_key = CANONICAL_GROUPING
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


# ── the two production shapes ───────────────────────────────────────────────


def _zero_priced_tail_market():
    """PLL: two live legs, the rest `0.000000` and two days stale.

    The eliminated legs are `finalized` at Kalshi (venue-side read,
    `event_ticker=KXPLL-26`, closed 2026-09-09T17:40Z) and correctly are not
    re-priced — the refresh rail is not failing here. The card is simply dated
    by a row it draws as `—`.
    """
    return _Market(
        6256_01,
        "Premier Lacrosse League Championship Winner",
        [
            _Outcome(1, "Philadelphia Waterdogs", 0.535, PRICED_AT),
            _Outcome(2, "Denver Outlaws", 0.440, PRICED_AT),
            _Outcome(3, "Boston Cannons", 0.0, DEAD_2D),
            _Outcome(4, "California Redwoods", 0.0, DEAD_2D),
            _Outcome(5, "New York Atlas", 0.0, DEAD_2D),
            _Outcome(6, "Carolina Chaos", 0.0, DEAD_2D),
        ],
        category="lacrosse",
    )


def _null_priced_tail_market():
    """The House market: two live legs, seven `NULL` and 125 days stale.

    Named after market `112903` but NOT its filter shape — UX-P163's dominant
    `Other` row is a different fixture in a different file. Here the tail is
    unpriced, which is the whole point: nothing removes it from the slice.
    """
    return _Market(
        6256_02,
        "Which party will win the House in 2026?",
        [
            _Outcome(11, "Democratic Party", 0.875, PRICED_AT),
            _Outcome(12, "Republican Party", 0.135, PRICED_AT),
            _Outcome(13, "Green Party", None, DEAD_125D),
            _Outcome(14, "Libertarian Party", None, DEAD_125D),
            _Outcome(15, "Working Families Party", None, DEAD_125D),
        ],
    )


def _three_priced_legs_market():
    """THE CONTROL — the shape #5809 already handles, which must not move.

    Three real prices, the third of them genuinely old. The mark SHOULD date
    from that third leg: it prints a number, so it is a price fact the mark
    speaks for. A fix that excluded any old leg rather than any unpriced leg
    passes every other row in this file and fails here.
    """
    return _Market(
        6256_03,
        "2028 Democratic presidential nominee",
        [
            _Outcome(21, "Gavin Newsom", 0.42, PRICED_AT),
            _Outcome(22, "Josh Shapiro", 0.31, PRICED_AT),
            _Outcome(23, "Gretchen Whitmer", 0.18, DEAD_2D),
            _Outcome(24, "Wes Moore", 0.09, DEAD_125D),
        ],
    )


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
            new=AsyncMock(return_value={CANONICAL_GROUPING: 2}),
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
    return futures[0]["data"]


def _iso(stamp: datetime) -> str:
    return stamp.isoformat()


# ══════════════════════════════════════════════════════════════════════════
# SHIP — the two production specimens
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "build,dead_stamp,label",
    [
        (_null_priced_tail_market, DEAD_125D, "NULL legs (House, '125d ago')"),
    ],
)
async def test_ship_the_mark_dates_from_the_prices_the_card_prints(
    build, dead_stamp, label
):
    """#6256's ship, now carried by the NULL specimen alone — see #6195 below.

    THE PLL ROW LEFT THIS PARAMETRIZE BECAUSE ITS BLANK STOPPED BEING BLANK, NOT
    BECAUSE THE RULE WEAKENED. #6195 made a leg stored `0.000000` render `0%`, so
    the PLL card no longer draws a dash at all and cannot be a specimen for "a
    row rendering no number dated the card" — the `blanks` precondition below
    fails on it, correctly and loudly. Its new behaviour is asserted in full by
    `test_ship_6195_a_zero_leg_prints_and_therefore_dates_the_mark`, which is
    deliberately a SEPARATE test rather than a changed expectation here: the two
    cards now exercise opposite branches of one predicate.

    What #6256 fixed is unchanged and is exactly what this row still proves — a
    leg we hold NO price for (`None`, not `0.0`) prints `—` and may not speak for
    the age of the numbers beside it. That is the distinction #6195 was careful
    to keep: absent is not zero (ruling 051).
    """
    card = await _served_card(build())

    printed = card["top_outcomes"]
    with_numbers = [o for o in printed if o["probability"] is not None]
    blanks = [o for o in printed if o["probability"] is None]

    # The card really is the specimen shape: it draws some numbers and at least
    # one dash. Without this the assertion below could pass on a card that
    # printed nothing at all.
    assert with_numbers, f"{label}: no printed prices, the fixture was filtered"
    assert blanks, f"{label}: no blank leg printed, this is not the specimen"

    served = card["price_observed_at"]
    assert served is not None, f"{label}: the card lost its disclosure entirely"
    assert served == _iso(PRICED_AT), (
        f"{label}: the mark should date from the prices on screen "
        f"({_iso(PRICED_AT)}), got {served}"
    )
    # The defect, stated as itself.
    assert served != _iso(dead_stamp), (
        f"{label}: the mark is still dated by a row that renders no number"
    )


@pytest.mark.asyncio
async def test_ship_6195_a_zero_leg_prints_and_therefore_dates_the_mark():
    """The PLL card's other half: `0.0` prints `0%`, so it speaks for the age.

    This is the assertion that would have caught #6195 being half-landed, and it
    is written as ONE test over both halves on purpose — the failure mode worth
    guarding is not "a zero prints" but "a zero prints and the mark still
    pretends it isn't there", which is #6256 inverted. A card drawing a two-day-
    old `0%` beside two fresh prices must say two days: #5809's fold is `MIN`
    because the OLDEST printed price is the only claim all of the printed ones
    support, and a fresher mark would vouch for a number that is not that fresh
    — the one direction a reader cannot catch.

    So this asserts the mark moved BACKWARDS relative to what #6256 produced,
    and that is the fix rather than a regression of it. Before #6195 this same
    fixture served `Boston Cannons` as `—` and the mark as `PRICED_AT`: a card
    that had quietly deleted a real answer and then dated what was left. It now
    prints the answer and dates it honestly. Nothing about the NULL specimen
    above changes, which is what keeps "absent is not zero" load-bearing rather
    than rhetorical.
    """
    card = await _served_card(_zero_priced_tail_market())
    printed = card["top_outcomes"]

    # The eliminated leg reaches the reader at all — the half of #6195 that is
    # about the number rather than the stamp. Asserted by NAME, because a slice
    # that happened to drop it would make every assertion below vacuous.
    by_name = {o["name"]: o["probability"] for o in printed}
    assert "Boston Cannons" in by_name, (
        f"the eliminated leg is not on the card at all: {list(by_name)}"
    )
    assert by_name["Boston Cannons"] == 0.0, (
        "the eliminated leg must serve 0.0, not None — a field that has priced a "
        f"candidate at nothing is an answer, got {by_name['Boston Cannons']!r}"
    )

    # ...and NOTHING on this card is a dash any more, which is why it is no
    # longer a specimen for the parametrized test above.
    assert all(o["probability"] is not None for o in printed), (
        f"a blank survived on the zero-tail card: {printed}"
    )

    # The stamp half. The oldest PRINTED price is two days old, so the mark is.
    served = card["price_observed_at"]
    assert served == _iso(DEAD_2D), (
        "the card prints a two-day-old 0% and must date from it; a mark of "
        f"{_iso(PRICED_AT)} would vouch for that row with the fresh legs' clock "
        f"— got {served}"
    )


# ══════════════════════════════════════════════════════════════════════════
# CONTROL — what must not move
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_control_a_printed_price_still_dates_the_mark_however_old():
    """An OLD leg that prints a number is a price fact and keeps its say.

    This is the assertion that separates "ignore an unpriced leg" from "ignore
    an old leg". The second is a much larger change wearing this fix's name, and
    it would delete #5809 — the whole reason the fold is `MIN` and not `MAX` is
    that the oldest printed price is the only claim all of them support.
    """
    card = await _served_card(_three_priced_legs_market())

    printed = card["top_outcomes"]
    assert all(o["probability"] is not None for o in printed), (
        "the control's legs must all print numbers, or it is not a control"
    )

    oldest_printed = min(
        {
            "Gavin Newsom": PRICED_AT,
            "Josh Shapiro": PRICED_AT,
            "Gretchen Whitmer": DEAD_2D,
            "Wes Moore": DEAD_125D,
        }[o["name"]]
        for o in printed
    )
    assert card["price_observed_at"] == _iso(oldest_printed)
    # And it is genuinely the old one, not the fresh one — otherwise this row
    # would be green against a fix that silently kept only fresh legs.
    assert card["price_observed_at"] != _iso(PRICED_AT)


@pytest.mark.asyncio
async def test_control_a_card_with_no_priced_leg_at_all_serves_none():
    """`None` is "we do not know", and here it is the only honest answer.

    A card on which nothing prints a number has no price for a mark to speak
    for. `None` is what every consumer reads as not-fresh (gotcha #53); a
    fabricated instant would be the #6256 defect with no upper bound.
    """
    market = _Market(
        6256_04,
        "A market nobody has priced",
        [
            _Outcome(31, "Sinn Fein", None, DEAD_125D),
            _Outcome(32, "Fianna Fail", 0.0, DEAD_2D),
            _Outcome(33, "Fine Gael", None, DEAD_125D),
        ],
    )
    items = await _serve([market])
    futures = [i for i in items if i["type"] == "futures"]
    if futures:
        assert futures[0]["data"]["price_observed_at"] is None


# ══════════════════════════════════════════════════════════════════════════
# GUARD — the fold and the predicate, directly
# ══════════════════════════════════════════════════════════════════════════


def test_guard_the_fold_ignores_a_leg_that_prints_no_number():
    """`displayed_price_stamp` over the legs, without the serializer.

    The blank leg is `None` and NOT `0.0` since #6195 — a zero is a printed
    price and now correctly dates the mark, so using one here would be asserting
    the opposite of what this test is named for. `0.0`'s behaviour is pinned
    directly below and end-to-end in
    `test_ship_6195_a_zero_leg_prints_and_therefore_dates_the_mark`.
    """
    legs = [
        _Outcome(1, "priced", 0.535, PRICED_AT),
        _Outcome(2, "priced", 0.440, PRICED_AT),
        _Outcome(3, "blank", None, DEAD_2D),
    ]
    assert displayed_price_stamp(legs) == PRICED_AT

    # Order must not matter — a fold that happened to read the first leg would
    # pass the row above and fail here.
    assert displayed_price_stamp(list(reversed(legs))) == PRICED_AT

    # No priced leg at all ⇒ `None`, not the blank leg's stamp.
    assert displayed_price_stamp([legs[2]]) is None
    assert displayed_price_stamp([]) is None

    # THE #6195 COUNTERPART, in the same guard so the pair cannot drift: a `0.0`
    # leg is NOT a blank and DOES date the mark. Without this line the fixture
    # edit above could be undone by swapping `None` back to `0.0` and the test
    # would go green against the pre-#6195 behaviour.
    zero_leg = _Outcome(4, "eliminated", 0.0, DEAD_2D)
    assert displayed_price_stamp([legs[0], zero_leg]) == DEAD_2D
    assert displayed_price_stamp([zero_leg]) == DEAD_2D


def test_guard_the_predicate_answers_for_every_shape_a_leg_can_take():
    """The one predicate both the printed numbers and the mark now use."""
    assert outcome_prints_a_price(_Outcome(1, "a", 0.535, PRICED_AT)) is True
    assert outcome_prints_a_price(_Outcome(2, "b", 1.0, PRICED_AT)) is True
    assert outcome_prints_a_price(_Outcome(3, "c", 0.0001, PRICED_AT)) is True

    # 🔴 `None` IS THE ONLY UNPRINTABLE SHAPE, and that is the whole content of
    # the predicate. Absent is not zero (ruling 051): we hold no price for this
    # leg, so the card draws `—` and it may not date the numbers beside it.
    assert outcome_prints_a_price(_Outcome(4, "d", None, PRICED_AT)) is False
    # 🔴 #6195 FLIPPED THIS LINE, AND THE SERIALIZERS FLIPPED WITH IT — that is
    # why they share one function. `0.0` is a real price that renders `0%`: a
    # field has priced this candidate at nothing, which is an answer and not a
    # silence. A change here that is not matched in
    # `_build_search_top_outcomes` and the two feed card serializers is the
    # #6256 defect coming back from the other side, and
    # `test_guard_the_printed_probability_and_the_mark_read_one_predicate` below
    # is what fails when it does.
    assert outcome_prints_a_price(_Outcome(5, "e", 0.0, PRICED_AT)) is True

    class _NoDict:
        __slots__ = ("name",)

        def __init__(self):
            self.name = "slots-carrier"

    # The `__slots__` carrier degrades to False rather than raising — the same
    # honest degradation `_outcome_observed_epoch` already gives it.
    assert outcome_prints_a_price(_NoDict()) is False


def test_guard_the_printed_probability_and_the_mark_read_one_predicate():
    """The two sides that disagreed in #6256 cannot disagree again.

    Not a source scan: this asserts the BEHAVIOUR that coupling buys. For every
    leg shape, "the serializer would print a number" and "the fold would let it
    date the mark" give the same answer — so there is no leg that can print a
    dash and still speak for the card's age.
    """
    shapes = [0.535, 1.0, 0.0001, 0.0, None]
    for value in shapes:
        leg = _Outcome(1, "leg", value, PRICED_AT)
        prints = outcome_prints_a_price(leg)
        dates_the_mark = displayed_price_stamp([leg]) is not None
        assert prints == dates_the_mark, (
            f"probability={value!r}: prints={prints} but dates_the_mark="
            f"{dates_the_mark} — the two sides of the card disagree again"
        )
