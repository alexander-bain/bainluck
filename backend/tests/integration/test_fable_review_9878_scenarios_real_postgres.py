"""Regression scenarios for #9878 / #11040 (adapted from Fable independent review of 310ef459).

All defective-behavior assertions from the v3 review reproduction (`D4b`, `C3`,
`C4`, `Q8c`, `Q8d`, `Q8e`) are converted here to assert the required v4 behavior
across both the cached snapshot carrier (`to_plain` -> `from_plain`) and direct ORM rows.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.test_fable_review_9878_real_postgres import (  # noqa: F401
    DB_URL, GROUP_ID, OUT_DIR, _event, _feed, _ids, _leg, _poll, _retained, _sql, _summ,
    engine,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DB_URL, reason="set SEARCH_TEST_DATABASE_URL"),
]

#: The retained read instant (fetch.json "at").
RETAINED_NOW = datetime(2026, 10, 14, 23, 51, 9, 274669, tzinfo=timezone.utc)
#: Retained observation stamps (65678073/74-detail.json outcomes[].last_updated).
OBS_OCT = "2026-10-14T23:46:39.982014+00:00"
OBS_DEC = "2026-10-14T23:46:52.386630+00:00"
#: Retained history point used as the 24h-class basis (65678074-history.json).
BASIS_AT = "2026-10-14T04:31:09.814685+00:00"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def _base(engine):
    r = _retained()
    st = await _poll(_event([_leg(r, "oct"), _leg(r, "dec")]))
    assert not st["errors"], st["errors"]
    ids = await _ids(engine)
    return r, ids


async def _set_outcome(engine, oid, **cols):
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    await _sql(engine, f"UPDATE futures_outcomes SET {sets} WHERE id = :oid", oid=oid, **cols)


async def _set_meta(engine, market_id, patch: dict):
    await _sql(
        engine,
        "UPDATE futures_markets SET market_metadata = coalesce(market_metadata,'{}'::jsonb) || cast(:p as jsonb) WHERE id = :mid",
        p=json.dumps(patch), mid=market_id,
    )


async def _retained_prices(engine, r, ids, *, oct_obs=OBS_OCT, dec_obs=OBS_DEC,
                           oct_yes=None, dec_yes=None):
    """Retained current prices + retained observation stamps (No = 1 - Yes)."""
    o, d = ids[r["cid_oct"]], ids[r["cid_dec"]]
    oy = r["yes_oct"] if oct_yes is None else oct_yes
    dy = r["yes_dec"] if dec_yes is None else dec_yes
    for oid, p, ts in ((o["Yes"], oy, oct_obs), (o["No"], round(1 - oy, 6), oct_obs),
                       (d["Yes"], dy, dec_obs), (d["No"], round(1 - dy, 6), dec_obs)):
        await _set_outcome(engine, oid, current_probability=p, last_updated=datetime.fromisoformat(ts),
                           probability_change_24h=None)
    await _sql(engine, "UPDATE futures_markets SET updated_at = :u WHERE group_id = :g",
               u=datetime.fromisoformat(dec_obs), g=GROUP_ID)
    return o, d


def _record(name, result, extra=None):
    out = OUT_DIR / "scenarios"
    out.mkdir(parents=True, exist_ok=True)
    disp = result["displayed"]
    bundle = next((x for x in disp if x.get("type") == "bundle"), None)
    fam = ((bundle or {}).get("data") or {}).get("deadline_family") or {}
    members = [
        {k: m.get(k) for k in ("market_id", "deadline_label", "yes_outcome_id", "yes_probability",
                               "price_observed_at", "stored_movement_claim", "movement_status",
                               "supported_move_points", "near_certain_open_eligible", "is_near_certain")}
        | {"settlement_state": (m.get("settlement") or {}).get("state"),
           "settlement_result": (m.get("settlement") or {}).get("result"),
           "lagging_local_status": (m.get("settlement") or {}).get("lagging_local_status"),
           "basis": m.get("movement_basis"),
           "timeframe_utc": (m.get("timeframe") or {}).get("sentence_timeframe")}
        for m in fam.get("members") or []
    ]
    summary = {
        "scenario": name,
        "displayed": _summ(disp),
        "family": {k: fam.get(k) for k in ("selection_reason", "representative_market_id",
                                           "represented_count", "verified_family_count",
                                           "provider_market_count", "inventory_complete",
                                           "nested_window_proven", "window_start_kind")} if fam else None,
        "members": members,
        **(extra or {}),
    }
    (out / f"{name}.json").write_text(json.dumps({"summary": summary, "displayed": disp}, indent=1, default=str))
    return summary


def _bundle(summary):
    return next((x for x in summary["displayed"] if x["type"] == "bundle"), None)


def _member(summary, market_id):
    return next(m for m in summary["members"] if m["market_id"] == market_id)


# ── D. Movement binds to the exact Yes outcome ──────────────────────────────


async def test_D1_retained_null_claims_are_no_claim_controls(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids)
    await _set_meta(engine, o["market_id"], {"dated_movement_basis": {str(o["Yes"]): [0.084, BASIS_AT]}})
    await _set_meta(engine, d["market_id"], {"dated_movement_basis": {str(d["Yes"]): [0.31, BASIS_AT]}})
    s = _record("D1_retained_null_control", await _feed(engine, RETAINED_NOW))
    assert _bundle(s)
    assert {m["movement_status"] for m in s["members"]} == {"no_stored_claim"}
    assert s["family"]["selection_reason"] == "nearest_50_pct_fallback"
    assert s["family"]["representative_market_id"] == d["market_id"]


async def test_D2_synthetic_stored_claim_plus_bank_selects_dec31_down_6_5(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids)
    await _set_outcome(engine, d["Yes"], probability_change_24h=-0.065)
    await _set_outcome(engine, d["No"], probability_change_24h=0.065)
    await _set_outcome(engine, o["Yes"], probability_change_24h=-0.011)
    await _set_meta(engine, o["market_id"], {"dated_movement_basis": {str(o["Yes"]): [0.084, BASIS_AT]}})
    await _set_meta(engine, d["market_id"], {"dated_movement_basis": {str(d["Yes"]): [0.31, BASIS_AT]}})
    s = _record("D2_synthetic_hero_dec31", await _feed(engine, RETAINED_NOW))
    dm = _member(s, d["market_id"])
    assert dm["movement_status"] == "hero" and dm["supported_move_points"] == -6.5
    assert dm["yes_outcome_id"] == d["Yes"]
    assert _member(s, o["market_id"])["movement_status"] == "sub_threshold"
    assert s["family"]["selection_reason"] == "largest_supported_dated_move"


async def test_D3_bank_keyed_to_the_No_outcome_never_moves_Yes(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids)
    await _set_outcome(engine, d["Yes"], probability_change_24h=-0.065)
    await _set_outcome(engine, d["No"], probability_change_24h=0.065)
    await _set_meta(engine, d["market_id"], {"dated_movement_basis": {str(d["No"]): [0.69, BASIS_AT]}})
    s = _record("D3_bank_on_no_outcome", await _feed(engine, RETAINED_NOW))
    dm = _member(s, d["market_id"])
    assert dm["movement_status"] == "missing_or_invalid_basis", dm
    assert dm["supported_move_points"] is None


async def test_D4_stale_or_pre_basis_endpoint_refuses_and_D4b_producer_consumer_aligned(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids, dec_obs="2026-10-13T20:00:00+00:00")
    await _set_outcome(engine, d["Yes"], probability_change_24h=-0.065)
    await _set_meta(engine, d["market_id"], {"dated_movement_basis": {str(d["Yes"]): [0.31, BASIS_AT]}})
    s = _record("D4_endpoint_older_than_basis", await _feed(engine, RETAINED_NOW))
    dm = _member(s, d["market_id"]) if s["members"] else None
    assert dm is None or dm["movement_status"] in {"stale_price_observation", "missing_observation_timestamp"}, dm

    # D4b (B1 fix): endpoint 1h after the basis (observed - basis = 1.0h < 12h min).
    # Both producer and consumer now enforce `12h <= observed - basis <= 24h` and
    # refuse the movement claim, falling back to `nearest_50_pct_fallback`.
    await _set_outcome(engine, d["Yes"], last_updated=datetime.fromisoformat("2026-10-14T05:31:09+00:00"))
    await _set_outcome(engine, d["No"], last_updated=datetime.fromisoformat("2026-10-14T05:31:09+00:00"))
    s2 = _record("D4b_endpoint_1h_after_basis", await _feed(engine, RETAINED_NOW))
    dm2 = _member(s2, d["market_id"])
    assert dm2["movement_status"] == "stale_price_observation", dm2
    assert dm2["supported_move_points"] is None, dm2
    assert s2["family"]["selection_reason"] == "nearest_50_pct_fallback", s2


async def test_D5_expired_and_premature_basis_refuse(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids)
    await _set_outcome(engine, d["Yes"], probability_change_24h=-0.065)
    for name, at in (("D5a_basis_25h_old", RETAINED_NOW - timedelta(hours=25)),
                     ("D5b_basis_6h_old", RETAINED_NOW - timedelta(hours=6))):
        await _set_meta(engine, d["market_id"], {"dated_movement_basis": {str(d["Yes"]): [0.31, _iso(at)]}})
        s = _record(name, await _feed(engine, RETAINED_NOW))
        assert _member(s, d["market_id"])["movement_status"] == "basis_out_of_window", s


# ── C. Settlement states ────────────────────────────────────────────────────


async def test_C1_deadline_passed_without_closure(engine):
    r, ids = await _base(engine)
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    obs = _iso(now - timedelta(minutes=10))
    o, d = await _retained_prices(engine, r, ids, oct_obs=obs, dec_obs=obs)
    s = _record("C1_deadline_passed", await _feed(engine, now),
                {"note": "production pool query also filters resolution_date >= now"})
    assert s["family"] is None
    assert not any(x["type"] == "bundle" for x in s["displayed"])


async def test_C2_venue_closure_without_result(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids)
    await _set_meta(engine, o["market_id"], {"price_refresh_venue_settled_since": "2026-10-14T20:00:00+00:00"})
    s = _record("C2_trading_closed", await _feed(engine, RETAINED_NOW))
    assert _member(s, o["market_id"])["settlement_state"] == "trading_closed"


async def test_C3_authoritative_result_on_lagging_open_row_and_precedence(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids)
    # SYNTHETIC authoritative settlement written while our row still reads open,
    # PLUS synthetic stored movement claim + dated basis to prove exclusion from
    # live movement and representative selection even on the cached snapshot path (B2).
    await _set_outcome(engine, o["No"], is_winner=True, resolution_source="api_settlement")
    await _set_outcome(engine, o["Yes"], is_winner=False, resolution_source="api_settlement", probability_change_24h=-0.05)
    await _set_meta(engine, o["market_id"], {"dated_movement_basis": {str(o["Yes"]): [0.123, BASIS_AT]}})
    s = _record("C3_resolved_no_lagging_open", await _feed(engine, RETAINED_NOW))
    direct = _record("C3_resolved_no_lagging_open_DIRECT_ORM", await _feed(engine, RETAINED_NOW, snapshot=False))

    # B2 fix: same rows, same clock -> identical `resolved` decision on cached snapshot and direct ORM paths.
    oct_snap = _member(s, o["market_id"])
    oct_direct = _member(direct, o["market_id"])
    assert oct_snap["settlement_state"] == "resolved", oct_snap
    assert oct_direct["settlement_state"] == "resolved", oct_direct
    assert oct_snap["settlement_result"] == "No"
    assert oct_direct["settlement_result"] == "No"
    assert oct_snap["lagging_local_status"] is True
    assert oct_snap["movement_status"] == "settled_suppressed"
    assert oct_snap["supported_move_points"] is None
    assert oct_snap["near_certain_open_eligible"] is False
    assert s["family"]["representative_market_id"] == d["market_id"]

    # Precedence on both paths: closure + authoritative result -> resolved.
    await _set_meta(engine, o["market_id"], {"price_refresh_venue_settled_since": "2026-10-14T20:00:00+00:00"})
    s2 = _record("C3b_result_plus_closure_SNAPSHOT", await _feed(engine, RETAINED_NOW, snapshot=True))
    s2_direct = _record("C3b_result_plus_closure_DIRECT_ORM", await _feed(engine, RETAINED_NOW, snapshot=False))
    assert _member(s2, o["market_id"])["settlement_state"] == "resolved"
    assert _member(s2_direct, o["market_id"])["settlement_state"] == "resolved"


async def test_C4_conflicting_winners_refuse_the_family(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids)
    await _set_outcome(engine, o["No"], is_winner=True, resolution_source="api_settlement")
    await _set_outcome(engine, o["Yes"], is_winner=True, resolution_source="api_settlement")
    s = _record("C4_conflicting_winners", await _feed(engine, RETAINED_NOW))
    direct = _record("C4_conflicting_winners_DIRECT_ORM", await _feed(engine, RETAINED_NOW, snapshot=False))
    # B2 fix: both direct ORM and cached snapshot paths see conflicting winners and refuse the family.
    assert _bundle(direct) is None, direct
    assert _bundle(s) is None, s


# ── E. Members ──────────────────────────────────────────────────────────────


async def test_E1_unpriced_member_reaches_assembly_or_not(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids)
    await _set_outcome(engine, o["Yes"], current_probability=None)
    s = _record("E1_unpriced_oct31", await _feed(engine, RETAINED_NOW))
    assert _bundle(s) is not None
    assert len(s["members"]) == 2


async def test_E2_equidistant_tie_breaks_to_earliest_deadline(engine):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids, oct_yes=0.40, dec_yes=0.60)
    s = _record("E2_tie_40_60", await _feed(engine, RETAINED_NOW))
    assert s["family"]["representative_market_id"] == o["market_id"], s


# ── F / Q8. Near-certain exception ──────────────────────────────────────────


async def _q8_family(engine, *, basis_at, obs):
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids, oct_obs=obs, dec_obs=obs, oct_yes=0.975, dec_yes=0.985)
    await _set_outcome(engine, o["Yes"], probability_change_24h=0.30)
    await _set_outcome(engine, d["Yes"], probability_change_24h=0.40)
    await _set_meta(engine, o["market_id"], {"dated_movement_basis": {str(o["Yes"]): [0.675, _iso(basis_at)]}})
    await _set_meta(engine, d["market_id"], {"dated_movement_basis": {str(d["Yes"]): [0.585, _iso(basis_at)]}})
    return r, o, d


async def test_Q8a_both_deadlines_jumped_family_eligible(engine):
    r, o, d = await _q8_family(engine, basis_at=RETAINED_NOW - timedelta(hours=19.3),
                               obs=OBS_DEC)
    s = _record("Q8a_family_near_certain", await _feed(engine, RETAINED_NOW))
    assert _bundle(s), s

    # B2 + B3: if a 98.5% member has an authoritative winner on its lagging `open` row,
    # the cached snapshot path must exclude it from the Q8 near-certain exception.
    await _set_outcome(engine, o["Yes"], is_winner=True, resolution_source="api_settlement")
    await _set_outcome(engine, o["No"], is_winner=False, resolution_source="api_settlement")
    await _set_outcome(engine, d["Yes"], is_winner=True, resolution_source="api_settlement")
    await _set_outcome(engine, d["No"], is_winner=False, resolution_source="api_settlement")
    s_settled = _record("Q8a_authoritative_settled_excluded_from_q8", await _feed(engine, RETAINED_NOW))
    assert _bundle(s_settled) is None, s_settled


async def test_Q8b_expired_basis_returns_both_to_the_standard_rule(engine):
    r, o, d = await _q8_family(engine, basis_at=RETAINED_NOW - timedelta(hours=25), obs=OBS_DEC)
    s = _record("Q8b_expired", await _feed(engine, RETAINED_NOW))
    assert _bundle(s) is None
    assert all(x["type"] == "futures" and not x["deadline_member"] for x in s["displayed"]), s


async def test_Q8c_exception_does_not_admit_standalone_card_when_no_family_forms(engine):
    """B3 fix: Dec 31 jumped to 98.5% on dated evidence; Oct 31 sits at 2% with no claim.

    Oct 31 is blocked by the standard near-zero rule, so no family can form. Because
    Q8 is strictly family-local, Dec 31 must NOT leak as a standalone 98.5% card."""
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids, oct_yes=0.02, dec_yes=0.985)
    await _set_outcome(engine, d["Yes"], probability_change_24h=0.40)
    await _set_meta(engine, d["market_id"], {"dated_movement_basis": {str(d["Yes"]): [0.585, BASIS_AT]}})
    s = _record("Q8c_standalone_leak", await _feed(engine, RETAINED_NOW))
    assert _bundle(s) is None
    assert not any(x.get("type") == "futures" and x.get("id") == d["market_id"] for x in s["displayed"]), s
    assert all(x["type"] == "futures" and not x["deadline_member"] for x in s["displayed"]), s


async def test_Q8d_near_zero_band_is_not_exempted_and_placeholder_floor_agrees(engine):
    """B3 fix:
    1) Oct 31 at 2% (<= 3%) with a dated -5 pt move is NOT exempted from `near_zero_binary`.
    2) A leg at <= 5% (e.g. 4.5%) that enters a family has its movement claim suppressed by
       `DEADLINE_MOVER_MIN_PROBABILITY` (0.05) so hero and row movement displays agree."""
    r, ids = await _base(engine)
    o, d = await _retained_prices(engine, r, ids, oct_yes=0.02)
    await _set_outcome(engine, o["Yes"], probability_change_24h=-0.05)
    await _set_meta(engine, o["market_id"], {"dated_movement_basis": {str(o["Yes"]): [0.07, BASIS_AT]}})
    s = _record("Q8d_near_zero_exempted", await _feed(engine, RETAINED_NOW))
    assert _bundle(s) is None, s
    assert not any(x.get("type") == "futures" and x.get("id") == o["market_id"] for x in s["displayed"]), s

    # Now set Oct 31 to 5.0% (having opened at 50%, so it passes `all_outcomes_settled` `< 0.05`
    # and `effectively_resolved`, and sits at the `<= 5%` `DEADLINE_MOVER_MIN_PROBABILITY` floor):
    o, d = await _retained_prices(engine, r, ids, oct_yes=0.05)
    await _set_outcome(engine, o["Yes"], probability_change_24h=-0.05, opening_probability=0.50)
    await _set_outcome(engine, o["No"], opening_probability=0.50)
    await _set_meta(engine, o["market_id"], {"dated_movement_basis": {str(o["Yes"]): [0.10, BASIS_AT]}})
    s_floor = _record("Q8d_placeholder_floor_5_0_pct", await _feed(engine, RETAINED_NOW))
    assert _bundle(s_floor) is not None, s_floor
    oct_m = _member(s_floor, o["market_id"])
    assert oct_m["movement_status"] == "placeholder_floor_suppressed", oct_m
    assert oct_m["supported_move_points"] is None
    assert s_floor["family"]["selection_reason"] == "nearest_50_pct_fallback"
    assert s_floor["family"]["representative_market_id"] == d["market_id"]


async def test_Q8e_producer_and_consumer_agree_on_12h_observation_separation(engine):
    """B1 fix: Observation 1h old, basis 12.5h old -> `observed - basis = 11.5h < 12h`.
    Producer and consumer now enforce the same dated-observation window, so neither
    admits the 97.5% / 98.5% leg as a dated mover."""
    obs = _iso(RETAINED_NOW - timedelta(hours=1))
    r, o, d = await _q8_family(engine, basis_at=RETAINED_NOW - timedelta(hours=12.5), obs=obs)
    s = _record("Q8e_backend_admits_consumer_refuses", await _feed(engine, RETAINED_NOW))
    assert _bundle(s) is None, s
    assert all(x["type"] == "futures" and not x["deadline_member"] for x in s["displayed"]), s


# ── F. Reader-local wording across the reader's midnight ────────────────────


async def test_F1_reader_midnight_payload(engine):
    """Basis Oct 14 12:30 AM PDT, observation Oct 14 11:45 PM PDT, served at Oct 15 12:15 AM PDT."""
    r, ids = await _base(engine)
    now = datetime(2026, 10, 15, 7, 15, tzinfo=timezone.utc)
    obs = "2026-10-15T06:45:00+00:00"
    o, d = await _retained_prices(engine, r, ids, oct_obs=obs, dec_obs=obs)
    await _set_outcome(engine, d["Yes"], probability_change_24h=-0.065)
    await _set_meta(engine, d["market_id"], {"dated_movement_basis": {str(d["Yes"]): [0.31, "2026-10-14T07:30:00+00:00"]}})
    s = _record("F1_reader_midnight", await _feed(engine, now),
                {"server_now": now.isoformat(), "reader_tz": "America/Los_Angeles"})
    assert _member(s, d["market_id"])["movement_status"] == "hero"


async def test_F2_stale_8h_prices_for_age_mark_check(engine):
    r, ids = await _base(engine)
    obs = _iso(RETAINED_NOW - timedelta(hours=8))
    o, d = await _retained_prices(engine, r, ids, oct_obs=obs, dec_obs=obs)
    s = _record("F2_prices_8h_old", await _feed(engine, RETAINED_NOW))
    assert _bundle(s), s
