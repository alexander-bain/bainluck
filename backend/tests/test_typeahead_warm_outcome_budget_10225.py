"""The head warmer runs the typeahead outcome arm under ITS OWN bound — #10225.

WHAT PRODUCTION SHOWED. Sentry BAINLUCK-14R, `typeahead outcome arm SHED for
'<q>' after 2000ms`: 21,231 events, **21,044 of them (99.1%) in
`app.tasks.warm_typeahead`** and 187 on the reader route, 122 in the 24 h to
2026-10-02, on the head terms the warmer exists to keep warm — `us open`,
`sabalenka`, `fed chair`, `masters winner`.

WHY A READER SAW IT. An outcome-arm shed is cacheable (LAT-P241/#3399), so a
shed rebuild by the warmer wrote the incomplete answer over the complete one, and
every reader of that term got it for the 65 s TTL. The warmer was paying its cold
read under the 2,000 ms bound sized for a person waiting on a keystroke.

THE FIX, AND THE TWO THINGS THAT MUST STAY TRUE. Under `_force_cache_rebuild`
(set by the warmer and nothing else) the arm gets
`_TYPEAHEAD_WARM_OUTCOME_ARM_TIMEOUT_MS`; otherwise the reader's bound,
unchanged. (1) A reader request never waits longer than it did. (2) The warm
bound is still clamped to the request deadline. No database, no timings: the
assertions read the `SET LOCAL statement_timeout` the resolver issues.
"""

from __future__ import annotations

import inspect
import re

import pytest
from sqlalchemy import select

from app.models.models import FuturesMarket, FuturesOutcome
from app.routes import events as events_mod
from app.routes.events import (
    _SEARCH_MIN_STAGE_TIMEOUT_MS,
    _TYPEAHEAD_DEADLINE_MS,
    _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS,
    _TYPEAHEAD_WARM_OUTCOME_ARM_TIMEOUT_MS,
    _force_cache_rebuild,
    _resolve_typeahead_outcome_arm,
    _typeahead_outcome_arm_budget_ms,
)

ARM = FuturesMarket.id.in_(
    select(FuturesOutcome.market_id).where(FuturesOutcome.name.ilike("%us open%"))
)
OPEN_NOW = (FuturesMarket.status == "open",)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Session:
    """Records each `SET LOCAL statement_timeout`; answers every other statement."""

    def __init__(self):
        self.set_local_ms: list[int] = []

    async def execute(self, stmt, *args, **kwargs):
        match = re.search(r"SET LOCAL statement_timeout = (\d+)", str(stmt))
        if match:
            self.set_local_ms.append(int(match.group(1)))
            return _Result([])
        return _Result([(1,)])

    async def rollback(self):
        pass


@pytest.fixture
def warmer_flag():
    token = _force_cache_rebuild.set(True)
    try:
        yield
    finally:
        _force_cache_rebuild.reset(token)


def _far() -> float:
    return events_mod.time.monotonic() + 3600


class TestTheReaderBoundIsUnchanged:
    @pytest.mark.asyncio
    async def test_a_reader_request_gets_the_reader_bound(self):
        assert _force_cache_rebuild.get() is False
        db = _Session()
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, _far())
        assert db.set_local_ms[0] == _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS == 2000

    def test_the_helper_answers_the_reader_bound_by_default(self):
        assert _typeahead_outcome_arm_budget_ms() == _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS


class TestTheWarmerGetsItsOwnBound:
    @pytest.mark.asyncio
    async def test_the_warmer_path_gets_the_warm_bound(self, warmer_flag):
        db = _Session()
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, _far())
        assert db.set_local_ms[0] == _TYPEAHEAD_WARM_OUTCOME_ARM_TIMEOUT_MS, (
            "the warmer ran the outcome arm under the reader's 2 s bound — the "
            "BAINLUCK-14R shed, cached over the complete answer for 65 s"
        )

    @pytest.mark.asyncio
    async def test_the_warm_bound_is_still_clamped_to_the_request_deadline(
        self, warmer_flag
    ):
        db = _Session()
        near = events_mod.time.monotonic() + 3.0
        await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, near)
        assert 2500 <= db.set_local_ms[0] <= 3000

    @pytest.mark.asyncio
    async def test_the_warmer_still_sheds_below_the_stage_floor(self, warmer_flag):
        db = _Session()
        spent = events_mod.time.monotonic() + (_SEARCH_MIN_STAGE_TIMEOUT_MS - 500) / 1000
        assert await _resolve_typeahead_outcome_arm(db, ARM, OPEN_NOW, spent) is None
        assert db.set_local_ms == []

    @pytest.mark.asyncio
    async def test_the_flag_reaches_the_route_through_warm_one(self, monkeypatch):
        """`_warm_one` wraps the route in `asyncio.wait_for`, which runs it in a
        new task with a COPY of the context — the flag must already be set when
        that copy is taken, or the route reads the reader bound."""
        from app.tasks import typeahead_warmer

        seen: dict = {}

        async def _fake_route(**kwargs):
            seen["budget"] = events_mod._typeahead_outcome_arm_budget_ms()
            return {}

        monkeypatch.setattr(events_mod, "typeahead_search", _fake_route)
        monkeypatch.setattr(typeahead_warmer, "_cache_ttl_seconds", lambda q: None)
        await typeahead_warmer._warm_one(object(), "us open")
        assert seen["budget"] == _TYPEAHEAD_WARM_OUTCOME_ARM_TIMEOUT_MS
        assert _force_cache_rebuild.get() is False


class TestTheConstants:
    def test_the_warm_bound_is_larger_than_the_reader_bound(self):
        assert _TYPEAHEAD_WARM_OUTCOME_ARM_TIMEOUT_MS > _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS

    def test_the_warm_bound_leaves_the_later_stages_their_floor_twice_over(self):
        """A futures-stage shed is `_ta_degraded`, which blocks the cache write —
        worse than the outcome-arm shed this buys back."""
        assert (
            _TYPEAHEAD_DEADLINE_MS - _TYPEAHEAD_WARM_OUTCOME_ARM_TIMEOUT_MS
            >= 2 * _SEARCH_MIN_STAGE_TIMEOUT_MS
        )

    def test_the_warm_bound_is_env_tunable(self):
        assert 'os.getenv("TYPEAHEAD_WARM_OUTCOME_ARM_TIMEOUT_MS"' in inspect.getsource(
            events_mod
        )


class TestTheShedLineNamesTheBoundThatApplied:
    def test_the_shed_log_reports_the_helper_not_the_reader_constant(self):
        src = inspect.getsource(events_mod.typeahead_search)
        start = src.index("typeahead outcome arm SHED for")
        block = src[start:start + 600]
        assert "_typeahead_outcome_arm_budget_ms()" in block
        assert "_TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS" not in block
