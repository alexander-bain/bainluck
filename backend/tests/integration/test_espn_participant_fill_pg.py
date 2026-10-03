"""#10305 D2 — the participant fill and its restore, on real Postgres.

Everything here needs a server: the write's fences are re-judged by Postgres
inside the UPDATE, RETURNING reports what a concurrent writer committed while
the UPDATE waited for the lock, a SAVEPOINT rollback is the database's, and the
stale taxonomy writers' erasure is an ORM flush of a value loaded earlier. A
fake session answers whatever it is told, so none of this can be a unit test.

Every pass is the ACTUAL scheduled pass, driven in its caller's exact shape
(``tasks/espn_sync.py``: ``try: async with _step_savepoint(session): await
sync_scheduled_events(...)`` / ``except Exception as e:
stats["errors"].append(f"scheduled_{sport}: {e}")``, ``_step_savepoint``
imported from the task module), then committed. G-CALLER in the unit file
pins that shape, so this driver is re-derived if Live ever reshapes it.

SYN throughout: synthetic sport, team rows and ESPN ids. No specimen claim.
A local run reading ``N skipped`` is NOT a pass — the CI step refuses one.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10305 D2 "
            "participant-fill contract (CI job `database-integration` provisions one)"
        ),
    ),
]

SYN_SPORT = "syn_10305_d2_fill"
ESPN_S, ESPN_H = "99030561", "99030562"
HOME_TID, AWAY_TID, WINGS_TID, STORM_TID = "990301", "990302", "990303", "990304"
TABLES = (
    "sports", "teams", "venues", "events", "team_identity_mapping",
    "futures_markets", "futures_outcomes",  # read by the real tag refresh (W14b)
)
COLS = (
    "home_team_name", "away_team_name", "home_team_id", "away_team_id",
    "home_team_normalized", "away_team_normalized", "home_team_alt_names",
    "away_team_alt_names", "event_tags",
)
LLM_TAG = "stakes:playoff_race"


def _espn_team(tid, display, short):
    from app.services.espn_api import ESPNTeam

    return ESPNTeam(
        espn_id=tid, name=short, abbreviation=None, display_name=display, short_name=short,
        nickname=None, primary_color=None, secondary_color=None, logo_url=None,
        logo_url_dark=None, record=None, location=display[: -len(short)].strip() or None,
    )


async def _clear(conn):
    sport = (await conn.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": SYN_SPORT})).scalar()
    if sport is None:
        return
    await conn.execute(text(
        "DELETE FROM team_identity_mapping WHERE team_id IN (SELECT id FROM teams WHERE sport_id = :s)"
    ), {"s": sport})
    await conn.execute(text("DELETE FROM events WHERE sport_id = :s"), {"s": sport})
    await conn.execute(text("DELETE FROM teams WHERE sport_id = :s"), {"s": sport})
    await conn.execute(text("DELETE FROM sports WHERE id = :s"), {"s": sport})


@dataclass
class Rig:
    engine: object
    maker: object
    sport_id: int
    teams: dict
    monkeypatch: object
    tmp_path: object
    start: datetime

    # ── seeding ──
    async def add_event(self, *, espn_id=ESPN_S, home="TBD", away="TBD", **over) -> int:
        from app.models.models import Event

        async with self.maker() as s:
            ev = Event(
                sport_id=self.sport_id, home_team_name=home, away_team_name=away,
                commence_time=self.start, commence_time_source="espn", status="scheduled",
                espn_id=espn_id, event_tags=over.pop("event_tags", ["status:upcoming"]), **over,
            )
            s.add(ev)
            await s.commit()
            return ev.id

    async def sql(self, statement, **params):
        async with self.engine.begin() as conn:
            return await conn.execute(text(statement), params)

    async def row(self, event_id) -> dict:
        async with self.engine.connect() as conn:
            r = (await conn.execute(text(
                "SELECT xmin::text AS xmin, espn_id, status, broadcast_info, " + ", ".join(COLS)
                + " FROM events WHERE id = :i"
            ), {"i": event_id})).mappings().first()
            return dict(r)

    # ── the board ──
    def board_s(self, *, sides=None, home=None, away=None, espn_id=ESPN_S):
        from app.services.espn_api import ESPNEvent

        home = home or _espn_team(HOME_TID, "Golden State Valkyries", "Valkyries")
        away = away or _espn_team(AWAY_TID, "Las Vegas Aces", "Aces")
        return ESPNEvent(
            espn_id=espn_id, name="Las Vegas Aces at Golden State Valkyries", short_name=None,
            date=self.start, status="scheduled", status_detail=None, period=None, clock=None,
            home_team=home, away_team=away, home_score=None, away_score=None, venue=None,
            broadcasts=[], home_win_probability=None,
            competitor_sides=sides if sides is not None else ((home.espn_id, "home"), (away.espn_id, "away")),
        )

    def board_h(self):
        from app.services.espn_api import ESPNEvent

        storm = _espn_team(STORM_TID, "Seattle Storm", "Storm")
        wings = _espn_team(WINGS_TID, "Dallas Wings", "Wings")
        return ESPNEvent(
            espn_id=ESPN_H, name="Dallas Wings at Seattle Storm", short_name=None,
            date=self.start, status="scheduled", status_detail=None, period=None, clock=None,
            home_team=storm, away_team=wings, home_score=None, away_score=None, venue=None,
            broadcasts=["SYN TV"], home_win_probability=None,
            competitor_sides=((STORM_TID, "home"), (WINGS_TID, "away")),
        )

    # ── the actual scheduled pass ──
    async def run_pass(self, board, *, stats=None):
        from app.tasks.espn_sync import _step_savepoint
        from app.utils.espn_helpers import sync_scheduled_events

        stats = {"errors": []} if stats is None else stats
        async with self.maker() as session:
            try:
                async with _step_savepoint(session):
                    await sync_scheduled_events(session, SYN_SPORT, board, stats)
            except Exception as e:
                stats["errors"].append(f"scheduled_{SYN_SPORT}: {str(e)}")
            await session.commit()
        return stats

    def hook(self, before=None, after=None, around=None):
        """Wrap the seam's call to the fill helper (the pass's own load is upstream)."""
        from app.utils import espn_helpers, espn_participant_fill as fill

        real = fill.maybe_fill_participants

        async def wrapped(session, event, ee, team_index, stats):
            if before is not None:
                await before(session, event)
            if around is not None:
                result = await around(real, session, event, ee, team_index, stats)
            else:
                result = await real(session, event, ee, team_index, stats)
            if after is not None:
                await after(session, event, result)
            return result

        self.monkeypatch.setattr(espn_helpers, "maybe_fill_participants", wrapped)

    def unhook(self):
        from app.utils import espn_helpers, espn_participant_fill as fill

        self.monkeypatch.setattr(espn_helpers, "maybe_fill_participants", fill.maybe_fill_participants)

    # ── the code denylist (plan §4.3 step 2, stood in for) ──
    def listed(self, *ids, fill_side=True, restore_side=True):
        from app.utils import espn_participant_fill as fill
        from scripts import restore_espn_participant_fill as restore

        if fill_side:
            self.monkeypatch.setattr(fill, "RESTORED_FILL_EVENT_IDS", frozenset(ids))
        if restore_side:
            self.monkeypatch.setattr(restore, "RESTORED_FILL_EVENT_IDS", frozenset(ids))

    # ── restore ──
    def env(self, *, age_s=600, version="5500", commit="b" * 40, **over):
        now = datetime.now(timezone.utc)
        env = {
            "HEROKU_APP_NAME": "bainluck",
            "HEROKU_RELEASE_VERSION": version,
            "HEROKU_SLUG_COMMIT": commit,
            "HEROKU_RELEASE_CREATED_AT": (now - timedelta(seconds=age_s)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        env.update(over)
        return {k: v for k, v in env.items() if v is not None}

    def proof(self, event_id, *, main=None, heavy=(), main_formation=1, heavy_formation=0,
              captured_ago=30, window=600, main_version=5500, main_commit="b" * 40,
              drop_heavy=False, name="proof.json"):
        now = datetime.now(timezone.utc)

        def ts(dt):
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        def app(name, instances, formation, version, commit):
            captured = now - timedelta(seconds=captured_ago)
            return {
                "app": name, "window_start": ts(captured - timedelta(seconds=window)),
                "captured_at": ts(captured), "release_version": version, "release_commit": commit,
                "formation": {"worker-realtime": formation}, "instances": list(instances),
            }

        main = [old_instance(now - timedelta(seconds=60)), new_instance()] if main is None else main
        apps = [app("bainluck", main, main_formation, main_version, main_commit)]
        if not drop_heavy:
            apps.append(app("bainluck-heavy", heavy, heavy_formation, 41, "d" * 40))
        path = self.tmp_path / name
        path.write_text(json.dumps({"event_id": event_id, "denylist_commit": "a" * 40, "apps": apps}))
        return str(path)

    async def restore(self, event_id, *, apply=True, proof="valid", env=None):
        from scripts import restore_espn_participant_fill as restore

        if proof == "valid":
            proof = self.proof(event_id)
        lines = []
        code = await restore.run_restore(
            self.maker, event_id=event_id, apply=apply, proof_path=proof,
            env=self.env() if env is None else env, out=lines.append,
        )
        return code, lines


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def old_instance(exited_at, *, evidence="exit", dyno="worker-realtime.1"):
    return {
        "dyno": dyno, "type": "worker-realtime", "release_version": 5499,
        "release_commit": "c" * 40, "carries_id": False, "state_at_capture": "exited",
        "exited_at": _ts(exited_at), "exit_evidence": evidence,
        "evidence_line": f"{dyno}: Process exited with status 0",
    }


def new_instance(*, dyno="worker-realtime.1", version=5500, commit="b" * 40, carries=True):
    return {
        "dyno": dyno, "type": "worker-realtime", "release_version": version,
        "release_commit": commit, "carries_id": carries, "state_at_capture": "up",
        "exited_at": None, "exit_evidence": None, "evidence_line": None,
    }


def refusals(lines):
    return [line.split("REFUSED: ", 1)[1].split(" ")[0] for line in lines if "REFUSED: " in line]


def fill_tags(row):
    from app.utils.espn_participant_fill import FILL_TAG_PREFIX

    return [t for t in row["event_tags"] if t.startswith(FILL_TAG_PREFIX)]


def markers(row):
    from app.utils.espn_participant_fill import RESTORED_TAG_PREFIX

    return [t for t in row["event_tags"] if t.startswith(RESTORED_TAG_PREFIX)]


def counters(stats):
    return stats.get("participant_fill", {})


@pytest.fixture
async def rig(monkeypatch, tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Sport, Team
    from app.services.database import Base
    from app.utils import espn_participant_fill as fill
    from scripts import restore_espn_participant_fill as restore

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[Base.metadata.tables[t] for t in TABLES], checkfirst=True
        )
        # The migration's partial unique index (alembic add_team_identity), which
        # the model does not declare and `register_team_identity` upserts on.
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tim_source_id ON team_identity_mapping "
            "(source, source_id, sport_key) WHERE source_id IS NOT NULL"
        ))
        await _clear(conn)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        sport = Sport(key=SYN_SPORT, name="SYN 10305 D2")
        s.add(sport)
        await s.flush()
        teams = {
            "valk": Team(name="Golden State Valkyries", sport_id=sport.id, espn_id=HOME_TID),
            "aces": Team(name="Las Vegas Aces", sport_id=sport.id, espn_id=AWAY_TID),
            "wings": Team(name="Dallas Wings", sport_id=sport.id, espn_id=WINGS_TID),
        }
        s.add_all(teams.values())
        await s.commit()
        team_ids = {k: t.id for k, t in teams.items()}
        sport_id = sport.id
    monkeypatch.setattr(fill, "RESTORED_FILL_EVENT_IDS", frozenset())
    monkeypatch.setattr(restore, "RESTORED_FILL_EVENT_IDS", frozenset())
    start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(second=0, microsecond=0)
    yield Rig(engine, maker, sport_id, team_ids, monkeypatch, tmp_path, start)
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _fill(rig, **event_kw):
    """Seed S, run pass 1, return (event_id, row after)."""
    eid = await rig.add_event(**event_kw)
    stats = await rig.run_pass([rig.board_s()])
    assert counters(stats).get("filled") == 1, stats
    return eid, await rig.row(eid)


# ── W1: the write ────────────────────────────────────────────────────────────


async def test_w1_the_fill_writes_exactly_the_seven_columns_and_the_orm_matches(rig):
    from app.utils.espn_participant_fill import parse_fill_tag

    eid = await rig.add_event(event_tags=["status:upcoming", "provenance:other"])
    before = await rig.row(eid)
    seen = {}

    async def after(session, event, result):
        seen["orm"] = {c: getattr(event, c) for c in COLS if c not in ("home_team_alt_names", "away_team_alt_names")}

    rig.hook(after=after)
    stats = await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    assert counters(stats) == {"filled": 1}
    assert stats["errors"] == [] and "team_binding_refused" not in stats
    assert (row["home_team_name"], row["away_team_name"]) == ("Golden State Valkyries", "Las Vegas Aces")
    assert (row["home_team_id"], row["away_team_id"]) == (rig.teams["valk"], rig.teams["aces"])
    assert row["home_team_normalized"] is None and row["away_team_normalized"] is None
    assert row["event_tags"][:2] == ["status:upcoming", "provenance:other"]
    (tag,) = fill_tags(row)
    assert row["event_tags"] == ["status:upcoming", "provenance:other", tag]
    r = parse_fill_tag(tag)
    assert (r.after_home_tid, r.after_away_tid, r.prior_home_name) == (rig.teams["valk"], rig.teams["aces"], "TBD")
    for col in seen["orm"]:
        assert seen["orm"][col] == row[col], col
    for col in ("espn_id", "status", "home_team_alt_names", "away_team_alt_names", "broadcast_info"):
        assert row[col] == before[col]


async def test_w1b_prime_our_spelling_is_written_and_the_respelling_is_a_no_op(rig):
    await rig.sql("UPDATE teams SET name = 'Golden St Valkyries' WHERE id = :i", i=rig.teams["valk"])
    eid = await rig.add_event()
    stats = await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    assert counters(stats) == {"filled": 1}
    assert "espn_scheduled_team_name_respelled" not in stats
    assert row["home_team_name"] == "Golden St Valkyries" and row["home_team_id"] == rig.teams["valk"]


async def test_w1b_double_prime_a_same_id_row_minted_mid_pass_fails_the_uniqueness_fence(rig):
    from app.models.models import Team

    await rig.sql("UPDATE teams SET name = 'Golden St Valkyries' WHERE id = :i", i=rig.teams["valk"])
    eid = await rig.add_event()
    before = await rig.row(eid)

    async def before_fill(session, event):
        session.add(Team(name="Golden State Valkyries", sport_id=rig.sport_id, espn_id=HOME_TID))
        await session.flush()

    rig.hook(before=before_fill)
    stats = await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    assert counters(stats) == {"fence_lost": 1}
    assert {c: row[c] for c in COLS} == {c: before[c] for c in COLS}


async def test_w1c_a_tag_committed_before_the_fill_is_kept_in_the_db_and_the_orm(rig):
    eid = await rig.add_event()
    seen = {}

    async def before_fill(session, event):
        await rig.sql(
            "UPDATE events SET event_tags = event_tags || '[\"provenance:test-unrelated\"]'::jsonb WHERE id = :i",
            i=eid,
        )

    async def after(session, event, result):
        seen["orm"] = list(event.event_tags)

    rig.hook(before=before_fill, after=after)
    await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    (tag,) = fill_tags(row)
    assert row["event_tags"] == ["status:upcoming", "provenance:test-unrelated", tag]
    assert seen["orm"] == row["event_tags"]


async def test_w1d_a_writer_holding_the_row_is_waited_for_and_its_tag_is_kept(rig):
    eid = await rig.add_event()
    seen = {}

    async def around(real, session, event, ee, team_index, stats):
        async with rig.engine.connect() as b:
            tx = await b.begin()
            await b.execute(text(
                "UPDATE events SET event_tags = event_tags || '[\"provenance:test-held\"]'::jsonb WHERE id = :i"
            ), {"i": eid})
            task = asyncio.create_task(real(session, event, ee, team_index, stats))
            await asyncio.sleep(0.5)
            seen["blocked"] = not task.done()
            await tx.commit()
        result = await asyncio.wait_for(task, timeout=10)
        seen["orm"] = list(event.event_tags)
        return result

    rig.hook(around=around)
    stats = await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    assert seen["blocked"] is True
    assert counters(stats) == {"filled": 1}
    (tag,) = fill_tags(row)
    assert row["event_tags"] == ["status:upcoming", "provenance:test-held", tag]
    assert seen["orm"] == row["event_tags"]


# ── W2–W8: every fence, changed between the verdict's read and the write ─────

FENCE_CHANGES = {
    "espn_id": "UPDATE events SET espn_id = '99030599' WHERE id = :i",
    "status": "UPDATE events SET status = 'live' WHERE id = :i",
    "prior_home_name": "UPDATE events SET home_team_name = 'TBA' WHERE id = :i",
    "prior_away_name": "UPDATE events SET away_team_name = 'TBA' WHERE id = :i",
    "home_fk": "UPDATE events SET home_team_id = :wings WHERE id = :i",
    "away_fk": "UPDATE events SET away_team_id = :wings WHERE id = :i",
    "home_norm": "UPDATE events SET home_team_normalized = 'TBA' WHERE id = :i",
    "away_norm": "UPDATE events SET away_team_normalized = 'TBA' WHERE id = :i",
    "home_alt": "UPDATE events SET home_team_alt_names = '[\"x\"]'::jsonb WHERE id = :i",
    "away_alt": "UPDATE events SET away_team_alt_names = '[\"x\"]'::jsonb WHERE id = :i",
    "fill_tag": (
        "UPDATE events SET event_tags = event_tags || "
        "'[\"provenance:espn-participant-fill:x:away=1:home=2:r1=x\"]'::jsonb WHERE id = :i"
    ),
    "restored_marker": (  # W8b
        "UPDATE events SET event_tags = event_tags || "
        "'[\"provenance:espn-participant-fill-restored:x:away=1:home=2:r1=x\"]'::jsonb WHERE id = :i"
    ),
    "home_team_renamed": "UPDATE teams SET name = 'Golden State Valkyries II' WHERE id = :valk",
    "away_team_deleted": "DELETE FROM teams WHERE id = :aces",
    "home_team_reid": "UPDATE teams SET espn_id = '990399' WHERE id = :valk",
    "away_team_other_sport": "UPDATE teams SET sport_id = :other_sport WHERE id = :aces",
    "home_team_other_sport": "UPDATE teams SET sport_id = :other_sport WHERE id = :valk",
    # A second row carrying the side's ESPN id (ORM-seeded, below).
    "home_second_same_id": ("Valk Two", HOME_TID),
    "away_second_same_id": ("Aces Two", AWAY_TID),
}


async def _add_team(rig, name, espn_id, sport_id=None):
    from app.models.models import Team

    async with rig.maker() as s:
        s.add(Team(name=name, sport_id=sport_id or rig.sport_id, espn_id=espn_id))
        await s.commit()


async def _add_sport(rig, key):
    from app.models.models import Sport

    async with rig.maker() as s:
        sport = Sport(key=key, name="SYN other")
        s.add(sport)
        await s.commit()
        return sport.id


@pytest.mark.parametrize("change", sorted(FENCE_CHANGES))
async def test_w2_to_w8_each_fence_lost_writes_nothing(rig, change):
    eid = await rig.add_event()
    await rig.sql("DELETE FROM sports WHERE key = :k", k=SYN_SPORT + "_other")
    other_sport = await _add_sport(rig, SYN_SPORT + "_other")
    snap = {}

    async def before_fill(session, event):
        what = FENCE_CHANGES[change]
        if isinstance(what, tuple):
            await _add_team(rig, *what)
        else:
            await rig.sql(
                what, i=eid, wings=rig.teams["wings"], valk=rig.teams["valk"],
                aces=rig.teams["aces"], other_sport=other_sport,
            )
        snap["after_change"] = await rig.row(eid)

    rig.hook(before=before_fill)
    try:
        stats = await rig.run_pass([rig.board_s()])
        row = await rig.row(eid)
        assert counters(stats) == {"fence_lost": 1}, stats
        assert row["xmin"] == snap["after_change"]["xmin"]
        assert {c: row[c] for c in COLS} == {c: snap["after_change"][c] for c in COLS}
    finally:
        await rig.sql("UPDATE teams SET sport_id = :s WHERE sport_id = :o", s=rig.sport_id, o=other_sport)
        await rig.sql("DELETE FROM sports WHERE id = :o", o=other_sport)


# ── W9: the exception contract, through the real caller ──────────────────────


async def _s_and_h(rig):
    s = await rig.add_event()
    h = await rig.add_event(espn_id=ESPN_H, home="Seattle Storm", away="Dallas Wings")
    return s, h


async def test_w9a_a_failure_after_the_update_rolls_the_fill_back_and_the_sibling_commits(rig):
    from app.utils import espn_participant_fill as fill

    s, h = await _s_and_h(rig)
    before = await rig.row(s)
    calls = {"n": 0}
    real = fill.set_committed_value

    def boom(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("injected after the UPDATE")
        return real(*a, **k)

    rig.monkeypatch.setattr(fill, "set_committed_value", boom)
    seen = {}

    async def after(session, event, result):
        if event.id == s:
            seen["orm"] = {c: getattr(event, c) for c in COLS}

    rig.hook(after=after)
    stats = await rig.run_pass([rig.board_s(), rig.board_h()])
    row = await rig.row(s)
    # H names two clubs already, so it reaches the seam and is refused on its own.
    assert counters(stats) == {"post_write_rolled_back": 1, "refused_not_both_placeholder": 1}
    assert stats["errors"] == []
    assert {c: row[c] for c in COLS} == {c: before[c] for c in COLS}
    assert seen["orm"] == {c: before[c] for c in COLS}
    assert (await rig.row(h))["broadcast_info"] == "SYN TV"


async def test_w9b_a_self_check_mismatch_rolls_back_the_same_way(rig):
    from app.utils import espn_participant_fill as fill

    s, h = await _s_and_h(rig)
    before = await rig.row(s)

    def mismatch(*a, **k):
        raise fill.FillPostWriteMismatch("injected")

    rig.monkeypatch.setattr(fill, "_self_check", mismatch)
    stats = await rig.run_pass([rig.board_s(), rig.board_h()])
    row = await rig.row(s)
    assert counters(stats) == {"post_write_rolled_back": 1, "refused_not_both_placeholder": 1}
    assert stats["errors"] == []
    assert {c: row[c] for c in COLS} == {c: before[c] for c in COLS}
    assert (await rig.row(h))["broadcast_info"] == "SYN TV"


async def test_w9c_a_later_gate_failing_rolls_back_the_sport_step_including_the_fill(rig):
    from app.utils import espn_helpers

    s, h = await _s_and_h(rig)
    before = await rig.row(s)
    real = espn_helpers.upsert_team

    async def upsert(session, team_name, *a, **k):
        if team_name == "Golden State Valkyries":
            raise RuntimeError("injected after the fill")
        return await real(session, team_name, *a, **k)

    rig.monkeypatch.setattr(espn_helpers, "upsert_team", upsert)
    stats = await rig.run_pass([rig.board_s(), rig.board_h()])
    row = await rig.row(s)
    assert counters(stats).get("filled") == 1
    assert any(e.startswith(f"scheduled_{SYN_SPORT}:") for e in stats["errors"])
    assert {c: row[c] for c in COLS} == {c: before[c] for c in COLS}
    assert (await rig.row(h))["broadcast_info"] is None


async def test_w9d_a_failing_post_rollback_refresh_propagates(rig):
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils import espn_participant_fill as fill

    s, h = await _s_and_h(rig)
    before = await rig.row(s)

    def boom(*a, **k):
        raise RuntimeError("injected after the UPDATE")

    real_refresh = AsyncSession.refresh

    async def refresh(self, instance, attribute_names=None, **k):
        if attribute_names == list(fill.FILL_COLUMNS):
            raise RuntimeError("injected refresh failure")
        return await real_refresh(self, instance, attribute_names=attribute_names, **k)

    rig.monkeypatch.setattr(fill, "set_committed_value", boom)
    rig.monkeypatch.setattr(AsyncSession, "refresh", refresh)
    stats = await rig.run_pass([rig.board_s(), rig.board_h()])
    row = await rig.row(s)
    assert "post_write_rolled_back" not in counters(stats)
    assert any(e.startswith(f"scheduled_{SYN_SPORT}:") for e in stats["errors"])
    assert {c: row[c] for c in COLS} == {c: before[c] for c in COLS}
    assert (await rig.row(h))["broadcast_info"] is None


async def test_w9e_a_siblings_pending_failure_surfaces_at_the_pre_flush_outside_the_catch(rig):
    s, _ = await _s_and_h(rig)
    before = await rig.row(s)

    async def before_fill(session, event):
        event.broadcast_info = "x" * 300  # varchar(255): fails at flush, not here

    rig.hook(before=before_fill)
    stats = await rig.run_pass([rig.board_s()])
    row = await rig.row(s)
    assert counters(stats) == {}
    assert any(e.startswith(f"scheduled_{SYN_SPORT}:") for e in stats["errors"])
    assert {c: row[c] for c in COLS} == {c: before[c] for c in COLS}


async def test_a_later_gate_that_moves_a_filled_side_is_counted_and_restore_refuses_it(rig):
    """§3.8 ``regate_disagree``: a same-NAME row with no ESPN id is invisible to
    the fill's uniqueness fence (it fences ESPN ids), but ``upsert_team``
    resolves by name, and the #1918 gate finds the binding sound. Counted, and
    the receipt no longer matches, so restore refuses — never silent."""
    from app.models.models import Team
    from app.utils import espn_helpers

    async with rig.maker() as s:
        dupe = Team(name="Golden State Valkyries", sport_id=rig.sport_id, espn_id=None)
        s.add(dupe)
        await s.commit()
        dupe_id = dupe.id
    real = espn_helpers.upsert_team

    async def upsert(session, team_name, *a, **k):
        if team_name == "Golden State Valkyries":
            return await session.get(Team, dupe_id)
        return await real(session, team_name, *a, **k)

    rig.monkeypatch.setattr(espn_helpers, "upsert_team", upsert)
    eid = await rig.add_event()
    stats = await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    assert counters(stats) == {"filled": 1, "regate_disagree": 1}
    assert row["home_team_id"] == dupe_id
    rig.listed(eid)
    code, lines = await rig.restore(eid)
    assert code == 1 and "after_drift:home_team_id" in refusals(lines)


async def test_w10_a_second_pass_does_not_fill_again(rig):
    eid, row1 = await _fill(rig)
    stats = await rig.run_pass([rig.board_s()])
    row2 = await rig.row(eid)
    assert counters(stats) == {"refused_prior_fill_present": 1}
    assert row2["xmin"] == row1["xmin"] and len(fill_tags(row2)) == 1


async def test_w15_a_pending_orm_change_is_flushed_not_discarded(rig):
    eid = await rig.add_event()

    async def before_fill(session, event):
        event.event_tags = list(event.event_tags) + ["provenance:test-pending"]

    rig.hook(before=before_fill)
    await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    (tag,) = fill_tags(row)
    assert row["event_tags"] == ["status:upcoming", "provenance:test-pending", tag]


# ── W13: restore ─────────────────────────────────────────────────────────────


async def _seed_filled(rig, tags):
    return await rig.add_event(
        home="Golden State Valkyries", away="Las Vegas Aces",
        home_team_id=rig.teams["valk"], away_team_id=rig.teams["aces"], event_tags=tags,
    )


def _good_tag(rig, **prior):
    from app.utils.espn_participant_fill import encode_fill_tag

    receipt = {
        "after": {"away_name": "Las Vegas Aces", "away_tid": rig.teams["aces"],
                  "home_name": "Golden State Valkyries", "home_tid": rig.teams["valk"]},
        "filled_at": "2031-10-03T14:50:00Z",
        "prior": {"away_name": "TBD", "away_norm": None, "home_name": "TBD", "home_norm": None, **prior},
    }
    return encode_fill_tag(ESPN_S, AWAY_TID, HOME_TID, receipt)


@pytest.mark.parametrize(
    "case, expect",
    [
        ("absent", "receipt_absent"),
        ("duplicate", "receipt_duplicate"),
        ("no_r1", "receipt_invalid:r1"),
        ("corrupt_pct", "receipt_invalid:percent"),
        ("missing_prior_key", "receipt_invalid:keys"),
    ],
)
async def test_w13a_an_incomplete_receipt_refuses_with_no_write(rig, case, expect):
    from urllib.parse import quote

    good = _good_tag(rig)
    head, pct = good.rsplit(":r1=", 1)
    receipt = json.loads(__import__("urllib.parse").parse.unquote(pct))
    del receipt["prior"]["home_norm"]
    tags = {
        "absent": ["status:upcoming"],
        "duplicate": [good, good],
        "no_r1": [head],
        "corrupt_pct": [good + "%zz"],
        "missing_prior_key": [head + ":r1=" + quote(
            json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False), safe=""
        )],
    }[case]
    eid = await _seed_filled(rig, tags)
    rig.listed(eid)
    before = await rig.row(eid)
    code, lines = await rig.restore(eid)
    assert code == 1 and expect in refusals(lines)
    assert (await rig.row(eid))["xmin"] == before["xmin"]


async def test_w13b_a_non_tbd_prior_is_restored_to_its_exact_bytes(rig):
    eid, filled = await _fill(rig, home=" TBA ", away="To Be Announced", home_team_normalized="tbd")
    rig.listed(eid)
    code, lines = await rig.restore(eid)
    row = await rig.row(eid)
    assert code == 0, lines
    assert (row["home_team_name"], row["away_team_name"]) == (" TBA ", "To Be Announced")
    assert (row["home_team_normalized"], row["away_team_normalized"]) == ("tbd", None)
    assert (row["home_team_id"], row["away_team_id"]) == (None, None)
    assert fill_tags(row) == [] and len(markers(row)) == 1


async def test_w13c_restore_after_the_w1b_prime_fill_succeeds(rig):
    await rig.sql("UPDATE teams SET name = 'Golden St Valkyries' WHERE id = :i", i=rig.teams["valk"])
    eid, _ = await _fill(rig)
    rig.listed(eid)
    code, lines = await rig.restore(eid)
    assert code == 0, lines
    assert (await rig.row(eid))["home_team_name"] == "TBD"


DRIFT = {
    "home_team_name": "UPDATE events SET home_team_name = 'Golden State Valkyries' WHERE id = :i",
    "away_team_id": "UPDATE events SET away_team_id = :wings WHERE id = :i",
    "home_team_normalized": "UPDATE events SET home_team_normalized = 'Golden St Valkyries' WHERE id = :i",
    "away_team_alt_names": "UPDATE events SET away_team_alt_names = '[\"Aces\"]'::jsonb WHERE id = :i",
    "espn_id": "UPDATE events SET espn_id = '99030598' WHERE id = :i",
    "status": "UPDATE events SET status = 'live' WHERE id = :i",
}
DRIFT_REFUSAL = {
    "home_team_name": "after_drift:home_team_name",
    "away_team_id": "after_drift:away_team_id",
    "home_team_normalized": "after_drift:home_team_normalized",
    "away_team_alt_names": "after_drift:away_team_alt_names",
    "espn_id": "espn_id_drift",
    "status": "not_scheduled",
}


@pytest.mark.parametrize("drift", sorted(DRIFT))
async def test_w13d_drift_after_the_fill_refuses_with_no_write(rig, drift):
    # "Golden St Valkyries" is our spelling, so the home-name drift is ESPN's
    # spelling applied by a later pass (#9482) — a write the fill did not make.
    await rig.sql("UPDATE teams SET name = 'Golden St Valkyries' WHERE id = :i", i=rig.teams["valk"])
    eid, _ = await _fill(rig)
    await rig.sql(DRIFT[drift], i=eid, wings=rig.teams["wings"])
    rig.listed(eid)
    before = await rig.row(eid)
    code, lines = await rig.restore(eid)
    assert code == 1 and DRIFT_REFUSAL[drift] in refusals(lines), lines
    assert (await rig.row(eid))["xmin"] == before["xmin"]


async def test_w13e_the_dry_run_writes_nothing(rig):
    eid, filled = await _fill(rig)
    rig.listed(eid)
    code, lines = await rig.restore(eid, apply=False)
    assert code == 0 and refusals(lines) == [], lines
    assert any("home_team_name" in line and "-> 'TBD'" in line for line in lines)
    assert (await rig.row(eid))["xmin"] == filled["xmin"]


async def test_w13f_a_tag_added_after_the_fill_survives_at_its_index(rig):
    eid, _ = await _fill(rig)
    await rig.sql(
        "UPDATE events SET event_tags = event_tags || '[\"provenance:later\"]'::jsonb WHERE id = :i", i=eid
    )
    filled = await rig.row(eid)
    rig.listed(eid)
    code, lines = await rig.restore(eid)
    row = await rig.row(eid)
    assert code == 0, lines
    idx = filled["event_tags"].index(fill_tags(filled)[0])
    assert row["event_tags"][idx] == markers(row)[0]
    assert markers(row)[0].split(":", 2)[2] == fill_tags(filled)[0].split(":", 2)[2]
    assert [t for i, t in enumerate(row["event_tags"]) if i != idx] == [
        t for i, t in enumerate(filled["event_tags"]) if i != idx
    ]


# ── W14: fill → restore → the next scheduled pass ────────────────────────────


async def test_w14a_a_listed_restored_row_is_refused_by_the_next_pass(rig):
    eid, _ = await _fill(rig)
    rig.listed(eid)
    code, lines = await rig.restore(eid)
    assert code == 0, lines
    restored = await rig.row(eid)
    stats = await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    assert counters(stats) == {"refused_restore_denylisted": 1}
    assert row["xmin"] == restored["xmin"]
    assert len(markers(row)) == 1 and fill_tags(row) == []


async def test_w14b_the_marker_survives_the_real_tag_refresh_and_the_pass_still_refuses(rig):
    from contextlib import asynccontextmanager

    from app.tasks import taxonomy

    eid, _ = await _fill(rig)
    rig.listed(eid)
    assert (await rig.restore(eid))[0] == 0

    @asynccontextmanager
    async def session_cm():
        async with rig.maker() as s:
            yield s
            await s.commit()

    class _Cursor:  # the drain arm's keyset cursor; no Redis in this job
        def __init__(self):
            self.kv = {}

        def get(self, key):
            return self.kv.get(key)

        def set(self, key, value, *a, **k):
            self.kv[key] = value

        def setex(self, key, ttl, value):
            self.kv[key] = value

        def delete(self, *keys):
            for key in keys:
                self.kv.pop(key, None)

    rig.monkeypatch.setattr(taxonomy, "get_task_session", session_cm)
    rig.monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: _Cursor())
    await taxonomy._update_event_tags_impl(limit=5000)
    after_refresh = await rig.row(eid)
    assert len(markers(after_refresh)) == 1
    stats = await rig.run_pass([rig.board_s()])
    assert counters(stats) == {"refused_restore_denylisted": 1}
    assert (await rig.row(eid))["xmin"] == after_refresh["xmin"]


async def _stale_loader(rig, eid):
    """A session built like ``get_task_session`` (expire_on_commit=False)."""
    from sqlalchemy.orm import selectinload

    from app.models.models import Event

    session = rig.maker()
    event = (await session.execute(
        select(Event).options(selectinload(Event.sport)).where(Event.id == eid)
    )).scalar_one()
    return session, event


async def _refresh_shape_flush(session, event):
    from app.tasks.taxonomy import _tag_event
    from app.utils.event_taxonomy import carry_provenance_tags

    event.event_tags = carry_provenance_tags(event.event_tags, _tag_event(event))  # taxonomy.py L75
    await session.commit()
    await session.close()


async def _enricher_shape_flush(session, event):
    from app.utils.event_taxonomy import merge_llm_tags

    event.event_tags = merge_llm_tags(event.event_tags or [], [LLM_TAG])  # taxonomy.py L657
    await session.commit()
    await session.close()


async def _verdict_now(rig, eid, board):
    from app.models.models import Event, Team
    from app.utils.espn_participant_fill import build_team_index, participant_fill_verdict

    async with rig.maker() as s:
        event = (await s.execute(select(Event).where(Event.id == eid))).scalar_one()
        teams = (await s.execute(select(Team).where(Team.sport_id == rig.sport_id))).scalars().all()
        return participant_fill_verdict(event, board, build_team_index(teams))


@pytest.mark.parametrize("shape", ["refresh", "enricher"])
@pytest.mark.parametrize("filled_ago", [timedelta(minutes=16), timedelta(days=1)])
@pytest.mark.parametrize("control", [False, True], ids=["treatment", "control"])
async def test_w14d_a_stale_writer_erases_every_tag_and_the_code_fence_still_refuses(
    rig, shape, filled_ago, control
):
    from app.utils import espn_participant_fill as fill

    eid = await rig.add_event()
    stale_session, stale_event = await _stale_loader(rig, eid)
    if shape == "enricher":
        await stale_session.commit()  # its transaction ends; its objects stay loaded
    rig.monkeypatch.setattr(fill, "_utcnow", lambda: datetime.now(timezone.utc) - filled_ago)
    stats1 = await rig.run_pass([rig.board_s()])
    assert counters(stats1) == {"filled": 1}
    rig.listed(eid)
    code, lines = await rig.restore(eid)
    assert code == 0, lines
    flush = _refresh_shape_flush if shape == "refresh" else _enricher_shape_flush
    await flush(stale_session, stale_event)
    erased = await rig.row(eid)
    assert fill_tags(erased) == [] and markers(erased) == []
    assert (erased["home_team_name"], erased["away_team_name"], erased["home_team_id"]) == ("TBD", "TBD", None)
    rig.monkeypatch.setattr(fill, "RESTORED_FILL_EVENT_IDS", frozenset())
    assert (await _verdict_now(rig, eid, rig.board_s())).action == "fill"  # every row-level check passes
    rig.monkeypatch.setattr(fill, "RESTORED_FILL_EVENT_IDS", frozenset() if control else frozenset({eid}))
    stats2 = await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    if control:  # a person reverted the refusal: the stale commit really re-created an eligible row
        assert counters(stats2) == {"filled": 1}
    else:
        assert counters(stats2) == {"refused_restore_denylisted": 1}
        assert row["xmin"] == erased["xmin"]


async def test_w14c_the_r2_interleavings_under_the_code_fence(rig):
    # (1) loaded after the fill, flushed after the restore
    eid, _ = await _fill(rig)
    stale_session, stale_event = await _stale_loader(rig, eid)
    rig.listed(eid)
    assert (await rig.restore(eid))[0] == 0
    await _refresh_shape_flush(stale_session, stale_event)
    stats = await rig.run_pass([rig.board_s()])
    assert counters(stats) == {"refused_restore_denylisted": 1}
    code, lines = await rig.restore(eid)
    assert code == 1 and "after_drift:home_team_name" in refusals(lines)
    await rig.sql("DELETE FROM events WHERE id = :i", i=eid)

    # (2) loaded before the fill, flushed after the fill and before the restore
    eid = await rig.add_event()
    stale_session, stale_event = await _stale_loader(rig, eid)
    assert counters(await rig.run_pass([rig.board_s()])) == {"filled": 1}
    await _refresh_shape_flush(stale_session, stale_event)
    rig.listed(eid)
    before = await rig.row(eid)
    code, lines = await rig.restore(eid)
    assert code == 1 and "receipt_absent" in refusals(lines)
    assert counters(await rig.run_pass([rig.board_s()])) == {"refused_restore_denylisted": 1}
    after = await rig.row(eid)
    assert after["xmin"] == before["xmin"] and after["home_team_name"] == "Golden State Valkyries"
    await rig.sql("DELETE FROM events WHERE id = :i", i=eid)

    # (3) loaded after the fill, flushed before the restore
    rig.listed()
    eid, _ = await _fill(rig)
    stale_session, stale_event = await _stale_loader(rig, eid)
    await _refresh_shape_flush(stale_session, stale_event)
    rig.listed(eid)
    code, lines = await rig.restore(eid)
    assert code == 0, lines
    assert counters(await rig.run_pass([rig.board_s()])) == {"refused_restore_denylisted": 1}


async def test_w14e_restore_refuses_an_id_the_code_does_not_list(rig):
    eid, filled = await _fill(rig)
    code, lines = await rig.restore(eid)
    assert code == 1 and "not_denylisted" in refusals(lines)
    code, lines = await rig.restore(eid, apply=False)
    assert code == 1 and "not_denylisted" in refusals(lines)
    assert (await rig.row(eid))["xmin"] == filled["xmin"]


@pytest.mark.parametrize(
    "env_kw, proof, expect",
    [
        (dict(age_s=30), "valid", "release_too_young"),
        (dict(HEROKU_RELEASE_CREATED_AT=None), "valid", "release_age_unknown"),
        (dict(HEROKU_RELEASE_CREATED_AT="soon"), "valid", "release_age_unknown"),
        (dict(age_s=185), None, "retirement_proof_absent"),  # W14f(c): age is not sufficient
    ],
)
async def test_w14f_release_age_is_checked_and_never_sufficient(rig, env_kw, proof, expect):
    eid, filled = await _fill(rig)
    rig.listed(eid)
    code, lines = await rig.restore(eid, proof=proof, env=rig.env(**env_kw))
    assert code == 1 and expect in refusals(lines), lines
    assert (await rig.row(eid))["xmin"] == filled["xmin"]


async def test_w14g_an_old_pass_that_loaded_before_the_restore_cannot_refill(rig):
    from app.utils import espn_participant_fill as fill

    eid, _ = await _fill(rig)
    rig.listed(eid, fill_side=False)  # the old pass runs the previous slug: empty set

    async def before_fill(session, event):
        code, lines = await rig.restore(eid)
        assert code == 0, lines

    rig.hook(before=before_fill)
    stats = await rig.run_pass([rig.board_s()])
    restored = await rig.row(eid)
    assert counters(stats) == {"refused_prior_fill_present": 1}
    assert restored["home_team_name"] == "TBD" and len(markers(restored)) == 1

    # With the verdict bypassed, the WHERE still refuses: the loaded names are real.
    await rig.sql("DELETE FROM events WHERE id = :i", i=eid)
    rig.unhook()
    rig.listed()
    eid, _ = await _fill(rig)
    rig.listed(eid, fill_side=False)
    real_verdict = fill.participant_fill_verdict

    def bypass(event, ee, team_index):
        v = real_verdict(event, ee, team_index)
        if v.reason != "prior_fill_present":
            return v
        teams = {t.espn_id: t for rows in team_index.values() for t in rows}
        return fill.FillVerdict(
            action=fill.FILL, reason="fill", home_team=teams[HOME_TID], away_team=teams[AWAY_TID],
            home_espn_tid=HOME_TID, away_espn_tid=AWAY_TID,
        )

    rig.monkeypatch.setattr(fill, "participant_fill_verdict", bypass)
    rig.hook(before=before_fill)
    stats = await rig.run_pass([rig.board_s()])
    row = await rig.row(eid)
    assert counters(stats) == {"fence_lost": 1}
    assert row["home_team_name"] == "TBD" and fill_tags(row) == []


# ── W14h: the delayed-release, old-code, POST-restore load ───────────────────


async def _w14h_setup(rig):
    """Pass 1 fills; T (enricher shape) loaded BEFORE it; the restore slug lists the id."""
    eid = await rig.add_event()
    stale_session, stale_event = await _stale_loader(rig, eid)
    await stale_session.commit()
    assert counters(await rig.run_pass([rig.board_s()])) == {"filled": 1}
    rig.listed(eid, fill_side=False)  # restore runs from the new slug
    return eid, stale_session, stale_event


async def _old_pass(rig, eid):
    """O: the actual pass with the previous slug's EMPTY set."""
    from app.utils import espn_participant_fill as fill

    rig.monkeypatch.setattr(fill, "RESTORED_FILL_EVENT_IDS", frozenset())
    return await rig.run_pass([rig.board_s()])


def _w14h_env(rig):
    return rig.env(age_s=185)  # the supplementary age check PASSES in every leg


async def test_w14h_i_hazard_control_r3s_admission_lets_the_old_worker_refill(rig):
    from scripts import restore_espn_participant_fill as restore

    eid, stale_session, stale_event = await _w14h_setup(rig)
    async with rig.maker() as s:  # r3's admission exactly: row refusals + age, no proof
        row = await restore._read_row(s, eid, lock=True)
        now = await restore._lock_now(s)
        adm = restore.admit_row(row, event_id=eid)
        assert adm.refusals == []
        assert restore.release_age_refusal(_w14h_env(rig)["HEROKU_RELEASE_CREATED_AT"], now) is None
        assert await restore._write(s, row, adm) == []
        await s.commit()
    await _enricher_shape_flush(stale_session, stale_event)
    erased = await rig.row(eid)
    assert markers(erased) == [] and fill_tags(erased) == []
    stats = await _old_pass(rig, eid)
    row = await rig.row(eid)
    assert counters(stats) == {"filled": 1}, "the hazard is not real; the treatment legs prove nothing"
    assert row["home_team_name"] == "Golden State Valkyries" and len(fill_tags(row)) == 1


async def test_w14h_ii_no_proof_refuses_before_the_write(rig):
    eid, stale_session, stale_event = await _w14h_setup(rig)
    filled = await rig.row(eid)
    code, lines = await rig.restore(eid, proof=None, env=_w14h_env(rig))
    assert code == 1 and "retirement_proof_absent" in refusals(lines)
    still = await rig.row(eid)
    assert still["xmin"] == filled["xmin"] and len(fill_tags(still)) == 1
    await _enricher_shape_flush(stale_session, stale_event)  # §4.4 row 3: names stay real
    t_row = await rig.row(eid)
    assert fill_tags(t_row) == [] and t_row["home_team_name"] == "Golden State Valkyries"
    stats = await _old_pass(rig, eid)
    assert counters(stats) == {"refused_not_both_placeholder": 1}
    assert (await rig.row(eid))["xmin"] == t_row["xmin"]


def _w14h_bad_proofs(rig, eid, now):
    up_old = new_instance(version=5499, commit="c" * 40, carries=False)
    return {
        "retirement_unproven:worker-realtime.1": dict(main=[up_old, new_instance(dyno="worker-realtime.2")],
                                                      main_formation=2),
        "retirement_after_lock:worker-realtime.1": dict(
            main=[old_instance(now - timedelta(seconds=5)), new_instance()], captured_ago=1),
        "retirement_after_lock:worker-realtime.1#sigterm": dict(
            main=[old_instance(now - timedelta(seconds=20), evidence="sigterm"), new_instance()],
            captured_ago=1),
        "replacement_absent:bainluck:worker-realtime": dict(main=[old_instance(now - timedelta(seconds=60))]),
        "replacement_not_carrying:worker-realtime.1": dict(
            main=[old_instance(now - timedelta(seconds=60), dyno="worker-realtime.9"),
                  new_instance(version=5498, commit="e" * 40)]),
        "retirement_unproven:worker-realtime.1#heavy": dict(
            heavy=[new_instance(version=40, commit="f" * 40, carries=False)], heavy_formation=1),
        "retirement_proof_stale_release": dict(main_version=5501),
        "retirement_proof_stale": dict(captured_ago=901),
        "retirement_window_short:bainluck": dict(window=299),
        "retirement_proof_invalid:apps": dict(drop_heavy=True),
    }


W14H_LEGS = [
    "retirement_unproven:worker-realtime.1",
    "retirement_after_lock:worker-realtime.1",
    "retirement_after_lock:worker-realtime.1#sigterm",
    "replacement_absent:bainluck:worker-realtime",
    "replacement_not_carrying:worker-realtime.1",
    "retirement_unproven:worker-realtime.1#heavy",
    "retirement_proof_stale_release",
    "retirement_proof_stale",
    "retirement_window_short:bainluck",
    "retirement_proof_invalid:apps",
    "release_metadata_unknown",
]


@pytest.mark.parametrize("leg", W14H_LEGS)
async def test_w14h_iii_an_open_late_or_uncarried_proof_refuses_before_the_write(rig, leg):
    eid, stale_session, stale_event = await _w14h_setup(rig)
    filled = await rig.row(eid)
    now = datetime.now(timezone.utc)
    env = _w14h_env(rig)
    if leg == "release_metadata_unknown":
        env.pop("HEROKU_SLUG_COMMIT")
        proof = rig.proof(eid)
    else:
        proof = rig.proof(eid, **_w14h_bad_proofs(rig, eid, now)[leg])
    code, lines = await rig.restore(eid, proof=proof, env=env)
    assert code == 1 and leg.split("#")[0] in refusals(lines), lines
    assert (await rig.row(eid))["xmin"] == filled["xmin"]
    await stale_session.close()
    stats = await _old_pass(rig, eid)
    assert "filled" not in counters(stats)
    assert (await rig.row(eid))["xmin"] == filled["xmin"]


async def test_w14h_iv_with_a_valid_proof_only_carrying_code_runs_and_it_refuses(rig):
    from app.utils import espn_participant_fill as fill

    eid, stale_session, stale_event = await _w14h_setup(rig)
    code, lines = await rig.restore(eid, env=_w14h_env(rig))  # O exited 60 s before the lock
    assert code == 0, lines
    await _enricher_shape_flush(stale_session, stale_event)
    erased = await rig.row(eid)
    assert markers(erased) == [] and fill_tags(erased) == []
    rig.monkeypatch.setattr(fill, "RESTORED_FILL_EVENT_IDS", frozenset({eid}))  # N: the carrying slug
    stats = await rig.run_pass([rig.board_s()])
    assert counters(stats) == {"refused_restore_denylisted": 1}
    assert (await rig.row(eid))["xmin"] == erased["xmin"]
