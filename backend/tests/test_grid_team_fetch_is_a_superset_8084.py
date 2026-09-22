"""#8084 — the grid's team FETCH must be a superset of what its MATCHER can match.

A reader on `/playoffs/la-liga` saw **Atletico Madrid** at rank 3 — charted in the
odds trend, named in the "Biggest Movers" chip — rendered as bare text with no
crest and no record, between two crested clubs. Four more rows (`Racing
Santander`, `Alaves`, `Deportivo De La Coruna`, `Malaga`) were bare at the foot
of the table: 15 of 20.

THE TWO HALVES DISAGREED ABOUT DIACRITICS. `_get_team_metadata` fetched
candidates with `Team.name.ilike(f"%{name}%")` on the RAW venue name, then keyed
them with `_normalize_team_name`, which strips diacritics. ILIKE does not. So
`'%Atletico Madrid%'` never returned `Atlético Madrid` and the matcher's
tolerance was unreachable for exactly the clubs it exists for. Measured on
production 2026-09-22, the grid's own SQL:

    ILIKE '%Atletico Madrid%'        -> 0 candidate rows
    ILIKE '%Alaves%'                 -> 0
    ILIKE '%Deportivo De La Coruna%' -> 0
    ILIKE '%Malaga%'                 -> 0
    ILIKE '%Barcelona%'              -> 7   <- ASCII control; the instrument is alive

while `2199 Alavés`, `2200 Atlético Madrid` (espn 1068, record 5-1-1), `16805
Málaga` and `16809 Deportivo La Coruña` all exist. The same narrowness stranded
every ALIAS — `_secondary_claims` keys a row by its abbreviation and
`alternate_names`, but a row whose only correspondence is an alias can never be
fetched by a `name` filter.

WHAT THESE TESTS DO AND DO NOT PROVE. `Team.alternate_names` is `JSONB`, so
there is no SQLite path and a real end-to-end fetch belongs to a Postgres gate.
So the fetch half is asserted on the STATEMENT the function emits (with a
config-driven control, below) and the match half on the existing fake-row
harness. Deliberately NOT mirrored into a hand-rolled predicate evaluator: a
mirror of the SQL is the drift that deleted 70 correct verdicts under #4923, and
a fake that re-implements the filter would be testing the fake.
"""

import pytest
from sqlalchemy.dialects import postgresql

from app.routes.playoffs import _get_team_metadata


class _FakeSport:
    def __init__(self, key):
        self.key = key


class _FakeTeam:
    """Only the attributes `_get_team_metadata` reads."""

    def __init__(
        self,
        team_id,
        name,
        sport_key,
        espn_id=None,
        abbreviation=None,
        alternate_names=None,
        record=None,
    ):
        self.id = team_id
        self.name = name
        self.sport = _FakeSport(sport_key)
        self.espn_id = espn_id
        self.abbreviation = abbreviation
        self.alternate_names = list(alternate_names or [])
        self.current_record = record
        self.logo_url_small = None
        self.logo_url_large = None
        self.primary_color = None
        self.secondary_color = None
        self.standings_data = None


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _CapturingSession:
    """Returns fixed rows AND keeps the statement, so the fetch can be read."""

    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self._rows)


def _compiled(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


# --- The production specimens ----------------------------------------------


def _atletico():
    """Row 2200, as production holds it — accented name, real record."""
    return _FakeTeam(
        2200,
        "Atlético Madrid",
        "soccer_spain_la_liga",
        espn_id="1068",
        abbreviation="ATM",
        record="5-1-1",
    )


def _alaves():
    return _FakeTeam(
        2199,
        "Alavés",
        "soccer_spain_la_liga",
        espn_id="96",
        record="3-2-2",
    )


def _barcelona():
    """The ASCII control: this club was never broken."""
    return _FakeTeam(
        2206,
        "Barcelona",
        "soccer_spain_la_liga",
        espn_id="83",
        record="7-0-0",
    )


async def _lookup(rows, league_slug, names):
    session = _CapturingSession(rows)
    meta = await _get_team_metadata(session, set(names), league_slug=league_slug)
    return meta, session


# --- The fetch half ---------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_admits_the_whole_league_scope_not_just_name_substrings():
    """THE GUARD. The statement must reach rows by sport scope.

    Revert the fix and the only conditions are the per-name ILIKEs, so
    `sports.key` never appears and this fails.
    """
    _meta, session = await _lookup([_atletico()], "la-liga", {"Atletico Madrid"})
    sql = _compiled(session.statements[0])

    assert "soccer_spain_la_liga" in sql, (
        "the fetch does not reach La Liga rows by scope, so a club whose stored "
        "name differs from the venue's spelling can never be loaded:\n" + sql
    )
    # The name arm is still there — scope is an ADDITION, not a replacement,
    # because the lookup deliberately still serves out-of-scope rows when they
    # are all there is ("a preference, not a filter").
    assert "Atletico Madrid" in sql


@pytest.mark.asyncio
async def test_without_a_league_config_the_scope_clause_is_absent():
    """THE CONTROL. Proves the assertion above can fail, and that the clause is
    config-driven rather than a constant someone pasted in.

    `league_slug=""` short-circuits `get_league_config`, so `scope_keys` is
    empty and the emitted statement is exactly the pre-fix one.
    """
    _meta, session = await _lookup([_atletico()], "", {"Atletico Madrid"})
    sql = _compiled(session.statements[0])

    assert "soccer_spain_la_liga" not in sql
    assert "sports" not in sql.split("WHERE", 1)[-1]
    assert "Atletico Madrid" in sql


@pytest.mark.asyncio
async def test_the_scope_clause_names_the_leagues_own_keys_only():
    """A grid must not drag in another league's rows: EPL's scope is not
    La Liga's. Guards against widening the fetch to 'every team'."""
    _meta, session = await _lookup([_atletico()], "epl", {"Hull City"})
    sql = _compiled(session.statements[0])

    assert "soccer_epl" in sql
    assert "soccer_spain_la_liga" not in sql


# --- The match half ---------------------------------------------------------


@pytest.mark.asyncio
async def test_an_ascii_venue_name_keys_the_accented_row_once_it_is_loaded():
    """The premise of the diagnosis: the matcher was never the broken half.

    This passes before and after the fix — that is the point. It pins that
    `_normalize_team_name` folds `Atlético` to `atletico`, so the ONLY thing
    standing between the reader and the crest was the fetch.
    """
    meta, _session = await _lookup([_atletico()], "la-liga", {"Atletico Madrid"})

    row = meta.get("atletico madrid")
    assert row is not None, "the accented row did not key under the ASCII name"
    assert row["team_id"] == 2200
    assert row["record"] == "5-1-1"
    assert row["espn_id"] == "1068"


@pytest.mark.asyncio
async def test_every_bare_la_liga_row_resolves_once_loaded():
    """The five specimens the reader saw, as one assertion."""
    rows = [_atletico(), _alaves(), _barcelona()]
    meta, _session = await _lookup(
        rows, "la-liga", {"Atletico Madrid", "Alaves", "Barcelona"}
    )

    assert meta["atletico madrid"]["record"] == "5-1-1"
    assert meta["alaves"]["record"] == "3-2-2"
    # The control never moved.
    assert meta["barcelona"]["record"] == "7-0-0"


# --- Widening the FETCH must not widen the MATCH ----------------------------


@pytest.mark.asyncio
async def test_extra_in_scope_rows_cannot_take_another_clubs_own_name():
    """#7727's refusal must survive the wider fetch.

    This is the direction that matters: a bare row is a far smaller harm than a
    crest belonging to someone else, and the fix hands the matcher MORE rows
    than it used to see. `Impostor FC` aliases Atlético's own name and has the
    higher id, so last-one-wins would hand it the key if `_alias_may_claim` were
    not still consulted. Both rows are in scope and carry different espn_ids,
    which is exactly the anchored refusal.
    """
    impostor = _FakeTeam(
        99999,
        "Impostor FC",
        "soccer_spain_la_liga",
        espn_id="424242",
        alternate_names=["Atlético Madrid", "Atletico Madrid"],
        record="0-0-0",
    )
    meta, _session = await _lookup(
        [_atletico(), impostor], "la-liga", {"Atletico Madrid"}
    )

    assert (
        meta["atletico madrid"]["team_id"] == 2200
    ), "an alias took another club's own name — #7727 has regressed"
    assert meta["atletico madrid"]["record"] == "5-1-1"


@pytest.mark.asyncio
async def test_a_second_row_for_the_same_club_still_wins_by_anchor():
    """The other direction of #7727: two rows, one club, one espn_id — the alias
    SHOULD be allowed to bind. A fix that made the refusal blanket would break
    the `Bournemouth`/`AFC Bournemouth` case the grid relies on.
    """
    second = _FakeTeam(
        30001,
        "Club Atlético de Madrid",
        "soccer_spain_la_liga",
        espn_id="1068",
        alternate_names=["Atletico Madrid"],
        record="5-1-1",
    )
    meta, _session = await _lookup(
        [_atletico(), second], "la-liga", {"Atletico Madrid"}
    )

    assert meta["atletico madrid"]["espn_id"] == "1068"
    assert meta["atletico madrid"]["record"] == "5-1-1"
