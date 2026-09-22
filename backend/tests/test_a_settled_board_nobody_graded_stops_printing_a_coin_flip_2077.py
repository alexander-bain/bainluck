"""#2077 — a market that settled eight weeks ago stops rendering as a live 50/50.

WHAT A READER SAW, ON PRODUCTION, THE DAY THIS WAS WRITTEN
----------------------------------------------------------

``GET /api/futures/56916563`` — *Mia Ristic vs. Viola Turini: Total Sets O/U
2.5* — resolved **2026-07-31** and served, on **2026-09-22**::

    status: "resolved"   resolution_date: 2026-07-31T14:00:00+00:00
    Under | probability 0.5  | is_winner false | resolution_source null
    Over  | probability null | is_winner false | resolution_source null

**53 days after it settled**, the page led with a coin flip. Its two siblings
``…64`` (*Set 2 Winner*) and ``…65`` (*Set 1 Games O/U 8.5*) were identical.
That is a standing-ruling-2 violation — *settled means settled* — on the one
surface that heroes a single number.

The lone surviving ``Under 0.5`` is not an accident of that board. It is the
shape of the defect: ``prices_withheld: 1`` means a per-leg rule had already
withheld the complementary leg, and withholding ONE side of a two-sided market
leaves the survivor reading as a standalone probability. A half-priced settled
board is worse than an unpriced one, because it looks deliberate.

WHY THE RULE THAT EXISTS COULD NOT REACH IT
--------------------------------------------

``unobserved_board_keys`` (#8011) is built for exactly this — "has anybody
observed this board lately" — and its own ``board_has_a_verdict`` early-return
(CERT-3298) is the precise discriminator needed here. But its CALLER gated it on
``status == "open"``, so the 1,112,815 resolved boards never reached it. The
stated reason is right in the general case and inverted in this one: *a settled
board is a RESULT, and a result shows what ran* — which **presupposes a
verdict**. On a board nobody ever graded there is no result, and the protected
number is the last quote before the market died, wearing a settled badge.

So this ships no new rule and no new threshold. It lets the ungraded half of the
settled population reach the existing rule and lets that rule's own early-return
protect every settled RESULT.

THE TWO DIRECTIONS THIS FILE HAS TO HOLD
-----------------------------------------

A withholding rule is only as good as what it refuses to touch, so every
"blanked" assertion below is paired with a "survives" one:

* ``/futures/413`` — *Finals MVP*, every leg ``api_settlement`` — heroes **Jalen
  Brunson 99%**, and that is the ANSWER. It must keep every price.
* A board ungraded for less than ``BOARD_UNOBSERVED_DAYS`` keeps its price: it
  is awaiting the 6-hourly grader, not dead, and its closing number is the most
  informative thing on the page.
* The CHART path passes no fleet stamp and must stay inert, because it sorts its
  plotted series on ``probability or 0``.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import pytest

from app.utils.futures_liveness import SETTLEMENT_SOURCE
from app.utils.market_staleness import BOARD_UNOBSERVED_DAYS


def _stamp(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=timezone.utc)


#: Every value below is the production row for market 56916563, read
#: 2026-09-22. The fixture IS the specimen; nothing here is representative.
SPECIMEN_RESOLVED_AT = _stamp("2026-07-31 14:00:00Z")
SPECIMEN_TOUCHED = _stamp("2026-07-31 14:15:00Z")
SPECIMEN_LEG_SEEN = _stamp("2026-07-24 11:21:34Z")
FLEET_NOW = _stamp("2026-09-22 17:00:00Z")

#: ``(id, name, probability, opening)`` — the two legs, as stored.
SPECIMEN_LEGS = [
    (211336091, "Under", 0.5, 0.39),
    (211336090, "Over", 0.5, 0.61),
]


def _outcome(oid, name, prob, opening, *, winner=False, source=None, seen=None):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"polymarket_{oid}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=opening,
        opening_american_odds=None,
        is_winner=winner,
        resolution_source=source,
        last_updated=SPECIMEN_LEG_SEEN if seen is None else seen,
        price_changed_at=None,
        team_id=None,
        team=None,
        current_yes_bid=None,
        current_yes_ask=None,
    )


#: `None` is a MEANINGFUL value for `touched` — "the parent stamp is unreadable"
#: is one of the fail-open cases — so the default cannot also be `None`.
_UNSET = object()


def _board(*, status="resolved", winner=False, source=None, touched=_UNSET, legs=None):
    rows = SPECIMEN_LEGS if legs is None else legs
    outcomes = [
        _outcome(
            oid,
            name,
            prob,
            opening,
            # The verdict, when there is one, is carried by BOTH legs — that is
            # what a real settlement writes (`api_settlement` on the losers too).
            winner=(winner and name == "Under"),
            source=source,
        )
        for oid, name, prob, opening in rows
    ]
    return SimpleNamespace(
        id=56916563,
        name="Mia Ristic vs. Viola Turini: Total Sets O/U 2.5",
        description=None,
        category="game_prop",
        source="polymarket",
        external_id="0x0e0633e0cce9cd3878ca5cc9f98d463d106e1234f248b27f7a106e1b3dbead8f",
        status=status,
        # A relationship, not a string: the serializer reads `market.sport.key`.
        sport=SimpleNamespace(key="tennis_other", name="Other Tennis"),
        sport_id=None,
        event_id=None,
        market_type="quantity",
        market_tier=None,
        llm_sport_category="tennis",
        mutually_exclusive=True,
        commence_time=_stamp("2026-07-23 22:00:54Z"),
        resolution_date=SPECIMEN_RESOLVED_AT,
        created_at=None,
        updated_at=SPECIMEN_TOUCHED if touched is _UNSET else touched,
        group_id="polymarket:740821",
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=outcomes,
    )


@contextmanager
def _at(now: datetime):
    """Pin the wall clock, for the sibling file's reason.

    `_format_market_detail` takes no `now`. Pinned to the measured instant so a
    rule that quietly started reading the clock would still have to agree with
    one reading the fleet stamp — and `test_a_fleet_wide_outage_withholds
    _nothing_new` is where those two disagree.
    """
    import app.routes.futures as futures_routes

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz else now.replace(tzinfo=None)

    with mock.patch.object(futures_routes, "datetime", _Clock):
        yield


def _served(board=None, *, fleet=FLEET_NOW):
    import app.routes.futures as futures_routes

    board = _board() if board is None else board
    with _at(FLEET_NOW):
        return futures_routes._format_market_detail(
            board, None, set(), fleet_newest_observation=fleet
        )


def _priced(detail):
    return {
        row["name"]: row["probability"]
        for row in detail["outcomes"]
        if row["probability"] is not None
    }


class TestTheSpecimenStopsPrintingACoinFlip:
    """The reader-visible claim, on the row that was actually broken."""

    def test_the_shipped_board_serves_no_price_at_all(self):
        assert _priced(_served()) == {}, (
            "a tennis prop that settled 2026-07-31 still printed a live "
            "probability 53 days later"
        )

    def test_neither_leg_survives_as_a_lone_standalone_number(self):
        """The defect's real shape, not just its headline.

        Production served `prices_withheld: 1` — ONE leg withheld, the other
        left at 0.5. Withholding one side of a two-sided market is what makes
        the survivor read as a standalone probability, so a repair that leaves
        either leg priced has reproduced the bug it was written to fix.
        """
        served = _priced(_served())
        assert "Under" not in served
        assert "Over" not in served

    def test_all_three_siblings_behave_identically(self):
        """`…63`, `…64` and `…65` are one defect, not three.

        Named because the issue lists three ids and a fix that happened to key
        on something particular to the first would pass a one-specimen test.
        """
        for name in (
            "Mia Ristic vs. Viola Turini: Total Sets O/U 2.5",
            "Set 2 Winner: Ristic vs Turini",
            "Ristic vs. Turini: Set 1 Games O/U 8.5",
        ):
            board = _board()
            board.name = name
            assert _priced(_served(board)) == {}

    def test_the_row_is_withheld_and_never_dropped(self):
        """Withheld, not dropped — the reader still sees both outcomes.

        `normalize_display_probs` reads an absent value as 0, so the leg leaves
        the DIVISOR without leaving the BOARD. A drop would also pull the row
        out of the chart's `canonical_board`.
        """
        detail = _served()
        assert [row["name"] for row in detail["outcomes"]] == ["Under", "Over"]
        assert detail["outcome_count"] == 2

    def test_a_withheld_price_is_null_and_never_zero(self):
        """🔴 A zero would render as "0%" — a confident claim we did not make.

        Gotcha: a stored zero and an absent value reach the renderer
        identically once something coalesces with `or 0`, so this pins null.
        """
        for row in _served()["outcomes"]:
            assert row["probability"] is None
            assert row["probability"] is not 0  # noqa: F632 — identity is the point

    def test_the_board_reports_what_it_withheld(self):
        assert _served()["prices_withheld"] == 2

    def test_the_completed_journey_survives(self):
        """*Freeze* the journey — do not erase it.

        `WITHHELD_PRICE_FIELDS` deliberately omits `opening_probability`, so the
        page keeps the opening and the chart keeps its history. A repair that
        blanked those would satisfy "no coin flip" by deleting the market.
        """
        openings = {
            row["name"]: row["opening_probability"] for row in _served()["outcomes"]
        }
        assert openings == {"Under": 0.39, "Over": 0.61}


class TestAResultStillShowsWhatRan:
    """The other direction, and the one this change could have broken.

    `/futures/413` heroes **Jalen Brunson 99%** with `api_settlement` on all 57
    legs. That is the Finals MVP ANSWER. Every assertion here fails if the new
    branch admits a board that carries a verdict.
    """

    def test_a_settled_board_with_the_settlement_badge_keeps_every_price(self):
        priced = _priced(_served(_board(source=SETTLEMENT_SOURCE)))
        assert set(priced) == {"Under", "Over"}, (
            "a board whose legs carry `api_settlement` is a RESULT; withholding "
            "it erases the answer rather than an unsourced price"
        )

    def test_a_graded_winner_is_a_verdict_even_without_the_badge(self):
        """`is_winner=True` is never set by accident, so it counts alone."""
        assert set(_priced(_served(_board(winner=True)))) == {"Under", "Over"}

    def test_a_retracted_grade_is_not_a_verdict(self):
        """🔴 `ungradeable_result` is a RETRACTION of a fabricated loss.

        Treating "has any resolution source" as a verdict would republish every
        retracted fabrication as a settled result — the exact harm
        `kalshi_fabricated_loss` exists to undo. So this board is still blanked.
        """
        assert _priced(_served(_board(source="ungradeable_result"))) == {}

    def test_is_winner_false_alone_is_not_a_verdict(self):
        """The column is `default=False`, so False is what a row is BORN with.

        This is the whole specimen population: both legs False, both sources
        null. If False were read as "graded a loser", nothing would ever blank.
        """
        assert _priced(_served(_board(winner=False, source=None))) == {}


class TestTheChangeIsNarrow:
    """What must NOT move, asserted rather than asserted-about."""

    def test_an_open_board_is_untouched_by_the_new_branch(self):
        """An open board still reaches both rules exactly as before.

        Its legs are 60 days behind the fleet, so #8011 blanks it — the point
        is that the verdict-less branch changed nothing about how it got there.
        """
        assert _priced(_served(_board(status="open"))) == {}

    def test_an_open_board_inside_the_floor_keeps_its_price(self):
        """The open path's own behaviour is unchanged by this ship."""
        fresh = FLEET_NOW - timedelta(days=1)
        board = _board(status="open", touched=fresh)
        for row in board.outcomes:
            row.last_updated = fresh
        assert set(_priced(_served(board))) == {"Under", "Over"}

    def test_a_status_the_database_never_holds_is_left_alone(self):
        """Measured 2026-09-22: `futures_markets.status` is exactly
        {open: 40,758, resolved: 1,112,815}. The new branch names `resolved`
        explicitly rather than "not open", so an unknown status keeps today's
        behaviour instead of being blanked by a catch-all.
        """
        assert set(_priced(_served(_board(status="closed")))) == {"Under", "Over"}

    def test_a_recent_settle_still_shows_its_closing_price(self):
        """🔴 THE RESIDUAL, PINNED SO IT CANNOT WIDEN SILENTLY.

        Grading runs 6-hourly across ~35 phases. A board that settled this
        morning is awaiting a grader, not dead, and its closing number is the
        most informative thing on the page. So the inherited
        `BOARD_UNOBSERVED_DAYS` floor is a feature here, and this test is the
        statement that ungraded-and-recent is NOT in scope.
        """
        recent = FLEET_NOW - timedelta(days=BOARD_UNOBSERVED_DAYS - 2)
        board = _board(touched=recent)
        for row in board.outcomes:
            row.last_updated = recent
        assert set(_priced(_served(board))) == {"Under", "Over"}

    def test_the_leg_level_stale_rule_was_not_widened_with_it(self):
        """🔴 Deliberate, and the reason the specimen looked the way it did.

        `stale_observation_keys` measures each leg against its OWN board's
        newest stamp, so on a dead board it is #8011's documented SELECTIVE
        fail-open: it withholds the older legs and certifies the last-written
        one. That is precisely how production served `prices_withheld: 1` with a
        lone surviving `Under 0.5`.

        Here the board is inside the board-level floor but its two legs are far
        apart. If the leg rule had been widened to settled boards, `Over` would
        be withheld and `Under` would survive — a half-priced settled board,
        which is the defect, not the repair. Both must keep their price.
        """
        recent = FLEET_NOW - timedelta(days=1)
        board = _board(touched=recent)
        board.outcomes[0].last_updated = recent
        board.outcomes[1].last_updated = recent - timedelta(days=45)
        assert set(_priced(_served(board))) == {"Under", "Over"}


class TestTheInheritedSafetyPropertiesStillHold:
    """These are `unobserved_board_keys`'s guarantees, re-asserted on the new
    population — because inheriting a rule inherits its failure modes only if
    the new caller actually reaches them."""

    def test_the_chart_path_withholds_nothing(self):
        """🔴 THE INERTNESS CONTROL THIS SHIP DEPENDS ON.

        `get_probability_timeline` builds `canonical_board` from this same
        formatter and sorts its plotted series on `probability or 0`. It passes
        no fleet stamp, so the rule returns the empty set and the chart is
        untouched. This is load-bearing: it is the reason the new branch could
        ride the existing rule rather than being a fourth spelling beside it.
        """
        assert set(_priced(_served(fleet=None))) == {"Under", "Over"}

    def test_a_fleet_wide_outage_withholds_nothing_new(self):
        """Measured against the FLEET's newest observation, never against `now`.

        If futures ingestion stops everywhere, that stamp freezes with
        everything else, every lag stops growing, and no board is newly
        withheld. The clock here says 2026-09-22 while the fleet says the board
        was the last thing anyone saw.
        """
        assert set(_priced(_served(fleet=SPECIMEN_LEG_SEEN))) == {"Under", "Over"}

    def test_an_unreadable_parent_stamp_fails_open(self):
        assert set(_priced(_served(_board(touched=None)))) == {"Under", "Over"}


class TestTheGateReadsTheSharedGradingSemantics:
    """One rule, not two: the branch must not grow a local `is_winner` test."""

    def test_the_route_asks_leg_is_graded_rather_than_testing_is_winner(self):
        import inspect

        import app.routes.futures as futures_routes

        src = inspect.getsource(futures_routes._board_has_a_verdict)
        assert "leg_is_graded" in src, (
            "the verdict test must delegate to `futures_liveness.leg_is_graded` "
            "— `is_winner` defaults to False and `ungradeable_result` is a "
            "retraction, and a local test would get both wrong"
        )

    def test_the_settlement_source_string_is_the_shared_constant(self):
        assert SETTLEMENT_SOURCE == "api_settlement"

    @pytest.mark.parametrize("source", ["api_settlement"])
    def test_the_badge_is_honoured_on_the_resolved_path_too(self, source):
        assert set(_priced(_served(_board(source=source)))) == {"Under", "Over"}
