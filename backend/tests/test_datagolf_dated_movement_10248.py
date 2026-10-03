"""#10248 — golf (DataGolf) rows serve a dated 24h move. Unit half.

The real-Postgres half (`tests/integration/test_datagolf_dated_movement_10248_pg.py`)
runs the actual writers, sweep and route end to end. This file pins the pieces
it cannot isolate: the reader's marked-zero rule (D4), the raw-reader helper
(D5) and the readers routed through it, the writer's 0.0-is-a-price rule (D1),
and the sweep's statement order and exclusions (D3), which the PG gate only
proves through their effect.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.utils.futures_market_snapshot import (
    DATED_BASIS_ELIGIBILITY_METADATA_KEY,
    DATED_BASIS_METADATA_KEY,
    DATED_BASIS_PRICED_LEG,
    dated_basis_admits_zero,
    dated_movement_points,
    reader_change_24h,
)

NOW = datetime(2026, 10, 2, 23, 30, tzinfo=timezone.utc)


def _stamp(hours_ago: float, now: datetime = NOW) -> str:
    return (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _market(*, source="datagolf", marked=True, basis=0.02, hours_ago=19.0, oid=7, now=NOW):
    """`now=None` stamps off the real clock, for routes that read it themselves."""
    now = now or datetime.now(timezone.utc)
    metadata = {DATED_BASIS_METADATA_KEY: {str(oid): [basis, _stamp(hours_ago, now)]}}
    if marked:
        metadata[DATED_BASIS_ELIGIBILITY_METADATA_KEY] = DATED_BASIS_PRICED_LEG
    return SimpleNamespace(source=source, market_metadata=metadata)


# ---------------------------------------------------------------------------
# D4 — the reader
# ---------------------------------------------------------------------------


def test_a_marked_bank_dates_an_unchanged_poll() -> None:
    """The specimen: basis 0.02 at 19 h, now 0.15, last poll unchanged (0)."""
    got = dated_movement_points(_market(), 7, 0.15, Decimal("0"), now=NOW)
    assert got == pytest.approx(0.13)


def test_a_marked_bank_still_refuses_a_leg_with_no_previous_price() -> None:
    assert dated_movement_points(_market(), 7, 0.15, None, now=NOW) is None


def test_an_unmarked_bank_keeps_the_shared_zero_refusal() -> None:
    """Shared banks and every other source keep `if not stored_change`."""
    market = _market(source="polymarket", marked=False)
    assert dated_movement_points(market, 7, 0.15, Decimal("0"), now=NOW) is None
    assert dated_movement_points(market, 7, 0.15, 0.0, now=NOW) is None
    assert dated_movement_points(market, 7, 0.15, 0.05, now=NOW) == pytest.approx(0.13)


@pytest.mark.parametrize("hours_ago", [11.0, 25.0])
def test_a_marked_bank_keeps_every_other_refusal(hours_ago) -> None:
    market = _market(hours_ago=hours_ago)
    assert dated_movement_points(market, 7, 0.15, 0, now=NOW) is None
    assert dated_movement_points(_market(), 8, 0.15, 0, now=NOW) is None  # no cell
    assert dated_movement_points(_market(), 7, None, 0, now=NOW) is None  # no price


@pytest.mark.parametrize(
    "metadata",
    [None, "null", [], {DATED_BASIS_ELIGIBILITY_METADATA_KEY: "something_else"}],
)
def test_only_the_exact_mark_admits_zero(metadata) -> None:
    assert dated_basis_admits_zero(SimpleNamespace(market_metadata=metadata)) is False


def test_the_mark_is_read_without_a_lazy_load() -> None:
    class _Slots:
        __slots__ = ("market_metadata",)

    row = _Slots()
    row.market_metadata = {DATED_BASIS_ELIGIBILITY_METADATA_KEY: DATED_BASIS_PRICED_LEG}
    assert dated_basis_admits_zero(row) is False


# ---------------------------------------------------------------------------
# D5 — the raw-reader helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stored", [None, Decimal("0"), 0.0, Decimal("0.031"), -0.4])
def test_every_other_source_keeps_its_stored_value_untouched(stored) -> None:
    for source in ("kalshi", "polymarket", "odds_api", None):
        market = _market(source=source)
        assert reader_change_24h(market, 7, 0.15, stored, now=NOW) is stored


def test_a_datagolf_leg_gets_the_dated_answer_not_the_poll_delta() -> None:
    assert reader_change_24h(_market(), 7, 0.15, Decimal("0.0005"), now=NOW) == pytest.approx(0.13)
    assert reader_change_24h(_market(), 8, 0.15, Decimal("0.0005"), now=NOW) is None


# ---------------------------------------------------------------------------
# D1 — the writer
# ---------------------------------------------------------------------------


def test_the_writer_stores_the_shared_per_write_meaning() -> None:
    from app.tasks.datagolf import _per_write_change

    assert _per_write_change(None, 0.15) is None
    assert _per_write_change(Decimal("0.000000"), 0.15) == pytest.approx(0.15)
    assert _per_write_change(Decimal("1.000000"), 0.0) == pytest.approx(-1.0)
    assert _per_write_change(Decimal("0.150000"), 0.15) == 0.0


# ---------------------------------------------------------------------------
# D2 / D3 — the sweep, statement by statement
# ---------------------------------------------------------------------------


class _Recording:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        self.calls.append((" ".join(str(stmt).split()), params or {}))
        return SimpleNamespace(rowcount=0)

    async def commit(self):
        return None


@pytest.fixture
def sweep(monkeypatch):
    import app.tasks.base as base_mod
    import app.tasks.futures_movers_warm as warm_mod
    from app.tasks import update_max_movement

    session = _Recording()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    async def _warm(_session):
        return {"terminal": "ok", "completed": 0}

    monkeypatch.setattr(base_mod, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(warm_mod, "warm_futures_movers", _warm)
    result = update_max_movement.run()
    return result, session.calls


def _bank_statements(calls):
    return [
        (i, sql, params)
        for i, (sql, params) in enumerate(calls)
        if "UPDATE futures_markets" in sql and DATED_BASIS_METADATA_KEY in sql
    ]


def test_datagolf_model_is_scale_identical() -> None:
    from app.tasks import SCALE_IDENTICAL_SNAPSHOT_SOURCES

    assert "datagolf_model" in SCALE_IDENTICAL_SNAPSHOT_SOURCES
    assert {"kalshi", "polymarket"} <= set(SCALE_IDENTICAL_SNAPSHOT_SOURCES)


def test_the_datagolf_arms_run_first_and_the_shared_arms_exclude_them(sweep) -> None:
    result, calls = sweep
    statements = _bank_statements(calls)
    assert len(statements) == 4, [s[1][:80] for s in statements]
    dg = [s for s in statements if DATED_BASIS_ELIGIBILITY_METADATA_KEY in s[1]]
    shared = [s for s in statements if DATED_BASIS_ELIGIBILITY_METADATA_KEY not in s[1]]
    assert len(dg) == 2 and len(shared) == 2
    # Run first, so a shared arm without its exclusion would overwrite/delete
    # the DataGolf bank in the same pass — which is what makes the exclusions
    # load-bearing (and the PG strawmen able to fail).
    assert max(i for i, _, _ in dg) < min(i for i, _, _ in shared)
    for _, sql, _ in shared:
        assert "source IS DISTINCT FROM 'datagolf'" in sql, sql
    assert "dated_basis_banked_datagolf" in result
    assert "dated_basis_unbanked_datagolf" in result


def test_the_datagolf_bank_has_no_per_write_floor_and_keeps_a8s_bar(sweep) -> None:
    _, calls = sweep
    bank = next(
        (sql, params)
        for _, sql, params in _bank_statements(calls)
        if DATED_BASIS_ELIGIBILITY_METADATA_KEY in sql and "jsonb_object_agg" in sql
    )
    sql, params = bank
    assert "m.source = 'datagolf'" in sql
    assert ":floor" not in sql and "floor" not in params
    assert "fo.probability_change_24h IS NOT NULL" in sql
    assert "obs.sources = 1" in sql
    assert "obs.foreign_scale IS FALSE" in sql
    assert "(:basis_age_hours * interval '1 hour')" in sql
    assert "opening_probability" not in sql and "valid_until" not in sql
    assert params["dg_mark"] == DATED_BASIS_PRICED_LEG


def test_the_datagolf_unbank_removes_the_mark_with_the_bank(sweep) -> None:
    _, calls = sweep
    unbank = [
        sql
        for _, sql, _ in _bank_statements(calls)
        if DATED_BASIS_ELIGIBILITY_METADATA_KEY in sql and "jsonb_object_agg" not in sql
    ]
    assert len(unbank) == 1
    sql = unbank[0]
    assert f"- CAST('{DATED_BASIS_METADATA_KEY}' AS text)" in sql
    assert f"- CAST('{DATED_BASIS_ELIGIBILITY_METADATA_KEY}' AS text)" in sql
    assert "fm.source = 'datagolf'" in sql


# ---------------------------------------------------------------------------
# D5 — the readers routed through the helper
# ---------------------------------------------------------------------------


def _outcome(oid=7, change=Decimal("0.0005"), prob=0.15, market=None, name="Matthew Jordan"):
    return SimpleNamespace(
        id=oid,
        name=name,
        market_id=1,
        market=market,
        current_probability=prob,
        probability_change_24h=change,
        current_american_odds=None,
        rank=1,
        rank_change_24h=None,
        opening_probability=0.02,
        last_updated=None,
    )


def test_the_movers_strip_serves_a_datagolf_legs_dated_move() -> None:
    from app.routes.futures import _movers_payload

    dg = _outcome(market=SimpleNamespace(name="Dunhill - Winner", **vars(_market(now=None))))
    other = _outcome(
        oid=8,
        change=Decimal("0.05"),
        market=SimpleNamespace(name="K", **vars(_market(source="kalshi", oid=8, now=None))),
    )
    rows = {r["outcome_id"]: r for r in _movers_payload([dg, other], 24)["movers"]}
    assert rows[7]["probability_change_24h"] == pytest.approx(0.13)
    assert rows[8]["probability_change_24h"] == pytest.approx(0.05)


def test_the_movers_strip_refuses_an_undated_datagolf_leg() -> None:
    from app.routes.futures import _movers_payload

    market = SimpleNamespace(name="Dunhill - Winner", source="datagolf", market_metadata={})
    rows = _movers_payload([_outcome(change=Decimal("0.04"), market=market)], 24)["movers"]
    assert rows[0]["probability_change_24h"] is None


def test_the_golf_card_never_takes_the_undated_fallback_for_datagolf() -> None:
    from app.routes.golf import _aggregate_golfer_outcome

    golfers: dict = {}
    _aggregate_golfer_outcome(_outcome(change=Decimal("0.03")), "datagolf_model", golfers, {})
    entry = next(iter(golfers.values()))
    assert entry["undated_change"] is None
    assert entry["movement_24h"] is None

    golfers = {}
    _aggregate_golfer_outcome(_outcome(change=Decimal("0.03")), "kalshi", golfers, {})
    assert next(iter(golfers.values()))["undated_change"] == pytest.approx(0.03)


def test_the_related_futures_entry_routes_datagolf() -> None:
    from app.utils.related_futures import build_futures_entry

    common = dict(
        clean_label="x", display_category="x", merge_group=None, stage_display=None,
        stage_type=None, stage_order=None, relevance_score=0, relevance_reason="",
        next_update_iso=None, bookmaker_count=1,
    )
    market = SimpleNamespace(
        id=1, name="Dunhill - Winner", market_tier=1, category="championship",
        resolution_date=None, **vars(_market(now=None)),
    )
    entry = build_futures_entry(market=market, outcome=_outcome(), **common)
    assert entry["probability_change_24h"] == pytest.approx(0.13)

    market.market_metadata = {}
    entry = build_futures_entry(market=market, outcome=_outcome(), **common)
    assert entry["probability_change_24h"] is None
