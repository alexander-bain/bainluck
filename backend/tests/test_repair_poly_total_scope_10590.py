"""#10590 — the repair re-grades mis-scoped `poly_total_score` rows from the venue.

The CLOB payload below is the specimen's own, fetched 2026-10-06 from
``clob.polymarket.com/markets/0xf0f014d8…`` ("San Diego Padres Team Total: O/U
3.5", SD scored 3): Under is the winner token. The stored grade was Over-won.
"""

from unittest.mock import MagicMock

import pytest

import app.tasks.repair_poly_total_scope as rp

COND = "0xf0f014d8adc07162aa919fbf286c7d9a785e0a5d07644d40d29bc15bb5557b65"
NAME = "San Diego Padres Team Total: O/U 3.5"
CLOB = {
    "question": NAME,
    "closed": True,
    "condition_id": COND,
    "tokens": [
        {"token_id": "1267", "outcome": "Over", "price": 0, "winner": False},
        {"token_id": "1089", "outcome": "Under", "price": 1, "winner": True},
    ],
}


def _legs(src="poly_total_score", over_won=True):
    return [
        {"id": 241493298, "name": "Over", "external_id": f"{COND}_yes",
         "is_winner": over_won, "resolution_source": src},
        {"id": 241493299, "name": "Under", "external_id": f"{COND}_no",
         "is_winner": not over_won, "resolution_source": src},
    ]


def test_the_specimen_regrades_to_under_from_the_venue():
    d = rp.decide(NAME, _legs(), CLOB)
    assert d["action"] == "regrade"
    assert d["winner_id"] == 241493299 and d["winner"] == "Under"
    assert d["verdict_changes"] is True


def test_a_venue_answer_that_agrees_is_a_confirmation_not_a_flip():
    d = rp.decide(NAME, _legs(over_won=False), CLOB)
    assert d["action"] == "regrade" and d["verdict_changes"] is False


@pytest.mark.parametrize("legs,clob,reason", [
    (_legs(src="api_settlement"), CLOB, "foreign_authority"),
    (_legs()[:1], CLOB, "mixed_sources"),
    ([_legs()[0], {**_legs()[1], "resolution_source": None}], CLOB, "mixed_sources"),
    (_legs(), None, "clob_missing"),
    (_legs(), {**CLOB, "question": "Will the Fed cut rates in March?"}, "name_discordant"),
    (_legs(), {**CLOB, "tokens": [{**t, "winner": False} for t in CLOB["tokens"]]}, "void"),
])
def test_every_unprovable_market_is_skipped_by_name(legs, clob, reason):
    d = rp.decide(NAME, legs, clob)
    assert d == {**d, "action": "skip", "reason": reason}, d


def test_condition_id_comes_from_the_market_or_a_leg_suffix():
    assert rp.condition_id_of(COND, []) == COND
    assert rp.condition_id_of("64157611", _legs()) == COND
    assert rp.condition_id_of(None, [{"external_id": "kalshi-x"}]) is None


# ---------------------------------------------------------------------------
# the page loop, against a fake session and a fake CLOB
# ---------------------------------------------------------------------------

class _Res:
    def __init__(self, rows=(), rowcount=None):
        self._rows = list(rows)
        self.rowcount = rowcount if rowcount is not None else len(self._rows)

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._rows[0][0]


def _mrow(**kw):
    m = MagicMock()
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def _legrow(d):
    m = MagicMock()
    m._mapping = d
    return m


class _Session:
    """Answers the page, the legs, the backup copy and the write; records writes.

    ``cas_refuses`` names leg ids another writer graded between our backup and
    our write: the compare-and-set skips them, so they must be pruned.
    """

    def __init__(self, page, legs_by_market, cas_refuses=()):
        self.page = page
        self.legs = legs_by_market
        self.cas_refuses = set(cas_refuses)
        self.writes = []
        self.pruned = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "FROM futures_markets m" in sql:
            return _Res(self.page)
        if "FROM futures_outcomes\n    WHERE market_id = :mid" in sql:
            return _Res([_legrow(d) for d in self.legs[params["mid"]]])
        if sql.lstrip().startswith(f"INSERT INTO {rp.BAK_TABLE}"):
            return _Res([(i,) for i in params["ids"]])
        if sql.lstrip().startswith("UPDATE futures_outcomes fo"):
            kept = [i for i in params["ids"] if i not in self.cas_refuses]
            self.writes.append((kept, params["winner_id"]))
            return _Res([(i,) for i in kept])
        if sql.lstrip().startswith(f"DELETE FROM {rp.BAK_TABLE}"):
            self.pruned.extend(params["ids"])
        return _Res()

    async def commit(self):
        self.commits += 1


class _Clob:
    def __init__(self, answers, raise_on=()):
        self.answers = answers
        self.raise_on = set(raise_on)
        self.asked = []

    async def get_clob_market_by_condition(self, cond):
        self.asked.append(cond)
        if cond in self.raise_on:
            raise RuntimeError("429 Too Many Requests")
        return self.answers.get(cond)


@pytest.fixture
def clob(monkeypatch):
    import app.services.polymarket_api as pa

    holder = {}

    def _factory():
        return holder["clob"]

    monkeypatch.setattr(pa, "PolymarketAPIService", _factory)
    return holder


def _page():
    return [
        # a full-game grade: right quantity, never touched, never fetched
        _mrow(market_id=64157600, market_ext="0xfull",
              market_name="San Diego Padres vs. Milwaukee Brewers: O/U 6.5"),
        _mrow(market_id=64157611, market_ext=COND, market_name=NAME),
    ]


async def test_dry_run_plans_the_regrade_and_writes_nothing(clob):
    clob["clob"] = _Clob({COND: CLOB})
    s = _Session(_page(), {64157611: _legs()})
    out = await rp.repair(s, apply=False)
    assert clob["clob"].asked == [COND]
    assert out["in_scope"] == 1 and out["regraded"] == 1
    assert out["verdicts_changed"] == 1 and out["legs_written"] == 0
    assert s.writes == [] and out["exhausted"] is True
    assert out["next_after_id"] == 64157611


async def test_apply_writes_the_venue_winner_behind_its_backup(clob):
    clob["clob"] = _Clob({COND: CLOB})
    s = _Session(_page(), {64157611: _legs()})
    out = await rp.repair(s, apply=True)
    assert s.writes == [([241493298, 241493299], 241493299)]
    assert out["legs_written"] == 2 and s.commits == 1 and s.pruned == []


async def test_a_leg_another_writer_graded_is_conceded_and_its_backup_pruned(clob):
    clob["clob"] = _Clob({COND: CLOB})
    s = _Session(_page(), {64157611: _legs()}, cas_refuses={241493298})
    out = await rp.repair(s, apply=True)
    assert s.pruned == [241493298]
    assert out["conceded_to_another_writer"] == 1 and out["legs_written"] == 1


async def test_a_clob_error_stops_before_the_market_so_it_is_retried(clob):
    clob["clob"] = _Clob({}, raise_on={COND})
    s = _Session(_page(), {64157611: _legs()})
    out = await rp.repair(s, apply=True)
    assert s.writes == []
    assert out["stopped_on"].startswith("clob_error")
    assert out["exhausted"] is False
    assert out["next_after_id"] == 64157600  # resume AT the failed market


def test_the_rail_is_dispatched_with_its_undo():
    from app.routes.admin_repairs import _REPAIRS

    assert _REPAIRS["poly-total-scope"] == ("app.tasks.repair_poly_total_scope", "repair")
    assert _REPAIRS["poly-total-scope-restore"] == (
        "app.tasks.repair_poly_total_scope", "restore")


def test_the_write_is_a_compare_and_set_joined_to_the_backup():
    sql = " ".join(rp._APPLY_SQL.split())
    assert f"FROM {rp.BAK_TABLE} b WHERE b.outcome_id = fo.id" in sql
    assert "AND fo.resolution_source = 'poly_total_score'" in sql
    assert "resolution_source = 'clob_authoritative'" in sql


def test_the_restore_only_touches_rows_still_carrying_our_write():
    sql = " ".join(rp._RESTORE_SQL.split())
    assert "AND fo.resolution_source = 'clob_authoritative'" in sql
