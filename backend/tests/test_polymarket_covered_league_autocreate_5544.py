"""#5544 — a Polymarket MLB fixture must not mint a `baseball_other` twin.

THE DEFECT. `_create_event_from_prediction_market` already refuses to
auto-create for leagues the Odds API covers end to end. That refusal tests
`sport_key.startswith("baseball_mlb")`, but a market with no ticker — every
Polymarket market — gets its key from `auto_create_sport_key_from_category`,
which can only ever return the `<prefix>_other` CATCH-ALL. So the gate written
to prevent exactly this defect could never fire for the population that
generates it.

Measured on production 2026-09-12: nine real MLB fixtures minted at
2026-09-11 13:24Z as unbound `baseball_other` rows stamped with Gamma's
LISTING time, four of them exact twins of StatPal rows that arrived 15 hours
later, with the Polymarket market on the PHANTOM and 0 markets on each real
game.

THE CONTROL IS THE POINT. The `_other` bucket is genuinely mixed — the same
production read found 6 NPB/CPBL fixtures beside the 9 MLB ones — so a
family-wide refusal would drop real rows for leagues the Odds API does not
carry. Every fixture below is a real matchup from that read, and the NPB/CPBL
arms must stay creatable.
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
    """Returns the covered-league clubs regardless of predicate.

    The real query filters to covered leagues in SQL; returning them all here
    means the test grades the EXACT-MATCH logic, which is the part that decides
    MLB from NPB, rather than re-testing SQLAlchemy's `startswith`.
    """

    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    async def execute(self, _statement):
        self.calls += 1
        return list(self._rows)


# Exactly as production serves them (db-query, 2026-09-12). The NPB clubs carry
# no alternates and the CPBL clubs are absent from `teams` altogether, which is
# why neither can be resolved into a covered league.
COVERED_CLUBS = [
    _Row("Milwaukee Brewers", ["Brewers", "Milwaukee"], "baseball_mlb"),
    _Row("Pittsburgh Pirates", ["Pittsburgh", "Pirates"], "baseball_mlb"),
    _Row("Athletics", ["A's"], "baseball_mlb"),
    _Row("Tampa Bay Rays", ["Rays", "Tampa Bay"], "baseball_mlb"),
    _Row("Milwaukee Brewers", ["Milwaukee", "Brewers"], "baseball_mlb_preseason"),
    _Row("Toronto Maple Leafs", ["Maple Leafs"], "icehockey_nhl"),
    _Row("Vegas Golden Knights", ["Golden Knights"], "icehockey_nhl"),
    _Row("Las Vegas Aces", ["Aces", "Las Vegas"], "basketball_wnba"),
    _Row("Phoenix Mercury", ["Mercury"], "basketball_wnba"),
    # Deliberately present and deliberately NOT covered: the token trap. A
    # substring test would read "Hanshin Tigers" as this club.
    _Row("Detroit Tigers", ["Tigers", "Detroit"], "baseball_mlb"),
    _Row("San Francisco Giants", ["Giants", "San Francisco"], "baseball_mlb"),
    _Row("New York Giants", ["Giants", "New York"], "americanfootball_nfl"),
]


def _session():
    return _FakeSession(COVERED_CLUBS)


class TestTheDefectArm:
    """Real MLB matchups that were minted as `baseball_other` phantoms."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Milwaukee Brewers", "Pittsburgh Pirates"),  # 15310210 / 15310673
            ("Athletics", "Tampa Bay Rays"),              # 15310214 / 15310675
        ],
    )
    async def test_an_mlb_matchup_is_refused(self, team_a, team_b):
        assert await covered_league_for_matchup(_session(), team_a, team_b) == (
            "baseball_mlb"
        )

    @pytest.mark.asyncio
    async def test_a_short_form_nhl_matchup_is_refused(self):
        """Polymarket names NHL clubs by nickname — `Maple Leafs vs. Golden
        Knights` is verbatim from the production read. Only `alternate_names`
        can resolve those, so this arm dies if the alternates are dropped."""
        assert await covered_league_for_matchup(
            _session(), "Maple Leafs", "Golden Knights"
        ) == "icehockey_nhl"

    @pytest.mark.asyncio
    async def test_a_wnba_matchup_is_refused(self):
        assert await covered_league_for_matchup(
            _session(), "Las Vegas Aces", "Phoenix Mercury"
        ) == "basketball_wnba"


class TestTheControlsThatMustStayCreatable:
    """The 15 real rows a family-wide refusal would have cost."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Hanshin Tigers", "Hiroshima Carp"),        # NPB, and the token trap
            ("Yomiuri Giants", "Chunichi Dragons"),      # NPB, ditto on "Giants"
            ("Wei Chuan Dragons", "TSG Hawks"),          # CPBL, absent from teams
            ("Storhamar Hockey", "Frolunda HC"),         # European ice hockey
            ("Spain", "USA"),                            # FIBA national sides
        ],
    )
    async def test_an_uncovered_league_is_still_creatable(self, team_a, team_b):
        assert await covered_league_for_matchup(_session(), team_a, team_b) is None

    @pytest.mark.asyncio
    async def test_a_foreign_matchup_colliding_on_BOTH_sides_is_still_creatable(self):
        """THE TOKEN TRAP, at full strength. Yomiuri Giants vs Hanshin Tigers is
        NPB's classic rivalry and a real Polymarket fixture — and "Giants" is
        San Francisco (and New York), "Tigers" is Detroit. A substring test
        resolves BOTH sides into `baseball_mlb` and refuses an NPB game.

        The other foreign controls above cannot catch this: mutating the exact
        test to a substring left `Hanshin Tigers vs Hiroshima Carp` green,
        because no covered club is called the Carp. That arm passes by luck of
        the opponent's name. This one does not.
        """
        assert await covered_league_for_matchup(
            _session(), "Yomiuri Giants", "Hanshin Tigers"
        ) is None

    @pytest.mark.asyncio
    async def test_one_covered_side_is_not_a_covered_matchup(self):
        """An MLB club against an unknown name is not an MLB fixture. Refusing
        on one side would let a single nickname veto a real create."""
        assert await covered_league_for_matchup(
            _session(), "Milwaukee Brewers", "Wei Chuan Dragons"
        ) is None

    @pytest.mark.asyncio
    async def test_a_nickname_shared_across_sports_refuses_nothing(self):
        """"Giants" is San Francisco AND New York. Neither side resolving to a
        SHARED league is what stops an ambiguous token deciding this alone."""
        assert await covered_league_for_matchup(
            _session(), "Giants", "Chunichi Dragons"
        ) is None


class TestItFailsOpen:
    """An over-refusing guard silently drops real markets, so every no-signal
    case must let the create proceed — the trade `_check_polymarket_fixture_reason`
    already makes."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "team_a,team_b",
        [(None, "Pittsburgh Pirates"), ("Milwaukee Brewers", None),
         ("", "Pittsburgh Pirates"), ("   ", "  "), (None, None)],
    )
    async def test_a_missing_side_refuses_nothing(self, team_a, team_b):
        assert await covered_league_for_matchup(_session(), team_a, team_b) is None

    @pytest.mark.asyncio
    async def test_a_missing_side_never_reaches_the_database(self):
        """Not just the verdict — the query itself is skipped, so a half-parsed
        matchup cannot cost a round trip on every unlinked market."""
        session = _session()
        await covered_league_for_matchup(session, "Milwaukee Brewers", None)
        assert session.calls == 0

    @pytest.mark.asyncio
    async def test_no_session_refuses_nothing(self):
        """The only refusal on this path that needs a session. `test_unanchored
        _create_loop_2020` drives the whole create with `session=None` to prove
        #2020's ticker stamp survives it, so raising there — or refusing on no
        evidence — would be this guard deciding an outcome it cannot see."""
        assert await covered_league_for_matchup(
            None, "Milwaukee Brewers", "Pittsburgh Pirates"
        ) is None

    @pytest.mark.asyncio
    async def test_an_empty_teams_table_refuses_nothing(self):
        assert await covered_league_for_matchup(
            _FakeSession([]), "Milwaukee Brewers", "Pittsburgh Pirates"
        ) is None

    @pytest.mark.asyncio
    async def test_a_malformed_alternates_value_does_not_raise(self):
        """`alternate_names` is free-form JSONB. A dict or a string there must
        degrade to "no alternates", never explode the matching pass."""
        rows = [
            _Row("Milwaukee Brewers", {"not": "a list"}, "baseball_mlb"),
            _Row("Pittsburgh Pirates", "Pirates", "baseball_mlb"),
        ]
        # Both still resolve on their exact NAME, so the refusal stands.
        assert await covered_league_for_matchup(
            _FakeSession(rows), "Milwaukee Brewers", "Pittsburgh Pirates"
        ) == "baseball_mlb"
        # ...and the unusable alternates resolve nothing on their own.
        assert await covered_league_for_matchup(
            _FakeSession(rows), "Brewers", "Pirates"
        ) is None


class TestCaseAndWhitespace:
    @pytest.mark.asyncio
    async def test_matching_is_case_insensitive_both_ways(self):
        """Gamma's casing is not ours. JSONB containment would be case-SENSITIVE,
        which is why the exact test is done in Python."""
        assert await covered_league_for_matchup(
            _session(), "milwaukee brewers", "PITTSBURGH PIRATES"
        ) == "baseball_mlb"
        assert await covered_league_for_matchup(
            _session(), "maple leafs", "golden knights"
        ) == "icehockey_nhl"

    @pytest.mark.asyncio
    async def test_surrounding_whitespace_is_ignored(self):
        assert await covered_league_for_matchup(
            _session(), "  Milwaukee Brewers ", "Pittsburgh Pirates  "
        ) == "baseball_mlb"


class TestTheRefusalIsWiredToTheBoundary:
    def test_the_covered_list_is_one_object(self):
        """#5544 lifted the tuple to module scope precisely so the prefix gate
        and this resolver cannot drift onto two copies."""
        assert "baseball_mlb" in ODDS_API_COVERED_PREFIXES
        assert _sport_key_is_odds_api_covered("baseball_mlb")
        assert _sport_key_is_odds_api_covered("baseball_mlb_preseason")

    def test_the_catch_all_is_exactly_what_the_prefix_gate_misses(self):
        """The whole reason this issue exists: `baseball_other` is the key the
        fallback produces, and no covered prefix is a prefix of it. If this ever
        becomes True the resolver is redundant — and so is the bug."""
        assert not _sport_key_is_odds_api_covered("baseball_other")
        assert not _sport_key_is_odds_api_covered("icehockey_other")
        assert not _sport_key_is_odds_api_covered("basketball_other")

    def test_the_boundary_calls_the_resolver(self):
        """The unit tests above grade the predicate; this is the one thing they
        cannot see — that `_create_event_from_prediction_market` actually
        consults it before minting. Without it, deleting the call site leaves
        every test green.

        READ AS A TREE, NOT AS TEXT, and both halves of that are load-bearing —
        each was written the cheap way first and each survived its mutation:

        * `"covered_league_for_matchup" in source` passed while the real call
          was replaced by `covered_league = None`, because the explanatory
          COMMENT above the call still carried the name. The scan was grading
          its own prose.
        * `"return None" in <text after the call>` then passed while the
          refusal was neutered to `if False and covered_league:`, because the
          function has later `return None`s of its own. A substring cannot tell
          a live branch from a dead one.

        So this asserts the SHAPE: the awaited call, and that the very next
        statement is an `if` on exactly that variable which returns None.
        """
        import ast
        import inspect

        from app.tasks import prediction_market_matching as task_module

        tree = ast.parse(inspect.getsource(
            task_module._create_event_from_prediction_market
        ))
        body = tree.body[0].body

        call_index = target = None
        for index, node in enumerate(body):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Await)
                and isinstance(node.value.value, ast.Call)
                and isinstance(node.value.value.func, ast.Name)
                and node.value.value.func.id == "covered_league_for_matchup"
            ):
                call_index, target = index, node.targets[0].id
                break

        assert call_index is not None, (
            "the auto-create boundary no longer AWAITS the #5544 refusal"
        )

        guard = body[call_index + 1]
        assert isinstance(guard, ast.If), (
            "the #5544 resolver's verdict is not tested by the next statement"
        )
        assert (
            isinstance(guard.test, ast.Name) and guard.test.id == target
        ), (
            "the statement after the #5544 call does not branch on its result "
            f"(branches on {ast.dump(guard.test)[:80]})"
        )
        assert any(
            isinstance(stmt, ast.Return)
            and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is None
            for stmt in guard.body
        ), "the #5544 refusal branch does not return None — it does not refuse"

    def test_the_db_refusal_comes_after_every_pure_one(self):
        """#5544's guard is the only refusal on this path that reads the DB, and
        it must stay last.

        Written first at the top of the refusal stack, it broke
        `test_unanchored_create_loop_2020` and `test_invented_start_time_4242`,
        which pass `session=None` precisely to prove their own predicates are
        reached before anything is read or written — five reds, and correctly
        so. It also cost a round trip on every market those two refuse for free.

        The ordering is the contract, so the ordering is asserted.
        """
        import ast
        import inspect

        from app.tasks import prediction_market_matching as task_module

        source = inspect.getsource(
            task_module._create_event_from_prediction_market
        )
        tree = ast.parse(source)

        offsets = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                offsets.setdefault(node.func.id, node.lineno)

        for pure in ("auto_create_time_is_invented", "auto_create_self_refutes"):
            assert pure in offsets, f"{pure} is no longer called at the boundary"
            assert offsets[pure] < offsets["covered_league_for_matchup"], (
                f"#5544's DB refusal now runs BEFORE {pure}, which is pure and "
                "is tested with session=None"
            )
