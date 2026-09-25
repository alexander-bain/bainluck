"""#6386 — a CFL game must not be minted as a rugby (or baseball, or basketball) fixture.

THE DEFECT, as a reader met it. On 2026-09-15 `/api/leagues/rugby_other` served
8 upcoming "rugby" games and the FIRST one was Canadian football:

    15312931  Montreal Alouettes v Hamilton Tiger-Cats  2026-09-18 23:30Z
    15310775  Ulster v Edinburgh                        2026-09-25 18:45Z
    15310773  Harlequins v Bath                         2026-09-25 18:45Z
    ...

Its twin is real and exact to the second — `americanfootball_cfl` 15312374,
Hamilton Tiger-Cats v Montreal Alouettes, 2026-09-18 23:30Z, `odds_api`. Same
instant, sides reversed, two rows. The phantom was minted 08:21Z that morning,
so the mint was ongoing and not historic residue.

The sport is guessed from the club NICKNAMES — Tiger-Cats, Elks, Stampeders,
Lions — which is why it lands somewhere different almost every time. Measured
over the whole table: 76 fixtures whose BOTH sides are CFL clubs, scattered
across FOUR unrelated catch-alls (`americanfootball_other` 22, `baseball_other`
21, `rugby_other` 20, `basketball_other` 13). Four is one worse than the three
#6377 measured for Aussie Rules; it is the same Q453 unmapped-series scatter.

WHY THE COVERED LIST IS THE RIGHT PLACE. All 76 duplicate a real CFL fixture —
76/76, checked by club pair rather than by `commence_time`, because the older
rows carry Gamma's LISTING stamp (#4965 / gotcha #14) and are days adrift. The
Odds API carries the league end to end (68 `odds_api` CFL rows all-time, latest
2026-09-14), so this list's stated predicate — the schedule already has the
game, so a market-born row can only be a twin — holds exactly.

WHY THIS FILE IS SHORTER THAN #6377's. That ship had to add `unambiguous_only`
because 37 AFL club pairs field a side in both codes. CFL has ZERO such
collisions: all 9 clubs plus the alternates `Argonauts` and `Blue Bombers`
resolve to `americanfootball_cfl` and to no other league. So there is no new
ambiguity hazard to guard, and the interesting property to pin is the opposite
one — that the relink arm, which needs the league NAMED, CAN name it here.
`TestTheRelinkCanNameIt` is that arm.

THE ANTI-VACUITY PROBLEM, inherited from #6377, and what was done about it
rather than documented around it. The real query bounds itself to the covered
leagues in SQL, so a fake session that IGNORES the predicate hands over CFL
clubs whether or not the tuple was ever changed. That was measured here, not
assumed: with #6377's pass-through fake, reverting the tuple addition failed
**2 of 25** — one compiled-SQL test carrying the file while twenty-three
resolver assertions passed on the pre-ship tree and proved nothing.

So `_FakeSession` was rewritten to honour the predicate: it renders the
statement, reads the league prefixes the query actually asked for back out of
it, and serves only the rows Postgres would have returned. The same revert now
fails **15 of 25**, and the defect arms are guards instead of prose.

MUTANTS RUN, not reasoned about — all four killed, each restored from git
(never from /tmp), against the committed tree so a restore cannot silently
revert the fix along with the mutation:

  * reverting the one-line tuple addition — **15 of 25 fail**, including every
    `TestTheDefectArm` case and both `TestTheResidual` arms.
  * widening it to the family prefix `"americanfootball"` — **3 fail**,
    `test_the_catch_all_is_not_covered` among them, because it would refuse
    every `americanfootball_other` row in the family: the failure mode
    `covered_league_for_matchup`'s docstring rejects by name.
  * making `unambiguous_only` refuse unconditionally — **3 fail**, all of
    `TestTheRelinkCanNameIt::test_a_cfl_pair_names_exactly_one_league`. This is
    what makes that arm non-vacuous: CFL is relinkable, and a flag that always
    declined would take that away silently.
  * making `unambiguous_only` a no-op — **1 fails**,
    `test_a_pair_in_two_real_leagues_is_still_ambiguous_and_refused`, which is
    the control that keeps the arm above honest. (It was the NFL/NFL-preseason
    pair until #8547 ruled a season variant beside its parent ONE league.)
"""
import re

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
    """HONOURS the covered-league predicate instead of ignoring it.

    #6377's fake returned its rows whatever the SQL said, and its own docstring
    flagged the consequence: every resolver assertion passed on the pre-ship
    tree, leaving one compiled-SQL test carrying the whole file. Measured here
    before this class was written — reverting the tuple addition under a
    pass-through fake failed 2 of 25.

    So this one renders the statement, reads the league prefixes the query
    ACTUALLY asked for back out of it, and serves only the rows a real
    Postgres would have returned. The prefixes come from the compiled SQL and
    not from re-importing `ODDS_API_COVERED_PREFIXES`, because re-importing the
    constant would make the fake agree with the tuple by construction — which
    is the same vacuity one level down.

    `last_statement` is kept as well, so `TestTheListItself` can still assert
    the prefix directly rather than only through its effect.
    """

    #: Quoted string literals in the rendered WHERE clause. With
    #: `literal_binds` the prefix arm renders as `sports.key LIKE
    #: 'basketball_nba%'` (or `'basketball_nba' || '%'`), so the league keys are
    #: exactly the quoted runs, with any trailing LIKE wildcard stripped.
    _LITERAL = re.compile(r"'([^']*)'")

    def __init__(self, rows):
        self._rows = rows
        self.last_statement = None

    @classmethod
    def _prefixes(cls, statement):
        rendered = str(
            statement.compile(compile_kwargs={"literal_binds": True})
        )
        found = {
            literal.rstrip("%")
            for literal in cls._LITERAL.findall(rendered)
            if literal.rstrip("%")
        }
        return found

    async def execute(self, statement):
        self.last_statement = statement
        prefixes = self._prefixes(statement)
        return [
            row
            for row in self._rows
            if any(tuple(row)[2].startswith(p) for p in prefixes)
        ]


# Verbatim from production (db-query, 2026-09-15). All nine CFL clubs, with
# their real `alternate_names` — seven have none, which is what makes the
# residual below real.
CLUBS = [
    _Row("BC Lions", None, "americanfootball_cfl"),
    _Row("Calgary Stampeders", None, "americanfootball_cfl"),
    _Row("Edmonton Elks", None, "americanfootball_cfl"),
    _Row("Hamilton Tiger-Cats", None, "americanfootball_cfl"),
    _Row("Montreal Alouettes", None, "americanfootball_cfl"),
    _Row("Ottawa Redblacks", None, "americanfootball_cfl"),
    _Row("Saskatchewan Roughriders", None, "americanfootball_cfl"),
    _Row("Toronto Argonauts", ["Argonauts"], "americanfootball_cfl"),
    _Row("Winnipeg Blue Bombers", ["Blue Bombers"], "americanfootball_cfl"),
    # The nickname trap, deliberately present: a substring or token test reads
    # "BC Lions" as Detroit. Both rows are verbatim, preseason included,
    # because `americanfootball_nfl` is a prefix of `americanfootball_nfl_
    # preseason` and so both are already covered.
    _Row("Detroit Lions", ["Lions"], "americanfootball_nfl"),
    _Row("Detroit Lions", None, "americanfootball_nfl_preseason"),
    _Row("Cincinnati Bengals", ["Bengals"], "americanfootball_nfl"),
    _Row("Cincinnati Bengals", None, "americanfootball_nfl_preseason"),
]


def _session():
    return _FakeSession(CLUBS)


class TestTheListItself:
    """The prefix addition, pinned on the consumers a fake session hides."""

    def test_the_cfl_is_covered(self):
        assert _sport_key_is_odds_api_covered("americanfootball_cfl") is True

    @pytest.mark.asyncio
    async def test_the_query_actually_bounds_itself_to_the_new_key(self):
        """Reads the prefix back out of the compiled SQL directly, rather than
        only through its effect on which rows come back. Kept even though
        `_FakeSession` now honours the predicate: this one states the contract
        the fake DEPENDS on, so if the query ever stopped bounding itself in
        SQL, this fails loudly instead of the fake quietly widening."""
        session = _session()
        await covered_league_for_matchup(
            session, "Montreal Alouettes", "Hamilton Tiger-Cats"
        )
        rendered = str(
            session.last_statement.compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert "americanfootball_cfl" in rendered

    def test_the_list_is_still_a_tuple_of_league_keys(self):
        """A family prefix here would refuse every `americanfootball_other` row
        in the family — the failure mode `covered_league_for_matchup`'s
        docstring rejects by name."""
        assert "americanfootball" not in ODDS_API_COVERED_PREFIXES


class TestTheDefectArm:
    """The fixtures a reader met, one per catch-all the scatter reached."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            # 15312931 — the live one, first upcoming card on the rugby page.
            ("Montreal Alouettes", "Hamilton Tiger-Cats"),
            ("Toronto Argonauts", "Hamilton Tiger-Cats"),      # rugby_other
            ("Saskatchewan Roughriders", "Winnipeg Blue Bombers"),  # basketball_other
            ("Ottawa Redblacks", "Toronto Argonauts"),         # basketball_other
            ("Montreal Alouettes", "Winnipeg Blue Bombers"),   # americanfootball_other
            ("Hamilton Tiger-Cats", "Calgary Stampeders"),     # rugby_other
        ],
    )
    async def test_a_cfl_matchup_is_refused_a_mint(self, team_a, team_b):
        assert await covered_league_for_matchup(
            _session(), team_a, team_b
        ) == "americanfootball_cfl"

    @pytest.mark.asyncio
    async def test_the_refusal_does_not_depend_on_side_order(self):
        """The live twin pair is spelled in opposite orders by the two sources —
        the phantom is Montreal v Hamilton, the real row Hamilton v Montreal."""
        assert await covered_league_for_matchup(
            _session(), "Hamilton Tiger-Cats", "Montreal Alouettes"
        ) == "americanfootball_cfl"

    @pytest.mark.asyncio
    async def test_an_alternate_name_resolves_its_club(self):
        """Two of the nine carry alternates, and the venue uses them."""
        assert await covered_league_for_matchup(
            _session(), "Argonauts", "Blue Bombers"
        ) == "americanfootball_cfl"


class TestTheRelinkCanNameIt:
    """`unambiguous_only=True` — and the measured reason it is satisfied here.

    This is the arm that makes CFL different from Aussie Rules. #6377 could
    only refuse the mint, because every live AFL specimen was ambiguous across
    the two codes. Zero CFL clubs collide, so `shared` is exactly 1 and the
    relink may actually move the market onto the real fixture.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Montreal Alouettes", "Hamilton Tiger-Cats"),
            ("Toronto Argonauts", "Saskatchewan Roughriders"),
            ("BC Lions", "Edmonton Elks"),
        ],
    )
    async def test_a_cfl_pair_names_exactly_one_league(self, team_a, team_b):
        assert await covered_league_for_matchup(
            _session(), team_a, team_b, unambiguous_only=True
        ) == "americanfootball_cfl"

    @pytest.mark.asyncio
    async def test_a_pair_in_two_real_leagues_is_still_ambiguous_and_refused(self):
        """THE CONTRAST THAT KEEPS THE ARM ABOVE HONEST. Two clubs that both
        resolve in two genuinely different covered leagues cannot be NAMED. If
        `unambiguous_only` were quietly neutered this would return a league and
        `test_a_cfl_pair_names_exactly_one_league` above would prove nothing."""
        rows = CLUBS + [
            _Row("Detroit Lions", None, "americanfootball_ncaaf"),
            _Row("Cincinnati Bengals", None, "americanfootball_ncaaf"),
        ]
        assert await covered_league_for_matchup(
            _FakeSession(rows), "Detroit Lions", "Cincinnati Bengals",
            unambiguous_only=True,
        ) is None

    @pytest.mark.asyncio
    async def test_the_nfl_pair_names_its_league_despite_preseason_rows_8547(self):
        """Production carries BOTH clubs under `americanfootball_nfl` AND
        `americanfootball_nfl_preseason` (all four rows verbatim in `CLUBS`).
        This pair was this file's ambiguity control until #8547: a season
        variant beside its own parent is ONE league, and reading it as two
        declined every Polymarket venue-instant relink in MLB/NFL/NHL/NBA."""
        assert await covered_league_for_matchup(
            _session(), "Detroit Lions", "Cincinnati Bengals",
            unambiguous_only=True,
        ) == "americanfootball_nfl"

    @pytest.mark.asyncio
    async def test_that_same_nfl_pair_is_still_refused_a_mint(self):
        """...while the MINTING refusal, which only needs a league to EXIST,
        still fires on it. The two arms ask different questions of one
        resolver and this pins both answers on one input."""
        assert await covered_league_for_matchup(
            _session(), "Detroit Lions", "Cincinnati Bengals"
        ) == "americanfootball_nfl"


class TestTheResidualIsRealAndPinned:
    """The 23 of 76 this ship does NOT reach, asserted rather than described.

    `teams` spells the club `BC Lions` with no alternates, but 23 of the 76
    market-born rows spell it `British Columbia Lions`. The resolver is
    strictly exact on `name`/`alternate_names` — deliberately, because a token
    test would read "Hanshin Tigers" as Detroit — so that side resolves to
    nothing and the refusal cannot fire.

    Pinned as a test so the gap is a measured fact rather than a sentence in a
    PR body, and so that whoever adds the alternate (an attended production
    write via `scripts/backfill_curated_team_aliases.py`, out of scope here)
    finds a red test telling them the coverage changed.
    """

    @pytest.mark.asyncio
    async def test_the_provider_spelling_is_not_reachable_today(self):
        assert await covered_league_for_matchup(
            _session(), "British Columbia Lions", "Montreal Alouettes"
        ) is None

    @pytest.mark.asyncio
    async def test_the_teams_spelling_of_the_same_club_is_reachable(self):
        """Same fixture, the other spelling — so the test above is pinning a
        NAME gap and not some other refusal in the resolver."""
        assert await covered_league_for_matchup(
            _session(), "BC Lions", "Montreal Alouettes"
        ) == "americanfootball_cfl"


class TestTheControlsThatMustStayCreatable:
    """Rows this ship must not touch."""

    def test_the_catch_all_is_not_covered(self):
        """`americanfootball_other` is where 22 of the phantoms landed, but the
        key itself names no competition the schedule carries, so the refusal
        has nothing to stand on. `americanfootball_cfl` is not a prefix of it —
        this asserts that stays true."""
        assert _sport_key_is_odds_api_covered("americanfootball_other") is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            # THE CONTROL THIS SHIP IS MOST LIKELY TO BREAK. Seven of the eight
            # upcoming games on that rugby page really were rugby union —
            # Premiership, URC and Top 14, none of them schedule-covered. Those
            # clubs are absent from `teams` entirely, which is the correct
            # answer and the reason their markets keep minting.
            ("Leicester Tigers", "Saracens"),
            ("Ulster", "Edinburgh"),
            ("Harlequins", "Bath"),
            ("Benetton Treviso", "Dragons"),
        ],
    )
    async def test_a_real_rugby_union_fixture_is_still_creatable(
        self, team_a, team_b
    ):
        assert await covered_league_for_matchup(_session(), team_a, team_b) is None

    @pytest.mark.asyncio
    async def test_one_cfl_side_alone_refuses_nothing(self):
        """BOTH sides must land in the same league. A single club facing an
        unknown opponent is not a CFL matchup, and treating it as one would
        refuse real markets on one nickname."""
        assert await covered_league_for_matchup(
            _session(), "Montreal Alouettes", "Leicester Tigers"
        ) is None

    @pytest.mark.asyncio
    async def test_the_detroit_lions_trap(self):
        """`BC Lions` and `Detroit Lions` share the bare alternate `Lions`. The
        exact test keeps them apart; a substring test would resolve the CFL
        club into the NFL and name the wrong league for the relink."""
        assert await covered_league_for_matchup(
            _session(), "BC Lions", "Calgary Stampeders"
        ) == "americanfootball_cfl"
