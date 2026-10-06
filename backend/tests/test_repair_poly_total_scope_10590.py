"""#10590 — the repair re-grades mis-scoped `poly_total_score` rows from the venue.

The CLOB payload below is the specimen's own, fetched 2026-10-06 from
``clob.polymarket.com/markets/0xf0f014d8…`` ("San Diego Padres Team Total: O/U
3.5", SD scored 3): Under is the winner token. The stored grade was Over-won.
"""

import json
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
        self.sql = []

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.sql.append(sql)
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


# ---------------------------------------------------------------------------
# ledger evidence: the identity and venue answer each decision stood on
# ---------------------------------------------------------------------------

OVER_WON = {**CLOB, "tokens": [
    {"token_id": "1267", "outcome": "Over", "price": 1, "winner": True},
    {"token_id": "1089", "outcome": "Under", "price": 0, "winner": False},
]}


@pytest.mark.parametrize("clob_payload,winner_id,loser_id", [
    (CLOB, 241493299, 241493298),      # the specimen: Under won
    (OVER_WON, 241493298, 241493299),  # the mirror: Over won
])
async def test_the_entry_shows_the_condition_legs_and_tokens_the_winner_came_from(
    clob, clob_payload, winner_id, loser_id,
):
    clob["clob"] = _Clob({COND: clob_payload})
    s = _Session(_page(), {64157611: _legs()})
    out = await rp.repair(s, apply=False)
    (entry,) = out["ledger"]
    ev = entry["evidence"]
    assert entry["action"] == "regrade" and entry["winner_id"] == winner_id

    assert ev["market_external_id"] == COND
    assert ev["condition_id_requested"] == COND
    assert ev["legs"] == [
        {"id": 241493298, "name": "Over", "external_id": f"{COND}_yes",
         "prior_is_winner": True, "prior_resolution_source": "poly_total_score"},
        {"id": 241493299, "name": "Under", "external_id": f"{COND}_no",
         "prior_is_winner": False, "prior_resolution_source": "poly_total_score"},
    ]
    assert ev["legs_total"] == 2 and ev["legs_truncated"] is False

    prov = ev["provider"]
    assert prov["retrieval"] == "returned"
    assert prov["condition_id"] == COND and prov["condition_id_agrees"] is True
    assert prov["question"] == NAME and prov["question_truncated"] is False
    assert prov["token_count"] == 2 and prov["tokens_truncated"] is False
    assert prov["tokens"] == [
        {k: t[k] for k in ("token_id", "outcome", "winner")}
        for t in clob_payload["tokens"]
    ]

    m = ev["mapping"]
    assert m["tier"] == "resolved_direct"
    assert (m["winner_id"], m["loser_id"]) == (winner_id, loser_id)
    assert m["winner_id"] == entry["winner_id"]
    assert m["clob_tokens"] == ["Over", "Under"]
    assert m["ordinal_agree"] is True
    json.dumps(out)  # the whole response stays serializable


async def test_a_missing_venue_answer_is_recorded_absent_and_still_skipped(clob):
    clob["clob"] = _Clob({})  # 404: the service returns None
    s = _Session(_page(), {64157611: _legs()})
    (entry,) = (await rp.repair(s, apply=False))["ledger"]
    assert entry["reason"] == "clob_missing"
    assert entry["evidence"]["provider"] == {"retrieval": "absent"}
    assert entry["evidence"]["mapping"] is None
    assert entry["evidence"]["legs"][0]["prior_is_winner"] is True


async def test_an_unaddressable_market_is_never_requested(clob):
    clob["clob"] = _Clob({})
    legs = [{**leg, "external_id": "pm-legacy"} for leg in _legs()]
    page = [_mrow(market_id=64157611, market_ext="64157611", market_name=NAME)]
    s = _Session(page, {64157611: legs})
    (entry,) = (await rp.repair(s, apply=False))["ledger"]
    assert entry["reason"] == "not_clob_addressable" and clob["clob"].asked == []
    assert entry["evidence"]["condition_id_requested"] is None
    assert entry["evidence"]["provider"] == {"retrieval": "not_requested"}


async def test_a_discordant_answer_without_a_provider_id_stays_unknown(clob):
    payload = {k: v for k, v in CLOB.items() if k != "condition_id"}
    payload["question"] = "Will the Fed cut rates in March?"
    clob["clob"] = _Clob({COND: payload})
    s = _Session(_page(), {64157611: _legs()})
    (entry,) = (await rp.repair(s, apply=False))["ledger"]
    assert entry["reason"] == "name_discordant"
    prov = entry["evidence"]["provider"]
    # never back-filled from the id we asked for
    assert prov["condition_id"] is None and prov["condition_id_agrees"] is None
    assert prov["question"] == "Will the Fed cut rates in March?"
    assert entry["evidence"]["mapping"] is None


async def test_a_void_answer_keeps_its_refusal_and_its_raw_winner_flags(clob):
    tokens = [{"token_id": "1267", "outcome": "Over", "winner": None},
              {"token_id": "1089", "outcome": "Under"}]  # winner key absent
    clob["clob"] = _Clob({COND: {**CLOB, "tokens": tokens}})
    s = _Session(_page(), {64157611: _legs()})
    out = await rp.repair(s, apply=True)
    (entry,) = out["ledger"]
    assert entry["reason"] == "void" and s.writes == [] and s.commits == 0
    prov = entry["evidence"]["provider"]
    assert prov["tokens"] == [
        {"token_id": "1267", "outcome": "Over", "winner": None},
        {"token_id": "1089", "outcome": "Under"},
    ]
    assert entry["evidence"]["mapping"] == {"skip": "void"}


@pytest.mark.parametrize("provider_cond,observed,agrees", [
    ("0xother", "0xother", False),
    ("", None, None),
    ("f0f014d8", None, None),
    (12345, None, None),
])
def test_the_provider_condition_id_is_reported_only_as_observed(
    provider_cond, observed, agrees,
):
    prov = rp._provider_evidence(COND, {**CLOB, "condition_id": provider_cond})
    assert prov["condition_id"] == observed
    assert prov["condition_id_agrees"] is agrees


def test_provider_values_are_bounded_and_json_safe():
    payload = {
        **CLOB,
        "question": "Q" * 5000,
        "tokens": CLOB["tokens"]
        + [{"token_id": str(i), "outcome": {"nested": i}} for i in range(6)],
        "rewards": {"huge": "x" * 10000},  # never copied
    }
    prov = rp._provider_evidence(COND, payload)
    assert len(prov["question"]) == rp._EVIDENCE_STR_CAP and prov["question_truncated"]
    assert prov["token_count"] == 8 and prov["tokens_truncated"] is True
    assert len(prov["tokens"]) == rp._EVIDENCE_LIST_CAP
    assert prov["tokens"][2]["outcome"] == {"unrecognized_type": "dict"}
    assert "rewards" not in json.dumps(prov)
    assert len(json.dumps(prov)) < 2000


async def test_evidence_costs_no_extra_request_or_query_and_a_dry_run_writes_nothing(
    clob,
):
    cond2 = "0x" + "ab" * 32
    name2 = "Milwaukee Brewers Team Total: O/U 4.5"
    clob2 = {**CLOB, "question": name2, "condition_id": cond2}
    legs2 = [{**leg, "id": leg["id"] + 10,
              "external_id": leg["external_id"].replace(COND, cond2)}
             for leg in _legs()]
    page = _page() + [_mrow(market_id=64157612, market_ext=cond2, market_name=name2)]
    clob["clob"] = _Clob({COND: CLOB, cond2: clob2})
    s = _Session(page, {64157611: _legs(), 64157612: legs2})
    out = await rp.repair(s, apply=False)
    assert [e["evidence"]["condition_id_requested"] for e in out["ledger"]] == [COND, cond2]
    # one CLOB fetch per in-scope market, none for the full-game row
    assert clob["clob"].asked == [COND, cond2]
    # SET LOCAL + the page + one legs read per in-scope market; nothing else
    assert len(s.sql) == 1 + 1 + 2
    assert not any(
        q.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE"))
        for q in s.sql
    )
    assert s.commits == 0 and s.writes == [] and out["legs_written"] == 0


@pytest.mark.parametrize("legs,clob_payload", [
    (_legs(), CLOB),
    (_legs(over_won=False), OVER_WON),
    (_legs(src="api_settlement"), CLOB),
    (_legs()[:1], CLOB),
    (_legs(), None),
    (_legs(), {**CLOB, "question": "Will the Fed cut rates in March?"}),
    (_legs(), {**CLOB, "tokens": [{**t, "winner": False} for t in CLOB["tokens"]]}),
    ([{**leg, "name": "Yes" if i == 0 else "No"} for i, leg in enumerate(_legs())],
     CLOB),
])
def test_decide_is_exactly_the_helpers_decision(legs, clob_payload):
    decision, _ = rp._decide_and_map(NAME, legs, clob_payload)
    assert rp.decide(NAME, legs, clob_payload) == decision


async def test_yes_no_stored_legs_stay_refused_and_the_entry_says_why(clob):
    """Over/Under tokens against legs stored "Yes"/"No": only the token ORDER
    could pair them. The rail admits the direct tier alone, so this is a skip,
    and the entry shows the mapper's own refusal rather than an ordinal guess."""
    legs = [{**leg, "name": "Yes" if i == 0 else "No"} for i, leg in enumerate(_legs())]
    clob["clob"] = _Clob({COND: CLOB})
    s = _Session(_page(), {64157611: legs})
    out = await rp.repair(s, apply=True)
    (entry,) = out["ledger"]
    assert entry["action"] == "skip" and entry["reason"] == "ambiguous_skipped"
    assert entry["evidence"]["mapping"] == {
        "skip": "ambiguous_skipped", "why": "totals_stored_yesno"}
    assert s.writes == [] and s.commits == 0
