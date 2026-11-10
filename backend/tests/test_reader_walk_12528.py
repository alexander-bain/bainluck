"""#12528: the reader walk sorts every answer into pass, fail, degraded or error.

(A fifth state, expired, is about a check past its date, never about the site.)

``tools/reader_walk/walk.py`` is a stdlib-only script, loaded by path so these tests read
exactly what gets run. Nothing here calls the live site: every answer is canned, and the
clock is passed in.

What these pin:
  * no committed check passes on an unrelated answer, including the six false passes
    Builder B found on the first draft (#12541): a check names the object asked for;
  * every committed check passes on its own example row;
  * a pass is proved by fields or by words, and the two are counted apart;
  * an ambiguous name needs both teams, not one team twice; "this week" names this week;
    and a check past its date is expired, never a pass or a fail (Builder B, #12541);
  * a degraded answer is never a pass, and an error is never an empty answer (#12290);
  * only a clean first call is a cold speed sample, and only a clean repeat is a repeat
    sample; the retry is the answer that gets judged; a non-pass keeps its raw answer.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WALK_PATH = REPO / "tools" / "reader_walk" / "walk.py"
QUERIES_PATH = REPO / "evals" / "reader-walk" / "queries" / "search-v1.json"

#: A fixed clock, years away from any real run. No test reads the wall clock.
NOW = datetime(2030, 1, 15, 2, 0, tzinfo=timezone.utc)


def _load():
    spec = importlib.util.spec_from_file_location("reader_walk", WALK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


walk = _load()
QUERIES = walk.load_queries(QUERIES_PATH)
BY_TEXT = {q["q"]: q for q in QUERIES}
EMPTY = {"empty": True}


def _answer(**lists):
    return {"query": "x", **lists}


def _in_hours(hours):
    return (NOW + timedelta(hours=hours)).isoformat()


def _state(search, payload, status=200):
    return walk.classify(status, payload, BY_TEXT[search]["check"], NOW)


def _raises(fn, *args):
    try:
        fn(*args)
    except ValueError as refusal:
        return str(refusal)
    return None


def _example_answer(query):
    example = query["example"]
    rows = [dict(r) for r in example.get("items") or [example["item"]]]
    if "starts_in_hours" in example:
        for row in rows:
            row["commence_time"] = _in_hours(example["starts_in_hours"])
    return _answer(**{example["kind"]: rows})


UNRELATED = _answer(
    event_concepts=[{"key": "event:unrelated", "name": "Unrelated"}],
    collections=[{"slug": "unrelated", "name": "Unrelated"}],
    teams=[{"slug": "unrelated-fc", "name": "Unrelated FC", "sport_key": "soccer_epl"}],
    futures=[{"id": 1, "name": "Unrelated market", "top_outcomes": [{"name": "Nobody"}]}],
    results=[{"sport": "soccer_epl", "home_team": "Liverpool", "away_team": "Chelsea", "commence_time": _in_hours(720)}],
)


def test_the_committed_query_set_loads_and_is_what_the_plan_counts():
    assert len(QUERIES) == 37
    by_class = {}
    for q in QUERIES:
        by_class[q["class"]] = by_class.get(q["class"], 0) + 1
    assert by_class == {"entity": 5, "alias": 6, "entity+market": 9, "set": 8, "other topics": 6, "honesty": 3}
    assert [q["q"] for q in QUERIES if q["check"].get("empty")] == ["asdfgh"]
    # Every committed check names its object. A words-only check would have to be added here on purpose.
    assert [q["q"] for q in QUERIES if walk.proof_of(q["check"]) == "words"] == []


def test_no_committed_check_passes_on_an_unrelated_answer():
    for q in QUERIES:
        assert walk.classify(200, UNRELATED, q["check"], NOW) == "fail", q["q"]


def test_every_committed_check_passes_on_its_own_example_row():
    for q in QUERIES:
        if q["check"].get("empty"):
            assert walk.classify(200, _answer(), q["check"], NOW) == "pass"
            continue
        assert walk.classify(200, _example_answer(q), q["check"], NOW) == "pass", q["q"]


def test_the_six_false_passes_found_in_review_now_fail():
    sole = {
        "celtics championship": _answer(futures=[{"id": 77, "name": "NFL Champion"}]),
        "nba champion": _answer(futures=[{"id": 78, "name": "NBA Finals MVP"}]),
        "snow boston": _answer(teams=[{"slug": "boston-celtics", "name": "Boston Celtics"}]),
        "close games tonight": _answer(collections=[{"slug": "oscars-2027", "name": "2027 Oscars"}]),
        "celtics next three games": _answer(collections=[{"slug": "celtics-win-total", "name": "Celtics season win total"}]),
    }
    for search, payload in sole.items():
        assert _state(search, payload) == "fail", search
    # "nba tonight": a soccer game tonight is the wrong sport, and an NBA game next week is the wrong night.
    soccer_tonight = {"sport": "soccer_epl", "home_team": "Liverpool", "away_team": "Chelsea", "commence_time": _in_hours(3)}
    nba_next_week = {"sport": "basketball_nba", "home_team": "Lakers", "away_team": "Celtics", "commence_time": _in_hours(170)}
    nba_tonight = {**nba_next_week, "commence_time": _in_hours(3)}
    assert _state("nba tonight", _answer(results=[soccer_tonight])) == "fail"
    assert _state("nba tonight", _answer(results=[nba_next_week])) == "fail"
    assert _state("nba tonight", _answer(results=[nba_tonight])) == "pass"
    # "games tonight" takes any sport, but still needs tonight.
    assert _state("games tonight", _answer(results=[soccer_tonight])) == "pass"
    assert _state("games tonight", _answer(results=[nba_next_week])) == "fail"


def test_the_right_slug_or_words_in_the_wrong_list_do_not_count():
    # A team row carrying the collection's slug is not the collection.
    assert _state("celtics next three games", _answer(teams=[{"slug": "celtics-next-3-games", "name": "x"}])) == "fail"
    assert _state("celtics next three games", _answer(collections=[{"slug": "celtics-next-3-games", "name": "x"}])) == "pass"
    # A market row carrying a team's slug is not the team.
    assert _state("celtics", _answer(futures=[{"slug": "boston-celtics", "name": "Boston Celtics"}])) == "fail"
    # Words are read only in the lists the check names.
    words = {"kinds": ["futures"], "name_has_all": ["snow", "boston"]}
    assert walk.check(words, walk.first_screen(_answer(futures=[{"name": "Snow in Boston?"}])), NOW) is True
    assert walk.check(words, walk.first_screen(_answer(collections=[{"name": "Snow in Boston?"}])), NOW) is False


def test_a_degraded_answer_is_never_a_pass_and_an_error_is_never_empty():
    celtics = _answer(teams=[{"slug": "boston-celtics", "name": "Boston Celtics"}])
    assert _state("celtics", celtics) == "pass"
    assert _state("celtics", {**celtics, "degraded": ["collections"]}) == "degraded"
    assert _state("celtics", {**celtics, "degraded": []}) == "pass"
    assert walk.classify(200, _answer(), EMPTY, NOW) == "pass"
    assert walk.classify(200, celtics, EMPTY, NOW) == "fail"
    assert walk.classify(200, _answer(degraded=["collections"]), EMPTY, NOW) == "degraded"
    assert walk.classify(0, {"_error": "timeout"}, EMPTY, NOW) == "error"
    assert walk.classify(503, _answer(), EMPTY, NOW) == "error"
    assert walk.classify(200, "not json", EMPTY, NOW) == "error"


def test_rank_counts_inside_the_items_own_list():
    second = _answer(
        collections=[{"slug": "nfl-2030-week-1", "name": "Week 1"}, {"slug": "x", "name": "X"}],
        teams=[{"slug": "celta-vigo-liga", "name": "Celta Vigo"}, {"slug": "boston-celtics", "name": "Boston Celtics"}],
    )
    # Second among teams: not "first" for the plain name, fine for the alias (top three).
    assert _state("celtics", second) == "fail"
    assert _state("celts", second) == "pass"
    # Collections ahead of the teams list do not push a first-ranked team down.
    first = _answer(collections=second["collections"], teams=list(reversed(second["teams"])))
    assert _state("celtics", first) == "pass"
    items = walk.first_screen(first)
    assert [(i.kind, i.rank) for i in items] == [("collections", 1), ("collections", 2), ("teams", 1), ("teams", 2)]


def test_a_slug_prefix_and_either_of_two_objects():
    assert _state("oscars", _answer(event_concepts=[{"key": "event:awards:oscars", "name": "The Oscars"}])) == "pass"
    assert _state("oscars", _answer(collections=[{"slug": "oscars-2027", "name": "Oscars 2027"}])) == "pass"
    assert _state("oscars", _answer(collections=[{"slug": "awards-2027", "name": "Oscars and more"}])) == "fail"
    assert _state("oscars", _answer(futures=[{"id": 6173044, "name": "Oscar Winner: Best Picture"}])) == "fail"
    assert _state("awards season", _answer(collections=[{"slug": "roundup-golden-globes-best-picture", "name": "x"}])) == "pass"
    assert _state("awards season", _answer(collections=[{"slug": "roundup-cfp-picture", "name": "Awards season"}])) == "fail"


def test_this_week_means_this_week_and_an_ambiguous_name_needs_both_teams():
    week_1 = {"slug": "nfl-2026-week-1", "name": "NFL Week 1"}
    week_10 = {"slug": "nfl-2026-week-10", "name": "NFL Week 10"}
    week_11 = {"slug": "nfl-2026-week-11", "name": "NFL Week 11"}
    # Any NFL week page is not this week's page.
    assert _state("nfl this week", _answer(collections=[week_1])) == "fail"
    assert _state("nfl this week", _answer(collections=[week_10, week_11])) == "pass"
    # This week's page has to come first among collections; "nfl week 10" only has to be there.
    assert _state("nfl this week", _answer(collections=[week_11, week_10])) == "fail"
    assert _state("nfl week 10", _answer(collections=[week_11, week_10])) == "pass"
    assert _state("nfl week 10", _answer(collections=[week_11])) == "fail"
    # One team returned twice is not both teams.
    ny, sf = {"slug": "new-york-giants", "name": "New York Giants"}, {"slug": "san-francisco-giants-mlb", "name": "San Francisco Giants"}
    assert _state("giants", _answer(teams=[ny, dict(ny)])) == "fail"
    assert _state("giants", _answer(teams=[sf, dict(sf)])) == "fail"
    assert _state("giants", _answer(teams=[ny, sf])) == "pass"
    nyr, tex = {"slug": "new-york-rangers", "name": "New York Rangers"}, {"slug": "texas-rangers-mlb", "name": "Texas Rangers"}
    assert _state("rangers", _answer(teams=[nyr, dict(nyr)])) == "fail"
    assert _state("rangers", _answer(teams=[tex, {"slug": "rangers", "name": "Rangers"}])) == "fail"
    assert _state("rangers", _answer(teams=[{"slug": "rangers", "name": "Rangers"}, tex, nyr])) == "pass"


def test_a_check_past_its_date_is_expired_and_never_a_pass_or_a_fail():
    hit = _answer(collections=[{"slug": "nfl-2029-week-18", "name": "Week 18"}])
    check = {"kinds": ["collections"], "where": {"slug": ["nfl-2029-week-18"]}}
    stale = {"class": "set", "q": "nfl this week", "expect": "this week", "check": check, "valid_until": "2029-12-31"}
    fresh = {**stale, "q": "nfl next year", "valid_until": "2030-12-31"}
    last_day = {**stale, "q": "nfl today", "valid_until": "2030-01-15"}
    fetch, _calls = _scripted([(200, 500, hit)] * 6)
    rows = walk.walk([stale, fresh, last_day], "https://example.invalid", fetch_fn=fetch, sleep=lambda _s: None, clock=lambda: NOW)
    # The stale check would have passed on this answer; it is reported as expired instead.
    assert [r["state"] for r in rows] == ["expired", "pass", "pass"]
    assert "raw" not in rows[0]
    assert walk.is_expired(last_day, NOW) is False
    assert walk.is_expired(last_day, NOW + timedelta(days=1)) is True
    summary = walk.summarize(rows)
    assert summary["states"] == {"pass": 2, "fail": 0, "degraded": 0, "error": 0, "expired": 1}
    assert summary["pass_by_proof"] == {"fields": 2, "words": 0}
    # The committed calendar-bound checks carry a date; a malformed one is refused.
    assert BY_TEXT["nfl this week"]["valid_until"] == BY_TEXT["nfl week 10"]["valid_until"]
    assert _raises(walk.valid_until, {"valid_until": "next week"}) is not None


def test_a_team_plus_market_search_needs_that_teams_outcome_on_the_card():
    with_pats = {"id": 86832, "name": "NFL Super Bowl Winner", "top_outcomes": [{"name": "New England Patriots"}]}
    without = {"id": 86832, "name": "NFL Super Bowl Winner", "top_outcomes": [{"name": "Buffalo Bills"}]}
    lookalike = {"id": 5, "name": "Super Bowl MVP", "top_outcomes": [{"name": "New England Patriots QB"}]}
    assert _state("superbowl patriots", _answer(futures=[with_pats])) == "pass"
    assert _state("superbowl patriots", _answer(futures=[without])) == "fail"
    assert _state("superbowl patriots", _answer(futures=[lookalike])) == "fail"
    assert _state("super bowl", _answer(futures=[without])) == "pass"
    assert _state("super bowl", _answer(futures=[lookalike])) == "fail"


def test_tonight_is_a_window_around_the_clock_that_was_passed_in():
    spec = BY_TEXT["games tonight"]["check"]

    def game(hours, stamp=None):
        row = {"sport": "icehockey_nhl", "home_team": "A", "away_team": "B"}
        row["commence_time"] = stamp if stamp is not None else _in_hours(hours)
        return walk.first_screen(_answer(results=[row]))

    assert walk.check(spec, game(-5), NOW) is True
    assert walk.check(spec, game(-7), NOW) is False
    assert walk.check(spec, game(17), NOW) is True
    assert walk.check(spec, game(19), NOW) is False
    assert walk.check(spec, game(0, "2030-01-15T04:00:00Z"), NOW) is True
    assert walk.check(spec, game(0, "2030-01-15T04:00:00"), NOW) is True
    assert walk.check(spec, game(0, "soon"), NOW) is False
    assert walk.check(spec, game(0, ""), NOW) is False
    # The same answer, judged a day later, is no longer tonight.
    assert walk.check(spec, game(3), NOW + timedelta(days=1)) is False


def test_how_a_pass_is_proved():
    assert walk.proof_of({"kinds": ["teams"], "where": {"slug": ["a"]}}) == "fields"
    assert walk.proof_of({"kinds": ["futures"], "where": {"id": [1]}, "name_has_all": ["x"]}) == "fields"
    assert walk.proof_of({"kinds": ["results"], "starts_within_hours": 18}) == "fields"
    assert walk.proof_of(EMPTY) == "fields"
    # Narrowing by a sport or a category names no object.
    assert walk.proof_of({"kinds": ["futures"], "where": {"category": ["weather"]}, "name_has_all": ["snow"]}) == "words"
    assert walk.proof_of({"kinds": ["futures"], "name_has_all": ["gemini"]}) == "words"
    both = [{"kinds": ["teams"], "where": {"slug": ["a"]}}, {"kinds": ["futures"], "name_has_all": ["a"]}]
    assert walk.proof_of({"any_of": both}) == "words"
    assert walk.proof_of({"any_of": [both[0], both[0]]}) == "fields"
    assert walk.proof_of({"all_of": both}) == "words"
    assert walk.proof_of({"all_of": [both[0], both[0]]}) == "fields"


def test_a_check_an_unrelated_answer_would_pass_is_refused():
    ok = {"kinds": ["teams"], "where": {"slug": ["boston-celtics"]}}
    assert walk.validate_spec(ok) == []
    assert walk.validate_spec(EMPTY) == []
    assert walk.validate_spec({"kinds": ["futures"], "name_has_all": ["gemini"]}) == []
    refused = [
        {},
        {"kinds": ["collections"]},
        {"kinds": ["results"], "min_count": 1},
        {"kinds": ["teams"], "rank_in_list_max": 1},
        {"kinds": ["futures"], "name_has_none": ["mvp"]},
        {"empty": True, "kinds": ["teams"]},
        {"empty": False},
        {"kinds": ["team"], "where": {"slug": ["a"]}},
        {"kinds": ["teams"], "where": {}},
        {"kinds": ["teams"], "where": {"slug": []}},
        {"kinds": ["teams"], "where": {"slug": ["*"]}},
        {"kinds": ["teams"], "where": {"slug": [True]}},
        {"kinds": ["teams"], "where": {"slug": ["a"]}, "rank_in_list_max": 0},
        {"kinds": ["teams"], "where": {"slug": ["a"]}, "top": 3},
        {"kinds": ["teams"], "where": {"slug": ["a"]}, "min_count": 2},
        {"kinds": ["teams"], "starts_within_hours": 18},
        {"kinds": ["futures"], "name_has_all": [" "]},
        {"any_of": [ok]},
        {"any_of": [ok, {"kinds": ["collections"]}]},
        {"any_of": [ok, ok], "kinds": ["teams"]},
        {"all_of": [ok]},
        {"all_of": [ok, {"kinds": ["collections"]}]},
        {"all_of": [ok, ok], "min_count": 2},
        "teams",
    ]
    for spec in refused:
        assert walk.validate_spec(spec) != [], spec


def test_a_bad_query_file_is_refused_with_its_reason(tmp_path):
    def write(queries):
        path = tmp_path / "q.json"
        path.write_text(json.dumps({"queries": queries}), encoding="utf-8")
        return path

    good = {"class": "entity", "q": "celtics", "expect": "the team", "check": BY_TEXT["celtics"]["check"]}
    assert len(walk.load_queries(write([good]))) == 1
    assert "appears twice" in _raises(walk.load_queries, write([good, dict(good)]))
    assert "unknown class" in _raises(walk.load_queries, write([{**good, "class": "team"}]))
    assert "expects" in _raises(walk.load_queries, write([{**good, "expect": ""}]))
    assert "unrelated answer would pass" in _raises(walk.load_queries, write([{**good, "check": {"kinds": ["teams"]}}]))
    assert "no queries" in _raises(walk.load_queries, write([]))
    assert "valid_until" in _raises(walk.load_queries, write([{**good, "valid_until": "Nov 16"}]))


def _scripted(answers):
    """A fetch that hands back canned (status, ms, payload) answers in order."""
    calls = []

    def fetch(api, path):
        calls.append(path)
        return answers[len(calls) - 1]

    return fetch, calls


def test_only_clean_calls_are_speed_samples_and_the_retry_is_what_gets_judged():
    hit = _answer(teams=[{"slug": "boston-celtics", "name": "Boston Celtics"}])
    snow = _answer(futures=[{"id": 9, "name": "Snow in Boston this month?"}])
    by_words = {
        "class": "other topics",
        "q": "snow boston",
        "expect": "a market on snow in Boston",
        "check": {"kinds": ["futures"], "name_has_all": ["snow", "boston"]},
    }
    queries = [BY_TEXT["celtics"], BY_TEXT["celts"], by_words, BY_TEXT["patriots"], BY_TEXT["asdfgh"]]
    fetch, calls = _scripted(
        [
            # celtics: clean first call, clean repeat.
            (200, 900, hit),
            (200, 100, hit),
            # celts: degraded first call, clean retry (judged), clean repeat.
            (200, 2500, {**hit, "degraded": ["collections"]}),
            (200, 300, hit),
            (200, 110, hit),
            # snow boston: clean, passes by words only.
            (200, 700, snow),
            (200, 90, snow),
            # patriots: degraded first call, still degraded on the retry, degraded repeat.
            (200, 2600, {"degraded": ["collections"]}),
            (200, 2700, {"degraded": ["collections"]}),
            (200, 2800, {"degraded": ["collections"]}),
            # asdfgh: no answer, no answer on the retry, then a clean empty repeat that is NOT judged.
            (0, 35000, {"_error": "timeout"}),
            (0, 35000, {"_error": "timeout"}),
            (200, 120, _answer()),
        ]
    )
    naps, ticks = [], []

    def clock():
        ticks.append(1)
        return NOW

    rows = walk.walk(queries, "https://example.invalid", fetch_fn=fetch, sleep=naps.append, clock=clock)
    assert [r["state"] for r in rows] == ["pass", "pass", "pass", "degraded", "error"]
    assert [r["proof"] for r in rows] == ["fields", "fields", "words", "fields", "fields"]
    assert len(calls) == 13 and all(c.startswith("/api/events/search?q=") for c in calls)
    assert calls[5] == "/api/events/search?q=snow%20boston"
    # One two-second pause per retry, never a real sleep, and the clock is the one passed in.
    assert naps.count(walk.RETRY_PAUSE_S) == 3
    assert len(ticks) == 5
    assert [r["ms_cold"] for r in rows] == [900, None, 700, None, None]
    assert [r["ms_repeat"] for r in rows] == [100, 110, 90, None, 120]
    assert [r["retried"] for r in rows] == [False, True, False, True, True]
    assert [r["first_call_degraded"] for r in rows] == [False, True, False, True, False]
    # Anything that isn't a pass keeps its raw answer; a pass does not.
    assert all("raw" not in r for r in rows[:3])
    assert rows[3]["raw"] == {"degraded": ["collections"]}
    assert rows[4]["raw"] == {"_error": "timeout"}

    summary = walk.summarize(rows)
    assert summary["states"] == {"pass": 3, "fail": 0, "degraded": 1, "error": 1, "expired": 0}
    assert summary["checks_by_proof"] == {"fields": 4, "words": 1}
    assert summary["pass_by_proof"] == {"fields": 2, "words": 1}
    assert summary["first_call_degraded"] == 2
    assert summary["first_call_not_200"] == 1
    assert summary["cold"] == {"n": 2, "p50_ms": 900, "p90_ms": 900, "p95_ms": 900, "max_ms": 900}
    assert summary["repeat"]["n"] == 4
    assert summary["by_class"]["honesty"] == {"pass": 0, "fail": 0, "degraded": 0, "error": 1, "expired": 0}


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
