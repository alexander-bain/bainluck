"""Tests for #13544 / #13703 split-set gate, template-only fill, and staged records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import app.utils.discover_fun_scout as dfs
from app.tasks.discover_fun_scout import (
    build_scout_nightly_artifact,
    format_scout_nightly_comment_markdown,
)
from app.utils.discover_fun_scout import (
    SCOUT_PREFERRED_MIN_MEMBERS,
    ScoutMarketRow,
    ScoutProposedSet,
    ScoutTaggedMarket,
    build_scout_rule_file_definition,
    detect_scout_split_set,
    fill_missing_scout_members,
    run_nightly_fun_scout,
    trim_scout_split_set,
    validate_scout_proposed_set,
)
from app.utils.discover_fun_tags import FunMarketEntry

FROZEN_NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[2]
DECK1_PATH = REPO_ROOT / "backend" / "data" / "discover" / "fun_scout_blind_40_deck_2026_11_23.json"
DECK2_PATH = REPO_ROOT / "backend" / "data" / "discover" / "fun_scout_blind_40_deck_v2_2026_11_23.json"
SNAPSHOT_PATH = REPO_ROOT / "backend" / "data" / "discover" / "fun-scout-benchmark-2026-11-19.json"

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


DECK1_EXPECTED_FLAGGED: dict[str, tuple[str, str, int]] = {
    "blind-01": ("template_suffix_split", "cast", 2),
    "blind-03": ("title_subject_split", "moon", 3),
    "blind-05": ("title_subject_split", "grammy", 3),
    "blind-16": ("platform_brand_split", "rotten tomatoes", 2),
    "blind-21": ("platform_brand_split", "spotify", 2),
    "blind-23": ("series_prefix_split", "taylor swift", 2),
    "blind-28": ("title_subject_split", "data", 2),
    "blind-31": ("question_stem_split", "which movie has", 2),
    "blind-39": ("show_season_split", "the voice", 2),
}


def _load_cards(path: Path) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {card["card_id"]: card for card in raw["cards"]}


def _deck_cards_by_id() -> dict[str, dict]:
    return _load_cards(DECK2_PATH)


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


def _snapshot_catalog() -> dict[int, ScoutMarketRow]:
    raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    out: dict[int, ScoutMarketRow] = {}
    for m in raw["markets"]:
        cat = str(m.get("category") or "culture").strip().lower()
        if cat in {"politics", "elections", "geopolitics", "government"}:
            cat = "culture"
        res_raw = m.get("resolution_date")
        res_dt = (
            datetime.fromisoformat(res_raw.replace("Z", "+00:00"))
            if isinstance(res_raw, str) and res_raw
            else None
        )
        mid = int(m["market_id"])
        out[mid] = ScoutMarketRow(
            market_id=mid,
            source=str(m.get("source") or "kalshi"),
            title=str(m.get("title") or ""),
            status=str(m.get("status") or "open"),
            category=cat,
            resolution_date=res_dt,
            volume=float(m.get("volume") or 0.0),
            volume_24h=float(m.get("volume_24h") or 2_500.0),
            canonical_market_key=m.get("canonical_market_key"),
            group_id=m.get("group_id"),
        )
    return out


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

    def test_deck1_expectations_and_long_awaited_releases_stays_clean(self):
        cards = _load_cards(DECK1_PATH)
        observed: dict[str, tuple[str, str, int]] = {}
        for cid, card in sorted(cards.items()):
            finding = detect_scout_split_set(card["title"], _members_for_card(card))
            if finding is not None:
                observed[cid] = (
                    finding.reason,
                    finding.shared_feature,
                    len(finding.coherent_indices),
                )

        assert observed == DECK1_EXPECTED_FLAGGED
        assert detect_scout_split_set(
            cards["blind-18"]["title"], _members_for_card(cards["blind-18"])
        ) is None
        assert len(cards["blind-18"]["members"]) == 6

    def test_validate_trims_or_rejects_split_sets_and_enforces_narrow_title_and_min_three(self):
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
            if validated is not None:
                assert len(validated.members) < len(members), cid
                assert len(validated.trimmed_members) >= 1, cid
                assert len(validated.members) >= 3, cid
            else:
                assert err is not None, cid

        # title_subject_split leaving >=3 members trims cleanly with original title.
        moon_card = cards["blind-33"]
        moon_members = _members_for_card(moon_card)
        v_moon, err_moon = validate_scout_proposed_set(
            ScoutProposedSet(
                slug="blind-33-trimmed",
                name=moon_card["title"],
                kicker="DISCOVER SET",
                category="culture",
                why_better_together="Three 2026 Moon landing markets track NASA and human missions back to the lunar surface.",
                look="bars",
                member_ids=tuple(m.market_id for m in moon_members),
            ),
            {m.market_id: m for m in moon_members},
            fill_missing_members=False,
            now=FROZEN_NOW,
        )
        assert err_moon is None and v_moon is not None
        assert len(v_moon.members) == 3
        assert len(v_moon.trimmed_members) == 1
        assert len(v_moon.trimmed_member_details) == 1
        assert detect_scout_split_set(v_moon.name, v_moon.members) is None

        # Non-title_subject_split (Spotify brand inside wide music title) is rejected without narrow name+why.
        music_card = cards["blind-05"]
        music_members = _members_for_card(music_card)
        music_catalog = {m.market_id: m for m in music_members}
        v_wide, err_wide = validate_scout_proposed_set(
            ScoutProposedSet(
                slug="blind-05-wide",
                name=music_card["title"],
                kicker="DISCOVER SET",
                category="culture",
                why_better_together="Top Spotify artist, top album and top US Spotify song crown streaming in 2026.",
                look="bars",
                member_ids=tuple(m.market_id for m in music_members),
            ),
            music_catalog,
            fill_missing_members=False,
            now=FROZEN_NOW,
        )
        assert v_wide is None
        assert err_wide == "split_set_needs_narrow_title:platform_brand_split:spotify"

        # With explicit narrow name + why for the surviving Spotify subset, it validates cleanly.
        v_narrow, err_narrow = validate_scout_proposed_set(
            ScoutProposedSet(
                slug="blind-05-spotify",
                name=music_card["title"],
                kicker="DISCOVER SET",
                category="culture",
                why_better_together="Top Spotify and Billboard artists lead music.",
                look="bars",
                member_ids=tuple(m.market_id for m in music_members),
                narrowed_name="Spotify's 2026 Leaders",
                narrowed_why_better_together="Top Spotify artist, album and US song markets show who owns streaming this year.",
            ),
            music_catalog,
            fill_missing_members=False,
            now=FROZEN_NOW,
        )
        assert err_narrow is None and v_narrow is not None
        assert v_narrow.name == "Spotify's 2026 Leaders"
        assert len(v_narrow.members) == 3
        assert v_narrow.trimmed_member_details[0]["title"] == "Billboard #1 Artist 2026"

        # Trimming a compound "A & B" title (AI Math & Data Centers -> Data Centers only) also requires narrow name+why.
        dc_rows = [
            _row(880001, "AI data center in space by...?", category="tech"),
            _row(880002, "Louisiana enacts data center moratorium by...?", category="tech"),
            _row(880003, "Ohio enacts data center moratorium by...?", category="tech"),
            _row(880004, "How many more Millennium Prize Problems will AI solve in 2026?", category="tech"),
        ]
        _, err_dc = validate_scout_proposed_set(
            ScoutProposedSet(
                slug="ai-math-dc",
                name="AI Math & Data Centers",
                kicker="TECH BETS",
                category="tech",
                why_better_together="Three data center markets trace orbital and state moratorium deadlines.",
                look="bars",
                member_ids=tuple(r.market_id for r in dc_rows),
            ),
            {r.market_id: r for r in dc_rows},
            fill_missing_members=False,
            now=FROZEN_NOW,
        )
        assert err_dc == "split_set_needs_narrow_title:title_subject_split:data"

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
    def test_snapshot_template_only_fill_blocks_four_bad_adds_and_keeps_five_good_ones(self, monkeypatch):
        cards2 = _deck_cards_by_id()
        cards1 = _load_cards(DECK1_PATH)
        snap_catalog = _snapshot_catalog()

        # Match Fable's harness condition: let volume, taste and still-ahead checks pass
        # so the template gate itself proves why bad adds are blocked.
        monkeypatch.setattr(dfs, "check_scout_member", lambda row, **kw: (row is not None, None))

        def _catalog_with(rows: list[ScoutMarketRow]) -> dict[int, ScoutMarketRow]:
            cat = dict(snap_catalog)
            for r in rows:
                cat[r.market_id] = r
            return cat

        # Bad Add #1: Taylor's Chart Year (Deck 2 blind-36) & Who Owns the Charts? (Deck 1 blind-23)
        for c in (cards2["blind-36"], cards1["blind-23"]):
            members = _members_for_card(c)
            kept, _, _ = trim_scout_split_set(c["title"], members)
            filled, added = fill_missing_scout_members(
                c["title"], "entertainment", "bars", kept, _catalog_with(members), now=FROZEN_NOW
            )
            assert added == []
            assert "Taylor Swift: Wedding Dress" not in {m.title for m in filled}

        # Bad Add #2: What 2026 Googled (blind-27) must NOT add Next Google Gemini Pro Model
        google_members = _members_for_card(cards2["blind-27"])
        filled_g, added_g = fill_missing_scout_members(
            cards2["blind-27"]["title"], "culture", "bars", google_members, _catalog_with(google_members), now=FROZEN_NOW
        )
        assert added_g == []
        assert not any("Gemini Pro Model" in m.title for m in filled_g)

        # Bad Add #3: Pure Long Shots (blind-26) trimmed Elon core must NOT fill net-worth/rich rows
        elon_members = _members_for_card(cards2["blind-26"])
        kept_e, _, _ = trim_scout_split_set(cards2["blind-26"]["title"], elon_members)
        filled_e, added_e = fill_missing_scout_members(
            cards2["blind-26"]["title"], "tech", "bars", kept_e, _catalog_with(elon_members), now=FROZEN_NOW
        )
        assert added_e == []
        assert not any("How rich will Elon Musk" in m.title or "net worth" in m.title.lower() for m in filled_e)

        # Bad Add #4: Will It Ever Come Out? (blind-28) must NOT add Stranger Things episode
        awaited_members = _members_for_card(cards2["blind-28"])
        filled_w, added_w = fill_missing_scout_members(
            cards2["blind-28"]["title"], "entertainment", "bars", awaited_members, _catalog_with(awaited_members), now=FROZEN_NOW
        )
        assert added_w == []
        assert not any('New "Stranger Things" episode' in m.title for m in filled_w)

        # Good Fills (all 5 template shapes survive against real snapshot):
        # 1) ": Cast" (+2)
        cast_members = _members_for_card(cards2["blind-10"])
        cast_core, _, _ = trim_scout_split_set(cards2["blind-10"]["title"], cast_members)
        filled_cast, added_cast = fill_missing_scout_members(
            cards2["blind-10"]["title"], "entertainment", "bars", cast_core, _catalog_with(cast_members), now=FROZEN_NOW
        )
        assert len(added_cast) == 2
        assert all(m.title.endswith(": Cast") for m in filled_cast)

        # 2) ": Headliners" (+1)
        head_members = _members_for_card(cards2["blind-38"])
        head_core, _, _ = trim_scout_split_set(cards2["blind-38"]["title"], head_members)
        filled_head, added_head = fill_missing_scout_members(
            cards2["blind-38"]["title"], "entertainment", "bars", head_core, _catalog_with(head_members), now=FROZEN_NOW
        )
        assert len(added_head) == 1
        assert filled_head[-1].title == "Boston Calling Music Festival 2027: Headliners"

        # 3) "Critics Choice Awards:" (+2)
        cca_members = _members_for_card(cards2["blind-39"])
        cca_core, _, _ = trim_scout_split_set(cards2["blind-39"]["title"], cca_members)
        filled_cca, added_cca = fill_missing_scout_members(
            cards2["blind-39"]["title"], "entertainment", "bars", cca_core, _catalog_with(cca_members), now=FROZEN_NOW
        )
        assert len(added_cca) == 2
        assert all(m.title.startswith("Critics Choice Awards:") for m in filled_cca)

        # 4) "Opening Weekend Box Office" (+1)
        box_members = _members_for_card(cards2["blind-15"])
        filled_box, added_box = fill_missing_scout_members(
            cards2["blind-15"]["title"], "entertainment", "bars", box_members, _catalog_with(box_members), now=FROZEN_NOW
        )
        assert len(added_box) == 1
        assert "Opening Weekend Box Office" in filled_box[-1].title

        # 5) "The Voice Season 30" (+1)
        voice_members = _members_for_card(cards2["blind-06"])
        voice_core, _, _ = trim_scout_split_set(cards2["blind-06"]["title"], voice_members)
        filled_voice, added_voice = fill_missing_scout_members(
            cards2["blind-06"]["title"], "entertainment", "bars", voice_core, _catalog_with(voice_members), now=FROZEN_NOW
        )
        assert len(added_voice) == 1
        assert "The Voice Season 30" in filled_voice[-1].title

    def test_trim_below_three_refuses_without_fill_rescue_while_template_fill_works_above_min(self):
        cards = _deck_cards_by_id()
        cover_members = _members_for_card(cards["blind-32"])
        extra_cover_gq = _row(990020, "GQ 2026: Cover model", category="culture", volume=45_000)
        extra_cover_elle = _row(990021, "Elle 2026: Cover model", category="culture", volume=42_000)
        catalog_cover = {m.market_id: m for m in (*cover_members, extra_cover_gq, extra_cover_elle)}

        # Trimming blind-32 leaves 2 members (<3): refused immediately without fill rescue.
        proposal_trim_2 = ScoutProposedSet(
            slug="who-makes-the-cover",
            name="Cover Models of the Year",
            kicker="MAGAZINE COVERS",
            category="culture",
            why_better_together="Vogue and Sports Illustrated cover models show who owns the spotlight.",
            look="bars",
            member_ids=tuple(m.market_id for m in cover_members),
            narrowed_name="Cover Models of the Year",
            narrowed_why_better_together="Vogue, GQ, Elle and Sports Illustrated cover models.",
        )
        validated_2, err_2 = validate_scout_proposed_set(proposal_trim_2, catalog_cover, now=FROZEN_NOW)
        assert validated_2 is None
        assert err_2 is not None and err_2.startswith("split_set_too_small_after_trim:")

        # Same template with 3 existing Cover Model members fills +1 from catalog cleanly.
        clean_cover_3 = [m for m in cover_members if "Cover model" in m.title or "Cover Models" in m.title] + [extra_cover_gq]
        validated_3, err_3 = validate_scout_proposed_set(
            ScoutProposedSet(
                slug="cover-models-clean-3",
                name="Magazine Cover Models 2026",
                kicker="MAGAZINE COVERS",
                category="culture",
                why_better_together="Magazine cover model markets trace Vogue, GQ and Sports Illustrated picks.",
                look="bars",
                member_ids=tuple(m.market_id for m in clean_cover_3),
            ),
            catalog_cover,
            now=FROZEN_NOW,
        )
        assert err_3 is None and validated_3 is not None
        assert len(validated_3.members) == SCOUT_PREFERRED_MIN_MEMBERS
        assert validated_3.added_member_ids == (990021,)
        assert validated_3.added_members == (
            {
                "market_id": 990021,
                "title": "Elle 2026: Cover model",
                "reason": "template_suffix:cover model",
            },
        )

    def test_persists_trimmed_and_added_members_in_staged_record_and_morning_post(self):
        cards = _deck_cards_by_id()
        moon_members = _members_for_card(cards["blind-33"])  # 3 Moon + 1 Mars outlier
        cast_cards = _members_for_card(cards["blind-10"])
        cast_three = [m for m in cast_cards if m.title.endswith(": Cast")] + [
            _row(990041, "X-Men: Cast", category="entertainment", volume=85_000)
        ]
        extra_cast = _row(990042, "The White Lotus S4: Cast", category="entertainment", volume=75_000)
        all_markets = [*moon_members, *cast_three, extra_cast]

        pretagged = (
            [
                ScoutTaggedMarket(market_id=m.market_id, fun_group="space-and-film", reason="Curated")
                for m in all_markets
            ],
            0.01,
        )
        set_payload = json.dumps(
            {
                "sets": [
                    {
                        "slug": "back-to-the-moon",
                        "name": "Back to the Moon",
                        "kicker": "SPACE RACE",
                        "category": "science",
                        "why_better_together": "NASA and commercial moon landing deadlines test whether humans return to the lunar surface.",
                        "look": "bars",
                        "selector_kind": "fun_tag",
                        "member_ids": [m.market_id for m in moon_members],
                    },
                    {
                        "slug": "next-big-cast",
                        "name": "Who Gets Cast?",
                        "kicker": "CASTING",
                        "category": "entertainment",
                        "why_better_together": "Major blockbuster casting markets track Avengers, Miami Vice and X-Men leads.",
                        "look": "bars",
                        "selector_kind": "fun_tag",
                        "member_ids": [m.market_id for m in cast_three],
                    },
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
        res = run_nightly_fun_scout(
            all_markets,
            [],
            openai_client=SimpleNamespace(),
            anthropic_client=anthropic_client,
            approved_examples=[
                FunMarketEntry(
                    market_id=moon_members[0].market_id,
                    title=moon_members[0].title,
                    fun_bucket="odd",
                    discover_category="science",
                    sub_tags=("space",),
                )
            ],
            pretagged=pretagged,
            now=FROZEN_NOW,
        )
        assert len(res["validated_sets"]) == 2
        v_moon, v_cast = res["validated_sets"]
        assert len(v_moon.trimmed_member_details) == 1
        assert len(v_cast.added_members) == 1 and v_cast.added_members[0]["market_id"] == 990042

        rule_moon = build_scout_rule_file_definition(v_moon, model_used="claude", created_at=FROZEN_NOW)
        assert len(rule_moon["scout"]["trimmed_members"]) == 1
        assert rule_moon["scout"]["trimmed_members"][0]["title"].startswith("Will a humanoid robot walk on Mars")

        artifact = build_scout_nightly_artifact(res, run_now=FROZEN_NOW, max_new_per_day=10)
        assert len(artifact["staged_sets"][0]["trimmed_members"]) == 1
        assert artifact["staged_sets"][1]["added_members"] == [
            {
                "market_id": 990042,
                "title": "The White Lotus S4: Cast",
                "reason": "template_suffix:cast",
            }
        ]
        md = format_scout_nightly_comment_markdown(artifact)
        assert "Split-set gate trimmed" in md
        assert "Missing-member fill added" in md
        assert "The White Lotus S4: Cast" in md
        assert "Will a humanoid robot walk on Mars before a human does?" in md
