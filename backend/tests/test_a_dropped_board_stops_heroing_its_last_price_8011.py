"""#8011 — A BOARD NOBODY HAS REPRICED IN MONTHS STOPPED HEROING ITS LAST PRICE.

Production specimen, read live 2026-09-22 12:2xZ from `api.bainluck.com/api/futures/10`
and `db-query` — *FIFA World Cup Winner*, `source: odds_api`, `status: open`,
`resolution_date: NULL`, 65 legs, `prices_withheld: 59`. The tournament was decided on
**2026-07-19**. Reader frame at 390px: `artifacts-live-510/BEFORE-8011-board10-390px.png`.

The page contradicted itself twice, and the hero was the only dishonest surface:

    hero    59%  Spain          <- no date, no qualification
    chart   "Last number 64 days ago"
    table   "All Outcomes as of Jul 12"

═══ 🔴 WHAT IS **NOT** THE BUG ═══

The four `0%` rows are correct. Spain and Argentina were the July 19 final and the
other 62 teams were genuinely eliminated. `formatProbability(null)` already prints
`-`, so those zeros are STORED zeros and not a null-render artifact. The data was
right on July 19; nothing has been right since.

`stale_observation_keys` (#7537) is also not the bug, and a fix that made it
wall-clock-absolute would be the real regression — see `TestOurOwnOutageStillCannotBlankABoard`.

═══ THE MECHANISM ═══

That rule measures each leg against its OWN board's newest stamp. On board 10 the
newest stamp is itself two months old, so it withheld the 59 legs behind
`2026-07-19 20:30` and certified the two legs HOLDING that stamp as fresh — the last
write before the market died. Renormalisation hid the wreck:
`0.587142 + 0.412858 = 1.000000`. Selective fail-open, not fail-open.

═══ WHY THE CONTROLS ARE THE POINT OF THIS FILE ═══

The issue's acceptance names two boards that must NOT move, and production showed a
third and fourth class that also must not:

  * a board mid-pass (#7537's rugby split)          -> `TestTheSplitBoardIsUntouched`
  * a fleet-wide ingestion stall                     -> `TestOurOwnOutageStillCannotBlankABoard`
  * live season props, legs stale / parent fresh     -> `TestEitherClauseAloneIsUnsound`
  * boards priced this minute, parent stale          -> `TestEitherClauseAloneIsUnsound`

A suite without all four cannot tell this rule from an absolute-age rule, which is
the rule #7537 was written to refuse.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import pytest

from app.utils.market_staleness import (
    BOARD_UNOBSERVED_DAYS,
    board_cannot_be_unobserved,
    OBSERVATION_LAG_DAYS,
    PRICES_STOPPED_DAYS,
    unobserved_board_keys,
)

#: The board's own newest write — the instant the market died.
BOARD_10_NEWEST = datetime(2026, 7, 19, 20, 30, 8, tzinfo=timezone.utc)

#: `futures_markets.updated_at` for board 10, measured: 2026-07-19T20:38:32Z. The
#: parent row froze eight minutes after the last leg, which is what "the venue
#: stopped listing it" looks like from our side.
BOARD_10_TOUCHED = datetime(2026, 7, 19, 20, 38, 32, tzinfo=timezone.utc)

#: The fleet's newest observation when this was measured. 64.7 days after the board.
FLEET_NOW = datetime(2026, 9, 22, 12, 21, 54, tzinfo=timezone.utc)

#: The six legs `/api/futures/10` still printed, and the 59 it had already withheld.
#: All 65 rows are the real stored values, not a reduction: the count feeds the
#: "withheld, not dropped" assertion, and a trimmed board cannot make it.
BOARD_10 = [
    ("Spain", 0.587142, "2026-07-19 20:30:08Z"),
    ("Argentina", 0.412858, "2026-07-19 20:30:08Z"),
    ("Albania", 0.0, "2026-05-02 20:30:07Z"),
    ("Algeria", 0.0, "2026-07-04 04:30:19Z"),
    ("Australia", 0.0, "2026-07-04 20:30:12Z"),
    ("Austria", 0.0, "2026-07-04 00:30:21Z"),
    ("Belgium", 0.0, "2026-07-12 00:32:39Z"),
    ("Bolivia", 0.0, "2026-05-02 20:30:07Z"),
    ("Bosnia & Herzegovina", 0.0, "2026-07-03 00:30:09Z"),
    ("Brazil", 0.0, "2026-07-06 20:30:14Z"),
    ("Canada", 0.0, "2026-07-05 16:30:14Z"),
    ("Cape Verde", 0.0, "2026-07-05 04:30:10Z"),
    ("Colombia", 0.0, "2026-07-09 00:30:13Z"),
    ("Croatia", 0.0, "2026-07-04 00:30:21Z"),
    ("Curaçao", 0.0, "2026-06-27 00:30:06Z"),
    ("Czech Republic", 0.0, "2026-06-26 00:32:18Z"),
    ("Denmark", 0.0, "2026-05-02 20:30:07Z"),
    ("DR Congo", 0.0, "2026-07-02 20:30:15Z"),
    ("Ecuador", 0.0, "2026-07-02 04:30:20Z"),
    ("Egypt", 0.0, "2026-07-08 16:30:10Z"),
    ("England", 0.0, "2026-07-16 20:31:34Z"),
    ("France", 0.0, "2026-07-16 00:31:00Z"),
    ("Germany", 0.0, "2026-07-01 00:30:05Z"),
    ("Ghana", 0.0, "2026-07-05 04:30:10Z"),
    ("Haiti", 0.0, "2026-06-21 08:30:33Z"),
    ("Iceland", 0.0, "2026-05-02 20:30:07Z"),
    ("Iran", 0.0, "2026-06-29 04:30:10Z"),
    ("Iraq", 0.0, "2026-06-27 20:30:19Z"),
    ("Italy", 0.0, "2026-05-02 20:30:07Z"),
    ("Ivory Coast", 0.0, "2026-07-01 16:30:21Z"),
    ("Jamaica", 0.0, "2026-05-02 20:30:07Z"),
    ("Japan", 0.0, "2026-06-30 20:30:04Z"),
    ("Jordan", 0.0, "2026-06-24 08:30:20Z"),
    ("Kosovo", 0.0, "2026-05-02 20:30:07Z"),
    ("Mexico", 0.0, "2026-07-07 04:30:10Z"),
    ("Morocco", 0.0, "2026-07-10 20:30:13Z"),
    ("Netherlands", 0.0, "2026-07-01 04:30:09Z"),
    ("New Caledonia", 0.0, "2026-05-02 20:30:07Z"),
    ("New Zealand", 0.0, "2026-06-28 04:30:18Z"),
    ("Northern Ireland", 0.0, "2026-05-02 20:30:07Z"),
    ("North Macedonia", 0.0, "2026-05-02 20:30:07Z"),
    ("Norway", 0.0, "2026-07-13 00:32:56Z"),
    ("Panama", 0.0, "2026-06-25 04:30:15Z"),
    ("Paraguay", 0.0, "2026-07-06 00:30:11Z"),
    ("Poland", 0.0, "2026-05-02 20:30:07Z"),
    ("Portugal", 0.0, "2026-07-07 20:30:15Z"),
    ("Qatar", 0.0, "2026-06-25 16:30:12Z"),
    ("Republic of Ireland", 0.0, "2026-05-02 20:30:07Z"),
    ("Romania", 0.0, "2026-05-02 20:30:07Z"),
    ("Saudi Arabia", 0.0, "2026-06-28 00:30:16Z"),
    ("Scotland", 0.0, "2026-06-29 00:30:06Z"),
    ("Senegal", 0.0, "2026-07-03 00:30:09Z"),
    ("Slovakia", 0.0, "2026-05-02 20:30:07Z"),
    ("South Africa", 0.0, "2026-06-29 20:30:15Z"),
    ("South Korea", 0.0, "2026-06-29 04:30:10Z"),
    ("Suriname", 0.0, "2026-05-02 20:30:07Z"),
    ("Sweden", 0.0, "2026-07-01 20:30:18Z"),
    ("Switzerland", 0.0, "2026-07-13 00:32:56Z"),
    ("Tunisia", 0.0, "2026-06-22 04:30:23Z"),
    ("Turkey", 0.0, "2026-06-21 08:30:33Z"),
    ("Ukraine", 0.0, "2026-05-02 20:30:07Z"),
    ("Uruguay", 0.0, "2026-06-28 00:30:16Z"),
    ("USA", 0.0, "2026-07-08 00:32:10Z"),
    ("Uzbekistan", 0.0, "2026-06-29 04:30:10Z"),
    ("Wales", 0.0, "2026-05-02 20:30:07Z"),
]

#: The four zeros that survive #7537 on this board, plus the two that make the hero.
SURVIVES_TODAY = {"Spain", "Argentina", "England", "France", "Norway", "Switzerland"}


def _stamp(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=timezone.utc)


def _outcome(oid, name, prob, stamp):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"odds_api_wc_{oid}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        # Measured: every row on board 10 carries `is_winner=False` and
        # `resolution_source=None`. Nobody graded this board; it simply stopped.
        is_winner=False,
        resolution_source=None,
        last_updated=stamp,
        price_changed_at=None,
        team_id=None,
        team=None,
        current_yes_bid=None,
        current_yes_ask=None,
    )


def _board(rows=None, *, status="open", touched=BOARD_10_TOUCHED, me=True):
    rows = BOARD_10 if rows is None else rows
    outcomes = [
        _outcome(i + 1, name, prob, _stamp(ts) if isinstance(ts, str) else ts)
        for i, (name, prob, ts) in enumerate(rows)
    ]
    return SimpleNamespace(
        id=10,
        name="FIFA World Cup Winner",
        description=None,
        category="championship",
        source="odds_api",
        external_id="soccer_fifa_world_cup_winner",
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type="field",
        market_tier=1,
        llm_sport_category="soccer",
        mutually_exclusive=me,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=touched,
        group_id=None,
        canonical_market_key="soccer:FIFA_WC:championship:",
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=outcomes,
    )


@contextmanager
def _at(now: datetime):
    """Pin the wall clock. `_format_market_detail` takes no `now` and reads it.

    🔴 Pinned to the REAL measured instant rather than to anything derived from
    the board, so that a rule which quietly started reading `now` would still
    have to agree with a rule that reads the fleet stamp — and the two disagree
    in `TestOurOwnOutageStillCannotBlankABoard`, which is where the mutant dies.
    """
    import app.routes.futures as futures_routes

    real = datetime

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz else now.replace(tzinfo=None)

    with mock.patch.object(futures_routes, "datetime", _Clock):
        assert real is datetime
        yield


def _served(board=None, *, fleet=FLEET_NOW):
    import app.routes.futures as futures_routes

    board = _board() if board is None else board
    with _at(FLEET_NOW):
        return futures_routes._format_market_detail(
            board, None, set(), fleet_newest_observation=fleet
        )


def _by_name(detail):
    return {row["name"]: row for row in detail["outcomes"]}


def _priced(detail):
    return {
        n: r["probability"]
        for n, r in _by_name(detail).items()
        if r["probability"] is not None
    }


class TestTheReaderStopsSeeingAnUndatedNumber:
    """The issue's acceptance line, on the real board."""

    def test_the_shipped_board_heroes_fifty_nine_percent_spain_today(self):
        """The defect, so the fix below is measured against a real BEFORE.

        A ship whose test suite contains no failing BEFORE proves only that the
        AFTER is self-consistent.
        """
        before = _served(fleet=None)
        assert before["prices_withheld"] == 59
        assert _priced(before)["Spain"] == pytest.approx(0.587142, abs=5e-7)
        assert set(_priced(before)) == SURVIVES_TODAY

    def test_no_leg_on_the_dead_board_carries_a_price(self):
        after = _served()
        assert _priced(after) == {}
        assert after["prices_withheld"] == 65

    def test_spain_specifically_loses_the_hero_number(self):
        """Named, because 'the hero' is not a payload field.

        The client crowns the leader on `probability ?? 0` and prints
        `formatProbability(null)` as `-`, so the payload-side statement of
        "no hero" is that the leg the hero would crown carries no number.
        """
        assert _by_name(_served())["Spain"]["probability"] is None

    def test_the_renormalised_one_point_zero_is_gone(self):
        """`0.587142 + 0.412858 = 1.000000` is what made the wreck look healthy.

        Asserting the SUM rather than the members: a fix that withheld Spain and
        left Argentina would squeeze Argentina to exactly 1.0 and print a 100%
        hero, which is worse than the defect and passes any per-leg assertion.
        """
        assert sum(_priced(_served()).values()) == 0

    def test_every_row_is_still_on_the_board(self):
        """Withheld, not dropped — the distinction #7537 made load-bearing.

        The reader still sees all 65 teams, each printing `-`. Dropping them
        would also pull rows out from under the chart's `canonical_board`.
        """
        after = _served()
        assert len(after["outcomes"]) == 65
        assert after["outcome_count"] == 65
        assert {r["name"] for r in after["outcomes"]} == {n for n, _, _ in BOARD_10}

    def test_a_withheld_price_is_null_and_never_zero(self):
        """`0` and `null` reach the renderer identically only if we send `0`.

        Sixty-three of these legs are stored at exactly `0.000000`, so a fix
        that zeroed instead of nulling would be invisible in any sum assertion
        and would print `0%` for Spain.
        """
        served = _served()["outcomes"]
        assert [r["probability"] for r in served] == [None] * 65


class TestTheSplitBoardIsUntouched:
    """Acceptance 2: a board mid-pass behaves exactly as it does today.

    #7537's own case. Some legs written this pass, some not — the board is
    being observed, so only the per-leg rule may speak.
    """

    def _split(self, *, touched_ago=timedelta(minutes=4)):
        newest = FLEET_NOW - timedelta(minutes=3)
        rows = [
            ("Leeds Rhinos", 0.302, newest),
            ("Hull KR", 0.190, newest),
            ("Wigan", 0.140, newest),
            # Eleven rows nobody repriced in a fortnight, all at one microsecond.
            *[(f"Club {i}", 0.11, newest - timedelta(days=14)) for i in range(11)],
        ]
        return _board(rows, touched=FLEET_NOW - touched_ago)

    def test_the_stale_eleven_are_withheld_and_the_quoted_three_are_not(self):
        priced = _priced(_served(self._split()))
        assert set(priced) == {"Leeds Rhinos", "Hull KR", "Wigan"}

    def test_the_board_clause_itself_contributes_nothing_here(self):
        """The rule under test, isolated — not the serialiser's composite answer.

        🪤 Asserting only the served payload would pass if the board clause
        withheld all fourteen and the per-leg clause happened to be asked first.
        """
        board = self._split()
        assert (
            unobserved_board_keys(
                ((o.id, o.last_updated) for o in board.outcomes),
                board_touched_at=board.updated_at,
                fleet_newest_observation=FLEET_NOW,
            )
            == set()
        )

    def test_a_split_board_whose_parent_went_quiet_is_still_untouched(self):
        """The Trump-out-by-September specimen: parent 19.2d, legs 0.2d.

        Measured on production. The parent row is rewritten when a market
        ATTRIBUTE changes, not on every visit, so parent silence is not
        evidence about prices and cannot be allowed to speak alone.
        """
        board = self._split(touched_ago=timedelta(days=19, hours=5))
        assert set(_priced(_served(board))) == {"Leeds Rhinos", "Hull KR", "Wigan"}


class TestOurOwnOutageStillCannotBlankABoard:
    """Acceptance 3, and the mutant that matters most.

    #7537 bought the guarantee that a fleet-wide ingestion stall withholds
    nothing, by measuring against the board instead of `now`. This rule adds a
    second reference and must not spend it.
    """

    def test_a_fleet_wide_stall_of_sixty_days_withholds_nothing_new(self):
        """Both stamps two months old; the board is one day behind the fleet.

        🔴 An absolute rule — `now - board_newest > 30d` — blanks this board.
        The fleet reference does not, because during an outage the reference
        ages with the board and the LAG stops growing. That is the whole
        structural difference and this is the only test that can see it.
        """
        stalled = FLEET_NOW - timedelta(days=60)
        rows = [(n, p, stalled - timedelta(days=1)) for n, p, _ in BOARD_10[:6]]
        board = _board(rows, touched=stalled - timedelta(days=1))
        assert set(_priced(_served(board, fleet=stalled))) == {n for n, _, _ in rows}

    def test_the_rule_never_reads_the_clock(self):
        """Structural, because behavioural clock tests are easy to write vacuously.

        🪤 The tempting version calls the rule twice in one instant and asserts
        the two answers agree. They always agree — a rule reading `now` agrees
        with itself — so that test passes on the mutant it exists to catch.
        This reads the source instead: the function must contain no clock call.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(unobserved_board_keys))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not called & {"now", "utcnow", "today", "time"}, (
            f"`unobserved_board_keys` reached for the wall clock ({called}). The "
            "fleet reference exists precisely so it does not have to — an "
            "absolute age cannot tell a dead board from our own outage."
        )


class TestEitherClauseAloneIsUnsound:
    """Both production directions, because each clause alone admits a live board.

    These are the tests that force the conjunction to stay a conjunction. Delete
    either clause and exactly one of them goes red.
    """

    def _keys(self, *, leg_lag, parent_lag):
        rows = [(n, p, FLEET_NOW - leg_lag) for n, p, _ in BOARD_10[:6]]
        board = _board(rows, touched=FLEET_NOW - parent_lag)
        return unobserved_board_keys(
            ((o.id, o.last_updated) for o in board.outcomes),
            board_touched_at=board.updated_at,
            fleet_newest_observation=FLEET_NOW,
        )

    def test_a_live_season_prop_with_stale_legs_keeps_its_price(self):
        """*Will Tommy DeVito finish as a top-12 QB* — legs 31.4d, parent 11.9d.

        Measured on production 2026-09-22, alongside *Buccaneers 2026-27*
        (41.9d / 11.9d) and *Sabrina Carpenter album in 2026* (62.8d / 12.0d).
        The leg clause alone withholds all three; every one is a genuinely open
        question whose parent row the poller touched inside a fortnight.
        """
        assert (
            self._keys(
                leg_lag=timedelta(days=31, hours=10),
                parent_lag=timedelta(days=11, hours=22),
            )
            == set()
        )

    def test_a_board_priced_this_minute_with_a_quiet_parent_keeps_its_price(self):
        """*Trump out as President by September 30?* — parent 19.2d, legs 0.2d.

        Measured, alongside *Will any CA state executives be federally charged*
        at 17.2d / 0.0d. The parent clause alone withholds prices written
        minutes ago.
        """
        assert (
            self._keys(
                leg_lag=timedelta(hours=5),
                parent_lag=timedelta(days=19, hours=5),
            )
            == set()
        )

    def test_a_board_priced_this_minute_whose_parent_is_past_the_floor(self):
        """*MLB: RBIs Leader* — parent lag > 45d, legs **0.1d**. Measured.

        🪤 THE CASE THE OBVIOUS CONTROL MISSES, and mutation is what found it.
        The two controls above both sit with at least one lag UNDER the floor,
        so deleting the leg clause leaves them green — the parent clause spares
        them on its own and the suite cannot tell the conjunction from the
        parent clause alone. Only a board whose parent is PAST the floor while
        its prices are minutes old can separate the two, and production has
        them: *Third-best AI Lab end of September* reads 0.0d against a parent
        well beyond 45 days.
        """
        assert (
            self._keys(
                leg_lag=timedelta(hours=2),
                parent_lag=timedelta(days=48),
            )
            == set()
        )

    def test_the_specimen_needs_both_and_has_both(self):
        """Board 10: 64.7d / 64.7d. The gap to the live population is not narrow.

        Every board hand inspection found live carried a parent lag <= 12.0
        days; every board it found finished carried >= 64.7. The constant sits
        between them with margin on each side, which is what makes it a
        boundary rather than a fitted threshold.
        """
        assert (
            len(
                self._keys(
                    leg_lag=timedelta(days=64, hours=17),
                    parent_lag=timedelta(days=64, hours=17),
                )
            )
            == 6
        )


class TestEveryMissingInputFailsOpen:
    """No evidence is not evidence of death — and a broken read is not either."""

    def _keys(self, **kw):
        board = _board()
        base = dict(
            board_touched_at=board.updated_at,
            fleet_newest_observation=FLEET_NOW,
        )
        base.update(kw)
        return unobserved_board_keys(
            ((o.id, o.last_updated) for o in board.outcomes), **base
        )

    def test_an_unreadable_fleet_stamp_withholds_nothing(self):
        """The route could not reach the database.

        🔴 The direction matters: a failed read must degrade to today's page,
        never to a blanked one. This is the difference between a database blip
        and a site-wide outage.
        """
        assert self._keys(fleet_newest_observation=None) == set()

    def test_a_non_datetime_fleet_stamp_withholds_nothing(self):
        assert self._keys(fleet_newest_observation="2026-09-22") == set()

    def test_an_unreadable_parent_stamp_withholds_nothing(self):
        """A board whose parent row was never stamped cannot be judged.

        This is also why every #7537 fixture stays green: they build markets
        with `updated_at=None`.
        """
        assert self._keys(board_touched_at=None) == set()

    def test_a_board_with_no_readable_leg_stamp_withholds_nothing(self):
        assert (
            unobserved_board_keys(
                [(1, None), (2, "not a datetime")],
                board_touched_at=BOARD_10_TOUCHED,
                fleet_newest_observation=FLEET_NOW,
            )
            == set()
        )

    def test_a_leg_whose_own_stamp_is_unreadable_stays_priced(self):
        """On a qualifying board, so the clause is the only thing being tested.

        The returned set is always a subset of the keys that carry a stamp —
        the same reading `_as_utc` gives everywhere else in this module.
        """
        keys = unobserved_board_keys(
            [(1, BOARD_10_NEWEST), (2, None)],
            board_touched_at=BOARD_10_TOUCHED,
            fleet_newest_observation=FLEET_NOW,
        )
        assert keys == {1}

    def test_a_naive_stamp_is_read_as_utc_rather_than_raising(self):
        """A naive/aware comparison raises `TypeError` at request time only."""
        keys = unobserved_board_keys(
            [(1, BOARD_10_NEWEST.replace(tzinfo=None))],
            board_touched_at=BOARD_10_TOUCHED.replace(tzinfo=None),
            fleet_newest_observation=FLEET_NOW,
        )
        assert keys == {1}


class TestTheBoundaryAndTheConstant:
    """A fourth clock, and the three ways it gets quietly folded into a third."""

    #: Far enough past the floor that the OTHER clause is never the reason.
    WELL_PAST = timedelta(days=BOARD_UNOBSERVED_DAYS + 20)

    def _keys(self, leg_lag, parent_lag):
        rows = [(n, p, FLEET_NOW - leg_lag) for n, p, _ in BOARD_10[:3]]
        board = _board(rows, touched=FLEET_NOW - parent_lag)
        return unobserved_board_keys(
            ((o.id, o.last_updated) for o in board.outcomes),
            board_touched_at=board.updated_at,
            fleet_newest_observation=FLEET_NOW,
        )

    # 🪤 EACH CLAUSE GETS ITS OWN BOUNDARY PAIR, and mutation is why. A single
    # test moving BOTH lags to the floor together passes when only one clause's
    # comparison is flipped: the clause still holding `<=` returns the empty set
    # first and the mutant never reaches the flipped one. A boundary test has to
    # put the other clause well past the floor or it is testing whichever clause
    # happens to be written first.
    def test_the_leg_clause_exactly_at_the_floor_is_not_withheld(self):
        assert (
            self._keys(timedelta(days=BOARD_UNOBSERVED_DAYS), self.WELL_PAST) == set()
        )

    def test_the_leg_clause_one_second_past_the_floor_is_withheld(self):
        assert (
            len(
                self._keys(
                    timedelta(days=BOARD_UNOBSERVED_DAYS, seconds=1), self.WELL_PAST
                )
            )
            == 3
        )

    def test_the_parent_clause_exactly_at_the_floor_is_not_withheld(self):
        assert (
            self._keys(self.WELL_PAST, timedelta(days=BOARD_UNOBSERVED_DAYS)) == set()
        )

    def test_the_parent_clause_one_second_past_the_floor_is_withheld(self):
        assert (
            len(
                self._keys(
                    self.WELL_PAST, timedelta(days=BOARD_UNOBSERVED_DAYS, seconds=1)
                )
            )
            == 3
        )

    def test_the_floor_is_not_shared_with_the_other_two_clocks(self):
        """Four clocks, four constants, and the warning is in all four docstrings.

        `PRICES_STOPPED_DAYS` folded into the parent clock once and a census by
        market tier is what caught it. This one reads the SAME COLUMN as
        `OBSERVATION_LAG_DAYS` and differs only in its reference, which makes it
        the easiest of the four to collapse by accident.
        """
        assert BOARD_UNOBSERVED_DAYS not in (OBSERVATION_LAG_DAYS, PRICES_STOPPED_DAYS)
        assert BOARD_UNOBSERVED_DAYS > OBSERVATION_LAG_DAYS

    def test_the_floor_clears_the_measured_live_population(self):
        """12.0 days was the largest parent lag on any board found live.

        Not a restatement of the constant: it is the margin claim the PR makes,
        so a later tightening has to come back through this assertion.
        """
        assert BOARD_UNOBSERVED_DAYS >= 2 * 12


class TestOnlyTheHeroSurfaceMoves:
    """Scope, asserted rather than described."""

    def test_a_settled_board_keeps_its_result(self):
        """Settled means settled — a result shows what ran (#7274's rule).

        The gate is `status == "open"`, and a settled World Cup board is
        precisely the row this rule must never touch.
        """
        priced = _priced(_served(_board(status="closed")))
        # Tolerance, not exactness: the settled path rounds (0.5871). The claim
        # is that the result SURVIVES, so pinning the 6th decimal here would
        # make this control fail for a reason that is not about this rule.
        assert priced["Spain"] == pytest.approx(0.587142, abs=1e-4)
        # All 65, not the 6 that survive today: BOTH staleness rules gate on
        # `status == "open"`, so a settled board keeps every stored number.
        assert len(priced) == 65

    def test_the_chart_route_is_not_handed_a_fleet_stamp(self):
        """`get_probability_timeline` must keep calling the formatter as before.

        🔴 It sorts the plotted series on `canonical_board[id]["probability"] or
        0`. Nulling every price on a dead board would collapse every sort key to
        0 and silently reorder which series get drawn — and the chart is the
        surface that was already telling the truth on board 10 ("Last number 64
        days ago"). Source-level because the reorder is invisible to any
        payload assertion that does not already know the right order.
        """
        import ast
        import inspect

        import app.routes.futures as futures_routes

        src = inspect.getsource(futures_routes.get_probability_timeline)
        tree = ast.parse(inspect.cleandoc(src).replace("async def", "def", 1))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_format_market_detail"
            ):
                assert not [
                    k for k in node.keywords if k.arg == "fleet_newest_observation"
                ], (
                    "The chart route now passes a fleet stamp. That nulls every "
                    "price on a dead board, and this route sorts its plotted "
                    "series on `probability or 0`."
                )

    def test_the_detail_route_does_pass_one(self):
        """The other half of the same claim — a scope test needs both directions."""
        import inspect

        import app.routes.futures as futures_routes

        src = inspect.getsource(futures_routes.get_futures_market)
        assert (
            "fleet_newest_observation=await _fleet_newest_observation(db, market)"
            in src
        )


class TestTheFleetReadItself:
    """The helper the route hands in."""

    @pytest.mark.asyncio
    async def test_a_failed_query_returns_none_rather_than_raising(self):
        """A database this route could not reach degrades to today's page.

        🔴 The failure mode this forbids is the loud one: an exception here
        would 500 the whole detail page for a staleness refinement.
        """
        import app.routes.futures as futures_routes

        class _Broken:
            async def execute(self, *a, **kw):
                raise RuntimeError("connection reset")

        assert (
            await futures_routes._fleet_newest_observation(_Broken(), _board()) is None
        )

    @pytest.mark.asyncio
    async def test_an_empty_table_returns_none(self):
        import app.routes.futures as futures_routes

        class _Empty:
            async def execute(self, *a, **kw):
                return SimpleNamespace(scalar_one_or_none=lambda: None)

        assert (
            await futures_routes._fleet_newest_observation(_Empty(), _board()) is None
        )

    @pytest.mark.asyncio
    async def test_a_board_that_cannot_qualify_never_reaches_the_database(self):
        """The query-count claim, asserted rather than described.

        LAT-P127 guards this route at three executes across two page loads. A
        board whose legs were written minutes ago must add none.
        """
        import app.routes.futures as futures_routes

        calls = []

        class _Counting:
            async def execute(self, *a, **kw):
                calls.append(1)
                return SimpleNamespace(scalar_one_or_none=lambda: FLEET_NOW)

        fresh = _board(
            [(n, p, datetime.now(timezone.utc)) for n, p, _ in BOARD_10[:3]],
            touched=datetime.now(timezone.utc),
        )
        assert (
            await futures_routes._fleet_newest_observation(_Counting(), fresh) is None
        )
        assert calls == [], "a board inside the floor must not query the fleet"

    @pytest.mark.asyncio
    async def test_a_board_that_could_qualify_does_reach_the_database(self):
        """Both directions — a skip test that never queries proves nothing."""
        import app.routes.futures as futures_routes

        calls = []

        class _Counting:
            async def execute(self, *a, **kw):
                calls.append(1)
                return SimpleNamespace(scalar_one_or_none=lambda: FLEET_NOW)

        assert (
            await futures_routes._fleet_newest_observation(_Counting(), _board())
            == FLEET_NOW
        )
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_a_settled_board_never_reaches_the_database(self):
        import app.routes.futures as futures_routes

        calls = []

        class _Counting:
            async def execute(self, *a, **kw):
                calls.append(1)
                return SimpleNamespace(scalar_one_or_none=lambda: FLEET_NOW)

        assert (
            await futures_routes._fleet_newest_observation(
                _Counting(), _board(status="closed")
            )
            is None
        )
        assert calls == []


class TestThePrefilterCanOnlySkipWork:
    """`board_cannot_be_unobserved` is the one place `now` appears in this ship.

    🔴 It exists so the fleet read does not run on every detail request
    (LAT-P127 guards that route at three executes across two page loads). It is
    sound because every stamp is in the past, so `fleet <= now` and therefore
    `fleet - board <= now - board`. The danger is that a later edit promotes it
    from "don't bother asking" to "withhold", which is exactly the absolute-age
    rule #7537 refuses.
    """

    def _rows(self, lag):
        return [(i, FLEET_NOW - lag) for i in range(3)]

    def test_a_board_inside_the_floor_of_now_skips_the_read(self):
        assert (
            board_cannot_be_unobserved(
                self._rows(timedelta(days=BOARD_UNOBSERVED_DAYS - 1)),
                board_touched_at=FLEET_NOW - timedelta(days=BOARD_UNOBSERVED_DAYS - 1),
                now=FLEET_NOW,
            )
            is True
        )

    def test_a_board_past_the_floor_of_now_does_not_skip(self):
        assert (
            board_cannot_be_unobserved(
                self._rows(timedelta(days=BOARD_UNOBSERVED_DAYS + 1)),
                board_touched_at=FLEET_NOW - timedelta(days=BOARD_UNOBSERVED_DAYS + 1),
                now=FLEET_NOW,
            )
            is False
        )

    def test_a_fleet_wide_stall_does_NOT_skip_the_read(self):
        """The property that keeps the outage guarantee whole.

        🔴 During a stall `now - board` keeps growing, so the prefilter answers
        False and the read HAPPENS — and then `unobserved_board_keys` compares
        against the frozen fleet stamp and withholds nothing. If the prefilter
        ever short-circuited to "withhold" instead of "ask", this is the case
        that would blank the site during our own outage.
        """
        stalled = FLEET_NOW - timedelta(days=90)
        assert (
            board_cannot_be_unobserved(
                self._rows(timedelta(days=90)),
                board_touched_at=stalled,
                now=FLEET_NOW,
            )
            is False
        )
        assert (
            unobserved_board_keys(
                self._rows(timedelta(days=90)),
                board_touched_at=stalled,
                fleet_newest_observation=stalled,
            )
            == set()
        )

    def test_the_route_hands_in_the_fleet_stamp_and_never_the_clock(self):
        """Structural, because the shortcut passes every behavioural test here.

        🪤 Handing `datetime.now()` to `unobserved_board_keys` once the
        prefilter says "could qualify" leaves the specimen blanked and the split
        board spared — only a real fleet-wide outage would reveal it.
        """
        import inspect

        import app.routes.futures as futures_routes

        src = inspect.getsource(futures_routes._fleet_newest_observation)
        assert "func.max(FuturesOutcome.last_updated)" in src, (
            "the fleet reference must come from the fleet's own newest "
            "observation, not from the clock"
        )
        assert "return datetime.now" not in src

    def test_a_skipped_board_is_read_as_withhold_nothing(self):
        assert (
            unobserved_board_keys(
                self._rows(timedelta(days=1)),
                board_touched_at=FLEET_NOW - timedelta(days=1),
                fleet_newest_observation=None,
            )
            == set()
        )


class TestASettledOpenBoardKeepsItsResult:
    """CERT-3298's required repair `8011-PRESERVE-SETTLED-OPEN-RESULTS`.

    🔴 THE BLOCK, AND IT WAS RIGHT. The first cut gated on
    `market.status == "open"` and read that as "unsettled". It is not:
    **gotcha #33 — settled Kalshi markets stay `status='open'` in our database**,
    because polling only ever sees open markets. Measured on production
    2026-09-22, **444 of the 969 boards this predicate admits carry an evidenced
    verdict**, and blanking them erases a RESULT rather than an unsourced price.
    "Settled means settled — a result shows what ran."

    `/futures/413` (*Finals MVP Winner*) is the specimen: it reads
    `status='open'` and heroes **99% Jalen Brunson**, and every one of its legs
    wears `resolution_source='api_settlement'`. That 99% is the ANSWER.

    🪤 And it is why `is_winner` alone cannot be the test. Brunson's own row is
    `is_winner=False, resolution_source='api_settlement'` on the losing legs;
    the column is `default=False`, so False is what a row is BORN with. The
    shared `leg_is_graded` reads the badge too, and treats `ungradeable_result`
    — a RETRACTION of a fabricated loss — as no verdict at all.
    """

    #: Board 413 as production serves it: open status, months of lag, graded.
    def _settled_open(self, *, source="api_settlement", winner=False):
        board = _board(
            [(n, p, FLEET_NOW - timedelta(days=40)) for n, p, _ in BOARD_10[:6]],
            touched=FLEET_NOW - timedelta(days=40),
        )
        for o in board.outcomes:
            o.resolution_source = source
            o.is_winner = winner
        return board

    def test_a_settled_open_board_keeps_every_price(self):
        priced = _priced(_served(self._settled_open()))
        assert len(priced) == 6, (
            "a board whose legs carry `api_settlement` is a RESULT; withholding "
            "its prices erases what ran (CERT-3298, 444 production boards)"
        )
        # Tolerance, not exactness: a graded board renders down the settled
        # path, which rounds (0.5871). That it rounds at all is itself the
        # confirmation the exemption reached that path.
        assert priced["Spain"] == pytest.approx(0.587142, abs=1e-4)

    def test_a_graded_winner_alone_exempts_the_board(self):
        """`is_winner IS TRUE` is the other half of the shared predicate.

        Nothing sets it by accident, so True is always a grader's decision.
        """
        board = self._settled_open(source=None, winner=False)
        board.outcomes[0].is_winner = True
        assert len(_priced(_served(board))) == 6

    def test_an_ungraded_board_is_still_withheld(self):
        """The repair must not swallow the ship. Board 10 has NO graded leg.

        Every one of its 65 rows is `is_winner=False, resolution_source=None`:
        nobody settled it, it simply stopped. 525 of the 969 admitted boards are
        this shape.
        """
        assert _priced(_served()) == {}

    def test_a_retracted_grade_is_not_a_verdict(self):
        """`ungradeable_result` is the badge written when a loss is RETRACTED.

        🪤 The tempting predicate is "has any resolution source". It would
        exempt every board whose fabricated losses were undone — republishing
        exactly the fossils this ship removes — and it is green on the two tests
        above, which both use `api_settlement`.
        """
        assert _priced(_served(self._settled_open(source="ungradeable_result"))) == {}

    def test_the_rule_itself_refuses_a_graded_board(self):
        """The helper, isolated from the serialiser's composite answer."""
        board = self._settled_open()
        assert (
            unobserved_board_keys(
                ((o.id, o.last_updated) for o in board.outcomes),
                board_touched_at=board.updated_at,
                fleet_newest_observation=FLEET_NOW,
                board_has_a_verdict=True,
            )
            == set()
        )

    def test_the_route_reads_the_shared_settlement_semantics(self):
        """Structural: `leg_is_graded`, not a local `is_winner` test.

        A hand-rolled predicate here would pass every behavioural test above and
        be wrong on the two cases the shared one exists for.
        """
        import inspect

        import app.routes.futures as futures_routes

        src = inspect.getsource(futures_routes._board_has_a_verdict)
        assert "leg_is_graded" in src

    @pytest.mark.asyncio
    async def test_a_graded_board_never_reaches_the_database(self):
        """Exempt boards cost no query either, and the two places agree."""
        import app.routes.futures as futures_routes

        calls = []

        class _Counting:
            async def execute(self, *a, **kw):
                calls.append(1)
                return SimpleNamespace(scalar_one_or_none=lambda: FLEET_NOW)

        assert (
            await futures_routes._fleet_newest_observation(
                _Counting(), self._settled_open()
            )
            is None
        )
        assert calls == []
