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

from app.tasks.futures_price_refresh import venue_volume_24h
from app.utils.futures_unsupported_price import (
    VOLUME_MEANS_UNTRADED,
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

#: The venue's own 24-hour volume per leg, READ FROM KALSHI 2026-09-21
#: (`GET /trade-api/v2/markets?event_ticker=KXATP-27USO`, notice 26 — the venue's
#: API, not our mirror). These are `volume_24h_fp` verbatim.
#:
#: 🪤 THESE ARE NOT DECORATION AND THE BOARD IS NOT UNIFORM. Sinner is the one leg
#: of the 25 anybody traded in the last day, so the volume term is actually
#: exercised by the fixture rather than being constant across it. Mensik's 0.00 —
#: beside a lifetime `volume_fp` of 189.01, so the contract is not new, just
#: dormant — is the number CERT-3244's repair turns on.
VOLUME_24H = {"Jannik Sinner": 1.74}
VOLUME_24H_DEFAULT = 0.00

#: Legs we have never asked the venue about. NULL is "we never looked", not
#: "nobody traded it" (gotcha #53), and it must FAIL OPEN.
VOLUME_24H_NULL = {"Valentin Vacherot"}


def _volume(name):
    """(volume_24h, volume_24h_at, last_updated) for a leg, from :data:`VOLUME_24H`.

    The stamp equals `last_updated` because the capture writes both from one
    `func.now()` in a single UPDATE — see `venue_reports_no_recent_trading` for
    why the freshness test is that equality and carries no constant.
    """
    if name in VOLUME_24H_NULL:
        return None, None, LAST_SEEN
    return VOLUME_24H.get(name, VOLUME_24H_DEFAULT), LAST_SEEN, LAST_SEEN


#: A leg the venue reports as untraded, and one it reports as traded. The unit
#: classes below are about the BOOK terms, so they hold the volume term fixed at
#: UNTRADED; the volume term has its own class and its own controls.
UNTRADED = (0.00, LAST_SEEN, LAST_SEEN)
TRADED = (1.74, LAST_SEEN, LAST_SEEN)


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
    volume_24h, volume_24h_at, last_updated = _volume(name)
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
        price_changed_at=None,
        volume_24h=volume_24h,
        volume_24h_at=volume_24h_at,
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
            volume_24h=UNTRADED[0],
            volume_24h_at=UNTRADED[1],
            last_seen_at=UNTRADED[2],
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
            volume_24h=UNTRADED[0],
            volume_24h_at=UNTRADED[1],
            last_seen_at=UNTRADED[2],
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
            volume_24h=UNTRADED[0],
            volume_24h_at=UNTRADED[1],
            last_seen_at=UNTRADED[2],
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
            volume_24h=UNTRADED[0],
            volume_24h_at=UNTRADED[1],
            last_seen_at=UNTRADED[2],
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
            volume_24h=UNTRADED[0],
            volume_24h_at=UNTRADED[1],
            last_seen_at=UNTRADED[2],
        )
        admitted = needs_unbacked_ask_evidence(
            "kalshi",
            None,
            prob,
            bid,
            ask,
            in_exclusive_field=True,
            volume_24h=UNTRADED[0],
            volume_24h_at=UNTRADED[1],
            last_seen_at=UNTRADED[2],
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
                volume_24h=UNTRADED[0],
                volume_24h_at=UNTRADED[1],
                last_seen_at=UNTRADED[2],
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
                volume_24h=UNTRADED[0],
                volume_24h_at=UNTRADED[1],
                last_seen_at=UNTRADED[2],
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


class TestTradeActivityNotPriceMovement:
    """CERT-3244 BLOCKed the repair and was RIGHT, so this class is the second one.

    The story is worth keeping whole, because the two BLOCKs are different
    mistakes and only the second one is subtle.

    CERT-3242 refused EVERY price printing at its own ask over a wide spread. The
    grader falsified it in minutes against four legs being traded at exactly that
    ask (Tunisia $87.67 of 24h volume, Gambia $54.43, Cameron Dicker $9.30,
    Davante Adams $6.10).

    The repair read the missing axis as TIME — `last_updated - price_changed_at`
    over 24 hours. 🔴 **A market can trade repeatedly at an unchanged price**, so
    that refused three more:

        leg               served   static for   Kalshi 24h volume
        Egypt              0.70     48.5h       $8.73
        Arch Manning       0.60    308h         $3.24
        Congo Republic     0.70     48.5h       $0.04

    Time does not separate this population AT ALL: Manning is 308 hours static and
    trading, the specimen 70 hours static and not. The axis is
    `venue_reports_no_recent_trading`, which is the ship's own criterion rather
    than a proxy for it — #7747's first sentence says "whose venue reports zero
    24-hour volume".

    🪤 Congo Republic is the reason the stored column is `Numeric(14, 2)` and the
    reason `venue_volume_24h` exists. **$0.04 floors to 0 under `int()`**, and 0 is
    the withhold trigger — so an integral column, or the shared parser's
    `int(float(val))`, would turn the grader's own counterexample into the very
    defect it blocked.
    """

    # (name, served, bid, ask, 24h volume) — production + venue, 2026-09-21.
    # The first four falsified CERT-3242's cut; the last three falsified
    # CERT-3244's. All seven are served today and must keep their number.
    LIVE_EXECUTIONS = [
        ("Tunisia", 0.79, 0.22, 0.79, 87.67),
        ("Gambia", 0.80, 0.13, 0.80, 54.43),
        ("Cameron Dicker", 0.52, 0.00, 0.52, 9.30),
        ("Davante Adams", 0.85, 0.00, 0.85, 6.10),
        ("Egypt", 0.70, 0.10, 0.70, 8.73),
        ("Arch Manning", 0.60, 0.00, 0.60, 3.24),
        ("Congo Republic", 0.70, 0.10, 0.70, 0.04),
    ]

    @staticmethod
    def _p(prob, bid, ask, volume_24h, *, volume_24h_at=LAST_SEEN):
        return price_is_an_unbacked_ask(
            "kalshi",
            None,
            prob,
            bid,
            ask,
            ask,  # the trade IS the ask in every one of these
            has_trade_evidence=True,
            in_exclusive_field=True,
            volume_24h=volume_24h,
            volume_24h_at=volume_24h_at,
            last_seen_at=LAST_SEEN,
        )

    @pytest.mark.parametrize("name,prob,bid,ask,volume", LIVE_EXECUTIONS)
    def test_the_seven_legs_that_falsified_the_two_cuts_keep_their_price(
        self, name, prob, bid, ask, volume
    ):
        assert (
            self._p(prob, bid, ask, volume) is False
        ), f"{name} traded ${volume} in the last 24 hours"

    def test_the_specimen_is_still_withheld(self):
        assert self._p(0.74, 0.04, 0.74, 0.00) is True

    def test_four_cents_of_trading_is_trading(self):
        """🔴 The single assertion that separates this ship from its second BLOCK.

        Congo Republic is a real leg the grader named, and `$0.04` is the whole
        margin between "the venue says nobody traded this" and "somebody did".
        A column, parser or comparison that rounds is caught here and nowhere
        else in this file.
        """
        assert self._p(0.70, 0.10, 0.70, 0.04) is False
        assert self._p(0.70, 0.10, 0.70, 0.00) is True

    def test_the_bound_is_the_named_constant_and_not_a_literal(self):
        assert VOLUME_MEANS_UNTRADED == 0
        assert self._p(0.74, 0.04, 0.74, VOLUME_MEANS_UNTRADED) is True
        assert self._p(0.74, 0.04, 0.74, VOLUME_MEANS_UNTRADED + 0.01) is False

    def test_a_null_volume_fails_open(self):
        """gotcha #53 — the column is populated FORWARD, so every row predating
        the first capture reads NULL. That is "we never asked the venue", not
        "the venue says nobody is trading this", and only a positive reading may
        withhold."""
        assert self._p(0.74, 0.04, 0.74, None) is False

    def test_a_reading_older_than_the_rows_last_touch_fails_open(self):
        """The anti-self-sealing term, and the reason the stamp is its own column.

        A writer that advances `last_updated` without taking a volume reading —
        the resolution writes in `tasks/kalshi.py`, the withdrawal clears, the
        empty-book decline that skips the row entirely — leaves the stamp behind.
        Reading a three-day-old zero as current would present it as "the venue
        says nobody is trading this, measured minutes ago", which is exactly the
        conflation #2024 split `price_changed_at` off `last_updated` to end.
        """
        stale_reading = LAST_SEEN - timedelta(hours=72)
        assert self._p(0.74, 0.04, 0.74, 0.00, volume_24h_at=stale_reading) is False

    def test_an_ingestion_outage_cannot_widen_the_withheld_set(self):
        """Both columns are on ONE row, so the comparison FREEZES in an outage.

        If the poller stops, `volume_24h_at` and `last_updated` stop advancing
        together, so every leg keeps whatever verdict it had when ingestion died
        and NO new leg is withheld. A wall-clock bound (`now - volume_24h_at <
        6h`) would instead have gone false fleet-wide during the outage and —
        worse — gone TRUE again on a stale zero the moment one unrelated writer
        touched the row. This is #7537's structural property, on the pair of
        columns that answers THIS question.
        """
        for outage_days in (0, 1, 7, 30):
            # The poller is dead; neither stamp advances, whatever the clock says.
            assert (
                self._p(0.70, 0.10, 0.70, 8.73) is False
            ), f"a {outage_days}-day outage must not withhold a traded leg"
            assert (
                self._p(0.74, 0.04, 0.74, 0.00) is True
            ), f"a {outage_days}-day outage must not acquit the specimen either"


class TestTheVenueFigureSurvivesTheRead:
    """`venue_volume_24h` — the parse, and why it is not the shipped one.

    🔴 `KalshiMarket.volume_24h` is built by
    `parse_int_str(volume_24h_fp) or market_data.get("volume_24h")`, and BOTH
    halves destroy the distinction this ship turns on. `int(float("0.04"))` is 0,
    and the `or` then treats that 0 as falsy and falls through to a legacy key the
    modern payload does not carry — so a four-cent trade AND a genuine zero both
    arrive as `None`. The specimen publishes `volume_24h_fp: '0.00'`, so the
    shipped field would have made Mensik unwithholdable and the ship inert.

    The payloads below are verbatim from
    `GET /trade-api/v2/markets?event_ticker=KXATP-27USO`, read 2026-09-21.
    """

    def test_the_specimens_own_zero_arrives_as_zero_and_not_as_absent(self):
        assert venue_volume_24h({"volume_24h_fp": "0.00"}) == 0.0

    def test_a_four_cent_trade_is_not_floored_to_untraded(self):
        assert venue_volume_24h({"volume_24h_fp": "0.04"}) == pytest.approx(0.04)

    def test_the_one_traded_leg_on_the_specimen_board_reads_its_real_figure(self):
        assert venue_volume_24h({"volume_24h_fp": "1.74"}) == pytest.approx(1.74)

    def test_the_shipped_parser_would_have_broken_both_of_those(self):
        """The control that proves the previous three are not vacuous.

        Reproduces `parse_int_str(...) or ...` on the same inputs. If someone
        later "simplifies" `venue_volume_24h` back onto the shared helper, the
        three assertions above fail — but only this one says WHY, and only this
        one fails if the shared helper is ever fixed and the duplication becomes
        removable.
        """
        shipped = lambda fp: (int(float(fp)) or None)  # noqa: E731
        assert shipped("0.00") is None, "a genuine zero became 'we never asked'"
        assert shipped("0.04") is None, "a four-cent trade became 'we never asked'"
        assert shipped("1.74") == 1, "and a real figure lost its decimals"

    def test_a_legacy_integer_payload_still_reads(self):
        assert venue_volume_24h({"volume_24h": 12}) == 12.0

    def test_the_fixed_point_form_wins_when_both_are_present(self):
        """`_fp` is the precise one; the plain key is the same figure truncated."""
        assert venue_volume_24h(
            {"volume_24h_fp": "0.04", "volume_24h": 0}
        ) == pytest.approx(0.04)

    @pytest.mark.parametrize(
        "payload", [{}, {"volume_24h_fp": None}, {"volume_24h_fp": ""}]
    )
    def test_an_absent_figure_is_none_and_never_zero(self, payload):
        """gotcha #53. Absent must not arrive wearing the withhold trigger."""
        assert venue_volume_24h(payload) is None

    def test_an_unreadable_figure_is_none_and_never_zero(self):
        assert venue_volume_24h({"volume_24h_fp": "not-a-number"}) is None


@pytest.mark.asyncio
class TestTradeActivityNotPriceMovementEndToEnd:
    """The same rule through the ROUTE and through the SERVED FORMATTER.

    CERT-3244 named this shape explicitly, and the reason it is not redundant with
    the class above is that a predicate is not a page: the helper hands back ids
    and the formatter is what nulls the fields.
    """

    @staticmethod
    def _board_with_a_live_execution():
        """The specimen board with ONE leg traded at an unchanged price.

        Alexander Zverev is given Mensik's exact book and price, so the two rows
        are identical in every column this rule reads EXCEPT the volume one. That
        is what makes the pair a control rather than two unrelated legs — and it
        is the precise shape CERT-3244 blocked, since NEITHER row's price has
        moved.
        """
        rows = []
        for oid, name, p, b, a, lp in USOPEN_2027:
            if name == "Alexander Zverev":
                rows.append((oid, name, 0.74, 0.0400, 0.7400, 0.7400))
            else:
                rows.append((oid, name, p, b, a, lp))
        return rows

    async def test_recent_same_price_execution_remains_priced_after_24h_while_zero_volume_mensik_is_withheld(
        self,
    ):
        """The guard CERT-3244 required, by name.

        Both legs are 70 hours static on an identical 0.04/0.74 book, so every
        term of the predicate except volume is equal between them. Zverev traded
        $3.24 without moving his price — the Arch Manning shape — and keeps his
        number; Mensik traded nothing and loses his.
        """
        rows = self._board_with_a_live_execution()
        VOLUME_24H["Alexander Zverev"] = 3.24
        try:
            names, _ = await _withheld_names(rows)
            assert "Jakub Mensik" in names, "zero 24h volume on a 4c bid"
            assert (
                "Alexander Zverev" not in names
            ), "identical book, identical price, unmoved for 70h — and traded $3.24"

            # ...and the same, as the reader is served it.
            detail = _detail(rows, withheld_names=names)
            served = _detail_by_name(detail)
            assert served["Jakub Mensik"]["probability"] is None
            assert served["Alexander Zverev"]["probability"] == pytest.approx(
                0.74, abs=0.01
            )
        finally:
            VOLUME_24H.pop("Alexander Zverev", None)

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


class TestTheCaptureActuallyUsesTheFaithfulParse:
    """🔴 THE GUARD THAT WAS MISSING, AND A MUTANT FOUND IT.

    Mutating the capture in `_fetch_kalshi_prices` from
    `volume_by_ticker.get(market.ticker)` back to the shipped `market.volume_24h`
    left **every other test in this file green**. That swap is not cosmetic: it is
    the difference between the ship working and the ship being INERT, because the
    shipped field turns the specimen's own `volume_24h_fp: '0.00'` into `None`
    (see `venue_volume_24h`) and a `None` fails open and serves.

    Unit-testing `venue_volume_24h` cannot catch it — the function stays correct
    and simply stops being called. So this class runs the REAL fetch over the REAL
    parser and asserts the figure that comes out the other end.

    The payload is verbatim from
    `GET /trade-api/v2/markets?event_ticker=KXATP-27USO`, read 2026-09-21, trimmed
    to the two legs that matter: the specimen (zero volume) and the one leg on the
    board anybody traded.
    """

    RAW_EVENT = {
        "event_ticker": "KXATP-27USO",
        "title": "US Open Men's Singles Winner",
        "markets": [
            {
                "ticker": "KXATP-27USO-MEN",
                "event_ticker": "KXATP-27USO",
                "title": "US Open Men's Singles: Jakub Mensik wins",
                "status": "active",
                "result": "",
                "yes_bid_dollars": "0.0400",
                "yes_ask_dollars": "0.7400",
                "last_price_dollars": "0.7400",
                "volume_24h_fp": "0.00",
                "volume_fp": "189.01",
            },
            {
                "ticker": "KXATP-27USO-SIN",
                "event_ticker": "KXATP-27USO",
                "title": "US Open Men's Singles: Jannik Sinner wins",
                "status": "active",
                "result": "",
                "yes_bid_dollars": "0.0700",
                "yes_ask_dollars": "0.5600",
                "last_price_dollars": "0.5500",
                "volume_24h_fp": "1.74",
                "volume_fp": "105.75",
            },
        ],
    }

    class _Venue:
        """`get_event` over a fixed payload; the PARSER is the real one.

        Same shape as `test_venue_answered_is_not_a_price_5771._Venue`, and the
        real parser is the point — a fake that handed back pre-parsed markets
        would skip the very step this class is testing.
        """

        def __init__(self, raw):
            from app.services.kalshi_api import KalshiAPIService

            self._raw = raw
            self._svc = KalshiAPIService(api_key=None)

        async def get_event(self, ticker, with_nested_markets=True):
            return self._raw

        def _parse_event(self, raw):
            return self._svc._parse_event(raw)

    def _priced(self):
        import asyncio

        from app.tasks import futures_price_refresh as fpr

        items = asyncio.run(
            fpr._fetch_kalshi_prices(self._Venue(self.RAW_EVENT), "KXATP-27USO")
        )
        return {item["external_id"]: item for item in items}

    def test_the_specimens_zero_reaches_the_write_as_zero_not_as_absent(self):
        """The assertion the surviving mutant needed.

        `0.0` withholds; `None` fails open and serves. The shipped
        `KalshiMarket.volume_24h` yields `None` here, so this fails the moment the
        capture is pointed back at it.
        """
        item = self._priced()["KXATP-27USO-MEN"]
        assert item["volume_24h"] == 0.0
        assert item["volume_24h"] is not None, (
            "the specimen's own '0.00' arrived as 'we never asked', which serves "
            "the price — the ship would be inert"
        )

    def test_the_traded_leg_keeps_its_fractional_figure(self):
        item = self._priced()["KXATP-27USO-SIN"]
        assert item["volume_24h"] == pytest.approx(1.74)

    def test_the_parsed_field_beside_it_really_does_disagree(self):
        """The control that proves the two assertions above are not vacuous.

        If `KalshiMarket.volume_24h` is ever fixed to carry the faithful figure,
        the capture's own indirection becomes removable — and this test is what
        says so out loud instead of leaving a stale workaround in place.
        """
        from app.services.kalshi_api import KalshiAPIService

        event = KalshiAPIService(api_key=None)._parse_event(self.RAW_EVENT)
        parsed = {m.ticker: m.volume_24h for m in event.markets}

        assert parsed["KXATP-27USO-MEN"] is None, (
            "the shipped parser no longer collapses a genuine zero to None; "
            "`venue_volume_24h`'s indirection may now be removable"
        )
        assert parsed["KXATP-27USO-SIN"] == 1, "and it still floors 1.74 to 1"


class TestTheWriteCarriesTheFigureAndItsStamp:
    """🔴 THREE MORE MUTANTS SURVIVED UNTIL THIS CLASS EXISTED.

    Nothing exercised `_write_prices`' half of the capture, so all three of these
    edits passed the whole file:

      * dropping `volume_24h_at` from the write — which makes the freshness test
        self-sealing, the exact defect the stamp was split out to prevent;
      * writing the columns even when the venue supplied nothing — which stamps
        `NULL` as a fresh reading, and a fresh NULL is not merely useless, it is
        an assertion we never made;
      * reading the volume off the LEG instead of the ITEM — which silently drops
        it for every market, because only the item carries it.

    The sibling suites' `_WriteSession` counts updates but not their CONTENTS, so
    it cannot see any of this; the recorder below keeps the statements.
    """

    class _RecordingSession:
        """`_write_prices`' session, keeping every statement it is handed."""

        def __init__(self, rows=((11, "KXATP-27USO-MEN"),)):
            self.rows = list(rows)
            self.statements = []

        async def execute(self, statement, params=None):
            sql = str(statement).lstrip().upper()
            self.statements.append(statement)
            if sql.startswith("SELECT ID, EXTERNAL_ID FROM FUTURES_OUTCOMES"):
                return _WriteResult(self.rows)
            return _WriteResult(rowcount=1)

        def updates(self):
            return [
                s
                for s in self.statements
                if str(s).lstrip().upper().startswith("UPDATE FUTURES_OUTCOMES")
            ]

    @staticmethod
    def _item(volume_24h):
        """The specimen leg, priced, with the venue's volume attached or absent."""
        item = {
            "external_id": "KXATP-27USO-MEN",
            "probability": 0.74,
            "yes_bid": 0.04,
            "yes_ask": 0.74,
            "last_price": 0.74,
        }
        if volume_24h is not _ABSENT:
            item["volume_24h"] = volume_24h
        return item

    async def _write(self, volume_24h):
        from app.tasks import futures_price_refresh as fpr

        session = self._RecordingSession()
        stats: dict = {}
        await fpr._write_prices(
            session, 61308736, "kalshi", [self._item(volume_24h)], stats
        )
        updates = session.updates()
        assert len(updates) == 1, f"expected one UPDATE, got {len(updates)}"
        return updates[0]

    async def test_a_zero_reading_is_written_with_a_stamp(self):
        """The specimen's own case: the figure lands AND it is dated."""
        sql = str(await self._write(0.0))
        assert "volume_24h=" in sql, "the venue's figure never reached the row"
        assert "volume_24h_at=" in sql, (
            "the figure was written with no observation time — the consumer's "
            "freshness test then reads whatever an unrelated writer last did to "
            "last_updated, which is the self-sealing lie the stamp prevents"
        )

    async def test_the_written_value_is_the_venues_and_not_a_rounding(self):
        update = await self._write(0.04)
        params = update.compile().params
        written = [v for k, v in params.items() if k.startswith("volume_24h")]
        assert written == [pytest.approx(0.04)], (
            f"the row would have stored {written}; four cents of trading must not "
            "arrive as zero, which is the withhold trigger"
        )

    async def test_the_stamp_and_the_touch_stamp_are_one_transaction_clock(self):
        """They must be EQUAL, not merely close — the consumer compares them with
        `>=` and carries no tolerance. Both are `now()`, evaluated once per
        statement by Postgres, so the rendered SQL shows the same function on both
        columns rather than a Python timestamp on one of them."""
        sql = str(await self._write(0.0)).lower()
        set_clause = sql.split(" where ")[0]
        assert "volume_24h_at=now()" in set_clause.replace(" ", "")
        assert "last_updated=now()" in set_clause.replace(" ", "")

    async def test_a_venue_that_supplies_no_volume_writes_neither_column(self):
        """OMITTED, NEVER NULLED — and this is what makes the omission safe.

        `_write_prices` is shared with Polymarket, whose items carry no volume at
        all. Writing NULL would erase a real reading; writing NULL with a fresh
        stamp would assert "the venue says nobody is trading this, measured just
        now". Skipping both leaves the old stamp behind the `last_updated` this
        same UPDATE advances, so the consumer's freshness test goes false on its
        own and the leg is SERVED.
        """
        sql = str(await self._write(_ABSENT))
        assert "volume_24h" not in sql, (
            "a market the venue said nothing about must not have its volume "
            "columns touched at all"
        )
        assert "last_updated=" in sql, "the price write itself must still happen"

    async def test_an_explicit_none_is_also_not_written(self):
        """The same property through the other door: the key present, value None."""
        sql = str(await self._write(None))
        assert "volume_24h" not in sql


#: Sentinel for "the key is not in the item at all", which is a different input
#: from "the key is present and None" — both must decline to write.
_ABSENT = object()


class _WriteResult:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return list(self._rows)

    def all(self):
        return list(self._rows)
