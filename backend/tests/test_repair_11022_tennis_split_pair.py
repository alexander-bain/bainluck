"""#11022 — the attended repair moves ONE Kalshi market onto the reviewed row,
only while every witness still holds, and the undo puts it back.

The specimen state is the production read of 2026-10-13 22:4xZ (db-query on
events 15329605 / 15329612, markets 65624229 / 65633052 and their outcomes).
Every refusal is paired with the specimen it must not refuse.
"""

import copy
from datetime import datetime, timezone

import pytest

from scripts import repair_11022_tennis_split_pair as r

NOW = datetime(2026, 10, 13, 22, 45, tzinfo=timezone.utc)


def _state():
    return {
        "market": {
            "id": r.MARKET_ID, "source": "kalshi", "external_id": r.TICKER,
            "name": "Justo vs Huertas Del Pino Cordova", "event_id": r.FROM_EVENT_ID,
            "llm_sport_category": "tennis", "competition": "ATP Challenger Santa Cruz 2",
        },
        "outcomes": ["Guido Ivan Justo", "Arklon Huertas Del Pino Cordova"],
        "from_row": {
            "id": r.FROM_EVENT_ID, "status": "live", "external_id": None,
            "espn_id": None, "statpal_fixture_id": None, "home_score": None,
            "away_score": None, "completed_at": None,
            "commence_time": datetime(2026, 10, 13, 22, 10, tzinfo=timezone.utc),
            "commence_time_source": "kalshi", "home_team_name": "Justo",
            "away_team_name": "Huertas Del Pino Cordova", "sport_id": 2,
            "sport_key": "tennis_atp",
        },
        "to_row": {
            "id": r.TO_EVENT_ID, "status": "live", "external_id": None,
            "espn_id": None, "statpal_fixture_id": None, "home_score": None,
            "away_score": None, "completed_at": None,
            "commence_time": datetime(2026, 10, 13, 21, 0, tzinfo=timezone.utc),
            "commence_time_source": "polymarket_venue", "home_team_name": "Guido Justo",
            "away_team_name": "Arklon Del Pino", "sport_id": 1, "sport_key": "tennis_other",
        },
        "from_market_ids": [r.MARKET_ID],
        "to_markets": [
            {"id": 65624229, "source": "polymarket", "external_id": r.PM_CONDITION,
             "name": "Santa Cruz 2: Guido Justo vs Arklon Del Pino"},
            {"id": 65624230, "source": "polymarket", "external_id": "0xe41c",
             "name": "Set 1 Winner: Guido Justo vs Arklon Del Pino"},
        ],
    }


def _decide(state):
    return r.decide(now=NOW, **state)


class TestTheSpecimen:
    def test_the_production_state_clears_every_witness(self):
        v = _decide(_state())
        assert v["refusals"] == []
        w = v["witness"]
        assert w["contracts"] == ["Guido Ivan Justo", "Arklon Huertas Del Pino Cordova"]
        assert w["yes_is_home"] is True
        assert w["tournament_label"] == "santa cruz 2"

    def test_the_digest_binds_the_witness(self):
        a = r.plan_digest(_decide(_state())["witness"])
        moved = _state()
        moved["to_row"]["home_team_name"], moved["to_row"]["away_team_name"] = (
            "Arklon Del Pino", "Guido Justo")
        b = r.plan_digest(_decide(moved)["witness"])
        assert a == r.plan_digest(_decide(_state())["witness"])
        assert a != b, "a flipped home side must change the reviewed plan"


def _mutate(path, value):
    state = _state()
    obj = state
    for key in path[:-1]:
        obj = obj[key]
    obj[path[-1]] = value
    return state


@pytest.mark.parametrize("state,reason", [
    (_mutate(("market", "event_id"), 999), "market_not_on_from_event"),
    (_mutate(("market", "source"), "polymarket"), "market_is_not_the_reviewed_kalshi_ticker"),
    (_mutate(("from_row", "espn_id"), "401"), "from_event_carries_a_provider_id"),
    (_mutate(("from_row", "home_score"), 2), "from_event_carries_a_result"),
    (_mutate(("from_row", "status"), "merged"), "from_event_retired"),
    (_mutate(("from_row", "commence_time_source"), "odds_api"), "from_event_not_kalshi_born"),
    (_mutate(("from_market_ids",), [r.MARKET_ID, 1]), "from_event_holds_other_markets"),
    (_mutate(("to_row", "status"), "completed"), "to_event_not_scheduled_or_live"),
    (_mutate(("to_row", "sport_key"), "basketball_other"), "forward_gate_refuses_the_target"),
    (_mutate(("to_row", "away_team_name"), "Juan Del Pino"), "forward_gate_refuses_the_target"),
    (_mutate(("outcomes",), ["Guido Ivan Justo"]), "contracts_do_not_rename_both_title_sides"),
    (_mutate(("to_markets",), []), "to_event_lacks_the_user_polymarket_condition"),
    (_mutate(("market", "competition"), "ATP Challenger Lima"), "venues_do_not_name_one_tournament"),
    (_mutate(("to_row", "commence_time"), datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc)),
     "ticker_date_conflicts_with_target_start"),
])
def test_each_witness_refuses_on_its_own(state, reason):
    assert reason in _decide(state)["refusals"]


def test_a_missing_target_refuses():
    assert "to_event_missing" in _decide(_mutate(("to_row",), None))["refusals"]


def test_only_production_apps_run():
    with pytest.raises(r.Refused):
        r.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
    r.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})


class _Result:
    def __init__(self, rows=(), rowcount=0, scalar=None):
        self._rows, self.rowcount, self._scalar = list(rows), rowcount, scalar

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar


class FakeSession:
    """The script's handful of statements, over one market and one bank row."""

    def __init__(self, event_id=r.FROM_EVENT_ID, bank=None, table=True):
        self.event_id, self.bank, self.table = event_id, bank, table
        self.commits, self.rollbacks, self.writes = 0, 0, []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        p = params or {}
        if sql.startswith("CREATE TABLE"):
            self.writes.append("ddl")
            return _Result()
        if sql.startswith(f"INSERT INTO {r.BACKUP_TABLE}"):
            self.bank = self.bank or [p["b"], p["a"], None]
            self.writes.append("bank")
            return _Result(rowcount=1)
        if sql.startswith("SELECT event_id_before, event_id_after FROM"):
            return _Result([tuple(self.bank[:2])] if self.bank else [])
        if sql.startswith("SELECT event_id_before, event_id_after, applied_at"):
            return _Result([tuple(self.bank)] if self.bank else [])
        if sql.startswith("SELECT to_regclass"):
            return _Result(scalar=r.BACKUP_TABLE if self.table else None)
        if sql.startswith("UPDATE futures_markets SET event_id"):
            if self.event_id == p["old"]:
                self.event_id = p["new"]
                self.writes.append(("move", p["old"], p["new"]))
                return _Result(rowcount=1)
            return _Result(rowcount=0)
        if sql.startswith(f"UPDATE {r.BACKUP_TABLE} SET applied_at"):
            self.bank[2] = NOW
            return _Result(rowcount=1)
        if sql.startswith("SELECT event_id FROM futures_markets"):
            return _Result([(self.event_id,)])
        if sql.startswith("SELECT name FROM futures_markets"):
            return _Result([("Justo vs Huertas Del Pino Cordova",)])
        raise AssertionError(f"unexpected statement: {sql}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def wired(monkeypatch):
    state = {"value": _state()}

    async def read_state(session):
        return copy.deepcopy(state["value"])

    async def receipt(market, old, new):
        return 1

    async def drain(session, event_id):
        return r.TO_EVENT_ID if session.event_id == r.TO_EVENT_ID else None

    monkeypatch.setattr(r, "read_state", read_state)
    monkeypatch.setattr(r, "_receipt", receipt)
    import app.services.anchor_channel as ac
    monkeypatch.setattr(ac, "resolve_market_born_duplicate", drain)
    return state


class TestApply:
    @pytest.mark.asyncio
    async def test_dry_run_writes_nothing(self, wired):
        s = FakeSession()
        out = await r.run(s, apply=False, now=NOW)
        assert out["outcome"] == r.DRY_RUN and s.writes == [] and s.commits == 0

    @pytest.mark.asyncio
    async def test_the_reviewed_digest_moves_the_market_and_drains_the_row(self, wired):
        digest = (await r.run(FakeSession(), apply=False, now=NOW))["plan_digest"]
        s = FakeSession()
        out = await r.run(s, apply=True, expected_digest=digest, now=NOW)
        assert out["outcome"] == r.APPLIED, out
        assert s.event_id == r.TO_EVENT_ID
        assert out["drain_verdict"] == r.TO_EVENT_ID
        assert out["undo"] == r.UNDO_LINE

    @pytest.mark.asyncio
    async def test_a_stale_digest_refuses_before_the_backup(self, wired):
        s = FakeSession()
        with pytest.raises(r.Refused):
            await r.run(s, apply=True, expected_digest="0" * 64, now=NOW)
        assert s.writes == []

    @pytest.mark.asyncio
    async def test_a_refused_witness_refuses_before_the_backup(self, wired):
        digest = (await r.run(FakeSession(), apply=False, now=NOW))["plan_digest"]
        wired["value"]["from_row"]["home_score"] = 1
        s = FakeSession()
        with pytest.raises(r.Refused):
            await r.run(s, apply=True, expected_digest=digest, now=NOW)
        assert s.writes == []

    @pytest.mark.asyncio
    async def test_a_market_that_moved_under_the_run_rolls_back(self, wired):
        digest = (await r.run(FakeSession(), apply=False, now=NOW))["plan_digest"]
        s = FakeSession(event_id=12345)
        out = await r.run(s, apply=True, expected_digest=digest, now=NOW)
        assert out["outcome"] == r.ROLLED_BACK_CHANGED_UNDER_RUN
        assert s.event_id == 12345 and s.rollbacks == 1


class TestRestore:
    @pytest.mark.asyncio
    async def test_restore_puts_the_market_back(self, wired):
        s = FakeSession(event_id=r.TO_EVENT_ID, bank=[r.FROM_EVENT_ID, r.TO_EVENT_ID, NOW])
        out = await r.restore(s)
        assert out["outcome"] == r.RESTORED and s.event_id == r.FROM_EVENT_ID

    @pytest.mark.asyncio
    async def test_restore_never_moves_a_market_that_left_the_target(self, wired):
        s = FakeSession(event_id=777, bank=[r.FROM_EVENT_ID, r.TO_EVENT_ID, NOW])
        out = await r.restore(s)
        assert out["outcome"] == r.RESTORE_SHORT and s.event_id == 777

    @pytest.mark.asyncio
    async def test_an_unapplied_bank_restores_nothing(self, wired):
        s = FakeSession(event_id=r.FROM_EVENT_ID, bank=[r.FROM_EVENT_ID, r.TO_EVENT_ID, None])
        out = await r.restore(s)
        assert out["outcome"] == r.NOTHING_TO_RESTORE and s.writes == []
