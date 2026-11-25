"""Tests for #13544 Deck 2 split-set gate and <4-member missing-member lookup."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.utils.discover_fun_scout import (
    SCOUT_PREFERRED_MIN_MEMBERS,
    ScoutMarketRow,
    ScoutProposedSet,
    ScoutTaggedMarket,
    detect_scout_split_set,
    fill_missing_scout_members,
    run_nightly_fun_scout,
    trim_scout_split_set,
    validate_scout_proposed_set,
)
from app.utils.discover_fun_tags import FunMarketEntry

FROZEN_NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[2]
DECK2_PATH = REPO_ROOT / "backend" / "data" / "discover" / "fun_scout_blind_40_deck_v2_2026_11_23.json"

SPLIT_FIX_DROP_IDS: tuple[str, ...] = (
    "blind-05",  # music-number-ones-2026: 3 Spotify + 1 Billboard
    "blind-06",  # finale-week: 2 The Voice + 2 unrelated
    "blind-10",  # who-gets-cast: 2 : Cast + 1 actor?
    "blind-12",  # who-sells-records: 3 Album sales + 1 release song
    "blind-26",  # pure-long-shots: 2 Elon Musk + 2 non-Elon
    "blind-29",  # box-office-2026: biggest + 3rd biggest missing 2nd + outlier
    "blind-32",  # who-makes-the-cover: 2 cover models + SNL host
    "blind-33",  # back-to-the-moon: 3 Moon + 1 Mars
    "blind-36",  # taylor-chart-year: 2 Taylor Swift + 2 non-Taylor
    "blind-38",  # festival-headliners-2027: 2 Headliners + Coachella
    "blind-39",  # tv-winners-season: 2 Critics Choice Awards + 2 others
)

KEEP_CARD_IDS: tuple[str, ...] = (
    "blind-01",
    "blind-02",
    "blind-03",
    "blind-04",
    "blind-07",
    "blind-08",
    "blind-09",
    "blind-11",
    "blind-14",
    "blind-15",
    "blind-16",
    "blind-17",
    "blind-18",
    "blind-19",
    "blind-20",
    "blind-21",
    "blind-22",
    "blind-23",
    "blind-24",
    "blind-27",
    "blind-30",
    "blind-31",
    "blind-34",
    "blind-35",
    "blind-37",
    "blind-40",
)


def _row(
    mid: int,
    title: str,
    *,
    category: str = "culture",
    volume: float = 50_000.0,
    source: str = "kalshi",
) -> ScoutMarketRow:
    return ScoutMarketRow(
        market_id=mid,
        source=source,
        title=title,
        status="open",
        category=category,
        resolution_date=datetime(2027, 6, 1, tzinfo=timezone.utc),
        volume=volume,
        volume_24h=2_500.0,
        canonical_market_key=None,
    )


def _deck_cards_by_id() -> dict[str, dict]:
    raw = json.loads(DECK2_PATH.read_text(encoding="utf-8"))
    return {card["card_id"]: card for card in raw["cards"]}


def _members_for_card(card: dict) -> list[ScoutMarketRow]:
    cat = str(card.get("category") or "culture").strip().lower()
    if cat in {"politics", "elections", "geopolitics", "government"}:
        cat = "culture"
    return [
        _row(
            int(m["market_id"]),
            str(m["title"]),
            category=cat,
            source=str(m.get("source") or "kalshi"),
        )
        for m in card["members"]
    ]


class TestDeck2SplitSetGate13544:
    def test_detects_all_11_graded_split_sets_and_quiet_on_all_26_keeps(self):
        cards = _deck_cards_by_id()

        for cid in SPLIT_FIX_DROP_IDS:
            card = cards[cid]
            finding = detect_scout_split_set(card["title"], _members_for_card(card))
            assert finding is not None, f"{cid} ({card['title']}) must trigger split-set gate"
            assert len(finding.coherent_indices) >= 2, cid
            assert len(finding.outlier_indices) >= 1, cid

        for cid in KEEP_CARD_IDS:
            card = cards[cid]
            finding = detect_scout_split_set(card["title"], _members_for_card(card))
            assert finding is None, f"Keep card {cid} ({card['title']}) triggered false positive: {finding}"

    def test_validate_trims_or_rejects_all_11_graded_split_sets(self):
        cards = _deck_cards_by_id()

        for cid in SPLIT_FIX_DROP_IDS:
            card = cards[cid]
            members = _members_for_card(card)
            catalog = {m.market_id: m for m in members}
            proposal = ScoutProposedSet(
                slug=cid,
                name=card["title"],
                kicker="DISCOVER SET",
                category="entertainment" if card.get("category") in {"politics", "economics"} else str(card.get("category") or "culture"),
                why_better_together=str(card.get("summary") or card["title"]),
                look=str(card.get("look") or "bars"),
                member_ids=tuple(m.market_id for m in members),
            )
            validated, err = validate_scout_proposed_set(
                proposal,
                catalog,
                fill_missing_members=False,
                now=FROZEN_NOW,
            )
            # With full original summary, either rejected (core < 3, skipped ordinal,
            # or stale blurb naming trimmed outlier) or trimmed strictly narrower.
            if validated is not None:
                assert len(validated.members) < len(members), cid
                assert len(validated.trimmed_members) >= 1, cid
            else:
                assert err is not None, cid

        # When blurb stays faithful to the narrower core, 3-of-4 split sets trim cleanly
        for cid, clean_blurb in (
            ("blind-33", "Three 2026 Moon landing markets track NASA and human missions back to the lunar surface."),
            ("blind-05", "Top Spotify artist, top album and top US Spotify song crown streaming in 2026."),
        ):
            card = cards[cid]
            members = _members_for_card(card)
            catalog = {m.market_id: m for m in members}
            proposal = ScoutProposedSet(
                slug=f"{cid}-trimmed",
                name=card["title"],
                kicker="DISCOVER SET",
                category="culture",
                why_better_together=clean_blurb,
                look="bars",
                member_ids=tuple(m.market_id for m in members),
            )
            validated, err = validate_scout_proposed_set(
                proposal,
                catalog,
                fill_missing_members=False,
                now=FROZEN_NOW,
            )
            assert err is None and validated is not None, (cid, err)
            assert len(validated.members) == 3, cid
            assert len(validated.trimmed_members) == 1, cid
            assert detect_scout_split_set(validated.name, validated.members) is None

    def test_trim_scout_split_set_exposes_narrower_core_and_outliers(self):
        cards = _deck_cards_by_id()
        taylor = cards["blind-36"]
        kept, trimmed, finding = trim_scout_split_set(
            taylor["title"], _members_for_card(taylor)
        )
        assert finding is not None and finding.trimmable is True
        assert [m.title for m in kept] == [
            "Taylor Swift · Weeks at #1 on the Billboard 200 in 2026",
            "Taylor Swift: Total weeks at #1 on the Billboard Hot 100 in 2026",
        ]
        assert len(trimmed) == 2

        box_office = cards["blind-29"]
        kept_bo, trimmed_bo, finding_bo = trim_scout_split_set(
            box_office["title"], _members_for_card(box_office)
        )
        assert finding_bo is not None and finding_bo.trimmable is False
        assert kept_bo == []
        assert len(trimmed_bo) == 4


class TestMissingMemberLookupBelowFour13544:
    def test_fills_three_member_google_search_set_from_catalog_without_duplicates(self):
        cards = _deck_cards_by_id()
        google_members = _members_for_card(cards["blind-27"])
        assert len(google_members) == 3

        extra_actors = _row(990001, "Google's Year in Search 2026 Global - Actors: #1 search", category="culture", volume=80_000)
        extra_movies_twin = _row(990002, "Google's Year in Search 2026 Global - Movies: #1 search", source="polymarket", category="culture", volume=40_000)
        extra_low_vol = _row(990003, "Google's Year in Search 2026 Global - Athletes: #1 search", category="culture", volume=500)
        unrelated = _row(990004, "Will GTA VI be delayed past 2027?", category="gaming", volume=120_000)

        catalog = {
            m.market_id: m
            for m in (*google_members, extra_actors, extra_movies_twin, extra_low_vol, unrelated)
        }
        proposal = ScoutProposedSet(
            slug="google-year-in-search",
            name="What 2026 Googled",
            kicker="YEAR IN SEARCH",
            category="culture",
            why_better_together="Global #1 searches across people and movies trace what 2026 searched most.",
            look="bars",
            member_ids=tuple(m.market_id for m in google_members),
        )
        validated, err = validate_scout_proposed_set(
            proposal,
            catalog,
            now=FROZEN_NOW,
        )
        assert err is None and validated is not None
        assert len(validated.members) >= SCOUT_PREFERRED_MIN_MEMBERS
        ids = {m.market_id for m in validated.members}
        assert 990001 in ids
        assert 990002 not in ids  # twin deduped
        assert 990003 not in ids  # below volume bar
        assert 990004 not in ids  # unrelated
        assert 990001 in validated.added_member_ids

    def test_fills_awaited_three_member_set_and_recovers_trimmed_two_member_core(self):
        cards = _deck_cards_by_id()
        awaited_members = _members_for_card(cards["blind-28"])
        extra_shrek = _row(990010, "When will Drake release a new album?", category="entertainment", volume=65_000)
        extra_hollow = _row(990011, "Will Silksong be announced before 2027?", category="gaming", volume=55_000)
        catalog_awaited = {m.market_id: m for m in (*awaited_members, extra_shrek, extra_hollow)}

        enriched, added = fill_missing_scout_members(
            "Will It Ever Come Out?",
            "entertainment",
            "bars",
            awaited_members,
            catalog_awaited,
            now=FROZEN_NOW,
        )
        assert len(enriched) >= 4
        assert len(added) >= 1

        # Trimmed 2-member cover-model core recovers via two extra Cover Model catalog rows
        cover_members = _members_for_card(cards["blind-32"])
        extra_cover_gq = _row(990020, "GQ 2026: Cover model", category="culture", volume=45_000)
        extra_cover_elle = _row(990021, "Elle 2026: Cover model", category="culture", volume=42_000)
        catalog_cover = {m.market_id: m for m in (*cover_members, extra_cover_gq, extra_cover_elle)}

        proposal = ScoutProposedSet(
            slug="who-makes-the-cover",
            name="Cover Models of the Year",
            kicker="MAGAZINE COVERS",
            category="culture",
            why_better_together="Major magazine cover model markets track who owns this year's spotlight.",
            look="bars",
            member_ids=tuple(m.market_id for m in cover_members),
        )
        validated, err = validate_scout_proposed_set(
            proposal,
            catalog_cover,
            now=FROZEN_NOW,
        )
        assert err is None and validated is not None
        assert len(validated.members) == 4
        assert {m.market_id for m in validated.members} >= {990020, 990021}
        assert len(validated.trimmed_members) == 1
        assert detect_scout_split_set(validated.name, validated.members) is None

    def test_run_nightly_fun_scout_passes_tagged_by_id_for_missing_member_fill(self):
        cards = _deck_cards_by_id()
        google_members = _members_for_card(cards["blind-27"])
        extra_search = _row(990030, "#1 Searched TV Show on Google 2026?", category="culture", volume=90_000)
        markets = [*google_members, extra_search]

        pretagged = (
            [
                ScoutTaggedMarket(market_id=m.market_id, fun_group="year-end", reason="Google top search")
                for m in markets
            ],
            0.01,
        )
        set_payload = json.dumps(
            {
                "sets": [
                    {
                        "slug": "google-search-2026",
                        "name": "What 2026 Googled",
                        "kicker": "YEAR IN SEARCH",
                        "category": "culture",
                        "why_better_together": "Searched people, movies and TV shows capture what the world looked up on Google in 2026.",
                        "look": "bars",
                        "selector_kind": "fun_tag",
                        "member_ids": [m.market_id for m in google_members],
                    }
                ]
            }
        )
        anthropic_client = SimpleNamespace(
            messages=SimpleNamespace(
                create=lambda **_: SimpleNamespace(
                    content=[SimpleNamespace(text=set_payload)],
                    usage=SimpleNamespace(input_tokens=100, output_tokens=50),
                )
            )
        )
        openai_client = SimpleNamespace()
        approved = [
            FunMarketEntry(
                market_id=google_members[0].market_id,
                title=google_members[0].title,
                fun_bucket="odd",
                discover_category="culture",
                sub_tags=("year-end",),
            )
        ]

        res = run_nightly_fun_scout(
            markets,
            [],
            openai_client=openai_client,
            anthropic_client=anthropic_client,
            approved_examples=approved,
            pretagged=pretagged,
            now=FROZEN_NOW,
        )
        assert len(res["validated_sets"]) == 1
        assert len(res["validated_sets"][0].members) == 4
        assert 990030 in {m.market_id for m in res["validated_sets"][0].members}
