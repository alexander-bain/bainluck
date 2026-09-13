"""THE FRONT DOOR, SECOND HALF: `yank` GETS ITS GAME. #5773.

═══ WHY THIS SUITE EXISTS ═══

Ship 7's own acceptance sentence, typed against production `api.bainluck.com` on
2026-09-12 (22:4xZ from the iPhone by native/138, reproduced 23:0xZ here):

    q=yank      teams 1  results 0   futures 10
    q=yanke     teams 1  results 0   futures  9
    q=yankees   teams 1  results 21  futures 10  -> fine

**"The team first, its game next" has no second half.** `_event_name_match` ANDs
an FTS whole-word arm onto the ILIKE, and `yank` is not a lexeme of `yankees`
(which stems to `yanke`), so the event rail serves nothing. Measured the same
minute, `dodg` -> Los Angeles Dodgers and `phil` -> five Philadelphia clubs do it
too: the team resolves, the games do not.

═══ THE HALF THIS SUITE DOES *NOT* COVER, AND WHY ═══

#5773 also reported three novelty markets — `Yankiel Rivera`, `Priyanka Gandhi
Vadra`, `Priyanka` — reached through the futures OUTCOME arm, which carries no
word test. That half was built, MEASURED, and **descoped on the measurement**:
production the same night says an AND-ed word test there takes `lebro` from 367
markets to 0 and `ohtan` from 987 to 0, deleting every market about a player a
reader is four letters into naming. The event rail can accept that loss because
the teams registry rescues it; an outcome has no registry. The numbers live in
`routes/events.py` beside the arm, and
`test_search_latency_contract.py::test_the_outcome_arm_is_deliberately_not_word_tested`
— which demanded exactly this before/after — stays green and unedited.

═══ THE REFUSALS THIS SUITE MUST NOT BREAK ═══

🔴 **Prefix matching is refused for the EVENT predicate, in writing, naming this
exact query.** `_event_name_match`'s LAT-P037 docstring rules out `yank:*`
because it also matches `fed:*` -> `Federico` — the 25 rows of minor-tour tennis
LAT-P033/LAT-P034 closed. #5773 does NOT lift it. The repair reuses the club the
TEAMS rail already resolved (#4126's prefix arm lives there, behind the
individual-sport strip), which is why `fed` and `apple` still resolve nothing.

🔴 **A minimum-length constant is the other repair LAT-P034 measured and
rejected** (it lets `apple` -> `Appleton` back in). Not used here either.

🔴 **The event recall is deliberately FTS-free** (LAT-P002/#1494 (1c): no
tsvector index exists on those columns, so one unindexable arm forces a seq
scan). The rescue arm is plain ILIKE on a resolved name.

`TestTheRefusalsStillHold` is the control class and is the most important one in
this file — it is what a future widening trips over.

═══ WHAT IS TESTED, AND WHAT CANNOT BE ═══

These are the PURE halves — the compiled SQL and the row reduction — which need
no Postgres and so run in every CI job. `TestTheRouteIsWiredToThem` reads the
route's own AST rather than its behaviour, because the wiring (does the rescue
run BEFORE the trigram guess, and does a resolved club suppress it) is a
statement-ordering property that no pure call can observe. End-to-end recall
belongs to the `search-recall` job and the gold set.
"""

import ast
import pathlib
import re
import types

import pytest
from sqlalchemy.dialects import postgresql

from app.routes.events import (
    _event_name_match,
    _futures_name_match_term,
    _rescue_teams_from_rows,
    _resolved_team_event_filter,
    _RESOLVED_TEAM_RESCUE_CAP,
)


def _sql(clause) -> str:
    """Compile to Postgres SQL with literals inlined, so an assertion can read
    the actual tsquery string rather than a bind marker."""
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _arm_pairs(sql: str) -> list[tuple[str, str]]:
    """Every `(sport_key, club)` the compiled filter actually pairs together.

    Reading the two as a PAIR is the point: a filter that flattened its scopes
    would still contain both keys and both names, and only the pairing tells
    them apart."""
    return re.findall(
        r"sports\.key = '([^']+)' AND \(events\.home_team_name ILIKE '%%([^%]+)%%'",
        sql,
    )


def _row(name: str, sport_key: str | None):
    """The shape `select(Team.name, Sport.key.label('sport_key'))` returns."""
    return types.SimpleNamespace(name=name, sport_key=sport_key)


# ─────────────────────────────────────────────────────────────────────────────
# HALF A — which clubs a rescue may speak for
# ─────────────────────────────────────────────────────────────────────────────


class TestTheClubsTheRescueMaySpeakFor:
    """`_rescue_teams_from_rows` is where the safety property lives."""

    def test_a_real_club_survives(self):
        assert _rescue_teams_from_rows([_row("New York Yankees", "baseball_mlb")]) == [
            ("New York Yankees", "baseball_mlb")
        ]

    @pytest.mark.parametrize(
        "sport_key",
        ["tennis_atp", "tennis_wta_italian_open", "mma_mixed_martial_arts",
         "boxing_boxing", "golf_pga_championship"],
    )
    def test_an_individual_sport_row_is_stripped(self, sport_key):
        """THE SAFETY PROPERTY. Tennis players, MMA fighters, golfers and boxers
        are modelled as "teams" by the Odds API and are exactly the population
        `fed` -> `Federico` was made of. If this strip ever stops running, the
        rescue reopens LAT-P033/LAT-P034 through the prefix arm it reuses."""
        assert _rescue_teams_from_rows([_row("Federico Coria", sport_key)]) == []

    def test_a_fed_shaped_result_builds_no_arm_at_all(self):
        """Measured on production 2026-09-12 23:0xZ: `fed` and `apple` resolve no
        surviving team, so the reader keeps the honest empty rail. The rescue is
        safe because of the DATA the registry holds, not because of a constant."""
        rows = [_row("Federico Coria", "tennis_atp"), _row("Fedorova", "tennis_wta")]
        assert _rescue_teams_from_rows(rows) == []

    def test_a_row_with_no_sport_key_is_dropped(self):
        """An unscoped arm is the cross-league fan-out the sport key exists to
        prevent — bare `Patriots` reaching a Caribbean Premier League side."""
        assert _rescue_teams_from_rows([_row("New York Yankees", None)]) == []

    def test_repeats_collapse(self):
        rows = [_row("Boston Red Sox", "baseball_mlb")] * 3
        assert _rescue_teams_from_rows(rows) == [("Boston Red Sox", "baseball_mlb")]

    def test_the_same_name_in_two_sports_is_two_clubs(self):
        """Dedupe is on (name, sport), not on name: `Philadelphia` clubs share a
        city and nothing else, and a club is identified by both."""
        rows = [_row("Philadelphia Union", "soccer_usa_mls"),
                _row("Philadelphia Union", "soccer_usa_usl")]
        assert len(_rescue_teams_from_rows(rows)) == 2

    def test_the_cap_is_five_and_it_bites(self):
        """`phil` is the specimen that needs more than one club — Phillies,
        Flyers, 76ers, Eagles and Union all resolve and all five are the right
        answer. Five is what the teams bucket itself prints, so a sixth arm would
        search for a club the reader is not being shown."""
        assert _RESOLVED_TEAM_RESCUE_CAP == 5
        rows = [_row(f"Club {i}", "baseball_mlb") for i in range(9)]
        assert len(_rescue_teams_from_rows(rows)) == 5
        assert _rescue_teams_from_rows(rows)[-1] == ("Club 4", "baseball_mlb")

    def test_rank_order_is_preserved(self):
        """The rows arrive ordered by `_team_search_rank` — the same ranking the
        teams bucket prints. Reordering them here would make the rescue speak for
        a different five than the page shows."""
        rows = [_row("A", "baseball_mlb"), _row("B", "icehockey_nhl"),
                _row("C", "basketball_nba")]
        assert [n for n, _ in _rescue_teams_from_rows(rows)] == ["A", "B", "C"]

    def test_the_strip_runs_before_the_cap_not_after(self):
        """Order of operations, and it decides whether the rescue works at all: a
        cap applied first would spend all five slots on tennis players and leave
        the one real club unreachable. Six individual-sport rows ahead of the
        Yankees is the shape `yank` actually returns from a 25-row candidate
        window."""
        rows = [_row(f"Player {i}", "tennis_atp") for i in range(6)]
        rows.append(_row("New York Yankees", "baseball_mlb"))
        assert _rescue_teams_from_rows(rows) == [("New York Yankees", "baseball_mlb")]


class TestTheRescueArmItself:
    """`_resolved_team_event_filter` — what the clubs compile into."""

    def test_it_matches_home_and_away(self):
        sql = _sql(_resolved_team_event_filter([("New York Yankees", "baseball_mlb")]))
        assert "events.home_team_name ILIKE '%%New York Yankees%%'" in sql
        assert "events.away_team_name ILIKE '%%New York Yankees%%'" in sql

    def test_each_club_carries_its_own_sport(self):
        """NOT one shared scope. Event team names are the words venues print, so
        a club token loose in another league is a wrong answer, and a single
        OR-ed scope over five clubs would let every club match every sport.

        Asserted as PAIRS, not as "the key appears somewhere": every arm's own
        `sports.key` has to sit with that arm's own club, which is the property
        a flattened scope would break while still containing both keys."""
        sql = _sql(_resolved_team_event_filter([
            ("Philadelphia Phillies", "baseball_mlb"),
            ("Philadelphia Flyers", "icehockey_nhl"),
        ]))
        pairs = _arm_pairs(sql)
        assert pairs == [
            ("baseball_mlb", "Philadelphia Phillies"),
            ("icehockey_nhl", "Philadelphia Flyers"),
        ]

    def test_the_event_predicate_stays_fts_free(self):
        """LAT-P002/#1494 (1c): no tsvector index exists on the event name
        columns, so one FTS arm in this predicate forces a seq scan of `events`.
        The rescue buys its precision from the TEAMS table, never from a tsquery
        here."""
        sql = _sql(_resolved_team_event_filter([
            ("New York Yankees", "baseball_mlb"),
        ]))
        assert "tsquery" not in sql
        assert "to_tsvector" not in sql

    def test_five_clubs_make_five_arms(self):
        sql = _sql(_resolved_team_event_filter([
            ("Philadelphia Phillies", "baseball_mlb"),
            ("Philadelphia Flyers", "icehockey_nhl"),
            ("Philadelphia 76ers", "basketball_nba"),
            ("Philadelphia Eagles", "americanfootball_nfl"),
            ("Philadelphia Union", "soccer_usa_mls"),
        ]))
        assert sql.count("home_team_name ILIKE") == 5
        for key in ("baseball_mlb", "icehockey_nhl", "basketball_nba",
                    "americanfootball_nfl", "soccer_usa_mls"):
            assert f"sports.key = '{key}'" in sql


# ─────────────────────────────────────────────────────────────────────────────
# THE CONTROL CLASS
# ─────────────────────────────────────────────────────────────────────────────


class TestTheRefusalsStillHold:
    """The most important class in this file. #5773 must not have widened the
    arms LAT-P033/LAT-P034/LAT-P037 narrowed on purpose."""

    def test_the_event_name_arm_got_no_prefix_tsquery(self):
        """`yank:*` on the event predicate would "fix" this issue and reopen
        `fed` -> `Federico` in the same line. The rescue exists precisely so this
        does not have to happen."""
        sql = _sql(_event_name_match("yank", None))
        assert ":*" not in sql
        assert "to_tsquery('english', 'yank:*')" not in sql

    def test_the_event_name_arm_still_ands_its_word_test(self):
        """The AND is LAT-P034's judgment. A rescue is not a licence to loosen
        the arm it rescues."""
        sql = _sql(_event_name_match("yank", None))
        assert "ILIKE" in sql and "websearch_to_tsquery" in sql
        assert "numnode" in sql

    def test_the_futures_name_arm_is_untouched(self):
        """#5773 changed the OUTCOME arm. Its sibling must compile exactly as it
        did — same three parts, no prefix."""
        sql = _sql(_futures_name_match_term("yank", None))
        assert "ILIKE" in sql and "websearch_to_tsquery" in sql and "numnode" in sql
        assert ":*" not in sql

    def test_no_minimum_length_constant_was_introduced(self):
        """The other repair LAT-P034 measured and rejected: a length floor lets
        `apple` -> `Appleton` back in. The rescue's only constant is a CAP on how
        many resolved clubs may speak, which is not a length test."""
        source = pathlib.Path(
            _event_name_match.__code__.co_filename
        ).read_text()
        rescue = source[source.index("# #5773 — THE RESOLVED-TEAM RESCUE ARM"):]
        rescue = rescue[:rescue.index("# #4809 — a query that resolved")]
        assert "len(term)" not in rescue
        assert "MIN_" not in rescue


# ─────────────────────────────────────────────────────────────────────────────
# WIRING — properties no pure call can observe
# ─────────────────────────────────────────────────────────────────────────────


def _search_events_ast() -> ast.FunctionDef:
    source = pathlib.Path(_event_name_match.__code__.co_filename).read_text()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "search_events":
            return node
    raise AssertionError("search_events not found")


def _fuzzy_fallback_if(fn: ast.AsyncFunctionDef) -> ast.If:
    """The trigram "did you mean" branch, found by the two conjuncts that have
    always been its signature rather than by a line number."""
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
        if {"had_substring_match", "_event_nickname_arms"} <= names:
            return node
    raise AssertionError("the fuzzy fallback branch is not recognisable any more")


class TestTheRouteIsWiredToThem:

    def test_a_resolved_club_suppresses_the_trigram_guess(self):
        """THE SECOND HALF OF THE SHIP, and not a tidy-up. The rescue replaces
        `query` only when the resolved clubs actually have games in the window; a
        bye week, an off-season or a narrow `days_back` leaves the count at 0
        with the club still positively identified — and that is exactly when the
        trigram would answer `yank` with `Petr Yan`'s fights (sim 0.273,
        measured). #4809 made this call for `niners` -> `UTEP Miners`; this is
        the same call on the same grounds."""
        names = {
            n.id
            for n in ast.walk(_fuzzy_fallback_if(_search_events_ast()).test)
            if isinstance(n, ast.Name)
        }
        assert "_resolved_teams" in names

    def test_the_rescue_runs_before_the_guess(self):
        """Knowing what `yank` names is strictly better than guessing its nearest
        spelling, so the registry is asked first. Reversed, the trigram would
        have already replaced `query` and `total_count` and the rescue could
        never fire."""
        fn = _search_events_ast()
        fuzzy_line = _fuzzy_fallback_if(fn).lineno
        rescue_lines = [
            node.lineno
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_rescue_teams_from_rows"
        ]
        assert rescue_lines, "the rescue is not called from the route at all"
        assert max(rescue_lines) < fuzzy_line

    def test_the_rescue_reuses_the_shared_scope_list(self):
        """#2263's proven-duplicate clause and #4794's blank-card clause were
        both left behind once by a path that hand-rolled its conditions. The
        rescue takes `event_scope_conditions` whole, so it cannot happen a third
        time here."""
        source = pathlib.Path(_event_name_match.__code__.co_filename).read_text()
        block = source[source.index("_rescue_conditions = ["):]
        block = block[:block.index("]")]
        assert "*event_scope_conditions" in block

    def test_the_rescue_counts_before_it_replaces_the_query(self):
        """A rail that is still empty must leave the primary statement exactly as
        it was — otherwise a zero-row rescue would silently become the answer."""
        source = pathlib.Path(_event_name_match.__code__.co_filename).read_text()
        block = source[source.index("_rescue_conditions = ["):]
        block = block[:block.index("logger.info(")]
        assert block.index("_rescue_count = _rescue_count_r.scalar()") < block.index(
            "if _rescue_count:"
        )
        assert block.index("if _rescue_count:") < block.index("query = (")
