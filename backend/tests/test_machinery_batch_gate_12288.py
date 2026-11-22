"""Unit & CI gate tests for #12288 Item 6 (`machinery_batch_gate` & CLI)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.container_machinery import (
    discover_machinery_candidate_paths,
    load_machinery_definition,
)
from app.utils.machinery_batch_gate import (
    MAX_HEADLINE_LINES_390PX,
    audit_picture_policy_for_definition,
    audit_public_assembly_for_definition,
    build_synthetic_snapshot_for_definition,
    check_machinery_wording,
    estimate_headline_lines_390px,
)
from scripts import check_machinery_batch_pr

NOW = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)


def _sample_public_definition(*, stage: str = "public", min_items: int = 3) -> dict:
    return {
        "slug": "machinery-long-shots",
        "stage": stage,
        "look": "bars",
        "membership": "computed-produced",
        "kind": "roundup",
        "relations": ["same_window", "sibling"],
        "level": "member",
        "kicker": "ODD · LONG SHOTS",
        "name": "Long shots",
        "category": "odd",
        "section_title": "Long shots",
        "footer": "",
        "rule": {
            "producer": "container_machinery",
            "refusal": "all-or-nothing",
            "materialize": "read-time",
            "card_rows": 3,
            "suppress_card_photo": True,
            "card_image_url": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ae/Milky_Way_Streaky_Bay_%28Unsplash%29.jpg/960px-Milky_Way_Streaky_Bay_%28Unsplash%29.jpg",
            "card_image_alt": "Star-filled night sky showing the Milky Way galaxy",
            "card_image_credit": "Thom Schneider (CC0 1.0 Public Domain, Wikimedia Commons)",
            "card_image_author": "Thom Schneider",
            "card_image_license": "CC0 1.0 Public Domain",
            "card_image_source_page": "https://commons.wikimedia.org/wiki/File:Milky_Way_Streaky_Bay_(Unsplash).jpg",
            "headline_predicate": "is the likeliest long shot",
            "sections": [
                {
                    "key": "long_shots",
                    "title": "Long shots",
                    "item_noun": "markets",
                    "note": "Long-shot outcomes priced under 25%.",
                    "atom_query": {
                        "kind": "markets",
                        "market_ids": [990001, 990002, 990003],
                        "shape": "binary",
                        "min_lifetime_volume": 100,
                        "min_items": min_items,
                        "max_items": 6,
                        "max_outcomes": 1,
                    },
                }
            ],
        },
    }


def _sample_market(mid: int, title: str, prob: float, *, volume: float | None = 5000.0) -> dict:
    res_iso = (NOW + timedelta(days=180)).isoformat()
    now_iso = NOW.isoformat()
    outs = [
        {"id": mid * 10 + 1, "name": "Yes", "probability": prob, "last_updated": now_iso},
        {"id": mid * 10 + 2, "name": "No", "probability": 1.0 - prob, "last_updated": now_iso},
    ]
    return {
        "id": mid,
        "name": title,
        "title": title,
        "status": "open",
        "source": "kalshi",
        "category": "odd",
        "llm_sport_category": "odd",
        "market_tier": 1,
        "volume": volume,
        "resolution_date": res_iso,
        "newest_outcome_updated_at": now_iso,
        "top_outcomes": outs,
        "outcomes": outs,
    }


def test_wording_doubled_word_across_label_and_answer() -> None:
    bad_card = {
        "slug": "machinery-pop-culture-oddities",
        "title": "Mariah Carey leads holiday charts at 45%",
        "rows": [
            {"name": '"All I Want for Christmas Is You" Hot 100 rank: Rank 11 or lower'},
            {"label": "Chart rank", "answer": "Rank 1 to 10"},
        ],
    }
    res = check_machinery_wording(bad_card)
    assert not res.ok
    rules = [e.rule for e in res.errors]
    assert rules.count("doubled_label_answer_word") == 2

    good_card = {
        "slug": "machinery-pop-culture-oddities",
        "title": "Mariah Carey leads holiday charts at 45%",
        "rows": [
            {"name": '"All I Want for Christmas Is You" Hot 100 rank on Dec 19: Rank 11 or lower'},
            {"name": "Best Game Direction: Grand Theft Auto VI"},
        ],
    }
    good_res = check_machinery_wording(good_card)
    assert good_res.ok, good_res.errors


def test_wording_repeated_name_in_single_row() -> None:
    bad_card = {
        "slug": "machinery-test",
        "title": "Clean headline at 50%",
        "rows": [
            {"name": "Trump on SNL: Trump"},
            {"name": "Grand Theft Auto VI for Best Game Direction: Grand Theft Auto VI"},
        ],
    }
    res = check_machinery_wording(bad_card)
    assert not res.ok
    repeated = [e for e in res.errors if e.rule == "repeated_name_in_row"]
    assert len(repeated) == 2

    good_card = {
        "slug": "machinery-cast-delayed-cancelled",
        "title": "Avengers cast leads 2026 at 96%",
        "rows": [
            {"name": "Dune vs Avengers score: Dune: Part Three"},
            {"name": "Avengers: Doomsday cast: Benedict Cumberbatch as Doctor Strange"},
        ],
    }
    good_res = check_machinery_wording(good_card)
    assert good_res.ok, good_res.errors


@pytest.mark.parametrize(
    "bad_text",
    [
        "Heavy trading lifts Apple to 95%",
        "The likeliest bet before December",
        "Bets point toward SpaceX",
        "Active betting on the Oscars",
        "A stale price remains on the card",
        "This question closes on Sunday",
        "Five questions on the docket",
    ],
)
def test_wording_banned_words_caught(bad_text: str) -> None:
    res = check_machinery_wording({"slug": "machinery-test", "title": bad_text, "rows": []})
    assert not res.ok
    assert any(e.rule == "banned_word" for e in res.errors)


def test_wording_banned_words_ignore_substrings_like_alphabet_or_better() -> None:
    clean = check_machinery_wording(
        {
            "slug": "machinery-test",
            "title": "Alphabet is better positioned for AI leadership at 83%",
            "rows": [{"name": "Alphabet leads AI hardware: Google TPU"}],
        }
    )
    assert clean.ok, clean.errors


def test_wording_headline_over_five_lines_at_390px() -> None:
    # Longest live headline currently on Discover (144 chars) must fit cleanly <= 5 lines.
    longest_live = (
        "Blue Origin beating SpaceX to the Moon leads the race to the Moon and Mars at 66%, "
        "with the United States as the next country on the Moon at 57%"
    )
    assert estimate_headline_lines_390px(longest_live) <= MAX_HEADLINE_LINES_390PX
    assert check_machinery_wording({"slug": "machinery-space-race", "title": longest_live, "rows": []}).ok

    oversized = (
        "Benedict Cumberbatch returning as Doctor Strange in Avengers Doomsday alongside "
        "Robert Downey Jr returning as Doctor Doom and Timothee Chalamet hosting Saturday Night Live "
        "is at 96 percent while Dune Part Three leads the summer box office"
    )
    assert estimate_headline_lines_390px(oversized) > MAX_HEADLINE_LINES_390PX
    res = check_machinery_wording({"slug": "machinery-long", "title": oversized, "rows": []})
    assert not res.ok
    assert any(e.rule == "headline_too_long_390px" for e in res.errors)


@pytest.mark.asyncio
async def test_public_rule_assembly_fails_when_public_set_comes_up_short(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    defn = _sample_public_definition(stage="public", min_items=3)
    short_snapshot = {
        "events": [],
        "markets": [
            _sample_market(990001, "Mars mission by 2030", 0.14, volume=5000.0),
            _sample_market(990002, "Aliens confirmed", 0.12, volume=None),
            _sample_market(990003, "Fusion reactor live", 0.10, volume=None),
        ],
        "paired_sets": {},
        "market_histories": {},
    }
    res = await audit_public_assembly_for_definition(defn, short_snapshot, now=NOW)
    assert not res.ok
    assert res.status == "FAIL_PUBLIC_SHORTFALL"
    missing_vol = [m for m in res.refused_members if m["reason"] == "missing_volume"]
    assert {m["market_id"] for m in missing_vol} == {990002, 990003}

    # Preview set with identical shortfall stays a preview warning unless strict_preview=True.
    preview_defn = _sample_public_definition(stage="preview", min_items=3)
    prev_res = await audit_public_assembly_for_definition(preview_defn, short_snapshot, now=NOW)
    assert prev_res.ok
    assert prev_res.status == "PREVIEW_SHORTFALL"
    strict_res = await audit_public_assembly_for_definition(
        preview_defn, short_snapshot, now=NOW, require_preview_pass=True
    )
    assert not strict_res.ok

    # Healthy public snapshot passes with 0 parity mismatches and clean wording/picture checks.
    healthy_snapshot = {
        "events": [],
        "markets": [
            _sample_market(990001, "Mars mission by 2030", 0.14, volume=5000.0),
            _sample_market(990002, "Aliens confirmed", 0.12, volume=5000.0),
            _sample_market(990003, "Fusion reactor live", 0.10, volume=5000.0),
        ],
        "paired_sets": {},
        "market_histories": {},
    }
    healthy_res = await audit_public_assembly_for_definition(defn, healthy_snapshot, now=NOW)
    assert healthy_res.ok
    assert healthy_res.status == "PASS"
    assert healthy_res.member_count == 3
    assert healthy_res.parity_mismatches == ()


def test_cli_exits_nonzero_on_public_shortfall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defn = _sample_public_definition(stage="public", min_items=3)
    fake_path = tmp_path / "machinery-long-shots.json"
    fake_path.write_text(json.dumps(defn), encoding="utf-8")
    monkeypatch.setattr(
        check_machinery_batch_pr,
        "discover_machinery_candidate_paths",
        lambda: (fake_path,),
    )
    monkeypatch.setattr(
        check_machinery_batch_pr,
        "build_synthetic_snapshot_for_definition",
        lambda *_args, **_kwargs: {
            "events": [],
            "markets": [
                _sample_market(990001, "Mars mission by 2030", 0.14, volume=5000.0),
                _sample_market(990002, "Aliens confirmed", 0.12, volume=None),
                _sample_market(990003, "Fusion reactor live", 0.10, volume=None),
            ],
            "paired_sets": {},
            "market_histories": {},
        },
    )
    exit_code = check_machinery_batch_pr.main(["--slugs", "machinery-long-shots"])
    assert exit_code == 1


def test_picture_policy_rejects_unverified_and_pexels_urls() -> None:
    bad_defn = _sample_public_definition(stage="public")
    bad_defn["rule"]["card_image_url"] = "https://images.pexels.com/photos/12345/pexels-photo-12345.jpeg"
    res = audit_picture_policy_for_definition(bad_defn)
    assert not res.ok
    assert any(e.rule == "picture_policy" for e in res.errors)


@pytest.mark.asyncio
async def test_all_repo_machinery_definitions_pass_batch_gate_on_structural_snapshot() -> None:
    """CI gate (a)+(b)+(c): every candidate definition passes wording & picture checks,
    and every public definition assembles cleanly without shortfalls or parity drift.
    """
    paths = discover_machinery_candidate_paths()
    assert paths, "Expected machinery candidate definitions"
    failures: list[str] = []
    for path in paths:
        defn = load_machinery_definition(path)
        snapshot = build_synthetic_snapshot_for_definition(defn, now=NOW)
        res = await audit_public_assembly_for_definition(
            defn,
            snapshot,
            now=NOW,
            require_preview_pass=True,
        )
        if not res.ok:
            failures.append(
                f"{path.stem}: status={res.status} refusal={res.refusal_reasons} "
                f"wording={res.wording.errors if res.wording else ()} "
                f"picture={res.picture.errors if res.picture else ()} "
                f"parity={res.parity_mismatches}"
            )
    assert not failures, "Machinery batch CI gate failures:\n" + "\n".join(failures)
