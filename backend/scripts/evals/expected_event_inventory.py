"""Queue #269 / #1467 — Expected-event inventory + named-event recovery ledger.

Parent #1466's binding success definition forbids grading recovery against a
*markets/outcomes* denominator that can only ever contain rows Bain Luck already
captured. A missing event is invisible to such a denominator. This tool builds an
**independent** expected-event inventory for Tier-1 NBA / MLB / NHL from an
authoritative schedule source the project already uses (the ESPN scoreboard API,
a first-class win-prob source), then grades every expected event across the eight
inventory dimensions #1466 enumerates — so a game we never ingested still shows up
in the denominator as ``recoverable-missing`` instead of silently vanishing.

Design (mirrors the Template-A eval scripts in this directory):

* **Pure functions** (``parse_espn_scoreboard``, ``grade_event``, ``summarize``)
  take plain dicts and are fully unit-tested offline with fixtures — no network,
  no DB. They are import-safe (only stdlib) so ``tests/test_startup.py`` stays
  green.
* **Two pluggable I/O boundaries**, injected so tests never touch the wire:
    - ``ScheduleProvider`` — enumerates the "should-exist" slate for a
      (league, date). Default: ESPN scoreboard over ``urllib``.
    - ``LedgerBackend`` — grades the Bain Luck side of each expected event.
      Default: the documented read-only ``POST /api/admin/db-query`` rail
      (reachable headless; reproducible by anyone with ``ADMIN_TOKEN``).
* **Idempotent + resumable** via a JSON checkpoint keyed by canonical event id:
  slate fetches and graded rows are cached; a rerun with the same window is a
  no-op and produces byte-identical census output (asserted by a test).

Honesty rules baked into the grading (parent #1466 gate #5):

* An ``error`` (fetch/parse failure) is **never** collapsed into ``no data``. A
  slate whose ESPN fetch failed is recorded as ``request_failure`` /
  ``parse_failure`` and its expected count is ``unknown`` — it does not become a
  zero that shrinks the denominator.
* Named missing events and worst-case rows are always emitted by name; aggregate
  percentages may not mask them.
* No coverage threshold is invented and calibration success is not redefined —
  this tool measures and names gaps; the robustness thresholds it applies live in
  an explicit, versioned ``policy`` block.

CLI::

    # Real census (reads live production through the admin db-query rail):
    python3 scripts/evals/expected_event_inventory.py census \\
        --start 2026-04-01 --end 2026-07-27 \\
        --checkpoint /tmp/eei_q2q3.json --out /tmp/eei_census.json

    # Grade a JSON export offline (no network), e.g. in CI:
    python3 scripts/evals/expected_event_inventory.py grade --input export.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SCHEMA_VERSION = "expected-event-ledger/v1"

# ESPN sport/league path per Tier-1 league (matches SPORT_LEAGUE_MAP).
ESPN_PATHS = {
    "NBA": ("basketball", "nba"),
    "MLB": ("baseball", "mlb"),
    "NHL": ("hockey", "nhl"),
}
LEAGUES = tuple(ESPN_PATHS)

# Dimension states — the four #1466 buckets, plus NOT_APPLICABLE for games that
# genuinely did not happen (postponed/canceled) or have not happened yet.
PRESENT = "present"
RECOVERABLE_MISSING = "recoverable-missing"
ATTEMPTED_UNAVAILABLE = "attempted-unavailable"
NOT_APPLICABLE = "not-applicable"
UNKNOWN = "unknown"
DIM_STATES = (PRESENT, RECOVERABLE_MISSING, ATTEMPTED_UNAVAILABLE, NOT_APPLICABLE, UNKNOWN)

# Recovery-stage attempt classes (gate #5) — never collapse error -> no data.
COMPLETE = "complete"
SPARSE_HISTORY = "sparse-history"
ABSENT_UPSTREAM = "absent-upstream"
REQUEST_FAILURE = "request-failure"
PARSE_FAILURE = "parse-failure"
UNRESOLVED_IDENTITY = "unresolved-identity"
EVENT_MISSING = "event-missing"

DIMENSIONS = (
    "event_existence",
    "event_linkage",
    "final_result",
    "winner_truth",
    "calibration_forecast",
    "pregame_history",
    "ingame_history",
    "rendered_chart",
)

# Explicit, versioned robustness policy. No hidden thresholds; this is what
# "good enough that a user would not know there had been a capture failure"
# is operationalised as for the FIRST census. It is a measurement policy, not a
# redefinition of calibration success.
DEFAULT_POLICY = {
    "version": "expected-event-robustness/v1",
    "pregame_min_points": 3,
    "ingame_min_points": 6,
    "chart_min_points": 10,
}


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_team(name: str) -> str:
    """Lowercase, strip punctuation, keep the final significant token.

    ESPN and Bain Luck agree on the nickname ("Rays", "Yankees") far more often
    than on the full display name, so the last token is the stable key. Falls
    back to the whole slug if there is only one token.
    """
    if not name:
        return ""
    slug = _NON_ALNUM.sub(" ", name.lower()).strip()
    if not slug:
        return ""
    tokens = slug.split()
    return tokens[-1]


def canonical_event_id(league: str, game_date: str, away: str, home: str, game_number: int) -> str:
    """Stable identity independent of any Bain Luck row.

    ``game_number`` disambiguates MLB doubleheaders (and is always present, ``1``
    for ordinary games, so the key shape never changes).
    """
    a = normalize_team(away) or "unknown"
    h = normalize_team(home) or "unknown"
    return f"{league}:{game_date}:{a}@{h}:G{game_number}"


# --------------------------------------------------------------------------- #
# ESPN scoreboard parsing (pure)
# --------------------------------------------------------------------------- #
_ESPN_STATUS = {
    "STATUS_FINAL": ("final", True),
    "STATUS_FULL_TIME": ("final", True),
    "STATUS_SCHEDULED": ("scheduled", False),
    "STATUS_IN_PROGRESS": ("in", False),
    "STATUS_HALFTIME": ("in", False),
    "STATUS_END_PERIOD": ("in", False),
    "STATUS_POSTPONED": ("postponed", False),
    "STATUS_CANCELED": ("canceled", False),
    "STATUS_SUSPENDED": ("suspended", False),
    "STATUS_DELAYED": ("scheduled", False),
    "STATUS_RAIN_DELAY": ("scheduled", False),
}


def parse_espn_scoreboard(payload: dict, league: str, slate_date: str) -> list[dict]:
    """Turn one ESPN scoreboard payload into expected-game dicts.

    ``slate_date`` (the queried YYYY-MM-DD) is the authoritative slate date — it
    sidesteps the UTC-vs-local boundary because a game belongs to the date you
    asked ESPN for it under. Preseason (``season.type == 1``) is excluded.
    Doubleheaders are numbered by commence order within a (date, matchup).
    """
    games: list[dict] = []
    for ev in payload.get("events", []) or []:
        try:
            season_type = (ev.get("season") or {}).get("type")
            if season_type == 1:  # preseason is not a Tier-1 "should-exist" game
                continue
            comp = (ev.get("competitions") or [{}])[0]
            competitors = comp.get("competitors") or []
            home = away = None
            home_score = away_score = None
            for c in competitors:
                team = (c.get("team") or {}).get("displayName") or ""
                score = c.get("score")
                try:
                    score = int(score) if score not in (None, "") else None
                except (TypeError, ValueError):
                    score = None
                if c.get("homeAway") == "home":
                    home, home_score = team, score
                elif c.get("homeAway") == "away":
                    away, away_score = team, score
            if not home or not away:
                continue
            st = (ev.get("status") or {}).get("type") or {}
            status, completed = _ESPN_STATUS.get(st.get("name", ""), (st.get("state", "unknown"), bool(st.get("completed"))))
            games.append(
                {
                    "league": league,
                    "espn_event_id": str(ev.get("id")) if ev.get("id") is not None else None,
                    "game_date": slate_date,
                    "commence_time": ev.get("date"),
                    "away_team": away,
                    "home_team": home,
                    "away_norm": normalize_team(away),
                    "home_norm": normalize_team(home),
                    "status": status,
                    "completed": completed,
                    "away_score": away_score,
                    "home_score": home_score,
                    "season_type": season_type,
                }
            )
        except Exception:  # one malformed event must not drop the whole slate
            continue

    # Assign doubleheader game numbers deterministically by commence order.
    by_matchup: dict[tuple[str, str], list[dict]] = {}
    for g in games:
        by_matchup.setdefault((g["away_norm"], g["home_norm"]), []).append(g)
    for matchup_games in by_matchup.values():
        matchup_games.sort(key=lambda g: (g.get("commence_time") or "", g.get("espn_event_id") or ""))
        for idx, g in enumerate(matchup_games, start=1):
            g["game_number"] = idx
    for g in games:
        g["canonical_event_id"] = canonical_event_id(
            g["league"], g["game_date"], g["away_team"], g["home_team"], g["game_number"]
        )
    games.sort(key=lambda g: g["canonical_event_id"])
    return games


# --------------------------------------------------------------------------- #
# Grading (pure)
# --------------------------------------------------------------------------- #
def _dim(state: str, attempt: str, value: Any = None, evidence: str = "") -> dict:
    return {"state": state, "attempt": attempt, "value": value, "evidence": evidence}


def grade_event(expected: dict, bl: Optional[dict], policy: Optional[dict] = None) -> dict:
    """Grade one expected event across the eight #1466 dimensions.

    ``bl`` is the matched Bain Luck side (or ``None`` when no row exists), a plain
    dict with keys: ``exists``, ``match_method``, ``status``, ``completed``,
    ``home_score``, ``away_score``, ``has_closing_prob``, ``linkage_count``,
    ``pregame_snaps``, ``ingame_snaps``, ``total_snaps``, ``wp_sources``.
    Downstream dimensions are never fabricated: if the event row is missing they
    are ``recoverable-missing`` with attempt ``event-missing`` (recovering the row
    unlocks them), not ``unknown`` and not a silent zero.
    """
    policy = policy or DEFAULT_POLICY
    status = expected.get("status")
    played = expected.get("completed") is True or status in ("final", "in")
    did_not_happen = status in ("postponed", "canceled", "suspended")
    future = status == "scheduled"

    dims: dict[str, dict] = {}

    # 1. Event existence — the one dimension that is truly denominator-independent.
    if bl and bl.get("exists"):
        dims["event_existence"] = _dim(
            PRESENT, COMPLETE, True, f"matched via {bl.get('match_method', 'unknown')}"
        )
    else:
        # Named as recoverable-missing (or attempted-unavailable if a prior
        # recovery attempt proved it unavailable upstream — not the case here).
        dims["event_existence"] = _dim(
            RECOVERABLE_MISSING, EVENT_MISSING, False,
            "ESPN lists this game; no Bain Luck event row matched",
        )

    def _downstream(present_test: Callable[[], bool], value: Any, na: bool = False,
                    sparse_test: Optional[Callable[[], bool]] = None, note: str = "") -> dict:
        if not (bl and bl.get("exists")):
            return _dim(RECOVERABLE_MISSING, EVENT_MISSING, value,
                        "blocked: event row missing — recover existence first")
        if na:
            return _dim(NOT_APPLICABLE, COMPLETE, value, note)
        if present_test():
            return _dim(PRESENT, COMPLETE, value, note)
        if sparse_test and sparse_test():
            return _dim(RECOVERABLE_MISSING, SPARSE_HISTORY, value, note or "present but sparse")
        return _dim(RECOVERABLE_MISSING, COMPLETE, value, note or "recoverable and missing")

    lc = (bl or {}).get("linkage_count") or 0
    hs = (bl or {}).get("home_score")
    as_ = (bl or {}).get("away_score")
    has_close = bool((bl or {}).get("has_closing_prob"))
    pre = (bl or {}).get("pregame_snaps") or 0
    ing = (bl or {}).get("ingame_snaps") or 0
    tot = (bl or {}).get("total_snaps") or 0

    # 2. Event linkage — game markets linked via event_id.
    dims["event_linkage"] = _downstream(lambda: lc > 0, lc, note=f"{lc} linked market(s)")

    # 3. Final result — real final score present (only meaningful once played).
    dims["final_result"] = _downstream(
        lambda: hs is not None and as_ is not None,
        {"home": hs, "away": as_},
        na=(did_not_happen or future),
        note="final score present" if not (did_not_happen or future) else "game did not occur / not yet played",
    )

    # 4. Winner truth — score + completed status determines the authoritative winner.
    dims["winner_truth"] = _downstream(
        lambda: hs is not None and as_ is not None and bool((bl or {}).get("completed")),
        {"completed": bool((bl or {}).get("completed"))},
        na=(did_not_happen or future),
    )

    # 5. Calibration forecast — closing line present (analogue of calibration_probability).
    dims["calibration_forecast"] = _downstream(
        lambda: has_close, has_close, na=did_not_happen,
        note="closing line present" if has_close else "no closing_home_probability",
    )

    # 6. Pre-event price history density.
    dims["pregame_history"] = _downstream(
        lambda: pre >= policy["pregame_min_points"], pre, na=did_not_happen,
        sparse_test=lambda: 0 < pre < policy["pregame_min_points"],
        note=f"{pre} pregame snapshot(s)",
    )

    # 7. In-event win-probability density (only applies once the game was played).
    dims["ingame_history"] = _downstream(
        lambda: ing >= policy["ingame_min_points"], ing,
        na=(did_not_happen or future),
        sparse_test=lambda: 0 < ing < policy["ingame_min_points"],
        note=f"{ing} in-game snapshot(s)",
    )

    # 8. Rendered-chart readiness — enough spanning points to draw a usable chart.
    dims["rendered_chart"] = _downstream(
        lambda: tot >= policy["chart_min_points"] and pre >= policy["pregame_min_points"] and ing >= policy["ingame_min_points"],
        tot,
        na=(did_not_happen or future),
        sparse_test=lambda: 0 < tot < policy["chart_min_points"],
        note=f"{tot} total snapshot(s) (aggregate-density proxy; --verify-charts confirms rendered points)",
    )

    overall = _overall_state([d["state"] for d in dims.values()])
    return {
        "canonical_event_id": expected["canonical_event_id"],
        "league": expected["league"],
        "game_date": expected["game_date"],
        "matchup": f"{expected['away_team']} @ {expected['home_team']}",
        "espn_event_id": expected.get("espn_event_id"),
        "status": status,
        "played": played,
        "bl_event_id": (bl or {}).get("event_id"),
        "match_method": (bl or {}).get("match_method") if bl else None,
        "dimensions": dims,
        "overall_state": overall,
    }


def _overall_state(states: Iterable[str]) -> str:
    states = list(states)
    applicable = [s for s in states if s != NOT_APPLICABLE]
    if not applicable:
        return NOT_APPLICABLE
    if UNKNOWN in applicable:
        return UNKNOWN
    if RECOVERABLE_MISSING in applicable:
        return RECOVERABLE_MISSING
    if ATTEMPTED_UNAVAILABLE in applicable:
        return ATTEMPTED_UNAVAILABLE
    return PRESENT


# --------------------------------------------------------------------------- #
# Census summary (pure)
# --------------------------------------------------------------------------- #
def _month(game_date: str) -> str:
    return game_date[:7]


def summarize(rows: list[dict], slate_attempts: list[dict], policy: Optional[dict] = None,
              worst_case_limit: int = 25) -> dict:
    """Aggregate the ledger without ever hiding a named gap.

    Emits: per league×month per-dimension state counts, overall totals
    (expected · present · recoverable · attempted-unavailable · unknown ·
    not-applicable · missing-event), named worst-case lists, a separate June
    breakout, and the slate-fetch failure ledger (so ``error`` never reads as a
    shrunken denominator).
    """
    policy = policy or DEFAULT_POLICY

    def _empty_dim_counts() -> dict:
        return {dim: {s: 0 for s in DIM_STATES} for dim in DIMENSIONS}

    per_league_month: dict[str, dict] = {}
    totals = {
        "expected": 0,
        "present": 0,          # every applicable dimension present
        "recoverable": 0,      # >=1 recoverable-missing dimension
        "missing_event": 0,    # the event row itself is absent
        "attempted_unavailable": 0,
        "unknown": 0,
        "not_applicable": 0,   # game did not occur / not yet played
    }
    dim_totals = _empty_dim_counts()
    worst: dict[str, list[dict]] = {
        "missing_event": [],
        "missing_final_result": [],
        "missing_winner_truth": [],
        "missing_calibration_forecast": [],
        "missing_pregame_history": [],
        "missing_ingame_history": [],
        "not_chart_ready": [],
    }

    for r in rows:
        key = f"{r['league']}:{_month(r['game_date'])}"
        lm = per_league_month.setdefault(
            key, {"league": r["league"], "month": _month(r["game_date"]),
                  "expected": 0, "overall": {s: 0 for s in DIM_STATES}, "dimensions": _empty_dim_counts()}
        )
        lm["expected"] += 1
        totals["expected"] += 1
        lm["overall"][r["overall_state"]] = lm["overall"].get(r["overall_state"], 0) + 1

        for dim, d in r["dimensions"].items():
            lm["dimensions"][dim][d["state"]] += 1
            dim_totals[dim][d["state"]] += 1

        ov = r["overall_state"]
        if ov == PRESENT:
            totals["present"] += 1
        elif ov == NOT_APPLICABLE:
            totals["not_applicable"] += 1
        elif ov == UNKNOWN:
            totals["unknown"] += 1
        elif ov == ATTEMPTED_UNAVAILABLE:
            totals["attempted_unavailable"] += 1
        else:
            totals["recoverable"] += 1

        if r["dimensions"]["event_existence"]["state"] != PRESENT:
            totals["missing_event"] += 1

        # Named worst-case capture (only games that were played).
        stub = {"canonical_event_id": r["canonical_event_id"], "matchup": r["matchup"],
                "game_date": r["game_date"], "league": r["league"], "espn_event_id": r["espn_event_id"]}
        if r["dimensions"]["event_existence"]["state"] != PRESENT:
            worst["missing_event"].append(stub)
        if r["played"]:
            def _bad(dim):
                return r["dimensions"][dim]["state"] in (RECOVERABLE_MISSING, ATTEMPTED_UNAVAILABLE, UNKNOWN)
            if _bad("final_result"):
                worst["missing_final_result"].append(stub)
            if _bad("winner_truth"):
                worst["missing_winner_truth"].append(stub)
            if _bad("calibration_forecast"):
                worst["missing_calibration_forecast"].append(stub)
            if _bad("pregame_history"):
                worst["missing_pregame_history"].append({**stub, "pregame_snaps": r["dimensions"]["pregame_history"]["value"]})
            if _bad("ingame_history"):
                worst["missing_ingame_history"].append({**stub, "ingame_snaps": r["dimensions"]["ingame_history"]["value"]})
            if _bad("rendered_chart"):
                worst["not_chart_ready"].append({**stub, "total_snaps": r["dimensions"]["rendered_chart"]["value"]})

    # Worst-case lists: report full count, but only inline the first N named rows.
    worst_summary = {}
    for k, lst in worst.items():
        lst.sort(key=lambda s: (s["league"], s["game_date"], s["canonical_event_id"]))
        worst_summary[k] = {"count": len(lst), "named": lst[:worst_case_limit],
                            "truncated": max(0, len(lst) - worst_case_limit)}

    # Slate-fetch failure ledger — error is never no-data.
    slate_ledger = {"ok": 0, REQUEST_FAILURE: 0, PARSE_FAILURE: 0, ABSENT_UPSTREAM: 0, "failed_slates": []}
    for s in slate_attempts:
        cls = s.get("result", "ok")
        slate_ledger[cls] = slate_ledger.get(cls, 0) + 1
        if cls in (REQUEST_FAILURE, PARSE_FAILURE):
            slate_ledger["failed_slates"].append(
                {"league": s.get("league"), "date": s.get("date"), "result": cls, "detail": s.get("detail", "")}
            )

    # June breakout (2026-06) — separately from the Q2/Q3 aggregate per #1467 scope.
    june_keys = [k for k in per_league_month if k.endswith(":2026-06")]
    june = {k: per_league_month[k] for k in sorted(june_keys)}

    return {
        "schema_version": SCHEMA_VERSION,
        "policy": policy,
        "totals": totals,
        "dimension_totals": dim_totals,
        "per_league_month": dict(sorted(per_league_month.items())),
        "june_breakout": june,
        "worst_cases": worst_summary,
        "slate_ledger": slate_ledger,
        "denominator_note": (
            "Expected count is ESPN-authoritative and independent of Bain Luck rows. "
            "Slates whose fetch failed are counted as request/parse failures, NOT as zero — "
            "so a fetch error cannot shrink the denominator."
        ),
    }


# --------------------------------------------------------------------------- #
# I/O boundaries (injected; excluded from unit tests)
# --------------------------------------------------------------------------- #
def _http_json(url: str, method: str = "GET", body: Optional[dict] = None,
               headers: Optional[dict] = None, timeout: int = 20, retries: int = 2) -> dict:
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode() if body is not None else None
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:  # noqa: BLE001 — caller classifies request vs parse
            last_exc = exc
            if attempt < retries:
                time.sleep(0.6 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


class ESPNScheduleProvider:
    """Default ScheduleProvider — the keyless ESPN scoreboard API."""

    BASE = "https://site.api.espn.com/apis/site/v2/sports"

    def __init__(self, delay: float = 0.25):
        self.delay = delay

    def fetch(self, league: str, day: str) -> dict:
        """Return {'result': ok|request-failure|parse-failure, 'games': [...], 'detail': ...}."""
        sport, lg = ESPN_PATHS[league]
        ymd = day.replace("-", "")
        url = f"{self.BASE}/{sport}/{lg}/scoreboard?dates={ymd}"
        try:
            payload = _http_json(url)
        except Exception as exc:  # noqa: BLE001
            return {"result": REQUEST_FAILURE, "games": [], "detail": f"{type(exc).__name__}: {exc}"}
        try:
            games = parse_espn_scoreboard(payload, league, day)
        except Exception as exc:  # noqa: BLE001
            return {"result": PARSE_FAILURE, "games": [], "detail": f"{type(exc).__name__}: {exc}"}
        time.sleep(self.delay)
        return {"result": "ok", "games": games}


class DBQueryLedgerBackend:
    """Default LedgerBackend — grades the Bain Luck side via POST /api/admin/db-query."""

    def __init__(self, api_base: str, admin_token: str):
        self.api = api_base.rstrip("/")
        self.token = admin_token

    def _query(self, sql: str, limit: int = 1000) -> list[list]:
        payload = _http_json(
            f"{self.api}/api/admin/db-query", method="POST",
            body={"sql": sql, "limit": limit},
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            timeout=40,
        )
        return payload.get("rows", [])

    def fetch_bl_side(self, league: str, month_start: str, month_end: str) -> dict:
        """Return {espn_id: bl_dict} plus {(date, away_norm, home_norm): bl_dict} for fallback matching."""
        ev_rows = self._query(
            "SELECT e.id, e.espn_id, e.home_team_name, e.away_team_name, "
            "e.home_team_normalized, e.away_team_normalized, e.commence_time, e.status, "
            "e.home_score, e.away_score, e.completed_at, "
            "(e.closing_home_probability IS NOT NULL) AS has_close, "
            "(e.win_probability_sources IS NOT NULL) AS has_wps "
            f"FROM events e WHERE e.llm_league = '{league}' "
            f"AND e.commence_time >= '{month_start}' AND e.commence_time < '{month_end}' "
            "ORDER BY e.id"
        )
        events: dict[int, dict] = {}
        for r in ev_rows:
            (eid, espn_id, home_name, away_name, home_norm, away_norm, commence, status,
             hs, as_, completed_at, has_close, has_wps) = r
            events[eid] = {
                "event_id": eid, "exists": True, "espn_id": str(espn_id) if espn_id else None,
                "home_norm": (home_norm or normalize_team(home_name or "")),
                "away_norm": (away_norm or normalize_team(away_name or "")),
                "commence_time": commence, "status": status,
                "completed": status in ("completed", "closed") or completed_at is not None,
                "home_score": hs, "away_score": as_, "has_closing_prob": bool(has_close),
                "has_wps": bool(has_wps), "linkage_count": 0,
                "pregame_snaps": 0, "ingame_snaps": 0, "total_snaps": 0,
            }
        ids = list(events)
        if ids:
            id_list = ",".join(str(i) for i in ids)
            for eid, cnt in self._query(
                f"SELECT event_id, count(*) FROM futures_markets WHERE event_id IN ({id_list}) GROUP BY event_id"
            ):
                if eid in events:
                    events[eid]["linkage_count"] = cnt
            for row in self._query(
                "SELECT s.event_id, count(*) AS total, "
                "sum(CASE WHEN s.captured_at < e.commence_time THEN 1 ELSE 0 END) AS pregame, "
                "sum(CASE WHEN s.captured_at >= e.commence_time THEN 1 ELSE 0 END) AS ingame "
                f"FROM win_prob_snapshots s JOIN events e ON e.id = s.event_id "
                f"WHERE s.event_id IN ({id_list}) GROUP BY s.event_id"
            ):
                eid, total, pregame, ingame = row
                if eid in events:
                    events[eid]["total_snaps"] = total or 0
                    events[eid]["pregame_snaps"] = pregame or 0
                    events[eid]["ingame_snaps"] = ingame or 0

        by_espn = {v["espn_id"]: v for v in events.values() if v["espn_id"]}
        by_teams: dict[tuple, dict] = {}
        for v in events.values():
            ct = v["commence_time"]
            d = str(ct)[:10] if ct else ""
            by_teams[(d, v["away_norm"], v["home_norm"])] = v
        return {"by_espn": by_espn, "by_teams": by_teams}

    def fetch_chart_points(self, event_id: int) -> dict:
        """Rendered-chart proof: real win_prob_history point counts from /api/events/{id}/history."""
        try:
            payload = _http_json(f"{self.api}/api/events/{event_id}/history?hours=720", timeout=30)
        except Exception as exc:  # noqa: BLE001
            return {"result": REQUEST_FAILURE, "detail": f"{type(exc).__name__}: {exc}"}
        wp = payload.get("win_prob_history") or {}
        per_source = {src: len(pts or []) for src, pts in wp.items()}
        return {"result": "ok", "win_prob_points": sum(per_source.values()),
                "per_source": per_source, "odds_points": len(payload.get("history") or [])}


# --------------------------------------------------------------------------- #
# Matching + census orchestration
# --------------------------------------------------------------------------- #
def match_bl(expected: dict, bl_index: dict) -> Optional[dict]:
    """Match an expected ESPN game to a Bain Luck event: espn_id first, then
    (date, normalized teams). Returns the bl dict with ``match_method`` set."""
    espn_id = expected.get("espn_event_id")
    if espn_id and espn_id in bl_index.get("by_espn", {}):
        return {**bl_index["by_espn"][espn_id], "match_method": "espn_id"}
    key = (expected["game_date"], expected["away_norm"], expected["home_norm"])
    if key in bl_index.get("by_teams", {}):
        return {**bl_index["by_teams"][key], "match_method": "date+teams"}
    return None


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _month_bounds(start: date, end: date) -> list[tuple[str, str]]:
    bounds, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
        bounds.append((cur.isoformat(), nxt.isoformat()))
        cur = nxt
    return bounds


def run_census(start: str, end: str, schedule: Any, backend: Any,
               checkpoint: Optional[str] = None, force: bool = False,
               policy: Optional[dict] = None, verify_charts: int = 0,
               log: Callable[[str], None] = lambda m: None) -> dict:
    """Enumerate the expected slate, grade every game, and summarize.

    Idempotent + resumable: cached slate fetches and graded rows are reused from
    the checkpoint unless ``force``. Byte-identical output on a clean rerun.
    """
    policy = policy or DEFAULT_POLICY
    ck = {"slates": {}, "rows": {}}
    if checkpoint and Path(checkpoint).exists() and not force:
        try:
            ck = json.loads(Path(checkpoint).read_text())
        except Exception:  # a corrupt checkpoint should not wedge the run
            ck = {"slates": {}, "rows": {}}
    ck.setdefault("slates", {})
    ck.setdefault("rows", {})

    start_d, end_d = date.fromisoformat(start), date.fromisoformat(end)

    # 1) Fetch every (league, day) slate → expected inventory (with failure ledger).
    slate_attempts: list[dict] = []
    expected: dict[str, dict] = {}
    for league in LEAGUES:
        for d in _daterange(start_d, end_d):
            day = d.isoformat()
            skey = f"{league}:{day}"
            cached = ck["slates"].get(skey)
            if cached and not force:
                res = cached
            else:
                res = schedule.fetch(league, day)
                ck["slates"][skey] = res
                if checkpoint:
                    Path(checkpoint).write_text(json.dumps(ck))
            slate_attempts.append({"league": league, "date": day,
                                   "result": res.get("result", "ok"), "detail": res.get("detail", "")})
            for g in res.get("games", []):
                if g.get("season_type") == 1:
                    continue
                expected[g["canonical_event_id"]] = g
        log(f"{league}: enumerated through {end}")

    # 2) Grade each expected event against the Bain Luck side (bulk per league-month).
    bl_cache: dict[str, dict] = {}
    for league in LEAGUES:
        for ms, me in _month_bounds(start_d, end_d):
            bl_cache[f"{league}:{ms}"] = backend.fetch_bl_side(league, ms, me)
        log(f"{league}: fetched Bain Luck side")

    rows: list[dict] = []
    for cid, g in sorted(expected.items()):
        ms = f"{g['league']}:{g['game_date'][:7]}-01"
        # month bound key uses first-of-month; find the matching cache entry
        bl_index = None
        for ms2, me2 in _month_bounds(start_d, end_d):
            if ms2[:7] == g["game_date"][:7]:
                bl_index = bl_cache.get(f"{g['league']}:{ms2}")
                break
        bl = match_bl(g, bl_index or {})
        rows.append(grade_event(g, bl, policy))
    rows.sort(key=lambda r: r["canonical_event_id"])
    ck["rows"] = {r["canonical_event_id"]: r for r in rows}
    if checkpoint:
        Path(checkpoint).write_text(json.dumps(ck))

    census = summarize(rows, slate_attempts, policy)

    # 3) Optional rendered-chart proof for representative + worst-case events.
    if verify_charts and hasattr(backend, "fetch_chart_points"):
        present = [r for r in rows if r["played"] and r["overall_state"] == PRESENT and r["bl_event_id"]]
        worst = [r for r in rows if r["played"] and r["dimensions"]["rendered_chart"]["state"] != PRESENT and r["bl_event_id"]]
        sample = present[:verify_charts] + worst[:verify_charts]
        proofs = []
        for r in sample:
            proof = backend.fetch_chart_points(r["bl_event_id"])
            proofs.append({"canonical_event_id": r["canonical_event_id"], "matchup": r["matchup"],
                           "bl_event_id": r["bl_event_id"], "overall_state": r["overall_state"], **proof})
            log(f"chart proof {r['matchup']}: {proof.get('win_prob_points', proof.get('result'))}")
        census["rendered_chart_proofs"] = proofs

    census["window"] = {"start": start, "end": end,
                        "expected_events": len(expected),
                        "graded_rows": len(rows)}
    return census


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_env() -> tuple[str, str]:
    import os
    api = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")
    token = os.environ.get("ADMIN_TOKEN", "")
    return api, token


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Expected-event inventory + named-event recovery ledger (#1467)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("census", help="Run the real census against production")
    c.add_argument("--start", required=True)
    c.add_argument("--end", required=True)
    c.add_argument("--checkpoint", default=None)
    c.add_argument("--out", default=None)
    c.add_argument("--force", action="store_true")
    c.add_argument("--verify-charts", type=int, default=0)

    g = sub.add_parser("grade", help="Grade a JSON export offline (no network)")
    g.add_argument("--input", required=True, help="{'expected':[...], 'bl_index':{...}, 'slate_attempts':[...]}")

    args = parser.parse_args(argv)

    if args.cmd == "grade":
        data = json.loads(Path(args.input).read_text())
        rows = []
        for exp in data.get("expected", []):
            bl = match_bl(exp, data.get("bl_index", {}))
            rows.append(grade_event(exp, bl))
        report = summarize(rows, data.get("slate_attempts", []))
        print(json.dumps(report, indent=2, default=str))
        return 0

    api, token = _load_env()
    if not token:
        print("ADMIN_TOKEN not set (source ~/.claude/.env first)", file=sys.stderr)
        return 2
    schedule = ESPNScheduleProvider()
    backend = DBQueryLedgerBackend(api, token)
    census = run_census(args.start, args.end, schedule, backend,
                        checkpoint=args.checkpoint, force=args.force,
                        verify_charts=args.verify_charts,
                        log=lambda m: print(m, file=sys.stderr))
    out = json.dumps(census, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(out)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
