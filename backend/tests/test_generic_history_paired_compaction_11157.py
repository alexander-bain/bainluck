"""#11157 — a Yes/No pair keeps the instants it was observed at TOGETHER.

PILLARS: TRUTH / FORMATTING. SHIP: a supported Polymarket Yes/No chart retains
genuine shared observation times through compaction, so real available
movements reach the reader instead of an avoidable complete-field refusal.

The defect is ours, not the venue's. Both legs of one condition are fetched at
the same instants, then `compact_by_band` runs on each leg ALONE and spends its
budget by value change. A No leg that ticks once and a flat Yes leg keep
different instants, and the reader's complete-field rule
(`exclusive_field_incomplete_at_venue_instant`) then refuses the WHOLE chart for
a hole our own compactor made. Measured on Argon's pinned replay (#10955): 150
synchronous minutes per leg → 76 kept on each, 128 instants in only one leg,
chart refused.

The repair is a UNION of instants both legs genuinely carry, for an
identity-admitted pair only. Every arm here drives the actual fill
(`build_generic_history`) and, where the reader matters, the actual route
(`get_futures_history`) with a fake venue, fake Redis and a fake session:

  * the six comparisons Root reproduced on the pinned parent are permanent —
    five preservation controls that must not move, and the synchronous pair
    that must stop being refused;
  * identity negatives — nothing that is not one condition's `_yes`/`_no` on two
    distinct tokens is ever unioned;
  * every retained point is an original observation — no interpolation, no
    complement, no invented instant;
  * the budget is the COMBINED two-leg bound, stated as such, never the old
    per-leg cap.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.routes import futures as futures_route
from app.services.polymarket_api import PolymarketHistoryUnavailable
from app.tasks import futures_chart_series_fill as concept_fill
from app.tasks import generic_market_history_fill as fill
from app.tasks.polymarket_token_topup import OUTCOME_TOKEN_METADATA_KEY
from app.utils import futures_chart_series as series
from app.utils import generic_market_history as gmh

#: The reader windows by the wall clock (`get_futures_history` reads
#: `datetime.now`), so every instant here is anchored to it — never branched on.
NOW = datetime.now(timezone.utc).replace(microsecond=0)
#: When Root replayed the #10955 packet. Its fixed instants below are moved by
#: exactly this distance, so their spacing (to the microsecond) is unchanged.
PACKET_NOW = datetime(2026, 10, 15, 0, 9, 8, tzinfo=timezone.utc)
SHIFT = NOW - PACKET_NOW
REFUSED_FIELD = "exclusive_field_incomplete_at_venue_instant"


@pytest.fixture(autouse=True)
def _no_request_pause(monkeypatch):
    monkeypatch.setattr(concept_fill, "REQUEST_PAUSE_SECONDS", 0)


# ── fakes: a venue, a cache, a session ─────────────────────────────────────


class _Redis:
    """A cache that holds the bank. It has no `incr`, so the reader's on-demand
    claim fails CLOSED here and no test ever dispatches a fill."""

    def __init__(self, store: dict[str, str]) -> None:
        self._store = store

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value


class _Result:
    def __init__(self, value=None, rows=()):
        self._value = value
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def unique(self):
        return self


class _Session:
    """Answers the reader's statements in order; the last answer repeats."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]


class _Venue:
    """Polymarket CLOB that answers only the fine tier (the one with `start_ts`).

    The coarse and hourly tiers answer empty so a synthetic series is layered
    exactly once and its instants are the ones written here.
    """

    def __init__(self, histories_by_token: dict[str, object]) -> None:
        self._histories = histories_by_token

    async def get_event_by_id(self, event_id: str) -> dict:
        return {"markets": []}

    async def get_prices_history(self, **kwargs):
        answer = self._histories.get(kwargs["token_id"], [])
        if isinstance(answer, Exception):
            raise answer
        return list(answer) if "start_ts" in kwargs else []

    async def close(self) -> None:
        return None


def _outcome(oid, market_id, name, external_id, prob, *, yes_bid=None, yes_ask=None,
             last_price=None, volume_24h=1000.0):
    return SimpleNamespace(
        id=oid, market_id=market_id, name=name, external_id=external_id,
        current_probability=prob, current_american_odds=None,
        opening_probability=prob, opening_american_odds=None,
        probability_change_24h=0.0, price_changed_at=NOW - timedelta(hours=1),
        current_yes_bid=prob - 0.01 if yes_bid is None else yes_bid,
        current_yes_ask=prob + 0.01 if yes_ask is None else yes_ask,
        current_last_price=prob if last_price is None else last_price,
        volume_24h=volume_24h, volume_24h_at=NOW - timedelta(minutes=10),
        open_interest=5000.0, open_interest_at=NOW - timedelta(minutes=10),
        last_updated=NOW - timedelta(minutes=5), rank=1, team_id=None, team=None,
        is_winner=None, resolution_source=None,
    )


def _market(market_id, name, outcomes, *, mutually_exclusive, token_map,
            market_type="binary"):
    return SimpleNamespace(
        id=market_id, name=name, source="polymarket", external_id=str(market_id),
        group_id=None, status="open", market_type=market_type,
        mutually_exclusive=mutually_exclusive, llm_sport_category=None,
        sport_id=None, sport=None, created_at=NOW - timedelta(days=5),
        updated_at=NOW - timedelta(minutes=5), settled_at=None,
        closes_at=NOW + timedelta(days=30),
        market_metadata={OUTCOME_TOKEN_METADATA_KEY: {str(k): v for k, v in token_map.items()}},
        outcomes=outcomes,
    )


def _snap(oid, captured_at, prob):
    return SimpleNamespace(
        outcome_id=oid, captured_at=captured_at, probability=prob,
        american_odds=None, bookmaker="polymarket",
        yes_bid=round(max(0.001, prob - 0.005), 4),
        yes_ask=round(min(0.999, prob + 0.005), 4), last_price=prob,
    )


def _clob(points):
    return [{"t": int(ts.timestamp()), "p": p} for ts, p in points]


def _fill(market, venue, *, last_good=None):
    return asyncio.run(fill.build_generic_history(
        None, market, polymarket_service=venue, last_good=last_good, now=NOW,
    ))


def _read(market, snapshots, payload):
    rc = _Redis({gmh.cache_key(market.id): json.dumps(payload)})
    db = _Session(_Result(value=market), _Result(rows=snapshots), _Result(rows=snapshots))
    with (
        patch.object(futures_route, "_request_path_redis", return_value=rc),
        patch.object(futures_route, "_refuted_midpoint_outcome_ids", return_value=set()),
    ):
        return asyncio.run(futures_route.get_futures_history(
            market.id, outcome_id=None, hours=168, top_n=10, champion=None,
            db=db, history_range=None,
        ))


def _served(res):
    return {o["name"]: [pt["timestamp"] for pt in o["history"]] for o in res["outcomes"]}


def _instants(payload, oid):
    return [row[0] for row in payload["outcomes"][str(oid)]["points"]]


# ── the ship: a synchronous Yes/No pair is no longer refused ────────────────

#: The 11 capture pairs held for "Katie Zacharia out as Press Secretary by
#: October 31?" (market 65678073, outcomes 246879005 Yes / 246879006 No) in the
#: saved #10955 packet — captured together, so each pair shares one instant.
#: They are the reader's own layer, carried unchanged, and the venue series
#: below is synthetic: this proves the MECHANISM on real code paths, not that
#: production's bank for that market had this shape.
ZACHARIA_CONDITION = "0x57e97ab7f68a11013e7e4096ce6b0601b40b9e5a8609c4cb4196ef1b753e6953"
ZACHARIA_CAPTURES = [
    ("2026-10-13T16:16:56.614103+00:00", 0.0395),
    ("2026-10-13T17:16:51.907683+00:00", 0.042),
    ("2026-10-13T18:18:34.292933+00:00", 0.048),
    ("2026-10-13T19:19:03.197920+00:00", 0.0625),
    ("2026-10-13T21:17:27.866442+00:00", 0.077),
    ("2026-10-13T22:19:28.669595+00:00", 0.087),
    ("2026-10-14T04:31:09.814685+00:00", 0.084),
    ("2026-10-14T13:06:13.714931+00:00", 0.088),
    ("2026-10-14T20:05:40.403025+00:00", 0.0705),
    ("2026-10-14T21:13:45.911338+00:00", 0.067),
    ("2026-10-14T22:16:18.325259+00:00", 0.07),
]
YES_ID, NO_ID = 246879005, 246879006
SYNC_BASE = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc) + SHIFT
SYNC_MINUTES = 150


def _synchronous_pair():
    yes = _outcome(YES_ID, 65678073, "Yes", f"{ZACHARIA_CONDITION}_yes", 0.055,
                   yes_bid=0.03, yes_ask=0.08, last_price=0.055)
    no = _outcome(NO_ID, 65678073, "No", f"{ZACHARIA_CONDITION}_no", 0.945,
                  yes_bid=0.92, yes_ask=0.97, last_price=0.945)
    market = _market(65678073, "Katie Zacharia out as Press Secretary by October 31?",
                     [no, yes], mutually_exclusive=True, market_type="other",
                     token_map={YES_ID: "tok_yes", NO_ID: "tok_no"})
    # 150 synchronous minutes. Yes is flat at 0.055; No ticks once, by a tenth
    # of a cent, at minute 20 — the sum stays inside the field tolerance, so
    # every instant is admissible to the reader on both legs.
    instants = [SYNC_BASE + timedelta(minutes=m) for m in range(SYNC_MINUTES)]
    raw = {
        "tok_yes": [(ts, 0.055) for ts in instants],
        "tok_no": [(ts, 0.944 if m == 20 else 0.945) for m, ts in enumerate(instants)],
    }
    snapshots = [
        _snap(oid, datetime.fromisoformat(ts) + SHIFT, p if oid == YES_ID else round(1 - p, 4))
        for ts, p in ZACHARIA_CAPTURES for oid in (YES_ID, NO_ID)
    ]
    return market, raw, snapshots


def test_a_synchronous_yes_no_pair_survives_compaction_and_is_served_warm():
    market, raw, snapshots = _synchronous_pair()
    payload = _fill(market, _Venue({k: _clob(v) for k, v in raw.items()}))

    yes, no = set(_instants(payload, YES_ID)), set(_instants(payload, NO_ID))
    # Parent: 76 + 76 kept, 128 instants in one leg only, chart refused.
    assert yes == no, f"{len(yes ^ no)} instants survive in one leg only"
    assert len(yes) == 140

    res = _read(market, snapshots, payload)
    vh = res["venue_history"]
    assert vh["state"] == "warm", vh.get("refusals")
    assert REFUSED_FIELD not in json.dumps(vh.get("refusals") or [])
    assert vh["points_served"] == 280
    assert vh["unsupported_points_withheld"] == 0
    served = _served(res)
    assert len(served["Yes"]) == len(served["No"]) == 140 + len(ZACHARIA_CAPTURES)


def test_every_point_the_pair_keeps_is_an_original_observation():
    """No interpolation, no complement, no invented instant — and no lost value."""
    market, raw, _ = _synchronous_pair()
    payload = _fill(market, _Venue({k: _clob(v) for k, v in raw.items()}))
    for oid, token in ((YES_ID, "tok_yes"), (NO_ID, "tok_no")):
        original = {ts.isoformat(): p for ts, p in raw[token]}
        rows = payload["outcomes"][str(oid)]["points"]
        assert rows, oid
        for ts, prob, *_rest in rows:
            assert ts in original, f"{oid}: {ts} was never observed"
            assert prob == pytest.approx(original[ts], abs=1e-9), f"{oid}: {ts} value moved"
    # The one real move is on the line, on the leg that made it.
    no_values = dict((r[0], r[1]) for r in payload["outcomes"][str(NO_ID)]["points"])
    assert no_values[(SYNC_BASE + timedelta(minutes=20)).isoformat()] == pytest.approx(0.944)


def test_both_legs_keep_everything_each_leg_would_have_kept_alone():
    """The union only ADDS: no leg loses an instant its own compaction kept."""
    market, raw, _ = _synchronous_pair()
    payload = _fill(market, _Venue({k: _clob(v) for k, v in raw.items()}))
    for oid, token in ((YES_ID, "tok_yes"), (NO_ID, "tok_no")):
        alone = {ts.isoformat() for ts, _p in series.compact_by_band(raw[token], NOW)}
        assert alone <= set(_instants(payload, oid)), oid


def test_a_pair_that_shares_only_some_instants_keeps_each_legs_own_points():
    """Only SHARED instants are unioned. An instant one leg alone observed stays
    on that leg if its own compaction kept it, and never appears on the other."""
    cond = "0x" + "9a" * 32
    yes = _outcome(601, 9300, "Yes", f"{cond}_yes", 0.30)
    no = _outcome(602, 9300, "No", f"{cond}_no", 0.70)
    market = _market(9300, "Partly synchronous pair", [yes, no], mutually_exclusive=True,
                     token_map={601: "tok_y", 602: "tok_n"})
    # Past the 1W band's 90-point budget on each leg, so compaction really
    # drops points here and the union has something to restore.
    shared = [SYNC_BASE + timedelta(minutes=m) for m in range(SYNC_MINUTES)]
    own_yes = [SYNC_BASE + timedelta(minutes=m, seconds=30) for m in range(0, SYNC_MINUTES, 7)]
    own_no = [SYNC_BASE + timedelta(minutes=m, seconds=45) for m in range(0, SYNC_MINUTES, 11)]
    raw_yes = sorted([(ts, 0.30 + (0.01 if i % 3 == 0 else 0)) for i, ts in enumerate(shared)]
                     + [(ts, 0.33 + i * 0.001) for i, ts in enumerate(own_yes)])
    raw_no = sorted([(ts, 0.70 - (0.01 if i % 5 == 0 else 0)) for i, ts in enumerate(shared)]
                    + [(ts, 0.66 - i * 0.001) for i, ts in enumerate(own_no)])
    payload = _fill(market, _Venue({"tok_y": _clob(raw_yes), "tok_n": _clob(raw_no)}))

    kept_yes, kept_no = set(_instants(payload, 601)), set(_instants(payload, 602))
    alone_yes = {ts.isoformat() for ts, _ in series.compact_by_band(raw_yes, NOW)}
    alone_no = {ts.isoformat() for ts, _ in series.compact_by_band(raw_no, NOW)}
    own_yes_iso = {ts.isoformat() for ts in own_yes}
    own_no_iso = {ts.isoformat() for ts in own_no}
    shared_iso = {ts.isoformat() for ts in shared}

    # The arm can bite: compaction drops points on both legs, keeps some of
    # each leg's own instants, and alone keeps different shared instants.
    assert len(alone_yes) < len(raw_yes) and len(alone_no) < len(raw_no)
    assert alone_yes & own_yes_iso and alone_no & own_no_iso
    assert alone_yes & shared_iso != alone_no & shared_iso
    assert alone_yes <= kept_yes and alone_no <= kept_no
    assert kept_yes & shared_iso == kept_no & shared_iso
    assert kept_yes - shared_iso == alone_yes & own_yes_iso
    assert kept_no - shared_iso == alone_no & own_no_iso
    assert not kept_yes & own_no_iso and not kept_no & own_yes_iso


# ── the five preservation controls (Root's parent == candidate comparisons) ─


def test_C1_an_unrelated_outcomes_capture_never_displaces_its_neighbours_venue_point():
    t0600, t0800, t1100 = (NOW - timedelta(hours=h) for h in (6, 4, 1))
    c1, c2 = "0x" + "a1" * 32, "0x" + "b2" * 32
    a = _outcome(101, 9001, "Candidate A", f"{c1}_yes", 0.42)
    b = _outcome(102, 9001, "Candidate B", f"{c2}_yes", 0.36)
    market = _market(9001, "Non-exclusive approval poll", [a, b], mutually_exclusive=False,
                     market_type="multi", token_map={101: "tok_101", 102: "tok_102"})
    payload = _fill(market, _Venue({
        "tok_101": _clob([(t0800, 0.40), (t1100, 0.42)]),
        "tok_102": _clob([(t0800, 0.35), (t1100, 0.36)]),
    }))
    assert payload["status"] == "ok"
    assert {k: len(v["points"]) for k, v in payload["outcomes"].items()} == {"101": 2, "102": 2}

    res = _read(market, [_snap(101, t0800, 0.40), _snap(102, t0600, 0.34)], payload)
    assert res["venue_history"]["state"] == "warm"
    assert res["venue_history"]["points_served"] == 3
    assert _served(res)["Candidate B"] == [t.isoformat() for t in (t0600, t0800, t1100)]


def test_C2a_an_unsqueezed_board_with_a_withheld_leg_keeps_independently_timed_points():
    t0600, t0800, t1000 = (NOW - timedelta(hours=h) for h in (6, 4, 2))
    t0805 = t0800 + timedelta(minutes=5)
    o1 = _outcome(201, 9002, "Contender 1", f"0x{'c1' * 32}_yes", 0.36)
    o2 = _outcome(202, 9002, "Contender 2", f"0x{'c2' * 32}_yes", 0.24)
    # An empty book: `_empty_book_outcome_ids` withholds it, the field is not
    # complete, and #7954 reads the board unsqueezed.
    o3 = _outcome(203, 9002, "Withheld Contender 3", f"0x{'c3' * 32}_yes", 0.50,
                  yes_bid=0.01, yes_ask=0.99, last_price=None, volume_24h=0.0)
    market = _market(9002, "2027 Major Winner", [o1, o2, o3], mutually_exclusive=True,
                     market_type="championship", token_map={201: "tok_201", 202: "tok_202"})
    payload = _fill(market, _Venue({
        "tok_201": _clob([(t0800, 0.35), (t1000, 0.36)]),
        "tok_202": _clob([(t0805, 0.25), (t1000, 0.24)]),
    }))
    assert payload["status"] == "ok"
    assert payload["stats"]["outcomes_built"] == 2
    assert {k: len(v["points"]) for k, v in payload["outcomes"].items()} == {"201": 2, "202": 2}

    snapshots = [_snap(201, t0600, 0.35), _snap(202, t0600, 0.25), _snap(201, t0805, 0.355)]
    res = _read(market, snapshots, payload)
    assert res["venue_history"]["state"] == "warm"
    assert res["venue_history"]["points_served"] == 4
    assert t0805.isoformat() in _served(res)["Contender 2"]


def test_C2b_a_binary_pair_with_a_withheld_leg_and_asynchronous_points_is_left_alone():
    t0800 = NOW - timedelta(hours=4)
    t0805 = t0800 + timedelta(minutes=5)
    cond = "0x" + "d4" * 32
    yes = _outcome(211, 9003, "Yes", f"{cond}_yes", 0.35)
    no = _outcome(212, 9003, "No", f"{cond}_no", 0.50,
                  yes_bid=0.01, yes_ask=0.99, last_price=None, volume_24h=0.0)
    market = _market(9003, "Binary board with withheld No leg", [yes, no],
                     mutually_exclusive=True,
                     token_map={211: "tok_211_yes", 212: "tok_212_no"})
    payload = _fill(market, _Venue({
        "tok_211_yes": _clob([(t0800, 0.35)]),
        "tok_212_no": _clob([(t0805, 0.25)]),
    }))
    # Identity-admitted, but no instant is shared: nothing to union, nothing
    # invented to pair them.
    assert _instants(payload, 211) == [t0800.isoformat()]
    assert _instants(payload, 212) == [t0805.isoformat()]

    res = _read(market, [_snap(211, NOW - timedelta(hours=6), 0.35)], payload)
    assert res["venue_history"]["state"] == "warm"
    assert res["venue_history"]["points_served"] == 2


def test_C3_a_top_outcome_subset_is_compacted_as_before():
    t0800, t0900 = NOW - timedelta(hours=4), NOW - timedelta(hours=3)
    outcomes, token_map, histories = [], {}, {}
    for i in range(1, 16):
        oid, prob = 300 + i, (0.05 if i <= 12 else 0.01)
        outcomes.append(_outcome(oid, 9004, f"Runner {i}", f"0x{i:064x}_yes", prob))
        token_map[oid] = f"tok_{oid}"
        histories[f"tok_{oid}"] = _clob([(t0800, prob), (t0900, prob)])
    market = _market(9004, "15-Outcome Field", outcomes, mutually_exclusive=True,
                     market_type="championship", token_map=token_map)
    payload = _fill(market, _Venue(histories))
    assert payload["status"] == "ok"
    assert payload["stats"]["outcomes_considered"] == fill.TOP_N_OUTCOMES == 12
    assert payload["stats"]["outcomes_built"] == 12
    assert gmh.payload_point_count(payload) == 24


def test_C4_a_failed_leg_keeps_its_partner_and_the_last_good_points():
    t0600, t0700, t0800 = (NOW - timedelta(hours=h) for h in (6, 5, 4))
    cond = "0x" + "e5" * 32
    yes = _outcome(401, 9005, "Yes", f"{cond}_yes", 0.62)
    no = _outcome(402, 9005, "No", f"{cond}_no", 0.38)
    market = _market(9005, "Binary with last-good and a failed leg", [yes, no],
                     mutually_exclusive=True,
                     token_map={401: "tok_401_yes", 402: "tok_402_no"})
    last_good = gmh.build_payload(market, {401: {
        "contract": gmh.polymarket_contract(yes, token_id="tok_401_yes",
                                            resolved_via="outcome_token_metadata"),
        "points": [gmh.VenuePoint(t0600, 0.60, tier="polymarket_clob_120h_f1"),
                   gmh.VenuePoint(t0700, 0.61, tier="polymarket_clob_120h_f1")],
    }}, now=NOW - timedelta(hours=2), stats={}, degraded=False)
    payload = _fill(market, _Venue({
        "tok_401_yes": _clob([(t0800, 0.62)]),
        "tok_402_no": PolymarketHistoryUnavailable("synthetic CLOB 500 on the No token"),
    }), last_good=last_good)
    assert payload["status"] == "degraded"
    assert payload["stats"]["fetch_errors"] == 3
    assert payload["stats"]["carried_points"] == 2
    assert payload["stats"]["outcomes_built"] == 1
    assert payload["stats"]["outcomes_empty"] == 1
    assert _instants(payload, 401) == [t.isoformat() for t in (t0600, t0700, t0800)]


# ── identity: only one condition's _yes/_no on two distinct tokens pairs ────


def _sync_raw():
    """Synchronous legs whose independent compaction keeps DIFFERENT instants."""
    instants = [SYNC_BASE + timedelta(minutes=m) for m in range(SYNC_MINUTES)]
    return ([(ts, 0.055) for ts in instants],
            [(ts, 0.944 if m == 20 else 0.945) for m, ts in enumerate(instants)])


def _independent(points):
    return [ts.isoformat() for ts, _p in series.compact_by_band(points, NOW)]


def _pair_market(*, ext_a, ext_b, tok_a="tok_a", tok_b="tok_b", oid_b=502):
    a = _outcome(501, 9100, "Yes", ext_a, 0.055)
    b = _outcome(oid_b, 9100, "No", ext_b, 0.945)
    return _market(9100, "Pairing identity negative", [a, b], mutually_exclusive=True,
                   token_map={501: tok_a, oid_b: tok_b})


COND = "0x" + "f6" * 32
OTHER = "0x" + "f7" * 32


@pytest.mark.parametrize("ext_a, ext_b, why", [
    (f"{COND}_yes", f"{OTHER}_no", "two conditions"),
    (f"{COND}_yes", f"{COND}_yes", "both legs say Yes"),
    (f"{COND}_no", f"{COND}_no", "both legs say No"),
    (f"{COND}_yes", COND, "a bare rung is not a leg"),
])
def test_legs_that_are_not_one_conditions_yes_and_no_compact_alone(ext_a, ext_b, why):
    raw_a, raw_b = _sync_raw()
    market = _pair_market(ext_a=ext_a, ext_b=ext_b)
    payload = _fill(market, _Venue({"tok_a": _clob(raw_a), "tok_b": _clob(raw_b)}))
    built = {k for k, v in payload["outcomes"].items() if v["points"]}
    assert built, why
    if "501" in built:
        assert _instants(payload, 501) == _independent(raw_a), why
    if "502" in built:
        assert _instants(payload, 502) == _independent(raw_b), why


def test_one_token_behind_both_legs_is_not_a_pair():
    raw_a, raw_b = _sync_raw()
    market = _pair_market(ext_a=f"{COND}_yes", ext_b=f"{COND}_no", tok_a="tok_same",
                          tok_b="tok_same")
    payload = _fill(market, _Venue({"tok_same": _clob(raw_a)}))
    for oid in ("501", "502"):
        if payload["outcomes"].get(oid, {}).get("points"):
            assert _instants(payload, int(oid)) == _independent(raw_a)


def _entry(venue, cond, leg, token, points):
    return {"contract": {"venue": venue, "condition_id": cond, "token_id": token,
                         "outcome_external_id": f"{cond}_{leg}" if leg else cond},
            "points": [gmh.VenuePoint(ts, p) for ts, p in points]}


def _two(a=501, b=502):
    return [SimpleNamespace(id=a), SimpleNamespace(id=b)]


def test_the_pairing_rule_admits_exactly_one_conditions_two_distinct_tokens():
    raw_a, raw_b = _sync_raw()
    ok = {501: _entry("polymarket", COND, "yes", "t1", raw_a),
          502: _entry("polymarket", COND, "no", "t2", raw_b)}
    assert fill._paired_binary_leg_ids(_two(), ok) == (501, 502)

    def broken(**over_b):
        b = _entry("polymarket", COND, "no", "t2", raw_b)
        b["contract"].update(over_b)
        return {501: ok[501], 502: b}

    refusals = {
        "kalshi venue": broken(venue="kalshi"),
        "other condition": broken(condition_id=OTHER, outcome_external_id=f"{OTHER}_no"),
        # A contract whose own two fields disagree is refused on the condition
        # alone, not rescued by the leg id still naming ours.
        "condition disagrees with its leg id": broken(condition_id=OTHER),
        "same token": broken(token_id="t1"),
        "no token": broken(token_id=None),
        "two Yes legs": broken(outcome_external_id=f"{COND}_yes"),
        "bare rung": broken(outcome_external_id=COND),
    }
    for why, entries in refusals.items():
        assert fill._paired_binary_leg_ids(_two(), entries) is None, why

    not_hex = {501: _entry("polymarket", "abc", "yes", "t1", raw_a),
               502: _entry("polymarket", "abc", "no", "t2", raw_b)}
    assert fill._paired_binary_leg_ids(_two(), not_hex) is None, "condition is not 0x"
    assert fill._paired_binary_leg_ids(_two(), {501: ok[501]}) is None, "one leg unfetched"
    # One outcome twice: both contracts are then the same object, so the token
    # rule refuses it before the id rule can — the id rule is defence in depth
    # and its removal is an equivalent mutant here, not an untested branch.
    assert fill._paired_binary_leg_ids(_two(501, 501), ok) is None, "one outcome twice"
    three = _two() + [SimpleNamespace(id=503)]
    assert fill._paired_binary_leg_ids(three, ok) is None, "not a binary"


# ── budget: the COMBINED two-leg bound, never the old per-leg cap ───────────

#: One leg compacted alone keeps at most the sum of its band budgets — 400, the
#: number every other outcome is held to. A paired leg also keeps the shared
#: instants its partner kept, so ONE paired leg may hold up to TWICE that, and
#: the pair as a whole up to the two legs' combined budget on each leg.
PER_LEG = sum(budget for _edge, budget in series.RANGE_BANDS)
PAIRED_LEG_BOUND = 2 * PER_LEG


def _adversarial_pair():
    """Synchronous minutes and hours across every band, the legs moving on
    alternate instants — each leg alone saturates its budget, and the two
    budgets land on DISJOINT instants. The worst case the union can make."""
    instants = sorted(
        {NOW - timedelta(minutes=m) for m in range(1, 24 * 60, 1)}
        | {NOW - timedelta(hours=h) for h in range(24, 60 * 24)}
    )
    a = [(ts, 0.40 + (0.01 if i % 4 == 0 else 0.0) + i * 1e-7) for i, ts in enumerate(instants)]
    b = [(ts, 0.60 + (0.01 if i % 4 == 2 else 0.0) - i * 1e-7) for i, ts in enumerate(instants)]
    return instants, a, b


def test_the_per_leg_budget_is_the_published_target():
    assert PER_LEG == series.TARGET_POINTS_PER_OUTCOME == 400


def test_a_paired_leg_is_bounded_by_the_combined_two_leg_budget_not_the_old_cap():
    _instants_, raw_a, raw_b = _adversarial_pair()
    outcomes = _two()
    entries = {501: _entry("polymarket", COND, "yes", "t1", raw_a),
               502: _entry("polymarket", COND, "no", "t2", raw_b)}
    alone_a = len(series.compact_by_band(raw_a, NOW))
    alone_b = len(series.compact_by_band(raw_b, NOW))
    assert alone_a <= PER_LEG and alone_b <= PER_LEG

    fill._compact_entries(outcomes, entries, NOW)
    kept_a, kept_b = len(entries[501]["points"]), len(entries[502]["points"])
    # Honest about the cost: a paired leg CAN exceed the old per-leg cap…
    assert max(kept_a, kept_b) > PER_LEG
    # …but never the combined budget of the two legs it was compacted with.
    assert kept_a <= alone_a + alone_b <= PAIRED_LEG_BOUND
    assert kept_b <= alone_a + alone_b <= PAIRED_LEG_BOUND


def test_a_worst_case_pair_payload_is_smaller_than_an_ordinary_full_board():
    """Storage and read cost: the pair at its bound stays below what a
    TOP_N_OUTCOMES board at the per-leg cap already banks today."""
    instants, raw_a, raw_b = _adversarial_pair()
    cond = COND
    yes = _outcome(501, 9200, "Yes", f"{cond}_yes", 0.40)
    no = _outcome(502, 9200, "No", f"{cond}_no", 0.60)
    market = _market(9200, "Worst-case pair", [yes, no], mutually_exclusive=True,
                     token_map={501: "tok_a", 502: "tok_b"})
    market.created_at = NOW - timedelta(days=90)
    entries = {501: _entry("polymarket", cond, "yes", "tok_a", raw_a),
               502: _entry("polymarket", cond, "no", "tok_b", raw_b)}
    fill._compact_entries([yes, no], entries, NOW)
    pair = gmh.build_payload(market, entries, now=NOW, stats={}, degraded=False)

    board_entries = {
        oid: _entry("polymarket", f"0x{oid:064x}", "yes", f"tok_{oid}",
                    [(ts, 0.05) for ts in instants[-PER_LEG:]])
        for oid in range(1, fill.TOP_N_OUTCOMES + 1)
    }
    board = gmh.build_payload(market, board_entries, now=NOW, stats={}, degraded=False)

    assert gmh.payload_point_count(pair) <= 2 * PAIRED_LEG_BOUND
    assert gmh.payload_point_count(board) == fill.TOP_N_OUTCOMES * PER_LEG
    assert gmh.payload_point_count(pair) < gmh.payload_point_count(board)
    pair_bytes = len(json.dumps(pair, separators=(",", ":")))
    board_bytes = len(json.dumps(board, separators=(",", ":")))
    assert pair_bytes < board_bytes, (pair_bytes, board_bytes)
