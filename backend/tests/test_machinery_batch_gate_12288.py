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
    check_machinery_form_rules,
    check_machinery_wording,
    estimate_headline_lines_390px,
)
from scripts import check_machinery_batch_pr
from scripts.check_machinery_batch_pr import build_synthetic_snapshot_for_definition

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
            check_tile_pictures=False,
        )
        if not res.ok:
            failures.append(
                f"{path.stem}: status={res.status} refusal={res.refusal_reasons} "
                f"wording={res.wording.errors if res.wording else ()} "
                f"picture={res.picture.errors if res.picture else ()} "
                f"form={res.form_rules.errors if res.form_rules else ()} "
                f"parity={res.parity_mismatches}"
            )
    assert not failures, "Machinery batch CI gate failures:\n" + "\n".join(failures)


def test_wording_rejects_card_face_venues_jargon_units_and_ellipsis() -> None:
    """Item 2 wording check: venue names on card face, pts/pp/bps, and '…'/'...'."""
    bad_card = {
        "slug": "machinery-long-shots",
        "title": "Kalshi favorite jumps 10pp…",
        "subtitle": "Up 25 bps since opening while moving 3 pts against Polymarket",
        "source": "kalshi",
        "source_mark": "Polymarket",
        "rows": [
            {
                "name": "DraftKings candidate",
                "label": "Lead nominee",
                "answer": "Example",
                "source": "polymarket",
                "rendered_percent": "42%…",
            },
            {
                "name": "Runner up",
                "value": "12...",
                "delta": "+4 pts",
            },
        ],
    }
    res = check_machinery_wording(bad_card)
    assert not res.ok
    rules = {e.rule for e in res.errors}
    assert "venue_name_on_card_face" in rules
    assert "banned_jargon_unit" in rules
    assert "ellipsis_in_headline_or_number" in rules

    # Source metadata keys alone must not trigger venue_name_on_card_face; normal words must pass.
    clean_card = {
        "slug": "machinery-long-shots",
        "title": "Houston leads the Dec 7 AP #1 race at 54%",
        "subtitle": "Tracking top scripts, copper shipments, and apple harvest estimates.",
        "source": "polymarket",
        "source_mark": "Kalshi",
        "rows": [
            {
                "label": "Scripts reviewed",
                "answer": "Approved",
                "rendered_percent": 54,
                "source": "kalshi",
            }
        ],
    }
    clean_res = check_machinery_wording(clean_card)
    assert clean_res.ok, f"Unexpected violations: {clean_res.errors}"


def test_form_rules_enforce_duel_threshold_tile_pictures_and_history_chart() -> None:
    """Item 2 form rules: duel >=20%, spotlight/tile-grid 100% pictured, history >=10pt + sentence."""
    # 1. duel_bar trailing side under 20% fails; >= 20% passes.
    weak_duel = {
        "slug": "test-duel",
        "form_id": "duel_bar",
        "title": "Clear favorite dominates",
        "rows": [
            {"label": "Leader", "rendered_percent": 82},
            {"label": "Trailer", "rendered_percent": 18},
        ],
    }
    r_weak = check_machinery_form_rules(card=weak_duel)
    assert not r_weak.ok
    assert {e.rule for e in r_weak.errors} == {"form_duel_trailing_under_20"}

    tight_duel = {
        "slug": "test-duel",
        "form_id": "duel_bar",
        "title": "Close two-way contest",
        "rows": [
            {"label": "Leader", "rendered_percent": 80},
            {"label": "Trailer", "rendered_percent": 20},
        ],
    }
    assert check_machinery_form_rules(card=tight_duel).ok

    # 2. contender_spotlight & sibling_fields_grid require real pictures unless scale_ordered.
    no_pic_art = {"url": None, "kind": "monogram", "initials": "AB"}
    good_art = {"url": "https://a.espncdn.com/i/teamlogos/ncaa/500/248.png", "kind": "team_logo"}
    bad_spotlight = {
        "slug": "test-spot",
        "form_id": "contender_spotlight",
        "title": "Three contenders",
        "rows": [
            {"name": "A", "art": good_art},
            {"name": "B", "art": no_pic_art},
            {"name": "C", "art": good_art},
        ],
    }
    r_spot = check_machinery_form_rules(card=bad_spotlight)
    assert not r_spot.ok
    assert {e.rule for e in r_spot.errors} == {"form_spotlight_missing_picture"}

    bad_grid = {
        "slug": "test-grid",
        "form_id": "sibling_fields_grid",
        "title": "Three races",
        "sibling_fields": [
            {"title": "Race A", "outcomes": [{"name": "X", "art": good_art}]},
            {"title": "Race B", "outcomes": [{"name": "Y", "art": no_pic_art}]},
        ],
    }
    r_grid = check_machinery_form_rules(card=bad_grid)
    assert not r_grid.ok
    assert {e.rule for e in r_grid.errors} == {"form_tile_grid_missing_picture"}

    # scale_ordered cards remain exempt from picture enforcement.
    assert check_machinery_form_rules(card={**bad_spotlight, "scale_ordered": True}).ok
    assert check_machinery_form_rules(
        card={
            "slug": "test-spot",
            "form_id": "contender_spotlight",
            "title": "Three pictured contenders",
            "rows": [{"name": c, "art": good_art} for c in ("A", "B", "C")],
        }
    ).ok

    # 3. probability_history_chart: >= 10pt window swing & written sentence subhead.
    container_titles = {
        "sections": [
            {
                "visual_block": {
                    "form_id": "benchmark_strip",
                    "items": [
                        {"title": "Which company leads AI benchmarks?"},
                        {"title": "Will OpenAI launch GPT-6 in 2026?"},
                    ],
                }
            }
        ]
    }
    small_chart = {
        "slug": "test-chart",
        "form_id": "probability_history_chart",
        "title": "Tight weekly market",
        "subtitle": "Gemini climbed sharply while OpenAI slipped this week.",
        "mini_chart": {
            "series": [{"points": [{"probability": 0.42}, {"probability": 0.49}]}],
        },
    }
    r_small = check_machinery_form_rules(card=small_chart, container=container_titles)
    assert not r_small.ok
    assert {e.rule for e in r_small.errors} == {"form_history_chart_under_10_pts"}
    assert "7 percentage points" in r_small.errors[0].detail

    for bad_sub in (
        "",
        "7-day odds movement across Which company leads AI benchmarks and Will OpenAI launch GPT-6",
        "Which company leads AI benchmarks and Will OpenAI launch GPT-6 in 2026?",
        "Top tech markets, hardware launches, and more.",
    ):
        bad_sub_card = {
            **small_chart,
            "subtitle": bad_sub,
            "mini_chart": {"series": [{"points": [{"probability": 0.35}, {"probability": 0.50}]}]},
        }
        r_sub = check_machinery_form_rules(card=bad_sub_card, container=container_titles)
        assert not r_sub.ok, f"Expected bad subhead rejection for {bad_sub!r}"
        assert "form_history_chart_bad_subhead" in {e.rule for e in r_sub.errors}

    good_chart = {
        **small_chart,
        "subtitle": "Gemini gained 15 points over OpenAI in weekly trading.",
        "mini_chart": {"series": [{"points": [{"probability": 0.35}, {"probability": 0.50}]}]},
    }
    assert check_machinery_form_rules(card=good_chart, container=container_titles).ok


def test_machinery_batch_gate_module_has_no_subprocess_or_git_shellout() -> None:
    """Item 2 architecture check: git shell-outs live under scripts/, never app/utils/."""
    import ast

    gate_file = Path(__file__).resolve().parents[1] / "app" / "utils" / "machinery_batch_gate.py"
    tree = ast.parse(gate_file.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    defined_funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_funcs.add(node.name)
    assert "subprocess" not in imported_modules
    assert "discover_changed_machinery_slugs" not in defined_funcs


def test_scripts_discover_changed_machinery_slugs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`scripts.check_machinery_batch_pr.discover_changed_machinery_slugs` resolves touched sets."""
    from types import SimpleNamespace

    cand_path = tmp_path / "backend" / "data" / "groupings" / "candidates" / "machinery-long-shots.json"
    cand_path.parent.mkdir(parents=True, exist_ok=True)
    cand_path.write_text(json.dumps(_sample_public_definition()), encoding="utf-8")

    monkeypatch.setattr(
        check_machinery_batch_pr,
        "discover_machinery_candidate_paths",
        lambda: (cand_path,),
    )
    monkeypatch.setattr(
        check_machinery_batch_pr.subprocess,
        "run",
        lambda *_a, **_kw: SimpleNamespace(
            returncode=0,
            stdout="backend/data/groupings/candidates/machinery-long-shots.json\n",
        ),
    )
    assert check_machinery_batch_pr.discover_changed_machinery_slugs(repo_root=tmp_path) == (
        "machinery-long-shots",
    )
