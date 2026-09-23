"""#7547 — PHONE slice: the selected range keeps the venue's genuine turns.

PILLAR: TRUTH / FORMATTING. SHIP: the phone's selected history range preserves
genuine price reversals already available from the venue, rather than reducing a
busy hour to one point.

═══ WHERE THE PHONE LOST THEM ═══════════════════════════════════════════════

`FuturesDetailView` mounts `EvolutionChartView`, which fetches
`/api/futures/{id}/probability-timeline?top=50&hours=168` (`APIClient.swift:928`);
nothing native reads `/history`. That reader admitted venue observations
(#7351) through the SAME `in_window` / `unclaimed_instants` seam the web reader
uses, and then threw most of them away one layer later, in its own
`venue_cells` selection:

  * ONE ROW PER (outcome, bucket), THE LAST — a busy hour of minute candles
    became the price the hour closed on; every turn inside it vanished;
  * A BUCKET OUR CAPTURE REACHED SERVED NO VENUE ROW AT ALL — and on the
    hourly-captured population #7547 is about, every hour holds a capture.

The web `/history` slice (Live/493, market 61097129, 2,085 venue points) was
paid on 2026-09-21 and is not redone here: it serves every admitted row. This
file is the phone half, replayed through the real route.

═══ THE NAMED SPECIMENS — SAVED PRODUCTION RECEIPTS, NOT SYNTHETIC ══════════

Both fixtures under `tests/fixtures/phone_history_detail_7547/` are derived
verbatim (every timestamp, every value) from two production `/history?hours=168`
receipts codex saved on 2026-09-22 ~18:26Z
(`artifacts/codex-7807-positive-review/{61097129,56775596}-history.json`,
sha256 in each fixture's `receipt` block and in `PROVENANCE.md`). A `/history`
receipt's `provenance: venue_history` rows ARE the reader-admitted venue rows —
the output of the very `in_window` the phone route calls — so replaying them
as the bank replays what the phone reader was handed.

  * 61097129 *New York G vs Los Angeles R: Spread* (Kalshi, the Live/493
    market). Outcome 229589757 *over 9.5*, hour 2026-09-18T21Z: TWELVE venue
    minutes and ONE capture. 0.430 → 0.425 (21:26, trough) → 0.435 (21:46,
    peak) → … → 0.430. Both extrema interior. The phone served the capture and
    nothing else for that hour.
  * 56775596 *Las Vegas: Team Specials* (Kalshi, codex's own #7807 acceptance
    specimen). Outcome 222329146 *Fernando Mendoza 300+ passing yards*, hour
    2026-09-16T23Z: NINE venue minutes, NO capture. 0.670 → 0.665 (23:12,
    trough) → … → 0.675 (23:27, peak) → … → 0.670 (23:56). The phone served
    23:56 alone.

WHAT IS REAL: both route handlers through the real FastAPI app, a real
PostgreSQL, a real Redis, the real identity validation, support filter and
layering. CONTROLLED: the clock (frozen at the instant a phone reader would
have asked), and the bank is PUT rather than fetched — the venue is not called,
because the receipt already holds what the venue said. Leg tickers are not in
either payload and are REPLICA identities: the binding checks bank contract ==
seeded `external_id`, and that is the only property they carry. The tier label
is not in a `/history` receipt either and is set to the fine tier, which is
what the real bank's finest tier declares; it drives only the ±30 s capture
claim.

A SKIP IS NOT A PASS. Same disposable-service contract as the #7351 file this
imports its rig from.
"""

# ruff: noqa: F811 — `venue` / `broker` are the #7351 rig's fixtures, imported by name so
# pytest can see them here; a test parameter of the same name is how a fixture is used.
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

import pytest

from tests.integration.test_generic_market_history_7351_real_pg_redis import (  # noqa: F401 — fixtures
    DB_URL,
    NONCE,
    REDIS_URL,
    FrozenDatetime,
    _arun,
    _get,
    _put_payload,
    _schema,
    _world,
    broker,
    venue,
)

pytestmark = pytest.mark.skipif(
    not (DB_URL and REDIS_URL and NONCE),
    reason=(
        "NOT RUN — set GENERIC_HISTORY_DATABASE_URL + GENERIC_HISTORY_REDIS_URL + "
        "GENERIC_HISTORY_NONCE to run the #7547 phone acceptance on disposable "
        "Postgres and Redis. A skip here is NOT a pass."
    ),
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "phone_history_detail_7547"

SPREAD_ID, SPREAD_OUTCOME = 61097129, 229589757
SPECIALS_ID, SPECIALS_OUTCOME = 56775596, 222329146

#: A phone reader on the Monday before kickoff (`commence_time` 2026-09-22T03:13Z).
#: Not in play, so the reader buckets by the hour and searches the whole week.
SPREAD_NOW = datetime(2026, 9, 21, 20, 0, 0, tzinfo=timezone.utc)
#: The instant codex's receipt was read; the bank it served was built 16:03:02Z.
SPECIALS_NOW = datetime(2026, 9, 22, 18, 26, 21, tzinfo=timezone.utc)
SPECIALS_BUILT_AT = "2026-09-22T16:03:02.112582+00:00"

#: The named hour on each specimen, with what the receipt holds inside it.
SPREAD_HOUR = datetime(2026, 9, 18, 21, 0, 0, tzinfo=timezone.utc)
SPECIALS_HOUR = datetime(2026, 9, 16, 23, 0, 0, tzinfo=timezone.utc)


def _fixture(market_id: int) -> dict:
    return json.loads((FIXTURES / f"{market_id}-receipt.json").read_text())


def _ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


async def _seed_receipt(fx: dict, *, now: datetime):
    """The market as the detail read described it, and every capture the receipt served up to `now`."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models as m

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add(
            m.FuturesMarket(
                id=fx["market_id"],
                source=fx["source"],
                external_id=fx["external_id"],
                name=fx["market_name"],
                category="sports",
                llm_sport_category="sports",
                market_tier=2,
                mutually_exclusive=fx["mutually_exclusive"],
                status="open",
                commence_time=_ts(fx["commence_time"]) if fx.get("commence_time") else None,
                created_at=_ts(fx["created_at"]),
                resolution_date=now + timedelta(days=100),
                market_metadata={},
            )
        )
        await s.flush()
        for rank, o in enumerate(fx["outcomes"], start=1):
            captures = [(ts, p) for ts, p in o["captures"] if _ts(ts) <= now]
            current = captures[-1][1] if captures else 0.5
            s.add(
                m.FuturesOutcome(
                    id=o["outcome_id"],
                    market_id=fx["market_id"],
                    external_id=o["replica_ticker"],
                    name=o["name"],
                    current_probability=current,
                    opening_probability=current,
                    rank=rank,
                    is_winner=False,
                    last_updated=now,
                )
            )
            await s.flush()
            for ts, p in captures:
                s.add(
                    m.FuturesOddsSnapshot(
                        outcome_id=o["outcome_id"],
                        bookmaker=fx["source"],
                        probability=p,
                        captured_at=_ts(ts),
                    )
                )
        await s.commit()
    await engine.dispose()


def _bank(fx: dict, *, now: datetime, built_at: str) -> dict:
    """The receipt's admitted venue rows, as the bank the reader is handed.

    A bank holds only what was observed before it was built: a row after
    `built_at` is refused whole by `validate_payload` (`timestamp_after_build`),
    which is a fence, not a fixture accident, so the rows stop at `built_at`.
    """
    from app.utils.generic_market_history import CACHE_VERSION, SCALE, SCHEMA

    horizon = min(now, _ts(built_at))
    outcomes = {}
    for o in fx["outcomes"]:
        rows = [
            [ts, p, None, None, None, "kalshi_candle_1m"]
            for ts, p in o["venue"]
            if _ts(ts) <= horizon
        ]
        if not rows:
            continue
        outcomes[str(o["outcome_id"])] = {
            "outcome_id": o["outcome_id"],
            "contract": {
                "venue": "kalshi",
                "ticker": o["replica_ticker"],
                "outcome_external_id": o["replica_ticker"],
            },
            "points": rows,
            "observed_through": rows[-1][0],
        }
    return {
        "schema": SCHEMA,
        "version": CACHE_VERSION,
        "scale": SCALE,
        "market_id": fx["market_id"],
        "market_source": fx["source"],
        "market_external_id": fx["external_id"],
        "attempted_at": built_at,
        "built_at": built_at,
        "status": "ok",
        "outcomes": outcomes,
        "stats": {"replayed_from": fx["receipt"]["path"]},
    }


def _stage(market_id: int, *, now: datetime, built_at: str | None = None) -> dict:
    fx = _fixture(market_id)
    FrozenDatetime.current = now
    _arun(_seed_receipt(fx, now=now))
    _put_payload(
        _bank(fx, now=now, built_at=built_at or (now - timedelta(hours=1)).isoformat()), market_id
    )
    return fx


def _phone(market_id: int, hours: int = 168) -> dict:
    return _get(f"/api/futures/{market_id}/probability-timeline?hours={hours}&top=50")[0]


def _web(market_id: int, hours: int = 168) -> dict:
    # `top_n=50`: the same breadth the phone asks for, so the two readers are
    # compared on the same lines (`/history` charts ten by default).
    return _get(f"/api/futures/{market_id}/history?hours={hours}&top_n=50")[0]


def _phone_series(body: dict, name: str) -> list[tuple[datetime, float]]:
    """Every point the phone draws for one line, in the order it draws them."""
    return [
        (_ts(e["timestamp"]), e["outcomes"][name])
        for e in body["timeline"]
        if name in e["outcomes"]
    ]


def _web_venue_points(body: dict, outcome_id: int) -> set[tuple[datetime, float]]:
    for entry in body["outcomes"]:
        if entry["outcome_id"] == outcome_id:
            return {
                (_ts(pt["timestamp"]), pt["probability"])
                for pt in entry["history"]
                if pt.get("provenance") == "venue_history"
            }
    return set()


def _in_hour(points, hour: datetime):
    return [(ts, v) for ts, v in points if hour <= ts < hour + timedelta(hours=1)]


def _name(fx: dict, outcome_id: int) -> str:
    return next(o["name"] for o in fx["outcomes"] if o["outcome_id"] == outcome_id)


def _receipt_hour(
    fx: dict, outcome_id: int, hour: datetime, key: str
) -> list[tuple[datetime, float]]:
    o = next(o for o in fx["outcomes"] if o["outcome_id"] == outcome_id)
    return _in_hour([(_ts(ts), p) for ts, p in o[key]], hour)


# ═══ P1 — a busy hour with NO capture keeps its peak AND its trough ══════════


def test_P1_a_busy_hour_with_no_capture_keeps_both_turns_in_order(venue, broker):
    """56775596 / 222329146, 2026-09-16T23Z: nine venue minutes, no capture.

    RED on the base: the phone served one point for the hour — 23:56, the price
    the hour closed on — and the 23:12 trough and 23:27 peak were gone. Its own
    describe block said `points_served` counted them; the timeline did not carry
    them.
    """
    fx = _stage(SPECIALS_ID, now=SPECIALS_NOW, built_at=SPECIALS_BUILT_AT)
    name = _name(fx, SPECIALS_OUTCOME)
    expected = _receipt_hour(fx, SPECIALS_OUTCOME, SPECIALS_HOUR, "venue")
    assert not _receipt_hour(fx, SPECIALS_OUTCOME, SPECIALS_HOUR, "captures")
    assert len(expected) == 9, expected

    body = _phone(SPECIALS_ID)
    assert body["venue_history"]["unsupported_points_withheld"] == 0, body["venue_history"]
    served = _in_hour(_phone_series(body, name), SPECIALS_HOUR)

    peak = max(expected, key=lambda p: p[1])
    trough = min(expected, key=lambda p: p[1])
    assert peak[1] > expected[0][1] and trough[1] < expected[0][1]  # both are TURNS, not endpoints
    assert peak in served, f"the hour's peak {peak} was not served; got {served}"
    assert trough in served, f"the hour's trough {trough} was not served; got {served}"
    # Every admitted observation, at its own instant, in the order it happened —
    # nothing summarised, nothing relabelled, nothing invented between them.
    assert served == expected, f"\n got  {served}\n want {expected}"
    assert served == sorted(served)


# ═══ P2 — an hour OUR CAPTURE reached keeps the venue's turns around it ═══════


def test_P2_a_capture_hour_serves_the_venue_turns_and_the_capture_at_its_own_instant(venue, broker):
    """61097129 / 229589757, 2026-09-18T21Z, read on the Monday before kickoff.

    Twelve venue minutes and one capture in the hour. RED on the base: the
    phone served exactly ONE point for the hour — the capture, stamped at the
    hour mark — and refused every venue row because the bucket "was reached".

    The capture is still served, with its own value, and is never displaced by
    a venue row: the one venue minute inside its ±30 s claim is not served.
    But it is served AT THE INSTANT IT WAS TAKEN. A capture stamped at 21:00
    carrying a 21:5x price, sitting in front of real 21:2x minutes, would draw
    a move nobody observed at an instant nobody observed it — the exact thing
    #7351 refused to do to venue rows.
    """
    fx = _stage(SPREAD_ID, now=SPREAD_NOW)
    name = _name(fx, SPREAD_OUTCOME)
    expected_venue = _receipt_hour(fx, SPREAD_OUTCOME, SPREAD_HOUR, "venue")
    captures = _receipt_hour(fx, SPREAD_OUTCOME, SPREAD_HOUR, "captures")
    assert len(expected_venue) == 12 and len(captures) == 1, (expected_venue, captures)
    capture_at, capture_value = captures[0]

    body = _phone(SPREAD_ID)
    assert body["bucket_seconds"] == 3600, "pre-kickoff: hourly buckets"
    served = _in_hour(_phone_series(body, name), SPREAD_HOUR)

    peak = max(expected_venue, key=lambda p: p[1])
    trough = min(expected_venue, key=lambda p: p[1])
    assert peak[1] > expected_venue[0][1] and trough[1] < expected_venue[0][1]
    assert peak in served, f"peak {peak} lost; got {served}"
    assert trough in served, f"trough {trough} lost; got {served}"

    # Capture precedence, unchanged: it is served, with its value, and any venue
    # minute that restates it (inside the claim) is not.
    assert (capture_at, capture_value) in served, f"the capture was displaced: {served}"
    for ts, _v in served:
        if ts != capture_at:
            assert abs((ts - capture_at).total_seconds()) > 30
    assert (
        SPREAD_HOUR,
        capture_value,
    ) not in served, "the capture was still stamped at the hour mark in front of real minutes"
    assert served == sorted(served)
    # Exactly the receipt's admitted minutes plus the capture — and the venue
    # minute the capture claims is the one row the receipt also did not carry.
    assert served == sorted(
        expected_venue + [(capture_at, capture_value)]
    ), f"\n got  {served}\n want {sorted(expected_venue + [(capture_at, capture_value)])}"


# ═══ P3 — the two readers agree, except where our own polls are already fine ═


def _capture_instants_per_cell(
    fx: dict, *, now: datetime, bucket_s: int, since: datetime | None = None
) -> dict[tuple[int, int], set]:
    cells: dict[tuple[int, int], set] = defaultdict(set)
    for o in fx["outcomes"]:
        for ts, _p in o["captures"]:
            at = _ts(ts)
            if at <= now and (since is None or at >= since):
                cells[(o["outcome_id"], int(at.timestamp()) // bucket_s * bucket_s)].add(at)
    return cells


@pytest.mark.parametrize(
    "market_id,now,built_at",
    [
        (SPREAD_ID, SPREAD_NOW, None),
        (SPECIALS_ID, SPECIALS_NOW, SPECIALS_BUILT_AT),
    ],
)
def test_P3_the_phone_serves_every_venue_row_the_web_serves_outside_densely_captured_cells(
    venue, broker, market_id, now, built_at
):
    """Parity with the paid web slice, stated with its one deliberate exception.

    A cell our own polls fill with TWO OR MORE readings keeps its shape — one
    median at the bucket start, no venue rows — exactly as `test_C9` requires
    of a finely captured market. Everywhere else the phone serves the same
    venue instants and values `/history` serves.
    """
    fx = _stage(market_id, now=now, built_at=built_at)
    phone, web = _phone(market_id), _web(market_id)
    assert phone["venue_history"]["state"] == "warm" and web["venue_history"]["state"] == "warm"
    assert "refusals" not in phone["venue_history"], phone["venue_history"]
    assert phone["venue_history"]["unsupported_points_withheld"] == 0
    dense = {
        cell
        for cell, instants in _capture_instants_per_cell(
            fx, now=now, bucket_s=phone["bucket_seconds"]
        ).items()
        if len(instants) >= 2
    }

    total_web = total_phone = 0
    for o in fx["outcomes"]:
        oid, name = o["outcome_id"], o["name"]
        web_points = _web_venue_points(web, oid)
        phone_points = set(_phone_series(phone, name))
        expected = {
            (ts, v)
            for ts, v in web_points
            if (oid, int(ts.timestamp()) // phone["bucket_seconds"] * phone["bucket_seconds"])
            not in dense
        }
        missing = sorted(expected - phone_points)
        assert (
            not missing
        ), f"{name}: {len(missing)} venue rows the web serves are missing on the phone, e.g. {missing[:3]}"
        vetoed = sorted(web_points - expected)
        # A dense cell's own entry sits at its bucket start; a venue candle that
        # closed on the hour with the same value is indistinguishable from it by
        # (instant, value) alone, so the capture's own stamp is set aside here.
        bucket_stamps = {
            datetime.fromtimestamp(cell[1], tz=timezone.utc) for cell in dense if cell[0] == oid
        }
        leaked = sorted(pt for pt in set(vetoed) & phone_points if pt[0] not in bucket_stamps)
        assert not leaked, f"{name}: a densely captured cell admitted a venue row: {leaked[:4]}"
        total_web += len(web_points)
        total_phone += len(expected)
    assert phone["venue_history"]["points_served"] == total_phone
    assert web["venue_history"]["points_served"] == total_web
    assert total_phone > 0


# ═══ P4 — controls: what did not move ════════════════════════════════════════


def test_P4a_a_densely_captured_cell_keeps_its_median_at_the_bucket_start(venue, broker):
    """The settled game, read at the receipt's own clock: in play, 15-minute
    buckets, our own poll every two to four minutes. Every venue row in the game
    lands in a cell with several captures, so the phone draws exactly what it
    drew before this change — one median per cell, at the cell's start — and
    the bank contributes nothing there.
    """
    now = _ts("2026-09-22T18:26:00+00:00")
    fx = _stage(SPREAD_ID, now=now, built_at="2026-09-22T16:02:31.156467+00:00")
    body = _phone(SPREAD_ID)
    assert body["bucket_seconds"] == 900
    clamp = _ts(fx["commence_time"])
    # Only captures INSIDE the served window count — the clamp cuts the query at
    # the event start, so a capture before it is not a reading in any cell.
    dense_cells = {
        cell
        for cell, instants in _capture_instants_per_cell(
            fx, now=now, bucket_s=900, since=clamp
        ).items()
        if len(instants) >= 2
    }
    assert dense_cells, "the receipt's in-play captures are two to four minutes apart"
    checked = 0
    for o in fx["outcomes"]:
        oid, name = o["outcome_id"], o["name"]
        served = _phone_series(body, name)
        assert all(
            ts >= clamp.replace(minute=0, second=0, microsecond=0) for ts, _v in served
        ), "the in-play clamp to the event start (#1138) moved"
        venue_rows = {(_ts(ts), p) for ts, p in o["venue"]}
        per_cell: dict[int, list] = defaultdict(list)
        for ts, v in served:
            per_cell[int(ts.timestamp()) // 900 * 900].append((ts, v))
        for bucket, points in per_cell.items():
            if (oid, bucket) in dense_cells:
                checked += 1
                assert points == [
                    (datetime.fromtimestamp(bucket, tz=timezone.utc), points[0][1])
                ], f"{name}: a densely captured cell no longer serves one median at its start: {points}"
                assert not (
                    set(points) & venue_rows
                ), f"{name}: a densely captured cell admitted a venue row"
    assert checked > 0


def test_P4b_a_venue_minute_that_restates_a_capture_is_still_refused_on_the_phone(venue, broker):
    """Capture precedence is the instant-level claim, and it still holds: on the
    pre-kickoff specimen, no served venue point sits inside ±30 s of a capture,
    and every capture is served with its own value."""
    fx = _stage(SPREAD_ID, now=SPREAD_NOW)
    body = _phone(SPREAD_ID)
    for o in fx["outcomes"]:
        captures = {_ts(ts): p for ts, p in o["captures"] if _ts(ts) <= SPREAD_NOW}
        served = dict(_phone_series(body, o["name"]))
        venue_set = {_ts(ts) for ts, _p in o["venue"]}
        for at, value in served.items():
            if at in venue_set and at not in captures:
                assert all(abs((at - c).total_seconds()) > 30 for c in captures), (at, o["name"])
        # A capture whose cell gained venue rows is served at its instant with
        # its value; one whose cell did not is served at the bucket start — as
        # the median of the cell's readings, which for one reading is itself.
        by_cell: dict[datetime, list[float]] = defaultdict(list)
        for at, p in captures.items():
            by_cell[
                datetime.fromtimestamp(int(at.timestamp()) // 3600 * 3600, tz=timezone.utc)
            ].append(p)
        for at, p in captures.items():
            bucket = datetime.fromtimestamp(int(at.timestamp()) // 3600 * 3600, tz=timezone.utc)
            assert served.get(at) == pytest.approx(p) or served.get(bucket) == pytest.approx(
                median(by_cell[bucket])
            ), f"{o['name']}: capture {at} = {p} was displaced"


def test_P4c_no_entry_is_published_at_an_instant_nothing_was_observed(venue, broker):
    """Relocating a capture must not leave an empty hour-mark entry behind,
    and no entry may carry an empty outcomes dict (C5's rule, kept)."""
    _stage(SPECIALS_ID, now=SPECIALS_NOW, built_at=SPECIALS_BUILT_AT)
    body = _phone(SPECIALS_ID)
    for entry in body["timeline"]:
        assert entry["outcomes"], f"empty entry at {entry['timestamp']}"
    stamps = [e["timestamp"] for e in body["timeline"]]
    assert stamps == sorted(stamps) and len(stamps) == len(set(stamps))


# ═══ P5 — the payload is bounded by the bank, and the cost is measured ════════


@pytest.mark.parametrize("hours", [24, 168, 4320])
def test_P5_the_phone_payload_is_bounded_by_the_bank_at_every_range(venue, broker, hours):
    """The bank is compacted per band at fill time (`compact_by_band`, ≤400 per
    outcome, ≤12 outcomes); the phone serves at most those rows, never more —
    no cap was raised, nothing was resampled or interpolated to fill a range."""
    fx = _stage(SPECIALS_ID, now=SPECIALS_NOW, built_at=SPECIALS_BUILT_AT)
    bank_rows = sum(
        len([1 for ts, _p in o["venue"] if _ts(ts) <= SPECIALS_NOW]) for o in fx["outcomes"]
    )
    body = _phone(SPECIALS_ID, hours=hours)
    venue_served = body["venue_history"]["points_served"]
    assert 0 < venue_served <= bank_rows
    # Every served instant is either a capture instant, a bucket start, or a
    # venue instant — there is no fourth kind.
    venue_instants = {_ts(ts) for o in fx["outcomes"] for ts, _p in o["venue"]}
    capture_instants = {_ts(ts) for o in fx["outcomes"] for ts, _p in o["captures"]}
    for entry in body["timeline"]:
        at = _ts(entry["timestamp"])
        assert (
            at in venue_instants
            or at in capture_instants
            or int(at.timestamp()) % body["bucket_seconds"] == 0
        ), at
    size = len(json.dumps(body, separators=(",", ":")).encode())
    print(
        f"\n#7547 phone payload hours={hours}: {size} bytes, {len(body['timeline'])} entries, "
        f"venue points_served={venue_served} of {bank_rows} banked"
    )
