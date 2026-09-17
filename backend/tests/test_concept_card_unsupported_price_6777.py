"""#6777 — a fight card may not lead with a price its own book refutes.

═══ WHAT A READER SAW ═══

The Power Slap 23 card led Discover with **Brandon Wilson 50% / Brian Ellis
49.5%**. Verbatim from production 2026-09-17, market `61148613`:

    outcome    name             current_probability   yes_bid   yes_ask
    229923170  Brandon Wilson              0.500000    0.0200    0.9900
    229923171  Brian Ellis                 0.495000    0.0100    0.9800

Nobody is bidding above two cents and nobody is offering below 98. A quote that
wide locates no price at all, and we printed one to three significant figures
and made it the headline of the card.

═══ THE CLAIM IS NARROW, AND THAT IS DELIBERATE ═══

Not "this market never traded" — `volume IS NULL` is UNKNOWN, not proof of zero
trades, and the first draft of #6777 leaned on it and was corrected. Not "a 50%
price is suspicious" and not "a wide spread is suspicious": neither authorises
anything by itself. The whole claim is that **this quote pair does not locate a
price here**, which is exactly the three conditions
:func:`app.utils.feed_market_quality.is_empty_book_midpoint` already applies on
five other surfaces. No new threshold and no new constant is introduced by the
change this file guards — if one ever is, the controls at the bottom go red.

═══ WHAT IS WITHHELD, AND WHAT IS NEVER TOUCHED ═══

The number, and only the number. The card keeps its page, its bouts, its
sections and both fighters' names — a refusal lands in the shape this module
already ships for an unpriced venue bout, `{"name": ..., "probability": None}`.
Nothing stored moves (gotcha #21): the builder declines to publish.

═══ THREE PLACES A NUMBER REACHES THE READER ═══

A gate that fixes one and not the others just moves the unsupported number, so
each is asserted separately here:

    1. `primary.competitors`  — the card's hero, and what the Discover leader is
                                resolved from (`_resolve_concept_leader`)
    2. `children[].outcomes`  — the bout rail on the card's page, plus the
                                child's own `probability`
    3. `headline_bout`        — attached by `_attach_headline_bouts`, which
                                reads its own projection of `futures_outcomes`
                                and is therefore a genuinely independent path

The Discover consequence is asserted too: with no supported number the envelope
yields no leader and no bout, which is what makes the card ineligible for a
Discover slot under the gate that already exists (`_concept_can_render`). That
is a card declining to advertise a number it cannot stand up — not a deletion.
"""

from __future__ import annotations

import itertools
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.feed import _bout_from_competitors
from app.utils.event_combat import (
    _DATE_TOKEN_RE,
    _attach_headline_bouts,
    printable_probabilities,
    venue_card_token,
)
from app.utils.event_ufc import UFC_CONFIG, UFCEventAdapter

_IDS = itertools.count(90000)


def _far(days: int, hour: int = 19) -> datetime:
    """A fixed instant `days` out. Offset FIRST, then truncate (gotcha #44)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


_FIGHT_START = _far(1, hour=23)
_LISTED_AT = _far(-6, hour=22)

#: The specimen's two books, verbatim from production. Named so a later reader
#: can see that the refusal rests on the stored triple and not on a shape
#: invented to make the assertion pass.
_WILSON_BOOK = (0.0200, 0.9900)
_ELLIS_BOOK = (0.0100, 0.9800)


def _outcome(name, probability, book=(None, None), resolution_source=None):
    yes_bid, yes_ask = book
    return SimpleNamespace(
        name=name,
        current_probability=probability,
        last_updated=None,
        current_yes_bid=yes_bid,
        current_yes_ask=yes_ask,
        resolution_source=resolution_source,
    )


def _venue_row(name, outcomes, event_id="1035400"):
    """A Polymarket `futures_markets` row, ORM-shaped for the adapter."""
    return SimpleNamespace(
        id=next(_IDS),
        external_id=f"0x{next(_IDS):x}",
        name=name,
        source="polymarket",
        status="open",
        commence_time=_LISTED_AT,
        market_metadata={
            "venue_game_start": _FIGHT_START.isoformat().replace("+00:00", "Z"),
            "polymarket_event_id": event_id,
        },
        outcomes=list(outcomes),
    )


_TITLE = "Power Slap 23: Brandon Wilson vs. Brian Ellis"


def _specimen_rows():
    """The card exactly as production holds it — an empty book on both sides."""
    return [
        _venue_row(
            _TITLE,
            [
                _outcome("Brandon Wilson", 0.500000, _WILSON_BOOK),
                _outcome("Brian Ellis", 0.495000, _ELLIS_BOOK),
            ],
        )
    ]


def _traded_rows():
    """The same card with a real, tight, two-sided book at the same 50%.

    The control that stops this being "we refuse coin-flips". Same price, same
    fighters, same everything — only the book differs.
    """
    return [
        _venue_row(
            _TITLE,
            [
                _outcome("Brandon Wilson", 0.500000, (0.4900, 0.5100)),
                _outcome("Brian Ellis", 0.495000, (0.4850, 0.5050)),
            ],
        )
    ]


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)

    def scalars(self):
        return self

    def unique(self):
        return self

    def first(self):
        return self._items[0] if self._items else None


class _FakeDB:
    """Dispatch on the statement text — the outcomes projection and the market
    scan are different reads and must not be fed the same list."""

    def __init__(self, markets=(), outcome_rows=()):
        self._markets = list(markets)
        self._outcome_rows = list(outcome_rows)

    async def execute(self, statement, *_a, **_k):
        sql = str(statement)
        if "futures_outcomes" in sql:
            return _FakeResult(self._outcome_rows)
        if "futures_markets" in sql:
            return _FakeResult(self._markets)
        return _FakeResult([])


async def _page(rows):
    token = venue_card_token(UFC_CONFIG, rows[0].name, rows[0].market_metadata)
    assert token, "the harness must produce a real card token"
    return await UFCEventAdapter().build_event(token, _FakeDB(markets=rows))


def _slug_target(slug: str) -> str:
    target = re.sub(r"[^a-z0-9]", "", slug.lower())
    match = _DATE_TOKEN_RE.search(target)
    return target[match.start() :] if match else target


# ═══════════════════════════════════════════════════════════════════════════
# The three places a number reaches the reader
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestTheUnsupportedNumberIsWithheldEverywhere:
    async def test_the_hero_prints_no_probability(self):
        """Path 1 — `primary.competitors`, the card's headline pair."""
        built = await _page(_specimen_rows())
        competitors = built["primary"]["competitors"]
        assert [c["name"] for c in competitors] == ["Brandon Wilson", "Brian Ellis"], (
            "both fighters must still be named — the refusal withholds the "
            "number, it does not delete the bout"
        )
        assert all(c["probability"] is None for c in competitors), (
            "0.02/0.99 does not locate a price at 50%; the hero must print no "
            f"number, got {competitors}"
        )

    async def test_the_bout_rail_prints_no_probability(self):
        """Path 2 — `children[].outcomes` and the child's own `probability`."""
        built = await _page(_specimen_rows())
        assert len(built["children"]) == 1, "the card keeps its bout"
        child = built["children"][0]
        assert {o["name"] for o in child["outcomes"]} == {
            "Brandon Wilson",
            "Brian Ellis",
        }
        assert all(o["probability"] is None for o in child["outcomes"])
        assert child["probability"] is None, (
            "the child's lead price is the same unsupported number one level up"
        )

    async def test_the_headline_bout_is_not_attached(self):
        """Path 3 — `_attach_headline_bouts`, an independent read.

        It selects its own projection of `futures_outcomes`, so it could keep
        serving the refused pair after the other two paths were fixed. "Half a
        bout is not a bout" already refuses a pair missing a number, and a
        withheld price reaches that rule the same way an absent one does.
        """
        concepts = [{"key": "event:ufc:powerslap23", "main_event_id": 7}]
        await _attach_headline_bouts(
            _FakeDB(
                outcome_rows=[
                    (7, "Brandon Wilson", 0.500000, *_WILSON_BOOK),
                    (7, "Brian Ellis", 0.495000, *_ELLIS_BOOK),
                ]
            ),
            concepts,
        )
        assert "headline_bout" not in concepts[0], (
            "an unsupported pair must attach no headline at all, rather than a "
            f"nameless or half-priced one: {concepts[0].get('headline_bout')}"
        )

    async def test_the_card_keeps_its_page_and_its_sections(self):
        """The refusal is a withheld number, never a deleted card (#6777's
        explicit bound: no card loses its real bouts)."""
        built = await _page(_specimen_rows())
        assert built is not None
        assert built["event"]["name"]
        assert _slug_target(built["event"]["slug"])
        assert built["sections"] and built["sections"][0]["market_ids"], (
            "the bout must stay reachable on the page even with no price"
        )


@pytest.mark.asyncio
class TestTheDiscoverConsequence:
    """With no supported number the envelope offers the feed nothing to lead
    with — which is what makes the card ineligible for a Discover slot under the
    gate that already exists. Asserted on the envelope the feed actually reads,
    not by re-deriving the gate here."""

    async def test_no_leader_can_be_resolved_from_the_envelope(self):
        built = await _page(_specimen_rows())
        primary = built["primary"]
        # The exact filter `_resolve_concept_leader` applies to the envelope.
        usable = [
            c
            for c in primary["competitors"]
            if isinstance(c.get("probability"), (int, float))
        ]
        assert usable == [], "no side may qualify as the card's favourite"
        assert _bout_from_competitors(primary, usable) is None, (
            "and no headline bout may be built out of the survivors"
        )

    async def test_a_traded_card_still_leads_and_still_ships(self):
        """The other direction, on the same harness: a card whose book supports
        its price is untouched, so this is a gate and not a blanket."""
        built = await _page(_traded_rows())
        primary = built["primary"]
        usable = [
            c
            for c in primary["competitors"]
            if isinstance(c.get("probability"), (int, float))
        ]
        assert len(usable) == 2, primary["competitors"]
        bout = _bout_from_competitors(primary, usable)
        assert bout is not None, "a real book must still produce a headline bout"
        assert {c["name"] for c in bout["competitors"]} == {
            "Brandon Wilson",
            "Brian Ellis",
        }


# ═══════════════════════════════════════════════════════════════════════════
# The controls — each names a class that must NOT be withheld
# ═══════════════════════════════════════════════════════════════════════════


class TestWhatIsNeverWithheld:
    """Unit-level, on the integration helper every builder calls. If a future
    change introduces its own threshold instead of delegating to Authority's
    shared predicate, these go red."""

    def test_the_specimen_is_refused_on_its_stored_triple(self):
        """Anti-vacuity: the refusal must rest on the production values above."""
        assert printable_probabilities(
            [(0.500000, *_WILSON_BOOK), (0.495000, *_ELLIS_BOOK)]
        ) == [None, None]

    def test_a_genuinely_traded_tight_book_keeps_its_fifty_percent(self):
        assert printable_probabilities([(0.50, 0.49, 0.51), (0.50, 0.49, 0.51)]) == [
            0.5,
            0.5,
        ]

    def test_a_supported_lone_ask_is_not_a_wide_book(self):
        """A one-sided book still carries information — an ask at 36c says
        nobody will sell below 36c — and those rows are honest longshots."""
        assert printable_probabilities([(0.36, None, 0.36), (0.64, None, 0.64)]) == [
            0.36,
            0.64,
        ]

    def test_a_model_price_with_no_book_is_passed_through(self):
        """The non-Polymarket control: a blended/derived price (DataGolf,
        odds_api, a complement) has no book at all and is never judged here."""
        assert printable_probabilities([(0.62, None, None), (0.38, None, None)]) == [
            0.62,
            0.38,
        ]

    def test_a_settled_side_keeps_its_number_without_a_carve_out(self):
        """"Settled means settled" — and it needs no exemption here. A graded
        side carries 0 or 1, a whole midpoint-tolerance away from any book this
        rule can reach, so condition 3 fails and the result is kept. Withholding
        it would quietly delete a result."""
        assert printable_probabilities([(1.0, *_WILSON_BOOK), (0.0, *_ELLIS_BOOK)]) == [
            1.0,
            0.0,
        ]

    def test_an_absent_price_is_still_absent(self):
        assert printable_probabilities(
            [(None, *_WILSON_BOOK), (None, *_ELLIS_BOOK)]
        ) == [None, None]


class TestTheQuantifierIsAnyForABoutAndNotForALadder:
    """The correction authority/433 named on my first build, which refused
    per-leg. Both halves are asserted, because each is a way to get it wrong."""

    def test_one_refused_side_refuses_the_pair(self):
        """A bout is ONE question with two sides. Refusing Wilson and keeping
        Ellis leaves the card leading "Brian Ellis 49.5%", whose complement is
        exactly the number just refused — #5333's defect one surface over.

        The two sides are two rows from two upserts, so nothing guarantees they
        stay algebraic complements; #6727's leg/complement invariance makes the
        specimen's own books answer alike, and this is the case it does not
        cover.
        """
        assert printable_probabilities(
            [(0.500000, *_WILSON_BOOK), (0.4700, 0.4600, 0.4800)]
        ) == [None, None], "the supported side must fall with the refused one"

    def test_a_longer_set_is_judged_side_by_side(self):
        """A ladder's rungs are SEPARATE questions — method/round/distance props
        reach this same builder. Dropping every rung because one has an empty
        book would destroy honest ones, so the pair rule fires only on a
        two-sided set and a longer one is served as it is today."""
        assert printable_probabilities(
            [
                (0.500000, *_WILSON_BOOK),
                (0.3000, 0.2900, 0.3100),
                (0.2000, 0.1900, 0.2100),
            ]
        ) == [0.5, 0.3, 0.2], "a three-rung prop must not fall to one empty book"
