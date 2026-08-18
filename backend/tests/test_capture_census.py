"""Unit tests for the reusable capture-census library (the sentinel axis).

Covers the pure aggregation + alarm layer over already-fetched rows, so the
same logic the calibration sentinel runs every sweep is verified without a DB.
"""

from datetime import datetime, timezone

from app.utils.capture_census import (
    MIN_GAMES_FOR_CAPTURE_ALARM,
    MassCounts,
    capture_findings,
    drift_findings,
    snapshot_for_baseline,
    tally_market_rows,
    tally_source_split,
)

# Pinned clocks for the season gate (#1906). Real dates in real phases, never
# `datetime.now().replace(...)` — gotcha #44 is explicit that pinning an HOUR
# pins nothing, and that a seasonal assertion must not contain an `if`.
IN_SEASON_NBA = datetime(2026, 1, 15, tzinfo=timezone.utc)   # NBA regular season
OFFSEASON_NFL = datetime(2026, 8, 17, tzinfo=timezone.utc)   # NFL preseason (#1897)
IN_SEASON_NFL = datetime(2026, 11, 15, tzinfo=timezone.utc)  # NFL regular season

# CAL-P065 — gotcha #44's LATENT instance in this file, and why "it passes" was
# not evidence that it was fixed.
#
# #1906 pinned the clock on the tests it had just written and left five earlier
# `capture_findings(...)` calls reading the real wall clock. A 12-month sweep
# (`scripts/clock_sweep.py`, the #1109 standard) reports all 18 green at every
# month — so nothing was RED and nothing looked owed. That is precisely what
# latent means here: those five assertions are green by ACCIDENT OF THE DATA,
# not by any property they state.
#
#   * `tennis_atp` and `soccer_epl` are absent from `_SEASON_LEAGUE_SLUG`, so
#     `league_phase()` answers "in_season" year-round. Add bands for either
#     league — a plainly reasonable future change — and those tests start
#     branching on the month.
#   * `icehockey_nhl` IS banded. `test_sane_sport_produces_no_findings` asserts
#     `== []` against a league the gate knows, and survives only because a
#     1.5-moneyline-per-game ratio never reaches the gate at all.
#
# So the sweep proves invariance TODAY and nothing about tomorrow, and the
# defect is one data change away in each case. Every assertion-bearing call
# below is pinned. The single deliberate exception is
# `test_capture_findings_defaults_to_real_clock_without_now`, which exists to
# prove the parameter is optional and therefore asserts nothing clock-dependent.
ANY_DATE = datetime(2026, 6, 15, tzinfo=timezone.utc)

#: One instant per month, for the in-suite invariance assertion below. The
#: sweep script is a thing somebody has to remember to run; this is the same
#: property as a test that fails on its own.
TWELVE_MONTHS = tuple(
    datetime(2026, m, 15, tzinfo=timezone.utc) for m in range(1, 13)
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
    # #1906: the clock is PINNED, mid-NBA-regular-season. Before the season gate
    # landed this test read the wall clock and so was green from late October to
    # mid-April and red the rest of the year — gotcha #44 sitting latent in the
    # suite. It is pinned to a DATE (a real phase), not to an hour of today.
    findings = capture_findings(games, by_sc, now=IN_SEASON_NBA)
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
    findings = capture_findings(games, by_sc, now=ANY_DATE)
    starved = [f for f in findings if f.kind == "starved_class"]
    assert starved and all(f.severity == "WATCH" for f in starved)


def test_classifier_leak_flags_when_other_exceeds_ceiling():
    games = {"soccer_epl": 50}
    by_sc = {"soccer_epl": {
        "moneyline": MassCounts(markets=60, outcomes=120),
        "other": MassCounts(markets=40, outcomes=40),  # 40% other
    }}
    findings = capture_findings(games, by_sc, now=ANY_DATE)
    assert any(f.kind == "classifier_leak" for f in findings)


def test_sane_sport_produces_no_findings():
    games = {"icehockey_nhl": 30}
    by_sc = {"icehockey_nhl": {
        "moneyline": MassCounts(markets=45, outcomes=90),  # 1.5/game
        "spread": MassCounts(markets=30, outcomes=60),
        "total": MassCounts(markets=30, outcomes=60),
        "other": MassCounts(markets=2, outcomes=2),  # ~2%
    }}
    assert capture_findings(games, by_sc, now=ANY_DATE) == []


def test_passrate_outlier_detects_low_source_sport():
    games = {s: 100 for s in
             ["s1", "s2", "s3", "s4", "s5"]}
    by_sc = {s: {"moneyline": MassCounts(markets=150, outcomes=300)} for s in games}
    # kalshi pass-rate ~0.8 for four sports, ~0.05 for the fifth -> outlier
    src = {}
    for s in ["s1", "s2", "s3", "s4"]:
        src[(s, "kalshi")] = MassCounts(outcomes=1000, vol_pos=800, vol_null=0)
    src[("s5", "kalshi")] = MassCounts(outcomes=1000, vol_pos=50, vol_null=0)
    findings = capture_findings(games, by_sc, src, now=ANY_DATE)
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
    findings = capture_findings(games, by_sc, src, now=ANY_DATE)
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


# ---------------------------------------------------------------------------
# #1906 — the capture axis needs an n-floor and a season window.
#
# Both directions are asserted, per gotcha #43: the artifact must be DOWNGRADED
# *and* the genuine alarm must survive. A guard tested in one direction only is
# how the diversity-cap fix emptied the Sports tab.
#
# And the downgrade is never a disappearance: WATCH still SURFACES the finding
# with the reason named in `detail`. An alarm that vanishes is indistinguishable
# from an alarm that never fired (gotcha #53), which is the whole failure this
# instrument keeps re-creating.
# ---------------------------------------------------------------------------

def _starved(games_n, sport="americanfootball_nfl", now=None):
    """A cohort that ALWAYS trips the raw moneyline-per-game rule."""
    games = {sport: games_n}
    by_sc = {sport: {"moneyline": MassCounts(markets=0, outcomes=0)}}
    found = capture_findings(games, by_sc, now=now)
    return next((f for f in found if f.kind == "starved_class"), None)


def test_small_n_downgrades_to_watch_but_still_surfaces():
    # #1900 was filed as a REAL P2 off FOUR games. One missing market flips that
    # ratio, so it cannot carry a filing.
    f = _starved(4, now=IN_SEASON_NFL)
    assert f is not None, "the finding must still SURFACE, not vanish"
    assert f.severity == "WATCH"
    assert "floor" in f.detail and "4 games" in f.detail


def test_n_floor_boundary_is_inclusive_on_the_real_side():
    # Exactly at the floor files; one below does not. Pins the comparison
    # direction so a later `<` -> `<=` slip is caught.
    assert _starved(MIN_GAMES_FOR_CAPTURE_ALARM, now=IN_SEASON_NFL).severity == "REAL"
    assert _starved(MIN_GAMES_FOR_CAPTURE_ALARM - 1, now=IN_SEASON_NFL).severity == "WATCH"


def test_offseason_downgrades_to_watch_even_with_plenty_of_games():
    # #1897: 19 NFL games, 2026-08-07..08-16 — preseason only. The detector's
    # premise ("a game without a winner market is impossible") is not true of
    # NFL preseason. n is deliberately well OVER the floor here, so this proves
    # the SEASON gate fired and not the n-floor.
    f = _starved(500, now=OFFSEASON_NFL)
    assert f is not None
    assert f.severity == "WATCH"
    assert "offseason" in f.detail.lower()


def test_in_season_core_sport_with_enough_games_still_files_real():
    # The other direction. The instrument must not have been silenced.
    f = _starved(500, now=IN_SEASON_NFL)
    assert f is not None
    assert f.severity == "REAL"
    assert "WATCH not REAL" not in f.detail


def test_season_gate_only_applies_to_leagues_with_known_bands():
    # season_windows returns "in_season" for anything it has no bands for, so an
    # unmapped core sport must NOT be silenced by the calendar. Mapping more
    # leagues than season_windows knows would be coverage theatre.
    f = _starved(500, sport="soccer_epl", now=OFFSEASON_NFL)
    assert f is not None and f.severity == "REAL"


def test_capture_findings_defaults_to_real_clock_without_now():
    # `now` is optional; omitting it must not raise. (Value not asserted — that
    # would reintroduce the wall-clock dependency this whole block removes.)
    #
    # This is the ONE deliberately-unpinned call in the file. It is safe because
    # it asserts only that a finding exists at all, which no season phase can
    # change: the gate downgrades severity and never drops a finding.
    assert _starved(500, sport="soccer_epl") is not None


# ---------------------------------------------------------------------------
# CAL-P065 — the invariance itself, as a test rather than as a script run.
# ---------------------------------------------------------------------------


def test_banded_league_verdict_is_identical_at_every_month_of_the_year():
    """A banded league's severity must be a function of its PHASE, not of when
    the suite runs — and the phase must be the injected clock's, never today's.

    NHL is the specimen because it is in ``_SEASON_LEAGUE_SLUG``: the gate
    genuinely consults the calendar for it, so a cohort that is starved in
    January and starved in July should be REAL in one and WATCH in the other,
    and each answer must be stable no matter what day the test runs.

    The pair is asserted TOGETHER (gotcha #43): proving only that some month
    says WATCH would also pass if the gate had been silenced into always-WATCH.
    """
    by_month = {
        m.month: _starved(500, sport="icehockey_nhl", now=m) for m in TWELVE_MONTHS
    }
    assert all(f is not None for f in by_month.values()), "a finding must never vanish"

    severities = {m: f.severity for m, f in by_month.items()}
    assert set(severities.values()) == {"REAL", "WATCH"}, (
        "the season gate must actually discriminate for a banded league — "
        f"got {sorted(set(severities.values()))} across 12 months"
    )
    # January is NHL regular season; July is not. Named explicitly so a bands
    # change that inverts them fails here rather than drifting quietly.
    assert severities[1] == "REAL"
    assert severities[7] == "WATCH"
    assert "offseason" in by_month[7].detail.lower() or "season" in by_month[7].detail.lower()


def test_every_pinned_scenario_is_invariant_to_the_month_it_is_graded_in():
    """The #1109 standard, in the suite. Each scenario is evaluated at all twelve
    pinned instants and must return the SAME verdict every time.

    ``scripts/clock_sweep.py`` proves this for the file as a whole, but only when
    somebody remembers to run it — and #1906's five surviving wall-clock calls
    are what that gap looks like. Pinning the clock at the call site is the fix;
    this is the assertion that the pinning is real, i.e. that nothing downstream
    reaches past the injected clock to `datetime.now()`.
    """
    scenarios = {
        "noncore_tennis": (
            {"tennis_atp": 2700},
            {"tennis_atp": {"moneyline": MassCounts(markets=100, outcomes=200)}},
        ),
        "epl_classifier_leak": (
            {"soccer_epl": 50},
            {"soccer_epl": {
                "moneyline": MassCounts(markets=60, outcomes=120),
                "other": MassCounts(markets=40, outcomes=40),
            }},
        ),
        "sane_nhl": (
            {"icehockey_nhl": 30},
            {"icehockey_nhl": {
                "moneyline": MassCounts(markets=45, outcomes=90),
                "spread": MassCounts(markets=30, outcomes=60),
                "total": MassCounts(markets=30, outcomes=60),
                "other": MassCounts(markets=2, outcomes=2),
            }},
        ),
    }
    for label, (games, by_sc) in scenarios.items():
        verdicts = {
            tuple(sorted((f.kind, f.cohort, f.severity)
                         for f in capture_findings(games, by_sc, now=m)))
            for m in TWELVE_MONTHS
        }
        assert len(verdicts) == 1, (
            f"{label} returns {len(verdicts)} different verdicts across the year — "
            "it is reading a clock the caller did not give it"
        )
