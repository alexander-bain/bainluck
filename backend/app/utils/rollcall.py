"""The daily ground-truth roll call — pure core (C-ROLLCALL-BUILD-1).

Every day, an external truth source publishes a list of fixtures. For the
leagues Alex declared complete, the answer to *"is that fixture in our product,
exactly once, with every source we carry attached to it?"* is **yes by axiom** —
not by baseline. This module holds the axiom, the scoring, and the verdict; the
network reads and the durable writes live in ``app/tasks/rollcall.py``.

Three properties are deliberate and each one exists because of a specific way
this check has been got wrong before:

* **No baseline is cut from today.** ``C-ROLLCALL-PREP-1`` measured tonight's
  MLB slate at ``15 external, 0 matched_1, 15 dupes, 0/15 kalshi`` — a baseline
  taken from that state would have enshrined a total outage as normal. Axiom
  leagues are graded against 100%, full stop. Baselines exist only for the three
  genuinely partial domains below, and each one carries a written justification
  for why 100% is not the axiom there — no silent 100% cut.
* **Golf truth is Datagolf, not ESPN** (Alex golf ruling, 2026-08-26), and for
  golf the-odds-api is *measured*, not axiom: the prep probed
  ``sport_id IN ('golf_pga','golf_lpga')`` ±30d and found **0** betting rows
  (fingerprint ``7c5f83956fd010b4``). Odds API does not sell PGA/LPGA outrights,
  so demanding them would manufacture a permanent red.
* **An empty slate is not a finding** (gotcha #53). ``events_external == 0`` is
  an off-day, and off-days are silent. The alarm predicate is guarded on
  ``events_external > 0`` for exactly that reason, and a truth read that FAILED
  is a third state — never folded into "no fixtures".

Pure: dicts in, dicts out, no I/O, no clock branching (callers pass ``now``).
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

#: Payload contract version for the durable scorecard.
SCORECARD_SCHEMA = "rollcall/v1"

#: Redis key template — one key per day, 30-day TTL, so the measured-baseline
#: domains have a history to compute a sigma against without a second store.
REDIS_KEY_TEMPLATE = "bainluck:rollcall:{date}"
REDIS_TTL_SECONDS = 30 * 24 * 3600

#: Fingerprint marker used by the shared sentinel filing rail.
FINGERPRINT_MARKER = "rollcall-fingerprint"

#: The four sources a fan can see attached to a team-sport fixture.
ALL_SOURCES = ("kalshi", "polymarket", "espn", "odds_api")

#: Team-sport axiom sources: all four.
TEAM_AXIOM_SOURCES = ALL_SOURCES

#: Golf tour axiom sources: Kalshi + Polymarket only. See the justification.
GOLF_AXIOM_SOURCES = ("kalshi", "polymarket")

#: Verbatim from C-ROLLCALL-PREP-1. Written into every golf scorecard so the
#: exclusion travels with the number instead of living in a report nobody reads.
GOLF_ODDS_API_JUSTIFICATION = (
    "Odds API does not offer PGA/LPGA tour outrights — tour fields priced via "
    "Kalshi/Polymarket/Datagolf only"
)


@dataclass(frozen=True)
class AxiomLeague:
    """One league whose coverage is 100% BY AXIOM, not by measured baseline."""

    key: str
    #: ``sports.key`` values whose events can satisfy a fixture of this league.
    sport_keys: tuple[str, ...]
    #: Key handed to the truth client (an Odds-API-style key for ESPN's
    #: ``SPORT_LEAGUE_MAP``; the Datagolf tour name for golf).
    truth_key: str
    #: ``espn`` or ``datagolf``.
    truth: str
    axiom_sources: tuple[str, ...]
    #: Why a source is excluded from the axiom, when one is.
    exclusions: tuple[str, ...] = ()


AXIOM_LEAGUES: tuple[AxiomLeague, ...] = (
    AxiomLeague("mlb", ("baseball_mlb", "baseball_mlb_preseason"), "baseball_mlb",
                "espn", TEAM_AXIOM_SOURCES),
    AxiomLeague("nba", ("basketball_nba",), "basketball_nba", "espn", TEAM_AXIOM_SOURCES),
    AxiomLeague("nhl", ("icehockey_nhl",), "icehockey_nhl", "espn", TEAM_AXIOM_SOURCES),
    AxiomLeague("nfl", ("americanfootball_nfl",), "americanfootball_nfl", "espn",
                TEAM_AXIOM_SOURCES),
    AxiomLeague("wnba", ("basketball_wnba",), "basketball_wnba", "espn", TEAM_AXIOM_SOURCES),
    AxiomLeague("golf_pga", ("golf_pga", "golf_other"), "pga", "datagolf",
                GOLF_AXIOM_SOURCES, (GOLF_ODDS_API_JUSTIFICATION,)),
    AxiomLeague("golf_lpga", ("golf_lpga", "golf_other"), "lpga", "datagolf",
                GOLF_AXIOM_SOURCES, (GOLF_ODDS_API_JUSTIFICATION,)),
)

AXIOM_LEAGUE_KEYS = tuple(lg.key for lg in AXIOM_LEAGUES)


@dataclass(frozen=True)
class MeasuredDomain:
    """A genuinely partial domain: graded against its own trailing baseline.

    ``justification`` is mandatory and is written into the scorecard. A domain
    that cannot say in one line why 100% is not the axiom there does not belong
    in this list — it belongs in :data:`AXIOM_LEAGUES`.
    """

    key: str
    sport_keys: tuple[str, ...]
    justification: str


MEASURED_DOMAINS: tuple[MeasuredDomain, ...] = (
    MeasuredDomain(
        "golf_non_tour", ("golf_other",),
        "Event-based sport — no fixture exists until Datagolf publishes a field; "
        "field size varies and qualifying is not a Kalshi market",
    ),
    MeasuredDomain(
        "soccer_non_major", ("soccer_other",),
        "Hundreds of concurrent lower-league fixtures; Kalshi lists only EPL/UCL "
        "tier-1 and Polymarket only the top five leagues",
    ),
    MeasuredDomain(
        "tennis_qualifying", ("tennis_atp", "tennis_wta"),
        "ESPN lists ATP/WTA qualifying draws that carry no prediction market and "
        "no Odds line; main-draw market_tier=1 only",
    ),
)

#: A trailing baseline needs enough days to have a spread at all. Below this the
#: verdict is ``unmeasurable``, not ``pass`` — an absence of history is not
#: evidence of health (the schedule_adherence lesson, applied here).
MIN_BASELINE_DAYS = 5

#: Sigma multiple at which a measured domain's drop becomes an alarm.
BASELINE_SIGMA = 2.0

# ---------------------------------------------------------------------------
# Fixture identity
# ---------------------------------------------------------------------------

#: Tokens that identify a place rather than a club. Dropped before comparing, so
#: "New York Yankees" and "New York Mets" cannot match each other on "new york".
_PLACE_STOPWORDS = frozenset({
    "the", "fc", "sc", "afc", "cf", "club", "de", "st", "st.",
})


def _tokens(name: str) -> list[str]:
    cleaned = (name or "").lower().replace(".", " ").replace("-", " ")
    return [t for t in cleaned.split() if t and t not in _PLACE_STOPWORDS]


def team_nickname(name: str) -> str:
    """The discriminating token of a team name.

    ESPN and our rows disagree constantly about the city half ("LA Clippers" /
    "Los Angeles Clippers" / "Clippers") and never about the club half, so the
    club half is what identity is taken from. Returns ``""`` for an empty name,
    which never matches anything (see :func:`fixture_matches`).
    """
    toks = _tokens(name)
    return toks[-1] if toks else ""


def fixture_matches(
    our_home: str, our_away: str, truth_home: str, truth_away: str
) -> bool:
    """Does our (home, away) pair name the same fixture as truth's?

    Orientation-tolerant, because our home/away can be recorded swapped relative
    to the truth feed. Deliberately STRICTER than
    ``schedule_diff.teams_match``: that one takes any token overlap on both
    sides, which pairs "New York Yankees @ Boston Red Sox" with "New York Mets @
    Boston Red Sox". Here both sides must agree on the club token, so a
    same-city sibling is not a match.
    """
    ph, pa = team_nickname(our_home), team_nickname(our_away)
    th, ta = team_nickname(truth_home), team_nickname(truth_away)
    if not (ph and pa and th and ta):
        return False
    return (ph == th and pa == ta) or (ph == ta and pa == th)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass
class FixtureRow:
    """One truth fixture and everything we found for it.

    ``event_ids`` is every DB event that claims this fixture — the *count* is
    the duplicate signal. ``sources`` maps source name → linked (bool), and is
    only meaningful when exactly one event was found; with zero or two events
    the linkage question has no well-defined subject, so it reads all-False and
    the fixture is already red on its own count.
    """

    label: str
    kickoff: str | None = None
    event_ids: list[int] = field(default_factory=list)
    sources: dict[str, bool] = field(default_factory=dict)
    truth_ref: str | None = None
    #: Events that name this fixture, at this fixture's time, but carry a
    #: DIFFERENT provider id — so the id pass could not take them and the name
    #: pass must not. Recorded because "we never created this game" and "we
    #: created it and stamped it with the wrong id" are opposite defects with
    #: opposite repairs, and a bare ``missing`` says the first about both.
    id_conflicts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def matched_one(self) -> bool:
        return len(self.event_ids) == 1

    @property
    def mis_stamped(self) -> bool:
        return not self.event_ids and bool(self.id_conflicts)

    def missing_sources(self, axiom_sources: Sequence[str]) -> list[str]:
        if not self.matched_one:
            return list(axiom_sources)
        return [s for s in axiom_sources if not self.sources.get(s)]

    def is_clean(self, axiom_sources: Sequence[str]) -> bool:
        return self.matched_one and not self.missing_sources(axiom_sources)


def score_fixtures(
    fixtures: Iterable[FixtureRow], axiom_sources: Sequence[str]
) -> dict[str, Any]:
    """Reduce fixture rows to the frozen scorecard shape.

    ``{events_external, matched_1, dupes, missing, clean, per_source: {...}}``
    """
    rows = list(fixtures)
    per_source = {s: 0 for s in ALL_SOURCES}
    matched_1 = dupes = missing = clean = mis_stamped = 0
    for row in rows:
        n = len(row.event_ids)
        if n == 0:
            missing += 1
            if row.mis_stamped:
                mis_stamped += 1
        elif n == 1:
            matched_1 += 1
        else:
            dupes += 1
        if row.matched_one:
            for s in ALL_SOURCES:
                if row.sources.get(s):
                    per_source[s] += 1
        if row.is_clean(axiom_sources):
            clean += 1
    return {
        "events_external": len(rows),
        "matched_1": matched_1,
        "dupes": dupes,
        "missing": missing,
        #: A SUBSET of ``missing`` — the fixture has no event the roll call may
        #: claim, but a same-name same-time row exists under a foreign id.
        "mis_stamped": mis_stamped,
        "clean": clean,
        "per_source": per_source,
    }


def axiom_offenders(
    fixtures: Iterable[FixtureRow], axiom_sources: Sequence[str]
) -> list[dict[str, Any]]:
    """Every fixture that breaks the axiom, named. No silent aggregation."""
    out: list[dict[str, Any]] = []
    for row in fixtures:
        gaps: list[str] = []
        if len(row.event_ids) == 0:
            # Two different defects, two different repairs. `mis_stamped` says
            # the game exists and its provider id is wrong; `missing` says it
            # was never created. Collapsing them sends the wrong fix.
            gaps.append("mis_stamped" if row.mis_stamped else "missing")
        elif len(row.event_ids) > 1:
            gaps.append(f"dupes={len(row.event_ids)}")
        gaps.extend(f"{s}=0" for s in row.missing_sources(axiom_sources))
        if not gaps:
            continue
        out.append({
            "fixture": row.label,
            "kickoff": row.kickoff,
            "event_ids": list(row.event_ids),
            "gaps": gaps,
            "truth_ref": row.truth_ref,
            "id_conflicts": list(row.id_conflicts),
        })
    return out


def axiom_is_red(scorecard: dict[str, Any], axiom_sources: Sequence[str]) -> bool:
    """The alarm predicate for an axiom league.

    Guarded on ``events_external > 0``: an off-day publishes no fixtures and is
    not a finding. Above zero the whole matrix must hold — exactly one event per
    fixture AND every axiom source linked on every fixture. The frozen
    acceptance writes the source clause as ``per_source.kalshi <
    events_external``; the expectation matrix above it requires all four, and
    the matrix is what is implemented, so a Polymarket-shaped outage cannot pass
    a Kalshi-shaped gate.
    """
    total = scorecard.get("events_external", 0)
    if total <= 0:
        return False
    if scorecard.get("matched_1") != total:
        return True
    if scorecard.get("dupes") or scorecard.get("missing"):
        return True
    per_source = scorecard.get("per_source") or {}
    return any(per_source.get(s, 0) < total for s in axiom_sources)


def baseline_verdict(
    history: Sequence[float], today: float | None
) -> tuple[str, dict[str, Any]]:
    """Grade a measured domain against its own trailing history.

    Returns ``(verdict, evidence)`` where verdict is ``pass`` / ``drop`` /
    ``unmeasurable``. ``unmeasurable`` is a first-class answer: fewer than
    :data:`MIN_BASELINE_DAYS` of history, or a zero-variance history, cannot
    support a 2σ claim, and inventing one would be the crying-wolf failure the
    grid health score was retired for.
    """
    samples = [float(h) for h in history if h is not None]
    if today is None:
        return "unmeasurable", {"reason": "no reading today", "n": len(samples)}
    if len(samples) < MIN_BASELINE_DAYS:
        return "unmeasurable", {
            "reason": f"{len(samples)} days of history, need {MIN_BASELINE_DAYS}",
            "n": len(samples),
        }
    mean = statistics.fmean(samples)
    sigma = statistics.pstdev(samples)
    if sigma == 0:
        # A flat history is real information, but 2σ of nothing is not a test.
        # Fall back to an exact-drop check so a flat 100% that falls still speaks.
        return ("drop" if today < mean else "pass"), {
            "mean": round(mean, 4), "sigma": 0.0, "today": round(today, 4),
            "rule": "flat history — any drop below the mean",
            "n": len(samples),
        }
    floor = mean - BASELINE_SIGMA * sigma
    return ("drop" if today < floor else "pass"), {
        "mean": round(mean, 4),
        "sigma": round(sigma, 4),
        "floor": round(floor, 4),
        "today": round(today, 4),
        "n": len(samples),
    }


def coverage_percent(scorecards: Iterable[dict[str, Any]]) -> float | None:
    """The lane needle: % of today's axiom fixtures that are fully clean.

    Clean means exactly one DB event AND every axiom source linked. Returns
    ``None`` when there were no axiom fixtures at all — a league-wide off-day
    publishes no number rather than a flattering 100%.
    """
    total = clean = 0
    for card in scorecards:
        total += int(card.get("events_external", 0) or 0)
        clean += int(card.get("clean", 0) or 0)
    if total == 0:
        return None
    return round(100.0 * clean / total, 2)


# ---------------------------------------------------------------------------
# Filing
# ---------------------------------------------------------------------------


def rollcall_fingerprint(league: str, offenders: Sequence[dict[str, Any]]) -> str:
    """Stable dedup key: same league + same SHAPE of breakage == same issue.

    Keyed on the sorted set of gap kinds, not on the fixture list, so a nightly
    slate of different games with the identical defect files once instead of
    once a night forever.
    """
    kinds = sorted({g.split("=")[0] for o in offenders for g in o.get("gaps", [])})
    payload = f"rollcall|{league}|{','.join(kinds)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def build_rollcall_issue_title(league: str, scorecard: dict[str, Any]) -> str:
    total = scorecard.get("events_external", 0)
    return (
        f"[rollcall] {league.upper()}: {total - scorecard.get('clean', 0)}/{total} "
        f"fixtures fail the coverage axiom"
    )


def build_rollcall_issue_body(
    league: str,
    date: str,
    scorecard: dict[str, Any],
    offenders: Sequence[dict[str, Any]],
    truth_url: str,
    axiom_sources: Sequence[str],
    exclusions: Sequence[str] = (),
    max_named: int = 25,
) -> str:
    fp = rollcall_fingerprint(league, offenders)
    ps = scorecard.get("per_source") or {}
    lines = [
        f"`{FINGERPRINT_MARKER}:{fp}`  (dedupe key — one issue per league per "
        f"breakage shape)",
        "",
        f"**{league.upper()} roll call, {date}** — coverage for this league is "
        f"100% BY AXIOM (Alex, 2026-08-26). Any gap below is a defect, not a "
        f"feature gap.",
        "",
        "| metric | value |",
        "|---|---|",
        f"| fixtures published by truth | {scorecard.get('events_external')} |",
        f"| exactly one DB event | {scorecard.get('matched_1')} |",
        f"| duplicated | {scorecard.get('dupes')} |",
        f"| no claimable event | {scorecard.get('missing')} |",
        f"| …of which exist under a WRONG provider id | {scorecard.get('mis_stamped', 0)} |",
        f"| fully clean (1 event + all axiom sources) | {scorecard.get('clean')} |",
        "",
        "| source | linked | axiom |",
        "|---|---|---|",
    ]
    for s in ALL_SOURCES:
        mark = "yes" if s in axiom_sources else "measured"
        lines.append(f"| {s} | {ps.get(s, 0)}/{scorecard.get('events_external')} | {mark} |")
    for note in exclusions:
        lines += ["", f"> {note}"]
    lines += ["", f"**Truth source:** {truth_url}", "", "### Offending fixtures", ""]
    for o in offenders[:max_named]:
        ids = "/".join(str(i) for i in o.get("event_ids") or []) or "none"
        lines.append(
            f"- `{o.get('fixture')}` {o.get('kickoff') or ''} → DB ids {ids} "
            f"({', '.join(o.get('gaps', []))})"
        )
        for c in o.get("id_conflicts") or []:
            lines.append(
                f"    - event `{c.get('event_id')}` names this fixture at this "
                f"time but is stamped `{c.get('espn_id')}`, truth says "
                f"`{o.get('truth_ref')}`"
            )
    if len(offenders) > max_named:
        lines.append(f"- …and {len(offenders) - max_named} more (full list in the scorecard)")
    lines += [
        "",
        "### Reproduce",
        "",
        "```",
        f"GET /api/admin/rollcall?date={date}",
        "```",
        "",
        "```json",
        'POST /api/admin/db-query',
        '{"sql": "SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time, '
        "e.espn_id FROM events e JOIN sports s ON s.id = e.sport_id WHERE s.key = "
        "'<sport_key>' AND e.commence_time BETWEEN '<day>T00:00Z' AND '<day>T23:59Z' "
        'ORDER BY e.commence_time"}',
        "```",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def rollcall_terminal(
    leagues_graded: int,
    leagues_expected: int,
    truth_failures: int,
    mirror_written: bool,
) -> str:
    """``complete`` / ``partial`` / ``failed`` for ``ENFORCED_TASKS``.

    A run that could not read truth for some league did NOT observe those
    fixtures, and saying ``complete`` would be the exact false-GREEN this
    enrolment exists to stop — a silent truth outage would read as a clean
    slate forever. Same for a scorecard that never reached its durable mirror:
    the check ran, the artifact operators read did not appear.
    """
    if leagues_graded == 0:
        return "failed"
    if truth_failures or leagues_graded < leagues_expected or not mirror_written:
        return "partial"
    return "complete"
