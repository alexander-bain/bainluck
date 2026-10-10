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
        sql = " ".join(str(stmt).split())
        self.calls.append((sql, params or {}))
        # The lock-free A4/A7 prepare reads (f44c689c88) select ids, none
        # prepared here; the retirement clock reads the transaction's time.
        clock = NOW if sql == "SELECT transaction_timestamp()" else None
        return SimpleNamespace(
            rowcount=0,
            scalars=lambda: SimpleNamespace(all=lambda: []),
            scalar_one=lambda: clock,
        )

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


def test_the_datagolf_bank_takes_its_basis_inside_the_window_by_the_lead(sweep) -> None:
    """After-check, 2026-10-03: a basis banked at the window's edge expired
    minutes after the sweep that banked it, so a live golf board's 24h column
    read "-" between sweeps. The lead must outlast the gap between two sweeps
    with a missed run to spare, or the column still goes dark between them."""
    from app.tasks import DATED_BASIS_BANK_LEAD_MINUTES, celery_app

    _, calls = sweep
    sql, params = next(
        (sql, params)
        for _, sql, params in _bank_statements(calls)
        if DATED_BASIS_ELIGIBILITY_METADATA_KEY in sql and "jsonb_object_agg" in sql
    )
    assert (
        "> now() - (:window_hours * interval '1 hour')"
        " + (:bank_lead_minutes * interval '1 minute')"
    ) in sql, sql
    assert params["bank_lead_minutes"] == DATED_BASIS_BANK_LEAD_MINUTES

    minutes = sorted(celery_app.conf.beat_schedule["update-max-movement"]["schedule"].minute)
    gap = max(b - a for a, b in zip(minutes, minutes[1:] + [minutes[0] + 60]))
    assert DATED_BASIS_BANK_LEAD_MINUTES >= 2 * gap, (gap, DATED_BASIS_BANK_LEAD_MINUTES)
    # Still a lead, not a second window: the basis stays at least half a day old.
    from app.tasks import DATED_BASIS_MIN_AGE_HOURS, MOVEMENT_WINDOW_HOURS

    assert DATED_BASIS_BANK_LEAD_MINUTES < (MOVEMENT_WINDOW_HOURS - DATED_BASIS_MIN_AGE_HOURS) * 60


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


# ---------------------------------------------------------------------------
# D5d — every routed SERVES site, by name. Putting the raw read back at any of
# them (`float(<row>.probability_change_24h)`) turns its case red. The three
# root-approved sites are also proven end to end in the real-PG file.
# ---------------------------------------------------------------------------

import inspect  # noqa: E402
import re  # noqa: E402

_RAW_PRINT = re.compile(r"float\(\s*\w+\.probability_change_24h\s*\)")

#: (module, function, reader calls expected, raw prints allowed and why)
D5_SITES = [
    ("app.routes.futures", "_movers_payload", 1, 0),
    ("app.routes.futures", "browse_futures", 1, 0),
    ("app.routes.futures", "faceted_futures_search", 1, 0),
    ("app.routes.futures", "get_playoff_grid", 1, 0),
    ("app.routes.futures", "get_multi_market_history", 1, 0),
    ("app.routes.futures", "get_progression", 2, 0),
    ("app.routes.futures", "get_cross_source_timeline", 1, 0),
    ("app.routes.futures", "_format_market_summary", 1, 0),
    ("app.routes.golf", "get_golf_tournament", 1, 0),
    ("app.utils.related_futures", "build_futures_entry", 1, 0),
    # One raw read stays: `compute_relevance_score`'s input SELECTS, it prints nothing.
    ("app.routes.events", "_build_related_futures", 2, 1),
    ("app.routes.events", "_build_search_top_outcomes", 2, 0),
    ("app.routes.events", "_mover_chips", 1, 0),
    ("app.routes.market_moves", "get_market_was_wrong", 1, 0),
    ("app.tasks.daily_digest", "build_digest_content", 1, 0),
    ("app.tasks.push_notifications", "_served_change", 1, 0),
    # Root's 07:42Z two-reader approval.
    ("app.routes.league_futures", "_serialize_outcomes", 1, 0),
    ("app.tasks.enrich_markets", "enrich_market_hooks", 1, 0),
    ("app.tasks.enrich_markets", "enrich_discover_llm_metadata", 1, 0),
    ("app.tasks.enrich_markets", "enrich_snippet_angles", 1, 0),
]


@pytest.mark.parametrize("module,function,calls,raw", D5_SITES, ids=[s[1] for s in D5_SITES])
def test_d5d_each_serves_site_reads_through_the_dated_reader(module, function, calls, raw) -> None:
    import importlib

    source = inspect.getsource(getattr(importlib.import_module(module), function))
    assert source.count("reader_change_24h(") == calls, f"{module}.{function}"
    assert len(_RAW_PRINT.findall(source)) == raw, (
        f"{module}.{function} prints the raw per-write column: {_RAW_PRINT.findall(source)}"
    )


def test_d5d_the_push_loop_uses_the_served_change() -> None:
    from app.tasks.push_notifications import _send_big_move_alerts

    source = inspect.getsource(_send_big_move_alerts)
    assert "_served_change(row)" in source
    # The alert prints the dated move, so a DataGolf row clears the bar on it.
    assert "change is None or abs(float(change)) < BIG_MOVE_THRESHOLD" in source


def test_d5d_the_discover_classifier_dates_through_a_carrier_not_the_dict() -> None:
    """`cand_rows` are dicts; `reader_change_24h(market, …)` on one would
    silently return the raw value. The real-PG case drives the dict path."""
    from app.tasks.enrich_markets import enrich_discover_llm_metadata

    source = inspect.getsource(enrich_discover_llm_metadata)
    assert 'source=market["source"]' in source
    assert 'market_metadata=market["market_metadata"]' in source
    assert "reader_change_24h(market," not in source


def test_d5d_the_golf_card_fallback_excludes_datagolf() -> None:
    from app.routes.golf import _aggregate_golfer_outcome

    assert "not is_datagolf" in inspect.getsource(_aggregate_golfer_outcome)


def test_d5_a_trending_chip_states_a_datagolf_legs_dated_move_or_nothing() -> None:
    """The movers query SELECTS on the stored column; the chip PRINTS. A DataGolf
    leg with a 90 s delta and no bank gets no chip; a dated one states the dated
    move; a Kalshi leg is unchanged."""
    from app.routes.events import _mover_chips

    def _row(oid, name, change, market):
        return SimpleNamespace(
            id=oid, name=name, market_id=oid, market=market,
            current_probability=0.15, probability_change_24h=change,
        )

    undated = SimpleNamespace(name="Dunhill - Winner", source="datagolf", market_metadata={})
    dated = SimpleNamespace(name="Dunhill - Top 5", **vars(_market(oid=2, now=None)))
    kalshi = SimpleNamespace(name="Masters winner", source="kalshi", market_metadata={})
    chips = _mover_chips([
        _row(1, "Matthew Jordan", Decimal("0.04"), undated),
        _row(2, "Rory McIlroy", Decimal("0.04"), dated),
        _row(3, "Scottie Scheffler", Decimal("0.05"), kalshi),
    ])
    text = " | ".join(str(c) for c in chips)
    assert "Matthew Jordan" not in text, chips
    assert "Rory McIlroy" in text and "13" in text, chips
    assert "Scottie Scheffler" in text and "5" in text, chips
