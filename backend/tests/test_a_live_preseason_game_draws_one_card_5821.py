"""Guard: a LIVE preseason game gets one card, not two (#5821).

THE PAGE THIS EXISTS FOR. `/search?q=wild`, phone width, 2026-09-24 ~01:15Z,
two adjacent live cards for one game with two different numbers:

    NHL            ● 2nd Period   Dallas Stars 0  50% / Minnesota Wild 0  50%
    NHL PRESEASON  ● LIVE         Dallas Stars 0  59% / Minnesota Wild 0  41%

`15313798` (`icehockey_nhl`, espn_id 401886429, StatPal 650468, kick-off
00:00:00Z, prices kalshi + stat_model) and `15318094` (`icehockey_nhl_preseason`,
Odds-API-born, no espn_id, kick-off 00:08:46Z, prices betting). #7915's
season-variant pass folds this exact pair once it is Final and refused it while
live, because it could not tell which row's score was current.

It can: the ESPN-anchored parent is the faster score rail (Rangers at Devils,
2026-09-21 23:00Z, parent 1-2 while the variant read 0-1 at the same instant),
and `twin_identity_rank` already elects the `espn_id` row. So the licence is
"parent ESPN-anchored, variant not", and every arm below is a way that licence
could go wrong and reach a reader:

* it does not fire, and the reader still sees the live game twice;
* it fires and elects the VARIANT, showing the slower score as the only score;
* it fires and drops the variant's price, so the one card is one venue's number;
* it fires on a pair nothing can rank (both anchored, neither anchored, half
  anchored), or on a status it does not know;
* it leaks into the #8100 passes, whose asymmetry says nothing about freshness.
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import (
    _VARIANT_COLLAPSIBLE_STATUSES,
    fold_twin_events,
)

PUCK_DROP = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)

NHL = "icehockey_nhl"
NHL_PRE = "icehockey_nhl_preseason"


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


class _Row:
    """The subset of `Event` the fold reads — not a MagicMock (see #4100's suite:
    an auto-attribute mock makes every `espn_id` truthy)."""

    def __init__(
        self,
        id,
        *,
        sport_key,
        commence_time,
        home="Minnesota Wild",
        away="Dallas Stars",
        home_score=0,
        away_score=1,
        espn_id=None,
        external_id=None,
        sources=None,
        status="live",
    ):
        self.id = id
        self.sport_id = abs(hash(sport_key)) % 10**6
        self.sport = _Sport(self.sport_id, sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.home_score = home_score
        self.away_score = away_score
        self.espn_id = espn_id
        self.external_id = external_id
        self.win_probability_sources = sources
        self.status = status
        self.opening_home_probability = None
        self.opening_away_probability = None


def _stars_wild(**parent_overrides):
    """The two production rows, as read 2026-09-24 01:31Z."""
    parent_kwargs = dict(
        sport_key=NHL,
        commence_time=PUCK_DROP,
        espn_id="401886429",
        sources={"kalshi": 0.5, "stat_model": 0.5},
    )
    parent_kwargs.update(parent_overrides)
    parent = _Row(15313798, **parent_kwargs)
    variant = _Row(
        15318094,
        sport_key=NHL_PRE,
        commence_time=PUCK_DROP + timedelta(minutes=8, seconds=46),
        external_id="885c2b962a6750f20eedfb2d57d1ca50",
        sources={"betting": 0.41, "betting_book_count": 7},
    )
    return parent, variant


def test_the_live_stars_wild_game_is_one_card():
    """The ship. Both live rows in, one card out."""
    parent, variant = _stars_wild()

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 1, "one live game must be one card"


def test_the_survivor_is_the_espn_row_and_its_score_is_the_one_shown():
    """The hazard the old refusal guarded, asserted in the direction that matters.

    The rows disagree the way Rangers at Devils did — the parent ahead — and the
    card must print the parent's score. If the election ever flipped to the
    variant this arm fails rather than passing for a new reason.
    """
    parent, variant = _stars_wild(home_score=2, away_score=1)
    variant.home_score, variant.away_score = 1, 1

    result = fold_twin_events([variant, parent])

    (survivor,) = result.events
    assert survivor.id == 15313798, "the ESPN-anchored parent carries the live score"
    assert (survivor.home_score, survivor.away_score) == (2, 1)
    assert result.dropped_ids == [15318094]
    assert result.survivor_of == {15318094: 15313798}


def test_the_one_card_keeps_the_variants_price():
    """The 59% on the second card was the betting price. A fold that drops it is
    a filter wearing a fold's name, and the blend is the product."""
    parent, variant = _stars_wild()

    result = fold_twin_events([parent, variant])

    merged = result.merged_sources[15313798]
    assert set(merged) == {"kalshi", "stat_model", "betting", "betting_book_count"}
    assert merged["kalshi"] == 0.5, "the survivor's own readings are never overwritten"


def test_a_final_espn_row_absorbs_a_variant_still_reading_live():
    """`15316894`/`15312791` on 2026-09-21: one side Final, the other still live.
    With the Final on the ESPN row the card shows the Final."""
    parent, variant = _stars_wild(status="completed", home_score=3, away_score=2)

    result = fold_twin_events([parent, variant])

    (survivor,) = result.events
    assert survivor.id == 15313798
    assert survivor.status == "completed"


def test_a_variant_with_the_only_score_keeps_it():
    """Rung 1 of the election outranks the anchor: a live ESPN row that has not
    posted a score yet loses nothing by showing the variant's. Asserted so the
    direction is a decision, not an accident."""
    parent, variant = _stars_wild(home_score=None, away_score=None)

    result = fold_twin_events([parent, variant])

    (survivor,) = result.events
    assert survivor.id == 15318094
    assert (survivor.home_score, survivor.away_score) == (0, 1)


def test_a_live_pair_where_both_rows_carry_espn_ids_stays_two_cards():
    """Two ESPN ids is two things ESPN knows about, and nothing ranks their scores."""
    parent, variant = _stars_wild()
    variant.espn_id = "401886430"

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_a_live_pair_where_neither_row_carries_an_espn_id_stays_two_cards():
    parent, variant = _stars_wild(espn_id=None)

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_the_licence_reads_the_parent_side_not_whichever_side_is_anchored():
    """The ESPN id on the VARIANT and none on the parent inverts the measured
    shape; the variant would then be elected on a rail nobody measured."""
    parent, variant = _stars_wild(espn_id=None)
    variant.espn_id = "401886429"

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_a_half_anchored_parent_group_stays_two_cards():
    """A parent GROUP holding one anchored and one unanchored row at the same
    minute is unmeasured; the licence needs every parent row anchored."""
    parent, variant = _stars_wild()
    parent_twin = _Row(
        15313799,
        sport_key=NHL,
        commence_time=PUCK_DROP,
        sources={"polymarket": 0.52},
    )

    result = fold_twin_events([parent, parent_twin, variant])

    ids = sorted(e.id for e in result.events)
    assert 15318094 in ids, "the variant must not fold into a half-anchored group"


def test_an_unknown_status_is_still_refused():
    parent, variant = _stars_wild()
    variant.status = "suspended"

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_live_did_not_join_the_set_the_other_passes_read():
    """`_VARIANT_COLLAPSIBLE_STATUSES` still governs the #8100 passes, whose
    anchored-vs-id-less asymmetry says nothing about which score is current."""
    assert "live" not in _VARIANT_COLLAPSIBLE_STATUSES


def test_a_live_anchored_claim_pair_on_one_sport_key_is_still_two_cards():
    """#8100's population (one sport key, one id-less claim, minutes apart) is
    untouched by this licence: live there stays double."""
    anchored = _Row(
        1,
        sport_key=NHL,
        commence_time=PUCK_DROP,
        espn_id="401886429",
    )
    claim = _Row(
        2,
        sport_key=NHL,
        commence_time=PUCK_DROP + timedelta(minutes=6),
        sources={"polymarket": 0.41},
    )

    result = fold_twin_events([anchored, claim])

    assert len(result.events) == 2
