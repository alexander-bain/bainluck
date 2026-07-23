"""Settled-Concept Sentinel — the guard Queue #225 earned (Queue #226 Item 1).

When a marquee event settles, its concept page must switch cleanly into the ONE
settled language: the champion is the hero, the field is purged of non-competitors,
the evolution chart resolves to the winner, and round/derivative markets stop
showing live odds. #225 fixed The Open by hand after Alex found the rot on a Monday.
This sentinel is that Monday-morning check, automated: within ~24h of any marquee
concept settling (THE HORIZON CALENDAR knows the dates), it reads the LIVE
event-concept surface and asserts the settled contract, filing work when it breaks.

Four checks per settled concept (each classified REAL vs EXPLAINED so RED == REAL,
per the Grid/Flow sentinel family):

  A. CHAMPION HERO   — primary is a winner class, exactly one competitor carries
                       ``won: true``, and that winner is the top-probability
                       competitor. Catches: null hero, a co-winner / out-of-domain
                       squash-class winner (#225 Item 1), a non-winner crowned.
  B. FIELD MEMBERSHIP — every outcome in a round-leader / round-finish market
                       resolves to a competitor in the settled field (under name
                       normalization: exact, diacritic-stripped, last|first-initial).
                       Catches: out-of-field contamination (the Tiger-Woods class,
                       #225 golf round-leader forensic). A name that matches only a
                       fuzzy key is a spelling variant = EXPLAINED, not a defect.
  C. EVOLUTION RESOLVES — the winner-evolution chart (``evolution_market_id``)
                       resolves: exactly one line reaches ~100% and it is the graded
                       winner; no 0.99-wall (> N outcomes at >= 0.98, the overround
                       artifact); the winner line is not fizzled below the resolve
                       floor (#225 Item 3, the odds_api-fizzle-vs-Kalshi-resolve bug).
                       #1177: the ``evolution_market_id`` now PREFERS a graded market
                       by rule (``winner_field_selection.prefer_graded_winner_field``),
                       so this check should stay GREEN once a concept settles.

CLOSE DISCIPLINE (#1177): an issue of this class may only be closed after
``GREEN_STREAK_TO_CLOSE`` (=2) CONSECUTIVE GREEN runs on the concept — the WC
re-broke once because a single green read (a lucky market-selection snapshot) was
trusted. Each run tracks a per-concept green streak (Redis) and the scorecard
exposes ``green_streak`` + ``closeable`` + a top-level ``closeable_concepts`` list;
the closer (human/agent or a future auto-close) must gate on ``closeable``.
  D. ROUND RESOLUTION — no single-winner round-leader market is double-graded
                       (>= 2 outcomes at resolved-high — two leaders is impossible).
                       A round market with NO graded winner is EXPLAINED (field-shaped
                       prop grading is the deferred #887 / L2-121 backend), never RED.

Modeled on the Horizon/Flow/Grid sentinels: same mine -> classify -> evidence-pack
-> auto-file rail (``bug_report_github``), same fingerprint dedup, same Redis
scorecard, same admin ``run``/``last`` pair. Read-only against production — it files
work, never data (gotcha #21). Targets come from THE HORIZON CALENDAR
(``app/config/majors_calendar.yaml``): any entry with a ``concept_key`` whose window
just ended, plus any explicit ``concept_keys`` passed to a run.
"""

import hashlib
import logging
import os
import re
import time as _time
from datetime import date, datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SETTLED_SENTINEL_API = os.environ.get(
    "SETTLED_SENTINEL_API", os.environ.get("FLOW_SENTINEL_API", "https://api.bainluck.com")
)
HTTP_TIMEOUT = 20.0

# A concept is a "recently settled" target when its calendar window ended within
# this many days of today. Daily cadence + a few days of slack = every settle is
# caught within ~24h even if a run is missed. Explicit concept_keys bypass this.
SETTLE_WINDOW_DAYS = 3

# Check thresholds (all parameterized so a domain override is a one-liner later).
RESOLVE_MIN = 0.90   # the winner line must reach this or it "fizzled"
WALL_PROB = 0.98     # "resolved-high" band
WALL_MAX = 3         # > this many outcomes at >= WALL_PROB in the field = a 0.99-wall

# #1177 close discipline: this class of issue (settled winner-field selection) may
# only be CLOSED after this many CONSECUTIVE GREEN sentinel runs on the concept. A
# single green read can be a lucky market-selection snapshot (the WC re-broke on
# exactly that), so `closeable` in the scorecard requires a sustained streak.
GREEN_STREAK_TO_CLOSE = 2
_GREEN_STREAK_TTL = 30 * 86400

# Winner-field kinds — a settled concept's hero must be one of these, never a
# non-winner market class (a prop / placement / squash contaminant).
_WINNER_KINDS = {"winner_field", "winner", "bracket"}

# A settled field is "frozen" when some competitor sits at/near 100% — i.e. the
# settled-means-settled freeze ran (champion 1.0, field 0.0). Below this, the
# field is still a live/pre-settlement distribution (nobody graded to 1.0), the
# signature of the correct-crown-stale-probs class (#229): the champion is graded
# (won:true) but the winner market is re-polluting current_probability (gotcha
# #33) so the crown displays a stale price below the live field.
_FROZEN_WINNER_THRESHOLD = 0.90

# Round-leader / round-finish market families (field-shaped, golfer/competitor
# name outcomes). Field membership + round-resolution checks scope to these.
_ROUND_LEADER_RE = re.compile(r"round\s+\d+\s+leader|end of round\s+\d+\s+leader", re.I)
_ROUND_FINISH_RE = re.compile(r"round\s+\d+.*(top\s+\d+|finisher)", re.I)

# Structural (non-competitor) outcome tokens that legitimately appear in a
# round/finish-shaped market and must NOT be flagged as field contamination
# (region roll-ups, yes/no, over/under threshold ladders).
_STRUCTURAL_OUTCOME_RE = re.compile(
    r"^(yes|no|under|over|exactly|the field|no leader|tie|"
    r"united states|united kingdom|rest of world|europe|asia|"
    r"\d)",
    re.I,
)

_AREA_LABEL = "area:event-details"


# ---------------------------------------------------------------------------
# Name normalization (imported from the concept builder so the sentinel and the
# page share ONE definition of "same competitor" — a divergence would make the
# guard cry wolf on the very variants the page already bridges).
# ---------------------------------------------------------------------------
def _name_keys(name: str | None) -> set[str]:
    """The set of keys a competitor name is known by: exact-normalized,
    diacritic-stripped, and the ambiguity-guarded last|first-initial bridge.
    Two names refer to the same person when their key sets intersect."""
    from app.utils.event_concept import (
        _ascii_player_name,
        _last_first_initial_key,
        _norm_player_name,
    )

    keys: set[str] = set()
    n = _norm_player_name(name)
    if n:
        keys.add(f"n:{n}")
    a = _ascii_player_name(name)
    if a:
        keys.add(f"a:{a}")
    lfi = _last_first_initial_key(name)
    if lfi:
        keys.add(f"l:{lfi}")
    return keys


def _build_field_keys(competitors: list[dict]) -> set[str]:
    keys: set[str] = set()
    for c in competitors or []:
        keys |= _name_keys(c.get("name"))
    return keys


def _in_field(name: str | None, field_keys: set[str]) -> bool:
    return bool(_name_keys(name) & field_keys)


# ---------------------------------------------------------------------------
# Pure check functions (each returns a list of findings; a finding carries a
# ``verdict`` of REAL or EXPLAINED — only REAL files an issue).
# ---------------------------------------------------------------------------
def check_champion_hero(payload: dict) -> list[dict]:
    """A. The hero is the graded champion via a winner market."""
    primary = payload.get("primary") or {}
    kind = primary.get("kind")
    competitors = primary.get("competitors") or []
    out: list[dict] = []

    if kind not in _WINNER_KINDS:
        out.append(
            {
                "check": "champion_hero",
                "verdict": "REAL",
                "detail": f"settled hero is not a winner class (primary.kind=`{kind}`) — "
                "the champion must come from a winner market, not a prop/placement class.",
            }
        )
        return out  # nothing else is meaningful without a winner field

    winners = [c for c in competitors if c.get("won")]
    if len(winners) == 0:
        out.append(
            {
                "check": "champion_hero",
                "verdict": "REAL",
                "detail": "settled concept has NO champion (zero competitors with `won: true`) — "
                "the hero would render null on a concluded event.",
            }
        )
    elif len(winners) > 1:
        names = ", ".join(str(w.get("name")) for w in winners[:5])
        out.append(
            {
                "check": "champion_hero",
                "verdict": "REAL",
                "detail": f"settled concept has {len(winners)} champions (won:true): {names} — "
                "a single-winner field cannot have co-winners (the squash-class / "
                "out-of-domain contaminant, #225 Item 1).",
            }
        )
    else:
        # Exactly one winner — it must be the top-probability competitor. When it
        # is not, report the two facets DISTINCTLY (#229) so RED diagnoses itself:
        #   * wrong-crown (WORST): the field IS frozen (some competitor at ~100%)
        #     but the won:true flag sits on a different, lower-prob competitor — a
        #     genuinely mis-graded hero.
        #   * correct-crown-stale-probs: nobody is near 100% (the field is still a
        #     live/pre-settlement distribution); the crown is right but the settled
        #     freeze never ran, so the champion shows a re-polluted price below the
        #     live field (gotcha #33). The window between settle-in-reality and
        #     settle-in-DB, and the golf.py freeze that closes it.
        winner = winners[0]
        wprob = winner.get("probability") or 0.0
        top = max((c.get("probability") or 0.0) for c in competitors)
        if wprob + 1e-9 < top:
            leader = max(competitors, key=lambda c: c.get("probability") or 0.0)
            if top >= _FROZEN_WINNER_THRESHOLD:
                out.append(
                    {
                        "check": "champion_hero",
                        "verdict": "REAL",
                        "facet": "wrong-crown",
                        "detail": f"WRONG CROWN — the settled field is frozen to a champion "
                        f"(`{leader.get('name')}` at {top:.3f}) but the won:true flag sits on a "
                        f"different competitor `{winner.get('name')}` ({wprob:.3f}) — the champion "
                        "flag is on the wrong competitor (a mis-graded hero).",
                    }
                )
            else:
                out.append(
                    {
                        "check": "champion_hero",
                        "verdict": "REAL",
                        "facet": "correct-crown-stale-probs",
                        "detail": f"STALE PROBS — crowned champion `{winner.get('name')}` "
                        f"({wprob:.3f}) is graded but shows a stale price below the live field "
                        f"(top `{leader.get('name')}` at {top:.3f}); the settled winner field was "
                        "never frozen — polling is re-polluting current_probability on the "
                        "stuck-open winner market (gotcha #33). Expected: champion 1.0, field 0.0.",
                    }
                )
    return out


def check_field_membership(payload: dict) -> list[dict]:
    """B. Every round-leader / round-finish outcome is a member of the settled field."""
    primary = payload.get("primary") or {}
    field_keys = _build_field_keys(primary.get("competitors") or [])
    out: list[dict] = []
    if not field_keys:
        return out  # no field to check against (a separate defect, caught by check A)

    for child in payload.get("children") or []:
        mname = child.get("market_name") or child.get("name") or ""
        if not (_ROUND_LEADER_RE.search(mname) or _ROUND_FINISH_RE.search(mname)):
            continue
        strays: list[str] = []
        for o in child.get("outcomes") or []:
            oname = o.get("name")
            if not oname or _STRUCTURAL_OUTCOME_RE.match(str(oname).strip()):
                continue
            if not _in_field(oname, field_keys):
                strays.append(str(oname))
        if strays:
            out.append(
                {
                    "check": "field_membership",
                    "verdict": "REAL",
                    "market": mname,
                    "detail": f"`{mname}` shows {len(strays)} non-competitor(s) not in the settled "
                    f"field: {', '.join(strays[:6])}"
                    + (" …" if len(strays) > 6 else "")
                    + " — round/leader markets must respect field membership "
                    "(the out-of-field contamination class, #225 golf forensic).",
                }
            )
    return out


def check_evolution_resolves(payload: dict, chart: dict | None) -> list[dict]:
    """C. The winner-evolution chart resolves to exactly one ~100% line = the winner."""
    primary = payload.get("primary") or {}
    evo_id = primary.get("evolution_market_id")
    out: list[dict] = []

    if not evo_id:
        out.append(
            {
                "check": "evolution_resolves",
                "verdict": "REAL",
                "detail": "settled concept carries no `evolution_market_id` — the path-to-"
                "resolution chart has no series to draw.",
            }
        )
        return out

    if not chart or not chart.get("outcomes"):
        # Could not fetch the series — a WATCH (transient / endpoint), not a data defect.
        out.append(
            {
                "check": "evolution_resolves",
                "verdict": "EXPLAINED",
                "detail": f"evolution chart (market {evo_id}) returned no series this run — "
                "transient fetch/endpoint issue, re-checked next cadence.",
            }
        )
        return out

    # Latest real probability per outcome.
    latest: list[tuple[str, float]] = []
    for o in chart["outcomes"]:
        pts = [p.get("probability") for p in (o.get("history") or []) if p.get("probability") is not None]
        if pts:
            latest.append((o.get("name") or "?", float(pts[-1])))

    resolved = [(n, p) for n, p in latest if p >= RESOLVE_MIN]
    wall = [(n, p) for n, p in latest if p >= WALL_PROB]

    if len(resolved) == 0:
        top = max(latest, key=lambda t: t[1], default=("?", 0.0))
        out.append(
            {
                "check": "evolution_resolves",
                "verdict": "REAL",
                "detail": f"no evolution line resolves — the highest is `{top[0]}` at {top[1]:.3f} "
                f"(< {RESOLVE_MIN:.2f}). The winner line fizzled instead of reaching ~100% "
                "(#225 Item 3: odds_api-fizzle vs Kalshi-resolve).",
            }
        )
    elif len(wall) > WALL_MAX:
        names = ", ".join(f"{n} {p:.3f}" for n, p in sorted(wall, key=lambda t: -t[1])[:6])
        out.append(
            {
                "check": "evolution_resolves",
                "verdict": "REAL",
                "detail": f"0.99-wall: {len(wall)} evolution lines sit at >= {WALL_PROB:.2f} "
                f"({names}) — an overround artifact, not one clean winner line "
                "(the independent-binary GC-field overround class).",
            }
        )
    elif len(resolved) > 1:
        # More than one line reaches the resolve floor but not the wall — a soft
        # ambiguity (two near-certain lines). Flag as REAL: a single-winner
        # evolution should have exactly one resolving line.
        names = ", ".join(f"{n} {p:.3f}" for n, p in sorted(resolved, key=lambda t: -t[1])[:6])
        out.append(
            {
                "check": "evolution_resolves",
                "verdict": "REAL",
                "detail": f"{len(resolved)} evolution lines resolve above {RESOLVE_MIN:.2f} "
                f"({names}) — the path-to-resolution should converge on ONE winner.",
            }
        )
    return out


def check_round_resolution(payload: dict) -> list[dict]:
    """D. No single-winner round-leader market is double-graded."""
    out: list[dict] = []
    for child in payload.get("children") or []:
        mname = child.get("market_name") or child.get("name") or ""
        if not _ROUND_LEADER_RE.search(mname):
            continue  # only single-winner "Round N Leader"; Top-K finish is multi-winner
        highs = [
            (o.get("name"), o.get("probability"))
            for o in (child.get("outcomes") or [])
            if isinstance(o.get("probability"), (int, float)) and o["probability"] >= WALL_PROB
        ]
        if len(highs) >= 2:
            names = ", ".join(f"{n} {p:.3f}" for n, p in highs[:5])
            out.append(
                {
                    "check": "round_resolution",
                    "verdict": "REAL",
                    "market": mname,
                    "detail": f"`{mname}` is double-graded: {len(highs)} outcomes at >= {WALL_PROB:.2f} "
                    f"({names}) — a round can have only one leader.",
                }
            )
        # len(highs) == 0 is EXPLAINED (field-shaped round-prop grading is deferred,
        # #887 / L2-121 Item 3) — no finding.
    return out


_CHECK_LABELS = {
    "champion_hero": "Champion hero",
    "field_membership": "Field membership",
    "evolution_resolves": "Evolution chart resolves",
    "round_resolution": "Round resolution",
}


def run_all_checks(payload: dict, chart: dict | None) -> list[dict]:
    """Run all four checks against a settled concept payload. Pure — the caller
    supplies the (optionally fetched) evolution chart. Returns every finding
    (REAL and EXPLAINED); the caller files only REAL ones."""
    findings: list[dict] = []
    findings += check_champion_hero(payload)
    findings += check_field_membership(payload)
    findings += check_evolution_resolves(payload, chart)
    findings += check_round_resolution(payload)
    return findings


# ---------------------------------------------------------------------------
# Fingerprint + issue rendering (one issue per concept; re-observations comment)
# ---------------------------------------------------------------------------
def settled_fingerprint(concept_key: str) -> str:
    return hashlib.sha1(f"settled-concept:{concept_key}".encode("utf-8")).hexdigest()[:12]


def _update_green_streak(concept_key: str, is_green: bool) -> int:
    """Increment (GREEN) or reset (RED) a concept's consecutive-green counter in
    Redis and return the new value. Best-effort: a dead Redis returns 1 on green /
    0 on red so the run never fails on instrumentation, and the closer simply won't
    see a qualifying streak (fails safe toward NOT closing). #1177 close discipline."""
    key = f"bainluck:settled_concept_sentinel:green_streak:{settled_fingerprint(concept_key)}"
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        if not is_green:
            rc.setex(key, _GREEN_STREAK_TTL, 0)
            return 0
        new_val = rc.incr(key)
        rc.expire(key, _GREEN_STREAK_TTL)
        return int(new_val)
    except Exception as exc:  # noqa: BLE001 — instrumentation must never break a run
        logger.warning("Settled sentinel: green-streak update failed for %s: %s", concept_key, exc)
        return 1 if is_green else 0


def build_issue_title(concept_key: str, name: str, real: list[dict]) -> str:
    checks = ", ".join(sorted({_CHECK_LABELS.get(f["check"], f["check"]) for f in real}))
    title = f"[Settled Sentinel] {name} — settled contract broken: {checks}"
    return title[:256]


def build_issue_body(concept_key: str, name: str, real: list[dict], explained: list[dict]) -> str:
    fp = settled_fingerprint(concept_key)
    parts = [
        "## Settled-Concept Sentinel finding",
        "",
        f"`settled-concept-fingerprint:{fp}`  (dedupe key — do not remove)",
        "",
        f"**Concept:** {name}  ",
        f"**Key:** `{concept_key}`  ",
        f"**Checked against:** {SETTLED_SENTINEL_API}/api/event/{concept_key}  ",
        f"**REAL defects:** {len(real)}  ",
        "",
        "### REAL defects (settled contract broken)",
    ]
    for f in real:
        parts.append(f"- **{_CHECK_LABELS.get(f['check'], f['check'])}**: {f['detail']}")
    if explained:
        parts += ["", "### Explained (not filed — recorded for context)"]
        for f in explained[:10]:
            parts.append(f"- _{_CHECK_LABELS.get(f['check'], f['check'])}_: {f['detail']}")
    parts += [
        "",
        "### The settled contract (Alex, *settled means settled*)",
        "- Hero shows the champion (winner market, `won: true`, top probability).",
        "- Round/leader/finish markets show only real field members.",
        "- The evolution chart resolves to exactly one ~100% winner line.",
        "- Single-winner round markets are cleanly graded (never double-graded).",
        "",
        "---",
        "*Auto-filed by the Settled-Concept Sentinel (Queue #226) — the guard #225 "
        "earned. Read-only detection; it files work, never data (gotcha #21). "
        "Reproduce with `POST /api/admin/settled-concept-sentinel/run"
        "?inline=true&file_issues=false`.*",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Filing + dedup (reuses the bug_report_github rail, per the sentinel family)
# ---------------------------------------------------------------------------
def _find_open_issue_by_fingerprint(fingerprint: str) -> int | None:
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return None
    q = f'repo:{REPO} in:body "settled-concept-fingerprint:{fingerprint}" state:open'
    try:
        resp = httpx.get(
            "https://api.github.com/search/issues",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"q": q},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return items[0]["number"] if items else None
    except Exception as exc:
        logger.warning("Settled sentinel dedup search failed for %s: %s", fingerprint, exc)
        return None


def file_settled_issue(concept_key: str, name: str, real: list[dict], explained: list[dict]) -> dict:
    """File OR update one issue per concept fingerprint when REAL defects exist."""
    from app.tasks.bug_report_github import (
        GITHUB_TOKEN,
        add_to_project_board,
        comment_on_issue,
        create_github_issue,
    )

    fp = settled_fingerprint(concept_key)
    if not GITHUB_TOKEN:
        return {"concept_key": concept_key, "fingerprint": fp, "action": "skipped_no_token"}

    existing = _find_open_issue_by_fingerprint(fp)
    if existing:
        try:
            checks = ", ".join(sorted({_CHECK_LABELS.get(f["check"], f["check"]) for f in real}))
            comment_on_issue(
                existing,
                f"Settled Sentinel re-observed {len(real)} REAL defect(s) on **{name}** "
                f"(`{concept_key}`): {checks} (fingerprint `{fp}`). Still open.",
            )
        except Exception as exc:
            logger.warning("Settled sentinel comment failed on #%d: %s", existing, exc)
        return {"concept_key": concept_key, "fingerprint": fp, "action": "commented", "issue": existing}

    labels = ["alert-intake", "needs-agent", _AREA_LABEL, "priority:p1"]
    title = build_issue_title(concept_key, name, real)
    body = build_issue_body(concept_key, name, real, explained)
    try:
        number, node_id = create_github_issue(title, body, labels)
    except Exception as exc:
        logger.error("Settled sentinel issue creation failed (%s): %s", fp, exc)
        return {"concept_key": concept_key, "fingerprint": fp, "action": "error", "error": str(exc)[:200]}
    try:
        add_to_project_board(node_id)
    except Exception:
        logger.warning("Settled sentinel: add issue #%d to board failed (non-fatal)", number, exc_info=True)
    return {"concept_key": concept_key, "fingerprint": fp, "action": "filed", "issue": number}


# ---------------------------------------------------------------------------
# Target selection (calendar-driven) + live fetch
# ---------------------------------------------------------------------------
def _parse_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return datetime.strptime(v[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def recently_settled_targets(today: date, window_days: int = SETTLE_WINDOW_DAYS) -> list[dict]:
    """Calendar entries with a concept_key whose window ended within the last
    ``window_days`` — the concepts that just settled and must switch to settled
    language. Marquee/major only is not required (any adapter-backed concept is
    worth guarding), but marquee is carried through for severity context."""
    from app.utils.majors_calendar import load_calendar

    out: list[dict] = []
    for e in load_calendar():
        ck = e.get("concept_key")
        if not ck:
            continue
        end = _parse_date(e.get("end")) or _parse_date(e.get("start"))
        if end is None:
            continue
        days_since = (today - end).days
        if 0 <= days_since <= window_days:
            out.append(e)
    return out


async def _fetch_concept(client: httpx.AsyncClient, concept_key: str) -> dict | None:
    try:
        resp = await client.get(f"{SETTLED_SENTINEL_API}/api/event/{concept_key}")
    except Exception as exc:
        logger.info("Settled sentinel concept fetch failed for %s: %s", concept_key, exc)
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


async def _fetch_evolution_chart(
    client: httpx.AsyncClient, market_id: int, champion: str | None = None
) -> dict | None:
    try:
        params: dict[str, Any] = {"hours": 8760, "top_n": 8}
        # #232: odds_api winner-field markets never carry is_winner, so the freeze
        # can't resolve the line by grade. Pass the concept's authoritative crown
        # (won:true competitor) so /history resolves the champion's line by name —
        # the SAME resolution the product's WinnerEvolutionChart requests.
        if champion:
            params["champion"] = champion
        resp = await client.get(
            f"{SETTLED_SENTINEL_API}/api/futures/{market_id}/history",
            params=params,
        )
    except Exception as exc:
        logger.info("Settled sentinel chart fetch failed for market %s: %s", market_id, exc)
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
async def _run_settled_concept_sentinel(
    file_issues: bool = True,
    concept_keys: list[str] | None = None,
    deadline_seconds: float = 240.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Check every recently-settled marquee concept against the settled contract,
    file one deduped issue per concept with REAL defects, and cache a scorecard.

    ``concept_keys`` overrides calendar target selection (used for on-demand
    verification of a specific page, e.g. the Open acceptance run)."""
    start_mono = _time.monotonic()
    today = (now or datetime.now(timezone.utc)).date()

    if concept_keys:
        targets = [{"concept_key": k, "name": k, "marquee": None} for k in concept_keys]
    else:
        targets = recently_settled_targets(today)

    concept_results: list[dict] = []
    filed: list[dict] = []
    n_green = 0
    n_red = 0

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        for entry in targets:
            if _time.monotonic() - start_mono > deadline_seconds:
                logger.warning("Settled sentinel: deadline hit; %d targets unchecked", len(targets))
                break
            ck = entry.get("concept_key")
            name = entry.get("name") or ck
            payload = await _fetch_concept(client, ck)
            if payload is None:
                concept_results.append({"concept_key": ck, "name": name, "status": "unresolved",
                                        "note": "page did not resolve (no page / 404) — horizon sentinel's domain"})
                continue
            status = ((payload.get("event") or {}).get("status") or "").lower()
            if status != "settled":
                concept_results.append({"concept_key": ck, "name": name, "status": status or "unknown",
                                        "note": "not settled yet — settled contract not asserted"})
                continue

            primary = payload.get("primary") or {}
            evo_id = primary.get("evolution_market_id")
            # #232: the concept's authoritative crown (structural sole-survivor,
            # #228) — the ONLY champion signal for odds_api winner fields that
            # never grade is_winner. Exactly one won:true competitor, else None.
            crowned = [c for c in (primary.get("competitors") or []) if c.get("won")]
            champion = crowned[0].get("name") if len(crowned) == 1 else None
            chart = (
                await _fetch_evolution_chart(client, evo_id, champion=champion)
                if evo_id
                else None
            )

            findings = run_all_checks(payload, chart)
            real = [f for f in findings if f["verdict"] == "REAL"]
            explained = [f for f in findings if f["verdict"] == "EXPLAINED"]
            verdict = "RED" if real else "GREEN"
            if real:
                n_red += 1
            else:
                n_green += 1

            # #1177 close discipline: a concept's settled-contract issue may only be
            # closed after ≥2 CONSECUTIVE GREEN runs — the WC re-broke once because a
            # single green read (a lucky market-selection snapshot) was trusted. Track
            # the per-concept green streak in Redis (increment on GREEN, reset on RED)
            # and surface it so the closer can gate on green_streak >= GREEN_STREAK_TO_CLOSE.
            green_streak = _update_green_streak(ck, is_green=not real)

            result = {
                "concept_key": ck,
                "name": name,
                "status": "settled",
                "verdict": verdict,
                "n_real": len(real),
                "green_streak": green_streak,
                "closeable": (not real) and green_streak >= GREEN_STREAK_TO_CLOSE,
                "real": real,
                "explained": explained,
                "checks": {
                    lbl: ("RED" if any(f["check"] == key and f["verdict"] == "REAL" for f in findings) else "GREEN")
                    for key, lbl in _CHECK_LABELS.items()
                },
            }
            concept_results.append(result)

            if file_issues and real:
                filed.append(file_settled_issue(ck, name, real, explained))

    stats: dict[str, Any] = {
        "mode": "live" if file_issues else "detect_only",
        "api": SETTLED_SENTINEL_API,
        "as_of": today.isoformat(),
        "targets": len(targets),
        "checked_settled": n_green + n_red,
        "green": n_green,
        "red": n_red,
        "green_streak_to_close": GREEN_STREAK_TO_CLOSE,
        "closeable_concepts": [
            r["concept_key"] for r in concept_results if r.get("closeable")
        ],
        "concepts": concept_results,
        "filed": filed,
        "duration_s": round(_time.monotonic() - start_mono, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        import json as _json

        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(
            "bainluck:settled_concept_sentinel:last", 14 * 86400, _json.dumps(stats, default=str)
        )
    except Exception as exc:
        logger.warning("Settled sentinel: Redis cache write failed: %s", exc)

    return stats
