"""Guard the two joins the live/057 latency instrument's number rests on.

`scripts/measure_live_tennis_card_latency.py` produces a median that gets
quoted at Alex. Two silent ways for that median to be wrong, neither of which
any amount of running it would reveal:

1. **The set count.** Both observers must be keyed on the SAME quantity — sets
   COMPLETE. Upstream that means counting ESPN's per-set linescores, where 7-6
   is a finished set and 6-5 is not; miscount either and every latency shifts
   by a whole set of play and still looks like a plausible number. The first
   run of this instrument used ``status.period`` instead and 3 of its 9
   latencies came out NEGATIVE, because ESPN's ``period`` trails its own
   linescores.
2. **The warm-up.** The first observation of each side is the state the
   observers walked in on, not a transition they watched. Pair those and the
   "latency" is really the order the two poll loops happened to boot in.

Both arms are asserted throughout: the guard fires on the bad case AND a
control proves it is not simply rejecting everything.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "measure_live_tennis_card_latency.py"
)


@pytest.fixture(scope="module")
def instrument():
    spec = importlib.util.spec_from_file_location(
        "measure_live_tennis_card_latency", _SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- the set count


@pytest.mark.parametrize(
    "a,b,complete",
    [
        (6, 4, True),    # ordinary set
        (6, 0, True),    # bagel
        (7, 5, True),    # served out from 5-5
        (7, 6, True),    # tiebreak — one clear game, still a finished set
        (6, 5, False),   # still playing
        (6, 6, False),   # tiebreak in progress
        (5, 4, False),   # nowhere near
        (0, 0, False),   # set just started
        ("", "", False),  # ESPN's placeholder for a set not begun
        (None, 3, False),
    ],
)
def test_set_is_complete(instrument, a, b, complete):
    assert instrument.set_is_complete(a, b) is complete


def test_completed_sets_excludes_the_set_in_progress(instrument):
    """A live 5th set at 3-3 is FOUR complete sets, not five."""
    games = [[7, 5, 6, 2, 3], [5, 7, 4, 6, 3]]
    assert instrument.completed_sets(games) == 4


def test_completed_sets_counts_a_tiebreak_set(instrument):
    assert instrument.completed_sets([[7, 4], [6, 2]]) == 1


def test_completed_sets_on_a_match_that_just_started(instrument):
    assert instrument.completed_sets([[1], [0]]) == 0


def test_completed_sets_needs_two_sides(instrument):
    assert instrument.completed_sets([]) is None
    assert instrument.completed_sets([[6, 4]]) is None


def test_pairs_join_on_the_same_set_total(instrument):
    """Both sides keyed on sets complete — the subtraction only means something then."""
    started = 1000.0
    pairs = instrument.pair_transitions(
        espn_seen={"182725": {1: 1100.0, 2: 1400.0}},
        card_seen={15300836: {1: 1150.0, 2: 1700.0}},
        by_espn={"182725": 15300836},
        started=started,
        espn_interval=15.0,
        card_interval=20.0,
    )
    by_sets = {p["sets"]: p for p in pairs}
    assert set(by_sets) == {1, 2}
    assert by_sets[1]["latency_s"] == pytest.approx(50.0)
    assert by_sets[2]["latency_s"] == pytest.approx(300.0)


def test_a_card_that_led_the_upstream_is_reported_not_dropped(instrument):
    """A negative latency is a reading. Dropping it selects on the outcome.

    The first run's median was computed over non-negative pairs only and came
    out 144.1s; over all nine it was 73.3s. Same trace, two answers — so the
    sign has to survive as far as the summary.
    """
    pairs = instrument.pair_transitions(
        espn_seen={"182725": {1: 1400.0}},
        card_seen={15300836: {1: 1310.0}},
        by_espn={"182725": 15300836},
        started=1000.0,
        espn_interval=15.0,
        card_interval=20.0,
    )
    assert len(pairs) == 1
    assert pairs[0]["latency_s"] == pytest.approx(-90.0)


# ------------------------------------------------------------------ the warm-up


def test_state_we_walked_in_on_is_not_a_transition(instrument):
    """Both first observations land inside the opening cycle — nothing to pair."""
    started = 1000.0
    pairs = instrument.pair_transitions(
        espn_seen={"182725": {2: started + 5.0}},
        card_seen={15300836: {2: started + 3.0}},
        by_espn={"182725": 15300836},
        started=started,
        espn_interval=15.0,
        card_interval=20.0,
    )
    assert pairs == []


def test_a_transition_after_warm_up_survives(instrument):
    """Control for the test above: the same shape, just later, must pair.

    Without this arm the warm-up guard could reject everything forever and the
    exclusion test would still be green.
    """
    started = 1000.0
    pairs = instrument.pair_transitions(
        espn_seen={"182725": {2: started + 300.0}},
        card_seen={15300836: {2: started + 420.0}},
        by_espn={"182725": 15300836},
        started=started,
        espn_interval=15.0,
        card_interval=20.0,
    )
    assert len(pairs) == 1
    assert pairs[0]["latency_s"] == pytest.approx(120.0)


def test_unwatched_event_is_ignored(instrument):
    """An ESPN id with no event behind it must not raise or invent a pair."""
    pairs = instrument.pair_transitions(
        espn_seen={"999999": {2: 1400.0}},
        card_seen={15300836: {2: 1500.0}},
        by_espn={"182725": 15300836},
        started=1000.0,
        espn_interval=15.0,
        card_interval=20.0,
    )
    assert pairs == []


# --------------------------------------------------------------- observer A shape


def _scoreboard(*competitions) -> dict:
    return {
        "events": [
            {"groupings": [{"competitions": list(competitions)}]}
        ]
    }


def _competition(comp_id: str, state: str, period: int, games) -> dict:
    return {
        "id": comp_id,
        "status": {"period": period, "type": {"state": state, "detail": f"Set {period}"}},
        "competitors": [
            {"linescores": [{"value": v} for v in side]} for side in games
        ],
    }


def test_read_espn_takes_live_competitions_only(instrument, monkeypatch):
    """A finished match carries a period too; counting it would fake a set end."""
    payload = _scoreboard(
        _competition("182725", "in", 5, [[7, 5, 6, 2, 3], [5, 7, 4, 6, 3]]),
        _competition("184607", "post", 2, [[7, 6], [6, 3]]),
        _competition("182999", "pre", 0, [[], []]),
    )
    monkeypatch.setattr(instrument, "_get_json", lambda url, timeout=15.0: payload)

    live = instrument.read_espn()

    assert set(live) == {"182725"}
    assert live["182725"]["period"] == 5
    assert live["182725"]["sets"] == 4, "the live 5th set is not a completed one"
    assert live["182725"]["games"] == [[7, 5, 6, 2, 3], [5, 7, 4, 6, 3]]


def test_read_espn_survives_a_dead_tour_read(instrument, monkeypatch):
    """One tour 403ing must not cost the other tour's matches (ESPN does 403)."""
    calls = {"n": 0}

    def flaky(url, timeout=15.0):
        calls["n"] += 1
        if "wta" in url:
            return None
        return _scoreboard(_competition("182725", "in", 3, [[6, 4], [3, 2]]))

    monkeypatch.setattr(instrument, "_get_json", flaky)

    live = instrument.read_espn()

    assert calls["n"] == 2, "both tours must still be attempted"
    assert set(live) == {"182725"}


def test_get_json_sends_no_custom_user_agent(instrument):
    """ESPN 403s a bespoke agent from this network — the observer must stay bare.

    Reads the source rather than the wire because the failure is a header that
    LOOKS harmless; a request-level assertion would need the network that
    refuses it.
    """
    source = _SCRIPT.read_text()
    body = source.split("def _get_json", 1)[1].split("\ndef ", 1)[0]
    # Comments are where the header is EXPLAINED; code is where it would be
    # sent. Scanning both makes the guard unsatisfiable by anyone documenting
    # the constraint — which is the same trap as a scan that can never fire.
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    assert "User-Agent" in body, (
        "the reason the agent stays bare must survive in the source"
    )
    assert "User-Agent" not in code
    assert "urllib.request.Request(url)" in code


# ═════════════════ live/058: the games grain, same two observers ═════════════


def test_orientation_puts_our_home_player_first(instrument):
    """ESPN's competitor order is its own and does not match ours.

    ═══ WHY THE GAMES JOIN NEEDS THIS AND THE SETS JOIN DOES NOT ═══

    The sets key is `home_score + away_score`, a SUM — the same number whichever
    way round the sides are. A games tuple is not: `6-2` and `2-6` are different
    keys for one scoreboard. Unoriented, observer A would never match observer B
    and the games median would come back EMPTY while looking like a run.
    """
    sides = [
        {"name": "Alejandro Tabilo", "games": [2, 7]},
        {"name": "Alexei Popyrin", "games": [6, 6]},
    ]
    oriented = instrument.orient_home_first("Alexei Popyrin", sides)
    assert [s["name"] for s in oriented] == ["Alexei Popyrin", "Alejandro Tabilo"]
    assert instrument.games_key(oriented) == "6-2|6-7"


def test_orientation_refuses_rather_than_guesses(instrument):
    """Neither side contains our surname — dropped, not paired at random.

    A reversed key does not produce a wrong latency; it produces NO latency,
    silently, which is worse because the run still prints a median over
    whatever else it caught.
    """
    sides = [
        {"name": "Alejandro Tabilo", "games": [2]},
        {"name": "Alexei Popyrin", "games": [6]},
    ]
    assert instrument.orient_home_first("Somebody Else", sides) is None
    assert instrument.orient_home_first("", sides) is None


def test_the_key_is_the_whole_board_not_the_current_set(instrument):
    """`4-1` in set four must not collide with `4-1` in set two.

    Keyed on the current set alone, the join would pair a game won at 20:40
    with one won an hour earlier and report a latency of an hour.
    """
    set_two = instrument.games_key([{"games": [6, 4]}, {"games": [2, 1]}])
    set_four = instrument.games_key(
        [{"games": [6, 3, 6, 4]}, {"games": [2, 6, 4, 1]}]
    )
    assert set_two == "6-2|4-1"
    assert set_four == "6-2|3-6|6-4|4-1"
    assert set_two != set_four


def test_a_side_espn_has_not_written_yet_is_a_question_mark_not_a_zero(instrument):
    """The changeover. `0` there is a score; `?` is the absence of one.

    Both observers build the key through this one function, so the instant is
    keyed identically on both sides and pairs normally once ESPN catches up.
    """
    assert instrument.games_key([{"games": [6, 1]}, {"games": [3]}]) == "6-3|1-?"


def test_no_line_on_either_side_yields_no_key(instrument):
    assert instrument.games_key([{"games": []}, {"games": [1]}]) is None
    assert instrument.games_key([{"games": [1]}]) is None


def test_the_card_reader_builds_its_key_through_the_same_function(instrument, monkeypatch):
    """ONE key builder, two callers.

    Two spellings of `6-2|7-6` would join nothing and read as an infinitely slow
    card — the failure this whole extension is most likely to have.
    """
    payload = {
        "home_score": 1,
        "away_score": 1,
        "status": "live",
        "linescore": {
            "sets": [
                {"home": 6, "away": 2},
                {"home": 6, "away": 7},
                {"home": 4, "away": 1},
            ],
        },
    }
    monkeypatch.setattr(instrument, "_get_json", lambda url, timeout=15.0: payload)
    card = instrument.read_card("https://api.example", 15300836)
    assert card["games_key"] == "6-2|6-7|4-1"
    assert card["sets"] == 2

    espn = instrument.orient_home_first("Alexei Popyrin", [
        {"name": "Alexei Popyrin", "games": [6, 6, 4]},
        {"name": "Alejandro Tabilo", "games": [2, 7, 1]},
    ])
    assert instrument.games_key(espn) == card["games_key"]


def test_a_deployment_without_a_linescore_reads_as_absent_not_as_fast(instrument, monkeypatch):
    """gotcha #53 / the zero-yield rule.

    Run against a build that predates #2746, the card has no `linescore` key.
    That must surface as `card_carries_linescore: false` and no game pairs —
    NEVER as a fast median over an empty set.
    """
    monkeypatch.setattr(
        instrument, "_get_json",
        lambda url, timeout=15.0: {"home_score": 1, "away_score": 1, "status": "live"},
    )
    card = instrument.read_card("https://api.example", 15300836)
    assert card["games_key"] is None
    assert card["sets"] == 2


def test_the_games_pairs_use_the_same_rules_as_the_set_pairs(instrument):
    """Same warm-up drop, same sign policy, same function — only the key differs."""
    pairs = instrument.pair_transitions(
        espn_seen={"182725": {"6-2|4-1": 1100.0, "6-2|5-1": 1400.0}},
        card_seen={15300836: {"6-2|4-1": 1112.0, "6-2|5-1": 1390.0}},
        by_espn={"182725": 15300836},
        started=1000.0,
        espn_interval=15.0,
        card_interval=20.0,
        key_field="games",
    )
    by_key = {p["games"]: p for p in pairs}
    assert set(by_key) == {"6-2|4-1", "6-2|5-1"}
    assert by_key["6-2|4-1"]["latency_s"] == pytest.approx(12.0)
    # The negative survives to the summary, exactly as it does for sets.
    assert by_key["6-2|5-1"]["latency_s"] == pytest.approx(-10.0)
    assert instrument.summarize(pairs)["median_latency_s"] == pytest.approx(1.0)
    assert instrument.summarize(pairs)["negative_pairs"] == 1


def test_summarize_on_an_empty_run_says_nothing_rather_than_zero(instrument):
    """`0.0` would read as a perfect card. `None` reads as no measurement."""
    assert instrument.summarize([]) == {
        "n": 0,
        "negative_pairs": 0,
        "median_latency_s": None,
        "min_latency_s": None,
        "max_latency_s": None,
    }
