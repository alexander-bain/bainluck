"""#12529: the team-logo lookup loads only the columns its snapshot keeps.

`_enriched_teams_stmt` loaded every `teams` column: 622,434 calls, mean 577 ms,
the heaviest statement in `pg_stat_statements` by total time on Nov 10, and
`roster_players` was 1,048 kB of the 1,536 kB it read across 1,809 branded
teams. `_snapshot_team` never reads it.
"""
import ast
import inspect
import textwrap

from sqlalchemy.dialects import postgresql

from app.routes import events


def _snapshot_reads() -> set[str]:
    fn = ast.parse(textwrap.dedent(inspect.getsource(events._snapshot_team))).body[0]
    reads = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "team":
            reads.add(node.attr)
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "getattr"
                and isinstance(node.args[0], ast.Name) and node.args[0].id == "team"
                and isinstance(node.args[1], ast.Constant)):
            reads.add(node.args[1].value)
    return reads


def test_every_column_the_snapshot_reads_is_loaded():
    loaded = {c.key for c in events.TEAM_LOOKUP_COLUMNS}
    missing = _snapshot_reads() - loaded
    assert not missing, f"_snapshot_team reads {missing} but the lookup doesn't load them"


def test_nothing_else_is_loaded():
    assert {c.key for c in events.TEAM_LOOKUP_COLUMNS} == _snapshot_reads()


def _sql() -> str:
    return str(events._enriched_teams_stmt().compile(dialect=postgresql.dialect()))


def test_the_heavy_unused_columns_are_not_selected():
    sql = _sql()
    for unused in ("roster_players", "teams.location", "teams.logo_url,", "teams.external_id", "statpal_team_id"):
        assert unused not in sql, unused


def test_the_population_and_the_outer_join_are_unchanged():
    sql = _sql()
    assert "LEFT OUTER JOIN sports ON sports.id = teams.sport_id" in sql
    assert "teams.primary_color IS NOT NULL OR teams.logo_url_small IS NOT NULL" in sql
    assert "sports.key" in sql
