"""#7021 — the twin drain's candidate SELECT, EXECUTED against a real PostgreSQL.

## Why a mock session cannot gate this change

The change is a SQL predicate: three name arms that used to compare
``LOWER(x)`` and now compare ``REGEXP_REPLACE(LOWER(x), '[^a-z0-9]', '', 'g')``.
Every property worth asserting about it belongs to PostgreSQL —

* whether the composed 40-line statement is even legal (the drain builds it by
  string concatenation from two helpers, and
  ``test_polymarket_resolved_candidate_sql_pg.py`` exists because that shape
  shipped a ``SELECT DISTINCT`` / ``ORDER BY`` syntax error that 23 unit guards
  passed straight over);
* which rows the regex actually joins;
* and whether the SQL fold agrees with the Python fold, which is the drift this
  pair of functions is built to prevent and which no single-form test can see.

The unit guards in ``tests/test_twin_drain_punctuation_and_survival_7021_7191.py``
own the judgement — what ``matchup_agrees`` permits, what the drain does with a
failing write. This owns the half that is the database's.

## The statement is imported, never retyped

Every arm runs ``duplicate_pairs_sql()``. A retyped copy of the query would pass
while the shipped one was broken, which is the entire failure mode.

Opt-in on ``SEARCH_TEST_DATABASE_URL``; runs in the ``search-recall`` CI job,
whose "Verify the gate is actually armed" step exists so a skipped gate cannot
read as a passing one. There is no local Postgres in the agent sandbox.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.tasks.sports import duplicate_pairs_sql
from app.utils.event_merge_invariant import fold_participant_name, folded_name_sql

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7021 twin "
            "candidate-SQL gate (CI job: search-recall)"
        ),
    ),
]

#: A private schema for the same reason `poly_sweep_gate_2637` has one: this job
#: shares one database with gates that build the real schema from
#: `Base.metadata.create_all`, and a narrow impostor `events` left in `public`
#: would break a later step. A schema on the `search_path` resolves first and
#: tears down whole.
_GATE_SCHEMA = "twin_fold_gate_7021"


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def seeded(pg_session):
    """Five pairs, each chosen against a verdict the predicate must reach.

    Times are relative to ``now()`` because the shipped query carries its own
    ``commence_time > NOW() - INTERVAL '30 days'``; a fixed date would age out
    of the window and silently empty every arm.
    """
    await pg_session.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await pg_session.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
    await pg_session.execute(text(f"SET search_path TO {_GATE_SCHEMA}, public"))
    await pg_session.execute(
        text(
            """
            CREATE TABLE events (
                id bigint PRIMARY KEY,
                sport_id integer NOT NULL,
                commence_time timestamptz NOT NULL,
                status varchar(20) NOT NULL,
                home_team_name varchar(200),
                away_team_name varchar(200),
                home_team_normalized varchar(200),
                away_team_normalized varchar(200),
                external_id varchar(200),
                espn_id varchar(50),
                statpal_fixture_id varchar(50),
                commence_time_source varchar(50),
                statpal_end_time timestamptz,
                home_team_id integer,
                away_team_id integer
            )
            """
        )
    )
    # The EXISTS sub-select in the shipped query reads this table; it must be
    # present and resolvable or the statement cannot plan.
    await pg_session.execute(
        text("CREATE TABLE odds_snapshots (id serial PRIMARY KEY, event_id bigint)")
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO events
                (id, sport_id, commence_time, status, home_team_name,
                 away_team_name, external_id, espn_id, statpal_fixture_id,
                 commence_time_source)
            VALUES
                -- (1) THE SPECIMEN. StatPal's typo vs the ESPN spelling, one
                -- shared statpal_fixture_id. Production 15310833 / 15314166,
                -- including their contradictory states: the copy a reader
                -- cannot merge away is frozen `suspended` while its twin has
                -- gone `completed`.
                (1, 10, now() - interval '1 day', 'suspended',
                 'St.Louis Cardinals', 'Washington Nationals',
                 NULL, NULL, '365774', 'statpal'),
                (2, 10, now() - interval '1 day', 'completed',
                 'St. Louis Cardinals', 'Washington Nationals',
                 'odds-card', '401816991', '365774', 'espn'),

                -- (2) A hyphen. Production 15297786 / 15311919.
                (3, 20, now() - interval '2 days', 'completed', 'Brest',
                 'Paris Saint Germain', NULL, NULL, '77001', 'statpal'),
                (4, 20, now() - interval '2 days', 'completed', 'Brest',
                 'Paris Saint-Germain', 'odds-psg', NULL, '77001', 'espn'),

                -- (3) An ALIAS, not punctuation. Production Getafe/Getafe CF:
                -- shares an id, and folding must NOT reach it.
                (5, 20, now() - interval '3 days', 'scheduled', 'Getafe',
                 'Malaga', NULL, NULL, '77002', 'statpal'),
                (6, 20, now() - interval '3 days', 'scheduled', 'Getafe CF',
                 'Málaga CF', 'odds-get', NULL, '77002', 'espn'),

                -- (4) A punctuation twin with NO shared provider id. Ruling 048
                -- arm A is untouched by #7021 and must still refuse it.
                (7, 10, now() - interval '4 days', 'completed',
                 'St.Louis Cardinals', 'Chicago White Sox',
                 NULL, NULL, 'anchor-x', 'statpal'),
                (8, 10, now() - interval '4 days', 'completed',
                 'St. Louis Cardinals', 'Chicago White Sox',
                 NULL, NULL, 'anchor-y', 'espn'),

                -- (5) Two DIFFERENT fixtures whose names hold no ASCII
                -- alphanumerics, sharing an id. Both fold to '', so without the
                -- emptiness guard every arm matches and one is deleted.
                (9, 30, now() - interval '5 days', 'completed', '横浜', '鹿島',
                 NULL, NULL, '77003', 'statpal'),
                (10, 30, now() - interval '5 days', 'completed', '浦和', '川崎',
                 'odds-jp', NULL, '77003', 'espn')
            """
        )
    )
    await pg_session.commit()
    yield pg_session
    await pg_session.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await pg_session.commit()


async def _candidate_pairs(session) -> set[tuple[int, int]]:
    """Run the SHIPPED statement and return the pairs it offers the drain."""
    rows = (await session.execute(text(duplicate_pairs_sql()))).mappings().all()
    return {(r["id_a"], r["id_b"]) for r in rows}


class TestTheShippedStatementRunsAndSelectsTheRightPairs:
    async def test_the_composed_query_is_legal_sql(self, seeded):
        """The gate the mock sessions cannot be: PostgreSQL parses and plans it."""
        await _candidate_pairs(seeded)

    async def test_the_punctuation_twins_are_candidates(self, seeded):
        pairs = await _candidate_pairs(seeded)
        assert (1, 2) in pairs, (
            "the St.Louis/St. Louis twin is still invisible to the drain — this "
            "is 10 of the 11 in-window production pairs #7021 measured"
        )
        assert (3, 4) in pairs, "the Paris Saint-Germain hyphen twin is invisible"

    async def test_an_alias_pair_is_not_a_candidate(self, seeded):
        """#7021 folds PUNCTUATION, not words.

        ``Getafe``/``Getafe CF`` shares a provider id and is one of the six
        production pairs deliberately left for an alias rail. If this arm ever
        goes green the fold has become a fuzzy matcher.
        """
        assert (5, 6) not in await _candidate_pairs(seeded)

    async def test_a_punctuation_twin_without_a_shared_id_is_not_a_candidate(
        self, seeded
    ):
        """Ruling 048 arm A, unchanged: the names agreeing is not enough."""
        assert (7, 8) not in await _candidate_pairs(seeded)

    async def test_two_unnameable_rows_are_not_joined_by_folding_to_empty(
        self, seeded
    ):
        """The emptiness guard, executed.

        Both rows fold to ``''`` in Postgres — ``[^a-z0-9]`` deletes every
        multi-byte character — so ``'' = ''`` satisfies all three arms and the
        shared id would license the delete.
        """
        assert (9, 10) not in await _candidate_pairs(seeded)


class TestThePythonAndSqlFoldsDoNotDrift:
    """The two forms are a pair, and only a database can compare them.

    ``str.isalnum()`` is Unicode-aware and ``[^a-z0-9]`` is not, so the obvious
    Python spelling of this fold disagrees with the SQL on every accented name.
    The corpus is real production team names, including the ones the drain must
    NOT merge.
    """

    CORPUS = [
        "St.Louis Cardinals", "St. Louis Cardinals", "Paris Saint-Germain",
        "Paris Saint Germain", "Málaga CF", "Malaga CF", "Atlético Madrid",
        "FSV Mainz 05", "Mainz", "D.C. United", "Gen.G", "Olympiacos B.C.",
        "Falkirk F.C.", "Estudiantes L.P.", "Virtus.pro", "横浜", "  Lazio  ",
    ]

    @pytest.mark.parametrize("name", CORPUS)
    async def test_the_sql_fold_equals_the_python_fold(self, seeded, name):
        got = await seeded.execute(
            text(f"SELECT {folded_name_sql(':name')} AS folded"), {"name": name}
        )
        assert got.scalar_one() == fold_participant_name(name), (
            f"the SQL and Python folds disagree on {name!r}: the candidate "
            "SELECT and the corroboration that licenses the DELETE would then "
            "answer differently about the same two rows"
        )
