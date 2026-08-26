"""CAL-P096/P098 — ROW IDENTITY between the fused and the narrowed population CTEs.

THE CLAIM UNDER TEST. C-FOLD-EXPLAIN-1 §3's narrowing rewrite moves
``ranked_outcomes``' two window functions off the nine-way LEFT JOIN and onto the
narrow ``fo ⋈ virtual_market ⋈ clean_vms`` row, then joins the nine per-market
slices back afterwards. Its acceptance bar is not "the ECE is about the same" and
not "the aggregates match" — it is ROW IDENTITY: the same final rows, with the
same values, in every column.

WHY A REAL POSTGRES AND NOT A STRING ASSERTION. The sibling gate
``tests/test_calibration_fold_narrowing_p096.py`` proves the three structural
premises (the nine relations are at most one row per market; no deferred column
feeds a window; the emitted column list is unchanged). Those are arguments about
the SQL. This one is the argument about the ANSWER, and it can only be made by a
planner: ``rn`` is decided by a window, and a window's output is a fact about
executed rows.

WHAT CAL-P098 ADDED, AND WHY. `C-FOLD-REWRITE-1` returned BLOCK with G2 and four
fifths of G4 unmet, and the two findings share a root: **this file asserted that
OLD equals NEW, and never once asserted what either of them should be.** Global
equality is satisfied by two chains that are both wrong in the same way, and it
is satisfied vacuously by a seed that publishes nothing. So:

* **A per-fixture oracle** (:data:`EXPECTED`) now names, for every seeded market,
  the exact set of ``outcome_id`` values that must publish and why — and it is
  asserted against OLD and NEW *separately*, so "they agree" is no longer the
  only thing on record.
* **The incomplete field** G2 named as missing now exists (``_m(140)``): a
  four-member Kalshi weather field where one member carries a wide book, is
  therefore excluded per-outcome, and drops the **whole** field. It is the one
  specimen that proves the flags must exist on every candidate member rather
  than on the representative — which is exactly what §3's rejected shortcut
  would have broken.
* **Liquidity and placeholder PAIRS** now differ in one dimension only
  (``_m(120)``/``_m(160)`` on snapshot bid evidence; ``_m(110)``/``_m(150)`` on
  trade evidence at the same 0.50 price), so the discriminator is the difference
  and not a coincidence of the seed.
* **Five mutation controls** run through ``FOLD_GATE_MUTANT``. Each one makes
  this file exit **1** — a semantic assertion failure, not a collection error —
  and the unmutated run exits 0. The CI step records both.
* **The production harness's own statements** are executed here. The comparator
  in ``app/utils/fold_narrowing_gate.py`` is not a test-only reimplementation:
  it is the same ``EXCEPT ALL`` text the one-off-dyno runner sends to
  production, proved runnable on a seeded database before production is asked
  to run it.

THE ORACLE for the OLD side is ``tests/fixtures/cal_p096_fused_population_ctes.sql``
— the verbatim pre-split emission of ``_calibration_population_ctes()``, frozen at
``8bd08265``. It stays an oracle only while the untouched parts of the chain still
match it; ``TestEmittedRelationIsUnchanged`` in the sibling file is that staleness
alarm, and if it goes red this gate is comparing against something that is no
longer the thing it certified.

Gated on a throwaway Postgres, armed in CI by the ``search-recall`` job's service
container (``SEARCH_TEST_DATABASE_URL``). There is no local Postgres in the agent
sandbox (``initdb`` dies on ``shmget`` — re-confirmed 2026-08-25), so CI is the
only environment that runs it, and that is precisely why every assertion here
prints the actual table on failure: nobody gets an interactive second look.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL") or os.environ.get(
    "SEARCH_TEST_DATABASE_URL"
)

#: The G4 seam. Unset = the real gate. Set = one deliberate defect is injected
#: into the NEW chain (or into the comparator's NEW relation) and this file is
#: REQUIRED to go red. See ``MUTANTS`` in ``app/utils/fold_narrowing_gate.py``.
MUTANT = os.environ.get("FOLD_GATE_MUTANT", "").strip()

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL (CI's service container) or "
            "CALIBRATION_TEST_DATABASE_URL to run the CAL-P096 row-identity gate"
        ),
    ),
]

FUSED_SQL = (
    Path(__file__).parents[1] / "fixtures" / "cal_p096_fused_population_ctes.sql"
)

# int32, and far from every other gate's ids in this job — `events.id` is
# INTEGER, not BIGINT, and an id over 2147483647 fails every INSERT with an
# asyncpg DataError rather than a test assertion (INT-121's hotfix class).
EVENT_ID = 960001
SPORT_ID = 96001
BASE = 9600000

#: The displacement the aggregate-collision control uses for its swapped row.
#: Far enough from BASE that the synthetic id cannot collide with a real one.
SWAP_OFFSET = 7_000_000


def _m(offset: int) -> int:
    return BASE + offset


#: market -> (source, category, market_type, mutually_exclusive, shape, event_id,
#:            group_id, [(outcome_offset, name, price, is_winner[, overrides]), ...])
#:
#: ``shape`` is the persisted exclusivity evidence read by
#: ``mex_field_candidates``; only the field markets need a real one.
#:
#: Per-outcome ``overrides`` (CAL-P098) is a dict accepting ``yes_bid`` /
#: ``yes_ask`` (written to ``futures_outcomes``, which is what the weather
#: wide-spread rule reads) and ``snapshot`` — one of ``"traded"`` (default; a
#: snapshot with both a bid and a last price), ``"bid_only"`` (bid evidence, no
#: trade) or ``"none"``. The distinction is load-bearing and was not expressible
#: before: ``is_liquid`` reads SNAPSHOT evidence, while
#: ``is_weather_wide_spread`` reads the OUTCOME's book and the absence of a
#: traded snapshot. A member can therefore be liquid, in the field roster, and
#: still excluded — which is the only way to build an incomplete field.
_PROVED_SHAPE = '{"exhaustive": "true", "expected_winners": "1", "outcome_relation": "competitors"}'

SEED: tuple[tuple[int, dict], ...] = (
    # --- mex_field_candidates + mex_field_divisor: a COMPLETE 4-member field.
    #     Prices sum to 1.60 > MEX_NORMALIZE_THRESHOLD (1.15), one winner.
    (
        _m(10),
        dict(
            source="kalshi",
            category="politics",
            market_type="field",
            mex=True,
            shape=_PROVED_SHAPE,
            outcomes=[
                (1, "alpha", 0.70, True),
                (2, "bravo", 0.40, False),
                (3, "charlie", 0.30, False),
                (4, "delta", 0.20, False),
            ],
        ),
    ),
    # --- golf_placeholder_markets: mex golf, two members in the >=0.80 band.
    (
        _m(20),
        dict(
            source="kalshi",
            category="golf",
            market_type="field",
            mex=True,
            outcomes=[
                (1, "golfer-a", 0.90, True),
                (2, "golfer-b", 0.85, False),
                (3, "golfer-c", 0.10, False),
            ],
        ),
    ),
    # --- malformed_binaries AND no_winner_markets: 2-outcome mex, zero winners.
    (
        _m(30),
        dict(
            source="kalshi",
            category="politics",
            market_type="binary",
            mex=True,
            event_id=EVENT_ID,
            outcomes=[(1, "yes", 0.55, False), (2, "no", 0.45, False)],
        ),
    ),
    # --- esports_multi_bundles AND nonexclusive_bundle_markets: >=3 outcomes,
    #     >=2 winners, category esports.
    (
        _m(40),
        dict(
            source="polymarket",
            category="esports",
            market_type="multi",
            mex=False,
            outcomes=[
                (1, "kills over 10.5", 0.60, True),
                (2, "kills over 15.5", 0.40, True),
                (3, "kills over 20.5", 0.20, False),
            ],
        ),
    ),
    # --- draw_authority_markets: soccer duel, 2 outcomes, no draw member.
    (
        _m(50),
        dict(
            source="kalshi",
            category="soccer",
            market_type="duel",
            mex=True,
            outcomes=[(1, "home", 0.60, True), (2, "away", 0.40, False)],
        ),
    ),
    # --- orphan_partition_markets: market_type 'field' with a single outcome.
    (
        _m(60),
        dict(
            source="kalshi",
            category="politics",
            market_type="field",
            mex=True,
            outcomes=[(1, "lonely", 0.50, True)],
        ),
    ),
    # --- The multi pool + THE TIE. Five legs on one event, so vm_id is the
    #     event arm and eligible = 5. Two legs sit at 0.40 and 0.60: both are
    #     exactly 0.10 from 0.50, so `rn` is decided ONLY by the fo.id
    #     tie-break, which is the part of the window a join reordering could
    #     plausibly disturb.
    (
        _m(70),
        dict(
            source="kalshi",
            category="politics",
            market_type="binary",
            mex=False,
            event_id=EVENT_ID,
            outcomes=[(1, "tie-low", 0.40, False), (2, "tie-high", 0.60, True)],
        ),
    ),
    (
        _m(80),
        dict(
            source="kalshi",
            category="politics",
            market_type="binary",
            mex=False,
            event_id=EVENT_ID,
            outcomes=[(1, "far", 0.05, False)],
        ),
    ),
    (
        _m(90),
        dict(
            source="kalshi",
            category="politics",
            market_type="binary",
            mex=False,
            event_id=EVENT_ID,
            outcomes=[(1, "mid", 0.52, True)],
        ),
    ),
    # --- is_weather_wide_spread: kalshi weather, ask-bid >= 0.50, no trade.
    (
        _m(100),
        dict(
            source="kalshi",
            category="weather",
            market_type="binary",
            mex=False,
            yes_bid=0.10,
            yes_ask=0.90,
            traded=False,
            outcomes=[(1, "rain", 0.50, True)],
        ),
    ),
    # --- is_poly_placeholder: polymarket in [0.45, 0.55] with no bid or trade.
    (
        _m(110),
        dict(
            source="polymarket",
            category="politics",
            market_type="binary",
            mex=False,
            traded=False,
            outcomes=[(1, "coinflip", 0.50, True)],
        ),
    ),
    # --- is_liquid false: kalshi with no bid and no trade in any snapshot.
    (
        _m(120),
        dict(
            source="kalshi",
            category="politics",
            market_type="binary",
            mex=False,
            traded=False,
            outcomes=[(1, "phantom", 0.30, True)],
        ),
    ),
    # --- is_kalshi_prop_threshold: the 'Player: N+' OVER name in the
    #     degenerate >= 0.90 band.
    (
        _m(130),
        dict(
            source="kalshi",
            category="basketball",
            market_type="binary",
            mex=False,
            outcomes=[(1, "Curry: 20+", 0.95, True)],
        ),
    ),
    # --- CAL-P098 / G2: THE INCOMPLETE FIELD. Four Kalshi weather members with a
    #     proved exhaustive shape and exactly one winner, so all four are in
    #     ``mex_field_candidates`` (terminal_eligible_n = 4) and the divisor sums
    #     to 1.60 > 1.15. Member ``wx-d`` carries a 0.10/0.90 book with bid
    #     evidence but NO trade: it stays LIQUID and stays in the roster, and it
    #     is excluded per-outcome by ``is_weather_wide_spread``. So survivor_n
    #     (3) != eligible_n (4), ``is_field_incomplete`` fires, and the WHOLE
    #     field drops — including the three members that were perfectly fine.
    #
    #     This is the specimen that makes §3's rejected shortcut visible. If the
    #     exclusion flags were joined after ``rn = 1``, ``field_completeness``
    #     would aggregate them over one row instead of four, ``wx-d``'s exclusion
    #     would be invisible, and this field would publish NORMALIZED over its
    #     survivors — four wrong rows, right count, plausible curve.
    (
        _m(140),
        dict(
            source="kalshi",
            category="weather",
            market_type="field",
            mex=True,
            shape=_PROVED_SHAPE,
            outcomes=[
                (1, "wx-a", 0.70, True),
                (2, "wx-b", 0.40, False),
                (3, "wx-c", 0.30, False),
                (
                    4,
                    "wx-d",
                    0.20,
                    False,
                    dict(yes_bid=0.10, yes_ask=0.90, snapshot="bid_only"),
                ),
            ],
        ),
    ),
    # --- CAL-P098 / G2: the polymarket NON-placeholder half of the pair. Same
    #     source, same 0.50 price, same band as ``_m(110)``; the only difference
    #     is that this one has trade evidence. #151's census says that is the
    #     discriminator, so the pair proves the gate keys on evidence rather than
    #     on the price.
    (
        _m(150),
        dict(
            source="polymarket",
            category="politics",
            market_type="binary",
            mex=False,
            outcomes=[(1, "real-coinflip", 0.50, True)],
        ),
    ),
    # --- CAL-P098 / G2: the kalshi LIQUID half of the pair. Same source, same
    #     0.30 price as the ``_m(120)`` phantom; the only difference is one
    #     snapshot carrying a bid and no trade — the Queue #267 / C44 #1 case
    #     where a bid-bearing, never-traded, volume-0 row MUST survive.
    (
        _m(160),
        dict(
            source="kalshi",
            category="politics",
            market_type="binary",
            mex=False,
            outcomes=[(1, "bid-bearing", 0.30, True, dict(snapshot="bid_only"))],
        ),
    ),
)

ALL_MARKETS = [mid for mid, _ in SEED]


#: THE PER-FIXTURE ORACLE (G2). For every seeded market: exactly which
#: ``outcome_id`` values reach ``deduped``, and the one sentence that says why.
#:
#: This is the assertion the BLOCK found missing. Global OLD == NEW equality is
#: green when both chains are wrong together and green when the seed publishes
#: nothing at all; naming the answer is what makes the gate non-vacuous. It is
#: checked against OLD and NEW *independently*, so a wrong expectation fails on
#: both sides identically and reads as an expectation bug rather than a rewrite
#: defect — which is the difference between a one-line fix and a re-cert.
EXPECTED: dict[int, dict] = {
    _m(10): {
        "published": [_m(10) + 1, _m(10) + 2, _m(10) + 3, _m(10) + 4],
        "why": "complete 4-member field: every member survives, so it normalizes and publishes whole",
        "flags": {"is_mex_normalized": True, "is_field_incomplete": False},
        # cp / 1.60 over the four members.
        "adj": {
            _m(10) + 1: 0.4375,
            _m(10) + 2: 0.25,
            _m(10) + 3: 0.1875,
            _m(10) + 4: 0.125,
        },
    },
    _m(20): {
        "published": [_m(20) + 3],
        "why": "golf placeholder: the two >=0.80 members are excluded, the 0.10 member is not",
        "flags": {"is_golf_placeholder": False},
    },
    _m(30): {
        "published": [],
        "why": "malformed 2-outcome mex binary with zero winners — also a no-winner market",
        "flags": {"is_malformed_binary": True, "is_no_winner_market": True},
    },
    _m(40): {
        "published": [],
        "why": "esports multi bundle with two winners",
        "flags": {"is_esports_bundle": True, "is_nonexclusive_bundle": True},
    },
    _m(50): {
        "published": [],
        "why": "soccer duel with no draw member — draw authority missing",
        "flags": {"is_draw_authority_missing": True},
    },
    _m(60): {
        "published": [],
        "why": "'field' that captured a single member — orphan partition",
        "flags": {"is_orphan_partition": True},
    },
    _m(70): {
        "published": [_m(70) + 1, _m(70) + 2],
        "why": "multi pool: both legs publish; the tie only decides rn, not membership",
        "flags": {"is_multi": True},
    },
    _m(80): {
        "published": [_m(80) + 1],
        "why": "multi pool leg at 0.05, inside the (0.005, 0.98) band",
        "flags": {"is_multi": True},
    },
    _m(90): {
        "published": [_m(90) + 1],
        "why": "multi pool leg at 0.52",
        "flags": {"is_multi": True},
    },
    _m(100): {
        "published": [],
        "why": "kalshi weather wide book with no snapshot at all — illiquid AND wide-spread",
        "flags": {"is_weather_wide_spread": True, "is_liquid": False},
    },
    _m(110): {
        "published": [],
        "why": "polymarket 0.50 with no bid and no trade — synthetic placeholder",
        "flags": {"is_poly_placeholder": True},
    },
    _m(120): {
        "published": [],
        "why": "kalshi with no snapshot evidence at all — never bid, never traded",
        "flags": {"is_liquid": False},
    },
    _m(130): {
        "published": [],
        "why": "kalshi 'Curry: 20+' OVER capture in the degenerate >=0.90 band",
        "flags": {"is_kalshi_prop_threshold": True},
    },
    _m(140): {
        "published": [],
        "why": (
            "INCOMPLETE FIELD: one wide-book member is excluded per-outcome, so "
            "survivor_n (3) != eligible_n (4) and the whole field drops — it is "
            "never normalized over its survivors"
        ),
        "flags": {"is_mex_normalized": False, "is_field_incomplete": True},
    },
    _m(150): {
        "published": [_m(150) + 1],
        "why": "polymarket 0.50 WITH trade evidence — a genuine coin flip, kept",
        "flags": {"is_poly_placeholder": False},
    },
    _m(160): {
        "published": [_m(160) + 1],
        "why": "kalshi bid-bearing, never-traded, volume-0 row — the C44 #1 keep",
        "flags": {"is_liquid": True},
    },
}


def _snapshot_kind(spec: dict, override: dict) -> str:
    if "snapshot" in override:
        return override["snapshot"]
    return "traded" if spec.get("traded", True) else "none"


async def _seed(session) -> None:
    from sqlalchemy import text

    await session.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :n, true)"),
        {"i": SPORT_ID, "k": f"test_p096_{SPORT_ID}", "n": "Test P096"},
    )
    await session.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status) VALUES (:i, :s, 'H96', 'A96', :ct, 'completed')"
        ),
        {
            "i": EVENT_ID,
            "s": SPORT_ID,
            "ct": datetime(2026, 2, 3, 4, 5, tzinfo=timezone.utc).replace(tzinfo=None),
        },
    )

    for mid, spec in SEED:
        await session.execute(
            text(
                "INSERT INTO futures_markets (id, external_id, name, source, status, "
                "category, event_id, group_id, mutually_exclusive, market_type, "
                "llm_sport_category, volume, market_metadata) "
                "VALUES (:id, :xid, :nm, :src, 'resolved', 'championship', :ev, :gid, "
                ":mex, :mt, :cat, 100, CAST(:meta AS jsonb))"
            ),
            {
                "id": mid,
                "xid": f"test-p096-{mid}",
                "nm": f"market-{mid}",
                "src": spec["source"],
                "ev": spec.get("event_id"),
                "gid": spec.get("group_id"),
                "mex": spec["mex"],
                "mt": spec["market_type"],
                "cat": spec["category"],
                # ``shape`` is what mex_field_candidates reads; markets without
                # one are simply not partition candidates, which is the point.
                "meta": '{"shape": %s}' % spec["shape"]
                if spec.get("shape")
                else "{}",
            },
        )
        for outcome in spec["outcomes"]:
            off, name, price, winner = outcome[:4]
            override = outcome[4] if len(outcome) > 4 else {}
            oid = mid + off
            await session.execute(
                text(
                    "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
                    "opening_probability, calibration_probability, is_winner, "
                    "resolution_source, volume, current_yes_bid, current_yes_ask) "
                    "VALUES (:id, :mid, :xid, :nm, :p, :p, :w, 'api_settlement', 10, "
                    ":bid, :ask)"
                ),
                {
                    "id": oid,
                    "mid": mid,
                    "xid": f"test-p096-out-{oid}",
                    "nm": name,
                    "p": price,
                    "w": winner,
                    "bid": override.get("yes_bid", spec.get("yes_bid")),
                    "ask": override.get("yes_ask", spec.get("yes_ask")),
                },
            )
            kind = _snapshot_kind(spec, override)
            if kind == "none":
                continue
            # ``bid_only`` is the row that is liquid without ever trading: the
            # #940 filter keeps it (yes_bid > 0) and the weather wide-spread
            # rule can still exclude it (no last_price > 0). Without the two
            # being separable, an incomplete field cannot be constructed.
            await session.execute(
                text(
                    "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                    "probability, reading_count, last_price, yes_bid) VALUES "
                    "(:oid, 'test-p096', :p, 1, :last, :p)"
                ),
                {"oid": oid, "p": price, "last": price if kind == "traded" else None},
            )
    await session.commit()


async def _cleanup(session) -> None:
    from sqlalchemy import text

    await session.execute(
        text(
            "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
            "(SELECT id FROM futures_outcomes WHERE market_id = ANY(:m))"
        ),
        {"m": ALL_MARKETS},
    )
    await session.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = ANY(:m)"),
        {"m": ALL_MARKETS},
    )
    await session.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:m)"), {"m": ALL_MARKETS}
    )
    await session.execute(text("DELETE FROM events WHERE id = :i"), {"i": EVENT_ID})
    await session.execute(text("DELETE FROM sports WHERE id = :i"), {"i": SPORT_ID})
    await session.commit()


def _chains() -> tuple[str, str]:
    """``(old, new)`` — with ``FOLD_GATE_MUTANT`` applied to NEW when set.

    Every mutant is validated to have CHANGED the text before it is used. A
    mutation that silently fails to apply is the worst possible outcome here:
    the control runs, the gate stays green, and the green is filed as evidence
    that the comparator has teeth it was never shown to have.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes
    from app.utils import fold_narrowing_gate as gate

    old = FUSED_SQL.read_text()
    new = _calibration_population_ctes()

    if not MUTANT:
        return old, new
    if MUTANT == "wide_shape":
        # NEW becomes the pre-rewrite shape. Row identity is trivially perfect;
        # the width gate is what must go red.
        return old, old
    if MUTANT == "row_swap":
        # Applied at the comparator, not the chain — the swap is a perturbation
        # of the final relation, which is the only way to keep every aggregate
        # identical while moving a row identity.
        return old, new
    mutated = {
        "global_rn1": gate.mutant_global_rn1,
        "flag_flip": gate.mutant_flag_flip,
        "narrow_population": gate.mutant_narrow_population,
    }[MUTANT](new)
    assert mutated != new, f"mutant {MUTANT!r} did not change the SQL"
    return old, mutated


async def _rows(session, ctes: str, relation: str, order_by: str):
    from sqlalchemy import text

    result = await session.execute(
        text(f"WITH {ctes} SELECT * FROM {relation} ORDER BY {order_by}")
    )
    return [tuple(r) for r in result.all()], list(result.keys())


async def _engine_and_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_narrowed_ctes_select_the_same_rows_as_the_fused_ctes():
    fused, narrowed = _chains()
    assert "ranked_outcomes_core" not in fused, (
        "the frozen oracle already contains the split — it is no longer the "
        "pre-rewrite SQL and cannot certify the rewrite"
    )
    if not MUTANT:
        assert "ranked_outcomes_core" in narrowed

    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed(session)

            # (a) ranked_outcomes itself — every candidate row, all 31 columns.
            #     This is the strictest form of the claim: not just the
            #     published rows, but the relation every downstream CTE reads.
            fused_ro, fused_cols = await _rows(
                session, fused, "ranked_outcomes", "outcome_id"
            )
            narrow_ro, narrow_cols = await _rows(
                session, narrowed, "ranked_outcomes", "outcome_id"
            )
            assert fused_cols == narrow_cols, (
                "column NAMES or ORDER moved; downstream `SELECT ro.*` consumers "
                f"do not see the same relation (fused={fused_cols}, "
                f"narrowed={narrow_cols})"
            )
            assert len(fused_cols) == 31
            assert fused_ro, "the seed reached no candidate rows — vacuous gate"
            assert narrow_ro == fused_ro

            # (b) THE TIE, named rather than trusted. Both legs of market _m(70)
            #     sit exactly 0.10 from 0.50, so rn is decided by fo.id alone.
            by_outcome = {
                row[fused_cols.index("outcome_id")]: row for row in narrow_ro
            }
            low, high = _m(70) + 1, _m(70) + 2
            assert low in by_outcome and high in by_outcome, (
                "PREMISE GONE: the tied pair no longer reaches ranked_outcomes, "
                "so the tie-break is untested. Re-aim the seed, do not delete it."
            )
            rn = fused_cols.index("rn")
            assert by_outcome[low][rn] < by_outcome[high][rn], (
                "the lower fo.id must win an exact ABS(cp-0.5) tie (Queue 300D "
                "Item 1 / Alex's 2026-08-03 tie authority)"
            )

            # (c) deduped — the published population, which is what the page is.
            fused_pub, fused_pub_cols = await _rows(
                session, fused, "deduped", "outcome_id"
            )
            narrow_pub, narrow_pub_cols = await _rows(
                session, narrowed, "deduped", "outcome_id"
            )
            assert fused_pub_cols == narrow_pub_cols
            assert fused_pub, "nothing published — vacuous gate"
            assert narrow_pub == fused_pub

            # (d) field_completeness — the aggregate that made §3's proposed
            #     "join the flags after rn=1" unavailable. It reads the flags
            #     over EVERY row of a market, so if the rewrite had deferred
            #     them past the rn=1 filter this is where it would show.
            fused_fc, _ = await _rows(
                session, fused, "field_completeness", "market_id"
            )
            narrow_fc, _ = await _rows(
                session, narrowed, "field_completeness", "market_id"
            )
            assert fused_fc, "no normalization candidate in the seed — vacuous"
            assert narrow_fc == fused_fc
        async with Session() as session:
            await _cleanup(session)
    finally:
        # Always, including on an assertion failure. Under FOLD_GATE_MUTANT
        # every one of these tests is SUPPOSED to fail, and a failing test
        # that leaves its seed behind hands the next of the loop's six runs
        # a database it did not build.
        async with Session() as session:
            await _cleanup(session)
        await engine.dispose()


async def test_every_deferred_flag_is_actually_exercised_by_the_seed():
    """A row-identity gate over a seed that never lights a flag proves nothing
    about that flag's join. Assert the coverage instead of hoping for it."""
    from sqlalchemy import text

    _, narrowed = _chains()
    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed(session)
            row = (
                await session.execute(
                    text(
                        "WITH "
                        + narrowed
                        + """
                        SELECT
                          COUNT(*) FILTER (WHERE candidate_market_id IS NOT NULL) AS mfc,
                          COUNT(*) FILTER (WHERE mnm_cp_sum IS NOT NULL) AS mfd,
                          COUNT(*) FILTER (WHERE is_malformed_binary) AS mb,
                          COUNT(*) FILTER (WHERE is_esports_bundle) AS emb,
                          COUNT(*) FILTER (WHERE is_no_winner_market) AS nwm,
                          COUNT(*) FILTER (WHERE is_draw_authority_missing) AS dam,
                          COUNT(*) FILTER (WHERE is_orphan_partition) AS opm,
                          COUNT(*) FILTER (WHERE is_nonexclusive_bundle) AS nbm,
                          COUNT(*) FILTER (WHERE is_golf_placeholder) AS gpm,
                          COUNT(*) FILTER (WHERE NOT is_liquid) AS illiquid,
                          COUNT(*) FILTER (WHERE is_liquid) AS liquid,
                          COUNT(*) FILTER (WHERE is_poly_placeholder) AS poly,
                          COUNT(*) FILTER (WHERE is_weather_wide_spread) AS weather,
                          COUNT(*) FILTER (WHERE is_kalshi_prop_threshold) AS prop
                        FROM ranked_outcomes
                        WHERE market_id = ANY(:m)
                        """
                    ),
                    {"m": ALL_MARKETS},
                )
            ).one()
            missing = [k for k, v in row._mapping.items() if not v]
            assert not missing, (
                f"the seed never lights {missing} — those joins are carried by "
                "this gate in name only"
            )
        async with Session() as session:
            await _cleanup(session)
    finally:
        # Always, including on an assertion failure. Under FOLD_GATE_MUTANT
        # every one of these tests is SUPPOSED to fail, and a failing test
        # that leaves its seed behind hands the next of the loop's six runs
        # a database it did not build.
        async with Session() as session:
            await _cleanup(session)
        await engine.dispose()


async def test_per_fixture_expected_rows_and_values():
    """G2 — name the answer, per fixture, on BOTH chains independently.

    ``deduped`` is asserted market by market against :data:`EXPECTED`, and every
    named flag and normalized probability is asserted on the row itself. The two
    chains are graded separately and the failure message prints the actual
    published table, because CI is the only place this can run and a bare
    ``assert a == b`` there costs a whole cycle to diagnose.
    """
    fused, narrowed = _chains()
    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed(session)

            for label, chain in (("OLD/fused", fused), ("NEW/narrowed", narrowed)):
                rows, cols = await _rows(session, chain, "deduped", "outcome_id")
                idx = {name: i for i, name in enumerate(cols)}
                mine = [r for r in rows if r[idx["market_id"]] in EXPECTED]
                actual: dict[int, list[int]] = {mid: [] for mid in EXPECTED}
                for row in mine:
                    actual[row[idx["market_id"]]].append(row[idx["outcome_id"]])
                dump = "\n".join(
                    f"    {mid}: expected {spec['published']} got "
                    f"{sorted(actual[mid])}   ({spec['why']})"
                    for mid, spec in EXPECTED.items()
                    if sorted(actual[mid]) != sorted(spec["published"])
                )
                assert not dump, f"{label} published the wrong rows:\n{dump}"

                by_outcome = {r[idx["outcome_id"]]: r for r in mine}
                for mid, spec in EXPECTED.items():
                    for oid in spec["published"]:
                        row = by_outcome[oid]
                        for flag, want in spec.get("flags", {}).items():
                            assert row[idx[flag]] == want, (
                                f"{label} outcome {oid}: {flag} is "
                                f"{row[idx[flag]]!r}, expected {want!r}"
                            )
                        want_adj = spec.get("adj", {}).get(oid)
                        if want_adj is not None:
                            got = float(row[idx["adj_opening_probability"]])
                            assert got == pytest.approx(want_adj, abs=1e-9), (
                                f"{label} outcome {oid}: adjusted probability "
                                f"{got} != {want_adj}"
                            )

                # G2 names it explicitly: "a complete normalized field whose
                # every member must survive and sum to 1". The four members of
                # ``_m(10)`` divide by their own 1.60 divisor, so the partition
                # has to close — a field that publishes 0.999 or 1.004 is the
                # C14 defect, and only the SUM can see it.
                field = [
                    r for r in mine if r[idx["market_id"]] == _m(10)
                ]
                assert len(field) == 4
                total = sum(float(r[idx["adj_opening_probability"]]) for r in field)
                assert total == pytest.approx(1.0, abs=1e-9), (
                    f"{label}: the complete field publishes {total}, not 1.0"
                )

            # The excluded specimens carry their flags in ``normalized`` even
            # though they never reach ``deduped`` — assert them there, or an
            # exclusion that happened for the WRONG reason reads as a pass.
            for label, chain in (("OLD/fused", fused), ("NEW/narrowed", narrowed)):
                rows, cols = await _rows(session, chain, "normalized", "outcome_id")
                idx = {name: i for i, name in enumerate(cols)}
                by_outcome = {r[idx["outcome_id"]]: r for r in rows}
                for mid, spec in EXPECTED.items():
                    if spec["published"]:
                        continue
                    for flag, want in spec.get("flags", {}).items():
                        members = [
                            r for r in rows if r[idx["market_id"]] == mid
                        ]
                        assert members, f"{label}: market {mid} vanished before normalized"
                        assert any(r[idx[flag]] == want for r in members), (
                            f"{label}: market {mid} has no member with "
                            f"{flag}={want!r} — it was excluded, but not for the "
                            f"reason this fixture exists to test ({spec['why']})"
                        )

            # The incomplete field, stated exactly: four candidate members, a
            # 1.60 divisor, three survivors, and nothing published.
            rows, cols = await _rows(session, narrowed, "field_completeness", "market_id")
            idx = {name: i for i, name in enumerate(cols)}
            fc = {r[idx["market_id"]]: r for r in rows}
            assert _m(140) in fc, (
                "the incomplete field is not a normalization candidate at all — "
                "its shape/winner/roster premises broke and the specimen is inert"
            )
            assert fc[_m(140)][idx["eligible_n"]] == 4
            assert fc[_m(140)][idx["survivor_n"]] == 3, (
                "the wide-book member must be in the roster and excluded from "
                "the survivors — that gap IS the specimen"
            )
        async with Session() as session:
            await _cleanup(session)
    finally:
        # Always, including on an assertion failure. Under FOLD_GATE_MUTANT
        # every one of these tests is SUPPOSED to fail, and a failing test
        # that leaves its seed behind hands the next of the loop's six runs
        # a database it did not build.
        async with Session() as session:
            await _cleanup(session)
        await engine.dispose()


async def test_the_production_g1_comparator_runs_and_agrees_on_the_seed():
    """Execute the ONE-OFF-DYNO harness's own statement against the seed.

    This is the finding-1 fix, proved rather than described. The statement built
    here is byte-for-byte what
    ``scripts/verify_fold_narrowing_row_identity.py`` sends to production: one
    statement, both chains nested in their own scopes, bilateral ``EXCEPT ALL``,
    duplicate cardinality by ``outcome_id``, and the bucket aggregate demoted to
    a secondary line. If the harness cannot execute, that fact is discovered
    here on a seeded database rather than on a one-off dyno at MOD 64.
    """
    from sqlalchemy import text

    from app.utils.fold_narrowing_gate import (
        G1_COLUMNS,
        G1_REQUIRED_COLUMNS,
        g1_statement,
        g1_verdict,
        row_swap_expr,
    )

    fused, narrowed = _chains()
    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed(session)

            pub_cols = (await _rows(session, narrowed, "deduped", "outcome_id"))[1]
            missing = [c for c in G1_REQUIRED_COLUMNS if c not in pub_cols]
            assert not missing, (
                f"deduped no longer carries {missing}; G1 names those columns as "
                "semantically consumed, so the comparison would not cover them"
            )

            new_rows_expr = "SELECT * FROM new_base"
            if MUTANT == "row_swap":
                victim = min(
                    r[pub_cols.index("outcome_id")]
                    for r in (await _rows(session, narrowed, "deduped", "outcome_id"))[0]
                )
                new_rows_expr = row_swap_expr(
                    columns=pub_cols, victim_outcome_id=victim, offset=SWAP_OFFSET
                )

            statement = g1_statement(
                old_chain=fused, new_chain=narrowed, new_rows_expr=new_rows_expr
            )
            record = (await session.execute(text(statement))).one()
            row = {k: v for k, v in zip(G1_COLUMNS, record)}
            verdict, reasons = g1_verdict(row)
            assert verdict == "PASS", f"{verdict}: {reasons}  counters={row}"
    finally:
        # Always, including on an assertion failure. Under FOLD_GATE_MUTANT
        # every one of these tests is SUPPOSED to fail, and a failing test
        # that leaves its seed behind hands the next of the loop's six runs
        # a database it did not build.
        async with Session() as session:
            await _cleanup(session)
        await engine.dispose()


async def test_aggregate_green_while_row_identity_red_collision_control():
    """Queue 299 / #259's precedent, kept permanently: prove the oracles disagree.

    A row is deleted and replaced by one carrying every value except a different
    ``outcome_id``. ``outcome_id`` is in no bucket key, so the AGGREGATE
    comparator must stay green — same source, category, ``price_moved``, bucket,
    count, winners, probability sum — while the ROW comparator must go red with
    exactly one old-only and one new-only row.

    Without this, G1 is vacuous by the frozen text's own words. It runs
    unconditionally, including under every mutant, because it tests the ruler
    rather than the thing being measured.
    """
    from sqlalchemy import text

    from app.tasks.precompute_calibration import _calibration_population_ctes
    from app.utils.fold_narrowing_gate import G1_COLUMNS, g1_statement, row_swap_expr

    fused = FUSED_SQL.read_text()
    narrowed = _calibration_population_ctes()

    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed(session)

            rows, cols = await _rows(session, narrowed, "deduped", "outcome_id")
            assert rows, "nothing published — the collision control is vacuous"
            victim = rows[0][cols.index("outcome_id")]

            statement = g1_statement(
                old_chain=fused,
                new_chain=narrowed,
                new_rows_expr=row_swap_expr(
                    columns=cols, victim_outcome_id=victim, offset=SWAP_OFFSET
                ),
            )
            record = (await session.execute(text(statement))).one()
            row = {k: v for k, v in zip(G1_COLUMNS, record)}

            assert row["old_only_rows"] == 1 and row["new_only_rows"] == 1, (
                "the ROW-identity oracle did not notice a swapped row — it is "
                f"not an oracle. counters={row}"
            )
            assert row["n_old"] == row["n_new"], "the swap must preserve the count"
            assert row["bucket_old_only"] == 0 and row["bucket_new_only"] == 0, (
                "the AGGREGATE comparator noticed the swap, so this fixture is "
                "not the collision the precedent requires; pick a perturbation "
                f"that no bucket key can see. counters={row}"
            )
    finally:
        # Always, including on an assertion failure. Under FOLD_GATE_MUTANT
        # every one of these tests is SUPPOSED to fail, and a failing test
        # that leaves its seed behind hands the next of the loop's six runs
        # a database it did not build.
        async with Session() as session:
            await _cleanup(session)
        await engine.dispose()


async def test_new_sort_is_narrower_than_the_old_sort():
    """G3's width clause, on the seed — plan-only, so it costs nothing.

    ``EXPLAIN`` without ``ANALYZE`` still reports ``Plan Width``, and width is a
    property of the projection rather than of the data, so the seed can grade it
    honestly where it could not grade a duration. The production runner measures
    rows, spill and time with ``ANALYZE`` on real samples; this is the part of
    G3 that is checkable in CI, and it is also the control that ``wide_shape``
    must break.
    """
    import json

    from sqlalchemy import text

    from app.utils.fold_narrowing_gate import (
        G3_MAX_WIDTH_RATIO,
        NEW_WINDOW_CTE,
        OLD_WINDOW_CTE,
        named_node_metrics,
    )
    from app.utils.sql_comment_strip import strip_sql_comments

    fused, narrowed = _chains()
    engine, Session = await _engine_and_session()
    try:
        async with Session() as session:
            await _cleanup(session)
            await _seed(session)

            # Under ``wide_shape`` the NEW chain IS the pre-split chain, so its
            # window lives in ``ranked_outcomes`` and the ratio comes out at
            # 1.0 — which is the red this control exists to produce.
            new_cte = OLD_WINDOW_CTE if MUTANT == "wide_shape" else NEW_WINDOW_CTE
            widths = {}
            for label, chain, cte in (
                ("old", fused, OLD_WINDOW_CTE),
                ("new", narrowed, new_cte),
            ):
                raw = (
                    await session.execute(
                        text(
                            strip_sql_comments(
                                "EXPLAIN (VERBOSE, FORMAT JSON) WITH "
                                + chain
                                + " SELECT * FROM deduped"
                            )
                        )
                    )
                ).scalar()
                plan = json.loads(raw) if isinstance(raw, str) else raw
                metrics = named_node_metrics(plan[0]["Plan"], cte)
                widths[label] = metrics.get("sort_plan_width")

            assert widths["old"], (
                "no Sort under the OLD window CTE — the named node moved and "
                f"G3 cannot be graded from this plan ({widths})"
            )
            assert widths["new"], f"no Sort under the NEW window CTE ({widths})"
            ratio = widths["new"] / widths["old"]
            assert ratio <= G3_MAX_WIDTH_RATIO, (
                f"the narrowed Sort is {widths['new']} B, {ratio:.1%} of OLD's "
                f"{widths['old']} B — G3.2's bar is {G3_MAX_WIDTH_RATIO:.0%}. "
                "The whole rewrite is the width."
            )
    finally:
        # Always, including on an assertion failure. Under FOLD_GATE_MUTANT
        # every one of these tests is SUPPOSED to fail, and a failing test
        # that leaves its seed behind hands the next of the loop's six runs
        # a database it did not build.
        async with Session() as session:
            await _cleanup(session)
        await engine.dispose()
