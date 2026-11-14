"""#12519: merging two team rows never deletes one of the team's other names.

THE DEFECT (found by Builder B on #1511, Nov 10). After a merge, both the
admin route (``admin_team_clusters``) and the rail (``team_merge``) ran a
"scoped mapping dedup":

    DELETE FROM team_identity_mapping a USING team_identity_mapping b
    WHERE a.id > b.id AND a.team_id = b.team_id AND a.source = b.source
      AND a.source_id IS NOT DISTINCT FROM b.source_id AND a.team_id = :tid

Two rows whose ``source_id`` is NULL compare as equal there, so every NULL-id
name one source holds for the team collapsed to the oldest row, whatever the
names said. In Alex's 114 approved merges that is 43 groups across 30 clusters
losing 112 distinct names: Montreal would keep Polymarket's "Lightning" and lose
"Canadiens"; St Louis would keep Kalshi's "Stars" and lose "St. Louis".

THE RULE NOW (one statement, shared by both paths):
  * a row with a source id is a duplicate only of an older row with the SAME id;
  * a row with no source id is a duplicate only of an older exact repeat: same
    source, same name, same sport key;
  * a distinct name is never deleted.

The database half runs the statement against a real Postgres (temp table, so
nothing else is touched) and is skipped where ``SEARCH_TEST_DATABASE_URL`` is
unset, as CI's database-integration job sets it.
"""

from __future__ import annotations

import importlib
import os

import pytest

team_merge = importlib.import_module("app.utils.team_merge")
clusters = importlib.import_module("app.routes.admin_team_clusters")

#: The statement both paths ran before #12519, kept verbatim as the control: the
#: same rig must show it deleting a distinct name, or the fixed-statement tests
#: below would prove nothing.
OLD_DEDUP_SQL = (
    "DELETE FROM team_identity_mapping a USING team_identity_mapping b "
    "WHERE a.id > b.id AND a.team_id = b.team_id AND a.source = b.source "
    "AND a.source_id IS NOT DISTINCT FROM b.source_id AND a.team_id = :tid"
)


class TestOneStatementForBothPaths:
    def test_the_rail_owns_the_statement(self):
        assert hasattr(team_merge, "MAPPING_DEDUP_SQL")

    def test_the_route_runs_the_rails_statement_character_for_character(self):
        # The route writes the statement out (the destructive-handler census
        # reads handler text), so pin its literal to the rail's constant.
        import ast

        tree = ast.parse(open(clusters.__file__).read())
        literals = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value.startswith("DELETE FROM team_identity_mapping")
        ]
        assert literals == [team_merge.MAPPING_DEDUP_SQL]

    @pytest.mark.parametrize("module", [team_merge, clusters], ids=["rail", "route"])
    def test_neither_file_keeps_the_null_collapsing_comparison(self, module):
        src = open(module.__file__).read()
        assert "a.source_id IS NOT DISTINCT FROM b.source_id" not in src

    def test_the_statement_is_scoped_to_one_team(self):
        assert "a.team_id = :tid" in team_merge.MAPPING_DEDUP_SQL

    def test_the_source_id_branch_also_matches_the_sport(self):
        # Fable, Nov 10 (from Builder B's read on #12534): the resolver's key and
        # the production unique index both include the sport key, so one source
        # id under two sports is two rows, not a duplicate.
        sql = team_merge.MAPPING_DEDUP_SQL
        id_branch = sql[sql.index("(a.source_id IS NOT NULL"):sql.index(" OR (a.source_id IS NULL")]
        assert "a.sport_key IS NOT DISTINCT FROM b.sport_key" in id_branch


DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

# (id, team_id, source, source_id, source_name, sport_key). Team 1 is the kept
# team after a merge; team 2 is another team the statement must not touch.
ROWS = [
    (1, 1, "polymarket", None, "Lightning", "icehockey_nhl"),
    (2, 1, "polymarket", None, "Canadiens", "icehockey_nhl"),
    (3, 1, "polymarket", None, "Canadiens", "icehockey_nhl"),       # exact repeat of 2
    (4, 1, "polymarket", None, "Canadiens", "icehockey_ahl"),       # same name, other sport
    (5, 1, "kalshi", "MTL", "Montreal", "icehockey_nhl"),
    (6, 1, "kalshi", "MTL", "Montreal Canadiens", "icehockey_nhl"),  # same id as 5
    (7, 1, "kalshi", None, "Montreal", "icehockey_nhl"),             # no id: not 5's twin
    (8, 1, "odds_api", None, None, "icehockey_nhl"),
    (9, 1, "odds_api", None, None, "icehockey_nhl"),                 # exact repeat (NULL name)
    (10, 2, "polymarket", None, "Lightning", "icehockey_nhl"),
    (11, 2, "polymarket", None, "Lightning", "icehockey_nhl"),       # repeat, but team 2
    (12, 1, "kalshi", "MTL", "Montreal", "icehockey_ahl"),           # 5's id, other sport
]


@pytest.fixture
async def mapping():
    if not DB_URL:
        pytest.skip("SEARCH_TEST_DATABASE_URL unset")
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        await conn.execute(text(
            "CREATE TEMP TABLE team_identity_mapping ("
            " id integer PRIMARY KEY, team_id integer NOT NULL, source text NOT NULL,"
            " source_id text, source_name text, sport_key text)"
        ))
        for row in ROWS:
            await conn.execute(text(
                "INSERT INTO team_identity_mapping VALUES (:i, :t, :s, :sid, :n, :k)"
            ), dict(zip(("i", "t", "s", "sid", "n", "k"), row)))

        async def run(sql: str) -> set[int]:
            await conn.execute(text(sql), {"tid": 1})
            return set((await conn.execute(
                text("SELECT id FROM team_identity_mapping")
            )).scalars())

        yield run
        await conn.rollback()
    await engine.dispose()


class TestTheDedupOnARealDatabase:
    async def test_the_old_statement_deleted_a_distinct_name(self, mapping):
        # Control: every Polymarket NULL-id name collapses into the oldest,
        # "Lightning", so the team loses "Canadiens" in both sports.
        left = await mapping(OLD_DEDUP_SQL)
        assert 1 in left
        assert not {2, 3, 4} & left

    async def test_two_null_id_names_from_one_source_both_survive(self, mapping):
        left = await mapping(team_merge.MAPPING_DEDUP_SQL)
        assert {1, 2} <= left  # "Lightning" and "Canadiens"

    async def test_an_exact_repeat_collapses_to_the_oldest(self, mapping):
        left = await mapping(team_merge.MAPPING_DEDUP_SQL)
        assert 3 not in left and 2 in left
        assert 9 not in left and 8 in left  # NULL name repeats too

    async def test_the_same_name_in_another_sport_is_not_a_repeat(self, mapping):
        left = await mapping(team_merge.MAPPING_DEDUP_SQL)
        assert 4 in left

    async def test_a_repeated_source_id_still_collapses(self, mapping):
        left = await mapping(team_merge.MAPPING_DEDUP_SQL)
        assert 5 in left and 6 not in left

    async def test_the_same_source_id_in_another_sport_is_not_a_twin(self, mapping):
        left = await mapping(team_merge.MAPPING_DEDUP_SQL)
        assert 12 in left

    async def test_a_row_without_an_id_is_not_an_id_rows_twin(self, mapping):
        left = await mapping(team_merge.MAPPING_DEDUP_SQL)
        assert 7 in left

    async def test_another_team_is_untouched(self, mapping):
        left = await mapping(team_merge.MAPPING_DEDUP_SQL)
        assert {10, 11} <= left

    async def test_exactly_the_three_duplicates_go(self, mapping):
        left = await mapping(team_merge.MAPPING_DEDUP_SQL)
        assert {r[0] for r in ROWS} - left == {3, 6, 9}
