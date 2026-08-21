"""#2075 — the labelling sampler served Alex games that had already been played.

Market 59183794, `Los Angeles D vs Colorado`, was served on 2026-08-21 for a game
that started on the 18th. It got through because BOTH date fields the sampler
trusts are false at once for a settled Kalshi game: `status` stays `'open'`
forever (regular polling only fetches open markets, gotcha #33) and
`resolution_date` is Kalshi's CLOSE time, not the start (gotcha #14).

The card passed the admission test **because** of the defect: the strata admit
"live, unresolved" markets by `status`, and `status` is the stale field.

## Why the predicate is three conditions and not one

MEASURED on production 2026-08-21: of the 52,615 markets the sampler admits,
**42,046 (80%) have a `commence_time` in the past**. A bare "refuse a past start"
would have emptied the pool, because on a season future or a non-sport question
that column is not a kickoff. Narrowed to head-to-head sport names started more
than 12 hours ago, the cohort is 27,088 — and in a LIVE 100-card sample of the
served queue, **13 cards** matched, every one a real finished game, the oldest 138
hours old.

## What each side of this file is for

`is_finished_contest` is the POLICY: pure, driven through cases here, and the
thing the endpoint refuses with. The stratum SQL applies the same three conditions
because `top_feed_like` orders by `volume_24h DESC` and a just-finished game
carries high 24h volume, so the dead rows crowd the top of the budget — but a
WHERE clause cannot be driven through cases. Both are built from the same three
constants; the tests at the bottom pin that the SQL still reads all three.

Both directions, per gotcha #43. The refusals are one half; the survivors — a live
game, a game that finished an hour ago, a non-sport "vs" question, an unclassified
market — are the other, and they are the half that would empty Alex's queue.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.admin_judgments import (
    _GAME_CERTAINLY_OVER,
    _labeling_stratum_query,
    is_finished_contest,
)
from app.utils.sport_keys import NON_SPORT_LLM_CATEGORIES

NOW = datetime(2026, 8, 21, 16, 0, tzinfo=timezone.utc)


def _verdict(name, category, hours_ago):
    """`hours_ago` is an AGE, never an hour of the day (gotcha #44).

    The anchor is `NOW`, a frozen constant, and every case is expressed as an
    offset from it — so this file cannot start failing in the evening, and it has
    no branch on the clock to get wrong.
    """
    commence = None if hours_ago is None else NOW - timedelta(hours=hours_ago)
    return is_finished_contest(
        name=name,
        llm_sport_category=category,
        commence_time=commence,
        now=NOW,
    )


# The 13 real cards the live sample surfaced, with their measured ages.
FINISHED = [
    ("Los Angeles D vs Colorado", "baseball", 88, "THE SPECIMEN — #2075, market 59183794"),
    ("Los Angeles D vs Colorado: Total Runs", "baseball", 88, "a prop on the same dead game"),
    ("Los Angeles D vs Colorado: Spread", "baseball", 88, "and its spread sibling"),
    ("Prague: Eduardo Ribeiro vs Andrew Paulson", "tennis", 138, "the oldest in the sample"),
    ("The Hundred: Manchester Super Giants vs Sunrisers Leeds", "cricket", 17, "the youngest"),
    ("Sion: Kai Wehnelt vs Calvin Hemery", "table_tennis", 78, "table tennis is a sport no allowlist would have held"),
    ("Counter-Strike: Vitality vs Spirit (BO3) - Esports World Cup", "esports", 24, "esports BO3"),
    ("Dota 2: Team Yandex vs Nigma Galaxy (BO3) - The International", "esports", 23, "esports, colon-heavy name"),
    ("Washington vs Texas: Total Runs", "baseball", 64, ""),
    ("Seattle vs Milwaukee: Total Runs", "baseball", 63, ""),
]


@pytest.mark.parametrize(
    ("name", "category", "hours", "why"),
    FINISHED,
    ids=[f[0][:28] for f in FINISHED],
)
def test_a_game_that_has_certainly_been_played_is_refused(name, category, hours, why):
    assert _verdict(name, category, hours) is True, why


# ── THE OTHER HALF: everything that must still reach Alex ────────────────────

SURVIVES = [
    ("Los Angeles D vs Colorado", "baseball", -3, "tips off in three hours — the healthy case"),
    ("Los Angeles D vs Colorado", "baseball", 1, "started an hour ago: LIVE, and a live game is a good card"),
    ("Los Angeles D vs Colorado", "baseball", 11, "eleven hours: inside the bound, so still served"),
    ("Chiefs vs Bills", "football", None, "no start time at all — nothing is known, so nothing is refused"),
    ("Will Trump vs Biden debate happen?", "politics", 500, "a non-sport question that merely contains 'vs'"),
    ("Oppenheimer vs Barbie opening weekend", "entertainment", 500, "same, on the entertainment side"),
    ("Nasdaq vs S&P spread on Aug 1", "economics", 500, "same, on the finance side"),
    ("Los Angeles Dodgers to win the World Series", "baseball", 500, "a sport FUTURE: past start, but no head-to-head"),
    ("Who wins the AL East?", "baseball", 500, "a sport field market, likewise"),
    ("Los Angeles D vs Colorado", None, 500, "unclassified: unknown is not dead (gotcha #53)"),
    ("Los Angeles D vs Colorado", "other", 500, "'other' is in the non-sport set, so its dates mean nothing"),
]


@pytest.mark.parametrize(
    ("name", "category", "hours", "why"),
    SURVIVES,
    ids=[f"{s[1]}-{s[2]}" for s in SURVIVES],
)
def test_everything_else_still_reaches_the_queue(name, category, hours, why):
    assert _verdict(name, category, hours) is False, why


def test_the_survivor_list_is_not_all_one_reason():
    """Anti-vacuity for the leave-alone direction.

    Eleven survivors that all pass for the same reason would prove one arm and
    look like four. Each of the four escape hatches — inside the bound, no start
    time, non-sport category, no head-to-head shape — must be represented, or a
    predicate that dropped three of them would still be green here.
    """
    assert any(s[2] is not None and s[2] <= 12 for s in SURVIVES)
    assert any(s[2] is None for s in SURVIVES)
    assert any(s[1] in NON_SPORT_LLM_CATEGORIES for s in SURVIVES)
    assert any(s[1] is None for s in SURVIVES)
    assert any(
        " vs " not in s[0] and " @ " not in s[0] and " at " not in s[0]
        for s in SURVIVES
    )


def test_a_market_object_missing_the_field_entirely_is_not_refused():
    """The duck-typed arm, and it is here because it went red first.

    The candidate loop is fed `SimpleNamespace` fakes by several tests and by the
    trace tooling, and the first version read `market.commence_time` directly —
    four unrelated tests in `test_admin_judgments.py` failed with
    `AttributeError` on a full-suite run that the focused runs had all passed.
    The loop now reads with `getattr(..., None)`, and None must mean "unknown, do
    not refuse" rather than "no start time, therefore old".
    """
    assert (
        is_finished_contest(
            name=None, llm_sport_category=None, commence_time=None, now=NOW
        )
        is False
    )
    assert (
        is_finished_contest(
            name="A vs B",
            llm_sport_category="baseball",
            commence_time=None,
            now=NOW,
        )
        is False
    )


def test_the_boundary_is_the_constant_and_is_inclusive_on_the_live_side():
    """Exactly at the bound the game is NOT refused.

    Stated as a test because the direction of a `<=` is the kind of thing that
    gets flipped in a later tidy-up, and flipping it here would start refusing
    games at the twelve-hour mark with nothing to notice.
    """
    hours = _GAME_CERTAINLY_OVER.total_seconds() / 3600
    assert _verdict("A vs B", "baseball", hours) is False
    assert _verdict("A vs B", "baseball", hours + 0.01) is True


@pytest.mark.parametrize("shape", ["A vs B", "A vs. B", "A @ B", "A at B", "Cup: A vs B"])
def test_every_head_to_head_spelling_is_recognised(shape):
    assert _verdict(shape, "soccer", 500) is True


@pytest.mark.parametrize(
    "not_a_matchup",
    [
        "Vsauce to hit 20M subscribers",  # 'vs' inside a word
        "Atlanta to win the pennant",  # 'at' inside a word
        "Will the Vatican name a new saint?",
        "Cost of a Big Mac above $6",
    ],
)
def test_a_word_containing_vs_or_at_is_not_a_matchup(not_a_matchup):
    """The pattern requires word boundaries on both sides.

    Without them `Vsauce` and `Atlanta` are matchups, and a sport-categorised
    market with either in its title disappears from the queue for no reason.
    """
    assert _verdict(not_a_matchup, "baseball", 500) is False


# ── THE QUERY ARM: the same three conditions, still wired ────────────────────


@pytest.fixture(scope="module")
def stratum_sql() -> str:
    query = _labeling_stratum_query("top_feed_like", now=NOW, limit=10)
    return str(query.compile(compile_kwargs={"literal_binds": True}))


def test_the_query_filters_on_commence_time_at_the_same_threshold(stratum_sql):
    """The SQL is an optimisation over the policy, so it must use its constant.

    Not a second threshold written by hand: two literals would be two policies,
    and the second is the one nobody remembers to change.
    """
    assert "commence_time" in stratum_sql
    cutoff = NOW - _GAME_CERTAINLY_OVER
    assert cutoff.strftime("%Y-%m-%d %H:%M:%S") in stratum_sql, (
        "the stratum query no longer excludes finished games at the policy's own "
        "cutoff, so the volume-ordered budget goes back to being spent on games "
        "that have already been played"
    )


def test_the_category_list_is_emitted_in_a_STABLE_order(stratum_sql):
    """`tuple(frozenset)` would emit a different SQL string per process.

    String hash randomisation is on by default, so an unsorted set renders its IN
    list in a different order on every worker — fragmenting this query's
    `pg_stat_statements` entry across restarts, and leaving nothing about the
    compiled text safe to assert beyond bare membership.
    """
    start = stratum_sql.find("llm_sport_category IN (")
    assert start > -1
    rendered = stratum_sql[start : stratum_sql.find(")", start)]
    emitted = [t.strip().strip("'") for t in rendered.split("(", 1)[1].split(",")]
    assert emitted == sorted(NON_SPORT_LLM_CATEGORIES), (
        f"the non-sport list is not emitted in sorted order: {emitted}"
    )


def test_the_query_keeps_all_three_conditions(stratum_sql):
    """One condition dropped is a different rule, and two of the three drops are
    silent: without the category arm the sampler starts refusing entertainment
    questions, and without the name arm it refuses season futures."""
    assert "llm_sport_category" in stratum_sql, "the sport-category arm is gone"
    assert "vs" in stratum_sql, "the head-to-head name arm is gone"
    assert "commence_time IS NULL" in stratum_sql, (
        "the NULL arm is gone. A market with no start time is UNKNOWN, not dead, "
        "and refusing it would drop every unstamped row"
    )


def test_the_five_escape_hatches_are_ORed_not_ANDed(stratum_sql):
    """Anti-vacuity for the SQL arm, and it took two attempts to write.

    The first version asserted `" OR " in sql`, which is TRUE of the unrelated
    `resolution_date` clause — so collapsing this arm into a conjunction (a
    planted mutation) passed it. As an AND the arm reads
    `commence_time IS NULL AND commence_time > cutoff`, which is unsatisfiable:
    the sampler would return nothing at all, forever, and the only symptom would
    be an empty labelling queue.

    So the assertion is over THIS arm's own text: its five escape hatches, in one
    parenthesised group, separated by OR.
    """
    arm_start = stratum_sql.find("futures_markets.commence_time IS NULL")
    assert arm_start > -1, "the finished-contest arm is gone from the query"
    # Slice to the end of the parenthesised GROUP, not to the next `)` — the name
    # pattern `(^| )(vs\.?|@) ` contains parentheses of its own, and slicing on the
    # first one truncated the arm before its last two hatches. This test failed on
    # a clean tree for exactly that reason before the bound was fixed.
    arm_end = stratum_sql.find(") AND ", arm_start)
    assert arm_end > arm_start, "could not find the end of the finished-contest arm"
    arm = stratum_sql[arm_start:arm_end]

    for hatch in (
        "commence_time IS NULL",
        "commence_time >",
        "llm_sport_category IS NULL",
        "llm_sport_category IN",
        "NOT (futures_markets.name",
    ):
        assert hatch in arm, f"escape hatch `{hatch}` is missing from the arm"

    assert " AND " not in arm, (
        "the finished-contest arm contains an AND. Its five conditions are "
        "escape hatches and must be a disjunction — `commence_time IS NULL AND "
        "commence_time > cutoff` can never be true, so the sampler would serve "
        "an empty queue with nothing to indicate why"
    )
    assert arm.count(" OR ") >= 4, (
        f"expected at least four ORs joining five hatches, found "
        f"{arm.count(' OR ')} in: {arm}"
    )
