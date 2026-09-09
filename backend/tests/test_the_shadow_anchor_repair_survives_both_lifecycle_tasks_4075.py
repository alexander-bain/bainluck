"""CERT-2314's nonblocking follow-up `4075-LIFECYCLE-TASK-SHADOW-ANCHOR-GUARD`.

#4075 shipped correct and shipped UNEXECUTED. Every test it carried calls the
pure predicates directly — `event_has_never_been_observed`,
`wall_clock_bound_hours`, `statpal_anchor_is_shadow` — plus a SQL twin under
SQLite. None of them runs either lifecycle task, and the two tasks are where the
repair is actually spent:

  * `espn_sync._transition_event_statuses_impl` — suspends a row that has
    outlived `wall_clock_bound_hours + 0.5`;
  * `odds_polling.detect_and_close_stale_events` — holds a row it considers
    inside its bound and never reaches its staleness checks at all.

A predicate that returns the right answer into a loop that does not ask it is
the defect #4075 IS: `dd753773` did not break `event_has_never_been_observed`,
it changed what the loops around it were entitled to conclude. So the gap here
is not theoretical symmetry — it is the same shape as the bug.

Both loops read the sport through `event.sport.key if event.sport else ""`, and
`statpal_anchor_is_shadow("")` is False. So ANY wiring fault that costs the loop
its `Sport` — a dropped `selectinload`, a row whose FK dangles — silently
restores the pre-#4075 reading and buys the 1.5 hours back, with every pure
predicate test still green. That is the hazard this file exists to make
executed, and `TestTheLoopsMustNotLoseTheSport` pins both halves of it: the
hazard is real (measured, not asserted) and today it is unreachable.

Coverage, not conduct — nothing in `app/` changes. The specimen is the one
`odds_polling` names in its own comment: a Eredivisie fixture 3.2h past
kick-off, no score, period, anchor-that-means-anything or play snapshot ever.

3.2h is chosen because it is the only window that separates the two readings in
BOTH tasks at once:

| reading | bound | espn suspends at | odds holds until |
|---|---|---|---|
| repaired (shadow anchor ignored) | 2.5h | >3.0h → **fires** | 2.5h → **released** |
| pre-#4075 (anchor counts) | 4.0h | >4.5h → holds | 4.0h → held |
"""

import contextlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.tasks.config import SPORT_MAX_DURATIONS

# Imported as a MODULE, not by name: `TestTheEspnNetSpendsTheRepair` patches
# `statpal_anchor_is_shadow` on it to drive the pre-#4075 reading, and mixing
# `import` with `import from` on one module is both a CodeQL notice and the
# thing that makes a patch target ambiguous to a reader.
import app.utils.event_completion as event_completion
from app.utils.sport_keys import STATPAL_SHADOW_ANCHOR_SPORT_PREFIXES

UTC = timezone.utc
NOW = datetime(2026, 9, 9, 18, 0, tzinfo=UTC)

#: The specimen's age. See the module docstring's table for why this number.
SPECIMEN_HOURS = 3.2
LATE = NOW - timedelta(hours=SPECIMEN_HOURS)

#: A real Eredivisie key, so the `soccer` prefix match is the production one.
SOCCER = "soccer_netherlands_eredivisie"


# ---------------------------------------------------------------------------
# 0. The premise. Every assertion below is about a 1.5h gap between two
#    constants; if the constants move, the specimen stops separating the two
#    readings and this whole file passes while proving nothing.
# ---------------------------------------------------------------------------


class TestTheSpecimenStillSeparatesTheTwoReadings:
    def test_soccer_is_still_a_shadow_anchor_sport(self):
        assert "soccer" in STATPAL_SHADOW_ANCHOR_SPORT_PREFIXES

    def test_soccer_still_has_no_maximum_of_its_own(self):
        """It takes `default`, which is the 4.0 the old reading bought."""
        assert not [k for k in SPORT_MAX_DURATIONS if k.startswith("soccer")]
        assert SPORT_MAX_DURATIONS["default"] == 4.0

    def test_the_unobserved_bound_is_still_the_narrower_one(self):
        assert event_completion.UNOBSERVED_MAX_HOURS["soccer"] == 2.5

    def test_the_specimen_sits_between_the_two_readings_in_both_tasks(self):
        """The arithmetic the table in the docstring states, asserted.

        Without this, a later edit to `SPECIMEN_HOURS` could park the specimen
        where both readings agree and every test below would pass vacuously.
        """
        repaired, old = 2.5, 4.0
        # espn suspends at `bound + 0.5`; odds releases above `bound`.
        assert repaired + 0.5 < SPECIMEN_HOURS <= old
        assert repaired < SPECIMEN_HOURS <= old


# ---------------------------------------------------------------------------
# 1. Harness. Self-contained, as every other test file in this repo is — no
#    test module imports another. Modelled on `test_event_completion.py`'s two
#    nets and trimmed to what this specimen needs.
# ---------------------------------------------------------------------------


class _Ev:
    """Mutable stand-in for an Event row. Both nets assign to it directly."""

    def __init__(
        self,
        id,
        sport_key,
        commence_time,
        home_score=None,
        away_score=None,
        period=None,
        espn_id=None,
        statpal_fixture_id=None,
        sport_missing=False,
    ):
        self.id = id
        self.status = "live"
        self.commence_time = commence_time
        self.completed_at = None
        self.statpal_end_time = None
        self.home_score = home_score
        self.away_score = away_score
        self.period = period
        self.espn_id = espn_id
        self.statpal_fixture_id = statpal_fixture_id
        self.win_probability_sources = {}
        self.home_team_name = "Ajax"
        self.away_team_name = "PSV"
        # `sport_missing` models the one wiring fault that matters: the loop
        # holding a row whose `Sport` never loaded.
        self.sport = None if sport_missing else type("S", (), {"key": sport_key})()


class _EspnSession:
    """The five selects `_transition_event_statuses_impl` issues, in order."""

    def __init__(self, live):
        self._selects = [[], live, [], [], []]

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "MAX(x.captured_at)" in sql:
            # No play source has ever captured the specimen post-commence.
            return type("R", (), {"all": lambda _s: []})()
        if sql.startswith("UPDATE"):
            return None
        rows = self._selects.pop(0)
        return type(
            "R", (), {"scalars": lambda _s: type("S", (), {"all": lambda _x: rows})()}
        )()

    async def commit(self):
        pass


async def _run_espn(live, now=NOW):
    session = _EspnSession(live)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.espn_sync as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch("app.tasks.base.get_task_session", _fake_session), patch.object(
        mod, "datetime", _FrozenNow
    ):
        return await mod._transition_event_statuses_impl()


class _OddsSession:
    """Dispatches on statement shape, as the odds net's real session does.

    The specimen's books have gone quiet: zero snapshots inside the stale
    window, the last capture hours old. So once the bound RELEASES the row,
    nothing else holds it — which is what makes the bound the only variable.
    """

    def __init__(self, live):
        self._live = live
        self.updates = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "MAX(x.captured_at)" in sql:
            return type("R", (), {"first": lambda _s: None})()
        if sql.startswith("UPDATE"):
            compiled = stmt.compile()
            values = {
                k: v
                for k, v in compiled.params.items()
                if k in ("status", "completed_at", "home_score", "away_score")
            }
            ev_id = compiled.params.get("id_1")
            self.updates.append((ev_id, values))
            for ev in self._live:
                if ev.id == ev_id:
                    for k, v in values.items():
                        setattr(ev, k, v)
            return None
        if "count(" in sql.lower() and "odds_snapshots" in sql:
            # `recent` = 0 (books quiet), `total` = 43 (it WAS priced) — the
            # specimen odds_polling's own comment describes.
            n = 0 if "valid_until" in sql else 43
            return type("R", (), {"scalar": lambda _s: n})()
        return type(
            "R",
            (),
            {"scalars": lambda _s: type("S", (), {"all": lambda _x: self._live})()},
        )()

    async def commit(self):
        pass


async def _run_odds(live, now=NOW):
    import app.tasks.odds_polling as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    session = _OddsSession(live)
    with patch.object(mod, "datetime", _FrozenNow):
        outcome = await mod.detect_and_close_stale_events(session)
    return session, outcome


def _shadow_soccer(**kw):
    """The specimen: silent on every play column, one soccer StatPal id."""
    kw.setdefault("statpal_fixture_id", "SP-EREDIVISIE-99213")
    return _Ev(4075, SOCCER, LATE, **kw)


# ---------------------------------------------------------------------------
# 2. §1 — espn_sync, executed.
# ---------------------------------------------------------------------------


class TestTheEspnNetSpendsTheRepair:
    @pytest.mark.asyncio
    async def test_the_shadow_anchored_soccer_row_is_suspended_at_3_2h(self):
        row = _shadow_soccer()
        stats = await _run_espn([row])

        assert row.status == event_completion.EVENT_SUSPENDED
        # Counted as reached BY THE UNOBSERVED RULE specifically, not merely
        # suspended — the task keeps that tally separate on purpose.
        assert stats["suspended_unobserved"] == 1

    @pytest.mark.asyncio
    async def test_the_pre_4075_reading_would_have_left_it_live(self):
        """The regression, driven through the loop rather than described.

        Patching `statpal_anchor_is_shadow` to its pre-#4075 answer is exactly
        what `dd753773` shipped. If the loop no longer consults that decision,
        this test goes green while the one above also goes green — which is why
        both are needed.
        """
        row = _shadow_soccer()
        with patch.object(
            event_completion, "statpal_anchor_is_shadow", lambda _k: False
        ):
            stats = await _run_espn([row])

        assert row.status == "live"
        assert stats["suspended_unobserved"] == 0

    @pytest.mark.asyncio
    async def test_a_soccer_row_something_really_reported_on_keeps_4_0h(self):
        """The narrowing reaches SILENT rows only. A score is a source
        speaking, and it restores the full sport maximum.
        """
        row = _shadow_soccer(home_score=1, away_score=0)
        stats = await _run_espn([row])

        assert row.status == "live"
        assert stats["suspended_unobserved"] == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sport_key", ["americanfootball_nfl", "basketball_nba", "tennis_atp_us_open"]
    )
    async def test_a_lit_sports_anchor_still_protects_its_row(self, sport_key):
        """#4075's second acceptance clause, through the task: every other
        sport's anchor is still an observation and still buys the maximum.
        """
        row = _Ev(4075, sport_key, LATE, statpal_fixture_id="SP-1")
        stats = await _run_espn([row])

        assert row.status == "live"
        assert stats["suspended_unobserved"] == 0


# ---------------------------------------------------------------------------
# 3. §2 — odds_polling, executed. Same four cases, opposite mechanism: this
#    task HOLDS inside the bound, so the repair shows up as a row that stops
#    being held rather than a row that gets written.
# ---------------------------------------------------------------------------


class TestTheOddsNetSpendsTheRepair:
    @pytest.mark.asyncio
    async def test_the_shadow_anchored_soccer_row_is_no_longer_held_at_3_2h(self):
        row = _shadow_soccer()
        session, outcome = await _run_odds([row])

        # Released by the bound and then judged by the staleness checks, which
        # is the whole point: at 4.0h it never reached them.
        assert session.updates, "the row was held inside its bound and never judged"
        assert row.status != "live"
        assert sum(outcome.values()) == 1

    @pytest.mark.asyncio
    async def test_the_pre_4075_reading_would_have_held_it(self):
        row = _shadow_soccer()
        with patch.object(
            event_completion, "statpal_anchor_is_shadow", lambda _k: False
        ):
            session, outcome = await _run_odds([row])

        assert session.updates == []
        assert row.status == "live"
        assert sum(outcome.values()) == 0

    @pytest.mark.asyncio
    async def test_a_soccer_row_something_really_reported_on_is_still_held(self):
        row = _shadow_soccer(period="2H")
        session, outcome = await _run_odds([row])

        assert session.updates == []
        assert row.status == "live"
        assert sum(outcome.values()) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sport_key", ["americanfootball_nfl", "basketball_nba", "tennis_atp_us_open"]
    )
    async def test_a_lit_sports_anchor_still_holds_its_row(self, sport_key):
        row = _Ev(4075, sport_key, LATE, statpal_fixture_id="SP-1")
        session, outcome = await _run_odds([row])

        assert session.updates == []
        assert row.status == "live"
        assert sum(outcome.values()) == 0


# ---------------------------------------------------------------------------
# 4. §3 — the wiring the repair rests on.
# ---------------------------------------------------------------------------


class TestTheLoopsMustNotLoseTheSport:
    """Both loops read `event.sport.key if event.sport else ""`, and
    `statpal_anchor_is_shadow("")` is False. So a row that reaches either loop
    without its `Sport` silently gets the PRE-#4075 reading back.

    Two halves, and both are needed. The first MEASURES the hazard by driving
    it — an assertion about today's behaviour, not a wish about it, because the
    follow-up is coverage and changing the fallback is conduct. The second
    proves the state is unreachable, which is why the first is a note and not
    an incident.
    """

    @pytest.mark.asyncio
    async def test_a_row_that_lost_its_sport_silently_buys_the_old_bound(self):
        """MEASURED, not endorsed. If someone later makes the fallback safe,
        this test reds and should be updated to the new behaviour — that is the
        point of pinning it.
        """
        row = _shadow_soccer(sport_missing=True)
        stats = await _run_espn([row])

        assert row.status == "live"
        assert stats["suspended_unobserved"] == 0

    @pytest.mark.parametrize(
        "module_name, func_name",
        [
            ("app.tasks.espn_sync", "_transition_event_statuses_impl"),
            ("app.tasks.odds_polling", "detect_and_close_stale_events"),
        ],
    )
    def test_both_entry_points_eager_load_the_sport(self, module_name, func_name):
        """Sliced to the FUNCTION, not the file — a `selectinload(Event.sport)`
        anywhere else in a 2,000-line task module would satisfy a file-wide
        grep while the loop that needs it went without.
        """
        import importlib
        import inspect

        func = getattr(importlib.import_module(module_name), func_name)
        source = inspect.getsource(func)

        assert "selectinload(Event.sport)" in source, (
            f"{func_name} reads `event.sport.key` but no longer eager-loads "
            'Sport; the `else ""` fallback then restores the pre-#4075 '
            "reading on every soccer row, silently"
        )
