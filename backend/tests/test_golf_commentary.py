"""Tests for the live AI commentary box (The Open Championship, live-only).

Covers the scope guard (Open-only), the live-only gate, pure mover selection,
prompt grounding, and graceful degradation (no box) on every failure path.
"""

from app.utils import golf_commentary as gc


# ---------------------------------------------------------------------------
# Scope guard — Open-only
# ---------------------------------------------------------------------------


def test_is_open_championship_matches_slug():
    assert gc.is_open_championship("the-open-championship") is True
    assert gc.is_open_championship("THE-OPEN-CHAMPIONSHIP") is True


def test_is_open_championship_matches_exact_name():
    assert gc.is_open_championship(None, "The Open Championship") is True
    assert gc.is_open_championship("some-slug", "the open championship") is True


def test_is_open_championship_rejects_other_golf_events():
    # The whole point of the guard — no other tournament turns the box on.
    assert gc.is_open_championship("us-open") is False
    assert gc.is_open_championship("u-s-open-championship") is False
    assert gc.is_open_championship("the-masters") is False
    assert gc.is_open_championship("scottish-open") is False
    assert gc.is_open_championship(None, "U.S. Open") is False
    assert gc.is_open_championship(None, "Women's Open Championship") is False
    assert gc.is_open_championship(None, None) is False
    assert gc.is_open_championship("") is False


# ---------------------------------------------------------------------------
# Mover selection (pure)
# ---------------------------------------------------------------------------


def _comp(name, prob, **kw):
    return {"name": name, "probability": prob, **kw}


def test_select_commentary_data_ranks_leaders_by_probability():
    comps = [
        _comp("Low", 0.05),
        _comp("High", 0.40, position="1"),
        _comp("Mid", 0.15),
    ]
    data = gc.select_commentary_data(comps)
    names = [r["name"] for r in data["leaders"]]
    assert names[0] == "High"
    assert data["leaders"][0]["win_pct"] == 40


def test_select_commentary_data_charging_requires_on_course_and_min_move():
    comps = [
        # Big gain, actively playing -> charging.
        _comp("Charger", 0.10, thru=8, today_score=-3, prob_delta_live=4.5),
        # Big gain but NOT on the course (overnight, thru=0) -> not a mover.
        _comp("Overnight", 0.37, thru=0, prob_delta_live=2.0),
        # Tiny move -> below threshold, not a mover.
        _comp("Flat", 0.08, thru=5, prob_delta_live=0.3),
        # Big drop, playing -> sliding.
        _comp("Slider", 0.09, thru=11, prob_delta_live=-3.1),
    ]
    data = gc.select_commentary_data(comps)
    assert [r["name"] for r in data["charging"]] == ["Charger"]
    assert [r["name"] for r in data["sliding"]] == ["Slider"]


def test_select_commentary_data_handles_string_numeric_fields():
    # The live leaderboard returns `thru` as a STRING ("9") — the mover gate must
    # not silently drop a real mover because of the type. (Live-day bug.)
    comps = [
        _comp("Charger", 0.06, thru="9", today_score=-3, score_to_par="-7",
              prob_delta_live=4.2),
        _comp("Overnight", 0.38, thru="0", prob_delta_live=0.3),
    ]
    data = gc.select_commentary_data(comps)
    assert [r["name"] for r in data["charging"]] == ["Charger"]
    # And the formatted line still renders the numbers from the strings.
    line = gc._fmt_competitor_line(data["charging"][0])
    assert "through 9 holes" in line
    assert "7 under par" in line


def test_to_num_coercion():
    assert gc._to_num("9") == 9.0
    assert gc._to_num(-7) == -7.0
    assert gc._to_num("  -7 ") == -7.0
    assert gc._to_num(None) is None
    assert gc._to_num("T5") is None
    assert gc._to_num(True) is None


def test_select_commentary_data_skips_none_probability():
    comps = [_comp("HasProb", 0.2), {"name": "NoProb", "probability": None}]
    data = gc.select_commentary_data(comps)
    assert [r["name"] for r in data["leaders"]] == ["HasProb"]


# ---------------------------------------------------------------------------
# Prompt building (pure, grounded)
# ---------------------------------------------------------------------------


def test_build_prompt_none_without_leaders():
    assert gc.build_commentary_prompt("The Open", {"leaders": []}) is None


def test_build_prompt_contains_only_given_numbers():
    data = gc.select_commentary_data(
        [
            _comp("Scottie Scheffler", 0.068, position="T5", thru=8,
                  today_score=-3, score_to_par=-7, prob_delta_live=4.5),
            _comp("Sam Burns", 0.37, position="1", thru=0,
                  today_score=0, score_to_par=-10, prob_delta_live=-0.9),
        ]
    )
    prompt = gc.build_commentary_prompt("The Open Championship", data)
    assert prompt is not None
    assert "Scottie Scheffler" in prompt
    assert "Sam Burns" in prompt
    # Scheffler win prob 0.068 -> 7%; Sam Burns 0.37 -> 37%.
    assert "7%" in prompt
    assert "37%" in prompt
    # Scheffler is the charging mover (+4.5 pts, thru 8).
    assert "+4.5 pts today" in prompt
    assert "win probability" in prompt.lower()


def test_par_formatting():
    assert gc._fmt_par(-7) == "7 under par"
    assert gc._fmt_par(3) == "3 over par"
    assert gc._fmt_par(0) == "even par"
    assert gc._fmt_par(None) is None


# ---------------------------------------------------------------------------
# generate_commentary — live-only + graceful degrade (no OpenAI on gated paths)
# ---------------------------------------------------------------------------


def test_generate_commentary_not_live_makes_no_call(monkeypatch):
    # If status != live, we must return None WITHOUT importing/calling the LLM.
    def _boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("LLM must not be called when not live")

    monkeypatch.setattr(
        "app.services.llm.generate_golf_live_commentary", _boom, raising=True
    )
    comps = [_comp("Leader", 0.4, thru=5)]
    assert gc.generate_commentary("The Open", comps, "upcoming") is None
    assert gc.generate_commentary("The Open", comps, "settled") is None


def test_generate_commentary_empty_competitors_returns_none():
    assert gc.generate_commentary("The Open", [], "live") is None


def test_generate_commentary_degrades_when_llm_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.generate_golf_live_commentary",
        lambda prompt: None,
        raising=True,
    )
    comps = [_comp("Leader", 0.4, thru=5, prob_delta_live=2.0)]
    assert gc.generate_commentary("The Open", comps, "live") is None


def test_generate_commentary_returns_text_when_live(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.generate_golf_live_commentary",
        lambda prompt: "  Scottie Scheffler is charging.  ",
        raising=True,
    )
    comps = [_comp("Scottie Scheffler", 0.4, thru=8, prob_delta_live=4.5)]
    out = gc.generate_commentary("The Open Championship", comps, "live")
    assert out == "Scottie Scheffler is charging."


def test_generate_commentary_swallows_llm_exception(monkeypatch):
    def _raise(prompt):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.services.llm.generate_golf_live_commentary", _raise, raising=True
    )
    comps = [_comp("Leader", 0.4, thru=5, prob_delta_live=2.0)]
    assert gc.generate_commentary("The Open", comps, "live") is None


# ---------------------------------------------------------------------------
# Change-detector: snapshot / diff / correlate (the 2026-07-19 redesign)
# ---------------------------------------------------------------------------


def _env(competitors, children=None):
    return {"primary": {"competitors": competitors}, "children": children or []}


def _region_prop(name, outcomes):
    # outcomes: list of (outcome_name, prob)
    return {
        "market_id": abs(hash(name)) % 100000,
        "market_name": name,
        "outcomes": [{"name": n, "probability": p} for n, p in outcomes],
    }


def test_snapshot_state_extracts_leaderboard_props_and_region():
    env = _env(
        [_comp("Cameron Young", 0.04, position="T3", thru="17", today_score=-5,
               score_to_par=-8)],
        [
            _region_prop("The Open Championship: Region to Win",
                         [("United States", 0.43), ("Rest of World", 0.22)]),
            _region_prop("The Open Championship: Top American Golfer",
                         [("Cameron Young", 0.10), ("Scottie Scheffler", 0.18)]),
        ],
    )
    snap = gc.snapshot_state(env)
    assert "cameron young" in snap["leaderboard"]
    lb = snap["leaderboard"]["cameron young"]
    assert lb["today"] == -5 and lb["thru"] == 17 and lb["win"] == 0.04
    # region derived from the "Top American Golfer" membership
    assert snap["golfer_region"]["cameron young"] == "United States"
    # region-to-win outcomes snapshotted
    assert any("Region to Win" in lbl for lbl in snap["labels"].values())


def test_diff_state_detects_birdie_with_hole_and_prop_move():
    prev = gc.snapshot_state(_env(
        [_comp("Cameron Young", 0.02, thru="16", today_score=-4)],
        [_region_prop("Region to Win", [("United States", 0.40)])],
    ))
    cur = gc.snapshot_state(_env(
        [_comp("Cameron Young", 0.04, thru="17", today_score=-5)],
        [_region_prop("Region to Win", [("United States", 0.43)])],
    ))
    diff = gc.diff_state(prev, cur)
    # scoring: single-hole advance 16->17 + one shot gained => birdie at 17
    cy = [s for s in diff["scoring"] if s["name"] == "Cameron Young"]
    assert cy and cy[0]["made"] == "birdie" and cy[0]["hole"] == 17
    assert cy[0]["win_from_pct"] == 2 and cy[0]["win_to_pct"] == 4
    # prop: US 40 -> 43 = +3 pts (>= threshold)
    us = [p for p in diff["props"] if p["outcome"] == "United States"]
    assert us and us[0]["from_pct"] == 40 and us[0]["to_pct"] == 43


def test_diff_no_prev_is_empty():
    cur = gc.snapshot_state(_env([_comp("X", 0.1, thru="5", today_score=-2)]))
    d = gc.diff_state(None, cur)
    assert d["scoring"] == [] and d["props"] == []
    assert gc.has_new_moves(d) is False


def test_multi_hole_advance_does_not_fabricate_hole():
    prev = gc.snapshot_state(_env([_comp("Y", 0.1, thru="12", today_score=-1)]))
    cur = gc.snapshot_state(_env([_comp("Y", 0.1, thru="15", today_score=-2)]))
    d = gc.diff_state(prev, cur)
    y = [s for s in d["scoring"] if s["name"] == "Y"][0]
    assert y["hole"] is None  # thru advanced 3 holes -> cannot pin the hole
    assert "gained 1 shot" in y["made"]


def test_correlate_links_american_birdie_to_region_move():
    prev = gc.snapshot_state(_env(
        [_comp("Cameron Young", 0.02, thru="16", today_score=-4)],
        [
            _region_prop("Region to Win", [("United States", 0.40)]),
            _region_prop("Top American Golfer", [("Cameron Young", 0.10)]),
        ],
    ))
    cur = gc.snapshot_state(_env(
        [_comp("Cameron Young", 0.05, thru="17", today_score=-5)],
        [
            _region_prop("Region to Win", [("United States", 0.44)]),
            _region_prop("Top American Golfer", [("Cameron Young", 0.14)]),
        ],
    ))
    diff = gc.diff_state(prev, cur)
    corr = gc.correlate_moves(diff, cur)
    # Cameron Young (US member, gaining) correlated to US region rising.
    us_corr = [c for c in corr if c["outcome"] == "United States"]
    assert us_corr, corr
    assert us_corr[0]["golfer"]["name"] == "Cameron Young"


def test_build_digest_prompt_leads_with_correlation_and_grounds_numbers():
    prev = gc.snapshot_state(_env(
        [_comp("Cameron Young", 0.02, thru="16", today_score=-4)],
        [_region_prop("Region to Win", [("United States", 0.40)]),
         _region_prop("Top American Golfer", [("Cameron Young", 0.10)])],
    ))
    cur = gc.snapshot_state(_env(
        [_comp("Cameron Young", 0.05, thru="17", today_score=-5)],
        [_region_prop("Region to Win", [("United States", 0.44)]),
         _region_prop("Top American Golfer", [("Cameron Young", 0.14)])],
    ))
    diff = gc.diff_state(prev, cur)
    corr = gc.correlate_moves(diff, cur)
    seed = gc.select_commentary_data(cur_competitors := [
        {"name": "Cameron Young", "probability": 0.05, "thru": "17"}
    ])
    prompt = gc.build_digest_prompt("The Open Championship", diff, corr, seed)
    assert prompt is not None
    assert "Cameron Young" in prompt
    assert "birdie" in prompt and "hole 17" in prompt
    assert "United States" in prompt
    assert "40%->44%" in prompt


def test_build_digest_prompt_falls_back_to_seed_when_quiet():
    # No moves -> should produce the seed (current-standings) prompt, not None.
    seed = gc.select_commentary_data([{"name": "Leader", "probability": 0.4}])
    prompt = gc.build_digest_prompt("The Open", {"scoring": [], "props": []}, [], seed)
    assert prompt is not None
    assert "Leader" in prompt


def test_generate_from_snapshots_not_live_makes_no_call(monkeypatch):
    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("must not call LLM when not live")

    monkeypatch.setattr(
        "app.services.llm.generate_golf_live_commentary", _boom, raising=True
    )
    cur = gc.snapshot_state(_env([_comp("X", 0.1, thru="5", today_score=-2)]))
    assert gc.generate_from_snapshots("The Open", cur, None, "settled", []) is None


def test_generate_from_snapshots_degrades_on_llm_none(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.generate_golf_live_commentary",
        lambda p: None,
        raising=True,
    )
    comps = [_comp("Cameron Young", 0.05, thru="17", today_score=-5)]
    prev = gc.snapshot_state(_env([_comp("Cameron Young", 0.02, thru="16",
                                         today_score=-4)]))
    cur = gc.snapshot_state(_env(comps))
    assert gc.generate_from_snapshots("The Open", cur, prev, "live", comps) is None
