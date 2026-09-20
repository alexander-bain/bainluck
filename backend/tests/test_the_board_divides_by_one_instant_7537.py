"""#7537 — the table's divisor may only hold legs observed at the same time.

`/futures/3971707` (*Super League Rugby Championship*) printed **Leeds Rhinos
30%** in its hero and its All Outcomes table while the Probability Trend chart
between them drew that same outcome at **39.5%** — one screen, one stamp
(`2026-09-20T14:53:14`), two numbers for one leg.

The chart is the honest side. `0.395` is Kalshi's own midpoint
(`yes_bid 0.3300 / yes_ask 0.4600`, read at the venue on 2026-09-20); `0.302` is
what the table manufactured by squeezing three genuinely-quoted prices against
**eleven legs nobody had repriced in a fortnight**. Fourteen legs summing to
1.7200 entered the divisor; exactly three had been observed that day.

WHY NO RULE ALREADY SHIPPED CATCHES IT. Every unsupported-price screen reads the
leg's own `yes_bid` / `yes_ask` / `last_price`, and on a fossil all three are
frozen at the same stale instant: Hull Kingston Rovers presents `0.1900/0.4700`
— a healthy two-sided book — while the venue's live answer for
`KXSLRCHAMP-26-HKR` is `yes_bid 0.0000 / yes_ask 0.9600 / last 0.0000 /
volume_24h 0`. The rules acquit it correctly on the stale evidence they are
shown. Nothing asked whether the evidence was CURRENT.

Every row below is the row production served on 2026-09-20, copied from the
named market rather than invented, and every stamp is an OFFSET from the
fixture's own frozen instant (gotcha #44) so no assertion here can age out.

THE RULE IS RELATIVE TO THE BOARD, NEVER TO `now`, and
`TestOurOwnOutageCannotBlankABoard` is the control that keeps that visible: if
ingestion stalls for a whole market every leg ages together, the spread stays
at zero and nothing is withheld.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import app.routes.futures as futures_routes
import app.utils.futures_market_snapshot as snapshot_utils
from app.utils.market_staleness import (
    OBSERVATION_LAG_DAYS,
    stale_observation_keys,
)

# ONE IMPORT FORM PER MODULE. `app.routes.futures` is already imported above as
# a module (`_at` patches its `datetime`), so a `from app.routes.futures import
# _format_market_detail` beside it is `py/import-and-import-from` — a CodeQL
# note, and the same one 5ef820189 cleared for `espn_sync`. The formatter is
# reached through the module instead; it is the same object either way.
_format_market_detail = futures_routes._format_market_detail

#: The minute the rugby board was read off production.
MEASURED_AT = datetime(2026, 9, 20, 15, 40, tzinfo=timezone.utc)

#: The board's two observation instants, as AGES rather than dates. Production
#: read `2026-09-20 14:53:14` and `2026-09-06 05:46:08`; the gap is what the
#: rule judges, and 14.4 days of it is what a reader met.
FRESH_AGE = timedelta(minutes=47)
FOSSIL_AGE = timedelta(days=14, hours=9)

# (name, stored probability, bid, ask, observed) — market 3971707's fourteen
# `futures_outcomes` rows exactly as production holds them. The three FRESH legs
# are the three Kalshi still quotes.
RUGBY_3971707 = [
    ("Leeds Rhinos", 0.395, 0.3300, 0.4600, FRESH_AGE),
    ("St Helens", 0.130, 0.0000, 0.9600, FRESH_AGE),
    ("Warrington Wolves", 0.110, 0.0000, 0.9600, FRESH_AGE),
    ("Hull Kingston Rovers", 0.330, 0.1900, 0.4700, FOSSIL_AGE),
    ("Wigan Warriors", 0.295, 0.1900, 0.4000, FOSSIL_AGE),
    ("Wakefield Trinity", 0.120, 0.0000, 0.1200, FOSSIL_AGE),
    ("Hull FC", 0.090, 0.0000, 0.0900, FOSSIL_AGE),
    ("Leigh Leopards", 0.080, 0.0000, 0.0800, FOSSIL_AGE),
    ("Catalan Dragons", 0.040, 0.0000, 0.0400, FOSSIL_AGE),
    ("Toulouse Olympique", 0.030, 0.0000, 0.0300, FOSSIL_AGE),
    ("York Knights", 0.030, 0.0000, 0.0300, FOSSIL_AGE),
    ("Huddersfield Giants", 0.030, 0.0000, 0.0300, FOSSIL_AGE),
    ("Bradford Bulls", 0.020, 0.0000, 0.0200, FOSSIL_AGE),
    ("Castleford Tigers", 0.020, 0.0000, 0.0200, FOSSIL_AGE),
]

#: What the chart drew for Leeds, and therefore what the table owes it.
LEEDS_ON_THE_CHART = 0.395

#: What the table printed instead, before this ship. 0.395 / 1.308.
LEEDS_BEFORE = 0.302

#: The three legs Kalshi still quotes, and the sum that keeps them off the
#: squeeze (`normalize_display_probs` fires above 1.05).
FRESH_NAMES = {"Leeds Rhinos", "St Helens", "Warrington Wolves"}
FRESH_SUM = 0.635
FULL_SUM = 1.72

#: 🔴 THE SEVEN LEGS THE SHIPPED UNSUPPORTED-PRICE RULE ALREADY WITHHOLDS, AND
#: WITHOUT THEM THIS FIXTURE CANNOT REPRODUCE THE DEFECT AT ALL.
#:
#: The served payload reports `prices_withheld: 7`. Those seven quote
#: `yes_bid 0.0000` against a low ask, so #5611's screen takes their price — and
#: that is precisely what drags the field's sum from 1.7200 down to **1.3100**,
#: under `_FIELD_SUM_MAX` (1.60) and into the squeeze band. THEN the squeeze
#: fires, and 0.395 / 1.310 is the **0.302** a reader met.
#:
#: A fixture that passes no withheld set leaves the sum at 1.72, where #1200
#: bails out to raw prices — so Leeds serves 0.395 before AND after, the
#: headline assertion passes on master, and the guard proves nothing. Measured:
#: that version of this file failed 7 of 26 at `origin/master`; this one fails
#: the arms that matter, including the headline.
#:
#: Huddersfield and Castleford are fossils that the rule SPARES (their stale
#: snapshots carry a positive `last_price`, so "trade evidence beats a wide
#: book" acquits them) — which is why staleness catches eleven where the
#: shipped screen catches seven.
UNSUPPORTED_BY_SHIPPED_RULE = {
    "Wakefield Trinity",
    "Hull FC",
    "Leigh Leopards",
    "Catalan Dragons",
    "Toulouse Olympique",
    "York Knights",
    "Bradford Bulls",
}

#: What the table printed for the two stored favourites behind Leeds, before
#: this ship — both of them fossils, both ranked above three live legs.
HULL_KR_BEFORE = 0.252
WIGAN_BEFORE = 0.225

_CLOCK_READERS = (futures_routes, snapshot_utils)


@contextmanager
def _at(instant: datetime = MEASURED_AT):
    """Every reader on one clock — #7284's fixture rule, and its reason.

    Half-freezing is a time bomb rather than a weaker freeze: the ages here are
    relative to `instant`, so a reader left on the real clock measures a
    relative basis against an absolute now.
    """

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant if tz is None else instant.astimezone(tz)

    with ExitStack() as stack:
        for module in _CLOCK_READERS:
            stack.enter_context(patch.object(module, "datetime", _Frozen))
        yield


def _outcome(oid, name, prob, bid, ask, age, *, at=MEASURED_AT, winner=None,
             resolution_source=None):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"KXSLRCHAMP-26-{oid:03d}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=winner,
        # Production carries `ungradeable_result` on all fourteen rows — the
        # grader gave up, which is a RETRACTION and not a settlement. The rule
        # under test must not read it as either.
        resolution_source=resolution_source or "ungradeable_result",
        last_updated=at - age,
        price_changed_at=None,
        team_id=None,
        team=None,
        current_yes_bid=bid,
        current_yes_ask=ask,
    )


def _market(rows, *, status="open", me=True, at=MEASURED_AT):
    outcomes = [
        _outcome(i + 1, name, prob, bid, ask, age, at=at)
        for i, (name, prob, bid, ask, age) in enumerate(rows)
    ]
    return SimpleNamespace(
        id=3971707,
        name="Super League Rugby Championship Winner",
        description=None,
        category="sports",
        source="kalshi",
        external_id="KXSLRCHAMP-26",
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=2,
        llm_sport_category="rugby",
        mutually_exclusive=me,
        commence_time=at - timedelta(days=30),
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=outcomes,
    )


def _unsupported_ids(market):
    """The ids the shipped #5611 screen names, as the route would hand them in.

    Looked up by NAME off the built market so the set survives a fixture
    reorder — an id list written out by hand would silently withhold the wrong
    clubs the moment a row moved.
    """
    return {o.id for o in market.outcomes if o.name in UNSUPPORTED_BY_SHIPPED_RULE}


def _served(rows=RUGBY_3971707, **kw):
    at = kw.pop("at", MEASURED_AT)
    market = _market(rows, at=at, **kw)
    with _at(at):
        return _format_market_detail(market, None, _unsupported_ids(market))


def _served_staleness_only(rows=RUGBY_3971707, **kw):
    """The board with the shipped screen switched OFF, isolating this rule.

    The controls below assert "staleness withholds nothing here". Handing them
    the #5611 set too would have them assert `prices_withheld == 7` for a
    reason that has nothing to do with the rule under test — a control that
    cannot tell which rule moved is not a control.
    """
    at = kw.pop("at", MEASURED_AT)
    with _at(at):
        return _format_market_detail(_market(rows, at=at, **kw))


def _by_name(detail):
    return {row["name"]: row for row in detail["outcomes"]}


class TestTheReaderSeesOneNumber:
    """The defect, stated as the acceptance the issue asked for."""

    def test_leeds_is_served_at_the_number_its_own_chart_draws(self):
        """39.5%, not 30.2% — the two-numbers-on-one-screen defect itself."""
        leeds = _by_name(_served())["Leeds Rhinos"]
        assert leeds["probability"] == pytest.approx(LEEDS_ON_THE_CHART)
        assert leeds["probability"] != pytest.approx(LEEDS_BEFORE, abs=1e-3)

    def test_the_other_two_quoted_legs_are_served_raw_too(self):
        """St Helens 13% and Warrington 11%, the numbers Kalshi last traded."""
        served = _by_name(_served())
        assert served["St Helens"]["probability"] == pytest.approx(0.130)
        assert served["Warrington Wolves"]["probability"] == pytest.approx(0.110)

    def test_the_eleven_unobserved_legs_carry_no_number(self):
        """Present and null — `formatProbability(null)` prints "-"."""
        served = _by_name(_served())
        fossils = [row for name, row in served.items() if name not in FRESH_NAMES]
        assert len(fossils) == 11
        for row in fossils:
            assert "probability" in row, "the key is present, never omitted"
            assert row["probability"] is None

    def test_the_withheld_count_names_all_eleven(self):
        assert _served()["prices_withheld"] == 11


class TestTheRuleCannotBeMistakenForASmallnessFilter:
    """Non-vacuity: the withheld legs OUTRANK surviving ones.

    Hull Kingston Rovers is stored at 0.330 and Wigan at 0.295 — both ABOVE the
    two fresh legs that survive at 0.130 and 0.110. A rule that merely dropped
    longshots, or one that kept the top N, reproduces none of this. The board's
    stored SECOND and THIRD favourites are exactly what goes.
    """

    def test_the_second_favourite_by_stored_price_is_the_one_withheld(self):
        """Ranks 2 and 3 on the page a reader met — 25.2% and 22.5% — both go.

        Neither number was ever refused by anything shipped: they survived the
        #5611 screen on a two-sided book that has not existed since September 6.
        """
        served = _by_name(_served())
        assert served["Hull Kingston Rovers"]["probability"] is None
        assert served["Wigan Warriors"]["probability"] is None
        assert HULL_KR_BEFORE > served["Leeds Rhinos"]["probability"] / 2
        assert WIGAN_BEFORE > 0.2, "it was printed as a fifth of the field"

    def test_a_surviving_leg_is_priced_below_a_withheld_one(self):
        """0.110 survives while 0.330 does not — the inversion, pinned."""
        served = _by_name(_served())
        assert served["Warrington Wolves"]["probability"] == pytest.approx(0.110)
        assert served["Hull Kingston Rovers"]["probability"] is None

    def test_the_leader_is_unchanged_by_the_rule(self):
        """Leeds led before and leads after; this is not a re-ranking."""
        detail = _served()
        priced = [
            row for row in detail["outcomes"] if row["probability"] is not None
        ]
        assert max(priced, key=lambda r: r["probability"])["name"] == "Leeds Rhinos"


class TestTheBoardKeepsEveryTeam:
    """Withheld, not dropped — and three separate things depend on that."""

    def test_all_fourteen_rows_are_still_served(self):
        """A reader still sees every club in the competition."""
        assert len(_served()["outcomes"]) == 14

    def test_identity_does_not_move(self):
        """`concept_outcome_count` is the identity answer (UX-P164).

        It is a local rather than a served key, and it reads `len(outcomes)` at
        that point in the pipeline — so the observable that proves it is the
        length of the list this rule hands on. #7274's expiry DROP shortened
        that list and had to add its rows back by hand; a withhold never
        shortens it, so it needs no add-back and cannot turn a 14-team board
        into the two-row 'fight-shaped' one the combat adapters would read.
        """
        together = [
            (name, prob, bid, ask, FRESH_AGE)
            for name, prob, bid, ask, _ in RUGBY_3971707
        ]
        assert len(_served()["outcomes"]) == len(_served(together)["outcomes"]) == 14

    def test_a_withheld_row_keeps_its_name_and_id(self):
        """The chart's `canonical_board` filter keys on id.

        Rows the board DROPS leave the chart too. Dropping here would have
        pulled the three honest lines' own board out from under them.
        """
        served = _by_name(_served())
        assert served["Hull Kingston Rovers"]["id"] is not None


class TestOurOwnOutageCannotBlankABoard:
    """Codex's counterexample, answered structurally rather than by a guard.

    "price .395, no result, last_confirmed = now - 4 days ... is equally
    compatible with a still-quoted leg whose ingestion has failed for four
    days." A wall-clock rule cannot separate those. This one never reads the
    wall clock: it compares legs with each other.
    """

    def test_a_board_whose_every_leg_is_ancient_withholds_nothing(self):
        """Ingestion stopped for the whole market a year ago. Nothing changes."""
        ancient = [
            (name, prob, bid, ask, timedelta(days=365))
            for name, prob, bid, ask, _ in RUGBY_3971707
        ]
        detail = _served_staleness_only(ancient)
        assert detail["prices_withheld"] == 0
        assert all(row["probability"] is not None for row in detail["outcomes"])

    def test_the_newest_leg_is_never_withheld(self):
        """So the divisor can never be empty. The reference IS a member."""
        for rows in (RUGBY_3971707, [("Solo", 0.5, 0.4, 0.6, timedelta(days=900))]):
            detail = _served_staleness_only(rows)
            assert any(
                row["probability"] is not None for row in detail["outcomes"]
            )


class TestTheControlsThatMustNotMove:
    """Boards the rule has no business touching, measured on production."""

    def test_a_board_observed_in_one_pass_is_untouched(self):
        """Market 61461681 (133 legs) spreads 0.00h; 56947465 (36) spreads 7.34h.

        Both measured on production 2026-09-20. The rule is inert on each, which
        is what keeps it clear of #7548's separate mechanism and of #7546's.
        """
        together = [
            (name, prob, bid, ask, FRESH_AGE + timedelta(hours=h))
            for h, (name, prob, bid, ask, _) in enumerate(RUGBY_3971707)
        ]
        detail = _served_staleness_only(together)
        assert detail["prices_withheld"] == 0
        assert len(detail["outcomes"]) == 14

    def test_a_settled_board_is_untouched(self):
        """A result shows what ran — #7274's gate, inherited deliberately.

        The same fourteen rows with the same fourteen-day split: on an open
        board eleven lose their price, on a closed one none do.
        """
        detail = _served_staleness_only(status="closed")
        assert detail["prices_withheld"] == 0
        assert _served_staleness_only()["prices_withheld"] == 11, (
            "and the gate is the only difference between these two calls"
        )

    def test_the_squeeze_still_fires_on_a_contemporaneous_overround(self):
        """The rule must not become an excuse to stop normalizing.

        The mirror image of the specimen: a mild vig-shaped field, every leg
        observed together, summing to 1.30 — inside the band
        (`> 1.05`, under `_FIELD_SUM_MAX` 1.60). Nothing is withheld and the
        squeeze SHOULD still push every printed number down.

        Scaled deliberately rather than reusing the stored prices: at 1.72 the
        rugby field sits ABOVE `_FIELD_SUM_MAX`, where #1200 bails out to raw
        prices and no squeeze would fire for reasons that have nothing to do
        with this rule — a control that passes for the wrong reason.
        """
        scale = 1.30 / FULL_SUM
        together = [
            (name, round(prob * scale, 6), bid, ask, FRESH_AGE)
            for name, prob, bid, ask, _ in RUGBY_3971707
        ]
        detail = _served_staleness_only(together)
        assert detail["prices_withheld"] == 0, "nothing stale, nothing withheld"
        leeds = _by_name(detail)["Leeds Rhinos"]
        raw_leeds = 0.395 * scale
        assert leeds["probability"] < raw_leeds, "the squeeze still fires"


class TestThePredicateItself:
    """`stale_observation_keys`, at the boundaries a route cannot reach."""

    def test_the_specimen_splits_three_from_eleven(self):
        base = datetime(2026, 9, 20, 14, 53, 14, tzinfo=timezone.utc)
        stale = stale_observation_keys(
            (name, base - age) for name, _, _, _, age in RUGBY_3971707
        )
        assert len(stale) == 11
        assert not (stale & FRESH_NAMES)

    def test_the_fresh_and_full_sums_are_the_measured_ones(self):
        """0.6350 and 1.7200 — the two numbers three independent reads agree on."""
        base = datetime(2026, 9, 20, 14, 53, 14, tzinfo=timezone.utc)
        stale = stale_observation_keys(
            (name, base - age) for name, _, _, _, age in RUGBY_3971707
        )
        full = sum(prob for _, prob, _, _, _ in RUGBY_3971707)
        fresh = sum(
            prob for name, prob, _, _, _ in RUGBY_3971707 if name not in stale
        )
        assert full == pytest.approx(FULL_SUM)
        assert fresh == pytest.approx(FRESH_SUM)
        assert fresh <= 1.05, "and so the squeeze declines"

    def test_exactly_at_the_bound_is_not_stale(self):
        """`>`, not `>=` — a leg one second inside the window keeps its price."""
        now = MEASURED_AT
        assert stale_observation_keys(
            [("new", now), ("edge", now - timedelta(days=OBSERVATION_LAG_DAYS))]
        ) == set()

    def test_one_second_past_the_bound_is_stale(self):
        now = MEASURED_AT
        assert stale_observation_keys(
            [
                ("new", now),
                ("over", now - timedelta(days=OBSERVATION_LAG_DAYS, seconds=1)),
            ]
        ) == {"over"}

    def test_an_unreadable_stamp_is_not_stale(self):
        """No evidence is not evidence of death (`prices_have_stopped`' rule)."""
        assert stale_observation_keys(
            [("new", MEASURED_AT), ("none", None), ("junk", "2026-09-06")]
        ) == set()

    def test_a_group_with_no_readable_stamp_yields_nothing(self):
        assert stale_observation_keys([("a", None), ("b", None)]) == set()

    def test_an_empty_group_yields_nothing(self):
        assert stale_observation_keys([]) == set()

    def test_the_bound_is_its_own_constant(self):
        """A third clock, deliberately not folded into the other two.

        `PRICES_STOPPED_DAYS` answers "has anybody moved a price on this
        market" against the wall clock. This answers "were these legs seen
        together". Two clocks measuring different things must not share a
        constant — the module says so in its own words.
        """
        from app.utils import market_staleness

        assert OBSERVATION_LAG_DAYS != market_staleness.PRICES_STOPPED_DAYS


class TestTheFixtureIsNotFrozenToAnHour:
    """Gotcha #44: offsets first, and the assertions hold at any instant."""

    @pytest.mark.parametrize(
        "instant",
        [
            datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 59, tzinfo=timezone.utc),
            datetime(2027, 3, 2, 12, 0, tzinfo=timezone.utc),
        ],
    )
    def test_the_split_is_the_same_at_any_clock(self, instant):
        with _at(instant):
            detail = _format_market_detail(_market(RUGBY_3971707, at=instant))
        assert detail["prices_withheld"] == 11
        leeds = _by_name(detail)["Leeds Rhinos"]
        assert leeds["probability"] == pytest.approx(LEEDS_ON_THE_CHART)
