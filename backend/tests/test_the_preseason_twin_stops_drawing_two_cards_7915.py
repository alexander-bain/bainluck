"""Guard: a preseason game gets one card, not two (#7915).

THE PAGE THIS EXISTS FOR. `/sport/hockey/nhl/team/calgary-flames`, phone width,
2026-09-21 18:26 PDT. RECENT RESULTS carried two adjacent cards:

    vs Seattle Kraken   Sep 20   we had them at 50%   L 2-4
    vs Seattle Kraken   Sep 20                        L 2-4

One game, two cards, above a header reading 0-0-0. The rows are `15312340`
(`icehockey_nhl`, espn_id 401879309, kick-off 00:00:00Z) and `15316214`
(`icehockey_nhl_preseason`, no espn_id, kick-off 00:08:24Z).

WHY NEITHER EXISTING PASS REACHED IT, which is the whole point of the new one:

* the strict key has been league-aware since #2866, so the two sport keys are
  one league — but element 3 is the MINUTE, and these two providers are eight
  minutes apart, so the key makes two groups;
* the soccer name pass is the only thing that widens the clock, and it is
  soccer-gated on purpose (its subset rule cannot tell `Miami` from `Miami (OH)`).

WHAT EACH ARM HERE IS ACTUALLY DEFENDING. Not "a function returns a list" — the
ways this pass can go wrong and reach Alex, in both directions:

* it does not fire, and the Flames page still draws the game twice;
* it fires on a LIVE pair and elects the stale copy, so the reader is shown a
  wrong score as the only score (MEASURED: the one pair of 13 whose two rows
  disagreed about the score was live);
* it fires on two rows that are genuinely two games (a chain, a swapped
  orientation, a different opponent, a second fixture past the bound);
* it fires on the SYMMETRIC pair this module deliberately refuses to guess
  between (two rows sharing one sport key);
* it quietly widens the soccer populations #5918 and #5905 own;
* it breaks the same-minute case #2866 already closed.
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import (
    SEASON_VARIANT_KICKOFF_DRIFT,
    SOCCER_KICKOFF_DRIFT,
    fold_twin_events,
)
from app.utils.sport_keys import is_season_variant

# The measured kick-off of the production specimen, to the second.
PUCK_DROP = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)

NHL = "icehockey_nhl"
NHL_PRE = "icehockey_nhl_preseason"


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


class _Row:
    """The subset of `Event` the fold reads.

    Deliberately not a MagicMock, for the reason the #4100 suite gives: an
    auto-attribute mock makes every `espn_id` truthy and every `sport_id`
    unique, which would make this whole file pass without the pass existing.
    `sport` is a real object here because :func:`loaded_sport_key` is what the
    new pass reads, and a row without it must fall through untouched — which is
    its own arm below.
    """

    def __init__(
        self,
        id,
        *,
        sport_key=NHL,
        sport_id=None,
        home="Calgary Flames",
        away="Seattle Kraken",
        commence_time=PUCK_DROP,
        home_score=2,
        away_score=4,
        espn_id=None,
        external_id=None,
        sources=None,
        status="completed",
        load_sport=True,
        opening_home=None,
        opening_away=None,
    ):
        self.id = id
        # One sport row per key, the way production stores it.
        self.sport_id = sport_id if sport_id is not None else abs(hash(sport_key)) % 10**6
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
        # The PRE-MATCH line, which lives in these columns and has never been in
        # the JSONB bag above (`merge_opening_line`'s docstring carries the
        # measurement that established the difference). Present on the fixture
        # because on THIS population it is the number the reader keeps or loses:
        # see `test_the_surviving_card_keeps_the_only_pre_match_line_there_is`.
        self.opening_home_probability = opening_home
        self.opening_away_probability = opening_away


def _flames_pair(**overrides):
    """The two production rows, as measured 2026-09-21 23:5xZ."""
    parent = _Row(
        15312340,
        sport_key=NHL,
        commence_time=PUCK_DROP,
        espn_id="401879309",
        sources={"espn": 0.55, "stat_model": 0.52},
        **overrides,
    )
    variant = _Row(
        15316214,
        sport_key=NHL_PRE,
        commence_time=PUCK_DROP + timedelta(minutes=8, seconds=24),
        sources={"betting": 0.61},
        **overrides,
    )
    return parent, variant


def test_the_flames_page_stops_drawing_one_game_as_two_cards():
    """The ship. Both rows in, one card out."""
    parent, variant = _flames_pair()

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 1, "one game must be one card"
    assert result.dropped_ids in ([15312340], [15316214])


def test_the_surviving_card_keeps_both_rows_venues():
    """A fold that loses a venue is a filter wearing a fold's name.

    The parent row carries ESPN's reading and the variant row carries the
    betting price — on this population they are never on the same row — so the
    survivor must report all three or the card is one venue's opinion.
    """
    parent, variant = _flames_pair()

    result = fold_twin_events([parent, variant])

    survivor = result.events[0]
    merged = result.merged_sources[survivor.id]
    assert set(merged) == {"espn", "stat_model", "betting"}


def test_the_surviving_card_keeps_the_only_pre_match_line_there_is():
    """🔴 THE FOLD ELECTS THE UNPRICED ROW ON THIS POPULATION, EVERY TIME.

    The venue union above cannot reach this and the difference is the ship: the
    card's "we had them at 56%" is served from the `Event.opening_*` COLUMNS by
    `teams.py::_format_event_brief`, which has never read the JSONB bag. So the
    number survives only because :func:`_carry_opening_line` runs.

    WHY THIS ARM IS NOT A DUPLICATE OF THE SOCCER SUITE THAT ALREADY COVERS THAT
    FUNCTION. #5853 wrote it for a population where which row held the line was
    incidental. Here it is SYSTEMATIC and it points the wrong way: measured on
    production 2026-09-21, the parent carries `espn_id` in 13 of 13 pairs and the
    variant in 0 of 13, so `twin_identity_rank` elects the parent at rung 2 —
    while the pre-match line is on the VARIANT. Measured on the specimen itself
    at 2026-09-22 02:36Z, `/api/teams/calgary-flames` served
    `15316214  pregame_win_probability 0.557` beside `15312340  null`.

    So on every pair this pass folds, the elected survivor is the row with no
    line, and without the carry the reader trades two cards for one card with no
    percentage on it — a worse page than the bug. That is the regression #5918
    was filed to refuse, and this pass is a new way to arrive at it.
    """
    parent = _Row(
        15312340,
        sport_key=NHL,
        commence_time=PUCK_DROP,
        espn_id="401879309",
        sources={"espn": 0.55, "stat_model": 0.52},
    )
    variant = _Row(
        15316214,
        sport_key=NHL_PRE,
        commence_time=PUCK_DROP + timedelta(minutes=8, seconds=24),
        sources={"betting": 0.61},
        # The production reading, and its two-way complement.
        opening_home=0.557,
        opening_away=0.443,
    )

    result = fold_twin_events([parent, variant])

    survivor = result.events[0]
    # The direction is asserted, not assumed: if the election ever flips to the
    # priced row this arm must FAIL rather than quietly pass for a new reason.
    assert survivor.id == 15312340, "the espn-anchored parent is the survivor"
    assert result.dropped_ids == [15316214]

    assert survivor.opening_home_probability == 0.557, (
        "the survivor must carry the absorbed row's pre-match line, or the "
        "Flames card prints one game once with no percentage on it"
    )
    assert survivor.opening_away_probability == 0.443, "a pair travels as a pair"
    assert result.merged_opening[15312340] == (0.557, 0.443)


def test_a_pre_match_line_the_survivor_already_has_is_never_overwritten():
    """Gap-fill, not a blend: the carry may only supply, never replace.

    `merge_opening_line`'s first clause, asserted on this population because
    this pass is a new caller of it. A parent that DOES hold its own line keeps
    it — otherwise the fold would state one provider's opening under another's,
    and the two are medians taken at different moments over different
    sportsbooks (#1841), so they need not even sum to 1.
    """
    parent = _Row(
        15312340,
        sport_key=NHL,
        commence_time=PUCK_DROP,
        espn_id="401879309",
        opening_home=0.610,
        opening_away=0.390,
    )
    variant = _Row(
        15316214,
        sport_key=NHL_PRE,
        commence_time=PUCK_DROP + timedelta(minutes=8, seconds=24),
        opening_home=0.557,
        opening_away=0.443,
    )

    result = fold_twin_events([parent, variant])

    survivor = result.events[0]
    assert survivor.id == 15312340
    assert survivor.opening_home_probability == 0.610, "its own line stands"
    assert survivor.opening_away_probability == 0.390
    assert 15312340 not in result.merged_opening, "nothing was supplied"


def test_a_live_pair_is_left_as_two_cards():
    """MEASURED, not cautious. Of 13 production pairs on 2026-09-21, six were
    live and the ONLY pair whose rows disagreed about the score was one of them.
    While the game is live we cannot read which copy is current, so folding
    risks showing a stale score as the only score."""
    parent, variant = _flames_pair()
    parent.status = "live"
    variant.status = "live"

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2, "a live twin stays double — see #2693"


def test_one_live_row_is_enough_to_refuse_the_pair():
    """The production pair `15316894`/`15312791` was live on one side and
    completed on the other in the same read. The refusal is per GROUP, so the
    disagreement does not need to be mutual to be dangerous."""
    parent, variant = _flames_pair()
    parent.status = "completed"
    variant.status = "live"

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_a_scheduled_preseason_pair_folds_too():
    """The bug is not only about Finals: the same two providers file the same
    fixture ahead of time, and a reader looking at UPCOMING GAMES must not see
    it twice either. `scheduled` is in the collapsible set for that reason."""
    parent, variant = _flames_pair()
    parent.status = "scheduled"
    variant.status = "scheduled"
    parent.home_score = parent.away_score = None
    variant.home_score = variant.away_score = None

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 1


def test_two_rows_sharing_a_sport_key_are_still_refused():
    """The SYMMETRIC case, which this module has always refused and still does.

    Two `icehockey_nhl` rows eight minutes apart offer no asymmetry to read: no
    dominance test can pick a survivor and none should try. If this ever folds,
    the new pass has stopped being about season variants.
    """
    parent, variant = _flames_pair()
    variant.sport = _Sport(parent.sport_id, NHL)
    variant.sport_id = parent.sport_id

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_two_variant_rows_are_refused_in_the_same_way():
    """The other half of the asymmetry. Two `_preseason` rows are symmetric."""
    parent, variant = _flames_pair()
    parent.sport = _Sport(variant.sport_id, NHL_PRE)
    parent.sport_id = variant.sport_id

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_a_pair_past_the_bound_stays_two_cards():
    """The bound is what separates a twin from a second fixture. Sixteen minutes
    is outside it, and outside means two cards — not a closer look."""
    parent, variant = _flames_pair()
    variant.commence_time = PUCK_DROP + timedelta(minutes=16)

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_the_bound_sits_in_the_empty_band_it_was_measured_into():
    """Pins the SIZING, so widening it later is a decision and not a drift.

    Below: the measured disagreement on this population maxed at 9.45 minutes.
    Above: the 30-minute re-mint class that #5918 excluded on purpose and the
    three-hour Kalshi rows #5905 corrects. A value that leaves either band is a
    different ship and should have to say so here first.
    """
    assert SEASON_VARIANT_KICKOFF_DRIFT > timedelta(minutes=9, seconds=45)
    assert SEASON_VARIANT_KICKOFF_DRIFT < timedelta(minutes=30)
    # And it is genuinely wider than the soccer bound, which is the reason this
    # pass exists rather than a relaxation of that one.
    assert SEASON_VARIANT_KICKOFF_DRIFT > SOCCER_KICKOFF_DRIFT


def test_a_swapped_orientation_is_not_the_same_fixture():
    """Home and away are not interchangeable: the same two clubs meet twice in a
    preseason week and the second meeting is at the other rink."""
    parent, variant = _flames_pair()
    variant.home_team_name, variant.away_team_name = (
        parent.away_team_name,
        parent.home_team_name,
    )

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_a_different_opponent_in_the_same_bucket_never_folds():
    """The bucket is a day of one league; it is a candidate finder, not a
    licence. Two different games eight minutes apart must survive it."""
    parent, variant = _flames_pair()
    variant.away_team_name = "Vancouver Canucks"

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_a_chain_of_three_is_discarded_whole():
    """The clique refusal, and it is load-bearing: the drift bound is NOT
    transitive. Rows at 0, 12 and 24 minutes are pairwise-linked end to end but
    the outer two are 24 minutes apart, so this must collapse to nothing rather
    than pick which link to break."""
    a = _Row(1, sport_key=NHL, commence_time=PUCK_DROP, espn_id="x")
    b = _Row(2, sport_key=NHL_PRE, commence_time=PUCK_DROP + timedelta(minutes=12))
    c = _Row(3, sport_key=NHL, commence_time=PUCK_DROP + timedelta(minutes=24))

    result = fold_twin_events([a, b, c])

    assert len(result.events) == 3, "a chain is not a fixture"


def test_the_same_minute_case_2866_closed_still_folds():
    """#2866's 47 NFL preseason pairs share a MINUTE, so the strict key folds
    them and this pass never sees them. If this arm goes red, the new pass has
    taken something off the old one."""
    parent = _Row(
        10,
        sport_key="americanfootball_nfl",
        home="Denver Broncos",
        away="Minnesota Vikings",
        commence_time=PUCK_DROP,
        espn_id="401xxxx",
    )
    variant = _Row(
        11,
        sport_key="americanfootball_nfl_preseason",
        home="Denver Broncos",
        away="Minnesota Vikings",
        commence_time=PUCK_DROP,
    )

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 1


def test_a_caller_that_did_not_load_the_sport_is_untouched():
    """Gotcha #42 as a property: with no sport key in memory the pass has no
    licence, and the rail it cannot improve it must not damage."""
    parent, variant = _flames_pair()
    parent.sport = None
    variant.sport = None

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2, "no key, no licence — leave the rows alone"


def test_a_half_loaded_pair_never_even_becomes_a_candidate():
    """Pins the BUCKET, which is what actually refuses this — stated precisely
    because a mutant proved the obvious explanation wrong.

    The tempting reading is that `_group_has_season_variant` returns `None` and
    the pass declines. It does, but that is not what keeps these two apart:
    a row whose `Event.sport` is not in memory is absent from the identity map,
    so element 0 of its key is the raw `sport_id` rather than the league string,
    and the two rows are never in the same bucket to be compared. Reading the
    missing key as the PARENT instead leaves this arm green, which is how the
    distinction was found. It is asserted here so a future change to the
    bucketing cannot quietly make the `None` load-bearing without a red test.
    """
    parent, variant = _flames_pair()
    parent.sport = None

    result = fold_twin_events([parent, variant])

    assert len(result.events) == 2


def test_a_group_that_already_holds_both_sides_is_left_alone():
    """Three rows for one fixture: the same-minute pair #2866 folds, plus a
    third on the variant key eight minutes later.

    The already-mixed group has no side of the asymmetry to take, so this pass
    skips it and the third row stays a second card. That is conservative rather
    than obviously right — no production fixture has this shape today — and it
    is pinned so that folding it later is a measured decision, not a drift.
    """
    same_minute_parent = _Row(20, sport_key=NHL, commence_time=PUCK_DROP, espn_id="a")
    same_minute_variant = _Row(21, sport_key=NHL_PRE, commence_time=PUCK_DROP)
    late_variant = _Row(
        22, sport_key=NHL_PRE, commence_time=PUCK_DROP + timedelta(minutes=8)
    )

    result = fold_twin_events(
        [same_minute_parent, same_minute_variant, late_variant]
    )

    assert len(result.events) == 2, "#2866 folds the pair; the third row stays"


def test_a_surviving_cluster_is_never_wider_than_the_bound():
    """Pins the reasoning that let the clock be expressed once.

    Four alternating rows spanning 36 minutes are pairwise-linked end to end.
    Every cluster of three or more holds two rows on the same side of the
    asymmetry, so the clique test must discard all of them — which is what makes
    a second clock check inside the predicate dead code rather than a backstop.
    If this ever goes red, put the bound back into `same_fixture`.
    """
    rows = [
        _Row(1, sport_key=NHL, commence_time=PUCK_DROP, espn_id="a"),
        _Row(2, sport_key=NHL_PRE, commence_time=PUCK_DROP + timedelta(minutes=12)),
        _Row(3, sport_key=NHL, commence_time=PUCK_DROP + timedelta(minutes=24), espn_id="c"),
        _Row(4, sport_key=NHL_PRE, commence_time=PUCK_DROP + timedelta(minutes=36)),
    ]

    result = fold_twin_events(rows)

    assert len(result.events) == 4, "no cluster may span more than the bound"


def test_no_soccer_key_can_reach_this_pass():
    """Pins the BLAST-RADIUS claim the docstring makes, rather than asserting it
    in prose. The new pass is gated on a season-variant key; if a soccer league
    ever grows one, the populations #5918 and #5905 own become reachable and
    this must be re-measured before that happens."""
    from app.utils.sport_keys import SPORT_LEAGUE_MAP

    soccer_keys = [k for k in SPORT_LEAGUE_MAP if str(k).startswith("soccer")]
    assert soccer_keys, "fixture is vacuous if the map holds no soccer keys"
    assert not [k for k in soccer_keys if is_season_variant(k)]
