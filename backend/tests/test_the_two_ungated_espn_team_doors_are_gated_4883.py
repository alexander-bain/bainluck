"""#4883 — the other two ESPN doors that write ``events.<side>_team_id``.

WHAT WAS UNGATED, AND WHY THE GUARD LOOKED PRESENT

``app/utils/team_binding_invariant.accept_team_binding`` is #1918's write-time
answer to #1798: an event side's ``team_id`` must dereference to a club whose
name matches that side's own ``*_team_name``. Its own test file
(``test_team_binding_invariant.py``) asserts the call sites exist — and it passes,
because it checks ``tasks/statpal_sync`` and ``tasks/espn_sync``.

ESPN writes that column from **three** places, not one. Measured 2026-09-20:

    tasks/espn_sync.py       _process_live_sport()      GATED since #1918
    utils/espn_helpers.py    sync_scheduled_events()    UNGATED
    utils/espn_helpers.py    backfill_missing_scores()  UNGATED

All three resolve the club through the same ``upsert_team`` and all three
OVERWRITE rather than only filling NULLs, so "the guard is wired in" was true of
the rail nobody was asking about. #4883's standing population — 136 of 21,468
bound sides over 90 days whose id dereferences to a different club (0.63%) — was
not draining, and two of its three producers could not see the guard.

THE CONTROL THIS FILE OWES

A tightened gate passes trivially on "always no", and a door test that only shows
a refusal cannot tell a working gate from a broken door. So every door here is
asserted in both directions on the same harness: a pair that must still bind, an
alias spelling that must still bind, and the production cross-club specimen that
must not. The refusal cases also assert the legacy predicate (``team and
event.<side>_team_id != team.id``) was TRUE — i.e. the code as it stood really did
write that id — so deleting the defect reddens the test as surely as deleting the
guard does.

THE COST, STATED RATHER THAN DISCOVERED LATER

``binding_defect`` compares alphanumerics only. A club whose row name and team row
disagree by punctuation or case still binds; one that disagrees by ABBREVIATION
("LA Clippers" against "Los Angeles Clippers") does not — the gate leaves the FK
NULL, which the name-keyed binders refill on the next pass. Door 1 has paid that
cost since #1918; ``test_an_abbreviation_alias_is_this_gates_measured_cost`` pins
it so the next reader meets it here rather than in production.
"""

import inspect
from datetime import datetime, timedelta, timezone

import pytest

# One import style for this module, not two: `py/import-and-import-from` is a
# CodeQL note, and a note left on master is the thing a later PR's diff gets
# blamed for when it shifts into range.
import app.services.espn_api as espn_api_mod
from app.utils import espn_helpers
from app.utils.espn_id_stamp import STAMPED as _STAMPED
from app.utils.team_binding_invariant import CROSS_CLUB

EPL = 771
NFL = 3
# Not `*_KEY`, and not by accident: gitleaks' generic-api-key rule fires on a
# high-entropy string assigned to a name ending in `_KEY`, and a long sport slug
# under such a name cost a CI cycle on #7221. These two happen to sit under the
# threshold; the NAME is what decides whether the scanner looks at all, so don't
# rename them back. (Nor quote the #7221 line here — the scanner reads comments
# too, which cost this branch a second cycle.)
NFL_SPORT = "americanfootball_nfl"
EPL_SPORT = "soccer_epl"


# ---------------------------------------------------------------------------
# Fakes — deliberately dumb. Anything the door asks for that is not spelled out
# here raises, so a fixture that has drifted from the code fails loudly instead
# of quietly exercising a shorter path than the one under test.
# ---------------------------------------------------------------------------


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


class _Team:
    """The three attributes the guard reads off a ``Team`` row."""

    def __init__(self, id, name, sport_id):
        self.id = id
        self.name = name
        self.sport_id = sport_id


class _Event:
    def __init__(
        self,
        id,
        sport,
        home_team_name,
        away_team_name,
        *,
        espn_id=None,
        home_team_id=None,
        away_team_id=None,
        commence_time=None,
        home_score=None,
        status="scheduled",
    ):
        self.id = id
        self.sport = sport
        self.sport_id = sport.id
        self.espn_id = espn_id
        self.home_team_name = home_team_name
        self.away_team_name = away_team_name
        # `get_event_name_variations` reads all four before it matches.
        self.home_team_normalized = None
        self.away_team_normalized = None
        self.home_team_alt_names = None
        self.away_team_alt_names = None
        self.home_team_id = home_team_id
        self.away_team_id = away_team_id
        self.commence_time = commence_time
        self.commence_time_source = None
        self.status = status
        self.home_score = home_score
        self.away_score = home_score
        self.period = None
        self.broadcast_info = None
        self.llm_importance = None


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Answers the door's SELECTs in order and refuses anything else."""

    def __init__(self, *result_sets):
        self._queue = list(result_sets)

    async def execute(self, stmt):
        if not self._queue:
            raise AssertionError(
                "the door issued more queries than the fixture answers — the "
                "fixture has drifted from the code, so this run proves nothing"
            )
        return _FakeResult(self._queue.pop(0))

    def add(self, obj):  # pragma: no cover - the doors under test add nothing
        raise AssertionError("no door in this file creates rows")


def _espn_team(name, espn_id="9001"):
    return espn_api_mod.ESPNTeam(
        espn_id=espn_id,
        name=name,
        abbreviation=None,
        display_name=name,
        short_name=None,
        nickname=None,
        primary_color=None,
        secondary_color=None,
        logo_url=None,
        logo_url_dark=None,
        record=None,
    )


def _espn_event(espn_id, when, home_name, away_name, *, home_score=None):
    return espn_api_mod.ESPNEvent(
        espn_id=espn_id,
        name=f"{away_name} at {home_name}",
        short_name=None,
        date=when,
        status="post" if home_score is not None else "pre",
        status_detail=None,
        period=None,
        clock=None,
        home_team=_espn_team(home_name, espn_id=f"{espn_id}h"),
        away_team=_espn_team(away_name, espn_id=f"{espn_id}a"),
        home_score=home_score,
        away_score=home_score,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )


def _resolver(monkeypatch, home_team, away_team):
    """Pin what ``upsert_team`` hands the door.

    The door's contract is "write this id only if the club it names agrees with
    the row's own name". Whether ``upsert_team`` SHOULD have returned this club is
    a different question with its own file (#6215) — pinning it here keeps this
    test about the door and lets the cross-club return be stated outright rather
    than manufactured through three fuzzy arms.
    """
    calls = []

    async def _fake_upsert_team(session, team_name, espn_team, sport_id, cache=None, stats=None):
        calls.append(team_name)
        return home_team if len(calls) % 2 == 1 else away_team

    monkeypatch.setattr(espn_helpers, "upsert_team", _fake_upsert_team)
    return calls


# ---------------------------------------------------------------------------
# Door 2 — sync_scheduled_events()
# ---------------------------------------------------------------------------


async def _run_scheduled(monkeypatch, event, home_team, away_team):
    monkeypatch.setattr(
        espn_helpers,
        "register_espn_team_identities",
        lambda *a, **k: _noop(),
    )
    _resolver(monkeypatch, home_team, away_team)

    ee = _espn_event(event.espn_id, event.commence_time, event.home_team_name, event.away_team_name)
    session = _FakeSession([event], [])
    stats: dict = {}
    await espn_helpers.sync_scheduled_events(session, event.sport.key, [ee], stats)
    return stats


async def _noop():
    return None


def _scheduled_event(home_name, away_name, **kw):
    return _Event(
        7700001,
        _Sport(EPL, EPL_SPORT),
        home_name,
        away_name,
        espn_id="401820001",
        commence_time=datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc),
        **kw,
    )


@pytest.mark.asyncio
class TestScheduledDoor:
    async def test_an_agreeing_pair_still_binds(self, monkeypatch):
        """The control. Without this the gate could be `return False` and pass."""
        event = _scheduled_event("Manchester City", "Arsenal")
        stats = await _run_scheduled(
            monkeypatch,
            event,
            _Team(382, "Manchester City", EPL),
            _Team(359, "Arsenal", EPL),
        )

        assert event.home_team_id == 382
        assert event.away_team_id == 359
        assert "team_binding_refused" not in stats

    async def test_a_punctuation_alias_still_binds(self, monkeypatch):
        """`Nott'ham Forest` / `Nottingham Forest` is not the shape this guards."""
        event = _scheduled_event("St.Louis Cardinals", "brighton & hove albion")
        stats = await _run_scheduled(
            monkeypatch,
            event,
            _Team(2692, "St. Louis Cardinals", EPL),
            _Team(331, "Brighton & Hove Albion", EPL),
        )

        assert event.home_team_id == 2692
        assert event.away_team_id == 331
        assert "team_binding_refused" not in stats

    async def test_the_production_cross_club_pair_is_refused(self, monkeypatch):
        """`team_identity_mapping` espn 388 'Coventry City' -> Manchester City (382),
        read out of production 2026-09-20 (#7441). Two clubs cannot be one club."""
        event = _scheduled_event("Coventry City", "Manchester United")
        home = _Team(382, "Manchester City", EPL)
        away = _Team(361, "Newcastle United", EPL)

        # Half 1, fails-first: the predicate this door used before #4883 is TRUE
        # for both sides, so the pre-fix code really did write these ids.
        assert home and event.home_team_id != home.id
        assert away and event.away_team_id != away.id

        stats = await _run_scheduled(monkeypatch, event, home, away)

        # Half 2: refused, and refusing means writing nothing at all.
        assert event.home_team_id is None
        assert event.away_team_id is None
        assert stats["team_binding_refused"] == 2
        assert stats[f"team_binding_refused_{CROSS_CLUB}"] == 2

    async def test_a_correct_existing_binding_is_not_overwritten(self, monkeypatch):
        """The reason this door matters more than its NULL-filling siblings: it
        overwrites. A wrong resolution must leave the right id in place."""
        event = _scheduled_event("Coventry City", "Arsenal", home_team_id=388)
        stats = await _run_scheduled(
            monkeypatch,
            event,
            _Team(382, "Manchester City", EPL),
            _Team(359, "Arsenal", EPL),
        )

        assert event.home_team_id == 388
        assert event.away_team_id == 359
        assert stats["team_binding_refused"] == 1

    async def test_an_abbreviation_alias_is_this_gates_measured_cost(self, monkeypatch):
        """STATED COST, not an oversight — see the module docstring.

        The gate compares alphanumerics, so an abbreviation the resolver accepts
        is refused here. The column is left NULL, never wrong, and the name-keyed
        binders refill it; door 1 has behaved this way since #1918. If this ever
        needs to change it changes in `binding_defect`, for all three doors at
        once — not by dropping a door.
        """
        event = _scheduled_event("LA Clippers", "Arsenal")
        stats = await _run_scheduled(
            monkeypatch,
            event,
            _Team(12, "Los Angeles Clippers", EPL),
            _Team(359, "Arsenal", EPL),
        )

        assert event.home_team_id is None
        assert event.away_team_id == 359
        assert stats["team_binding_refused"] == 1


# ---------------------------------------------------------------------------
# Door 3 — backfill_missing_scores()
# ---------------------------------------------------------------------------


class _FakeESPNService:
    """Stands in for `ESPNAPIService` for the length of one backfill pass."""

    events: list = []

    def __init__(self):
        pass

    async def get_scoreboard(self, sport_key, date=None):
        return list(self.events)

    async def close(self):
        return None


async def _run_backfill(monkeypatch, event, espn_event, home_team, away_team):
    _FakeESPNService.events = [espn_event]
    monkeypatch.setattr(espn_api_mod, "ESPNAPIService", _FakeESPNService)
    monkeypatch.setattr(
        espn_helpers,
        "stamp_espn_id_if_unheld",
        lambda *a, **k: _stamped(),
    )
    _resolver(monkeypatch, home_team, away_team)

    session = _FakeSession([event], [])
    stats: dict = {"errors": []}
    await espn_helpers.backfill_missing_scores(session, stats)

    # `backfill_missing_scores` wraps its per-sport body in `except Exception` and
    # files the text under `stats["errors"]`, so a fixture that blows up reads as
    # a clean pass. Assert the pass was clean before believing anything else.
    assert stats["errors"] == [], stats["errors"]
    assert stats.get("scores_backfilled") == 1, (
        "the door never reached the binding — this run proves nothing"
    )
    return stats


async def _stamped():
    return (_STAMPED, None)


def _completed_event(home_name, away_name, **kw):
    when = datetime.now(timezone.utc) - timedelta(days=1)
    return _Event(
        7700002,
        _Sport(NFL, NFL_SPORT),
        home_name,
        away_name,
        commence_time=when,
        status="completed",
        **kw,
    ), when


@pytest.mark.asyncio
class TestScoreBackfillDoor:
    async def test_an_agreeing_pair_still_binds(self, monkeypatch):
        event, when = _completed_event("Kansas City Chiefs", "Buffalo Bills")
        ee = _espn_event("401700002", when, "Kansas City Chiefs", "Buffalo Bills", home_score=24)

        stats = await _run_backfill(
            monkeypatch,
            event,
            ee,
            _Team(4001, "Kansas City Chiefs", NFL),
            _Team(4002, "Buffalo Bills", NFL),
        )

        assert event.home_score == 24
        assert event.home_team_id == 4001
        assert event.away_team_id == 4002
        assert "team_binding_refused" not in stats

    async def test_a_cross_club_resolution_is_refused_and_the_score_still_lands(
        self, monkeypatch
    ):
        """The FK is the only thing a refusal costs. The score ESPN reported is
        not in doubt — the club the resolver named for it is."""
        event, when = _completed_event("Kansas City Chiefs", "Buffalo Bills")
        ee = _espn_event("401700002", when, "Kansas City Chiefs", "Buffalo Bills", home_score=24)
        home = _Team(4003, "Los Angeles Chargers", NFL)

        assert home and event.home_team_id != home.id  # fails-first

        stats = await _run_backfill(
            monkeypatch, event, ee, home, _Team(4002, "Buffalo Bills", NFL)
        )

        assert event.home_score == 24
        assert event.home_team_id is None
        assert event.away_team_id == 4002
        assert stats["team_binding_refused"] == 1
        assert stats[f"team_binding_refused_{CROSS_CLUB}"] == 1


# ---------------------------------------------------------------------------
# Structural — the behavioural tests above stay green if someone reverts the
# wiring and leaves the guard importable, so assert the doors themselves.
# ---------------------------------------------------------------------------


class TestAllThreeEspnDoorsAreWired:
    @pytest.mark.parametrize(
        "fn_name",
        ["sync_scheduled_events", "backfill_missing_scores"],
    )
    def test_each_espn_helpers_door_gates_both_sides(self, fn_name):
        src = inspect.getsource(getattr(espn_helpers, fn_name))
        assert src.count("accept_team_binding(") == 2, (
            f"{fn_name} must gate BOTH sides — it writes the same column, from "
            "the same resolver, with the same overwrite shape as the live door "
            "that has been gated since #1918 (#4883)"
        )
        assert 'side="home"' in src and 'side="away"' in src

    def test_no_ungated_team_id_write_survives_in_this_module(self):
        """The census half, and the reason it counts more than the two doors.

        The parametrized test above is keyed on two function NAMES, so a third
        door added to this module tomorrow passes it by not being mentioned. This
        one asks the module the general question instead: every assignment to a
        ``*_team_id`` column here must sit behind a ``accept_team_binding(`` call
        it is syntactically attached to.
        """
        lines = inspect.getsource(espn_helpers).splitlines()
        writes = [
            (n, line.strip())
            for n, line in enumerate(lines)
            if "_team_id = " in line and not line.strip().startswith("#")
        ]
        assert len(writes) == 4, (
            "expected the four assignments this file gates (home/away × two "
            f"doors); found {len(writes)}: {[w for _, w in writes]}"
        )

        ungated = [
            w
            for n, w in writes
            # the gated shape spans 9 lines: the `if … and accept_team_binding(`
            # header, seven keyword arguments, and the closing `):`.
            if not any("accept_team_binding(" in lines[k] for k in range(max(0, n - 10), n))
        ]
        assert ungated == [], (
            f"ungated `*_team_id` write(s) in espn_helpers: {ungated} (#4883)"
        )
