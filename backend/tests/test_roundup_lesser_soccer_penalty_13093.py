"""Tests for #13093 part (b): lesser soccer league penalty on multi-row round-up cards."""

from __future__ import annotations

import copy
from typing import Any

from app.utils.futures_highlights import (
    MINOR_LEAGUE_PENALTY,
    OBSCURE_SOCCER_PENALTY,
)
from app.utils.roundup_containers import (
    _is_roundup_bundle_card,
    _roundup_lesser_soccer_penalty,
    ensure_optional_roundup_candidates,
    insert_roundup_feed_items,
)


def _deck(scores: list[float]) -> list[dict[str, Any]]:
    return [
        {
            "type": "futures",
            "score": sc,
            "_rank_score": sc,
            "data": {
                "id": 1000 + i,
                "name": f"Control Market {i}",
                "llm_sport_category": "politics",
                "outcomes": [{"id": 1, "name": "Yes", "probability": 0.5}],
            },
        }
        for i, sc in enumerate(scores)
    ]


def _roundup_card(
    slug: str,
    title: str,
    *,
    tag: str = "SOCCER",
    kicker: str = "SOCCER",
    sibling: bool = True,
    score: float = 0.0,
    child_names: list[str] | None = None,
    child_cat: str = "soccer",
) -> dict[str, Any]:
    names = child_names or [title]
    return {
        "type": "bundle",
        "score": score,
        "reason": title,
        "headline": title,
        "data": {
            "id": f"roundup:{slug}",
            "title": title,
            "kind": "roundup",
            "story_key": f"roundup:{slug}",
            "item_count": len(names),
            "member_ids": [9000 + i for i in range(len(names))],
            "items": [
                {
                    "type": "futures",
                    "score": score,
                    "reason": n,
                    "headline": n,
                    "data": {
                        "id": 9000 + i,
                        "name": n,
                        "llm_sport_category": child_cat,
                    },
                }
                for i, n in enumerate(names)
            ],
            "collection_ref": {
                "slug": slug,
                "href": f"/collections/{slug}",
                "name": title,
                "revision": 1,
                "collection_count": len(names),
            },
            "roundup": {
                "kicker": kicker,
                "tag": tag,
                "footer": "Each row is its own market.",
                "rows": [{"label": n, "probability": 0.5} for n in names],
                "relations": ["same_measure", "sibling"] if sibling else ["same_window"],
                "level": "member",
            },
        },
    }


def test_roundup_lesser_soccer_penalty_matches_futures_highlights_constants() -> None:
    liga = _roundup_card(
        "liga-profesional-relegation-2026",
        "Which club will be relegated from the 2026 Liga Profesional (Argentina)?",
        child_names=[
            "Will Aldosivi be relegated from the 2026 Liga Profesional (Argentina)?",
            "Will Vélez Sarsfield be relegated from the 2026 Liga Profesional (Argentina)?",
        ],
    )
    assert _roundup_lesser_soccer_penalty(liga) == OBSCURE_SOCCER_PENALTY == -20

    eredivisie = _roundup_card(
        "eredivisie-title-2027",
        "Which club will win the Eredivisie in 2027?",
        child_names=["Eredivisie 2026-27 Champion: Ajax"],
    )
    assert _roundup_lesser_soccer_penalty(eredivisie) == MINOR_LEAGUE_PENALTY == -15

    # Top-tier soccer leagues stay unpenalized (e.g. Champions League, Premier League)
    top_tier = _roundup_card(
        "machinery-european-league-titles",
        "European Soccer League Title Races",
        child_names=[
            "English Premier League: 2026-27 Winner",
            "UEFA Champions League: 2027 Champion",
        ],
    )
    assert _roundup_lesser_soccer_penalty(top_tier) == 0

    # Batch 8 preview soccer card contains MLS/Europa League/Premier League/World Cup -> 0 penalty
    batch8_soccer = _roundup_card(
        "machinery-soccer-cups-and-relegation",
        "Soccer Cups & Relegation",
        kicker="SPORTS · SOCCER CUPS",
        child_names=[
            "UEFA Europa League Winner",
            "English Premier League: Team relegated?",
        ],
    )
    assert _roundup_lesser_soccer_penalty(batch8_soccer) == 0

    # Non-soccer card -> 0 penalty
    non_soccer = _roundup_card(
        "nhl-playoffs-2026-27",
        "Which team will make the 2026-27 NHL Playoffs?",
        tag="HOCKEY",
        kicker="HOCKEY",
        child_cat="hockey",
    )
    assert _roundup_lesser_soccer_penalty(non_soccer) == 0


def test_insert_roundup_feed_items_demotes_lesser_soccer_to_penalized_score_seat() -> None:
    scores = [95.0 - float(i) for i in range(45)]
    base_deck = _deck(scores)
    top_roundup = _roundup_card(
        "by-december-31",
        "By December 31",
        tag="POLITICS",
        kicker="TIMELINE",
        sibling=False,
        child_cat="politics",
    )
    liga = _roundup_card(
        "liga-profesional-relegation-2026",
        "Which club will be relegated from the 2026 Liga Profesional (Argentina)?",
    )
    nhl = _roundup_card(
        "nhl-playoffs-2026-27",
        "Which team will make the 2026-27 NHL Playoffs?",
        tag="HOCKEY",
        kicker="HOCKEY",
        child_cat="hockey",
    )
    # Without penalty, liga took seat ~13 (score ~82). With -20 penalty, score becomes 63-64
    # and seats behind all 66+ score cards, leaving top_roundup and nhl in page 1 unaffected.
    seated = insert_roundup_feed_items(
        copy.deepcopy(base_deck),
        [top_roundup, liga, nhl],
        seat_floor=10,
        page_window=20,
    )
    by_id = {
        it["data"]["id"]: (idx, it.get("score"))
        for idx, it in enumerate(seated)
        if _is_roundup_bundle_card(it)
    }
    assert by_id["roundup:by-december-31"][0] < 20
    assert by_id["roundup:nhl-playoffs-2026-27"][0] < 20
    liga_idx, liga_score = by_id["roundup:liga-profesional-relegation-2026"]
    assert liga_idx >= 30, f"Expected lesser soccer roundup demoted far below page 1, got idx={liga_idx}"
    assert liga_score <= 66.0, f"Expected -20 penalized score, got {liga_score}"
    # No item after liga_idx should carry a higher score than liga_score
    trailing_higher = [it.get("score") for it in seated[liga_idx + 1 :] if float(it.get("score") or 0.0) > liga_score]
    assert trailing_higher == [], trailing_higher


def test_splice_machinery_in_place_does_not_get_dragged_after_demoted_lesser_soccer() -> None:
    ensure_optional_roundup_candidates()
    scores = [95.0 - float(i) for i in range(45)]
    base_deck = _deck(scores)
    top_roundup = _roundup_card(
        "by-december-31",
        "By December 31",
        tag="POLITICS",
        kicker="TIMELINE",
        sibling=False,
        child_cat="politics",
    )
    liga = _roundup_card(
        "liga-profesional-relegation-2026",
        "Which club will be relegated from the 2026 Liga Profesional (Argentina)?",
    )
    seated_base = insert_roundup_feed_items(
        copy.deepcopy(base_deck),
        [top_roundup, liga],
        seat_floor=10,
        page_window=20,
    )
    machinery_card = _roundup_card(
        "machinery-white-christmas",
        "Pittsburgh is the likeliest white Christmas",
        tag="ODD",
        kicker="WEATHER",
        sibling=True,
        child_cat="weather",
    )
    spliced = insert_roundup_feed_items(
        copy.deepcopy(seated_base),
        [machinery_card],
        seat_floor=10,
        page_window=20,
        preserve_existing_roundups=True,
    )
    seats = {
        it["data"]["id"]: idx
        for idx, it in enumerate(spliced)
        if _is_roundup_bundle_card(it)
    }
    assert seats["roundup:by-december-31"] < 20
    assert seats["roundup:machinery-white-christmas"] < 20
    assert seats["roundup:liga-profesional-relegation-2026"] > 30
