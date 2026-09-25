"""#3013 — a golf card's move is the move of the number it shows.

The card prints the BLEND (the mean of the golfer's per-source prices) and
beside it "up N points today". The move used to be the largest SINGLE source's
dated move, so on 2026-09-25 the FedEx Open de France leader read

    Matthew Fitzpatrick 27.1% (up 26.7 points today)

because DataGolf's winner price jumped 0.169 -> 0.434, while Polymarket's
renormalized price moved about 7 points and Kalshi had no snapshot in the
23-25h window at all. The blend moved about half of what the card claimed.

The served move is now the mean of the per-source DATED deltas, over the
sources that have a 23-25h snapshot (`_set_blend_movement`). The fixture below
is the production specimen: the directive's served prices
{dg 0.421, pm 0.121, k 0.255} and served move 0.2518, with the bases measured on
production the same morning (DataGolf's 23-25h basis sits exactly 0.2518 below
it; Polymarket's raw 0.395 over a 0.170 basis, scaled onto the served 0.121;
Kalshi outcome 231407113 has no in-window snapshot).
"""

import pytest

from app.routes.golf import (
    _aggregate_golfer_outcome,
    _build_tournament_entry,
    _merge_abbreviated_golfers,
)


class _Outcome:
    """The attributes `_aggregate_golfer_outcome` actually reads."""

    def __init__(self, id, name, current_probability, probability_change_24h=None):
        self.id = id
        self.name = name
        self.current_probability = current_probability
        self.probability_change_24h = probability_change_24h
        self.opening_probability = None


class _Market:
    id = 1
    name = "FedEx Open de France - Winner"
    external_id = "golf_fedex_open_de_france"
    source = "datagolf"
    market_metadata: dict = {}


# The production specimen (see the module docstring).
_DG_NOW, _DG_MOVE = 0.421, 0.2518
_DG_BASIS = _DG_NOW - _DG_MOVE
_PM_RAW_NOW, _PM_RAW_BASIS, _PM_SERVED = 0.395, 0.170, 0.121
_PM_SCALE = _PM_SERVED / _PM_RAW_NOW
_K_NOW = 0.255


def _fitzpatrick(order=("datagolf_model", "polymarket", "kalshi")) -> dict[str, dict]:
    rows = {
        "datagolf_model": (_Outcome(232672440, "Matt Fitzpatrick", _DG_NOW), 1.0),
        "polymarket": (_Outcome(233295412, "Matthew Fitzpatrick", _PM_RAW_NOW), _PM_SCALE),
        "kalshi": (_Outcome(231407113, "Matt Fitzpatrick", _K_NOW), 1.0),
    }
    snapshots = {232672440: _DG_BASIS, 233295412: _PM_RAW_BASIS}
    data: dict[str, dict] = {}
    for label in order:
        outcome, scale = rows[label]
        _aggregate_golfer_outcome(outcome, label, data, snapshots, prob_scale=scale)
    return data


def _served(data: dict[str, dict], sources: list[str]) -> dict:
    entry = _build_tournament_entry(
        "fedex_open_de_france", [_Market()], data, [], [1], sources, None, None
    )
    assert entry is not None
    return entry["golfers"][0]


class TestTheServedMoveIsTheBlends:
    def test_the_production_specimen_does_not_claim_the_single_source_move(self):
        """THE guard: 0.2518 is DataGolf's move alone, never the blend's."""
        golfer = _served(_fitzpatrick(), ["datagolf", "polymarket", "kalshi"])
        pm_move = (_PM_RAW_NOW - _PM_RAW_BASIS) * _PM_SCALE
        blend_move = (_DG_MOVE + pm_move) / 2  # the two DATED sources
        assert golfer["movement_24h"] == pytest.approx(blend_move, abs=1e-4)
        assert golfer["movement_24h"] < _DG_MOVE - 0.05, (
            "the card would again print one source's move beside the blend"
        )
        assert golfer["movement_is_dated"] is True

    def test_the_move_equals_the_blend_now_minus_the_blend_then(self):
        """Over the dated sources, mean-of-deltas IS the blend's change."""
        data = _fitzpatrick()
        entry = data["matthew fitzpatrick"]
        dated = entry["dated_deltas"]
        assert set(dated) == {"datagolf_model", "polymarket"}, (
            "Kalshi has no 23-25h snapshot and must not enter the dated mean"
        )
        now = sum(entry["sources"][s] for s in dated) / len(dated)
        then = (_DG_BASIS + _PM_RAW_BASIS * _PM_SCALE) / 2
        assert entry["movement_24h"] == pytest.approx(now - then, abs=2e-3)

    @pytest.mark.parametrize(
        "order",
        [
            ("datagolf_model", "polymarket", "kalshi"),
            ("kalshi", "polymarket", "datagolf_model"),
            ("polymarket", "kalshi", "datagolf_model"),
        ],
    )
    def test_the_move_does_not_depend_on_query_order(self, order):
        a = _fitzpatrick()["matthew fitzpatrick"]["movement_24h"]
        b = _fitzpatrick(order)["matthew fitzpatrick"]["movement_24h"]
        assert a == b


class TestControls:
    def test_an_unchanged_dated_source_pulls_the_move_toward_zero(self):
        """CONTROL: a dated source that did not move is a dated ANSWER ("0"),
        not an absence — the old max-|delta| rule threw it away."""
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(
            _Outcome(1, "Neal Shipley", 0.30), "datagolf_model", data, {1: 0.05}
        )
        _aggregate_golfer_outcome(
            _Outcome(2, "Neal Shipley", 0.20), "kalshi", data, {2: 0.20}
        )
        entry = data["neal shipley"]
        assert entry["movement_24h"] == pytest.approx(0.125)
        assert entry["movement_is_dated"] is True

    def test_a_lone_dated_source_that_is_unchanged_states_no_move(self):
        """CONTROL: one dated source, unchanged — no move, and the undated
        per-write delta on the SAME outcome may not fill in for it."""
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(
            _Outcome(1, "Neal Shipley", 0.20, probability_change_24h=0.15),
            "kalshi",
            data,
            {1: 0.20},
        )
        entry = data["neal shipley"]
        assert entry["movement_24h"] is None
        assert entry["movement_is_dated"] is False

    def test_a_lone_dated_source_passes_through_unchanged(self):
        """CONTROL: with one source, the blend IS that source — same number."""
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(
            _Outcome(1, "Neal Shipley", 0.283153), "datagolf_model", data, {1: 0.03205}
        )
        assert data["neal shipley"]["movement_24h"] == pytest.approx(0.2511, abs=1e-4)

    def test_no_dated_source_falls_back_to_the_undated_rule(self):
        """CONTROL: the #7179 fallback is unchanged — number kept, flag False."""
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(
            _Outcome(1, "Neal Shipley", 0.285, probability_change_24h=0.254),
            "kalshi",
            data,
            {},
        )
        entry = data["neal shipley"]
        assert entry["movement_24h"] == pytest.approx(0.254)
        assert entry["movement_is_dated"] is False

    def test_a_later_outcome_of_the_same_source_replaces_its_delta(self):
        """Lockstep: `sources` is last-write-wins per source, so the dated
        delta must be the SAME outcome's — a later undated outcome drops it."""
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(
            _Outcome(1, "Neal Shipley", 0.30), "kalshi", data, {1: 0.05}
        )
        _aggregate_golfer_outcome(_Outcome(2, "Neal Shipley", 0.28), "kalshi", data, {})
        entry = data["neal shipley"]
        assert entry["sources"] == {"kalshi": 0.28}
        assert entry["dated_deltas"] == {}
        assert entry["movement_is_dated"] is False


class TestTheNameIsPinned:
    """Matt / Matthew flipped between reads: the first outcome seen named it."""

    @pytest.mark.parametrize(
        "order",
        [
            ("datagolf_model", "polymarket", "kalshi"),
            ("polymarket", "kalshi", "datagolf_model"),
            ("kalshi", "polymarket", "datagolf_model"),
        ],
    )
    def test_datagolfs_spelling_wins_in_any_order(self, order):
        golfer = _served(_fitzpatrick(order), ["datagolf", "polymarket", "kalshi"])
        assert golfer["name"] == "Matt Fitzpatrick"

    @pytest.mark.parametrize("first", ["Matt Fitzpatrick", "Matthew Fitzpatrick"])
    def test_without_datagolf_the_longest_form_wins_in_any_order(self, first):
        second = "Matthew Fitzpatrick" if first == "Matt Fitzpatrick" else "Matt Fitzpatrick"
        data: dict[str, dict] = {}
        _aggregate_golfer_outcome(_Outcome(1, first, 0.2), "kalshi", data, {})
        _aggregate_golfer_outcome(_Outcome(2, second, 0.1), "polymarket", data, {})
        assert data["matthew fitzpatrick"]["name"] == "Matthew Fitzpatrick"


class TestTheMergeRecomputesTheBlendMove:
    def test_a_merged_source_joins_the_dated_mean(self):
        merged = _merge_abbreviated_golfers({
            "s scheffler": {
                "name": "S. Scheffler",
                "sources": {"odds_api": 0.20},
                "movement_24h": 0.10,
                "movement_is_dated": True,
                "dated_deltas": {"odds_api": 0.10},
                "undated_change": None,
                "opening_probability": None,
            },
            "scottie scheffler": {
                "name": "Scottie Scheffler",
                "sources": {"datagolf_model": 0.22},
                "movement_24h": None,
                "movement_is_dated": False,
                "dated_deltas": {"datagolf_model": 0.0},
                "undated_change": None,
                "opening_probability": None,
            },
        })
        entry = merged["scottie scheffler"]
        assert entry["movement_24h"] == pytest.approx(0.05)
        assert entry["movement_is_dated"] is True
