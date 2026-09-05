"""Q441 (#1495) — a finished game stops publishing the losing team as the favorite.

Red-first. Every case below is either an ESPN-verified production row from
2026-08-29 or the kill that stops the fix from crowning a wrong winner.

The counts are pinned as counts so a reshape of ``RESOLVABLE_STATUSES`` fails
loudly rather than quietly covering nothing.
"""

import pytest

from app.utils.settled_hero import (
    FINAL_UNRESOLVED_SOURCE,
    FINISHED_STATUSES,
    RESOLVABLE_STATUSES,
    SETTLED_HERO_SOURCE,
    is_finished_status,
    resolve_settled_hero,
)

COMPLETED_AT = "2026-08-29T02:12:28.124912+00:00"


def _resolve(status="completed", home=3, away=1, completed_at=COMPLETED_AT):
    return resolve_settled_hero(
        status=status, home_score=home, away_score=away, completed_at=completed_at
    )


# --------------------------------------------------------------------------
# The five production contradictions, each verified against ESPN before the fix
# was written. hero_before is what production published on 2026-08-29.
# --------------------------------------------------------------------------
PRODUCTION_CONTRADICTIONS = [
    # (event_id, home, away, home_score, away_score, hero_before_home)
    (15294037, "Villanova", "William and Mary", 32, 35, 0.8199),
    (15291335, "Carolina Panthers", "Houston Texans", 16, 13, 0.4859),
    (15195988, "Watford", "Peterborough United", 1, 5, 0.6492),
    (15200188, "Criciuma", "Fortaleza", 0, 2, 0.6845),
    (15193258, "Sarmiento de Junin", "Estudiantes", 2, 0, 0.4533),
]


def test_production_contradiction_count_is_pinned():
    """5 of the 44-event sampled cohort. If this list shrinks, the evidence base
    for the whole queue shrank with it."""
    assert len(PRODUCTION_CONTRADICTIONS) == 5


@pytest.mark.parametrize(
    "event_id,home,away,hs,as_,hero_before", PRODUCTION_CONTRADICTIONS
)
def test_settled_hero_agrees_with_the_final_score(
    event_id, home, away, hs, as_, hero_before
):
    """The whole ship in one assertion: the resolved hero points at the winner."""
    resolved = _resolve(home=hs, away=as_)
    assert resolved is not None, f"{event_id} did not resolve"

    home_won = hs > as_
    assert (resolved.home_probability > 0.5) is home_won
    assert resolved.result == ("home" if home_won else "away")

    # and it actually CHANGES the published number — a fix that agrees with the
    # broken value everywhere would pass a direction check while shipping nothing.
    assert (hero_before > 0.5) is not home_won, (
        f"{event_id} is in this list because production had it backwards"
    )


@pytest.mark.parametrize(
    "event_id,home,away,hs,as_,hero_before", PRODUCTION_CONTRADICTIONS
)
def test_settled_hero_is_terminal(event_id, home, away, hs, as_, hero_before):
    """0 of 42 settled games reached a terminal value. All of them must now."""
    resolved = _resolve(home=hs, away=as_)
    assert {resolved.home_probability, resolved.away_probability} == {0.0, 1.0}
    assert resolved.home_probability + resolved.away_probability == 1.0
    assert resolved.source == SETTLED_HERO_SOURCE


# --------------------------------------------------------------------------
# THE KILL. `closed` scores are frozen mid-game and invert the winner. These are
# real rows sampled 2026-08-29 and checked against ESPN; resolving any of them
# would publish the losing team at 100% in the page title.
# --------------------------------------------------------------------------
CLOSED_FROZEN_ROWS = [
    # (event_id, our_home, our_away, espn_home, espn_away)
    (15290828, 3, 1, 3, 5),   # Angels/Phillies — ours inverts the winner
    (15228873, 3, 0, 9, 10),  # Giants/Reds     — ours inverts the winner
    (15290831, 5, 6, 6, 10),  # Giants/D-backs  — frozen, direction survived
    (15290829, 0, 2, 3, 4),   # Athletics/O's   — frozen, direction survived
]


def test_closed_frozen_row_count_is_pinned():
    assert len(CLOSED_FROZEN_ROWS) == 4
    inverted = [r for r in CLOSED_FROZEN_ROWS if (r[1] > r[2]) is not (r[3] > r[4])]
    assert len(inverted) == 2, "two of four sampled closed rows invert the winner"


@pytest.mark.parametrize("event_id,hs,as_,espn_h,espn_a", CLOSED_FROZEN_ROWS)
def test_closed_events_never_resolve(event_id, hs, as_, espn_h, espn_a):
    """#1495 criterion 1 asks for `status in (completed, closed)`. It is wrong.
    This test is the reason, and it must fail if anyone widens the gate."""
    assert _resolve(status="closed", home=hs, away=as_) is None


def test_resolvable_statuses_excludes_closed():
    assert "closed" not in RESOLVABLE_STATUSES
    assert RESOLVABLE_STATUSES == frozenset({"completed"})


@pytest.mark.parametrize("status", ["scheduled", "live", "voided", "merged", "closed"])
def test_non_completed_statuses_never_resolve(status):
    assert _resolve(status=status) is None


# --------------------------------------------------------------------------
# Refusals — every one of these leaves the caller's existing behaviour alone.
# --------------------------------------------------------------------------
def test_missing_completed_at_never_resolves():
    """Nothing ever declared this game over."""
    assert _resolve(completed_at=None) is None


@pytest.mark.parametrize("hs,as_", [(None, 2), (2, None), (None, None)])
def test_missing_score_never_resolves(hs, as_):
    assert _resolve(home=hs, away=as_) is None


@pytest.mark.parametrize("bad", ["", "  ", "TBD", object()])
def test_unreadable_score_never_resolves(bad):
    assert _resolve(home=bad, away=1) is None


def test_bool_is_not_a_score():
    """`True` is an int in Python and would silently grade as 1-0."""
    assert _resolve(home=True, away=False) is None


@pytest.mark.parametrize("status", [None, 123, object()])
def test_non_string_status_never_resolves(status):
    assert _resolve(status=status) is None


def test_status_is_case_and_whitespace_tolerant():
    assert _resolve(status="Completed") is not None
    assert _resolve(status=" completed ") is not None


# --------------------------------------------------------------------------
# Draws (criterion 4) — explicit, not a fallback to the stale blend.
# --------------------------------------------------------------------------
def test_draw_resolves_explicitly_rather_than_falling_back():
    resolved = _resolve(home=1, away=1)
    assert resolved is not None
    assert resolved.result == "draw"
    assert resolved.home_probability == 0.5
    assert resolved.away_probability == 0.5
    # the distinction a bare 0.5 destroys: this 0.5 is CARRIED by a settled source
    assert resolved.source == SETTLED_HERO_SOURCE


def test_draw_is_distinguishable_from_indeterminate():
    """A 0.5 with source 'settled' and result 'draw' is an answer. A 0.5 with
    source 'blend' is the absence of one."""
    draw = _resolve(home=2, away=2)
    unknown = _resolve(status="live", home=2, away=2)
    assert draw is not None and unknown is None


# --------------------------------------------------------------------------
# Decimal / string scores — the ingest is not consistent about the wire type.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("hs,as_", [("3", "1"), (3.0, 1.0), ("3.0", "1.0")])
def test_numeric_string_scores_resolve(hs, as_):
    resolved = _resolve(home=hs, away=as_)
    assert resolved is not None and resolved.result == "home"


class TestFinishedStatusIsWiderThanResolvable:
    """CERT-1938 — the game can be OVER without us being able to name a winner.

    The two sets are deliberately different sizes, and the asymmetry is load-bearing:
    `closed` may not crown a winner from its frozen score, but it absolutely may stop
    us calling the game a live forecast. A change that collapses them in either
    direction re-opens one of the two bugs.
    """

    def test_finished_covers_completed_and_closed(self):
        assert is_finished_status("completed") is True
        assert is_finished_status("closed") is True

    def test_finished_excludes_games_still_in_play(self):
        for status in ("scheduled", "live", "postponed", "cancelled", ""):
            assert is_finished_status(status) is False, status

    def test_finished_tolerates_casing_and_whitespace(self):
        assert is_finished_status("  Completed ") is True
        assert is_finished_status("CLOSED") is True

    def test_finished_rejects_non_strings(self):
        for value in (None, 1, True, object()):
            assert is_finished_status(value) is False

    def test_the_two_sets_are_not_the_same_set(self):
        # The guard that fails if someone "tidies" one into the other.
        assert RESOLVABLE_STATUSES < FINISHED_STATUSES
        assert "closed" in FINISHED_STATUSES
        assert "closed" not in RESOLVABLE_STATUSES

    def test_closed_is_finished_but_still_never_resolves_a_hero(self):
        # 15293846's exact shape: closed, decisive scores on the row, a real
        # completion timestamp. Finished — and still not a winner we may crown.
        assert is_finished_status("closed") is True
        assert (
            resolve_settled_hero(
                status="closed",
                home_score=3,
                away_score=0,
                completed_at="2026-08-30T20:25:53.487618+00:00",
            )
            is None
        )

    def test_the_two_source_words_are_distinct(self):
        # Both exist so a reader can tell "we know the result" from "it is over and
        # we do not". Collapsing them is how a 0.5 on a finished game becomes
        # indistinguishable from a draw (#1495 criterion 4).
        assert SETTLED_HERO_SOURCE != FINAL_UNRESOLVED_SOURCE
        assert FINAL_UNRESOLVED_SOURCE != "blend"
