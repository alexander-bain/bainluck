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
