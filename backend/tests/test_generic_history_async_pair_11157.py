"""#11157 — a Yes/No pair the venue samples at DIFFERENT SECONDS.

PILLARS: TRUTH / FORMATTING. SHIP: a market chart shows its genuine probability
move without inventing observation times or freshness.

PR #11160 kept the instants both legs of an identity-admitted Polymarket pair
share EXACTLY. Its fixture was synchronous; the venue is not. Polymarket's CLOB
`prices-history` stamps each token at its own second (65678073, fidelity=1:
Yes 461 points, No 459, ZERO exact shared instants, 456 shared minutes — Live's
read, #11157 comment 6229278103), so the reader's exact-instant field rule
refused every point of the rebuilt v5756 bank.

These guards are written against that SHAPE, not against the synchronous one,
and carry lane1's early-review guards G1–G11 (artifacts/lane1-11157-grain-
pair-review-20261017/REVIEW.md §4):

  * tokens of ONE condition, each sampled a few seconds from the other, with a
    step move (13% → 99.75%) whose small ticks sometimes fall between the two
    samples of a minute (G1);
  * every served point is an original observation AT ITS OWN CLOCK — never
    restamped to its peer's second; the pair's knowledge time is its own field
    (`pair_known_at`), never `timestamp` or `observed_through` (G1, I8);
  * the skew bound S, same tier, one-to-one, missing / reused samples, coarse
    and undeclared grain, and wrong token / condition / deadline each pair
    NOTHING they should not (G4–G8);
  * a mixed pair across a move is withheld and counted, never a whole-series
    refusal (G3); so is a half whose peer a capture claimed (I9);
  * two builds through last-good never hold one sample at two instants (G2); an
    old bank keeps today's refusal and a forged annotation is refused (G9);
  * the C2b withheld-leg board, unsupported-point accounting, the board-level
    capture comparison, the density gate and the combined two-leg budget (G10,
    G11, I10); and `/probability-timeline`, which never squeezes, keeps serving
    each leg at its own raw instants.

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
    """The test's OWN statement of what pairs in this fixture: one sample of each
    leg in one minute, which the fixture keeps ≤ 15 s apart and ~60 s from every
    other sample. Independent of the code under test."""
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
    assert vh["unpaired_points_withheld"] == kept_total - 2 * len(pairs)
    assert vh["incoherent_pair_points_withheld"] == 0
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


def test_samples_seconds_apart_of_one_tier_pair():
    assert _pairs([_at(0, 23)], [_at(0, 20)]) == [(0, 0)]


def test_G6_the_bound_is_the_skew_not_the_minute():
    # 2 s across a minute boundary pairs; 58 s apart never does, nor 58 s inside one.
    assert _pairs([_at(0, 59)], [_at(1, 1)]) == [(0, 0)]
    assert _pairs([_at(0, 31)], [_at(1, 29)]) == []
    assert _pairs([_at(0, 1)], [_at(0, 59)]) == []
    # Exactly the ceiling pairs; a second past it does not.
    assert _pairs([_at(0, 10)], [_at(0, 40)]) == [(0, 0)]
    assert _pairs([_at(0, 10)], [_at(0, 41)]) == []


def test_G5_a_sample_with_two_candidates_pairs_with_neither():
    # Yes samples 4 s apart: S shrinks to 2 s, and the No at :20 is within it
    # of both. No sample is ever banked twice.
    assert _pairs([_at(0, 18), _at(0, 22)], [_at(0, 20)]) == []
    assert _pairs([_at(0, 20)], [_at(0, 18), _at(0, 22)]) == []


def test_a_sample_is_only_ever_in_one_pair():
    a = [_at(m, 23) for m in range(30)]
    b = [_at(m, 20) for m in range(30)]
    pairs = _pairs(a, b)
    assert len({i for i, _ in pairs}) == len({j for _, j in pairs}) == len(pairs) == 30


def test_a_missing_partner_pairs_nothing_and_neighbours_still_pair():
    a = [_at(0, 21), _at(1, 22), _at(2, 23)]
    b = [_at(0, 18), _at(2, 19)]
    assert _pairs(a, b) == [(0, 0), (2, 1)]


def test_G4_G7_coarse_cross_tier_and_undeclared_grains():
    hourly, half_day = "polymarket_clob_1m_f60", "polymarket_clob_max_f720"
    # f720 points eleven hours apart never pair (lane1's P3).
    assert _pairs([_at(10, 0, half_day)], [_at(11 * 60 + 5, 0, half_day)]) == []
    # f60 legs beyond S stay unpaired; within S they are one call's two quotes.
    assert _pairs([_at(0, 0, hourly)], [_at(5, 0, hourly)]) == []
    assert _pairs([_at(0, 20, hourly)], [_at(0, 17, hourly)]) == [(0, 0)]
    # A minute sample and an hourly one are never one pair (P6).
    assert _pairs([_at(0, 23)], [_at(0, 20, hourly)]) == []
    # An undeclared tier pairs only at an exact shared instant (S = 0).
    for tier in ("", "polymarket_clob"):
        assert _pairs([_at(0, 23, tier)], [_at(0, 20, tier)]) == [], tier
        assert _pairs([_at(0, 20, tier)], [_at(0, 20, tier)]) == [(0, 0)], tier


def test_G_S1_the_coarse_tiers_ceiling_is_thirty_seconds_not_half_the_grain():
    # Lane1's G-S1: on f60 and f720, G/2 is 30 min / 6 h, so only the ceiling can
    # refuse 31 s. Isolated samples, so no local-spacing term applies either.
    for tier in ("polymarket_clob_1m_f60", "polymarket_clob_max_f720"):
        assert _pairs([_at(0, 10, tier)], [_at(0, 40, tier)]) == [(0, 0)], tier
        assert _pairs([_at(0, 10, tier)], [_at(0, 41, tier)]) == [], tier


def test_N4_a_whole_cent_book_is_coherent_despite_float_noise():
    from app.utils.async_binary_pair import pair_is_incoherent

    assert 0.795 + 0.195 - 1.0 != -0.01  # the float noise this guards against
    assert not pair_is_incoherent(0.795, 0.195)
    assert not pair_is_incoherent(0.195, 0.805)
    assert pair_is_incoherent(0.795, 0.194)
    assert pair_is_incoherent(0.40, 0.87)


def test_an_exact_pair_keeps_its_neighbour_out():
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


def test_G3_a_mixed_pair_across_a_move_is_withheld_and_counted():
    # Minute 1: Yes quoted at :20 before a jump, No at :35 after it (lane1's
    # P1/P2 shapes). Neither stands for the other's scale; the rest are served.
    yes = [(_t(0, 21), 0.13), (_t(1, 20), 0.13), (_t(2, 22), 0.57), (_t(3, 22), 0.57)]
    no = [(_t(0, 18), 0.87), (_t(1, 35), 0.43), (_t(2, 19), 0.43), (_t(3, 19), 0.43)]
    _m, _p, res = _one_minute_market(yes, no)
    vh = res["venue_history"]
    assert vh["state"] == "warm", vh.get("refusals")
    assert vh["points_served"] == 6
    assert vh["incoherent_pair_points_withheld"] == 2
    assert vh["unpaired_points_withheld"] == 0
    served = {pt["timestamp"] for n in ("Yes", "No") for pt in _venue_points(res, n)}
    assert _t(1, 20).isoformat() not in served and _t(1, 35).isoformat() not in served
    assert {pt["probability"] for pt in _venue_points(res, "Yes")} == {0.13, 0.57}


def test_G3_a_bigger_move_never_darkens_the_genuine_pairs():
    # y+n = 1.44 sits in the squeeze band: shipped, one such pair refused the
    # WHOLE series (P2). Now it is withheld and the genuine pairs stay drawn.
    yes = [(_t(0, 21), 0.40), (_t(1, 20), 0.57), (_t(2, 22), 0.57)]
    no = [(_t(0, 18), 0.60), (_t(1, 35), 0.87), (_t(2, 19), 0.43)]
    _m, _p, res = _one_minute_market(yes, no)
    vh = res["venue_history"]
    assert vh["points_served"] == 4
    assert vh["incoherent_pair_points_withheld"] == 2


def test_N4_a_pair_summing_to_exactly_99_cents_is_served():
    yes = [(_t(0, 21), 0.795), (_t(1, 20), 0.795)]
    no = [(_t(0, 18), 0.195), (_t(1, 17), 0.194)]
    _m, _p, res = _one_minute_market(yes, no)
    vh = res["venue_history"]
    assert vh["points_served"] == 2, vh
    assert vh["incoherent_pair_points_withheld"] == 2


def test_an_asynchronous_pair_carries_its_knowledge_time_beside_its_own_clock():
    yes = [(_t(0, 21), 0.40), (_t(1, 25), 0.41)]
    no = [(_t(0, 18), 0.60), (_t(1, 19), 0.59)]
    _m, _p, res = _one_minute_market(yes, no)
    yes_pts = {pt["timestamp"]: pt for pt in _venue_points(res, "Yes")}
    no_pts = {pt["timestamp"]: pt for pt in _venue_points(res, "No")}
    assert set(yes_pts) == {_t(0, 21).isoformat(), _t(1, 25).isoformat()}
    assert set(no_pts) == {_t(0, 18).isoformat(), _t(1, 19).isoformat()}
    assert yes_pts[_t(1, 25).isoformat()]["pair_known_at"] == _t(1, 25).isoformat()
    assert no_pts[_t(1, 19).isoformat()]["pair_known_at"] == _t(1, 25).isoformat()


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
    assert "unpaired_points_withheld" not in vh, why


def test_one_token_behind_both_legs_never_enters_pairing():
    """The same series twice is not two tokens. Whatever the old path decides
    for it, the pairing path adds nothing: no counter, no knowledge stamp."""
    yes = [(_t(m, 21), 0.40) for m in range(4)]
    _m, _p, res = _one_minute_market(yes, yes, tok_no="tok_yes")
    assert "paired_points_withheld" not in res["venue_history"]
    for name in ("Yes", "No"):
        for pt in _venue_points(res, name):
            assert "pair_known_at" not in pt


def test_a_bank_with_no_pair_inside_the_bound_keeps_the_old_refusal():
    # The legs were quoted in different minutes altogether: the fill annotates
    # nothing, and the reader says what it said before.
    yes = [(_t(m, 21), 0.40) for m in range(4)]
    no = [(_t(m + 10, 18), 0.60) for m in range(4)]
    _m, payload, res = _one_minute_market(yes, no)
    assert not any(len(r) > 6 for o in payload["outcomes"].values() for r in o["points"])
    vh = res["venue_history"]
    assert vh["points_served"] == 0
    assert vh["state"] == "refused"
    assert REFUSED_FIELD in json.dumps(vh.get("refusals"))
    assert "unpaired_points_withheld" not in vh


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
    assert vh["unpaired_points_withheld"] == 1
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
    assert "unpaired_points_withheld" not in vh
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
    pair, why = futures_route._verify_pair_bank(accepted, payload, market.outcomes)
    assert pair is not None and why is None
    rows = []
    for oid, pts in accepted.items():
        rows += gmh.as_snapshot_rows(oid, "polymarket", pts)
    futures_route._tag_pair_partner(rows, pair)
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
    (tier,) = tiers
    assert series.declared_resolution_seconds(tier) == 60.0
    assert _instants(payload, YES_ID)


# ── G2: two builds through last-good never hold one sample twice ────────────


def test_G2_a_second_build_through_last_good_keeps_every_sample_at_one_instant():
    raw_yes, raw_no = _async_raw()
    market = _async_market()
    venue = _Venue({"tok_yes": _clob(raw_yes), "tok_no": _clob(raw_no)})
    first = _fill(market, venue)
    second = _fill(market, venue, last_good=first)
    for oid, raw in ((YES_ID, dict(raw_yes)), (NO_ID, dict(raw_no))):
        rows = second["outcomes"][str(oid)]["points"]
        stamps = [datetime.fromisoformat(r[0]) for r in rows]
        assert len(stamps) == len(set(stamps))
        assert set(stamps) <= set(raw), "every banked instant is a raw venue instant"
    # Annotations are re-derived, not carried: the second bank's are the first's.
    for oid in (YES_ID, NO_ID):
        ann = lambda p: {r[0]: r[6] for r in p["outcomes"][str(oid)]["points"] if len(r) > 6}  # noqa: E731
        assert ann(first), "the first build must pair, or this arm cannot bite"
        assert ann(second) == ann(first)


# ── G9: an old bank keeps today's rule; a forged annotation is refused ──────


def _bank(market):
    raw_yes, raw_no = _async_raw()
    return _fill(market, _Venue({"tok_yes": _clob(raw_yes), "tok_no": _clob(raw_no)}))


def test_G9_an_old_bank_without_annotations_keeps_todays_refusal():
    market = _async_market()
    payload = _bank(market)
    for entry in payload["outcomes"].values():
        entry["points"] = [r[:6] for r in entry["points"]]
    vh = _read(market, _captures(), payload)["venue_history"]
    assert vh["points_served"] == 0
    assert REFUSED_FIELD in json.dumps(vh.get("refusals"))
    assert "unpaired_points_withheld" not in vh


def _later_annotated_half(payload, oid):
    """A half that is the LATER of its pair, so its `pair_at` is its own instant
    and forging its peer leaves every single-point check passing."""
    for row in payload["outcomes"][str(oid)]["points"]:
        if len(row) > 6 and row[6][0] == row[0] and row[6][1] != row[0]:
            return row
    raise AssertionError("no later half")


def test_G9_an_annotation_whose_peer_is_not_in_the_other_leg_refuses_the_series():
    market = _async_market()
    payload = _bank(market)
    row = _later_annotated_half(payload, YES_ID)
    row[6] = [row[6][0], (datetime.fromisoformat(row[6][1]) - timedelta(seconds=1)).isoformat()]
    vh = _read(market, _captures(), payload)["venue_history"]
    assert vh["points_served"] == 0
    assert vh["state"] == "refused"
    assert "pair_annotation_unverified" in json.dumps(vh.get("refusals"))


def test_G9_a_malformed_annotation_refuses_the_series():
    market = _async_market()
    payload = _bank(market)
    _later_annotated_half(payload, YES_ID)[6] = "yes"
    vh = _read(market, _captures(), payload)["venue_history"]
    assert vh["points_served"] == 0
    assert "pair_annotation_malformed" in json.dumps(vh.get("refusals"))


def _hand_bank(market, yes_points, no_points, *, tok_no="tok_no"):
    yes_o = next(o for o in market.outcomes if o.id == YES_ID)
    no_o = next(o for o in market.outcomes if o.id == NO_ID)
    entries = {
        YES_ID: {"contract": gmh.polymarket_contract(yes_o, token_id="tok_yes",
                                                     resolved_via="outcome_token_metadata"),
                 "points": yes_points},
        NO_ID: {"contract": gmh.polymarket_contract(no_o, token_id=tok_no,
                                                    resolved_via="outcome_token_metadata"),
                "points": no_points},
    }
    return gmh.build_payload(market, entries, now=NOW, stats={}, degraded=False)


def test_G9_one_sample_banked_as_the_peer_of_two_refuses_the_series():
    """Lane1's P4 as a forged bank: Yes :08 and Yes :10 both name No :12, which
    names :08 back. Every single-point check and every pair_at agrees."""
    market = _async_market()
    t08, t10, t12 = _t(0, 8), _t(0, 10), _t(0, 12)
    payload = _hand_bank(
        market,
        [gmh.VenuePoint(t08, 0.40, tier=FINE, pair_at=t12, peer_at=t12),
         gmh.VenuePoint(t10, 0.40, tier=FINE, pair_at=t12, peer_at=t12)],
        [gmh.VenuePoint(t12, 0.60, tier=FINE, pair_at=t12, peer_at=t08)],
    )
    vh = _read(market, _captures(), payload)["venue_history"]
    assert vh["points_served"] == 0
    assert "pair_annotation_unverified" in json.dumps(vh.get("refusals"))


def test_G8_annotations_on_a_bank_whose_tokens_are_not_two_are_never_consulted():
    """Identity is re-derived at read: a bank whose two contracts name ONE token
    reads as today's bank, annotations and all — refused on the field rule."""
    market = _async_market()
    t10, t12 = _t(0, 10), _t(0, 12)
    payload = _hand_bank(
        market,
        [gmh.VenuePoint(t10, 0.40, tier=FINE, pair_at=t12, peer_at=t12)],
        [gmh.VenuePoint(t12, 0.60, tier=FINE, pair_at=t12, peer_at=t10)],
        tok_no="tok_yes",
    )
    vh = _read(market, _captures(), payload)["venue_history"]
    assert vh["points_served"] == 0
    assert REFUSED_FIELD in json.dumps(vh.get("refusals"))
    assert "unpaired_points_withheld" not in vh


def test_a_carried_annotation_the_new_build_cannot_rederive_is_dropped():
    """Last-good held Yes :10 (hourly call) paired with No :12. This build
    fetches only No :12, from the fine call: the halves are now different tiers,
    so the carried Yes :10 loses its annotation instead of naming a peer that no
    longer names it back — and the bank still verifies."""
    market = _async_market()
    hourly = "polymarket_clob_1m_f60"
    t10, t12 = _t(0, 10), _t(0, 12)
    last_good = _hand_bank(
        market,
        [gmh.VenuePoint(t10, 0.40, tier=hourly, pair_at=t12, peer_at=t12)],
        [gmh.VenuePoint(t12, 0.60, tier=hourly, pair_at=t12, peer_at=t10)],
    )
    payload = _fill(market, _Venue({"tok_yes": [], "tok_no": _clob([(t12, 0.60)])}),
                    last_good=last_good)
    yes_rows = payload["outcomes"][str(YES_ID)]["points"]
    assert [r[0] for r in yes_rows] == [t10.isoformat()]
    assert len(yes_rows[0]) == 6
    accepted, _ = gmh.validate_payload(payload, market, market.outcomes)
    assert futures_route._verify_pair_bank(accepted, payload, market.outcomes)[1] is None


def test_a_single_line_read_reports_freshness_from_its_own_quotes():
    """`?outcome_id=` draws one leg. Its `observed_through` is that leg's latest
    quote, never the later knowledge time its pair shares with the other leg."""
    import asyncio
    from unittest.mock import patch

    from tests.test_generic_history_paired_compaction_11157 import _Redis, _Result, _Session

    yes = [(_t(m, 3), 0.40) for m in range(4)]
    no = [(_t(m, 21), 0.60) for m in range(4)]
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(yes), "tok_no": _clob(no)}))
    rc = _Redis({gmh.cache_key(market.id): json.dumps(payload)})
    snaps = _captures()
    db = _Session(_Result(value=market), _Result(rows=snaps), _Result(rows=snaps))
    with (
        patch.object(futures_route, "_request_path_redis", return_value=rc),
        patch.object(futures_route, "_refuted_midpoint_outcome_ids", return_value=set()),
    ):
        res = asyncio.run(futures_route.get_futures_history(
            market.id, outcome_id=YES_ID, hours=168, top_n=10, champion=None,
            db=db, history_range=None,
        ))
    vh = res["venue_history"]
    assert vh["points_served"] == 4, vh
    assert vh["observed_through"] == _t(3, 3).isoformat()


@pytest.mark.parametrize("annotation, reason", [
    ("yes", "pair_annotation_malformed"),
    (["2026-10-16T00:00:10+00:00"], "pair_annotation_malformed"),
    (["not a time", "2026-10-16T00:00:12+00:00"], "pair_annotation_malformed"),
    (["2026-10-16T00:00:10+00:00", "2026-10-16T00:00:12+00:00"],
     "pair_at_is_not_the_later_raw_instant"),
    (["2026-10-16T00:00:12+00:00", "2026-10-16T00:00:08+00:00"],
     "pair_at_is_not_the_later_raw_instant"),
])
def test_parse_points_drops_what_one_annotation_cannot_answer_and_keeps_the_point(
    annotation, reason
):
    row = ["2026-10-16T00:00:10+00:00", 0.4, None, None, None, FINE, annotation]
    points, why = gmh.parse_points([row], not_after=None)
    assert why is None, "a bad annotation never refuses the leg (lane1's R1)"
    (point,) = points
    assert point.observed_at == datetime.fromisoformat(row[0]) and point.probability == 0.4
    assert (point.pair_at, point.peer_at, point.pair_dropped) == (None, None, reason)


def _dropped(row, not_after=None):
    points, why = gmh.parse_points([row], not_after=not_after)
    assert why is None and len(points) == 1
    assert points[0].pair_at is None and points[0].peer_at is None
    return points[0].pair_dropped


def test_parse_points_drops_a_skew_past_the_bound_and_a_pair_after_the_build():
    own = datetime.fromisoformat("2026-10-16T00:00:10+00:00")
    far = own + timedelta(seconds=31)
    row = [own.isoformat(), 0.4, None, None, None, FINE, [far.isoformat(), far.isoformat()]]
    assert _dropped(row) == "pair_skew_exceeds_bound"
    # Only an hourly tier's ceiling (30 s) applies to it, not its grain.
    row[5] = "polymarket_clob_1m_f60"
    assert _dropped(row) == "pair_skew_exceeds_bound"
    # A peer quoted after the build cannot have been known at the build.
    near = own + timedelta(seconds=5)
    row = [own.isoformat(), 0.4, None, None, None, FINE, [near.isoformat(), near.isoformat()]]
    assert _dropped(row, not_after=own + timedelta(seconds=2)) == "pair_at_after_build"
    # And the honest annotation parses, carrying both instants untouched.
    points, why = gmh.parse_points([row], not_after=own + timedelta(seconds=10))
    assert why is None and points[0].observed_at == own
    assert points[0].pair_at == near and points[0].peer_at == near
    assert points[0].pair_dropped == ""


def test_an_unannotated_row_keeps_its_six_columns():
    point = gmh.VenuePoint(_t(0, 10), 0.4, tier=FINE)
    assert len(point.as_row()) == 6
    paired = gmh.VenuePoint(_t(0, 10), 0.4, tier=FINE, pair_at=_t(0, 12), peer_at=_t(0, 12))
    assert paired.as_row()[6] == [_t(0, 12).isoformat(), _t(0, 12).isoformat()]


# ── I9: a capture claiming one half withholds the survivor, never the series ─


def test_I9_a_capture_claiming_one_half_withholds_only_that_pair():
    yes = [(_t(m, 21), 0.40) for m in range(6)]
    no = [(_t(m, 3), 0.60) for m in range(6)]
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(yes), "tok_no": _clob(no)}))
    # A capture of the Yes leg at minute 2's Yes quote claims that instant.
    claim = [_snap(YES_ID, _t(2, 21), 0.40), _snap(NO_ID, _t(2, 21), 0.60)]
    res = _read(market, _captures() + claim, payload)
    vh = res["venue_history"]
    assert vh["state"] == "warm", vh.get("refusals")
    assert REFUSED_FIELD not in json.dumps(vh.get("refusals") or [])
    served = {pt["timestamp"] for n in ("Yes", "No") for pt in _venue_points(res, n)}
    assert _t(2, 21).isoformat() not in served
    # Whatever the claim took, nothing survives without its peer.
    for m in range(6):
        assert (_t(m, 21).isoformat() in served) == (_t(m, 3).isoformat() in served), m
    assert vh["points_served"] + vh["unpaired_points_withheld"] <= 12


# ── UX F1: /probability-timeline never squeezes and is ruled out by name ────


class _Lenient(SimpleNamespace):
    """The timeline route formats the market detail too; a missing attribute
    reads as None there, as an unset column would."""

    def __getattr__(self, name):
        return None


def test_the_timeline_route_serves_each_leg_at_its_own_raw_instants():
    """`get_probability_timeline` (iOS source mode) prints raw per-leg medians
    and venue values — no squeeze, so no denominator to pair for. It keeps one
    entry per raw instant: nothing at a knowledge time a leg was not quoted at,
    no pair field, and each leg's value is that leg's raw quote there."""
    import asyncio
    from unittest.mock import patch

    from tests.test_generic_history_paired_compaction_11157 import _Redis, _Result, _Session

    raw_yes, raw_no = _async_raw()
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(raw_yes), "tok_no": _clob(raw_no)}))
    lenient = _Lenient(**vars(market))
    rc = _Redis({gmh.cache_key(market.id): json.dumps(payload)})
    snaps = _captures()
    db = _Session(_Result(value=lenient), _Result(rows=snaps), _Result(rows=snaps))
    with (
        patch.object(futures_route, "_request_path_redis", return_value=rc),
        patch.object(futures_route, "_refuted_midpoint_outcome_ids", return_value=set()),
    ):
        res = asyncio.run(futures_route.get_probability_timeline(
            market.id, top=10, hours=168, db=db, representation="source",
        ))
    raw = {"Yes": {t.isoformat(): p for t, p in raw_yes},
           "No": {t.isoformat(): p for t, p in raw_no}}
    venue_instants = set(raw["Yes"]) | set(raw["No"])
    venue_seen = 0
    for entry in res["timeline"]:
        assert "pair_known_at" not in json.dumps(entry)
        if entry["timestamp"] not in venue_instants:
            continue  # a capture's hour bucket, ahead of the venue series
        for name, value in entry["outcomes"].items():
            assert entry["timestamp"] in raw[name], f"{name} drawn at a time it was not quoted"
            assert value == pytest.approx(raw[name][entry["timestamp"]], abs=1e-6)
            venue_seen += 1
    assert venue_seen == res["venue_history"]["points_served"] > 0


# ── lane1's R1: an annotation failure is /history's refusal, nobody else's ──


def _timeline(market, payload):
    import asyncio
    from unittest.mock import patch

    from tests.test_generic_history_paired_compaction_11157 import _Redis, _Result, _Session

    rc = _Redis({gmh.cache_key(market.id): json.dumps(payload)})
    snaps = _captures()
    db = _Session(_Result(value=_Lenient(**vars(market))), _Result(rows=snaps),
                  _Result(rows=snaps))
    with (
        patch.object(futures_route, "_request_path_redis", return_value=rc),
        patch.object(futures_route, "_refuted_midpoint_outcome_ids", return_value=set()),
    ):
        return asyncio.run(futures_route.get_probability_timeline(
            market.id, top=10, hours=168, db=db, representation="source",
        ))


def _stripped(payload):
    out = json.loads(json.dumps(payload))
    for entry in out["outcomes"].values():
        entry["points"] = [r[:6] for r in entry["points"]]
    return out


def test_R1_A_a_tightened_bound_never_blanks_the_timeline(monkeypatch):
    """Built at S = 30 s, read at S = 2 s (Live's E1 is the expected trigger):
    the native timeline serves what the same bank stripped of annotations
    serves; `/history` refuses, as G9 requires."""
    from app.utils import async_binary_pair as abp

    market = _async_market()
    payload = _bank(market)
    baseline = _timeline(market, _stripped(payload))["venue_history"]["points_served"]
    assert baseline > 0
    monkeypatch.setattr(abp, "PAIR_SKEW_MAX_SECONDS", 2.0)
    tl = _timeline(market, payload)["venue_history"]
    assert tl["points_served"] == baseline
    vh = _read(market, _captures(), payload)["venue_history"]
    assert vh["points_served"] == 0
    assert "pair_skew_exceeds_bound" in json.dumps(vh.get("refusals"))


def test_R1_B_a_tightened_bound_never_erases_carried_history(monkeypatch):
    """The same change, then a build the venue answers with nothing: the
    last-good carry still holds every banked point, as it would stripped."""
    from app.utils import async_binary_pair as abp

    market = _async_market()
    first = _bank(market)
    monkeypatch.setattr(abp, "PAIR_SKEW_MAX_SECONDS", 2.0)
    silent = _Venue({"tok_yes": [], "tok_no": []})
    carried = _fill(market, silent, last_good=first)
    control = _fill(market, silent, last_good=_stripped(first))
    assert carried["status"] == control["status"] != "empty"
    for oid in (YES_ID, NO_ID):
        # Re-compaction may thin a carried series; it must thin it exactly as
        # it thins the same history with no annotation on it.
        assert _instants(carried, oid) == _instants(control, oid)
        assert len(_instants(carried, oid)) > 100


def test_R1_C_one_unverified_annotation_never_blanks_the_timeline():
    market = _async_market()
    payload = _bank(market)
    baseline = _timeline(market, _stripped(payload))["venue_history"]["points_served"]
    row = _later_annotated_half(payload, YES_ID)
    row[6] = [row[6][0], (datetime.fromisoformat(row[6][1]) - timedelta(seconds=1)).isoformat()]
    assert _timeline(market, payload)["venue_history"]["points_served"] == baseline > 0
    vh = _read(market, _captures(), payload)["venue_history"]
    assert vh["points_served"] == 0
    assert "pair_annotation_unverified" in json.dumps(vh.get("refusals"))


def test_R1_a_refused_pair_bank_is_no_density_for_the_sparse_window_gate():
    """#7936's rule for this refusal too: a series `/history` refuses is density
    nobody draws. A synchronous bank (exact pairs, which the old field rule would
    admit) with one dropped annotation must not hold the window shut."""
    yes = [(_t(m, 20), 0.40) for m in range(40)]
    no = [(_t(m, 20), 0.60) for m in range(40)]
    market = _async_market()
    payload = _fill(market, _Venue({"tok_yes": _clob(yes), "tok_no": _clob(no)}))
    old = NOW - timedelta(days=10)
    recent = _captures()
    wider = recent + [_snap(YES_ID, old, 0.40), _snap(NO_ID, old, 0.60)]

    def read():
        import asyncio
        from unittest.mock import patch

        from tests.test_generic_history_paired_compaction_11157 import (
            _Redis,
            _Result,
            _Session,
        )

        rc = _Redis({gmh.cache_key(market.id): json.dumps(payload)})
        # The 7-day read, then the 30-day widening: the fake answers in order.
        db = _Session(_Result(value=market), _Result(rows=recent), _Result(rows=wider))
        with (
            patch.object(futures_route, "_request_path_redis", return_value=rc),
            patch.object(futures_route, "_refuted_midpoint_outcome_ids", return_value=set()),
        ):
            return asyncio.run(futures_route.get_futures_history(
                market.id, outcome_id=None, hours=168, top_n=10, champion=None,
                db=db, history_range=None,
            ))

    honest = read()
    assert honest["venue_history"]["points_served"] > 20
    assert honest["actual_hours"] == 168

    next(r for r in payload["outcomes"][str(YES_ID)]["points"] if len(r) > 6)[6] = "yes"
    refused = read()
    assert refused["venue_history"]["points_served"] == 0
    assert "pair_annotation_malformed" in json.dumps(refused["venue_history"].get("refusals"))
    assert refused["actual_hours"] > 168, "the refused bank held the sparse window shut"
