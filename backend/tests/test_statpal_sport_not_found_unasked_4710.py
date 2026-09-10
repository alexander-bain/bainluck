"""#4710 / authority/100 — the second way a sport goes unasked gets NAMED.

WHAT WAS BROKEN. #2907 gave `_sync_statpal_schedules` a `sports_unasked` list so
a pass that could not ask a mapped sport says WHICH and WHY, instead of leaving
the reader to subtract `sports_asked` from the key count and guess. It covered
one of the two arms:

    no_day_token     the sport IS rowed; `get_fixtures_result` declines to make
                     an HTTP request (StatPal serves that schedule one calendar
                     board at a time)                         -> appended
    sport_not_found  the key resolves to no `sports` row, so the loop
                     `continue`s ABOVE the fetch               -> appended NOTHING

The terminal was never wrong — the `sport_not_found` arm never reaches
`sports_asked += 1`, so an all-unasked pass already read `no_work`. The defect is
that the summary, which is the artifact an operator actually reads, named one
arm and left the other to be inferred. Two sports unasked for opposite reasons
want opposite responses (mint the missing row / accept a permanent property of
StatPal's product) and only one of them was legible. That is gotcha #53's shape
one level up from the venue: `sports_unasked: []` beside `sports_asked: 0` read
as "nothing was even attempted".

WHY THIS FILE INJECTS ITS OWN MAP. `golf_pga` was the only reachable
`sport_not_found` specimen in production and #4691 retires the key, so after that
lands there is no live instance. A test that sourced its sports from
`STATPAL_SPORT_MAPPING` would go green on the day #4691 merges while measuring
nothing — the guard would stop failing without the behaviour being right (a
guard that stops MEASURING rather than failing). So every case below patches the
map to a fixture of its own and never reads the production config.

THE ONE TERMINAL THAT MOVES, deliberately. A pass that asked somebody AND
dropped a `sport_not_found` sport used to read `complete` and now reads
`partial` — which is what the rule written above the terminal always said
("A MIXED pass is `partial`, not `complete`"); the missing append was why the
code disagreed with its own comment. No BEAT terminal moves: all four beats pass
a single explicit `sport_key`, as does the #4434 in-line failover, so
`sports_asked` is 0 or 1 there. `TestTheTerminalsThatMustNotMove` pins all four
paths so the claim is measured rather than asserted in prose.
"""
import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

import app.services.statpal_api as statpal_api

# `Event` carries Postgres JSONB/ARRAY columns sqlite cannot render as DDL — the
# repo's standing shim, same as `test_statpal_schedules_zero_yield_2907`.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


#: Our-key -> StatPal-sport, entirely invented. `ROWED` gets a `sports` row in
#: the rail below and `UNROWED` deliberately does not: that absence IS the
#: `sport_not_found` specimen, and building it here rather than borrowing it is
#: what keeps this file measuring after #4691.
ROWED = "americanfootball_nfl"
UNROWED = "fictional_sport_with_no_row_4710"
INJECTED_MAP = {ROWED: "nfl", UNROWED: "golf"}


def _inject_map(monkeypatch, mapping):
    """Replace the module's view of the sport map.

    `_sync_statpal_schedules` reads `STATPAL_SPORT_MAPPING` from its own module
    namespace both to build `sport_keys` and to pre-resolve the StatPal id
    spaces, so patching the one binding covers both.
    """
    monkeypatch.setattr(
        "app.tasks.statpal_sync.STATPAL_SPORT_MAPPING", dict(mapping)
    )


def _wire_rows(monkeypatch, *rowed_keys):
    """The smallest DB rail the pass will run against: a `Sport` row per key.

    Any key in the injected map WITHOUT a row here reaches `sport_not_found`.
    This file's subject is the summary and the terminal, not row writing.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.models import Base, Event, Sport, Team, TeamIdentityMapping

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__, Sport.__table__,
            Team.__table__, TeamIdentityMapping.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    for key in rowed_keys:
        session.add(Sport(key=key, name=key))
    session.commit()

    class _AsyncShim:
        def __init__(self, s):
            self._s = s

        async def execute(self, *a, **kw):
            return self._s.execute(*a, **kw)

        async def flush(self, *a, **kw):
            return self._s.flush(*a, **kw)

        async def commit(self):
            return self._s.commit()

        async def rollback(self):
            return self._s.rollback()

        def add(self, obj):
            return self._s.add(obj)

        def __getattr__(self, name):
            return getattr(self._s, name)

    class _Ctx:
        async def __aenter__(self):
            return _AsyncShim(session)

        async def __aexit__(self, exc_type, *_):
            if exc_type:
                session.rollback()
            return False

    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    return session


def _stub_venue_by_sport(monkeypatch, reason_by_statpal_sport):
    """A StatPal whose reason depends on WHICH StatPal sport is asked."""
    class _Service:
        async def get_fixtures_result(self, sport, *a, **k):
            return statpal_api.StatPalFixtureFetch(
                [], reason_by_statpal_sport[sport], sport, "season-schedule"
            )

        async def get_fixtures(self, *a, **k):
            return (await self.get_fixtures_result(*a, **k)).fixtures

        async def get_live_scores(self, sport):
            return []

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    async def _sleep(_s):
        return None

    monkeypatch.setattr("asyncio.sleep", _sleep)


async def _run(monkeypatch, mapping, rowed, reasons):
    from app.tasks.statpal_sync import _sync_statpal_schedules

    _inject_map(monkeypatch, mapping)
    _wire_rows(monkeypatch, *rowed)
    _stub_venue_by_sport(monkeypatch, reasons)
    return await _sync_statpal_schedules()


def _reason_for(summary, sport):
    for entry in summary["sports_unasked"]:
        if entry["sport"] == sport:
            return entry["reason"]
    return None


class TestASportNotFoundSportIsNamedNotMerelyUncounted:
    """Acceptance bullet 1: the arm appends, with its own reason."""

    @pytest.mark.asyncio
    async def test_the_unrowed_sport_appears_in_sports_unasked(self, monkeypatch):
        summary = await _run(
            monkeypatch, INJECTED_MAP, [ROWED], {"nfl": "ok", "golf": "ok"}
        )

        named = [e["sport"] for e in summary["sports_unasked"]]
        assert UNROWED in named, (
            "a mapped sport with no `sports` row went unasked and the summary "
            f"did not name it: {summary['sports_unasked']}"
        )

    @pytest.mark.asyncio
    async def test_its_reason_is_sport_not_found(self, monkeypatch):
        summary = await _run(
            monkeypatch, INJECTED_MAP, [ROWED], {"nfl": "ok", "golf": "ok"}
        )

        assert _reason_for(summary, UNROWED) == "sport_not_found"

    @pytest.mark.asyncio
    async def test_the_entry_carries_the_statpal_sport_like_the_other_arm(
        self, monkeypatch
    ):
        # Same shape as the `no_day_token` entries, so a reader parsing
        # `sports_unasked` does not have to branch on which arm produced a row.
        summary = await _run(
            monkeypatch, INJECTED_MAP, [ROWED], {"nfl": "ok", "golf": "ok"}
        )

        entry = next(
            e for e in summary["sports_unasked"] if e["sport"] == UNROWED
        )
        assert entry["statpal_sport"] == "golf"
        assert set(entry) == {"sport", "statpal_sport", "reason"}

    @pytest.mark.asyncio
    async def test_the_details_row_is_unchanged(self, monkeypatch):
        # The append is additive: `details` keeps the status it always had, so
        # anything reading the per-sport list still sees the same word.
        summary = await _run(
            monkeypatch, INJECTED_MAP, [ROWED], {"nfl": "ok", "golf": "ok"}
        )

        assert {"sport": UNROWED, "status": "sport_not_found"} in summary["sports"]


class TestTheTwoArmsAreDistinguishableByReason:
    """Acceptance bullet 2: named, and told apart — not merged into one word."""

    @pytest.mark.asyncio
    async def test_both_arms_are_named_in_one_pass(self, monkeypatch):
        # Three sports: one asked, one rowed-but-day-board, one unrowed.
        mapping = {
            ROWED: "nfl",
            "fictional_day_board_4710": "soccer",
            UNROWED: "golf",
        }
        summary = await _run(
            monkeypatch,
            mapping,
            [ROWED, "fictional_day_board_4710"],
            {"nfl": "ok", "soccer": "no_day_token", "golf": "ok"},
        )

        named = {e["sport"] for e in summary["sports_unasked"]}
        assert named == {"fictional_day_board_4710", UNROWED}

    @pytest.mark.asyncio
    async def test_the_reasons_differ(self, monkeypatch):
        mapping = {
            ROWED: "nfl",
            "fictional_day_board_4710": "soccer",
            UNROWED: "golf",
        }
        summary = await _run(
            monkeypatch,
            mapping,
            [ROWED, "fictional_day_board_4710"],
            {"nfl": "ok", "soccer": "no_day_token", "golf": "ok"},
        )

        day_board = _reason_for(summary, "fictional_day_board_4710")
        not_found = _reason_for(summary, UNROWED)
        assert day_board == "no_day_token"
        assert not_found == "sport_not_found"
        assert day_board != not_found, (
            "the two arms want opposite operator responses and must not collapse "
            "into one reason"
        )

    @pytest.mark.asyncio
    async def test_no_sport_is_unaccounted_for(self, monkeypatch):
        """The invariant the whole issue is about: no subtraction gap.

        Every mapped key is either asked or named as unasked. This is the
        assertion that would have caught the original defect regardless of which
        arm was missing, and it is why it is stated as arithmetic over the map
        rather than as a fact about one branch.
        """
        mapping = {
            ROWED: "nfl",
            "fictional_day_board_4710": "soccer",
            UNROWED: "golf",
        }
        summary = await _run(
            monkeypatch,
            mapping,
            [ROWED, "fictional_day_board_4710"],
            {"nfl": "ok", "soccer": "no_day_token", "golf": "ok"},
        )

        assert summary["sports_asked"] + len(summary["sports_unasked"]) == len(
            mapping
        )


class TestTheTerminalsThatMustNotMove:
    """Acceptance bullet 3, plus the one exception, measured not asserted."""

    @pytest.mark.asyncio
    async def test_an_all_unrowed_pass_is_still_no_work(self, monkeypatch):
        # The shape a single-sport BEAT hits if its row vanishes: nobody asked,
        # so `no_work` — the same word #2907 shipped, before and after #4710.
        summary = await _run(
            monkeypatch, {UNROWED: "golf"}, [], {"golf": "ok"}
        )

        assert summary["sports_asked"] == 0
        assert summary["terminal"] == "no_work"

    @pytest.mark.asyncio
    async def test_an_all_day_board_pass_is_still_no_work(self, monkeypatch):
        summary = await _run(
            monkeypatch,
            {"fictional_day_board_4710": "soccer"},
            ["fictional_day_board_4710"],
            {"soccer": "no_day_token"},
        )

        assert summary["terminal"] == "no_work"

    @pytest.mark.asyncio
    async def test_a_fully_asked_pass_is_still_complete(self, monkeypatch):
        # 0 rows written is the RIGHT answer for a season already complete from
        # ESPN/The Odds API, and it must stay green (#2907).
        summary = await _run(
            monkeypatch, {ROWED: "nfl"}, [ROWED], {"nfl": "ok"}
        )

        assert summary["sports_unasked"] == []
        assert summary["terminal"] == "complete"

    @pytest.mark.asyncio
    async def test_a_mixed_pass_with_an_unrowed_sport_is_partial(self, monkeypatch):
        """The ONE terminal #4710 moves, and only on the all-sports form.

        Pre-#4710 this read `complete`: the unrowed sport appended nothing, so
        the `fetch_failures or sports_unasked` arm never fired. The comment above
        the terminal already ruled that a mixed pass is `partial`, so this is the
        code catching up with its own stated rule, not a new policy.
        """
        summary = await _run(
            monkeypatch, INJECTED_MAP, [ROWED], {"nfl": "ok", "golf": "ok"}
        )

        assert summary["sports_asked"] == 1
        assert summary["terminal"] == "partial"

    @pytest.mark.asyncio
    async def test_no_beat_can_reach_the_moved_terminal(self, monkeypatch):
        """The claim "no beat terminal moves", measured on the beat kwargs.

        A terminal change is scoped by the ARGUMENTS its beats pass, not by the
        function's worst case: every scheduled entry hands over one explicit
        `sport_key`, so `sports_asked` is 0 or 1 and the mixed arm above is
        unreachable from the schedule. If a beat is ever added without a
        `sport_key`, this fails and the terminal claim gets re-read.
        """
        from app.tasks import celery_app

        entries = {
            name: spec
            for name, spec in celery_app.conf.beat_schedule.items()
            if spec.get("task") == "app.tasks.sync_statpal_schedules"
        }
        assert entries, "the schedules task lost its beats — re-read the claim"
        for name, spec in entries.items():
            assert spec.get("kwargs", {}).get("sport_key"), (
                f"beat {name} runs the all-sports form, which CAN reach the "
                "mixed `partial` terminal #4710 introduces"
            )


class TestTheGuardMeasuresAfter4691:
    """The specimen note in the issue, pinned so it cannot rot silently."""

    def test_this_file_does_not_source_its_sports_from_production_config(self):
        # #4691 retires `golf_pga`, the last live `sport_not_found` instance. A
        # guard that borrowed the production map would go green that day while
        # measuring nothing, so the fixture must be local and unrowed by
        # construction.
        from app.utils.sport_keys import STATPAL_SPORT_MAPPING

        assert UNROWED not in STATPAL_SPORT_MAPPING, (
            "this file's specimen leaked into the production map; pick another "
            "invented key or the guard stops measuring"
        )
