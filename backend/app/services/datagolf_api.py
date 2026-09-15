"""
DataGolf API integration service.

Provides live in-play finish probabilities, pre-tournament model predictions,
tournament schedules, field updates, and outright odds from 11+ sportsbooks.

API docs: https://datagolf.com/api-access
Plan: Scratch Plus ($30/mo)
"""

import logging
import os
import unicodedata
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.services.base_api import BaseAPIClient
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# #994: some tour codes our external_ids carry as ingestion aliases are rejected
# by DataGolf's HISTORICAL endpoints (which accept: pga, euro, kft, cha, jpn, anz,
# alp, champ, kor, ngl, bet, chn, afr, pgt, pgti, atvt, atgt, sam). 'alt' is our
# alias for the DP World Tour, which DataGolf's historical API calls 'euro'. The
# DNP-recovery (#994) 400'd on tour='alt' for ~24 markets; mapping it to the
# accepted code lets those resolve instead of residual-ing out. Non-harmful: an
# unmapped/wrong tour still just returns [] (residual), never worse.
_HISTORICAL_TOUR_ALIASES = {"alt": "euro"}


def _historical_tour(tour: str) -> str:
    """Translate an ingestion tour alias to a DataGolf historical tour code."""
    return _HISTORICAL_TOUR_ALIASES.get((tour or "").lower(), tour)


# #6211 / CERT-2930. The row list `historical-raw-data/rounds` actually answers
# with, measured against the live provider key on 2026-09-15 (tour=pga,
# event_id=100, year=2023 -> HTTP 200, 208,858 bytes):
#
#     top-level keys: event_completed, event_id, event_name, SCORES, season,
#                     sg_categories, tour, traditional_stats, year
#     scores: 156 rows, row0 keys dg_id, fin_text, player_name,
#             round_1..round_4 (each a nested per-round dict carrying `score`
#             and `course_par`)
#
# `scores` was not in the list this module read, so a real 200 carrying 156
# players parsed to zero rows. Its caller reads zero rows as "DataGolf says the
# event is not in its index" and writes a PERMANENT residual flag, so the fix
# for #6211 would itself have entrenched the very defect it exists to remove.
_HISTORICAL_ROW_KEYS = ("scores", "data", "rounds")


class DataGolfUnknownEnvelope(RuntimeError):
    """A 200 whose body carries content in a shape we do not recognise.

    Raised rather than degraded to an empty list because the empty list is a
    TRUTH CLAIM in this module's contract ("DataGolf's historical index has no
    such event") and an unrecognised envelope is evidence of nothing except
    that the provider's shape moved. Gotcha #53: an empty response is a
    response SHAPE, not an absence — and here the emptiness would be entirely
    manufactured by our own parser.
    """


# DataGolf answers a genuinely absent event with HTTP 400 and a prose body, not
# a 404 and not an empty 200 (measured 2026-09-15, same key):
#
#   event_id=999999 -> 400 "event number 999999 is not available in the 2023
#                      pga calendar year, please input a valid event number."
#   year=1899       -> 400 "we don't have any historical raw data for 1899 -
#                      please choose from the following: 1983, 1984, ..."
#
# Only the FIRST is evidence about the event. The second is a statement about
# our own request being outside the provider's data range, and a 400 from a bad
# tour code (#994) is the same kind of thing. So the absence channel matches the
# provider's own event-number sentence and nothing else; every other 400 stays
# in the retryable class, where it is withheld from the curve but never recorded
# as a claim that the tournament did not happen.
_EVENT_ABSENT_400_MARKERS = ("is not available in the", "calendar year")


def _is_evidenced_absent_400(body: str) -> bool:
    """True when a 400 body is DataGolf saying THIS EVENT is not in its index."""
    lowered = (body or "").lower()
    return all(marker in lowered for marker in _EVENT_ABSENT_400_MARKERS)


def _historical_result_rows(data: object) -> list:
    """Return the player-row list from a `historical-raw-data/rounds` 200 body.

    An empty list here means the provider answered with a row list that is
    empty — the only 200 this module is willing to read as an absence. A body
    carrying content we cannot locate rows in raises, so it reaches the caller
    as our failure (retryable) rather than as the provider's answer (terminal).
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in _HISTORICAL_ROW_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return value
        raise DataGolfUnknownEnvelope(
            "historical-raw-data/rounds returned 200 with no recognised row "
            f"list (looked for {_HISTORICAL_ROW_KEYS}); top-level keys="
            f"{sorted(str(k) for k in data)[:12]}"
        )
    raise DataGolfUnknownEnvelope(
        f"historical-raw-data/rounds returned 200 with a {type(data).__name__} "
        "body, which carries no row list"
    )


def _round_entries(row: dict) -> list[dict]:
    """The nested per-round dicts of a `scores`-shaped player row, in order."""
    rounds = []
    for key, value in row.items():
        if not isinstance(value, dict):
            continue
        name = str(key)
        if not name.startswith("round_"):
            continue
        try:
            rounds.append((int(name.split("_", 1)[1]), value))
        except (IndexError, ValueError):
            continue
    return [value for _, value in sorted(rounds)]


def _player_row_from_scores(row: dict) -> Optional[dict]:
    """Normalise ONE `scores`-shaped row (one player, rounds nested) .

    `scores` carries no total; the tournament figure is summed over the rounds
    the player actually completed, to par, which is the semantic the flat shape
    supplied under `total_to_par` and the one the leaderboard entries downstream
    already hold.
    """
    dg_id = row.get("dg_id")
    if dg_id is None:
        return None

    to_par: Optional[int] = None
    for entry in _round_entries(row):
        score, par = entry.get("score"), entry.get("course_par")
        if score is None or par is None:
            continue
        try:
            to_par = (to_par or 0) + int(score) - int(par)
        except (TypeError, ValueError):
            continue

    return {
        "dg_id": dg_id,
        "name": normalize_player_name(row.get("player_name", "")),
        "position": row.get("fin_text", row.get("current_pos", row.get("position"))),
        "total_score": to_par,
    }


def _is_scores_shaped(rows: list) -> bool:
    """True when rows are one-per-PLAYER with nested rounds, not one-per-ROUND.

    Decided on the rows themselves rather than on which key they arrived under,
    so a provider that moves the shape between keys cannot silently select the
    wrong aggregation.
    """
    for row in rows:
        if isinstance(row, dict) and _round_entries(row):
            return True
    return False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class DataGolfPlayer(BaseModel):
    """A single player's probability and leaderboard data."""
    dg_id: int
    player_name: str  # "Scheffler, Scottie" → normalized to "Scottie Scheffler"

    # Probabilities (0-1 scale, nullable — not all endpoints return all fields)
    win: Optional[float] = None
    top_5: Optional[float] = None
    top_10: Optional[float] = None
    top_20: Optional[float] = None
    make_cut: Optional[float] = None

    # Leaderboard state (only from in-play endpoint)
    position: Optional[str] = None  # "T3", "1", "CUT"
    total_score: Optional[int] = None  # e.g., -12
    today_score: Optional[int] = None  # e.g., -3
    thru: Optional[str] = None  # "F", "12", "—"
    current_round: Optional[int] = None  # 1-4


class DataGolfTournament(BaseModel):
    """A tournament from the schedule endpoint."""
    event_id: str  # DataGolf's internal event ID
    event_name: str
    course: Optional[str] = None
    start_date: Optional[str] = None  # "2026-04-10"
    end_date: Optional[str] = None  # Computed: start_date + 3 days (not in API)
    status: Optional[str] = None  # "completed", "in-progress", "upcoming", etc.
    tour: str  # "pga", "euro", "kft", "liv", etc.
    current_round: Optional[int] = None
    location: Optional[str] = None  # "Honolulu, HI"
    country: Optional[str] = None


class DataGolfOddsPlayer(BaseModel):
    """A single player's odds from the outright-odds endpoint."""
    dg_id: int
    player_name: str
    datagolf_model: Optional[float] = None  # Model-predicted probability
    # Sportsbook odds keyed by book name → probability
    sportsbook_odds: dict[str, Optional[float]] = {}


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

def normalize_player_name(name: str) -> str:
    """Normalize DataGolf 'Last, First' format to 'First Last'.

    Also strips diacritics for cross-source matching.
    Examples:
        'Scheffler, Scottie' → 'Scottie Scheffler'
        'Hovland, Viktor'    → 'Viktor Hovland'
        'Skarsgård, Gustav'  → 'Gustav Skarsgard'
    """
    if not name:
        return name

    # Split on comma if present
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            name = f"{parts[1]} {parts[0]}"

    return strip_diacritics(name).strip()


from app.utils.name_normalization import strip_diacritics


# ---------------------------------------------------------------------------
# API service
# ---------------------------------------------------------------------------

class DataGolfAPIService(BaseAPIClient):
    """Service for interacting with DataGolf's API."""

    BASE_URL = "https://feeds.datagolf.com"

    TOURS = ["pga", "euro", "kft", "liv", "opp", "alt"]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DATAGOLF_API_KEY")
        super().__init__(
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    # -- Core HTTP helper --------------------------------------------------

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        """Authenticated GET request with ?key=API_KEY."""
        if not self.api_key:
            raise ValueError("DATAGOLF_API_KEY not configured")

        params = params or {}
        params["key"] = self.api_key
        params["file_format"] = "json"

        url = f"{self.BASE_URL}/{endpoint}"
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("DataGolf rate limited on %s", endpoint)
            raise
        except httpx.ReadTimeout:
            logger.warning("DataGolf timeout on %s", endpoint)
            raise

    # -- In-play predictions -----------------------------------------------

    async def get_in_play(self, tour: str = "pga") -> list[DataGolfPlayer]:
        """Fetch live in-play finish probabilities + leaderboard positions.

        Returns an empty list when no tournament is in play.
        """
        try:
            data = await self._get("preds/in-play", {"tour": tour})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []  # No in-play event
            raise

        return self._parse_players(data, in_play=True)

    async def get_in_play_with_info(self, tour: str = "pga") -> tuple[list["DataGolfPlayer"], dict]:
        """Like get_in_play but also returns event info dict.

        Returns (players, info_dict). info_dict has keys like
        'event_name', 'current_round', 'last_update'.
        """
        try:
            data = await self._get("preds/in-play", {"tour": tour})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return [], {}
            raise

        info = data.get("info", {})

        # Log raw field names from first player entry for score debugging
        raw_players = data.get("data", [])
        if raw_players:
            sample = raw_players[0]
            logger.info(
                "DataGolf in-play raw keys: %s (sample player: %s, total=%s, today=%s)",
                sorted(sample.keys()),
                sample.get("player_name", "?"),
                sample.get("total"),
                sample.get("today"),
            )

        return self._parse_players(data, in_play=True), info

    # -- Pre-tournament predictions ----------------------------------------

    async def get_pre_tournament(self, tour: str = "pga") -> list[DataGolfPlayer]:
        """Fetch pre-tournament model predictions.

        Returns probabilities for all players in the field before the event starts.
        """
        try:
            data = await self._get("preds/pre-tournament", {"tour": tour})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise

        return self._parse_players(data, in_play=False)

    # -- Schedule ----------------------------------------------------------

    async def get_schedule(
        self,
        tour: str = "pga",
        season: Optional[int] = None,
    ) -> list[DataGolfTournament]:
        """Fetch tournament schedule for a tour."""
        params = {"tour": tour}
        if season:
            params["season"] = str(season)

        data = await self._get("get-schedule", params)

        schedule = data.get("schedule", [])
        result = []
        for entry in schedule:
            start = entry.get("start_date")
            # Compute end_date as start + 3 days (standard 4-day PGA event)
            end = None
            if start:
                try:
                    from datetime import timedelta as td
                    end = (datetime.strptime(start, "%Y-%m-%d") + td(days=3)).strftime("%Y-%m-%d")
                except ValueError:
                    pass

            result.append(DataGolfTournament(
                event_id=str(entry.get("event_id", "")),
                event_name=entry.get("event_name", ""),
                course=entry.get("course"),
                start_date=start,
                end_date=end,
                status=entry.get("status"),
                tour=tour,
                current_round=entry.get("current_round"),
                location=entry.get("location"),
                country=entry.get("country"),
            ))
        return result

    # -- Field updates -----------------------------------------------------

    async def get_field_updates(self, tour: str = "pga") -> dict:
        """Fetch field, withdrawals, and tee times for upcoming/in-play event.

        Returns raw dict with 'field' array and event metadata.
        """
        try:
            return await self._get("field-updates", {"tour": tour})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"field": []}
            raise

    # -- Outright odds (sportsbook comparison) -----------------------------

    async def get_outright_odds(
        self,
        tour: str = "pga",
        market: str = "win",
        odds_format: str = "decimal",
    ) -> list[DataGolfOddsPlayer]:
        """Fetch odds from 11+ sportsbooks + DataGolf model.

        market: 'win', 'top_5', 'top_10', 'top_20', 'make_cut'
        """
        data = await self._get("betting-tools/outrights", {
            "tour": tour,
            "market": market,
            "odds_format": odds_format,
        })

        players = []
        odds_data = data.get("odds", [])
        books = data.get("books", [])  # List of sportsbook names

        for entry in odds_data:
            name = normalize_player_name(entry.get("player_name", ""))
            dg_id = entry.get("dg_id", 0)

            # Model prediction
            model_prob = None
            baseline = entry.get("datagolf_base_history_fit")
            if baseline is not None:
                try:
                    model_prob = 1.0 / float(baseline) if float(baseline) > 0 else None
                except (ValueError, ZeroDivisionError):
                    pass

            # Sportsbook odds (decimal → probability)
            sportsbook_odds = {}
            for book in books:
                val = entry.get(book)
                if val is not None:
                    try:
                        decimal_odds = float(val)
                        if decimal_odds > 0:
                            sportsbook_odds[book] = 1.0 / decimal_odds
                    except (ValueError, ZeroDivisionError):
                        pass

            players.append(DataGolfOddsPlayer(
                dg_id=dg_id,
                player_name=name,
                datagolf_model=model_prob,
                sportsbook_odds=sportsbook_odds,
            ))

        return players

    # -- Historical results -------------------------------------------------

    async def get_historical_results(
        self,
        tour: str = "pga",
        event_id: str = "",
        year: Optional[int] = None,
    ) -> list[dict]:
        """Fetch historical round-level results for a completed tournament.

        Returns a list of player dicts with final position, score, dg_id, etc.
        Uses the historical-raw-data/rounds endpoint which provides per-round
        scoring data for any completed event.

        Returns an empty list ONLY when DataGolf itself says the event is not in
        its historical index — a 404, its 400 "event number N is not available
        in the YYYY TOUR calendar year", or a 200 whose own row list is empty.
        Every other failure RAISES, including a 200 whose envelope we cannot
        find rows in: a shape we do not recognise is evidence about our parser,
        never about the tournament.

        #6211 / CERT-2930: the recognised-envelope list did not include
        `scores`, which is the key the live endpoint actually answers under, so
        a 200 carrying 156 players parsed to zero rows and was about to be
        recorded as a permanent absence. See `_HISTORICAL_ROW_KEYS` and
        `_EVENT_ABSENT_400_MARKERS` above for the measured provider shapes.

        #6211: this method used to fold 403 and ReadTimeout into the same ``[]``
        as a 404, and its only caller — ``_datagolf_recovery`` — reads ``[]`` as
        "event genuinely not found" and writes a PERMANENT
        ``datagolf_recovery_residual`` flag that removes the whole market from the
        published calibration curve. So a plan/entitlement refusal or one slow
        response was being recorded as a durable truth claim about whether a
        tournament ever happened. Measured on production 2026-09-15: 322 of 340
        resolved DataGolf markets (94.7%) carried the flag, against a code comment
        in ``precompute_calibration`` that says the residual "is expected to be
        ~0", leaving a 36-row winner-only residue published as a 36.5pp accuracy
        figure about a named third-party provider.

        This is gotcha #36 (never catch-all in an API client returning an
        "absent" sentinel — ``[]`` may only mean 404) and gotcha #53 (an empty
        response is a response SHAPE, not an absence). A 403 is the venue
        declining to answer and a timeout is no answer at all; neither is
        evidence that the event does not exist, and the caller cannot tell them
        apart from a real absence once they share a return value.
        """
        params: dict = {"tour": _historical_tour(tour)}
        if event_id:
            params["event_id"] = event_id
        if year:
            params["year"] = str(year)

        try:
            data = await self._get("historical-raw-data/rounds", params)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            body = ""
            try:
                body = e.response.text or ""
            except Exception:  # noqa: BLE001 — a body we cannot read is not an absence
                body = ""
            if status == 404 or (status == 400 and _is_evidenced_absent_400(body)):
                logger.info(
                    "DataGolf historical results: event not in index "
                    "tour=%s event=%s year=%s status=%d provider_said=%r",
                    tour, event_id, year, status, body[:200],
                )
                return []
            raise

        rows = _historical_result_rows(data)
        if not rows:
            return []

        # Two shapes reach here. `scores` is one row PER PLAYER with the rounds
        # nested inside it; the flat shape is one row per player-ROUND and needs
        # the highest round kept per dg_id. Picking the wrong one silently
        # returns a plausible, wrong leaderboard, so the shape decides.
        if _is_scores_shaped(rows):
            return [
                player
                for player in (
                    _player_row_from_scores(row) for row in rows if isinstance(row, dict)
                )
                if player is not None
            ]

        raw_rows = rows

        # Group by dg_id, keep the latest round
        by_player: dict[int, dict] = {}
        for row in raw_rows:
            dg_id = row.get("dg_id")
            if dg_id is None:
                continue
            round_num = row.get("round_num", row.get("round", 0)) or 0
            existing = by_player.get(dg_id)
            if existing is None or round_num > existing.get("_round_num", 0):
                by_player[dg_id] = {
                    "dg_id": dg_id,
                    "name": normalize_player_name(row.get("player_name", "")),
                    "position": row.get("fin_text", row.get("current_pos", row.get("position"))),
                    "total_score": row.get("total_to_par", row.get("total_score")),
                    "_round_num": round_num,
                }

        # Strip internal field and return
        results = []
        for p in by_player.values():
            p.pop("_round_num", None)
            results.append(p)

        return results

    # -- Historical odds ---------------------------------------------------

    async def get_historical_outrights(
        self,
        tour: str = "pga",
        event_id: str = "",
        year: Optional[int] = None,
        market: str = "win",
        book: str = "datagolf",
    ) -> list[dict]:
        """Fetch historical outright odds with bet outcomes.

        Returns opening/closing lines and actual outcomes for outright
        markets (win, top_5, top_10, top_20, make_cut, mc).

        The bet_outcome field indicates the actual result (1=won, 0=lost).
        """
        params: dict = {"tour": _historical_tour(tour), "market": market, "book": book}
        if event_id:
            params["event_id"] = event_id
        if year:
            params["year"] = str(year)

        try:
            data = await self._get("historical-odds/outrights", params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                logger.info(
                    "DataGolf historical outrights unavailable: tour=%s event=%s market=%s status=%d",
                    tour, event_id, market, e.response.status_code,
                )
                return []
            raise
        except httpx.ReadTimeout:
            logger.warning("DataGolf historical outrights timeout: tour=%s event=%s", tour, event_id)
            return []

        rows = data if isinstance(data, list) else data.get("odds", data.get("data", []))
        return rows if isinstance(rows, list) else []

    async def get_historical_matchups(
        self,
        tour: str = "pga",
        event_id: str = "",
        year: Optional[int] = None,
        book: str = "datagolf",
    ) -> list[dict]:
        """Fetch historical matchup odds (H2H and 3-ball) with bet outcomes.

        Returns opening/closing lines for head-to-head and 3-ball matchups
        with actual outcomes. Used for:
        1. Resolving Kalshi H2H/3-ball golf markets
        2. Displaying multi-source aggregated matchup odds on event pages
        """
        params: dict = {"tour": _historical_tour(tour), "book": book}
        if event_id:
            params["event_id"] = event_id
        if year:
            params["year"] = str(year)

        try:
            data = await self._get("historical-odds/matchups", params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                logger.info(
                    "DataGolf historical matchups unavailable: tour=%s event=%s status=%d",
                    tour, event_id, e.response.status_code,
                )
                return []
            raise
        except httpx.ReadTimeout:
            logger.warning("DataGolf historical matchups timeout: tour=%s event=%s", tour, event_id)
            return []

        rows = data if isinstance(data, list) else data.get("matchups", data.get("data", []))
        return rows if isinstance(rows, list) else []

    async def get_event_list(
        self,
        tour: str = "pga",
    ) -> list[dict]:
        """Fetch the list of events with historical data available.

        Returns event_id, event_name, calendar_year, and flags for
        archived predictions, outrights, and matchup availability.
        """
        try:
            data = await self._get("historical-odds/event-list", {"tour": tour})
        except httpx.HTTPStatusError:
            return []
        except httpx.ReadTimeout:
            return []

        return data if isinstance(data, list) else data.get("events", [])

    # -- Internal parser ---------------------------------------------------

    def _parse_players(self, data: dict, in_play: bool = False) -> list[DataGolfPlayer]:
        """Parse player data from prediction endpoints.

        The in-play endpoint uses "data" as the key for player entries.
        The pre-tournament endpoint uses "baseline" (or "baseline_history_fit").
        We try all known keys to find the player list.
        """
        players = []
        raw_players = (
            data.get("data", [])
            or data.get("baseline_history_fit", [])
            or data.get("baseline", [])
        )

        # Some endpoints use top-level event info
        event_round = data.get("current_round")

        for entry in raw_players:
            name = normalize_player_name(entry.get("player_name", ""))
            dg_id = entry.get("dg_id", 0)

            player = DataGolfPlayer(
                dg_id=dg_id,
                player_name=name,
                win=_safe_prob(entry, "win_prob") or _safe_prob(entry, "win"),
                top_5=_safe_prob(entry, "top_5_prob") or _safe_prob(entry, "top_5"),
                top_10=_safe_prob(entry, "top_10_prob") or _safe_prob(entry, "top_10"),
                top_20=_safe_prob(entry, "top_20_prob") or _safe_prob(entry, "top_20"),
                make_cut=_safe_prob(entry, "make_cut_prob") or _safe_prob(entry, "make_cut"),
            )

            if in_play:
                player.position = entry.get("current_pos") or entry.get("position")
                # Use _first_int to avoid 0 (even par) being treated as falsy
                player.total_score = _first_int(entry, "current_score", "total", "total_to_par")
                player.today_score = _first_int(entry, "today", "today_to_par")
                player.thru = str(entry.get("thru", "")) or None
                player.current_round = _first_int(
                    {"r": event_round, **entry}, "r", "current_round", "round",
                ) if event_round else _first_int(entry, "current_round", "round")

                # Debug: log field names from first player to diagnose missing scores
                if not players and logger.isEnabledFor(logging.DEBUG):
                    score_keys = [k for k in entry.keys() if any(
                        t in k.lower() for t in ("score", "total", "today", "par", "round")
                    )]
                    logger.debug("DataGolf in-play fields for %s: %s (score_keys=%s)",
                                 name, list(entry.keys()), score_keys)

            players.append(player)

        return players


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_prob(d: dict, key: str) -> Optional[float]:
    """Safely extract a probability value from a dict entry."""
    val = d.get(key)
    if val is None:
        return None
    try:
        f = float(val)
        return f if 0.0 <= f <= 1.0 else None
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> Optional[int]:
    """Safely parse an integer, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _first_int(d: dict, *keys: str) -> Optional[int]:
    """Return the first non-None int value from the dict for the given keys.

    Unlike chaining with `or`, this correctly handles 0 (even par).
    """
    for key in keys:
        val = _safe_int(d.get(key))
        if val is not None:
            return val
    return None


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

async def fetch_datagolf_in_play(tour: str = "pga") -> list[DataGolfPlayer]:
    """One-off fetch of live in-play predictions."""
    service = DataGolfAPIService()
    try:
        return await service.get_in_play(tour)
    finally:
        await service.close()
