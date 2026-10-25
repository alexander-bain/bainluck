"""Regression suite for #9878 / #11040 (adapted from Fable independent review of 310ef459).

Runs the real ingestion writer (`tasks.polymarket._process_event_batch`) against
real local PostgreSQL and pushes the rows it wrote through the production feed chain
(`market_load_options` ORM load -> `to_plain`/`from_plain` -> `_score_futures`
-> `_dedupe_futures_by_canonical` -> `_dedupe_futures_by_group_id` ->
`_suppress_zero_probability_cards` -> `apply_discover_display_chain`).

Inputs: the retained Oct 14 Zacharia evidence (rule text, condition ids,
questions, groupItemTitles, cutoff instants, prices) from REVIEW_RETAINED_DIR.
Anything that is not retained is SYNTHETIC and is named as such at the point it is written.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
_DEFAULT_RETAINED = Path(
    "/Users/bain/.gemini/antigravity/brain/e9c17473-1c3f-435c-9dbb-a744b792aa74"
    "/scratch/fable-review-movement-story-slice1-v3-20261024/evidence/retained-inputs"
)
RETAINED = Path(os.environ.get("REVIEW_RETAINED_DIR", str(_DEFAULT_RETAINED)))
OUT_DIR = Path(os.environ.get("REVIEW_OUT_DIR", "/tmp/review-out-v4"))

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DB_URL, reason="set SEARCH_TEST_DATABASE_URL"),
]

EVENT_ID = "1183118"
GROUP_ID = f"polymarket:{EVENT_ID}"


def _retained():
    rules = json.loads((RETAINED / "polymarket-rules-extracted.json").read_text())
    d73 = json.loads((RETAINED / "65678073-detail.json").read_text())
    d74 = json.loads((RETAINED / "65678074-detail.json").read_text())
    return {
        "rule": rules[0]["description"],
        "q_oct": rules[2]["question"],
        "q_dec": rules[3]["question"],
        "cid_oct": rules[4]["conditionId"],
        "cid_dec": rules[5]["conditionId"],
        "git_oct": rules[6]["groupItemTitle"],
        "git_dec": rules[7]["groupItemTitle"],
        "end_oct": datetime.fromisoformat(d73["resolution_date"]),
        "end_dec": datetime.fromisoformat(d74["resolution_date"]),
        "yes_oct": next(o["probability"] for o in d73["outcomes"] if o["name"] == "Yes"),
        "yes_dec": next(o["probability"] for o in d74["outcomes"] if o["name"] == "Yes"),
    }


def _leg(r, which, *, description="__retained__", yes=None, closed=False):
    from app.services.polymarket_api import PolymarketMarket

    cid = r[f"cid_{which}"]
    p = r[f"yes_{which}"] if yes is None else yes
    return PolymarketMarket(
        condition_id=cid,
        question=r[f"q_{which}"],
        group_item_title=r[f"git_{which}"],
        end_date=r[f"end_{which}"],
        description=(r["rule"] if description == "__retained__" else description),
        outcomes=["Yes", "No"],
        outcome_prices=[p, round(1 - p, 6)],
        best_bid=round(p - 0.005, 4),
        best_ask=round(p + 0.005, 4),
        last_trade_price=p,
        volume=250_000.0,
        volume_24h=25_000.0,
        clob_token_ids=[f"tok-{which}-yes", f"tok-{which}-no"],
        closed=closed,
    )


def _event(markets, *, neg_risk=False):
    from app.services.polymarket_api import PolymarketEvent

    return PolymarketEvent(
        id=EVENT_ID,
        title="Katie Zacharia out as Press Secretary by...?",
        slug="katie-zacharia-out-as-press-secretary-by",
        tags=["Politics"],
        neg_risk=neg_risk,
        end_date=markets[-1].end_date,
        markets=markets,
        volume=500_000.0,
    )


@pytest.fixture
async def engine(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401
    import app.tasks.base as task_base
    from app.services.database import Base

    eng = create_async_engine(DB_URL)
    async with eng.begin() as conn:
        def _sync_init(sync_conn):
            if (sync_conn.dialect.server_version_info or (0,)) < (15,):
                tbl = Base.metadata.tables.get("container_provider_anchors")
                if tbl is not None:
                    for idx in tbl.indexes:
                        pg_opts = idx.dialect_options.get("postgresql")
                        if pg_opts is not None and hasattr(pg_opts, "_non_defaults"):
                            pg_opts._non_defaults.pop("nulls_not_distinct", None)
            Base.metadata.drop_all(sync_conn)
            Base.metadata.create_all(sync_conn)

        await conn.run_sync(_sync_init)
    monkeypatch.setattr(task_base, "DATABASE_URL", DB_URL)
    yield eng
    await eng.dispose()


async def _poll(event):
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting(errors=[], by_category={})
    await _process_event_batch(
        [event], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    return stats


async def _meta(engine) -> dict:
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT external_id, group_type, market_metadata FROM futures_markets "
                " WHERE group_id = :g ORDER BY id"
            ), {"g": GROUP_ID})
        ).fetchall()
    return {r[0]: {"group_type": r[1], "meta": r[2]} for r in rows}


async def _sql(engine, stmt: str, **params):
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text(stmt), params)


async def _ids(engine):
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT m.external_id, m.id, o.name, o.id FROM futures_markets m "
                "JOIN futures_outcomes o ON o.market_id = m.id "
                "WHERE m.group_id = :g AND m.group_type = 'polymarket_sub_market'"
            ), {"g": GROUP_ID})
        ).fetchall()
    out: dict = {}
    for ext, mid, oname, oid in rows:
        out.setdefault(ext, {"market_id": mid})[oname] = oid
    return out


async def _feed(engine, now, *, snapshot=True):
    """Production feed chain over every row of the group, loaded from PG."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models import FuturesMarket
    from app.routes import feed as feed_route
    from app.utils import futures_market_snapshot as fms
    from app.utils.personalization import PersonalizationContext

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        rows = (
            await s.execute(
                select(FuturesMarket)
                .options(*fms.market_load_options())
                .where(FuturesMarket.group_id == GROUP_ID)
                .order_by(FuturesMarket.id)
            )
        ).scalars().unique().all()
        markets = fms.from_plain(fms.to_plain(list(rows))) if snapshot else list(rows)
    scored = await feed_route._score_futures(
        db=None, now=now, sport_filter=None, ctx=PersonalizationContext(),
        preloaded_base={"markets": markets, "curator_ids": set()},
    )
    a = feed_route._dedupe_futures_by_canonical(scored)
    b = feed_route._dedupe_futures_by_group_id(a)
    c, _ = feed_route._suppress_zero_probability_cards(b)
    displayed, _ = feed_route.apply_discover_display_chain(
        c, limit=20, ctx=PersonalizationContext(), event_pct=0.15,
        include_events=True, my_teams_only=False, sports_mode=False, now=now,
    )
    wire = json.loads(json.dumps(displayed, default=str))
    return {"scored": scored, "after_group": b, "displayed": wire}


def _summ(displayed):
    out = []
    for it in displayed:
        d = it.get("data") or {}
        if it.get("type") == "bundle":
            fam = d.get("deadline_family") or {}
            out.append({
                "type": "bundle", "story_key": d.get("story_key"),
                "member_ids": d.get("member_ids"),
                "selection_reason": fam.get("selection_reason"),
                "representative_market_id": fam.get("representative_market_id"),
            })
        else:
            out.append({"type": it.get("type"), "id": d.get("id"), "name": d.get("name"),
                        "deadline_member": bool(d.get("deadline_member"))})
    return out


def _save(name, obj):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / name).write_text(json.dumps(obj, indent=2, default=str))


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def test_A_lifecycle_valid_incompatible_missing_strip_valid(engine, monkeypatch):
    r = _retained()
    log: dict = {"steps": []}

    def contracts(meta):
        return {
            ext: (v["meta"] or {}).get("deadline_rule_contract")
            for ext, v in meta.items() if v["group_type"] == "polymarket_sub_market"
        }

    async def feed_kind():
        now = datetime.now(timezone.utc)
        f = await _feed(engine, now)
        return _summ(f["displayed"]), f

    # Step 1 — valid retained rules
    st = await _poll(_event([_leg(r, "oct"), _leg(r, "dec")]))
    assert not st["errors"], st["errors"]
    m1 = await _meta(engine)
    c1 = contracts(m1)
    assert c1[r["cid_oct"]]["verified"] is True and c1[r["cid_dec"]]["verified"] is True
    await _sql(engine,
        "UPDATE futures_markets SET market_metadata = market_metadata || "
        "jsonb_build_object('review_marker','keep-me','dated_movement_basis', "
        "jsonb_build_object('999', jsonb_build_array(0.5, '2026-10-14T04:31:09Z'))) "
        "WHERE group_id = :g AND group_type = 'polymarket_sub_market'", g=GROUP_ID)
    s1, _ = await feed_kind()
    log["steps"].append({"step": "1 valid", "contracts": {k: (v or {}).get("status") for k, v in c1.items()}, "feed": s1})
    assert any(x["type"] == "bundle" for x in s1), s1

    # Step 2 — Dec 31 rule edited to an incompatible (non-cumulative window) rule
    bad = r["rule"].replace("between market creation and the specified date", "between November 1 and the specified date")
    st = await _poll(_event([_leg(r, "oct"), _leg(r, "dec", description=bad)]))
    assert not st["errors"], st["errors"]
    m2 = await _meta(engine)
    c2 = contracts(m2)
    dec_meta = m2[r["cid_dec"]]["meta"]
    assert c2[r["cid_dec"]]["verified"] is False
    assert c2[r["cid_dec"]]["status"] == "invalidated_incompatible_rule"
    assert dec_meta.get("review_marker") == "keep-me"
    assert "999" in (dec_meta.get("dated_movement_basis") or {})
    assert dec_meta.get("clob_token_ids") == ["tok-dec-yes", "tok-dec-no"]
    s2, _ = await feed_kind()
    log["steps"].append({"step": "2 incompatible", "contracts": {k: (v or {}).get("status") for k, v in c2.items()}, "feed": s2})
    assert not any(x["type"] == "bundle" for x in s2), s2

    # Step 3 — Dec 31 rule text missing from Gamma
    st = await _poll(_event([_leg(r, "oct"), _leg(r, "dec", description=None)]))
    assert not st["errors"], st["errors"]
    c3 = contracts(await _meta(engine))
    assert c3[r["cid_dec"]]["status"] == "missing_rule_description"
    s3, _ = await feed_kind()
    log["steps"].append({"step": "3 missing", "contracts": {k: (v or {}).get("status") for k, v in c3.items()}, "feed": s3})
    assert not any(x["type"] == "bundle" for x in s3), s3

    # Step 4 — valid again
    st = await _poll(_event([_leg(r, "oct"), _leg(r, "dec")]))
    assert not st["errors"], st["errors"]
    c4 = contracts(await _meta(engine))
    assert c4[r["cid_dec"]]["verified"] is True
    s4, _ = await feed_kind()
    log["steps"].append({"step": "4 valid again", "contracts": {k: (v or {}).get("status") for k, v in c4.items()}, "feed": s4})
    assert any(x["type"] == "bundle" for x in s4), s4

    # Step 5 — the `- 'deadline_rule_contract'` strip arm, executed by PG.
    import app.tasks.polymarket as poly

    monkeypatch.setattr(poly, "build_polymarket_submarket_deadline_contract", lambda e, m: None)
    st = await _poll(_event([_leg(r, "oct"), _leg(r, "dec")]))
    m5 = await _meta(engine)
    c5 = contracts(m5)
    log["steps"].append({
        "step": "5 forced strip arm",
        "errors": [str(e)[:400] for e in st["errors"]],
        "contracts_present": {k: v is not None for k, v in c5.items()},
        "review_marker_kept": {k: (v["meta"] or {}).get("review_marker") for k, v in m5.items() if v["group_type"] == "polymarket_sub_market"},
    })
    monkeypatch.undo()
    _save("A-lifecycle.json", log)
    assert not st["errors"], st["errors"]
    assert all(v is None for v in c5.values()), c5
    assert all((v["meta"] or {}).get("review_marker") == "keep-me" for v in m5.values() if v["group_type"] == "polymarket_sub_market")


async def test_A2_other_writer_changes_question_or_cutoff_without_refreshing_proof(engine):
    """Stored proof is bound to the row's question and cutoff (`question_sha256`, `end_date_iso`)."""
    r = _retained()
    st = await _poll(_event([_leg(r, "oct"), _leg(r, "dec")]))
    assert not st["errors"]
    now = datetime.now(timezone.utc)
    base = _summ((await _feed(engine, now))["displayed"])
    assert any(x["type"] == "bundle" for x in base)

    await _sql(engine, "UPDATE futures_markets SET name = 'Katie Zacharia out as Press Secretary by November 30?' WHERE external_id = :c", c=r["cid_dec"])
    renamed = _summ((await _feed(engine, now))["displayed"])
    await _sql(engine, "UPDATE futures_markets SET name = :n WHERE external_id = :c", n=r["q_dec"], c=r["cid_dec"])
    await _sql(engine, "UPDATE futures_markets SET resolution_date = resolution_date + interval '1 day' WHERE external_id = :c", c=r["cid_dec"])
    redated = _summ((await _feed(engine, now))["displayed"])
    _save("A2-binding.json", {"baseline": base, "renamed_without_proof_refresh": renamed, "redated_without_proof_refresh": redated})
    assert not any(x["type"] == "bundle" for x in renamed), renamed
    assert not any(x["type"] == "bundle" for x in redated), redated
