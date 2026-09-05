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
    nobody set. Only `BELOW` resets. The WALK itself is
    `authority_streak.compute_streak` (authority/021) and is tested in its own
    file; what is tested here is the seam — that a state added to the gate
    constants actually reaches that walk as a carrying one.

`the switch refuses for the RIGHT reason`
    "Not yet" has five meanings and only one is a defect: no id join, no
    governing number ruled, no ledger at all, a real streak short of seven, and
    a broken streak. Collapsing them into `False` is how MLB spent a day being
    waited on when what it needed was a ruling.
"""

from app.config import authority_by_sport as abs_module
from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    DEFAULT_AUTHORITY,
    DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE,
    DISCOVERY_SCHEDULED_SPORTS,
    ESPN,
    FLIP_EVIDENCE,
    STATPAL,
    authority_for,
    flip_permitted,
)
from app.utils.authority_agreement import (
    FLIP_BAR_PCT,
    GATE_BELOW,
    GATE_MEETS,
    GATE_NO_SCORE,
    GATE_TOO_FEW,
    GOVERNING_IDENTITY_NUMBERS,
    IDENTITY_DENOMINATORS,
    MINIMUM_SCORED_DENOMINATOR,
    SHADOW_STAMPERS,
    governing_identity,
)
from app.utils.authority_streak import REQUIRED_STREAK_DAYS


def _day(day: str, state: str) -> dict:
    """One durable-ledger day entry, in the only two fields the walk reads.

    Deliberately not built by `authority_streak.day_entry`: that function is the
    producer and `compute_streak` is the consumer, and driving both ends from one
    helper would hide a disagreement between them rather than surface it.
    """
    return {"day": day, "state": state}


def _run_of(n: int, state: str) -> list[dict]:
    """`n` CONSECUTIVE days ending 2026-09-30, all in one state.

    Consecutive on purpose: `compute_streak` stops at a day with no stored row,
    so a list of `n` entries with gaps in the dates is not a streak of `n` and a
    helper that produced one would make every test below quietly weaker.
    """
    from datetime import date, timedelta

    end = date(2026, 9, 30)
    return [
        _day((end - timedelta(days=n - 1 - i)).isoformat(), state) for i in range(n)
    ]


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
#
# The WALK is `authority_streak.compute_streak`, which shipped with
# authority/021 and is tested in `test_authority_streak.py`. Nothing here
# re-tests it. What is tested here is the one thing that changed: `TOO-FEW-TO-SCORE`
# is a NEW day-state, and it reaches that walk through `GATES_CARRY_STREAK`.
# A fifth state that the walk has never been taught does not carry — it stops
# the walk by name (D55) — so the two modules agreeing about it is a real seam.
# ---------------------------------------------------------------------------


def test_the_new_gate_state_reaches_the_streak_walk_as_a_carrying_day():
    """The seam. `DAY_STATES_CARRY` is built from `GATES_CARRY_STREAK`.

    If `TOO-FEW-TO-SCORE` had been added without going into that frozenset, the
    walk would have hit `else` and stopped by name — a six-day streak ended by a
    quiet Tuesday. That is the correct failure for an unknown state and the wrong
    one for this state, and only this test can tell them apart.
    """
    from app.utils.authority_streak import DAY_STATES_CARRY

    assert GATE_TOO_FEW in DAY_STATES_CARRY
    assert GATE_BELOW not in DAY_STATES_CARRY
    assert GATE_MEETS not in DAY_STATES_CARRY


def test_a_too_few_day_neither_advances_nor_resets_a_real_streak():
    """End to end through the shipped walk, not through a reimplementation."""
    from app.utils.authority_streak import compute_streak

    days = [
        _day("2026-09-01", GATE_MEETS),
        _day("2026-09-02", GATE_MEETS),
        _day("2026-09-03", GATE_TOO_FEW),
        _day("2026-09-04", GATE_MEETS),
    ]
    streak = compute_streak(days)

    assert streak["days"] == 3
    assert "2026-09-03" in streak["carried_days"]


def test_the_summary_and_the_streak_counter_agree_on_seven():
    """Two modules, one seven.

    `REQUIRED_STREAK_DAYS` cannot live in `authority_agreement` — `authority_streak`
    imports that module, so the constant would sit upstream of its own owner. The
    summary therefore carries a literal, and this is what stops the two drifting.
    """
    from app.utils.authority_agreement import FLIP_GATE_SUMMARY

    assert f"{REQUIRED_STREAK_DAYS} consecutive daily rows" in FLIP_GATE_SUMMARY


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
    permitted, why = flip_permitted("soccer_epl", _run_of(10, GATE_MEETS))
    assert not permitted
    assert "no shadow stamper" in why
    assert "not a wait" in why


def test_a_sport_with_no_governing_number_is_refused_as_a_ruling_not_a_wait():
    """MLB, today. Ten perfect days would not move it, and the reason must say so."""
    assert "baseball_mlb" in SHADOW_STAMPERS
    assert not GOVERNING_IDENTITY_NUMBERS.get("baseball_mlb")

    permitted, why = flip_permitted("baseball_mlb", _run_of(10, GATE_MEETS))
    assert not permitted
    assert "governing identity number" in why
    assert "not more days" in why


def test_a_sport_with_no_ledger_is_refused_as_not_measured():
    """An empty ledger has never been held to the bar.

    `compute_streak` returns `None` here, deliberately, and reporting that as
    "0/7 consecutive days" would describe a sport that FAILED a bar nobody ever
    applied to it. Gotcha #53 at the flip gate.
    """
    permitted, why = flip_permitted("basketball_nba", [])
    assert not permitted
    assert "not measured" in why
    assert "0/" not in why


def test_a_short_streak_is_refused_as_a_wait_and_says_how_far_along():
    permitted, why = flip_permitted("basketball_nba", _run_of(6, GATE_MEETS))
    assert not permitted
    assert f"6/{REQUIRED_STREAK_DAYS}" in why
    assert "not a defect" in why


def test_seven_days_permits_the_measured_half_and_says_the_other_half_is_alex():
    permitted, why = flip_permitted(
        "basketball_nba", _run_of(REQUIRED_STREAK_DAYS, GATE_MEETS)
    )
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

    permitted, why = flip_permitted(
        "basketball_nba", _run_of(REQUIRED_STREAK_DAYS, day)
    )
    assert not permitted
    assert f"0/{REQUIRED_STREAK_DAYS}" in why


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


# ---------------------------------------------------------------------------
# Agreement is not coverage. lane1, 2026-09-05, reviewing this lane's step-7
# handoff; their PR #3178 pins the beat-side half of the same invariant.
# ---------------------------------------------------------------------------


def test_the_discovery_list_is_the_beat_schedules_own_list():
    """The switch's idea of "discoverable" must be the scheduler's, or it rots.

    `DISCOVERY_SCHEDULED_SPORTS` is written out longhand rather than derived at
    import time, because `app.config` importing `app.tasks` is a circular-import
    hazard this repo has paid for (gotcha #3 is the standing version of it). The
    cost of writing it out is that it can drift from the thing it describes, and
    the drift is silent and one-directional in the dangerous way: adding a
    `sync-statpal-schedules-tennis` beat is a happy moment, nobody thinks about a
    config in `app/config/`, and a tennis flip becomes permissible on an
    agreement streak that never had to find a single fixture ESPN missed.

    So the test derives the set the switch refuses to derive. It fails in BOTH
    directions on purpose — a beat with no entry here, and an entry here with no
    beat — because the second one is the worse bug: it permits.
    """
    from app.tasks import celery_app

    scheduled = {
        entry["kwargs"]["sport_key"]
        for entry in celery_app.conf.beat_schedule.values()
        if entry["task"] == "app.tasks.sync_statpal_schedules"
        and (entry.get("kwargs") or {}).get("sport_key")
    }

    assert not (set(DISCOVERY_SCHEDULED_SPORTS) - scheduled), (
        "listed as discoverable with no beat at all: "
        f"{sorted(set(DISCOVERY_SCHEDULED_SPORTS) - scheduled)}. This is the "
        "direction that PERMITS — a flip on an agreement streak that never had to "
        "find a single fixture ESPN missed"
    )
    accounted = set(DISCOVERY_SCHEDULED_SPORTS) | set(
        DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE
    )
    assert scheduled <= accounted, (
        "on the discovery beat and in neither list: "
        f"{sorted(scheduled - accounted)}. A beat is either working (list it in "
        "`DISCOVERY_SCHEDULED_SPORTS`) or broken (name it, with the reason, in "
        "`DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE`). Silently absent is the state "
        "this pair of constants exists to make impossible"
    )
    assert not (
        set(DISCOVERY_SCHEDULED_SPORTS) & set(DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE)
    ), "a sport cannot be both discoverable and named as not discovering"


def test_a_listed_sport_actually_parses_and_an_excluded_one_actually_does_not():
    """CERT-1875's finding, pinned: a beat is not a discovery path.

    The first version of this file listed NFL because
    `sync-statpal-schedules-nfl` runs hourly. It does — and it creates nothing.
    `get_fixtures("nfl")` walks `_extract_match_items`, which knows
    `tournament.match` and `tournament.week`; the real NFL payload nests its games
    two levels deeper, under `stage[] → week[] → matches → match`. On the pinned
    payload — which retains 17 of the season's matches — the authority parser reads
    17 and the ingest parser reads 0. Zero rows, every hour, green.

    The count quoted is the FIXTURE's, not the season's. A full-census number
    beside a reduced-fixture measurement is how a figure ends up attributed to a
    file that never held it, and this test's whole value is that its numbers are
    the ones it actually read. Meanwhile the AUTHORITY read path
    (`_parse_nfl_season_schedule`) reads the same bytes correctly, which is why
    NFL's agreement row says 99.69% and its seven-day clock is running. Two
    parsers over one payload, one of them blind, and the blind one is the only one
    that writes.

    So membership is proven against the ingest chain's own parser on each sport's
    pinned real payload — never against the existence of a beat, and never against
    the parser the authority path happens to use.

    The exclusion assertion is the half that retires itself: the day somebody
    teaches the ingest parser the stage nesting, NFL starts parsing, this test
    fails, and its message says to move NFL into `DISCOVERY_SCHEDULED_SPORTS`.
    """
    import json
    from pathlib import Path

    from app.services.statpal_api import StatPalAPIService
    from app.tasks.config import STATPAL_SPORT_MAPPING

    pinned = {
        "basketball_nba": "statpal_nba_season_schedule_20260904.json",
        "icehockey_nhl": "statpal_nhl_season_schedule_20260904.json",
        "baseball_mlb": "statpal_mlb_season_schedule_20260904.json",
        "americanfootball_nfl": "statpal_nfl_season_schedule_20260903.json",
    }
    service = StatPalAPIService.__new__(StatPalAPIService)

    def _ingest_parse(sport_key: str) -> int:
        path = Path(__file__).parent / "fixtures" / pinned[sport_key]
        assert path.exists(), f"no pinned payload for {sport_key} at {path}"
        payload = json.loads(path.read_text())
        # The exact call the CREATING path makes: sync_statpal_schedules ->
        # get_fixtures(sport) -> _parse_fixtures(data, sport).
        return len(
            StatPalAPIService._parse_fixtures(
                service, payload, STATPAL_SPORT_MAPPING[sport_key]
            )
        )

    for sport_key in sorted(DISCOVERY_SCHEDULED_SPORTS):
        assert _ingest_parse(sport_key) > 0, (
            f"{sport_key} is listed as discoverable, but the ingest parser reads "
            "ZERO fixtures out of its real pinned payload — the beat runs and "
            "creates nothing, which is precisely the mistake CERT-1875 struck"
        )

    for sport_key in sorted(DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE):
        assert _ingest_parse(sport_key) == 0, (
            f"{sport_key} now parses out of its pinned payload — the ingest path "
            "has been fixed. Move it into `DISCOVERY_SCHEDULED_SPORTS` and delete "
            "its entry from `DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE`; the flip "
            "gate is refusing a sport that can now discover games"
        )


def test_nfl_cannot_be_flipped_today_and_its_running_clock_does_not_change_that():
    """The ship of CERT-1875's repair, stated where it bites.

    NFL's seven-day clock started 2026-09-05 and reads MEETS at 99.69%. Before
    this repair, seven of those days would have returned `permitted=True` for a
    sport whose event-creating path has never created an event. It now refuses,
    by name, with the beat's own failure quoted into the reason.
    """
    assert "americanfootball_nfl" in SHADOW_STAMPERS
    assert GOVERNING_IDENTITY_NUMBERS.get("americanfootball_nfl")

    permitted, why = flip_permitted(
        "americanfootball_nfl", _run_of(REQUIRED_STREAK_DAYS, GATE_MEETS)
    )

    assert not permitted
    assert "no working StatPal discovery pass" in why
    assert "creates nothing" in why, (
        "the refusal must quote the actual failure; a generic 'no discovery pass' "
        "reads as 'nobody built it yet' for a sport where somebody did"
    )
    assert "not a wait" in why


def _nfl_pinned_parser_counts() -> tuple[int, int]:
    """(authority, ingest) fixture counts, re-derived by importing the shipped code.

    Never carried from a scratch script or from the prose it is checking. The
    whole point of the guard below is that the refusal's number and the parser's
    number come from two independent reads of the same bytes.
    """
    import json
    from pathlib import Path

    from app.services.statpal_api import StatPalAPIService
    from app.tasks.config import STATPAL_SPORT_MAPPING

    path = (
        Path(__file__).parent / "fixtures" / "statpal_nfl_season_schedule_20260903.json"
    )
    assert path.exists(), f"no pinned NFL payload at {path}"
    payload = json.loads(path.read_text())
    service = StatPalAPIService.__new__(StatPalAPIService)

    authority = StatPalAPIService._parse_nfl_season_schedule(service, payload)
    ingest = StatPalAPIService._parse_fixtures(
        service, payload, STATPAL_SPORT_MAPPING["americanfootball_nfl"]
    )
    return len(authority), len(ingest)


def test_the_nfl_refusal_quotes_the_count_its_own_parsers_actually_read():
    """CERT-1887's follow-up, `AUTHORITY-028-PIN-REFUSAL-DENOMINATOR`.

    The refusal reason names a live defect to an operator, and the credibility
    of a named defect is entirely in its numbers. CERT-1887 corrected this text
    from the live season's **374** games to the **17** the reduced fixture
    actually retains — a full-census number standing beside a reduced-fixture
    measurement, which is how a figure gets attributed to a file that never held
    it. Nothing then stopped the old wording coming back: the sibling tests
    proved the ingest parser reads zero and that the reason names the defect,
    but neither one read the denominator.

    So this asserts the relation rather than the digits: **every count in the
    refusal is a number this test measured by running the shipped parsers over
    the pinned bytes.** A reversion to 374 fails not because 374 is blacklisted
    but because no parser produces it. Regenerate the fixture with more games
    and this fails too — correctly, because the sentence would then be stale.
    """
    authority_count, ingest_count = _nfl_pinned_parser_counts()

    # The shape CERT-1875 found: two parsers over one payload, and the blind one
    # is the only one that writes. If this ever stops holding, the refusal is
    # describing a defect that no longer exists.
    assert ingest_count == 0, (
        "the ingest parser now reads the pinned NFL payload — the refusal text "
        "is stale and NFL may belong in `DISCOVERY_SCHEDULED_SPORTS`"
    )
    assert authority_count > 0, (
        "the authority parser reads nothing either, so this is not the "
        "one-blind-parser defect the refusal describes"
    )

    # CERT-1887's measurement, pinned once. Re-derived above, not carried.
    assert (authority_count, ingest_count) == (17, 0), (
        f"the pinned NFL payload now parses {authority_count}/{ingest_count} "
        "(authority/ingest), not 17/0. Update "
        "`DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE['americanfootball_nfl']` and the "
        "docstring above it in the same commit — the refusal quotes these counts"
    )

    _, why = flip_permitted(
        "americanfootball_nfl", _run_of(REQUIRED_STREAK_DAYS, GATE_MEETS)
    )

    assert f"0 of the {authority_count} matches" in why, (
        "the refusal must say how many matches the payload holds, in the "
        f"payload's own terms; expected '0 of the {authority_count} matches' in: {why}"
    )
    assert f"reads all {authority_count}" in why, (
        "the refusal must say the authority parser reads the whole payload — "
        "that contrast IS the finding, and without the count it is an adjective"
    )

    # The general form: no invented number survives here. `CERT-1875` is a
    # citation, not a count, so it is stripped before the sweep.
    import re

    quoted = {int(n) for n in re.findall(r"\d+", re.sub(r"CERT-\d+", "", why))}
    assert quoted <= {authority_count, ingest_count}, (
        f"the refusal quotes {sorted(quoted - {authority_count, ingest_count})}, "
        "which no parser in this test produced. A count in an operator-facing "
        "reason must be one that was measured on the bytes being described"
    )


def test_every_stamped_sport_is_accounted_for_as_discoverable_or_named_broken():
    """No stamped sport may be silently outside both lists.

    This used to assert `SHADOW_STAMPERS <= DISCOVERY_SCHEDULED_SPORTS` — the
    darkness claim — and CERT-1875 is the reason it cannot: NFL is stamped and is
    NOT discoverable, so the arm is no longer dark and saying it is would be the
    comfortable lie. What must hold instead is that every stamped sport is in one
    list or the other, with a reason attached when it is the second.
    """
    unaccounted = (
        set(SHADOW_STAMPERS)
        - set(DISCOVERY_SCHEDULED_SPORTS)
        - set(DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE)
    )
    assert (
        not unaccounted
    ), f"stamped, measured daily, and in neither discovery list: {sorted(unaccounted)}"
    for sport_key, reason in DISCOVERY_BEAT_WITHOUT_A_WORKING_PARSE.items():
        assert len(reason) > 40, (
            f"{sport_key}'s exclusion has no usable reason attached; a bare "
            "exclusion is indistinguishable from a mistake"
        )


def test_a_mapped_sport_with_no_discovery_beat_is_refused_however_perfect(
    monkeypatch,
):
    """Tennis's exact shape, which is the next sport this lane stamps.

    `tennis_atp` is in `STATPAL_SPORT_MAPPING` and there is no
    `sync-statpal-schedules-tennis` beat. Give it everything else it could
    possibly need — a stamper, a ruled governing number, and TEN consecutive
    perfect days, three more than D50 asks for — and the flip is still refused,
    because agreement is measured over the fixtures both sources already share
    and that population can never demonstrate the thing the flip is for.

    The refusal must not read as a wait. "10/7 days, please hold" would be a
    sentence about patience for a problem that no amount of time solves.
    """
    monkeypatch.setattr(
        abs_module, "SHADOW_STAMPERS", {**SHADOW_STAMPERS, "tennis_atp": "stamp_tennis"}
    )
    monkeypatch.setattr(
        abs_module,
        "GOVERNING_IDENTITY_NUMBERS",
        {**GOVERNING_IDENTITY_NUMBERS, "tennis_atp": ("ours_covered_pct",)},
    )

    permitted, why = flip_permitted("tennis_atp", _run_of(10, GATE_MEETS))

    assert not permitted
    assert "no working StatPal discovery pass" in why
    assert "a `sync_statpal_schedules` beat" in why, (
        "tennis has no beat at all, so the reason must point at building one — "
        "not at a broken parse, which is NFL's different problem"
    )
    assert "not a wait" in why
    # And it must not describe the streak at all — there is nothing wrong with it.
    assert f"/{REQUIRED_STREAK_DAYS}" not in why


def test_the_discovery_refusal_does_not_shadow_the_no_stamper_one(monkeypatch):
    """Order matters, and the first question is still "is there anything to flip to?".

    A sport with neither a stamper nor a discovery beat — soccer_epl, today —
    must be told about the stamper, because that is the step that comes first.
    Reporting the discovery gap to a sport with no id join at all would send a
    reader to build the wrong thing.
    """
    assert "soccer_epl" not in SHADOW_STAMPERS
    assert "soccer_epl" not in DISCOVERY_SCHEDULED_SPORTS

    _permitted, why = flip_permitted("soccer_epl", _run_of(10, GATE_MEETS))
    assert "no shadow stamper" in why
    assert "discovery" not in why


def test_a_discoverable_sport_is_unaffected_and_still_permits_at_seven():
    """The blast radius, from the other side: NBA's answer is byte-for-byte its old one."""
    permitted, why = flip_permitted(
        "basketball_nba", _run_of(REQUIRED_STREAK_DAYS, GATE_MEETS)
    )
    assert permitted
    assert "discovery" not in why


def test_every_mapped_sport_off_the_discovery_beat_is_refused_by_name(monkeypatch):
    """The whole tier, not one specimen — and derived, so it grows by itself.

    lane1's review of the step-7 handoff (their PR #3178) closed this tier with a
    hand-written inventory. Deriving it instead means a sport added to
    `STATPAL_SPORT_MAPPING` without a schedule beat lands in this guard the day it
    is mapped, rather than the day somebody remembers a list. Today that set is
    `golf_pga`, seven soccer leagues, `tennis_atp` and `tennis_wta`.

    The trap lane1 hit and warned about, which this avoids: without FULL
    evidencing, every one of these sports is already refused at the first clause
    (no shadow stamper), so the test passes green with the discovery clause
    deleted — true by construction, which is not a test. Each sport here is given
    a stamper, a governing number and ten perfect days first, so the only thing
    left that can refuse it is the clause under test.
    """
    from app.tasks.config import STATPAL_SPORT_MAPPING

    off_the_beat = set(STATPAL_SPORT_MAPPING) - set(DISCOVERY_SCHEDULED_SPORTS)
    assert off_the_beat, (
        "every mapped sport is on the discovery beat, so this guard is vacuous — "
        "if that is genuinely true now, this test should be deleted, not left to "
        "pass over an empty set"
    )

    for sport_key in sorted(off_the_beat):
        monkeypatch.setattr(
            abs_module,
            "SHADOW_STAMPERS",
            {**SHADOW_STAMPERS, sport_key: f"stamp_{sport_key}"},
        )
        monkeypatch.setattr(
            abs_module,
            "GOVERNING_IDENTITY_NUMBERS",
            {**GOVERNING_IDENTITY_NUMBERS, sport_key: ("ours_covered_pct",)},
        )

        permitted, why = flip_permitted(sport_key, _run_of(10, GATE_MEETS))

        assert not permitted, (
            f"{sport_key} is mapped to StatPal with no scheduled discovery pass, "
            "and ten perfect agreement days let it through the flip gate"
        )
        assert (
            "discovery" in why
        ), f"{sport_key} was refused, but not for the reason that applies to it: {why!r}"
