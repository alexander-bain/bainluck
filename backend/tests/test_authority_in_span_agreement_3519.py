"""`identity.ours_covered_in_span_pct` — agreement over the dates BOTH sides serve.

PILLAR: MATCHING. SHIP: *nothing goes blank when ESPN does* — a sport can only be
failed over to StatPal once it has cleared D50's bar, and a sport whose score is
dominated by the other provider's retention window can never clear it however
perfect the matching becomes.

`ours_covered_pct` is scored over `measurement_bounds` — our inventory for
`now ± 40 days`. Where StatPal serves a whole season (NFL, NBA, NHL) both sides
carry the same dates and the number means what it says. Where StatPal serves a
ROLLING window (MLB ~17 days, tennis ~5) our months either side of it are
counted as misses that no matching could ever have won: MLB read 23.16% on
production 2026-09-06, of which 495 of its 574 misses were dated before
StatPal's first fixture.

The in-span number asks the same question over StatPal's own span. It governs
nothing — that is a D63 amendment and Alex's — so these guards pin two things:
that it measures agreement rather than horizon, and that it CANNOT move a gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.authority_agreement import (
    GOVERNING_IDENTITY_NUMBERS,
    IDENTITY_DENOMINATORS,
    Side,
    build_agreement_row,
    governing_identity,
    timed_span,
)
from app.utils.nfl_team_matching import normalize_team


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _fixture(ref, away, home, start):
    return Side(ref=ref, home=home, away=away, start=start, label="scheduled")


def _row(ref, away, home, start):
    return Side(
        ref=str(ref), home=home, away=away, start=start, label="scheduled"
    )


def _build(fixtures, rows, sport_key="americanfootball_nfl"):
    return build_agreement_row(
        sport_key=sport_key,
        fixtures=fixtures,
        rows=rows,
        normalize=normalize_team,
    )


# A rolling provider window with our inventory reaching well past both edges —
# the MLB/tennis shape, scaled down. StatPal serves 09-10 → 09-12 only.
_SPAN_START = _utc("2026-09-10T00:00:00")


def _rolling_case():
    """3 agreed inside the span, 1 missed inside it, 4 of ours outside it."""
    fixtures = [
        _fixture("s1", "Bears", "Packers", _SPAN_START),
        _fixture("s2", "Lions", "Vikings", _SPAN_START + timedelta(days=1)),
        _fixture("s3", "Jets", "Bills", _SPAN_START + timedelta(days=2)),
    ]
    rows = [
        _row(1, "Bears", "Packers", _SPAN_START),
        _row(2, "Lions", "Vikings", _SPAN_START + timedelta(days=1)),
        _row(3, "Jets", "Bills", _SPAN_START + timedelta(days=2)),
        # Inside StatPal's span and StatPal has no such game. THE finding.
        _row(4, "Rams", "Seahawks", _SPAN_START + timedelta(days=1, hours=6)),
        # Four of ours outside the span entirely — their horizon, not a
        # disagreement. These are the 495 in the MLB case.
        _row(5, "Giants", "Cowboys", _SPAN_START - timedelta(days=30)),
        _row(6, "Eagles", "Commanders", _SPAN_START - timedelta(days=20)),
        _row(7, "Texans", "Colts", _SPAN_START - timedelta(days=10)),
        _row(8, "Broncos", "Raiders", _SPAN_START + timedelta(days=30)),
    ]
    return fixtures, rows


def test_the_in_span_number_measures_agreement_where_ours_covered_measures_horizon():
    """The defect, in one assertion pair.

    Same row, same pass: 3 of 8 of our games have a StatPal counterpart, but 4 of
    the 5 that do not are dated outside the window StatPal publishes at all. The
    published number reads 37.5% and is mostly a statement about retention; the
    in-span number reads 75% and is a statement about matching.
    """
    identity = _build(*_rolling_case())["identity"]

    assert identity["ours_covered_pct"] == 37.5  # 3 / (3 + 5)
    assert identity["ours_covered_in_span_pct"] == 75.0  # 3 / (3 + 1)

    # And the gap is exactly the horizon complement, not a rounding of it.
    assert identity["ours_only_by_horizon"] == {
        "before_statpal_first": 3,
        "inside_statpal_span": 1,
        "beyond_statpal_last": 1,
        "unplaceable": 0,
    }


def test_the_in_span_number_is_scored_on_the_inside_bucket_and_not_on_every_miss():
    """The mutant that matters: dividing by `ours_only` instead of the bucket.

    That crossing is one identifier and it reproduces the exact bug this field
    exists to fix, so the case is built with the two denominators FAR apart (4
    against 8). A case where our inventory happens to sit inside StatPal's span
    cannot fail it — the two denominators are equal there by construction, which
    is why the fixture above deliberately reaches past both edges.
    """
    identity = _build(*_rolling_case())["identity"]

    both = identity["both"]
    inside = identity["ours_only_by_horizon"]["inside_statpal_span"]
    every_miss = identity["ours_only"]

    assert inside != every_miss, "the case cannot discriminate the two denominators"
    assert identity["ours_covered_in_span_pct"] == round(
        100.0 * both / (both + inside), 2
    )
    assert identity["ours_covered_in_span_pct"] != round(
        100.0 * both / (both + every_miss), 2
    )


def test_a_sport_inside_statpals_span_reads_the_same_under_both_numbers():
    """The property that lets this ship while three clocks are running.

    NFL, NBA and NHL hold no row outside StatPal's season, so the new number is
    the old one for them and their day-2-of-7 streaks cannot be moved by this
    field existing. If this ever fails, a running clock has been redefined
    underneath it.
    """
    fixtures = [
        _fixture("s1", "Bears", "Packers", _SPAN_START),
        _fixture("s2", "Lions", "Vikings", _SPAN_START + timedelta(days=1)),
    ]
    rows = [
        _row(1, "Bears", "Packers", _SPAN_START),
        _row(2, "Rams", "Seahawks", _SPAN_START + timedelta(hours=6)),
    ]
    identity = _build(fixtures, rows)["identity"]

    assert identity["ours_only_by_horizon"]["inside_statpal_span"] == 1
    assert identity["ours_covered_pct"] == identity["ours_covered_in_span_pct"] == 50.0


def test_no_statpal_span_publishes_none_and_never_a_triumphant_hundred():
    """gotcha #53: the wrong answer here is also the most plausible one.

    With no timed StatPal fixture there is no span, every miss is `unplaceable`,
    and the in-span denominator collapses to `both`. A bare ratio would print
    100% — a perfect score — at the exact moment StatPal told us nothing. The
    honest answer is that the question has no denominator.
    """
    rows = [
        _row(1, "Bears", "Packers", _SPAN_START),
        _row(2, "Lions", "Vikings", _SPAN_START + timedelta(days=1)),
    ]
    identity = _build([], rows)["identity"]

    assert identity["both"] == 0
    assert identity["ours_only_by_horizon"]["unplaceable"] == 2
    assert identity["ours_covered_in_span_pct"] is None


def test_an_untimed_statpal_fixture_that_still_pairs_does_not_fake_a_span():
    """The same trap with `both > 0`, which is the version a bare ratio survives.

    A StatPal fixture can pair on the team pair while carrying no kickoff. Then
    `both` is 1, every miss is `unplaceable`, and `both / (both + 0)` is a clean
    100%. Only the span check refuses it.
    """
    fixtures = [_fixture("s1", "Bears", "Packers", None)]
    rows = [
        _row(1, "Bears", "Packers", _SPAN_START),
        _row(2, "Lions", "Vikings", _SPAN_START + timedelta(days=1)),
    ]
    identity = _build(fixtures, rows)["identity"]

    assert identity["both"] == 1, "the pair must still match without a kickoff"
    assert identity["ours_only_by_horizon"]["inside_statpal_span"] == 0
    assert identity["ours_covered_in_span_pct"] is None


def test_timed_span_distinguishes_no_span_from_an_instantaneous_one():
    """`None` and `(t, t)` are different facts and must not share a value."""
    assert timed_span([]) is None
    assert timed_span([_fixture("s1", "Bears", "Packers", None)]) is None

    one = _fixture("s1", "Bears", "Packers", _SPAN_START)
    assert timed_span([one]) == (_SPAN_START, _SPAN_START)


# ---------------------------------------------------------------------------
# It governs nothing. These are the guards that let it ship dark.
# ---------------------------------------------------------------------------


def test_the_new_number_governs_no_sport_today():
    """Naming a governing number is a D63 amendment and Alex's, not this file's.

    If a later change adds it to the map, this test is the one that must be
    consciously deleted — which is the point of pinning it.
    """
    named = {name for names in GOVERNING_IDENTITY_NUMBERS.values() for name in names}
    assert "ours_covered_in_span_pct" not in named


@pytest.mark.parametrize("sport_key", ["americanfootball_nfl", "basketball_nba"])
def test_the_verdict_ignores_the_new_number_however_bad_it_reads(sport_key):
    """A sport clearing on its own governing number is not dragged down by this.

    The mirror risk of shipping a second percentage onto a scored row: a reader —
    or a future refactor of `governing_identity` — treating every `*_pct` on the
    block as gating. A 0.0 here must not disturb a MEETS.
    """
    identity = {
        "both": 200,
        "statpal_only": 0,
        "ours_only": 0,
        "pct": 100.0,
        "ours_covered_pct": 100.0,
        "ours_only_by_horizon": {"inside_statpal_span": 0},
        "ours_covered_in_span_pct": 0.0,
    }
    verdict = governing_identity(sport_key, identity)

    assert verdict["gate"] == "MEETS"
    assert "ours_covered_in_span_pct" not in verdict["numbers"]
    assert "ours_covered_in_span_pct" not in verdict["values"]


def test_the_new_number_can_state_the_population_it_was_scored_on():
    """So the D63 amendment is one line, not two files (the second easy to miss).

    `IDENTITY_DENOMINATORS` is what lets a percentage publish its own
    denominator; a governing name missing from it scores NO-SCORE silently.
    """
    identity = _build(*_rolling_case())["identity"]
    denominator = IDENTITY_DENOMINATORS["ours_covered_in_span_pct"](identity)

    assert denominator == 4  # 3 agreed + 1 missed, both inside the span
    assert identity["ours_covered_in_span_pct"] == round(
        100.0 * identity["both"] / denominator, 2
    )
