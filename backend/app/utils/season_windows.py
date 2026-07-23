"""Season windows — the single source of truth for "is this league in season?".

Queue #196 Item 3 (r197's ask): the sentinels (calibration, flow, grid) all file
freshness/volume/coverage alarms that are FALSE during an off-season or an
in-season break. A make-playoffs column with zero fill in July is not a bug for
the NBA (offseason) — it is the calendar. This module gives every filer one
break-aware seasonality check so RED means REAL and a seasonal quiet window is
annotated ("seasonal") instead of crying wolf.

Pure, dependency-free, and `now`-injectable for tests. Windows are approximate
month/day bands (UTC) — deliberately conservative at the edges so a genuinely
broken in-season feed is never silenced by a too-wide offseason band. This is a
suppression *hint* for alarm text, never a data mutation.

Phases:
  in_season   — regular season is being played
  postseason  — playoffs / championship series in progress
  break       — a mid-season pause (All-Star break) — schedules go quiet briefly
  offseason   — no games; futures are next-season and often illiquid
"""

from __future__ import annotations

from datetime import datetime, timezone

# A window is (start_month, start_day) .. (end_month, end_day), inclusive, and may
# wrap the new year (start after end, e.g. NBA regular season Oct→Apr).
_MD = tuple[int, int]


def _in_window(md: _MD, start: _MD, end: _MD) -> bool:
    """True when month/day ``md`` falls within [start, end], wrap-aware."""
    if start <= end:
        return start <= md <= end
    # Wrapping window (e.g. Oct..Apr): inside if after start OR before end.
    return md >= start or md <= end


# Per-league phase bands. Order matters: the FIRST matching band wins, so narrow
# break windows are listed before the broad regular-season band that contains
# them. Anything matching no band is offseason. Keyed by the grid league slug.
# Bands are intentionally slightly inside the true schedule edges.
_LEAGUE_BANDS: dict[str, list[tuple[str, _MD, _MD]]] = {
    "mlb": [
        ("break", (7, 14), (7, 17)),          # All-Star break (~mid-July)
        ("postseason", (10, 1), (11, 5)),     # playoffs + World Series
        ("in_season", (3, 20), (9, 30)),      # regular season
    ],
    "nba": [
        ("break", (2, 13), (2, 20)),          # All-Star break (~mid-Feb)
        ("postseason", (4, 16), (6, 25)),     # playoffs + Finals
        ("in_season", (10, 20), (4, 15)),     # regular season (wraps)
    ],
    "nhl": [
        ("break", (2, 1), (2, 6)),            # All-Star / bye (~early Feb)
        ("postseason", (4, 19), (6, 25)),     # playoffs + Stanley Cup
        ("in_season", (10, 4), (4, 18)),      # regular season (wraps)
    ],
    "nfl": [
        ("postseason", (1, 9), (2, 12)),      # playoffs + Super Bowl
        ("in_season", (9, 4), (1, 8)),        # regular season (wraps)
    ],
}

# Golf (and other continuous individual tours) have no clean season window; the
# grid sentinel judges golf illiquidity structurally instead of by the calendar.
_CONTINUOUS = {"golf", "tennis", "pga"}


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def league_phase(league: str, now: datetime | None = None) -> str:
    """Return the calendar phase for ``league``: in_season / postseason / break /
    offseason. Unknown or continuous leagues return ``"in_season"`` (never
    suppress — we only silence alarms we are confident are seasonal)."""
    slug = (league or "").strip().lower()
    if slug in _CONTINUOUS:
        return "in_season"
    bands = _LEAGUE_BANDS.get(slug)
    if not bands:
        return "in_season"
    dt = _now(now)
    md = (dt.month, dt.day)
    for phase, start, end in bands:
        if _in_window(md, start, end):
            return phase
    return "offseason"


def is_offseason(league: str, now: datetime | None = None) -> bool:
    return league_phase(league, now) == "offseason"


def is_break(league: str, now: datetime | None = None) -> bool:
    return league_phase(league, now) == "break"


def is_active(league: str, now: datetime | None = None) -> bool:
    """Games are being played (regular season or playoffs)."""
    return league_phase(league, now) in ("in_season", "postseason")


def is_quiet(league: str, now: datetime | None = None) -> bool:
    """The schedule is legitimately quiet (offseason or a mid-season break) — the
    window where freshness/volume/coverage alarms are expected to be false."""
    return league_phase(league, now) in ("offseason", "break")


# Human phase labels for a season descriptor (team-page truth: every number
# declares its season). Keyed by the phase() return value above.
_PHASE_LABELS: dict[str, str] = {
    "in_season": "Regular season",
    "postseason": "Playoffs",
    "break": "Regular season",   # a break is still within the regular season
    "offseason": "Offseason",
}

# Leagues whose season spans two calendar years and is labeled "YYYY-YY".
_WRAP_LEAGUES = {"nba", "nhl"}


def season_string(league: str, now: datetime | None = None) -> str | None:
    """Return the CURRENT (or, in the offseason, the upcoming) season's display
    string for ``league``. Wrap leagues (NBA/NHL) → "YYYY-YY"; calendar-year
    leagues (MLB/NFL) → "YYYY". None for unknown/continuous leagues.

    The season a team-page number belongs to is the season being *played now*, or
    — when the league is between seasons — the one about to start, because that is
    what the futures markets on the page are pricing.
    """
    slug = (league or "").strip().lower()
    dt = _now(now)
    month = dt.month
    if slug in _WRAP_LEAGUES:
        # Oct→June season. Sep+ starts this calendar year; Jan–Aug belongs to the
        # season that started last year, EXCEPT the Jul–Aug offseason which points
        # at the upcoming season (starts this year).
        base = dt.year if month >= 7 else dt.year - 1
        return f"{base}-{(base + 1) % 100:02d}"
    if slug == "mlb":
        # Calendar-year season (Mar–Oct). Nov–Dec offseason points at next year.
        return str(dt.year + 1) if month >= 11 else str(dt.year)
    if slug == "nfl":
        # Season labeled by its starting year (Sep–Jan). Jan–Feb is the prior
        # season's playoffs; Mar–Aug offseason points at the upcoming season.
        return str(dt.year) if month >= 3 else str(dt.year - 1)
    return None


def season_descriptor(league: str, now: datetime | None = None) -> dict:
    """The Season entity's first read shape: league × year × phase, plus a short
    human ``label`` ("2025-26 · Playoffs"). Every team-page number can attach this
    so the reader always knows WHICH season a probability describes. Unknown or
    continuous leagues return a descriptor with ``season=None`` and the phase from
    :func:`league_phase` (which is "in_season" for those, never suppressive)."""
    slug = (league or "").strip().lower()
    phase = league_phase(slug, now)
    season = season_string(slug, now)
    phase_label = _PHASE_LABELS.get(phase, "Regular season")
    if season:
        label = f"{season} · {phase_label}"
    else:
        label = phase_label
    return {
        "league": slug or None,
        "season": season,
        "phase": phase,
        "label": label,
    }


def seasonal_note(league: str, now: datetime | None = None) -> str | None:
    """A short human note explaining a quiet window, or None when the league is
    active (no seasonal excuse — an alarm here is REAL). Filers append this to a
    suppressed/annotated alarm so the reader sees WHY it was downgraded."""
    phase = league_phase(league, now)
    if phase == "offseason":
        return f"{(league or '').upper()} is in the offseason — quiet schedule is expected"
    if phase == "break":
        return f"{(league or '').upper()} is on an in-season break — quiet schedule is expected"
    return None
