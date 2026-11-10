"""#12528: the reader walk sorts every answer into pass, fail, degraded or error.

``tools/reader_walk/walk.py`` is a stdlib-only script, loaded by path so these tests read
exactly what gets run. Nothing here calls the live site: every answer is canned.

What these pin:
  * a degraded answer is never a pass, even when the right item is in it, and an error
    is never an empty answer (#12290: neither may count as a valid result);
  * only a clean first call is a cold speed sample, and only a clean repeat is a repeat
    sample;
  * the retry is the answer that gets judged, and anything that isn't a pass keeps its
    raw answer;
  * the committed query set loads, and a check that could pass on anything is refused.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WALK_PATH = REPO / "tools" / "reader_walk" / "walk.py"
QUERIES_PATH = REPO / "evals" / "reader-walk" / "queries" / "search-v1.json"


def _load():
    spec = importlib.util.spec_from_file_location("reader_walk", WALK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


walk = _load()

CELTICS = {"kinds": ["teams"], "name_has_all": ["celtics"], "top": 3}
EMPTY = {"empty": True}


def _answer(**lists):
    return {"query": "x", **lists}


def _raises(fn, *args):
    try:
        fn(*args)
    except ValueError as exc:
        return str(exc)
    return None


def test_the_committed_query_set_loads_and_is_what_the_plan_counts():
    queries = walk.load_queries(QUERIES_PATH)
    assert len(queries) == 37
    assert len({q["q"] for q in queries}) == 37
    by_class = {}
    for q in queries:
        by_class[q["class"]] = by_class.get(q["class"], 0) + 1
    assert by_class == {
        "entity": 5,
        "alias": 6,
        "entity+market": 9,
        "set": 8,
        "other topics": 6,
        "honesty": 3,
    }
    # The one search that expects nothing is the nonsense one.
    assert [q["q"] for q in queries if q["check"].get("empty")] == ["asdfgh"]


def test_a_clean_answer_passes_or_fails_on_what_the_first_screen_holds():
    hit = _answer(teams=[{"name": "Boston Celtics"}])
    miss = _answer(teams=[{"name": "Boston Bruins"}])
    assert walk.classify(200, hit, CELTICS) == "pass"
    assert walk.classify(200, miss, CELTICS) == "fail"
    assert walk.classify(200, _answer(), CELTICS) == "fail"


def test_a_degraded_answer_is_never_a_pass_even_with_the_right_item_in_it():
    partial = _answer(teams=[{"name": "Boston Celtics"}], degraded=["collections"])
    assert walk.classify(200, partial, CELTICS) == "degraded"
    # An empty degraded list is a clean answer.
    assert walk.classify(200, _answer(teams=[{"name": "Boston Celtics"}], degraded=[]), CELTICS) == "pass"


def test_an_error_or_a_degraded_answer_is_never_an_honest_empty_state():
    assert walk.classify(200, _answer(), EMPTY) == "pass"
    assert walk.classify(200, _answer(teams=[{"name": "Anything"}]), EMPTY) == "fail"
    assert walk.classify(200, _answer(degraded=["collections"]), EMPTY) == "degraded"
    assert walk.classify(0, {"_error": "timeout"}, EMPTY) == "error"
    assert walk.classify(503, _answer(), EMPTY) == "error"
    assert walk.classify(200, "not json", EMPTY) == "error"


def test_top_counts_across_the_whole_first_screen_before_the_list_filter():
    # Two collections come first, so the team is the third item: inside top 3, outside top 2.
    answer = _answer(
        collections=[{"name": "NBA tonight"}, {"name": "Closest games"}],
        teams=[{"name": "Boston Celtics"}],
    )
    assert walk.first_screen(answer) == [
        ("collections", "NBA tonight"),
        ("collections", "Closest games"),
        ("teams", "Boston Celtics"),
    ]
    assert walk.check(CELTICS, walk.first_screen(answer)) is True
    assert walk.check({**CELTICS, "top": 2}, walk.first_screen(answer)) is False
    # The right words in the wrong list do not count.
    wrong_list = _answer(futures=[{"name": "Will the Celtics win the title?"}])
    assert walk.check(CELTICS, walk.first_screen(wrong_list)) is False


def test_words_all_any_and_a_game_row_reads_as_away_at_home():
    spec = {"name_has_all": ["nba"], "name_has_any": ["champion", "finals"], "top": 5}
    assert walk.check(spec, [("futures", "NBA Champion")]) is True
    assert walk.check(spec, [("futures", "NBA Finals MVP")]) is True
    assert walk.check(spec, [("futures", "NBA MVP")]) is False
    assert walk.check(spec, [("futures", "NHL Champion")]) is False
    game = _answer(results=[{"home_team": {"name": "Lakers"}, "away_team": "Celtics"}])
    assert walk.first_screen(game) == [("results", "Celtics at Lakers")]
    assert walk.check({"kinds": ["results"]}, walk.first_screen(game)) is True
    assert walk.check({"kinds": ["results"], "min_count": 2}, walk.first_screen(game)) is False


def test_a_check_that_anything_would_pass_is_refused():
    assert walk.validate_spec(CELTICS) == []
    assert walk.validate_spec(EMPTY) == []
    assert walk.validate_spec({"top": 5}) != []
    assert walk.validate_spec({}) != []
    assert walk.validate_spec({"empty": True, "top": 3}) != []
    assert walk.validate_spec({"empty": False, "kinds": ["teams"]}) != []
    assert walk.validate_spec({"kinds": ["team"]}) != []
    assert walk.validate_spec({"name_has_all": [" "]}) != []
    assert walk.validate_spec({"kinds": ["teams"], "top": 0}) != []
    assert walk.validate_spec({"kinds": ["teams"], "tops": 3}) != []


def test_a_bad_query_file_is_refused_with_its_reason(tmp_path):
    def write(queries):
        path = tmp_path / "q.json"
        path.write_text(json.dumps({"queries": queries}), encoding="utf-8")
        return path

    good = {"class": "entity", "q": "celtics", "expect": "the team", "check": CELTICS}
    assert len(walk.load_queries(write([good]))) == 1
    assert "appears twice" in _raises(walk.load_queries, write([good, dict(good)]))
    assert "unknown class" in _raises(walk.load_queries, write([{**good, "class": "team"}]))
    assert "expects" in _raises(walk.load_queries, write([{**good, "expect": ""}]))
    assert "anything would pass" in _raises(walk.load_queries, write([{**good, "check": {"top": 5}}]))
    assert "no queries" in _raises(walk.load_queries, write([]))


def _scripted(answers):
    """A fetch that hands back canned (status, ms, payload) answers in order."""
    calls = []

    def fetch(api, path):
        calls.append(path)
        return answers[len(calls) - 1]

    return fetch, calls


def test_only_clean_calls_are_speed_samples_and_the_retry_is_what_gets_judged():
    hit = _answer(teams=[{"name": "Boston Celtics"}])
    queries = [
        {"class": "entity", "q": "celtics", "expect": "the team", "check": CELTICS},
        {"class": "entity", "q": "celtics two", "expect": "the team", "check": CELTICS},
        {"class": "entity", "q": "celtics three", "expect": "the team", "check": CELTICS},
        {"class": "honesty", "q": "asdfgh", "expect": "nothing", "check": EMPTY},
    ]
    fetch, calls = _scripted(
        [
            # 1: clean first call, clean repeat.
            (200, 900, hit),
            (200, 100, hit),
            # 2: degraded first call, clean retry (judged), clean repeat.
            (200, 2500, {**hit, "degraded": ["collections"]}),
            (200, 300, hit),
            (200, 110, hit),
            # 3: degraded first call, still degraded on the retry, degraded repeat.
            (200, 2600, {"degraded": ["collections"]}),
            (200, 2700, {"degraded": ["collections"]}),
            (200, 2800, {"degraded": ["collections"]}),
            # 4: no answer, no answer on the retry, then a clean empty repeat that is NOT judged.
            (0, 35000, {"_error": "timeout"}),
            (0, 35000, {"_error": "timeout"}),
            (200, 120, _answer()),
        ]
    )
    naps = []
    rows = walk.walk(queries, "https://example.invalid", fetch_fn=fetch, sleep=naps.append)
    assert [r["state"] for r in rows] == ["pass", "pass", "degraded", "error"]
    assert len(calls) == 11 and all(c.startswith("/api/events/search?q=") for c in calls)
    assert calls[2] == "/api/events/search?q=celtics%20two"
    # One two-second pause per retry, and never a real sleep in a test.
    assert naps.count(walk.RETRY_PAUSE_S) == 3
    # Cold samples: only the first query's first call was clean.
    assert [r["ms_cold"] for r in rows] == [900, None, None, None]
    # Repeat samples: the degraded repeat is not one.
    assert [r["ms_repeat"] for r in rows] == [100, 110, None, 120]
    assert [r["retried"] for r in rows] == [False, True, True, True]
    assert [r["first_call_degraded"] for r in rows] == [False, True, True, False]
    # Anything that isn't a pass keeps its raw answer; a pass does not.
    assert "raw" not in rows[0] and "raw" not in rows[1]
    assert rows[2]["raw"] == {"degraded": ["collections"]}
    assert rows[3]["raw"] == {"_error": "timeout"}

    summary = walk.summarize(rows)
    assert summary["states"] == {"pass": 2, "fail": 0, "degraded": 1, "error": 1}
    assert summary["first_call_degraded"] == 2
    assert summary["first_call_not_200"] == 1
    assert summary["cold"] == {"n": 1, "p50_ms": 900, "p90_ms": 900, "p95_ms": 900, "max_ms": 900}
    assert summary["repeat"]["n"] == 3
    assert summary["by_class"]["honesty"] == {"pass": 0, "fail": 0, "degraded": 0, "error": 1}


def test_percentiles_use_nearest_rank_and_say_none_for_nothing():
    assert walk.percentile([], 0.5) is None
    assert walk.percentile([7], 0.95) == 7
    values = list(range(1, 21))
    assert walk.percentile(values, 0.5) == 11
    assert walk.percentile(values, 0.95) == 20
    assert walk.percentile(values, 0.0) == 1


def test_the_tool_reads_no_secret_and_only_ever_gets():
    source = WALK_PATH.read_text(encoding="utf-8")
    for forbidden in ("os.environ", "getenv", "Authorization", "Cookie", "method=", "data=", "import requests"):
        assert forbidden not in source, forbidden
    assert source.count("urllib.request.urlopen(") == 1
