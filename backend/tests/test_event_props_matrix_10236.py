"""#10236 — the DURING player-props matrix: one typed question, one number.

Contract: `10236-DURING-INPUT-CONTRACT-v1.md` as amended by
`10236-DURING-INPUT-CONTRACT-v1.1-AUTHORITY.md`, plus Live's accepted addendum
(raw under pins, exact-union baselines and clocks, `actual_only` verbatim).

Two halves:

* PURE — `app/utils/event_props_matrix.py` typed, folded, valued and compared
  on hand-built pre-step-9 rows, with the route's REAL `_prop_player_and_stat`
  and `_pregame_mark_is_pregame`.
* INTEGRATED — the real `_build_game_markets` on a live game, proving the
  route wires its OWN window / grade / monotonic / redundant-parent decisions
  into the matrix, that the A0 pair (Kalshi `2+` and Polymarket `O/U 1.5 Over`)
  folds into one row while `player_props` still holds both, and that every
  existing key is byte-identical with the matrix built or not.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_route
from app.routes.events import (
    _game_markets_cache,
    _pregame_mark_is_pregame,
    _prop_player_and_stat,
    _redundant_parent_ids,
    _row_is_only_redundant_parents,
)
from app.utils import event_props_matrix as matrix
from app.utils.event_props_matrix import (
    COMPARISON_REASONS,
    REFUSAL_REASONS,
    STAT_TABLE,
    blend_mean,
    build_during_player_props,
    normalize_subject,
    pin_evidence,
    type_prop_row,
)

BACKEND = Path(__file__).resolve().parents[1]

# Anchors: offset first, never branch on the clock (gotcha #44).
COMMENCE = datetime(2026, 9, 6, 22, 15, tzinfo=timezone.utc)
PIN_SEEN = COMMENCE - timedelta(minutes=10)
NOW_SEEN = COMMENCE + timedelta(minutes=50)


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def _pin(outcomes, observed_at=PIN_SEEN, captured_at=None):
    pm = {"outcomes": {str(k): v for k, v in outcomes.items()}, "commence_time": _iso(COMMENCE)}
    if observed_at is not None:
        pm["observed_at"] = _iso(observed_at)
    if captured_at is not None:
        pm["captured_at"] = _iso(captured_at)
    return pm


# ═════════════════════════════════════════════════════════════════ PURE ═══


def _row(market_name, outcome_name, prob, *, source="kalshi", market_id=1, outcome_id=11,
         observed_at=NOW_SEEN, **extra):
    """One pre-step-9 prop row, in the shape the route's prop branch builds:
    over-oriented, an Under/No leg carrying the complement and `_inverted`."""
    lower = outcome_name.lower().strip()
    inverted = lower.startswith("under") or lower == "no"
    over = None if prob is None else (round(1.0 - prob, 4) if inverted else round(prob, 4))
    row = {
        "market_name": market_name,
        "outcome_name": outcome_name,
        "observed_at": _iso(observed_at),
        "contributor_outcome_ids": [outcome_id],
        "over_probability": over,
        "_inverted": inverted,
        "source": source,
        "_market_id": market_id,
    }
    row.update(extra)
    return row


def _graded(row):
    return row.get("resolution_source") is not None or row.get("hit") is not None


def _build(rows, *, window=lambda r: False, mono=None, redundant=lambda rows: set(),
           pins=None, home="San Diego Padres", away="San Francisco Giants"):
    return build_during_player_props(
        rows,
        player_and_stat=_prop_player_and_stat,
        window_is_closed=window,
        grade_is_in_hand=_graded,
        enforce_monotonicity=mono or (lambda items: items),
        redundant_parent_ids=redundant,
        pregame_mark_by_market_id=pins or {},
        is_pregame=_pregame_mark_is_pregame,
        commence_time=COMMENCE,
        home_team=home,
        away_team=away,
    )


def _one(payload, key):
    rows = [r for r in payload["rows"] if r["question_key"] == key]
    assert len(rows) == 1, f"{key!r} served {len(rows)} times: {[r['question_key'] for r in payload['rows']]}"
    return rows[0]


KALSHI_HITS = "San Francisco at San Diego: Hits"
PM_JUDGE_HITS = "Aaron Judge: Hits O/U 1.5"
TEAMS = matrix._team_forms("San Diego Padres", "San Francisco Giants")


class TestTheTypedQuestion:
    """A2/A4 — the three typed shapes and their keys."""

    def test_kalshi_count_plus(self):
        t = type_prop_row(KALSHI_HITS, "Aaron Judge: 2+", _prop_player_and_stat, TEAMS)
        assert t["question_key"] == "s:aaron judge|hits|full_game|ge:2|over"
        assert (t["kind"], t["count"], t["side"]) == ("count_at_least", 2, "over")
        assert t["subject_label"] == "Aaron Judge"

    def test_polymarket_over_half_line_is_the_next_count(self):
        t = type_prop_row(PM_JUDGE_HITS, "Over", _prop_player_and_stat, TEAMS)
        assert t["question_key"] == "s:aaron judge|hits|full_game|ge:2|over"

    def test_polymarket_under_half_line_is_at_most_k(self):
        t = type_prop_row(PM_JUDGE_HITS, "Under", _prop_player_and_stat, TEAMS)
        assert t["question_key"] == "s:aaron judge|hits|full_game|le:1|under"
        assert (t["kind"], t["count"], t["side"]) == ("count_at_most", 1, "under")

    def test_polymarket_yes_no(self):
        yes = type_prop_row("Pierce Charles: 1+ saves", "Yes", _prop_player_and_stat, TEAMS)
        no = type_prop_row("Pierce Charles: 1+ saves", "No", _prop_player_and_stat, TEAMS)
        assert yes["question_key"] == "s:pierce charles|saves|full_game|ge:1|over"
        assert no["question_key"] == "s:pierce charles|saves|full_game|le:0|under"

    @pytest.mark.parametrize("market,outcome", [
        ("Aaron Judge: Hits O/U 2.0", "Over"),   # integer line: a push is possible
        ("Aaron Judge: Hits O/U 2", "Over"),
        ("Aaron Judge: Hits O/U 1.25", "Over"),
        (KALSHI_HITS, "Aaron Judge: 2.5+"),       # non-integer Kalshi count
        (KALSHI_HITS, "Aaron Judge: 0+"),
        ("Pierce Charles: 1.5+ saves", "Yes"),
    ])
    def test_non_count_lines_are_untyped_predicate(self, market, outcome):
        assert type_prop_row(market, outcome, _prop_player_and_stat, TEAMS) == {"refused": "untyped_predicate"}

    @pytest.mark.parametrize("market,outcome", [
        ("Cardinals vs. Reds: O/U 10.5", "Over"),      # a game total: the fallback branch
        ("Yankees vs Red Sox: Both teams to score", "Yes"),
        ("Some prop with no colon", "Over"),
    ])
    def test_the_fallback_identity_is_refused_never_grouped(self, market, outcome):
        who, _stat = _prop_player_and_stat(market, outcome)
        assert who == outcome.lower(), "fixture must exercise the fallback branch"
        assert type_prop_row(market, outcome, _prop_player_and_stat, TEAMS) == {"refused": "ambiguous_subject"}

    @pytest.mark.parametrize("outcome", ["Detroit: 250+", "Lions: 2+", "Detroit Lions: 3+"])
    def test_a_team_subject_is_refused(self, outcome):
        forms = matrix._team_forms("Detroit Lions", "Buffalo Bills")
        t = type_prop_row("Detroit vs Buffalo: Passing Yards", outcome, _prop_player_and_stat, forms)
        assert t == {"refused": "team_subject"}

    def test_new_orleans_is_its_locality_not_a_player(self):
        forms = matrix._team_forms("New Orleans Saints", "Atlanta Falcons")
        t = type_prop_row("Atlanta vs New Orleans: Receptions", "New Orleans: 250+",
                          _prop_player_and_stat, forms)
        assert t == {"refused": "team_subject"}

    @pytest.mark.parametrize("market,outcome", [
        ("Yankees at Red Sox: 1st 5 Innings Strikeouts", "Gerrit Cole: 5+"),
        ("Sean Manaea: Outs Recorded O/U 16.5", "Over"),
        ("Brandon Marsh: Hits + Runs + RBIs O/U 1.5", "Over"),
        ("Ashton Jeanty: Receiving Yards O/U 24.5", "Over"),
    ])
    def test_a_stat_outside_the_table_is_untyped_stat(self, market, outcome):
        assert type_prop_row(market, outcome, _prop_player_and_stat, TEAMS) == {"refused": "untyped_stat"}

    def test_subject_normalisation_joins_accent_and_full_stop_spellings(self):
        a = type_prop_row("Ronald Acuña Jr.: Total Bases O/U 1.5", "Over", _prop_player_and_stat, TEAMS)
        b = type_prop_row("Atlanta at Miami: Total Bases", "Ronald Acuna Jr: 2+", _prop_player_and_stat, TEAMS)
        assert a["question_key"] == b["question_key"] == "s:ronald acuna jr|total_bases|full_game|ge:2|over"
        assert normalize_subject("  Ronald   Acuña  Jr. ") == "ronald acuna jr"


#: A3 — every admitted spelling, proved against a real market name retained in
#: the repo. `(spelling, market, outcome, file holding that market name)`.
ADMITTED_SPELLINGS = [
    ("hits", "Trea Turner: Hits O/U 2.5", "Over", "tests/test_a_runs_map_is_not_four_players_props_3594.py"),
    ("home runs", "Aaron Judge: Home Runs O/U 1.5", "Over", "tests/test_futures_categorization.py"),
    ("total bases", "Brandon Marsh: Total Bases O/U 2.5", "Over", "tests/test_runs_map_is_made_of_runs_3995.py"),
    ("rbis", "Jose Altuve: RBIs O/U 1.5", "Over", "tests/test_a_runs_map_is_not_four_players_props_3594.py"),
    ("runs", "Cubs at Cardinals: Runs", "Seiya Suzuki: 1+", "tests/test_futures_categorization.py"),
    ("strikeouts", "Grant Holmes: Strikeouts O/U 3.5", "Over", "tests/test_search_family_headline_answers_7261.py"),
    ("walks", "Kyle Schwarber: Walks O/U 0.5", "Over", "tests/test_a_runs_map_is_not_four_players_props_3594.py"),
    ("stolen bases", "Tampa Bay vs Atlanta: Stolen Bases", "Ronald Acuna Jr: 1+", "tests/test_pitcher_prop_stat_keys_5097.py"),
    ("receptions", "Ashton Jeanty: Receptions O/U 2.5", "Over", "tests/test_football_ou_props_leave_the_points_ladder_6909.py"),
    ("passing completions", "Kirk Cousins: Passing Completions O/U 7.5", "Over", "tests/test_football_ou_props_leave_the_points_ladder_6909.py"),
    ("passing attempts", "Bo Nix: Passing Attempts O/U 35.5", "Over", "tests/test_football_ou_props_leave_the_points_ladder_6909.py"),
    ("points", "Aaron Gordon: Points O/U 14.5", "Over", "tests/test_backfill_winners.py"),
    ("rebounds", "Aaron Nesmith: Rebounds O/U 3.5", "Over", "tests/test_backfill_winners.py"),
    ("assists", "Lakers at Celtics: Assists", "LeBron James: 8+", "tests/test_futures_categorization.py"),
    ("shots on goal", "Edmonton at Vancouver: Shots on Goal", "Connor McDavid: 3+", "tests/test_futures_categorization.py"),
    ("saves", "Pierce Charles: 1+ saves", "Yes", "tests/test_yes_no_player_props_keep_their_player_9608.py"),
]


class TestEveryAdmittedSpelling:
    """A3: a spelling ships only with a retained real market fixture."""

    @pytest.mark.parametrize("spelling,market,outcome,source_file", ADMITTED_SPELLINGS,
                             ids=[s[0] for s in ADMITTED_SPELLINGS])
    def test_the_spelling_types_on_its_retained_market(self, spelling, market, outcome, source_file):
        assert market in (BACKEND / source_file).read_text(), (
            f"{market!r} is not retained in {source_file} — the fixture this spelling ships on is gone"
        )
        expected = matrix._STAT_BY_SPELLING[spelling]
        typed = type_prop_row(market, outcome, _prop_player_and_stat, TEAMS)
        assert typed.get("stat_key") == expected, typed

    def test_no_spelling_ships_without_a_fixture(self):
        table = {s for row in STAT_TABLE for s in row[4]}
        assert table == {s[0] for s in ADMITTED_SPELLINGS}

    @pytest.mark.parametrize("spelling", ["goals", "home run", "rbi", "runs scored"])
    def test_v1_1_spellings_with_no_real_market_are_refused(self, spelling):
        assert spelling not in matrix._STAT_BY_SPELLING


class TestTheFold:
    """A1 — fold on the typed key, value by 9b's own rule."""

    def test_the_a0_pair_folds_into_one_row_with_the_union_mean(self):
        rows = [
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.40, source="kalshi", market_id=1, outcome_id=11),
            _row(PM_JUDGE_HITS, "Over", 0.44, source="polymarket", market_id=2, outcome_id=21),
        ]
        out = _one(_build(rows), "s:aaron judge|hits|full_game|ge:2|over")
        assert out["current"]["state"] == "quoted"
        assert out["current"]["probability"] == blend_mean([0.40, 0.44]) == 0.42
        assert out["current"]["basis"] == "blend_mean"
        assert [(c["source"], c["outcome_id"], c["probability"]) for c in out["contributors"]] == [
            ("kalshi", 11, 0.40), ("polymarket", 21, 0.44),
        ]
        assert out["_market_ids"] == [1, 2]
        assert out["contributor_outcome_ids"] == [11, 21]
        assert out["_market_id"] == 1

    def test_a_single_source_row_says_so(self):
        out = _one(_build([_row(KALSHI_HITS, "Aaron Judge: 2+", 0.40)]),
                   "s:aaron judge|hits|full_game|ge:2|over")
        assert out["current"]["basis"] == "single_source"

    def test_the_subject_label_comes_from_kalshi_first(self):
        rows = [
            _row("Aaron JUDGE: Hits O/U 1.5", "Over", 0.44, source="polymarket", market_id=2, outcome_id=5),
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.40, source="kalshi", market_id=1, outcome_id=11),
        ]
        out = _build(rows)["rows"][0]
        assert out["subject"] == {"key": "aaron judge", "label": "Aaron Judge", "kind": "player"}
        assert [c["source"] for c in out["contributors"]] == ["kalshi", "polymarket"]

    def test_blend_mean_is_9bs_arithmetic(self):
        for vals in ([0.4, 0.44], [0.1, 0.2, 0.35], [0.0], [0.33333, 0.66667, 0.5, 0.12345]):
            assert blend_mean(vals) == round(sum(vals) / len(vals), 4)

    def test_9b_calls_the_one_helper(self):
        src = (BACKEND / "app/routes/events.py").read_text()
        assert "avg_prob = blend_mean(probs)" in src
        assert "round(sum(probs) / len(probs), 4)" not in src


class TestHonestExtremes:
    """§4.1 — the interest band is the old card's editorial rule, not a quote rule."""

    @pytest.mark.parametrize("prob", [0.0, 0.01, 0.99, 1.0])
    def test_finite_extremes_are_quoted(self, prob):
        out = _build([_row(KALSHI_HITS, "Aaron Judge: 3+", prob)])["rows"][0]
        assert out["current"]["state"] == "quoted"
        assert out["current"]["probability"] == prob

    def test_a_zero_is_not_dropped_by_the_monotonic_pass(self):
        """The shared function drops `0.0` as a dead quote; the matrix keeps it."""
        def dropping_zero(items):
            return [i for i in items if i["over_probability"] > 0]
        out = _build([_row(KALSHI_HITS, "Aaron Judge: 4+", 0.0)], mono=dropping_zero)
        assert out["rows"][0]["current"]["probability"] == 0.0
        assert out["coverage"]["refused"]["monotonic_conflict"] == 0

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), None])
    def test_a_missing_or_non_finite_price_is_unavailable(self, bad):
        row = _row(KALSHI_HITS, "Aaron Judge: 2+", 0.4)
        row["over_probability"] = bad
        out = _build([row])["rows"][0]
        assert out["current"] == {"state": "unavailable", "probability": None, "basis": None, "observed_at": None}
        assert out["comparison"]["reason"] == "not_quoted"

    def test_one_unavailable_contributor_makes_the_union_unavailable(self):
        good = _row(KALSHI_HITS, "Aaron Judge: 2+", 0.40)
        bad = _row(PM_JUDGE_HITS, "Over", 0.44, source="polymarket", market_id=2, outcome_id=21)
        bad["over_probability"] = float("nan")
        out = _build([good, bad])["rows"][0]
        assert out["current"]["state"] == "unavailable"


class TestUnderRows:
    """A5 + addendum 3 — an under row carries its OWN quote and a server key."""

    def test_an_under_row_carries_its_own_price_and_complement(self):
        row = _row(PM_JUDGE_HITS, "Under", 0.32, source="polymarket", market_id=2, outcome_id=22)
        assert row["over_probability"] == 0.68 and row["_inverted"]
        out = _build([row])["rows"][0]
        assert out["question_key"] == "s:aaron judge|hits|full_game|le:1|under"
        assert out["current"]["probability"] == 0.32
        assert out["contributors"][0]["probability"] == 0.32
        assert out["complement_question_key"] == "s:aaron judge|hits|full_game|ge:2|over"
        assert out["predicate"] == {"kind": "count_at_most", "count": 1, "side": "under", "label": "1 or fewer"}

    def test_an_over_row_has_no_complement(self):
        out = _build([_row(KALSHI_HITS, "Aaron Judge: 2+", 0.4)])["rows"][0]
        assert out["complement_question_key"] is None
        assert out["predicate"]["label"] == "2+"

    def test_an_under_row_with_no_over_row_is_served_not_invented(self):
        out = _build([_row(PM_JUDGE_HITS, "Under", 0.32, source="polymarket", outcome_id=22)])
        assert [r["question_key"] for r in out["rows"]] == ["s:aaron judge|hits|full_game|le:1|under"]

    def test_monotonic_runs_on_over_oriented_copies(self):
        seen = []
        def spy(items):
            seen.append([(i["threshold"], i["over_probability"]) for i in items])
            return items
        rows = [
            _row("Aaron Judge: Hits O/U 0.5", "Under", 0.20, source="polymarket", market_id=3, outcome_id=31),
            _row(PM_JUDGE_HITS, "Under", 0.32, source="polymarket", market_id=2, outcome_id=22),
        ]
        _build(rows, mono=spy)
        assert seen == [[(0, 0.8), (1, 0.68)]]


class TestActualOnly:
    """§4.2 + addendum 4 — a graded row never gets a live chance."""

    def test_a_graded_row_carries_its_grade_verbatim_and_no_price(self):
        row = _row(PM_JUDGE_HITS, "Under", 0.99, source="polymarket", outcome_id=22,
                   actual=1, hit=True, is_winner=None, resolution_source=None)
        out = _build([row])["rows"][0]
        assert out["current"] == {"state": "actual_only", "probability": None, "basis": None, "observed_at": None}
        assert out["result"] == {"actual": 1, "hit": True, "is_winner": None, "resolution_source": None}
        assert out["contributors"][0]["probability"] is None
        assert out["comparison"]["reason"] == "not_quoted"

    def test_a_graded_row_survives_a_closed_window(self):
        row = _row(KALSHI_HITS, "Aaron Judge: 2+", 0.99, hit=True, actual=2)
        out = _build([row], window=lambda r: True)
        assert out["rows"][0]["current"]["state"] == "actual_only"
        assert out["coverage"]["refused"]["window_closed"] == 0


class TestClocks:
    """§4.5 — contributor clocks verbatim; the blend's is the oldest; unknown poisons."""

    def test_the_blend_clock_is_the_oldest_contributor(self):
        old, new = NOW_SEEN - timedelta(minutes=30), NOW_SEEN
        rows = [
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.40, observed_at=new),
            _row(PM_JUDGE_HITS, "Over", 0.44, source="polymarket", market_id=2, outcome_id=21, observed_at=old),
        ]
        out = _build(rows)["rows"][0]
        assert out["current"]["observed_at"] == _iso(old)
        assert [c["observed_at"] for c in out["contributors"]] == [_iso(new), _iso(old)]

    def test_one_unknown_clock_makes_the_blend_clock_unknown(self):
        rows = [
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.40),
            _row(PM_JUDGE_HITS, "Over", 0.44, source="polymarket", market_id=2, outcome_id=21, observed_at=None),
        ]
        assert _build(rows)["rows"][0]["current"]["observed_at"] is None

    def test_last_updated_is_never_read(self):
        row = _row(KALSHI_HITS, "Aaron Judge: 2+", 0.40, observed_at=None, last_updated=_iso(NOW_SEEN))
        out = _build([row])["rows"][0]
        assert out["current"]["observed_at"] is None
        assert out["contributors"][0]["observed_at"] is None


class TestComparison:
    """§4.4 + addendum 1/2 — only a raw pregame pin over the exact set compares."""

    def test_under_pin_is_raw_never_flipped(self):
        row = _row(PM_JUDGE_HITS, "Under", 0.32, source="polymarket", market_id=2, outcome_id=22)
        out = _build([row], pins={2: _pin({22: 0.30})})["rows"][0]
        assert out["comparison"]["state"] == "comparable"
        assert out["comparison"]["baseline"]["probability"] == 0.30
        assert out["comparison"]["delta_points"] == 2.0
        assert out["comparison"]["baseline"]["basis"] == "pregame_pin"
        assert out["comparison"]["baseline"]["observed_at"] == _iso(PIN_SEEN)

    def test_a_single_source_pin_pair(self):
        out = _build([_row(KALSHI_HITS, "Aaron Judge: 2+", 0.55)], pins={1: _pin({11: 0.40})})["rows"][0]
        assert out["comparison"]["delta_points"] == 15.0

    def test_the_union_baseline_is_the_mean_of_every_members_own_pin(self):
        rows = [
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.40),
            _row(PM_JUDGE_HITS, "Over", 0.44, source="polymarket", market_id=2, outcome_id=21),
        ]
        pins = {1: _pin({11: 0.30}), 2: _pin({21: 0.36}, observed_at=PIN_SEEN - timedelta(minutes=5))}
        cmp_ = _build(rows, pins=pins)["rows"][0]["comparison"]
        assert cmp_["baseline"]["probability"] == 0.33
        assert cmp_["baseline"]["observed_at"] == _iso(PIN_SEEN - timedelta(minutes=5))
        assert cmp_["delta_points"] == 9.0

    def test_one_missing_pin_makes_the_union_unavailable(self):
        rows = [
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.40),
            _row(PM_JUDGE_HITS, "Over", 0.44, source="polymarket", market_id=2, outcome_id=21),
        ]
        cmp_ = _build(rows, pins={1: _pin({11: 0.30})})["rows"][0]["comparison"]
        assert cmp_ == {"state": "unavailable", "reason": "no_pregame_pin", "baseline": None, "delta_points": None}

    def test_an_in_play_pin_is_not_a_baseline_and_no_opening_line_stands_in(self):
        row = _row(KALSHI_HITS, "Aaron Judge: 2+", 0.55, opening_over_probability=0.35,
                   pregame_mark=0.35, movement=0.2)
        late = _pin({11: 0.40}, observed_at=COMMENCE + timedelta(minutes=3))
        cmp_ = _build([row], pins={1: late})["rows"][0]["comparison"]
        assert cmp_["state"] == "unavailable"
        assert cmp_["reason"] == "baseline_basis_opening_line"

    def test_the_representatives_served_mark_alone_proves_nothing(self):
        row = _row(KALSHI_HITS, "Aaron Judge: 2+", 0.55, pregame_mark=0.40, opening_over_probability=0.40)
        assert _build([row])["rows"][0]["comparison"]["reason"] == "no_pregame_pin"

    def test_a_pin_with_no_clock_is_baseline_clock_unknown(self):
        legacy = _pin({11: 0.40}, observed_at=None, captured_at=PIN_SEEN - timedelta(minutes=10))
        cmp_ = _build([_row(KALSHI_HITS, "Aaron Judge: 2+", 0.55)], pins={1: legacy})["rows"][0]["comparison"]
        assert cmp_["reason"] == "baseline_clock_unknown"

    def test_an_unknown_current_clock(self):
        row = _row(KALSHI_HITS, "Aaron Judge: 2+", 0.55, observed_at=None)
        cmp_ = _build([row], pins={1: _pin({11: 0.40})})["rows"][0]["comparison"]
        assert cmp_["reason"] == "current_clock_unknown"

    def test_a_current_price_older_than_the_pin(self):
        row = _row(KALSHI_HITS, "Aaron Judge: 2+", 0.55, observed_at=PIN_SEEN - timedelta(minutes=1))
        cmp_ = _build([row], pins={1: _pin({11: 0.40})})["rows"][0]["comparison"]
        assert cmp_["reason"] == "baseline_not_earlier"

    def test_pin_evidence_reads_through_the_routes_gate(self):
        calls = []
        def gate(pm, commence):
            calls.append((pm, commence))
            return False
        pm = _pin({11: 0.4})
        assert pin_evidence(pm, 11, COMMENCE, gate) == {"reason": "baseline_basis_opening_line"}
        assert calls == [(pm, COMMENCE)]

    def test_every_emitted_reason_is_in_the_closed_set(self):
        assert set(COMPARISON_REASONS) == {
            "baseline_basis_opening_line", "no_pregame_pin", "baseline_clock_unknown",
            "current_clock_unknown", "baseline_not_earlier", "contributor_set_mismatch", "not_quoted",
        }


class TestCoverage:
    """The closed refusal set, counted once under the first reason, in order."""

    def test_refusals_are_counted_once_in_order(self):
        rows = [
            _row("Cardinals vs. Reds: O/U 10.5", "Over", 0.5, outcome_id=1),           # ambiguous_subject
            _row("Detroit vs Buffalo: Passing Yards", "Detroit: 250+", 0.5, outcome_id=2),  # team_subject
            _row("Ashton Jeanty: Receiving Yards O/U 24.5", "Over", 0.5, outcome_id=3),  # untyped_stat
            _row("Aaron Judge: Hits O/U 2.0", "Over", 0.5, outcome_id=4),              # untyped_predicate
            _row("Juan Soto: Hits O/U 0.5", "Over", 0.5, outcome_id=5),                # window_closed
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.4, outcome_id=6),                   # served
        ]
        out = _build(rows, window=lambda r: r["contributor_outcome_ids"] == [5],
                     home="Detroit Lions", away="Buffalo Bills")
        assert out["coverage"]["refused"] == {
            "ambiguous_subject": 1, "team_subject": 1, "untyped_stat": 1, "untyped_predicate": 1,
            "window_closed": 1, "monotonic_conflict": 0, "redundant_parent": 0,
        }
        assert list(out["coverage"]["refused"]) == list(REFUSAL_REASONS)
        assert out["coverage"]["questions"] == 1
        assert out["coverage"]["scope"] == "linked_markets_loaded_for_event"

    def test_a_capped_or_dropped_question_is_refused_monotonic_conflict(self):
        def cap_and_drop(items):
            out = [dict(items[0])]
            for i in items[1:]:
                if i["threshold"] == 3:
                    out.append({**i, "over_probability": out[-1]["over_probability"]})
                # threshold 4 dropped outright
                elif i["threshold"] != 4:
                    out.append(dict(i))
            return out
        rows = [
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.30, outcome_id=2),
            _row(KALSHI_HITS, "Aaron Judge: 3+", 0.45, outcome_id=3),
            _row(KALSHI_HITS, "Aaron Judge: 4+", 0.10, outcome_id=4),
        ]
        out = _build(rows, mono=cap_and_drop)
        assert [r["predicate"]["count"] for r in out["rows"]] == [2]
        assert out["coverage"]["refused"]["monotonic_conflict"] == 2

    def test_a_question_whose_every_market_is_a_redundant_parent_is_refused(self):
        rows = [
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.30, market_id=7, outcome_id=2),
            _row(PM_JUDGE_HITS, "Over", 0.34, source="polymarket", market_id=8, outcome_id=3),
            _row(KALSHI_HITS, "Juan Soto: 1+", 0.6, market_id=8, outcome_id=4),
        ]
        out = _build(rows, redundant=lambda rows: {8})
        keys = [r["question_key"] for r in out["rows"]]
        # The folded row also belongs to market 7, so it stays (partial match).
        assert keys == ["s:aaron judge|hits|full_game|ge:2|over"]
        assert out["coverage"]["refused"]["redundant_parent"] == 1

    def test_no_typed_row_is_null(self):
        assert _build([_row("Cardinals vs. Reds: O/U 10.5", "Over", 0.5)]) is None
        assert _build([]) is None

    def test_rows_are_server_ordered_and_stats_follow_the_table(self):
        rows = [
            _row("Yankees at Red Sox: Strikeouts", "Gerrit Cole: 6+", 0.4, outcome_id=1),
            _row(KALSHI_HITS, "Juan Soto: 1+", 0.6, outcome_id=2),
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.3, outcome_id=3),
            _row(KALSHI_HITS, "Aaron Judge: 1+", 0.7, outcome_id=4),
        ]
        out = _build(rows)
        assert [r["question_key"] for r in out["rows"]] == [
            "s:aaron judge|hits|full_game|ge:1|over",
            "s:aaron judge|hits|full_game|ge:2|over",
            "s:juan soto|hits|full_game|ge:1|over",
            "s:gerrit cole|strikeouts|full_game|ge:6|over",
        ]
        assert [s["stat_key"] for s in out["stats"]] == ["hits", "strikeouts"]
        assert out["stats"][0] == {
            "stat_key": "hits", "label": "Hits", "unit": "hits", "unit_singular": "hit",
            "period_key": "full_game", "period_label": "Game", "predicate": "count_at_least",
        }
        assert out["contract"] == "10236.v1"
        assert (out["coverage"]["subjects"], out["coverage"]["quoted"]) == (3, 4)

    def test_the_input_rows_are_not_mutated(self):
        rows = [
            _row(KALSHI_HITS, "Aaron Judge: 2+", 0.40),
            _row(PM_JUDGE_HITS, "Over", 0.44, source="polymarket", market_id=2, outcome_id=21),
        ]
        before = copy.deepcopy(rows)
        _build(rows)
        assert rows == before


class TestTheRedundantParentExtraction:
    """#4189's decision, lifted unchanged: the matrix asks the same function."""

    def _m(self, id, market_type, group_id):
        return SimpleNamespace(id=id, market_type=market_type, group_id=group_id)

    def test_a_surviving_member_makes_its_parent_redundant(self):
        markets = [self._m(1, "field", "g"), self._m(2, "container_member", "g")]
        assert _redundant_parent_ids(markets, {1}, {}, ([{"_market_id": 2}],)) == {1}

    def test_a_parent_alone_stays(self):
        markets = [self._m(1, "field", "g"), self._m(2, "container_member", "g")]
        assert _redundant_parent_ids(markets, {1}, {}, ([{"_market_id": 1}],)) == set()

    def test_leg_copy_members_count(self):
        markets = [self._m(1, "field", None)]
        assert _redundant_parent_ids(markets, {1}, {1: {9}}, ([{"_market_ids": [9, 4]}],)) == {1}

    def test_no_candidates_no_work(self):
        assert _redundant_parent_ids([self._m(1, "field", "g")], set(), {}, ([{"_market_id": 1}],)) == set()

    def test_the_row_rule(self):
        assert _row_is_only_redundant_parents({"_market_ids": [1, 2]}, {1, 2}) is True
        assert _row_is_only_redundant_parents({"_market_ids": [1, 2]}, {1}) is False
        assert _row_is_only_redundant_parents({}, {1}) is False


# ═══════════════════════════════════════════════════════════ INTEGRATED ═══


@pytest.fixture(autouse=True)
def _clear_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _event(*, status="live", commence=None):
    event = MagicMock()
    event.id = 15320207
    event.home_team_name = "San Diego Padres"
    event.away_team_name = "New York Yankees"
    event.status = status
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "baseball_mlb"
    event.commence_time = commence
    event.home_score, event.away_score = 2, 3
    event.period, event.game_clock = "Top 6th", None
    event.completed_at = None
    event.box_score_data = None
    event.score_source = event.score_observed_at = None
    return event


def _market(*, id, name, source, commence, market_type=None, group_id=None, pin=None):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = f"KX-{id}" if source == "kalshi" else f"0x{id:064x}"
    market.event_id = 15320207
    market.category = "game_prop"
    market.status = "open"
    market.source = source
    market.sport_id = None
    market.llm_sport_category = "baseball"
    market.commence_time = commence
    market.market_type = market_type
    market.group_id = group_id
    market.group_type = None
    market.market_metadata = {"pregame_mark": pin} if pin is not None else None
    return market


def _outcome(*, id, market_id, name, prob):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market_id
    outcome.name = name
    outcome.current_probability = prob
    outcome.opening_probability = None
    outcome.resolution_source = None
    outcome.is_winner = None
    return outcome


def _db(event, markets, outcomes, observations):
    rows = [
        SimpleNamespace(id=oid, observed_at=seen, price_changed_at=None,
                        resolution_source=None, current_probability=None)
        for oid, seen in observations.items()
    ]
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _result(scalar=event),
        _result(rows=[]),          # #2693 folded_event_ids
        _result(rows=markets),
        _result(all_rows=[]),      # polymarket parent groups
        _result(rows=[]),          # unlinked fallback
        _result(rows=outcomes),
        _result(all_rows=rows),    # #4970 observation load
    ])
    return db


def _page(*, status="live", extra_markets=(), extra_outcomes=()):
    """A live MLB game: Kalshi's Hits ladder for Judge, Polymarket's Judge O/U
    1.5 pair (the A0 shape), and a Polymarket Soto pair nothing else touches."""
    commence = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    pin_seen = commence - timedelta(minutes=10)
    seen = commence + timedelta(minutes=50)
    pin = lambda outcomes: {
        "outcomes": {str(k): v for k, v in outcomes.items()},
        "observed_at": pin_seen.isoformat(),
        "commence_time": commence.isoformat(),
    }
    markets = [
        _market(id=501, name="New York at San Diego: Hits", source="kalshi", commence=commence,
                pin=pin({5011: 0.82, 5012: 0.40, 5013: 0.12, 5014: 0.02})),
        _market(id=502, name="Aaron Judge: Hits O/U 1.5", source="polymarket", commence=commence,
                pin=pin({5021: 0.36, 5022: 0.64})),
        _market(id=503, name="Juan Soto: Hits O/U 0.5", source="polymarket", commence=commence),
        *extra_markets,
    ]
    outcomes = [
        _outcome(id=5011, market_id=501, name="Aaron Judge: 1+", prob=0.99),   # extreme
        _outcome(id=5012, market_id=501, name="Aaron Judge: 2+", prob=0.46),
        _outcome(id=5013, market_id=501, name="Aaron Judge: 3+", prob=0.15),
        _outcome(id=5014, market_id=501, name="Aaron Judge: 4+", prob=0.0),    # finite zero
        _outcome(id=5021, market_id=502, name="Over", prob=0.50),
        _outcome(id=5022, market_id=502, name="Under", prob=0.50),
        _outcome(id=5031, market_id=503, name="Over", prob=0.71),
        _outcome(id=5032, market_id=503, name="Under", prob=0.29),
        *extra_outcomes,
    ]
    observations = {o.id: seen - timedelta(seconds=o.id % 100) for o in outcomes}
    event = _event(status=status, commence=commence)
    response, _status, _ids = asyncio.run(
        events_route._build_game_markets(event.id, _db(event, markets, outcomes, observations))
    )
    return response


def _by_key(payload):
    return {r["question_key"]: r for r in payload["during_player_props"]["rows"]}


class TestTheServedMatrix:

    def test_the_a0_pair_is_one_cell_while_player_props_keeps_both(self):
        payload = _page()
        rows = _by_key(payload)
        judge2 = rows["s:aaron judge|hits|full_game|ge:2|over"]
        assert judge2["contributor_outcome_ids"] == [5012, 5021]
        assert judge2["current"]["probability"] == blend_mean([0.46, 0.50]) == 0.48
        legacy = {tuple(p["contributor_outcome_ids"]): p for p in payload["player_props"]}
        assert (5012,) in legacy and (5021,) in legacy, (
            "player_props must still serve Kalshi 2+ and Polymarket Over 1.5 as two rows (A0 is not fixed there)"
        )

    def test_the_consistency_invariant_in_both_directions(self):
        payload = _page()
        rows = _by_key(payload)
        checked_equal = checked_superset = 0
        for p in payload["player_props"]:
            ids = set(p["contributor_outcome_ids"])
            for r in rows.values():
                mine = set(r["contributor_outcome_ids"])
                if mine == ids and r["predicate"]["side"] == "over":
                    assert r["current"]["probability"] == p["over_probability"]
                    assert r["current"]["observed_at"] == p["observed_at"]
                    checked_equal += 1
                elif ids < mine:
                    p_clock = datetime.fromisoformat(p["observed_at"])
                    r_clock = datetime.fromisoformat(r["current"]["observed_at"])
                    assert r_clock <= p_clock
                    checked_superset += 1
        assert checked_equal >= 2 and checked_superset >= 2, (checked_equal, checked_superset)

    def test_extremes_the_old_card_deletes_are_quoted_here(self):
        payload = _page()
        legacy_ids = {i for p in payload["player_props"] for i in p["contributor_outcome_ids"]}
        assert 5011 not in legacy_ids and 5014 not in legacy_ids, "control: step 9's band deleted both"
        rows = _by_key(payload)
        assert rows["s:aaron judge|hits|full_game|ge:1|over"]["current"]["probability"] == 0.99
        assert rows["s:aaron judge|hits|full_game|ge:4|over"]["current"]["probability"] == 0.0

    def test_the_under_row_and_its_pins_through_the_route(self):
        rows = _by_key(_page())
        under = rows["s:aaron judge|hits|full_game|le:1|under"]
        assert under["current"]["probability"] == 0.50
        assert under["complement_question_key"] == "s:aaron judge|hits|full_game|ge:2|over"
        assert under["comparison"]["baseline"]["probability"] == 0.64
        assert under["comparison"]["delta_points"] == -14.0
        judge2 = rows["s:aaron judge|hits|full_game|ge:2|over"]
        assert judge2["comparison"]["baseline"]["probability"] == blend_mean([0.40, 0.36]) == 0.38
        assert judge2["comparison"]["delta_points"] == 10.0
        soto = rows["s:juan soto|hits|full_game|ge:1|over"]
        assert soto["comparison"]["reason"] == "no_pregame_pin"

    def test_every_existing_key_is_byte_identical_with_or_without_the_matrix(self, monkeypatch):
        with_matrix = _page()
        assert with_matrix["during_player_props"] is not None
        _game_markets_cache.clear()
        monkeypatch.setattr(events_route, "build_during_player_props", lambda *a, **k: None)
        without = _page()
        with_matrix.pop("during_player_props")
        without.pop("during_player_props")
        # Clocks are taken from `now` per build, so compare after re-basing.
        assert _strip_clocks(with_matrix) == _strip_clocks(without)

    @pytest.mark.parametrize("status", ["scheduled", "final", "completed"])
    def test_null_unless_the_served_game_is_live(self, status):
        assert _page(status=status)["during_player_props"] is None

    def test_null_when_nothing_types(self):
        payload = _page(
            extra_markets=(),
        )
        assert payload["during_player_props"] is not None
        # a live page whose only props are untyped
        commence = datetime.now(timezone.utc) - timedelta(hours=1)
        markets = [_market(id=601, name="Sean Manaea: Outs Recorded O/U 16.5", source="polymarket",
                           commence=commence)]
        outcomes = [_outcome(id=6011, market_id=601, name="Over", prob=0.5)]
        event = _event(commence=commence)
        _game_markets_cache.clear()
        response, _s, _i = asyncio.run(
            events_route._build_game_markets(event.id, _db(event, markets, outcomes, {}))
        )
        assert response["during_player_props"] is None


def _strip_clocks(payload):
    """`observed_at` is relative to each build's `now`; everything else is exact."""
    def walk(node):
        if isinstance(node, dict):
            return {k: (None if k in ("observed_at", "observed_at_by_source") else walk(v))
                    for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(payload)


class TestTheRoutesOwnDecisions:

    def test_the_routes_monotonic_pass_refuses_what_it_caps(self):
        """9c CAPS a rung priced above the rung below it. The old card serves
        the capped number; the matrix refuses the question rather than serve a
        number no contributor quoted."""
        commence = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
        markets = [_market(id=701, name="New York at San Diego: Hits", source="kalshi", commence=commence)]
        outcomes = [
            _outcome(id=7011, market_id=701, name="Gleyber Torres: 1+", prob=0.60),
            _outcome(id=7012, market_id=701, name="Gleyber Torres: 2+", prob=0.30),
            _outcome(id=7013, market_id=701, name="Gleyber Torres: 3+", prob=0.45),
        ]
        event = _event(commence=commence)
        response, _s, _i = asyncio.run(events_route._build_game_markets(
            event.id, _db(event, markets, outcomes, {o.id: commence + timedelta(minutes=40) for o in outcomes})
        ))
        legacy = {p["contributor_outcome_ids"][0]: p for p in response["player_props"]}
        assert legacy[7013]["over_probability"] == 0.30, "control: 9c capped the 3+ rung"
        dpp = response["during_player_props"]
        keys = {r["question_key"] for r in dpp["rows"]}
        assert "s:gleyber torres|hits|full_game|ge:3|over" not in keys
        assert dpp["coverage"]["refused"]["monotonic_conflict"] == 1
        assert {"s:gleyber torres|hits|full_game|ge:1|over",
                "s:gleyber torres|hits|full_game|ge:2|over"} <= keys

    def test_the_routes_redundant_parent_decision_on_the_matrix_population(self):
        """A decomposed container parent and its member both quote Judge O/U
        1.5; the parent also quotes a Soto line no member carries. The folded
        Judge question belongs to the member too and stays; Soto's belongs only
        to the redundant parent and is refused — exactly as the old card drops
        the parent's rows."""
        commence = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
        group = "polymarket:judge-hits"
        markets = [
            _market(id=801, name="Aaron Judge: Hits O/U 1.5", source="polymarket", commence=commence,
                    market_type="field", group_id=group),
            _market(id=802, name="Aaron Judge: Hits O/U 1.5", source="polymarket", commence=commence,
                    market_type="container_member", group_id=group),
            _market(id=803, name="Juan Soto: Hits O/U 0.5", source="polymarket", commence=commence,
                    market_type="field", group_id=group),
        ]
        outcomes = [
            _outcome(id=8011, market_id=801, name="Over", prob=0.44),
            _outcome(id=8021, market_id=802, name="Over", prob=0.40),
            _outcome(id=8031, market_id=803, name="Over", prob=0.70),
        ]
        event = _event(commence=commence)
        response, _s, _i = asyncio.run(events_route._build_game_markets(
            event.id, _db(event, markets, outcomes, {o.id: commence + timedelta(minutes=40) for o in outcomes})
        ))
        legacy_markets = {m for p in response["player_props"] for m in (p.get("_market_ids") or [p["_market_id"]])}
        assert 803 not in legacy_markets, "control: the old card dropped the redundant parent's own row"
        dpp = response["during_player_props"]
        keys = {r["question_key"]: r for r in dpp["rows"]}
        assert set(keys) == {"s:aaron judge|hits|full_game|ge:2|over"}
        judge = keys["s:aaron judge|hits|full_game|ge:2|over"]
        assert judge["_market_ids"] == [801, 802]
        # 9b merged 801+802 IN PLACE on the old card (its representative now
        # carries the 0.42 average). The matrix read its own deep copy, so each
        # contributor still says what it quoted and the mean is taken once.
        assert any(p.get("source_count") == 2 for p in response["player_props"]), "control: 9b merged"
        assert [c["probability"] for c in judge["contributors"]] == [0.40, 0.44] or \
            [c["probability"] for c in judge["contributors"]] == [0.44, 0.40]
        assert judge["current"]["probability"] == blend_mean([0.44, 0.40]) == 0.42
        assert dpp["coverage"]["refused"]["redundant_parent"] == 1
