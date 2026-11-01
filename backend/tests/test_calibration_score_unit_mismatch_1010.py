"""#1010 — tennis and MMA over/under and handicap lines are not graded from a
score that cannot settle them.

The spreads/totals curves grade every event as ``home + away > line`` /
``(home - away) + spread > 0``. For tennis the stored score counts SETS (sum
2..5) while the lines count GAMES (O/U 15.5..42.5); for MMA the stored score is a
1-0 WINNER FLAG while the lines count ROUNDS. Measured on the 2026-10-11 23:08Z
publish: tennis ``odds_api_totals`` winner rate 0.000 in all nine tournaments
(ECE ~50 each), MMA totals 0.020 over n=100.

Specimen numbers below are those published cells, so the arithmetic the guard
checks is the arithmetic a reader was shown.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import calibration as calibration_route
from app.tasks import precompute_calibration as pc
from tests.test_calibration_spreads_totals import (  # noqa: F401 — autouse fixture
    _bucket_row,
    _disable_sample_gate,
    _FakeDB,
)


class TestFamilyRule:
    @pytest.mark.parametrize(
        "category",
        ["tennis_atp_us_open", "tennis_wta_canadian_open", "mma_mixed_martial_arts", "tennis"],
    )
    def test_ungradeable_families(self, category):
        assert pc.category_has_score_unit_mismatch(category) is True

    @pytest.mark.parametrize(
        "category",
        [
            # Score and line share a unit (points, runs, goals): kept.
            "basketball_nba",
            "americanfootball_nfl",
            "baseball_mlb",
            "icehockey_nhl",
            "soccer_epl",
            # A family is the first `_` segment, never a substring.
            "table_tennis",
            "mmax_league",
            "",
            None,
        ],
    )
    def test_gradeable_families(self, category):
        assert pc.category_has_score_unit_mismatch(category) is False

    def test_sql_form_names_the_same_families(self):
        assert pc.score_unit_mismatch_sql("s.key") == "split_part(s.key, '_', 1) IN ('mma', 'tennis')"
        for family in pc.SCORE_UNIT_MISMATCH_FAMILIES:
            assert f"'{family}'" in pc.score_unit_mismatch_sql("s.key")

    def test_split_counts_outcomes_not_rows_and_names_the_cells(self):
        rows = [
            SimpleNamespace(source="odds_api_totals", category="tennis_wta_canadian_open", n=41),
            SimpleNamespace(source="odds_api_totals", category="basketball_nba", n=300),
            SimpleNamespace(source="odds_api_totals", category="mma_mixed_martial_arts", n=7),
            SimpleNamespace(source="odds_api_totals", category="tennis_wta_canadian_open", n=30),
        ]
        kept, excluded, cells = pc.split_score_unit_mismatch(rows)
        assert [r.category for r in kept] == ["basketball_nba"]
        assert excluded == 78
        assert cells == {
            ("odds_api_totals", "tennis_wta_canadian_open"),
            ("odds_api_totals", "mma_mixed_martial_arts"),
        }


def _row(source, category, bucket_idx, n, winners, avg_prob):
    return _bucket_row(
        bucket_idx=bucket_idx,
        source=source,
        category=category,
        n=n,
        winners=winners,
        avg_prob=avg_prob,
        sum_prob=avg_prob * n,
        sum_sq_err=winners * (1 - avg_prob) ** 2 + (n - winners) * avg_prob**2,
    )


# The published tennis_wta_canadian_open totals cells (bucket 4: 30 rows, 0
# winners; bucket 5: 41 rows, 0 winners), the MMA totals cell, and the matching
# spreads cells — next to NBA cells that must pass through untouched.
SPREADS = [
    _row("odds_api_spreads", "tennis_wta_canadian_open", 4, 25, 16, 0.4703),
    _row("odds_api_spreads", "mma_mixed_martial_arts", 5, 67, 25, 0.512),
    _row("odds_api_spreads", "basketball_nba", 5, 565, 293, 0.500),
]
TOTALS = [
    _row("odds_api_totals", "tennis_wta_canadian_open", 4, 30, 0, 0.4792),
    _row("odds_api_totals", "tennis_wta_canadian_open", 5, 41, 0, 0.5086),
    _row("odds_api_totals", "mma_mixed_martial_arts", 5, 100, 2, 0.545),
    _row("odds_api_totals", "basketball_nba", 5, 565, 295, 0.501),
]
# CONTROL: the moneyline for the same tennis tournament. Who won the match is
# what the stored score DOES say, so the rule must not touch this row.
EVENTS = [
    _row("odds_api", "tennis_wta_canadian_open", 5, 27, 14, 0.5434),
]


@pytest.fixture
async def payload():
    db = _FakeDB(events_rows=EVENTS, spreads_rows=SPREADS, totals_rows=TOTALS)
    return await pc.compute_calibration_payload(db)


class TestPublishedCurve:
    @pytest.mark.asyncio
    async def test_no_tennis_or_mma_spreads_or_totals_bucket_is_published(self, payload):
        leaked = [
            (b["source"], b["category"])
            for b in payload["buckets"]
            if b["source"] in ("odds_api_spreads", "odds_api_totals")
            and pc.category_has_score_unit_mismatch(b["category"])
        ]
        assert leaked == []

    @pytest.mark.asyncio
    async def test_gradeable_spreads_and_totals_pass_through_unchanged(self, payload):
        nba = {
            b["source"]: (b["n"], b["winners"])
            for b in payload["buckets"]
            if b["category"] == "basketball_nba"
        }
        assert nba == {"odds_api_spreads": (565, 293), "odds_api_totals": (565, 295)}

    @pytest.mark.asyncio
    async def test_tennis_moneyline_is_kept(self, payload):
        ml = [
            (b["n"], b["winners"])
            for b in payload["buckets"]
            if b["source"] == "odds_api" and b["category"] == "tennis_wta_canadian_open"
        ]
        assert ml == [(27, 14)]

    @pytest.mark.asyncio
    async def test_the_exclusion_is_named_and_counted(self, payload):
        block = payload["score_unit_filter"]
        assert block["spreads_excluded"] == 25 + 67
        assert block["totals_excluded"] == 30 + 41 + 100
        assert block["excluded"] == 25 + 67 + 30 + 41 + 100
        assert block["rule"] == pc.SCORE_UNIT_MISMATCH_RULE_TEXT
        assert block["excluded_cells"] == [
            ["odds_api_spreads", "mma_mixed_martial_arts"],
            ["odds_api_spreads", "tennis_wta_canadian_open"],
            ["odds_api_totals", "mma_mixed_martial_arts"],
            ["odds_api_totals", "tennis_wta_canadian_open"],
        ]

    @pytest.mark.asyncio
    async def test_excluded_rows_leave_the_outcome_total(self, payload):
        assert payload["total_outcomes"] == 27 + 565 + 565
        assert payload["totals_summary"]["outcomes"] == 565
        assert payload["spreads_summary"]["outcomes"] == 565

    @pytest.mark.asyncio
    async def test_the_exclusion_is_counted_per_cell(self, payload):
        block = payload["score_unit_filter"]
        assert block["excluded_by_cell"] == {
            "odds_api_spreads/mma_mixed_martial_arts": 67,
            "odds_api_spreads/tennis_wta_canadian_open": 25,
            "odds_api_totals/mma_mixed_martial_arts": 100,
            "odds_api_totals/tennis_wta_canadian_open": 30 + 41,
        }
        assert sum(block["excluded_by_cell"].values()) == block["excluded"]
        # The gate reads it back as stated.
        assert census(payload)["score_unit"]["by_cell"] == {
            "mma_mixed_martial_arts": {"odds_api_spreads": 67, "odds_api_totals": 100},
            "tennis_wta_canadian_open": {"odds_api_spreads": 25, "odds_api_totals": 71},
        }

    @pytest.mark.asyncio
    async def test_a_build_with_no_such_rows_reports_a_checked_zero(self):
        db = _FakeDB(spreads_rows=SPREADS[2:], totals_rows=TOTALS[3:])
        payload = await pc.compute_calibration_payload(db)
        assert payload["score_unit_filter"]["excluded"] == 0
        assert payload["score_unit_filter"]["excluded_cells"] == []
        assert payload["score_unit_filter"]["excluded_by_cell"] == {}

    def test_the_corrections_log_points_at_the_live_count(self):
        entry = [c for c in pc.CALIBRATION_CORRECTIONS if c["date"] == "2026-10-11"]
        assert len(entry) == 1
        assert entry[0]["rows"] is None


class _CapturingDB:
    def __init__(self):
        self.statements = []

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return SimpleNamespace(all=lambda: [])


class TestDrillDownSamples:
    """A reader clicking a spreads/totals bucket must not be shown a row the
    curve no longer counts."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("source", ["odds_api_spreads", "odds_api_totals"])
    async def test_spreads_and_totals_samples_exclude_the_families(self, source, monkeypatch):
        monkeypatch.setattr(calibration_route, "_examples_cache", {})
        db = _CapturingDB()
        await calibration_route.calibration_examples(
            db=db, source=source, bucket=5, well_traded=1, limit=5
        )
        assert len(db.statements) == 1
        assert f"NOT ({pc.score_unit_mismatch_sql('s.key')})" in db.statements[0]

    @pytest.mark.asyncio
    async def test_moneyline_samples_are_untouched(self, monkeypatch):
        monkeypatch.setattr(calibration_route, "_examples_cache", {})
        db = _CapturingDB()
        await calibration_route.calibration_examples(
            db=db, source="odds_api", bucket=5, well_traded=1, limit=5
        )
        assert len(db.statements) == 1
        assert "split_part(s.key" not in db.statements[0]


# ---------------------------------------------------------------------------
# The published population's identity moves with the rule, and the move is
# declared to the publish gate rather than slipped past it.
# ---------------------------------------------------------------------------

from app.utils.calibration_publish_gate import (  # noqa: E402
    DECLARED_PREDICATE_SUCCESSIONS,
    PREDICATE_FIELD,
    census,
    evaluate_publish,
)

PUBLISHED_PREDICATE = "3944c947edb78d220ed3bef7defcc526"
CANDIDATE_PREDICATE = "da21d87f0f001c635a813eefb3eb9532"
PAIR = (PUBLISHED_PREDICATE, CANDIDATE_PREDICATE)


class TestPredicateIdentity:
    def test_this_tree_states_the_declared_candidate(self):
        # #1011 (a declared WIDENING) and #938 (a declared narrowing) moved the
        # digest on. Walk the declared chain from this rule's candidate: every
        # step must be declared, so the chain is unbroken to this tree.
        current = pc.population_predicate_fingerprint()
        successor = {old: new for old, new in DECLARED_PREDICATE_SUCCESSIONS}
        step, seen = CANDIDATE_PREDICATE, set()
        while step != current and step not in seen:
            seen.add(step)
            step = successor.get(step, step)
        assert step == current

    def test_the_family_value_is_in_the_digest(self, monkeypatch):
        before = pc.population_predicate_fingerprint()
        monkeypatch.setattr(pc, "SCORE_UNIT_MISMATCH_FAMILIES", ("tennis",))
        assert pc.population_predicate_fingerprint() != before

    def test_the_family_helper_is_in_the_digest(self, monkeypatch):
        before = pc.population_predicate_fingerprint()

        def category_has_score_unit_mismatch(category):  # a widened rule
            return bool(category) and category.split("_", 1)[0] in ("mma", "tennis", "boxing")

        monkeypatch.setattr(pc, "category_has_score_unit_mismatch", category_has_score_unit_mismatch)
        assert pc.population_predicate_fingerprint() != before

    def test_the_split_helper_is_in_the_digest(self, monkeypatch):
        before = pc.population_predicate_fingerprint()

        def split_score_unit_mismatch(rows):  # a rule that drops nothing
            return list(rows), 0, set()

        monkeypatch.setattr(pc, "split_score_unit_mismatch", split_score_unit_mismatch)
        assert pc.population_predicate_fingerprint() != before

    def test_control_an_unrelated_value_does_not_move_it(self, monkeypatch):
        before = pc.population_predicate_fingerprint()
        monkeypatch.setattr(pc, "SCORE_UNIT_MISMATCH_RULE_TEXT", "prose only")
        assert pc.population_predicate_fingerprint() == before

    def test_futures_unit_reuse_is_unaffected(self):
        """The staged UNIT digest keys on the futures statement's bytes, which
        this rule does not touch, so banked units stay resumable. #938 later
        moved it (``dec3026b…`` -> ``5de54fd2…``) by adding a per-outcome flag
        to ``_calibration_population_ctes``; this rule still does not touch it.
        #994 moved it again, deliberately (``5de54fd2…`` -> ``74356774…``): Stage
        B's outer SELECT emits each DataGolf cell's members. Nor that."""
        assert pc.staged_unit_fingerprint() == "7435677428a14a4ecebfe02c9310e101"


def _gate_payload(*, outcomes, predicate, categories, score_unit=None, cells=None):
    """``cells`` is ``{category: {source: n}}``, the canonical bucket rows; by
    default each listed category is one Kalshi cell of its stated size."""
    if cells is None:
        cells = {name: {"kalshi": n} for name, n in categories.items()}
    buckets = []
    for category, by_source in sorted(cells.items()):
        for source, n in sorted(by_source.items()):
            for idx, (part, moved) in enumerate(((n // 2, True), (n - n // 2, False))):
                buckets.append({
                    "bucket_idx": 4 + idx, "source": source, "category": category,
                    "n": part, "winners": part // 2, "sum_prob": part * 0.5,
                    "price_moved": moved,
                })
    payload = {
        "buckets": buckets,
        "by_category": [
            {"category": name, "outcomes": n, "ece": 1.5} for name, n in categories.items()
        ],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes - 100,
        "total_winners": outcomes // 3,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applied": True},
        "truth_evidence": {"rungs": []},
        "population_version": "q271",
        PREDICATE_FIELD: predicate,
    }
    if score_unit is not None:
        payload["score_unit_filter"] = score_unit
    return payload


# The served 23:08Z artifact's tennis_atp_canadian_open, cell by cell: the rule
# removes its 89 spreads and 90 totals outcomes; its 796 sportsbook and 180
# moneyline outcomes say who won the match and must stay.
CANADIAN_PUBLISHED = {"odds_api_bookmaker": 796, "odds_api": 180,
                      "odds_api_totals": 90, "odds_api_spreads": 89}
CANADIAN_KEPT = {"odds_api_bookmaker": 796, "odds_api": 180}
# A second category the rule takes under the 1,000 publish bar.
CINCINNATI_PUBLISHED = {"odds_api_bookmaker": 700, "odds_api": 258, "odds_api_totals": 150}
CINCINNATI_KEPT = {"odds_api_bookmaker": 700, "odds_api": 258}

PUBLISHED_CATS = {"soccer": 250_323, "tennis_atp_canadian_open": 1_155,
                  "tennis_wta_cincinnati_open": 1_108}
CANDIDATE_CATS = {"soccer": 250_323}
PUBLISHED_CELLS = {"soccer": {"kalshi": 250_323},
                   "tennis_atp_canadian_open": CANADIAN_PUBLISHED,
                   "tennis_wta_cincinnati_open": CINCINNATI_PUBLISHED}
# Both tennis categories are parked under the bar: absent from by_category,
# present in the buckets.
CANDIDATE_CELLS = {"soccer": {"kalshi": 250_323},
                   "tennis_atp_canadian_open": CANADIAN_KEPT,
                   "tennis_wta_cincinnati_open": CINCINNATI_KEPT}
SCORE_UNIT_BLOCK = {
    "applies_to": "odds_api_spreads, odds_api_totals (tennis, mma)",
    "rule": "r",
    "excluded": 329,
    "spreads_excluded": 89,
    "totals_excluded": 240,
    "excluded_cells": [
        ["odds_api_spreads", "tennis_atp_canadian_open"],
        ["odds_api_totals", "tennis_atp_canadian_open"],
        ["odds_api_totals", "tennis_wta_cincinnati_open"],
    ],
    "excluded_by_cell": {
        "odds_api_spreads/tennis_atp_canadian_open": 89,
        "odds_api_totals/tennis_atp_canadian_open": 90,
        "odds_api_totals/tennis_wta_cincinnati_open": 150,
    },
}
PUBLISHED_POP = 1_154_060
CANDIDATE_POP = PUBLISHED_POP - 329


def _pair(*, cand_cells=None, cand_cats=None, block=SCORE_UNIT_BLOCK, prev_cells=None,
          cand_pop=CANDIDATE_POP):
    prev = _gate_payload(outcomes=PUBLISHED_POP, predicate=PUBLISHED_PREDICATE,
                         categories=PUBLISHED_CATS,
                         cells=PUBLISHED_CELLS if prev_cells is None else prev_cells)
    cand = _gate_payload(outcomes=cand_pop, predicate=CANDIDATE_PREDICATE,
                         categories=CANDIDATE_CATS if cand_cats is None else cand_cats,
                         cells=CANDIDATE_CELLS if cand_cells is None else cand_cells,
                         score_unit=block)
    return cand, prev


def _by_code(verdict, code, *, rejections=False):
    rows = verdict.rejections if rejections else verdict.observations
    return {r["category"]: r for r in rows if r["code"] == code}


class TestPublishGate:
    def test_the_pair_is_declared_with_a_bounded_cap(self):
        entry = DECLARED_PREDICATE_SUCCESSIONS[PAIR]
        assert entry["narrowing"] == "score_unit"
        assert entry["issue"] == 1010
        assert entry["listed"] is False
        # Measured 0.097%; the two curves together hold 2.65%.
        assert 0.097 < entry["max_narrowing_pct"] < 2.65

    def test_the_census_reads_the_section(self):
        cand, _ = _pair()
        assert census(cand)["score_unit"] == {
            "excluded": 329, "listed_outcomes": None, "section_present": True,
            "by_cell": {
                "tennis_atp_canadian_open": {"odds_api_spreads": 89, "odds_api_totals": 90},
                "tennis_wta_cincinnati_open": {"odds_api_totals": 150},
            },
        }
        assert census(cand)["cell_counts"]["tennis_atp_canadian_open"] == CANADIAN_KEPT
        assert census(None)["score_unit"] is None
        assert census(None)["cell_counts"] is None

    @pytest.mark.parametrize(
        "by_cell",
        [
            None,  # absent
            {"odds_api_totals/tennis_wta_cincinnati_open": 329},  # sums, wrong cells ok
            {"tennis_wta_cincinnati_open": 329},  # no source
            {"odds_api_totals/tennis_wta_cincinnati_open": -1},
            {"odds_api_totals/tennis_wta_cincinnati_open": True},
            {"odds_api_totals/tennis_wta_cincinnati_open": 328},  # does not sum
        ],
    )
    def test_an_unusable_per_cell_count_reads_none(self, by_cell):
        block = {k: v for k, v in SCORE_UNIT_BLOCK.items() if k != "excluded_by_cell"}
        if by_cell is not None:
            block["excluded_by_cell"] = by_cell
        cand, _ = _pair(block=block)
        parsed = census(cand)["score_unit"]["by_cell"]
        if by_cell == {"odds_api_totals/tennis_wta_cincinnati_open": 329}:
            # Well-formed and summing: read as stated. Whether it covers the
            # disclosed cells is the judge's question, not the census's.
            assert parsed == {"tennis_wta_cincinnati_open": {"odds_api_totals": 329}}
        else:
            assert parsed is None

    def test_the_first_build_publishes_with_its_parked_categories_disclosed(self):
        cand, prev = _pair()
        verdict = evaluate_publish(cand, prev)
        assert verdict.ok, verdict.summary()
        disclosed = sorted(
            o["category"] for o in verdict.observations
            if o["code"] == "category_collapse_disclosed_exclusion"
        )
        assert disclosed == ["tennis_atp_canadian_open", "tennis_wta_cincinnati_open"]

    def test_control_the_same_drop_undisclosed_refuses(self):
        block = {k: v for k, v in SCORE_UNIT_BLOCK.items()
                 if k not in ("excluded_cells", "excluded_by_cell")}
        cand, prev = _pair(block=block)
        verdict = evaluate_publish(cand, prev)
        assert not verdict.ok
        refused = sorted(
            r["category"] for r in verdict.rejections if r["code"] == "category_collapse"
        )
        assert refused == ["tennis_atp_canadian_open", "tennis_wta_cincinnati_open"]

    def test_the_declared_pair_publishes_across_growth(self):
        prev = _gate_payload(outcomes=1_154_060, predicate=PUBLISHED_PREDICATE,
                             categories={"soccer": 250_323})
        cand = _gate_payload(outcomes=1_250_000, predicate=CANDIDATE_PREDICATE,
                             categories={"soccer": 260_000}, score_unit=SCORE_UNIT_BLOCK)
        verdict = evaluate_publish(cand, prev)
        assert verdict.ok, verdict.summary()
        assert "population_predicate_succession_declared" in verdict.observation_codes

    def test_control_the_same_growth_on_an_undeclared_digest_refuses(self):
        prev = _gate_payload(outcomes=1_154_060, predicate=PUBLISHED_PREDICATE,
                             categories={"soccer": 250_323})
        cand = _gate_payload(outcomes=1_250_000, predicate="0" * 32,
                             categories={"soccer": 260_000}, score_unit=SCORE_UNIT_BLOCK)
        assert evaluate_publish(cand, prev).codes == ["population_drift"]

    def test_a_narrowing_past_the_cap_refuses(self):
        prev = _gate_payload(outcomes=1_154_060, predicate=PUBLISHED_PREDICATE,
                             categories={"soccer": 250_323})
        too_many = dict(SCORE_UNIT_BLOCK, excluded=20_000)
        cand = _gate_payload(outcomes=1_250_000, predicate=CANDIDATE_PREDICATE,
                             categories={"soccer": 260_000}, score_unit=too_many)
        verdict = evaluate_publish(cand, prev)
        assert verdict.codes == ["population_drift"]
        assert "cap" in verdict.summary()


class TestTheDisclosureIsBoundedByWhatTheRuleRemoved:
    """The 2187ed78 probe: 796 sportsbook outcomes vanished from
    tennis_atp_canadian_open beside the 179 the rule removed, and the gate read
    OK because the score-unit section named the category. A label explains its
    own cells, up to the count it states for them, and nothing else."""

    def test_healthy_the_rule_alone_publishes_with_its_arithmetic(self):
        cand, prev = _pair()
        verdict = evaluate_publish(cand, prev)
        assert verdict.ok, verdict.summary()
        obs = _by_code(verdict, "category_collapse_disclosed_exclusion")
        canadian = obs["tennis_atp_canadian_open"]
        assert canadian["magnitude_uncheckable"] is False
        assert canadian["score_unit_accounting"] == {
            "previous": 1_155,
            "candidate": 976,
            "candidate_listed": False,
            "explained": 179,
            "sources": ["odds_api_spreads 89", "odds_api_totals 90"],
            "retained_baseline": 976,
            "unexplained": 0,
            "unexplained_drop_pct": 0.0,
        }
        assert obs["tennis_wta_cincinnati_open"]["score_unit_accounting"]["explained"] == 150

    def test_negative_a_lost_sportsbook_beside_the_rule_refuses(self):
        lost = dict(CANDIDATE_CELLS, tennis_atp_canadian_open={"odds_api": 180})
        cand, prev = _pair(cand_cells=lost, cand_pop=CANDIDATE_POP - 796)
        verdict = evaluate_publish(cand, prev)
        assert not verdict.ok
        refused = _by_code(verdict, "category_collapse", rejections=True)
        assert list(refused) == ["tennis_atp_canadian_open"]
        acct = refused["tennis_atp_canadian_open"]["score_unit_accounting"]
        assert (acct["explained"], acct["unexplained"], acct["retained_baseline"]) == (179, 796, 976)
        assert acct["unexplained_drop_pct"] == 81.56
        # The healthy sibling the same rule took under the bar still publishes
        # its own arithmetic; the refusal is the category that lost a source.
        assert "tennis_wta_cincinnati_open" in _by_code(
            verdict, "category_collapse_disclosed_exclusion")

    def test_the_twenty_percent_tolerance_holds_on_what_the_rule_left(self):
        # 976 untouched outcomes; 20% of them is 195.2.
        for lost, ok in ((195, True), (196, False)):
            kept = {"odds_api_bookmaker": 796 - lost, "odds_api": 180}
            cells = dict(CANDIDATE_CELLS, tennis_atp_canadian_open=kept)
            cand, prev = _pair(cand_cells=cells, cand_pop=CANDIDATE_POP - lost)
            verdict = evaluate_publish(cand, prev)
            assert verdict.ok is ok, (lost, verdict.summary())

    def test_a_cell_falls_further_than_the_rule_says_it_removed(self):
        # The rule says 40 spreads left; the cell lost all 89. 49 are not its.
        block = dict(SCORE_UNIT_BLOCK, excluded=280, spreads_excluded=40, excluded_by_cell={
            "odds_api_spreads/tennis_atp_canadian_open": 40,
            "odds_api_totals/tennis_atp_canadian_open": 90,
            "odds_api_totals/tennis_wta_cincinnati_open": 150,
        })
        cand, prev = _pair(block=block)
        verdict = evaluate_publish(cand, prev)
        acct = _by_code(verdict, "category_collapse_disclosed_exclusion")[
            "tennis_atp_canadian_open"]["score_unit_accounting"]
        assert (acct["explained"], acct["unexplained"]) == (130, 49)
        # The cap decides a verdict: 60 sportsbook outcomes lost is 6.1% of
        # what the rule left when it states its true counts, and 20.6% when it
        # says it removed one outcome per cell (the other 177 are not its).
        cells = dict(CANDIDATE_CELLS, tennis_atp_canadian_open={
            "odds_api_bookmaker": 736, "odds_api": 180})
        cand, prev = _pair(cand_cells=cells, cand_pop=CANDIDATE_POP - 60)
        assert evaluate_publish(cand, prev).ok
        understated = dict(SCORE_UNIT_BLOCK, excluded=152, excluded_by_cell=dict(
            SCORE_UNIT_BLOCK["excluded_by_cell"], **{
                "odds_api_spreads/tennis_atp_canadian_open": 1,
                "odds_api_totals/tennis_atp_canadian_open": 1}))
        cand, prev = _pair(cand_cells=cells, cand_pop=CANDIDATE_POP - 60, block=understated)
        refused = _by_code(evaluate_publish(cand, prev), "category_collapse", rejections=True)
        acct = refused["tennis_atp_canadian_open"]["score_unit_accounting"]
        assert (acct["explained"], acct["unexplained"], acct["unexplained_drop_pct"]) == (
            2, 237, 20.56)

    def test_a_category_still_listed_is_read_from_its_stated_count(self):
        # The rule leaves a big category above the bar: by_category lists it,
        # and its count must equal the bucket sum it was built from.
        big_prev = {"odds_api_bookmaker": 5_000, "odds_api_totals": 2_000}
        big_cand = {"odds_api_bookmaker": 5_000}
        prev_cells = dict(PUBLISHED_CELLS, tennis_atp_us_open=big_prev)
        cand_cells = dict(CANDIDATE_CELLS, tennis_atp_us_open=big_cand)
        block = dict(SCORE_UNIT_BLOCK, excluded=2_329, totals_excluded=2_240,
                     excluded_cells=SCORE_UNIT_BLOCK["excluded_cells"]
                     + [["odds_api_totals", "tennis_atp_us_open"]],
                     excluded_by_cell=dict(SCORE_UNIT_BLOCK["excluded_by_cell"],
                                           **{"odds_api_totals/tennis_atp_us_open": 2_000}))
        prev = _gate_payload(outcomes=PUBLISHED_POP, predicate=PUBLISHED_PREDICATE,
                             categories=dict(PUBLISHED_CATS, tennis_atp_us_open=7_000),
                             cells=prev_cells)
        for listed, ok in ((5_000, True), (4_999, False)):
            cand = _gate_payload(outcomes=PUBLISHED_POP - 2_329,
                                 predicate=CANDIDATE_PREDICATE,
                                 categories=dict(CANDIDATE_CATS, tennis_atp_us_open=listed),
                                 cells=cand_cells, score_unit=block)
            verdict = evaluate_publish(cand, prev)
            assert verdict.ok is ok, (listed, verdict.summary())

    @pytest.mark.parametrize(
        "case",
        ["no_per_cell_count", "per_cell_not_summing", "cell_not_counted",
         "baseline_buckets_disagree", "candidate_buckets_unreadable"],
    )
    def test_fails_closed_when_the_quantities_are_unavailable(self, case):
        block = dict(SCORE_UNIT_BLOCK)
        prev_cells = None
        cand_cells = None
        if case == "no_per_cell_count":
            block.pop("excluded_by_cell")
        elif case == "per_cell_not_summing":
            block["excluded"] = 330
        elif case == "cell_not_counted":
            block["excluded_by_cell"] = {
                "odds_api_totals/tennis_atp_canadian_open": 179,
                "odds_api_totals/tennis_wta_cincinnati_open": 150,
            }
        elif case == "baseline_buckets_disagree":
            prev_cells = dict(PUBLISHED_CELLS, tennis_atp_canadian_open=dict(
                CANADIAN_PUBLISHED, odds_api_bookmaker=795))
        cand, prev = _pair(block=block, prev_cells=prev_cells, cand_cells=cand_cells)
        if case == "candidate_buckets_unreadable":
            cand["buckets"][0] = dict(cand["buckets"][0], source=None)
        verdict = evaluate_publish(cand, prev)
        assert not verdict.ok
        assert "tennis_atp_canadian_open" in _by_code(
            verdict, "category_collapse", rejections=True)

    def test_another_rung_keeps_its_own_path(self):
        """Only the score-unit rung is bounded here; a category another rung
        newly discloses is judged exactly as before (no general rewrite)."""
        cand, prev = _pair()
        cand["esports_multi_bundle_filter"] = {
            "excluded_cells": [["kalshi", "tennis_atp_canadian_open"]]}
        verdict = evaluate_publish(cand, prev)
        obs = _by_code(verdict, "category_collapse_disclosed_exclusion")
        assert obs["tennis_atp_canadian_open"]["magnitude_uncheckable"] is True
        assert "score_unit_accounting" not in obs["tennis_atp_canadian_open"]

    def test_the_ledger_record_carries_the_arithmetic(self):
        from app.utils.calibration_publish_gate import gate_ledger_record
        import json

        cand, prev = _pair()
        record = gate_ledger_record(evaluate_publish(cand, prev))
        rows = {r["category"]: r for r in record["disclosed_exclusions"]}
        assert rows["tennis_atp_canadian_open"]["score_unit_accounting"]["explained"] == 179
        json.dumps(record)
