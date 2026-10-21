"""#1529 phase-A acceptance accounting over a COMPLETE capture census.

PILLAR: TRUTH. SHIP: across sports, game pages put full-game winners in Game lines and
preserve player and segment questions in the correct sections. #1529's original
acceptance is a census result: every CORE_TEAM_SPORTS cohort carries at least one
moneyline market per game, and its 'other' bucket is below 10% of its markets. This
module grades that, and only that, from the four phase-A result sets.

Pure. No driver, no network, no clock, no I/O. It does not run, schedule or change the
census; it reads the rows the four ``capture_census`` statements return, in their
column order, and returns one JSON-able dict. Nothing calls it yet; the census that
would feed it is separately unadmitted.

Why it exists beside ``capture_census.capture_findings`` (which it does not change):
the sentinel's alarm layer iterates only sports that have market rows (a sport with
games and zero markets is never seen), skips zero-game cohorts, divides an empty
market set by a synthetic 1, omits zero class rows, compares with ``>`` (exactly 10%
passes there), and its season/n-floor/WATCH downgrades decide filing, not acceptance.
Each of those is right for an alarm and wrong for an acceptance gate. Here:

* the cohort set is the UNION of the 14 CORE keys, every sport with games, every sport
  with markets, every fixture-day sport and every source-split sport;
* every comparison is exact integer cross-multiplication — ``moneyline >= games`` and
  ``10 * other < markets`` — so exactly 10% FAILS and nothing is rounded;
* games > 0 with no markets is a moneyline FAIL with the other share UNDEFINED;
  no games is NO_POPULATION, which is never PASS;
* the full window is the only acceptance population. The season split is reported
  separately and never substitutes for it; no n-floor or WATCH applies;
* all seven classes (``segment_winner`` included) are reported for every cohort, zeros
  too, and class counts must reconcile to the markets fetched;
* rows with a NULL name, external id, side, fixture day or source, and zero-outcome
  markets, stay counted and are disclosed, never dropped;
* the four result sets must reconcile with each other (fixture days to games, markets
  to games and days, source split to markets). Any failure, a missing result set or a
  malformed result, row or value makes the whole verdict NO_RESULT: a partial census is
  never zero and never PASS;
* the acceptance subject is the frozen 30-day phase-A census
  (``capture_census.py --phase a --window 30``, sealed in ``tools/plan1529``). Any other
  window, however well formed, is not admitted: NO_RESULT, never a narrower PASS.

Class answers come from the shared classifier exactly as ``tally_market_rows`` calls it;
``TestNoClassifierDrift`` holds the two to the same counts.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Optional

from app.utils import capture_census as cc
from app.utils.game_market_class import classify_game_market_class

SCHEMA = "capture-census-1529-phase-a-acceptance/v1"

# #1529's acceptance cohort: the four phase-A statements at window 30, the window
# tools/plan1529's contract seals (WINDOW_DAYS). Rows from any other window are a
# different subject and are refused, not graded.
ACCEPTANCE_WINDOW_DAYS = 30

# Result-set arities, from capture_census's own SQL (games_sql, market_rows_sql,
# source_split_sql, fixture_days_sql at window=30).
GAMES_ARITY = 2          # sport_key, games
MARKET_ARITY = 11        # sport, name, external_id, outcomes, well, vol_pos, vol_null,
                         # artifact, home_team, away_team, fixture_day
SOURCE_ARITY = 7         # sport, source, outcomes, well, vol_pos, vol_null, artifact
FIXTURE_ARITY = 3        # sport, fixture_day, games

# A NULL key is a real row, not an absence: kept under a name no sport key can take.
NULL_KEY = "__null__"
UNCLASSIFIED = "__unclassified__"

PASS, FAIL, NO_POPULATION, NO_RESULT = "PASS", "FAIL", "NO_POPULATION", "NO_RESULT"
UNDEFINED = "UNDEFINED"
NOT_GRADED = "NOT_GRADED_NOT_CORE"

LIMITATIONS = (
    "Name/sides-only census: classes come from market names, external ids and the game's "
    "two team names. It does not read outcome contract names, so it does not prove the "
    "outcome-based player-container rendering contract (a bare-matchup name whose outcomes "
    "are player contracts must render as player props) or any page's rendering.",
    "vol_null_raw is the census's own COUNT(*) FILTER (volume IS NULL) over a LEFT JOIN: a "
    "zero-outcome market contributes one NULL row and so counts 1. vol_null_outcomes "
    "subtracts exactly that (one per zero-outcome market). NULL volume is unknown, not untraded.",
    "The source split drops (sport, source) groups with no outcomes (HAVING COUNT(fo.id) > 0), "
    "so it is not a market denominator; markets per source are not in any phase-A result.",
    "The four statements are separate reads. Unless they ran in one snapshot, concurrent "
    "writes can make them disagree; that surfaces here as a reconciliation failure "
    "(NO_RESULT), never as a silently adjusted count.",
    "Esports is outside CORE_TEAM_SPORTS and is reported, not graded. No esports games in "
    "the window is UNKNOWN coverage, not a favorable zero.",
)


class _Malformed(Exception):
    def __init__(self, code: str, **detail: Any):
        super().__init__(code)
        self.failure = {"code": code, **detail}


def _key(value) -> str:
    return NULL_KEY if value is None else str(value)


def _day_key(value) -> str:
    if value is None:
        return NULL_KEY
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value)


def _text(value, field: str, row_index: int, statement: str):
    # Keys, names, ids and sides are text or NULL; anything else is a malformed value.
    if value is not None and type(value) is not str:
        raise _Malformed("MALFORMED_VALUE", statement=statement, row=row_index, field=field)
    return value


def _day(value, row_index: int, statement: str):
    if value is not None and not isinstance(value, (str, date, datetime)):
        raise _Malformed("MALFORMED_VALUE", statement=statement, row=row_index, field="fixture_day")
    return value


def _count(value, field: str, row_index: int, statement: str) -> int:
    if type(value) is not int or value < 0:
        raise _Malformed("MALFORMED_COUNTER", statement=statement, row=row_index, field=field)
    return value


def _rows(rows, arity: int, statement: str) -> list[tuple]:
    if rows is None:
        raise _Malformed("MISSING_RESULT", statement=statement)
    if isinstance(rows, (str, bytes, dict)):
        raise _Malformed("MALFORMED_RESULT", statement=statement)
    try:
        iterator = iter(rows)
    except TypeError:
        raise _Malformed("MALFORMED_RESULT", statement=statement) from None
    out = []
    for i, row in enumerate(iterator):
        # A row is an ordered record; a scalar, NULL, text, mapping or set is not one.
        if row is None or isinstance(row, (str, bytes, bytearray, dict, set, frozenset)):
            raise _Malformed("MALFORMED_ROW", statement=statement, row=i)
        try:
            row = tuple(row)
        except TypeError:
            raise _Malformed("MALFORMED_ROW", statement=statement, row=i) from None
        if len(row) != arity:
            raise _Malformed("MALFORMED_ROW", statement=statement, row=i, arity=len(row), expected=arity)
        out.append(row)
    return out


def _fraction(num: int, den: int) -> Optional[dict]:
    return None if den == 0 else {"num": num, "den": den}


def _empty_class() -> dict:
    return {"markets": 0, "outcomes": 0, "well_traded": 0, "vol_pos": 0, "vol_null_raw": 0,
            "vol_null_outcomes": 0, "artifact": 0, "zero_outcome_markets": 0}


def _is_esports(sport: str) -> bool:
    # Same prefix convention as sport_keys.SPORT_PREFIX_TO_LLM_CATEGORY: the text before
    # the first underscore ("esports", "esports_lol", "esports_cs2", ...).
    return sport.split("_", 1)[0] == "esports"


def phase_a_acceptance(
    *,
    window_days: int,
    games_rows: Optional[Iterable],
    market_rows: Optional[Iterable],
    source_rows: Optional[Iterable],
    fixture_day_rows: Optional[Iterable],
) -> dict:
    """Grade #1529's phase-A acceptance from the four complete result sets.

    Rows are the statements' own tuples in column order (``games_sql``,
    ``market_rows_sql``, ``source_split_sql``, ``fixture_days_sql``). ``None`` for any
    of them means that statement produced no complete result: NO_RESULT.
    """
    base = {
        "schema": SCHEMA,
        "window_days": window_days,
        "core_sport_keys": sorted(cc.CORE_TEAM_SPORTS),
        "classes": list(cc.CLASSES),
        "thresholds": {
            "moneyline_per_game": {"rule": "moneyline >= games", "min": {"num": 1, "den": 1}},
            "other_share": {"rule": "10 * other < markets", "max_exclusive": {"num": 1, "den": 10}},
            "comparison": "exact integer cross-multiplication; nothing rounded",
        },
        "acceptance_population": "full window",
        "proves_player_container_rendering": False,
        "limitations": list(LIMITATIONS),
    }
    if type(window_days) is not int or window_days <= 0:
        return {**base, "verdict": NO_RESULT, "reconciliation": {
            "ok": False, "failures": [{"code": "MALFORMED_WINDOW"}]}}
    if window_days != ACCEPTANCE_WINDOW_DAYS:
        return {**base, "verdict": NO_RESULT, "reconciliation": {
            "ok": False, "failures": [{"code": "WINDOW_NOT_ACCEPTANCE_COHORT",
                                       "window_days": window_days,
                                       "acceptance_window_days": ACCEPTANCE_WINDOW_DAYS}]}}
    try:
        report = _account(games_rows, market_rows, source_rows, fixture_day_rows)
    except _Malformed as exc:
        return {**base, "verdict": NO_RESULT,
                "reconciliation": {"ok": False, "failures": [exc.failure]}}
    if report["reconciliation"]["failures"]:
        # Grades are never published over results that do not agree with each other.
        return {**base, "verdict": NO_RESULT, "reconciliation": report["reconciliation"]}
    return {**base, **report}


def _account(games_rows, market_rows, source_rows, fixture_day_rows) -> dict:
    games_raw = _rows(games_rows, GAMES_ARITY, "games")
    markets_raw = _rows(market_rows, MARKET_ARITY, "markets")
    sources_raw = _rows(source_rows, SOURCE_ARITY, "source_split")
    days_raw = _rows(fixture_day_rows, FIXTURE_ARITY, "fixture_days")
    failures: list[dict] = []

    games: dict[str, int] = {}
    for i, (sport, n) in enumerate(games_raw):
        key = _key(_text(sport, "sport_key", i, "games"))
        n = _count(n, "games", i, "games")
        if key in games:
            raise _Malformed("DUPLICATE_GROUP", statement="games", sport=key)
        if n == 0:
            raise _Malformed("EMPTY_GROUP", statement="games", sport=key)
        games[key] = n

    days: dict[str, dict[str, int]] = {}
    for i, (sport, day, n) in enumerate(days_raw):
        key = _key(_text(sport, "sport_key", i, "fixture_days"))
        dkey = _day_key(_day(day, i, "fixture_days"))
        n = _count(n, "games", i, "fixture_days")
        if dkey in days.get(key, {}):
            raise _Malformed("DUPLICATE_GROUP", statement="fixture_days", sport=key, fixture_day=dkey)
        if n == 0:
            raise _Malformed("EMPTY_GROUP", statement="fixture_days", sport=key, fixture_day=dkey)
        days.setdefault(key, {})[dkey] = n

    sources: dict[str, dict[str, dict]] = {}
    for i, (sport, source, outc, well, volp, voln, art) in enumerate(sources_raw):
        key = _key(_text(sport, "sport_key", i, "source_split"))
        skey = _key(_text(source, "source", i, "source_split"))
        if skey in sources.get(key, {}):
            raise _Malformed("DUPLICATE_GROUP", statement="source_split", sport=key, source=skey)
        entry = {
            "outcomes": _count(outc, "outcomes", i, "source_split"),
            "well_traded": _count(well, "well_traded", i, "source_split"),
            "vol_pos": _count(volp, "vol_pos", i, "source_split"),
            "vol_null_raw": _count(voln, "vol_null", i, "source_split"),
            "artifact": _count(art, "artifact", i, "source_split"),
        }
        if entry["outcomes"] == 0:  # the statement's HAVING forbids it
            raise _Malformed("EMPTY_GROUP", statement="source_split", sport=key, source=skey)
        sources.setdefault(key, {})[skey] = entry

    by_sport: dict[str, dict[str, dict]] = {}
    market_days: dict[str, set] = {}
    unknowns = {"null_sport_key_markets": 0, "null_name_markets": 0, "null_external_id_markets": 0,
                "null_side_markets": 0, "null_fixture_day_markets": 0, "unclassified_markets": 0,
                "zero_outcome_markets": 0, "null_source_groups": 0}
    for i, (sport, name, ext, outc, well, volp, voln, art, home, away, day) in enumerate(markets_raw):
        for field, value in (("sport_key", sport), ("name", name), ("external_id", ext),
                             ("home_team", home), ("away_team", away)):
            _text(value, field, i, "markets")
        _day(day, i, "markets")
        key = _key(sport)
        counts = {
            "outcomes": _count(outc, "outcomes", i, "markets"),
            "well_traded": _count(well, "well_traded", i, "markets"),
            "vol_pos": _count(volp, "vol_pos", i, "markets"),
            "vol_null_raw": _count(voln, "vol_null", i, "markets"),
            "artifact": _count(art, "artifact", i, "markets"),
        }
        zero = counts["outcomes"] == 0
        # Invariants of the statement's own LEFT JOIN aggregates. A zero-outcome market
        # is one all-NULL row: vol_null 1, everything else 0.
        if zero:
            ok = counts["vol_null_raw"] == 1 and not (counts["well_traded"] or counts["vol_pos"] or counts["artifact"])
        else:
            ok = (max(counts["well_traded"], counts["vol_pos"], counts["vol_null_raw"]) <= counts["outcomes"]
                  and counts["artifact"] <= counts["vol_pos"])
        if not ok:
            raise _Malformed("MALFORMED_COUNTER", statement="markets", row=i, field="aggregate_invariant")
        cls = classify_game_market_class(name or "", ext, sport, sides=(home, away))
        if cls not in cc.CLASSES:
            cls = UNCLASSIFIED
            unknowns["unclassified_markets"] += 1
        bucket = by_sport.setdefault(key, {}).setdefault(cls, _empty_class())
        bucket["markets"] += 1
        for field, value in counts.items():
            bucket[field] += value
        bucket["vol_null_outcomes"] += counts["vol_null_raw"] - (1 if zero else 0)
        bucket["zero_outcome_markets"] += 1 if zero else 0
        market_days.setdefault(key, set()).add(_day_key(day))
        unknowns["null_sport_key_markets"] += sport is None
        unknowns["null_name_markets"] += name is None
        unknowns["null_external_id_markets"] += ext is None
        unknowns["null_side_markets"] += home is None or away is None
        unknowns["null_fixture_day_markets"] += day is None
        unknowns["zero_outcome_markets"] += zero
    unknowns["null_sport_key_game_groups"] = sum(1 for s, _ in games_raw if s is None)
    unknowns["null_source_groups"] = sum(1 for _, s, *_ in sources_raw if s is None)

    # ── reconciliation: the four reads must describe one population ──────────
    for sport in sorted(set(games) | set(days)):
        day_total = sum(days.get(sport, {}).values())
        if day_total != games.get(sport, 0):
            failures.append({"code": "FIXTURE_DAYS_DISAGREE_WITH_GAMES", "sport": sport,
                             "games": games.get(sport, 0), "fixture_day_games": day_total})
    for sport in sorted(by_sport):
        if sport not in games:
            failures.append({"code": "MARKETS_WITHOUT_GAMES", "sport": sport})
        missing = sorted(market_days[sport] - set(days.get(sport, {})))
        if missing:
            failures.append({"code": "MARKET_DAY_NOT_IN_FIXTURE_DAYS", "sport": sport, "fixture_days": missing})
    for sport in sorted(set(sources) | set(by_sport)):
        if sport not in games:
            if sport in sources:
                failures.append({"code": "SOURCE_SPLIT_WITHOUT_GAMES", "sport": sport})
            continue
        classes = by_sport.get(sport, {})
        market_sum = {f: sum(c[f] for c in classes.values())
                      for f in ("outcomes", "well_traded", "vol_pos", "artifact", "vol_null_raw", "zero_outcome_markets")}
        source_sum = {f: sum(s[f] for s in sources.get(sport, {}).values())
                      for f in ("outcomes", "well_traded", "vol_pos", "artifact", "vol_null_raw")}
        # A group the HAVING drops holds only zero-outcome markets: it contributes 0 to
        # these four, so they agree exactly.
        for field in ("outcomes", "well_traded", "vol_pos", "artifact"):
            if market_sum[field] != source_sum[field]:
                failures.append({"code": "SOURCE_SPLIT_DISAGREES_WITH_MARKETS", "sport": sport, "field": field,
                                 "markets": market_sum[field], "source_split": source_sum[field]})
        # ...and each dropped zero-outcome market's NULL row is the only vol_null gap.
        gap = market_sum["vol_null_raw"] - source_sum["vol_null_raw"]
        if not 0 <= gap <= market_sum["zero_outcome_markets"]:
            failures.append({"code": "SOURCE_SPLIT_DISAGREES_WITH_MARKETS", "sport": sport, "field": "vol_null_raw",
                             "markets": market_sum["vol_null_raw"], "source_split": source_sum["vol_null_raw"],
                             "zero_outcome_markets": market_sum["zero_outcome_markets"]})

    if failures:
        return {"reconciliation": {"ok": False, "failures": failures}}

    # ── per-cohort accounting over the union ─────────────────────────────────
    universe = set(cc.CORE_TEAM_SPORTS) | set(games) | set(by_sport) | set(days) | set(sources)
    sports: dict[str, dict] = {}
    for sport in sorted(universe):
        classes = by_sport.get(sport, {})
        full = {cls: dict(classes.get(cls, _empty_class())) for cls in cc.CLASSES}
        if UNCLASSIFIED in classes:
            full[UNCLASSIFIED] = dict(classes[UNCLASSIFIED])
        n_games = games.get(sport, 0)
        n_markets = sum(c["markets"] for c in full.values())
        ml = full["moneyline"]["markets"]
        other = full["other"]["markets"]
        entry = {
            "games": n_games,
            "markets": n_markets,
            "fixture_days": len(days.get(sport, {})),
            "fixture_day_games": sum(days.get(sport, {}).values()),
            "classes": full,
            "moneyline_per_game": _fraction(ml, n_games),
            "other_share": _fraction(other, n_markets),
            "source_split": {s: dict(v) for s, v in sorted(sources.get(sport, {}).items())},
            "core": sport in cc.CORE_TEAM_SPORTS,
            "esports": _is_esports(sport),
        }
        if sport in cc.CORE_TEAM_SPORTS:
            entry.update(_grade(n_games, n_markets, ml, other))
        else:
            entry["verdict"] = NOT_GRADED
        sports[sport] = entry

    core = {s: sports[s]["verdict"] for s in sorted(cc.CORE_TEAM_SPORTS)}
    if FAIL in core.values():
        verdict = FAIL
    elif NO_POPULATION in core.values():
        verdict = NO_POPULATION
    else:
        verdict = PASS

    esports_keys = sorted(s for s in sports if sports[s]["esports"])
    esports = {
        "status": "OBSERVED" if any(sports[s]["games"] for s in esports_keys) else "UNKNOWN",
        "sport_keys": esports_keys,
        "graded": False,
        "note": ("Reported, not graded: esports is outside CORE_TEAM_SPORTS. "
                 + ("" if esports_keys else "No esports games in the window: coverage is UNKNOWN, not zero.")),
    }

    return {
        "verdict": verdict,
        "core_verdicts": core,
        "sports": sports,
        "esports": esports,
        "season_breakdown": _season_breakdown(days_raw, markets_raw, games),
        "unknowns": unknowns,
        "totals": {
            "games": sum(games.values()),
            # Every fetched market row lands in exactly one cohort class (an answer outside
            # the seven is kept as __unclassified__), so these two are equal by construction.
            "markets": sum(s["markets"] for s in sports.values()),
            "fetched_market_rows": len(markets_raw),
            "fixture_day_rows": len(days_raw),
            "source_split_rows": len(sources_raw),
        },
        "reconciliation": {"ok": True, "failures": []},
    }


def _grade(games: int, markets: int, ml: int, other: int) -> dict:
    if games == 0:
        # No market can belong to a game outside the window, so markets == 0 here too.
        return {"moneyline_check": NO_POPULATION, "other_check": NO_POPULATION, "verdict": NO_POPULATION}
    moneyline_check = PASS if ml >= games else FAIL
    if markets == 0:
        other_check = UNDEFINED
    else:
        other_check = PASS if 10 * other < markets else FAIL
    verdict = PASS if moneyline_check == PASS and other_check == PASS else FAIL
    return {"moneyline_check": moneyline_check, "other_check": other_check, "verdict": verdict}


def _season_breakdown(days_raw, markets_raw, games: dict[str, int]) -> dict:
    """The in-season slice ``capture_census.season_cohort`` computes, reported beside —
    never instead of — the full-window grade. Only banded or dated leagues are split;
    every other league's whole window is its season."""
    cohort = cc.season_cohort(days_raw, markets_raw)
    out = {}
    for sport in sorted(set(cohort.games_by_sport) | set(cohort.excluded_games)):
        in_classes = cohort.by_sport_class.get(sport, {})
        in_markets = {cls: (in_classes[cls].markets if cls in in_classes else 0) for cls in cc.CLASSES}
        out[sport] = {
            "window_games": games.get(sport, 0),
            "in_season_games": cohort.games_by_sport.get(sport, 0),
            "excluded_games": cohort.excluded_games.get(sport, 0),
            "in_season_markets_by_class": in_markets,
            "in_season_markets": sum(in_markets.values()),
        }
    return {
        "role": "informational; not an acceptance population",
        "split_sports": sorted(cc._SEASON_SPLIT_SPORTS),
        "sports": out,
    }
