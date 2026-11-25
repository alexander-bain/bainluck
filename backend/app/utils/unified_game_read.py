"""Shared canonical game-chance read: one twin fold and one sportsbook read (#13508 / #13502).

Every endpoint that serves a game's win probabilities, source mark, or sportsbook
count MUST call :func:`load_unified_game_reads` (and, where formatting a card/brief,
:func:`resolve_unified_card_chance`) rather than running its own partial fold or
``OddsSnapshot`` query. A standing CI guard enforces that no mounted game-chance
endpoint bypasses this module.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import contains_eager

from app.models.models import Event, OddsSnapshot, Sport
from app.utils.draw_priced_winner import (
    printable_away,
    rendered_three_way_percents,
    resolve_three_way_probabilities,
    sport_prices_a_draw,
)
from app.utils.graded_card import rendered_duel_percents
from app.utils.event_completion import RETIRED_STATUSES
from app.utils.event_twin_fold import (
    _REVERSED_SAME_DAY_ANCHORED_CLAIM_LEAGUES,
    FoldResult,
    _group_is_id_anchored,
    fold_twin_events,
)
from app.utils.hero_probability import resolve_hero
from app.utils.kalshi_occurrence_start import loaded_sport_key
from app.utils.odds_filtering import filter_stale_bookmaker_snapshots
from app.utils.odds_math import aggregate_bookmaker_odds, detect_reversed_bookmakers
from app.utils import proven_duplicates as _pd_mod
from app.utils import serve_fold_absorbed as _serve_fold_mod
from app.utils.settled_hero import is_finished_status, settled_current_chance
from app.utils.source_mark import headline_source_marks, no_source_mark

logger = logging.getLogger(__name__)

# Canonical census registry: every mounted non-admin GET route returning game
# win chances must route through `load_unified_game_reads` (verified by
# `tests/test_unified_game_chance_registry_13508.py`).
UNIFIED_GAME_CHANCE_ADDRESSES: dict[str, tuple[str, ...]] = {
    "GET /api/events/{event_id}": ("app.routes.events", "get_event"),
    "GET /api/events": ("app.routes.events", "list_events"),
    "GET /api/events/search": ("app.routes.events", "search_events"),
    "GET /api/events/live": ("app.routes.events", "list_live_events"),
    "GET /api/events/highlights": ("app.routes.events", "get_highlights"),
    "GET /api/events/pulse-rankings": ("app.routes.events", "get_ei_rankings"),
    "GET /api/events/ei-rankings": ("app.routes.events", "get_ei_rankings"),
    "GET /api/events/faceted": ("app.routes.events", "faceted_search"),
    "GET /api/leagues/{sport_key}": ("app.routes.league_futures", "build_league"),
    "GET /api/feed": ("app.routes.feed", "_score_events"),
    "GET /api/feed/price-cards": ("app.routes.feed_prices", "_event_cards"),
    "GET /api/teams/{identifier}": ("app.routes.teams", "_folded_briefs"),
    "GET /api/containers/{slug}": ("app.routes.containers", "_assemble_event_cards"),
    "GET /api/containers/{slug}/preview": ("app.routes.containers", "_assemble_event_cards"),
    "GET /api/tournaments/{slug}": ("app.routes.tournaments", "_load_blends"),
    "GET /api/tournaments/by-event/{event_id}": ("app.routes.tournaments", "_load_blends"),
    "GET /api/march-madness/mens": ("app.routes.march_madness", "_process_bracket"),
    "GET /api/march-madness/womens": ("app.routes.march_madness", "_process_bracket"),
}

# Routes that touch Event objects without serving game win chances, or share the
# underlying event-page fold directly (SSE stream).
UNIFIED_GAME_CHANCE_EXEMPTIONS: dict[str, str] = {
    "GET /api/events/typeahead": "name/status autocomplete only; no chance fields",
    "GET /api/events/search-suggestions": "tag/team autocomplete suggestions only",
    "GET /api/events/{event_id}/debug": "diagnostic snapshot inspector dumping raw rows",
    "GET /api/events/{event_id}/stream": "SSE delta stream; already shares serve_fold_absorbed_rows + folded_series_event_ids",
    "GET /api/events/{event_id}/history": "time-series chart endpoint; uses folded_series_event_ids + serve_fold_absorbed_rows",
    "GET /api/events/{event_id}/props": "player prop markets endpoint",
    "GET /api/events/{event_id}/publications": "publication audit endpoint using serve_fold_absorbed_rows",
    "GET /api/events/{event_id}/injuries": "injury report only",
    "GET /api/events/{event_id}/related": "related futures/news links only",
    "GET /api/events/live-odds/{sport_key}": "raw Odds API diagnostic passthrough",
    "GET /api/events/sports/list": "sport catalog metadata only",
    "GET /api/events/teams/search": "team search metadata only",
    "GET /api/futures/{market_id}/related-events": "emits fixtures/scores/linked_teams only; zero probability fields",
}


@dataclass
class UnifiedGameRead:
    """Folded sources, absorbed IDs, and aggregated sportsbook state for one event."""

    event: Any
    folded_sources: dict | None
    folded_opening: tuple[Any, Any] | None
    blend_view: _pd_mod.FoldedBlendView
    blend_fold_revision: dict[str, int] | None = None
    absorbed_rows: list[Any] = field(default_factory=list)
    absorbed_ids: tuple[int, ...] = ()
    latest_raw_snapshots: list[Any] = field(default_factory=list)
    latest_snapshots: list[Any] = field(default_factory=list)
    odds_data: dict[str, Any] | None = None
    three_way_books: tuple[float, float] | None = None
    bookmaker_count: int = 0


@dataclass
class UnifiedGameReadBatch:
    """Batch output from :func:`load_unified_game_reads`."""

    events: list[Any]
    by_id: dict[int, UnifiedGameRead]
    fold_result: FoldResult
    folded_card_map: dict[int, _pd_mod.FoldedCardNumbers]
    odds_map: dict[int, dict[str, Any]]
    complete: bool = True


@dataclass(frozen=True)
class UnifiedCardChance:
    """Resolved win probabilities, rendered percents, source marks, and book count."""

    home_probability: float | None
    away_probability: float | None
    draw_probability: float | None
    home_rendered_percent: int | None
    away_rendered_percent: int | None
    draw_rendered_percent: int | None
    source_mark: dict
    away_source_mark: dict
    hero: Any | None
    effective_hero: Any | None
    hero_source_inputs: list[tuple[str, float]]
    hero_source_method: list[str]
    bookmaker_count: int


def _is_sqlite_session(db: Any) -> bool:
    """Return True only when backed by a concrete SQLite SQLAlchemy dialect."""
    for candidate in (
        db,
        getattr(db, "_session", None),
        getattr(db, "base", None),
        getattr(db, "sync_session", None),
    ):
        bind = getattr(candidate, "bind", None) if candidate is not None else None
        dialect = getattr(bind, "dialect", None)
        if getattr(dialect, "name", None) == "sqlite":
            return True
    return False


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _sync_folded_betting_book_count(
    merged: dict | None,
    canonical_sources: dict | None,
    twin_bags: Sequence[dict | None],
) -> dict | None:
    """Preserve a twin's ``betting_book_count`` when the fold adopted its ``betting`` leg."""
    if not isinstance(merged, dict):
        return merged
    if "betting" not in merged:
        return merged
    if _positive_int(merged.get("betting_book_count")) is not None:
        return merged
    from app.utils.aggregation import parse_source_entry

    if (
        isinstance(canonical_sources, dict)
        and parse_source_entry(canonical_sources.get("betting"))[0] is not None
    ):
        return merged
    for bag in twin_bags:
        if not isinstance(bag, dict):
            continue
        if parse_source_entry(bag.get("betting"))[0] is None:
            continue
        cnt = _positive_int(bag.get("betting_book_count"))
        if cnt is not None:
            out = dict(merged)
            out["betting_book_count"] = cnt
            return out
    return merged


def _default_odds_query_fn():
    from app.routes.events import latest_odds_per_bookmaker_query

    return latest_odds_per_bookmaker_query


def _empty_fold_result(events: Sequence[Any]) -> FoldResult:
    return FoldResult(
        events=list(events),
        merged_sources={},
        dropped_ids=[],
        survivor_of={},
        merged_opening={},
        flipped_loser_ids=set(),
    )


def _extract_sport_pairs(rows: Sequence[Any]) -> list[tuple[int, str]]:
    pairs: list[tuple[int, str]] = []
    for r in rows:
        if hasattr(r, "home_team_name"):
            continue
        if hasattr(r, "id") and hasattr(r, "key"):
            sid, sk = r.id, r.key
        elif isinstance(r, (tuple, list)) and len(r) == 2:
            sid, sk = r[0], r[1]
        else:
            continue
        if (
            isinstance(sid, int)
            and not isinstance(sid, bool)
            and isinstance(sk, str)
            and sk
        ):
            pairs.append((sid, sk))
    return pairs


async def _fetch_external_candidates_batch(
    db: Any,
    events: list[Any],
    *,
    sport_key_fallback: str | None,
    include_same_league_external: bool,
) -> tuple[list[Any], bool]:
    """Read untagged catch-all, cross-board, and external same-league twins in O(1) SQL."""
    page_ids = {int(e.id) for e in events if getattr(e, "id", None) is not None}
    if not page_ids:
        return [], True

    by_group: dict[tuple[str, bool], list[Any]] = {}
    all_target_keys: set[str] = set()
    other_prefixes: set[str] = set()
    same_day_leagues: set[str] = set()

    for ev in events:
        sk = loaded_sport_key(ev) or sport_key_fallback
        ct = getattr(ev, "commence_time", None)
        if not sk or not isinstance(ct, datetime):
            continue
        if not getattr(ev, "home_team_name", None) or not getattr(ev, "away_team_name", None):
            continue
        extra_keys = _serve_fold_mod._extra_foldable_sport_keys(sk)
        if include_same_league_external:
            extra_keys = [sk, *[k for k in extra_keys if k != sk]]
        is_catchall = sk.endswith("_other")
        if is_catchall:
            other_prefixes.add(_serve_fold_mod._sport_prefix(sk))
        for k in extra_keys:
            all_target_keys.add(k)
        anchored_claim = (
            sk in _REVERSED_SAME_DAY_ANCHORED_CLAIM_LEAGUES
            and _group_is_id_anchored([ev])
        )
        if anchored_claim:
            same_day_leagues.add(sk)
        by_group.setdefault((sk, anchored_claim), []).append(ev)

    if not by_group:
        return [], True

    # Single compact lookup on `sports` so leagues without catch-all/sibling rows
    # pay zero Event queries (and SQLite team-page tests with 1 sport stay fast).
    sport_clauses: list[Any] = []
    if all_target_keys:
        sport_clauses.extend(Sport.key == k for k in sorted(all_target_keys))
    for prefix in sorted(other_prefixes):
        sport_clauses.append(Sport.key.like(f"{prefix}%"))
    if not sport_clauses:
        return [], True

    if other_prefixes:
        sp_stmt = select(Sport.id, Sport.key).where(or_(*sport_clauses))
        sp_rows = (await db.execute(sp_stmt)).all()
    else:
        sp_stmt = select(Sport).where(or_(*sport_clauses))
        sp_rows = (await db.execute(sp_stmt)).scalars().all()
        if not sp_rows:
            return [], True

    key_to_sport_id: dict[str, int] = {}
    prefix_to_sport_ids: dict[str, list[int]] = {}
    for sid, sk in _extract_sport_pairs(sp_rows):
        key_to_sport_id[sk] = sid
        prefix_to_sport_ids.setdefault(_serve_fold_mod._sport_prefix(sk), []).append(sid)

    group_clauses: list[Any] = []
    for (sk, anchored_claim), group_evs in by_group.items():
        if sk.endswith("_other"):
            sids = sorted(
                set(prefix_to_sport_ids.get(_serve_fold_mod._sport_prefix(sk), []))
            )
        else:
            tkeys = _serve_fold_mod._extra_foldable_sport_keys(sk)
            if include_same_league_external:
                tkeys = [sk, *[k for k in tkeys if k != sk]]
            sids = sorted({key_to_sport_id[k] for k in tkeys if k in key_to_sport_id})
        if not sids:
            continue
        commence_times = [
            ct for e in group_evs if isinstance((ct := getattr(e, "commence_time", None)), datetime)
        ]
        if not commence_times:
            continue
        time_pred = _serve_fold_mod._coalesced_list_time_predicate(commence_times)
        group_clauses.append(and_(Event.sport_id.in_(sids), time_pred))
        if anchored_claim and sk in key_to_sport_id:
            claim_preds = [
                _serve_fold_mod._same_day_idless_claim_predicate(ct)
                for ct in {ct for ct in commence_times}
            ]
            group_clauses.append(
                and_(
                    Event.sport_id == key_to_sport_id[sk],
                    or_(*claim_preds),
                )
            )

    if not group_clauses:
        return [], True

    batch_cap = _serve_fold_mod.CANDIDATE_CAP * 4
    stmt = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(contains_eager(Event.sport))
        .where(
            Event.id.notin_(sorted(page_ids)),
            Event.status.notin_(list(RETIRED_STATUSES)),
            _pd_mod.not_a_proven_duplicate(),
            _serve_fold_mod._has_priced_signal_predicate(),
            or_(*group_clauses),
        )
        .limit(batch_cap)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    extras = [
        r for r in rows if getattr(r, "id", None) is not None and int(r.id) not in page_ids
    ]
    return extras, len(rows) < batch_cap


def _absorb_external_without_dropping_page(
    events: list[Any],
    page_ids: set[int],
    inner: FoldResult,
    extra_by_id: dict[int, Any],
    *,
    fold_fn=fold_twin_events,
) -> tuple[FoldResult, dict[int, list[Any]]]:
    """Attach external twin absorptions to each surviving/kept page event cleanly."""
    absorbed_by_survivor: dict[int, list[Any]] = {}
    extra_ids = set(extra_by_id)

    # First resolve which page events survive vs collapse using _keep_page_survivor,
    # ensuring no external *_other row ever replaces a page event.
    kept = _serve_fold_mod._keep_page_survivor(events, page_ids, inner, fold_fn=fold_fn)
    kept_by_id = {int(e.id): e for e in kept.events if getattr(e, "id", None) is not None}

    # Build direct clusters from `inner` so external candidates absorbed directly
    # into a cluster (whether the page row or the external row won `_elect`)
    # attach to the kept page survivor with corner-flip tracking preserved.
    cluster_members: dict[int, list[int]] = {}
    for lid, sid in inner.survivor_of.items():
        cluster_members.setdefault(int(sid), [int(sid)]).append(int(lid))
    for sid, mems in cluster_members.items():
        page_winner_id: int | None = None
        if sid in kept_by_id:
            page_winner_id = sid
        else:
            for m in mems:
                if m in kept_by_id:
                    page_winner_id = m
                    break
        if page_winner_id is None:
            continue
        winner_flipped_vs_cluster = page_winner_id in inner.flipped_loser_ids
        rows_for_winner: list[Any] = []
        for mid in sorted(set(mems)):
            if mid == page_winner_id or mid not in extra_ids:
                continue
            ext_row = extra_by_id[mid]
            member_flipped = (mid in inner.flipped_loser_ids) != winner_flipped_vs_cluster
            if member_flipped:
                setattr(ext_row, "_serve_fold_corner_flipped", True)
            rows_for_winner.append(ext_row)
        if rows_for_winner:
            absorbed_by_survivor[page_winner_id] = rows_for_winner

    return kept, absorbed_by_survivor


async def _fetch_odds_snapshots(
    db: Any,
    odds_query_ids: list[int],
    odds_query_fn: Any,
    *,
    single_event: bool = False,
) -> list[Any]:
    if not odds_query_ids:
        return []
    if _is_sqlite_session(db):
        stmt = (
            select(OddsSnapshot)
            .where(OddsSnapshot.event_id.in_(odds_query_ids))
            .order_by(OddsSnapshot.captured_at.desc(), OddsSnapshot.id.desc())
        )
        rows = list((await db.execute(stmt)).scalars().all())
    else:
        rows = list((await db.execute(odds_query_fn(odds_query_ids))).scalars().all())
    return [
        s
        for s in rows
        if not isinstance(s, (Event, Sport))
        and isinstance(getattr(s, "bookmaker", None), str)
        and isinstance(getattr(s, "captured_at", None), datetime)
        and (single_event or isinstance(getattr(s, "event_id", None), int))
    ]


async def load_unified_game_reads(
    db: Any,
    events: Sequence[Any],
    *,
    sport_key: str | None = None,
    collapse_in_page: bool = True,
    include_same_league_external: bool = True,
    include_odds: bool = True,
    odds_event_id_filter: set[int] | None = None,
    include_live_projections: bool = False,
    include_recent_projections: bool = False,
    include_fold_revision: bool = False,
    include_series_fold_ids: bool = False,
    post_fold_filter_fn: Callable[[list[Any]], Awaitable[list[Any]]] | None = None,
    fold_fn=fold_twin_events,
    fold_card_fn=None,
    fold_sources_fn=None,
    fold_revision_fn=None,
    odds_query_fn=None,
    on_stage: Callable[[str], None] | None = None,
    stage_timer_fn: Callable[[str], Any] | None = None,
    fault_tolerant_external: bool = False,
    fault_tolerant_odds: bool = False,
    now: datetime | None = None,
) -> UnifiedGameReadBatch:
    """Load canonical folded sources and sportsbook consensus for a page of events."""
    ev_list = list(events)
    if not ev_list:
        return UnifiedGameReadBatch(
            events=[],
            by_id={},
            fold_result=_empty_fold_result([]),
            folded_card_map={},
            odds_map={},
            complete=True,
        )

    def _stage_ctx(stage_name: str):
        return stage_timer_fn(stage_name) if stage_timer_fn is not None else nullcontext()

    clock_now = now or datetime.now(timezone.utc)
    complete = True
    runtime_absorbed_rows: dict[int, list[Any]] = {}
    fold_result = _empty_fold_result(ev_list)

    # 1. External + runtime twin fold
    if len(ev_list) == 1 and not collapse_in_page and include_same_league_external:
        ev0 = ev_list[0]
        try:
            abs_rows, complete = await _serve_fold_mod.serve_fold_absorbed_rows_with_completeness(
                db, ev0
            )
            if abs_rows:
                runtime_absorbed_rows[int(ev0.id)] = abs_rows
        except Exception:
            if not fault_tolerant_external:
                raise
            logger.exception(
                "unified game read: external fold failed for event %s",
                getattr(ev0, "id", None),
            )
            complete = False
    else:
        extras: list[Any] = []
        try:
            extras, complete = await _fetch_external_candidates_batch(
                db,
                ev_list,
                sport_key_fallback=sport_key,
                include_same_league_external=include_same_league_external,
            )
        except Exception:
            if not fault_tolerant_external:
                raise
            logger.exception("unified game read: batch external candidate lookup failed")
            complete = False

        try:
            if extras:
                page_ids = {
                    int(e.id) for e in ev_list if getattr(e, "id", None) is not None
                }
                extra_by_id = {int(r.id): r for r in extras}
                if collapse_in_page:
                    inner = fold_fn(ev_list + extras)
                    fold_result, runtime_absorbed_rows = _absorb_external_without_dropping_page(
                        ev_list, page_ids, inner, extra_by_id, fold_fn=fold_fn
                    )
                    ev_list = list(fold_result.events)
                else:
                    # Preserve every requested event slot (e.g. mixed team/container/
                    # league rails that already chose their cards) while folding extras.
                    for ev in ev_list:
                        eid = getattr(ev, "id", None)
                        if eid is None:
                            continue
                        inner = fold_fn([ev, *extras])
                        _kept, ext_map = _absorb_external_without_dropping_page(
                            [ev], {int(eid)}, inner, extra_by_id, fold_fn=fold_fn
                        )
                        if int(eid) in ext_map:
                            runtime_absorbed_rows[int(eid)] = ext_map[int(eid)]
            elif collapse_in_page:
                fold_result = fold_fn(ev_list)
                ev_list = list(fold_result.events)
        except Exception:
            if not fault_tolerant_external:
                raise
            logger.exception("unified game read: twin fold failed; keeping unfolded page")

    if on_stage is not None:
        on_stage("event_twin_fold")

    if post_fold_filter_fn is not None and ev_list:
        ev_list = list(await post_fold_filter_fn(ev_list))

    # Build in-page non-flipped loser map alongside external absorbed rows
    all_page_by_id = {int(e.id): e for e in events if getattr(e, "id", None) is not None}
    flipped_losers = set(getattr(fold_result, "flipped_loser_ids", None) or ())
    inpage_absorbed_by_surv: dict[int, list[Any]] = {}
    for loser_id, surv_id in (getattr(fold_result, "survivor_of", None) or {}).items():
        if int(loser_id) in all_page_by_id and int(surv_id) != int(loser_id):
            row = all_page_by_id[int(loser_id)]
            if int(loser_id) in flipped_losers:
                setattr(row, "_serve_fold_corner_flipped", True)
            inpage_absorbed_by_surv.setdefault(int(surv_id), []).append(row)

    # 2. Tagged duplicate fold (batched or with revision)
    folded_card_map: dict[int, _pd_mod.FoldedCardNumbers] = {}
    revisions_by_id: dict[int, dict[str, int] | None] = {}
    combined_absorbed_by_id: dict[int, list[Any]] = {}
    for ev in ev_list:
        eid = int(ev.id)
        seen_a: dict[int, Any] = {}
        for row in [
            *inpage_absorbed_by_surv.get(eid, ()),
            *runtime_absorbed_rows.get(eid, ()),
        ]:
            seen_a.setdefault(int(row.id), row)
        combined_absorbed_by_id[eid] = [seen_a[k] for k in sorted(seen_a)]

    if include_fold_revision:
        rev_loader = fold_revision_fn or _pd_mod.folded_probability_sources_with_revision
        for ev in ev_list:
            eid = int(ev.id)
            abs_for_ev = combined_absorbed_by_id.get(eid, ())
            non_flipped_abs = [
                r for r in abs_for_ev if not _pd_mod.is_corner_flipped_absorbed(r)
            ]
            flipped_abs_ids = {
                int(r.id) for r in abs_for_ev if _pd_mod.is_corner_flipped_absorbed(r)
            }
            try:
                sources, rev = await rev_loader(db, ev, abs_for_ev)
            except Exception:
                if not fault_tolerant_external:
                    raise
                logger.exception(
                    "unified game read: revision fold failed for event %s; "
                    "keeping own/runtime sources",
                    eid,
                )
                complete = False
                oriented_pairs_fb: list[tuple[int, dict | None]] = []
                for abs_row in abs_for_ev:
                    raw_bag = getattr(abs_row, "win_probability_sources", None)
                    if _pd_mod.is_corner_flipped_absorbed(abs_row) and raw_bag:
                        ok, turned = _pd_mod.flip_probability_sources(raw_bag)
                        oriented_bag = turned if ok else None
                    else:
                        oriented_bag = raw_bag
                    oriented_pairs_fb.append((int(abs_row.id), oriented_bag))
                sources = (
                    _pd_mod.merge_probability_sources(
                        getattr(ev, "win_probability_sources", None),
                        oriented_pairs_fb,
                        event_status=getattr(ev, "status", None),
                        now=clock_now,
                    )
                    if oriented_pairs_fb
                    else getattr(ev, "win_probability_sources", None)
                )
                rev = None

            if include_series_fold_ids:
                try:
                    series_ids = await _pd_mod.folded_series_event_ids(db, eid, non_flipped_abs)
                except Exception:
                    if not fault_tolerant_external:
                        raise
                    logger.exception(
                        "unified game read: series fold ids failed for event %s",
                        eid,
                    )
                    complete = False
                    series_ids = [eid, *(int(r.id) for r in non_flipped_abs)]
                fold_abs_ids = tuple(
                    int(tid)
                    for tid in series_ids
                    if int(tid) != eid and int(tid) not in flipped_abs_ids
                )
            else:
                seen_ids: set[int] = set()
                fold_abs_list: list[int] = []
                if isinstance(rev, dict):
                    for raw_k in rev:
                        try:
                            kid = int(raw_k)
                        except (TypeError, ValueError):
                            continue
                        if (
                            kid != eid
                            and kid not in flipped_abs_ids
                            and kid not in seen_ids
                        ):
                            seen_ids.add(kid)
                            fold_abs_list.append(kid)
                for r in non_flipped_abs:
                    rid = int(r.id)
                    if rid != eid and rid not in seen_ids:
                        seen_ids.add(rid)
                        fold_abs_list.append(rid)
                fold_abs_ids = tuple(fold_abs_list)

            sources = _sync_folded_betting_book_count(
                sources,
                getattr(ev, "win_probability_sources", None),
                [getattr(r, "win_probability_sources", None) for r in abs_for_ev],
            )
            open_h = getattr(ev, "opening_home_probability", None)
            open_a = getattr(ev, "opening_away_probability", None)
            open_pairs = [
                (
                    int(r.id),
                    getattr(r, "opening_home_probability", None),
                    getattr(r, "opening_away_probability", None),
                )
                for r in non_flipped_abs
            ]
            merged_opening = (
                _pd_mod.merge_opening_line(open_h, open_a, open_pairs)
                if open_pairs
                else (open_h, open_a)
            )
            folded_card_map[eid] = _pd_mod.FoldedCardNumbers(
                win_probability_sources=sources,
                opening=merged_opening,
                absorbed_ids=fold_abs_ids,
            )
            revisions_by_id[eid] = rev
    else:
        if fold_sources_fn is not None:
            try:
                raw_sources_map = await fold_sources_fn(db, ev_list)
                folded_card_map = {
                    eid: _pd_mod.FoldedCardNumbers(
                        win_probability_sources=srcs,
                        opening=(None, None),
                        absorbed_ids=(),
                    )
                    for eid, srcs in (raw_sources_map or {}).items()
                }
            except Exception:
                if not fault_tolerant_external:
                    raise
                logger.exception(
                    "unified game read: tagged source fold failed; "
                    "keeping own/runtime sources"
                )
                complete = False
                folded_card_map = {}
        else:
            card_loader = fold_card_fn or _pd_mod.folded_card_numbers_batch
            try:
                folded_card_map = await card_loader(db, ev_list)
            except Exception:
                if not fault_tolerant_external:
                    raise
                logger.exception(
                    "unified game read: tagged card fold failed; "
                    "keeping own/runtime sources"
                )
                complete = False
                folded_card_map = {}

        # Merge tagged sources/opening + oriented runtime absorbed rows identically to get_event
        updated_card_map: dict[int, _pd_mod.FoldedCardNumbers] = {}
        for ev in ev_list:
            eid = int(ev.id)
            own_sources = getattr(ev, "win_probability_sources", None)
            card = folded_card_map.get(eid)
            base_sources = (
                card.win_probability_sources
                if card is not None and card.win_probability_sources is not None
                else own_sources
            )
            base_opening = (
                card.opening
                if card is not None
                else (
                    getattr(ev, "opening_home_probability", None),
                    getattr(ev, "opening_away_probability", None),
                )
            )
            if base_opening == (None, None) and (
                getattr(ev, "opening_home_probability", None) is not None
                or getattr(ev, "opening_away_probability", None) is not None
            ):
                base_opening = (
                    getattr(ev, "opening_home_probability", None),
                    getattr(ev, "opening_away_probability", None),
                )
            base_absorbed_ids = list((card.absorbed_ids if card is not None else ()) or ())

            absorbed_for_ev = combined_absorbed_by_id.get(eid, ())
            oriented_pairs: list[tuple[int, dict | None]] = []
            opening_pairs: list[tuple[int, object, object]] = []
            twin_bags: list[dict | None] = []
            seen_abs_ids = set(base_absorbed_ids)

            for abs_row in absorbed_for_ev:
                aid = int(abs_row.id)
                raw_bag = getattr(abs_row, "win_probability_sources", None)
                flipped = _pd_mod.is_corner_flipped_absorbed(abs_row)
                if flipped and raw_bag:
                    ok, turned = _pd_mod.flip_probability_sources(raw_bag)
                    oriented_bag = turned if ok else None
                else:
                    oriented_bag = raw_bag
                oriented_pairs.append((aid, oriented_bag))
                twin_bags.append(oriented_bag)
                if not flipped:
                    opening_pairs.append(
                        (
                            aid,
                            getattr(abs_row, "opening_home_probability", None),
                            getattr(abs_row, "opening_away_probability", None),
                        )
                    )
                    if aid not in seen_abs_ids:
                        base_absorbed_ids.append(aid)
                        seen_abs_ids.add(aid)

            merged_sources = (
                _pd_mod.merge_probability_sources(
                    base_sources,
                    oriented_pairs,
                    event_status=getattr(ev, "status", None),
                    now=clock_now,
                )
                if oriented_pairs
                else (dict(base_sources) if isinstance(base_sources, dict) else base_sources)
            )
            merged_sources = _sync_folded_betting_book_count(
                merged_sources, own_sources, twin_bags
            )
            merged_opening = (
                _pd_mod.merge_opening_line(base_opening[0], base_opening[1], opening_pairs)
                if opening_pairs
                else base_opening
            )
            updated_card_map[eid] = _pd_mod.FoldedCardNumbers(
                win_probability_sources=merged_sources,
                opening=merged_opening,
                absorbed_ids=tuple(base_absorbed_ids),
            )
        folded_card_map = updated_card_map

    # 3. Same-orientation absorbed IDs + unified sportsbook snapshot read
    owner_by_event_id: dict[int, int] = {}
    odds_query_ids: list[int] = []
    same_orient_ids_by_ev: dict[int, tuple[int, ...]] = {}

    for ev in ev_list:
        eid = int(ev.id)
        card = folded_card_map.get(eid)
        abs_ids: list[int] = []
        seen_tids: set[int] = set()
        for tid in (card.absorbed_ids if card is not None else ()) or ():
            itid = int(tid)
            if itid != eid and itid not in seen_tids:
                seen_tids.add(itid)
                abs_ids.append(itid)
        if not include_series_fold_ids:
            for row in combined_absorbed_by_id.get(eid, ()):
                if not _pd_mod.is_corner_flipped_absorbed(row):
                    itid = int(row.id)
                    if itid != eid and itid not in seen_tids:
                        seen_tids.add(itid)
                        abs_ids.append(itid)
        same_orient_ids_by_ev[eid] = tuple(abs_ids)

        if not include_odds:
            continue
        if odds_event_id_filter is not None and eid not in odds_event_id_filter:
            continue
        if eid not in owner_by_event_id:
            owner_by_event_id[eid] = eid
            odds_query_ids.append(eid)
        for tid in abs_ids:
            if tid not in owner_by_event_id:
                owner_by_event_id[tid] = eid
                odds_query_ids.append(tid)

    raw_snapshots_by_owner: dict[int, list[Any]] = {}
    latest_snaps_by_owner: dict[int, list[Any]] = {}
    odds_map: dict[int, dict[str, Any]] = {}

    _apply_live_line_projection = None
    _event_state_clock = None
    if include_live_projections:
        from app.utils.live_line_clock import (
            apply_live_line_projection as _apply_live_line_projection,
            event_state_clock as _event_state_clock,
        )

    if include_odds:
        with _stage_ctx("bookmaker_odds"):
            if odds_query_ids:
                query_fn = odds_query_fn or _default_odds_query_fn()
                raw_snapshots: list[Any] = []
                try:
                    raw_snapshots = await _fetch_odds_snapshots(
                        db,
                        odds_query_ids,
                        query_fn,
                        single_event=(len(ev_list) == 1),
                    )
                except Exception:
                    if not fault_tolerant_odds:
                        raise
                    logger.exception("unified game read: odds snapshot lookup failed")
                    raw_snapshots = []

                if on_stage is not None:
                    on_stage("event_odds_query")

                if len(ev_list) == 1:
                    eid0 = int(ev_list[0].id)
                    if raw_snapshots:
                        raw_snapshots_by_owner[eid0] = list(raw_snapshots)
                        deduped = _pd_mod.latest_snapshot_for_each_bookmaker(
                            raw_snapshots, eid0
                        )
                        if deduped:
                            latest_snaps_by_owner[eid0] = deduped
                else:
                    for snap in raw_snapshots:
                        seid = getattr(snap, "event_id", None)
                        if seid is None:
                            continue
                        owner = owner_by_event_id.get(int(seid))
                        if owner is not None:
                            raw_snapshots_by_owner.setdefault(owner, []).append(snap)

                    latest_snaps_by_owner = _pd_mod.group_latest_snapshots_by_event(
                        raw_snapshots, owner_by_event_id
                    )

                ev_by_id = {int(e.id): e for e in ev_list}
                for owner_id, snaps in latest_snaps_by_owner.items():
                    ev = ev_by_id.get(owner_id)
                    filtered_snaps = filter_stale_bookmaker_snapshots(
                        snaps,
                        event_status=(ev.status if ev is not None else "scheduled"),
                        commence_time=(ev.commence_time if ev is not None else None),
                    )
                    reversed_bks = detect_reversed_bookmakers(filtered_snaps)
                    agg_snaps = (
                        [s for s in filtered_snaps if s.bookmaker not in reversed_bks]
                        if reversed_bks
                        else filtered_snaps
                    )
                    if not agg_snaps:
                        agg_snaps = filtered_snaps
                    aggregated = aggregate_bookmaker_odds(agg_snaps)
                    if (
                        include_live_projections
                        and ev is not None
                        and _apply_live_line_projection is not None
                        and _event_state_clock is not None
                    ):
                        card = folded_card_map.get(owner_id)
                        bag_for_clock = (
                            card.win_probability_sources
                            if card is not None and card.win_probability_sources is not None
                            else getattr(ev, "win_probability_sources", None)
                        )
                        aggregated = _apply_live_line_projection(
                            aggregated,
                            agg_snaps,
                            now=clock_now,
                            state_changed_at=_event_state_clock(ev, bag_for_clock),
                        )
                    latest_time = max(
                        (
                            s.captured_at
                            for s in filtered_snaps
                            if getattr(s, "captured_at", None)
                        ),
                        default=None,
                    )
                    odds_map[owner_id] = {
                        "snapshots": filtered_snaps,
                        "all_snapshots": snaps,
                        "aggregated": aggregated,
                        "captured_at": latest_time,
                    }
            elif on_stage is not None and ev_list:
                on_stage("event_odds_query")

        if include_recent_projections:
            with _stage_ctx("recent_lines"):
                if odds_map:
                    from app.utils.recent_line_readings import (
                        apply_recent_line_projections,
                    )

                    proj_events = [e for e in ev_list if int(e.id) in odds_map]
                    if proj_events:
                        await apply_recent_line_projections(db, proj_events, odds_map)
    elif on_stage is not None and ev_list:
        on_stage("event_odds_query")

    if on_stage is not None:
        on_stage("event_odds_aggregate")

    by_id: dict[int, UnifiedGameRead] = {}
    for ev in ev_list:
        eid = int(ev.id)
        card = folded_card_map.get(eid)
        folded_sources = (
            card.win_probability_sources
            if card is not None
            else getattr(ev, "win_probability_sources", None)
        )
        folded_opening = (
            card.opening
            if card is not None
            and (card.opening[0] is not None or card.opening[1] is not None)
            else None
        )
        blend_view = _pd_mod.FoldedBlendView(ev, folded_sources, opening=folded_opening)
        odds_entry = odds_map.get(eid)
        three_way_books: tuple[float, float] | None = None
        bk_count = 0
        if odds_entry and isinstance(odds_entry.get("aggregated"), dict):
            agg = odds_entry["aggregated"]
            bh, ba = agg.get("home_probability"), agg.get("away_probability")
            if bh is not None and ba is not None:
                three_way_books = (float(bh), float(ba))
            bk_count = int(agg.get("bookmaker_count") or 0)
        by_id[eid] = UnifiedGameRead(
            event=ev,
            folded_sources=folded_sources,
            folded_opening=folded_opening,
            blend_view=blend_view,
            blend_fold_revision=revisions_by_id.get(eid),
            absorbed_rows=list(combined_absorbed_by_id.get(eid, ())),
            absorbed_ids=same_orient_ids_by_ev.get(eid, ()),
            latest_raw_snapshots=raw_snapshots_by_owner.get(eid, []),
            latest_snapshots=latest_snaps_by_owner.get(eid, []),
            odds_data=odds_entry,
            three_way_books=three_way_books,
            bookmaker_count=bk_count,
        )

    return UnifiedGameReadBatch(
        events=ev_list,
        by_id=by_id,
        fold_result=fold_result,
        folded_card_map=folded_card_map,
        odds_map=odds_map,
        complete=complete,
    )


def resolve_unified_card_chance(
    read: UnifiedGameRead,
    *,
    sport_key: str | None,
    served_status: str,
) -> UnifiedCardChance:
    """Resolve probabilities, rendered percents, source marks, and book count cleanly."""
    view = read.blend_view
    raw_wps = getattr(view, "win_probability_sources", None)
    if not isinstance(raw_wps, (dict, type(None))):
        view = _pd_mod.FoldedBlendView(view, None, opening=read.folded_opening)
    hero_inputs: list[tuple[str, float]] = []
    hero_method: list[str] = []
    hero = resolve_hero(view, source_inputs=hero_inputs, source_method=hero_method)
    draw_priced = sport_prices_a_draw(sport_key)
    finished = is_finished_status(served_status)

    if finished:
        sc = settled_current_chance(hero, sport_key=sport_key)
        home_mark, away_mark = headline_source_marks(
            view,
            hero,
            hero_inputs,
            method=hero_method[0] if hero_method else None,
        )
        if sc.resolved:
            return UnifiedCardChance(
                home_probability=sc.home_probability,
                away_probability=sc.away_probability,
                draw_probability=sc.draw_probability,
                home_rendered_percent=sc.home_rendered_percent,
                away_rendered_percent=sc.away_rendered_percent,
                draw_rendered_percent=sc.draw_rendered_percent,
                source_mark=home_mark,
                away_source_mark=away_mark,
                hero=hero,
                effective_hero=hero,
                hero_source_inputs=hero_inputs,
                hero_source_method=hero_method,
                bookmaker_count=read.bookmaker_count,
            )
        return UnifiedCardChance(
            home_probability=None,
            away_probability=None,
            draw_probability=None,
            home_rendered_percent=None,
            away_rendered_percent=None,
            draw_rendered_percent=None,
            source_mark=home_mark,
            away_source_mark=away_mark,
            hero=hero,
            effective_hero=hero,
            hero_source_inputs=hero_inputs,
            hero_source_method=hero_method,
            bookmaker_count=read.bookmaker_count,
        )

    effective_hero = hero
    home_prob = hero.home_probability if hero is not None else None
    away_prob = hero.away_probability if hero is not None else None
    draw_prob: float | None = None
    home_pct: int | None = None
    away_pct: int | None = None
    draw_pct: int | None = None
    three_way_tuple: tuple[float, float, float] | None = None

    # Match `get_event` Tier-3 fallback: a live game with `bookmaker_odds` but no
    # valid `win_probability_sources` falls back to its bookmaker consensus.
    if (
        home_prob is None
        and served_status == "live"
        and read.three_way_books is not None
    ):
        home_prob = round(float(read.three_way_books[0]), 6)
        away_prob = round(1.0 - home_prob, 6)

    if draw_priced:
        bh_ba = read.three_way_books
        if (
            bh_ba is None
            and hero is not None
            and hero.source == "opening"
            and getattr(view, "opening_home_probability", None) is not None
            and getattr(view, "opening_away_probability", None) is not None
        ):
            bh_ba = (
                float(view.opening_home_probability),
                float(view.opening_away_probability),
            )
        if bh_ba is not None:
            three_way_tuple = resolve_three_way_probabilities(
                home_prob,
                books_home=bh_ba[0],
                books_away=bh_ba[1],
                sport_key=sport_key,
            )
        if three_way_tuple is not None:
            home_prob, away_prob, draw_prob = three_way_tuple
            home_pct, draw_pct, away_pct = rendered_three_way_percents(
                home_prob, draw_prob, away_prob
            )
        else:
            home_prob = None
            away_prob = None
            draw_prob = None
            effective_hero = None
    elif home_prob is not None:
        away_prob = printable_away(away_prob, home_prob, sport_key)
        away_pct, home_pct = rendered_duel_percents(away_prob, home_prob)

    if hero is None and home_prob is None:
        home_mark = no_source_mark("no_probability")
        away_mark = no_source_mark("no_probability")
    elif effective_hero is None and draw_priced:
        home_mark = no_source_mark("no_probability")
        away_mark = no_source_mark("no_probability")
    else:
        home_mark, away_mark = headline_source_marks(
            view,
            effective_hero,
            hero_inputs,
            method=hero_method[0] if hero_method else None,
            away_available=away_prob is not None,
            three_way_probs=three_way_tuple,
            books_three_way=read.three_way_books,
        )

    return UnifiedCardChance(
        home_probability=home_prob,
        away_probability=away_prob,
        draw_probability=draw_prob,
        home_rendered_percent=home_pct,
        away_rendered_percent=away_pct,
        draw_rendered_percent=draw_pct,
        source_mark=home_mark,
        away_source_mark=away_mark,
        hero=hero,
        effective_hero=effective_hero,
        hero_source_inputs=hero_inputs,
        hero_source_method=hero_method,
        bookmaker_count=read.bookmaker_count,
    )
