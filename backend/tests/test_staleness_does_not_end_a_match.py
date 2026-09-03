"""A MATCH ENDS WHEN SOMETHING THAT WATCHED IT SAYS SO — live/048, CERT-752.

═══ WHAT THIS SUITE IS FOR ═══

CERT-752 blocked the first cut of this repair, and the block is the reason this
file exists. That cut was RIGHT about the negative rule — a Kalshi price tick is
not evidence of play, so it must not hold a match live — and it shipped that
rule with 50 tests. What it had no rule for was the state the row lands in once
the ticks stop counting. The next transition pass found no admitted snapshot,
took the wall-clock fallback, and wrote:

    status='closed', pm_resolved=1, blend graded 1.0/0.0 off a score of 1-2

on a US Open match that was SUSPENDED and scheduled to resume that afternoon.
Every client renders ``closed`` as Final. So the fix replaced a false LIVE with
a false FINAL, and only one of those two grades a market.

The lesson generalises past this bug, and it is what these tests actually pin:
**a negative rule needs the positive authority next to it.** Saying what may not
decide state is only half a rule; the other half is naming what may. That half
is the state ladder, EVENT-GRAPH-DOCTRINE §R:

    authority state  >  venue settlement  >  scores  >  (never) price

and wall-clock silence, which is what a staleness net has, is below all four.

═══ THE SPECIMEN ═══

Every end-to-end case below is built on event 15295047, De Jong v Passaro,
measured on production 2026-09-02: tennis, ~15 hours past its recorded start,
score 1-2 in sets, every one of its post-commence snapshots ``source='kalshi'``,
ESPN reporting it scheduled to resume. It is the exact row CERT-752 ran through
an exact-head harness to produce ``closed`` / ``pm_resolved=1``.

═══ RED-FIRST ═══

Verified by reverting ONLY the four source files and re-running this file: the
behavioural cases go red, the controls stay green in BOTH arms. Controls that
fail against pre-fix source cannot tell you the fix left the healthy direction
alone — they just re-report that the fix is absent. See
``TestTheHealthyDirectionIsUntouched``.
"""
import ast
import contextlib
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ONE odds-net harness, not two. `test_event_completion` already builds a
# fake session that applies the net's Core `UPDATE` back onto the row, which
# is the only way `ev.status` reads the way the database would — the net does
# not use ORM attribute assignment. A second copy here would agree today and
# drift later, which is the failure mode this whole file is about.
from tests.test_event_completion import (  # noqa: E402
    _OddsEv,
    _run_odds_net,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 2, 15, 0, tzinfo=UTC)

#: De Jong v Passaro's recorded start, ~15h before NOW — well past tennis's 6.0h
#: maximum, which is what puts it in front of the staleness net at all.
DE_JONG_START = NOW - timedelta(hours=15)

#: The shared odds harness freezes its own clock; its cases anchor to that
#: one so the two files cannot disagree about "now".
from tests.test_event_completion import NOW as HARNESS_NOW  # noqa: E402


# ---------------------------------------------------------------------------
# The ladder, as a set of pure rules.
# ---------------------------------------------------------------------------


class TestTheLadderIsWrittenDown:
    def test_suspended_is_the_states_actual_name(self):
        from app.utils.event_completion import EVENT_SUSPENDED

        # live/044 asked for `scheduled|live|suspended|final`; this is its first
        # rung, and the payload work depends on the spelling.
        assert EVENT_SUSPENDED == "suspended"

    def test_suspended_is_not_a_settled_state(self):
        from app.utils.event_completion import EVENT_SUSPENDED, SETTLED_STATUSES

        # THE load-bearing assertion of the whole change. Roughly a hundred
        # queries across tasks and routes mean "settled" by writing
        # `status IN ('completed','closed')`, and every one of them excludes
        # `suspended` for free — calibration, backfill_winners, the PM
        # resolution ladder, the excitement index. If `suspended` ever joined
        # this set, a suspended match would start being graded again and the
        # repair would silently unwind.
        assert EVENT_SUSPENDED not in SETTLED_STATUSES
        assert SETTLED_STATUSES == frozenset({"completed", "closed"})

    def test_an_authority_may_settle_a_suspended_row_in_one_hop(self):
        from app.utils.event_completion import EVENT_SUSPENDED, authority_may_settle

        # Without this, `suspended` would be a trap: the net could put a row in
        # but ESPN's `post` could not take it out, because every settle site
        # gated on `status == "live"`.
        assert authority_may_settle(EVENT_SUSPENDED) is True
        assert authority_may_settle("live") is True

    def test_an_authority_does_not_re_settle_a_settled_row(self):
        from app.utils.event_completion import authority_may_settle

        # Churning `closed` into `completed` rewrites history for no reader,
        # and un-settling is a bigger claim with its own predicate (#1201).
        assert authority_may_settle("closed") is False
        assert authority_may_settle("completed") is False

    def test_a_match_nobody_started_cannot_have_finished(self):
        from app.utils.event_completion import authority_may_settle

        assert authority_may_settle("scheduled") is False

    def test_play_resumes_a_suspended_row(self):
        from app.utils.event_completion import EVENT_SUSPENDED, play_resumes

        assert play_resumes(EVENT_SUSPENDED) is True
        assert play_resumes("scheduled") is True

    def test_play_alone_does_not_un_settle(self):
        from app.utils.event_completion import play_resumes

        # Reserved for `espn_replay_unsettles`, which clears `completed_at` in
        # the same write so the row never holds both facts at once.
        assert play_resumes("closed") is False
        assert play_resumes("completed") is False

    def test_the_two_doors_are_disjoint_on_the_settled_states(self):
        from app.utils.event_completion import (
            RESUMABLE_STATUSES,
            SETTLED_STATUSES,
            SETTLEABLE_STATUSES,
        )

        # A state cannot be both somewhere a terminal verdict lands and
        # somewhere play resumes from... except `suspended`, which is precisely
        # both, and that is the property that makes it non-terminal rather than
        # a second graveyard.
        assert SETTLEABLE_STATUSES & RESUMABLE_STATUSES == frozenset({"suspended"})
        assert not (SETTLEABLE_STATUSES & SETTLED_STATUSES)
        assert not (RESUMABLE_STATUSES & SETTLED_STATUSES)


class TestAPriceIsNotAStateSignal:
    def test_the_three_venues_are_named(self):
        from app.utils.event_completion import VENUE_PRICE_SOURCES

        assert VENUE_PRICE_SOURCES == frozenset({"betting", "kalshi", "polymarket"})

    def test_a_venue_source_cannot_satisfy_the_play_evidence_query(self):
        from app.utils.event_completion import (
            LAST_POST_COMMENCE_SNAPSHOT_SQL,
            VENUE_PRICE_SOURCES,
        )

        # The SQL is the only place this rule is enforced for the nets, so it
        # is asserted against the constant rather than against a local literal
        # that could drift away from the set the code actually uses.
        for venue in VENUE_PRICE_SOURCES:
            assert f"'{venue}'" in LAST_POST_COMMENCE_SNAPSHOT_SQL
        assert "NOT IN" in LAST_POST_COMMENCE_SNAPSHOT_SQL

    def test_a_null_source_still_counts_as_play(self):
        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        # A DENYLIST, not an allowlist, deliberately: StatPal writes
        # `source='statpal'` and is not in WIN_PROB_SOURCES at all, so an
        # allowlist would silently drop a real play source. Rows predating the
        # column carry NULL and must not be dropped either.
        assert "w.source IS NULL" in LAST_POST_COMMENCE_SNAPSHOT_SQL

    def test_every_market_source_is_named_a_venue(self):
        from app.config.win_prob_sources import WIN_PROB_SOURCES
        from app.utils.event_completion import VENUE_PRICE_SOURCES

        # The completeness risk runs the other way from the denylist: a NEW
        # venue that nobody classifies would silently become evidence of play.
        # Pinned against the registry's own `source_type`, so adding a market
        # source without naming it here fails here rather than in production.
        market_sources = {
            key for key, meta in WIN_PROB_SOURCES.items()
            if getattr(meta, "source_type", None) == "market"
            or (isinstance(meta, dict) and meta.get("source_type") == "market")
        }
        assert market_sources, "the registry exposes no market sources to pin against"
        assert market_sources <= VENUE_PRICE_SOURCES, (
            f"unclassified venue source(s): {market_sources - VENUE_PRICE_SOURCES}"
        )


class TestAVenueMayNotUnSettleARow:
    def test_a_settled_row_refuses_the_venues_live_write(self):
        from app.utils.event_completion import venue_live_write_is_a_resurrection

        assert venue_live_write_is_a_resurrection("closed", None) is True
        assert venue_live_write_is_a_resurrection("completed", None) is True

    def test_a_lingering_completion_alone_refuses_it(self):
        from app.utils.event_completion import venue_live_write_is_a_resurrection

        # The measured production shape: `status='live'` AND a `completed_at`,
        # served together from /api/events/{id} on five US Open rows.
        assert venue_live_write_is_a_resurrection("live", NOW) is True

    def test_a_suspended_row_is_not_refused(self):
        from app.utils.event_completion import (
            EVENT_SUSPENDED,
            venue_live_write_is_a_resurrection,
        )

        # THE live/048 clause, and the reason suspending is not a quieter way of
        # stranding a match. A suspended row is not settled and carries no
        # completion, so the scores feed — rung 3 — may promote it straight back
        # to live. Without this, the six US Open rows would have gone from
        # permanently LIVE to permanently SUSPENDED, which is a different bug
        # with the same shape.
        assert venue_live_write_is_a_resurrection(EVENT_SUSPENDED, None) is False

    def test_an_ordinary_unsettled_row_is_not_refused(self):
        from app.utils.event_completion import venue_live_write_is_a_resurrection

        assert venue_live_write_is_a_resurrection("scheduled", None) is False
        assert venue_live_write_is_a_resurrection("live", None) is False


# ---------------------------------------------------------------------------
# End to end, on the named row.
# ---------------------------------------------------------------------------


class _Ev:
    def __init__(self, id, sport_key, commence_time, status="live",
                 home_score=None, away_score=None, win_probability_sources=None,
                 home="Jesper de Jong", away="Francesco Passaro"):
        self.id = id
        self.status = status
        self.commence_time = commence_time
        self.completed_at = None
        self.home_score = home_score
        self.away_score = away_score
        self.win_probability_sources = win_probability_sources or {}
        self.home_team_name = home
        self.away_team_name = away
        self.sport = SimpleNamespace(key=sport_key)


class _NetSession:
    """Dispatches on statement shape and select order, which is deterministic."""

    def __init__(self, live, snapshots, suspended=None):
        self._selects = [[], live, suspended or [], [], []]
        self._snapshots = snapshots
        self.raw_updates = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "MAX(x.captured_at)" in sql:
            return SimpleNamespace(all=lambda: [
                SimpleNamespace(event_id=i, last_snap=t)
                for i, t in self._snapshots.items()
                if i in (params or {}).get("event_ids", [])
            ])
        if sql.strip().upper().startswith("UPDATE"):
            self.raw_updates.append(sql)
            return None
        rows = self._selects.pop(0)
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: rows)
        )

    async def commit(self):
        pass


async def _run_net(live, snapshots, now=NOW, suspended=None):
    session = _NetSession(live, snapshots, suspended)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.espn_sync as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch("app.tasks.base.get_task_session", _fake_session), \
            patch.object(mod, "datetime", _FrozenNow):
        stats = await mod._transition_event_statuses_impl()
    return session, stats


def _de_jong(**kw):
    """The CERT-752 specimen: 1-2 in sets, 15h in, only ever priced."""
    kw.setdefault("home_score", 1)
    kw.setdefault("away_score", 2)
    kw.setdefault("win_probability_sources", {"kalshi": {"value": 0.31}})
    return _Ev(15295047, "tennis_atp_us_open", DE_JONG_START, **kw)


class TestTheSuspendedMatchIsNotSettled:
    """The four facts CERT-752's harness measured, inverted."""

    @pytest.mark.asyncio
    async def test_it_does_not_become_closed(self):
        ev = _de_jong()
        _, stats = await _run_net([ev], {})
        assert ev.status == "suspended"
        assert stats["live_to_suspended"] == 1

    @pytest.mark.asyncio
    async def test_its_partial_score_is_not_graded(self):
        # `pm_resolved=1` was the finding. 1-2 down in sets is not a loss; it is
        # a match in progress, and resolving the blend to 0.0 publishes a
        # settled wrong answer that calibration then grades against (gotcha #21).
        ev = _de_jong()
        session, stats = await _run_net([ev], {})
        assert "pm_resolved" not in stats
        assert session.raw_updates == []
        assert ev.win_probability_sources == {"kalshi": {"value": 0.31}}
        assert "final_result" not in ev.win_probability_sources

    @pytest.mark.asyncio
    async def test_it_is_stamped_with_no_completion_time(self):
        # THE SNAPSHOT HERE IS LOAD-BEARING, and its absence made the first cut
        # of this test vacuous — it passed against pre-fix source too. With no
        # snapshot at all, `derive_completed_at` returns None either way, so the
        # assertion could not see the defect it was written for.
        #
        # A STALE one (3h old, well outside the 30-minute window) is the shape
        # that discriminates: the old net closed on it AND stamped it as the
        # game-end time, which is a fabricated completion for a match still to
        # be played. The new net writes nothing.
        stale = NOW - timedelta(hours=3)
        ev = _de_jong()
        await _run_net([ev], {ev.id: stale})
        assert ev.status == "suspended"
        assert ev.completed_at is None, (
            "a game-end time for a game nothing said had ended"
        )

    @pytest.mark.asyncio
    async def test_a_kalshi_tick_neither_holds_it_live_nor_ends_it(self):
        # The whole loop in one case. The venue is still quoting the suspended
        # match — 1,037 post-commence snapshots, every one `source='kalshi'` —
        # and the evidence query refuses to see it, so the row does not stay
        # live. Having refused it, the net must also not treat its own blindness
        # as proof the match ended. Both halves, or the bug changes sign.
        ev = _de_jong()
        _, stats = await _run_net([ev], {})  # venue rows never reach `snapshots`
        assert ev.status == "suspended"
        assert stats["held_still_running"] == 0
        assert stats["live_to_suspended"] == 1


class TestTheMatchCanComeBack:
    @pytest.mark.asyncio
    async def test_the_scores_feed_may_promote_a_suspended_row(self):
        from app.utils.event_completion import venue_live_write_is_a_resurrection

        ev = _de_jong(status="suspended")
        assert venue_live_write_is_a_resurrection(ev.status, ev.completed_at) is False

    @pytest.mark.asyncio
    async def test_a_play_report_puts_it_back_on_court(self):
        ev = _de_jong(status="suspended")
        _, stats = await _run_net(
            [], {ev.id: NOW - timedelta(minutes=4)}, suspended=[ev]
        )
        assert ev.status == "live"
        assert stats["suspended_to_live"] == 1

    @pytest.mark.asyncio
    async def test_a_venue_tick_does_not_put_it_back_on_court(self):
        # The resume arm shares the hold's evidence query on purpose: a Kalshi
        # tick cannot resume a match any more than it could hold one. Venue rows
        # never reach the query's result, which is what this models.
        ev = _de_jong(status="suspended")
        _, stats = await _run_net([], {}, suspended=[ev])
        assert ev.status == "suspended"
        assert stats["suspended_to_live"] == 0

    def test_the_authority_settles_it_without_a_hop_through_live(self):
        # ESPN reporting `post` on a suspended row must close it directly. The
        # settle site used to read `event.status == "live"`, which would have
        # left every suspended row unreachable by the authority.
        from app.utils.espn_helpers import authority_may_settle

        src = inspect.getsource(
            __import__("app.utils.espn_helpers", fromlist=["x"])
        )
        assert 'ee.status in ("post", "final") and authority_may_settle(' in src
        assert authority_may_settle("suspended") is True

    def test_the_authority_resumes_it_without_clearing_a_completion(self):
        from app.utils.espn_helpers import play_resumes

        src = inspect.getsource(
            __import__("app.utils.espn_helpers", fromlist=["x"])
        )
        assert 'ee.status == "in" and play_resumes(event.status)' in src
        assert play_resumes("suspended") is True


class TestNoNetWritesATerminalState:
    """Structural, over both nets: the rule, not one of its instances."""

    def test_the_transition_net_assigns_no_settled_status(self):
        from app.tasks.espn_sync import _transition_event_statuses_impl
        from app.utils.event_completion import SETTLED_STATUSES

        tree = ast.parse(inspect.getsource(_transition_event_statuses_impl))
        assigned = {
            n.value.value for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "status"
                for t in n.targets
            )
        }
        assert assigned, "the AST walk found no status assignment to check"
        assert not (assigned & SETTLED_STATUSES)

    @pytest.mark.asyncio
    async def test_the_odds_net_suspends_on_quiet_books(self):
        # The sibling net, on the same specimen. Its close signal is
        # `all_bookmakers_stale` — the bottom rung of the ladder reporting its
        # own ABSENCE, which is if anything weaker than a tick.
        ev = _OddsEv(15295047, "tennis_atp", HARNESS_NOW - timedelta(hours=15))
        _, outcome = await _run_odds_net(
            [ev],
            {15295047: {"recent": 0, "total": 40,
                        "last_snap": HARNESS_NOW - timedelta(hours=9)}},
            now=HARNESS_NOW,
        )
        assert outcome == {"closed": 0, "suspended": 1}
        assert ev.status == "suspended"
        assert ev.completed_at is None

    @pytest.mark.asyncio
    async def test_the_odds_net_still_closes_on_a_real_end_time(self):
        # THE CONTROL, and it is the one that makes the rule above meaningful
        # rather than "suspend everything". StatPal WATCHES the match, so its
        # end time is a positive statement on rung 3, not an inference from
        # silence. Green in both arms.
        ended = HARNESS_NOW - timedelta(minutes=10)
        ev = _OddsEv(2, "tennis_atp", HARNESS_NOW - timedelta(hours=2),
                     statpal_end_time=ended)
        # Asserted on the ROW only. The function's RETURN SHAPE changed in this
        # repair (`int` -> `{"closed", "suspended"}`), so checking it here would
        # make the control red in the pre-fix arm and prove nothing. What must
        # hold in BOTH arms is the row: StatPal closes it, with its real end
        # time.
        await _run_odds_net(
            [ev], {2: {"recent": 0, "total": 40, "last_snap": ended}},
            now=HARNESS_NOW,
        )
        assert ev.status == "closed"
        assert ev.completed_at == ended


class TestTheHealthyDirectionIsUntouched:
    """Controls. Green against BOTH pre-fix and post-fix source.

    Each reads a fact that neither the ladder nor the denylist can move — a
    play source's own timestamp, the shared 30-minute window, the per-sport
    duration table. A control routed through a symbol the fix introduces goes
    red in the pre-fix arm and then tells you nothing except that the fix is
    absent, which is the flaw live/042's first red run exposed in its own
    harness.
    """

    def test_a_play_source_still_holds_a_running_game(self):
        from app.utils.event_completion import game_may_still_be_running

        assert game_may_still_be_running(NOW - timedelta(minutes=2), NOW) is True

    def test_silence_past_the_window_still_releases_the_hold(self):
        from app.utils.event_completion import (
            STILL_ACTIVE_MINUTES,
            game_may_still_be_running,
        )

        assert game_may_still_be_running(
            NOW - timedelta(minutes=STILL_ACTIVE_MINUTES + 1), NOW
        ) is False

    def test_the_hold_window_is_still_thirty_minutes(self):
        from app.utils.event_completion import STILL_ACTIVE_MINUTES

        assert STILL_ACTIVE_MINUTES == 30

    def test_the_per_sport_duration_table_is_untouched(self):
        from app.tasks.config import SPORT_MAX_DURATIONS

        # The staleness net's TRIGGER is unchanged by this repair — only its
        # verdict moved. If a change ever "fixes" this class by widening the
        # window instead, this fails.
        assert SPORT_MAX_DURATIONS["tennis"] == 6.0
        assert SPORT_MAX_DURATIONS["baseball"] == 5.0

    @pytest.mark.asyncio
    async def test_a_game_inside_its_maximum_is_left_alone_entirely(self):
        # Asserted on the ROW, not on a stats key. `live_to_suspended` is a name
        # the fix introduces, so reading it here would make this control fail in
        # the pre-fix arm — and a control that fails without the fix cannot tell
        # you the fix left the healthy direction alone.
        ev = _de_jong()
        ev.commence_time = NOW - timedelta(hours=1)
        session, _ = await _run_net([ev], {})
        assert ev.status == "live"
        assert ev.completed_at is None
        assert session.raw_updates == []

    def test_a_derived_start_still_does_not_start_the_clock(self):
        from app.utils.event_completion import commence_time_is_a_reported_start

        # q076, the rule this one is the other half of. Unchanged.
        assert commence_time_is_a_reported_start("kalshi_ticker") is False
        assert commence_time_is_a_reported_start("odds_api") is True
