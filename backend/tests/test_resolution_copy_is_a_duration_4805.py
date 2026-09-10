"""#4805 — a resolution caption that names a calendar it cannot know.

Ship D1 (#4066): page one says why each card is here, and says it truthfully.

THE DEFECT. The two resolution rungs rendered as "resolves this week" and
"resolves this month". Their predicate is a DURATION — `days_until <= 7` and
`<= 30` in `futures_highlights.compute_futures_highlight` — so the calendar word
was right only for the cards whose window happened not to cross a boundary.

MEASURED on the served `GET /api/feed?limit=250`, 2026-09-10 14:39Z, over every
card that fired a clause, classified in the READER's zone (America/New_York and
America/Los_Angeles agree on every row):

    "resolves this month"   16 cards, 6 resolve in October
    "resolves this week"     8 cards, 7 resolve after Sunday

The specimens below are those rows, with the dates the wire carried.

WHY THE FIX IS NOT "NAME THE DATE", which is what the issue asked for first. The
card already prints its own "Resolves <date>" chip, and the chip renders the
instant in the reader's timezone while this module only has UTC — the standing
comment above `BinaryCardCopy` says so, and the BEFORE LOOK proved it: the Brazil
card's chip read "Resolves Oct 3, 2026" over a wire value of `2026-10-04T00:00Z`.
A second date emitted server-side would have sat two lines above the first and
disagreed with it by a day.

WHY IT IS NOT "FIX THE PREDICATE" either. A calendar boundary is a fact about the
reader's zone. `ANTHROPIC` below closes `2026-09-14T03:59Z` — Monday in UTC,
Sunday for every US reader — so a boundary computed here is wrong for somebody
whichever way it goes. `test_the_copy_survives_the_clock` is that argument as a
test: a duration is the one statement true in every zone at every hour.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import feed_reasons as fr
from app.utils.feed_market_quality import _GENERIC_HEADLINES
from app.utils.feed_quality_debug import _card_why_now
from app.utils.feed_reasons import (
    RESOLVING_WITHIN_MONTH_HEADLINE,
    RESOLVING_WITHIN_WEEK_HEADLINE,
)
from app.utils.futures_highlights import (
    PRIMARY_REASON_LABELS,
    compute_futures_highlight,
)

#: 07:39 Pacific on the Thursday the census was taken. Fixed, and offset from a
#: literal rather than derived from the wall clock: the whole subject is what the
#: copy says relative to a date, so an anchor that moves tests nothing (#44).
NOW = datetime(2026, 9, 10, 14, 39, tzinfo=timezone.utc)

#: A calendar word is any claim about a named period the reader's zone decides.
CALENDAR_WORDS = ("this week", "this month", "next week", "next month")


# ── The specimens, verbatim from the served payload ─────────────────────────
#
# name, resolution instant, leader, leader probability. The six month-class rows
# are every card whose caption said "this month" while resolving in October; the
# week-class rows are the ones that said "this week" while resolving after the
# Sunday. Two more month-class rows (Amgen Irish Open, Spanish Grand Prix) are
# kept as the TRUE cases — the old copy was right about them, and the new copy
# must not have bought its correctness by going silent.

MONTH_CLASS_LYING = [
    ("Premier Lacrosse League Championship Winner",
     datetime(2026, 10, 4, 20, 0, tzinfo=timezone.utc), "Philadelphia Waterdogs", 0.54),
    ("Brazil Presidential Election",
     datetime(2026, 10, 4, 0, 0, tzinfo=timezone.utc), "Flávio Bolsonaro", 0.48),
    ("Online Sportsbook Ad Spend in September",
     datetime(2026, 10, 6, 3, 59, tzinfo=timezone.utc), "Above 118", 0.60),
    ("Presidents Cup Winner",
     datetime(2026, 10, 11, 14, 0, tzinfo=timezone.utc), "Team USA", 0.80),
    ("Caribbean Premier League Champion",
     datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc), "Guyana Amazon Warriors", 0.46),
    ("StarLadder StarSeries Fall 2026: Winner",
     datetime(2026, 10, 5, 3, 59, tzinfo=timezone.utc), "Team Falcons", 0.11),
]

MONTH_CLASS_TRUE = [
    ("Amgen Irish Open Winner",
     datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc), "Rory McIlroy", 0.10),
    ("Spanish Grand Prix Winner",
     datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc), "Andrea Kimi Antonelli", 0.30),
]

WEEK_CLASS_LYING = [
    ("Will South Carolina have D4 (Exceptional Drought) this week?",
     datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc), "Texas", 0.50),
    ("Will Ukraine target Moscow by September 11, 2026?",
     datetime(2026, 9, 15, 20, 59, tzinfo=timezone.utc), None, None),
    ("What will be the top US Netflix show this week?",
     datetime(2026, 9, 15, 23, 59, tzinfo=timezone.utc),
     "Death of the Pastor's Wife: Season 1", 0.50),
    ("What will be the top global Netflix show this week?",
     datetime(2026, 9, 15, 23, 59, tzinfo=timezone.utc), "The Gentlemen: Season 2", 0.84),
    ("What will be the #2 US Netflix movie this week?",
     datetime(2026, 9, 15, 23, 59, tzinfo=timezone.utc), "The Whisper Man", 0.75),
]

#: The row whose truth depends on where the reader is sitting: 03:59Z on Monday
#: the 14th is Sunday the 13th in every US zone, and its own chip says so
#: ("Closes Sep 13", photographed at 390px in the BEFORE LOOK).
ANTHROPIC = ("Anthropic market share this week",
             datetime(2026, 9, 14, 3, 59, tzinfo=timezone.utc), "Above 2.25%", 0.53)

US_ZONES = {"America/New_York": timedelta(hours=-4), "America/Los_Angeles": timedelta(hours=-7)}


def _reasons_for(resolution: datetime, *, name: str) -> list[str]:
    """The producer's OWN reason codes for a specimen, never a hand-written list.

    Every copy assertion below runs on these. A fixture that drifts from what
    `compute_futures_highlight` actually emits is how #4695 stayed invisible for
    four months, so the join is made once, here.
    """
    return compute_futures_highlight(
        market_tier=2,
        sport_category="politics",
        resolution_date=resolution,
        outcomes=[{"name": "Yes", "probability": 0.5, "rank": 1}],
        source_count=1,
        now=NOW,
        market_name=name,
    ).reasons


#: THE LEADER SHAPE IS PART OF THE SPECIMEN, not a detail of it. Each rung in
#: each generator has three arms — a named leader, a leader whose label is a bare
#: date or threshold (`_weak_outcome_label`), and no leader at all — and they
#: spell the resolution clause SEPARATELY. The first cut of this file used the
#: served leader for every specimen, and the mutation run caught it: reverting
#: the leaderless arms to "resolving this month" / "Resolution window is this
#: month" left every test green. A sweep that only exercises the arm production
#: happened to serve today is a sweep that guards one third of the copy.
LEADER_SHAPES = {
    "named": lambda leader, p: (leader, p),
    "weak-label": lambda leader, p: ("December 31", p if p is not None else 0.46),
    "absent": lambda leader, p: (None, None),
}


def _all_copy(name, resolution, leader, probability) -> list[str]:
    """Every string the four generators can serve for one specimen."""
    reasons = _reasons_for(resolution, name=name)
    headline = fr.generate_futures_headline(
        highlight_reasons=reasons,
        leader_name=leader,
        leader_probability=probability,
        market_name=name,
        now=NOW,
    )
    return [
        headline,
        fr.generate_futures_reason(
            market_name=name,
            highlight_reasons=reasons,
            leader_name=leader,
            leader_probability=probability,
            now=NOW,
        ),
        fr.generate_futures_context_summary(
            headline=headline,
            highlight_reasons=reasons,
            market_name=name,
            leader_name=leader,
            leader_probability=probability,
            now=NOW,
        ),
        fr.compose_binary_card_copy(
            market_name=name,
            highlight_reasons=reasons,
            affirmative_probability=probability if probability is not None else 0.5,
            now=NOW,
        ).context_summary,
    ]


# ── 1. The census, in the repo ──────────────────────────────────────────────


@pytest.mark.parametrize("name,resolution,_leader,_p", MONTH_CLASS_LYING)
def test_the_month_specimens_resolve_in_a_later_month(name, resolution, _leader, _p):
    """The claim the old copy made, checked against the date it was made about.

    This is the census itself, not a restatement of it: each row asserts that the
    card's own resolution instant falls in a LATER calendar month than the day it
    was served, in both US zones. If a specimen ever stops being a lie, it stops
    being evidence, and the test says so rather than the file quietly aging.
    """
    for offset in US_ZONES.values():
        zone = timezone(offset)
        assert (resolution.astimezone(zone).year, resolution.astimezone(zone).month) != (
            NOW.astimezone(zone).year,
            NOW.astimezone(zone).month,
        ), f"{name} no longer resolves in a later month than {NOW.date()}"


@pytest.mark.parametrize("name,resolution,_leader,_p", WEEK_CLASS_LYING)
def test_the_week_specimens_resolve_after_the_sunday(name, resolution, _leader, _p):
    """Same, for the sharper half: 7 of the 8 "this week" cards were next week's."""
    for offset in US_ZONES.values():
        zone = timezone(offset)
        assert (
            resolution.astimezone(zone).isocalendar()[:2]
            != NOW.astimezone(zone).isocalendar()[:2]
        ), f"{name} no longer resolves after the week it was served in"


def test_the_boundary_itself_depends_on_the_reader():
    """Why the predicate was not "fixed" to match the words.

    One specimen, two zones, two different answers to "is this week?" — so no
    calendar word computed in UTC can be right for every reader. This is the
    refutation of the issue's third option, kept as a test because it is the
    reason the chosen wording is the one it is.
    """
    _name, resolution, _leader, _p = ANTHROPIC
    answers = {
        zone: resolution.astimezone(timezone(offset)).isocalendar()[:2]
        == NOW.astimezone(timezone(offset)).isocalendar()[:2]
        for zone, offset in {**US_ZONES, "UTC": timedelta(0)}.items()
    }
    assert answers["UTC"] is False
    assert answers["America/New_York"] is True
    assert answers["America/Los_Angeles"] is True


# ── 2. No generator says a calendar word for either rung ────────────────────


@pytest.mark.parametrize("shape", sorted(LEADER_SHAPES))
@pytest.mark.parametrize(
    "specimen",
    MONTH_CLASS_LYING + MONTH_CLASS_TRUE + WEEK_CLASS_LYING + [ANTHROPIC],
    ids=lambda s: s[0][:40] if isinstance(s, tuple) else str(s),
)
def test_no_generator_serves_a_calendar_word(specimen, shape):
    """Every string, every generator, every leader arm, through the producer."""
    name, resolution, leader, probability = specimen
    leader, probability = LEADER_SHAPES[shape](leader, probability)
    for served in _all_copy(name, resolution, leader, probability):
        # The Netflix and drought questions carry "this week" in their own TITLE,
        # which is the market's name and not our claim. The generators embed the
        # title — sometimes whole, sometimes through `_short_market_name`, which
        # truncates and strips the "?" — so all three forms come out before the
        # assertion, and what is left is the caption WE wrote.
        caption = (served or "").lower()
        for title in (name, fr._short_market_name(name), name.rstrip("?")):
            caption = caption.replace(title.lower().rstrip("?"), "")
        for word in CALENDAR_WORDS:
            assert word not in caption, (
                f"{name}: served copy still claims a calendar period — {served!r}"
            )


@pytest.mark.parametrize("shape", sorted(LEADER_SHAPES))
@pytest.mark.parametrize("specimen", MONTH_CLASS_LYING + MONTH_CLASS_TRUE)
def test_the_month_rung_still_speaks(specimen, shape):
    """Silence is not a fix. Every month-class card keeps a resolution sentence.

    Run on all three leader arms: the leaderless one is where a rewording is
    most likely to be dropped rather than replaced, because nothing on today's
    page one exercises it.
    """
    name, resolution, leader, probability = specimen
    leader, probability = LEADER_SHAPES[shape](leader, probability)
    served = _all_copy(name, resolution, leader, probability)
    assert any("within a month" in (s or "").lower() for s in served), served


@pytest.mark.parametrize("shape", sorted(LEADER_SHAPES))
@pytest.mark.parametrize("specimen", WEEK_CLASS_LYING + [ANTHROPIC])
def test_the_week_rung_still_speaks(specimen, shape):
    """Same for the week class, whose rung also has a "resolving soon" branch."""
    name, resolution, leader, probability = specimen
    leader, probability = LEADER_SHAPES[shape](leader, probability)
    served = _all_copy(name, resolution, leader, probability)
    assert any(
        ("within a week" in (s or "").lower()) or ("resolving soon" in (s or "").lower())
        for s in served
    ), served


# ── 3. The predicate and the words agree, at the boundary ───────────────────


@pytest.mark.parametrize(
    "days,expected",
    [(2, "week"), (7, "week"), (8, "month"), (30, "month"), (31, None), (0.5, None)],
)
def test_the_words_match_the_predicate_at_its_own_boundary(days, expected):
    """A duration claim is only true if it tracks the duration that fires it.

    7 days is the last day of the week rung, 8 the first of the month rung, 30
    the last, 31 nothing — and 0.5 is the micro-bet suppression below both. The
    copy is read out of the real generators at each, so moving a comparison in
    `futures_highlights` without moving the words breaks this.
    """
    resolution = NOW + timedelta(days=days)
    served = " ".join(
        s or "" for s in _all_copy("Some Championship Winner", resolution, "Team A", 0.4)
    ).lower()
    if expected == "week":
        assert "within a week" in served or "resolving soon" in served
        assert "within a month" not in served
    elif expected == "month":
        assert "within a month" in served
        assert "within a week" not in served
    else:
        assert "within a week" not in served and "within a month" not in served


def test_the_copy_survives_the_clock():
    """The property the calendar words did not have: the hour cannot change it.

    Twelve serve times across a month, one fixed specimen. A calendar word would
    have flipped as the clock crossed its boundary — that IS the defect — so the
    strings being byte-identical is what "true at every hour in every zone" means
    operationally (`clock_sweep.py`'s rule, applied to copy).
    """
    name, resolution, leader, probability = MONTH_CLASS_LYING[1]
    baseline = None
    for hours in range(0, 24 * 25, 50):
        served_now = NOW + timedelta(hours=hours)
        reasons = compute_futures_highlight(
            market_tier=2,
            sport_category="politics",
            resolution_date=resolution,
            outcomes=[{"name": "Yes", "probability": 0.5, "rank": 1}],
            source_count=1,
            now=served_now,
            market_name=name,
        ).reasons
        if "resolving_soon_30d" not in reasons:
            continue  # the specimen has crossed into the week rung; not the subject
        summary = fr.generate_futures_context_summary(
            headline=fr.generate_futures_headline(
                highlight_reasons=reasons,
                leader_name=leader,
                leader_probability=probability,
                market_name=name,
                now=served_now,
            ),
            highlight_reasons=reasons,
            market_name=name,
            leader_name=leader,
            leader_probability=probability,
            now=served_now,
        )
        if baseline is None:
            baseline = summary
        assert summary == baseline, f"copy moved with the clock at +{hours}h: {summary!r}"
    assert baseline and "within a month" in baseline


# ── 4. The three-way handshake on the 30d headline ──────────────────────────


def test_the_thirty_day_headline_is_one_string_in_three_modules():
    """`routes/feed.py` serves `generate_futures_headline(...) or primary_reason`.

    So the context generator's `headline ==` branch can be handed EITHER
    producer's spelling, and `feed_market_quality` classifies whichever arrives.
    Three modules, one string: asserted by identity, not by eye.
    """
    label = dict(PRIMARY_REASON_LABELS)["resolving_soon_30d"]
    assert label == RESOLVING_WITHIN_MONTH_HEADLINE
    assert RESOLVING_WITHIN_MONTH_HEADLINE in _GENERIC_HEADLINES


def test_the_context_branch_fires_on_the_label_the_other_module_emits():
    """The join under load: the fallback headline reaches the matching branch."""
    summary = fr.generate_futures_context_summary(
        headline=dict(PRIMARY_REASON_LABELS)["resolving_soon_30d"],
        highlight_reasons=["resolving_soon_30d"],
        leader_name="No",
        leader_probability=0.61,
    )
    assert summary == "No leads at 61%; resolves within a month"


def test_the_retired_headline_no_longer_unlocks_the_branch():
    """The control for the test above — and the mutation that would hide a drift.

    If someone re-spells one module's copy and not the other's, the branch goes
    quietly unreachable and the card falls through to a leader line. Handing the
    OLD literal in must not work, or the test above would pass on a coincidence.
    """
    summary = fr.generate_futures_context_summary(
        headline="Resolving this month",
        highlight_reasons=["resolving_soon_30d"],
        leader_name="No",
        leader_probability=0.61,
    )
    assert summary != "No leads at 61%; resolves within a month"


def test_the_week_headline_is_deliberately_not_generic():
    """A declared non-change, so the next reader does not "fix" it silently.

    `Resolving soon` and the 30d headline are `_GENERIC_HEADLINES` members; the
    7d headline never was. Adding it would newly mark a class of cards generic —
    a ranking change riding a copy fix, which would make this ship's own
    acceptance unmeasurable. Filed as the #4805 follow-up instead.
    """
    assert RESOLVING_WITHIN_WEEK_HEADLINE not in _GENERIC_HEADLINES


# ── 5. The metric still reads the cards it read before ──────────────────────


@pytest.mark.parametrize(
    "specimen", MONTH_CLASS_LYING + WEEK_CLASS_LYING + [ANTHROPIC],
    ids=lambda s: s[0][:40] if isinstance(s, tuple) else str(s),
)
def test_the_new_wording_still_earns_why_now_credit(specimen):
    """`WHY_NOW_MARKERS` is a vocabulary two modules have to agree on.

    Its own docstring says to extend it in the same commit as the branch. A
    rewording that forgot it would drop `why-now coverage @10` without a single
    card changing — a metric regression with no defect behind it.
    """
    name, resolution, leader, probability = specimen
    headline, reason, summary, _binary = _all_copy(*specimen)
    assert _card_why_now(
        {"headline": headline, "context_summary": summary, "reason": reason}
    ), f"{name}: served copy no longer counts as a why-now — {summary!r}"
