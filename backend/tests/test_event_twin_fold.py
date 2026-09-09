"""Guard: one game gets one card, and that card keeps both venues (#4100).

THE PAGE THIS EXISTS FOR. `/sports`, phone width, 2026-09-08 evening. Page one
carried two adjacent MLB cards for one game:

    Top 6th · Momentum shift · MLB   St. Louis Cardinals 24% / SF Giants 76%  0-2
    LIVE    · Live           · MLB   St.Louis Cardinals  38% / SF Giants 62%  (no score)

Two rows (`15307210` odds_api+ESPN, `15300848` statpal+Kalshi), two probabilities,
two spellings of one team. Ruling 048 is right to refuse the registry merge — the
rows share no provider id — so the reader's page is fixed at serve time instead.

WHAT EACH TEST HERE IS ACTUALLY DEFENDING. Not "a function returns a list". The
four ways this fold can go wrong and reach Alex:

* it does not fire at all, because a normaliser that works on "St. Louis" does
  not work on "St.Louis" (`test_alex_pair_folds_despite_the_missing_space`);
* it fires and serves the WORSE row, losing the live score
  (`test_the_scored_row_survives_even_when_the_twin_is_richer`);
* it fires and drops a venue, so the surviving card is one venue's opinion
  rather than the blend (`test_survivor_gains_the_twins_venues`);
* it fires on two rows that are genuinely different games
  (`test_doubleheader_is_never_folded`, `test_different_sports_never_fold`).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_twin_fold import (
    fold_twin_events,
    twin_fold_key,
    twin_identity_rank,
)

FIRST_PITCH = datetime(2026, 9, 9, 1, 45, tzinfo=timezone.utc)


class _Row:
    """The subset of `Event` the fold reads. Deliberately not a MagicMock — an
    auto-attribute mock makes every `espn_id` truthy and every `sport_id`
    unique, which would make this whole file pass without the fold existing."""

    def __init__(
        self,
        id,
        *,
        sport_id=1,
        home="San Francisco Giants",
        away="St. Louis Cardinals",
        commence_time=FIRST_PITCH,
        home_score=None,
        away_score=None,
        espn_id=None,
        external_id=None,
        sources=None,
    ):
        self.id = id
        self.sport_id = sport_id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.home_score = home_score
        self.away_score = away_score
        self.espn_id = espn_id
        self.external_id = external_id
        self.win_probability_sources = sources


def _cards():
    """The two production rows, as measured 2026-09-09."""
    anchored = _Row(
        15307210,
        home="San Francisco Giants",
        away="St. Louis Cardinals",
        home_score=2,
        away_score=0,
        espn_id="401764128",
        external_id="7fe8727a…",
        sources={"betting": 0.76, "espn": 0.74, "mlb": 0.75, "stat_model": 0.72},
    )
    kalshi = _Row(
        15300848,
        home="San Francisco Giants",
        away="St.Louis Cardinals",
        sources={"kalshi": 0.62, "mlb": 0.60},
    )
    return anchored, kalshi


def test_alex_pair_folds_despite_the_missing_space():
    anchored, kalshi = _cards()
    result = fold_twin_events([anchored, kalshi])

    assert [e.id for e in result.events] == [15307210]
    assert result.dropped_ids == [15300848]


def test_the_existing_normalisers_would_not_have_folded_it():
    """Pins WHY this module has its own key rather than reusing a matcher's.

    If `normalize_team_name` ever learns to close "St.Louis", this test goes red
    and the next reader gets to delete a helper instead of wondering why one
    exists. It is asserting a fact about the OTHER module, on purpose.
    """
    from app.utils.name_normalization import match_key, normalize_team_name

    spaced, squeezed = "St. Louis Cardinals", "St.Louis Cardinals"
    assert normalize_team_name(spaced) != normalize_team_name(squeezed)
    assert match_key(spaced) != match_key(squeezed)

    key_a = twin_fold_key(_Row(1, away=spaced))
    key_b = twin_fold_key(_Row(2, away=squeezed))
    assert key_a == key_b, "the fold's own key must close what the others leave open"


def test_survivor_gains_the_twins_venues():
    anchored, kalshi = _cards()
    result = fold_twin_events([anchored, kalshi])

    merged = result.merged_sources[15307210]
    assert merged["kalshi"] == 0.62, "Kalshi's price was stranded on the dropped row"
    assert set(merged) == {"betting", "espn", "mlb", "stat_model", "kalshi"}


def test_the_union_never_overwrites_a_venue_the_survivor_already_has():
    """Additive only. The survivor's own `mlb` reading (0.75) is the one the rest
    of the pipeline has already scored against; the twin's stale 0.60 must not
    silently replace it."""
    anchored, kalshi = _cards()
    merged = fold_twin_events([anchored, kalshi]).merged_sources[15307210]
    assert merged["mlb"] == 0.75


def test_the_scored_row_survives_even_when_the_twin_is_richer():
    """Richness is the wrong axis and points backwards in real pairs.

    Here the scoreless Kalshi row carries FIVE venues to the anchored row's one.
    Electing on source count would serve a live game with no score on it, which
    is the worse of the two cards Alex photographed.
    """
    anchored = _Row(
        900,
        home_score=2,
        away_score=0,
        espn_id="401764128",
        sources={"betting": 0.76},
    )
    richer_twin = _Row(
        100,
        away="St.Louis Cardinals",
        sources={"kalshi": 0.6, "polymarket": 0.6, "mlb": 0.6, "a": 0.5, "b": 0.5},
    )
    result = fold_twin_events([richer_twin, anchored])
    assert [e.id for e in result.events] == [900]
    assert result.dropped_ids == [100]


def test_the_score_outranks_the_provider_ids_on_its_own():
    """Isolates the FIRST rung of the election, which every other test here
    lets `espn_id` decide for it.

    A mutation that deletes the score term survived the rest of this file
    because the scored row in those fixtures is also the anchored one. Here the
    scoring row has no ids and one venue while the twin has both ids and three,
    so the only thing that can elect it is the score itself — which is the whole
    reason the rung is first: a live card with no score is the worse page.
    """
    scored_but_id_less = _Row(700, home_score=4, away_score=1, sources={"mlb": 0.8})
    anchored_scoreless = _Row(
        800,
        away="St.Louis Cardinals",
        espn_id="401764128",
        external_id="7fe8727a…",
        sources={"betting": 0.7, "polymarket": 0.7, "kalshi": 0.7},
    )
    result = fold_twin_events([anchored_scoreless, scored_but_id_less])
    assert [e.id for e in result.events] == [700]
    assert twin_identity_rank(scored_but_id_less) > twin_identity_rank(
        anchored_scoreless
    )


def test_election_is_stable_under_input_order():
    anchored, kalshi = _cards()
    forward = fold_twin_events([anchored, kalshi])
    backward = fold_twin_events([kalshi, anchored])
    assert [e.id for e in forward.events] == [e.id for e in backward.events]
    assert forward.merged_sources == backward.merged_sources


def test_identical_rows_break_the_tie_on_the_lower_id():
    """Two rows with nothing to tell them apart still must not flicker between
    polls — the served `id` is what a tap navigates to."""
    a, b = _Row(500), _Row(400)
    assert twin_identity_rank(b) > twin_identity_rank(a)
    assert [e.id for e in fold_twin_events([a, b]).events] == [400]


def test_a_four_row_pileup_collapses_to_one():
    """Production 2026-09-09 held four rows for one ITF match at one minute
    ("Tsitsipas @ Catini", ids 15307450/64/72/15307508). Pairwise folding would
    have left two."""
    rows = [
        _Row(i, away="Tsitsipas", home="Catini")
        for i in (15307450, 15307464, 15307472, 15307508)
    ]
    result = fold_twin_events(rows)
    assert [e.id for e in result.events] == [15307450]
    assert sorted(result.dropped_ids) == [15307464, 15307472, 15307508]


# ── the fold must NOT fire ───────────────────────────────────────────────────


def test_doubleheader_is_never_folded():
    """Same teams, same day, two games. The key carries the MINUTE for exactly
    this reason; a date-only key would delete the nightcap from the feed."""
    game_one = _Row(1, commence_time=FIRST_PITCH)
    game_two = _Row(2, commence_time=FIRST_PITCH + timedelta(hours=4))
    result = fold_twin_events([game_one, game_two])
    assert [e.id for e in result.events] == [1, 2]
    assert result.dropped_ids == []


def test_seconds_do_not_split_a_twin():
    """The minute is the unit: two ingests of one fixture disagreeing by 30
    seconds are still one fixture."""
    a = _Row(1, commence_time=FIRST_PITCH, home_score=1)
    b = _Row(2, commence_time=FIRST_PITCH.replace(second=42))
    assert len(fold_twin_events([a, b]).events) == 1


def test_different_sports_never_fold():
    a = _Row(1, sport_id=1)
    b = _Row(2, sport_id=2, away="St.Louis Cardinals")
    assert len(fold_twin_events([a, b]).events) == 2


def test_reversed_fixture_never_folds():
    """Home and away are not interchangeable — a mirrored row is a different
    row, and folding it would pick a winner between two orientations."""
    a = _Row(1, home="San Francisco Giants", away="St. Louis Cardinals")
    b = _Row(2, home="St. Louis Cardinals", away="San Francisco Giants")
    assert len(fold_twin_events([a, b]).events) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"home": None},
        {"away": ""},
        {"commence_time": None},
        {"sport_id": None},
    ],
)
def test_an_unkeyable_row_is_never_folded_and_never_dropped(kwargs):
    """A row the fold cannot key is a row it cannot prove is a twin. It passes
    through untouched — the fold's licence is that it admits no false positives,
    and silently eating a row it could not classify would be the opposite."""
    keyable = _Row(1, home_score=3)
    unkeyable = _Row(2, **kwargs)
    result = fold_twin_events([keyable, unkeyable])
    assert [e.id for e in result.events] == [1, 2]
    assert result.dropped_ids == []


def test_two_unkeyable_rows_both_survive():
    result = fold_twin_events(
        [_Row(1, commence_time=None), _Row(2, commence_time=None)]
    )
    assert [e.id for e in result.events] == [1, 2]


def test_a_single_row_page_is_untouched():
    only = _Row(7, sources={"kalshi": 0.5})
    result = fold_twin_events([only])
    assert result.events == [only]
    assert result.merged_sources == {} and result.dropped_ids == []


def test_empty_input():
    result = fold_twin_events([])
    assert result.events == [] and result.folded_count == 0


def test_order_of_the_surviving_page_is_preserved():
    """The caller sorts before it folds in some paths and after in others; the
    fold must never re-order what it keeps."""
    rows = [
        _Row(1, away="Aaa", home="Bbb"),
        _Row(2, away="Ccc", home="Ddd", home_score=1),
        _Row(3, away="Ccc", home="Ddd"),
        _Row(4, away="Eee", home="Fff"),
    ]
    assert [e.id for e in fold_twin_events(rows).events] == [1, 2, 4]


def test_a_poison_row_costs_itself_and_nothing_else():
    """Gotcha #42 on the hot path. `commence_time` as a string raises inside the
    key (`str.replace` takes no keyword arguments), and the whole `/api/feed`
    candidate stage runs through here — so the failure must be scoped to the row
    that caused it, leaving the real twin still folded.
    """
    poison = _Row(1, away="Bad Row", commence_time="2026-09-09T01:45:00Z")
    anchored, kalshi = _cards()
    result = fold_twin_events([poison, anchored, kalshi])

    assert [e.id for e in result.events] == [1, 15307210]
    assert result.dropped_ids == [15300848]


def test_a_failed_election_keeps_the_whole_group():
    """The other half of #42: the key succeeded, so the two rows ARE grouped, and
    then the election itself raises.

    The fold then cannot say which row the reader needs, so it keeps both. The
    page is left exactly as wrong as it was before — the duplicate Alex reported
    — and never emptier, which is the only failure direction that would be worse
    than the bug.

    `id` as a non-numeric makes the rank tuple's `-id` term raise inside
    `sorted`; the two rows still share a key, so the group is real.
    """
    a, b = _Row(1), _Row(2, away="St.Louis Cardinals")
    assert twin_fold_key(a) == twin_fold_key(b), "the group must exist to be tested"
    a.id = object()

    result = fold_twin_events([a, b])
    assert [e.id for e in result.events] == [a.id, 2]
    assert result.dropped_ids == []


def test_an_espn_id_outranks_a_bare_provider_id():
    """The two id rungs are ORDERED, and production has a pair that needs it.

    Measured 2026-09-09, UC Davis @ SMU on 09-12: `15307471` carries an ESPN
    game anchor and both prediction-market venues; `15308167` carries only an
    Odds API id and no `win_probability_sources` at all. Both are scheduled, so
    the score rung is silent and the ids decide alone. Rank `external_id` first
    and the surviving card is the empty one.
    """
    espn_row = _Row(
        15307471, espn_id="401858223", sources={"kalshi": 0.6, "polymarket": 0.6}
    )
    odds_api_row = _Row(15308167, away="St.Louis Cardinals", external_id="e00feee7…")
    result = fold_twin_events([odds_api_row, espn_row])
    assert [e.id for e in result.events] == [15307471]
    assert result.merged_sources == {}, "the dropped row had no venue to contribute"
