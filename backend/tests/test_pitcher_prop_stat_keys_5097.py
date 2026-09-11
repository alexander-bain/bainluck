"""#5097 (slice of #5088 / T3-2) — a pitcher's prop graded off a BATTER's key.

Measured on production event 15308050 (Rays 7 @ Braves 2, `completed`), where
two rows about the same pitcher and the same statistic sat four lines apart:

    Tampa Bay vs Atlanta: Strikeouts | Griffin Jax: 6+   ->  "2.0 - miss"
    Griffin Jax: Strikeouts O/U 6.5  | Over              ->  "grading unavailable"

The first resolves through the Kalshi TICKER (`kxmlbks` -> `pitching
strikeouts`). The second has no usable ticker and falls to the market-NAME
path, whose only match is the bare single ``"strikeouts"`` -- the BATTER's key.
Jax has no batting line, so `_sum_prop_stats` correctly returns None and the
row is withheld. The evidence was in the same payload the whole time.

** THE WITHHELD ROW IS THE MILD HALF. ** `backfill_winners.py` already carries
#1990's warning for the ticker table: pointing KXMLBKS back at the bare
"strikeouts" key "would grade every pitcher prop off a BATTER's K count". The
route's NAME path is pointed at exactly that key. It fails safe today only
because a pitcher usually has no batting line -- for a two-way player, or a
pitcher who batted, it publishes a confident verdict off the wrong statistic.
T3-2's acceptance is ZERO false grades, so the ambiguous case is REFUSED here
rather than guessed: no verdict beats a wrong one (#1728's rule, same file).

Every test below drives the real `_grade_settled_prop` over a real-shaped box
score. No source scanning: a test anchored on a source string is a test that
ERRORS -- indistinguishable from failing -- the moment the string it quotes is
the thing you fixed.
"""

import pytest

from app.routes.events import _build_prop_grade_context, _grade_settled_prop


class _Obj:
    """Stand-in for the ORM rows the grader reads (attribute access only)."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# Griffin Jax's line as production served it on event 15308050, verbatim.
JAX = {
    "era": 3.99,
    "earned runs": 1.0,
    "pitch count": 66.0,
    "innings pitched": 5.0,
    "pitching strikeouts": 2.0,
    "pitching hits allowed": 2.0,
    "pitching runs allowed": 1.0,
    "pitching walks allowed": 1.0,
    "pitching home runs allowed": 1.0,
}

# A batter's line from the same payload (Liam Hicks), for the regression arm.
HICKS = {
    "hits": 1.0,
    "rbis": 1.0,
    "runs": 0.0,
    "walks": 0.0,
    "at bats": 4.0,
    "home runs": 0.0,
    "strikeouts": 1.0,
    "pitches seen": 13.0,
}

# The case that publishes a FALSE verdict today: one player, both K keys.
TWO_WAY = dict(HICKS, **{"pitching strikeouts": 9.0, "innings pitched": 6.0})


def _ctx(players):
    ctx = _build_prop_grade_context(_Obj(box_score_data={"players": players}))
    assert ctx is not None, "fixture box score must build a grading context"
    return ctx


def _grade(players, market_name, outcome_name, threshold, is_under=False):
    """Grade one prop row the way the event page does."""
    return _grade_settled_prop(
        True,
        _ctx(players),
        _Obj(name=market_name, external_id=None, status="resolved"),
        _Obj(name=outcome_name, is_winner=None, resolution_source=None),
        threshold,
        is_under,
    )


# --------------------------------------------------------------------------
# 1. The reported row.
# --------------------------------------------------------------------------


def test_pitcher_strikeout_over_under_grades_off_the_pitching_key():
    got = _grade({"Griffin Jax": JAX}, "Griffin Jax: Strikeouts O/U 6.5", "Over", 6.5)
    assert got["actual"] == 2.0, (
        "the pitching strikeout count is in the same payload the page renders"
    )
    assert got["hit"] is False


def test_pitcher_strikeout_under_leg_grades_the_same_number():
    got = _grade(
        {"Griffin Jax": JAX}, "Griffin Jax: Strikeouts O/U 6.5", "Under", 6.5, is_under=True
    )
    assert got["actual"] == 2.0
    assert got["hit"] is True


# --------------------------------------------------------------------------
# 2. THE FALSE-GRADE CASE. This is the one that must never guess.
# --------------------------------------------------------------------------


def test_a_player_carrying_both_strikeout_keys_is_refused_not_guessed():
    got = _grade({"Liam Hicks": TWO_WAY}, "Liam Hicks: Strikeouts O/U 6.5", "Over", 6.5)
    assert got["actual"] is None, (
        "with a batting AND a pitching strikeout line the market name cannot say "
        "which one it means; grading it publishes a confident wrong verdict"
    )
    assert got["hit"] is None


# --------------------------------------------------------------------------
# 3. The pitcher counting stats the name path never had at all.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "market_name,expected",
    [
        ("Tampa Bay vs Atlanta: Walks Allowed", 1.0),
        ("Tampa Bay vs Atlanta: Hits Allowed", 2.0),
        ("Tampa Bay vs Atlanta: Runs Allowed", 1.0),
        ("Tampa Bay vs Atlanta: Home Runs Allowed", 1.0),
        ("Tampa Bay vs Atlanta: Earned Runs", 1.0),
    ],
)
def test_pitching_counting_stats_resolve(market_name, expected):
    got = _grade({"Griffin Jax": JAX}, market_name, "Griffin Jax: 3+", 3)
    assert got["actual"] == expected, market_name
    assert got["hit"] is (expected >= 3)


def test_hits_allowed_never_answers_with_the_batters_hits():
    """The phrase order is the guard: "hits allowed" CONTAINS "hits"."""
    both = dict(HICKS, **{"pitching hits allowed": 7.0, "innings pitched": 6.0})
    got = _grade({"Liam Hicks": both}, "Tampa Bay vs Atlanta: Hits Allowed", "Liam Hicks: 3+", 3)
    assert got["actual"] == 7.0, "1.0 here is the BATTER's hit total answering a pitcher's prop"
    assert got["hit"] is True


def test_home_runs_allowed_never_answers_with_the_batters_home_runs():
    both = dict(HICKS, **{"pitching home runs allowed": 2.0, "home runs": 0.0})
    got = _grade(
        {"Liam Hicks": both}, "Tampa Bay vs Atlanta: Home Runs Allowed", "Liam Hicks: 2+", 2
    )
    assert got["actual"] == 2.0
    assert got["hit"] is True


# --------------------------------------------------------------------------
# 4. Both directions of the census (gotcha #43): nothing else moves.
# --------------------------------------------------------------------------


def test_a_batters_strikeout_prop_is_unchanged():
    got = _grade({"Liam Hicks": HICKS}, "Liam Hicks: Strikeouts O/U 1.5", "Over", 1.5)
    assert got["actual"] == 1.0
    assert got["hit"] is False


def test_a_batters_hits_prop_is_unchanged():
    got = _grade({"Liam Hicks": HICKS}, "Liam Hicks: Hits O/U 0.5", "Over", 0.5)
    assert got["actual"] == 1.0
    assert got["hit"] is True


@pytest.mark.parametrize(
    "market_name",
    [
        "Ronald Acuna Jr.: Total Bases O/U 3.5",
        "Tampa Bay vs Atlanta: Stolen Bases",
        "Griffin Jax: Outs Recorded O/U 14.5",
    ],
)
def test_families_with_no_supporting_stat_stay_pending(market_name):
    """39 of the specimen's 49 withheld rows are honestly ungradeable.

    Total bases needs doubles and triples, which the box score does not carry;
    stolen bases are not in its vocabulary at all; outs recorded is derivable
    from `innings pitched` but only under the thirds convention (5.1 IP is 16
    outs, not 5.1), which is a different change. "Unknown stays explicitly
    pending" is the other half of T3-2 and it is already right -- this asserts
    the slice did not widen into a guess.
    """
    got = _grade({"Griffin Jax": JAX, "Liam Hicks": HICKS}, market_name, "Over", 3.5)
    assert got["actual"] is None, market_name
    assert got["hit"] is None
