"""#10955 (live/212) — the N-leg field-cell PROTOTYPE, asked on the retained Oscars bodies.

PILLARS: TRUTH / FORMATTING. SHIP: the three retained Oscars charts recover
genuinely available history without inventing observations or weakening field
truth.

The fixture is cut from retained artifacts only (provenance inside it): Director
5869747's raw layered Kalshi entries before compaction, and Makeup 58492234's
CLOB fidelity=60 timestamps (prices were not retained). Leg ids are the
production outcome ids. Nothing here touches a route, a fill or the bank.
"""

from __future__ import annotations

import json
import pathlib
import random
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.async_binary_pair import pair_observations
from app.utils.exclusive_field_cell import (
    AMBIGUOUS,
    MEMBER_UNBANKED,
    NOT_MUTUAL,
    PEER_ABSENT,
    cell_at,
    cell_spread_seconds,
    field_cell_squeeze_moves,
    field_cell_leg_ids,
    field_cells,
    verify_field_cells,
)

FIXTURE = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "oscars_field_cells_10955.json").read_text()
)
DIRECTOR = FIXTURE["director"]
MAKEUP = FIXTURE["makeup"]
MK_TIER = MAKEUP["tier"]


def _utc(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def _director_legs() -> dict[int, list[tuple[datetime, str, float]]]:
    return {
        int(oid): [(_utc(t), tier, p) for t, tier, p in leg["points"]]
        for oid, leg in DIRECTOR["legs"].items()
    }


def _obs(legs):
    return {m: [(row[0], row[1]) for row in leg] for m, leg in legs.items()}


def _makeup_legs() -> dict[int, list[tuple[datetime, str]]]:
    return {
        int(oid): [(datetime.fromtimestamp(t, timezone.utc), MK_TIER) for t in leg["stamps"]]
        for oid, leg in MAKEUP["legs"].items()
    }


def _name(case, oid) -> str:
    return case["member_names"][str(oid)]


# ---------------------------------------------------------------- membership


def test_director_real_membership_admits_nothing_six_members_unbanked():
    legs = _director_legs()
    res = field_cells(_obs(legs), DIRECTOR["members"])
    assert len(DIRECTOR["members"]) == 18 and len(legs) == 12
    assert res.cells == []
    assert sorted(_name(DIRECTOR, m) for m in res.unbanked_members) == [
        "David Fincher", "Janus Metz Pedersen ", "Jesse Eisenberg",
        "Mike Leigh", "Na Hong-jin", "Steven Spielberg",
    ]
    assert res.refused == {MEMBER_UNBANKED: sum(len(v) for v in legs.values())}


def test_makeup_real_membership_admits_nothing_three_members_absent():
    legs = _makeup_legs()
    res = field_cells(legs, MAKEUP["members"])
    assert len(MAKEUP["members"]) == 13 and len(legs) == 10
    assert res.cells == []
    assert sorted(_name(MAKEUP, m) for m in res.unbanked_members) == [
        "Cry to Heaven", "Rose", "The Social Reckoning",
    ]


def test_a_leg_outside_the_membership_never_completes_a_cell():
    """The denominator is the members argument, never the legs the bank holds."""
    legs = _obs(_director_legs())
    banked = sorted(legs)
    assert field_cells(legs, banked[:-1] + [10**12]).cells == []


# ---------------------------------------------------------------- Kalshi (Director)


def test_director_subset_cell_preserves_every_raw_instant_and_price():
    legs = _director_legs()
    obs = _obs(legs)
    res = field_cells(obs, sorted(legs))
    assert len(res.cells) == 1
    cell = res.cells[0]
    at = cell_at(obs, cell)
    assert at == _utc("2026-10-18T16:31:00+00:00")
    assert cell_spread_seconds(obs, cell) == 0.0
    values = {m: legs[m][i][2] for m, i in cell.items()}
    nolan = next(m for m in cell if _name(DIRECTOR, m) == "Christopher Nolan")
    assert values[nolan] == 0.625
    assert all(legs[m][i][1] == "kalshi_candle_1m" for m, i in cell.items())
    assert round(sum(values.values()), 6) == 1.1
    # Today's scale contract: the #23 squeeze MOVES a 1.10 column, so admitting
    # this cell would refuse the whole series — the arithmetic the rule inherits.
    assert field_cell_squeeze_moves(values, source="kalshi") is True


def test_kalshi_candles_share_a_grid_so_the_skew_bound_adds_no_cell():
    """Kalshi peers are absent, never skewed: the cells equal the exact-instant cells."""
    legs = _director_legs()
    obs = _obs(legs)
    exact: dict = {}
    for m, leg in obs.items():
        for ts, tier in leg:
            exact.setdefault((ts, tier), set()).add(m)
    exact_cells = [k for k, v in exact.items() if v == set(obs)]
    res = field_cells(obs, sorted(obs))
    assert sorted(cell_at(obs, c) for c in res.cells) == sorted(ts for ts, _ in exact_cells)


def test_director_leader_quote_with_no_peer_is_refused_not_carried():
    legs = _director_legs()
    obs = _obs(legs)
    nolan = next(m for m in obs if _name(DIRECTOR, m) == "Christopher Nolan")
    last = obs[nolan][-1]
    assert last == (_utc("2026-10-22T14:43:00+00:00"), "kalshi_candle_1m")
    res = field_cells(obs, sorted(obs))
    assert all(c[nolan] != len(obs[nolan]) - 1 for c in res.cells)
    assert res.refused.get(PEER_ABSENT, 0) > 0
    assert set(res.refused) <= {PEER_ABSENT}


# ---------------------------------------------------------------- Polymarket (Makeup)


def test_makeup_subset_cells_bound_skew_and_keep_each_tokens_own_second():
    legs = _makeup_legs()
    res = field_cells(legs, sorted(legs))
    ats = sorted(cell_at(legs, c) for c in res.cells)
    assert ats == [
        datetime(2026, 10, 15, 15, 0, 51, tzinfo=timezone.utc),
        datetime(2026, 10, 15, 16, 0, 40, tzinfo=timezone.utc),
    ]
    first = min(res.cells, key=lambda c: cell_at(legs, c))
    assert cell_spread_seconds(legs, first) == 14.0
    wicker = next(m for m in legs if _name(MAKEUP, m) == "Wicker")
    assert legs[wicker][first[wicker]][0] == datetime(2026, 10, 15, 15, 0, 37, tzinfo=timezone.utc)
    # The exact-instant rule admits none of them: each token is stamped at its own second.
    stamps = {m: {legs[m][i][0] for i in range(len(legs[m]))} for m in legs}
    assert not set.intersection(*stamps.values())


def test_makeup_hour_with_two_tokens_unquoted_is_refused_for_absence():
    """2026-10-08 12:00Z: Madden and Michael have no sample that hour at the venue."""
    legs = _makeup_legs()
    res = field_cells(legs, sorted(legs))
    hour = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    assert not any(hour <= cell_at(legs, c) < hour + timedelta(hours=1) for c in res.cells)
    absent = {
        _name(MAKEUP, m) for m, leg in legs.items()
        if not any(hour <= ts < hour + timedelta(hours=1) for ts, _ in leg)
    }
    assert absent == {"Madden", "Michael"}


def test_makeup_hour_whose_total_spread_is_32s_is_refused_not_chained():
    """2026-10-09 00:00Z: all ten present, Wicker :20 → Madden :52 — adjacent gaps ≤30 s, spread 32 s."""
    legs = _makeup_legs()
    hour = datetime(2026, 10, 9, 0, tzinfo=timezone.utc)
    window = {
        m: [x for x in leg if hour <= x[0] < hour + timedelta(minutes=5)] for m, leg in legs.items()
    }
    assert all(len(v) == 1 for v in window.values())
    stamps = sorted(v[0][0] for v in window.values())
    assert (stamps[-1] - stamps[0]).total_seconds() == 32.0
    assert max((b - a).total_seconds() for a, b in zip(stamps, stamps[1:])) <= 30.0
    res = field_cells(legs, sorted(legs))
    assert not any(hour <= cell_at(legs, c) < hour + timedelta(hours=1) for c in res.cells)


def test_two_members_is_exactly_the_11157_pair_rule_on_real_tokens():
    legs = _makeup_legs()
    ids = sorted(legs)
    for a in ids:
        for b in ids:
            if a >= b:
                continue
            res = field_cells({a: legs[a], b: legs[b]}, [a, b])
            mine = sorted((c[a], c[b]) for c in res.cells)
            assert mine == pair_observations(legs[a], legs[b])


@pytest.mark.parametrize("seed", range(40))
def test_two_members_is_exactly_the_11157_pair_rule_on_jittered_legs(seed):
    rng = random.Random(seed)
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    tiers = ["polymarket_clob_1d_f1", "polymarket_clob_max_f60", "polymarket_clob_x_f0"]

    def leg():
        t, out = 0.0, []
        for _ in range(rng.randint(5, 40)):
            t += rng.choice([1, 5, 20, 40, 61, 3600])
            out.append((base + timedelta(seconds=t), rng.choice(tiers)))
        return out

    a, b = leg(), leg()
    res = field_cells({1: a, 2: b}, [1, 2])
    assert sorted((c[1], c[2]) for c in res.cells) == pair_observations(a, b)


# ---------------------------------------------------------------- controls


T0 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
F60 = "polymarket_clob_max_f60"


def _at(seconds: float, tier: str = F60):
    return (T0 + timedelta(seconds=seconds), tier)


def test_a_chain_of_adjacent_gaps_is_not_a_cell():
    # The anchor (leg 1, sparsest, lowest id) sits in the MIDDLE: each end is
    # within 20 s of it, and 40 s from the other end.
    legs = {1: [_at(20)], 2: [_at(0)], 3: [_at(40)]}
    res = field_cells(legs, [1, 2, 3])
    assert res.cells == []
    assert res.refused == {NOT_MUTUAL: 1, PEER_ABSENT: 2}


def test_a_member_ambiguous_only_from_a_peers_side_admits_nothing():
    # From leg 1 each other leg offers one candidate; leg 2's sample sits
    # exactly between leg 3's two quotes (S = 5 s each), so it has two.
    legs = {1: [_at(1)], 2: [_at(5)], 3: [_at(0), _at(10)]}
    res = field_cells(legs, [1, 2, 3])
    assert res.cells == []
    assert res.refused.get(NOT_MUTUAL, 0) >= 1


def test_two_candidates_in_one_member_is_ambiguity_and_admits_nothing():
    # Leg 2 quotes twice 20 s apart, so each of its samples has S = 10 s, and
    # both sit exactly 10 s from legs 1 and 3: two candidates, no cell.
    legs = {1: [_at(10)], 2: [_at(0), _at(20)], 3: [_at(10)]}
    res = field_cells(legs, [1, 2, 3])
    assert res.cells == []
    # The disposition is named: legs 1 and 3 each see two candidates (ambiguous);
    # leg 2's quotes each see one per leg but belong to no unique clique.
    assert res.refused == {AMBIGUOUS: 2, NOT_MUTUAL: 2}


def test_undeclared_grain_pairs_only_an_exact_shared_instant():
    tier = "polymarket_clob"  # the fill's fallback label — no declared grain
    assert field_cells({1: [_at(0, tier)], 2: [_at(1, tier)]}, [1, 2]).cells == []
    assert len(field_cells({1: [_at(0, tier)], 2: [_at(0, tier)]}, [1, 2]).cells) == 1


def test_mixed_tiers_never_form_a_cell():
    legs = {1: [_at(0, "kalshi_candle_1m")], 2: [_at(0, "kalshi_candle_60m")]}
    assert field_cells(legs, [1, 2]).cells == []


def test_no_cell_ever_exceeds_the_ceiling_on_random_fields():
    rng = random.Random(7)
    for _ in range(60):
        n = rng.randint(2, 6)
        legs = {}
        for m in range(n):
            t, leg = 0.0, []
            for _k in range(rng.randint(3, 25)):
                t += rng.choice([2, 9, 25, 31, 70, 3600])
                leg.append(_at(t))
            legs[m] = leg
        for c in field_cells(legs, list(legs)).cells:
            assert len(c) == n
            assert cell_spread_seconds(legs, c) <= 30.0


# ---------------------------------------------------------------- identity


def _kalshi_contracts():
    return {
        int(oid): {"venue": "kalshi", "ticker": ext, "outcome_external_id": ext}
        for oid, ext in DIRECTOR["member_external_ids"].items()
    }


def _makeup_contracts():
    return {
        int(oid): {
            "venue": "polymarket", "condition_id": ext, "token_id": tok,
            "outcome_external_id": ext, "resolved_via": "gamma_condition_by_name",
        }
        for oid, ext in MAKEUP["member_external_ids"].items()
        if (tok := MAKEUP["yes_token_ids"].get(oid))
    }


def test_identity_admits_the_real_director_event_family():
    members = DIRECTOR["members"]
    assert field_cell_leg_ids("kalshi", DIRECTOR["market_external_id"], members, _kalshi_contracts()) == sorted(members)


def test_identity_refuses_a_ticker_from_another_event_and_a_missing_contract():
    members = DIRECTOR["members"]
    contracts = _kalshi_contracts()
    stray = dict(contracts)
    stray[members[0]] = {"venue": "kalshi", "ticker": "KXOSCARPIC-27-ODY", "outcome_external_id": "KXOSCARPIC-27-ODY"}
    assert field_cell_leg_ids("kalshi", "KXOSCARDIR-27", members, stray) is None
    gap = dict(contracts)
    gap.pop(members[-1])
    assert field_cell_leg_ids("kalshi", "KXOSCARDIR-27", members, gap) is None


def test_identity_never_takes_a_two_leg_board_off_the_11157_pair_rule():
    members = DIRECTOR["members"][:2]
    assert field_cell_leg_ids("kalshi", "KXOSCARDIR-27", members, _kalshi_contracts()) is None


def test_identity_admits_ten_real_makeup_yes_tokens_and_refuses_a_no_leg_or_repeat():
    contracts = _makeup_contracts()
    members = sorted(contracts)
    assert len(members) == 10
    assert field_cell_leg_ids("polymarket", "805186", members, contracts) == members
    no_leg = dict(contracts)
    c = dict(no_leg[members[0]])
    c["outcome_external_id"] = c["condition_id"] + "_no"
    no_leg[members[0]] = c
    assert field_cell_leg_ids("polymarket", "805186", members, no_leg) is None
    twice = dict(contracts)
    twice[members[1]] = dict(contracts[members[0]], token_id="other")
    assert field_cell_leg_ids("polymarket", "805186", members, twice) is None
    # the real 13-member field: three members hold no contract here → None
    assert field_cell_leg_ids("polymarket", "805186", MAKEUP["members"], contracts) is None


# ---------------------------------------------------------------- reader verification


def _annotate(legs, res):
    ann = {m: [(ts, tier, None) for ts, tier in leg] for m, leg in legs.items()}
    for c in res.cells:
        at = cell_at(legs, c)
        for m, i in c.items():
            ts, tier, _ = ann[m][i]
            ann[m][i] = (ts, tier, at)
    return ann


def test_reader_verifies_the_fills_annotation_on_real_makeup_cells():
    legs = _makeup_legs()
    members = sorted(legs)
    ann = _annotate(legs, field_cells(legs, members))
    assert verify_field_cells(ann, members) is None


def test_reader_refuses_a_cell_independent_compaction_split():
    legs = _makeup_legs()
    members = sorted(legs)
    ann = _annotate(legs, field_cells(legs, members))
    victim = members[3]
    ann[victim] = [row for row in ann[victim] if row[2] is None]
    assert verify_field_cells(ann, members) == "cell_incomplete_after_compaction"


def test_reader_refuses_a_moved_clock_and_an_overwide_cell():
    legs = _makeup_legs()
    members = sorted(legs)
    ann = _annotate(legs, field_cells(legs, members))
    m = members[0]
    i = next(k for k, row in enumerate(ann[m]) if row[2] is not None)
    ts, tier, at = ann[m][i]
    moved = dict(ann)
    moved[m] = list(ann[m])
    moved[m][i] = (ts, tier, at + timedelta(seconds=1))
    assert verify_field_cells(moved, members) == "cell_incomplete_after_compaction"
    shifted = {
        k: [(t, tr, a + timedelta(seconds=1) if a == at else a) for t, tr, a in v]
        for k, v in ann.items()
    }
    assert verify_field_cells(shifted, members) == "cell_at_is_not_the_latest_raw_instant"
    wide = {k: list(v) for k, v in ann.items()}
    wide[m][i] = (at - timedelta(seconds=45), tier, at)
    assert verify_field_cells(wide, members) == "cell_spread_exceeds_tier_bound"


# ---------------------------------------------------------------- isolation


def test_prototype_is_not_wired_into_any_route_or_task():
    app = pathlib.Path(__file__).resolve().parents[1] / "app"
    hits = [
        str(p.relative_to(app)) for p in app.rglob("*.py")
        if p.name != "exclusive_field_cell.py" and "exclusive_field_cell" in p.read_text()
    ]
    assert hits == []
