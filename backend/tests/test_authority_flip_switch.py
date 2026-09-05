"""The flip switch, and the floor under the number that turns it. #2867, D50/D63.

**SHIP: the seven-day count D50 gates a source-of-record flip on is done in code
instead of by a person reading down a markdown ledger, and a percentage can no
longer clear the bar without saying how many games it was scored over.**

Three defect classes, each with its own band below:

`the denominator travels with the number`
    NBA's ledger line has read `covers=100.0%` since program step 3. Over 41
    games that is the strongest row we have; over 1 game it is arithmetic. The
    two used to render as the same six characters, and seven of them in a row
    would have read as a cleared bar. This is the lane's own recurring finding
    in its third shape — after "the row's denominator is StatPal's window, not
    our inventory" (CERT-962) and "the prediction was true by construction".

`a small day carries, it never resets`
    Every reason a day cannot be scored — StatPal unreachable, nothing to divide
    by, too few games — is a day nobody disagreed on. Resetting on those means
    the bar can only be cleared by seven consecutive busy days, which is a bar
    nobody set. Only `BELOW` resets.

`the switch refuses for the RIGHT reason`
    "Not yet" has four meanings and three of them are not waits: no id join, no
    governing number ruled, a real streak short of seven, and a broken streak.
    Collapsing them into `False` is how MLB spent a day being waited on when
    what it needed was a ruling.
"""

import pytest

from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    DEFAULT_AUTHORITY,
    ESPN,
    FLIP_EVIDENCE,
    STATPAL,
    authority_for,
    flip_permitted,
)
from app.utils.authority_agreement import (
    FLIP_BAR_PCT,
    FLIP_STREAK_DAYS,
    GATE_BELOW,
    GATE_MEETS,
    GATE_NO_SCORE,
    GATE_PENDING,
    GATE_TOO_FEW,
    GOVERNING_IDENTITY_NUMBERS,
    IDENTITY_DENOMINATORS,
    MINIMUM_SCORED_DENOMINATOR,
    READ_FAILED,
    SHADOW_STAMPERS,
    governing_identity,
    streak_from_gates,
)


def _identity(*, both: int, statpal_only: int = 0, ours_only: int = 0) -> dict:
    """The three counts a governing verdict is built from, with both percentages.

    Built with the same arithmetic `_identity_block` uses so a test can state a
    population in games rather than in percentages — the bug under test is
    precisely a percentage that has lost its population.
    """
    union = both + statpal_only + ours_only
    ours = both + ours_only
    return {
        "both": both,
        "statpal_only": statpal_only,
        "ours_only": ours_only,
        "pct": round(both / union * 100, 2) if union else None,
        "ours_covered_pct": round(both / ours * 100, 2) if ours else None,
    }


# ---------------------------------------------------------------------------
# the denominator travels with the number
# ---------------------------------------------------------------------------


def test_one_game_at_100_pct_does_not_meet_the_bar():
    """The catching test named in authority/023, fixed under either answer to #3071.

    A single game either agrees or does not: 100% or 0%, with no third
    possibility. Whatever minimum denominator Alex rules, it is not one — so
    refusing this case commits to nothing and closes the case where the bar is
    cleared by arithmetic rather than by agreement.
    """
    verdict = governing_identity("basketball_nba", _identity(both=1))

    assert verdict["values"]["ours_covered_pct"] == 100.0
    assert verdict["gate"] == GATE_TOO_FEW
    assert verdict["gate"] != GATE_MEETS
    assert verdict["denominators"]["ours_covered_pct"] == 1


def test_a_too_small_day_is_not_reported_as_a_disagreement():
    """TOO-FEW must not be BELOW.

    Both are "did not advance", and only one of them means somebody was wrong
    about a game. Collapsing them would file a quiet Tuesday as a matching
    defect and reset a streak that nothing contradicted.
    """
    verdict = governing_identity("basketball_nba", _identity(both=1))

    assert verdict["gate"] != GATE_BELOW
    assert str(MINIMUM_SCORED_DENOMINATOR) in verdict["why"]
    assert "#3071" in verdict["why"], (
        "the row must say the real floor is unruled; a bare refusal reads as a "
        "settled policy nobody set (D55: the gap tags loudly)"
    )


def test_every_governing_number_publishes_the_denominator_it_was_scored_on():
    """A percentage with no population beside it is the finding, not the number.

    NFL's real 2026-09-04 pass: 320 in both, one each side. It reads 99.38 /
    99.69 and is BELOW by 0.12 — a genuine miss on a real population, which is
    the case that must keep being scored normally once a floor exists.
    """
    verdict = governing_identity(
        "americanfootball_nfl", _identity(both=320, statpal_only=1, ours_only=1)
    )

    assert verdict["gate"] == GATE_BELOW, "a real miss must still be a miss"
    assert verdict["gate"] != GATE_TOO_FEW
    # NFL is scored on both numbers, and they have DIFFERENT denominators: the
    # union (322) and the games we list (321). A single shared denominator field
    # would be wrong for one of them on every NFL row ever published.
    assert verdict["denominators"] == {"pct": 322, "ours_covered_pct": 321}
    assert set(verdict["denominators"]) == set(verdict["numbers"])


def test_the_two_denominators_are_not_the_same_number():
    """Guards the pair above against a refactor that shares one denominator.

    Stated as its own test because `{"pct": 322, "ours_covered_pct": 321}` is a
    literal, and a literal can be updated to match a regression. This asserts
    the RELATIONSHIP: StatPal-only games are in one denominator and not the
    other, which is the whole reason the row carries two numbers.
    """
    identity = _identity(both=10, statpal_only=5, ours_only=2)
    verdict = governing_identity("americanfootball_nfl", identity)

    assert verdict["denominators"]["pct"] == 17
    assert verdict["denominators"]["ours_covered_pct"] == 12
    assert (
        verdict["denominators"]["pct"] - verdict["denominators"]["ours_covered_pct"]
        == identity["statpal_only"]
    )


def test_every_governing_number_can_say_its_denominator():
    """A number added to D63's map without one scores nothing, and CI says so first.

    `_denominator_of` returns `None` for an unknown name and `None` lands in
    NO-SCORE rather than being waved through. That is the runtime behaviour; this
    is the build-time one, because a sport silently stuck on NO-SCORE for weeks
    is a streak that never starts and nobody notices.
    """
    named = {name for names in GOVERNING_IDENTITY_NUMBERS.values() for name in names}
    missing = sorted(named - set(IDENTITY_DENOMINATORS))
    assert not missing, (
        f"{missing} govern a sport's flip and have no entry in "
        "IDENTITY_DENOMINATORS, so their rows would publish a percentage with "
        "no population and score nothing"
    )


def test_an_unteachable_governing_number_scores_nothing_rather_than_meeting():
    """The runtime half of the test above: unknown denominator, no MEETS."""
    identity = _identity(both=50)
    identity["invented_pct"] = 100.0
    verdict = governing_identity("basketball_nba", identity)
    assert verdict["gate"] == GATE_MEETS  # baseline: the real number does clear

    from app.utils import authority_agreement as aa

    original = aa.GOVERNING_IDENTITY_NUMBERS["basketball_nba"]
    aa.GOVERNING_IDENTITY_NUMBERS["basketball_nba"] = ("invented_pct",)
    try:
        verdict = aa.governing_identity("basketball_nba", identity)
    finally:
        aa.GOVERNING_IDENTITY_NUMBERS["basketball_nba"] = original

    assert verdict["gate"] == GATE_NO_SCORE
    assert verdict["denominators"] == {"invented_pct": None}


def test_the_ledger_line_prints_the_denominator_beside_the_percentage():
    """`gate=MEETS(covers=100.0%)` is the line that could not be read."""
    from app.utils.authority_agreement import _gate_text

    identity = _identity(both=41)
    identity["governing"] = governing_identity("basketball_nba", identity)
    line = _gate_text(identity)

    assert "100.0%/41" in line, f"denominator missing from the ledger token: {line}"
    assert line.startswith(GATE_MEETS)


# ---------------------------------------------------------------------------
# a small day carries, it never resets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "carried", [GATE_NO_SCORE, GATE_TOO_FEW, GATE_PENDING, READ_FAILED]
)
def test_an_unscorable_day_carries_the_streak_rather_than_resetting_it(carried):
    """Four ways a day says nothing, and none of them is a disagreement.

    `READ_FAILED` is in here because it is NOT a gate state — a failed read
    returns before `governing_identity` is ever called — and a counter that only
    understands gate states would reset a six-day streak the morning StatPal 500s.
    """
    gates = [GATE_MEETS, GATE_MEETS, carried, GATE_MEETS]
    assert streak_from_gates(gates) == 3


def test_a_day_below_the_bar_resets_the_streak():
    gates = [GATE_MEETS] * 6 + [GATE_BELOW]
    assert streak_from_gates(gates) == 0
    assert streak_from_gates(gates + [GATE_MEETS]) == 1


def test_the_streak_is_the_tail_not_the_best_run():
    """Six good days, one bad, one good is 1 — not 6, and not 7."""
    gates = [GATE_MEETS] * 6 + [GATE_BELOW, GATE_MEETS]
    assert streak_from_gates(gates) == 1


def test_an_unrecognised_gate_state_resets():
    """A state this counter has not been taught is not evidence of agreement."""
    assert streak_from_gates([GATE_MEETS] * 7 + ["SOMETHING-NEW"]) == 0


def test_no_days_is_not_a_streak():
    assert streak_from_gates([]) == 0


def test_a_carried_day_cannot_manufacture_a_seventh():
    """Six MEETS and a quiet day is six, not seven.

    Carrying means "leave it as it was", and the cheapest way to get this wrong
    is to skip the day and then count the list's length.
    """
    assert streak_from_gates([GATE_MEETS] * 6 + [GATE_NO_SCORE]) == 6


# ---------------------------------------------------------------------------
# the switch refuses for the RIGHT reason
# ---------------------------------------------------------------------------


def test_nothing_has_flipped():
    """The whole switch is dark, and CI is where that stops being true quietly."""
    flipped = sorted(k for k, v in AUTHORITY_BY_SPORT.items() if v != ESPN)
    assert not flipped, (
        f"{flipped} are set to a non-ESPN authority. A flip is Alex's under D50 "
        "and needs a YOUR-TURN entry he has seen; it does not arrive in a diff"
    )
    assert DEFAULT_AUTHORITY == ESPN


def test_a_flipped_sport_must_carry_its_evidence():
    """The one-line change brings its receipts, or CI stops it.

    This is the test that makes `FLIP_EVIDENCE` load-bearing rather than a
    comment. It passes vacuously today — nothing is flipped — and it is the
    reason the day something IS flipped cannot also be the day the evidence is
    left for later.
    """
    for sport_key, authority in AUTHORITY_BY_SPORT.items():
        if authority != STATPAL:
            continue
        evidence = FLIP_EVIDENCE.get(sport_key)
        assert evidence, f"{sport_key} is flipped with no FLIP_EVIDENCE entry"
        assert evidence.get("your_turn"), (
            f"{sport_key} names no YOUR-TURN entry; D50's second half is not "
            "optional and not checkable anywhere else"
        )
        permitted, why = flip_permitted(sport_key, evidence.get("days") or [])
        assert permitted, f"{sport_key} is flipped but its own evidence says: {why}"


def test_an_unknown_sport_key_resolves_to_espn_and_does_not_raise():
    """A typo is a bug to find, never a reason for a surface to change provider."""
    assert authority_for("baseball_kbo") == ESPN
    assert authority_for("") == ESPN
    assert authority_for(None) == ESPN


def test_a_sport_with_no_shadow_stamper_is_refused_as_a_build_not_a_wait():
    permitted, why = flip_permitted("soccer_epl", [GATE_MEETS] * 10)
    assert not permitted
    assert "no shadow stamper" in why
    assert "not a wait" in why


def test_a_sport_with_no_governing_number_is_refused_as_a_ruling_not_a_wait():
    """MLB, today. Ten perfect days would not move it, and the reason must say so."""
    assert "baseball_mlb" in SHADOW_STAMPERS
    assert not GOVERNING_IDENTITY_NUMBERS.get("baseball_mlb")

    permitted, why = flip_permitted("baseball_mlb", [GATE_MEETS] * 10)
    assert not permitted
    assert "governing identity number" in why
    assert "not more days" in why


def test_a_short_streak_is_refused_as_a_wait_and_says_how_far_along():
    permitted, why = flip_permitted("basketball_nba", [GATE_MEETS] * 6)
    assert not permitted
    assert f"6/{FLIP_STREAK_DAYS}" in why
    assert "not a defect" in why


def test_seven_days_permits_the_measured_half_and_says_the_other_half_is_alex():
    permitted, why = flip_permitted("basketball_nba", [GATE_MEETS] * FLIP_STREAK_DAYS)
    assert permitted
    assert "YOUR-TURN" in why
    assert str(FLIP_BAR_PCT) in why


def test_seven_days_of_too_few_does_not_permit_a_flip():
    """The two halves of this ship meeting: a week of 1-game days is not a week.

    Each of these days would have read `MEETS(covers=100.0%)` before the floor
    existed, and seven of them is exactly the shape of a cleared bar. This is
    the end-to-end statement — the gate refuses the day, and the counter refuses
    to build a streak out of days it refused.
    """
    day = governing_identity("basketball_nba", _identity(both=1))["gate"]
    assert day == GATE_TOO_FEW

    permitted, why = flip_permitted("basketball_nba", [day] * FLIP_STREAK_DAYS)
    assert not permitted
    assert f"0/{FLIP_STREAK_DAYS}" in why


def test_todays_real_nba_and_nhl_populations_still_clear_the_floor():
    """The floor closes the degenerate case and nothing else.

    NBA read 41/41 and NHL 32/32 on 2026-09-04. Both are under whatever #3071
    eventually rules, quite possibly — and this ship does not pre-empt that. If a
    later edit raises `MINIMUM_SCORED_DENOMINATOR` to a guessed floor, this fails
    and sends the guesser to Alex.
    """
    for sport_key, both in (("basketball_nba", 41), ("icehockey_nhl", 32)):
        verdict = governing_identity(sport_key, _identity(both=both))
        assert verdict["gate"] == GATE_MEETS, (
            f"{sport_key}'s measured {both}-game population no longer scores; "
            "the minimum denominator is #3071's and is Alex's to rule"
        )
