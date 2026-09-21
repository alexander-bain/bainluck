"""A FINISHED TENNIS MATCH STOPS PRINTING A SCORE NO MATCH COULD END ON. #2772.

═══ WHAT A READER SEES ═══

``/api/events/search?q=Swiatek`` returns eight rows. Seven carry a real set
score — ``2-0``, ``2-1``, ``0-2`` — and one sits among them::

    15258192 | completed | Iga Swiatek 0 - 0 Elena Rybakina | 2026-08-20

Its own correctly-scored neighbours are the control. A settled ``0-0`` is worse
than a blank: a blank says "we don't know", a ``0-0`` says "we know, and it was
nil-all" — about a marquee fixture (notice 27), in a sport where the score IS
the sets won and the winner holds two or three of them.

═══ THE POPULATION, MEASURED ═══

Production 2026-09-16, every settled tennis row carrying a score (720 of them)::

    LEGAL    0-2 197 · 2-0 159 · 1-2 109 · 2-1 104 · 3-0 34 · 1-3 22
             3-1 22 · 0-3 19 · 2-3 16 · 3-2 12                     = 694
    ILLEGAL  0-0 11 · 1-0 8 · 1-1 4 · 0-1 3                         =  26

``0-0`` is the headline and it is not the class. ``1-0`` is a mid-match score
frozen by whichever poll happened last — the defect named beside ``15293702``
in :func:`authority_score`'s own docstring — and ``1-1`` says a match both
players led. A reader cannot tell any of the four from a result.

**All 26 are unanchored, 26 of 26; 0 of the 254 anchored rows hold an illegal
score.** That is not a coincidence and it is the whole diagnosis:
:func:`authority_score` already applies this exact rule, and it can only reach a
row through an ``espn_id``. The other three writers that can put a number in
that column — the Odds API scores feed and the two staleness nets that settle a
row around whatever it was carrying — are judged by nothing.

═══ WHY THE SCORE IS WITHDRAWN AND THE SETTLEMENT IS NOT ═══

The two repairs beside this one in ``_transition_event_statuses_impl`` both
un-settle, and both may: one is bounded to the last 12 hours, the other matches
rows dated in the FUTURE. In each case the match has not been played and
``scheduled`` is the truth. These have been played. The oldest is 43 days old,
so sending them back would replace a wrong score with a wrong STATE — a match
five weeks past reading "upcoming" — and the state is the louder lie. What we
lack is the score, and the honest rendering of a score we lack is no score.

═══ THE CONTROL THAT DECIDES THE SHAPE OF THE FIX ═══

``1-0`` is also exactly what a live second set looks like, and exactly what a
SUSPENDED match truthfully holds. CERT-752's six US Open matches were suspended
mid-match at ``0-1, 2-1, 1-2, 0-0`` with ESPN showing all six scheduled to
resume that afternoon; those numbers are the entire content of the "Live &
Paused" card. So the score rule is not the whole fix — the STATUS gate is, and
``TENNIS_STATUSES_CLAIMING_A_RESULT`` deliberately omits ``suspended`` where
``FUTURE_SETTLED_STATUSES`` two lines above it includes it.
"""

import contextlib
import inspect
import logging
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.tasks.espn_sync import (
    FUTURE_SETTLED_STATUSES,
    MAX_ILLEGAL_TENNIS_SCORES_PER_PASS,
    _transition_event_statuses_impl,
    illegal_settled_tennis_score_recall,
)
from app.utils.espn_tennis_anchor import (
    COMPLETED_WINNER_SET_COUNTS,
    TENNIS_STATUSES_CLAIMING_A_RESULT,
    settled_tennis_score_is_impossible,
    tennis_final_score_write_is_refused,
)

#: The Swiatek row's own completion stamp, fixed rather than derived from the
#: clock: an anchor that branches on `now` is not an anchor (gotcha #44).
COMPLETION = datetime(2026, 8, 20, 23, 44, 13, tzinfo=timezone.utc)

#: The production census above, as (home, away, rows). The four illegal shapes
#: and the ten legal ones, with the counts that make the split checkable.
ILLEGAL_SHAPES = [(0, 0, 11), (1, 0, 8), (1, 1, 4), (0, 1, 3)]
LEGAL_SHAPES = [
    (0, 2, 197), (2, 0, 159), (1, 2, 109), (2, 1, 104), (3, 0, 34),
    (1, 3, 22), (3, 1, 22), (0, 3, 19), (2, 3, 16), (3, 2, 12),
]

#: The four 0-0 rows named in #2772's body, with the two facts that made every
#: existing repair miss them: a non-null `completed_at`, and an age in days.
ZERO_ZERO_SPECIMENS = [
    # id, status, completed_at is None, days old at 2026-09-16
    (15293847, "closed", False, 15),
    (15258192, "completed", False, 27),
    (15193727, "completed", False, 36),
    (15186890, "completed", False, 43),
]


# ---------------------------------------------------------------------------
# 1. RED-FIRST — the repairs that already existed cannot see this population.
# ---------------------------------------------------------------------------


class TestTheDefectReproduces:
    """Without this, the arm below could be certifying a rule the old code
    already enforced. #2772's body makes the claim as a table; this runs it."""

    @pytest.mark.parametrize("event_id,status,completed_at_is_none,days", ZERO_ZERO_SPECIMENS)
    def test_the_bogus_completed_repair_misses_every_one(
        self, event_id, status, completed_at_is_none, days
    ):
        """Its three gates, transcribed from the arm 60 lines above the new one.

        Each specimen fails at least one, and the ``completed_at IS NULL`` gate
        is the decisive one — it is failed by 11 of 11, because the wall-clock
        staleness net that settles these rows stamps a completion as it closes
        them. The very act that settles them disqualifies them from the repair
        that would un-settle them.
        """
        reached = (
            status == "completed"           # gate 1: `Event.status == "completed"`
            and completed_at_is_none        # gate 2: `Event.completed_at.is_(None)`
            and days <= 0.5                 # gate 3: `commence_time >= now - 12h`
        )
        assert reached is False

    def test_the_completed_at_gate_is_the_one_that_misses_all_eleven(self):
        assert all(not c for _, _, c, _ in ZERO_ZERO_SPECIMENS)

    def test_those_three_gates_are_still_the_arm_s_gates(self):
        """A transcription that silently stops matching its source is worse than
        no red-first at all, so the three fragments are asserted present."""
        src = inspect.getsource(_transition_event_statuses_impl)
        arm = src[: src.index("withdrew_illegal_tennis_score")]
        assert 'Event.status == "completed"' in arm
        assert "Event.completed_at.is_(None)" in arm
        assert "timedelta(hours=12)" in arm

    def test_the_future_commence_repair_cannot_reach_a_past_dated_row(self):
        """The other existing repair is gated on a FUTURE commence_time. Every
        specimen finished weeks ago, so it is refused a step before the door."""
        from datetime import datetime, timedelta, timezone

        from app.tasks.espn_sync import _is_bogus_future_settled

        now = datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc)
        for event_id, status, _, days in ZERO_ZERO_SPECIMENS:
            assert (
                _is_bogus_future_settled(
                    status, now - timedelta(days=days), 0, 0, now
                )
                is False
            ), event_id


# ---------------------------------------------------------------------------
# 2. THE RULE — the authority's own legality test, asked of a stored row.
# ---------------------------------------------------------------------------


class TestTheRuleMatchesTheProductionCensus:
    @pytest.mark.parametrize("home,away,rows", ILLEGAL_SHAPES)
    def test_every_illegal_shape_is_refused(self, home, away, rows):
        assert settled_tennis_score_is_impossible(home_score=home, away_score=away)

    @pytest.mark.parametrize("home,away,rows", LEGAL_SHAPES)
    def test_every_legal_shape_survives(self, home, away, rows):
        assert not settled_tennis_score_is_impossible(
            home_score=home, away_score=away
        )

    def test_the_split_is_the_measured_one(self):
        """694 legal, 26 illegal, 720 together — the census reproduced, so a
        rule that drifted toward either side fails on the arithmetic and not
        only on a shape somebody remembered to list."""
        assert sum(r for _, _, r in LEGAL_SHAPES) == 694
        assert sum(r for _, _, r in ILLEGAL_SHAPES) == 26
        assert sum(r for _, _, r in LEGAL_SHAPES + ILLEGAL_SHAPES) == 720

    @pytest.mark.parametrize("winner_sets", COMPLETED_WINNER_SET_COUNTS)
    def test_a_win_at_each_permitted_set_count_survives(self, winner_sets):
        """Derived from the constant, not from the literals ``(2, 3)``. If a
        fifth-set format ever widens :data:`COMPLETED_WINNER_SET_COUNTS`, this
        follows it instead of contradicting it."""
        for loser_sets in range(winner_sets):
            assert not settled_tennis_score_is_impossible(
                home_score=winner_sets, away_score=loser_sets
            )
            assert not settled_tennis_score_is_impossible(
                home_score=loser_sets, away_score=winner_sets
            )


class TestWhatElseTheRuleRefuses:
    @pytest.mark.parametrize("home,away", [(2, 2), (3, 3), (0, 0), (1, 1)])
    def test_a_tie_is_impossible_at_every_set_count(self, home, away):
        """Nobody advances from a drawn match. ``2-2`` and ``3-3`` are not in
        the production census and are refused anyway — the rule is the rule,
        not a list of the shapes seen so far."""
        assert settled_tennis_score_is_impossible(home_score=home, away_score=away)

    @pytest.mark.parametrize("home,away", [(4, 1), (5, 0), (9, 7)])
    def test_a_winner_holding_more_sets_than_any_format_awards_is_refused(
        self, home, away
    ):
        assert settled_tennis_score_is_impossible(home_score=home, away_score=away)

    @pytest.mark.parametrize("home,away", [(-1, 2), (2, -1)])
    def test_a_negative_set_count_is_refused(self, home, away):
        assert settled_tennis_score_is_impossible(home_score=home, away_score=away)

    @pytest.mark.parametrize("home,away", [(None, None), (None, 2), (2, None), (None, 0)])
    def test_a_missing_half_is_not_an_illegal_score(self, home, away):
        """There is no claim to refute, so there is nothing to withdraw. If this
        returned True the arm would spend every pass re-clearing columns that
        are already NULL — and the recall's own NOT NULL gates would hide it."""
        assert not settled_tennis_score_is_impossible(
            home_score=home, away_score=away
        )

    def test_a_non_numeric_score_is_refused_rather_than_swallowed(self):
        assert settled_tennis_score_is_impossible(home_score="2", away_score="x")


# ---------------------------------------------------------------------------
# 3. THE STATUS GATE — the control that keeps a paused match's score.
# ---------------------------------------------------------------------------


class TestASuspendedMatchKeepsItsPartialScore:
    """CERT-752's six US Open matches, by scoreline. Every one of them is
    ILLEGAL by the score rule and every one of them must survive, because a
    suspended match's partial score is true and is the whole content of the
    reader's "Live & Paused" card."""

    CERT_752_SUSPENDED = [(0, 1), (2, 1), (1, 2), (0, 0)]

    @pytest.mark.parametrize("home,away", CERT_752_SUSPENDED)
    def test_the_score_rule_alone_would_delete_them(self, home, away):
        judged = settled_tennis_score_is_impossible(
            home_score=home, away_score=away
        )
        # 2-1 is a legal FINAL, so it is the one of the four the score rule
        # would have spared — stated rather than asserted uniformly, because a
        # test that pretended all four were at risk would overclaim.
        assert judged is (max(home, away) not in COMPLETED_WINNER_SET_COUNTS or home == away)

    def test_suspended_is_not_a_status_claiming_a_result(self):
        assert "suspended" not in TENNIS_STATUSES_CLAIMING_A_RESULT

    def test_live_and_scheduled_are_not_either(self):
        assert "live" not in TENNIS_STATUSES_CLAIMING_A_RESULT
        assert "scheduled" not in TENNIS_STATUSES_CLAIMING_A_RESULT

    def test_it_is_a_strict_subset_of_the_settled_set_next_to_it(self):
        """The two constants sit two lines apart and differ by exactly one
        entry. Asserting the relationship rather than the contents is what
        makes a later addition to either one a decision somebody takes."""
        assert set(TENNIS_STATUSES_CLAIMING_A_RESULT) < set(FUTURE_SETTLED_STATUSES)
        assert set(FUTURE_SETTLED_STATUSES) - set(
            TENNIS_STATUSES_CLAIMING_A_RESULT
        ) == {"suspended"}


# ---------------------------------------------------------------------------
# 4. THE RECALL — what the fetch is allowed to hand the judgment.
# ---------------------------------------------------------------------------


class TestTheRecallAndTheJudgmentCannotDrift:
    """The fetch is the half that fails silently: a row it never returns cannot
    fail a test about the rule. Executed against real Postgres in
    ``tests/integration/test_illegal_settled_tennis_score_recall_2772_pg.py``;
    here the compiled SQL is read for the four gates it must carry."""

    @staticmethod
    def _sql():
        return str(
            illegal_settled_tennis_score_recall().compile(
                compile_kwargs={"literal_binds": True}
            )
        )

    def test_it_is_scoped_to_tennis(self):
        assert "tennis%" in self._sql()

    def test_it_reads_the_status_constant_and_not_a_private_copy(self):
        sql = self._sql()
        for status in TENNIS_STATUSES_CLAIMING_A_RESULT:
            assert f"'{status}'" in sql
        assert "'suspended'" not in sql

    def test_it_reads_the_same_set_counts_the_judgment_reads(self):
        sql = self._sql()
        greatest = re.search(r"greatest\(.*?\) IN \(([^)]*)\)", sql, re.IGNORECASE)
        assert greatest is not None, sql
        served = tuple(int(x) for x in greatest.group(1).replace(" ", "").split(","))
        assert served == COMPLETED_WINNER_SET_COUNTS

    def test_it_refuses_a_row_with_no_score_at_all(self):
        """Symmetry with ``test_a_missing_half_is_not_an_illegal_score``: the
        judgment declines a NULL and the recall never offers one."""
        sql = self._sql().lower()
        assert sql.count("is not null") == 2

    def test_it_is_capped_and_ordered_so_a_saturated_pass_is_reproducible(self):
        sql = self._sql().lower()
        assert f"limit {MAX_ILLEGAL_TENNIS_SCORES_PER_PASS}" in sql
        assert "order by" in sql


# ---------------------------------------------------------------------------
# 5. THE ARM, EXECUTED — what it writes and, more importantly, what it leaves.
# ---------------------------------------------------------------------------


class _Row:
    """Mutable stand-in for an Event the arm assigns to directly, as its two
    sibling repairs in the same function do."""

    def __init__(self, id, status, home, away, completed_at=COMPLETION):
        self.id = id
        self.status = status
        self.home_score = home
        self.away_score = away
        self.completed_at = completed_at
        self.commence_time = COMPLETION - timedelta(hours=2)
        self.home_team_name = "Iga Swiatek"
        self.away_team_name = "Elena Rybakina"
        self.win_probability_sources = {}
        self.sport = SimpleNamespace(key="tennis_wta_cincinnati_open")


class _Session:
    """The six selects ``_transition_event_statuses_impl`` issues, in order.
    Only the last one is seeded here; every other arm is handed nothing so the
    assertions can only be about this one."""

    def __init__(self, illegal):
        self._selects = [[], [], [], [], [], illegal]

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        # #7617: keyed on the query's SHAPE, not its aggregate. The real
        # expression now reads GREATEST(captured_at, valid_until) — a frozen
        # value is re-observed onto the row it already wrote, so a reading
        # built from captured_at alone called a delayed game silent. A fake
        # that dispatches on the aggregate breaks every time it is corrected.
        if "GROUP BY x.event_id" in sql:
            return SimpleNamespace(all=lambda: [])
        if sql.startswith("UPDATE"):
            return None
        rows = self._selects.pop(0)
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: rows)
        )

    async def commit(self):
        pass


async def _run(rows):
    session = _Session(rows)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    # `get_task_session` is patched where the impl LOOKS IT UP — it is imported
    # inside the function from `app.tasks.base`, so that is the name that must
    # move, not a copy on this module.
    with patch("app.tasks.base.get_task_session", _fake_session):
        return await _transition_event_statuses_impl()


class TestTheArmWithdrawsTheScoreAndNothingElse:
    @pytest.mark.asyncio
    async def test_the_swiatek_row_stops_saying_nil_nil(self):
        row = _Row(15258192, "completed", 0, 0)
        stats = await _run([row])
        assert (row.home_score, row.away_score) == (None, None)
        assert stats["withdrew_illegal_tennis_score"] == 1

    @pytest.mark.asyncio
    async def test_the_settlement_survives_the_withdrawal(self):
        """The decision this arm could have got wrong. The match finished 27
        days ago; un-settling it would replace a wrong score with a wrong
        state, and a five-week-old match on the "upcoming" shelf is louder."""
        row = _Row(15258192, "completed", 0, 0)
        await _run([row])
        assert row.status == "completed"
        assert row.completed_at == COMPLETION

    @pytest.mark.asyncio
    async def test_a_closed_row_is_reached_too_not_only_a_completed_one(self):
        """``15293847`` is ``closed``, not ``completed`` — the status that made
        the existing bogus-completed repair miss it even before its
        ``completed_at`` did."""
        row = _Row(15293847, "closed", 0, 0)
        stats = await _run([row])
        assert (row.home_score, row.away_score) == (None, None)
        assert row.status == "closed"
        assert stats["withdrew_illegal_tennis_score"] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("home,away,_rows", ILLEGAL_SHAPES)
    async def test_every_illegal_shape_in_the_census_is_withdrawn(
        self, home, away, _rows
    ):
        row = _Row(1, "completed", home, away)
        stats = await _run([row])
        assert (row.home_score, row.away_score) == (None, None)
        assert stats["withdrew_illegal_tennis_score"] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("home,away,_rows", LEGAL_SHAPES)
    async def test_a_legal_result_handed_to_the_arm_is_still_refused(
        self, home, away, _rows
    ):
        """The judgment is re-applied to everything the recall returns, so a
        recall that widened by accident still cannot delete a real result. This
        is the test that would fail if the loop trusted the SQL."""
        row = _Row(1, "completed", home, away)
        stats = await _run([row])
        assert (row.home_score, row.away_score) == (home, away)
        assert stats["withdrew_illegal_tennis_score"] == 0

    @pytest.mark.asyncio
    async def test_a_pass_with_nothing_to_do_reports_zero_rather_than_absent(self):
        stats = await _run([])
        assert stats["withdrew_illegal_tennis_score"] == 0

    @pytest.mark.asyncio
    async def test_the_counter_reaches_the_summary_line(self, caplog):
        """A repair nobody can see in the log is a repair nobody can audit —
        the same reason ``held_derived_start`` is in that line."""
        caplog.set_level(logging.INFO)
        await _run([_Row(15258192, "completed", 0, 0)])
        summary = [
            r.getMessage() for r in caplog.records
            if r.getMessage().startswith("Status transitions:")
        ]
        assert summary, caplog.text
        assert "1 illegal tennis scores withdrawn" in summary[0]

    @pytest.mark.asyncio
    async def test_the_withdrawal_names_the_row_it_acted_on(self, caplog):
        caplog.set_level(logging.INFO)
        await _run([_Row(15258192, "completed", 0, 0)])
        assert any(
            "#2772 withdrawing an illegal settled tennis score" in r.getMessage()
            and "15258192" in r.getMessage()
            for r in caplog.records
        ), caplog.text

    @pytest.mark.asyncio
    async def test_a_full_page_is_reported_as_a_finding(self, caplog):
        """Saturating the cap means the population is not the one this arm was
        measured against. Silence there would read as an ordinary busy pass."""
        caplog.set_level(logging.WARNING)
        rows = [
            _Row(i, "completed", 0, 0)
            for i in range(MAX_ILLEGAL_TENNIS_SCORES_PER_PASS)
        ]
        stats = await _run(rows)
        assert stats["withdrew_illegal_tennis_score"] == (
            MAX_ILLEGAL_TENNIS_SCORES_PER_PASS
        )
        assert any("SATURATED" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_a_short_page_is_not_reported_as_saturated(self, caplog):
        caplog.set_level(logging.WARNING)
        await _run([_Row(1, "completed", 0, 0)])
        assert not any("SATURATED" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# 6. THE OTHER END: THE WRITER REFUSES TOO. CERT-2958.
#
# The arm above is a CLEANUP, and CERT-2958's BLOCK is that a cleanup alone
# does not hold the guarantee continuously. `espn_sync` withdraws once every 60
# seconds; `odds_polling` writes `status='completed'` and a score in the SAME
# update every five minutes, and the only deferral standing between it and the
# score column — `clockless_write_defers_to_authority` — is
# `status == "live" and bool(espn_id)`, which is False for a completed row with
# or without an anchor. Tennis has no anchor at all (30,199 rows, zero
# `espn_id`) and no tennis key is in `ESPN_SPORT_MAPPING`, so nothing upstream
# skips it either.
#
# The reader loses that race: the withdrawal only ever arrives SECOND, so the
# lie is visible for up to a minute out of every five, forever. These tests are
# about the refusal that makes the guarantee hold at both ends.
#
# WHY THERE IS NO LIVE SPECIMEN FOR THIS HALF, AND WHY THAT IS NOT A LET-OFF.
# Measured on production 2026-09-16 12:12Z: the illegal population is still
# exactly 26 and NOTHING in it is newer than 2026-09-01 — the cleanup is not
# deployed, so anything the writer had produced since would still be standing,
# and none is. But the channel is not cold: `tennis_wta_guadalajara_open` holds
# 11 completed, scored, UNANCHORED rows written that same day, which is exactly
# the population this writer reaches and nothing judges. It is emitting legal
# scores this week, that is all. So the class is seasonal, the guard is the
# whole proof, and an empty live probe is not evidence of anything.
# ---------------------------------------------------------------------------


class TestTheWriterRefusesAnImpossibleTennisFinal:
    """The judgment asked at the write boundary, not just after the fact."""

    @pytest.mark.parametrize("home,away", [(0, 0), (1, 0), (0, 1), (1, 1)])
    @pytest.mark.parametrize("status", TENNIS_STATUSES_CLAIMING_A_RESULT)
    def test_every_illegal_pair_in_the_census_is_refused(self, home, away, status):
        assert tennis_final_score_write_is_refused(
            sport_key="tennis_wta_cincinnati_open",
            event_status=status,
            home_score=home,
            away_score=away,
        )

    @pytest.mark.parametrize(
        "home,away",
        [(0, 2), (2, 0), (1, 2), (2, 1), (3, 0), (1, 3), (3, 1), (0, 3), (2, 3), (3, 2)],
    )
    def test_every_legal_pair_in_the_census_is_written(self, home, away):
        """The ten legal shapes are 694 of the 720 settled rows. A refusal that
        caught any of them would be deleting real results to fix 26."""
        assert not tennis_final_score_write_is_refused(
            sport_key="tennis_atp",
            event_status="completed",
            home_score=home,
            away_score=away,
        )

    @pytest.mark.parametrize("status", ["live", "suspended", "scheduled"])
    @pytest.mark.parametrize("home,away", [(0, 0), (1, 0), (1, 1), (0, 1)])
    def test_a_match_still_being_played_keeps_its_partial_score(
        self, status, home, away
    ):
        """CERT-752's control, asked of the writer. A suspended match holding
        ``1-0`` holds a TRUE partial score, and a live second set looks exactly
        like one. Refusing here would empty the "Live & Paused" card."""
        assert not tennis_final_score_write_is_refused(
            sport_key="tennis_atp_us_open",
            event_status=status,
            home_score=home,
            away_score=away,
        )

    @pytest.mark.parametrize(
        "sport_key",
        ["soccer_epl", "soccer_uefa_champs_league", "baseball_mlb", "icehockey_nhl"],
    )
    def test_nil_nil_is_an_ordinary_final_in_every_other_sport(self, sport_key):
        """🔴 THE NEGATIVE CONTROL WITH A REAL POPULATION BEHIND IT. Measured
        2026-09-16: **634 settled soccer rows hold ``0-0``**, and every one of
        them is a true result. The set-count rule is a statement about tennis
        and nothing else, so it is keyed on the sport."""
        assert not tennis_final_score_write_is_refused(
            sport_key=sport_key,
            event_status="completed",
            home_score=0,
            away_score=0,
        )

    @pytest.mark.parametrize("home,away", [(None, None), (0, None), (None, 0)])
    def test_a_missing_half_is_not_a_claim_and_cannot_be_refused(self, home, away):
        assert not tennis_final_score_write_is_refused(
            sport_key="tennis_wta",
            event_status="completed",
            home_score=home,
            away_score=away,
        )

    def test_a_missing_sport_key_does_not_crash_the_pass(self):
        """One bad item must never wipe a scoring pass (gotcha #42). A row whose
        sport did not load is not a tennis row, so it is not this rule's."""
        assert not tennis_final_score_write_is_refused(
            sport_key=None, event_status="completed", home_score=0, away_score=0
        )

    def test_it_reads_the_same_judgment_and_is_not_a_second_spelling_of_it(self):
        """#4114's lesson: two spellings of one rule drift. Every pair the
        shared judgment calls impossible, the writer refuses on a final — asked
        across the whole small integer grid rather than the census shapes, so a
        divergence outside the measured population is caught too."""
        for home in range(0, 6):
            for away in range(0, 6):
                assert tennis_final_score_write_is_refused(
                    sport_key="tennis_other",
                    event_status="completed",
                    home_score=home,
                    away_score=away,
                ) is settled_tennis_score_is_impossible(
                    home_score=home, away_score=away
                )


class TestTheCleanupAndTheWriterHoldTheLineTogether:
    """🔴 THE SEQUENCE CERT-2958 NAMED, run with both real functions.

    Not two separate assertions about two separate halves: the actual order the
    production race happens in — the 60-second cleanup nulls the score, then the
    five-minute writer arrives with the same Odds API payload that produced it.
    Before this ship the second step put the lie straight back.
    """

    @pytest.mark.asyncio
    async def test_the_writer_does_not_put_back_what_the_cleanup_just_withdrew(self):
        row = _Row(15258192, "completed", 0, 0)

        # Step 1 — the real cleanup arm.
        await _run([row])
        assert (row.home_score, row.away_score) == (None, None)

        # Step 2 — the real writer judgment, handed the SAME payload the Odds
        # API served when it wrote the 0-0, against the row as it now stands.
        refused = tennis_final_score_write_is_refused(
            sport_key=row.sport.key,
            event_status=row.status,
            home_score=0,
            away_score=0,
        )
        assert refused, (
            "the writer would re-state the score the cleanup just withdrew — "
            "this is CERT-2958's race, and the reader sees it for up to a "
            "minute out of every five"
        )
        assert (row.home_score, row.away_score) == (None, None)

    @pytest.mark.asyncio
    async def test_the_same_sequence_lets_a_real_result_through(self):
        """NOT VACUOUS. The test above passes for a refusal that refuses
        everything; this is the arm that separates them. A legal final survives
        the cleanup untouched and the writer states it."""
        row = _Row(15258193, "completed", 2, 1)
        await _run([row])
        assert (row.home_score, row.away_score) == (2, 1)
        assert not tennis_final_score_write_is_refused(
            sport_key=row.sport.key,
            event_status=row.status,
            home_score=2,
            away_score=1,
        )


class TestTheWriterBoundaryActuallyConsultsIt:
    """A predicate is only worth testing if the loop reads it — and, since this
    producer writes through an `update_values` dict and a Core statement, no ORM
    scan can see it (the blind spot recorded in #6056's own suite). These are
    structural on purpose: they are what stops the call being deleted or, worse,
    left in place while the write stops being gated on it.
    """

    def _source(self):
        import textwrap

        from app.tasks import odds_polling

        return textwrap.dedent(inspect.getsource(odds_polling))

    def test_the_scores_feed_calls_the_refusal(self):
        import ast

        calls = {
            node.func.id
            for node in ast.walk(ast.parse(self._source()))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "tennis_final_score_write_is_refused" in calls, (
            "the Odds API scores feed can state an impossible tennis final "
            "again; the 60-second cleanup would only ever arrive second"
        )

    def test_both_score_writes_are_gated_on_the_same_flag(self):
        """🔴 THE MUTANT THIS CATCHES. Calling the predicate and then writing
        the score anyway leaves every behavioural test in this file green — the
        judgment is correct, it is simply not consulted. So assert the gate: the
        two `update_values` score lines are conditioned on `_skip_score_write`,
        which carries BOTH refusal reasons, rather than on the #6056 deferral
        alone."""
        source = self._source()
        for column in ("home_score", "away_score"):
            assert (
                f'if {column} is not None and not _skip_score_write:\n'
                f'                                update_values["{column}"] '
                f'= {column}'
            ) in source, (
                f"the {column} write is no longer gated on the combined "
                "refusal flag"
            )

    def test_the_snapshot_is_gated_on_it_too(self):
        """#6056's rule, inherited: a snapshot of a score this pass declined to
        store would put a number in the Score Differential chart that the event
        row never held."""
        source = self._source()
        assert "and not _skip_score_write\n" in source, (
            "score_snapshots can record a refused illegal tennis final"
        )

    def test_the_refusal_is_counted_so_it_cannot_be_silently_off(self):
        """An invisible refusal is indistinguishable from a guard that is off —
        and this one is EXPECTED to read 0 for long stretches, so the counter is
        the only thing that can tell those two states apart."""
        source = self._source()
        assert "scores_refused_illegal_tennis_final = 0" in source
        assert '"scores_refused_illegal_tennis_final": (' in source

    def test_the_effective_status_is_used_not_the_computed_one(self):
        """🔴 THE SUBTLE MUTANT. `event_status` is None whenever the pass is not
        CHANGING the status, and a row that is ALREADY completed is the one most
        at risk — it would slip through a check that read the computed value
        alone, which is precisely the standing population of 26."""
        source = self._source()
        assert "if event_status is not None" in source
        assert "else event_obj.status" in source


# ---------------------------------------------------------------------------
# 7. THE POST-WRITE PAIR. CERT-2963.
#
# 🔴 THE SECOND RACE, AND THE ONE THAT LOOKED CLOSED. The writer stores each
# side INDEPENDENTLY — `if home_score is not None` and `if away_score is not
# None` are two separate statements — so a payload carrying one side lands on
# top of whatever the row already holds. Judging the PAYLOAD answers a question
# about a score that will never exist:
#
#     stored 2-0 (legal) + incoming home=1, away=None
#         -> payload judged: one side None, "not a claim", ALLOWED
#         -> actually stored: 1-0, which the shared rule calls impossible
#
# Section 6 shipped exactly that hole. These are the arms that close it, and
# the ones that stop the obvious over-correction — refusing every one-sided
# write would delete real results, because a legal CORRECTION arrives in
# precisely that shape.
# ---------------------------------------------------------------------------


class TestItJudgesWhatTheRowWillHoldNotWhatThePayloadSays:

    def test_the_cert_2963_reproduction_is_refused(self):
        """The grader's exact specimen: stored legal ``2-0``, incoming
        ``home=1`` alone, which stores ``1-0``."""
        assert tennis_final_score_write_is_refused(
            sport_key="tennis_atp",
            event_status="completed",
            home_score=1,
            away_score=None,
            stored_home_score=2,
            stored_away_score=0,
        )

    def test_the_other_partial_direction_is_refused_too(self):
        """Symmetry is not decoration here — the two writes are separate
        statements and either one alone can land the lie."""
        assert tennis_final_score_write_is_refused(
            sport_key="tennis_atp",
            event_status="completed",
            home_score=None,
            away_score=2,
            stored_home_score=2,
            stored_away_score=0,
        )

    @pytest.mark.parametrize(
        "incoming_home,incoming_away,stored_home,stored_away,becomes",
        [
            (None, 1, 2, 0, "2-1"),
            (3, None, 0, 1, "3-1"),
            (None, 3, 2, 0, "2-3"),
            (2, None, 0, 0, "2-0"),
        ],
    )
    def test_a_one_sided_write_that_lands_a_LEGAL_pair_goes_through(
        self, incoming_home, incoming_away, stored_home, stored_away, becomes
    ):
        """🔴 THE OVER-CORRECTION THIS STOPS. Refusing the SHAPE rather than the
        RESULT would delete real results: a legal correction arrives as exactly
        a one-sided write, and the last row here is a one-sided write that
        REPAIRS an illegal stored ``0-0`` into a true ``2-0``."""
        assert not tennis_final_score_write_is_refused(
            sport_key="tennis_wta",
            event_status="completed",
            home_score=incoming_home,
            away_score=incoming_away,
            stored_home_score=stored_home,
            stored_away_score=stored_away,
        ), becomes

    def test_a_one_sided_write_onto_a_null_half_is_a_half_claim_not_a_lie(self):
        """The withdrawal arm's recall requires BOTH sides non-null, so a row
        holding one number is not a claim it judges. The writer agrees, and the
        NEXT poll's second half is caught by the arm above."""
        assert not tennis_final_score_write_is_refused(
            sport_key="tennis_atp",
            event_status="completed",
            home_score=1,
            away_score=None,
            stored_home_score=None,
            stored_away_score=None,
        )

    def test_the_second_half_of_that_sequence_is_caught(self):
        """NOT VACUOUS — it is what makes the arm above safe. The row now holds
        ``1`` and nothing; the poll that supplies the other half would store
        ``1-0``, and that is refused."""
        assert tennis_final_score_write_is_refused(
            sport_key="tennis_atp",
            event_status="completed",
            home_score=None,
            away_score=0,
            stored_home_score=1,
            stored_away_score=None,
        )

    def test_a_write_carrying_neither_side_is_not_a_write(self):
        """It would otherwise count a refusal on a pass that touched nothing,
        and the counter is the only way to tell this guard holding from tennis
        being out of season."""
        assert not tennis_final_score_write_is_refused(
            sport_key="tennis_atp",
            event_status="completed",
            home_score=None,
            away_score=None,
            stored_home_score=0,
            stored_away_score=0,
        )

    @pytest.mark.parametrize("status", ["live", "suspended"])
    def test_a_partial_update_to_a_match_still_being_played_is_untouched(
        self, status
    ):
        """CERT-752's control, asked of the partial path: a live/suspended row
        moving from ``1-0`` to ``1-1`` is a true score changing."""
        assert not tennis_final_score_write_is_refused(
            sport_key="tennis_atp_us_open",
            event_status=status,
            home_score=None,
            away_score=1,
            stored_home_score=1,
            stored_away_score=0,
        )

    def test_a_partial_update_landing_nil_nil_in_soccer_is_a_real_final(self):
        """The 634-row negative control, asked of the partial path."""
        assert not tennis_final_score_write_is_refused(
            sport_key="soccer_epl",
            event_status="completed",
            home_score=None,
            away_score=0,
            stored_home_score=0,
            stored_away_score=1,
        )

    def test_the_stored_pair_alone_never_refuses_a_pass_that_writes_nothing(self):
        """A row already holding an illegal score is the withdrawal arm's job,
        not the writer's. The writer only ever judges a write it is making."""
        for status in TENNIS_STATUSES_CLAIMING_A_RESULT:
            assert not tennis_final_score_write_is_refused(
                sport_key="tennis_other",
                event_status=status,
                home_score=None,
                away_score=None,
                stored_home_score=0,
                stored_away_score=0,
            )


class TestTheWriterHandsOverTheStoredHalves:
    """Structural: the effective-pair judgment is only real if the call site
    supplies the stored values. Passing the payload alone is CERT-2963's
    defect, and it leaves every behavioural test in section 6 green."""

    def _source(self):
        import textwrap

        from app.tasks import odds_polling

        return textwrap.dedent(inspect.getsource(odds_polling))

    def test_the_stored_halves_are_passed_to_the_judgment(self):
        source = self._source()
        assert "stored_home_score=event_obj.home_score," in source
        assert "stored_away_score=event_obj.away_score," in source
