"""Unit tests for the reusable capture-census library (the sentinel axis).

Covers the pure aggregation + alarm layer over already-fetched rows, so the
same logic the calibration sentinel runs every sweep is verified without a DB.
"""

from app.utils.capture_census import (
    MassCounts,
    capture_findings,
    drift_findings,
    snapshot_for_baseline,
    tally_market_rows,
    tally_source_split,
)


def _mkt(sport, name, ext, outc, well, volp, voln, art):
    return (sport, name, ext, outc, well, volp, voln, art)


def test_tally_market_rows_classifies_and_sums():
    rows = [
        _mkt("baseball_mlb", "Yankees at Dodgers", None, 2, 2, 2, 0, 0),
        _mkt("baseball_mlb", "Red Sox vs. Rays", None, 2, 1, 2, 0, 1),
        _mkt("baseball_mlb", "Yankees at Red Sox: Run Line", None, 2, 2, 2, 0, 0),
        _mkt("baseball_mlb", "Aaron Judge Home Runs", None, 2, 0, 0, 2, 0),
    ]
    by_sc, other_names = tally_market_rows(rows)
    assert by_sc["baseball_mlb"]["moneyline"].markets == 2
    assert by_sc["baseball_mlb"]["moneyline"].outcomes == 4
    assert by_sc["baseball_mlb"]["moneyline"].artifact == 1
    assert by_sc["baseball_mlb"]["spread"].markets == 1
    assert by_sc["baseball_mlb"]["player_prop"].markets == 1
    assert "other" not in by_sc["baseball_mlb"]
    assert other_names == {}


def test_starved_class_flags_when_moneyline_below_one_per_game():
    games = {"basketball_nba": 100}
    # only 40 moneyline markets for 100 games -> impossible
    by_sc = {"basketball_nba": {
        "moneyline": MassCounts(markets=40, outcomes=80),
        "other": MassCounts(markets=5, outcomes=5),
    }}
    findings = capture_findings(games, by_sc)
    kinds = {f.kind for f in findings}
    assert "starved_class" in kinds
    starved = next(f for f in findings if f.kind == "starved_class")
    assert starved.severity == "REAL"
    assert "basketball_nba/moneyline" == starved.cohort


def test_noncore_sport_starved_is_watch_not_real():
    # A long-tail / individual / combat sport must SURFACE (WATCH) but not
    # auto-file (REAL) — the sentinel must not cry wolf where the ~1 ml/game
    # expectation does not hold or the classifier naming differs.
    games = {"tennis_atp": 2700}
    by_sc = {"tennis_atp": {
        "moneyline": MassCounts(markets=100, outcomes=200),  # 0.04/game
        "other": MassCounts(markets=50, outcomes=50),
    }}
    findings = capture_findings(games, by_sc)
    starved = [f for f in findings if f.kind == "starved_class"]
    assert starved and all(f.severity == "WATCH" for f in starved)


def test_classifier_leak_flags_when_other_exceeds_ceiling():
    games = {"soccer_epl": 50}
    by_sc = {"soccer_epl": {
        "moneyline": MassCounts(markets=60, outcomes=120),
        "other": MassCounts(markets=40, outcomes=40),  # 40% other
    }}
    findings = capture_findings(games, by_sc)
    assert any(f.kind == "classifier_leak" for f in findings)


def test_sane_sport_produces_no_findings():
    games = {"icehockey_nhl": 30}
    by_sc = {"icehockey_nhl": {
        "moneyline": MassCounts(markets=45, outcomes=90),  # 1.5/game
        "spread": MassCounts(markets=30, outcomes=60),
        "total": MassCounts(markets=30, outcomes=60),
        "other": MassCounts(markets=2, outcomes=2),  # ~2%
    }}
    assert capture_findings(games, by_sc) == []


def test_passrate_outlier_detects_low_source_sport():
    games = {s: 100 for s in
             ["s1", "s2", "s3", "s4", "s5"]}
    by_sc = {s: {"moneyline": MassCounts(markets=150, outcomes=300)} for s in games}
    # kalshi pass-rate ~0.8 for four sports, ~0.05 for the fifth -> outlier
    src = {}
    for s in ["s1", "s2", "s3", "s4"]:
        src[(s, "kalshi")] = MassCounts(outcomes=1000, vol_pos=800, vol_null=0)
    src[("s5", "kalshi")] = MassCounts(outcomes=1000, vol_pos=50, vol_null=0)
    findings = capture_findings(games, by_sc, src)
    outliers = [f for f in findings if f.kind == "passrate_outlier"]
    assert len(outliers) == 1
    assert outliers[0].cohort == "kalshi/s5"
    assert outliers[0].severity == "WATCH"


def test_passrate_outlier_skips_no_volume_sources_and_thin_signal():
    games = {"golf": 100}
    by_sc = {"golf": {"moneyline": MassCounts(markets=150, outcomes=300)}}
    src = {
        ("golf", "odds_api"): MassCounts(outcomes=5000, vol_pos=0, vol_null=5000),
        ("golf", "datagolf"): MassCounts(outcomes=5000, vol_pos=0, vol_null=5000),
        # kalshi golf below the min-outcomes floor -> skipped, not flagged
        ("golf", "kalshi"): MassCounts(outcomes=50, vol_pos=1, vol_null=0),
    }
    findings = capture_findings(games, by_sc, src)
    assert not any(f.kind == "passrate_outlier" for f in findings)


def test_tally_source_split_shape():
    rows = [("baseball_mlb", "kalshi", 100, 40, 30, 10, 5)]
    out = tally_source_split(rows)
    mc = out[("baseball_mlb", "kalshi")]
    assert mc.outcomes == 100 and mc.well_traded == 40
    assert mc.vol_pos == 30 and mc.vol_null == 10 and mc.artifact == 5


def test_snapshot_and_no_drift_on_first_sweep():
    games = {"baseball_mlb": 100}
    by_sc = {"baseball_mlb": {"moneyline": MassCounts(markets=150, outcomes=300)}}
    snap = snapshot_for_baseline(30, games, by_sc)
    assert snap["sports"]["baseball_mlb"]["markets_per_game"]["moneyline"] == 1.5
    # No prior snapshot => no drift.
    assert drift_findings(None, snap) == []
    # Identical snapshot => no drift.
    assert drift_findings(snap, snap) == []


def test_drift_flags_mass_collapse():
    games = {"baseball_mlb": 100}
    prev = snapshot_for_baseline(
        30, games, {"baseball_mlb": {"moneyline": MassCounts(markets=150, outcomes=300)}}
    )
    curr = snapshot_for_baseline(
        30, games, {"baseball_mlb": {"moneyline": MassCounts(markets=40, outcomes=80)}}
    )
    findings = drift_findings(prev, curr)
    assert any(f.kind == "drift" and f.cohort == "baseball_mlb/moneyline"
               for f in findings)


def test_drift_ignores_tiny_prior_mass():
    games = {"minor": 100}
    prev = snapshot_for_baseline(
        30, games, {"minor": {"moneyline": MassCounts(markets=5, outcomes=10)}}
    )
    curr = snapshot_for_baseline(
        30, games, {"minor": {"moneyline": MassCounts(markets=0, outcomes=0)}}
    )
    # prior mass (5 markets) below DRIFT_MIN_PREV_MARKETS -> not drift noise
    assert drift_findings(prev, curr) == []


def test_source_passrate_drift():
    games = {"baseball_mlb": 100}
    by_sc = {"baseball_mlb": {"moneyline": MassCounts(markets=150, outcomes=300)}}
    prev = snapshot_for_baseline(
        30, games, by_sc,
        {("baseball_mlb", "kalshi"): MassCounts(outcomes=1000, vol_pos=800)},
    )
    curr = snapshot_for_baseline(
        30, games, by_sc,
        {("baseball_mlb", "kalshi"): MassCounts(outcomes=1000, vol_pos=300)},
    )
    findings = drift_findings(prev, curr)
    assert any(f.kind == "drift" and f.cohort == "kalshi/baseball_mlb"
               for f in findings)
