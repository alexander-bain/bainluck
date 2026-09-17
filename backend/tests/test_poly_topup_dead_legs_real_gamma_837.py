"""#837 — dead legs hold the top-up's window, against the REAL Gamma client.

PROVENANCE, because it matters for how much this file is worth: the fixture, the
captured payloads and every assertion below are the other-model diagnostic's
(``artifacts/other-model-clob-coverage/``, 2026-09-17 02:2xZ), which reproduced
the defect red — 2 failed / 4 passed — against the real backend models before any
repair existed. Adopted here rather than rewritten, because a red-first fixture
written by someone who was not the fixer is the strongest evidence this ship has.

ADAPTED AT EXACTLY ONE SEAM, and the seam is the point. It drove the window
through ``_recycle_clock``, the wall-clock design that was PROVED to starve
before it was built (900 ids, cap 300, a pass every 900 s asks only ids 0-599,
for ever). What shipped resumes from a DURABLE POSITION and has no clock in it,
so the driver below carries a cursor store — which is also the more faithful
rig: it is what Redis does across a runner restart. Nothing else is touched; the
assertions are the author's, including the ones this file could fail.

BEFORE the repair (master ba8b5bf93, which contains 28c647c19):
    2 FAIL  (the starved hero leg is never asked, in either shape)
    4 pass  (the controls — they describe behaviour that must not change)
AFTER it: 6 pass.

WHAT IS REAL HERE. The request builder and the parser are the production ones:
``PolymarketAPIService.get_markets_by_conditions`` and ``_parse_market`` run
unmodified against an ``httpx.MockTransport`` that replays Gamma payloads
captured 2026-09-17 02:2xZ, and that reproduces the ONE provider behaviour that
matters: ``/markets?condition_ids=`` silently applies ``closed=false``, so a
named, existing, closed market answers **HTTP 200 []** — byte-identical to an id
that never existed. The mapper is the production ``token_for_outcome``.

THE DEFECT. ``kept = sorted(addressable)[:max_outcomes]``. #6634 made FILLED
outcomes leave the ask. Nothing makes UNFILLABLE ones leave, and on a live MLB
parent row most legs are unfillable for good:

* a CLOSED sub-market (1st-5-innings lines, NRFI after the first) — never returned;
* an OPEN spread/total — returned, but our leg is named "Spread -1.5" / "O/U 7.5"
  while Gamma's outcomes are the two teams / Over-Under, so ``token_for_outcome``
  correctly refuses (one parent leg cannot be two books);
* an id Gamma does not know.

They keep their lexicographic seats forever; whatever sorts above the 300th seat
is never asked. The Braves moneyline ``0x8670…`` is such a leg — asked directly,
it maps first time (see the control).
"""

import json
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
import pytest

import app.tasks.polymarket_token_topup as topup_mod
from app.services.polymarket_api import PolymarketAPIService
from app.tasks.polymarket_token_topup import (
    OUTCOME_TOKEN_METADATA_KEY,
    topup_outcome_clob_tokens,
)
from sqlalchemy.sql.dml import Update

pytestmark = pytest.mark.asyncio

FIXTURE = json.loads(
    (Path(__file__).parent / "gamma_markets_fixture_20260917.json").read_text()
)
GAMMA = {m["conditionId"]: m for m in FIXTURE["markets"]}

# ---- exact public ids, from Gamma events 999056 (atl-chc) / 999059 (bos-tex) ----
CONTROL = "0x06146cca6d8e1906e6fa1e80c1cab9cf4c5582b2c63f23b5786ea25f854fe267"  # BOS/TEX moneyline
HERO = "0x8670003719f234dabcca91cf962e205c76c2ae0b7cc2bb1b835b0378fa5ff45a"  # ATL/CHC moneyline
CLOSED_F5_SPREAD = "0x00038b26b675a9eb71b1475b95899bcc34cc2ef780bffdb98b8055e6371ce4a4"
CLOSED_F5_TOTAL = "0x23ea4ae8b17ccb2cdf01c986ba145003f1a7dc275848bb1f8a24db078bb2255f"
OPEN_TOTAL = "0x119a107304a904103edded5b6ab69be7c1152dc58b12f37cf0a9b0f66ae0676a"
OPEN_SPREAD = "0x4115c9766348e7cbda80cf5acbd51bf8752ca4aeb23cf80bee7a421beea47fa7"
NEVER_EXISTED = "0x" + "00" * 31 + "01"

PARENT_MARKET_ID = 1  # one parent row; its legs are the sub-markets, as ingest writes them
# (outcome_id, condition id, OUR FuturesOutcome.name per `_leg_label`:
#  groupItemTitle when Gamma sends one, else outcomes[0] for a bare matchup)
LEGS = [
    (11, NEVER_EXISTED, "Nobody"),
    (12, CLOSED_F5_SPREAD, "1st 5 Innings Spread -1.5"),
    (13, OPEN_TOTAL, "O/U 7.5"),
    (14, CLOSED_F5_TOTAL, "1st 5 Innings O/U 2.5"),
    (15, OPEN_SPREAD, "Spread -1.5"),
    (16, HERO, "Atlanta Braves"),
]
DEAD = [cid for _oid, cid, _n in LEGS if cid != HERO]
assert all(cid < HERO for cid in DEAD), (
    "the defect is lexicographic: every dead leg must sort BELOW the hero leg or "
    "this fixture proves nothing"
)
CAP = 3  # production is 300 of ~1,473; 3 of 6 is the same shape at fixture size


def _gamma(request: httpx.Request) -> httpx.Response:
    """Gamma's measured behaviour: `closed` is a strict filter defaulting to false."""
    params = parse_qsl(request.url.query.decode())
    want_closed = ("closed", "true") in params
    asked = [v for k, v in params if k == "condition_ids"]
    _gamma.requests.append(params)
    body = [
        GAMMA[c]
        for c in asked
        if c in GAMMA and bool(GAMMA[c]["closed"]) == want_closed
    ]
    return httpx.Response(200, json=body)  # a miss is an EMPTY 200, never a 404


def _service() -> PolymarketAPIService:
    _gamma.requests = []
    svc = PolymarketAPIService()
    svc.gamma_client = httpx.AsyncClient(
        base_url="https://gamma-api.polymarket.com",
        transport=httpx.MockTransport(_gamma),
    )
    return svc


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _Session:
    """The two SELECTs in the order the function makes them, plus the UPDATE."""

    def __init__(self, stored: dict[str, str], legs):
        self.stored = stored
        self.legs = legs
        self.updates = 0
        self._selects = 0

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates += 1
            return _Rows([])
        self._selects += 1
        if self._selects == 1:  # stored-token read (#6634)
            # FULL WIDTH, and the width is load-bearing. The read returns
            # ``(market_id, metadata, event_start, event_status)`` (#837), and a
            # short row raises INSIDE the module's fail-open `except`, which
            # swallows it and re-asks the whole slate. This fake was two wide,
            # so every recycle below took that branch and the stored round trip
            # these tests exist to prove was never executed — 18 silent
            # "stored-token read failed" logs and a green suite.
            #
            # Both event columns are ``None`` = "unknown", which is never stale,
            # so nothing here is dropped for staleness: this file is about dead
            # legs at Gamma, not about the staleness filter.
            return _Rows(
                [
                    (
                        PARENT_MARKET_ID,
                        {OUTCOME_TOKEN_METADATA_KEY: dict(self.stored)},
                        None,
                        None,
                    )
                ]
            )
        return _Rows([(oid, name) for oid, _cid, name in self.legs])  # outcome names


async def _run_recycles(n: int, monkeypatch, legs=LEGS):
    """n consecutive 600 s socket recycles. What one pass fills, the next reads
    back as stored — the round trip the production UPDATE performs."""
    stored: dict[str, str] = {}
    asked_per_pass: list[list[str]] = []
    filled: dict = {}

    # The durable position, held OUTSIDE the loop because that is what Redis
    # does: each pass resumes where the last one stopped, and a process death
    # between passes changes nothing. `raising=False` keeps the fixture failing
    # on its ASSERTION rather than on an AttributeError against code that
    # predates the seam.
    box: dict = {"cursor": None}

    async def _load():
        return box["cursor"]

    async def _save(cursor):
        if cursor:
            box["cursor"] = cursor

    monkeypatch.setattr(topup_mod, "load_topup_cursor", _load, raising=False)
    monkeypatch.setattr(topup_mod, "save_topup_cursor", _save, raising=False)

    for _i in range(n):
        svc = _service()
        filled = await topup_outcome_clob_tokens(
            _Session(stored, legs),
            [(PARENT_MARKET_ID, oid, cid) for oid, cid, _n in legs],
            service=svc,
            max_outcomes=CAP,
        )
        await svc.close()
        asked_per_pass.append(
            sorted({v for p in _gamma.requests for k, v in p if k == "condition_ids"})
        )
        stored = {str(oid): tok for oid, (_mid, tok) in filled.items()}
    return filled, asked_per_pass


# --------------------------------------------------------------- the defect ----


async def test_a_hero_leg_above_a_window_of_dead_legs_is_reached(monkeypatch):
    """FAILS TODAY. Six legs, cap three, the three lowest are dead for good, so
    every pass asks the same three and 0x8670… is never named to Gamma."""
    filled, asked = await _run_recycles(4, monkeypatch)

    assert any(HERO in a for a in asked), (
        f"the hero leg was never asked in 4 recycles; every pass asked {asked[0]}"
    )
    # IDENTITY AND SIDE, not merely 'a token came back': it must be the token
    # index-aligned with "Atlanta Braves" in Gamma's own outcomes — the Cubs
    # token here would print 1-p on the hero.
    g = GAMMA[HERO]
    outcomes, tokens = json.loads(g["outcomes"]), json.loads(g["clobTokenIds"])
    assert filled[16] == (PARENT_MARKET_ID, tokens[outcomes.index("Atlanta Braves")])
    assert filled[16][1] != tokens[outcomes.index("Chicago Cubs")]


async def test_every_leg_is_asked_within_a_bounded_number_of_recycles(monkeypatch):
    """FAILS TODAY. The anti-starvation bound itself: ceil(6/3) = 2 windows, so
    allow 3. Today the union of what was asked never grows past the first three."""
    _filled, asked = await _run_recycles(3, monkeypatch)
    assert {c for a in asked for c in a} == {cid for _o, cid, _n in LEGS}


# ------------------------------------------ controls: must hold before AND after ----


async def test_control_the_healthy_leg_maps_first_pass_to_the_right_side(monkeypatch):
    legs = [(21, CONTROL, "Boston Red Sox")]
    filled, _ = await _run_recycles(1, monkeypatch, legs=legs)
    g = GAMMA[CONTROL]
    outcomes, tokens = json.loads(g["outcomes"]), json.loads(g["clobTokenIds"])
    assert filled[21][1] == tokens[outcomes.index("Boston Red Sox")]


async def test_control_dead_legs_are_never_mapped_however_often_they_are_asked(
    monkeypatch,
):
    """Success must not be reachable by mapping something wrong. After many
    recycles: the unknown id, both CLOSED markets and both open line markets are
    still unmapped — a spread leg pointed at a team token is an inverted card."""
    filled, _ = await _run_recycles(8, monkeypatch)
    assert set(filled) <= {16}, f"a dead leg acquired a token: {filled}"


async def test_control_a_closed_market_is_an_empty_200_not_an_absence():
    """The provider shape, through the production request builder. Default ask:
    HTTP 200 []. Same id with include_closed: present, closed, WITH tokens. So
    'not returned' must never be written down as 'does not exist' (gotcha #53)."""
    svc = _service()
    assert await svc.get_markets_by_conditions([CLOSED_F5_SPREAD]) == []
    assert ("closed", "true") not in _gamma.requests[0]
    assert ("limit", "1") in _gamma.requests[0]
    got = await svc.get_markets_by_conditions([CLOSED_F5_SPREAD], include_closed=True)
    await svc.close()
    assert [(m.condition_id, m.closed, len(m.clob_token_ids)) for m in got] == [
        (CLOSED_F5_SPREAD, True, 2)
    ]
    assert await _service().get_markets_by_conditions(
        [NEVER_EXISTED], include_closed=True
    ) == []


async def test_control_the_top_up_never_asks_for_closed_markets(monkeypatch):
    """The correction is NOT include_closed: a closed book has nothing to stream,
    and subscribing it spends a socket leg on a dead market."""
    await _run_recycles(2, monkeypatch)
    assert all(("closed", "true") not in p for p in _gamma.requests)
