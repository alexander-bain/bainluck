"""End-to-end turn-on packet verification for all 13 switched-off grouped-card candidates (#12288)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.utils import roundup_containers as rc
from app.utils.ceremony_award_categories import (
    build_ceremony_award_categories_producer,
    produce_ceremony_award_categories,
)
from app.utils.field_selection import select_field_selection

CANDIDATES_DIR = Path(__file__).resolve().parents[1] / "data" / "discover" / "candidates"
CONTAINERS_DIR = rc.CONTAINERS_DATA_DIR

EXPECTED_11_CANDIDATE_SLUGS = (
    "roundup-ai-race",
    "roundup-as-likely-as",
    "roundup-big-movers-today",
    "roundup-ceremony-award-categories",
    "roundup-headliners-and-hosts",
    "roundup-long-shot-movers",
    "roundup-nba-award-ladders",
    "roundup-nba-division-races",
    "roundup-opening-weekend-slate",
    "roundup-team-active-streaks",
    "roundup-upsets-brewing",
)

EXPECTED_2_DISABLED_CONTAINER_SLUGS = (
    "roundup-awards-84th-golden-globe-awards",
    "roundup-cfp-selected-field-2026",
)

FORBIDDEN_READER_COPY_RE = re.compile(
    r"\b(?:questions?|stale|settled|venues?|kalshi|polymarket)\b",
    re.IGNORECASE,
)


def _eval_now_from_packet(packet: dict[str, Any]) -> datetime:
    raw = str(packet["captured_at"])
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_all_13_candidates_remain_switched_off_and_have_eval_packets() -> None:
    """Every switched-off candidate must remain unreachable by live readers until explicitly enabled."""
    def_files = sorted(
        p for p in CANDIDATES_DIR.glob("*.json") if not p.name.endswith("-rows.json")
    )
    found_candidate_slugs = tuple(json.loads(p.read_text())["slug"] for p in def_files)
    assert found_candidate_slugs == EXPECTED_11_CANDIDATE_SLUGS

    for slug in EXPECTED_11_CANDIDATE_SLUGS:
        assert slug not in rc.ROUNDUP_PRODUCERS, f"{slug} must stay switched off in candidates/"
        assert not (CONTAINERS_DIR / f"{slug}.json").exists()
        assert (CANDIDATES_DIR / f"{slug}-rows.json").exists()

    disabled_in_containers = tuple(
        sorted(
            slug
            for slug, prod in rc.ROUNDUP_PRODUCERS.items()
            if callable(prod.enabled) and not prod.enabled()
        )
    )
    assert disabled_in_containers == EXPECTED_2_DISABLED_CONTAINER_SLUGS
    for slug in EXPECTED_2_DISABLED_CONTAINER_SLUGS:
        assert (CANDIDATES_DIR / f"{slug}-rows.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", EXPECTED_11_CANDIDATE_SLUGS)
async def test_each_r4_candidate_passes_eval_rows_trading_guard_and_website_contract(
    slug: str,
) -> None:
    """Every R4 candidate passes its Nov 14 eval packet, excludes untraded markets, and satisfies RoundupCard."""
    defn = json.loads((CANDIDATES_DIR / f"{slug}.json").read_text())
    packet = json.loads((CANDIDATES_DIR / f"{slug}-rows.json").read_text())
    assert packet["candidate_slug"] == slug
    assert packet["producer"] == defn["rule"]["producer"]

    producer = rc.build_roundup_producer_from_definition(defn)
    eval_now = _eval_now_from_packet(packet)

    inp: Any = (
        packet.get("input_markets")
        or packet.get("input_items")
        or packet.get("input_payload")
        or packet.get("input_events")
    )
    assert inp is not None

    # Pass eval timestamp when the producer accepts `now=` so 6h freshness windows remain deterministic.
    import inspect

    mod = __import__(
        rc._KIND_TO_MODULE_BUILDER[defn["rule"]["producer"]][0],
        fromlist=["*"],
    )
    produce_fn = next(
        getattr(mod, attr)
        for attr in dir(mod)
        if attr.startswith("produce_") and callable(getattr(mod, attr))
    )
    if "now" in inspect.signature(produce_fn).parameters:
        members = await produce_fn(inp, rule=producer.rule, now=eval_now)
    else:
        members = await producer.produce(inp)

    assert not isinstance(
        members, rc.RoundupRefusal
    ), f"{slug} refused eval packet: {members.reasons}"

    member_ids = [int(m["id"]) for m in members.members]
    if "expected_member_ids" in packet:
        assert set(member_ids) == set(packet["expected_member_ids"])
    if "expected_event_ids" in packet:
        assert member_ids == list(packet["expected_event_ids"])
    if "expected_card_row_ids" in packet:
        row_market_ids = [int(r["market_id"]) for r in members.rows]
        assert row_market_ids == list(packet["expected_card_row_ids"])

    excluded_ids: set[int] = set()
    for key in (
        "excluded_ids",
        "excluded_untraded_ids",
        "excluded_unpriced_event_ids",
        "excluded_event_ids",
    ):
        excluded_ids.update(int(x) for x in (packet.get(key) or ()))
    assert excluded_ids, f"{slug} eval packet must include at least one excluded untraded/stale control row"

    seated_row_base_ids = {
        int(r["market_id"] if r.get("market_id") is not None else r["event_id"])
        for r in members.rows
    }
    assert not (excluded_ids & set(member_ids)), f"{slug} leaked excluded member IDs"
    assert not (excluded_ids & seated_row_base_ids), f"{slug} leaked excluded row IDs"

    # Verify every seated futures market in input_markets is open & actively trading (volume > 0).
    if "input_markets" in packet:
        by_id = {int(m["id"]): m for m in packet["input_markets"]}
        for mid in member_ids:
            src_m = by_id[mid]
            assert src_m.get("status") == "open"
            vol = src_m.get("volume_24h", src_m.get("volume"))
            if vol is not None:
                assert float(vol) > 0.0, f"{slug} seated $0-volume market #{mid}"

    feed_item = rc.compose_roundup_feed_item(producer, members)
    container = rc.compose_roundup_container(producer, members)
    assert feed_item is not None
    bundle = feed_item["data"]
    roundup = bundle["roundup"]

    # Website RoundupCard.tsx / buildRoundupCardModel contract checks:
    title = str(bundle.get("title") or "").strip()
    subtitle = str(roundup.get("subtitle") or "").strip()
    kicker = str(roundup.get("kicker") or "").strip()
    footer = str(roundup.get("footer") or "").strip()
    rows = roundup.get("rows") or []

    assert len(title) >= 12
    assert len(subtitle) >= 45
    assert subtitle == roundup.get("context_line")
    assert subtitle == feed_item.get("context_summary")
    assert subtitle == container.get("context_line")
    assert kicker
    assert footer
    assert 3 <= len(rows) <= 5

    seen_row_ids: set[int] = set()
    for row in rows:
        has_market = row.get("market_id") is not None
        has_event = row.get("event_id") is not None
        assert has_market != has_event, f"{slug} row must set market_id XOR event_id: {row}"
        base_id = int(row["market_id"] if has_market else row["event_id"])
        assert base_id > 0
        row_id = int(row["outcome_id"]) if row.get("outcome_id") is not None else base_id
        assert row_id > 0
        assert row_id not in seen_row_ids, f"{slug} duplicate row_id {row_id}"
        seen_row_ids.add(row_id)
        prob = float(row["probability"])
        assert 0.0 < prob < 1.0
        label = str(row.get("label") or "").strip()
        assert label
        assert not FORBIDDEN_READER_COPY_RE.search(label)

    for text_field in (title, subtitle, kicker, footer):
        assert not FORBIDDEN_READER_COPY_RE.search(text_field), f"{slug} banned copy in: {text_field}"


@pytest.mark.asyncio
async def test_held_container_candidates_12_and_13_eval_packets() -> None:
    """Verify #12 (84th Golden Globes) and #13 (CFP Selected Field) eval packets and hold reasons."""
    # #12: 84th Golden Globes — held enabled=false in data/containers/; its active categories pass ceremony_award_categories
    gg_packet = json.loads(
        (CANDIDATES_DIR / "roundup-awards-84th-golden-globe-awards-rows.json").read_text()
    )
    gg_prod = rc.ROUNDUP_PRODUCERS["roundup-awards-84th-golden-globe-awards"]
    assert gg_prod.enabled is not None and gg_prod.enabled() is False

    gg_slate_defn = {
        "slug": "roundup-golden-globes-slate-eval",
        "name": "84th Golden Globe Awards — active categories",
        "kind": "roundup",
        "membership": "computed-produced",
        "category": "culture",
        "section_title": "Active categories",
        "footer": "Single-winner 84th Golden Globe Awards categories",
        "relations": ["same_event", "sibling"],
        "level": "member",
        "rule": {
            "producer": "ceremony_award_categories",
            "ceremony": "golden_globes",
            "min_categories": 3,
            "max_card_rows": 5,
            "min_volume_24h": 100.0,
        },
    }
    gg_slate_prod = build_ceremony_award_categories_producer(gg_slate_defn)
    gg_members = await produce_ceremony_award_categories(
        gg_packet["input_markets"],
        rule=gg_slate_prod.rule,
        now=_eval_now_from_packet(gg_packet),
    )
    assert not isinstance(gg_members, rc.RoundupRefusal)
    gg_member_ids = [int(m["id"]) for m in gg_members.members]
    assert set(gg_member_ids) == set(gg_packet["expected_member_ids"])
    assert not (set(gg_packet["excluded_ids"]) & set(gg_member_ids))

    # #13: CFP Selected Field 2026 — calendar-gated Selection Sunday (Dec 6) successor; refuses pre-Selection-Sunday
    cfp_packet = json.loads(
        (CANDIDATES_DIR / "roundup-cfp-selected-field-2026-rows.json").read_text()
    )
    cfp_prod = rc.ROUNDUP_PRODUCERS["roundup-cfp-selected-field-2026"]
    assert cfp_prod.enabled is not None and cfp_prod.enabled() is False

    cfp_defn = json.loads(
        (CONTAINERS_DIR / "roundup-cfp-selected-field-2026.json").read_text()
    )
    live_markets = {
        int(k): v for k, v in cfp_packet["live_pre_selection_markets"].items()
    }
    pre_res = select_field_selection(live_markets, definition=cfp_defn)
    assert isinstance(pre_res, rc.RoundupRefusal)
    assert cfp_packet["expected_live_refusal"] in str(pre_res.reasons)
