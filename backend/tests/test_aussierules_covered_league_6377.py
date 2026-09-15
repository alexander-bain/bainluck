"""#6377 — an Aussie Rules match must not be minted as a basketball fixture.

THE DEFECT, as a reader met it. On 2026-09-15 `/api/leagues/basketball_other`
served 8 upcoming "basketball" games and 3 of them were Australian-rules
football:

    15312509  Hawthorn Hawks v North Melbourne Kangaroos  2026-09-18 07:45Z
    15311099  Hawthorn Hawks v Brisbane Lions             2026-09-19 07:15Z
    15312508  Essendon Bombers v Gold Coast Suns          2026-09-20 03:05Z

Polymarket tags those events `afl` / `aflw` and neither tag is in
`_TAG_TO_CATEGORY` (polymarket.py), so `_tags_to_category` falls through to the
"sports" catch-all, the sport is guessed from the club NICKNAMES — Hawks, Suns,
Kangaroos — and the fixture is minted into whatever catch-all the guess lands
on. Measured over 30 days: 17 such phantoms, scattered across THREE unrelated
catch-alls (`basketball_other` 11, `americanfootball_other` 4,
`motorsport_other` 3). The scatter is the unmapped-series signature Q453
records.

WHY THE COVERED LIST IS THE RIGHT PLACE. All 17 duplicate a real scheduled
fixture — 17/17, checked by club pair rather than by `commence_time`, because
the older rows carry Gamma's LISTING stamp (#4965 / gotcha #14) and are 90-167h
adrift while the three minted since #6073 are exact to the second. "The
schedule already carries the game, so a market-born row can only be a twin" is
this list's stated predicate, and Aussie Rules meets it.

THE HAZARD THAT CAME WITH IT, and why half this file is about a flag. Adding
the two AFL keys makes `covered_league_for_matchup` reachable for club pairs
that field a side in BOTH codes. Measured on production: 37 such pairs, and one
of them — North Melbourne Kangaroos v Geelong Cats, 2026-08-15 — plays the two
codes 2h45m apart, INSIDE `_PM_FIXTURE_MAX_DIFF_HOURS`. The phase-15 relink
searches the ONE key the resolver names, so `sorted(shared)[0]` spelling the
men's key first would move a women's market onto the men's game: a wrong-sport
attachment under notice 40, not a missed link.

So the resolver keeps its tie-break for the MINTING refusal, which only needs
the league to EXIST, and gains `unambiguous_only=True` for the relink, which
needs it NAMED. Both arms are pinned below, and the two mutants were run rather
than reasoned about:

  * making the flag UNCONDITIONAL kills all three
    `TestTheDefectArm::test_an_aussie_rules_matchup_is_refused_a_mint` cases —
    every live specimen is ambiguous, so a resolver that declined to name a
    league on ambiguity would stop refusing the mint and the phantoms would
    come straight back. (It does NOT touch
    `test_an_unambiguous_aussie_rules_pair_names_its_code`, which is
    unambiguous by construction — the reason that test is not the one named
    here.)
  * DROPPING the flag, i.e. the pre-ship tree, fails 8 of these 19.
"""
import pytest

from app.tasks.prediction_market_matching import (
    ODDS_API_COVERED_PREFIXES,
    _sport_key_is_odds_api_covered,
    covered_league_for_matchup,
)


class _Row:
    """One `teams`-joined-`sports` row as the query returns it."""

    def __init__(self, name, alternates, sport_key):
        self._values = (name, alternates, sport_key)

    def __iter__(self):
        return iter(self._values)


class _FakeSession:
    """Returns its rows regardless of predicate, and KEEPS the statement.

    The real query bounds itself to the covered leagues in SQL, so a fake
    session that ignores the predicate cannot see `ODDS_API_COVERED_PREFIXES`
    at all — every exact-match assertion below would pass just as well before
    this ship as after it. `last_statement` is what closes that hole:
    `TestTheListItself` compiles it and reads the prefixes back out.
    """

    def __init__(self, rows):
        self._rows = rows
        self.last_statement = None

    async def execute(self, statement):
        self.last_statement = statement
        return list(self._rows)


# Verbatim from production (db-query, 2026-09-15). Every AFL club below carries
# a same-named row in BOTH codes, which is the ambiguity this file is about.
CLUBS = [
    _Row("Hawthorn Hawks", ["Hawks"], "aussierules_afl"),
    _Row("Hawthorn Hawks", ["Hawks"], "aussierules_aflw"),
    _Row("North Melbourne Kangaroos", ["Kangaroos"], "aussierules_afl"),
    _Row("North Melbourne Kangaroos", ["Kangaroos"], "aussierules_aflw"),
    _Row("Brisbane Lions", ["Lions"], "aussierules_afl"),
    _Row("Brisbane Lions", ["Lions"], "aussierules_aflw"),
    _Row("Essendon Bombers", ["Bombers"], "aussierules_afl"),
    _Row("Essendon Bombers", ["Bombers"], "aussierules_aflw"),
    _Row("Gold Coast Suns", ["Suns"], "aussierules_afl"),
    _Row("Gold Coast Suns", ["Suns"], "aussierules_aflw"),
    # Geelong Cats field only the men's side in `teams` today, which is what
    # makes the 2026-08-15 pair resolve to ONE league and therefore relinkable.
    _Row("Geelong Cats", ["Cats"], "aussierules_afl"),
    # The nickname trap, deliberately present: a substring test reads "Gold
    # Coast Suns" as Phoenix and "Hawthorn Hawks" as Atlanta.
    _Row("Phoenix Suns", ["Suns", "Phoenix"], "basketball_nba"),
    _Row("Atlanta Hawks", ["Hawks", "Atlanta"], "basketball_nba"),
    _Row("Illawarra Hawks", ["Hawks"], "basketball_nbl"),
]


def _session():
    return _FakeSession(CLUBS)


class TestTheListItself:
    """The prefix addition, pinned on the two consumers a fake session hides.

    These are the only assertions here that fail on the pre-ship tree; the
    resolver arms below would pass either way, because `_FakeSession` serves
    the AFL clubs whatever the SQL says.
    """

    @pytest.mark.parametrize(
        "sport_key", ["aussierules_afl", "aussierules_aflw"]
    )
    def test_both_codes_are_covered(self, sport_key):
        assert _sport_key_is_odds_api_covered(sport_key) is True

    def test_the_catch_all_is_not_covered(self):
        """`aussierules_other` must not be swept in by the prefix. It names no
        competition the schedule carries, so the refusal has nothing to stand
        on — and `aussierules_afl` is a prefix of `aussierules_aflw` but not of
        this."""
        assert _sport_key_is_odds_api_covered("aussierules_other") is False

    @pytest.mark.asyncio
    async def test_the_query_actually_bounds_itself_to_the_new_keys(self):
        """THE ANTI-VACUITY ARM. Reads the prefixes back out of the compiled
        SQL, so this file cannot pass on a tree where the tuple was never
        changed and the fake session simply handed over AFL clubs anyway."""
        session = _session()
        await covered_league_for_matchup(session, "Hawthorn Hawks", "Brisbane Lions")
        rendered = str(
            session.last_statement.compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert "aussierules_afl" in rendered
        assert "aussierules_aflw" in rendered

    def test_the_list_is_still_a_tuple_of_league_keys(self):
        """A family prefix here would refuse every `_other` row in the family —
        the failure mode `covered_league_for_matchup`'s docstring rejects by
        name. `"aussierules"` alone would do exactly that."""
        assert "aussierules" not in ODDS_API_COVERED_PREFIXES


class TestTheDefectArm:
    """The three fixtures a reader met on the basketball page."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Hawthorn Hawks", "North Melbourne Kangaroos"),  # 15312509
            ("Hawthorn Hawks", "Brisbane Lions"),             # 15311099
            ("Essendon Bombers", "Gold Coast Suns"),          # 15312508
        ],
    )
    async def test_an_aussie_rules_matchup_is_refused_a_mint(self, team_a, team_b):
        """The MINTING refusal: any covered league answers it, so the AFL/AFLW
        ambiguity must NOT stop it firing."""
        league = await covered_league_for_matchup(_session(), team_a, team_b)
        assert league is not None
        assert league.startswith("aussierules_")

    @pytest.mark.asyncio
    async def test_an_unambiguous_aussie_rules_pair_names_its_code(self):
        """Geelong field only the men's side in `teams`, so this pair collapses
        to one key. Stated separately from the three above because it is the
        ONLY Aussie Rules pair here that the relink arm may also act on, and
        `TestTheAmbiguityGuard` asserts exactly that about it."""
        assert await covered_league_for_matchup(
            _session(), "North Melbourne Kangaroos", "Geelong Cats"
        ) == "aussierules_afl"


class TestTheAmbiguityGuard:
    """`unambiguous_only=True` — the relink's stricter question."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Hawthorn Hawks", "North Melbourne Kangaroos"),
            ("Hawthorn Hawks", "Brisbane Lions"),
            ("Essendon Bombers", "Gold Coast Suns"),
        ],
    )
    async def test_an_ambiguous_pair_is_refused_by_name(self, team_a, team_b):
        """Both clubs field a side in both codes, so no key can be NAMED and the
        relink must decline rather than tie-break onto the men's game."""
        assert await covered_league_for_matchup(
            _session(), team_a, team_b, unambiguous_only=True
        ) is None

    @pytest.mark.asyncio
    async def test_the_measured_2026_08_15_pair_is_the_one_that_mattered(self):
        """North Melbourne Kangaroos v Geelong Cats played both codes 2h45m
        apart — inside `_PM_FIXTURE_MAX_DIFF_HOURS`. Geelong field only the
        men's side in `teams`, so `shared` collapses to one key and the relink
        is ALLOWED here. This arm exists to state that the guard is not a
        blanket off-switch: it declines on ambiguity, not on Aussie Rules."""
        assert await covered_league_for_matchup(
            _session(), "North Melbourne Kangaroos", "Geelong Cats",
            unambiguous_only=True,
        ) == "aussierules_afl"

    @pytest.mark.asyncio
    async def test_an_unambiguous_covered_pair_still_relinks(self):
        """THE NON-VACUITY ARM for the flag. If `unambiguous_only` were wired to
        return None always, this passes only by accident of the NBA rows — so it
        asserts the league by name."""
        assert await covered_league_for_matchup(
            _session(), "Phoenix Suns", "Atlanta Hawks", unambiguous_only=True
        ) == "basketball_nba"

    @pytest.mark.asyncio
    async def test_the_default_is_unchanged(self):
        """Every existing caller passes no flag and must keep the tie-break."""
        assert await covered_league_for_matchup(
            _session(), "Phoenix Suns", "Atlanta Hawks"
        ) == "basketball_nba"


class TestTheControlsThatMustStayCreatable:
    """Rows this ship must not touch."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Hanshin Tigers", "Hiroshima Carp"),   # NPB
            ("Wei Chuan Dragons", "TSG Hawks"),     # CPBL, and the "Hawks" trap
            ("Spain", "Germany"),                   # FIBA national sides
        ],
    )
    async def test_an_uncovered_league_is_still_creatable(self, team_a, team_b):
        assert await covered_league_for_matchup(_session(), team_a, team_b) is None

    @pytest.mark.asyncio
    async def test_an_nbl_matchup_is_still_creatable(self):
        """THE CONTROL THIS SHIP IS MOST LIKELY TO BREAK. Five of the eight
        fixtures on that basketball page really were basketball — Australian NBL
        — and the NBL is NOT schedule-covered. "Illawarra Hawks" shares a
        nickname with Hawthorn and a city-less name with Atlanta; if the AFL
        addition were written as a family prefix, or if the exact match slipped
        to a substring, this row would stop being creatable and five real
        fixtures would vanish."""
        assert await covered_league_for_matchup(
            _session(), "Illawarra Hawks", "Melbourne United"
        ) is None
