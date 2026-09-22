"""A team match-play event stops being scored as a stroke-play tournament (#7985).

Seen on production `GET /api/golf`, 2026-09-22 ~10:0xZ, four days before the
Presidents Cup teed off at Medinah. The PGA Tour card read:

    Presidents Cup — Medinah Country Club (No. 3) — 6.1% Jackson Koivun, Leader
    Bridgeman 4.2% · Ghim 3.2% · James 3.0% · Conners 2.9%

The Presidents Cup is a **24-player team match-play event**. There is no cut to
miss, no individual champion, and Jackson Koivun is not in it. `_all_golfers` on
that card carried **132** entries.

The cause is upstream of the card. `tasks/datagolf.py` mints five markets for
whatever event the tour's schedule says is current, unconditionally:

    61720777  datagolf:pga:500:win        "Presidents Cup - Winner"
    61720778  datagolf:pga:500:top_5      "Presidents Cup - Top 5 Finish"
    61720779  datagolf:pga:500:top_10     "Presidents Cup - Top 10 Finish"
    61720780  datagolf:pga:500:top_20     "Presidents Cup - Top 20 Finish"
    61720781  datagolf:pga:500:make_cut   "Presidents Cup - Make the Cut"

These are not mispriced markets. They are markets for questions the event cannot
be asked, and the serve path cannot tell a phantom 6.1% from a real one, so it
ranked one to the top of the card.

The correct market was in the same payload the whole time — Kalshi's, and it is
the one the reader should have been led with:

    16757297  kalshi  KXPRESCUP-26  "Presidents Cup Winner"  Team USA 81.5% / Team World 14.5%

Every market row in this file is a verbatim replay of those seven production rows.

═══ THE CONTROL IS THE POINT OF THIS FILE: `is_tour_event` IS NOT THE PROPERTY ═══

#7985 was filed proposing `is_tour_event` as the discriminator, on this evidence:

    Presidents Cup             is_tour_event=False   <- the defect
    FedEx Open de France       is_tour_event=True
    NW Arkansas Championship   is_tour_event=True
    Compliance Solutions       is_tour_event=True

which is a true reading of one September week's payload and a false reading of
the flag. `routes/golf.py` computes it as *"this key is not in
`TOURNAMENT_ORDER`"*, and `TOURNAMENT_ORDER` is the hand-maintained list of named
events — **the four men's majors**, the women's majors, the Players, LIV, TGL and
the two cups. The route says so itself: *"Majors are NOT flagged `is_tour_event`
(they sit in TOURNAMENT_ORDER)"*.

So a guard keyed on that flag would withhold the Winner market from the Masters,
the PGA Championship, the U.S. Open and the Open Championship — and **no
measurement taken in September could have caught it**, because no major is in
season in September. That is strictly worse than the defect being fixed.

`TestTheGuardIsNotKeyedOnIsTourEvent` walks every non-team key in
`TOURNAMENT_ORDER` and asserts none of them is withheld. It exists to fail, loudly
and out of season, for anyone who reaches for the flag again.

═══ THE SECOND CONTROL: THE REAL WINNER MARKET IS NAMED "WINNER" TOO ═══

Kalshi's correct market is called **"Presidents Cup Winner"**, one hyphen away
from our phantom **"Presidents Cup - Winner"**. A withhold keyed on the market
NAME would therefore delete the real team market and keep nothing. The guard is
scoped to `source == "datagolf"` — it can only ever reach rows we minted
ourselves — and `TestItCannotReachAVenuesOwnMarket` is that safety property
asserted rather than assumed.

═══ THE THIRD CONTROL: DO NOT FIX THIS BY DELETING THE CARD ═══

`_build_tournament_entry` returns `None` for a tournament with no golfers, and
h2h matchups are routed and attached AFTER it returns. So withholding the
phantoms without touching that rule does not fix the card — it removes the
Presidents Cup from /golf during the Presidents Cup, which trades a truth defect
for a notice-27 marquee absence. `TestTheCardSurvivesOnItsTeamMarket` is the
reader-level assertion that both halves shipped together.
"""

import pytest

from app.routes import golf as golf_route
from app.routes.golf import (
    TOURNAMENT_ORDER,
    _build_tournament_entry,
    _drop_contentless_team_cards,
    _promote_team_matchup_to_card,
    get_golf,
)
from app.tasks.datagolf import MARKET_TYPES
from app.utils.golf_event_format import (
    INDIVIDUAL_STROKE_PLAY_MARKET_TYPES,
    TEAM_MATCH_PLAY_KEYS,
    TEAM_SIDE_NAMES,
    datagolf_market_type,
    is_team_match_play_key,
    is_team_match_play_name,
    is_team_side_name,
    select_team_side_matchup,
    withhold_individual_market,
)


# ──────────────────────────────────────────────────────────────────────────────
# Production replay fixtures
# ──────────────────────────────────────────────────────────────────────────────

class _Outcome:
    _next = iter(range(1, 10_000))

    def __init__(self, name, probability):
        self.id = next(_Outcome._next)
        self.name = name
        self.current_probability = probability
        # Every other column the route reads. Spelled out rather than left to a
        # `__getattr__` returning None: a fake that answers every attribute makes
        # a helper take its unknown-value branch, which reads exactly like a
        # principled refusal and would let these tests pass for the wrong reason.
        self.probability_change_24h = None
        self.opening_probability = probability
        self.current_american_odds = None
        self.is_winner = None


class _Market:
    def __init__(
        self, id, source, external_id, name,
        outcomes, mutually_exclusive=False,
        commence_time=None, resolution_date=None,
    ):
        self.id = id
        self.source = source
        self.external_id = external_id
        self.name = name
        self.status = "open"
        self.llm_sport_category = "golf"
        self.mutually_exclusive = mutually_exclusive
        self.commence_time = commence_time
        self.resolution_date = resolution_date
        self.market_metadata: dict = {}
        self.outcomes = outcomes


#: The four phantom placement/cut markets plus the phantom winner, verbatim.
def _presidents_cup_phantom_markets():
    field = [
        ("Jackson Koivun", 0.061),
        ("Jacob Bridgeman", 0.042),
        ("Doug Ghim", 0.032),
        ("Ben James", 0.030),
    ]
    return [
        _Market(
            61720777, "datagolf", "datagolf:pga:500:win",
            "Presidents Cup - Winner",
            [_Outcome(n, p) for n, p in field],
            mutually_exclusive=True,
        ),
        _Market(
            61720778, "datagolf", "datagolf:pga:500:top_5",
            "Presidents Cup - Top 5 Finish",
            [_Outcome(n, p * 3) for n, p in field],
        ),
        _Market(
            61720779, "datagolf", "datagolf:pga:500:top_10",
            "Presidents Cup - Top 10 Finish",
            [_Outcome(n, p * 4) for n, p in field],
        ),
        _Market(
            61720780, "datagolf", "datagolf:pga:500:top_20",
            "Presidents Cup - Top 20 Finish",
            [_Outcome(n, p * 5) for n, p in field],
        ),
        _Market(
            61720781, "datagolf", "datagolf:pga:500:make_cut",
            "Presidents Cup - Make the Cut",
            [_Outcome(n, 0.9) for n, _ in field],
        ),
    ]


def _presidents_cup_real_team_market():
    """Kalshi KXPRESCUP-26 — the market the card should lead with."""
    return _Market(
        16757297, "kalshi", "KXPRESCUP-26", "Presidents Cup Winner",
        [_Outcome("Team USA", 0.815), _Outcome("Team World", 0.145)],
        mutually_exclusive=True,
    )


def _stroke_play_control_markets():
    """A real stroke-play tournament in the same payload, untouched by the guard."""
    field = [
        ("Ludvig Aberg", 0.105),
        ("Tommy Fleetwood", 0.079),
        ("Matt Fitzpatrick", 0.078),
    ]
    return [
        _Market(
            61720786, "datagolf", "datagolf:euro:2026137:win",
            "FedEx Open de France - Winner",
            [_Outcome(n, p) for n, p in field],
            mutually_exclusive=True,
        ),
        _Market(
            61720787, "datagolf", "datagolf:euro:2026137:make_cut",
            "FedEx Open de France - Make the Cut",
            [_Outcome(n, 0.8) for n, _ in field],
        ),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# The decision
# ──────────────────────────────────────────────────────────────────────────────

class TestThePhantomMarketsAreWithheld:
    @pytest.mark.parametrize("market_type", sorted(INDIVIDUAL_STROKE_PLAY_MARKET_TYPES))
    def test_every_minted_stroke_play_type_is_withheld_from_the_presidents_cup(
        self, market_type,
    ):
        assert withhold_individual_market(
            "presidents_cup", "datagolf", f"datagolf:pga:500:{market_type}",
        ) is True

    def test_the_ryder_cup_is_the_same_format_and_the_same_answer(self):
        assert withhold_individual_market(
            "ryder_cup", "datagolf", "datagolf:pga:42:win",
        ) is True

    def test_the_mint_path_recognises_the_event_by_the_venues_own_name(self):
        """The mint has no tournament key — DataGolf's schedule has no format field."""
        assert is_team_match_play_name("Presidents Cup") is True
        assert is_team_match_play_name("Ryder Cup") is True
        assert is_team_match_play_name("FedEx Open de France") is False
        assert is_team_match_play_name("Masters Tournament") is False
        assert is_team_match_play_name(None) is False


class TestTheGuardIsNotKeyedOnIsTourEvent:
    """The out-of-season control. See this file's docstring.

    Every one of these keys is served `is_tour_event=False`, exactly like the
    Presidents Cup, because every one of them sits in `TOURNAMENT_ORDER`. Not one
    of them may lose its Winner market.
    """

    #: Spelled out, NOT derived as `TOURNAMENT_ORDER - TEAM_MATCH_PLAY_KEYS`.
    #
    #: Deriving it was the first way this was written, and mutation testing caught
    #: it: widening `TEAM_MATCH_PLAY_KEYS` to the whole of `TOURNAMENT_ORDER` — the
    #: exact wrong guard this class exists to convict — emptied the parametrize
    #: list, and the suite reported 5 SKIPPED instead of red. A control whose cases
    #: come from the constant under test cannot fail when that constant is wrong.
    _NON_TEAM_TOURNAMENT_ORDER_KEYS = [
        "masters", "pga_championship", "us_open", "the_open",
        "players",
        "masters_womens", "pga_championship_womens",
        "us_open_womens", "the_open_womens",
        "liv", "tgl", "other",
    ]

    @pytest.mark.parametrize("tourn_key", _NON_TEAM_TOURNAMENT_ORDER_KEYS)
    @pytest.mark.parametrize("market_type", sorted(INDIVIDUAL_STROKE_PLAY_MARKET_TYPES))
    def test_a_non_team_tournament_order_key_keeps_every_market(
        self, tourn_key, market_type,
    ):
        assert withhold_individual_market(
            tourn_key, "datagolf", f"datagolf:pga:14:{market_type}",
        ) is False

    def test_the_control_list_still_matches_the_routes_own_order(self):
        """Keeps the literal above honest as `TOURNAMENT_ORDER` changes.

        The list is hard-coded so the control cannot be emptied by the bug it
        hunts; this asserts the hard-coding has not gone stale, which is the only
        cost of not deriving it.
        """
        expected = [k for k in TOURNAMENT_ORDER if k not in TEAM_MATCH_PLAY_KEYS]

        assert sorted(self._NON_TEAM_TOURNAMENT_ORDER_KEYS) == sorted(expected)
        assert set(TEAM_MATCH_PLAY_KEYS) < set(TOURNAMENT_ORDER)

    def test_the_four_mens_majors_are_named_explicitly(self):
        """Named, not just parametrized, so the failure says which event broke."""
        for major in ("masters", "pga_championship", "us_open", "the_open"):
            assert is_team_match_play_key(major) is False
            assert withhold_individual_market(
                major, "datagolf", "datagolf:pga:14:win",
            ) is False

    def test_an_ordinary_tour_event_keeps_every_market(self):
        assert withhold_individual_market(
            "fedex_open_de_france", "datagolf", "datagolf:euro:2026137:win",
        ) is False


class TestItCannotReachAVenuesOwnMarket:
    """The safety property: the guard can only withhold rows we minted."""

    def test_the_real_kalshi_team_winner_market_is_kept(self):
        """One hyphen from the phantom's name, and it must survive."""
        assert withhold_individual_market(
            "presidents_cup", "kalshi", "KXPRESCUP-26",
        ) is False

    def test_the_kalshi_field_market_is_kept(self):
        assert withhold_individual_market(
            "presidents_cup", "kalshi", "KXPGACOMPETE-PRESCUP26SEP",
        ) is False

    def test_a_polymarket_row_on_the_same_card_is_kept(self):
        assert withhold_individual_market(
            "presidents_cup", "polymarket", "polymarket:0xabc",
        ) is False

    @pytest.mark.parametrize(
        "external_id",
        [None, "", "datagolf", "datagolf:pga", "datagolf:pga:500",
         "datagolf:pga:500:win:extra", "golf_presidents_cup"],
    )
    def test_an_id_that_is_not_the_mint_shape_reads_as_no_market_type(self, external_id):
        """A truncated or foreign id must never be read as a market type."""
        assert datagolf_market_type(external_id) is None
        assert withhold_individual_market(
            "presidents_cup", "datagolf", external_id,
        ) is False


class TestTheMintAndTheGuardCannotDrift:
    def test_every_minted_market_type_is_covered_by_the_guard(self):
        """A sixth stroke-play type added to the mint fails here until it is listed.

        `MARKET_TYPES` is what `tasks/datagolf.py` actually creates. If it grows a
        type this guard does not know, the Presidents Cup silently regains a
        phantom market and no other test in the repo would notice.
        """
        minted = {market_type for market_type, _category in MARKET_TYPES}

        assert minted == INDIVIDUAL_STROKE_PLAY_MARKET_TYPES


# ──────────────────────────────────────────────────────────────────────────────
# The card
# ──────────────────────────────────────────────────────────────────────────────

def _entry(tourn_key, golfer_data):
    return _build_tournament_entry(
        tourn_key, [], golfer_data, [], [1], ["datagolf"], None, None,
    )


class TestAnEmptyTeamCardIsKeptLongEnoughToBeJudged:
    def test_a_team_card_with_no_golfers_is_not_dropped_at_build_time(self):
        """Its real market is an h2h, and h2h matchups attach later."""
        assert _entry("presidents_cup", {}) is not None

    def test_a_stroke_play_card_with_no_golfers_is_still_dropped(self):
        """Unchanged behaviour for every other tournament."""
        assert _entry("fedex_open_de_france", {}) is None

    def test_a_team_card_that_gained_a_matchup_is_kept(self):
        cards = [{
            "key": "presidents_cup", "name": "Presidents Cup",
            "golfers": [], "prop_markets": [],
            "h2h_matchups": [{"golfer_a": {"name": "Team USA", "probability": 0.815}}],
        }]

        assert _drop_contentless_team_cards(cards) == cards

    def test_a_team_card_that_gained_nothing_is_dropped(self):
        """The licence above is paid back here: an empty card is worse than none."""
        cards = [{
            "key": "presidents_cup", "name": "Presidents Cup",
            "golfers": [], "prop_markets": [], "h2h_matchups": [],
        }]

        assert _drop_contentless_team_cards(cards) == []

    def test_a_contentless_stroke_play_card_is_left_alone(self):
        """This rule only ever removes a card its own licence created."""
        cards = [{
            "key": "fedex_open_de_france", "name": "FedEx Open de France",
            "golfers": [], "prop_markets": [], "h2h_matchups": [],
        }]

        assert _drop_contentless_team_cards(cards) == cards


# ──────────────────────────────────────────────────────────────────────────────
# The reader
# ──────────────────────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, markets):
        self._markets = markets

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._markets


class _DB:
    def __init__(self, markets):
        self._markets = markets

    async def execute(self, *_args, **_kwargs):
        return _Result(self._markets)


@pytest.fixture
def served(monkeypatch):
    """Drive the real `/api/golf` builder over the production specimen."""
    async def _no_schedule():
        return []

    async def _no_snapshots(_db, _ids, _now):
        return {}

    monkeypatch.setattr(golf_route, "_get_golf_schedule", _no_schedule)
    monkeypatch.setattr(golf_route, "_fetch_24h_snapshots", _no_snapshots)

    async def _run():
        markets = (
            _presidents_cup_phantom_markets()
            + [_presidents_cup_real_team_market()]
            + _stroke_play_control_markets()
        )
        return await get_golf(db=_DB(markets))

    return _run


def _card(body, name_fragment):
    for t in body["tournaments"]:
        if name_fragment.lower() in (t.get("name") or "").lower():
            return t
    return None


class TestTheCardSurvivesOnItsTeamMarket:
    async def test_the_presidents_cup_card_is_still_on_the_page(self, served):
        """Do not fix the phantom by deleting a marquee event (notice 27)."""
        body = await served()

        assert _card(body, "Presidents Cup") is not None

    async def test_no_individual_golfer_is_ranked_on_it(self, served):
        """The reader-visible assertion: "6.1% Jackson Koivun, Leader" is gone.

        Asserted as "the field is the two teams", NOT as "the field is empty".
        The empty form is what this test said when CERT-3289 blocked the first
        build: it passes for a card that leads with nothing, which is the defect
        `TestTheTeamPairReachesTheRenderedCard` below exists to prevent.
        """
        card = _card(await served(), "Presidents Cup")

        assert [g["name"] for g in card["golfers"]] == ["Team USA", "Team World"]
        assert [g["name"] for g in card["_all_golfers"]] == ["Team USA", "Team World"]

    async def test_jackson_koivun_is_named_so_the_test_fails_for_its_own_reason(
        self, served,
    ):
        """The vacuity guard: the string a reader actually saw, by name."""
        body = await served()
        names = [
            g["name"]
            for t in body["tournaments"]
            for g in t.get("_all_golfers", [])
        ]

        assert "Jackson Koivun" not in names

    async def test_it_leads_with_team_usa_against_team_world(self, served):
        """What the card is FOR. Kalshi's market, kept, correct, and present."""
        card = _card(await served(), "Presidents Cup")

        assert len(card["h2h_matchups"]) == 1
        matchup = card["h2h_matchups"][0]
        assert matchup["golfer_a"]["name"] == "Team USA"
        assert matchup["golfer_a"]["probability"] == pytest.approx(0.815)
        assert matchup["golfer_b"]["name"] == "Team World"
        assert matchup["golfer_b"]["probability"] == pytest.approx(0.145)

    async def test_the_stroke_play_tournament_beside_it_is_untouched(self, served):
        """Scope control: the guard did not empty the rest of the page."""
        card = _card(await served(), "FedEx Open de France")

        assert card is not None
        assert [g["name"] for g in card["golfers"]][:1] == ["Ludvig Aberg"]
        assert card["golfers"][0]["probability"] == pytest.approx(0.105, abs=0.002)


# ──────────────────────────────────────────────────────────────────────────────
# THE FOURTH CONTROL: WITHHOLDING IS ONLY HALF — THE PAIR MUST REACH THE CARD
#
# CERT-3289 blocked the first build of this fix. Everything above passed: the
# phantoms were withheld, the card survived, Kalshi's market was preserved in
# `h2h_matchups`. And the rendered card was a bare title, because
# `frontend/components/TournamentCard.tsx` enters its cup renderer on
#
#     _isCupEvent(tournament) && tournament.golfers.length === 2        (line 59)
#
# reads its hero from `const [teamA, teamB] = tournament.golfers`       (line 224)
#
# and never reads `h2h_matchups` at all. A truth defect had been traded for an
# empty card. `card["golfers"] == []` — what this file used to assert — is
# satisfied by exactly that emptiness, which is why the assertion below is
# phrased as what the reader SEES rather than as what is absent.
# ──────────────────────────────────────────────────────────────────────────────

def _singles_matchup(name_a, prob_a, name_b, prob_b, market_id=99001):
    """A player-v-player matchup of the kind a cup's own card carries."""
    return {
        "market_id": market_id,
        "source": "kalshi",
        "golfer_a": {"name": name_a, "probability": prob_a},
        "golfer_b": {"name": name_b, "probability": prob_b},
    }


def _team_matchup(name_a="Team USA", prob_a=0.815, name_b="Team World", prob_b=0.145):
    return {
        "market_id": 16757297,
        "source": "kalshi",
        "golfer_a": {"name": name_a, "probability": prob_a},
        "golfer_b": {"name": name_b, "probability": prob_b},
    }


def _cup_card(h2h_matchups, key="presidents_cup", golfers=None):
    return {
        "key": key, "name": "Presidents Cup",
        "golfers": list(golfers or []), "prop_markets": [],
        "h2h_matchups": list(h2h_matchups),
    }


class TestTheTeamPairReachesTheRenderedCard:
    """The repair CERT-3289 required, asserted on the served payload."""

    async def test_the_card_satisfies_the_cup_renderer_gate(self, served):
        """`_isCupEvent(t) && t.golfers.length === 2` — both halves, on the wire."""
        card = _card(await served(), "Presidents Cup")

        assert "presidents" in card["key"].lower()
        assert len(card["golfers"]) == 2

    async def test_the_reader_sees_team_usa_81_5_against_team_world_14_5(self, served):
        """The exact two numbers and two names `CupCard` prints, in its own order."""
        golfers = _card(await served(), "Presidents Cup")["golfers"]

        # `CupCard` renders `(teamA.probability * 100).toFixed(1)`.
        rendered = [(g["name"], round(g["probability"] * 100, 1)) for g in golfers]
        assert rendered == [("Team USA", 81.5), ("Team World", 14.5)]

    async def test_the_hero_is_a_team_and_not_a_person(self, served):
        """The defect, restated as the thing that must never come back."""
        hero = _card(await served(), "Presidents Cup")["golfers"][0]

        assert hero["name"] == "Team USA"
        assert "Koivun" not in hero["name"]

    @pytest.mark.parametrize("field", [
        "name", "probability", "rank", "movement_24h",
        "movement_is_dated", "sources", "opening_probability",
    ])
    async def test_a_promoted_team_carries_every_field_a_golfer_entry_carries(
        self, served, field,
    ):
        """`routes/feed.py` reads `g["rank"]` and `g["movement_24h"]` by SUBSCRIPT.

        A short entry would not render a wrong card, it would 500 the Discover
        feed. The shape is the contract, not just the two values.
        """
        golfers = _card(await served(), "Presidents Cup")["golfers"]

        # Not decoration: `for g in []` asserts nothing, so without this line the
        # whole class passes for a card that promoted NOBODY — measured, on the
        # mutant that removes the promotion call.
        assert len(golfers) == 2
        for golfer in golfers:
            assert field in golfer

    async def test_the_two_teams_are_attributed_to_kalshi(self, served):
        """The source mark (D91) has to name the venue the number came from."""
        golfers = _card(await served(), "Presidents Cup")["golfers"]

        assert len(golfers) == 2  # see the vacuity note above
        for golfer in golfers:
            assert list(golfer["sources"]) == ["kalshi"]

    async def test_neither_team_is_reported_as_a_biggest_mover(self, served):
        """A team promoted from an h2h has no 24h basis, so it has no move."""
        movers = [m["name"] for m in (await served())["biggest_movers"]]

        assert "Team USA" not in movers
        assert "Team World" not in movers

    async def test_the_real_matchup_is_still_carried_too(self, served):
        """Promotion COPIES onto the card; the detail page's list is untouched."""
        card = _card(await served(), "Presidents Cup")

        assert len(card["h2h_matchups"]) == 1
        assert card["h2h_matchups"][0]["golfer_a"]["name"] == "Team USA"


class TestThePromotionCannotPutAPersonOnTheCard:
    """The safety property, and the reason position is not the key.

    `routes/golf.py` sorts a card's h2h matchups by CLOSENESS, so during the cup
    itself every tight singles pairing sorts ahead of a lopsided 81.5/14.5 team
    market. `h2h_matchups[0]` would therefore put a golfer back at the top of the
    Presidents Cup card by a different road — the defect this issue is about,
    reintroduced by the fix for it.
    """

    def test_a_singles_matchup_sorted_first_is_not_promoted(self):
        """The convicting case: the team market is LAST and must still be found."""
        card = _cup_card([
            _singles_matchup("Scottie Scheffler", 0.52, "Sungjae Im", 0.48),
            _singles_matchup("Xander Schauffele", 0.55, "Hideki Matsuyama", 0.45),
            _team_matchup(),
        ])

        assert _promote_team_matchup_to_card([card]) == 1
        assert [g["name"] for g in card["golfers"]] == ["Team USA", "Team World"]

    def test_a_card_carrying_only_singles_promotes_nobody(self):
        """No team market means no hero — never a person standing in for one."""
        card = _cup_card([
            _singles_matchup("Scottie Scheffler", 0.52, "Sungjae Im", 0.48),
        ])

        assert _promote_team_matchup_to_card([card]) == 0
        assert card["golfers"] == []

    def test_a_card_carrying_only_singles_is_then_dropped_not_served_empty(self):
        """And the two halves compose: an unled cup card does not reach the page.

        Asserted through both functions in their served order, because "promotion
        declined" and "the reader saw a bare title" are only the same statement if
        the drop actually sees the declined card.
        """
        card = _cup_card([
            _singles_matchup("Scottie Scheffler", 0.52, "Sungjae Im", 0.48),
        ])
        card["h2h_matchups"] = []  # the singles did not route to this card either

        _promote_team_matchup_to_card([card])

        assert _drop_contentless_team_cards([card]) == []

    def test_a_real_field_is_never_displaced(self):
        """Promotion only ever FILLS an empty card."""
        card = _cup_card(
            [_team_matchup()],
            golfers=[{"name": "Ludvig Aberg", "probability": 0.105}],
        )

        assert _promote_team_matchup_to_card([card]) == 0
        assert [g["name"] for g in card["golfers"]] == ["Ludvig Aberg"]

    def test_a_stroke_play_card_is_never_promoted(self):
        """Scope control: this rule exists for two tournaments in the world."""
        card = _cup_card([_team_matchup()], key="fedex_open_de_france")

        assert _promote_team_matchup_to_card([card]) == 0
        assert card["golfers"] == []


class TestTheTeamSideNamesAreAClosedSet:
    """`select_team_side_matchup`'s allowlist, asserted rather than assumed."""

    @pytest.mark.parametrize("name", [
        "Team USA", "USA", "U.S.A.", "United States",
        "Team World", "World", "International", "Team International",
        "Europe", "Team Europe",
        "Great Britain & Ireland",
    ])
    def test_a_team_side_is_recognised_however_the_venue_spells_it(self, name):
        assert is_team_side_name(name) is True

    @pytest.mark.parametrize("name", [
        "Jackson Koivun", "Scottie Scheffler", "Sungjae Im", "Ludvig Aberg",
        "Tommy Fleetwood", "Hideki Matsuyama", "Xander Schauffele",
        # Near misses that must not open the gate.
        "", "   ", "Team", "The Field", "Field", "Tie", "Yes", "No",
    ])
    def test_a_person_or_a_placeholder_is_never_a_team_side(self, name):
        assert is_team_side_name(name) is False

    def test_the_golfer_who_led_the_card_is_named_by_hand(self):
        """The vacuity guard: the exact string the reader saw, spelled out."""
        assert is_team_side_name("Jackson Koivun") is False

    def test_both_sides_must_be_teams(self):
        """A team against a person is a data defect, not a card hero."""
        assert select_team_side_matchup([
            _singles_matchup("Team USA", 0.8, "Scottie Scheffler", 0.2),
        ]) is None

    def test_a_side_against_itself_is_refused(self):
        """"USA" v "Team USA" folds to one team; 50/50 of a team against itself
        would read worse than the phantom it replaced."""
        assert select_team_side_matchup([
            _singles_matchup("USA", 0.5, "Team USA", 0.5),
        ]) is None

    def test_an_empty_or_absent_list_is_not_an_error(self):
        assert select_team_side_matchup([]) is None
        assert select_team_side_matchup(None) is None

    def test_every_listed_side_is_stored_in_its_folded_form(self):
        """A name added with a "Team " prefix or a period could never match."""
        for side in TEAM_SIDE_NAMES:
            assert side == side.strip().lower()
            assert not side.startswith("team ")
            assert "." not in side
            assert "&" not in side


class TestTheCardContractMatchesTheFrontend:
    """The gate this fix depends on lives in a file this lane does not own.

    `frontend/components/TournamentCard.tsx` decides whether a promoted pair is
    rendered as a cup or ignored. If that decision moves, the Presidents Cup card
    silently goes back to being a bare title and no backend test would notice —
    so the two conditions it turns on are asserted here, by their source text.
    Read-only: a red test here is a message, not an edit.
    """

    # Hard-coded, not parsed out of the file. The `is_tour_event` control in this
    # same file is red today because a DERIVED list let a mutant empty it and
    # report SKIPPED; the lesson travelled.
    _CUP_TOKENS = ("ryder", "presidents", "walker", "solheim")

    @staticmethod
    def _tsx():
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[2]
            / "frontend" / "components" / "TournamentCard.tsx"
        )
        assert path.exists(), f"the card component moved: {path}"
        return path.read_text(encoding="utf-8")

    def test_the_cup_renderer_still_gates_on_exactly_two_golfers(self):
        """If this count changes, the backend must promote that many sides."""
        assert "tournament.golfers.length === 2" in self._tsx()

    def test_the_cup_renderer_still_reads_its_teams_out_of_golfers(self):
        """If it learns to read `h2h_matchups`, the promotion becomes redundant."""
        assert "const [teamA, teamB] = tournament.golfers;" in self._tsx()

    @pytest.mark.parametrize("token", _CUP_TOKENS)
    def test_the_cup_predicate_still_names_each_token(self, token):
        assert f'key.includes("{token}")' in self._tsx()

    @pytest.mark.parametrize("key", sorted(TEAM_MATCH_PLAY_KEYS))
    def test_every_team_match_play_key_is_rendered_as_a_cup(self, key):
        """A key we promote onto but the card does not recognise is a bare title.

        This is the join between the two halves: the backend decides WHICH
        tournaments get a team pair, the frontend decides which get the renderer
        that can draw one, and nothing else checks that the two agree.
        """
        assert any(token in key for token in self._CUP_TOKENS), (
            f"{key!r} is promoted to a two-team card by "
            f"`_promote_team_matchup_to_card`, but `_isCupEvent` in "
            f"TournamentCard.tsx matches none of {self._CUP_TOKENS} — the card "
            f"would render a title with two unread golfers under it. Add the "
            f"token there (ux owns that file) before adding the key here."
        )
