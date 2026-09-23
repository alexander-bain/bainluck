"""Guard: one NPB game gets one card, not two — the NAME half of #8100.

THE PAGE THIS EXISTS FOR. `bainluck.com/sports/baseball_npb`, 390px,
2026-09-23 00:53Z. Two adjacent cards for one game, twice over, and each pair
carries a DIFFERENT answer:

    Today 11:00 PM    Hiroshima Toyo Carp 54%   / Yomiuri Giants 46%
    Today 11:00 PM    Hiroshima Carp      56%   / Yomiuri Giants 44%
    Tomorrow 2:00 AM  Yokohama BayStars   61%   / Chunichi Dragons 39%
    Tomorrow 2:00 AM  Yokohama DeNA BayStars 60%/ Chunichi Dragons 40%

`/api/leagues/baseball_npb` → `upcoming_games` carries all four rows; the frame
is `artifacts-lane1-606/BEFORE-npb-league-8100.png`. Each pair is one id-less
`polymarket_venue` row (`15313545`, `15313549` — no `espn_id`, no `external_id`)
beside one `odds_api` row (`15317392`, `15317394` — `external_id` set), minted
six days apart, which is ruling 048 / gotcha #32 working exactly as ruled: the
later claim could only CREATE.

WHY NO EXISTING PASS REACHED IT. The strict key holds the exact squashed names,
so `hiroshimacarp` and `hiroshimatoyocarp` are two groups; the soccer name pass
is soccer-gated; the season-variant pass needs a LEAGUE asymmetry; and #8100's
own first half, `_merge_anchored_claim_kickoffs`, widened the CLOCK and kept the
names exact — the opposite axis from the one these rows need.

WHAT EACH ARM HERE IS DEFENDING — the ways this pass can go wrong and reach a
reader, in both directions:

* it does not fire, and the league page still draws the game twice with two
  different percentages;
* it fires and the reader loses a venue's price, because the survivor is elected
  on provenance and the price may be on the other row (#7929 from the far side);
* it fires on the SYMMETRIC populations the licence exists to refuse — the
  `tennis_other` cluster measured at 3,111 pairs with 0 asymmetric, and the
  id-less `esports` bulk;
* 🔴 it fires on a pair where BOTH sides differ, which is where the one measured
  false fold in the whole population lives: `West Georgia v North Florida`
  beside `Georgia v Florida`, same league, same minute, asymmetric, and refused
  by NEITHER of this module's objective controls. That arm is the reason this
  pass requires one side to be squash-identical, and it is armed from a
  production specimen rather than invented;
* it fires on a reserve squad, a swapped orientation, a different opponent, a
  chain, or a pair at a different minute;
* it takes something off the clock half of #8100, or off #5918 / #2866.

THE CENSUS THE ARMS QUOTE — production, whole `events` table, all time,
2026-09-23 00:5x–01:2xZ, counted as adjacent pairs inside one `(sport_id,
minute)` bucket whose names are token-subset related:

    BOTH sides differ        3,810 pairs      135 asymmetric   1 false fold
      of which tennis_other  3,111 pairs        0 asymmetric
      of which esports           0 pairs        0 asymmetric
    ONE side IDENTICAL         251 pairs        22 asymmetric   0 false folds
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import (
    _merge_anchored_claim_name_variants,
    _name_tokens,
    _one_club_named_twice,
    fold_twin_events,
    twin_fold_key,
)

#: The measured first pitch of the production specimen.
FIRST_PITCH = datetime(2026, 9, 23, 6, 0, tzinfo=timezone.utc)

NPB = "baseball_npb"
NCAA = "baseball_ncaa"
EREDIVISIE = "soccer_netherlands_eredivisie"


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


class _Row:
    """The subset of `Event` the fold reads.

    Deliberately not a MagicMock, for the reason the #4100, #7915 and #8100
    clock suites give: an auto-attribute mock makes every `external_id` truthy
    and every `sport_id` unique, which would make this whole file pass without
    the pass existing — and `external_id` truthiness IS this licence's input.
    """

    def __init__(
        self,
        id,
        *,
        sport_key=NPB,
        sport_id=None,
        home="Hiroshima Carp",
        away="Yomiuri Giants",
        commence_time=FIRST_PITCH,
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


def _carp_pair(**overrides):
    """The two production rows for the Carp game, as measured 2026-09-23 00:5xZ.

    The id-less row is the Polymarket-born one and it carries the 55%; the
    anchored row is the Odds-API one and it carries the 46.2%. Two answers to
    one question, which is what the reader actually saw.
    """
    claim = _Row(
        15313545,
        home="Hiroshima Carp",
        sources={"polymarket": 0.55},
        **overrides,
    )
    anchored = _Row(
        15317392,
        home="Hiroshima Toyo Carp",
        external_id="3dee8218",
        sources={"betting": 0.462},
        **overrides,
    )
    return claim, anchored


def _baystars_pair(**overrides):
    """The second production pair, which differs on the AWAY side instead."""
    claim = _Row(
        15313549,
        away="Yokohama BayStars",
        home="Chunichi Dragons",
        commence_time=FIRST_PITCH + timedelta(hours=3),
        sources={"polymarket": 0.605},
        **overrides,
    )
    anchored = _Row(
        15317394,
        away="Yokohama DeNA BayStars",
        home="Chunichi Dragons",
        commence_time=FIRST_PITCH + timedelta(hours=3),
        external_id="8c076d06",
        sources={"betting": 0.5993},
        **overrides,
    )
    return claim, anchored


# ── the ship ──────────────────────────────────────────────────────────────────


def test_the_league_page_stops_drawing_the_carp_game_as_two_cards():
    """The ship, home side in dispute. Both rows in, one card out."""
    claim, anchored = _carp_pair()

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1, "one game must be one card"
    assert result.dropped_ids in ([15313545], [15317392])


def test_the_league_page_stops_drawing_the_baystars_game_as_two_cards():
    """The ship again with the dispute on the AWAY side.

    Both orientations are shipped because the pass reads elements 1 and 2 of the
    key separately and a rule that only handled one of them would close half the
    specimen — and the half it closed would depend on which way round the issue
    happened to write the fixture.
    """
    claim, anchored = _baystars_pair()

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1
    assert result.dropped_ids in ([15313549], [15317394])


def test_the_one_card_still_carries_both_venues():
    """🔴 THE FOLD ELECTS THE ANCHORED ROW, SO THE CLAIM'S PRICE MUST BE UNIONED.

    `twin_identity_rank` puts "carries a provider id" above "carries a venue's
    reading", so the survivor is the Odds-API row and Polymarket's 55% lives on
    the row that loses. Trading two cards for one card that has quietly dropped
    a venue is not the ship — "the blend is the product" — so this arm, not the
    card count above, is the acceptance test.
    """
    claim, anchored = _carp_pair()

    result = fold_twin_events([claim, anchored])

    survivor = result.events[0]
    assert survivor.id == 15317392, "the anchored row is the one that survives"
    assert result.merged_sources[survivor.id] == {
        "betting": 0.462,
        "polymarket": 0.55,
    }, "the one card must hold BOTH venues, which is what makes it the blend"


# ── the licence: the provenance asymmetry ─────────────────────────────────────


def test_two_id_less_rows_are_refused():
    """🔴 THE 3,111. This is why the licence is an asymmetry and not a name rule.

    `tennis_other` holds ~25 rows for one match at one instant — `Abe v Lu`
    beside `Hiromi Abe v Jia-Jing Lu` — which is 3,111 token-subset pairs, and
    #8100 named exactly that cluster as the reason not to build this pass. Not
    one of those 3,111 is asymmetric: every row in it is id-less. A symmetric
    pair is a question this module cannot answer, so it stays two cards.
    """
    claim, anchored = _carp_pair()
    anchored.external_id = None

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_two_anchored_rows_are_refused():
    """The same refusal from the other side. Two providers that each know the
    fixture BY id are two reports, and this module has never guessed between
    them."""
    claim, anchored = _carp_pair()
    claim.external_id = "3dee8218-other"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_an_espn_id_alone_makes_a_row_anchored():
    """The licence reads BOTH id columns, the way `_group_is_id_anchored` does.

    Without this arm the pass could be keyed on `external_id` only and every
    test above would still pass, because the specimen happens to be an Odds-API
    row. An ESPN-anchored claim is the same licence.
    """
    claim, anchored = _carp_pair()
    anchored.external_id = None
    anchored.espn_id = "401882866"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1


# ── the licence: one side must be EXACT ───────────────────────────────────────


def test_west_georgia_is_not_georgia():
    """🔴 THE ONE MEASURED FALSE FOLD IN THE WHOLE POPULATION, AND IT IS ARMED.

    Production rows `14706238` *Georgia v Florida* and `14707767* *West Georgia
    v North Florida*, `baseball_ncaa`, both at 2026-05-14 22:05Z, asymmetric
    provenance, no score on either row and no `espn_id` on either — so
    `_objectively_different_games` cannot refuse it and neither can the
    asymmetry. Two token-subset relations hold at once (`georgia` ⊆ `west
    georgia`, `florida` ⊆ `north florida`) and they are two real games.

    The ONLY thing that keeps them apart is this pass demanding that one side be
    squash-identical. If this arm goes red, somebody has allowed both sides to
    be adjudicated by the name rule and has put two college baseball games on
    one card.
    """
    georgia = _Row(
        14706238,
        sport_key=NCAA,
        away="Georgia",
        home="Florida",
        commence_time=datetime(2026, 5, 14, 22, 5, tzinfo=timezone.utc),
    )
    west_georgia = _Row(
        14707767,
        sport_key=NCAA,
        away="West Georgia",
        home="North Florida",
        commence_time=datetime(2026, 5, 14, 22, 5, tzinfo=timezone.utc),
        external_id="ncaa-west-georgia",
    )

    result = fold_twin_events([georgia, west_georgia])

    assert len(result.events) == 2, "two real games must stay two cards"


def test_a_different_opponent_never_folds():
    """The exact side is EQUALITY, not a second token rule: an unrelated club in
    the shared position is not the same fixture however alike the other names
    are."""
    claim, anchored = _carp_pair()
    anchored.away_team_name = "Hanshin Tigers"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_a_swapped_orientation_is_not_the_same_fixture():
    """Home and away are read in their own positions, so a mirrored row is a
    different key and is never folded — a doubleheader's second leg is exactly
    this shape."""
    claim, anchored = _carp_pair()
    anchored.away_team_name, anchored.home_team_name = (
        "Hiroshima Toyo Carp",
        "Yomiuri Giants",
    )

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


# ── the licence: the name rule itself ─────────────────────────────────────────


def test_the_longer_name_may_be_either_side_of_the_comparison():
    """🔴 MUTATION FOUND THIS GAP: one-directional containment SURVIVED.

    Both NPB specimens happen to sort the SHORT name first — `hiroshimacarp` <
    `hiroshimatoyocarp`, `yokohamabaystars` < `yokohamadenabaystars` — so every
    arm above asks `left ⊆ right` and a rule that dropped the other direction
    passed the whole file. Production has the opposite ordering: `Army Black
    Knights` squashes to `armyblackknights`, which sorts BEFORE `armyknights`,
    so the longer name is `left` and only `right ⊆ left` can see it.

    Rows `14635382` / `14635586`, `baseball_ncaa`, 2026-05-10 19:55Z — and the
    production drive folds exactly this pair.
    """
    long_first = _Row(
        14635382,
        sport_key=NCAA,
        away="Holy Cross Crusaders",
        home="Army Black Knights",
        home_score=6,
        away_score=2,
        status="closed",
    )
    short_second = _Row(
        14635586,
        sport_key=NCAA,
        away="Holy Cross Crusaders",
        home="Army Knights",
        home_score=6,
        away_score=2,
        status="closed",
        external_id="ncaa-army",
    )
    assert "armyblackknights" < "armyknights", "the longer name sorts first"

    result = fold_twin_events([long_first, short_second])

    assert len(result.events) == 1


def test_a_name_that_is_not_a_superset_is_refused():
    """`Hiroshima Carp` and `Hiroshima Dragons` share a city and nothing else.

    The rule is set CONTAINMENT, not a shared prefix and not a similarity
    score — the two names must be one club written short and long.
    """
    claim, anchored = _carp_pair()
    anchored.home_team_name = "Hiroshima Dragons"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_the_tokenizer_strips_diacritics_the_way_the_key_does():
    """🟡 MEASURED INERT OUTSIDE SOCCER, AND ASSERTED ON THE TOKENIZER ALONE.

    `_name_tokens` strips diacritics because `_squash` does, and a tokenizer
    that disagreed with the key about what a name is would let the exact-side
    clause and the subset clause read two different strings.

    It changes no outcome this pass can reach today. Of the six production pairs
    that diacritic folding adds to the 251, three are `Montréal Canadiens`
    spellings that `_squash` already collapses into ONE strict group, one is
    `Málaga` for the same reason, and the two that genuinely need it — the
    Madrid derby `15307707` / `15312071` and `CF Montréal` `14307152` /
    `14618969` — are both soccer and are both the soccer pass's. So this is
    pinned where it is true instead of through a fold that would be proving
    somebody else's pass.
    """
    assert _name_tokens("Atlético Madrid") == {"atletico", "madrid"}
    assert _one_club_named_twice("Atletico", "Atlético Madrid")
    assert _one_club_named_twice("Montreal Canadiens", "Montréal Canadiens")


def test_the_soccer_leagues_are_left_to_the_soccer_pass():
    """🔴 #6047's LA LIGA TRIPLE IS WHY, AND IT IS A THREE-CARD REGRESSION.

    `Athletic Bilbao v Alavés` (anchored), `Athletic Club v Alaves` and
    `Bilbao v Alaves` (both id-less), same minute. This pass's rule reaches
    `Athletic Bilbao` ⊇ `Bilbao` and would merge those two, after which the
    soccer pass reads the merged group by its lowest-id member — `Bilbao` — and
    `Bilbao` ≡ `Athletic Club` is the one pair its name rule cannot make, so the
    star rescue never fires and the reader is served two cards for one fixture
    instead of one.

    The suite that owns that page is `test_nonclique_star_fold_6047.py`; this arm
    pins the skip from THIS side, so the exclusion cannot be quietly dropped by
    somebody reading only this file.
    """
    rows = [
        _Row(
            15312047,
            sport_key="soccer_spain_la_liga",
            away="Athletic Bilbao",
            home="Alavés",
            espn_id="401882866",
        ),
        _Row(15307698, sport_key="soccer_spain_la_liga", away="Bilbao", home="Alaves"),
    ]
    groups = {}
    for row in rows:
        groups.setdefault(twin_fold_key(row), []).append(row)
    assert len(groups) == 2, "the strict key must hand this pass two groups"

    assert (
        _merge_anchored_claim_name_variants(groups) is groups
    ), "this pass must not act on a soccer bucket"


def test_a_reserve_squad_is_out_of_reach_rather_than_refused():
    """🟡 THE GUARD THIS PASS LOOKS LIKE IT NEEDS IS THE ONE IT CANNOT USE.

    `Ajax` ⊆ `Jong Ajax` is exactly the hazard a token-subset rule opens, and
    `_names_a_different_squad` (#2866 rung 3) is the module's existing answer to
    it — so the obvious move is to call it here. It would be dead code: `jong`
    and `amateurs` are Dutch football markers, every football key begins
    `soccer`, and this pass skips every soccer bucket before any name is read.

    This arm pins the REASON, not a refusal, so the next session does not add a
    guard back on the strength of the hazard being real. If a non-soccer league
    ever produces a squad marker, the census is owed again and this arm is where
    the argument was recorded.
    """
    assert EREDIVISIE.startswith("soccer"), "the marker's leagues are all soccer"
    # The name rule ALONE would fold it, which is why the skip is load-bearing.
    assert _one_club_named_twice("Ajax", "Jong Ajax")

    claim = _Row(90001, sport_key=EREDIVISIE, away="Ajax", home="Feyenoord")
    anchored = _Row(
        90002,
        sport_key=EREDIVISIE,
        away="Jong Ajax",
        home="Feyenoord",
        external_id="eredivisie-jong",
    )
    groups = {}
    for row in (claim, anchored):
        groups.setdefault(twin_fold_key(row), []).append(row)
    assert len(groups) == 2, "the strict key must hand this pass two groups"

    assert (
        _merge_anchored_claim_name_variants(groups) is groups
    ), "the soccer skip, not a squad refusal, is what keeps this pass out"


# ── the objective controls ────────────────────────────────────────────────────


def test_two_different_scorelines_refuse_even_an_asymmetric_pair():
    """A fold here would have to throw one scoreline away, and neither is ours
    to discard."""
    claim, anchored = _carp_pair()
    claim.status = "completed"
    anchored.status = "completed"
    claim.home_score, claim.away_score = 3, 1
    anchored.home_score, anchored.away_score = 7, 2

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_one_row_carrying_a_score_the_other_lacks_is_not_evidence():
    """Absence is not a conflict. Refusing on it would refuse the entire
    population this pass exists for — every NPB row here is scoreless."""
    claim, anchored = _carp_pair()
    claim.status = "completed"
    anchored.status = "completed"
    anchored.home_score, anchored.away_score = 7, 2

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1


def test_two_espn_ids_inside_the_anchored_group_refuse_the_claim():
    """One game, one authority id (#2693), so two of them is two games.

    🟡 THE ONLY SHAPE THIS ARM CAN TAKE, and it is stated rather than dressed up
    as a control that fires on the specimen. An id-less group has no `espn_id`
    BY CONSTRUCTION — that is the licence — so the `espn_id` half of
    `_objectively_different_games` can only ever see a conflict that the strict
    key already built inside the anchored group. Here the two anchored rows
    spell the club the same way, so they arrive as ONE group holding two
    authority ids, and the claim is refused from joining it.
    """
    claim, anchored = _carp_pair()
    anchored.espn_id = "401222222"
    anchored_twin = _Row(
        15317393,
        home="Hiroshima Toyo Carp",
        espn_id="401111111",
        external_id="3dee8218-twin",
    )

    result = fold_twin_events([claim, anchored, anchored_twin])

    survivors = {row.id for row in result.events}
    assert 15313545 in survivors, "the claim must not join a two-authority group"
    assert len(result.events) == 2, (
        "the two anchored rows share a strict key and fold to one card; the "
        "claim stays its own"
    )


def test_a_live_pair_is_left_as_two_cards():
    """While a game is live the asymmetry this can read is outranked by one it
    cannot — which row's score is current — and electing the stale copy shows a
    wrong score as the only score."""
    claim, anchored = _carp_pair()
    claim.status = "live"
    anchored.status = "live"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


def test_one_live_row_is_enough_to_refuse_the_pair():
    """The refusal is on the GROUP, not on the pair's agreement about status."""
    claim, anchored = _carp_pair()
    anchored.status = "live"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


# ── the clock is NOT this pass's axis ─────────────────────────────────────────


def test_a_name_variant_one_minute_off_is_not_reached():
    """🟡 DELIBERATE, AND PINNED SO WIDENING IT IS A DECISION.

    This pass keeps element 3 of the strict key exactly as it found it: the
    bucket is the minute. A pair that disagrees about BOTH the name and the
    clock is neither half of #8100 and is unmeasured, so it stays two cards.
    If this arm goes green somebody has composed the two licences and owes the
    census for the composition.
    """
    claim, anchored = _carp_pair()
    anchored.commence_time = FIRST_PITCH + timedelta(minutes=1)

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 2


# ── chains ────────────────────────────────────────────────────────────────────


def test_one_claim_between_two_anchored_spellings_is_discarded_whole():
    """🔴 THE CLIQUE REFUSAL, AND UNLIKE THE CLOCK HALF IT IS LOAD-BEARING HERE.

    `_anchored_claim_clusters` can argue a surviving cluster is always exactly
    two groups: anchored and id-less are the only two sides there are, so any
    third group sits on one of them and is refused. That argument survives here
    too for the ASYMMETRY — but this pass's name rule is not transitive, so a
    claim can name two different anchored spellings at once. `Carp` is a subset
    of both `Hiroshima Carp` and `Hiroshima Toyo Carp`; those two are anchored
    and therefore symmetric with each other; the clique fails and all three
    rows stand rather than the pass choosing which anchor the claim belongs to.

    This is the `Madrid` ⊆ `Real Madrid` / `Atlético Madrid` hazard
    `_merge_soccer_name_variants` records, reached by a different door.
    """
    claim = _Row(15313546, home="Carp")
    anchored_short = _Row(15313545, home="Hiroshima Carp", external_id="a")
    anchored_long = _Row(15317392, home="Hiroshima Toyo Carp", external_id="b")

    result = fold_twin_events([claim, anchored_short, anchored_long])

    assert len(result.events) == 3, "no fold may choose between two anchors"
    assert result.dropped_ids == []


def test_two_claims_on_one_anchor_are_discarded_whole():
    """The mirror of the arm above — two id-less spellings beside one anchored
    row. The two claims are symmetric with each other, so the clique fails and
    nothing folds rather than the pass picking a claim."""
    anchored = _Row(15317392, home="Hiroshima Toyo Carp", external_id="3dee8218")
    claim_a = _Row(15313545, home="Hiroshima Carp")
    claim_b = _Row(15313546, home="Carp")

    result = fold_twin_events([anchored, claim_a, claim_b])

    assert len(result.events) == 3


# ── the pass is inert where it should be ──────────────────────────────────────


def test_a_page_with_nothing_to_merge_is_handed_straight_back():
    """The early return is identity, not a copy: a caller with no such pair pays
    nothing and gets byte-identical behaviour to before #8100."""
    rows = [
        _Row(1, home="Hiroshima Carp", away="Yomiuri Giants"),
        _Row(2, home="Hanshin Tigers", away="Tokyo Yakult Swallows"),
    ]
    groups = {}
    for row in rows:
        groups.setdefault(twin_fold_key(row), []).append(row)

    assert _merge_anchored_claim_name_variants(groups) is groups


def test_the_exact_same_minute_identical_name_case_is_untouched():
    """#2866's population is the strict key's own and must not move: two rows
    that already share a key arrive as ONE group and this pass never sees a
    second one to merge it with."""
    claim, anchored = _carp_pair()
    anchored.home_team_name = "Hiroshima Carp"

    result = fold_twin_events([claim, anchored])

    assert len(result.events) == 1, "the strict key already folded this"
    assert result.dropped_ids == [15313545]
