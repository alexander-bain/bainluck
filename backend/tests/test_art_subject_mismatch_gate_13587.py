"""Tests for #13587: portrait/subject mismatch gate in container machinery."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
    SubjectArtResolver,
    art_subject_mismatch_reason,
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import clear_fun_markets_cache

NOW = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)


def test_resolver_matches_cast_actor_prefix_only_when_actor_is_verified() -> None:
    resolver = SubjectArtResolver()
    benedict = resolver.resolve("Benedict Cumberbatch as Doctor Strange?", allow_team_lookup=False)
    assert benedict["kind"] == "person"
    assert "Benedict Cumberbatch TMDB portrait" in str(benedict.get("detail") or "")
    assert str(benedict.get("url") or "").startswith("https://image.tmdb.org/")

    jackman = resolver.resolve("Hugh Jackman as Wolverine?", allow_team_lookup=False)
    assert jackman["url"] is None
    assert jackman["kind"] == "monogram"
    assert "Cumberbatch" not in str(jackman.get("detail") or "")


def test_art_subject_mismatch_gate_allows_artist_work_and_stage_names_but_blocks_wrong_face() -> None:
    resolver = SubjectArtResolver()
    benedict = resolver.resolve("Benedict Cumberbatch", allow_team_lookup=False)
    assert art_subject_mismatch_reason(
        ["Hugh Jackman as Wolverine?"], benedict, resolver=resolver
    )

    mariah = resolver.resolve("Mariah Carey", allow_team_lookup=False)
    assert (
        art_subject_mismatch_reason(
            ["Rank 1 to 2", '"All I Want for Christmas Is You" in the Hot 100\'s top 2 on Dec 19'],
            mariah,
            resolver=resolver,
        )
        is None
    )

    kevin = resolver.resolve("Kevin Parker", allow_team_lookup=False)
    assert art_subject_mismatch_reason(["Tame Impala"], kevin, resolver=resolver) is None

    joe = resolver.resolve("Joe Keery", allow_team_lookup=False)
    assert (
        art_subject_mismatch_reason(["End of Beginning – Djo"], joe, resolver=resolver)
        is None
    )

    haaland = resolver.resolve("Erling Braut Haaland", allow_team_lookup=False)
    assert (
        art_subject_mismatch_reason(["Erling Braut Haaland"], haaland, resolver=resolver)
        is None
    )


@pytest.mark.asyncio
async def test_cast_delayed_cancelled_never_shows_cumberbatch_on_hugh_jackman_row() -> None:
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    defn = load_machinery_definition(paths_by_slug["machinery-cast-delayed-cancelled"])
    markets = [
        {
            "id": 109214,
            "name": "Avengers: Doomsday: Cast",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 90000.0,
            "outcomes": [
                {"id": 10921401, "name": "Hugh Jackman as Wolverine?", "probability": 0.94},
                {"id": 10921402, "name": "Benedict Cumberbatch as Doctor Strange?", "probability": 0.60},
            ],
        },
        {
            "id": 59172754,
            "name": "Dune vs Avengers: Highest Rotten Tomatoes Score",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 80000.0,
            "outcomes": [{"id": 5917275401, "name": "Dune: Part Three", "probability": 0.83}],
        },
        {
            "id": 108275,
            "name": "Will there be an announcement that The Simpsons is ending?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 70000.0,
            "outcomes": [{"id": 10827501, "name": "Yes", "probability": 0.67}],
        },
        {
            "id": 56867561,
            "name": "Avengers: Secret Wars delayed?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 65000.0,
            "outcomes": [{"id": 5686756101, "name": "Yes", "probability": 0.50}],
        },
        {
            "id": 108506,
            "name": "Miles Morales cast",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 60000.0,
            "outcomes": [{"id": 10850601, "name": "Caleb McLaughlin", "probability": 0.19}],
        },
        {
            "id": 108275,
            "name": "Will there be an announcement that The Simpsons is ending?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 55000.0,
            "outcomes": [{"id": 10827501, "name": "Yes", "probability": 0.67}],
        },
    ]

    res = await produce_container_machinery({"markets": markets, "teams": []}, defn, now=NOW)
    sec_items = res.sections[0]["visual_block"]["items"]
    jackman_item = next(it for it in sec_items if int(it["market_id"]) == 109214)
    jackman_art = jackman_item["outcomes"][0]["art"]
    assert jackman_art["url"] is None
    assert jackman_art["kind"] == "monogram"
    assert jackman_art["initials"] == "HJ"
    assert "Cumberbatch" not in str(jackman_art.get("detail") or "")

    card_row0_art = res.machinery_card["rows"][0]["art"]
    assert card_row0_art["url"] is None
    assert card_row0_art["kind"] == "monogram"
    assert "Cumberbatch" not in str(card_row0_art.get("detail") or "")


@pytest.mark.asyncio
async def test_cast_delayed_cancelled_allows_cumberbatch_when_he_leads() -> None:
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    defn = load_machinery_definition(paths_by_slug["machinery-cast-delayed-cancelled"])
    markets = [
        {
            "id": 109214,
            "name": "Avengers: Doomsday: Cast",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 90000.0,
            "outcomes": [{"id": 10921402, "name": "Benedict Cumberbatch as Doctor Strange?", "probability": 0.94}],
        },
        {
            "id": 59172754,
            "name": "Dune vs Avengers: Highest Rotten Tomatoes Score",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 80000.0,
            "outcomes": [{"id": 5917275401, "name": "Dune: Part Three", "probability": 0.83}],
        },
        {
            "id": 108275,
            "name": "Will there be an announcement that The Simpsons is ending?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 70000.0,
            "outcomes": [{"id": 10827501, "name": "Yes", "probability": 0.67}],
        },
    ]

    res = await produce_container_machinery({"markets": markets, "teams": []}, defn, now=NOW)
    card_row0_art = res.machinery_card["rows"][0]["art"]
    assert "Benedict Cumberbatch TMDB portrait" in str(card_row0_art.get("detail") or "")
    assert str(card_row0_art.get("url") or "").startswith("https://image.tmdb.org/")


@pytest.mark.asyncio
async def test_set_page_art_gate_drops_mismatched_explicit_person_portrait(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.utils.discover_fun_tags as dft

    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    defn = load_machinery_definition(paths_by_slug["machinery-cast-delayed-cancelled"])

    # Simulate a stale/wrong per-market art_subject hint on a named contender row.
    orig_art_subj = dft.fun_market_art_subject

    def fake_art_subj(market_id: int, *, sub_tag: str | None = None) -> str | None:
        if int(market_id) == 109214:
            return "Benedict Cumberbatch"
        return orig_art_subj(market_id, sub_tag=sub_tag)

    monkeypatch.setattr(dft, "fun_market_art_subject", fake_art_subj)
    markets = [
        {
            "id": 109214,
            "name": "Avengers: Doomsday: Cast",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 90000.0,
            "outcomes": [{"id": 10921401, "name": "Hugh Jackman as Wolverine?", "probability": 0.94}],
        },
        {
            "id": 108506,
            "name": "Miles Morales cast",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 60000.0,
            "outcomes": [{"id": 10850601, "name": "Caleb McLaughlin", "probability": 0.19}],
        },
        {
            "id": 108275,
            "name": "Will there be an announcement that The Simpsons is ending?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 55000.0,
            "outcomes": [{"id": 10827501, "name": "Yes", "probability": 0.67}],
        },
    ]

    res = await produce_container_machinery({"markets": markets, "teams": []}, defn, now=NOW)
    item = next(
        it for it in res.sections[0]["visual_block"]["items"] if int(it["market_id"]) == 109214
    )
    assert item["outcomes"][0]["art"]["url"] is None
    assert item["outcomes"][0]["art"]["kind"] == "monogram"
