"""#11157 — a Yes/No pair the venue samples at DIFFERENT SECONDS.

PILLARS: TRUTH / FORMATTING. SHIP: a market chart shows its genuine probability
move without inventing observation times or freshness.

PR #11160 kept the instants both legs of an identity-admitted Polymarket pair
share EXACTLY. Its fixture was synchronous; the venue is not. Polymarket's CLOB
`prices-history` stamps each token at its own second (65678073, fidelity=1:
Yes 461 points, No 459, ZERO exact shared instants, 456 shared minutes — Live's
read, #11157 comment 6229278103), so the reader's exact-instant field rule
refused every point of the rebuilt v5756 bank.

These guards are written against that SHAPE, not against the synchronous one:

  * tokens of ONE condition, each sampled a few seconds from the other inside
    the venue's declared one-minute grain, with a step move (13% → 99.95%)
    whose book events sometimes fall between the two samples of a minute;
  * every served point is an original observation AT ITS OWN CLOCK — a Yes
    point is never restamped to the No sample's second or vice versa, the pair's
    knowledge time is published as its own field, and never as `timestamp`;
  * grain boundaries, a rapid move inside one grain, missing / older-cell /
    reused samples, coarse and undeclared grain, and wrong token / condition /
    deadline each pair NOTHING they should not;
  * the C2b withheld-leg board, unsupported-point accounting, the board-level
    capture comparison and the combined two-leg budget are unchanged.

No production read: every venue answer here is a fake, every instant is
anchored to the wall clock the reader windows by.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_route
from app.tasks import futures_chart_series_fill as concept_fill
from app.tasks import generic_market_history_fill as fill
from app.utils import futures_chart_series as series
from app.utils import generic_market_history as gmh
from tests.test_generic_history_paired_compaction_11157 import (
    NOW,
    PAIRED_LEG_BOUND,
    PER_LEG,
    REFUSED_FIELD,
    ZACHARIA_CONDITION,
    _clob,
    _fill,
    _instants,
    _market,
    _outcome,
    _read,
    _snap,
    _Venue,
)

FINE = "polymarket_clob_120h_f1"
#: Minute-aligned so the fixture's own cells are the venue's minute cells.
BASE = (NOW - timedelta(hours=6)).replace(second=0)
MINUTES = 240
YES_ID, NO_ID = 246879005, 246879006
TICK = 0.0005


@pytest.fixture(autouse=True)
def _no_request_pause(monkeypatch):
    monkeypatch.setattr(concept_fill, "REQUEST_PAUSE_SECONDS", 0)


def _tick(p: float) -> float:
    return round(round(p / TICK) * TICK, 4)


# ── the real shape ──────────────────────────────────────────────────────────

#: The book's own events: Yes holds 0.13, then climbs to 0.9995 from minute 150
#: (17:05Z on the specimen). The climb lands on each minute's first second, so
#: both tokens' samples in a minute see the same book — what the specimen shows,
#: where only 12 of 456 shared minutes are off by more than 5e-5 and none by more
#: than 0.0035. Those few are made here too: in every moving minute one small
#: tick (+0.002) lands at its own second, and where it falls between the two
#: samples the minute's legs disagree by exactly that tick.
def _book_events() -> list[tuple[datetime, float]]:
    events = [(BASE - timedelta(days=1), 0.13)]
    path = [0.13 + (0.57 - 0.13) * k / 5 for k in range(1, 6)]
    path += [0.57 + (0.98 - 0.57) * k / 30 for k in range(1, 31)]
    path += [0.98 + (0.9975 - 0.98) * k / 15 for k in range(1, 16)]
    for k, value in enumerate(path):
        minute = 150 + k
        events.append((BASE + timedelta(minutes=minute), value))
        events.append((BASE + timedelta(minutes=minute, seconds=(minute * 17) % 60),
                       value + 0.002))
    return events


def _yes_at(ts: datetime, events) -> float:
    value = events[0][1]
    for at, v in events:
        if at <= ts:
            value = v
    return value


#: Per-minute sample seconds: Yes at :20–:32, No at :17–:27, never equal — the
#: venue gives each token its own second, as on 65678073 (Yes 22:57:23, No 22:57:20).
def _offsets(minute: int) -> tuple[int, int]:
    yes_s = 20 + (minute * 7) % 13
    no_s = 17 + (minute * 5) % 11
    if no_s == yes_s:
        no_s -= 1
    return yes_s, no_s


#: The venue omits a bucket with nothing to say: No skips two minutes, Yes one.
NO_MISSING = {40, 170}
YES_MISSING = {90}


def _async_raw():
    events = _book_events()
    yes, no = [], []
    for m in range(MINUTES):
        ys, ns = _offsets(m)
        t_y = BASE + timedelta(minutes=m, seconds=ys)
        t_n = BASE + timedelta(minutes=m, seconds=ns)
        if m not in YES_MISSING:
            yes.append((t_y, _tick(_yes_at(t_y, events))))
        if m not in NO_MISSING:
            no.append((t_n, _tick(1 - _yes_at(t_n, events))))
    return yes, no


def _async_market(*, yes_ext=None, no_ext=None, tok_yes="tok_yes", tok_no="tok_no",
                  no_withheld=False):
    yes = _outcome(YES_ID, 65678073, "Yes", yes_ext or f"{ZACHARIA_CONDITION}_yes", 0.99,
                   yes_bid=0.985, yes_ask=0.995, last_price=0.99)
    if no_withheld:
        no = _outcome(NO_ID, 65678073, "No", no_ext or f"{ZACHARIA_CONDITION}_no", 0.50,
                      yes_bid=0.01, yes_ask=0.99, last_price=None, volume_24h=0.0)
    else:
        no = _outcome(NO_ID, 65678073, "No", no_ext or f"{ZACHARIA_CONDITION}_no", 0.01,
                      yes_bid=0.005, yes_ask=0.015, last_price=0.01)
    return _market(65678073, "Katie Zacharia out as Press Secretary by October 31?",
                   [no, yes], mutually_exclusive=True, market_type="other",
                   token_map={YES_ID: tok_yes, NO_ID: tok_no})


def _captures(before=BASE):
    """Hourly captures of BOTH legs at one instant, ahead of the venue series so
    no capture claims a venue minute (the claim rule is not under test here)."""
    out = []
    for h in (3, 2, 1):
        ts = before - timedelta(hours=h, minutes=-2, seconds=-43)
        out += [_snap(YES_ID, ts, 0.13), _snap(NO_ID, ts, 0.87)]
    return out


def _payload_rows(payload, oid):
    return [(datetime.fromisoformat(r[0]), r[1]) for r in payload["outcomes"][str(oid)]["points"]]


def _oracle_pairs(yes_rows, no_rows):
    """The test's OWN statement of what may pair: one sample per leg in one
    minute cell, at different seconds or the same one. Independent of the code."""
    def cells(rows):
        out: dict[int, list] = {}
        for ts, p in rows:
            out.setdefault(int(ts.timestamp()) // 60, []).append((ts, p))
        return out
    cy, cn = cells(yes_rows), cells(no_rows)
    pairs = []
    for key in sorted(set(cy) & set(cn)):
        if len(cy[key]) == 1 and len(cn[key]) == 1:
            pairs.append((cy[key][0], cn[key][0]))
    return pairs


def _venue_points(res, name):
    for o in res["outcomes"]:
        if o["name"] == name:
            return [pt for pt in o["history"] if pt.get("provenance") == "venue_history"]
    return []


# ── the ship ────────────────────────────────────────────────────────────────


def test_an_asynchronous_real_shape_pair_draws_its_move():
    raw_yes, raw_no = _async_raw()
    shared_exact = {t for t, _ in raw_yes} & {t for t, _ in raw_no}
    assert not shared_exact, "the fixture must have the venue's shape: no shared second"

    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(raw_yes), "tok_no": _clob(raw_no)}))
    res = _read(market, _captures(), payload)
    vh = res["venue_history"]

    assert vh["state"] == "warm", vh.get("refusals")
    assert REFUSED_FIELD not in json.dumps(vh.get("refusals") or [])

    pairs = _oracle_pairs(_payload_rows(payload, YES_ID), _payload_rows(payload, NO_ID))
    straddled = [(y, n) for y, n in pairs if abs(y[1] + n[1] - 1.0) >= 1e-9]
    assert straddled, "the move must straddle some minutes, or this arm cannot bite"
    # Every cell pair is admitted under the reader's OWN scale contract (no sum
    # here is near the squeeze threshold), straddled minutes included: each half
    # is served at its own second, so neither is asked to stand for the other's.
    assert vh["points_served"] == 2 * len(pairs)

    yes_pts = _venue_points(res, "Yes")
    values = [pt["probability"] for pt in yes_pts]
    assert min(values) == pytest.approx(0.13)
    assert max(values) == pytest.approx(0.9995)
    # The chart reaches the move's end, not the last capture before it.
    assert max(datetime.fromisoformat(pt["timestamp"]) for pt in yes_pts) >= BASE + timedelta(
        minutes=200
    )

    # Everything the venue sent that was not served is COUNTED, in its own field.
    kept_total = len(_payload_rows(payload, YES_ID)) + len(_payload_rows(payload, NO_ID))
    assert vh["paired_points_withheld"] == kept_total - 2 * len(pairs)
    paired_ts = {t for y, n in pairs for t in (y[0], n[0])}
    unpaired = [t for oid in (YES_ID, NO_ID) for t, _p in _payload_rows(payload, oid)
                if t not in paired_ts]
    assert unpaired, "a missing minute must leave a kept half alone, or this arm cannot bite"
    served_ts = {pt["timestamp"] for n in ("Yes", "No") for pt in _venue_points(res, n)}
    assert not served_ts & {t.isoformat() for t in unpaired}
    assert vh["unsupported_points_withheld"] == 0


def test_every_served_point_is_an_original_observation_at_its_own_clock():
    raw_yes, raw_no = _async_raw()
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(raw_yes), "tok_no": _clob(raw_no)}))
    res = _read(market, _captures(), payload)

    own = {"Yes": dict(raw_yes), "No": dict(raw_no)}
    other = {"Yes": dict(raw_no), "No": dict(raw_yes)}
    served_any = False
    for name in ("Yes", "No"):
        for pt in _venue_points(res, name):
            served_any = True
            ts = datetime.fromisoformat(pt["timestamp"])
            assert ts in own[name], f"{name}: {ts} was never observed on this leg"
            assert ts not in other[name], f"{name}: stamped at the partner's clock"
            assert pt["probability"] == pytest.approx(own[name][ts], abs=1e-9)
            # Knowledge time is its OWN field: never earlier than the quote,
            # never more than one grain later, and never written as `timestamp`.
            known = datetime.fromisoformat(pt["pair_known_at"])
            assert ts <= known < ts + timedelta(seconds=60)
            partner_ts = known if known != ts else None
            if partner_ts is not None:
                assert partner_ts in other[name], "knowledge time is the partner's real clock"
    assert served_any
    # Freshness is the latest ORIGINAL observation served, not a pair's later knowledge.
    vh = res["venue_history"]
    served_ts = [
        datetime.fromisoformat(pt["timestamp"])
        for name in ("Yes", "No") for pt in _venue_points(res, name)
    ]
    assert vh["observed_through"] == max(served_ts).isoformat()


def test_compaction_keeps_both_halves_of_every_pair_either_half_kept():
    raw_yes, raw_no = _async_raw()
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(raw_yes), "tok_no": _clob(raw_no)}))
    kept_y = {t for t, _ in _payload_rows(payload, YES_ID)}
    kept_n = {t for t, _ in _payload_rows(payload, NO_ID)}
    alone_y = {t for t, _ in series.compact_by_band(raw_yes, NOW)}
    alone_n = {t for t, _ in series.compact_by_band(raw_no, NOW)}
    assert alone_y <= kept_y and alone_n <= kept_n, "the union only adds"
    raw_pairs = _oracle_pairs(raw_yes, raw_no)
    widowed = [
        (y[0], n[0]) for y, n in raw_pairs
        if (y[0] in kept_y) != (n[0] in kept_n)
    ]
    assert not widowed, f"{len(widowed)} pairs lost one half to compaction"
    # And it bit: alone, the legs keep halves of different pairs.
    assert any((y[0] in alone_y) != (n[0] in alone_n) for y, n in raw_pairs)
    # Nothing that is not an original observation, nothing moved.
    for oid, raw in ((YES_ID, dict(raw_yes)), (NO_ID, dict(raw_no))):
        for ts, p in _payload_rows(payload, oid):
            assert ts in raw and p == pytest.approx(raw[ts], abs=1e-9)


# ── the pairing rule, unit by unit ──────────────────────────────────────────


def _pairs(a, b):
    from app.utils.async_binary_pair import pair_observations

    return pair_observations(a, b)


def _at(minute, second, tier=FINE):
    return (BASE + timedelta(minutes=minute, seconds=second), tier)


def test_samples_seconds_apart_inside_one_declared_grain_pair():
    assert _pairs([_at(0, 23)], [_at(0, 20)]) == [(0, 0)]
    assert _pairs([_at(0, 0)], [_at(0, 59)]) == [(0, 0)]


def test_a_grain_boundary_is_never_crossed_even_a_second_apart():
    assert _pairs([_at(0, 59)], [_at(1, 0)]) == []
    assert _pairs([_at(1, 0)], [_at(0, 59)]) == []


def test_an_older_cells_sample_is_never_borrowed():
    # No's only sample is 20 s before Yes, in the previous minute: within one
    # grain of distance, but the venue said it about a different minute.
    assert _pairs([_at(1, 10)], [_at(0, 50)]) == []


def test_a_sample_is_never_reused_for_two_partners():
    # Two Yes in one minute, one No: nothing in that cell pairs.
    assert _pairs([_at(0, 10), _at(0, 40)], [_at(0, 20)]) == []
    assert _pairs([_at(0, 20)], [_at(0, 10), _at(0, 40)]) == []


def test_a_missing_partner_pairs_nothing_and_neighbours_still_pair():
    a = [_at(0, 21), _at(1, 22), _at(2, 23)]
    b = [_at(0, 18), _at(2, 19)]
    assert _pairs(a, b) == [(0, 0), (2, 1)]


def test_coarse_and_undeclared_grains_pair_only_at_an_exact_shared_instant():
    hourly = "polymarket_clob_1m_f60"
    assert _pairs([_at(0, 23, hourly)], [_at(0, 20, hourly)]) == []
    for tier in ("", "polymarket_clob"):
        assert _pairs([_at(0, 23, tier)], [_at(0, 20, tier)]) == [], tier
    # Mixed grains: a fine sample and a coarse one are not one cell's statements.
    assert _pairs([_at(0, 23)], [_at(0, 20, hourly)]) == []
    # The #11160 exact rule is unchanged, whatever the label.
    for tier in (hourly, "", FINE):
        assert _pairs([_at(0, 20, tier)], [_at(0, 20, tier)]) == [(0, 0)], tier


def test_an_exact_pair_and_its_cell_mate_do_not_cross_pair():
    # Yes has an exact partner at :20 and a second sample at :40; No has only
    # the :20. The extra Yes is not a second partner for anything.
    assert _pairs([_at(0, 20), _at(0, 40)], [_at(0, 20)]) == [(0, 0)]


# ── reader-level arms ───────────────────────────────────────────────────────


def _one_minute_market(yes_pts, no_pts, **kw):
    market = _async_market(**kw)
    tok_yes = kw.get("tok_yes", "tok_yes")
    tok_no = kw.get("tok_no", "tok_no")
    venue = {tok_yes: _clob(yes_pts)}
    if tok_no != tok_yes:
        venue[tok_no] = _clob(no_pts)
    payload = _fill(market, _Venue(venue))
    return market, payload, _read(market, _captures(), payload)


def _t(minute, second):
    return BASE + timedelta(minutes=minute, seconds=second)


def test_a_rapid_move_inside_one_grain_is_served_at_both_clocks_never_averaged():
    # Minute 1: Yes sampled at :05 before a jump, No at :55 after it. Each is a
    # real quote at its own second; neither is restamped, averaged or completed.
    yes = [(_t(0, 21), 0.13), (_t(1, 5), 0.13), (_t(2, 22), 0.57)]
    no = [(_t(0, 18), 0.87), (_t(1, 55), 0.43), (_t(2, 19), 0.43)]
    _m, _p, res = _one_minute_market(yes, no)
    vh = res["venue_history"]
    assert vh["state"] == "warm", vh.get("refusals")
    assert vh["points_served"] == 6
    assert vh["paired_points_withheld"] == 0
    yes_pts = {pt["timestamp"]: pt for pt in _venue_points(res, "Yes")}
    no_pts = {pt["timestamp"]: pt for pt in _venue_points(res, "No")}
    assert yes_pts[_t(1, 5).isoformat()]["probability"] == 0.13
    assert no_pts[_t(1, 55).isoformat()]["probability"] == 0.43
    # The Yes quote became admissible only once its partner existed — and that
    # instant is published as knowledge, never as the quote's own time.
    assert yes_pts[_t(1, 5).isoformat()]["pair_known_at"] == _t(1, 55).isoformat()
    assert no_pts[_t(1, 55).isoformat()]["pair_known_at"] == _t(1, 55).isoformat()
    assert {pt["probability"] for pt in yes_pts.values()} == {0.13, 0.57}


def test_a_cell_pair_the_squeeze_would_move_still_refuses_the_series_whole():
    # The reader's scale contract is unchanged and still WHOLE-series: a cell
    # whose two quotes sum past the squeeze threshold is not withheld quietly.
    yes = [(_t(0, 21), 0.40), (_t(1, 21), 0.55), (_t(2, 21), 0.40)]
    no = [(_t(0, 18), 0.60), (_t(1, 18), 0.56), (_t(2, 18), 0.60)]
    _m, _p, res = _one_minute_market(yes, no)
    vh = res["venue_history"]
    assert vh["points_served"] == 0
    assert "printed_scale_is_not_the_venue_raw_scale" in json.dumps(vh.get("refusals"))


def test_a_genuine_reversal_survives():
    yes = [(_t(m, 21), p) for m, p in enumerate([0.30, 0.45, 0.25, 0.40])]
    no = [(_t(m, 18), round(1 - p, 4)) for m, p in enumerate([0.30, 0.45, 0.25, 0.40])]
    _m, _p, res = _one_minute_market(yes, no)
    assert [pt["probability"] for pt in _venue_points(res, "Yes")] == [0.30, 0.45, 0.25, 0.40]


@pytest.mark.parametrize("why, kw", [
    ("two conditions (a sibling deadline)", {"no_ext": "0x" + "ab" * 32 + "_no"}),
    ("both legs say Yes", {"no_ext": f"{ZACHARIA_CONDITION}_yes"}),
])
def test_a_pair_that_is_not_one_conditions_yes_and_no_is_still_refused_whole(why, kw):
    yes = [(_t(m, 21), 0.40) for m in range(4)]
    no = [(_t(m, 18), 0.60) for m in range(4)]
    _m, _p, res = _one_minute_market(yes, no, **kw)
    vh = res["venue_history"]
    assert vh["points_served"] == 0, why
    assert REFUSED_FIELD in json.dumps(vh.get("refusals")), why
    assert "paired_points_withheld" not in vh, why


def test_one_token_behind_both_legs_never_enters_pairing():
    """The same series twice is not two tokens. Whatever the old path decides
    for it, the pairing path adds nothing: no counter, no knowledge stamp."""
    yes = [(_t(m, 21), 0.40) for m in range(4)]
    _m, _p, res = _one_minute_market(yes, yes, tok_no="tok_yes")
    assert "paired_points_withheld" not in res["venue_history"]
    for name in ("Yes", "No"):
        for pt in _venue_points(res, name):
            assert "pair_known_at" not in pt


def test_a_bank_with_no_shared_cell_keeps_the_old_refusal():
    # The legs were observed in different minutes altogether: nothing pairs, and
    # the reader says what it said before, not "warm with zero points".
    yes = [(_t(m, 21), 0.40) for m in range(4)]
    no = [(_t(m + 10, 18), 0.60) for m in range(4)]
    _m, _p, res = _one_minute_market(yes, no)
    vh = res["venue_history"]
    assert vh["points_served"] == 0
    assert vh["state"] == "refused"
    assert REFUSED_FIELD in json.dumps(vh.get("refusals"))
    assert "paired_points_withheld" not in vh


def test_the_board_level_capture_comparison_still_refuses_whole():
    # Captures whose squeeze moves the number (0.55 + 0.55) still convict the
    # board; pairing is no way round the per-capture measurement.
    yes = [(_t(m, 21), 0.40) for m in range(4)]
    no = [(_t(m, 18), 0.60) for m in range(4)]
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(yes), "tok_no": _clob(no)}))
    ts = BASE - timedelta(hours=1)
    res = _read(market, [_snap(YES_ID, ts, 0.55), _snap(NO_ID, ts, 0.55)], payload)
    vh = res["venue_history"]
    assert vh["points_served"] == 0
    assert "printed_scale_is_not_the_venue_raw_scale" in json.dumps(vh.get("refusals"))


def test_unsupported_point_accounting_keeps_its_own_meaning(monkeypatch):
    yes = [(_t(m, 21), 0.40) for m in range(4)]
    no = [(_t(m, 18), 0.60) for m in range(4)]
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(yes), "tok_no": _clob(no)}))
    drop_at = _t(2, 21)
    real = futures_route._drop_unsupported_snapshot_points

    def drop_one(rows, *a, **k):
        kept = real(rows, *a, **k)
        return [r for r in kept if getattr(r, "captured_at", None) != drop_at]

    monkeypatch.setattr(futures_route, "_drop_unsupported_snapshot_points", drop_one)
    res = _read(market, _captures(), payload)
    vh = res["venue_history"]
    assert vh["unsupported_points_withheld"] == 1
    # Its widowed partner is a PAIRING withhold, not an unsupported one.
    assert vh["paired_points_withheld"] == 1
    assert vh["points_served"] == 6


def test_C2b_the_withheld_leg_board_is_byte_identical():
    """The unsqueezed board (No leg price-withheld) never enters pairing: same
    served points, same venue block, no new key."""
    t0800 = NOW - timedelta(hours=4)
    t0805 = t0800 + timedelta(minutes=5)
    market = _async_market(no_withheld=True)
    payload = _fill(market, _Venue({
        "tok_yes": _clob([(t0800, 0.35)]),
        "tok_no": _clob([(t0805 + timedelta(seconds=3), 0.25)]),
    }))
    res = _read(market, [_snap(YES_ID, NOW - timedelta(hours=6), 0.35)], payload)
    vh = res["venue_history"]
    assert vh["state"] == "warm"
    assert vh["points_served"] == 2
    assert set(vh) == {
        "state", "tier", "points_served", "outcomes_served", "observed_from",
        "observed_through", "built_at", "fill_status", "scale",
        "unsupported_points_withheld", "fill",
    } | ({"fill_trigger"} if "fill_trigger" in vh else set())
    for name in ("Yes", "No"):
        for pt in _venue_points(res, name):
            assert set(pt) == {"timestamp", "probability", "american_odds", "bookmaker",
                               "provenance"}


def test_C2b_an_unsqueezed_pair_with_same_minute_samples_never_enters_pairing():
    """C2b's board with samples that WOULD pair: the unsqueezed board keeps
    serving every independently timed point, unpaired halves included, and
    gains no pairing field — pairing exists only for a squeezed board."""
    market = _async_market(no_withheld=True)
    yes = [(_t(0, 21), 0.35), (_t(1, 22), 0.36), (_t(2, 23), 0.36)]
    no = [(_t(0, 18), 0.64), (_t(1, 19), 0.64)]
    payload = _fill(market, _Venue({"tok_yes": _clob(yes), "tok_no": _clob(no)}))
    res = _read(market, [_snap(YES_ID, NOW - timedelta(hours=8), 0.35)], payload)
    vh = res["venue_history"]
    assert vh["state"] == "warm"
    assert vh["points_served"] == 5
    assert "paired_points_withheld" not in vh
    for name in ("Yes", "No"):
        for pt in _venue_points(res, name):
            assert "pair_known_at" not in pt


def test_a_synchronous_pair_adds_no_knowledge_stamp():
    """#11160's exact pairs know themselves at their own instant: no new field
    on their points, so its served payload keeps its bytes."""
    yes = [(_t(m, 20), 0.40) for m in range(4)]
    no = [(_t(m, 20), 0.60) for m in range(4)]
    _m, _p, res = _one_minute_market(yes, no)
    assert res["venue_history"]["points_served"] == 8
    for name in ("Yes", "No"):
        for pt in _venue_points(res, name):
            assert "pair_known_at" not in pt


# ── density (the auto-extend gate) counts only what will be drawn ───────────


def test_the_density_gate_counts_admitted_points_only():
    yes = [(_t(m, 21), 0.40) for m in range(4)] + [(_t(5, 21), 0.40)]
    no = [(_t(m, 18), 0.60) for m in range(4)]
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(yes), "tok_no": _clob(no)}))
    accepted, _ = gmh.validate_payload(payload, market, market.outcomes)
    rows = []
    for oid, pts in accepted.items():
        rows += gmh.as_snapshot_rows(oid, "polymarket", pts)
    futures_route._tag_venue_pair(rows, payload, market.outcomes)
    n = futures_route._venue_points_countable_as_density(
        market, market.outcomes, rows, {YES_ID, NO_ID}, field_complete=True,
    )
    assert n == 8


# ── budget: still the combined two-leg bound ────────────────────────────────


def test_an_asynchronous_worst_case_pair_stays_inside_the_combined_budget():
    instants = sorted(
        {NOW - timedelta(minutes=m) for m in range(1, 24 * 60)}
        | {NOW - timedelta(hours=h) for h in range(24, 60 * 24)}
    )
    a = [(ts.replace(second=20), 0.40 + (0.01 if i % 4 == 0 else 0.0) + i * 1e-7)
         for i, ts in enumerate(instants)]
    b = [(ts.replace(second=17), 0.60 + (0.01 if i % 4 == 2 else 0.0) - i * 1e-7)
         for i, ts in enumerate(instants)]
    cond = "0x" + "f6" * 32

    def entry(leg, tok, pts):
        return {"contract": {"venue": "polymarket", "condition_id": cond, "token_id": tok,
                             "outcome_external_id": f"{cond}_{leg}"},
                "points": [gmh.VenuePoint(ts, p, tier=FINE) for ts, p in pts]}

    entries = {501: entry("yes", "t1", a), 502: entry("no", "t2", b)}
    alone_a = len(series.compact_by_band(a, NOW))
    alone_b = len(series.compact_by_band(b, NOW))
    fill._compact_entries([SimpleNamespace(id=501), SimpleNamespace(id=502)], entries, NOW)
    kept_a, kept_b = len(entries[501]["points"]), len(entries[502]["points"])
    assert max(kept_a, kept_b) > PER_LEG, "the arm must reach past one leg's cap"
    assert kept_a <= alone_a + alone_b <= PAIRED_LEG_BOUND
    assert kept_b <= alone_a + alone_b <= PAIRED_LEG_BOUND


def test_the_fixture_tier_is_the_fine_one_the_rig_banks():
    raw_yes, raw_no = _async_raw()
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(raw_yes), "tok_no": _clob(raw_no)}))
    tiers = {r[5] for oid in (YES_ID, NO_ID) for r in payload["outcomes"][str(oid)]["points"]}
    assert len(tiers) == 1
    assert series.declared_resolution_seconds(tiers.pop()) == 60.0
    assert _instants(payload, YES_ID)
