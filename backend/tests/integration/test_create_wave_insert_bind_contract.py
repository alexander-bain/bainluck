"""The CREATE wave's INSERT, executed against a REAL asyncpg driver (#1796/#1947).

WHY THIS FILE EXISTS: FOUR DEATHS BEHIND FOUR GREEN GATES
---------------------------------------------------------
The 328-game attended CREATE wave (#1947/#1796) has now failed at four different
depths, and every single one of them was invisible to every gate upstream of it:

* **#2003** — the statpal absorber. Gate met, rail replaced.
* **#2013** — ``asyncpg.exceptions.AmbiguousParameterError: inconsistent types
  deduced for parameter $2``. ``:truth_id`` is bound in TWO positions that infer
  different Postgres types (bare in the ``SELECT`` list asyncpg deduces ``text``;
  compared against ``events.espn_id`` it deduces ``character varying``) and was
  cast in NEITHER. The statement is refused at PREPARE, before a row is written.
* **#2023** — the espn_id minting writer. Gate met, rail replaced.
* **#2026** — ``asyncpg.exceptions.DataError: invalid input for query argument
  $7: '2026-06-21T02:10:00+00:00' (expected a datetime.date or datetime.datetime
  instance, got 'str')``. ``commence_time`` went to the driver as its ISO string.
  ``CAST(:commence_time AS timestamptz)`` does **not** save it: asyncpg
  type-checks the PYTHON argument before the statement ever reaches the server,
  so a server-side cast is applied to a value that was already rejected
  client-side.

Fable's ruling, 2026-08-20, is the reason this file is the deliverable rather
than a fifth parameter fix: **"A dry run gates only what it executes."** Both
#2013 and #2026 are the same structural blindness one parameter apart — the
dry run is GREEN on every gate it has (``plan_hash`` re-derives identical,
``still_missing 328``, ``already_present 0``) *because the dry run never
executes the INSERT*. The unit suite cannot see them either: its session double
(``tests/test_create_events_from_truth_consumer.py::_Session``) reads the bind
dict as plain Python, and plain Python is perfectly happy with a ``str`` in a
timestamp slot and with a parameter used twice.

The finding was never the fourth bug. It was that this rail had no test that
EXECUTES its INSERT against a real driver. This file is that test.

The precedent is exact: ``test_kalshi_cliff_bind_contract.py`` (#1884 — 39 green
unit tests, ``asyncpg.DataError`` on the first statement of every production
run). Its shape, its fixture, its skip discipline and its CI wiring are reused
here deliberately rather than reinvented.

WHY EACH ARM IS SHAPED THE WAY IT IS
------------------------------------
1. ``test_the_wave_insert_executes_against_real_postgres`` — the POSITIVE arm.
   It calls :func:`app.tasks.create_events_from_truth.repair` — the function the
   admin dispatcher actually invokes — with a plan row whose ``commence_time``
   is the ISO **string** the plan genuinely carries. Not ``_as_datetime`` in
   isolation, not a local restatement of the SQL: a test that models the rail
   proves the model.

2. ``test_binding_the_iso_string_raw_is_refused_by_the_real_driver`` — the
   NEGATIVE CONTROL for #2026. It reverts the coercion at the bind (by making
   ``_as_datetime`` the identity function, which is exactly what deleting its
   call site does) and asserts the real driver RAISES. **A gate that cannot fail
   proves nothing.** This arm is what makes one green run of arm 1 mean
   "red-first was proved" rather than "nothing objected".

3. ``test_an_uncast_truth_id_is_refused_by_the_real_driver`` — the NEGATIVE
   CONTROL for #2013, the sibling class on the same rail. It reverts the casts
   in the statement itself, derived from the module's own ``_INSERT_SQL`` text
   so it cannot drift away from what production runs.

Arms 2 and 3 revert the two fixes at their two different layers — the bind dict
and the statement text — and both are routed through ``repair()``, so neither is
a re-statement of the rail. If a future edit deletes either fix, arm 1 goes red
and the matching control goes green-when-it-should-raise; either way this file
fails.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following the search contracts — CI's
``search-recall`` job provides a Postgres 15 service, and its step greps for
skips, because a silently-skipped gate reads exactly like a passing one.
"""

import os
import re
from datetime import datetime, timezone

import pytest

from app.tasks import create_events_from_truth as rail
from app.utils.repair_apply_plan import PlannedCreate, build_create_plan

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres CREATE-wave "
            "INSERT bind contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

#: The exact literal from #2026's production traceback. Kept verbatim so the
#: specimen this file closes is the specimen that shipped, not a paraphrase of it.
SPECIMEN_ISO = "2026-06-21T02:10:00+00:00"
SPECIMEN_DT = datetime(2026, 6, 21, 2, 10, tzinfo=timezone.utc)


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, real asyncpg type coercion.

    Function-scoped: ``pytest.ini`` leaves ``asyncio_default_fixture_loop_scope``
    unset, so a module-scoped async fixture would outlive the event loop that
    created its engine. (Same call, same reason, as the cliff-drain contract.)
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _seed_anchors(session):
    """One sport and two clubs, so the created event's FKs resolve.

    ``events.sport_id`` -> ``sports.id`` and ``events.{home,away}_team_id`` ->
    ``teams.id`` are real foreign keys, so the row the rail writes cannot land
    without them. Raw ``text()`` INSERTs deliberately, following the cliff
    contract: this gate exists to exercise the driver's own type coercion, and
    going through the ORM would let SQLAlchemy adapt values on the way in —
    which is the layer whose absence is the defect.

    The cost of that choice, which CI found on the cliff contract's first run:
    Python-side column defaults do NOT apply to a raw INSERT, so every NOT NULL
    column with only a ``default=`` must be supplied. ``sports.active`` is in
    that class.
    """
    from sqlalchemy import text

    sport_id = (
        await session.execute(
            text(
                """
                INSERT INTO sports (key, name, active)
                VALUES ('baseball_mlb_bindcontract', 'MLB (bind contract)', TRUE)
                RETURNING id
                """
            )
        )
    ).scalar()

    home_id = (
        await session.execute(
            text(
                "INSERT INTO teams (sport_id, name) VALUES (:sid, :name) RETURNING id"
            ),
            {"sid": sport_id, "name": "Bind Contract Home"},
        )
    ).scalar()
    away_id = (
        await session.execute(
            text(
                "INSERT INTO teams (sport_id, name) VALUES (:sid, :name) RETURNING id"
            ),
            {"sid": sport_id, "name": "Bind Contract Away"},
        )
    ).scalar()

    await session.commit()
    return sport_id, home_id, away_id


def _plan_for(sport_id, home_id, away_id, *, truth_id):
    """One reviewed CREATE row, carrying ``commence_time`` as the plan carries it.

    The ISO **string** is deliberate and is not a shortcut. ``commence_time`` is
    inside the plan's CONTENT ADDRESS — it is how a reviewer knows which game a
    row is — so retyping the field on ``PlannedCreate`` would move ``plan_hash``
    and invalidate the artifact Alex approved. The string is the reviewed object;
    turning it into a ``datetime`` is an implementation detail of talking to the
    driver, and it therefore has to happen at the bind. Binding a string here is
    reproducing production, not simplifying it.
    """
    return build_create_plan(
        [
            PlannedCreate(
                truth_id=truth_id,
                provider="espn",
                home_team_id=home_id,
                away_team_id=away_id,
                home_name="Bind Contract Home",
                away_name="Bind Contract Away",
                commence_time=SPECIMEN_ISO,
                sport_id=sport_id,
                label=f"Bind Contract Away @ Bind Contract Home {SPECIMEN_ISO[:10]}",
            )
        ],
        context={"issue": "#1796", "population": "2", "source": "bind contract"},
    )


def _driver_refusal_name(exc) -> str:
    """The asyncpg exception class name behind a SQLAlchemy ``DBAPIError``.

    Do NOT simplify this to ``isinstance(exc.orig, asyncpg.exceptions.X)``. The
    asyncpg dialect does not hand asyncpg's exception through as ``.orig``: its
    DBAPI shim TRANSLATES it (``_asyncpg_error_translate``, matched down the
    MRO) into a shim error whose message is ``"<class
    'asyncpg.exceptions.X'>: <message>"``, and chains the original with ``raise
    ... from error``. So the real class is reachable via the ``__cause__`` chain
    on some versions and only via that embedded string on others.

    Both readings are affirmative evidence of the same fact — the driver refused
    with that named error — so this resolves the name once and the arms assert on
    it, rather than each arm pinning one representation and going brittle in the
    direction that matters least.
    """
    seen = 0
    cur = exc
    while cur is not None and seen < 12:
        seen += 1
        if (type(cur).__module__ or "").startswith("asyncpg"):
            return type(cur).__name__
        cur = getattr(cur, "orig", None) or cur.__cause__ or cur.__context__
    match = re.search(r"asyncpg\.exceptions\.(\w+)", str(exc))
    return match.group(1) if match else type(exc).__name__


def _arm_the_rail(monkeypatch, plan):
    """Substitute ONLY the artifact store and the cache invalidation.

    Everything between them — ``bind_apply``, ``create_gate``, the
    outside-the-approved-set assertion, the advisory lock, ``_INSERT_SQL``, the
    bind dict, the per-row commit and the after-verification — is the shipped
    code path, unpatched. That boundary is the point of the file: the two things
    stubbed here are a durable-snapshot read and a Redis scan, neither of which
    is a driver type boundary and neither of which the ``search-recall`` job
    provisions.
    """
    import app.utils.feed_cache as feed_cache

    async def _load(population):  # noqa: ARG001 — signature parity with the real one
        return plan, "ok"

    async def _invalidate(reason):
        return {"status": "ok", "deleted": 0, "reason": reason}

    monkeypatch.setattr(rail, "_load_plan", _load)
    monkeypatch.setattr(feed_cache, "invalidate_feed_response_cache", _invalidate)


async def test_the_wave_insert_executes_against_real_postgres(pg_session, monkeypatch):
    """The wave's own apply path writes a row, through the real driver.

    On the code as it stood at #2026 this raises ``DataError`` before writing
    anything — the production failure, reproduced end to end rather than
    described. On the fixed code it writes the reviewed row and reads it back
    with a real ``timestamptz``.
    """
    from sqlalchemy import text

    sport_id, home_id, away_id = await _seed_anchors(pg_session)
    plan = _plan_for(sport_id, home_id, away_id, truth_id="401698026")
    _arm_the_rail(monkeypatch, plan)

    result = await rail.repair(
        pg_session, apply=True, plan_hash=plan.plan_hash, population="2"
    )

    assert result.get("refused") is not True, (
        f"the apply refused before reaching the INSERT: {result.get('reason_codes')}. "
        "This arm must exercise the write, so a refusal here means the harness is "
        "wrong, not that the rail is right."
    )
    assert result["census"]["created"] == 1, (
        f"expected one created row, got {result['census']}. Zero created with no "
        "exception means the existence check refused it; an exception means a bind "
        "type is wrong again."
    )
    assert result["success"] is True

    row = (
        await pg_session.execute(
            text(
                """
                SELECT sport_id, espn_id, home_team_id, away_team_id,
                       home_team_name, away_team_name, commence_time, status
                  FROM events WHERE espn_id = :tid
                """
            ),
            {"tid": "401698026"},
        )
    ).mappings().one()

    # All seven written columns plus the status literal, because the point of
    # executing the real statement is to check what it actually wrote — not just
    # that it did not throw.
    assert row["sport_id"] == sport_id
    assert row["espn_id"] == "401698026"
    assert row["home_team_id"] == home_id
    assert row["away_team_id"] == away_id
    assert row["home_team_name"] == "Bind Contract Home"
    assert row["away_team_name"] == "Bind Contract Away"
    assert row["status"] == "scheduled"
    assert row["commence_time"] == SPECIMEN_DT, (
        f"the ISO string {SPECIMEN_ISO!r} must land as {SPECIMEN_DT!r}. A shifted "
        "value here would mean the coercion dropped or mis-read the offset, which "
        "a non-throwing bind can still do."
    )


async def test_binding_the_iso_string_raw_is_refused_by_the_real_driver(
    pg_session, monkeypatch
):
    """NEGATIVE CONTROL for #2026 — the gate must be able to SEE the defect.

    Making ``_as_datetime`` the identity function is precisely what deleting its
    call site does: the ISO string reaches asyncpg unconverted. If this arm ever
    stops raising, either the driver started coercing strings (it does not) or
    this file has quietly stopped executing the INSERT — which is the exact
    condition, one layer up, that let four bugs ship behind green gates.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    sport_id, home_id, away_id = await _seed_anchors(pg_session)
    plan = _plan_for(sport_id, home_id, away_id, truth_id="401698027")
    _arm_the_rail(monkeypatch, plan)

    # Revert the fix AT THE BIND, leaving every other layer shipped-as-is.
    monkeypatch.setattr(rail, "_as_datetime", lambda value: value)

    with pytest.raises(DBAPIError) as caught:
        await rail.repair(
            pg_session, apply=True, plan_hash=plan.plan_hash, population="2"
        )

    assert _driver_refusal_name(caught.value) == "DataError", (
        "expected asyncpg's own DataError for the un-coerced timestamp, got "
        f"{caught.value!r}"
    )

    # And nothing was written: the driver refuses client-side, so the failure is
    # total rather than partial. `CAST(... AS timestamptz)` is still in the
    # statement here and did not help — that is the whole lesson of #2026.
    await pg_session.rollback()
    written = (
        await pg_session.execute(
            text("SELECT COUNT(*) FROM events WHERE espn_id = :tid"),
            {"tid": "401698027"},
        )
    ).scalar()
    assert written == 0


async def test_an_uncast_truth_id_is_refused_by_the_real_driver(
    pg_session, monkeypatch
):
    """NEGATIVE CONTROL for #2013 — the sibling class, one parameter over.

    ``:truth_id`` appears TWICE in ``_INSERT_SQL``, in two positions Postgres
    infers differently (``text`` bare in the SELECT list, ``character varying``
    against ``events.espn_id``). Casting one side only relocates the
    disagreement; casting neither is what production shipped, and asyncpg
    refuses the statement at PREPARE with ``AmbiguousParameterError``.

    The reverted statement is DERIVED from the module's own text rather than
    retyped, so this control cannot drift away from what production runs — and
    the assertion below that the substitution actually changed something is what
    stops it from silently becoming a second copy of arm 1.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    sport_id, home_id, away_id = await _seed_anchors(pg_session)
    plan = _plan_for(sport_id, home_id, away_id, truth_id="401698013")
    _arm_the_rail(monkeypatch, plan)

    shipped = str(rail._INSERT_SQL)
    assert shipped.count("CAST(:truth_id AS varchar)") == 2, (
        "the shipped statement must cast BOTH occurrences of :truth_id — see "
        f"#2013. Found {shipped.count('CAST(:truth_id AS varchar)')}."
    )
    uncast = shipped.replace("CAST(:truth_id AS varchar)", ":truth_id")
    assert uncast != shipped

    # Revert the fix AT THE STATEMENT. `_INSERT_SQL` is a module global read at
    # call time, so the real `repair()` picks this up and every other layer stays
    # shipped-as-is.
    monkeypatch.setattr(rail, "_INSERT_SQL", text(uncast))

    with pytest.raises(DBAPIError) as caught:
        await rail.repair(
            pg_session, apply=True, plan_hash=plan.plan_hash, population="2"
        )

    assert _driver_refusal_name(caught.value) == "AmbiguousParameterError", (
        "expected asyncpg to refuse the twice-inferred parameter at PREPARE, got "
        f"{caught.value!r}"
    )

    await pg_session.rollback()
    written = (
        await pg_session.execute(
            text("SELECT COUNT(*) FROM events WHERE espn_id = :tid"),
            {"tid": "401698013"},
        )
    ).scalar()
    assert written == 0
