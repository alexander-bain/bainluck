"""D63: which of identity's two numbers decides a sport's flip.

D63 = A (Alex, 2026-09-04): *"NBA/NHL seven-day agreement = 'of the games WE
list, StatPal has them'; NFL symmetric."*

`identity` has always been the governing BUCKET, against `schedule` and
`anchors`. What it did not say is which of its own two numbers a sport is scored
on, and the answer is not the same for every sport:

* ``pct`` divides by the UNION of both sides. It only means anything where both
  sides publish the same population.
* ``ours_covered_pct`` divides by the games WE list. It is the question Alex's
  bar actually asks, and the only reachable one where StatPal publishes a whole
  season on day one and we ingest a rolling odds-driven slice.

NFL measured 99.69 against 99.38 on 9/4 — symmetric, so both govern and asking
both is free. NBA and NHL measured 100.00 against 3.40. Before D63 the ledger
scored them on `pct`, which is a bar no NBA row could ever clear for a reason
that is not a disagreement about a single game.

## what each test here can fail on

* NBA or NHL being scored on the union number again, which silently restores an
  unreachable bar (spec rule 5's failure mode, and the whole of what D63 fixes);
* NFL quietly dropping to one number, throwing away a real signal on the one
  sport where both questions are answerable;
* a sport with no ruling being scored by a default — the half-configured sport
  `LeagueSpec` exists to forbid, and D55's "explicit or absent, never inferred";
* an unscored number (`None`, spec rule 6) being compared against the bar and
  resetting a streak that should only pause (gotcha #53);
* `NO-SCORE` and `BELOW` rendering alike in the ledger line, which would be a
  check whose pass and fail look the same;
* the published number and the verdict beside it disagreeing, which is what
  happens the moment they are derived twice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.authority_agreement import (
    FLIP_BAR_PCT,
    GATES_CARRY_STREAK,
    GATE_BELOW,
    GATE_MEETS,
    GATE_NO_SCORE,
    GATE_PENDING,
    GOVERNING_IDENTITY_NUMBERS,
    SHADOW_STAMPERS,
    Side,
    build_agreement_row,
    governing_identity,
    ledger_line,
)
from app.utils.nfl_team_matching import normalize_team

KICKOFF = datetime(2026, 12, 27, 18, 0, tzinfo=timezone.utc)


def _fixture(ref, away, home, start):
    return Side(ref=ref, home=home, away=away, start=start, label="Regular Season")


def _row(ref, away, home, start, held_id=None):
    return Side(
        ref=str(ref), home=home, away=away, start=start, label="scheduled", held_id=held_id
    )


def _build(sport_key, fixtures, rows):
    return build_agreement_row(
        sport_key=sport_key,
        fixtures=fixtures,
        rows=rows,
        normalize=normalize_team,
    )


def _season_against_a_slice(sport_key):
    """Production's shape: StatPal publishes a season, we list two games of it.

    Both of ours are in StatPal, so `ours_covered_pct` is a clean 100. The union
    number is 2/6 = 33.33 — not a disagreement about any game, just the two
    sides carrying different populations. This is NBA and NHL every morning.
    """
    fixtures = [
        _fixture("1050110", "Boston Celtics", "Detroit Pistons", KICKOFF),
        _fixture("1050111", "Miami Heat", "Toronto Raptors", KICKOFF + timedelta(hours=2)),
        _fixture("1050112", "Chicago Bulls", "New York Knicks", KICKOFF + timedelta(days=3)),
        _fixture("1050113", "Phoenix Suns", "Denver Nuggets", KICKOFF + timedelta(days=9)),
        _fixture("1050114", "Utah Jazz", "Sacramento Kings", KICKOFF + timedelta(days=15)),
        _fixture("1050115", "Orlando Magic", "Atlanta Hawks", KICKOFF + timedelta(days=21)),
    ]
    rows = [
        _row(1, "Boston Celtics", "Detroit Pistons", KICKOFF),
        _row(2, "Miami Heat", "Toronto Raptors", KICKOFF + timedelta(hours=2)),
    ]
    return _build(sport_key, fixtures, rows)


# ---------------------------------------------------------------------------
# The reversal itself.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport_key", ["basketball_nba", "icehockey_nhl"])
def test_nba_and_nhl_are_scored_on_the_games_we_list_and_not_on_the_union(sport_key):
    """The bar has to be reachable on a day where nothing disagrees.

    Every game we list is in StatPal here. Under D63 that is a clearing day. If
    this sport is ever scored on `pct` again it reads 33.33% and the day resets
    a streak on a morning where the two sides agreed about every game we hold.
    """
    identity = _season_against_a_slice(sport_key)["identity"]

    assert identity["ours_covered_pct"] == 100.0
    # Published, and deliberately awful-looking. The gap between the two IS the
    # finding, so it is never blended away (spec rule 2).
    assert identity["pct"] == 33.33

    governing = identity["governing"]
    assert governing["numbers"] == ["ours_covered_pct"]
    assert governing["gate"] == GATE_MEETS
    # The union number is not merely outweighed — it is not consulted. A
    # "governing" list that still contained it would clear only by arithmetic
    # luck on days when both happen to be high.
    assert "pct" not in governing["values"]


def test_nfl_is_scored_on_both_numbers_because_both_sides_carry_one_population():
    """Where the two questions have the same answer, asking both is free.

    NFL measured 99.69 against 99.38 on 9/4. Dropping to one number would throw
    away a real signal on the only sport where the union denominator means
    something.
    """
    governing = _season_against_a_slice("americanfootball_nfl")["identity"]["governing"]

    assert governing["numbers"] == ["pct", "ours_covered_pct"]
    # And it bites: NFL does NOT clear on the same numbers NBA clears on,
    # because for NFL the union really is a population disagreement.
    assert governing["gate"] == GATE_BELOW
    assert "pct" in governing["why"]


def test_a_sport_with_no_ruling_cannot_clear_the_bar_and_says_so():
    """The half-configured sport, refused.

    MLB joins the shadow at program step 5 and has never produced a row, so
    which of its two numbers should decide is UNMEASURED. Under D55 the answer
    is explicit or it is absent — never inferred from a plausible-looking
    neighbour. So the gate refuses, loudly, and both numbers are still
    published for whoever measures it.
    """
    identity = _season_against_a_slice("baseball_mlb")["identity"]

    # Both numbers are there to be read...
    assert identity["pct"] == 33.33
    assert identity["ours_covered_pct"] == 100.0
    # ...and neither of them advances anything.
    governing = identity["governing"]
    assert governing["gate"] == GATE_PENDING
    assert governing["numbers"] == []
    assert "baseball_mlb" in governing["why"]
    # A 100% number sitting in the row must not be mistakable for a clearing
    # day just because it is high.
    assert governing["gate"] != GATE_MEETS


def test_every_sport_with_a_governing_number_is_a_sport_we_actually_stamp():
    """A ruling about a sport nothing writes a correspondence for is a ruling
    about nothing — and the reverse gap is the one that must stay legible.

    `SHADOW_STAMPERS` is allowed to run ahead: a sport joins the shadow dark,
    then earns its governing number from its first rows. That is MLB today. What
    is NOT allowed is a governing number for a sport with no stamper, because
    that would score a streak on a correspondence nobody writes.
    """
    assert set(GOVERNING_IDENTITY_NUMBERS) <= set(SHADOW_STAMPERS)


# ---------------------------------------------------------------------------
# The three not-advancing states, kept apart.
# ---------------------------------------------------------------------------


def test_an_unscored_number_pauses_the_streak_and_never_resets_it():
    """`None` is not a low score, and comparing it to the bar is the bug.

    We list nothing, so "of the games we list, does StatPal have them" has no
    denominator. A day like that proves nothing about StatPal in either
    direction: it must not reset a streak, and it must not advance one either.
    """
    identity = _build(
        "americanfootball_nfl",
        [_fixture("280497", "Arizona Cardinals", "Las Vegas Raiders", KICKOFF)],
        [],
    )["identity"]

    assert identity["ours_covered_pct"] is None
    governing = identity["governing"]
    assert governing["gate"] == GATE_NO_SCORE
    assert governing["gate"] in GATES_CARRY_STREAK
    # Distinct from the measured failure. If these ever collapse into one state,
    # an empty morning starts resetting seven days of real agreement.
    assert GATE_BELOW not in GATES_CARRY_STREAK
    assert GATE_MEETS not in GATES_CARRY_STREAK


def test_a_sport_does_not_half_clear_a_bar():
    """One unscored governing number makes the whole verdict unscored.

    The tempting alternative — score the numbers you can and ignore the rest —
    would let NFL advance on `pct` alone on exactly the days its other number
    went missing, which is to say it would silently become NBA's rule on the
    sport that least needs it.
    """
    verdict = governing_identity(
        "americanfootball_nfl", {"pct": 100.0, "ours_covered_pct": None}
    )
    assert verdict["gate"] == GATE_NO_SCORE
    assert verdict["values"] == {"pct": 100.0, "ours_covered_pct": None}


def test_the_bar_is_inclusive_at_its_own_boundary():
    """Rule 1 says "≥99.5%", so 99.5 clears and 99.49 does not.

    Written down because an off-by-one at the boundary of a seven-day gate is a
    week of lost progress that looks exactly like a real disagreement.
    """
    assert governing_identity("basketball_nba", {"ours_covered_pct": FLIP_BAR_PCT})[
        "gate"
    ] == GATE_MEETS
    assert governing_identity("basketball_nba", {"ours_covered_pct": 99.49})[
        "gate"
    ] == GATE_BELOW


# ---------------------------------------------------------------------------
# What the bus actually reads.
# ---------------------------------------------------------------------------


def test_the_ledger_line_carries_the_verdict_so_the_bus_never_picks_a_number():
    """D46's pattern: the app scores it, the bus reads it.

    A bus operator holding two percentages and a remembered bar is a bus
    operator who can score NBA on the wrong question — which is the situation
    D63 exists to end.
    """
    row = _season_against_a_slice("basketball_nba")
    line = ledger_line(row, day="2026-09-04", streak="1/7")

    # Both numbers still printed — the pair is the finding.
    assert "identity=33.33%" in line
    assert "covers=100.0%" in line
    # And the verdict, naming the number it was decided on, so the line cannot
    # be read as scoring the 33.33.
    assert "gate=MEETS(ours_covered_pct=100.0% vs 99.5%)" in line


def test_pending_and_below_do_not_render_alike_in_the_ledger():
    """Two lines a reader must never confuse: "we have not ruled on this sport"
    and "this sport measured under the bar"."""
    pending = ledger_line(
        _season_against_a_slice("baseball_mlb"), day="2026-09-04", streak="0/7"
    )
    below = ledger_line(
        _season_against_a_slice("americanfootball_nfl"), day="2026-09-04", streak="0/7"
    )

    assert f"gate={GATE_PENDING}" in pending
    assert GATE_BELOW in below
    assert GATE_PENDING not in below
    # The pending line carries no percentage in its gate field at all: there is
    # no number to show, and showing one would invite it being read as a score.
    assert "vs 99.5%" not in pending.split("gate=")[1].split("|")[0]


def test_the_verdict_is_computed_from_the_numbers_the_row_publishes():
    """Derived once, not twice.

    A verdict built from a second, parallel computation of `pct` is a verdict
    that can contradict the figure printed beside it — and the contradiction
    would surface as a flip granted on a number nobody can find in the row.
    """
    identity = _season_against_a_slice("americanfootball_nfl")["identity"]
    governing = identity["governing"]

    for name in governing["numbers"]:
        assert governing["values"][name] == identity[name]
