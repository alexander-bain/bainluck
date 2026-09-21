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

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import (
    UNBACKED_ASK_STATIC_FOR,
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

#: The touch-stamp every leg of this board carries, and the instant the rest of
#: the fixture is measured against. Production value at capture.
LAST_SEEN = datetime(2026, 9, 21, 10, 52, 29, tzinfo=timezone.utc)

#: Hours each leg's price has sat UNMOVED — `last_updated - price_changed_at`,
#: read off production for this board. `None` is a NULL `price_changed_at`.
#:
#: 🪤 THESE ARE NOT DECORATION AND THE BOARD IS NOT UNIFORM. Sinner and Alcaraz
#: moved 14 hours ago and the rest of the field has been frozen for 78, so the
#: recency term is actually exercised by the fixture rather than being constant
#: across it. Mensik's 70.0 is the number CERT-3242's repair turns on.
STATIC_HOURS = {"Jakub Mensik": 70.0, "Jannik Sinner": 14.0, "Carlos Alcaraz": 14.0}
STATIC_HOURS_DEFAULT = 78.0
STATIC_HOURS_NULL = {"Valentin Vacherot"}


def _stamps(name):
    """(price_changed_at, last_updated) for a leg, from :data:`STATIC_HOURS`."""
    if name in STATIC_HOURS_NULL:
        return None, LAST_SEEN
    hours = STATIC_HOURS.get(name, STATIC_HOURS_DEFAULT)
    return LAST_SEEN - timedelta(hours=hours), LAST_SEEN


#: A price frozen far longer than `UNBACKED_ASK_STATIC_FOR` (the specimen's own
#: 70 hours) and one that moved well inside it (Cameron Dicker's 2.0, one of the
#: four live executions CERT-3242 falsified the first cut with).
#:
#: The unit classes below are about the BOOK terms, so they hold the time term
#: fixed at STALE; the recency term has its own class and its own controls.
STALE = (LAST_SEEN - timedelta(hours=70), LAST_SEEN)
FRESH = (LAST_SEEN - timedelta(hours=2), LAST_SEEN)


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
    price_changed_at, last_updated = _stamps(name)
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"KXATP-27USO-{oid}",
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        current_american_odds=None,
        opening_probability=None,
        opening_american_odds=None,
        probability_change_24h=None,
        rank=None,
        rank_change_24h=None,
        is_winner=None,
        volume=None,
        team_id=None,
        team=None,
        resolution_source=resolution_source,
        price_changed_at=price_changed_at,
        last_updated=last_updated,
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
        names, _ = await _withheld_names()
        market = _market()
        assert names, "if nothing is withheld this asserts nothing at all"
        assert names <= {
            o.name for o in market.outcomes
        }, "the route names rows that are still ON the board"
        assert len(market.outcomes) == 25


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
            price_changed_at=STALE[0],
            last_seen_at=STALE[1],
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
            price_changed_at=STALE[0],
            last_seen_at=STALE[1],
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
            price_changed_at=STALE[0],
            last_seen_at=STALE[1],
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
            price_changed_at=STALE[0],
            last_seen_at=STALE[1],
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
            price_changed_at=STALE[0],
            last_seen_at=STALE[1],
        )
        admitted = needs_unbacked_ask_evidence(
            "kalshi",
            None,
            prob,
            bid,
            ask,
            in_exclusive_field=True,
            price_changed_at=STALE[0],
            last_seen_at=STALE[1],
        )
        assert not (
            refused and not admitted
        ), "a leg the rule refuses must survive the cheap screen"

    def test_the_screen_is_not_vacuously_true(self):
        """It must actually reject, or it is not a screen."""
        assert (
            needs_unbacked_ask_evidence(
                "kalshi",
                None,
                0.03,
                0.00,
                0.57,
                in_exclusive_field=True,
                price_changed_at=STALE[0],
                last_seen_at=STALE[1],
            )
            is False
        )

    def test_a_missing_probability_is_not_read_as_zero(self):
        """gotcha #53 again: an unpriced leg has nothing to withhold."""
        assert (
            needs_unbacked_ask_evidence(
                "kalshi",
                None,
                None,
                0.04,
                0.74,
                in_exclusive_field=True,
                price_changed_at=STALE[0],
                last_seen_at=STALE[1],
            )
            is False
        )


# --------------------------------------------------------------------------
# CERT-3242's required repair: 7747-RECENT-EXECUTED-ASK-IS-EVIDENCE
# --------------------------------------------------------------------------


def _detail(rows=USOPEN_2027, withheld_names=()):
    """The board as `_format_market_detail` serves it.

    The grader required this rule proved "through the helper AND the served
    formatter", and the two can disagree: the helper returns a SET OF IDS and the
    formatter is what turns those into nulls, so a wiring change that dropped the
    set on the floor would leave every helper test green.
    """
    from app.routes.futures import _format_market_detail

    market = _market(rows)
    market.description = None
    market.category = "sports"
    market.external_id = "KXATP-27USO"
    market.sport = None
    market.sport_id = None
    market.event_id = None
    market.market_tier = 2
    market.llm_sport_category = "tennis"
    market.mutually_exclusive = True
    market.commence_time = None
    market.resolution_date = None
    market.created_at = None
    market.updated_at = None
    market.group_id = None
    market.canonical_market_key = None
    market.hook_description = None
    market.image_url = None
    market.category_tags = []
    ids = {o.id for o in market.outcomes if o.name in set(withheld_names)}
    return _format_market_detail(market, None, ids)


def _detail_by_name(detail):
    return {row["name"]: row for row in detail["outcomes"]}


class TestRecentExecutedAskIsEvidence:
    """CERT-3242 BLOCKed the first cut and was RIGHT, so this class is the repair.

    The first cut refused EVERY price printing at its own ask over a wide spread.
    The grader falsified it against the venue in minutes — four legs that are
    being traded right now at exactly that ask:

        leg               served   book           Kalshi 24h volume
        Tunisia            0.79    0.22 / 0.79    $87.67
        Gambia             0.80    0.13 / 0.80    $54.43
        Cameron Dicker     0.52    0.00 / 0.52    $9.30
        Davante Adams      0.85    0.00 / 0.85    $6.10

    All four are served on production and all four were withheld by the staged
    code. 🔴 A trade at the ask is not evidence because it is STALE, not because
    it is at the ask — and the specimen's own diagnosis had already said so
    (`volume_24h 0.00`, `liquidity 0.0000`) while the predicate failed to encode
    it. The cross-tab that justified the first cut separated trades by PRICE; the
    axis it was missing is TIME.

    The four sit at 2.0, 6.0, 6.8 and 7.9 hours static against the specimen's
    70.0, read off `last_updated - price_changed_at` on production.
    """

    # (name, served, bid, ask, hours static) — production, 2026-09-21.
    LIVE_EXECUTIONS = [
        ("Tunisia", 0.79, 0.22, 0.79, 6.8),
        ("Gambia", 0.80, 0.13, 0.80, 6.0),
        ("Cameron Dicker", 0.52, 0.00, 0.52, 2.0),
        ("Davante Adams", 0.85, 0.00, 0.85, 7.9),
    ]

    @staticmethod
    def _p(prob, bid, ask, hours):
        return price_is_an_unbacked_ask(
            "kalshi",
            None,
            prob,
            bid,
            ask,
            ask,  # the trade IS the ask in every one of these
            has_trade_evidence=True,
            in_exclusive_field=True,
            price_changed_at=LAST_SEEN - timedelta(hours=hours),
            last_seen_at=LAST_SEEN,
        )

    @pytest.mark.parametrize("name,prob,bid,ask,hours", LIVE_EXECUTIONS)
    def test_the_four_legs_that_falsified_the_first_cut_keep_their_price(
        self, name, prob, bid, ask, hours
    ):
        assert (
            self._p(prob, bid, ask, hours) is False
        ), f"{name} is being traded at its ask right now"

    def test_the_specimen_is_still_withheld(self):
        assert self._p(0.74, 0.04, 0.74, 70.0) is True

    def test_the_bound_is_the_named_constant_and_not_a_literal(self):
        hours = UNBACKED_ASK_STATIC_FOR.total_seconds() / 3600.0
        assert self._p(0.74, 0.04, 0.74, hours) is True
        assert self._p(0.74, 0.04, 0.74, hours - 0.1) is False

    def test_a_null_price_stamp_fails_open(self):
        """gotcha #53 — 409 of 467 legs of this shape carry no stamp at all."""
        assert (
            price_is_an_unbacked_ask(
                "kalshi",
                None,
                0.74,
                0.04,
                0.74,
                0.74,
                has_trade_evidence=True,
                in_exclusive_field=True,
                price_changed_at=None,
                last_seen_at=LAST_SEEN,
            )
            is False
        )

    def test_an_ingestion_outage_cannot_blank_the_fleet(self):
        """The gap is between two columns of ONE row, so it FREEZES in an outage.

        If the poller stops, `last_updated` stops advancing with
        `price_changed_at`, so a leg that was fresh when ingestion died stays
        fresh however long the outage runs. An absolute `now - price_changed_at`
        would have turned a two-day outage into a fleet-wide blanking — this is
        #7537's structural property on the pair of columns that answers THIS
        question.
        """
        moved = LAST_SEEN - timedelta(hours=2)
        for outage_days in (0, 1, 7, 30):
            frozen_touch = LAST_SEEN  # the poller is dead; it stops advancing
            assert (
                price_is_an_unbacked_ask(
                    "kalshi",
                    None,
                    0.74,
                    0.04,
                    0.74,
                    0.74,
                    has_trade_evidence=True,
                    in_exclusive_field=True,
                    price_changed_at=moved,
                    last_seen_at=frozen_touch,
                )
                is False
            ), f"a {outage_days}-day outage must not withhold a fresh price"


@pytest.mark.asyncio
class TestRecentExecutedAskIsEvidenceEndToEnd:
    """The same rule through the ROUTE and through the SERVED FORMATTER.

    CERT-3242 named this shape explicitly, and the reason it is not redundant
    with the class above is that a predicate is not a page: the helper hands back
    ids and the formatter is what nulls the fields.
    """

    @staticmethod
    def _board_with_a_live_execution():
        """The specimen board with ONE leg repriced two hours ago.

        Alexander Zverev is given Mensik's exact book and price so the two rows
        are identical in every column this rule reads EXCEPT the time one. That
        is what makes the pair a control rather than two unrelated legs.
        """
        rows = []
        for oid, name, p, b, a, lp in USOPEN_2027:
            if name == "Alexander Zverev":
                rows.append((oid, name, 0.74, 0.0400, 0.7400, 0.7400))
            else:
                rows.append((oid, name, p, b, a, lp))
        return rows

    async def test_recent_executed_trade_at_ask_remains_priced_while_stale_zero_volume_mensik_is_withheld(
        self,
    ):
        rows = self._board_with_a_live_execution()
        # Zverev's price moved 2 hours ago; Mensik's has not moved in 70.
        STATIC_HOURS["Alexander Zverev"] = 2.0
        try:
            names, _ = await _withheld_names(rows)
            assert "Jakub Mensik" in names, "70 hours static on a 4c bid"
            assert (
                "Alexander Zverev" not in names
            ), "identical book, identical price, traded 2 hours ago"

            # ...and the same, as the reader is served it.
            detail = _detail(rows, withheld_names=names)
            served = _detail_by_name(detail)
            assert served["Jakub Mensik"]["probability"] is None
            assert served["Alexander Zverev"]["probability"] == pytest.approx(
                0.74, abs=0.01
            )
        finally:
            STATIC_HOURS.pop("Alexander Zverev", None)

    async def test_the_served_board_nulls_the_leg_and_keeps_the_row(self):
        names, _ = await _withheld_names()
        detail = _detail(withheld_names=names)
        served = _detail_by_name(detail)
        assert served["Jakub Mensik"]["probability"] is None
        assert len(detail["outcomes"]) == 25, "withheld, never dropped"
        assert detail["prices_withheld"] == 10, "the shipped 9 plus Mensik"

    async def test_the_served_hero_is_the_leg_somebody_will_pay_for(self):
        names, _ = await _withheld_names()
        detail = _detail(withheld_names=names)
        priced = [
            (o["probability"], o["name"])
            for o in detail["outcomes"]
            if o.get("probability") is not None
        ]
        assert max(priced)[1] == "Jannik Sinner"
