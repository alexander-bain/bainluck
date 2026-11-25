"""Tests for #13544 Ask 1 (report-only split-set audit + price guard + retired drops) and #13551 Ask 1 (7-looks variety)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils import discover_fun_scout
from app.utils.discover_fun_scout import (
    SCOUT_RETIRED_SETS_PATH,
    ScoutMarketRow,
    ScoutProposedSet,
    check_scout_price_set_context,
    load_retired_scout_sets,
    validate_scout_proposed_set,
)
from app.utils.discover_opening_mix import (
    ALEX_LOOK_PILE_LABELS,
    FORM_TO_LOOK_PILE,
    card_look_pile,
    card_visual_form_or_legacy,
    summarize_discover_form_and_look_variety,
)
from app.utils.feed_quality_debug import served_window_quality
from app.utils.set_split_audit_report import (
    audit_public_set_split_report_only,
    audit_served_public_sets_report_only,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "discover"
DECK_V2_PATH = DATA_DIR / "fun_scout_blind_40_deck_v2_2026_11_23.json"
FROZEN_NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)

# All 11 split-set cards Alex graded Fix or Drop in Deck 2 (#13544 comment 7150409147).
SPLIT_FIX_DROP_IDS: frozenset[str] = frozenset(
    {
        "blind-05",
        "blind-06",
        "blind-10",
        "blind-12",
        "blind-26",
        "blind-29",
        "blind-32",
        "blind-33",
        "blind-36",
        "blind-38",
        "blind-39",
    }
)
PRICE_FIX_DROP_IDS: frozenset[str] = frozenset({"blind-13", "blind-25"})
TOO_FEW_IDS: frozenset[str] = frozenset({"blind-28"})
KEEP_IDS: frozenset[str] = frozenset(
    {f"blind-{i:02d}" for i in range(1, 41)}
    - SPLIT_FIX_DROP_IDS
    - PRICE_FIX_DROP_IDS
    - TOO_FEW_IDS
)


def _deck_cards_by_id() -> dict[str, dict[str, Any]]:
    payload = json.loads(DECK_V2_PATH.read_text(encoding="utf-8"))
    return {c["card_id"]: c for c in payload["cards"]}


def _row_from_member(member: dict[str, Any], *, context_line: str | None = None) -> ScoutMarketRow:
    meta = {"context_line": context_line} if context_line else None
    return ScoutMarketRow(
        market_id=int(member["market_id"]),
        source=str(member["source"]),
        title=str(member["title"]),
        status="open",
        category="culture",
        resolution_date=FROZEN_NOW + timedelta(days=90),
        volume=60_000.0,
        volume_24h=3_000.0,
        market_metadata=meta,
    )


def test_split_set_report_only_flags_all_11_split_cards_and_zero_keeps() -> None:
    cards = _deck_cards_by_id()
    assert len(SPLIT_FIX_DROP_IDS) == 11
    assert len(KEEP_IDS) == 26

    split_reports = {
        cid: audit_public_set_split_report_only(cards[cid]["title"], cards[cid]["members"])
        for cid in sorted(SPLIT_FIX_DROP_IDS)
    }
    assert all(
        rep["mode"] == "report_only"
        and rep["is_split"] is True
        and isinstance(rep["reason"], str)
        and rep["reason"].startswith("split_set:")
        for rep in split_reports.values()
    ), f"Missed split cards: {[k for k, v in split_reports.items() if not v['is_split']]}"

    keep_false_positives = {
        cid: rep
        for cid in sorted(KEEP_IDS)
        if (rep := audit_public_set_split_report_only(cards[cid]["title"], cards[cid]["members"]))["is_split"]
    }
    assert keep_false_positives == {}, f"False positives on Keep sets: {keep_false_positives}"


def test_split_set_audit_delegates_to_builder_e_detect_scout_split_set_when_present(monkeypatch) -> None:
    @dataclass
    class _FakeFinding:
        reason: str
        shared_feature: str

    captured: list[tuple[str, list[ScoutMarketRow]]] = []

    def _fake_detect_scout_split_set(set_title: str, members: list[ScoutMarketRow]):
        captured.append((set_title, list(members)))
        return _FakeFinding(reason="split_subset_subject", shared_feature="elon musk")

    monkeypatch.setattr(discover_fun_scout, "detect_scout_split_set", _fake_detect_scout_split_set, raising=False)
    cards = _deck_cards_by_id()
    rep = audit_public_set_split_report_only(cards["blind-26"]["title"], cards["blind-26"]["members"])
    assert rep["mode"] == "report_only"
    assert rep["detector"] == "detect_scout_split_set"
    assert rep["is_split"] is True
    assert rep["reason"] == "split_subset_subject"
    assert rep["shared_feature"] == "elon musk"
    assert len(captured) == 1 and all(isinstance(r, ScoutMarketRow) for r in captured[0][1])


def test_split_set_stays_report_only_until_13703_while_price_guard_enforces() -> None:
    cards = _deck_cards_by_id()
    # Until #13703 lands, validate_scout_proposed_set runs no duplicate split detector of its own.
    split_card = cards["blind-26"]
    catalog_split = {int(m["market_id"]): _row_from_member(m) for m in split_card["members"]}
    vset_split, err_split = validate_scout_proposed_set(
        ScoutProposedSet(
            slug="pure-long-shots-report-only-check",
            name=split_card["title"],
            kicker="ODD",
            category="culture",
            why_better_together="Earth, meteor, Mars, and Superman appear in this set.",
            look="bars",
            member_ids=tuple(catalog_split.keys()),
        ),
        catalog_split,
        now=FROZEN_NOW,
    )
    assert err_split is None
    assert vset_split is not None

    # Consumer price sets stay blocked without per-row context_line (#13544 Ask 4).
    price_card = cards["blind-13"]
    catalog_price = {int(m["market_id"]): _row_from_member(m) for m in price_card["members"]}
    vset_price, err_price = validate_scout_proposed_set(
        ScoutProposedSet(
            slug="what-things-cost-guard-test",
            name=price_card["title"],
            kicker="MONEY",
            category="economics",
            why_better_together="Disneyland tickets, gas, diesel, and eggs side by side.",
            look="bars",
            member_ids=tuple(catalog_price.keys()),
        ),
        catalog_price,
        now=FROZEN_NOW,
    )
    assert vset_price is None
    assert err_price is not None and err_price.startswith("price_set_missing_row_context:")


def test_price_set_guard_blocks_bare_price_sets_and_allows_contextualized_rows() -> None:
    cards = _deck_cards_by_id()
    for cid in sorted(PRICE_FIX_DROP_IDS):
        card = cards[cid]
        rows = [_row_from_member(m) for m in card["members"]]
        err = check_scout_price_set_context(card["title"], rows)
        assert err is not None and err.startswith("price_set_missing_row_context:")

        rows_with_ctx = [
            _row_from_member(m, context_line="Coin-flip cutoff sits at $5.20 (57%) vs $5.40 (41%).")
            for m in card["members"]
        ]
        assert check_scout_price_set_context(card["title"], rows_with_ctx) is None

    # Fable #13706 review point 2: match "What Stuff Costs Now" (costs?) + >=2 member hits,
    # and never false-positive on an inflation set titled "Consumer prices in December".
    stuff_rows = [
        _row_from_member({"market_id": 9901, "source": "kalshi", "title": "U.S. average retail gas price by December?"}),
        _row_from_member({"market_id": 9902, "source": "kalshi", "title": "Retail diesel price on Dec 31?"}),
        _row_from_member({"market_id": 9903, "source": "kalshi", "title": "Will Costco raise hot dog price in 2026?"}),
        _row_from_member({"market_id": 9904, "source": "kalshi", "title": "Netflix standard plan price above $20?"}),
        _row_from_member({"market_id": 9905, "source": "kalshi", "title": "Spotify Duo price increase?"}),
        _row_from_member({"market_id": 9906, "source": "kalshi", "title": "AMC movie ticket average?"}),
    ]
    err_stuff = check_scout_price_set_context("What Stuff Costs Now", stuff_rows)
    assert err_stuff is not None and err_stuff.startswith("price_set_missing_row_context:")

    inflation_rows = [
        _row_from_member({"market_id": 9911, "source": "kalshi", "title": "December CPI YoY above 2.7%?"}),
        _row_from_member({"market_id": 9912, "source": "kalshi", "title": "Core CPI MoM above 0.3%?"}),
        _row_from_member({"market_id": 9913, "source": "kalshi", "title": "PCE inflation above 2.5%?"}),
    ]
    assert check_scout_price_set_context("Consumer prices in December", inflation_rows) is None


def test_retired_scout_sets_include_deck2_drops_and_load_durably(monkeypatch) -> None:
    import importlib

    scout_task = importlib.import_module("app.tasks.discover_fun_scout")
    entries = load_retired_scout_sets(SCOUT_RETIRED_SETS_PATH)
    slugs = {str(e.get("slug") or "") for e in entries}
    assert {"finale-week", "what-things-cost-2026", "what-things-cost"}.issubset(slugs)

    class _FakeRedis:
        def get(self, _key: str):
            return None

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: _FakeRedis())
    durable_slugs = scout_task._load_retired_sets_durable(SCOUT_RETIRED_SETS_PATH)
    assert {"finale-week", "what-things-cost-2026", "what-things-cost"}.issubset(durable_slugs)


def test_served_audit_and_7_looks_variety_summarize_top10_top20() -> None:
    assert len(FORM_TO_LOOK_PILE) == 14
    assert set(FORM_TO_LOOK_PILE.values()) == set(ALEX_LOOK_PILE_LABELS.keys()) == {
        f"pile_{i}" for i in range(1, 8)
    }

    def _mach_bundle(form_id: str) -> dict[str, Any]:
        return {
            "type": "bundle",
            "data": {"kind": "roundup", "roundup": {"machinery_card": {"form_id": form_id}}},
        }

    legacy_bundle = {
        "type": "bundle",
        "data": {"kind": "roundup", "roundup": {"kicker": "CFP"}},
    }
    assert card_visual_form_or_legacy(legacy_bundle) == "benchmark_strip_legacy"
    assert card_look_pile(legacy_bundle) == "pile_5"

    cards = _deck_cards_by_id()
    split_bundle = {
        "type": "bundle",
        "data": {
            "id": "split-bundle",
            "kind": "roundup",
            "title": cards["blind-26"]["title"],
            "roundup": {"machinery_card": {"form_id": "benchmark_strip"}},
            "items": [
                {"type": "futures", "data": {"id": m["market_id"], "name": m["title"]}}
                for m in cards["blind-26"]["members"]
            ],
        },
    }

    sample_items = [
        split_bundle,
        _mach_bundle("sibling_fields_grid"),        # same look as benchmark_strip -> pile_2
        _mach_bundle("probability_history_chart"),  # same look as benchmark_strip -> pile_2
        {"type": "bundle", "data": {"kind": "theme", "story_key": "story:ai"}},  # pile_1
        _mach_bundle("coin_flip_matchups"),         # pile_3
        _mach_bundle("paired_stage_bars"),          # pile_6
        legacy_bundle,                              # pile_5
        {"type": "futures", "score": 80, "data": {"id": 999, "name": "Single", "category": "odd", "status": "open", "top_outcomes": []}},
        _mach_bundle("matchup_slate"),              # same pile_3 as coin_flip_matchups
        {"type": "bundle", "data": {"kind": "theme", "story_key": "story:congress_control"}},  # pile_1
        _mach_bundle("contender_spotlight"),        # pile_4
        _mach_bundle("duel_bar"),                   # pile_7
    ]
    summary = summarize_discover_form_and_look_variety(sample_items)
    assert summary["top_10"]["grouped_count"] == 9
    assert summary["top_10"]["distinct_forms"] == 9
    assert summary["top_10"]["distinct_looks"] == 5
    assert summary["top_20"]["distinct_looks"] == 7
    assert "5 distinct looks" in summary["summary_line"]
    assert "7 distinct looks" in summary["summary_line"]

    served = served_window_quality(sample_items, top_n=20)
    assert served["forms_top10"] == 9
    assert served["looks_top10"] == 5
    assert served["looks_top20"] == 7
    assert len(served["split_set_audit_report"]) == 1
    assert served["split_set_audit_report"][0]["mode"] == "report_only"
    assert len(audit_served_public_sets_report_only(sample_items)) == 1
