"""Schedule Sentinel — the completeness check (#1796, Queue 342).

    Every check we have verifies that what exists renders. Nothing verifies
    that what should exist, exists.

The Flow Sentinel, the Grid Sentinel, the Calibration Sentinel, the data-quality
watchdog and the L1–L4 matching audits are, without exception, *predicates over
rows we already hold*. L1 asks "does every game we know about have its sources";
it cannot ask "is every game that happened a game we know about". **A row that was
never created is invisible to all of them, and an absence has no field to be
wrong.** It stayed invisible until Alex personally looked for a Red Sox game and
could not find it (#1779, rage-shake #146).

A completeness check needs a denominator we do not own. That is the entire
design: this sentinel fetches an AUTHORITATIVE external schedule and reconciles
our ``events`` against it, rather than reconciling our rows against each other.

Four defect classes (#1796):

  * ``MISSING``          — in truth, not in ours. The class with no prior detector.
  * ``EXTRA``/``DUPLICATE`` — ours, not in truth. Two of our rows paired to one real
    game is a DUPLICATE; a row that pairs to no real game at all is EXTRA. The
    issue framed this as "duplicate"; the wider EXTRA framing is the honest one
    (measured 2026-08-13), so both are supported and the scorecard says which fired.
  * ``MISATTACHED``      — the row exists but ``home_team_id``/``away_team_id``
    points at a different club. **This check DEREFERENCES the FK and compares the
    club it resolves to.** The #1779 rows had *correct names and wrong ids*, which
    is precisely the comparison a names-only check survives; every misattachment
    finding therefore records ``names_agree`` so the report can state, per row,
    that a name check would have passed it.
  * ``SCORE_DISAGREEMENT`` — a settled game whose score is not the real score. Two
    sub-shapes: a plain mismatch, and the #1779 fingerprint — our score is
    *another real game's* score, folded on by the ±28h absorption. When the
    absorbed-from game is identifiable in the window it is named inline.

Plus two state classes that ride the same pairing: ``stale_state`` (truth is Final,
we are still ``live``/``scheduled`` well past the start) and ``premature_settle``
(we settled a game the authority still has live/scheduled — the #1193/#1201 rot).

**A verdict, not a score.** The Grid Sentinel's mlb-66 lesson applies directly: a
raw health score that cries wolf gets ignored. Every finding is classified REAL /
EXPLAINED / WATCH before anything alarms, so **RED means REAL**, and only REAL
files. Postponements, rain-outs and doubleheader re-schedules are the common
EXPLAINED class and are expected to be frequent.

**Coverage is stated, never assumed.** A league with no truth adapter is
``not_covered`` and says so; the scorecard reports "N of M leagues have a truth
source" rather than an unqualified percentage. Silently scoring an uncovered
league GREEN is the exact failure mode that produced #1796.

**Gotcha #53 is load-bearing here.** An empty 200 from a schedule API is a response
*shape*, not an absence: "the schedule API returned nothing" and "there were no
games" must not collapse into the same conclusion. Both truth adapters therefore
return a typed :class:`TruthResult` whose ``ok`` says the source ANSWERED — a
zero-game day is ``ok=True, games=[]`` only when the payload structurally declares
it, and a fetch fault is ``ok=False`` which makes the day UNVERIFIED, never green.
(This is also why the adapters do not route through
``MLBAPIService.get_todays_games`` / ``ESPNAPIService.get_scoreboard``: both swallow
their exceptions and return a bare ``[]``, which is the collapse this sentinel
exists to refuse.)

Read-only against production and the DB. It files work, never data (gotcha #21).

Modeled on ``app/tasks/grid_sentinel.py``: same finding constructor, same artifact
registry, same verdict discipline, same ``sentinel_filing`` dedupe rail, same
admin endpoint pair, same durable-snapshot persistence. The value here is that it
behaves exactly like its siblings, not that it is clever.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time as _time
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime, time as _dtime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from app.utils import season_windows

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (Redis-tunable, no-deploy — mirrors the flow/grid sentinels)
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = 25.0
STATSAPI_BASE = os.environ.get("STATSAPI_BASE", "https://statsapi.mlb.com")
ESPN_SCOREBOARD_BASE = os.environ.get(
    "ESPN_SCOREBOARD_BASE", "https://site.api.espn.com/apis/site/v2/sports"
)

# Rolling window: yesterday / today / tomorrow, in the league's own calendar.
WINDOW_DAYS_BACK = 1
WINDOW_DAYS_FORWARD = 1

# Pairing bars. Two stages so a consecutive-day series (same matchup, 24h apart)
# can never cross-pair while the confident pairs exist.
MATCH_BAR = 0.60          # schedule:sentinel_match_bar — per-side name similarity
STRICT_PAIR_HOURS = 12.0  # stage 1: a confident pair
LOOSE_PAIR_HOURS = 30.0   # stage 2 (leftovers only): a mis-dated row, reported as such

# A settled truth game we still show as live/scheduled is stale only after this.
STALE_STATE_HOURS = 6.0   # schedule:sentinel_stale_state_hours

# Evidence caps so an issue body stays readable.
MAX_FINDINGS_IN_BODY = 40

# Our terminal statuses.
_OUR_SETTLED = {"completed", "closed", "final", "resolved"}
_OUR_ACTIVE = {"scheduled", "live", "in_progress"}


# ---------------------------------------------------------------------------
# League registry — the coverage contract.
#
# ``truth=None`` means NOT COVERED, and the sentinel SAYS SO rather than scoring
# the league green. ``partial_by_design`` marks leagues whose event population is
# deliberately a subset of the authority's (we do not, and do not intend to,
# carry all ~360 D1 basketball programs); a MISSING there is a WATCH, never a
# filed REAL defect, because filing it would be the cry-wolf this sentinel is
# built to avoid.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LeagueSpec:
    slug: str
    sport_keys: tuple[str, ...]
    truth: Optional[str]                 # "mlb_statsapi" | "espn" | None
    espn_path: Optional[tuple[str, str]] = None   # (sport, league) for ESPN
    tz: str = "America/New_York"         # the calendar the authority's "day" uses
    partial_by_design: bool = False
    season_key: Optional[str] = None     # season_windows slug (defaults to slug)
    uncovered_reason: Optional[str] = None


SCHEDULE_LEAGUES: tuple[LeagueSpec, ...] = (
    # --- covered -----------------------------------------------------------
    LeagueSpec("mlb", ("baseball_mlb", "baseball_mlb_preseason"), "mlb_statsapi"),
    LeagueSpec("nfl", ("americanfootball_nfl",), "espn", ("football", "nfl")),
    LeagueSpec("nba", ("basketball_nba",), "espn", ("basketball", "nba")),
    LeagueSpec("nhl", ("icehockey_nhl",), "espn", ("hockey", "nhl")),
    LeagueSpec("wnba", ("basketball_wnba",), "espn", ("basketball", "wnba"),
               season_key="wnba"),
    LeagueSpec("mls", ("soccer_usa_mls",), "espn", ("soccer", "usa.1")),
    LeagueSpec("epl", ("soccer_epl",), "espn", ("soccer", "eng.1"), tz="Europe/London"),
    LeagueSpec("ucl", ("soccer_uefa_champs_league",), "espn",
               ("soccer", "uefa.champions"), tz="Europe/London"),
    LeagueSpec("ncaaf", ("americanfootball_ncaaf",), "espn",
               ("football", "college-football"), partial_by_design=True),
    LeagueSpec("ncaab", ("basketball_ncaab",), "espn",
               ("basketball", "mens-college-basketball"), partial_by_design=True),
    # --- declared NOT COVERED ----------------------------------------------
    LeagueSpec("npb", ("baseball_npb",), None, tz="Asia/Tokyo",
               uncovered_reason="no free authoritative NPB schedule adapter"),
    LeagueSpec("kbo", ("baseball_kbo",), None, tz="Asia/Seoul",
               uncovered_reason="no free authoritative KBO schedule adapter"),
    LeagueSpec("milb", ("baseball_milb",), None,
               uncovered_reason="MiLB schedule adapter not built (statsapi sportId "
                                "varies per level)"),
    LeagueSpec("pga", ("golf_pga",), None,
               uncovered_reason="field event — no per-game schedule to reconcile"),
    LeagueSpec("ufc", ("mma_ufc", "mma_mixed_martial_arts"), None,
               uncovered_reason="card/bout structure — not a two-team game schedule"),
    LeagueSpec("atp", ("tennis_atp", "tennis_wta"), None,
               uncovered_reason="draw-based; ESPN tennis scoreboard is not a "
                                "head-to-head game list"),
)


def _load_overrides() -> None:
    """Redis-tunable thresholds, no-deploy (mirrors the grid sentinel)."""
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        for key, name, cast in (
            ("schedule:sentinel_match_bar", "MATCH_BAR", float),
            ("schedule:sentinel_stale_state_hours", "STALE_STATE_HOURS", float),
        ):
            v = r.get(key)
            if v is not None:
                globals()[name] = cast(v.decode() if isinstance(v, bytes) else v)
    except Exception as exc:
        logger.info("Schedule sentinel overrides not loaded (using defaults): %s", exc)


# ---------------------------------------------------------------------------
# Name normalization + similarity (pure, unit-tested)
# ---------------------------------------------------------------------------
_TEAM_STOPWORDS = {"the", "fc", "sc", "cf", "afc", "club", "de"}


def _norm_name(s: Optional[str]) -> str:
    """Lowercase, strip punctuation to spaces, collapse whitespace.

    Punctuation becomes a SPACE rather than being deleted so ``"St.Louis
    Cardinals"`` and ``"St. Louis Cardinals"`` normalize identically — a real
    divergence between our stored name and statsapi's."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _name_tokens(s: Optional[str]) -> frozenset:
    return frozenset(t for t in _norm_name(s).split() if t not in _TEAM_STOPWORDS)


def name_similarity(a: Optional[str], b: Optional[str]) -> float:
    """0.0–1.0 similarity between two club names. Pure.

    Deliberately stricter than plain token OVERLAP, which the existing
    ``schedule_diff.teams_match`` uses: overlap alone makes "Chicago Cubs" match
    "Chicago White Sox" (shared token ``chicago``) and "New York Mets" match "New
    York Yankees", which would silently pair the wrong game and hide a MISSING.

      * identical normalized strings           → 1.0
      * one token set contains the other       → 0.85  ("Red Sox" ⊂ "Boston Red Sox")
      * otherwise                              → Jaccard  (Cubs/White Sox → 0.25)
    """
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return 0.0
    if ta <= tb or tb <= ta:
        return 0.85
    inter = ta & tb
    if not inter:
        return 0.0
    return len(inter) / len(ta | tb)


# ---------------------------------------------------------------------------
# Truth model — a typed result so an empty 200 is never read as an absence.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TruthGame:
    key: str
    home: str
    away: str
    start: Optional[datetime]        # tz-aware UTC
    state: str                       # final | live | scheduled | postponed | unknown
    raw_state: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    doubleheader: bool = False
    game_number: int = 1

    @property
    def label(self) -> str:
        dh = f" (DH game {self.game_number})" if self.doubleheader else ""
        when = self.start.strftime("%Y-%m-%d %H:%MZ") if self.start else "?"
        return f"{self.away} @ {self.home}{dh} [{when}]"


@dataclass
class TruthResult:
    """Gotcha #53: ``ok`` means the source ANSWERED authoritatively. An empty
    ``games`` with ``ok=True`` is a real off-day; ``ok=False`` is "I could not
    look", and a day that could not be looked at is UNVERIFIED, never green."""

    ok: bool
    games: list[TruthGame] = field(default_factory=list)
    source: Optional[str] = None
    error: Optional[str] = None
    empty_authoritative: bool = False

    @property
    def zero_yield(self) -> bool:
        """Loud zero: the source answered and reported no games at all."""
        return self.ok and not self.games


_MLB_FINAL = {"Final", "Game Over", "Completed Early"}
_MLB_LIVE = {"In Progress", "Manager Challenge", "Instant Replay"}
_MLB_SCHEDULED = {"Scheduled", "Pre-Game", "Warmup", "Delayed Start", "Delayed"}
_MLB_POSTPONED = {"Postponed", "Suspended", "Cancelled", "Canceled"}


def _mlb_state(detailed: str) -> str:
    if detailed in _MLB_FINAL:
        return "final"
    if detailed in _MLB_LIVE:
        return "live"
    if detailed in _MLB_POSTPONED:
        return "postponed"
    if detailed in _MLB_SCHEDULED:
        return "scheduled"
    return "unknown"


def parse_statsapi_payload(payload: Any) -> TruthResult:
    """Pure parse of a statsapi ``/api/v1/schedule`` body into a TruthResult.

    The structural declaration of "authoritatively empty" is the presence of the
    ``dates`` key (statsapi always emits it, with ``totalGames``). A body without
    it is malformed → ``ok=False`` → the day is UNVERIFIED. This is the whole
    gotcha-#53 disambiguation, kept pure so it is testable without a network."""
    if not isinstance(payload, dict) or "dates" not in payload:
        return TruthResult(ok=False, source="mlb_statsapi",
                           error="statsapi body has no 'dates' key (malformed)")
    games: list[TruthGame] = []
    for date_entry in payload.get("dates") or []:
        for raw in (date_entry or {}).get("games") or []:
            try:
                teams = raw.get("teams") or {}
                home_side = teams.get("home") or {}
                away_side = teams.get("away") or {}
                start_raw = raw.get("gameDate")
                start = (
                    datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
                    if start_raw else None
                )
                detailed = ((raw.get("status") or {}).get("detailedState")) or ""
                try:
                    gnum = int(raw.get("gameNumber", 1) or 1)
                except (TypeError, ValueError):
                    gnum = 1
                games.append(TruthGame(
                    key=str(raw.get("gamePk") or ""),
                    home=(home_side.get("team") or {}).get("name") or "",
                    away=(away_side.get("team") or {}).get("name") or "",
                    start=start,
                    state=_mlb_state(detailed),
                    raw_state=detailed,
                    home_score=home_side.get("score"),
                    away_score=away_side.get("score"),
                    doubleheader=(raw.get("doubleHeader") or "N") not in ("N", ""),
                    game_number=gnum,
                ))
            except Exception as exc:  # gotcha #42 — one bad game never voids the day
                logger.warning("statsapi game parse failed: %s", exc)
    return TruthResult(ok=True, games=games, source="mlb_statsapi",
                       empty_authoritative=not games)


_ESPN_FINAL = {"STATUS_FINAL", "STATUS_FULL_TIME", "STATUS_FINAL_PEN"}
_ESPN_LIVE = {"STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_END_PERIOD",
              "STATUS_FIRST_HALF", "STATUS_SECOND_HALF", "STATUS_RAIN_DELAY"}
_ESPN_SCHEDULED = {"STATUS_SCHEDULED", "STATUS_PRE", "STATUS_DELAYED"}
_ESPN_POSTPONED = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED",
                   "STATUS_SUSPENDED", "STATUS_ABANDONED"}


def _espn_state(name: str) -> str:
    if name in _ESPN_FINAL:
        return "final"
    if name in _ESPN_LIVE:
        return "live"
    if name in _ESPN_POSTPONED:
        return "postponed"
    if name in _ESPN_SCHEDULED:
        return "scheduled"
    return "unknown"


def parse_espn_payload(payload: Any) -> TruthResult:
    """Pure parse of an ESPN scoreboard body into a TruthResult.

    ESPN structurally declares an empty slate with an ``events`` key present and
    empty (it still emits ``leagues``). A body carrying neither key is malformed →
    ``ok=False``. Same gotcha-#53 discipline as statsapi."""
    if not isinstance(payload, dict) or (
        "events" not in payload and "leagues" not in payload
    ):
        return TruthResult(ok=False, source="espn",
                           error="ESPN body has neither 'events' nor 'leagues' (malformed)")
    games: list[TruthGame] = []
    for ev in payload.get("events") or []:
        try:
            comps = (ev.get("competitions") or [{}])[0] or {}
            status_name = (
                ((comps.get("status") or ev.get("status") or {}).get("type") or {})
                .get("name") or ""
            )
            home = away = ""
            hs = aws = None
            for c in comps.get("competitors") or []:
                team = c.get("team") or {}
                nm = team.get("displayName") or team.get("name") or ""
                raw_score = c.get("score")
                try:
                    sc = int(raw_score) if raw_score not in (None, "") else None
                except (TypeError, ValueError):
                    sc = None
                if c.get("homeAway") == "home":
                    home, hs = nm, sc
                else:
                    away, aws = nm, sc
            start_raw = ev.get("date") or comps.get("date")
            start = (
                datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
                if start_raw else None
            )
            games.append(TruthGame(
                key=str(ev.get("id") or ""),
                home=home, away=away, start=start,
                state=_espn_state(status_name), raw_state=status_name,
                home_score=hs, away_score=aws,
            ))
        except Exception as exc:  # gotcha #42
            logger.warning("ESPN event parse failed: %s", exc)
    return TruthResult(ok=True, games=games, source="espn",
                       empty_authoritative=not games)


async def fetch_truth(client: httpx.AsyncClient, spec: LeagueSpec,
                      day: _date) -> TruthResult:
    """Fetch one league-day of authoritative schedule.

    Deliberately does NOT route through ``MLBAPIService.get_todays_games`` or
    ``ESPNAPIService.get_scoreboard``: both swallow their exceptions and return a
    bare ``[]``, which makes "the API fell over" indistinguishable from "there
    were no games" — the exact collapse gotcha #53 names."""
    if spec.truth == "mlb_statsapi":
        url = f"{STATSAPI_BASE}/api/v1/schedule"
        params = {"sportId": 1, "date": day.isoformat()}
        parse = parse_statsapi_payload
        source = "mlb_statsapi"
    elif spec.truth == "espn" and spec.espn_path:
        sport, league = spec.espn_path
        url = f"{ESPN_SCOREBOARD_BASE}/{sport}/{league}/scoreboard"
        params = {"dates": day.strftime("%Y%m%d")}
        parse = parse_espn_payload
        source = "espn"
    else:
        return TruthResult(ok=False, source=None,
                           error=f"no truth adapter for league '{spec.slug}'")
    try:
        resp = await client.get(url, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        return TruthResult(ok=False, source=source,
                           error=f"{source} fetch failed for {day}: {str(exc)[:140]}")
    result = parse(body)
    if result.zero_yield:
        # Gotcha #53: make the zero-yield case LOUD. "It returned" is not "it worked".
        logger.info("Schedule sentinel: %s reported ZERO games for %s on %s "
                    "(authoritative empty, not a fetch fault)", source, spec.slug, day)
    return result


# ---------------------------------------------------------------------------
# Our side
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OurEvent:
    id: int
    home_name: str
    away_name: str
    home_team_id: Optional[int]
    away_team_id: Optional[int]
    home_fk_name: Optional[str]     # DEREFERENCED FK — the misattachment probe
    away_fk_name: Optional[str]
    status: str
    home_score: Optional[int]
    away_score: Optional[int]
    commence_time: Optional[datetime]
    # The schedule providers' own game ids (ruling 042, Codex C-SEN-1). Before
    # these existed the model could not EXPRESS identity, so pairing had nothing
    # to reach for and reached for names — see ``pair_events``.
    espn_id: Optional[str] = None
    statpal_fixture_id: Optional[str] = None
    external_id: Optional[str] = None

    @property
    def individuated(self) -> bool:
        """True when SOME schedule provider has named this specific game.

        Deliberately provider-agnostic, exactly as the event registry's
        ``_individuating_provider_ids`` is: which provider spoke does not matter
        for this question, only that the row is not an anonymous name-and-time
        shell. An id-less row is the population Codex's specimen lives in and the
        one no name comparison can ever verify.
        """
        return bool(self.espn_id or self.statpal_fixture_id or self.external_id)

    @property
    def label(self) -> str:
        when = (self.commence_time.strftime("%Y-%m-%d %H:%MZ")
                if self.commence_time else "?")
        return f"event {self.id} — {self.away_name} @ {self.home_name} [{when}] ({self.status})"


# Which of OUR id columns lives in the same id space as a truth source's
# ``TruthGame.key``, so the two can actually be compared.
#
# ESPN's scoreboard ``event.id`` is precisely what we store in ``Event.espn_id``,
# so an ESPN-truth league can be paired on identity outright. MLB StatsAPI's key
# is a ``gamePk``, which we hold on no event column — ``mlb_sync`` writes it into
# a ``win_prob_snapshots.game_state`` blob for LIVE games only. That is a real
# limit and it is reported as one (``paired_by_names_foreign_id_space``) rather
# than papered over: a pair we could not verify by id is not the same thing as a
# pair we verified, and it is not the same thing as a defect either.
_TRUTH_ID_ATTR: dict[str, str] = {"espn": "espn_id"}


def _finding(check: str, severity: str, detail: str, *,
             kind: str, seasonal_ok: bool = False, tier: str = "completeness",
             **extra: Any) -> dict:
    """Finding constructor. ``kind`` is the #1796 defect class; ``real`` is decided
    later by the artifact registry (mirrors the grid sentinel's shape)."""
    return {"check": check, "severity": severity, "detail": detail, "kind": kind,
            "seasonal_ok": seasonal_ok, "tier": tier, **extra}


# ---------------------------------------------------------------------------
# Pairing — two stages so a consecutive-day series can never cross-pair.
# ---------------------------------------------------------------------------
def _pair_score(o: OurEvent, t: TruthGame) -> tuple[float, str]:
    """Best (similarity, orientation) for one candidate pair. Pure."""
    aligned = min(name_similarity(o.home_name, t.home),
                  name_similarity(o.away_name, t.away))
    swapped = min(name_similarity(o.home_name, t.away),
                  name_similarity(o.away_name, t.home))
    if aligned >= swapped:
        return aligned, "aligned"
    return swapped, "swapped"


def _hours_apart(o: OurEvent, t: TruthGame) -> Optional[float]:
    if o.commence_time is None or t.start is None:
        return None
    return abs((o.commence_time - t.start).total_seconds()) / 3600.0


def pair_events(truth: list[TruthGame], ours: list[OurEvent],
                truth_id_attr: Optional[str] = None) -> dict:
    """One-to-one pairing of truth games against our events. Pure.

    **Stage 0 — IDENTITY (ruling 042, Codex C-SEN-1).** When the truth source's
    ``key`` lives in an id space we store (``truth_id_attr`` names our column),
    exact id equality pairs first and its pairs are CONSUMED before any name is
    compared. This is not a tiebreak on top of the name score, and the ordering is
    the whole fix: a name-and-time pass ranks a doubleheader's two games by the
    clock, so a row whose id says "game 2" but whose stored start is nearer game 1
    pairs backwards, silently, with a high name score. The id cannot be outvoted
    by how close two clocks happen to be.

    Stage 1 then takes only confident NAME pairs (both names above the bar AND
    within ``STRICT_PAIR_HOURS``). Stage 2 re-runs over the leftovers with
    ``LOOSE_PAIR_HOURS`` and flags each pair it makes as mis-dated. Splitting those
    two stages is what stops a three-game series (same matchup on consecutive days)
    from cross-pairing: the exact-time pairs are consumed before the loose pass
    ever runs.

    Every pair records ``paired_by`` — ``"id"`` or ``"names"``. A caller that acts
    on a pair is entitled to know whether the pairing was dereferenced or inferred,
    and per ruling 042 that fact travels ON the pair rather than in a comment here.

    Returns ``{pairs, unmatched_truth, unmatched_ours, near_miss_ours,
    duplicate_ids}`` where a near-miss is one of our events that WOULD have paired
    to an already-taken truth game — the DUPLICATE signal, as distinct from a
    genuine EXTRA — and ``duplicate_ids`` is the set of values stage 0 REFUSED to
    pair on because more than one of our rows asserted them.

    ``duplicate_ids`` is returned rather than re-derived by the caller (Codex
    C-SEN-2 specimen 2). Stage 0 is the only place that knows an id was refused;
    when that fact stayed local, the refused rows fell through into name pairing
    and the caller — seeing an id it could not account for — labelled the truth
    source's OWN namespace "foreign" and reported green."""
    taken_t: set[int] = set()
    taken_o: set[int] = set()
    pairs: list[dict] = []
    duplicate_ids: set[str] = set()

    # --- Stage 0: identity. ------------------------------------------------
    if truth_id_attr:
        by_our_id: dict[str, int] = {}
        for oi, o in enumerate(ours):
            try:
                val = getattr(o, truth_id_attr, None)
            except Exception:  # gotcha #42
                continue
            if val:
                # A duplicated id is not an identity; refuse to pair on it rather
                # than pick one arbitrarily. Those rows fall through to the name
                # stages — but the REFUSAL travels out with them (``duplicate_ids``)
                # so the caller can report the contradiction instead of inferring
                # innocence from the absence of an id pair.
                if str(val) in by_our_id:
                    by_our_id[str(val)] = -1
                    duplicate_ids.add(str(val))
                else:
                    by_our_id[str(val)] = oi
        for ti, t in enumerate(truth):
            try:
                oi = by_our_id.get(str(t.key or ""))
                if t.key in (None, "") or oi is None or oi < 0 or oi in taken_o:
                    continue
                o = ours[oi]
                score, orient = _pair_score(o, t)
            except Exception as exc:  # gotcha #42
                logger.warning("schedule sentinel id pairing failed: %s", exc)
                continue
            taken_t.add(ti)
            taken_o.add(oi)
            pairs.append({"truth": t, "ours": o, "score": score,
                          "orientation": orient, "hours_apart": _hours_apart(o, t),
                          # Deliberately NOT mis_dated: an id-paired row whose clock
                          # disagrees is a WRONG_DATE finding on a CORRECTLY paired
                          # row, not a pairing compromise, so it must not be
                          # relabelled as one.
                          #
                          # C-SEN-2 specimen 3: this comment used to end "...which
                          # _check_pair already raises", and _check_pair did not —
                          # it gated the date finding on ``mis_dated``, which is
                          # False here by construction. The date check was therefore
                          # disabled for exactly the pairs we trust most, and an
                          # exact ESPN id 24h off the official start reported green.
                          # ``_check_pair`` now raises it off ``paired_by == "id"``.
                          "mis_dated": False, "paired_by": "id"})

    def _run(bound: float, mis_dated: bool) -> None:
        cands = []
        for ti, t in enumerate(truth):
            if ti in taken_t:
                continue
            for oi, o in enumerate(ours):
                if oi in taken_o:
                    continue
                try:  # gotcha #42 — one poison row never voids the whole pass
                    score, orient = _pair_score(o, t)
                    if score < MATCH_BAR:
                        continue
                    dt = _hours_apart(o, t)
                    if dt is not None and dt > bound:
                        continue
                except Exception as exc:
                    logger.warning("schedule sentinel pair scoring failed: %s", exc)
                    continue
                cands.append((score, -(dt if dt is not None else bound), ti, oi, orient, dt))
        for score, _negdt, ti, oi, orient, dt in sorted(cands, key=lambda c: (-c[0], -c[1])):
            if ti in taken_t or oi in taken_o:
                continue
            taken_t.add(ti)
            taken_o.add(oi)
            pairs.append({"truth": truth[ti], "ours": ours[oi], "score": score,
                          "orientation": orient, "hours_apart": dt,
                          "mis_dated": mis_dated, "paired_by": "names"})

    _run(STRICT_PAIR_HOURS, False)
    _run(LOOSE_PAIR_HOURS, True)

    unmatched_truth = [t for i, t in enumerate(truth) if i not in taken_t]
    unmatched_ours = [o for i, o in enumerate(ours) if i not in taken_o]

    # Which leftovers are DUPLICATES (they match a truth game that is already
    # paired) rather than EXTRAS (they match no real game at all)?
    near_miss: dict[int, TruthGame] = {}
    for o in unmatched_ours:
        try:  # gotcha #42
            best: tuple[float, Optional[TruthGame]] = (0.0, None)
            for t in truth:
                score, _ = _pair_score(o, t)
                dt = _hours_apart(o, t)
                if (score >= MATCH_BAR and (dt is None or dt <= LOOSE_PAIR_HOURS)
                        and score > best[0]):
                    best = (score, t)
            if best[1] is not None:
                near_miss[o.id] = best[1]
        except Exception as exc:
            logger.warning("schedule sentinel near-miss scan failed: %s", exc)

    return {"pairs": pairs, "unmatched_truth": unmatched_truth,
            "unmatched_ours": unmatched_ours, "near_miss_ours": near_miss,
            "duplicate_ids": duplicate_ids}


# ---------------------------------------------------------------------------
# The four defect classes (pure — this is the reconcile)
# ---------------------------------------------------------------------------
def _scores_match(o: OurEvent, t: TruthGame, orientation: str) -> bool:
    if orientation == "swapped":
        return (o.home_score, o.away_score) == (t.away_score, t.home_score)
    return (o.home_score, o.away_score) == (t.home_score, t.away_score)


def _absorbed_from(o: OurEvent, truth: list[TruthGame],
                   paired: TruthGame) -> Optional[TruthGame]:
    """The #1779 fingerprint: our score is ANOTHER real game's score.

    A plain wrong score is a grading bug; a score that exactly equals a different
    real game's score is the ±28h absorption folding one game's state onto
    another's row. Naming the source game turns "wrong number" into a diagnosis."""
    if o.home_score is None or o.away_score is None:
        return None
    for t in truth:
        if t is paired or t.key == paired.key:
            continue
        if t.home_score is None or t.away_score is None:
            continue
        if (t.home_score, t.away_score) == (o.home_score, o.away_score):
            return t
    return None


def reconcile(truth: list[TruthGame], ours: list[OurEvent], spec: LeagueSpec,
              now: Optional[datetime] = None) -> tuple[list[dict], dict]:
    """Reconcile one league's window. Pure — dicts in, findings out.

    Returns ``(findings, stats)``. Every loop body is individually guarded
    (gotcha #42): one poison game can never void the rest of the reconcile."""
    now = now or datetime.now(timezone.utc)
    out: list[dict] = []
    truth_id_attr = _TRUTH_ID_ATTR.get(spec.truth or "")
    paired = pair_events(truth, ours, truth_id_attr)
    L = spec.slug.upper()

    # --- Which pairs did we actually VERIFY? (ruling 042, Codex C-SEN-1/C-SEN-2) -
    # A pair made on names and a clock is a claim about the name-matcher. FIVE
    # outcomes now, because C-SEN-2 showed the original three collapsed two very
    # different things into "individuated, not a finding":
    #
    #   id                        — dereferenced, verified;
    #   names, SAME id space, id duplicated across our rows
    #                             — two of our rows assert one official game id.
    #                               Provable without inference, so REAL;
    #   names, SAME id space, id disagrees with the pair
    #                             — our row carries the truth source's own id space
    #                               and it names a different game. Not provably a
    #                               defect, but certainly not verified;
    #   names, FOREIGN id space   — the truth source's key lives in a space we hold
    #                               on no column (MLB's gamePk), or this row has no
    #                               value in the comparable column. We could not
    #                               cross-reference. Counted here and declared ONCE
    #                               for the league below — deliberately not once per
    #                               pair, because for MLB that would be a constant,
    #                               and a constant is not a signal;
    #   names, row un-individuated — nothing has ever named this game. The pairing
    #                               cannot be verified even in principle.
    #
    # A doubleheader paired by name is always unverified regardless of
    # individuation — the provider's own game_number says two games share this
    # matchup and this day, so no clock reading disambiguates them.
    paired_by_id = 0
    foreign_id_space = 0
    duplicate_ids = paired.get("duplicate_ids") or set()
    for p in paired["pairs"]:
        try:
            if p.get("paired_by") == "id":
                paired_by_id += 1
                continue
            t, o = p["truth"], p["ours"]
            ambiguous_dh = t.doubleheader

            # Does this row carry a value in the SAME id space as the truth key?
            our_same_space_id = None
            if truth_id_attr:
                try:
                    v = getattr(o, truth_id_attr, None)
                except Exception:  # gotcha #42
                    v = None
                our_same_space_id = str(v) if v else None

            if our_same_space_id is not None:
                # It is NOT foreign — it is the authority's own namespace, and the
                # pairing did not come from it. Codex C-SEN-2: counting these as
                # `foreign_id_space` is the mislabel that produced the green.
                if our_same_space_id in duplicate_ids:
                    out.append(_finding(
                        "schedule_duplicate_identity", "critical",
                        f"{L} {o.label} asserts {truth_id_attr}="
                        f"{our_same_space_id!r}, and so does another of our rows in "
                        f"this window — two rows claim to be the one official game "
                        f"{t.label}. A shared provider id is evidence of identity, "
                        f"never proof of it (#1947), so this is either a duplicate "
                        f"row or a mis-stamped id; both are defects",
                        kind="DUPLICATE", event_id=o.id, truth_key=t.key,
                        duplicated_id=our_same_space_id, id_space=truth_id_attr,
                    ))
                    continue
                if our_same_space_id != str(t.key or ""):
                    out.append(_finding(
                        "schedule_identity_conflict", "info",
                        f"{L} {o.label} was paired to the official {t.label} on "
                        f"NAMES, but it carries {truth_id_attr}="
                        f"{our_same_space_id!r} — an identifier in the authority's "
                        f"OWN id space naming a different game. The pairing "
                        f"contradicts a dereferenceable identity and cannot be "
                        f"reported as checked",
                        kind="UNVERIFIED", tier="provenance", event_id=o.id,
                        truth_key=t.key, paired_by="names",
                        our_id=our_same_space_id, id_space=truth_id_attr,
                    ))
                    continue

            if o.individuated and not ambiguous_dh:
                foreign_id_space += 1
                continue
            out.append(_finding(
                "schedule_unverified_pairing", "info",
                f"{L} {o.label} was paired to the official {t.label} on NAMES and a "
                f"clock, not on an identifier"
                + (" — the authority reports a DOUBLEHEADER on this matchup and day, "
                   "so two official games share these names and no start time "
                   "separates them"
                   if ambiguous_dh else
                   " — no schedule provider has ever named this row (no espn_id, "
                   "statpal_fixture_id or external_id), so the pairing cannot be "
                   "verified and this row cannot be reported as checked"),
                kind="UNVERIFIED", tier="provenance", event_id=o.id,
                truth_key=t.key, paired_by="names",
                our_row_individuated=o.individuated,
                truth_is_doubleheader=t.doubleheader,
                truth_game_number=t.game_number,
            ))
        except Exception as exc:  # gotcha #42
            logger.warning("schedule sentinel pairing provenance failed (%s): %s",
                           L, exc)

    # --- The league-level identity-coverage declaration (Codex C-SEN-2 #1) ----
    # ONE statement, not one per pair. The distinction matters in both directions
    # and each direction has a named failure behind it:
    #
    #   * N findings would make the state CONSTANT for MLB — every pair, every
    #     night, forever. The committed suite was right to refuse that, and its
    #     `test_an_individuated_row_in_a_foreign_id_space_is_not_flagged` is what
    #     kept it out. A constant is not a signal.
    #   * ZERO findings, which is what we had, meant a league where NOTHING was
    #     dereferenced reported the same `green` as a league where EVERYTHING was.
    #     That is the false green C-SEN-2 blocked on, and it is the more dangerous
    #     error: this is the only detector we have for an ABSENT GAME, so a green
    #     it did not earn is worse than no sentinel at all.
    #
    # So: one declaration, carrying the COUNT. The count is what moves when the
    # anchor channel (#1946) starts storing gamePk and this league becomes
    # verifiable — at which point this finding stops firing on its own.
    if foreign_id_space:
        out.append(_finding(
            "schedule_identity_space_unavailable", "info",
            f"{L}: {foreign_id_space} of {len(paired['pairs'])} pairings could not "
            f"be dereferenced — the authority's key lives in "
            f"{truth_id_attr or (spec.truth or 'none') + ' (not stored)'}, which is "
            f"not an id space we hold on the event row. These pairings rest on "
            f"names and a clock, so this league has been COMPARED, not checked",
            kind="UNVERIFIED", tier="provenance",
            pairings_not_dereferenced=foreign_id_space,
            pairings_total=len(paired["pairs"]),
            truth_id_space=truth_id_attr or f"{spec.truth or 'none'} (not stored)",
        ))

    # --- MISSING: in truth, not in ours. The class with no prior detector. -----
    for t in paired["unmatched_truth"]:
        try:
            postponed = t.state == "postponed"
            dh_reschedule = t.doubleheader and t.game_number > 1 and t.state != "final"
            out.append(_finding(
                "schedule_missing", "critical" if t.state == "final" else "warning",
                f"{L} {t.label} is on the official schedule ({t.raw_state or t.state}) "
                f"but we hold NO event for it",
                kind="MISSING",
                seasonal_ok=postponed or dh_reschedule,
                explain_hint=("postponed/cancelled by the authority" if postponed
                              else "doubleheader re-schedule not yet ingested"
                              if dh_reschedule else None),
                partial_by_design=spec.partial_by_design,
                truth_key=t.key, truth_state=t.raw_state or t.state,
            ))
        except Exception as exc:
            logger.warning("schedule sentinel MISSING classify failed (%s): %s", L, exc)

    # --- EXTRA / DUPLICATE: ours, not in truth. --------------------------------
    for o in paired["unmatched_ours"]:
        try:
            dup_of = paired["near_miss_ours"].get(o.id)
            settled_with_score = (
                (o.status or "").lower() in _OUR_SETTLED
                and o.home_score is not None and o.away_score is not None
            )
            if dup_of is not None:
                out.append(_finding(
                    "schedule_duplicate", "critical",
                    f"{L} {o.label} is a SECOND row for the single official game "
                    f"{dup_of.label} — the authority has one game, we have two",
                    kind="DUPLICATE", event_id=o.id, truth_key=dup_of.key,
                ))
            else:
                out.append(_finding(
                    "schedule_extra",
                    "critical" if settled_with_score else "info",
                    f"{L} {o.label} matches NO game on the official schedule"
                    + (f" — and it is settled with a published score "
                       f"{o.away_score}-{o.home_score}, so we are showing a result "
                       f"for a game the authority says never happened"
                       if settled_with_score else ""),
                    kind="EXTRA", event_id=o.id,
                    settled_with_score=settled_with_score,
                ))
        except Exception as exc:
            logger.warning("schedule sentinel EXTRA classify failed (%s): %s", L, exc)

    # --- Matched pairs: MISATTACHED, SCORE, state, orientation, date. ----------
    for p in paired["pairs"]:
        try:
            out.extend(_check_pair(p, truth, spec, now))
        except Exception as exc:
            logger.warning("schedule sentinel pair check failed (%s): %s", L, exc)

    stats = {
        "truth_games": len(truth),
        "our_events": len(ours),
        "paired": len(paired["pairs"]),
        "unmatched_truth": len(paired["unmatched_truth"]),
        "unmatched_ours": len(paired["unmatched_ours"]),
        # Ruling 042 obligation 1: a count of a population states, in the OUTPUT,
        # how much of it was chosen by identifier and how much by label.
        "paired_by_id": paired_by_id,
        "paired_by_names_foreign_id_space": foreign_id_space,
        "paired_unverified": sum(
            1 for f in out if f["check"] == "schedule_unverified_pairing"
        ),
        "truth_id_space": truth_id_attr or f"{spec.truth or 'none'} (not stored)",
    }
    return out, stats


def _check_pair(p: dict, truth: list[TruthGame], spec: LeagueSpec,
                now: datetime) -> list[dict]:
    """All per-pair checks for one matched (truth, ours) pair. Pure."""
    t: TruthGame = p["truth"]
    o: OurEvent = p["ours"]
    L = spec.slug.upper()
    out: list[dict] = []

    # --- MISATTACHED — DEREFERENCE the FK. -----------------------------------
    # #1779's rows had CORRECT NAMES and WRONG IDS. Comparing `home_team_name`
    # against the authority is exactly the comparison those rows survive, so this
    # check compares the club the FK RESOLVES TO, and records `names_agree` to
    # state, per finding, that a names-only check would have passed it.
    sides = (
        ("home", o.home_team_id, o.home_fk_name, o.home_name,
         t.home if p["orientation"] == "aligned" else t.away),
        ("away", o.away_team_id, o.away_fk_name, o.away_name,
         t.away if p["orientation"] == "aligned" else t.home),
    )
    for side, fk_id, fk_name, declared, official in sides:
        if fk_id is None:
            out.append(_finding(
                "schedule_team_unlinked", "info",
                f"{L} event {o.id} {side} team is UNLINKED (team_id NULL) for "
                f"{official!r}",
                kind="MISATTACHED", tier="linkage", event_id=o.id, side=side,
            ))
            continue
        if name_similarity(fk_name, official) < MATCH_BAR:
            names_agree = name_similarity(declared, official) >= MATCH_BAR
            out.append(_finding(
                "schedule_misattached", "critical",
                f"{L} event {o.id} {side}_team_id={fk_id} dereferences to "
                f"{fk_name!r}, but the official {side} club is {official!r}"
                + (f" — the row's own {side}_team_name is {declared!r}, which is "
                   f"CORRECT, so a name-only check passes this row"
                   if names_agree else f" (row name: {declared!r})"),
                kind="MISATTACHED", event_id=o.id, side=side, team_id=fk_id,
                fk_name=fk_name, official=official, names_agree=names_agree,
            ))

    # --- Home/away orientation --------------------------------------------
    if p["orientation"] == "swapped":
        out.append(_finding(
            "schedule_home_away_swapped", "critical",
            f"{L} event {o.id} has home/away REVERSED against the official "
            f"{t.label}",
            kind="MISATTACHED", event_id=o.id,
        ))

    # --- Mis-dated (stage-2 pair) ------------------------------------------
    if p.get("mis_dated"):
        out.append(_finding(
            "schedule_wrong_date", "warning",
            f"{L} event {o.id} sits {p['hours_apart']:.1f}h from the official "
            f"start of {t.label} — the row exists but is on the wrong date",
            kind="MISSING", event_id=o.id, hours_apart=p["hours_apart"],
            paired_by=p.get("paired_by", "names"),
        ))
    # --- Mis-dated (IDENTITY pair) — Codex C-SEN-2 specimen 3 ----------------
    # An id pair is never marked `mis_dated` (that flag means "the pairing itself
    # was a compromise", and an identity pair is not one). The date finding was
    # gated on that flag, so it could not fire for id pairs at all: an exact ESPN
    # id sitting 24h off the official start produced ZERO findings and a literal
    # green. That is the strongest evidence case there is — the id PROVES the two
    # rows are the same game, so the clock disagreement is not ambiguity to be
    # weighed, it is a wrong date to be reported.
    #
    # The bound is STRICT_PAIR_HOURS, the same bar a confident NAME pair must
    # clear, so the two stages cannot disagree about what "the right day" means.
    # Below it, a provider start-time revision is routine and is not a defect.
    elif (p.get("paired_by") == "id"
          and p.get("hours_apart") is not None
          and p["hours_apart"] > STRICT_PAIR_HOURS):
        out.append(_finding(
            "schedule_wrong_date", "warning",
            f"{L} event {o.id} sits {p['hours_apart']:.1f}h from the official "
            f"start of {t.label} — and the two are the SAME GAME by identifier, "
            f"so this is a wrong date on a correctly-paired row, not a pairing "
            f"ambiguity",
            kind="MISSING", event_id=o.id, hours_apart=p["hours_apart"],
            paired_by="id", truth_key=t.key,
        ))

    # --- SCORE DISAGREEMENT on a settled game ------------------------------
    ours_status = (o.status or "").lower()
    if (t.state == "final" and t.home_score is not None and t.away_score is not None
            and o.home_score is not None and o.away_score is not None
            and not _scores_match(o, t, p["orientation"])):
        absorbed = _absorbed_from(o, truth, t)
        extra_detail = ""
        if absorbed is not None:
            extra_detail = (
                f" — and that is EXACTLY the score of {absorbed.label}, i.e. another "
                f"game's state folded onto this row (the #1779 ±28h absorption)"
            )
        out.append(_finding(
            "schedule_score_disagreement", "critical",
            f"{L} event {o.id} shows {o.away_score}-{o.home_score} for {t.label}, "
            f"but the authority's final is {t.away_score}-{t.home_score}"
            + extra_detail,
            kind="SCORE_DISAGREEMENT", event_id=o.id, truth_key=t.key,
            absorbed_from=absorbed.label if absorbed else None,
        ))

    # --- State divergence ---------------------------------------------------
    age_h = ((now - t.start).total_seconds() / 3600.0) if t.start else None
    if (t.state == "final" and ours_status in _OUR_ACTIVE
            and age_h is not None and age_h > STALE_STATE_HOURS):
        out.append(_finding(
            "schedule_stale_state", "critical",
            f"{L} event {o.id} is still {ours_status!r} {age_h:.0f}h after "
            f"{t.label} went Final",
            kind="SCORE_DISAGREEMENT", event_id=o.id,
        ))
    elif t.state in ("live", "scheduled") and ours_status in _OUR_SETTLED:
        out.append(_finding(
            "schedule_premature_settle", "critical",
            f"{L} event {o.id} is settled ({ours_status}) but the authority has "
            f"{t.label} as {t.raw_state or t.state} — premature settle "
            f"(#1201 / gotcha #32)",
            kind="SCORE_DISAGREEMENT", event_id=o.id,
        ))
    elif t.state == "postponed" and ours_status not in _OUR_SETTLED:
        out.append(_finding(
            "schedule_postponed", "info",
            f"{L} event {o.id} is {ours_status!r} but the authority has "
            f"{t.label} as {t.raw_state} — postponement not reflected",
            kind="SCORE_DISAGREEMENT", seasonal_ok=True, event_id=o.id,
            explain_hint="postponed/cancelled by the authority",
        ))

    return out


# ---------------------------------------------------------------------------
# Artifact registry — REAL vs EXPLAINED vs WATCH. This is what makes RED mean REAL.
# ---------------------------------------------------------------------------
def classify_findings(findings: list[dict], spec: LeagueSpec,
                      now: Optional[datetime] = None) -> dict:
    """Split findings into real / explained / watch.

      * ``explained`` — a postponement, a cancellation, a doubleheader re-schedule,
        or a quiet-window artifact. #1796 names these explicitly: they will be
        frequent and they are NOT defects.
      * ``watch``     — surfaced, never filed: an unlinked (NULL) team FK, a
        low-signal EXTRA row, and every MISSING in a league whose coverage is
        partial BY DESIGN (we do not carry all of college football; filing that
        daily is the cry-wolf this sentinel exists to avoid).
      * ``real``      — everything else. Only these file.
    """
    season_slug = spec.season_key or spec.slug
    phase = season_windows.league_phase(season_slug, now)
    quiet = phase in ("offseason", "break")
    note = season_windows.seasonal_note(season_slug, now)
    real, explained, watch, unverified = [], [], [], []
    for f in findings:
        try:
            if f.get("kind") == "UNVERIFIED":
                # Its own bucket, and deliberately neither `real` nor `watch`.
                # `real` would make an absent identifier a defect (it is not — it
                # is an absent measurement), and `watch` is ignored by the verdict,
                # which is the exact laundering Codex C-SEN-1 blocked on.
                unverified.append(f)
            elif f.get("explain_hint"):
                explained.append({**f, "explained_by": f["explain_hint"]})
            elif f.get("seasonal_ok") and quiet:
                explained.append({**f, "explained_by": note or f"{spec.slug} {phase}"})
            elif f.get("tier") == "linkage":
                watch.append({**f, "note": "team FK not yet linked — not a misattachment"})
            elif f.get("kind") == "MISSING" and f.get("partial_by_design"):
                watch.append({**f, "note": "coverage is partial BY DESIGN for this "
                                           "league — surfaced, never filed"})
            elif f.get("kind") == "EXTRA" and not f.get("settled_with_score"):
                watch.append({**f, "note": "extra row carries no published result"})
            else:
                real.append(f)
        except Exception as exc:  # gotcha #42
            logger.warning("schedule sentinel classify failed: %s", exc)
            real.append(f)
    return {"league": spec.slug, "phase": phase, "real": real,
            "explained": explained, "watch": watch, "unverified": unverified}


GREEN_UNVERIFIED = "green_unverified"
NOT_COVERED = "not_covered"


def schedule_verdict(classified: dict, *, covered: bool,
                     days_unverified: list[str] | None = None) -> str:
    """RED iff a REAL defect survives; NOT_COVERED when the league has no truth
    source; GREEN_UNVERIFIED when a day's truth read failed; else GREEN.

    A league with no denominator is NEVER green — that is #1796's whole complaint
    about the existing rails, and repeating it here would be the same bug wearing
    a new hat. Likewise a day whose authority could not be read has not been
    checked, and an unchecked day may not borrow GREEN's authority (the
    LAT-P017 lesson the Grid Sentinel already paid for).

    A pairing we could not dereference is the same shape of claim and gets the same
    answer (Codex C-SEN-1). If an event was matched to official truth on names and
    a clock alone, this league has not been *checked* — it has been compared. RED
    still outranks it: an unverified pairing must never launder a MISSING game."""
    if not covered:
        return NOT_COVERED
    if classified["real"]:
        return "red"
    if days_unverified or classified.get("unverified"):
        return GREEN_UNVERIFIED
    return "green"


# ---------------------------------------------------------------------------
# Fingerprint + filing (shared sentinel_filing rail — never hand-rolled)
# ---------------------------------------------------------------------------
_SCHEDULE_MARKER = "schedule-sentinel-fingerprint"


def schedule_fingerprint(league: str) -> str:
    """ONE deduped issue per league — deliberately NOT per day.

    #1796 asks for "one deduped issue per league per day … so a persistent hole
    does not file daily". A date in the fingerprint would file a fresh issue every
    morning for the same standing hole, which is the opposite of dedupe. The
    fingerprint is therefore stable per league: the first RED day files, every
    later RED day comments, and the first clean day closes."""
    return hashlib.sha1(f"schedule:{league}".encode("utf-8")).hexdigest()[:12]


def severity_for_schedule(real: list[dict]) -> str:
    return "P1" if any(f["severity"] == "critical" for f in real) else "P2"


def build_schedule_issue_title(league: str, real: list[dict], window: str) -> str:
    by_kind: dict[str, int] = {}
    for f in real:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
    parts = ", ".join(f"{v} {k}" for k, v in sorted(by_kind.items()))
    return (f"[Schedule Sentinel] {league.upper()} schedule has {len(real)} real "
            f"defect(s) over {window} ({parts})")[:256]


def _schedule_title_prefix(league: str) -> str:
    return f"[Schedule Sentinel] {league.upper()} schedule has "


def build_schedule_issue_body(result: dict) -> str:
    classified = result["classified"]
    league = classified["league"]
    fp = schedule_fingerprint(league)
    real, explained, watch = (classified["real"], classified["explained"],
                              classified.get("watch") or [])
    unverified = classified.get("unverified") or []
    cov = result.get("coverage") or {}
    parts = [
        "## Schedule Sentinel finding — a game that should exist does not",
        "",
        f"`schedule-sentinel-fingerprint:{fp}`  (dedupe key — do not remove)",
        "",
        f"**League:** `{league}` (phase: {classified['phase']})  ",
        f"**Window:** {result.get('window')}  ",
        f"**Truth source:** `{cov.get('truth')}` — "
        f"{result.get('truth_games')} official game(s) vs "
        f"{result.get('our_events')} of our events  ",
        f"**Real defects:** {len(real)}  ",
        f"**Explained (postponement / re-schedule / quiet window — not filed):** "
        f"{len(explained)}  ",
        f"**Watch (not filed):** {len(watch)}  ",
        # Ruling 042 obligation 1: a count states how much of it rests on a label.
        f"**Pairings that could NOT be dereferenced (names-only):** "
        f"{len(unverified)}  ",
        "",
        "> Every other check we have verifies that what exists renders. This one "
        "verifies that what should exist, exists — the denominator is the "
        "authority's schedule, not our own table.",
        "",
        "### Real defects (RED — the calendar does NOT explain these)",
    ]
    for f in real[:MAX_FINDINGS_IN_BODY]:
        parts.append(f"- **[{f['kind']} / {f['severity']}]** {f['detail']}")
    if len(real) > MAX_FINDINGS_IN_BODY:
        parts.append(f"- …and {len(real) - MAX_FINDINGS_IN_BODY} more")
    if explained:
        parts += ["", "### Explained (context — suppressed by the artifact registry)"]
        for f in explained[:15]:
            parts.append(f"- {f['detail']} — _{f.get('explained_by')}_")
    if watch:
        parts += ["", "### Watch (surfaced, never filed)"]
        for f in watch[:15]:
            parts.append(f"- {f['detail']} — _{f.get('note')}_")
    if unverified:
        parts += [
            "",
            "### Unverified pairings (this league is measured, not checked)",
            "",
            "These rows were matched to the authority on NAMES and a clock because "
            "no identifier could be dereferenced. They are neither defects nor "
            "clean results — read the counts above with that in mind.",
        ]
        for f in unverified[:15]:
            parts.append(f"- {f['detail']}")
    parts += [
        "",
        "---",
        "*Auto-filed by the Schedule Sentinel (#1796, Queue 342). Read-only "
        "detection against an external authority; files work, never data "
        "(gotcha #21). Reproduce with "
        "`POST /api/admin/schedule-sentinel/run?inline=true&file_issues=false`.*",
    ]
    return "\n".join(parts)


def file_schedule_issue(result: dict, open_issues=None) -> dict:
    """RED/GREEN lifecycle for a league's schedule fingerprint via the shared rail.

    A NOT_COVERED or UNVERIFIED league neither files nor closes — it has not been
    measured, and an unmeasured league must never close a real issue."""
    from app.tasks.sentinel_filing import reconcile_issue

    classified = result["classified"]
    league = classified["league"]
    fp = schedule_fingerprint(league)
    real = classified["real"]

    if not real:
        res = reconcile_issue(
            red=False, fingerprint=fp, marker_key=_SCHEDULE_MARKER,
            green_comment=(
                f"Schedule Sentinel re-checked GREEN — the {league.upper()} schedule "
                f"reconciles against its authority with 0 real defects over "
                f"{result.get('window')} (fingerprint `{fp}`). Auto-closing; a future "
                f"recurrence opens a fresh episode."
            ),
            open_issues=open_issues,
        )
        res["league"] = league
        return res

    severity = severity_for_schedule(real)
    labels = ["alert-intake", "needs-agent", "area:backend",
              f"priority:{severity.lower()}"]
    res = reconcile_issue(
        red=True, fingerprint=fp, marker_key=_SCHEDULE_MARKER, labels=labels,
        title=build_schedule_issue_title(league, real, str(result.get("window"))),
        body=build_schedule_issue_body(result),
        title_prefix=_schedule_title_prefix(league),
        red_comment=(
            f"Schedule Sentinel re-observed {len(real)} real defect(s) on the "
            f"{league.upper()} schedule over {result.get('window')} "
            f"(fingerprint `{fp}`). Still open."
        ),
        open_issues=open_issues,
    )
    res["league"] = league
    if res.get("action") == "filed":
        res["severity"] = severity
    return res


# ---------------------------------------------------------------------------
# DB read — our population for the window, in the AUTHORITY's calendar.
# ---------------------------------------------------------------------------
def window_days(spec: LeagueSpec, now: Optional[datetime] = None) -> list[_date]:
    """The rolling yesterday/today/tomorrow window, in the league's own calendar.

    The authority defines the day (statsapi's ``date=`` is an Eastern calendar day,
    not a UTC one), so our side must be bucketed on the SAME calendar or the
    comparison manufactures boundary defects. The pre-existing MLB coverage check
    anchors on UTC noon ±18h instead, which is a different day."""
    tz = ZoneInfo(spec.tz)
    today = (now or datetime.now(timezone.utc)).astimezone(tz).date()
    return [today + timedelta(days=d)
            for d in range(-WINDOW_DAYS_BACK, WINDOW_DAYS_FORWARD + 1)]


async def load_our_events(spec: LeagueSpec, days: list[_date]) -> list[OurEvent]:
    """Our events for the window, selected by the SPORT FK — never by an LLM field.

    Measured 2026-08-13: selecting the MLB population by ``events.llm_league='MLB'``
    yields 12/20/13 rows over Aug 10–12, of which the surplus is Triple-A games
    (``baseball_milb``), Polymarket-derived pseudo-events (``baseball_other``,
    ingest-stamped ``commence_time`` with nonzero seconds) and Mexican-League rows
    mis-sported as ``americanfootball_other`` — all mis-tagged ``MLB`` by the LLM.
    Selecting by ``sports.key`` yields 10/6/11, the real population. A completeness
    check whose numerator is chosen by a classifier measures the classifier."""
    from sqlalchemy import or_, select
    from sqlalchemy.orm import aliased

    from app.models.models import Event, Sport, Team
    from app.tasks.base import get_task_session

    if not days:
        return []
    tz = ZoneInfo(spec.tz)
    start = datetime.combine(min(days), _dtime.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(max(days) + timedelta(days=1), _dtime.min,
                           tzinfo=tz).astimezone(timezone.utc)

    home_t = aliased(Team)
    away_t = aliased(Team)
    stmt = (
        select(
            Event.id, Event.status, Event.home_team_name, Event.away_team_name,
            Event.home_team_id, Event.away_team_id, Event.home_score,
            Event.away_score, Event.commence_time,
            home_t.name.label("home_fk_name"), away_t.name.label("away_fk_name"),
            # The provider game ids, so the pairing below can dereference rather
            # than compare strings (ruling 042). Omitting them is what let an
            # id-less row consume authoritative truth and report GREEN.
            Event.espn_id, Event.statpal_fixture_id, Event.external_id,
        )
        .join(Sport, Sport.id == Event.sport_id)
        .outerjoin(home_t, home_t.id == Event.home_team_id)
        .outerjoin(away_t, away_t.id == Event.away_team_id)
        .where(
            or_(*[Sport.key == k for k in spec.sport_keys]),
            Event.commence_time >= start,
            Event.commence_time < end,
        )
        .order_by(Event.commence_time)
    )
    async with get_task_session() as s:
        rows = (await s.execute(stmt)).all()

    out: list[OurEvent] = []
    for r in rows:
        try:
            ct = r.commence_time
            if ct is not None and ct.tzinfo is None:
                ct = ct.replace(tzinfo=timezone.utc)
            out.append(OurEvent(
                id=r.id, home_name=r.home_team_name or "",
                away_name=r.away_team_name or "",
                home_team_id=r.home_team_id, away_team_id=r.away_team_id,
                home_fk_name=r.home_fk_name, away_fk_name=r.away_fk_name,
                status=r.status or "", home_score=r.home_score,
                away_score=r.away_score, commence_time=ct,
                espn_id=r.espn_id, statpal_fixture_id=r.statpal_fixture_id,
                external_id=r.external_id,
            ))
        except Exception as exc:  # gotcha #42
            logger.warning("schedule sentinel row load failed: %s", exc)
    return out


# ---------------------------------------------------------------------------
# Per-league runner
# ---------------------------------------------------------------------------
async def run_league(client: httpx.AsyncClient, spec: LeagueSpec,
                     now: Optional[datetime] = None) -> dict:
    """Reconcile one league's rolling window. Never raises — a poison league
    yields a RED crash finding and its healthy siblings still run (gotcha #42)."""
    now = now or datetime.now(timezone.utc)
    days = window_days(spec, now)
    window = f"{days[0]}..{days[-1]}"
    coverage = {
        "league": spec.slug, "covered": spec.truth is not None,
        "truth": spec.truth, "reason": spec.uncovered_reason,
        "partial_by_design": spec.partial_by_design,
    }

    if spec.truth is None:
        # A league with no denominator is NOT COVERED and says so. It is never
        # scored green — that silence is the failure #1796 was filed about.
        return {
            "league": spec.slug, "window": window, "coverage": coverage,
            "verdict": NOT_COVERED,
            "classified": {"league": spec.slug,
                           "phase": season_windows.league_phase(
                               spec.season_key or spec.slug, now),
                           "real": [], "explained": [], "watch": [],
                           "unverified": []},
            "days_unverified": [], "truth_games": None, "our_events": None,
            "stats": {},
        }

    truth: list[TruthGame] = []
    days_unverified: list[str] = []
    truth_by_day: dict[str, int] = {}
    for day in days:
        res = await fetch_truth(client, spec, day)
        if not res.ok:
            days_unverified.append(f"{day}: {res.error}")
            continue
        truth_by_day[str(day)] = len(res.games)
        truth.extend(res.games)

    try:
        ours = await load_our_events(spec, days)
    except Exception as exc:
        logger.warning("schedule sentinel DB read failed (%s): %s", spec.slug, exc)
        return {
            "league": spec.slug, "window": window, "coverage": coverage,
            "verdict": GREEN_UNVERIFIED,
            "classified": {"league": spec.slug,
                           "phase": season_windows.league_phase(
                               spec.season_key or spec.slug, now),
                           "real": [], "explained": [], "watch": []},
            "days_unverified": days_unverified + [f"db read: {str(exc)[:120]}"],
            "truth_games": len(truth), "our_events": None, "stats": {},
        }

    findings, stats = reconcile(truth, ours, spec, now)
    classified = classify_findings(findings, spec, now)
    verdict = schedule_verdict(classified, covered=True,
                               days_unverified=days_unverified)
    return {
        "league": spec.slug, "window": window, "coverage": coverage,
        "verdict": verdict, "classified": classified,
        "days_unverified": days_unverified,
        "truth_games": len(truth), "our_events": len(ours),
        "truth_by_day": truth_by_day,
        "stats": stats,
        "kind_counts": _kind_counts(classified["real"]),
    }


def _kind_counts(findings: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        out[f.get("kind", "?")] = out.get(f.get("kind", "?"), 0) + 1
    return out


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
async def _run_schedule_sentinel(
    file_issues: bool = True,
    leagues: Optional[list[str]] = None,
    deadline_seconds: float = 480.0,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Reconcile every registered league against its authoritative schedule,
    classify findings, and (in a live run) file ONE deduped issue per league with
    REAL defects. Returns a scorecard cached for the cockpit tile."""
    _load_overrides()
    start = _time.monotonic()
    wanted = {s.lower() for s in leagues} if leagues else None
    specs = [s for s in SCHEDULE_LEAGUES if wanted is None or s.slug in wanted]

    stats: dict[str, Any] = {
        "mode": "live" if file_issues else "detect_only",
        "config": {"match_bar": MATCH_BAR,
                   "strict_pair_hours": STRICT_PAIR_HOURS,
                   "loose_pair_hours": LOOSE_PAIR_HOURS,
                   "stale_state_hours": STALE_STATE_HOURS},
        "leagues": [], "filed": [], "errors": [],
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        for spec in specs:
            if _time.monotonic() - start > deadline_seconds:
                stats["errors"].append({"deadline": f"stopped before {spec.slug}"})
                break
            try:
                result = await run_league(client, spec, now)
            except Exception as exc:  # gotcha #42 — siblings survive a poison league
                logger.error("Schedule sentinel league %s crashed: %s", spec.slug, exc)
                result = {
                    "league": spec.slug, "window": "?",
                    "coverage": {"league": spec.slug, "covered": spec.truth is not None,
                                 "truth": spec.truth},
                    "verdict": "red",
                    "classified": {"league": spec.slug, "phase": "?", "real": [
                        _finding("schedule_crash", "critical",
                                 f"league reconcile crashed: {str(exc)[:150]}",
                                 kind="MISSING")
                    ], "explained": [], "watch": []},
                    "days_unverified": [], "stats": {},
                }
            stats["leagues"].append(result)

    # --- Scorecard. Coverage is stated as "N of M", never as a bare percentage. ---
    covered = [lg for lg in stats["leagues"] if lg["verdict"] != NOT_COVERED]
    red = [lg for lg in covered if lg["verdict"] == "red"]
    unverified = [lg for lg in covered if lg["verdict"] == GREEN_UNVERIFIED]
    not_covered = [lg for lg in stats["leagues"] if lg["verdict"] == NOT_COVERED]
    total_kinds: dict[str, int] = {}
    for lg in stats["leagues"]:
        for k, v in (lg.get("kind_counts") or {}).items():
            total_kinds[k] = total_kinds.get(k, 0) + v

    stats["scorecard"] = {
        "leagues_total": len(stats["leagues"]),
        "leagues_covered": len(covered),
        "leagues_not_covered": len(not_covered),
        "coverage_label": f"{len(covered)} of {len(stats['leagues'])} leagues "
                          f"have a truth source",
        "leagues_red": len(red),
        "leagues_green": len(covered) - len(red) - len(unverified),
        "leagues_unverified": len(unverified),
        "real_defects_by_kind": total_kinds,
        "uncovered_leagues": [
            {"league": lg["league"], "reason": (lg.get("coverage") or {}).get("reason")}
            for lg in not_covered
        ],
        "per_league": [
            {
                "league": lg["league"],
                "verdict": lg["verdict"],
                "covered": (lg.get("coverage") or {}).get("covered"),
                "truth": (lg.get("coverage") or {}).get("truth"),
                "partial_by_design": (lg.get("coverage") or {}).get("partial_by_design"),
                "window": lg.get("window"),
                "phase": (lg.get("classified") or {}).get("phase"),
                "truth_games": lg.get("truth_games"),
                "our_events": lg.get("our_events"),
                "real_defects": len((lg.get("classified") or {}).get("real") or []),
                "explained": len((lg.get("classified") or {}).get("explained") or []),
                "watch": len((lg.get("classified") or {}).get("watch") or []),
                "kind_counts": lg.get("kind_counts") or {},
                "days_unverified": lg.get("days_unverified") or [],
                # Codex C-SEN-2 specimen 4. Without this the cockpit could see
                # only `days_unverified` — the FETCH-failure list — so a league
                # whose verdict was `green_unverified` purely from PAIRING
                # uncertainty rendered green. A verdict that survives the trip and
                # is then ignored is gotcha #145 wearing an operator's hat.
                "unverified": len((lg.get("classified") or {}).get("unverified") or []),
            }
            for lg in stats["leagues"]
        ],
    }

    # --- Filing + recovery. NOT_COVERED and UNVERIFIED neither file nor close. ---
    if file_issues:
        from app.tasks.sentinel_filing import fetch_open_alert_issues

        open_issues = fetch_open_alert_issues()
        for lg in red:
            stats["filed"].append(file_schedule_issue(lg, open_issues=open_issues))
        stats["resolved"] = [
            r for r in (
                file_schedule_issue(lg, open_issues=open_issues)
                for lg in covered if lg["verdict"] == "green"
            )
            if r.get("action") in ("resolved", "close_failed")
        ]

    stats["duration_seconds"] = round(_time.monotonic() - start, 1)
    stats["generated_at"] = datetime.now(timezone.utc).isoformat()

    from app.services.durable_snapshots import publish_sentinel_evidence
    from app.utils.durable_state import evaluate_publication

    stages = await publish_sentinel_evidence(
        identity="sentinel:schedule",
        redis_key="bainluck:schedule_sentinel:last",
        stats=stats,
        source="schedule_sentinel",
    )
    stats["persistence"] = stages
    evaluate_publication(
        compute_complete=True,
        durable_write="ok" if stages["durable"] in ("ok", "superseded") else "error",
        volatile_write=stages.get("volatile", "not_attempted"),
        stages=stages,
    ).raise_if_failed("schedule sentinel evidence")

    logger.info(
        "Schedule sentinel (%s): %s; %d red, %d unverified, %d filed in %.1fs",
        stats["mode"], stats["scorecard"]["coverage_label"],
        len(red), len(unverified), len(stats["filed"]), stats["duration_seconds"],
    )
    return stats
