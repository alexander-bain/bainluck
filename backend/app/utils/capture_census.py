"""Capture-truth census as a reusable, DB-agnostic library.

This is the SINGLE implementation of the cross-sport capture census (program:
calibration, 2026-08-03). It is shared by:
  * scripts/capture_census.py — the one-off-dyno report, and
  * the calibration sentinel — which runs the same cohorts every sweep so a
    MISSING or STARVED market class (a sport with <1 moneyline/game, a
    source/sport whose well-traded pass-rate is an outlier) is flagged the same
    day, exactly like a miscalibrated cohort (2026-08-03 addendum).

Design: the SQL lives here (single source of truth), but the aggregation and
alarm logic are PURE functions over already-fetched rows, so a sync psycopg2
caller (the dyno script) and an async SQLAlchemy caller (the sentinel) can both
feed rows in without this module importing a DB driver. Market class comes from
the shared classifier (game_market_class) — no drift.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

from app.utils.game_market_class import classify_game_market_class

CLASSES = ["moneyline", "spread", "total", "player_prop", "team_prop", "other"]

# Absolute impossibility rules (a class that MUST exist per game, or a bucket
# that means the classifier is failing rather than the markets being exotic).
MONEYLINE_PER_GAME_FLOOR = 1.0
OTHER_SHARE_CEILING = 0.10
# Cross-sectional pass-rate outlier: flag a source x sport whose volume-based
# well-traded pass-rate sits this many MADs below the median for its source,
# but only when there is enough volume signal to trust the comparison.
PASSRATE_OUTLIER_MADS = 3.0
MIN_OUTCOMES_FOR_PASSRATE = 200
MIN_VOLUME_COVERAGE = 0.5   # fraction of outcomes with non-NULL volume

# Sources with no volume/trade concept — excluded from the volume-based bar.
NO_VOLUME_SOURCES = frozenset({"odds_api", "odds_api_bookmaker", "datagolf"})

# Team-ball sports where "~1 game-winner (moneyline) market per game" is a
# genuine expectation AND the classifier's "Team at/vs Team" recognizer applies.
# ONLY these get a REAL (files an issue) starved_class / classifier_leak alarm —
# so the sentinel does not cry wolf on the long tail where the expectation is
# wrong or the naming is different:
#   * individual sports (tennis) are dominated by set/game totals, not a ML;
#   * combat (mma/boxing) winners are FIGHTER matchups the team recognizer misses
#     (a real classifier gap, tracked separately — not a capture regression);
#   * aggregate catch-all buckets (baseball_other, soccer_other) mix many leagues.
# Everything else still SURFACES as WATCH (the permanent axis measures it), but
# does not auto-file until Alex ratifies its per-sport expected menu (NEEDS-RULING).
CORE_TEAM_SPORTS = frozenset({
    "baseball_mlb", "basketball_nba", "basketball_wnba", "basketball_ncaab",
    "icehockey_nhl", "americanfootball_nfl", "americanfootball_ncaaf",
    "soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga",
    "soccer_italy_serie_a", "soccer_france_ligue_one", "soccer_usa_mls",
    "soccer_uefa_champs_league",
})


# ---------------------------------------------------------------------------
# SQL — single source of truth. %(window)s is an int (validated by callers).
# ---------------------------------------------------------------------------
_GAME_CTE = """
WITH g AS (
  SELECT e.id, s.key AS sport_key
  FROM events e
  JOIN sports s ON s.id = e.sport_id
  WHERE e.status IN ('completed', 'closed')
    AND e.commence_time >= NOW() - INTERVAL '%(window)s days'
)
"""

_WELL_TRADED = """
COUNT(*) FILTER (
  WHERE fo.calibration_probability IS DISTINCT FROM fo.opening_probability
    AND fo.opening_probability IS NOT NULL
)
"""
_VOLUME_POSITIVE = "COUNT(*) FILTER (WHERE fo.volume > 0)"
_VOLUME_NULL = "COUNT(*) FILTER (WHERE fo.volume IS NULL)"
_ARTIFACT = """
COUNT(*) FILTER (
  WHERE fo.volume > 0
    AND NOT (fo.calibration_probability IS DISTINCT FROM fo.opening_probability
             AND fo.opening_probability IS NOT NULL)
)
"""


def games_sql(window: int) -> str:
    return _GAME_CTE % {"window": window} + \
        "SELECT sport_key, COUNT(*) FROM g GROUP BY sport_key ORDER BY 2 DESC;"


def market_rows_sql(window: int) -> str:
    """One row per game-linked market: (sport, name, external_id, outcomes,
    well_traded, vol_pos, vol_null, artifact)."""
    return _GAME_CTE % {"window": window} + f"""
        SELECT g.sport_key, fm.name, fm.external_id,
               COUNT(fo.id), {_WELL_TRADED}, {_VOLUME_POSITIVE},
               {_VOLUME_NULL}, {_ARTIFACT}
        FROM futures_markets fm
        JOIN g ON g.id = fm.event_id
        LEFT JOIN futures_outcomes fo ON fo.market_id = fm.id
        GROUP BY g.sport_key, fm.id, fm.name, fm.external_id;
    """


def source_split_sql(window: int) -> str:
    """One row per (sport, source): (sport, source, outcomes, well, vol_pos,
    vol_null, artifact)."""
    return _GAME_CTE % {"window": window} + f"""
        SELECT g.sport_key, fm.source, COUNT(fo.id), {_WELL_TRADED},
               {_VOLUME_POSITIVE}, {_VOLUME_NULL}, {_ARTIFACT}
        FROM futures_markets fm
        JOIN g ON g.id = fm.event_id
        LEFT JOIN futures_outcomes fo ON fo.market_id = fm.id
        GROUP BY g.sport_key, fm.source
        HAVING COUNT(fo.id) > 0
        ORDER BY g.sport_key, 3 DESC;
    """


def published_population_sql() -> str:
    """Q5: honest well-traded number in the PUBLISHED calibration population."""
    return f"""
        SELECT fm.source, COUNT(*), {_WELL_TRADED}, {_VOLUME_POSITIVE},
               {_VOLUME_NULL}, {_ARTIFACT}
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
        GROUP BY fm.source
        ORDER BY 2 DESC;
    """


# ---------------------------------------------------------------------------
# Pure aggregation over fetched rows.
# ---------------------------------------------------------------------------
@dataclass
class MassCounts:
    markets: int = 0
    outcomes: int = 0
    well_traded: int = 0   # snapshot bar
    vol_pos: int = 0       # volume bar (volume>0)
    artifact: int = 0      # fails snapshot bar but volume>0
    vol_null: int = 0      # outcomes with NULL volume (unknown, not untraded)


@dataclass
class CaptureCohorts:
    window_days: int
    games_by_sport: dict[str, int] = field(default_factory=dict)
    # sport -> class -> MassCounts
    by_sport_class: dict[str, dict[str, MassCounts]] = field(default_factory=dict)
    # (sport, source) -> aggregate MassCounts
    by_source_sport: dict[tuple[str, str], MassCounts] = field(default_factory=dict)
    # sport -> {truncated name: count} for the 'other' bucket
    other_names: dict[str, dict[str, int]] = field(default_factory=dict)


def tally_market_rows(rows) -> tuple[dict[str, dict[str, MassCounts]], dict]:
    """rows: (sport, name, external_id, outcomes, well, vol_pos, vol_null, art)."""
    by_sc: dict[str, dict[str, MassCounts]] = {}
    other_names: dict[str, dict[str, int]] = {}
    for sport, name, ext, outc, well, volp, _voln, art in rows:
        cls = classify_game_market_class(name or "", ext, sport)
        mc = by_sc.setdefault(sport, {}).setdefault(cls, MassCounts())
        mc.markets += 1
        mc.outcomes += int(outc or 0)
        mc.well_traded += int(well or 0)
        mc.vol_pos += int(volp or 0)
        mc.artifact += int(art or 0)
        if cls == "other":
            key = (name or "")[:70]
            other_names.setdefault(sport, {})
            other_names[sport][key] = other_names[sport].get(key, 0) + 1
    return by_sc, other_names


def tally_source_split(rows) -> dict[tuple[str, str], MassCounts]:
    """rows: (sport, source, outcomes, well, vol_pos, vol_null, artifact)."""
    out: dict[tuple[str, str], MassCounts] = {}
    for sport, source, outc, well, volp, voln, art in rows:
        out[(sport, source or "?")] = MassCounts(
            markets=0, outcomes=int(outc or 0), well_traded=int(well or 0),
            vol_pos=int(volp or 0), artifact=int(art or 0), vol_null=int(voln or 0),
        )
    return out


# ---------------------------------------------------------------------------
# Findings — the alarm layer the sentinel consumes.
# ---------------------------------------------------------------------------
@dataclass
class CaptureFinding:
    kind: str            # starved_class | classifier_leak | passrate_outlier | drift
    cohort: str          # human cohort label, e.g. "baseball_mlb/moneyline"
    detail: str
    severity: str = "REAL"   # REAL (files) | WATCH (surfaces, no file)
    fingerprint: str = ""    # stable dedup key for the filing rail

    def as_fingerprint(self) -> str:
        return self.fingerprint or f"capture:{self.kind}:{self.cohort}"


def capture_findings(
    games_by_sport: dict[str, int],
    by_sport_class: dict[str, dict[str, MassCounts]],
    by_source_sport: Optional[dict[tuple[str, str], MassCounts]] = None,
) -> list[CaptureFinding]:
    """Cross-sectional alarms for THIS sweep (no history needed).

    * starved_class: a sport with < 1 moneyline market/game (impossible).
    * classifier_leak: a sport whose 'other' bucket exceeds the ceiling.
    * passrate_outlier: a (source, sport) whose volume-based well-traded rate is
      a low outlier vs the same source's other sports (drift-vs-baseline is
      added by the sentinel, which owns the stored history).
    """
    findings: list[CaptureFinding] = []

    for sport, classes in by_sport_class.items():
        games = max(games_by_sport.get(sport, 0), 0)
        if games == 0:
            continue
        total_markets = sum(mc.markets for mc in classes.values()) or 1
        ml = classes.get("moneyline", MassCounts()).markets
        other = classes.get("other", MassCounts()).markets
        # REAL (files) only where the expectation genuinely holds; else WATCH.
        sev = "REAL" if sport in CORE_TEAM_SPORTS else "WATCH"
        if ml / games < MONEYLINE_PER_GAME_FLOOR:
            findings.append(CaptureFinding(
                kind="starved_class",
                cohort=f"{sport}/moneyline",
                severity=sev,
                detail=(f"{ml} moneyline markets across {games} games "
                        f"= {ml/games:.2f}/game (< {MONEYLINE_PER_GAME_FLOOR}). "
                        f"A game without a winner market is impossible — a "
                        f"missing/mis-classified class, not a fact."),
            ))
        if other / total_markets > OTHER_SHARE_CEILING:
            findings.append(CaptureFinding(
                kind="classifier_leak",
                cohort=f"{sport}/other",
                severity=sev,
                detail=(f"'other' is {other/total_markets:.0%} of {total_markets} "
                        f"markets (> {OTHER_SHARE_CEILING:.0%}). The classifier "
                        f"is failing to recognize known classes for {sport}."),
            ))

    if by_source_sport:
        findings.extend(_passrate_outliers(by_source_sport))
    return findings


def _volume_coverage(mc: MassCounts) -> float:
    return (mc.outcomes - mc.vol_null) / mc.outcomes if mc.outcomes else 0.0


def _passrate_outliers(
    by_source_sport: dict[tuple[str, str], MassCounts]
) -> list[CaptureFinding]:
    findings: list[CaptureFinding] = []
    # Group volume-based pass rates by source, over sports with enough signal.
    by_source: dict[str, list[tuple[str, float]]] = {}
    for (sport, source), mc in by_source_sport.items():
        if source in NO_VOLUME_SOURCES:
            continue
        if mc.outcomes < MIN_OUTCOMES_FOR_PASSRATE:
            continue
        if _volume_coverage(mc) < MIN_VOLUME_COVERAGE:
            continue
        rate = mc.vol_pos / mc.outcomes if mc.outcomes else 0.0
        by_source.setdefault(source, []).append((sport, rate))

    for source, pairs in by_source.items():
        if len(pairs) < 4:  # need a peer distribution to call an outlier
            continue
        rates = [r for _, r in pairs]
        med = statistics.median(rates)
        mad = statistics.median([abs(r - med) for r in rates]) or 1e-9
        for sport, rate in pairs:
            if rate < med - PASSRATE_OUTLIER_MADS * mad:
                findings.append(CaptureFinding(
                    kind="passrate_outlier",
                    cohort=f"{source}/{sport}",
                    severity="WATCH",
                    detail=(f"{source} well-traded (volume) pass-rate for {sport} "
                            f"is {rate:.0%} vs a {source} median of {med:.0%} "
                            f"({PASSRATE_OUTLIER_MADS} MADs low) — a starved "
                            f"cohort or a capture-cadence gap, not necessarily "
                            f"real illiquidity."),
                ))
    return findings


# ---------------------------------------------------------------------------
# Baseline snapshot + drift (the sentinel's expected-vs-actual, over history).
# ---------------------------------------------------------------------------
# A cohort must carry at least this much mass last sweep before a drop counts as
# drift (protects against noise on tiny cohorts).
DRIFT_MIN_PREV_MARKETS = 20
DRIFT_MIN_PREV_OUTCOMES = 300
# A relative drop this large in markets-per-game or volume pass-rate is drift.
DRIFT_DROP_FRACTION = 0.40


def snapshot_for_baseline(
    window_days: int,
    games_by_sport: dict[str, int],
    by_sport_class: dict[str, dict[str, MassCounts]],
    by_source_sport: Optional[dict[tuple[str, str], MassCounts]] = None,
) -> dict:
    """A compact JSON-able snapshot the sentinel persists as the next expected."""
    sports: dict[str, dict] = {}
    for sport, classes in by_sport_class.items():
        games = max(games_by_sport.get(sport, 0), 1)
        sports[sport] = {
            "games": games_by_sport.get(sport, 0),
            "markets_per_game": {
                cls: round(mc.markets / games, 4) for cls, mc in classes.items()
            },
        }
    sources: dict[str, float] = {}
    for (sport, source), mc in (by_source_sport or {}).items():
        if source in NO_VOLUME_SOURCES or mc.outcomes < DRIFT_MIN_PREV_OUTCOMES:
            continue
        if _volume_coverage(mc) < MIN_VOLUME_COVERAGE:
            continue
        sources[f"{sport}|{source}"] = round(mc.vol_pos / mc.outcomes, 4)
    return {"window_days": window_days, "sports": sports, "sources": sources}


def drift_findings(prev: Optional[dict], curr: dict) -> list[CaptureFinding]:
    """Expected-vs-actual drift: a cohort's mass or pass-rate that fell sharply
    since the last sweep. Needs a prior snapshot (first sweep produces none)."""
    if not prev:
        return []
    findings: list[CaptureFinding] = []

    prev_sports = prev.get("sports", {})
    curr_sports = curr.get("sports", {})
    for sport, pinfo in prev_sports.items():
        cinfo = curr_sports.get(sport)
        if not cinfo:
            continue
        pgames = pinfo.get("games", 0)
        for cls, prev_mpg in pinfo.get("markets_per_game", {}).items():
            # require material prior mass to avoid noise
            if prev_mpg * max(pgames, 1) < DRIFT_MIN_PREV_MARKETS:
                continue
            curr_mpg = cinfo.get("markets_per_game", {}).get(cls, 0.0)
            if prev_mpg > 0 and curr_mpg < prev_mpg * (1 - DRIFT_DROP_FRACTION):
                findings.append(CaptureFinding(
                    kind="drift",
                    cohort=f"{sport}/{cls}",
                    severity="REAL" if sport in CORE_TEAM_SPORTS else "WATCH",
                    detail=(f"{sport} {cls} mass fell from {prev_mpg:.2f} to "
                            f"{curr_mpg:.2f} markets/game "
                            f"({(1 - curr_mpg/prev_mpg):.0%} drop) since the last "
                            f"sweep — a capture regression (starved or "
                            f"mis-classified), not a slow-moving calibration move."),
                ))

    prev_src = prev.get("sources", {})
    curr_src = curr.get("sources", {})
    for key, prev_rate in prev_src.items():
        curr_rate = curr_src.get(key)
        if curr_rate is None:
            continue
        if prev_rate > 0 and curr_rate < prev_rate * (1 - DRIFT_DROP_FRACTION):
            sport, _, source = key.partition("|")
            findings.append(CaptureFinding(
                kind="drift",
                cohort=f"{source}/{sport}",
                severity="WATCH",
                detail=(f"{source} volume pass-rate for {sport} fell from "
                        f"{prev_rate:.0%} to {curr_rate:.0%} since the last sweep "
                        f"— a capture-cadence or ingestion regression."),
            ))
    return findings
