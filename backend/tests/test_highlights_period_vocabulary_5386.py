"""Guards for #5386 — the two #5012 regexes are pinned to their full vocabulary.

#5012 stopped a kickoff card saying "Overtime" with two layers: a scheduled-date
refusal and an anchored ordinal. Both layers are ALTERNATIONS OF WORDS, and a
word list is the one kind of pattern that can be 90% right and read as finished.
This file sweeps each list entry by entry, because both had a hole that every
existing guard was green on:

1. **The weekday arm dropped two of eighteen spellings.** It was written as a
   stem list with an optional `(?:day)?`, which completes `mon`->`monday` and
   `sun`->`sunday` but not the two weekdays whose full form is not stem+"day":
   `wed`+`nesday` and `sat`+`urday` both fail the trailing `\\b`. `Wednesday` and
   `Saturday` standalone were never refused. #5012's guards exercised exactly one
   weekday standalone (`Sunday`) — a regular one — which is why this survived.

2. **The ordinal's qualifier list was unpinned for two live shapes.** Nothing
   asserted `end` or `mid`, so the list could be narrowed to the obvious
   `top|bot|bottom` with every test still green. Production says that would be a
   regression: see `PRODUCTION_INNING_SHAPES` below.

Neither was a live bug when filed, and the first is why: a bare `"Wednesday"`
carries no ordinal to misread, and every realistic ESPN date is refused anyway by
the month or clock arm. This is hardening. What it buys is that the NEXT edit to
either alternation cannot quietly drop a member, which is precisely how both
holes got here.
"""

import pytest

from app.utils.highlights import _SCHEDULED_DATETIME_RE, parse_game_progress

#: Every spelling of a weekday ESPN could plausibly emit — the three-letter stem,
#: the common four/five-letter abbreviations, and the full name. Eighteen forms;
#: the alternation must refuse all of them, and `test_the_sweep_covers...` below
#: asserts this list itself has not been thinned.
WEEKDAY_SPELLINGS = [
    "Mon", "Monday",
    "Tue", "Tues", "Tuesday",
    "Wed", "Weds", "Wednesday",
    "Thu", "Thur", "Thurs", "Thursday",
    "Fri", "Friday",
    "Sat", "Saturday",
    "Sun", "Sunday",
]

#: The two the shorthand dropped. Named separately so a reader of a future
#: failure knows instantly whether the regression is the old one returning.
IRREGULAR_WEEKDAYS = ["Wednesday", "Saturday"]

#: Every `espn.period` string served to a live card over 13 samples of
#: `GET /api/feed?mode=sports&limit=250` across the 2026-09-11 first-pitch window
#: (49 live-card observations), with its count and the inning it must resolve to.
#: MLB, so `SPORT_TOTAL_PERIODS` is 9 and a 1st inning is (1 - 0.5) / 9.
PRODUCTION_INNING_SHAPES = [
    ("Top 1st", 14),
    ("Bottom 1st", 4),
    ("End 1st", 2),
    ("Mid 1st", 1),
]


# --- The weekday arm, spelling by spelling ------------------------------


@pytest.mark.parametrize("weekday", WEEKDAY_SPELLINGS)
def test_every_weekday_spelling_is_refused_standalone(weekday):
    """Standalone, so only the weekday arm can be doing the work.

    A weekday inside a full date ("Wednesday, September 13th at 1:00 PM") is
    refused by the month and clock arms whatever the weekday arm does, so a test
    on that shape cannot see this hole — and #5012's guards were all that shape
    bar one. Passing a bare weekday is the only form that isolates the arm.
    """
    assert _SCHEDULED_DATETIME_RE.search(
        weekday.lower()
    ), f"{weekday!r} is a weekday and must be refused as a scheduled date"


@pytest.mark.parametrize("weekday", WEEKDAY_SPELLINGS)
def test_no_weekday_spelling_is_read_as_a_period(weekday):
    """The same sweep through the public function, not the private pattern.

    `_SCHEDULED_DATETIME_RE` could be complete while a later edit stops calling
    it; this is the assertion a reader actually depends on.
    """
    progress, is_overtime = parse_game_progress(weekday, "americanfootball_nfl")
    assert is_overtime is False
    assert progress == 0.0, f"{weekday!r} is not a period and has no progress"


@pytest.mark.parametrize("weekday", IRREGULAR_WEEKDAYS)
def test_the_stem_plus_day_shorthand_cannot_produce_this_weekday(weekday):
    """Non-vacuity: proves the two named cases are genuinely the irregular ones.

    Without this, `WEEKDAY_SPELLINGS` is just a list someone typed. This asserts
    the property that made these two different — they are not stem+"day" — so
    the sweep above is pinned to a fact about English, not to an anecdote. If a
    future editor reaches for a shorthand again, this says why it will not work.
    """
    stem = weekday.lower()[:3]
    assert (
        stem + "day" != weekday.lower()
    ), f"{weekday!r} IS {stem}+day — it is not an irregular spelling"


def test_the_sweep_covers_all_seven_days_in_full_and_abbreviated_form():
    """Non-vacuity: the sweep must not be thinned to the cases that pass.

    A parametrized list is only coverage while it is complete; the hole this
    file exists for was created by a list that omitted two members and looked
    finished. Asserts every day appears at least twice (a stem and a full name)
    and that all seven days are present.
    """
    lowered = [w.lower() for w in WEEKDAY_SPELLINGS]
    assert len(lowered) == len(set(lowered)), "duplicate spelling in the sweep"
    for full in [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    ]:
        forms = [w for w in lowered if full.startswith(w) or w == full]
        assert full in lowered, f"{full} missing from the sweep"
        assert len(forms) >= 2, f"{full} has only one spelling in the sweep"


# --- What the completed weekday arm must not have widened ----------------


@pytest.mark.parametrize(
    "period,sport_key,expected",
    [
        # The two newly-refused words are long enough to collide with nothing,
        # but the arm they were added to sits in front of every period reader,
        # so the real period tokens are re-pinned here rather than assumed.
        ("Top 12th", "baseball_mlb", (1.0, True)),
        ("1st Quarter", "basketball_nba", (0.125, False)),
        ("3rd Period", "icehockey_nhl", (2.5 / 3, False)),
        ("Q4", "basketball_nba", (0.875, False)),
        ("OT", "basketball_nba", (1.0, True)),
        ("Final", "soccer_epl", (1.0, False)),
        ("4", "basketball_nba", (0.875, False)),
        ("61'", "soccer_epl", (61 / 90, False)),
    ],
)
def test_real_period_tokens_are_unchanged(period, sport_key, expected):
    """Pinned to the values these returned before this change."""
    progress, is_overtime = parse_game_progress(period, sport_key)
    assert (pytest.approx(progress), is_overtime) == (
        pytest.approx(expected[0]),
        expected[1],
    )


def test_a_period_token_that_merely_contains_a_weekday_stem_is_unaffected():
    """The arm is `\\b`-anchored and must stay that way.

    "Sun" is a weekday; a token that merely contains those letters is not. This
    is the false-refusal direction — the cost of completing a refusal list is
    paid here, and it must be zero.
    """
    for token in ["sunk", "monsoon", "satellite", "montage", "fright", "thug"]:
        assert not _SCHEDULED_DATETIME_RE.search(
            token
        ), f"{token!r} merely contains a weekday's letters — it is not a weekday"


def test_the_widening_is_exactly_the_two_missing_words_and_nothing_else():
    """Which population NEWLY matches? Completing a refusal list is a widening.

    A refusal that fires on more strings can only cost real period tokens, so
    the widening is characterised rather than trusted: the shipped pattern is
    compared against the shorthand it replaced over a corpus built from real
    period tokens and every weekday spelling. The set of strings whose verdict
    CHANGED must be exactly those containing a standalone `wednesday` or
    `saturday` — the two the shorthand dropped, and no third thing.
    """
    import re

    shorthand = re.compile(
        r"\b(?:january|february|march|april|may|june|july|august|september|october"
        r"|november|december)\b"
        r"|\b(?:mon|tue|tues|wed|weds|thu|thur|thurs|fri|sat|sun)(?:day)?\b"
        r"|\b\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)\b"
    )
    real_tokens = [
        "top 12th", "bot 11th", "mid 5th", "end 1st", "1st quarter", "4th quarter",
        "3rd period", "period 5", "q4", "ot", "2nd ot", "halftime", "1st half",
        "2nd half", "final", "61'", "90+3'", "4", "6:55 - 1st quarter", "shootout",
    ]
    corpus = list(real_tokens) + [w.lower() for w in WEEKDAY_SPELLINGS]
    for token in real_tokens:
        for weekday in WEEKDAY_SPELLINGS:
            corpus.append(f"{weekday.lower()} {token}")

    changed = [
        s
        for s in corpus
        if bool(_SCHEDULED_DATETIME_RE.search(s)) != bool(shorthand.search(s))
    ]
    assert changed, "no verdict changed — this test is not exercising the fix"
    offenders = [
        s
        for s in changed
        if not re.search(r"\b(?:wednesday|saturday)\b", s)
    ]
    assert not offenders, (
        f"the completed weekday arm changed the verdict on {offenders[:5]}, which "
        "contain neither 'wednesday' nor 'saturday' — the widening is wider than "
        "the two words it was supposed to add"
    )


# --- The ordinal qualifiers, pinned to what production serves ------------


@pytest.mark.parametrize("period,count", PRODUCTION_INNING_SHAPES)
def test_every_production_inning_shape_resolves_to_its_real_inning(period, count):
    """`End 1st` and `Mid 1st` are live strings, not defensive padding.

    Narrowing the qualifier list to `top|bot|bottom` — the obvious shortening —
    drops these two out of the anchored ordinal entirely. They then fall past
    every branch to the 0.5 "unknown mid-game" default: a 1st-inning game
    reporting 50% elapsed instead of 5.6%, which feeds the late-game bonus in
    the feed ranking. `count` is carried so the failure message says how much of
    a Friday night the regression covers.
    """
    progress, is_overtime = parse_game_progress(period, "baseball_mlb")
    assert is_overtime is False
    assert progress == pytest.approx(0.5 / 9), (
        f"{period!r} ({count} of 21 observed live MLB cards) resolved to "
        f"{progress:.3f} elapsed, not a 1st inning"
    )


def test_the_unknown_fallback_really_is_the_value_a_narrowing_would_produce():
    """Non-vacuity: names the number the test above is defending against.

    If the fallback were also 0.5/9 the assertion would be unfalsifiable. This
    pins the two apart, so the guard above is known to distinguish "parsed as
    the 1st inning" from "parsed as nothing".
    """
    assert parse_game_progress("nonsense", "baseball_mlb") == (0.5, False)
    assert 0.5 != pytest.approx(0.5 / 9)


@pytest.mark.parametrize("qualifier", ["top", "bot", "bottom", "mid", "middle", "end", "start"])
def test_every_half_inning_qualifier_leads_an_ordinal(qualifier):
    """The whole qualifier list, not only the four shapes seen on one night.

    One Friday's sample is evidence that `end`/`mid` are real; it is not
    evidence that `middle`/`start` are not. Sweeping the list as written keeps
    a member from being dropped for want of a sighting, which is the same
    failure as the weekday hole above.
    """
    progress, is_overtime = parse_game_progress(f"{qualifier} 3rd", "baseball_mlb")
    assert is_overtime is False
    assert progress == pytest.approx(2.5 / 9), f"{qualifier!r} 3rd is the 3rd inning"


def test_extra_innings_still_read_as_beyond_regulation_behind_every_qualifier():
    """The qualifiers must not become a way to lose a real overtime signal."""
    for qualifier in ["top", "bot", "bottom", "mid", "middle", "end", "start"]:
        assert parse_game_progress(f"{qualifier} 12th", "baseball_mlb") == (1.0, True)
