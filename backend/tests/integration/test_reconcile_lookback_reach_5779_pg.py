"""#5779 — the duplicate reconciliation reaches a match that has already kicked off.

## What was wrong, measured on production

`#5783` shipped the id-anchored writer: two rows carrying one `statpal_fixture_id`
get `provenance:duplicate-of:` on the loser, and `not_a_proven_duplicate()` stops
printing it. Read back at 04:5xZ on 2026-09-13, **5 of the 12 shared-id groups were
tagged and all five were MLB.** Two of the seven untagged were that day's matches:

| fixture | league | rows | reader sees |
|---|---|---|---|
| `9543399` | Bundesliga, Mainz v Eintracht Frankfurt, kicked off 13:30Z | 15297803 + 15310934 | two FINAL cards for one match |
| `9545725` | Serie A, Lazio v AC Milan, kicked off 16:00Z | 15297966 + 15298413 | the same, on the Serie A rail |

The reconciliation was handed `[f.fixture_id for f in fixtures]` — *the contests
this pass read from StatPal*. The soccer spec reads day offsets `(1, 2, 3)`, i.e.
boards in the FUTURE, so a fixture id leaves that list the moment its match starts.
The second row of a twin normally appears at or after kickoff. **The pair became
provable exactly when the pass stopped being able to see it.** MLB's season-schedule
read spans played games, which is the whole reason only MLB was tagged.

## Why this gate is real PostgreSQL and not a session double

The fix is a SQL predicate — `GROUP BY statpal_fixture_id HAVING count(*) > 1`
inside a window, with an equality plan for a single-key league and a `LIKE` plan
for soccer's ~40 keys. Every way it can be wrong is a way a double cannot see:

* `HAVING count(*) > 1` written as `>= 1` returns every anchored row in the league;
* the window bounds inverted or dropped returns the whole table;
* the `%` interpolated rather than bound reads as a literal and returns nothing
  (gotcha #45), which looks exactly like "there were no duplicates".

The caller half — that the look-back's ids are UNIONED with the read's rather than
replacing them, and that the window starts at `now - DUPLICATE_SCAN_LOOKBACK` —
is graded in `tests/test_stamp_v1_agreement_row.py`, where a fake can see it.

The rows below are the production specimens above, with their real ids, real
kickoffs and real club spellings, plus the NBA fabricated-id pair (`1027790`,
two games 24 hours apart wearing one id) that the look-back MUST hand over and
the refusals MUST then decline. That split is the point: widening the reach must
not widen what gets tagged.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #5779 "
            "look-back reach gate (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

#: The pass's "now". Both production specimens kicked off hours before it, which
#: is the state the old reach could not see.
NOW = datetime(2026, 9, 13, 4, 50, tzinfo=timezone.utc)

#: The only leagues this file creates, deletes or asserts over. Named once so the
#: teardown's blast radius is readable beside the seeding.
SEEDED_SPORT_KEYS = [
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "basketball_nba",
]


def _closure(*roots):
    """The tables these queries need, and nothing else.

    `Base.metadata.create_all()` emits DDL for every model, and one unrelated
    table carries `NULLS NOT DISTINCT` — PostgreSQL 15+ only. Building the whole
    schema would make this gate's ability to run depend on a clause no part of it
    uses, and the failure would read as "the #5779 gate is broken" rather than
    "the server is old". Same helper, same reason, as #5789's gate.
    """
    seen: dict = {}
    pending = list(roots)
    while pending:
        table = pending.pop()
        if table.key in seen:
            continue
        seen[table.key] = table
        for fk in table.foreign_keys:
            pending.append(fk.column.table)
    return list(seen.values())


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema. Function-scoped for the reason the siblings give."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, Sport
    from app.services.database import Base

    tables = _closure(Sport.__table__, Event.__table__)
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(sync, tables=tables, checkfirst=True)
        )
        # Start from a known population in MY three leagues — and only those.
        # CI's `search-recall` job runs every PG gate against ONE database, so a
        # bare `DELETE FROM events` here would be this file reaching into other
        # gates' seeded rows (and it fails outright on the `futures_markets` FK
        # that #5789's gate leaves behind).
        await conn.execute(
            text(
                "DELETE FROM events WHERE sport_id IN "
                "(SELECT id FROM sports WHERE key = ANY(:keys))"
            ),
            {"keys": SEEDED_SPORT_KEYS},
        )
        await conn.execute(
            text("DELETE FROM sports WHERE key = ANY(:keys)"),
            {"keys": SEEDED_SPORT_KEYS},
        )

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _sport(session, key: str) -> int:
    from sqlalchemy import text

    return (
        await session.execute(
            text(
                "INSERT INTO sports (key, name, active) VALUES (:k, :k, TRUE) "
                "RETURNING id"
            ),
            {"k": key},
        )
    ).scalar()


async def _event(
    session,
    *,
    sport_id: int,
    home: str,
    away: str,
    start: datetime,
    fixture_id,
    espn_id=None,
    home_score=None,
    away_score=None,
    status: str = "completed",
) -> int:
    from sqlalchemy import text

    return (
        await session.execute(
            text(
                """
                INSERT INTO events
                    (sport_id, home_team_name, away_team_name, commence_time,
                     status, statpal_fixture_id, espn_id, home_score, away_score)
                VALUES
                    (:sid, :home, :away, :ct, :status, :fid, :espn, :hs, :as_)
                RETURNING id
                """
            ),
            {
                "sid": sport_id,
                "home": home,
                "away": away,
                "ct": start,
                "status": status,
                "fid": fixture_id,
                "espn": espn_id,
                "hs": home_score,
                "as_": away_score,
            },
        )
    ).scalar()


@pytest.fixture
async def seeded(pg_session):
    """The production population, in one league family and one control league."""
    bundesliga = await _sport(pg_session, "soccer_germany_bundesliga")
    serie_a = await _sport(pg_session, "soccer_italy_serie_a")
    nba = await _sport(pg_session, "basketball_nba")

    ids: dict[str, int] = {}

    # #5779's own pair: kicked off 15h before NOW, so the pass's future boards
    # no longer list it. Names differ, which is why the id-free fold misses it.
    ids["mainz_statpal"] = await _event(
        pg_session,
        sport_id=bundesliga,
        home="FSV Mainz 05",
        away="Eintracht Frankfurt",
        start=NOW - timedelta(hours=15, minutes=20),
        fixture_id="9543399",
        home_score=1,
        away_score=3,
    )
    ids["mainz_espn"] = await _event(
        pg_session,
        sport_id=bundesliga,
        home="Mainz",
        away="Eintracht Frankfurt",
        start=NOW - timedelta(hours=15, minutes=20),
        fixture_id="9543399",
        espn_id="401884794",
        home_score=1,
        away_score=3,
    )

    # The Serie A pair, same shape, a different one of our ~40 soccer keys — the
    # reason the soccer read is a prefix and not an equality.
    ids["lazio_a"] = await _event(
        pg_session,
        sport_id=serie_a,
        home="Lazio",
        away="AC Milan",
        start=NOW - timedelta(hours=12, minutes=50),
        fixture_id="9545725",
    )
    ids["lazio_b"] = await _event(
        pg_session,
        sport_id=serie_a,
        home="Lazio",
        away="AC Milan",
        start=NOW - timedelta(hours=12, minutes=50),
        fixture_id="9545725",
        espn_id="401872001",
    )

    # A normally anchored row: one contest, one row. The overwhelming majority
    # state, and `HAVING count(*) > 1` is the only thing keeping it out.
    ids["single"] = await _event(
        pg_session,
        sport_id=bundesliga,
        home="SC Freiburg",
        away="Borussia Monchengladbach",
        start=NOW - timedelta(hours=18),
        fixture_id="9543401",
    )

    # A real duplicate OLDER than the look-back: past every rail that renders it.
    ids["ancient_a"] = await _event(
        pg_session,
        sport_id=bundesliga,
        home="Werder Bremen",
        away="Hamburg",
        start=NOW - timedelta(days=40),
        fixture_id="9500001",
    )
    ids["ancient_b"] = await _event(
        pg_session,
        sport_id=bundesliga,
        home="Werder",
        away="Hamburg",
        start=NOW - timedelta(days=40),
        fixture_id="9500001",
    )

    # Two unstamped rows. `GROUP BY` puts every NULL in ONE group, so without
    # the `IS NOT NULL` these two — which have nothing to do with each other —
    # become a "contest held twice" whose id is NULL. Production's soccer table
    # is mostly this state, so the group would be enormous.
    ids["unstamped_a"] = await _event(
        pg_session,
        sport_id=bundesliga,
        home="Bayern Munich",
        away="Bayer Leverkusen",
        start=NOW - timedelta(days=2),
        fixture_id=None,
    )
    ids["unstamped_b"] = await _event(
        pg_session,
        sport_id=bundesliga,
        home="Union Berlin",
        away="VfB Stuttgart",
        start=NOW - timedelta(days=2),
        fixture_id=None,
    )

    # Production's NBA `1027790`: two DIFFERENT games wearing one fabricated id,
    # kickoffs 24 hours apart. The look-back must surface it and the refusals
    # must decline it.
    ids["nba_early"] = await _event(
        pg_session,
        sport_id=nba,
        home="Charlotte Hornets",
        away="Miami Heat",
        start=NOW - timedelta(days=3),
        fixture_id="1027790",
    )
    ids["nba_late"] = await _event(
        pg_session,
        sport_id=nba,
        home="Charlotte Hornets",
        away="Miami Heat",
        start=NOW - timedelta(days=2),
        fixture_id="1027790",
    )

    await pg_session.commit()
    return ids


async def _lookback(session, *, sport_key, is_prefix, start=None, end=None):
    from app.tasks.reconcile_shared_fixture_ids import (
        DUPLICATE_SCAN_LOOKBACK,
        shared_fixture_ids_on_our_rows,
    )

    return await shared_fixture_ids_on_our_rows(
        session,
        sport_key=sport_key,
        sport_key_is_prefix=is_prefix,
        window_start=start if start is not None else NOW - DUPLICATE_SCAN_LOOKBACK,
        window_end=end if end is not None else NOW + timedelta(days=1),
    )


class TestTheReach:
    async def test_a_match_that_has_already_kicked_off_is_found(
        self, pg_session, seeded
    ):
        """#5779 itself. Neither id is on any board the pass reads today."""
        found = await _lookback(pg_session, sport_key="soccer", is_prefix=True)
        assert "9543399" in found
        assert "9545725" in found

    async def test_the_prefix_spans_our_forty_soccer_keys(self, pg_session, seeded):
        """One StatPal sport, many of our `sports.key` values (CERT-2189).

        The two pairs sit in different leagues. An equality read on
        `'soccer'` — the StatPal-side id space, which is not one of our keys —
        returns neither, and that is the mutant this kills.
        """
        prefixed = await _lookback(pg_session, sport_key="soccer", is_prefix=True)
        equality = await _lookback(pg_session, sport_key="soccer", is_prefix=False)
        assert set(prefixed) >= {"9543399", "9545725"}
        assert equality == [], (
            "'soccer' is not one of our sports.key values; an equality read on "
            "it must find nothing rather than quietly matching the family"
        )

    async def test_a_league_with_one_key_is_read_by_equality(self, pg_session, seeded):
        found = await _lookback(pg_session, sport_key="basketball_nba", is_prefix=False)
        assert found == ["1027790"]

    async def test_one_row_per_contest_is_not_a_duplicate(self, pg_session, seeded):
        """The majority state stays out. `HAVING count(*) > 1` is load-bearing."""
        found = await _lookback(pg_session, sport_key="soccer", is_prefix=True)
        assert "9543401" not in found

    async def test_the_window_is_a_bound_and_not_decoration(self, pg_session, seeded):
        """A pair 40 days old is past every rail that could render it."""
        found = await _lookback(pg_session, sport_key="soccer", is_prefix=True)
        assert "9500001" not in found

        # Present in the table, and reachable when the window is widened — so the
        # absence above is the BOUND, not a seeding accident.
        widened = await _lookback(
            pg_session,
            sport_key="soccer",
            is_prefix=True,
            start=NOW - timedelta(days=90),
        )
        assert "9500001" in widened

    async def test_two_unstamped_rows_are_not_one_contest(self, pg_session, seeded):
        """The NULL group is not a duplicate — it is most of the table.

        `GROUP BY` collapses every unstamped row into one group, so a predicate
        without `IS NOT NULL` reports a "contest" whose id is NULL and whose
        members are unrelated games. Nothing downstream would tag them (the
        contest-id refusal catches it), but the pass would hand the
        reconciliation a bogus group every hour and its receipts would say so.
        """
        found = await _lookback(pg_session, sport_key="soccer", is_prefix=True)
        assert all(f and f.strip() for f in found), found
        assert "None" not in found

    async def test_a_league_the_pass_is_not_reading_is_not_swept(
        self, pg_session, seeded
    ):
        """Each pass sweeps its OWN league. The NBA pair is not soccer's to see."""
        found = await _lookback(pg_session, sport_key="soccer", is_prefix=True)
        assert "1027790" not in found


class TestWideningTheReachDidNotWidenWhatGetsTagged:
    async def test_the_soccer_pair_is_tagged_and_the_reader_keeps_the_espn_row(
        self, pg_session, seeded
    ):
        from sqlalchemy import text

        from app.services.anchor_channel import duplicate_tag
        from app.tasks.reconcile_shared_fixture_ids import (
            reconcile_shared_fixture_ids,
        )
        from app.tasks.stamp_v1_statpal_fixtures import is_statpal_contest_id

        ids = await _lookback(pg_session, sport_key="soccer", is_prefix=True)
        result = await reconcile_shared_fixture_ids(
            pg_session, ids, is_contest_id=is_statpal_contest_id, apply=True
        )

        assert result["tags_written"] == 2, result
        tagged = dict(
            (
                await pg_session.execute(
                    text(
                        "SELECT id, event_tags FROM events "
                        "WHERE event_tags IS NOT NULL AND event_tags::text "
                        "LIKE '%duplicate-of%'"
                    )
                )
            ).all()
        )
        # The survivor is the scored, ESPN-anchored row — the one production
        # already serves — and the loser carries the tag naming it.
        assert seeded["mainz_statpal"] in tagged
        assert seeded["mainz_espn"] not in tagged
        assert duplicate_tag(seeded["mainz_espn"]) in str(
            tagged[seeded["mainz_statpal"]]
        )

    async def test_the_fabricated_nba_id_is_surfaced_and_then_refused(
        self, pg_session, seeded
    ):
        """Two real games 24h apart share one id. Tagging one would hide a game."""
        from app.tasks.reconcile_shared_fixture_ids import (
            REFUSAL_KICKOFF_DIFFERS,
            reconcile_shared_fixture_ids,
        )
        from app.tasks.stamp_v1_statpal_fixtures import is_statpal_contest_id

        ids = await _lookback(pg_session, sport_key="basketball_nba", is_prefix=False)
        assert ids == ["1027790"], "the look-back must hand the group over"

        result = await reconcile_shared_fixture_ids(
            pg_session, ids, is_contest_id=is_statpal_contest_id, apply=True
        )
        assert result["tags_written"] == 0
        assert result["tags_planned"] == 0
        reasons = {
            r.get("reason") for r in result["duplicate_refusal_receipts"]
        }
        assert REFUSAL_KICKOFF_DIFFERS in reasons, result["duplicate_refusal_receipts"]

    async def test_a_second_pass_writes_nothing_new(self, pg_session, seeded):
        """Idempotent in the database, which is what makes the undo a statement."""
        from app.tasks.reconcile_shared_fixture_ids import (
            reconcile_shared_fixture_ids,
        )
        from app.tasks.stamp_v1_statpal_fixtures import is_statpal_contest_id

        ids = await _lookback(pg_session, sport_key="soccer", is_prefix=True)
        first = await reconcile_shared_fixture_ids(
            pg_session, ids, is_contest_id=is_statpal_contest_id, apply=True
        )
        second = await reconcile_shared_fixture_ids(
            pg_session, ids, is_contest_id=is_statpal_contest_id, apply=True
        )
        assert first["tags_written"] == 2
        assert second["tags_written"] == 0


class TestTheLookbackCoversWhatAReaderCanStillSee:
    async def test_the_lookback_covers_the_deepest_rail_a_reader_sees(self):
        """Two constants, one capability question — so assert the gap.

        `RESULTS_LOOKBACK_DAYS` is how far back the league page's results rail
        renders. A duplicate inside that window is two cards on a page someone
        can open; one outside it is invisible. The look-back is not imported from
        the route (a task reaching into a serving decision is the coupling this
        avoids), so this is what notices if the RAIL widens and the sweep does
        not.
        """
        from app.routes.league_futures import RESULTS_LOOKBACK_DAYS
        from app.tasks.reconcile_shared_fixture_ids import DUPLICATE_SCAN_LOOKBACK

        assert DUPLICATE_SCAN_LOOKBACK >= timedelta(days=RESULTS_LOOKBACK_DAYS), (
            f"the results rail renders {RESULTS_LOOKBACK_DAYS} days of finished "
            f"games and the duplicate sweep only reaches {DUPLICATE_SCAN_LOOKBACK} "
            "— the gap is games a reader can see doubled and no pass can tag"
        )
