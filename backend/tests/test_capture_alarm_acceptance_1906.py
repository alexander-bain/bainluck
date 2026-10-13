"""#1906 acceptance: the capture axis files REAL only on a real in-season sample.

CAL-P064 (`8dc504f6`) added a game floor and a season gate to the capture
alarms. Two gaps survived it, and this file pins both:

1. ``classifier_leak`` is a share of MARKETS but was gated on the GAME count.
   30 EPL games carrying 27 markets, 3 of them 'other', filed REAL — the issue
   names exactly this shape (#1899 fired on 27 markets).
2. The season gate read the SWEEP date while the census counts a trailing
   30-day window of fixtures. A mid-September NFL sweep is "in season" while half
   its window is August preseason, so preseason games with no winner market were
   graded against the regular-season expectation (#1897 re-observed REAL on
   2026-09-14, 43 moneylines / 56 games). Each fixture is now placed by its OWN
   date with the same authority (``season_windows``), numerator and denominator
   through one predicate.
3. The issue's own Ligue 1 case had no authority at all: Ligue 1 has no annual
   band, so its August 6, 2026 fixture graded as in season. The league's
   published 2026/27 calendar (opener August 21) and LFP's preseason list (July
   25 – August 16, Monaco–Getafe on August 6) now place exactly the dates they
   cover; every other date — another year included — fails open.

The verdicts: REAL files; EXPLAINED is a shortfall a season calendar proves is an
artifact (the issue's word, and the grid sentinel's); WATCH is one too thin to
file on. Only REAL files (``capture_filing_split``).

Every clock is pinned (gotcha #44). Both directions are asserted (gotcha #43):
the artifact is downgraded AND a genuine in-season starvation still files. A
downgrade is never a disappearance (gotcha #53): it surfaces with its reason.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.utils import capture_census as cc
from app.utils.capture_census import (
    MIN_MARKETS_FOR_CLASSIFIER_ALARM,
    MassCounts,
    capture_findings,
    fixture_in_season,
    season_cohort,
)

UTC = timezone.utc
AUG_17 = datetime(2026, 8, 17, tzinfo=UTC)    # the issue's sweep
SEP_14 = datetime(2026, 9, 14, tzinfo=UTC)    # #1897's REAL re-observation
SEP_30 = datetime(2026, 9, 30, tzinfo=UTC)
NOV_15 = datetime(2026, 11, 15, tzinfo=UTC)   # NFL regular season, no preseason in window
JAN_15 = datetime(2026, 1, 15, tzinfo=UTC)    # NHL regular season

NFL = "americanfootball_nfl"
L1 = "soccer_france_ligue_one"
WNBA = "basketball_wnba"
ML = ("Buffalo Bills at Miami Dolphins", "KXNFLGAME-26SEP13BUFMIA")
SPREAD = ("Buffalo Bills at Miami Dolphins: Spread", "KXNFLSPREAD-26SEP13BUFMIA-BUF3")
OTHER = ("Buffalo Bills at Miami Dolphins: Coin toss heads?", "KXNFLCOIN-26SEP13BUFMIA")


def _of(findings, kind):
    hits = [f for f in findings if f.kind == kind]
    assert len(hits) <= 1
    return hits[0] if hits else None


def _class_counts(**markets):
    return {cls: MassCounts(markets=n, outcomes=2 * n) for cls, n in markets.items()}


# ---------------------------------------------------------------------------
# gap 1 — classifier_leak's denominator is MARKETS
# ---------------------------------------------------------------------------

def test_the_directive_reproducer_files_starved_but_only_watches_the_tiny_leak():
    """soccer_epl, 30 games, 24 moneylines + 3 'other' = 27 markets, Aug 17.
    The game ratio has its 30 games and stays REAL; the 'other' share has only
    27 markets and must not."""
    games = {"soccer_epl": 30}
    by_sc = {"soccer_epl": _class_counts(moneyline=24, other=3)}
    found = capture_findings(games, by_sc, now=AUG_17)

    starved = _of(found, "starved_class")
    assert starved is not None and starved.severity == "REAL"

    leak = _of(found, "classifier_leak")
    assert leak is not None, "below the floor the leak still SURFACES"
    assert leak.severity == "WATCH"
    assert "27 markets" in leak.detail and "market floor" in leak.detail


@pytest.mark.parametrize(
    "markets,expected",
    [
        (MIN_MARKETS_FOR_CLASSIFIER_ALARM - 1, "WATCH"),
        (MIN_MARKETS_FOR_CLASSIFIER_ALARM, "REAL"),
        (MIN_MARKETS_FOR_CLASSIFIER_ALARM + 1, "REAL"),
    ],
)
def test_the_market_floor_boundary_both_sides(markets, expected):
    """Games are well over their floor, the share is well over the ceiling;
    only the market count moves. Pins `<` vs `<=` on the market comparison."""
    other = markets // 2
    games = {"soccer_epl": 100}
    by_sc = {"soccer_epl": _class_counts(moneyline=markets - other, other=other)}
    leak = _of(capture_findings(games, by_sc, now=AUG_17), "classifier_leak")
    assert leak is not None
    assert leak.severity == expected


def test_the_market_floor_does_not_touch_the_moneyline_alarm():
    """The starved alarm is a per-GAME ratio; a small market count must not
    downgrade it (otherwise a sport with NO markets at all could never file)."""
    games = {"soccer_epl": 40}
    by_sc = {"soccer_epl": _class_counts(moneyline=5)}
    starved = _of(capture_findings(games, by_sc, now=AUG_17), "starved_class")
    assert starved is not None and starved.severity == "REAL"


def test_the_game_floor_still_binds_the_leak():
    """Markets cluster by fixture; 100 markets over 5 games is not a sample."""
    games = {"soccer_epl": 5}
    by_sc = {"soccer_epl": _class_counts(moneyline=60, other=40)}
    leak = _of(capture_findings(games, by_sc, now=AUG_17), "classifier_leak")
    assert leak is not None and leak.severity == "WATCH"
    assert "game floor" in leak.detail or "-game floor" in leak.detail


# ---------------------------------------------------------------------------
# gap 2 — each fixture is placed in its season by its own date
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sport,day,expected",
    [
        (NFL, date(2026, 8, 20), False),           # preseason
        (NFL, date(2026, 9, 3), False),            # band starts 9/4 (inside the edge)
        (NFL, date(2026, 9, 10), True),            # regular season
        (NFL, date(2027, 1, 20), True),            # postseason
        (NFL, date(2027, 3, 1), False),            # offseason
        (NFL, None, False),                        # undated: cannot be placed
        ("icehockey_nhl", date(2026, 9, 25), False),   # NHL preseason
        ("icehockey_nhl", date(2026, 10, 10), True),
        ("soccer_epl", date(2026, 7, 27), True),   # no band: never excluded
        ("soccer_epl", None, True),
        # Ligue 1: only the published 2026/27 dates place a fixture (#1906).
        (L1, date(2026, 8, 6), False),             # Monaco–Getafe, a listed friendly
        (L1, date(2026, 7, 25), False),            # first listed preseason day
        (L1, date(2026, 8, 16), False),            # last listed preseason day
        (L1, date(2026, 8, 20), False),            # before the published opener
        (L1, date(2026, 8, 21), True),             # the published opener
        (L1, date(2026, 12, 23), True),            # winter break has no published days
        (L1, date(2027, 5, 29), True),             # the published final day
        (L1, date(2027, 5, 30), True),             # past the calendar: not established
        (L1, date(2026, 7, 24), True),             # before the listed preseason: same
        (L1, date(2027, 8, 6), True),              # 2027 is not 2026: no extrapolation
        (L1, date(2025, 8, 6), True),              # nor backwards
        (L1, None, True),                          # undated: not established
        (WNBA, date(2026, 8, 6), True),            # no band, no calendar
    ],
)
def test_fixture_in_season(sport, day, expected):
    assert fixture_in_season(sport, day) is expected


def test_fixture_in_season_accepts_a_datetime():
    assert fixture_in_season(NFL, datetime(2026, 9, 10, 23, 15, tzinfo=UTC)) is True
    assert fixture_in_season(NFL, datetime(2026, 8, 20, 23, 15, tzinfo=UTC)) is False


def _window(fixtures):
    """fixtures: list of (day, [market (name, ext) ...]) for NFL games.

    Returns the three inputs the sentinel builds — whole-window games, whole-window
    class counts, and the season cohort — from the SAME rows, through the same
    public functions the sentinel calls."""
    day_counts: dict[date, int] = {}
    market_rows = []
    for day, markets in fixtures:
        day_counts[day] = day_counts.get(day, 0) + 1
        for name, ext in markets:
            market_rows.append(
                (NFL, name, ext, 2, 0, 0, 0, 0, "Buffalo Bills", "Miami Dolphins", day)
            )
    day_rows = [(NFL, d, n) for d, n in day_counts.items()]
    games = {NFL: sum(day_counts.values())}
    by_sc, _ = cc.tally_market_rows(market_rows)
    return games, by_sc, season_cohort(day_rows, market_rows)


def _days(start: date, n_games: int):
    """n_games fixtures, two per day from ``start``."""
    return [start + timedelta(days=i // 2) for i in range(n_games)]


def test_the_september_sweep_with_a_preseason_tail_is_not_real():
    """#1897's shape: 56 games, 43 moneylines, on 2026-09-14. 40 August preseason
    fixtures carry 27 moneylines; 16 Week-1 fixtures carry one each. The whole
    window reads 0.77/game; the regular-season slice reads 1.00. It SURFACES as
    EXPLAINED with the split named — and is not REAL."""
    pre = [(d, [ML] if i < 27 else [SPREAD]) for i, d in enumerate(_days(date(2026, 8, 15), 40))]
    reg = [(d, [ML, SPREAD]) for d in _days(date(2026, 9, 10), 16)]
    games, by_sc, season = _window(pre + reg)
    assert by_sc[NFL]["moneyline"].markets == 43 and games[NFL] == 56

    f = _of(capture_findings(games, by_sc, now=SEP_14, season=season), "starved_class")
    assert f is not None, "the whole-window breach must still surface"
    assert f.severity == "EXPLAINED"
    assert "16 of the window's 56 games" in f.detail
    assert "40 fell outside NFL's regular season/postseason" in f.detail


def test_without_the_cohort_the_same_sweep_is_real():
    """Control for the arm above: the whole-window path (the old behaviour) files
    this exact input REAL, so the downgrade is the cohort's doing."""
    pre = [(d, [ML] if i < 27 else [SPREAD]) for i, d in enumerate(_days(date(2026, 8, 15), 40))]
    reg = [(d, [ML, SPREAD]) for d in _days(date(2026, 9, 10), 16)]
    games, by_sc, _season = _window(pre + reg)
    f = _of(capture_findings(games, by_sc, now=SEP_14), "starved_class")
    assert f is not None and f.severity == "REAL"


def test_a_starved_regular_season_slice_files_real_and_names_the_split():
    """The real in-season control on a MIXED window: 10 fixtures before the band
    plus 48 regular-season fixtures carrying only 30 moneylines. The slice
    (30/48 = 0.62) is starved and over the floor: REAL."""
    pre = [(d, [ML]) for d in _days(date(2026, 8, 25), 10)]
    reg = [(d, [ML] if i < 30 else [SPREAD]) for i, d in enumerate(_days(date(2026, 9, 6), 48))]
    games, by_sc, season = _window(pre + reg)
    f = _of(capture_findings(games, by_sc, now=SEP_30, season=season), "starved_class")
    assert f is not None and f.severity == "REAL"
    assert "30 moneyline markets across 48 games" in f.detail
    assert "10 fell outside" in f.detail


def test_preseason_moneylines_cannot_mask_a_starved_regular_season():
    """The numerator and the denominator are sliced together. 40 preseason games
    with TWO moneylines each lift the whole window to 90/72 >= 1 — the old path
    raised nothing at all — while the 32 regular-season games carry 10."""
    pre = [(d, [ML, ML]) for d in _days(date(2026, 8, 10), 40)]
    reg = [(d, [ML] if i < 10 else [SPREAD]) for i, d in enumerate(_days(date(2026, 9, 10), 32))]
    games, by_sc, season = _window(pre + reg)
    assert _of(capture_findings(games, by_sc, now=SEP_30), "starved_class") is None

    f = _of(capture_findings(games, by_sc, now=SEP_30, season=season), "starved_class")
    assert f is not None and f.severity == "REAL"
    assert "10 moneyline markets across 32 games" in f.detail


def test_an_in_season_slice_under_the_game_floor_watches():
    pre = [(d, [SPREAD]) for d in _days(date(2026, 8, 15), 40)]
    reg = [(d, [ML] if i < 8 else [SPREAD]) for i, d in enumerate(_days(date(2026, 9, 10), 16))]
    games, by_sc, season = _window(pre + reg)
    f = _of(capture_findings(games, by_sc, now=SEP_14, season=season), "starved_class")
    assert f is not None and f.severity == "WATCH"
    assert "16 games is under the" in f.detail


def test_a_window_with_no_in_season_fixture_is_explained_and_says_so():
    """Sweep on 9/14 of an all-preseason window (e.g. Week 1 not yet ingested)."""
    games, by_sc, season = _window([(d, [SPREAD]) for d in _days(date(2026, 8, 15), 40)])
    f = _of(capture_findings(games, by_sc, now=SEP_14, season=season), "starved_class")
    assert f is not None and f.severity == "EXPLAINED"
    assert "no fixture in the window is in the regular season/postseason" in f.detail


def test_a_clean_all_regular_season_window_is_unchanged():
    """November: nothing excluded, so the slice IS the window and the detail
    carries no split clause."""
    reg = [(d, [ML] if i < 40 else [SPREAD]) for i, d in enumerate(_days(date(2026, 10, 20), 60))]
    games, by_sc, season = _window(reg)
    f = _of(capture_findings(games, by_sc, now=NOV_15, season=season), "starved_class")
    assert f is not None and f.severity == "REAL"
    assert "40 moneyline markets across 60 games" in f.detail
    assert "fell outside" not in f.detail


def test_a_leak_carried_by_preseason_fixtures_is_explained():
    pre = [(d, [ML, OTHER]) for d in _days(date(2026, 8, 15), 30)]
    reg = [(d, [ML, SPREAD]) for d in _days(date(2026, 9, 10), 30)]
    games, by_sc, season = _window(pre + reg)
    assert _of(capture_findings(games, by_sc, now=SEP_30), "classifier_leak").severity == "REAL"

    leak = _of(capture_findings(games, by_sc, now=SEP_30, season=season), "classifier_leak")
    assert leak is not None and leak.severity == "EXPLAINED"
    assert "the in-season slice does not breach" in leak.detail


def test_an_in_season_leak_is_graded_on_the_slices_markets():
    """Both floors read the SLICE: 30 regular-season games, 29 in-season markets
    with a large 'other' share, and a big preseason menu that would have pushed
    the window's market count far past the floor."""
    pre = [(d, [ML, SPREAD, SPREAD]) for d in _days(date(2026, 8, 15), 30)]
    reg = [(d, [OTHER] if i < 10 else ([ML] if i < 29 else [])) for i, d in
           enumerate(_days(date(2026, 9, 10), 30))]
    games, by_sc, season = _window(pre + reg)
    leak = _of(capture_findings(games, by_sc, now=SEP_30, season=season), "classifier_leak")
    assert leak is not None and leak.severity == "WATCH"
    assert "29 markets is under the" in leak.detail


def test_an_unbanded_league_ignores_the_cohort():
    """EPL has no season band, so the cohort carries nothing for it and its whole
    window is graded exactly as without one."""
    games = {"soccer_epl": 40}
    by_sc = {"soccer_epl": _class_counts(moneyline=10)}
    rows = [("soccer_epl", date(2026, 7, 27), 40)]
    season = season_cohort(rows, [])
    assert "soccer_epl" not in season.games_by_sport
    with_c = capture_findings(games, by_sc, now=AUG_17, season=season)
    without = capture_findings(games, by_sc, now=AUG_17)
    assert [(f.kind, f.severity, f.detail) for f in with_c] == \
        [(f.kind, f.severity, f.detail) for f in without]


# ---------------------------------------------------------------------------
# gap 3 — Ligue 1, placed by its published 2026/27 calendar; WNBA as the control
# ---------------------------------------------------------------------------

L1_ML = ("AS Monaco vs Getafe", "KXLIGUE1GAME-26AUG06MONGET")
L1_TOTAL = ("AS Monaco vs Getafe: Total goals", "KXLIGUE1TOTAL-26AUG06MONGET-2")
WNBA_ML = ("Las Vegas Aces at Seattle Storm", "KXWNBAGAME-26AUG06LVSEA")
WNBA_SPREAD = ("Las Vegas Aces at Seattle Storm: Spread", "KXWNBASPREAD-26AUG06LVSEA-3")
SIDES = {L1: ("AS Monaco", "Getafe"), WNBA: ("Las Vegas Aces", "Seattle Storm"),
         NFL: ("Buffalo Bills", "Miami Dolphins")}
SEP_30_27 = datetime(2027, 9, 30, tzinfo=UTC)


def _sweep(fixtures):
    """fixtures: list of (sport, day, [market (name, ext) ...]). The whole-window
    games, class counts and season cohort, built as ``_window`` builds them but
    across several sports in ONE sweep."""
    day_counts: dict[tuple[str, date], int] = {}
    market_rows = []
    for sport, day, markets in fixtures:
        day_counts[(sport, day)] = day_counts.get((sport, day), 0) + 1
        for name, ext in markets:
            market_rows.append((sport, name, ext, 2, 0, 0, 0, 0, *SIDES[sport], day))
    games: dict[str, int] = {}
    for (sport, _d), n in day_counts.items():
        games[sport] = games.get(sport, 0) + n
    by_sc, _ = cc.tally_market_rows(market_rows)
    day_rows = [(sport, d, n) for (sport, d), n in day_counts.items()]
    return games, by_sc, season_cohort(day_rows, market_rows)


def _starved_of(findings, sport):
    hits = [f for f in findings if f.kind == "starved_class" and f.cohort == f"{sport}/moneyline"]
    assert len(hits) <= 1
    return hits[0] if hits else None


def test_the_issues_ligue1_cohort_is_explained_by_its_published_calendar():
    """The issue's #1900 shape: an August 17 sweep whose Ligue 1 games are the
    July 27 and August 6 friendlies, neither carrying a winner market. The
    calendar places both outside the season, so it is EXPLAINED — named, counted,
    never filed — rather than graded against the regular-season expectation."""
    games, by_sc, season = _sweep([(L1, date(2026, 7, 27), [L1_TOTAL]),
                                   (L1, date(2026, 8, 6), [L1_TOTAL])])
    assert season.excluded_games == {L1: 2} and L1 not in season.games_by_sport
    f = _starved_of(capture_findings(games, by_sc, now=AUG_17, season=season), L1)
    assert f is not None, "the shortfall must still surface"
    assert f.severity == "EXPLAINED"
    assert "no fixture in the window is in the regular season/postseason" in f.detail
    assert "2 fell outside LIGUE1's regular season/postseason" in f.detail
    assert "per its published season calendar" in f.detail


def test_a_full_ligue1_preseason_is_explained_by_the_calendar_not_the_floor():
    """40 friendlies across the listed July 25 – August 16 preseason, swept on
    August 17: well over every floor, so EXPLAINED is the calendar's verdict.
    The control — the same input without the cohort — files REAL, so the
    downgrade is the calendar's doing and nothing else's."""
    fixtures = [(L1, d, [L1_TOTAL]) for d in _days(date(2026, 7, 25), 40)]
    assert max(d for _s, d, _m in fixtures) <= date(2026, 8, 16)
    games, by_sc, season = _sweep(fixtures)
    f = _starved_of(capture_findings(games, by_sc, now=AUG_17, season=season), L1)
    assert f is not None and f.severity == "EXPLAINED"
    control = _starved_of(capture_findings(games, by_sc, now=AUG_17), L1)
    assert control is not None and control.severity == "REAL"


def test_a_starved_ligue1_regular_season_after_august_21_files_real():
    """The genuine in-season control on a MIXED Ligue 1 window: 30 friendlies
    (August 6–16, two moneylines each, which would lift the whole window over
    the floor) plus 40 fixtures from the August 21 opener carrying 15 moneylines.
    The slice is 15/40 — REAL — and the friendlies are named as excluded."""
    pre = [(L1, d, [L1_ML, L1_ML]) for d in _days(date(2026, 8, 6), 22)]
    pre += [(L1, date(2026, 8, 16), [L1_ML, L1_ML]) for _ in range(8)]
    reg = [(L1, d, [L1_ML] if i < 15 else [L1_TOTAL])
           for i, d in enumerate(_days(date(2026, 8, 21), 40))]
    games, by_sc, season = _sweep(pre + reg)
    assert games[L1] == 70 and by_sc[L1]["moneyline"].markets == 75
    assert season.games_by_sport == {L1: 40} and season.excluded_games == {L1: 30}
    assert _starved_of(capture_findings(games, by_sc, now=SEP_30), L1) is None

    f = _starved_of(capture_findings(games, by_sc, now=SEP_30, season=season), L1)
    assert f is not None and f.severity == "REAL"
    assert "15 moneyline markets across 40 games" in f.detail
    assert "30 fell outside LIGUE1's" in f.detail


def test_the_ligue1_calendar_is_not_extrapolated_to_another_year():
    """The same August-friendlies shape one year later: 2027 has no published
    calendar in the table, so its dates are not established and the window is
    graded whole, exactly as before #1906 — REAL, not EXPLAINED."""
    fixtures = [(L1, d, [L1_TOTAL]) for d in _days(date(2027, 7, 25), 40)]
    games, by_sc, season = _sweep(fixtures)
    assert season.games_by_sport == {L1: 40} and not season.excluded_games
    f = _starved_of(capture_findings(games, by_sc, now=datetime(2027, 8, 17, tzinfo=UTC),
                                     season=season), L1)
    assert f is not None and f.severity == "REAL"
    assert "fell outside" not in f.detail


def test_wnba_in_august_stays_real_beside_an_explained_ligue1_in_one_sweep():
    """The issue's control: 73 WNBA games July 19 – August 16, mid-season, with a
    starved winner market (50 of 73). Same August 17 sweep, same cohort, as the
    Ligue 1 friendlies — the one survives REAL, the other is EXPLAINED."""
    days = [date(2026, 7, 19) + timedelta(days=i // 3) for i in range(73)]  # 3 a day
    wnba = [(WNBA, d, [WNBA_ML] if i < 50 else [WNBA_SPREAD]) for i, d in enumerate(days)]
    assert max(d for _s, d, _m in wnba) <= date(2026, 8, 16)
    l1 = [(L1, date(2026, 7, 27), [L1_TOTAL]), (L1, date(2026, 8, 6), [L1_TOTAL])]
    games, by_sc, season = _sweep(wnba + l1)
    assert WNBA not in season.games_by_sport and WNBA not in season.excluded_games

    found = capture_findings(games, by_sc, now=AUG_17, season=season)
    w = _starved_of(found, WNBA)
    assert w is not None and w.severity == "REAL"
    assert "50 moneyline markets across 73 games" in w.detail
    assert _starved_of(found, L1).severity == "EXPLAINED"

    import importlib

    cs = importlib.import_module("app.tasks.calibration_sentinel")
    filed, counts = cs.capture_filing_split(found)
    assert [f.cohort for f in filed] == [f"{WNBA}/moneyline"]
    assert counts["real_count"] == 1 and counts["explained_count"] >= 1


def test_only_real_files_and_every_verdict_is_counted():
    """The payload contract (#1906): REAL files; EXPLAINED and WATCH surface in
    ``findings`` and are counted, and the three counts partition the list."""
    import importlib

    cs = importlib.import_module("app.tasks.calibration_sentinel")
    mk = [cc.CaptureFinding(kind="starved_class", cohort=c, detail="d", severity=sev)
          for c, sev in (("a", "REAL"), ("b", "EXPLAINED"), ("c", "WATCH"),
                         ("d", "EXPLAINED"), ("e", "REAL"))]
    filed, counts = cs.capture_filing_split(mk)
    assert [f.cohort for f in filed] == ["a", "e"]
    assert counts == {"real_count": 2, "explained_count": 2, "watch_count": 1}


# ---------------------------------------------------------------------------
# pinned multi-month guard: the same daily slate, swept on the 15th of each month
# ---------------------------------------------------------------------------

#: Expected NFL starved_class severity for a 30-day window of 3 fixtures/day,
#: none with a moneyline, swept on the 15th. Written out, not derived:
#:  Jan — window 12/17..1/15 regular season + postseason, sweep in postseason.
#:  Feb — window is postseason but the SWEEP date (2/15) is offseason.
#:  Mar–Aug — offseason sweep, and no in-season fixture in the window.
#:  Sep — window 8/17..9/15: 12 band days (9/4..9/15) = 36 games >= 30.
#:  Oct–Dec — regular season throughout.
#: Every non-REAL month is a calendar verdict, so EXPLAINED — never WATCH.
NFL_MONTHLY = {1: "REAL", 2: "EXPLAINED", 3: "EXPLAINED", 4: "EXPLAINED",
               5: "EXPLAINED", 6: "EXPLAINED", 7: "EXPLAINED", 8: "EXPLAINED",
               9: "REAL", 10: "REAL", 11: "REAL", 12: "REAL"}


def test_the_season_split_verdict_across_twelve_pinned_months():
    for month, expected in NFL_MONTHLY.items():
        now = datetime(2026, month, 15, tzinfo=UTC)
        days = [(now - timedelta(days=i)).date() for i in range(30) for _ in range(3)]
        games, by_sc, season = _window([(d, [SPREAD]) for d in days])
        f = _of(capture_findings(games, by_sc, now=now, season=season), "starved_class")
        assert f is not None, f"month {month}: a finding must never vanish"
        assert f.severity == expected, f"month {month}: {f.severity} != {expected}: {f.detail}"


def test_september_real_is_on_the_slice_not_the_window():
    """Under the September REAL above, the finding grades the 36 in-season games,
    not all 90 — the August fixtures are named as excluded."""
    now = datetime(2026, 9, 15, tzinfo=UTC)
    days = [(now - timedelta(days=i)).date() for i in range(30) for _ in range(3)]
    games, by_sc, season = _window([(d, [SPREAD]) for d in days])
    f = _of(capture_findings(games, by_sc, now=now, season=season), "starved_class")
    assert "across 36 games" in f.detail and "54 fell outside" in f.detail


# ---------------------------------------------------------------------------
# the SQL and the wiring
# ---------------------------------------------------------------------------

def test_fixture_days_and_market_rows_share_one_cte_and_one_day_column():
    """Numerator and denominator must place a game on the SAME day, so both read
    `fixture_day` off the one CTE (UTC, explicitly — the bands are UTC)."""
    days = " ".join(cc.fixture_days_sql(30).split())
    rows = " ".join(cc.market_rows_sql(30).split())
    games = " ".join(cc.games_sql(30).split())
    cte = " ".join(cc._GAME_CTE.split()).replace("%(window)s", "30")
    for sql in (days, rows, games):
        assert sql.startswith(cte)
    assert "(e.commence_time AT TIME ZONE 'UTC')::date AS fixture_day" in cte
    assert "SELECT sport_key, fixture_day, COUNT(*) FROM g GROUP BY 1, 2" in days
    assert rows.split(" FROM futures_markets")[0].rstrip().endswith("g.fixture_day")


def test_tally_reads_the_day_column_without_disturbing_sides():
    """An 11-column row keeps the #1529 sides AND gains a day; the in-season
    filter drops exactly the preseason market."""
    row_pre = (NFL, "Buffalo Bills: 3+ touchdowns", "X1", 2, 0, 0, 0, 0,
               "Buffalo Bills", "Miami Dolphins", date(2026, 8, 20))
    row_reg = (NFL, ML[0], ML[1], 2, 0, 0, 0, 0,
               "Buffalo Bills", "Miami Dolphins", date(2026, 9, 13))
    all_sc, _ = cc.tally_market_rows([row_pre, row_reg])
    legacy_sc, _ = cc.tally_market_rows([r[:10] for r in (row_pre, row_reg)])
    assert {k: v.markets for k, v in all_sc[NFL].items()} == \
        {k: v.markets for k, v in legacy_sc[NFL].items()}
    in_sc, _ = cc.tally_market_rows([row_pre, row_reg], in_season_only=True)
    assert {k: v.markets for k, v in in_sc[NFL].items()} == {"moneyline": 1}


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _CensusSession:
    """Answers the sentinel's four census statements by their own SQL text."""

    def __init__(self, day_rows, market_rows):
        self.day_rows, self.market_rows = day_rows, market_rows
        self.statements: list[str] = []

    async def execute(self, stmt):
        sql = str(stmt)
        self.statements.append(sql)
        if "fixture_day, COUNT(*) FROM g GROUP BY 1, 2" in sql:
            return _Rows(self.day_rows)
        if "GROUP BY sport_key ORDER BY 2 DESC" in sql:
            totals: dict[str, int] = {}
            for s, _d, n in self.day_rows:
                totals[s] = totals.get(s, 0) + n
            return _Rows(list(totals.items()))
        if "fm.name, fm.external_id" in sql:
            return _Rows(self.market_rows)
        return _Rows([])


@pytest.mark.asyncio
async def test_the_sentinel_grades_the_in_season_slice():
    """The real `_mine_capture_cohorts`, fed #1897's September shape. Without
    the wiring this files REAL (see the control above); with it, EXPLAINED."""
    import importlib

    # `app.tasks` re-exports a task object under the module's name.
    cs = importlib.import_module("app.tasks.calibration_sentinel")

    pre = [(d, [ML] if i < 27 else [SPREAD]) for i, d in enumerate(_days(date(2026, 8, 15), 40))]
    reg = [(d, [ML, SPREAD]) for d in _days(date(2026, 9, 10), 16)]
    day_counts: dict[date, int] = {}
    market_rows = []
    for d, markets in pre + reg:
        day_counts[d] = day_counts.get(d, 0) + 1
        for name, ext in markets:
            market_rows.append((NFL, name, ext, 2, 0, 0, 0, 0, "Buffalo Bills", "Miami Dolphins", d))
    session = _CensusSession([(NFL, d, n) for d, n in day_counts.items()], market_rows)

    import app.utils.capture_census as live_cc

    real = live_cc.capture_findings

    def _pinned(*a, **k):
        k.setdefault("now", SEP_14)
        return real(*a, **k)

    mp = pytest.MonkeyPatch()
    mp.setattr(live_cc, "capture_findings", _pinned)
    try:
        out = await cs._mine_capture_cohorts(session, None)
    finally:
        mp.undo()

    starved = [f for f in out["_findings_objs"] if f.kind == "starved_class"]
    assert len(starved) == 1 and starved[0].severity == "EXPLAINED"
    assert out["in_season_games_by_sport"] == {NFL: 16}
    assert out["games_by_sport"] == {NFL: 56}
