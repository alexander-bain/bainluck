"""#6358 — the NFL game a reader searches for is a phantom basketball fixture.

THE SHIP THESE GUARD. A production search for "Los Angeles R" returns exactly one
row, and it is the wrong one::

    14632820  Los Angeles Rams v San Francisco 49ers  americanfootball_nfl
              completed 7-27, espn 401872657, statpal 280446, 66 markets
    15305029  San Francisco v Los Angeles R           basketball_other
              scheduled 2026-09-10 00:00:00+00, 1 market   ← the only search hit

Both rows carry the Kalshi event ticker ``26SEP10SFLAR``. That is the id-anchored
correspondence ruling 048 names as arm A, and it is the ONLY thing that can pair
this couple: the sides are reversed, the away club is truncated to ``Los Angeles
R``, the sport key is wrong, and the ghost's kickoff is the ``00:00:00``
placeholder #6316 named — so no name rule, no competition map and no clock
reaches it. ``fixture_ticker_pass`` already knew how to decide this block. It was
never shown the rows, because the sweep read ``WHERE s.key LIKE 'soccer%'``.

TWO CHANGES, AND THE SECOND IS THE ONE THAT NEEDS GUARDING HARDEST.

1. :func:`plan_ghost_tags` PARTITIONS instead of the SQL filtering: the four
   name-based passes are handed :func:`row_is_soccer` rows and the fifth is
   handed everything. ``TestTheFourNameBasedPassesNeverSeeAnotherSport`` is the
   whole safety argument — it builds an NFL pair that WOULD pair under the first
   pass's own rule and proves no tag is produced.

2. The fifth pass's ghost arm becomes
   :func:`row_could_be_a_venue_ticker_ghost`, dropping "unscored and advertised"
   because the venue id already proved what those two were inferring. Six of the
   seven American football repairs are ``completed`` copies carrying the
   fixture's real final score (26SEP06LOUMISS reads 41-38 on BOTH rows, three
   markets on the anchored one and eighteen on the copy), so the strict arm
   refuses them for having been played.

WHAT DID NOT CHANGE, VERIFIED BY ID AND NOT BY COUNT. Over the sweep's own
-45d/+5d window on production 2026-09-15 — 5,653 rows resolving to exactly one
Kalshi event ticker, 4,785 distinct keys — the widened plan is 25 ghost rows, of
which the 16 soccer ones are the SAME 16 the shipped pass already tagged, one
block is still refused for holding two played canonicals, and the 9 new rows are
7 American football, the Rams row above, and Sabalenka v Rybakina.

WHAT IS STILL OUT OF REACH AND IS PINNED HERE SO NOBODY "FIXES" IT BY GUESSING.
366 tennis and 126 baseball blocks hold two or more rows on one event key with no
fixture-anchored row among them — tennis rows carry neither ``espn_id`` nor
``statpal_fixture_id``, so every row in the block fails
:func:`row_is_a_played_canonical` and the pass is silent by construction. One
Bonzi v Hanfmann match exists as six rows, five of them holding a single Kalshi
market each. ``test_a_block_with_no_authority_named_row_is_left_alone`` is that
population in miniature: the answer is a canonical test that does not depend on
an authority id, not "the row with the most markets wins", which is the
name-and-shape absorption gotcha #32 refuses.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tasks import soccer_ghost_twin_sweep as sweep  # noqa: E402
from app.utils.soccer_ghost_twins import (  # noqa: E402
    GHOST_KICKOFF_GRACE,
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    TWIN_FOUND,
    SoccerRow,
    classify_fixture_ticker_block,
    fixture_ticker_pass,
    plan_ghost_tags,
    residual_pass,
    row_could_be_a_ghost,
    row_could_be_a_venue_ticker_ghost,
    row_is_soccer,
    stranded_market_pass,
    ticker_pass,
)

#: Offsets from a fixed anchor, applied BEFORE anything is truncated (gotcha
#: #44). Nothing here may read the calendar: what every assertion needs is that
#: the rows sit outside the kickoff grace, never which day it is.
NOW = datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc)
PLAYED_AT = NOW - timedelta(days=4)
COPY_AT = PLAYED_AT - timedelta(hours=1)

RAMS_TICKER = "26SEP10SFLAR"
RAMS_CANON_ID = 14632820
RAMS_GHOST_ID = 15305029


def row(
    event_id,
    home,
    away,
    *,
    when=COPY_AT,
    sport_key="americanfootball_nfl",
    status="scheduled",
    scored=False,
    anchored=False,
    market_count=1,
    ticker_event_key=RAMS_TICKER,
):
    return SoccerRow(
        event_id=event_id,
        sport_key=sport_key,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status=status,
        has_final_score=scored,
        is_fixture_anchored=anchored,
        market_count=market_count,
        ticker_event_key=ticker_event_key,
    )


def rams_canonical(**kw):
    """14632820 — the game that was played: 7-27, ESPN and StatPal both name it."""
    base = dict(
        event_id=RAMS_CANON_ID,
        home="Los Angeles Rams",
        away="San Francisco 49ers",
        when=PLAYED_AT,
        sport_key="americanfootball_nfl",
        status="completed",
        scored=True,
        anchored=True,
        market_count=66,
    )
    return row(**{**base, **kw})


def rams_ghost(**kw):
    """15305029 — the same fixture as a scheduled `basketball_other` row."""
    base = dict(
        event_id=RAMS_GHOST_ID,
        home="San Francisco",
        away="Los Angeles R",
        when=COPY_AT,
        sport_key="basketball_other",
        status="scheduled",
        scored=False,
        anchored=False,
        market_count=1,
    )
    return row(**{**base, **kw})


class TestTheProductionSpecimen:
    def test_the_rams_block_is_decided_and_the_basketball_row_is_the_ghost(self):
        outcome, tags, explanation = classify_fixture_ticker_block(
            [rams_ghost(), rams_canonical()], now=NOW
        )

        assert outcome == TWIN_FOUND
        assert [(t.ghost_id, t.canonical_id) for t in tags] == [
            (RAMS_GHOST_ID, RAMS_CANON_ID)
        ]
        assert explanation == "fixture ticker"

    def test_the_whole_planner_takes_it_and_it_is_the_FIFTH_pass_that_does(self):
        """The tag is real AND it is attributed, because attribution is the only
        thing distinguishing "the id pass reached a new sport" from "a name pass
        quietly started judging football"."""
        plan = plan_ghost_tags([rams_ghost(), rams_canonical()], now=NOW)

        assert [t.ghost_id for t in plan.tags] == [RAMS_GHOST_ID]
        assert plan.fixture_tags == 1
        assert plan.fixture_blocks_examined == 1
        # Every other pass saw an empty population and said so.
        assert plan.blocks_examined == 0
        assert plan.residual_tags == 0
        assert plan.ticker_tags == 0
        assert plan.stranded_tags == 0

    def test_the_two_populations_are_counted_separately(self):
        plan = plan_ghost_tags([rams_ghost(), rams_canonical()], now=NOW)

        assert plan.rows_considered == 2
        assert plan.soccer_rows_considered == 0
        assert plan.ticker_rows_considered == 2

    def test_no_name_rule_could_have_paired_these_two(self):
        """The control. If this ever starts failing because the names became
        comparable, the specimen has been edited rather than the code fixed."""
        ghost, canonical = rams_ghost(), rams_canonical()

        assert ghost.home_team_name != canonical.away_team_name
        assert ghost.away_team_name not in (
            canonical.home_team_name,
            canonical.away_team_name,
        )
        assert not row_is_soccer(ghost) and not row_is_soccer(canonical)
        assert ghost.sport_key != canonical.sport_key


class TestAPlayedCopyIsStillACopy:
    """The six American football repairs the strict ghost arm refuses."""

    def ole_miss_pair(self):
        canonical = row(
            1177062,
            "Ole Miss Rebels",
            "Louisville Cardinals",
            when=PLAYED_AT,
            sport_key="americanfootball_ncaaf",
            status="completed",
            scored=True,
            anchored=True,
            market_count=3,
            ticker_event_key="26SEP06LOUMISS",
        )
        copy = row(
            15265652,
            "Ole Miss Rebels",
            "Louisville Cardinals",
            when=PLAYED_AT,
            sport_key="americanfootball_ncaaf",
            status="completed",
            scored=True,
            anchored=False,
            market_count=18,
            ticker_event_key="26SEP06LOUMISS",
        )
        return copy, canonical

    def test_a_completed_scored_unanchored_copy_is_tagged(self):
        copy, canonical = self.ole_miss_pair()

        outcome, tags, _ = classify_fixture_ticker_block([copy, canonical], now=NOW)

        assert outcome == TWIN_FOUND
        assert [(t.ghost_id, t.canonical_id) for t in tags] == [(15265652, 1177062)]

    def test_the_strict_arm_is_what_refused_it_and_still_would(self):
        """Names the exact predicate the widening replaced, so a revert cannot
        look like a no-op: this row is a ghost under the new arm and is not one
        under the old."""
        copy, _ = self.ole_miss_pair()

        assert row_could_be_a_venue_ticker_ghost(copy)
        assert not row_could_be_a_ghost(copy)

    def test_the_canonical_is_never_its_own_ghost(self):
        _, canonical = self.ole_miss_pair()

        assert not row_could_be_a_venue_ticker_ghost(canonical)


class TestTheFourNameBasedPassesNeverSeeAnotherSport:
    """The safety half of the widening, and the reason the partition is in the
    pure planner rather than in the SQL.

    A SQL ``WHERE`` clause cannot be unit-tested; a partition can. These rows are
    built to be the WORST case — an NFL pair that satisfies the first pass's own
    rule in every respect (identical names, identical sport key, the copy dated
    after the played row and inside ``MAX_GHOST_LAG``, the copy unanchored and
    unscored) — and carry no Kalshi ticker at all, so the fifth pass cannot reach
    them either. A tag here means a name-based pass has started judging football.
    """

    def nfl_name_pair(self, sport_key="americanfootball_nfl"):
        canonical = row(
            700001,
            "Kansas City Chiefs",
            "Denver Broncos",
            when=PLAYED_AT,
            sport_key=sport_key,
            status="completed",
            scored=True,
            anchored=True,
            market_count=0,
            ticker_event_key=None,
        )
        copy = row(
            700002,
            "Kansas City Chiefs",
            "Denver Broncos",
            when=PLAYED_AT + timedelta(days=1),
            sport_key=sport_key,
            status="scheduled",
            scored=False,
            anchored=False,
            market_count=9,
            ticker_event_key=None,
        )
        return copy, canonical

    def test_an_nfl_pair_a_name_pass_would_take_produces_no_tag(self):
        copy, canonical = self.nfl_name_pair()

        plan = plan_ghost_tags([copy, canonical], now=NOW)

        assert plan.tags == []
        assert plan.blocks_examined == 0
        assert plan.residual_blocks_examined == 0
        assert plan.ticker_blocks_examined == 0
        assert plan.stranded_blocks_examined == 0

    def test_the_identical_pair_in_soccer_IS_taken(self):
        """The mutation control for the test above. Without it, a partition that
        rejected EVERY row would pass, and so would a planner that had stopped
        running its first four passes altogether."""
        copy, canonical = self.nfl_name_pair(sport_key="soccer_epl")

        plan = plan_ghost_tags([copy, canonical], now=NOW)

        assert [t.ghost_id for t in plan.tags] == [700002]
        assert plan.fixture_tags == 0

    def test_a_football_row_cannot_dilute_a_soccer_block(self):
        """The other direction: adding the NFL specimen to a soccer population
        leaves every soccer number exactly where it was."""
        copy, canonical = self.nfl_name_pair(sport_key="soccer_epl")

        without = plan_ghost_tags([copy, canonical], now=NOW)
        with_football = plan_ghost_tags(
            [copy, canonical, rams_ghost(), rams_canonical()], now=NOW
        )

        assert without.blocks_examined == with_football.blocks_examined
        assert without.residual_tags == with_football.residual_tags
        assert without.ticker_tags == with_football.ticker_tags
        assert without.stranded_tags == with_football.stranded_tags
        assert {t.ghost_id for t in with_football.tags} == {
            t.ghost_id for t in without.tags
        } | {RAMS_GHOST_ID}

    def test_each_name_based_pass_is_handed_ONLY_soccer_rows(self, monkeypatch):
        """The contract stated directly, because a specimen can only ever probe
        the passes it happens to be shaped for.

        A behavioural test needs a pair that the pass under test would take, and
        passes 2 and 3 key on club legal suffixes and ticker-derived
        competitions — shapes that barely occur outside soccer, so a specimen
        built for them proves little and rots quietly. What must hold is simpler
        and is asserted here: whatever the population, the four name-based passes
        see the soccer partition and the fifth sees all of it.
        """
        seen: dict[str, set[int]] = {}

        def spy(name, real):
            def _wrapped(rows, **kw):
                seen[name] = {r.event_id for r in rows}
                return real(rows, **kw)

            return _wrapped

        # Patched through the module PATH rather than a module object, so this
        # file never mixes `import x` with `from x import y` — and patching the
        # module global is what the assertion needs anyway: `plan_ghost_tags`
        # resolves each pass in its own module namespace at call time, so the
        # name imported at the top of this file still reaches the spy.
        for name in ("residual_pass", "ticker_pass", "stranded_market_pass"):
            monkeypatch.setattr(
                f"app.utils.soccer_ghost_twins.{name}",
                spy(
                    name,
                    {
                        "residual_pass": residual_pass,
                        "ticker_pass": ticker_pass,
                        "stranded_market_pass": stranded_market_pass,
                    }[name],
                ),
            )
        monkeypatch.setattr(
            "app.utils.soccer_ghost_twins.fixture_ticker_pass",
            spy("fixture", fixture_ticker_pass),
        )

        soccer_copy, soccer_canonical = self.nfl_name_pair(sport_key="soccer_epl")
        plan_ghost_tags(
            [soccer_copy, soccer_canonical, rams_ghost(), rams_canonical()], now=NOW
        )

        soccer_ids = {soccer_copy.event_id, soccer_canonical.event_id}
        assert seen["residual_pass"] == soccer_ids
        assert seen["ticker_pass"] == soccer_ids
        assert seen["stranded_market_pass"] == soccer_ids
        assert seen["fixture"] == soccer_ids | {RAMS_GHOST_ID, RAMS_CANON_ID}

    def test_the_preseason_pair_is_taken_by_the_FIFTH_pass_and_not_the_third(self):
        """A real specimen for the pass that could plausibly have reached it.

        26AUG13ARILV is one fixture on two rows whose SPORT KEYS differ
        (`americanfootball_nfl` against `americanfootball_nfl_preseason`) while
        their Kalshi tickers name one competition — which is precisely the shape
        `ticker_pass` was built to merge, and the copy is dated a day AFTER the
        played row, inside `MAX_GHOST_LAG`, so its direction rule is satisfied
        too. Hand that pass every sport and it would take this pair on names. The
        tag must come from the id.
        """
        canonical = row(
            15196980,
            "Las Vegas Raiders",
            "Arizona Cardinals",
            when=PLAYED_AT,
            sport_key="americanfootball_nfl",
            status="completed",
            scored=True,
            anchored=True,
            market_count=1,
            ticker_event_key="26AUG13ARILV",
        )
        copy = row(
            15191796,
            "Las Vegas Raiders",
            "Arizona Cardinals",
            when=PLAYED_AT + timedelta(days=1),
            sport_key="americanfootball_nfl_preseason",
            status="completed",
            scored=True,
            anchored=False,
            market_count=19,
            ticker_event_key="26AUG13ARILV",
        )
        object.__setattr__(canonical, "ticker_sport_key", "americanfootball_nfl")
        object.__setattr__(copy, "ticker_sport_key", "americanfootball_nfl")

        plan = plan_ghost_tags([copy, canonical], now=NOW)

        assert [t.ghost_id for t in plan.tags] == [15191796]
        assert plan.fixture_tags == 1
        assert plan.ticker_tags == 0
        assert plan.ticker_blocks_examined == 0

    def test_row_is_soccer_reads_the_prefix_and_survives_a_null_key(self):
        assert row_is_soccer(row(1, "a", "b", sport_key="soccer_epl"))
        assert row_is_soccer(row(2, "a", "b", sport_key="soccer_other"))
        assert not row_is_soccer(row(3, "a", "b", sport_key="americanfootball_nfl"))
        assert not row_is_soccer(row(4, "a", "b", sport_key="basketball_other"))
        assert not row_is_soccer(row(5, "a", "b", sport_key=None))


class TestWhatTheWiderArmStillRefuses:
    def test_a_live_row_is_never_a_ghost_however_good_the_id(self):
        """The one exclusion the id does not buy out: a match in progress is
        unscored and may not be anchored yet, and mislabelling it reaches a
        reader mid-match."""
        live_copy = rams_ghost(status="live")

        assert not row_could_be_a_venue_ticker_ghost(live_copy)

        outcome, tags, _ = classify_fixture_ticker_block(
            [live_copy, rams_canonical()], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tags == []

    def test_a_row_inside_its_own_kickoff_grace_is_left_alone(self):
        just_kicked_off = rams_ghost(when=NOW - GHOST_KICKOFF_GRACE / 2)

        outcome, tags, _ = classify_fixture_ticker_block(
            [just_kicked_off, rams_canonical()], now=NOW
        )

        assert outcome == NOT_A_TWIN
        assert tags == []

    def test_two_authority_named_rows_on_one_ticker_are_refused(self):
        """The ghost has to be in the block for the refusal to be REACHED — with
        two canonicals and nothing else the answer is NOT_A_TWIN, which is a
        different sentence and would hide a regression that started picking one
        of the two authorities."""
        second = rams_canonical(event_id=RAMS_CANON_ID + 1)

        outcome, tags, explanation = classify_fixture_ticker_block(
            [rams_ghost(), rams_canonical(), second], now=NOW
        )

        assert outcome == REFUSE_AMBIGUOUS
        assert tags == []
        assert "authority has named one venue fixture twice" in explanation

    def test_a_block_with_no_authority_named_row_is_left_alone(self):
        """The tennis population in miniature — six rows, one fixture, not one of
        them carrying an espn or statpal id. Silent by construction, and it must
        stay silent: picking the market-richest row as the canonical would be
        absorption on shape."""
        rows = [
            row(
                15259290 + i,
                "Benjamin Bonzi",
                "Yannick Hanfmann",
                when=PLAYED_AT,
                sport_key="tennis_atp",
                status="closed",
                scored=False,
                anchored=False,
                market_count=1,
                ticker_event_key="26AUG02BONHAN",
            )
            for i in range(5)
        ] + [
            row(
                15186578,
                "Benjamin Bonzi",
                "Yannick Hanfmann",
                when=PLAYED_AT,
                sport_key="tennis_atp_canadian_open",
                status="completed",
                scored=True,
                anchored=False,
                market_count=18,
                ticker_event_key="26AUG02BONHAN",
            )
        ]

        outcome, tags, _ = classify_fixture_ticker_block(rows, now=NOW)

        assert outcome == NOT_A_TWIN
        assert tags == []

    def test_rows_on_different_tickers_are_never_one_block(self):
        elsewhere = rams_ghost(
            event_id=RAMS_GHOST_ID + 1, ticker_event_key="26SEP10OTHER"
        )

        plan = plan_ghost_tags([elsewhere, rams_canonical()], now=NOW)

        assert plan.tags == []
        assert plan.fixture_blocks_examined == 0


class TestTheReadIsBoundedAndTheBandKnowsAboutBothHalves:
    def test_the_population_sql_no_longer_refuses_every_other_sport(self):
        sql = sweep._POPULATION_SQL

        assert "s.key LIKE 'soccer%%'" in sql
        assert "OR EXISTS" in sql
        assert "fm.source = 'kalshi'" in sql

    def test_the_second_arm_is_bounded_by_the_kalshi_market_rather_than_open(self):
        """The bound is the point: a row with no Kalshi market can never carry an
        event key, so reading it changes no outcome and would sextuple a read
        that runs every twenty minutes (84,876 rows against 15,009, measured
        2026-09-15)."""
        sql = sweep._POPULATION_SQL

        arm = sql.split("OR EXISTS", 1)[1].split(")", 1)[0]
        assert "futures_markets" in arm
        assert "fm.event_id = e.id" in arm

    def test_the_soccer_floor_fires_while_the_ticker_rail_is_healthy(self):
        plan = plan_ghost_tags(
            [rams_ghost(), rams_canonical()]
            + [
                row(
                    800000 + i,
                    f"A{i}",
                    f"B{i}",
                    sport_key="americanfootball_nfl",
                    ticker_event_key=f"26SEP10T{chr(ord('A') + i % 26)}{i // 26}X",
                )
                for i in range(sweep.MIN_EXPECTED_TICKER_ROWS)
            ],
            now=NOW,
        )

        reason = sweep.band_refusal_reason(plan)

        assert reason is not None and "soccer row" in reason

    def test_the_ticker_floor_fires_while_the_soccer_join_is_healthy(self):
        plan = plan_ghost_tags(
            [
                row(
                    810000 + i,
                    f"Club C{i}",
                    f"Club D{i}",
                    sport_key="soccer_epl",
                    ticker_event_key=None,
                )
                for i in range(sweep.MIN_EXPECTED_ROWS)
            ],
            now=NOW,
        )

        reason = sweep.band_refusal_reason(plan)

        assert reason is not None and "event ticker" in reason

    def test_the_verdict_reports_both_halves_beside_the_total(self):
        """So an operator reading a quiet run can tell WHICH population went
        quiet — the whole reason there are two floors rather than one."""
        source = sweep.run_soccer_ghost_twin_sweep.__doc__ or ""
        import inspect

        body = inspect.getsource(sweep.run_soccer_ghost_twin_sweep)

        assert "soccer_rows_read" in body
        assert "ticker_rows_read" in body
        assert source  # the task still documents itself
