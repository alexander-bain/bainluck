"""#5576 — a Polymarket fixture is placed in its real league, not the catch-all.

THE READER'S COMPLAINT. On 2026-09-15, `/search?q=Yakult Swallows` served an
`Other Baseball (5)` chip holding five Yakult fixtures beside an `NPB (20)` chip
holding the rest of the same club's season — one team, two competition labels,
on one page. The five are Polymarket-born rows sitting on `baseball_other`.

THE MECHANISM. `auto_create_sport_key_from_category` can only ever return
`<prefix>_other`, because the league map it consults is keyed on a Kalshi TICKER
and a Polymarket market has none. So the league is never asked about, only
defaulted.

WHAT THIS DOES NOT DO, stated here because the acceptance for #5576 turns on it:
it does not collapse the twin standing next to the specimen. A market-born claim
is unanchored, ruling 048 makes the structured matcher unreachable for it, and
`find_or_create_event` creates whatever the sport key says. Placing the row puts
the card under the right competition; merging the pair is #1946 / #2693.

EVERY FIXTURE BELOW IS A PRODUCTION ROW, read by db-query on 2026-09-15 over
`_other` events in `NOW() - 2 days … NOW() + 10 days`. The controls are the point:
of 42 `baseball_other` rows, 19 are NPB and placeable, and the CPBL and Mexican
League rows beside them resolve to nothing and must stay exactly where they are.
"""
import pytest

from app.tasks.prediction_market_matching import (
    _sport_key_is_odds_api_covered,
    placeable_league_for_matchup,
)


class _TeamRow:
    """One `teams`-joined-`sports` row: (name, alternate_names, league)."""

    def __init__(self, name, alternates, league):
        self._values = (name, alternates, league)

    def __iter__(self):
        return iter(self._values)


class _AliasRow:
    """One `team_identity_mapping`-joined-`teams`-joined-`sports` row:
    (source_name, league). The mapping's own `sport_key` is not returned —
    the query requires it to EQUAL the club's league, so a row that reaches
    Python has already agreed with itself."""

    def __init__(self, source_name, league):
        self._values = (source_name, league)

    def __iter__(self):
        return iter(self._values)


class _FakeSession:
    """Serves the club arm first and the alias arm second, in call order.

    Neither arm is filtered by the fake, though the real queries bound both to
    the family in SQL. That is deliberate: it means these tests grade the
    PYTHON refusals — family, ambiguity, covered, `_other` — rather than
    re-testing SQLAlchemy's `startswith`. Every cross-family row below would be
    invisible in production and is present here to be refused.
    """

    def __init__(self, team_rows, alias_rows):
        self._arms = [team_rows, alias_rows]
        self.calls = 0
        self.statements = []

    async def execute(self, statement):
        arm = self._arms[min(self.calls, len(self._arms) - 1)]
        self.calls += 1
        self.statements.append(statement)
        return list(arm)


# `teams` as production serves it (12 NPB clubs, the MLB clubs that collide with
# them by nickname, and the `_other` clubs that let the catch-all resolve to
# itself). NPB carries no alternates, which is why the alias arm matters.
TEAM_ROWS = [
    _TeamRow("Tokyo Yakult Swallows", None, "baseball_npb"),
    _TeamRow("Hiroshima Toyo Carp", None, "baseball_npb"),
    _TeamRow("Hanshin Tigers", None, "baseball_npb"),
    _TeamRow("Yomiuri Giants", None, "baseball_npb"),
    _TeamRow("Chunichi Dragons", None, "baseball_npb"),
    _TeamRow("Yokohama BayStars", None, "baseball_npb"),
    _TeamRow("Chiba Lotte Marines", None, "baseball_npb"),
    _TeamRow("Saitama Seibu Lions", None, "baseball_npb"),
    _TeamRow("Tohoku Rakuten Golden Eagles", None, "baseball_npb"),
    _TeamRow("Fukuoka SoftBank Hawks", None, "baseball_npb"),
    _TeamRow("Orix Buffaloes", None, "baseball_npb"),
    _TeamRow("Hokkaido Nippon-Ham Fighters", None, "baseball_npb"),
    # The nickname traps, all real: a substring test reads "Hanshin Tigers" as
    # Detroit and "Yomiuri Giants" as San Francisco.
    _TeamRow("Detroit Tigers", ["Tigers", "Detroit"], "baseball_mlb"),
    _TeamRow("San Francisco Giants", ["Giants"], "baseball_mlb"),
    _TeamRow("Milwaukee Brewers", ["Brewers"], "baseball_mlb"),
    _TeamRow("Pittsburgh Pirates", ["Pirates"], "baseball_mlb"),
    _TeamRow("Milwaukee Brewers", ["Brewers"], "baseball_mlb_preseason"),
    _TeamRow("Pittsburgh Pirates", ["Pirates"], "baseball_mlb_preseason"),
    # `basketball_other` is a REAL row in `sports` carrying nine teams, so the
    # catch-all can resolve to itself if nothing forbids it.
    _TeamRow("Adelaide 36ers", None, "basketball_other"),
    _TeamRow("Sydney Kings", None, "basketball_other"),
    # Ice hockey, for the covered-league arm.
    _TeamRow("Toronto Maple Leafs", ["Maple Leafs"], "icehockey_nhl"),
    _TeamRow("Vegas Golden Knights", ["Golden Knights"], "icehockey_nhl"),
    _TeamRow("Frolunda HC", None, "icehockey_shl"),
    # National sides, which really do play in several competitions at once —
    # `Spain` and `Germany` each resolve to BOTH of these today (read off
    # event 15311656). Neither league is Odds-API-covered, so this is the one
    # pair that isolates the ambiguity refusal from the covered one.
    _TeamRow("Spain", None, "soccer_fifa_world_cup"),
    _TeamRow("Germany", None, "soccer_fifa_world_cup"),
    _TeamRow("Spain", None, "soccer_uefa_nations_league"),
    _TeamRow("Germany", None, "soccer_uefa_nations_league"),
]

# `team_identity_mapping` as production serves it. The first two rows are the
# whole reason this channel is consulted: Polymarket writes `Hiroshima Carp`,
# `teams` carries `Hiroshima Toyo Carp`, and the mapping between them was
# written 2026-07-09 — two months before the phantom of 2026-09-12 was minted.
ALIAS_ROWS = [
    _AliasRow("Hiroshima Carp", "baseball_npb"),
    _AliasRow("Tokyo Yakult Swallows", "baseball_npb"),
    _AliasRow("Hanshin Tigers", "baseball_npb"),
    _AliasRow("Chunichi Dragons", "baseball_npb"),
    _AliasRow("Yokohama BayStars", "baseball_npb"),
    _AliasRow("Yomiuri Giants", "baseball_npb"),
    _AliasRow("Chiba Lotte Marines", "baseball_npb"),
    _AliasRow("Saitama Seibu Lions", "baseball_npb"),
    _AliasRow("Tohoku Rakuten Golden Eagles", "baseball_npb"),
    _AliasRow("Fukuoka SoftBank Hawks", "baseball_npb"),
    _AliasRow("Orix Buffaloes", "baseball_npb"),
    # The NFL games that are sitting in `basketball_other` today (Kalshi
    # occurrence rows 15305031, 15305034, 15305036): the catch-all is sometimes
    # wrong about the SPORT, not merely about the league.
    _AliasRow("Baltimore", "americanfootball_nfl"),
    _AliasRow("Indianapolis", "americanfootball_nfl"),
    _AliasRow("Cleveland", "americanfootball_nfl"),
    _AliasRow("Jacksonville", "americanfootball_nfl"),
    # Real, and exactly the wrong-sport attachment this must never make: a club
    # the world knows as ice hockey, carried in `teams` under a SOCCER league.
    _AliasRow("TPS Turku", "soccer_finland_veikkausliiga"),
    _AliasRow("KooKoo", "icehockey_liiga"),
    _AliasRow("Milwaukee Brewers", "baseball_mlb"),
    _AliasRow("Pittsburgh Pirates", "baseball_mlb"),
    _AliasRow("Milwaukee Brewers", "baseball_mlb_preseason"),
    _AliasRow("Pittsburgh Pirates", "baseball_mlb_preseason"),
]


def _session():
    return _FakeSession(TEAM_ROWS, ALIAS_ROWS)


class TestTheDefectArm:
    """The rows a reader saw under the wrong competition label."""

    @pytest.mark.asyncio
    async def test_the_live_specimen_is_placed_in_npb(self):
        """Event 15310925, badged `● LIVE` beside its `baseball_npb` twin on
        `/search?q=Yakult Swallows` at 11:26Z on 2026-09-15.

        THIS ARM DIES IF THE ALIAS CHANNEL IS REMOVED. `Hiroshima Carp` is not
        in `teams` under that name — only `Hiroshima Toyo Carp` is — so the
        club table alone resolves one side and refuses the placement. It is the
        reason this resolver reads two channels instead of reusing
        `covered_league_for_matchup`'s single one.
        """
        assert await placeable_league_for_matchup(
            _session(), "Tokyo Yakult Swallows", "Hiroshima Carp", "baseball_other"
        ) == "baseball_npb"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Yomiuri Giants", "Chunichi Dragons"),                    # 15310208
            ("Tohoku Rakuten Golden Eagles", "Fukuoka SoftBank Hawks"),  # 15310920
            ("Chiba Lotte Marines", "Saitama Seibu Lions"),            # 15310918
            ("Hanshin Tigers", "Hiroshima Carp"),                      # 15310219
            ("Chunichi Dragons", "Hiroshima Carp"),                    # 15311931
            ("Yokohama BayStars", "Tokyo Yakult Swallows"),            # 15310221
        ],
    )
    async def test_every_other_npb_fixture_in_the_window_is_placed(
        self, team_a, team_b
    ):
        assert await placeable_league_for_matchup(
            _session(), team_a, team_b, "baseball_other"
        ) == "baseball_npb"

    @pytest.mark.asyncio
    async def test_the_nickname_trap_does_not_drag_npb_into_mlb(self):
        """`Yomiuri Giants` vs `Hanshin Tigers` is NPB's classic rivalry, and
        "Giants" is San Francisco while "Tigers" is Detroit. A substring test
        resolves both sides into `baseball_mlb` and misplaces a real NPB game
        into the MLB league page — strictly worse than the catch-all it came
        from. Exactness is what stops it."""
        assert await placeable_league_for_matchup(
            _session(), "Yomiuri Giants", "Hanshin Tigers", "baseball_other"
        ) == "baseball_npb"


class TestTheControlsThatMustNotMove:
    """23 of the 42 `baseball_other` rows in the window are NOT placeable, and
    a resolver that moved them would be inventing a league."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Wei Chuan Dragons", "TSG Hawks"),              # CPBL, 15310215
            ("Fubon Guardians", "Rakuten Monkeys"),          # CPBL, 15310207
            ("Chinatrust Brothers", "Uni-President Lions"),  # CPBL, 15310216
            ("Toros de Tijuana", "Olmecas de Tabasco"),      # LMB,  15311781
        ],
    )
    async def test_a_league_we_do_not_carry_stays_in_the_catch_all(
        self, team_a, team_b
    ):
        assert await placeable_league_for_matchup(
            _session(), team_a, team_b, "baseball_other"
        ) is None

    @pytest.mark.asyncio
    async def test_one_resolvable_side_is_not_a_placement(self):
        """Event 15310922, and it is the honest limit of this channel.
        `Orix Buffaloes` resolves; `Nippon Ham Fighters` does not, because
        `teams` and the mapping both carry `Hokkaido Nippon-Ham Fighters`. One
        side is not a matchup — a single nickname must not place a game on its
        own — so the row stays in the catch-all and the gap stays visible."""
        assert await placeable_league_for_matchup(
            _session(), "Nippon Ham Fighters", "Orix Buffaloes", "baseball_other"
        ) is None

    @pytest.mark.asyncio
    async def test_an_ambiguous_pair_of_UNCOVERED_leagues_is_not_a_placement(self):
        """Two candidates is not a league — and this is the pair that PROVES it.

        `Spain` and `Germany` each play in `soccer_fifa_world_cup` and
        `soccer_uefa_nations_league` (event 15311656). Neither is Odds-API
        covered, so nothing downstream can refuse this pair on another ground:
        drop the `len(shared) != 1` test and a real fixture is filed into
        whichever competition sorts first.

        The MLB pair below CANNOT prove it. Mutating the ambiguity refusal to
        "take the first candidate" left that arm green, because `baseball_mlb`
        sorts ahead of `baseball_mlb_preseason` and is then refused for being
        covered. Two guards, one specimen, one of them asleep.
        """
        assert await placeable_league_for_matchup(
            _session(), "Spain", "Germany", "soccer_other"
        ) is None

    @pytest.mark.asyncio
    async def test_the_mlb_phantoms_are_refused_on_both_grounds(self):
        """The nine phantoms of #5544 resolve to `baseball_mlb` AND
        `baseball_mlb_preseason` — ambiguous, and covered either way."""
        assert await placeable_league_for_matchup(
            _session(), "Milwaukee Brewers", "Pittsburgh Pirates", "baseball_other"
        ) is None


class TestItNeverCrossesAFamily:
    """A wrong-sport attachment is a truth defect (notice 40), and the
    catch-all is sometimes wrong about the sport rather than the league."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Baltimore", "Indianapolis"),  # NFL game on `basketball_other`, 15305031
            ("Cleveland", "Jacksonville"),  # NFL game on `basketball_other`, 15305034
        ],
    )
    async def test_an_nfl_game_filed_under_basketball_is_not_placed_as_nfl(
        self, team_a, team_b
    ):
        """These rows ARE misfiled, and this resolver still refuses them. Moving
        a row across families on a name lookup is how `basketball_other` would
        become a source of NFL fixtures; the family key is the one piece of
        evidence here that came from the venue's own category."""
        assert await placeable_league_for_matchup(
            _session(), team_a, team_b, "basketball_other"
        ) is None

    @pytest.mark.asyncio
    async def test_an_ice_hockey_club_carried_under_soccer_is_not_placed(self):
        """`TPS Turku` resolves to `soccer_finland_veikkausliiga` in `teams`
        today. Read out of an `icehockey_other` row it is a soccer league, and
        placing on it would file a hockey game in a soccer competition."""
        assert await placeable_league_for_matchup(
            _session(), "TPS Turku", "KooKoo", "icehockey_other"
        ) is None


class TestItNeverPlacesIntoALeagueThatShouldNotHoldIt:
    @pytest.mark.asyncio
    async def test_a_covered_league_is_never_placed_into(self):
        """A covered-league row should not have been created at all — that is
        #5544's refusal, which has already run by the time this is reached.
        If this channel sees one the club table did not, the answer is to leave
        it in the catch-all: minting a phantom INTO the real league page is
        worse than leaving it out of the way."""
        assert await placeable_league_for_matchup(
            _session(), "Maple Leafs", "Golden Knights", "icehockey_other"
        ) is None
        assert _sport_key_is_odds_api_covered("icehockey_nhl")

    @pytest.mark.asyncio
    async def test_the_catch_all_is_never_placed_into_itself(self):
        """`basketball_other` is a real `sports` row with nine teams on it, so
        both sides of a matchup can genuinely resolve to it. Rewriting a key to
        the key it already has is not a placement, and for a DIFFERENT family's
        catch-all it would be a wrong-sport attachment dressed as one."""
        assert await placeable_league_for_matchup(
            _session(), "Adelaide 36ers", "Sydney Kings", "basketball_other"
        ) is None


class TestOnlyACatchAllIsReRead:
    """A key the venue's own structure spelled is evidence; this may only ever
    improve on "we did not know"."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sport_key", ["baseball_npb", "baseball_mlb", "icehockey_nhl", "soccer_epl"],
    )
    async def test_a_real_league_key_is_returned_untouched(self, sport_key):
        assert await placeable_league_for_matchup(
            _session(), "Tokyo Yakult Swallows", "Hiroshima Carp", sport_key
        ) is None

    @pytest.mark.asyncio
    async def test_a_real_league_key_never_reaches_the_database(self):
        """Not just the verdict — the round trip is skipped, so the matching
        pass does not pay two queries per market to re-derive a key it already
        has from a ticker."""
        session = _session()
        await placeable_league_for_matchup(
            session, "Tokyo Yakult Swallows", "Hiroshima Carp", "baseball_npb"
        )
        assert session.calls == 0

    @pytest.mark.asyncio
    async def test_a_bare_other_names_no_family(self):
        """`"_other"` leaves an empty prefix, and `startswith("_")` would match
        nothing in `sports` — but the empty family must be refused explicitly
        rather than relying on that, because the refusal is the claim."""
        session = _FakeSession(TEAM_ROWS, ALIAS_ROWS)
        assert await placeable_league_for_matchup(
            session, "Tokyo Yakult Swallows", "Hiroshima Carp", "_other"
        ) is None
        assert session.calls == 0


class TestItFailsClosed:
    """Unlike `covered_league_for_matchup`, which fails OPEN because refusing
    costs a real market, this fails CLOSED: a placement is a positive claim
    about which competition a game belongs to."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [(None, "Hiroshima Carp"), ("Tokyo Yakult Swallows", None),
         ("", "Hiroshima Carp"), ("   ", "  "), (None, None)],
    )
    async def test_a_missing_side_places_nothing(self, team_a, team_b):
        assert await placeable_league_for_matchup(
            _session(), team_a, team_b, "baseball_other"
        ) is None

    @pytest.mark.asyncio
    async def test_a_missing_side_never_reaches_the_database(self):
        session = _session()
        await placeable_league_for_matchup(
            session, "Tokyo Yakult Swallows", None, "baseball_other"
        )
        assert session.calls == 0

    @pytest.mark.asyncio
    async def test_no_session_places_nothing(self):
        """#2020's call-site tests drive the whole create path with
        `session=None`; raising here would break them, and guessing a league
        would be this resolver deciding something it cannot see."""
        assert await placeable_league_for_matchup(
            None, "Tokyo Yakult Swallows", "Hiroshima Carp", "baseball_other"
        ) is None

    @pytest.mark.asyncio
    async def test_empty_tables_place_nothing(self):
        assert await placeable_league_for_matchup(
            _FakeSession([], []), "Tokyo Yakult Swallows", "Hiroshima Carp",
            "baseball_other",
        ) is None

    @pytest.mark.asyncio
    async def test_a_malformed_alternates_value_does_not_raise(self):
        """`alternate_names` is free-form JSONB. A dict or a string there must
        degrade to "no alternates", never explode the matching pass."""
        rows = [
            _TeamRow("Tokyo Yakult Swallows", {"not": "a list"}, "baseball_npb"),
            _TeamRow("Hiroshima Toyo Carp", "Carp", "baseball_npb"),
        ]
        assert await placeable_league_for_matchup(
            _FakeSession(rows, []), "Tokyo Yakult Swallows", "Hiroshima Toyo Carp",
            "baseball_other",
        ) == "baseball_npb"
        # ...and the unusable alternates resolve nothing on their own.
        assert await placeable_league_for_matchup(
            _FakeSession(rows, []), "Swallows", "Carp", "baseball_other"
        ) is None

    @pytest.mark.asyncio
    async def test_a_null_league_on_a_row_does_not_raise(self):
        assert await placeable_league_for_matchup(
            _FakeSession([_TeamRow("Tokyo Yakult Swallows", None, None)],
                         [_AliasRow("Hiroshima Carp", None)]),
            "Tokyo Yakult Swallows", "Hiroshima Carp", "baseball_other",
        ) is None


class TestCaseAndWhitespace:
    @pytest.mark.asyncio
    async def test_matching_is_case_insensitive_both_ways(self):
        """Gamma's casing is not ours, and JSONB containment would be
        case-SENSITIVE — which is why the exact test happens in Python."""
        assert await placeable_league_for_matchup(
            _session(), "tokyo yakult swallows", "HIROSHIMA CARP", "baseball_other"
        ) == "baseball_npb"

    @pytest.mark.asyncio
    async def test_surrounding_whitespace_is_ignored(self):
        assert await placeable_league_for_matchup(
            _session(), "  Tokyo Yakult Swallows ", "Hiroshima Carp  ",
            "baseball_other",
        ) == "baseball_npb"


class TestBothChannelsAreLoadBearing:
    """Each arm resolves a real production row the other cannot, so neither is
    redundant and deleting either reddens a named specimen."""

    @pytest.mark.asyncio
    async def test_the_club_table_alone_places_a_row_the_aliases_miss(self):
        session = _FakeSession(TEAM_ROWS, [])
        assert await placeable_league_for_matchup(
            session, "Chiba Lotte Marines", "Saitama Seibu Lions", "baseball_other"
        ) == "baseball_npb"

    @pytest.mark.asyncio
    async def test_the_aliases_alone_place_the_row_the_club_table_misses(self):
        """The live specimen again, with `teams` emptied: `Hiroshima Carp`
        exists ONLY as a Polymarket alias."""
        session = _FakeSession([], ALIAS_ROWS)
        assert await placeable_league_for_matchup(
            session, "Tokyo Yakult Swallows", "Hiroshima Carp", "baseball_other"
        ) == "baseball_npb"

    @pytest.mark.asyncio
    async def test_both_arms_are_queried_for_a_catch_all(self):
        session = _session()
        await placeable_league_for_matchup(
            session, "Tokyo Yakult Swallows", "Hiroshima Carp", "baseball_other"
        )
        assert session.calls == 2

    @pytest.mark.asyncio
    async def test_the_alias_arm_requires_the_mapping_to_agree_with_the_club(self):
        """ASSERTED ON THE STATEMENT, because this guard lives in SQL and a fake
        session cannot enforce it — every mutation of the other refusals reddens
        a specimen, and dropping THIS one reddened nothing until this test.

        `team_identity_mapping.sport_key` disagrees with the club's own league
        on 724 of 19,777 rows (measured 2026-09-15). Requiring the two to agree
        is a second signal inside one channel and costs nothing; without it the
        stale 3.7% can place a fixture on their own.
        """
        session = _session()
        await placeable_league_for_matchup(
            session, "Tokyo Yakult Swallows", "Hiroshima Carp", "baseball_other"
        )
        alias_sql = str(session.statements[1])
        assert "team_identity_mapping.sport_key = sports.key" in alias_sql
