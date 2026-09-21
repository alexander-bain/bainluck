"""#7747 — a board stops crowning the leg nobody has bid above four cents.

WHAT A READER SAW, on production 2026-09-21. `/futures/61308736` ("2027 US Open
Men's Singles Winner") printed, in the page's largest type:

    74%
    Jakub Mensik
    Resolves Sep 20, 2027

ranked #1 above Jannik Sinner 31% and Carlos Alcaraz 27%, and repeated the card
in the "MORE TENNIS" rail of every live tennis event page.

Read at the venue the same morning — Kalshi's own `/trade-api/v2/markets/
KXATP-27USO-MEN`, not our mirror (notices 26/27):

    yes_bid 0.0400 (size 7)      yes_ask 0.7400 (size 171)
    no_bid  0.2600 (size 171)    last_price 0.7400
    volume_24h 0.00              liquidity 0.0000              status active

Every actual YES buyer on that book is at three or four cents, 45 contracts in
all. The 0.74 is the far side: `yes_ask` is `1 - no_bid`, quoted at the same 171
size, i.e. the mirror of a NO bid rather than an independent YES offer.

🔴 THE FIXTURE IS THE SPECIMEN. Every row in `USOPEN_2027` is a real production
row of market 61308736, book and newest Kalshi trade included, so the numbers
this file asserts are the numbers a reader met. Its most useful property is that
the SHIPPED screen already withholds exactly nine of these legs, which is what
production served (`prices_withheld: 9`) — so any drift in this fixture shows up
as the shipped count moving, not as a silent strawman.

🪤 THE CONTROLS ARE ON THE SPECIMEN'S OWN BOARD, which is why they are worth
more than invented ones:

  * Casper Ruud  — 0.03 on a 0.0000/0.5700 book. The spread is 0.57, WIDER than
    Mensik's, and he must keep his price: the rule is about printing the TOP of
    an unlocated spread, never about the spread alone. A rule that refused Ruud
    would delete an honest longshot.
  * Jannik Sinner — 0.31 on a 0.0700/0.5500 book, spread 0.48, one cent under
    the bound. He is the board's leader after the fix, so a rule that reached
    one cent further would blank the replacement hero too.
  * Alexander Zverev and five more — 0.01 on a 0.0000/0.7400 book. Same ask as
    Mensik, same spread, price at the BID end. Six legs that isolate "at the
    ask" from "wide book" on live data.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import (
    needs_unbacked_ask_evidence,
    price_is_an_unbacked_ask,
)
from app.utils.kalshi_empty_book import (
    ASK_ONLY_TRUSTED_MAX,
    BOOK_REFUTES_PRICE_EPSILON,
)

# The classifier's persisted verdict for market 61308736, copied from
# `market_metadata->'shape'` on production. `exhaustive`/`expected_winners`/
# `outcome_relation` are the three `market_is_proved_exclusive_field` reads.
USOPEN_SHAPE = {
    "v": 2,
    "shape": "field",
    "side_kind": "competitors",
    "confidence": "high",
    "exhaustive": True,
    "outcome_count": 25,
    "expected_winners": 1,
    "outcome_relation": "competitors",
    "classifier_version": 2,
}
USOPEN_METADATA = {"shape": USOPEN_SHAPE}

# (id, name, probability, yes_bid, yes_ask, newest kalshi last_price)
USOPEN_2027 = [
    (230781795, "Jakub Mensik", 0.74, 0.0400, 0.7400, 0.7400),
    (230781778, "Jannik Sinner", 0.31, 0.0700, 0.5500, 0.5500),
    (230781780, "Carlos Alcaraz", 0.27, 0.0700, 0.4700, 0.0500),
    (230781797, "Casper Ruud", 0.03, 0.0000, 0.5700, 0.0300),
    (230781801, "Andrey Rublev", 0.01, 0.0000, 0.0100, 0.0300),
    (230781799, "Luciano Darderi", 0.01, 0.0000, 0.0100, 0.0000),
    (230781779, "Alexander Zverev", 0.01, 0.0000, 0.7400, 0.0100),
    (230781781, "Felix Auger-Aliassime", 0.01, 0.0000, 0.0100, 0.0000),
    (230781783, "Flavio Cobolli", 0.01, 0.0000, 0.0100, 0.0000),
    (230781784, "Alex de Minaur", 0.01, 0.0000, 0.0100, 0.0300),
    (230781802, "Francisco Cerundolo", 0.01, 0.0000, 0.0100, 0.0000),
    (230781782, "Novak Djokovic", 0.01, 0.0000, 0.1900, 0.0100),
    (230781785, "Daniil Medvedev", 0.01, 0.0000, 0.7400, 0.0100),
    (230781786, "Ben Shelton", 0.01, 0.0000, 0.2900, 0.0100),
    (230781787, "Taylor Fritz", 0.01, 0.0000, 0.7400, 0.0100),
    (230781788, "Arthur Fils", 0.01, 0.0000, 0.7400, 0.0100),
    (230781789, "Frances Tiafoe", 0.01, 0.0000, 0.0100, 0.0000),
    (230781790, "Rafael Jodar", 0.01, 0.0000, 0.7400, 0.0100),
    (230781791, "Lorenzo Musetti", 0.01, 0.0000, 0.0100, 0.0000),
    (230781792, "Learner Tien", 0.01, 0.0000, 0.0100, 0.0000),
    (230781793, "Alexander Bublik", 0.01, 0.0000, 0.0100, 0.0000),
    (230781794, "Brandon Nakashima", 0.01, 0.0000, 0.0100, 0.0000),
    (230781796, "Jiri Lehecka", 0.01, 0.0000, 0.0100, 0.0300),
    (230781798, "Tommy Paul", 0.01, 0.0000, 0.7400, 0.0100),
    (230781800, "Valentin Vacherot", None, None, None, None),
]

#: The nine legs the SHIPPED #5611/#6846 screen already withholds — a zero bid,
#: a positive ask and a newest trade of 0.0. Production served
#: `prices_withheld: 9`, and this list reproducing that exactly is what makes
#: the fixture a replay rather than an invention.
ALREADY_WITHHELD_BY_SHIPPED_RULE = {
    "Luciano Darderi",
    "Felix Auger-Aliassime",
    "Flavio Cobolli",
    "Francisco Cerundolo",
    "Frances Tiafoe",
    "Lorenzo Musetti",
    "Learner Tien",
    "Alexander Bublik",
    "Brandon Nakashima",
}

BY_NAME = {row[1]: row for row in USOPEN_2027}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    """The newest-Kalshi-trade read, answered for EVERY leg of the board.

    🪤 It deliberately does not filter to the candidate list. A fake that
    answered only for the legs the shipped screen selects would make the
    widening untestable: Mensik would come back with no trade row, fail open on
    `has_trade_evidence`, and the test would pass against the defect.
    """

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeResult(self.rows)


def _outcome(oid, name, prob, bid, ask, *, resolution_source=None):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        resolution_source=resolution_source,
    )


def _market(
    rows=USOPEN_2027, *, metadata=USOPEN_METADATA, market_type="field", source="kalshi"
):
    return SimpleNamespace(
        id=61308736,
        name="2027 US Open Men's Singles Winner",
        source=source,
        status="open",
        market_type=market_type,
        market_metadata=metadata,
        outcomes=[_outcome(i, n, p, b, a) for i, n, p, b, a, _ in rows],
    )


async def _withheld_names(rows=USOPEN_2027, **kw):
    """The ids the route refuses, resolved back to names.

    Names rather than ids so a fixture edit cannot quietly move the assertion
    onto a different player.
    """
    from app.routes.futures import _unsupported_price_outcome_ids

    market = _market(rows, **kw)
    trades = [(i, lp) for i, _n, _p, _b, _a, lp in rows if lp is not None]
    db = _FakeSession(trades)
    ids = await _unsupported_price_outcome_ids(db, market)
    return {o.name for o in market.outcomes if o.id in ids}, db


@pytest.mark.asyncio
class TestTheReaderStopsSeeingAFavouriteNobodyWillBuy:
    """The defect, stated as the acceptance #7747 asked for."""

    async def test_mensik_loses_the_number_the_book_does_not_support(self):
        names, _ = await _withheld_names()
        assert (
            "Jakub Mensik" in names
        ), "the leg crowned at 74% off a 4c bid is exactly the ship"

    async def test_the_board_stops_naming_him_its_leader(self):
        names, _ = await _withheld_names()
        survivors = [
            (p, n)
            for _i, n, p, _b, _a, _lp in USOPEN_2027
            if p is not None and n not in names
        ]
        assert max(survivors)[1] == "Jannik Sinner", (
            "with the unbacked ask withheld the hero is the best leg somebody "
            "will actually pay for"
        )

    async def test_he_is_the_only_leg_this_arm_adds(self):
        """One leg moves on this board, and the count says which rule moved it.

        The shipped screen's nine are a separate, independently-measured set;
        asserting the union rather than the delta is how a widening hides.
        """
        names, _ = await _withheld_names()
        assert names == ALREADY_WITHHELD_BY_SHIPPED_RULE | {"Jakub Mensik"}
        assert len(names) == 10, "production served 9; the ship makes it 10"

    async def test_the_shipped_nine_are_reproduced_exactly(self):
        """If this fails the fixture has drifted and every delta above is void."""
        names, _ = await _withheld_names()
        assert names - {"Jakub Mensik"} == ALREADY_WITHHELD_BY_SHIPPED_RULE

    async def test_the_leg_is_withheld_not_dropped(self):
        """Withholding keeps the row; the reader still sees the player.

        `WITHHELD_PRICE_FIELDS` nulls the number at the serializer, so the id
        set returned here is the whole of this arm's effect on the board — no
        outcome leaves the list and `len(outcomes)` cannot move.
        """
        _names, _db = await _withheld_names()
        assert len(_market().outcomes) == 25


@pytest.mark.asyncio
class TestTheControlsOnTheSpecimensOwnBoard:
    """Live rows that must not move, each isolating one term of the rule."""

    async def test_ruud_keeps_his_price_on_a_wider_book_than_mensiks(self):
        names, _ = await _withheld_names()
        assert "Casper Ruud" not in names, (
            "0.03 on a 0.0000/0.5700 book: the spread clears the bound just as "
            "Mensik's does, and his price sits at the BID end of it. The rule "
            "is about printing the TOP of an unlocated spread, never about the "
            "spread alone — refusing Ruud would delete an honest longshot."
        )

    async def test_the_replacement_hero_is_not_blanked_too(self):
        names, _ = await _withheld_names()
        assert (
            "Jannik Sinner" not in names
        ), "spread 0.48, one cent under ASK_ONLY_TRUSTED_MAX"

    async def test_the_six_legs_sharing_mensiks_ask_are_untouched(self):
        """Same ask, same spread, price at the other end. Isolates the price term."""
        names, _ = await _withheld_names()
        same_ask = [
            n
            for _i, n, p, b, a, _lp in USOPEN_2027
            if a == 0.7400 and n != "Jakub Mensik"
        ]
        assert len(same_ask) == 6, "the fixture must keep carrying this control"
        assert not (set(same_ask) & names)

    async def test_alcaraz_keeps_a_price_his_own_trade_sits_below(self):
        """0.27 on 0.07/0.47 — spread 0.40, and the trade is 0.05. Untouched."""
        names, _ = await _withheld_names()
        assert "Carlos Alcaraz" not in names


@pytest.mark.asyncio
class TestTheRouteActuallyAsksTheNewQuestion:
    """A predicate can be right while the route never reaches it.

    The candidate screen in `_unsupported_price_outcome_ids` selected only legs
    with a zero bid before this ship, so Mensik was never a candidate and no
    trade was ever read for him. These pin the wiring, not the rule.
    """

    async def test_the_trade_read_happens(self):
        _names, db = await _withheld_names()
        assert db.statements, "the widened candidate list must reach the read"

    async def test_an_unproved_partition_is_left_alone(self):
        """Outside a proved single-winner field an upper bound is defensible."""
        unproved = {"shape": {**USOPEN_SHAPE, "outcome_relation": "unknown"}}
        names, _ = await _withheld_names(metadata=unproved)
        assert "Jakub Mensik" not in names

    async def test_a_market_the_classifier_never_shaped_is_left_alone(self):
        names, _ = await _withheld_names(metadata=None)
        assert "Jakub Mensik" not in names

    async def test_polymarket_is_not_governed_by_kalshis_book_rule(self):
        """gotcha #19: a Polymarket price legitimately sits above its own ask."""
        names, _ = await _withheld_names(source="polymarket")
        assert names == set()

    async def test_a_leg_with_no_snapshot_at_all_fails_open(self):
        """gotcha #53 — "we never looked" is not "it never traded"."""
        rows = [r for r in USOPEN_2027 if r[1] != "Jakub Mensik"]
        rows.append((230781795, "Jakub Mensik", 0.74, 0.0400, 0.7400, None))
        names, _ = await _withheld_names(rows)
        assert "Jakub Mensik" not in names


class TestRuleTwosExemptionIsIntact:
    """`price_is_unsupported` spares a leg carrying a real trade, deliberately.

    That exemption rests on the trade being INDEPENDENT information. These pin
    both halves: a trade that locates a price below the ask still acquits, and a
    trade that merely restates the ask does not.

    Measured on production 2026-09-21 over the 467 legs of proved exclusive
    Kalshi fields whose price sits at their own ask across a spread of at least
    ASK_ONLY_TRUSTED_MAX: 388 never traded, 79 traded AT the ask, and **zero**
    traded inside the spread. The exemption is protecting no independent trade
    in this population — but the acquittal below is what keeps it whole the day
    one appears.
    """

    @staticmethod
    def _p(prob, bid, ask, last, **kw):
        return price_is_an_unbacked_ask(
            "kalshi",
            kw.pop("resolution_source", None),
            prob,
            bid,
            ask,
            last,
            has_trade_evidence=kw.pop("has_trade_evidence", True),
            in_exclusive_field=kw.pop("in_exclusive_field", True),
        )

    def test_a_trade_inside_the_spread_still_acquits(self):
        assert self._p(0.74, 0.04, 0.74, 0.35) is False

    def test_a_trade_one_cent_below_the_ask_acquits(self):
        assert self._p(0.74, 0.04, 0.74, 0.73) is False

    def test_a_trade_at_the_ask_corroborates_nothing(self):
        assert self._p(0.74, 0.04, 0.74, 0.74) is True

    def test_never_traded_is_not_a_trade_at_zero(self):
        """lp 0.0 is "we looked and it has never traded", not evidence of 0."""
        assert self._p(0.98, 0.00, 0.98, 0.0) is True

    def test_absence_of_a_snapshot_fails_open(self):
        assert self._p(0.74, 0.04, 0.74, None, has_trade_evidence=False) is False
        assert self._p(0.74, 0.04, 0.74, 0.74, has_trade_evidence=False) is False


class TestTheRuleIsSymmetricAcrossBookShapes:
    """The first draft carved this to `yes_bid > 0` and was INVERTED.

    Staying clear of rule 2 by exempting a zero bid refuses a leg bid at one
    cent while sparing the identical leg bid at nothing — most lenient exactly
    where the book is weakest. A zero bid backs a 74c ask no better than 4c.
    """

    @staticmethod
    def _p(bid):
        return price_is_an_unbacked_ask(
            "kalshi",
            None,
            0.74,
            bid,
            0.74,
            0.74,
            has_trade_evidence=True,
            in_exclusive_field=True,
        )

    @pytest.mark.parametrize("bid", [0.0, 0.01, 0.04, 0.10, 0.23])
    def test_every_bid_that_fails_to_back_the_ask_is_refused(self, bid):
        assert self._p(bid) is True

    def test_a_bid_that_does_reach_the_price_is_spared(self):
        """Spread 0.49 — the book now locates the number it is printing."""
        assert self._p(0.25) is False


class TestTheBoundsAreTheModulesOwnAndAreNotRestated:
    """Both constants are imported from `kalshi_empty_book`, not re-derived.

    ASK_ONLY_TRUSTED_MAX is the measured bound on how much of the probability
    range an untaken offer may claim; BOOK_REFUTES_PRICE_EPSILON is the venue's
    own one-cent grid, halved. A copy of either would drift (the module says so
    in its own words) so these pin the boundary to the shared value rather than
    to a literal.
    """

    @staticmethod
    def _p(prob, bid, ask):
        return price_is_an_unbacked_ask(
            "kalshi",
            None,
            prob,
            bid,
            ask,
            ask,
            has_trade_evidence=True,
            in_exclusive_field=True,
        )

    def test_a_spread_exactly_at_the_bound_is_refused(self):
        ask = 0.60
        assert self._p(ask, ask - ASK_ONLY_TRUSTED_MAX, ask) is True

    def test_a_spread_one_cent_under_the_bound_is_spared(self):
        ask = 0.60
        assert self._p(ask, ask - ASK_ONLY_TRUSTED_MAX + 0.01, ask) is False

    def test_a_price_within_display_rounding_of_the_ask_is_the_ask(self):
        assert self._p(0.74 - BOOK_REFUTES_PRICE_EPSILON, 0.04, 0.74) is True

    def test_a_price_clearly_below_the_ask_is_not(self):
        assert self._p(0.74 - 0.02, 0.04, 0.74) is False


class TestSettledMeansSettled:
    """A graded row is a RESULT and this arm never touches one."""

    @staticmethod
    def _p(resolution_source):
        return price_is_an_unbacked_ask(
            "kalshi",
            resolution_source,
            1.0,
            0.04,
            0.99,
            0.99,
            has_trade_evidence=True,
            in_exclusive_field=True,
        )

    @pytest.mark.parametrize(
        "source",
        [
            "api_settlement",
            "did_not_play",
            "withdrew",
            "all_losers",
            "pass2_loser",
            "date_passed",
            "clean_resolution",
        ],
    )
    def test_a_verdict_is_never_withheld(self, source):
        assert self._p(source) is False

    def test_a_retraction_is_a_quote_again(self):
        """#6876: `ungradeable_result` asserts no winner, so it is still a quote."""
        assert self._p("ungradeable_result") is True


class TestTheCheapScreenAgreesWithTheFullPredicate:
    """`needs_unbacked_ask_evidence` is the row-only half and must never
    acquit something the full rule would refuse — that would cost the leg its
    trade read and serve it regardless.
    """

    @pytest.mark.parametrize(
        "prob,bid,ask,last",
        [
            (0.74, 0.04, 0.74, 0.74),
            (0.98, 0.00, 0.98, 0.00),
            (0.99, 0.00, 0.97, 0.99),
            (0.03, 0.00, 0.57, 0.03),
            (0.31, 0.07, 0.55, 0.55),
            (0.27, 0.07, 0.47, 0.05),
        ],
    )
    def test_the_screen_admits_everything_the_rule_refuses(self, prob, bid, ask, last):
        refused = price_is_an_unbacked_ask(
            "kalshi",
            None,
            prob,
            bid,
            ask,
            last,
            has_trade_evidence=True,
            in_exclusive_field=True,
        )
        admitted = needs_unbacked_ask_evidence(
            "kalshi", None, prob, bid, ask, in_exclusive_field=True
        )
        assert not (
            refused and not admitted
        ), "a leg the rule refuses must survive the cheap screen"

    def test_the_screen_is_not_vacuously_true(self):
        """It must actually reject, or it is not a screen."""
        assert (
            needs_unbacked_ask_evidence(
                "kalshi", None, 0.03, 0.00, 0.57, in_exclusive_field=True
            )
            is False
        )

    def test_a_missing_probability_is_not_read_as_zero(self):
        """gotcha #53 again: an unpriced leg has nothing to withhold."""
        assert (
            needs_unbacked_ask_evidence(
                "kalshi", None, None, 0.04, 0.74, in_exclusive_field=True
            )
            is False
        )
