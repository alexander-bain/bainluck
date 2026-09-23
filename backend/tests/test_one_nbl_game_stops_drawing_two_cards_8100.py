"""Guard: one NBL game gets one card, not two (#8100).

THE PAGE THIS EXISTS FOR. `bainluck.com/search?q=Perth+Wildcats`, 390px,
2026-09-22 ~22:5xZ. Two adjacent cards for one game:

    NBL   Sep 24 4:30 AM   Perth Wildcats 41%  / Adelaide 36ers 59%
    NBL   Sep 24 4:36 AM   Perth Wildcats (No price yet) / Adelaide 36ers

The rows are `15314490` (Polymarket-born, `commence_time_source`
`polymarket_venue`, NO `espn_id` and NO `external_id`, carrying the only price
there is — `{"polymarket": 0.41}`) and `15316489` (Odds-API-born, `external_id`
set, and otherwise EMPTY: no sources, no odds snapshots, no opening line).

WHY NO EXISTING PASS REACHED IT, which is the whole point of the new one:

* the strict key is exact-minute and these two providers are six minutes apart;
* `_merge_soccer_name_variants` is the only pass that widens the clock for two
  rows sharing a sport key, and it is soccer-gated on purpose;
* `_merge_season_variant_kickoffs` widens the clock with no name rule, but its
  licence is a LEAGUE asymmetry (`*_preseason` beside its parent) and two
  `basketball_nbl` rows cannot satisfy it.

WHAT EACH ARM HERE IS ACTUALLY DEFENDING. Not "a function returns a list" — the
ways this pass can go wrong and reach Alex, in both directions:

* it does not fire, and search still draws the game twice;
* it fires and the reader LOSES the 41%, because on this population the fold
  elects the anchored row and the anchored row is the empty one (#7929's lesson
  from the other side: the survivor must not be the row without the number);
* it fires on the SYMMETRIC id-less pair — the 954 esports pairs measured on
  2026-09-22 that #8100 could not bound, and the reason the licence is an
  asymmetry rather than a clock;
* it fires on two ANCHORED rows, five of whose sixteen measured pairs hold two
  different scorelines and so are two real games;
* it fires on an asymmetric pair that nonetheless holds two scorelines (1 of the
  15 measured — the control #8100 said it could not arm);
* it fires on a LIVE pair and elects the stale copy, showing a wrong score as
  the only score;
* it fires on a chain, a swapped orientation, a different opponent, or a pair
  past the bound;
* it widens the soccer populations #5918 and #5905 own, or takes something off
  the same-minute case #2866 already closed.

WHAT THIS PASS DELIBERATELY DOES NOT CLOSE, pinned below: the two NPB pairs
(`Hiroshima Carp` v `Hiroshima Toyo Carp`, `Yokohama BayStars` v `Yokohama DeNA
BayStars`) are at the SAME minute and differ on NAMES, and this pass keeps the
strict key's exact squashed names. That is #8100's proposal 2. It HAS since
shipped, as its own pass with its own census —
`_merge_anchored_claim_name_variants`, guarded by
`test_the_npb_league_page_stops_drawing_two_cards_8100.py` — so the arm below
now asks THIS pass the question instead of asking the whole fold.
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import (
    ANCHORED_CLAIM_KICKOFF_DRIFT,
    SOCCER_KICKOFF_DRIFT,
    _merge_anchored_claim_kickoffs,
    fold_twin_events,
    twin_fold_key,
)

#: The measured kick-off of the production specimen, to the second.
TIP_OFF = datetime(2026, 9, 24, 11, 30, tzinfo=timezone.utc)

#: The measured disagreement between the two providers on that specimen.
PERTH_DRIFT = timedelta(minutes=6)

NBL = "basketball_nbl"
LA_LIGA = "soccer_spain_la_liga"


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


class _Row:
    """The subset of `Event` the fold reads.

    Deliberately not a MagicMock, for the reason the #4100 and #7915 suites
    give: an auto-attribute mock makes every `external_id` truthy and every
    `sport_id` unique, which would make this whole file pass without the pass
    existing — and `external_id` truthiness is precisely this licence's input.
    """

    def __init__(
        self,
        id,
        *,
        sport_key=NBL,
        sport_id=None,
        home="Perth Wildcats",
        away="Adelaide 36ers",
        commence_time=TIP_OFF,
        home_score=None,
        away_score=None,
        espn_id=None,
        external_id=None,
        sources=None,
        status="scheduled",
        load_sport=True,
        opening_home=None,
        opening_away=None,
    ):
        self.id = id
        # One sport row per key, the way production stores it.
        self.sport_id = (
            sport_id if sport_id is not None else abs(hash(sport_key)) % 10**6
        )
        self.sport = _Sport(self.sport_id, sport_key) if load_sport else None
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.home_score = home_score
        self.away_score = away_score
        self.espn_id = espn_id
        self.external_id = external_id
        self.win_probability_sources = sources
        self.status = status
        self.opening_home_probability = opening_home
        self.opening_away_probability = opening_away


def _perth_pair(**overrides):
    """The two production rows, as measured 2026-09-22 23:4xZ.

    The asymmetry is the specimen's own, not a convenience: the id-less row is
    the one holding the price and the anchored row holds nothing at all.
    """
    claim = _Row(
        15314490,
        commence_time=TIP_OFF,
        sources={"polymarket": 0.41},
        **overrides,
    )
    anchored = _Row(
        15316489,
        commence_time=TIP_OFF + PERTH_DRIFT,
        external_id="eeae390a",
        sources=None,
        **overrides,
    )
    return claim, anchored


def test_the_search_page_stops_drawing_one_game_as_two_cards():
    """The ship. Both rows in, one card out."""
    claim, anchored = _perth_pair()

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1, "one game must be one card"
    assert result.dropped_ids in ([15314490], [15316489])


def test_the_one_card_still_says_forty_one_percent():
    """🔴 THE FOLD ELECTS THE EMPTY ROW ON THIS POPULATION, EVERY TIME.

    `twin_identity_rank` puts "carries a provider id" above "carries a venue's
    reading", so the survivor here is `15316489` — the row with no sources at
    all. Without the union the reader trades two cards for one card reading
    "No price yet", which is a worse page than the bug. This arm is the ship's
    real acceptance test, not the card count above it.
    """
    claim, anchored = _perth_pair()

    result = fold_twin_events([claim, anchored])

    survivor = result.events[0]
    assert survivor.id == 15316489, "the anchored row is the one that survives"
    assert result.merged_sources[survivor.id] == {"polymarket": 0.41}


def test_two_id_less_rows_are_refused():
    """🔴 THE 954. This is the whole reason the licence is an asymmetry.

    Measured 2026-09-22 over the whole `events` table: of 985 adjacent pairs
    sharing both squashed names and sitting 0–15 minutes apart, 954 have NO
    provider id on either side and 954 of those are the `esports` bulk #8100
    could not bound. A symmetric pair is a question this module cannot answer,
    so it stays two cards.
    """
    claim, anchored = _perth_pair()
    anchored.external_id = None

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_two_anchored_rows_are_refused():
    """The same refusal from the other side, and it is not symmetry for its own
    sake: five of the sixteen measured both-anchored pairs hold two DIFFERENT
    scorelines, which is two real games."""
    claim, anchored = _perth_pair()
    claim.external_id = "3dee8218"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_two_different_scorelines_refuse_even_an_asymmetric_pair():
    """🔴 THE ARMED CONTROL. #8100 recorded that the scoreline control is
    VACUOUS on the population the clock alone would have folded — 111k scoreless
    esports rows — and would not build on an unarmed guard. On THIS pass's
    population it fires: 1 of the 15 measured asymmetric pairs holds two
    different scorelines. Neither score is ours to discard, so both rows stay.
    """
    claim, anchored = _perth_pair()
    claim.status = anchored.status = "completed"
    claim.home_score, claim.away_score = 2, 0
    anchored.home_score, anchored.away_score = 4, 0

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_one_row_carrying_a_score_the_other_lacks_is_not_evidence():
    """The other half of that rule, and it is load-bearing rather than lenient:
    three of the measured asymmetric pairs have a score on exactly one side
    (`--- vs 3-9`). A refusal on ABSENCE would refuse most of the population
    this pass exists for."""
    claim, anchored = _perth_pair()
    claim.status = anchored.status = "completed"
    anchored.home_score, anchored.away_score = 3, 9

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1


def test_a_live_pair_is_left_as_two_cards():
    """While a game is live the asymmetry this pass can read is outranked by one
    it cannot: which row's score is current. Electing the stale copy shows a
    wrong score as the ONLY score, which is worse than showing the game twice."""
    claim, anchored = _perth_pair()
    claim.status = anchored.status = "live"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_one_live_row_is_enough_to_refuse_the_pair():
    """The refusal is per GROUP, not per pair-of-statuses."""
    claim, anchored = _perth_pair()
    anchored.status = "in_progress"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_a_pair_past_the_bound_stays_two_cards():
    """Outside the bound means two cards, not a closer look."""
    claim, anchored = _perth_pair()
    anchored.commence_time = TIP_OFF + timedelta(minutes=13)

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_a_pair_exactly_on_the_bound_still_folds():
    """The bound is inclusive, and saying so here is what stops a later edit
    turning `<=` into `<` without anybody noticing."""
    claim, anchored = _perth_pair()
    anchored.commence_time = TIP_OFF + ANCHORED_CLAIM_KICKOFF_DRIFT

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1


def test_the_bound_sits_in_the_empty_band_it_was_measured_into():
    """Pins the SIZING, so widening it later is a decision and not a drift.

    Below: the asymmetric population measured on 2026-09-22 runs 0.4 → 9.7
    minutes (14 pairs, three sports), and the reader-reachable defect sits at
    6.0. Above: the next asymmetric pair in the whole table is at 15.0 minutes,
    which is why the bound is NOT the 15 the issue proposed — that would sit on
    a pair rather than clear of it. A value that leaves this band is a different
    ship and should have to change this arm first.
    """
    assert ANCHORED_CLAIM_KICKOFF_DRIFT > timedelta(minutes=9, seconds=42)
    assert ANCHORED_CLAIM_KICKOFF_DRIFT < timedelta(minutes=15)
    # And it is genuinely wider than the soccer bound, which is why this is a
    # new pass rather than a relaxation of that one.
    assert ANCHORED_CLAIM_KICKOFF_DRIFT > SOCCER_KICKOFF_DRIFT


def test_a_swapped_orientation_is_not_the_same_fixture():
    """Home and away are not interchangeable."""
    claim, anchored = _perth_pair()
    anchored.home_team_name, anchored.away_team_name = (
        claim.away_team_name,
        claim.home_team_name,
    )

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_a_different_opponent_in_the_same_bucket_never_folds():
    """The bucket is a day of one league: a candidate finder, not a licence."""
    claim, anchored = _perth_pair()
    anchored.away_team_name = "Sydney Kings"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_the_clock_pass_still_cannot_reach_a_name_variant():
    """🟡 THIS PASS WIDENS THE CLOCK ONLY, AND THAT IS STILL TRUE.

    `Hiroshima Carp` and `Hiroshima Toyo Carp` are one club and two rows, at the
    same minute. This pass keeps the strict key's EXACT squashed names, so it
    cannot reach them and must not start to.

    🔴 THE SUBJECT MOVED, AND THE ASSERTION DID NOT WEAKEN. Until #8100's second
    half shipped, this arm asked `fold_twin_events` — the whole fold — because
    no pass in it could reach a name variant, so the front door was a faithful
    proxy for this one. `_merge_anchored_claim_name_variants` now closes exactly
    this specimen through that same front door (the NPB suite is where that ship
    is proven), so the proxy became a confound: asked end to end, this arm would
    now be reporting the new pass's behaviour under the old pass's name. It is
    asked of the clock pass directly instead. If IT ever folds a name variant,
    somebody has merged the two licences without the census for the composition.
    """
    claim = _Row(15313545, home="Hiroshima Carp", away="Yomiuri Giants")
    anchored = _Row(
        15317392,
        home="Hiroshima Toyo Carp",
        away="Yomiuri Giants",
        external_id="3dee8218",
    )
    groups = {}
    for row in (claim, anchored):
        groups.setdefault(twin_fold_key(row), []).append(row)
    assert len(groups) == 2, "the strict key splits them on the NAME"

    assert (
        _merge_anchored_claim_kickoffs(groups) is groups
    ), "the clock half of #8100 has no name rule and must merge nothing here"


def test_a_chain_of_three_is_discarded_whole():
    """The clique refusal. Here the ASYMMETRY is what breaks the chain, not the
    clock: three groups hold two on the same side of anchored/id-less, that pair
    is refused, and the cluster goes whole rather than the pass choosing which
    link to keep."""
    a = _Row(1, commence_time=TIP_OFF, external_id="x")
    b = _Row(2, commence_time=TIP_OFF + timedelta(minutes=5))
    c = _Row(3, commence_time=TIP_OFF + timedelta(minutes=10))

    result = fold_twin_events([a, b, c])

    assert len(result.events) == 3, "a chain is not a fixture"


def test_the_same_minute_case_is_untouched():
    """The strict key still folds a same-minute pair on its own. If this arm
    goes red the new pass has taken something off the old one."""
    claim, anchored = _perth_pair()
    anchored.commence_time = TIP_OFF

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1


def test_a_soccer_pair_past_the_soccer_bound_is_still_two_cards():
    """🔴 NO SILENT WIDENING OF SOMEBODY ELSE'S POPULATION.

    Measured 2026-09-22: ZERO soccer pairs appear in the asymmetric 0–15 minute
    band, so this pass is inert on soccer today. It is not soccer-GATED though,
    so this arm is what keeps it honest — two soccer rows eight minutes apart
    that are symmetric about the anchor stay two cards, exactly as
    `SOCCER_KICKOFF_DRIFT` (5 minutes) decides today.
    """
    left = _Row(
        10,
        sport_key=LA_LIGA,
        home="Getafe",
        away="Deportivo",
        commence_time=TIP_OFF,
        espn_id="401001",
    )
    right = _Row(
        11,
        sport_key=LA_LIGA,
        home="Getafe",
        away="Deportivo",
        commence_time=TIP_OFF + timedelta(minutes=8),
        espn_id="401002",
    )

    result = fold_twin_events([left, right])

    assert len(result.events) == 2


def test_the_third_row_folds_when_it_is_an_id_less_claim():
    """🟡 A SHAPE #7915 PINNED AS AN OPEN DECISION, AND THIS IS THE DECISION.

    `test_a_group_that_already_holds_both_sides_is_left_alone` records three rows
    for one fixture — the same-minute pair #2866 folds, plus a third a few
    minutes later — and leaves the third as a second card, saying in as many
    words that folding it later must be "a measured decision, not a drift".

    It is folded here, and only when the third row is an id-less CLAIM: the
    already-folded group carries an anchor, so the asymmetry this pass reads is
    present and the claim is a claim about that anchored fixture. A third row
    that is itself ANCHORED is still refused, and #7915's arm keeps that shape.
    """
    same_minute_anchored = _Row(20, commence_time=TIP_OFF, espn_id="401001")
    same_minute_claim = _Row(21, commence_time=TIP_OFF)
    late_claim = _Row(22, commence_time=TIP_OFF + timedelta(minutes=8))

    result = fold_twin_events([same_minute_anchored, same_minute_claim, late_claim])

    assert len(result.events) == 1, "one fixture, one card"


def test_a_third_row_that_is_itself_anchored_is_still_refused():
    """The boundary of the arm above: two anchored sides is nobody's licence."""
    same_minute_anchored = _Row(20, commence_time=TIP_OFF, espn_id="401001")
    same_minute_claim = _Row(21, commence_time=TIP_OFF)
    late_anchored = _Row(
        22, commence_time=TIP_OFF + timedelta(minutes=8), external_id="b"
    )

    result = fold_twin_events([same_minute_anchored, same_minute_claim, late_anchored])

    assert len(result.events) == 2


def test_a_page_with_nothing_to_merge_is_left_exactly_as_it_arrived():
    """The early return hands back the same groups object. A page of unrelated
    fixtures must come out unfolded, in arrival order."""
    rows = [
        _Row(20, home="Perth Wildcats", away="Adelaide 36ers"),
        _Row(21, home="Sydney Kings", away="Melbourne United", external_id="a"),
        _Row(22, home="Illawarra Hawks", away="Cairns Taipans"),
    ]

    result = fold_twin_events(rows)

    assert [e.id for e in result.events] == [20, 21, 22]
    assert result.dropped_ids == []
