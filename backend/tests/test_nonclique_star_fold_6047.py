"""Guard: a third row stops making a La Liga page worse (#6047, under #2693).

THE PAGE THIS EXISTS FOR. `/sports/soccer_spain_la_liga`, 2026-09-17, three days
before kick-off: **Athletic Bilbao v Alavés is served THREE times**, two of the
cards side by side with different numbers — 58% and 83% — so a reader meets one
fixture twice and has no way to tell which number to distrust.

    15312047  espn    "Athletic Bilbao" v "Alavés"   espn_id 401882866, 0.5781
    15312903  kalshi  "Athletic Club"   v "Alaves"   no ids, 0.83
    15307698  kalshi  "Bilbao"          v "Alaves"   no ids, no price

The fold's name pass reaches `Athletic Bilbao` ≡ `Athletic Club` and
`Athletic Bilbao` ≡ `Bilbao`, and does not reach `Athletic Club` ≡ `Bilbao` —
two providers' short names for one club sharing no token. So the cluster is
connected but not a clique, and the clique refusal discarded it WHOLE.

**Both pairs fold on master today.** Driving `fold_twin_events` over doubles of
these exact rows:

    rows handed to the fold        dropped
    15312047 + 15312903            15312903
    15312047 + 15307698            15307698
    all three                      nothing

That is the defect in one line: a third row arrived and the reader got a third
card, not a second. `test_each_pair_folds_without_the_third_row_present` pins
the two pairs so the class cannot be re-read as "the name rule was too strict".

WHAT THESE TESTS DEFEND — the four ways rescuing a non-clique reaches a reader as
a WORSE page than three cards, each one a refusal this file requires:

* two real clubs chained through a vague row that matched both — the trap
  `_merge_soccer_name_variants` names, in the two shapes it can take
  (`test_two_anchored_madrid_clubs_never_chain_through_a_vague_row`,
  `test_a_vague_row_between_one_anchor_and_a_second_club_is_refused`);
* an anchor count that only LOOKS load-bearing because two different `espn_id`s
  would have refused the cluster anyway
  (`test_two_anchors_are_refused_even_when_no_espn_id_can_tell_them_apart`);
* three claims and nothing to be a claim ABOUT
  (`test_three_id_less_rows_never_fold`);
* two rows the venues disagree about, folded onto one card that must throw a
  scoreline away (`test_a_score_disagreement_refuses_the_star`).

And the rescue must stay inside soccer and inside the shape it was measured on:
`test_a_college_bucket_is_never_rescued`, `test_a_clique_of_three_is_unchanged`.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_twin_fold import (
    _group_is_id_anchored,
    fold_twin_events,
)

#: The real kick-off, which is what the ESPN row holds.
KICKOFF = datetime(2026, 9, 19, 14, 15, tzinfo=timezone.utc)

#: What the two Kalshi rows hold: `expected_expiration`, three hours later.
#: `recover_kalshi_occurrence_starts` puts the kick-off back at the top of the
#: fold (#5905), so these rows are written the way production stores them rather
#: than the way the fold ends up reading them — a test that pre-corrected them
#: would pass with that recovery deleted.
EXPIRATION = KICKOFF + timedelta(hours=3)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads, with `Event.sport` loaded.

    Deliberately not a MagicMock, for the reason
    `test_soccer_name_pair_fold_5918` gives: an auto-attribute mock makes every
    `espn_id` truthy, which is exactly the field the anchor count reads — this
    whole file would pass with `_star_on_one_anchor` deleted.
    """

    def __init__(
        self,
        id,
        home,
        away,
        *,
        sport_key="soccer_spain_la_liga",
        sport_id=1317,
        commence_time=KICKOFF,
        commence_time_source="espn",
        home_score=None,
        away_score=None,
        espn_id=None,
        external_id=None,
        status="scheduled",
        sources=None,
    ):
        self.id = id
        self.sport_id = sport_id
        self.sport = _Sport(sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.commence_time_source = commence_time_source
        self.home_score = home_score
        self.away_score = away_score
        self.espn_id = espn_id
        self.external_id = external_id
        self.status = status
        self.win_probability_sources = sources


def _ids(result):
    return [row.id for row in result.events]


# ── the production triple, as measured 2026-09-17 ───────────────────────────


def _anchored_row():
    return _Row(
        15312047,
        "Athletic Bilbao",
        "Alavés",
        espn_id="401882866",
        external_id="a995ad3266759e67c9f9b0617c184b71",
        sources={"betting": {"value": 0.5781}},
    )


def _athletic_club_ghost():
    return _Row(
        15312903,
        "Athletic Club",
        "Alaves",
        commence_time=EXPIRATION,
        commence_time_source="kalshi",
        sources={"kalshi": {"value": 0.83}},
    )


def _bilbao_ghost():
    return _Row(
        15307698,
        "Bilbao",
        "Alaves",
        commence_time=EXPIRATION,
        commence_time_source="kalshi",
    )


def _triple():
    return [_anchored_row(), _athletic_club_ghost(), _bilbao_ghost()]


def test_the_la_liga_triple_becomes_one_card():
    """The ship: one fixture, one card, and the two ghosts gone."""
    result = fold_twin_events(_triple())

    assert _ids(result) == [15312047]
    assert sorted(result.dropped_ids) == [15307698, 15312903]


def test_the_survivor_is_the_anchored_row_and_the_83_percent_is_the_one_that_goes():
    """Which card a reader keeps is the whole point of electing rather than hiding.

    58% is the ESPN-anchored row's number and 83% is the id-less ghost's. Serving
    the ghost would replace a duplicate with a wrong single card, which is worse
    than the bug.
    """
    result = fold_twin_events(_triple())

    # `events[0]` is 15312047 on master too, where nothing folded at all — the
    # length assertion is what stops this passing vacuously.
    assert len(result.events) == 1
    survivor = result.events[0]

    assert (survivor.id, survivor.espn_id) == (15312047, "401882866")
    assert survivor.win_probability_sources == {"betting": {"value": 0.5781}}


def test_the_ghosts_price_is_carried_onto_the_surviving_card():
    """The fold merges; it never hides. The Kalshi leg must reach the survivor."""
    result = fold_twin_events(_triple())

    assert result.merged_sources[15312047]["kalshi"] == {"value": 0.83}


def test_each_pair_folds_without_the_third_row_present():
    """The control that names the defect: master folds both pairs already.

    Neither name rule, bucket nor clock bound moves in #6047 — the only thing
    that changes is that the third row stops vetoing these two folds. If this
    test ever fails, the finding above has been misread and the rescue is
    reaching pairs the predicate never licensed.
    """
    with_club = fold_twin_events([_anchored_row(), _athletic_club_ghost()])
    with_bilbao = fold_twin_events([_anchored_row(), _bilbao_ghost()])

    assert with_club.dropped_ids == [15312903]
    assert with_bilbao.dropped_ids == [15307698]


def test_the_order_rows_arrive_in_does_not_decide_the_card():
    """A serve-time fold runs on whatever order a query returned."""
    forward = fold_twin_events(_triple())
    backward = fold_twin_events(list(reversed(_triple())))

    assert _ids(forward) == _ids(backward) == [15312047]


# ── the non-transitivity trap, in both shapes it can take ───────────────────


def test_two_anchored_madrid_clubs_never_chain_through_a_vague_row():
    """`Madrid` ⊆ `Real Madrid` and `Madrid` ⊆ `Atlético Madrid`.

    The vague row matches both and the two clubs do not match each other. Two
    member groups are anchored, so the cluster is not a star and the refusal
    stands — all three rows survive, exactly as on master.
    """
    rows = [
        _Row(1, "Madrid", "Getafe"),
        _Row(2, "Real Madrid", "Getafe", espn_id="401000001"),
        _Row(3, "Atlético Madrid", "Getafe", espn_id="401000002"),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2, 3]
    assert result.dropped_ids == []


def test_two_anchors_are_refused_even_when_no_espn_id_can_tell_them_apart():
    """The anchor count must do real work, not inherit another guard's refusal.

    Written because the test above would pass with the anchor clause deleted:
    two different `espn_id`s make the cluster `_objectively_different_games` on
    their own. Here the two clubs are anchored by `external_id` only and carry no
    scores, so NOTHING except the anchor count refuses this cluster.
    """
    rows = [
        _Row(1, "Madrid", "Getafe"),
        _Row(2, "Real Madrid", "Getafe", external_id="a" * 32),
        _Row(3, "Atlético Madrid", "Getafe", external_id="b" * 32),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2, 3]
    assert result.dropped_ids == []


def test_a_vague_row_between_one_anchor_and_a_second_club_is_refused():
    """The star clause is about the ANCHOR, not about the row in the middle.

    One anchor (`Real Madrid`), a vague row that matches it, and a second club
    that matches only the vague row. The cluster has exactly one anchored group,
    so the anchor count alone would admit it — and it must not, because
    `Atlético Madrid` never claimed to be the anchored fixture. Every member has
    to match the anchor itself.
    """
    rows = [
        _Row(1, "Real Madrid", "Getafe", espn_id="401000001"),
        _Row(2, "Madrid", "Getafe"),
        _Row(3, "Atlético Madrid", "Getafe"),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2, 3]
    assert result.dropped_ids == []


def test_three_id_less_rows_never_fold():
    """Three claims and nothing to be a claim about.

    With no anchor there is no row that is known to be one real fixture, so
    nothing licenses collapsing a chain — the refusal is master's.
    """
    rows = [
        _Row(1, "Athletic Bilbao", "Alavés"),
        _Row(2, "Athletic Club", "Alaves"),
        _Row(3, "Bilbao", "Alaves"),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2, 3]
    assert result.dropped_ids == []


def test_a_score_disagreement_refuses_the_star():
    """Two venues reporting different scorelines are not one card to be elected.

    A fold here would have to throw a result away, and neither is ours to
    discard — the same control `_objectively_different_games` applies to the
    catch-all pass.
    """
    rows = [
        _Row(1, "Athletic Bilbao", "Alavés", espn_id="401882866", status="completed"),
        _Row(2, "Athletic Club", "Alaves", home_score=2, away_score=1),
        _Row(3, "Bilbao", "Alaves", home_score=1, away_score=1),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2, 3]
    assert result.dropped_ids == []


def test_one_scoreline_and_one_silent_ghost_still_folds():
    """Absence is not disagreement — the #6047 shape is a phantom with no score.

    The control above must refuse a CONTRADICTION, not any cluster where one row
    knows the score. This is the finished-card-plus-phantom pair from #6047's own
    filing, with the third row that made it a triple.
    """
    rows = [
        _Row(
            1,
            "Athletic Bilbao",
            "Alavés",
            espn_id="401882866",
            home_score=1,
            away_score=1,
            status="completed",
        ),
        _Row(
            2,
            "Athletic Club",
            "Alaves",
            commence_time=EXPIRATION,
            commence_time_source="kalshi",
        ),
        _Row(
            3,
            "Bilbao",
            "Alaves",
            commence_time=EXPIRATION,
            commence_time_source="kalshi",
        ),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1]
    assert sorted(result.dropped_ids) == [2, 3]


def test_two_anchored_rows_and_a_ghost_are_refused_in_either_arrival_order():
    """Exactly ONE anchor, and the count is load-bearing rather than tidy.

    Here both `Athletic Bilbao` (ESPN) and `Athletic Club` (a provider hash) are
    anchored and `Bilbao` matches only the first. Every member does match the
    FIRST anchor — so a rule that merely required "some anchor everybody agrees
    with" would fold this list and refuse the same three rows handed over in the
    opposite order, because the anchor it centred on would change. A serve-time
    fold whose card depends on the order a query returned rows in is a worse
    thing than the duplicate it removes.

    So the refusal is deliberate and it is master's behaviour: this shape did not
    occur once in the 6,501-row population #6047 was measured on, and the rescue
    goes no wider than the shape that did.
    """
    rows = [
        _Row(1, "Athletic Bilbao", "Alavés", espn_id="401882866"),
        _Row(2, "Athletic Club", "Alaves", external_id="d" * 32),
        _Row(3, "Bilbao", "Alaves"),
    ]

    forward = fold_twin_events(rows)
    backward = fold_twin_events(list(reversed(rows)))

    assert sorted(_ids(forward)) == [1, 2, 3]
    assert sorted(_ids(backward)) == [1, 2, 3]
    assert forward.dropped_ids == backward.dropped_ids == []


def test_a_refused_cluster_never_costs_the_page_its_other_folds():
    """gotcha #42, asked of this pass: one cluster's refusal is its own.

    A La Liga page carrying BOTH an unrescuable chain (three id-less Madrid rows)
    and an ordinary twin pair must still fold the pair. Written because the
    cheapest wrong way to write the anchor test — reading `anchored[0]` before
    checking there is one — raises on the chain, and a fold that raises is
    swallowed by the caller and serves the whole page unfolded.
    """
    chain = [
        _Row(1, "Madrid", "Getafe"),
        _Row(2, "Real Madrid", "Getafe"),
        _Row(3, "Atlético Madrid", "Getafe"),
    ]
    pair = [
        _Row(
            4,
            "Celta Vigo",
            "Málaga",
            commence_time=KICKOFF + timedelta(hours=2),
            espn_id="401882885",
        ),
        _Row(
            5,
            "RC Celta de Vigo",
            "Malaga CF",
            commence_time=KICKOFF + timedelta(hours=2),
        ),
    ]

    result = fold_twin_events(chain + pair)

    assert sorted(_ids(result)) == [1, 2, 3, 4]
    assert result.dropped_ids == [5]


# ── the rescue stays inside soccer, and inside the shape it was measured on ──


def test_a_college_bucket_is_never_rescued():
    """`Texas` ⊆ `Texas State` and `Texas` ⊆ `Texas A&M` are three schools.

    The soccer gate is what keeps the token rule off a vocabulary it was never
    measured on, and the rescue runs strictly inside that pass.
    """
    rows = [
        _Row(
            1,
            "Texas",
            "Baylor",
            sport_key="americanfootball_ncaaf",
            sport_id=42,
            espn_id="401500001",
        ),
        _Row(
            2, "Texas State", "Baylor", sport_key="americanfootball_ncaaf", sport_id=42
        ),
        _Row(3, "Texas A&M", "Baylor", sport_key="americanfootball_ncaaf", sport_id=42),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1, 2, 3]
    assert result.dropped_ids == []


def test_an_unloaded_sport_never_rescues():
    """No `Event.sport` in memory means this pass has nothing it may say.

    `loaded_sport_key` answers `None` rather than emitting IO, and the soccer
    pass — rescue included — must stand down rather than guess the league.
    """
    rows = _triple()
    for row in rows:
        row.sport = None

    result = fold_twin_events(rows)

    assert sorted(_ids(result)) == [15307698, 15312047, 15312903]


def test_a_clique_of_three_is_unchanged():
    """The rescue is reached only after the clique test says no.

    Three vocabularies for one club, every pair matching: this folded before
    #6047 and must fold by the same route, not by the rescue.
    """
    rows = [
        _Row(1, "Celta Vigo", "Málaga", espn_id="401882885"),
        _Row(2, "RC Celta de Vigo", "Malaga CF"),
        _Row(3, "Celta", "Malaga"),
    ]

    result = fold_twin_events(rows)

    assert _ids(result) == [1]
    assert sorted(result.dropped_ids) == [2, 3]


def test_a_different_kick_off_is_still_a_different_fixture():
    """The clock bound is the caller's and the rescue re-asks it, not around it.

    The `Bilbao` row is moved 40 minutes past the drift bound, so it is not a
    claim on this fixture at all. The pair that remains still folds.
    """
    rows = _triple()
    rows[2].commence_time_source = "espn"
    rows[2].commence_time = KICKOFF + timedelta(minutes=40)

    result = fold_twin_events(rows)

    assert sorted(_ids(result)) == [15307698, 15312047]
    assert result.dropped_ids == [15312903]


def test_the_reverse_fixture_is_never_a_claim_on_this_one():
    """Orientation is kept by the predicate and the rescue asks the predicate."""
    rows = [
        _Row(1, "Athletic Bilbao", "Alavés", espn_id="401882866"),
        _Row(2, "Athletic Club", "Alaves"),
        _Row(3, "Alaves", "Bilbao"),
    ]

    result = fold_twin_events(rows)

    assert sorted(_ids(result)) == [1, 3]
    assert result.dropped_ids == [2]


def test_a_b_team_is_not_its_first_team():
    """The squad-marker refusal is inside `same_fixture`, which the rescue calls."""
    rows = [
        _Row(1, "Athletic Bilbao", "Alavés", espn_id="401882866"),
        _Row(2, "Athletic Club", "Alaves"),
        _Row(3, "Athletic Bilbao B", "Alaves"),
    ]

    result = fold_twin_events(rows)

    assert sorted(_ids(result)) == [1, 3]
    assert result.dropped_ids == [2]


# ── the anchor test itself ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "row, expected",
    [
        (_Row(1, "A", "B", espn_id="401000001"), True),
        (_Row(2, "A", "B", external_id="c" * 32), True),
        (_Row(3, "A", "B"), False),
    ],
)
def test_a_group_is_anchored_by_either_provider_id(row, expected):
    """Both columns count, and neither is inferred from a name or a clock."""
    assert _group_is_id_anchored([row]) is expected


def test_one_anchored_row_anchors_the_whole_group():
    """A group is the rows that already share the strict key — any anchor does."""
    assert _group_is_id_anchored([_Row(1, "A", "B"), _Row(2, "A", "B", espn_id="x")])
