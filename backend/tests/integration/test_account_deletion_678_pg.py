"""#678 — account deletion, measured on real PostgreSQL.

App Review rejected version 1.0(7) on 2026-05-25 under Guideline 5.1.1(v). The
iOS half of that (the route to deletion was hidden from any account that had
not finished onboarding) is gated in `BainLuckTests`. This file gates the half
that no unit test could see: whether ``DELETE /api/auth/me`` actually deletes.

## Why this cannot be a unit test

`tests/integration/test_route_auth.py::test_delete_me_authenticated` has passed
throughout. It asserts ``mock_db.delete.assert_called_once_with(user)`` — a
mock session records the call and returns. Every way the endpoint was broken is
a way a mock cannot see:

* ``User.favorites`` / ``.preferences`` / ``.pins`` declare no delete cascade,
  so the ORM's cascade emits ``UPDATE ... SET user_id = NULL`` against a NOT
  NULL column;
* ``device_tokens``, ``oscars_pool_members`` and ``prediction_challenges`` hold
  a NO ACTION foreign key to ``users.id`` (read from `pg_constraint` on
  production, 2026-09-14) that the ORM never loads, so PostgreSQL refuses the
  DELETE;
* ``user_predictions``, ``user_seen_markets``, ``discover_interactions``,
  ``search_query_logs`` and ``bug_reports`` carry a bare ``user_id`` integer
  with no constraint at all, so their rows simply stayed behind.

Measured against the pre-fix endpoint on this fixture: an account with
preferences, a pin or a device token could not be deleted at all (500), and an
account with predictions was deleted while its predictions remained. Every
signed-in iOS account has preferences and a device token.

## What is asserted

The three things the guideline actually asks for, plus the one thing a
too-eager fix would break:

1. the delete SUCCEEDS for an account carrying every kind of associated row;
2. the user's own rows are GONE;
3. rows kept for other people or for operations carry nothing that names the
   deleted person;
4. a second account's identical rows are UNTOUCHED.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import delete as sa_delete, select, text, update as sa_update

from app.routes.auth import _ACCOUNT_DEIDENTIFIED_ROWS, _ACCOUNT_OWNED_ROWS

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #678 account-deletion gate "
            "(CI job: search-recall)"
        ),
    ),
]

#: Only the tables this gate touches. `Base.metadata.create_all` over the whole
#: schema needs PostgreSQL 15 for a `NULLS NOT DISTINCT` index elsewhere in the
#: model, which is not this test's subject.
_TABLES = [
    "sports",
    "venues",
    "teams",
    "events",
    "futures_markets",
    "users",
    "user_preferences",
    "user_pins",
    "user_favorites",
    "device_tokens",
    "user_predictions",
    "user_seen_markets",
    "discover_interactions",
    "oscars_pools",
    "oscars_pool_members",
    "search_query_logs",
    "bug_reports",
    "prediction_challenges",
]

#: The tables whose rows are the user's own and must not survive deletion.
_OWNED_TABLES = [
    "user_preferences",
    "user_pins",
    "user_favorites",
    "device_tokens",
    "user_predictions",
    "user_seen_markets",
    "discover_interactions",
    "oscars_pool_members",
]


@pytest.fixture
async def db():
    """A real Postgres carrying the tables this gate needs.

    Deliberately NOT `drop_all` + `create_all`, which is what the sibling gates
    in this CI job do. They reset the WHOLE schema; this file needs a subset,
    and dropping a subset fails once the siblings have run — `events`,
    `futures_markets` and `teams` are referenced by a dozen tables outside it,
    so PostgreSQL refuses the drop. (Green locally against a fresh database,
    red in CI, which is the whole reason the job runs these in one database.)

    So: create what is missing, destroy nothing, and make every fixture row
    unique per call — every assertion here is scoped by `user_id`, so rows left
    by another gate are invisible to it.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    tables = [Base.metadata.tables[name] for name in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _account_with_everything(session, label: str) -> tuple[int, str]:
    """A user carrying one row of every kind that points at a user.

    Deliberately maximal: the pre-fix endpoint failed on the FIRST of these it
    met, so a fixture carrying only one kind would under-report the damage.

    Returns ``(user_id, tag)``. The tag carries a unique suffix because the
    database is shared with the other gates in this job and several of these
    columns are UNIQUE — `device_tokens.device_token`, `users.firebase_uid`,
    `oscars_pools.code`, `oscars_pool_members.member_token`.
    """
    import uuid

    import app.models.models as m

    tag = f"{label}-{uuid.uuid4().hex[:8]}"

    sport = (
        await session.execute(select(m.Sport).where(m.Sport.key == "basketball_nba"))
    ).scalar_one_or_none()
    if sport is None:
        sport = m.Sport(key="basketball_nba", name="NBA")
        session.add(sport)
        await session.flush()

    user = m.User(firebase_uid=f"fb-{tag}", email=f"{tag}@example.com")
    session.add(user)
    await session.flush()

    team = m.Team(sport_id=sport.id, name=f"Team {tag}")
    market = m.FuturesMarket(
        source=f"kalshi-{tag}", external_id=f"X-{tag}", name=f"Market {tag}"
    )
    pool = m.OscarsPool(
        name=f"Pool {tag}", code=uuid.uuid4().hex[:8], created_by_name=label
    )
    session.add_all([team, market, pool])
    await session.flush()

    session.add_all([
        m.UserPreference(user_id=user.id, onboarding_completed=True),
        m.UserPin(user_id=user.id, pin_type="event", target_id=1),
        m.UserFavorite(user_id=user.id, team_id=team.id),
        m.DeviceToken(device_token=f"token-{tag}", platform="ios", user_id=user.id),
        m.UserPrediction(
            user_id=user.id, market_id=market.id, guess="over",
            threshold=50, actual_probability=0.5, correct=True,
        ),
        m.UserSeenMarket(user_id=user.id, item_type="event", item_id=1),
        m.DiscoverInteraction(
            user_id=user.id, action="swipe", item_type="event", item_id="1",
        ),
        m.OscarsPoolMember(
            pool_id=pool.id, user_id=user.id, display_name=tag,
            member_token=f"member-{tag}",
        ),
        m.SearchQueryLog(user_id=user.id, query=f"query-{tag}"),
        m.BugReport(
            user_id=user.id, user_email=f"{tag}@example.com",
            description=f"bug-{tag}",
        ),
        m.PredictionChallenge(
            creator_user_id=user.id, challenge_code=uuid.uuid4().hex[:20],
            market_id=market.id, creator_guess="over", creator_threshold=50,
        ),
    ])
    await session.commit()
    return user.id, tag


async def _delete_account(session, user_id: int, load_in=None) -> None:
    """Run the REAL endpoint handler, not a copy of its body.

    Calling `delete_account` itself is deliberate: a gate that restates the
    implementation only ever proves the restatement right. The commit is the
    one thing added here, because in the app it belongs to `get_db_rw` rather
    than to the handler.

    ``load_in`` optionally loads the user through a DIFFERENT session, which is
    how the handler is reached if FastAPI ever stops handing the dependency and
    the handler one cached session.
    """
    import app.models.models as m
    from app.routes.auth import delete_account

    loader = load_in or session
    user = (
        await loader.execute(select(m.User).where(m.User.id == user_id))
    ).scalar_one()

    result = await delete_account(user=user, db=session)
    assert result == {"status": "deleted"}
    await session.commit()


async def _count(session, table: str, user_id: int) -> int:
    column = "creator_user_id" if table == "prediction_challenges" else "user_id"
    return (
        await session.execute(
            text(f"SELECT count(*) FROM {table} WHERE {column} = :u"), {"u": user_id}
        )
    ).scalar()


async def test_deleting_a_fully_populated_account_succeeds(db):
    """The headline. Before #678 this raised NotNullViolationError on the first
    owned table and the reviewer saw a spinner reset with no message.
    """
    import app.models.models as m

    user_id, _tag = await _account_with_everything(db, "headline")

    await _delete_account(db, user_id)

    remaining = (
        await db.execute(select(m.User).where(m.User.id == user_id))
    ).scalar_one_or_none()
    assert remaining is None, "the account row survived a deletion request"


@pytest.mark.parametrize("table", _OWNED_TABLES)
async def test_the_users_own_rows_are_gone(db, table):
    user_id, _tag = await _account_with_everything(db, "owned")

    # The strawman guard. "0 rows after" is the assertion, and 0 rows BEFORE
    # satisfies it without the endpoint doing anything — which is exactly what
    # happened while the fixture forgot to create an oscars_pool_members row
    # and this case passed green against an empty table.
    assert await _count(db, table, user_id) == 1, (
        f"the fixture created no {table} row, so the assertion below proves nothing"
    )

    await _delete_account(db, user_id)

    assert await _count(db, table, user_id) == 0, (
        f"{table} still holds rows for a deleted account — 'and all associated "
        "data' is the part of Guideline 5.1.1(v) that fails silently"
    )


async def test_kept_rows_keep_nothing_that_names_the_person(db):
    """Bug reports, challenges and the search corpus outlive the account, so
    the row stays and every identifying field goes — including the profile
    email copied onto a bug report, which nulling ``user_id`` alone would miss.
    """
    user_id, tag = await _account_with_everything(db, "kept")

    await _delete_account(db, user_id)

    for table in ["bug_reports", "search_query_logs", "prediction_challenges"]:
        assert await _count(db, table, user_id) == 0, (
            f"{table} still links to the deleted account"
        )

    surviving_bug = (
        await db.execute(
            text("SELECT user_id, user_email FROM bug_reports WHERE description = :d"),
            {"d": f"bug-{tag}"},
        )
    ).one()
    assert surviving_bug == (None, None), (
        f"the bug report survived carrying {surviving_bug} — the email is a "
        "direct identifier"
    )

    kept_query = (
        await db.execute(
            text("SELECT count(*) FROM search_query_logs WHERE query = :q"),
            {"q": f"query-{tag}"},
        )
    ).scalar()
    assert kept_query == 1, "the de-identified row should survive, not be deleted"


async def test_a_second_account_is_untouched(db):
    """The refusal half. A deletion scoped by anything other than this user's
    id — or a cascade reaching further than intended — takes someone else's
    data with it, and nothing in the response would say so.
    """
    victim_id, _victim_tag = await _account_with_everything(db, "victim")
    bystander_id, _bystander_tag = await _account_with_everything(db, "bystander")

    await _delete_account(db, victim_id)

    import app.models.models as m

    bystander = (
        await db.execute(select(m.User).where(m.User.id == bystander_id))
    ).scalar_one_or_none()
    assert bystander is not None, "deleting one account removed another"

    for table in _OWNED_TABLES:
        assert await _count(db, table, bystander_id) == 1, (
            f"{table} lost the other account's row"
        )
    for table in ["bug_reports", "search_query_logs", "prediction_challenges"]:
        assert await _count(db, table, bystander_id) == 1, (
            f"{table} de-identified the other account's row"
        )


async def test_it_does_not_matter_which_session_loaded_the_user(db):
    """The handler must not depend on the caller's session arrangement.

    FastAPI caches `get_db_rw` per request, so today `get_current_user` and the
    handler share a session and the stale-instance `expunge` is safe. Reached
    with a user loaded elsewhere, an unguarded `expunge` raises
    InvalidRequestError and "delete my account" 500s. Found by driving a real
    HTTP request at the route rather than its statements.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.models.models as m

    user_id, _tag = await _account_with_everything(db, "foreign")

    other_session = async_sessionmaker(db.bind, expire_on_commit=False)()
    try:
        await _delete_account(db, user_id, load_in=other_session)
    finally:
        await other_session.close()

    assert (
        await db.execute(select(m.User).where(m.User.id == user_id))
    ).scalar_one_or_none() is None


async def test_deleting_an_account_that_has_nothing_still_works(db):
    """The boundary the old code DID handle, kept so a fix aimed at populated
    accounts cannot regress the empty one.
    """
    import app.models.models as m

    user = m.User(firebase_uid="fb-empty", email="empty@example.com")
    db.add(user)
    await db.commit()

    await _delete_account(db, user.id)

    assert (
        await db.execute(select(m.User).where(m.User.id == user.id))
    ).scalar_one_or_none() is None
