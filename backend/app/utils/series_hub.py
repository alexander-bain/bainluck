"""Playoff series hub producer, 3-family series context, labeled game-start baseline, and ``advances_to`` graph writer (#9715, #12221 Stage 3).

PILLAR: DISCOVER / FORMATTING / TRUTH · SHIP:
1. A playoff series hub (``series_hub``) built from stored IDs shows its series
   games, series winner, exact series score, series total games, game props, and
   championship/pennant path together in one container and Discover card, ready
   for MLB, NBA, and NHL playoffs.
2. Series markets are classified into three canonical families:
   - ``series_winner`` (``distribution_kind == "exhaustive"``)
   - ``exact_series_score`` (``distribution_kind == "exhaustive"``)
   - ``series_total_games`` (``distribution_kind == "independent_binary"`` —
     cumulative/binary threshold rungs, never normalized or squeezed to 100%).
3. During-game movement is computed only when comparable timestamped observations
   exist at or before ``game_start`` from the same venue. The baseline is
   explicitly labeled (``baseline_kind == "game_start"``, ``baseline_label ==
   "since game start"``) and never conflated with ``opening_probability`` (market
   open) or 24-hour change. Settled states (``Won`` / ``Lost``) are preserved
   and never overwritten by live movement logic.
4. Writes the first ``advances_to`` edges on the container graph
   (``parent_type="container"``, ``child_type="container"``, ``kind="advances_to"``,
   ``edge_class=None``), validated through ``app.utils.container_graph``.
"""

from __future__ import annotations

import copy
import importlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from app.utils.container_graph import (
    validate_confidence,
    validate_edge_kind_and_class,
    validate_edge_source,
    validate_node_type,
)

NODE_CONTAINER = "container"
EDGE_SOURCE_REGISTER = "register"
from app.utils.container_presentation import (
    MEMBER_EVENT,
    MEMBER_MARKET,
    event_destination,
    market_destination,
)
from app.utils.field_band import _validate_narrative_copy
from app.utils.postseason_series import PlayoffSeries, certain_to_be_played
from app.utils.series_card_labels import relabel_series_card
from app.utils.series_probability import series_state_label

__all__ = [
    "CORE_SERIES_FAMILIES",
    "DEFAULT_SERIES_HUB_LEVEL",
    "DEFAULT_SERIES_HUB_RELATIONS",
    "DISTRIBUTION_EXHAUSTIVE",
    "DISTRIBUTION_INDEPENDENT_BINARY",
    "FAMILY_EXACT_SERIES_SCORE",
    "FAMILY_OTHER_SERIES",
    "FAMILY_SERIES_SPREAD",
    "FAMILY_SERIES_TOTAL_GAMES",
    "FAMILY_SERIES_WINNER",
    "MLB_2026_ALWC_BOS_NYY_DEFINITION",
    "MLB_2026_ALWC_BOS_NYY_DEFINITION_PATH",
    "MLB_2026_ALWC_BOS_NYY_PRODUCER",
    "MLB_2026_ALWC_BOS_NYY_SLUG",
    "PLAYOFF_SERIES_BEST_OF_BY_SPORT",
    "PRODUCER_KIND_SERIES_HUB",
    "SeriesAdvancementEdge",
    "build_event_series_context",
    "build_series_advances_to_edge",
    "build_series_hub_producer",
    "classify_series_market_family",
    "compute_series_game_start_movement",
    "load_series_hub_definition",
    "mlb_2026_alwc_bos_nyy",
    "produce_series_hub",
    "select_series_hub",
    "series_family_distribution_contract",
    "series_hub_enabled",
    "write_series_advances_to_edges",
]


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


PRODUCER_KIND_SERIES_HUB = "series_hub"
DEFAULT_SERIES_HUB_RELATIONS: tuple[str, ...] = (
    "same_series",
    "same_event",
    "path",
)
DEFAULT_SERIES_HUB_LEVEL = "member"

MLB_2026_ALWC_BOS_NYY_SLUG = "mlb-2026-alwc-bos-nyy"
MLB_2026_ALWC_BOS_NYY_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{MLB_2026_ALWC_BOS_NYY_SLUG}.json"
)

FAMILY_SERIES_WINNER = "series_winner"
FAMILY_EXACT_SERIES_SCORE = "exact_series_score"
FAMILY_SERIES_TOTAL_GAMES = "series_total_games"
FAMILY_SERIES_SPREAD = "series_spread"
FAMILY_OTHER_SERIES = "other_series"

CORE_SERIES_FAMILIES: tuple[str, ...] = (
    FAMILY_SERIES_WINNER,
    FAMILY_EXACT_SERIES_SCORE,
    FAMILY_SERIES_TOTAL_GAMES,
)

DISTRIBUTION_EXHAUSTIVE = "exhaustive"
DISTRIBUTION_INDEPENDENT_BINARY = "independent_binary"

_FAMILY_LABELS: dict[str, str] = {
    FAMILY_SERIES_WINNER: "Series Winner",
    FAMILY_EXACT_SERIES_SCORE: "Exact Series Score",
    FAMILY_SERIES_TOTAL_GAMES: "Series Total Games",
    FAMILY_SERIES_SPREAD: "Series Spread",
    FAMILY_OTHER_SERIES: "Series Market",
}

_FAMILY_SORT_ORDER: dict[str, int] = {
    FAMILY_SERIES_WINNER: 0,
    FAMILY_EXACT_SERIES_SCORE: 1,
    FAMILY_SERIES_TOTAL_GAMES: 2,
    FAMILY_SERIES_SPREAD: 3,
    FAMILY_OTHER_SERIES: 4,
}

#: Default best-of length by sport/round for MLB, NBA, and NHL playoffs.
PLAYOFF_SERIES_BEST_OF_BY_SPORT: dict[str, dict[str, int]] = {
    "baseball_mlb": {
        "WC": 3,
        "ALWC": 3,
        "NLWC": 3,
        "DS": 5,
        "ALDS": 5,
        "NLDS": 5,
        "CS": 7,
        "ALCS": 7,
        "NLCS": 7,
        "WS": 7,
        "DEFAULT": 5,
    },
    "basketball_nba": {
        "R1": 7,
        "R2": 7,
        "CONF": 7,
        "ECF": 7,
        "WCF": 7,
        "FINALS": 7,
        "DEFAULT": 7,
    },
    "icehockey_nhl": {
        "R1": 7,
        "R2": 7,
        "CONF": 7,
        "ECF": 7,
        "WCF": 7,
        "SCF": 7,
        "FINALS": 7,
        "DEFAULT": 7,
    },
}

_KALSHI_SERIES_WINNER_RE = re.compile(
    r"^KX(?:MLB|NBA|NHL|WNBA)SERIES-[A-Z0-9]+$", re.IGNORECASE
)
_KALSHI_SERIES_SCORE_RE = re.compile(
    r"^KX(?:MLB|NBA|NHL|WNBA)SERIESSCORE-[A-Z0-9]+$", re.IGNORECASE
)
_KALSHI_SERIES_GAMES_RE = re.compile(
    r"^KX(?:MLB|NBA|NHL|WNBA)SERIESGAMES-[A-Z0-9]+$", re.IGNORECASE
)
_KALSHI_SERIES_SPREAD_RE = re.compile(
    r"^KX(?:MLB|NBA|NHL|WNBA)SERIESSPREAD-[A-Z0-9]+$", re.IGNORECASE
)

_SETTLED_MARKET_STATUSES: frozenset[str] = frozenset(
    {"settled", "closed", "completed", "final", "graded", "resolved"}
)
_LIVE_EVENT_STATUSES: frozenset[str] = frozenset(
    {"live", "in_progress", "halftime", "in progress"}
)
_FINISHED_EVENT_STATUSES: frozenset[str] = frozenset(
    {"completed", "closed", "final", "finished", "settled"}
)


def series_hub_enabled() -> bool:
    """One setting turns series_hub cards and containers on or off together.

    Note (#9715 / Decide 63-A): ``series_hub`` in ``backend/data/grouping_licences.json``
    has ``"status": "HELD"`` and ``"mode": "hand_defined"``, which blocks automated
    proposal promotion (``is_kind_licensed_for_promotion``) until the kind passes
    its grading exam. The hand-authored 2026 MLB proof definition
    (``mlb-2026-alwc-bos-nyy``) suppresses its Discover card because the series is
    finished (``suppress_feed_item=True``) while publishing its results collection
    page at ``/collections/mlb-2026-alwc-bos-nyy``; setting ``SERIES_HUB_ENABLED=false``
    or transitioning the licence to ``"SUSPENDED"`` halts both immediately.
    """
    return os.getenv("SERIES_HUB_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _parse_utc(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc)
            if value.tzinfo is not None
            else value.replace(tzinfo=timezone.utc)
        )
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        return (
            dt.astimezone(timezone.utc)
            if dt.tzinfo is not None
            else dt.replace(tzinfo=timezone.utc)
        )
    return None


def classify_series_market_family(
    market_name: Optional[str],
    external_id: Optional[str] = None,
    outcomes: Optional[Sequence[Mapping[str, Any]]] = None,
) -> str:
    """Classify a series market into one of the canonical series families (#9715).

    Families:
    - ``"series_winner"``: who wins the series (exhaustive)
    - ``"exact_series_score"``: exact series score such as 2-0 / 2-1 / 4-2 (exhaustive)
    - ``"series_total_games"``: total games / length ladder (independent binary rungs)
    - ``"series_spread"``: series games handicap/spread (exhaustive)
    - ``"other_series"``: any other series-level market
    """
    ext = str(external_id or "").strip().upper()
    if ext:
        if _KALSHI_SERIES_SCORE_RE.match(ext) or "SERIESSCORE-" in ext:
            return FAMILY_EXACT_SERIES_SCORE
        if _KALSHI_SERIES_GAMES_RE.match(ext) or "SERIESGAMES-" in ext:
            return FAMILY_SERIES_TOTAL_GAMES
        if _KALSHI_SERIES_SPREAD_RE.match(ext) or "SERIESSPREAD-" in ext:
            return FAMILY_SERIES_SPREAD
        if _KALSHI_SERIES_WINNER_RE.match(ext) or re.search(
            r"KX(?:MLB|NBA|NHL|WNBA)SERIES-", ext
        ):
            return FAMILY_SERIES_WINNER

    if outcomes:
        for out in outcomes:
            if not isinstance(out, Mapping):
                continue
            out_ext = str(out.get("external_id") or "").strip().upper()
            if "SERIESSCORE-" in out_ext:
                return FAMILY_EXACT_SERIES_SCORE
            if "SERIESGAMES-" in out_ext:
                return FAMILY_SERIES_TOTAL_GAMES
            if "SERIESSPREAD-" in out_ext:
                return FAMILY_SERIES_SPREAD
            if re.search(r"KX(?:MLB|NBA|NHL|WNBA)SERIES-", out_ext):
                return FAMILY_SERIES_WINNER

    name_lower = str(market_name or "").strip().lower()
    if any(
        tok in name_lower
        for tok in (
            "exact score",
            "exact series score",
            "correct score",
            "series score",
        )
    ):
        return FAMILY_EXACT_SERIES_SCORE
    if any(
        tok in name_lower
        for tok in (
            "total games",
            "series length",
            "how many games",
            "number of games",
            "games in series",
        )
    ):
        return FAMILY_SERIES_TOTAL_GAMES
    if "series spread" in name_lower or (
        "spread" in name_lower and "series" in name_lower
    ):
        return FAMILY_SERIES_SPREAD
    if any(
        tok in name_lower
        for tok in (
            "series winner",
            "win series",
            "win the series",
            "to win series",
            "who will win series",
            "advance",
        )
    ):
        return FAMILY_SERIES_WINNER

    if outcomes:
        names = [
            str(o.get("name") or "").strip().lower()
            for o in outcomes
            if isinstance(o, Mapping)
        ]
        if any("total games" in n or re.search(r"\bover\s+\d+\.5\b", n) for n in names):
            return FAMILY_SERIES_TOTAL_GAMES
        if any(re.search(r"\bwins\s+\d+-\d+\b", n) for n in names):
            return FAMILY_EXACT_SERIES_SCORE

    return FAMILY_OTHER_SERIES


def series_family_distribution_contract(family: str) -> dict[str, Any]:
    """Return the distribution contract for a classified series market family (#9715).

    ``series_total_games`` is an independent binary / cumulative threshold ladder
    (e.g. ``Over 2.5 total games``, ``Over 4.5 / 5.5 / 6.5 total games``) and
    must NEVER be squeezed or normalized to sum to 100%.
    """
    fam = str(family or FAMILY_OTHER_SERIES).strip()
    label = _FAMILY_LABELS.get(fam, _FAMILY_LABELS[FAMILY_OTHER_SERIES])
    if fam == FAMILY_SERIES_TOTAL_GAMES:
        return {
            "series_family": fam,
            "series_family_label": label,
            "distribution_kind": DISTRIBUTION_INDEPENDENT_BINARY,
            "exhaustive": False,
            "normalize_to_unit_sum": False,
            "sum_note": "Each line is its own yes-or-no question, so these don't add up to 100%.",
        }
    return {
        "series_family": fam,
        "series_family_label": label,
        "distribution_kind": DISTRIBUTION_EXHAUSTIVE,
        "exhaustive": True,
        "normalize_to_unit_sum": True,
        "sum_note": None,
    }


def _select_game_start_snapshot(
    snapshots: Sequence[Any],
    *,
    game_start: datetime,
    market_source: Optional[str],
    max_pregame_age_hours: float,
) -> Optional[tuple[float, datetime]]:
    """Return ``(probability, captured_at)`` for the latest comparable pre-game snapshot.

    Enforces #1844 / #9715:
    - Observation timestamp ``captured_at`` must fall in
      ``[game_start - max_pregame_age_hours, game_start]``.
    - If ``market_source`` is specified (e.g. ``"kalshi"`` or ``"polymarket"``) and
      the snapshot declares ``bookmaker`` / ``source``, they must match so a raw
      sportsbook row is never compared to a prediction market or blend.
    """
    earliest = game_start - timedelta(hours=max(0.25, float(max_pregame_age_hours)))
    expected_source = str(market_source or "").strip().lower() or None

    best_prob: Optional[float] = None
    best_ts: Optional[datetime] = None

    for snap in snapshots:
        if isinstance(snap, Mapping):
            raw_prob = snap.get("probability")
            raw_ts = snap.get("captured_at") or snap.get("observed_at") or snap.get("timestamp")
            snap_source = (
                snap.get("bookmaker")
                or snap.get("source")
                or snap.get("venue")
            )
        else:
            raw_prob = getattr(snap, "probability", None)
            raw_ts = getattr(snap, "captured_at", None) or getattr(
                snap, "observed_at", None
            )
            snap_source = getattr(snap, "bookmaker", None) or getattr(
                snap, "source", None
            )

        if raw_prob is None:
            continue
        try:
            prob_val = float(raw_prob)
        except (TypeError, ValueError):
            continue
        if not (0.0 <= prob_val <= 1.0):
            continue

        ts = _parse_utc(raw_ts)
        if ts is None or ts > game_start or ts < earliest:
            continue

        if expected_source and snap_source is not None:
            clean_snap_source = str(snap_source).strip().lower()
            if clean_snap_source and clean_snap_source != expected_source:
                continue

        if best_ts is None or ts >= best_ts:
            best_ts = ts
            best_prob = prob_val

    if best_prob is None or best_ts is None:
        return None
    return (best_prob, best_ts)


def compute_series_game_start_movement(
    outcomes: Sequence[Mapping[str, Any]],
    *,
    game_start: datetime | str | None,
    event_status: Optional[str] = None,
    market_status: Optional[str] = None,
    market_source: Optional[str] = None,
    snapshots_by_outcome_id: Optional[Mapping[int, Sequence[Any]]] = None,
    now: Optional[datetime] = None,
    max_pregame_age_hours: float = 6.0,
) -> dict[str, Any]:
    """Compute during-game movement for a series market against a labeled game-start baseline (#9715).

    Rules:
    1. **Settled states preserved**: when ``market_status`` is settled/closed or
       outcomes carry ``is_winner`` on a decided market, ``settled_state``
       (``"Won"`` / ``"Lost"``) is preserved and ``movement_since_baseline`` is
       ``None`` (``baseline_status == "settled_preserved"``).
    2. **Pre-game**: when ``event_status == "scheduled"`` (or ``now < game_start``),
       during-game movement is not computed (``baseline_status == "pre_game"``).
       Any ``opening_probability`` is kept under ``market_open_probability`` with
       ``market_open_label == "market open"`` — never conflated with game start.
    3. **During-game / post-start**: movement is computed ONLY for outcomes with a
       comparable timestamped snapshot in ``[game_start - max_pregame_age_hours,
       game_start]`` from the same venue. When found, the baseline is explicitly
       labeled ``baseline_kind = "game_start"``, ``baseline_label = "since game start"``.
       When absent, ``baseline_status = "missing_baseline"`` and
       ``movement_since_baseline = None`` (never falling back to ``opening_probability``
       or ``probability_change_24h``).
    """
    start_dt = _parse_utc(game_start)
    now_dt = _parse_utc(now)
    mkt_status_clean = str(market_status or "open").strip().lower()
    ev_status_clean = str(event_status or "").strip().lower()

    any_winner_flagged = any(
        isinstance(o, Mapping) and o.get("is_winner") is True for o in outcomes
    )
    market_is_settled = (
        mkt_status_clean in _SETTLED_MARKET_STATUSES or any_winner_flagged
    )

    is_pre_game = False
    if not market_is_settled:
        if ev_status_clean in ("scheduled", "upcoming", "pre_game"):
            if now_dt is None or start_dt is None or now_dt < start_dt:
                is_pre_game = True
        elif now_dt is not None and start_dt is not None and now_dt < start_dt:
            is_pre_game = True

    enriched_outcomes: list[dict[str, Any]] = []
    any_game_start_baseline = False
    earliest_baseline_at: Optional[datetime] = None

    for raw_out in outcomes:
        out = dict(raw_out)
        oid = out.get("outcome_id") or out.get("id")
        is_winner = out.get("is_winner")
        settled_flag = bool(out.get("settled")) or market_is_settled or (
            is_winner is False and any_winner_flagged
        )

        # Preserve explicit settled state (Won / Lost)
        if is_winner is True:
            settled_state: Optional[str] = "Won"
        elif is_winner is False and (market_is_settled or settled_flag):
            settled_state = "Lost"
        else:
            settled_state = None
        out["settled"] = settled_flag
        out["settled_state"] = settled_state

        # Record market-open baseline separately so it is never conflated with game start
        raw_open = out.get("opening_probability")
        if raw_open is not None:
            try:
                out["market_open_probability"] = round(float(raw_open), 4)
                out["market_open_label"] = "market open"
            except (TypeError, ValueError):
                out["market_open_probability"] = None
                out["market_open_label"] = None
        else:
            out["market_open_probability"] = None
            out["market_open_label"] = None

        # 1. Settled outcome or settled market: never overwrite with live movement
        if settled_state is not None or market_is_settled:
            out["baseline_status"] = "settled_preserved"
            out["baseline_kind"] = None
            out["baseline_label"] = None
            out["baseline_probability"] = None
            out["baseline_at"] = None
            out["movement_since_baseline"] = None
            out["movement_percentage_points"] = None
            enriched_outcomes.append(out)
            continue

        # 2. Pre-game: game has not started yet
        if is_pre_game or start_dt is None:
            out["baseline_status"] = (
                "pre_game" if is_pre_game else "missing_baseline"
            )
            out["baseline_kind"] = None
            out["baseline_label"] = None
            out["baseline_probability"] = None
            out["baseline_at"] = None
            out["movement_since_baseline"] = None
            out["movement_percentage_points"] = None
            enriched_outcomes.append(out)
            continue

        # 3. During-game / post-start: look up comparable timestamped snapshot at/before game_start
        snaps = (
            snapshots_by_outcome_id.get(int(oid))
            if (
                snapshots_by_outcome_id is not None
                and isinstance(oid, int)
            )
            else None
        )
        matched = (
            _select_game_start_snapshot(
                snaps,
                game_start=start_dt,
                market_source=market_source,
                max_pregame_age_hours=max_pregame_age_hours,
            )
            if snaps
            else None
        )
        cur_prob = out.get("probability")
        if matched is not None and cur_prob is not None:
            base_prob, base_ts = matched
            cur_val = float(cur_prob)
            delta = round(cur_val - base_prob, 4)
            out["baseline_status"] = "ok"
            out["baseline_kind"] = "game_start"
            out["baseline_label"] = "since game start"
            out["baseline_probability"] = round(base_prob, 4)
            out["baseline_at"] = base_ts.isoformat()
            out["movement_since_baseline"] = delta
            out["movement_percentage_points"] = round(delta * 100.0, 1)
            any_game_start_baseline = True
            if earliest_baseline_at is None or base_ts > earliest_baseline_at:
                earliest_baseline_at = base_ts
        else:
            out["baseline_status"] = "missing_baseline"
            out["baseline_kind"] = None
            out["baseline_label"] = None
            out["baseline_probability"] = None
            out["baseline_at"] = None
            out["movement_since_baseline"] = None
            out["movement_percentage_points"] = None

        enriched_outcomes.append(out)

    if market_is_settled:
        market_baseline_status = "settled_preserved"
    elif is_pre_game:
        market_baseline_status = "pre_game"
    elif any_game_start_baseline:
        market_baseline_status = "ok"
    else:
        market_baseline_status = "missing_baseline"

    return {
        "baseline_status": market_baseline_status,
        "baseline_kind": "game_start" if any_game_start_baseline else None,
        "baseline_label": "since game start" if any_game_start_baseline else None,
        "baseline_at": (
            earliest_baseline_at.isoformat()
            if earliest_baseline_at is not None
            else None
        ),
        "outcomes": enriched_outcomes,
    }


def _resolve_event_series_hub_metadata(
    event_id: Optional[int],
    *,
    series_hub_slug: Optional[str] = None,
    series_hub_href: Optional[str] = None,
    series_score_summary: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve the matching ``series_hub`` slug, collection href, and summary for ``event_id``."""
    slug = str(series_hub_slug).strip() if series_hub_slug else None
    href = str(series_hub_href).strip() if series_hub_href else None
    summary = str(series_score_summary).strip() if series_score_summary else None

    if slug is None and isinstance(event_id, int):
        try:
            rc = _rc()
            for prod in rc.ROUNDUP_PRODUCERS.values():
                rule = prod.rule if isinstance(prod.rule, Mapping) else {}
                if rule.get("producer") != PRODUCER_KIND_SERIES_HUB:
                    continue
                eids = [
                    int(eid)
                    for eid in (rule.get("event_ids") or ())
                    if isinstance(eid, int) or (isinstance(eid, str) and eid.isdigit())
                ]
                if event_id in eids:
                    slug = prod.slug
                    if href is None:
                        href = prod.destination_href or f"/collections/{prod.slug}"
                    if summary is None:
                        summary = prod.name
                    break
        except Exception:  # noqa: BLE001 — fallback to builtin definition
            slug = None

        if slug is None:
            builtin_rule = (
                MLB_2026_ALWC_BOS_NYY_DEFINITION.get("rule")
                if isinstance(MLB_2026_ALWC_BOS_NYY_DEFINITION.get("rule"), Mapping)
                else {}
            )
            builtin_eids = [
                int(eid)
                for eid in (builtin_rule.get("event_ids") or ())
                if isinstance(eid, int) or (isinstance(eid, str) and eid.isdigit())
            ]
            if event_id in builtin_eids:
                slug = MLB_2026_ALWC_BOS_NYY_SLUG
                if href is None:
                    href = f"/collections/{MLB_2026_ALWC_BOS_NYY_SLUG}"
                if summary is None:
                    summary = str(
                        MLB_2026_ALWC_BOS_NYY_DEFINITION.get("name")
                        or "Red Sox vs Yankees: AL Wild Card Series"
                    )

    if slug and href is None:
        href = f"/collections/{slug}"
    return slug, href, summary


def build_event_series_context(
    series_markets: Sequence[Mapping[str, Any]],
    *,
    event_id: Optional[int] = None,
    game_start: datetime | str | None = None,
    event_status: Optional[str] = None,
    snapshots_by_outcome_id: Optional[Mapping[int, Sequence[Any]]] = None,
    external_id_by_market_id: Optional[Mapping[int, Optional[str]]] = None,
    series_hub_slug: Optional[str] = None,
    series_hub_href: Optional[str] = None,
    series_score_summary: Optional[str] = None,
    now: Optional[datetime] = None,
    max_pregame_age_hours: float = 6.0,
) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    """Enrich an event's ``series_markets`` and build the coherent ``series_context`` summary (#9715).

    Returns ``(enriched_series_markets, series_context)``:
    - Orders markets by canonical family (``series_winner`` → ``exact_series_score``
      → ``series_total_games`` → ``series_spread`` → ``other_series``).
    - Attaches ``series_family``, ``series_family_label``, ``distribution_kind``,
      ``exhaustive``, ``normalize_to_unit_sum``, and ``sum_note`` to every market.
    - Attaches labeled game-start movement (``baseline_kind``, ``baseline_label``,
      ``baseline_status``, ``movement_since_baseline``) to every market and outcome.
    - Reports ``inventory_status`` (``"complete"`` when all 3 core families are
      present, ``"partial"`` when 1–2 are present, ``"empty"`` when none are
      present) and ``missing_families``.
    """
    if not series_hub_enabled():
        return [
            copy.deepcopy(dict(m))
            for m in series_markets
            if isinstance(m, Mapping)
        ], None
    enriched: list[dict[str, Any]] = []
    for raw_market in series_markets:
        if not isinstance(raw_market, Mapping):
            continue
        mkt = copy.deepcopy(dict(raw_market))
        mid = mkt.get("market_id") or mkt.get("id")
        ext_id = mkt.get("external_id") or (
            external_id_by_market_id.get(int(mid))
            if external_id_by_market_id is not None and isinstance(mid, int)
            else None
        )
        family = classify_series_market_family(
            mkt.get("market_name") or mkt.get("name"),
            external_id=ext_id,
            outcomes=mkt.get("outcomes") or (),
        )
        contract = series_family_distribution_contract(family)
        movement = compute_series_game_start_movement(
            mkt.get("outcomes") or (),
            game_start=game_start,
            event_status=event_status,
            market_status=mkt.get("status"),
            market_source=mkt.get("source"),
            snapshots_by_outcome_id=snapshots_by_outcome_id,
            now=now,
            max_pregame_age_hours=max_pregame_age_hours,
        )
        mkt.update(contract)
        mkt["baseline_status"] = movement["baseline_status"]
        mkt["baseline_kind"] = movement["baseline_kind"]
        mkt["baseline_label"] = movement["baseline_label"]
        mkt["baseline_at"] = movement["baseline_at"]
        mkt["outcomes"] = movement["outcomes"]
        enriched.append(mkt)

    enriched.sort(
        key=lambda m: (
            _FAMILY_SORT_ORDER.get(str(m.get("series_family")), 99),
            int(m.get("market_id") or m.get("id") or 0),
        )
    )

    families_present: list[str] = []
    markets_by_family: dict[str, list[dict[str, Any]]] = {}
    for mkt in enriched:
        fam = str(mkt.get("series_family") or FAMILY_OTHER_SERIES)
        if fam not in families_present:
            families_present.append(fam)
        markets_by_family.setdefault(fam, []).append(mkt)

    core_present = [f for f in CORE_SERIES_FAMILIES if f in families_present]
    missing_core = [f for f in CORE_SERIES_FAMILIES if f not in families_present]
    if len(core_present) == len(CORE_SERIES_FAMILIES):
        inventory_status = "complete"
    elif enriched:
        inventory_status = "partial"
    else:
        inventory_status = "empty"

    any_ok_baseline = any(m.get("baseline_status") == "ok" for m in enriched)
    all_settled = bool(enriched) and all(
        m.get("baseline_status") == "settled_preserved" for m in enriched
    )
    all_pre_game = bool(enriched) and all(
        m.get("baseline_status") == "pre_game" for m in enriched
    )
    if any_ok_baseline:
        overall_baseline_status = "ok"
    elif all_settled:
        overall_baseline_status = "settled_preserved"
    elif all_pre_game:
        overall_baseline_status = "pre_game"
    else:
        overall_baseline_status = "missing_baseline"

    resolved_slug, resolved_href, resolved_summary = (
        _resolve_event_series_hub_metadata(
            event_id,
            series_hub_slug=series_hub_slug,
            series_hub_href=series_hub_href,
            series_score_summary=series_score_summary,
        )
    )

    series_context = {
        "section_title": "Series Outlook",
        "series_hub_slug": resolved_slug,
        "series_hub_href": resolved_href,
        "series_score_summary": resolved_summary,
        "families_present": families_present,
        "core_families_present": core_present,
        "missing_families": missing_core,
        "inventory_status": inventory_status,
        "baseline_status": overall_baseline_status,
        "baseline_kind": "game_start" if any_ok_baseline else None,
        "baseline_label": "since game start" if any_ok_baseline else None,
        "game_start": (
            _parse_utc(game_start).isoformat()
            if _parse_utc(game_start) is not None
            else None
        ),
        "markets": enriched,
        "markets_by_family": markets_by_family,
    }
    return enriched, series_context


# ── Container Graph: First ``advances_to`` Writer (#12221 Stage 3) ───────────


@dataclass(frozen=True)
class SeriesAdvancementEdge:
    """Validated ``advances_to`` container-to-container bracket progression edge."""

    parent_id: int
    child_id: int
    parent_slug: str
    child_slug: str
    sport: str
    from_round: str
    to_round: str
    edge_kind: str = "advances_to"
    edge_class: None = None
    source: str = EDGE_SOURCE_REGISTER
    confidence: float = 1.0

    def to_edge_row(self) -> dict[str, Any]:
        """Return a row dict validated against ``app.utils.container_graph``."""
        validate_node_type(NODE_CONTAINER)
        validate_edge_kind_and_class(self.edge_kind, self.edge_class)
        validate_edge_source(self.source)
        validate_confidence(self.confidence)
        return {
            "parent_type": NODE_CONTAINER,
            "parent_id": int(self.parent_id),
            "child_type": NODE_CONTAINER,
            "child_id": int(self.child_id),
            "kind": self.edge_kind,
            "edge_class": self.edge_class,
            "source": self.source,
            "confidence": float(self.confidence),
            "parent_slug": self.parent_slug,
            "child_slug": self.child_slug,
            "sport": self.sport,
            "from_round": self.from_round,
            "to_round": self.to_round,
        }


def build_series_advances_to_edge(
    *,
    from_series_slug: str,
    to_series_slug: str,
    sport: str = "baseball_mlb",
    from_round: str = "WC",
    to_round: str = "DS",
    from_container_id: Optional[int] = None,
    to_container_id: Optional[int] = None,
    source: str = EDGE_SOURCE_REGISTER,
    confidence: float = 1.0,
) -> SeriesAdvancementEdge:
    """Build and validate a container-to-container ``advances_to`` edge (#12221 Stage 3).

    Supports MLB (Wild Card → Division Series → Championship Series → World Series),
    NBA (First Round → Conference Semifinals → Conference Finals → NBA Finals),
    and NHL (First Round → Second Round → Conference Finals → Stanley Cup Final).
    """
    clean_from = str(from_series_slug or "").strip()
    clean_to = str(to_series_slug or "").strip()
    if not clean_from or not clean_to:
        raise ValueError("build_series_advances_to_edge requires non-empty series slugs")
    if clean_from == clean_to:
        raise ValueError("A series container cannot advance to itself")

    validate_node_type(NODE_CONTAINER)
    validate_edge_kind_and_class("advances_to", None)
    validate_edge_source(source)
    validate_confidence(confidence)

    rc = _rc()
    parent_id = (
        int(from_container_id)
        if from_container_id is not None
        else rc.roundup_container_id(clean_from)
    )
    child_id = (
        int(to_container_id)
        if to_container_id is not None
        else rc.roundup_container_id(clean_to)
    )
    return SeriesAdvancementEdge(
        parent_id=parent_id,
        child_id=child_id,
        parent_slug=clean_from,
        child_slug=clean_to,
        sport=str(sport or "baseball_mlb").strip(),
        from_round=str(from_round or "").strip(),
        to_round=str(to_round or "").strip(),
        edge_kind="advances_to",
        edge_class=None,
        source=source,
        confidence=float(confidence),
    )


async def write_series_advances_to_edges(
    db: Any,
    edges: Sequence[SeriesAdvancementEdge | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate and write ``advances_to`` edges to ``event_edges`` (or an in-memory sink).

    First ``advances_to`` writer on the container graph (#12221 Stage 3):
    - Validates every edge via ``container_graph.validate_edge_kind_and_class("advances_to", None)``.
    - If ``db`` is a mutable list, appends the validated edge rows for inspection.
    - If ``db`` is an async SQLAlchemy session, upserts into ``event_edges``
      using ``uq_event_edge`` (``["parent_type", "parent_id", "child_type", "child_id", "kind"]``).
    """
    validated_rows: list[dict[str, Any]] = []
    for item in edges:
        if isinstance(item, SeriesAdvancementEdge):
            row = item.to_edge_row()
        elif isinstance(item, Mapping):
            edge_obj = build_series_advances_to_edge(
                from_series_slug=str(
                    item.get("parent_slug") or item.get("from_series_slug") or ""
                ),
                to_series_slug=str(
                    item.get("child_slug") or item.get("to_series_slug") or ""
                ),
                sport=str(item.get("sport") or "baseball_mlb"),
                from_round=str(item.get("from_round") or "WC"),
                to_round=str(item.get("to_round") or "DS"),
                from_container_id=item.get("parent_id") or item.get("from_container_id"),
                to_container_id=item.get("child_id") or item.get("to_container_id"),
                source=str(item.get("source") or EDGE_SOURCE_REGISTER),
                confidence=float(item.get("confidence", 1.0)),
            )
            row = edge_obj.to_edge_row()
        else:
            raise TypeError(f"Unsupported advancement edge item: {type(item)!r}")
        validated_rows.append(row)

    if isinstance(db, list):
        db.extend(validated_rows)
        return validated_rows

    if hasattr(db, "execute") and callable(db.execute) and validated_rows:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.models.models import EventEdge

        values = [
            {
                "parent_type": r["parent_type"],
                "parent_id": r["parent_id"],
                "child_type": r["child_type"],
                "child_id": r["child_id"],
                "kind": r["kind"],
                "class": r["edge_class"],
                "source": r["source"],
                "confidence": r["confidence"],
            }
            for r in validated_rows
        ]
        stmt = pg_insert(EventEdge).values(values).on_conflict_do_nothing(
            index_elements=["parent_type", "parent_id", "child_type", "child_id", "kind"]
        )
        await db.execute(stmt)

    return validated_rows


# ── Series Hub Selector & Producer (#9715) ───────────────────────────────────


def _resolve_best_of(sport: str, round_code: str, explicit_best_of: Any = None) -> int:
    if explicit_best_of is not None:
        try:
            val = int(explicit_best_of)
            if val in (3, 5, 7):
                return val
        except (TypeError, ValueError):
            # Fall back to the sport/round lookup table when explicit_best_of is not an int.
            pass
    sport_key = str(sport or "baseball_mlb").strip().lower()
    round_upper = str(round_code or "").strip().upper()
    sport_map = PLAYOFF_SERIES_BEST_OF_BY_SPORT.get(
        sport_key, PLAYOFF_SERIES_BEST_OF_BY_SPORT["baseball_mlb"]
    )
    return sport_map.get(round_upper, sport_map.get("DEFAULT", 7))


def _format_series_member_market(
    raw_market: Mapping[str, Any],
    *,
    game_start: Optional[datetime] = None,
    event_status: Optional[str] = None,
    snapshots_by_outcome_id: Optional[Mapping[int, Sequence[Any]]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Normalize a series market or prop/path market into a container member envelope."""
    card = copy.deepcopy(dict(raw_market))
    mid = int(card.get("id") or card.get("market_id") or 0)
    card.setdefault("id", mid)
    card.setdefault("market_id", mid)
    if "name" not in card and "market_name" in card:
        card["name"] = card["market_name"]
    if "market_name" not in card and "name" in card:
        card["market_name"] = card["name"]

    outcomes = list(card.get("outcomes") or ())
    tickers: dict[int, Optional[str]] = {}
    norm_outcomes: list[dict[str, Any]] = []
    for idx, raw_o in enumerate(outcomes):
        if not isinstance(raw_o, Mapping):
            continue
        o = dict(raw_o)
        oid = int(o.get("outcome_id") or o.get("id") or (mid * 100 + idx + 1))
        o["id"] = oid
        o["outcome_id"] = oid
        if "probability" not in o and o.get("current_probability") is not None:
            o["probability"] = float(o["current_probability"])
        ext_o = o.get("external_id")
        if isinstance(ext_o, str) and ext_o.strip():
            tickers[oid] = ext_o.strip()
        norm_outcomes.append(o)
    card["outcomes"] = norm_outcomes

    if tickers:
        relabel_series_card([card], tickers)
        card["name"] = card.get("market_name") or card.get("name")

    family = classify_series_market_family(
        card.get("name"),
        external_id=card.get("external_id"),
        outcomes=card.get("outcomes"),
    )
    contract = series_family_distribution_contract(family)
    card.update(contract)

    movement = compute_series_game_start_movement(
        card["outcomes"],
        game_start=game_start,
        event_status=event_status,
        market_status=card.get("status"),
        market_source=card.get("source"),
        snapshots_by_outcome_id=snapshots_by_outcome_id,
        now=now,
    )
    card["baseline_status"] = movement["baseline_status"]
    card["baseline_kind"] = movement["baseline_kind"]
    card["baseline_label"] = movement["baseline_label"]
    card["baseline_at"] = movement["baseline_at"]
    card["outcomes"] = movement["outcomes"]

    return {
        "type": MEMBER_MARKET,
        "id": mid,
        "destination": market_destination(mid),
        "card": card,
        "event_id": card.get("event_id"),
    }


def _format_series_member_event(
    raw_event: Mapping[str, Any],
    *,
    game_number: int,
    necessary: bool = True,
) -> dict[str, Any]:
    card = copy.deepcopy(dict(raw_event))
    eid = int(card.get("id") or card.get("event_id") or 0)
    card["id"] = eid
    card["series_game_number"] = game_number
    card["if_necessary"] = not necessary
    return {
        "type": MEMBER_EVENT,
        "id": eid,
        "destination": event_destination(eid),
        "card": card,
        "event_id": eid,
    }


def select_series_hub(
    fixture: Mapping[str, Any],
    *,
    rule: Mapping[str, Any],
    definition: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Any:
    """Pure selector assembling a playoff series hub container and Discover card (#9715).

    Assembles:
    1. **Series Games** (ordered chronologically, with series state and
       ``certain_to_be_played`` / ``if_necessary`` annotations).
    2. **Series Outlook** (the 3 core series families: ``series_winner``,
       ``exact_series_score``, ``series_total_games`` — with ``distribution_kind``
       and labeled game-start baseline movement).
    3. **Game & Series Props** (player/game props linked to the series games).
    4. **Championship & Pennant Path** (league pennant and championship futures
       for the two clubs, plus ``advances_to`` bracket progression metadata).
    """
    rc = _rc()
    defn = definition or {}
    sport = str(rule.get("sport") or fixture.get("sport") or "baseball_mlb").strip()
    round_code = str(rule.get("round") or fixture.get("round") or "WC").strip()
    best_of = _resolve_best_of(sport, round_code, rule.get("best_of") or fixture.get("best_of"))
    wins_needed = (best_of // 2) + 1

    team_a = str(rule.get("team_a") or fixture.get("team_a") or "Boston Red Sox").strip()
    team_b = str(rule.get("team_b") or fixture.get("team_b") or "New York Yankees").strip()

    raw_games = list(fixture.get("games") or ())
    raw_series_markets = list(fixture.get("series_markets") or ())
    raw_prop_markets = list(fixture.get("prop_markets") or ())
    raw_path_markets = list(fixture.get("path_markets") or ())
    snapshots_by_outcome_id = fixture.get("snapshots_by_outcome_id") or {}

    if not raw_games and not raw_series_markets:
        return rc.RoundupRefusal((("series_hub", "empty_series_inventory"),))

    # Sort games chronologically by commence_time then id
    sorted_games = sorted(
        [g for g in raw_games if isinstance(g, Mapping)],
        key=lambda g: (
            _parse_utc(g.get("commence_time"))
            or datetime(2026, 1, 1, tzinfo=timezone.utc),
            int(g.get("id") or g.get("event_id") or 0),
        ),
    )

    # Determine active/reference game for during-game baseline comparison
    active_game: Optional[Mapping[str, Any]] = None
    for g in sorted_games:
        st = str(g.get("status") or "").strip().lower()
        if st in _LIVE_EVENT_STATUSES:
            active_game = g
            break
    if active_game is None and sorted_games:
        active_game = sorted_games[0]

    active_game_start = (
        _parse_utc(active_game.get("commence_time"))
        if active_game is not None
        else None
    )
    active_event_status = (
        str(active_game.get("status") or "scheduled")
        if active_game is not None
        else "scheduled"
    )

    # Compute series score from completed games and format game members
    game_members: list[dict[str, Any]] = []
    wins_a, wins_b = 0, 0
    for idx, g in enumerate(sorted_games):
        game_num = idx + 1
        necessary, _reason = certain_to_be_played(
            PlayoffSeries(
                game_number=game_num,
                total_games=best_of,
                wins=(wins_a, wins_b),
                completed=(max(wins_a, wins_b) >= wins_needed),
            )
        )
        st = str(g.get("status") or "").strip().lower()
        if st in _FINISHED_EVENT_STATUSES:
            hs = g.get("home_score")
            as_ = g.get("away_score")
            if hs is not None and as_ is not None and hs != as_:
                winner_name = (
                    str(g.get("home_team") or g.get("home_team_name") or "")
                    if hs > as_
                    else str(g.get("away_team") or g.get("away_team_name") or "")
                )
                if team_a.lower() in winner_name.lower() or winner_name.lower() in team_a.lower():
                    wins_a += 1
                elif team_b.lower() in winner_name.lower() or winner_name.lower() in team_b.lower():
                    wins_b += 1
        # Keep unplayed games only while the series is not yet clinched
        if st not in _FINISHED_EVENT_STATUSES and max(wins_a, wins_b) >= wins_needed:
            continue
        game_members.append(
            _format_series_member_event(g, game_number=game_num, necessary=necessary)
        )

    # Format and classify the 3-family Series Outlook markets
    series_member_entries: list[dict[str, Any]] = []
    for m in raw_series_markets:
        if not isinstance(m, Mapping):
            continue
        series_member_entries.append(
            _format_series_member_market(
                m,
                game_start=active_game_start,
                event_status=active_event_status,
                snapshots_by_outcome_id=snapshots_by_outcome_id,
                now=now,
            )
        )
    series_member_entries.sort(
        key=lambda entry: (
            _FAMILY_SORT_ORDER.get(
                str(entry["card"].get("series_family")), 99
            ),
            int(entry["id"]),
        )
    )

    # Format Game & Series Props
    prop_member_entries: list[dict[str, Any]] = []
    for p in raw_prop_markets:
        if not isinstance(p, Mapping):
            continue
        prop_member_entries.append(
            _format_series_member_market(
                p,
                game_start=active_game_start,
                event_status=active_event_status,
                snapshots_by_outcome_id=snapshots_by_outcome_id,
                now=now,
            )
        )

    # Format Championship & Pennant Path markets
    path_member_entries: list[dict[str, Any]] = []
    for pm in raw_path_markets:
        if not isinstance(pm, Mapping):
            continue
        path_member_entries.append(
            _format_series_member_market(
                pm,
                game_start=active_game_start,
                event_status=active_event_status,
                snapshots_by_outcome_id=snapshots_by_outcome_id,
                now=now,
            )
        )

    sections: list[dict[str, Any]] = []
    if series_member_entries:
        sections.append(
            {
                "class": "title",
                "title": "Series Outlook",
                "layout": "field",
                "members": series_member_entries,
            }
        )
    if game_members:
        sections.append(
            {
                "class": "schedule",
                "title": "Series Games",
                "layout": "schedule",
                "members": game_members,
            }
        )
    if prop_member_entries:
        sections.append(
            {
                "class": "props",
                "title": "Series & Game Props",
                "layout": "field",
                "members": prop_member_entries,
            }
        )
    if path_member_entries:
        sections.append(
            {
                "class": "path",
                "title": "Championship & Pennant Path",
                "layout": "field",
                "members": path_member_entries,
            }
        )

    all_members: list[dict[str, Any]] = [
        *series_member_entries,
        *game_members,
        *prop_member_entries,
        *path_member_entries,
    ]
    if not all_members:
        return rc.RoundupRefusal((("series_hub", "no_series_members"),))

    # Build Discover card rows from Series Winner + Series Total Games + Next/Live Game
    card_rows: list[dict[str, Any]] = []
    for entry in series_member_entries:
        card = entry["card"]
        fam = card.get("series_family")
        outcomes = card.get("outcomes") or ()
        if fam == FAMILY_SERIES_WINNER and outcomes:
            priced_outcomes = [
                o for o in outcomes if o.get("probability") is not None
            ]
            if priced_outcomes:
                leader = max(
                    priced_outcomes, key=lambda o: float(o["probability"])
                )
                pct = round(float(leader["probability"]) * 100)
                card_rows.append(
                    {
                        "market_id": int(entry["id"]),
                        "label": f"Series Winner · {leader.get('name')}",
                        "probability": float(leader["probability"]),
                        "rendered_percent": pct,
                        "rendered_probability": f"{pct}%",
                        "series_family": fam,
                        "distribution_kind": card.get("distribution_kind"),
                        "baseline_kind": leader.get("baseline_kind"),
                        "baseline_label": leader.get("baseline_label"),
                        "movement_since_baseline": leader.get(
                            "movement_since_baseline"
                        ),
                        "destination": entry["destination"],
                    }
                )
        elif fam == FAMILY_EXACT_SERIES_SCORE and outcomes:
            priced_outcomes = [
                o for o in outcomes if o.get("probability") is not None
            ]
            if priced_outcomes:
                leader = max(
                    priced_outcomes, key=lambda o: float(o["probability"])
                )
                pct = round(float(leader["probability"]) * 100)
                card_rows.append(
                    {
                        "market_id": int(entry["id"]),
                        "label": f"Exact Score · {leader.get('name')}",
                        "probability": float(leader["probability"]),
                        "rendered_percent": pct,
                        "rendered_probability": f"{pct}%",
                        "series_family": fam,
                        "distribution_kind": card.get("distribution_kind"),
                        "baseline_kind": leader.get("baseline_kind"),
                        "baseline_label": leader.get("baseline_label"),
                        "movement_since_baseline": leader.get(
                            "movement_since_baseline"
                        ),
                        "destination": entry["destination"],
                    }
                )
        elif fam == FAMILY_SERIES_TOTAL_GAMES and outcomes:
            priced_outcomes = [
                o for o in outcomes if o.get("probability") is not None
            ]
            if priced_outcomes:
                rung = priced_outcomes[0]
                pct = round(float(rung["probability"]) * 100)
                card_rows.append(
                    {
                        "market_id": int(entry["id"]),
                        "label": str(rung.get("name") or "Over 2.5 total games"),
                        "probability": float(rung["probability"]),
                        "rendered_percent": pct,
                        "rendered_probability": f"{pct}%",
                        "series_family": fam,
                        "distribution_kind": card.get("distribution_kind"),
                        "baseline_kind": rung.get("baseline_kind"),
                        "baseline_label": rung.get("baseline_label"),
                        "movement_since_baseline": rung.get(
                            "movement_since_baseline"
                        ),
                        "destination": entry["destination"],
                    }
                )

    state_summary = series_state_label(
        wins_a, wins_b, games_to_win=wins_needed, team_name=team_a
    )
    footer = str(
        defn.get("footer")
        or f"{state_summary} · Best-of-{best_of} series"
    )
    slug = str(defn.get("slug") or MLB_2026_ALWC_BOS_NYY_SLUG)
    dest_href = str(
        rule.get("destination_href")
        or defn.get("destination_href")
        or f"/collections/{slug}"
    )
    series_clinched = max(wins_a, wins_b) >= wins_needed
    all_series_markets_settled = bool(series_member_entries) and all(
        str(entry["card"].get("status") or "").strip().lower()
        in _SETTLED_MARKET_STATUSES
        or entry["card"].get("baseline_status") == "settled_preserved"
        for entry in series_member_entries
    )
    suppress_feed_item = series_clinched or all_series_markets_settled

    return rc.RoundupMembers(
        members=all_members,
        rows=() if suppress_feed_item else card_rows[:4],
        footer=footer,
        count_line=f"{len(game_members)} games · {len(series_member_entries)} series markets",
        destination_href=dest_href,
        sections=sections,
        revision_ids=[int(m["id"]) for m in all_members],
        suppress_feed_item=suppress_feed_item,
    )


async def _load_series_hub_from_db(
    db: Any,
    rule: Mapping[str, Any],
) -> Any:
    """Load stored events, series markets, props, and path markets for a ``series_hub`` rule."""
    from sqlalchemy.ext.asyncio import AsyncSession

    rc = _rc()
    if not isinstance(db, AsyncSession):
        return rc.RoundupRefusal((("series_hub", "missing_db_session"),))

    from sqlalchemy import or_, select
    from sqlalchemy.orm import selectinload
    from app.models.models import Event, FuturesMarket, FuturesOddsSnapshot
    from app.routes.containers import _hydrate_event_cards

    event_ids = [
        int(eid)
        for eid in (rule.get("event_ids") or ())
        if isinstance(eid, int) or (isinstance(eid, str) and eid.isdigit())
    ]
    series_code = str(rule.get("series_code") or "").strip().upper()
    series_market_ids = [
        int(mid)
        for mid in (rule.get("series_market_ids") or ())
        if isinstance(mid, int) or (isinstance(mid, str) and mid.isdigit())
    ]
    prop_market_ids = [
        int(mid)
        for mid in (rule.get("prop_market_ids") or ())
        if isinstance(mid, int) or (isinstance(mid, str) and mid.isdigit())
    ]
    path_market_ids = [
        int(mid)
        for mid in (rule.get("path_market_ids") or ())
        if isinstance(mid, int) or (isinstance(mid, str) and mid.isdigit())
    ]

    games: list[dict[str, Any]] = []
    if event_ids:
        cards_by_id, _failed = await _hydrate_event_cards(db, event_ids)
        for eid in event_ids:
            if eid in cards_by_id:
                games.append(dict(cards_by_id[eid]))

    # Load series markets by series_code or explicit series_market_ids
    mkt_clauses = []
    if series_code:
        mkt_clauses.append(FuturesMarket.external_id.ilike(f"%{series_code}%"))
    if series_market_ids:
        mkt_clauses.append(FuturesMarket.id.in_(series_market_ids))
    if prop_market_ids:
        mkt_clauses.append(FuturesMarket.id.in_(prop_market_ids))
    if path_market_ids:
        mkt_clauses.append(FuturesMarket.id.in_(path_market_ids))
    if event_ids:
        mkt_clauses.append(FuturesMarket.event_id.in_(event_ids))

    series_markets: list[dict[str, Any]] = []
    prop_markets: list[dict[str, Any]] = []
    path_markets: list[dict[str, Any]] = []
    outcome_ids: list[int] = []

    if mkt_clauses:
        stmt = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(or_(*mkt_clauses))
            .order_by(FuturesMarket.id.asc())
        )
        res = await db.execute(stmt)
        rows = res.scalars().all() if hasattr(res, "scalars") else []
        for mkt in rows:
            mid = getattr(mkt, "id", None)
            if not isinstance(mid, int):
                continue
            outs = []
            for o in getattr(mkt, "outcomes", None) or ():
                oid = getattr(o, "id", None)
                if isinstance(oid, int):
                    outcome_ids.append(oid)
                outs.append(
                    {
                        "id": oid,
                        "outcome_id": oid,
                        "name": getattr(o, "name", None),
                        "external_id": getattr(o, "external_id", None),
                        "probability": (
                            float(o.current_probability)
                            if getattr(o, "current_probability", None) is not None
                            else None
                        ),
                        "opening_probability": (
                            float(o.opening_probability)
                            if getattr(o, "opening_probability", None) is not None
                            else None
                        ),
                        "probability_change_24h": (
                            float(o.probability_change_24h)
                            if getattr(o, "probability_change_24h", None) is not None
                            else None
                        ),
                        "is_winner": getattr(o, "is_winner", None),
                    }
                )
            serialized = {
                "id": mid,
                "market_id": mid,
                "name": getattr(mkt, "name", None),
                "market_name": getattr(mkt, "name", None),
                "external_id": getattr(mkt, "external_id", None),
                "source": getattr(mkt, "source", None),
                "status": getattr(mkt, "status", None),
                "event_id": getattr(mkt, "event_id", None),
                "outcomes": outs,
            }
            ext_upper = str(serialized["external_id"] or "").upper()
            if (
                mid in series_market_ids
                or (series_code and series_code in ext_upper)
                or classify_series_market_family(
                    serialized["name"], serialized["external_id"], outs
                )
                in CORE_SERIES_FAMILIES
            ):
                series_markets.append(serialized)
            elif mid in path_market_ids:
                path_markets.append(serialized)
            else:
                prop_markets.append(serialized)

    snapshots_by_outcome_id: dict[int, list[dict[str, Any]]] = {}
    active_game_start: Optional[datetime] = None
    for g in games:
        g_status = str(g.get("status") or "").strip().lower()
        if g_status in _LIVE_EVENT_STATUSES:
            active_game_start = _parse_utc(g.get("commence_time"))
            if active_game_start is not None:
                break

    if outcome_ids and active_game_start is not None:
        snap_window_start = active_game_start - timedelta(hours=6)
        snap_stmt = (
            select(FuturesOddsSnapshot)
            .distinct(FuturesOddsSnapshot.outcome_id)
            .where(
                FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
                FuturesOddsSnapshot.captured_at >= snap_window_start,
                FuturesOddsSnapshot.captured_at <= active_game_start,
            )
            .order_by(
                FuturesOddsSnapshot.outcome_id.asc(),
                FuturesOddsSnapshot.captured_at.desc(),
            )
        )
        snap_res = await db.execute(snap_stmt)
        snap_rows = snap_res.scalars().all() if hasattr(snap_res, "scalars") else []
        for s in snap_rows:
            oid = getattr(s, "outcome_id", None)
            if isinstance(oid, int):
                snapshots_by_outcome_id.setdefault(oid, []).append(
                    {
                        "probability": float(s.probability)
                        if getattr(s, "probability", None) is not None
                        else None,
                        "captured_at": getattr(s, "captured_at", None),
                        "bookmaker": getattr(s, "bookmaker", None),
                    }
                )

    if not games and not series_markets:
        return rc.RoundupRefusal((("series_hub", "no_stored_rows_found"),))

    return {
        "games": games,
        "series_markets": series_markets,
        "prop_markets": prop_markets,
        "path_markets": path_markets,
        "snapshots_by_outcome_id": snapshots_by_outcome_id,
    }


async def produce_series_hub(
    definition: Mapping[str, Any],
    db: Any,
    *,
    now: Optional[datetime] = None,
) -> Any:
    """Execute a ``series_hub`` container definition against ``db`` or an in-memory fixture."""
    if not series_hub_enabled():
        return _rc().RoundupRefusal((("series_hub", "series_hub_disabled"),))
    rule = (
        definition.get("rule")
        if isinstance(definition.get("rule"), Mapping)
        else {}
    )
    if isinstance(db, Mapping):
        fixture = db
    else:
        loaded = await _load_series_hub_from_db(db, rule)
        if not isinstance(loaded, Mapping):
            return loaded
        fixture = loaded

    return select_series_hub(
        fixture,
        rule=rule,
        definition=definition,
        now=now,
    )


def load_series_hub_definition(path: Path | str) -> dict[str, Any]:
    """Load and validate a stored ``series_hub`` definition JSON file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Container definition at {path} must be a JSON object")
    _validate_narrative_copy(
        str(raw.get("name") or ""),
        str(raw.get("footer") or ""),
        str(raw.get("kicker") or ""),
        str(raw.get("section_title") or ""),
    )
    return raw


def build_series_hub_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> Any:
    """Build a ``RoundupProducer`` from a declarative ``series_hub`` definition."""
    rule = definition.get("rule")
    if (
        not isinstance(rule, Mapping)
        or rule.get("producer") != PRODUCER_KIND_SERIES_HUB
    ):
        raise ValueError(
            f"Definition {definition.get('slug')!r} requires rule.producer={PRODUCER_KIND_SERIES_HUB!r}"
        )
    slug = str(definition["slug"])
    name = str(definition["name"])
    kind = str(definition.get("kind") or "roundup")
    membership = str(definition.get("membership") or PRODUCER_KIND_SERIES_HUB)
    category = str(definition.get("category") or "mlb")
    section_title = str(definition.get("section_title") or "Series Outlook")
    footer = str(
        definition.get("footer")
        or "Series winner and exact score are mutually exclusive; each total-games line stands on its own."
    )
    kicker = str(definition.get("kicker") or "PLAYOFF SERIES")
    _validate_narrative_copy(name, footer, kicker, section_title)
    tag = str(definition.get("tag") or category.upper())
    destination_href = str(
        rule.get("destination_href")
        or definition.get("destination_href")
        or f"/collections/{slug}"
    )
    order = str(rule.get("order") or "sequence")
    presentation = str(rule.get("presentation") or "series_hub")
    story_key = f"roundup:{slug.removeprefix('roundup-')}"
    frozen_def = dict(definition)
    frozen_def["rule"] = dict(rule)

    async def _produce(db: Any) -> Any:
        current_now = now_fn() if now_fn is not None else None
        return await produce_series_hub(frozen_def, db, now=current_now)

    return _rc().RoundupProducer(
        slug=slug,
        name=name,
        kind=kind,
        membership=membership,
        relations=definition.get("relations") or DEFAULT_SERIES_HUB_RELATIONS,
        level=definition.get("level") or DEFAULT_SERIES_HUB_LEVEL,
        rule=frozen_def["rule"],
        category=category,
        tag=tag,
        kicker=kicker,
        section_title=section_title,
        footer=footer,
        story_key=story_key,
        destination_href=destination_href,
        order=order,
        presentation=presentation,
        produce=_produce,
        enabled=enabled if enabled is not None else series_hub_enabled,
    )


async def mlb_2026_alwc_bos_nyy(
    db: Any,
    *,
    now: Optional[datetime] = None,
) -> Any:
    """Convenience entry point for the ``mlb-2026-alwc-bos-nyy`` series hub producer."""
    return await produce_series_hub(
        MLB_2026_ALWC_BOS_NYY_DEFINITION,
        db,
        now=now,
    )


MLB_2026_ALWC_BOS_NYY_DEFINITION: dict[str, Any] = (
    load_series_hub_definition(MLB_2026_ALWC_BOS_NYY_DEFINITION_PATH)
    if MLB_2026_ALWC_BOS_NYY_DEFINITION_PATH.exists()
    else {
        "slug": MLB_2026_ALWC_BOS_NYY_SLUG,
        "membership": PRODUCER_KIND_SERIES_HUB,
        "kind": "roundup",
        "relations": list(DEFAULT_SERIES_HUB_RELATIONS),
        "level": DEFAULT_SERIES_HUB_LEVEL,
        "kicker": "AL WILD CARD SERIES",
        "name": "Red Sox vs Yankees: AL Wild Card Series",
        "category": "mlb",
        "tag": "MLB",
        "section_title": "Series Outlook",
        "footer": "Series winner and exact score are mutually exclusive; each total-games line stands on its own.",
        "id_list_reason": "Verified production IDs on api.bainluck.com (#9715): Game 1 event 15319563 (2026-09-30, 0-9) and Game 2 event 15321907 (2026-10-01, 2-9, ESPN 401907963) found via GET /api/events/search?q=Yankees+Red+Sox&days_back=60 (Game 3 not played after 2-0 clinch); series markets 62383730 (Series Winner), 62455755 (Series Exact Score), and 62455756 (Series Total Games) verified via GET /api/futures/{id}; prop markets 63367383 (Payton Tolle Outs Recorded O/U 13.5 from GET /api/events/15319563/game-markets) and 63398300 (Ben Rice Home Runs O/U 0.5 from GET /api/events/15321907/game-markets) verified via GET /api/futures/{id}; path_market_ids empty.",
        "rule": {
            "producer": PRODUCER_KIND_SERIES_HUB,
            "sport": "baseball_mlb",
            "league": "mlb",
            "season": 2026,
            "round": "ALWC",
            "best_of": 3,
            "series_code": "26BOSNYYWC",
            "team_a": "Boston Red Sox",
            "team_b": "New York Yankees",
            "event_ids": [15319563, 15321907],
            "series_market_ids": [62383730, 62455755, 62455756],
            "prop_market_ids": [63367383, 63398300],
            "path_market_ids": [],
            "advances_to": {
                "to_series_slug": "mlb-2026-alds-yankees-guardians",
                "from_round": "ALWC",
                "to_round": "ALDS",
            },
            "order": "sequence",
            "presentation": "series_hub",
        },
    }
)

MLB_2026_ALWC_BOS_NYY_PRODUCER = build_series_hub_producer(
    MLB_2026_ALWC_BOS_NYY_DEFINITION
)

_rc().register_roundup_producer(MLB_2026_ALWC_BOS_NYY_PRODUCER)
