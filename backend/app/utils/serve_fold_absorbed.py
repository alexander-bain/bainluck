"""The rows a serve-time fold absorbed into THIS event — for its own page (#3391).

WHAT A READER SAW. 2026-09-27 03:50Z, FC Dallas 1–0 LAFC, final. `/search?q=lafc`
printed the fixture once, as `15318170` — the ESPN row (espn_id 761835, a score,
0 markets). Its twin `15314003` (Odds API + StatPal anchors, same minute) held
121 Kalshi/Polymarket markets, the 43% pregame reading, 1,139 odds snapshots and
the whole chart. Tapping the one card opened a page with a score, WON, and
nothing else.

WHY BOTH HALVES WERE RIGHT AND THE PAGE WAS STILL EMPTY. `fold_twin_events`
(#4100) keeps the anchored, scored row on purpose (`twin_identity_rank`: the row
settlement and the chart can reach), and the card carries the loser's venues
through `merged_sources`. But that fold only ever runs over a LIST. The event
page has one row and nothing to fold it against, and its three endpoints read
twins only through `provenance:duplicate-of:` tags (`folded_event_ids`,
`folded_series_event_ids`, `folded_probability_sources`) — which a serve-time
pair never carries. So the card promised a game the page could not show.

WHAT THIS DOES. Hands the fold the page's row plus every row that could share a
fixture with it, and returns the rows the fold dropped INTO this one. The three
endpoints union those ids into the tag fold they already run. Nothing is
written, merged or repointed; this is the same read the card already made.

It returns nothing when this row LOSES the election. The loser's own page keeps
serving its own content, exactly as before — the election is not changed here,
and trading the anchor for the markets was ruled out on #3391.

ORIENTATION IS THE FOLD'S, NOT RE-CHECKED. `orientation_agrees` is a token-subset
test and refuses `LAFC` against `Los Angeles FC` — the specimen itself. The
fold's own licence already carries orientation (the strict key is `(away, home)`;
the soccer pass matches home to home and refuses the swap), and every list
surface already puts these rows' HOME probabilities on the survivor's card on
that licence (`merged_sources`, `_carry_opening_line`). Re-testing it here would
make the page refuse a number the card prints.

CANDIDATES, AND WHY THIS IS NOT THE WHOLE DAY. The fold can only pair rows in
one league (or a `*_other` catch-all of the same sport), and only at three
kinds of distance: within :data:`NEAR` (every drift bound in the fold is ≤25
minutes), one Kalshi expiration pad away (+180/+240 minutes, which
`recover_kalshi_occurrence_starts` puts back), or a date-only row at midnight.
A whole soccer window reads ~400 `soccer_other` rows on a Saturday; these arms
read the handful that could be this fixture.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.orm import contains_eager, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.models.models import Event, Sport
from app.utils.event_completion import RETIRED_STATUSES
from app.utils.event_twin_fold import (
    _REVERSED_SAME_DAY_ANCHORED_CLAIM_LEAGUES,
    CROSS_BOARD_TWIN_KEYS,
    FoldResult,
    _catchall_sport_prefix,
    _group_is_id_anchored,
    cross_board_identity,
    fold_twin_events,
    twin_identity_rank,
)
from app.utils.kalshi_occurrence_start import loaded_sport_key
from app.utils.proven_duplicates import (
    flip_probability_sources,
    merge_probability_sources,
    not_a_proven_duplicate,
)
from app.utils.sport_keys import league_identity

logger = logging.getLogger(__name__)

#: Covers every pairwise drift bound in the fold, the widest being
#: `SETTLED_SOCCER_KICKOFF_DRIFT` (25 min).
NEAR = timedelta(minutes=30)

#: A Kalshi-timed row sits 180 (`…GAME`) or 240 (`…TOTAL`) minutes after the
#: kick-off it stands for; the band holds both, either side of this row.
PAD_BAND = (timedelta(hours=2, minutes=30), timedelta(hours=4, minutes=30))

#: A bound, not a sample: the arms above return single digits on a real board.
CANDIDATE_CAP = 200


def _sport_prefix(key: str) -> str:
    return _catchall_sport_prefix(key) or key.split("_", 1)[0]


def _norm_status(row: Any) -> str:
    return str(getattr(row, "status", None) or "").strip().lower()


async def _partition_foldable_sport_ids(db, sport_key: str) -> tuple[list[int], list[int]]:
    """Return ``(foldable_sport_ids, own_league_sport_ids)`` for ``sport_key``.

    ``foldable_sport_ids`` covers the same league (season variants via
    ``league_identity``), its ``*_other`` catch-all, and cross-board siblings
    (#5774). ``own_league_sport_ids`` keeps only exact same-league ids (never
    ``*_other``) for same-UTC-day reversed claims (#13142).
    """
    prefix = _sport_prefix(sport_key)
    own_identity = league_identity(sport_key)
    own_is_catchall = _catchall_sport_prefix(sport_key) is not None
    rows = (
        await db.execute(select(Sport.id, Sport.key).where(Sport.key.like(f"{prefix}%")))
    ).all()
    ids = []
    own_league_ids = []
    for sport_id, key in rows:
        if not key or _sport_prefix(key) != prefix:
            continue
        if (
            own_is_catchall
            or _catchall_sport_prefix(key) is not None
            or league_identity(key) == own_identity
            or cross_board_identity(key) == own_identity
            or cross_board_identity(sport_key) == league_identity(key)
        ):
            ids.append(sport_id)
            # Standalone catch-all claims are refused by `_reversed_claim_league`,
            # so excluded here to avoid loading hundreds of `basketball_other` rows.
            if (
                not own_is_catchall
                and _catchall_sport_prefix(key) is None
                and league_identity(key) == own_identity
            ):
                own_league_ids.append(sport_id)
    return ids, own_league_ids


async def _foldable_sport_ids(db, sport_key: str) -> list[int]:
    """Sport rows the fold could pair a row of ``sport_key`` with.

    The same league (season variants included, via `league_identity`), plus the
    sport's `*_other` catch-all; a catch-all row itself can meet any league of
    its sport (`_merge_catchall_leagues`). Plus the other board of a game listed
    on two (`cross_board_identity`, #5774). The `sports` table is small.
    """
    ids, _own_league_ids = await _partition_foldable_sport_ids(db, sport_key)
    return ids


def _utc_day_bounds(commence: datetime) -> tuple[datetime, datetime]:
    """Return UTC ``[day_start, next_day_start)`` matching ``commence`` tz awareness."""
    utc_commence = commence.astimezone(timezone.utc) if commence.tzinfo else commence
    tz = timezone.utc if commence.tzinfo else None
    day_start = datetime.combine(utc_commence.date(), time(0), tzinfo=tz)
    return day_start, day_start + timedelta(days=1)


def _commence_arms(commence: datetime) -> Any:
    """Near-time commence windows for serve-time candidate selection."""
    lo_pad, hi_pad = PAD_BAND
    day_start, _day_end = _utc_day_bounds(commence)
    return or_(
        Event.commence_time.between(commence - NEAR, commence + NEAR),
        Event.commence_time.between(commence + lo_pad, commence + hi_pad),
        Event.commence_time.between(commence - hi_pad, commence - lo_pad),
        Event.commence_time == day_start,
    )


def _same_day_idless_claim_predicate(commence: datetime) -> Any:
    """Select id-less own-league claim rows on ``commence``'s UTC calendar day (#13142)."""
    day_start, day_end = _utc_day_bounds(commence)
    return and_(
        Event.commence_time >= day_start,
        Event.commence_time < day_end,
        Event.espn_id.is_(None),
        Event.external_id.is_(None),
        Event.statpal_fixture_id.is_(None),
    )


def _has_priced_signal_predicate() -> Any:
    """Select rows carrying at least one probability source or opening line."""
    return or_(
        and_(
            Event.win_probability_sources.isnot(None),
            cast(Event.win_probability_sources, String) != "{}",
            cast(Event.win_probability_sources, String) != "null",
        ),
        Event.opening_home_probability.isnot(None),
        Event.opening_away_probability.isnot(None),
    )


def _extra_foldable_sport_keys(sport_key: str) -> list[str]:
    """Pure-Python sibling/catch-all keys foldable into ``sport_key`` on list rails."""
    keys: list[str] = []
    catchall = f"{_sport_prefix(sport_key)}_other"
    if catchall != sport_key:
        keys.append(catchall)
    own_id = league_identity(sport_key)
    cb_target = cross_board_identity(sport_key)
    for src_key, tgt_key in CROSS_BOARD_TWIN_KEYS.items():
        if (src_key == sport_key or league_identity(src_key) == own_id) and tgt_key != sport_key and tgt_key not in keys:
            keys.append(tgt_key)
        if (
            tgt_key == sport_key
            or league_identity(tgt_key) == own_id
            or (cb_target and league_identity(src_key) == cb_target)
        ) and src_key != sport_key and src_key not in keys:
            keys.append(src_key)
    return keys


def _coalesced_list_time_predicate(commence_times: list[datetime]) -> Any:
    """Coalesce page ``[ct - PAD_BAND[1], ct + PAD_BAND[1]]`` arms + UTC midnights."""
    aware = any(ct.tzinfo is not None for ct in commence_times)
    norm = [
        (ct if ct.tzinfo is not None else ct.replace(tzinfo=timezone.utc))
        if aware
        else ct
        for ct in commence_times
    ]
    ivs = sorted((ct - PAD_BAND[1], ct + PAD_BAND[1]) for ct in norm)
    merged: list[list[datetime]] = []
    for lo, hi in ivs:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        elif hi > merged[-1][1]:
            merged[-1][1] = hi
    if len(merged) > 12:
        merged = [[min(norm) - PAD_BAND[1], max(norm) + PAD_BAND[1]]]
    midnights = sorted({_utc_day_bounds(ct)[0] for ct in norm})
    clauses: list[Any] = [Event.commence_time.between(lo, hi) for lo, hi in merged]
    if midnights:
        clauses.append(Event.commence_time.in_(midnights))
    return or_(*clauses)


async def _read_candidates(
    db,
    exclude_ids: int | Sequence[int],
    sport_ids: list[int] | None,
    time_predicate: Any,
    *,
    sport_keys: Sequence[str] | None = None,
    extra_filters: Sequence[Any] = (),
    limit: int = CANDIDATE_CAP,
    order_by_id: bool = True,
) -> list:
    """Read up to ``limit`` untagged twin candidates matching ``time_predicate``."""
    predicates: list[Any] = [
        time_predicate,
        not_a_proven_duplicate(),
        Event.status.notin_(list(RETIRED_STATUSES)),
    ]
    if sport_keys is not None:
        predicates.append(Sport.key.in_(list(sport_keys)))
    elif sport_ids is not None:
        predicates.append(Event.sport_id.in_(sport_ids))
    if isinstance(exclude_ids, int):
        predicates.append(Event.id != exclude_ids)
    elif exclude_ids:
        predicates.append(Event.id.notin_(list(exclude_ids)))
    predicates.extend(extra_filters)

    stmt = select(Event)
    if sport_keys is not None:
        stmt = stmt.join(Sport, Event.sport_id == Sport.id).options(
            contains_eager(Event.sport)
        )
    else:
        stmt = stmt.options(selectinload(Event.sport))
    stmt = stmt.where(and_(*predicates))
    if order_by_id:
        stmt = stmt.order_by(Event.id)
    stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def serve_fold_absorbed_rows(db, event) -> list:
    """Rows `fold_twin_events` drops into ``event``, ascending id; ``[]`` if none.

    See :func:`serve_fold_absorbed_rows_with_completeness`, which this returns
    the rows of.
    """
    rows, _complete = await serve_fold_absorbed_rows_with_completeness(db, event)
    return rows


async def serve_fold_absorbed_rows_with_completeness(
    db, event, *, keep_page_survivor: bool = False
) -> tuple[list, bool]:
    """``(rows, complete)``: the absorbed rows, and whether the fold ran whole.

    ``complete`` is False when the fold raised (the rows are then ``[]``, as
    they always were) or a candidate read hit `CANDIDATE_CAP`, so a row past
    the cap could be missing. A caller that CERTIFIES its membership
    (#10090 `history_fold_revision`) must not certify either; every other
    caller reads only the rows.

    When ``keep_page_survivor`` is True (used by single-event detail reads via
    `load_unified_game_reads`), a page row that loses `_elect` to a non-retired
    external twin sitting outside its `(sport_key, status)` slice
    (`winner_sk != sport_key or winner_status != event_status`: same-league
    different-status `#13768`, cross-board `#5774`, or `*_other` catch-all `#13508`)
    retains the page and absorbs that winning twin's cluster so detail and list
    endpoints agree, while same-league same-status losers keep `#3391` detail
    behavior. Raw callers with ``keep_page_survivor=False`` keep `#3391`
    semantics where only named-league rows losing to ``*_other`` mirror
    `_keep_page_survivor`.

    ``event`` must carry `Event.sport` loaded (every event-page route loads it);
    a row whose sport is not in memory cannot be keyed by league and folds
    nothing, which is today's page.

    The candidate read is not wrapped: it is two (or three for anchored
    same-day-allowlisted pages) indexed statements, and a failure there is the
    database failing (the reasoning `folded_event_ids` gives, gotcha #53). The
    fold itself is pure and is wrapped — gotcha #42: a fold that cannot run
    leaves the page exactly as it was.
    """
    sport_key = loaded_sport_key(event)
    commence = getattr(event, "commence_time", None)
    if not sport_key or commence is None or event.sport_id is None:
        return [], True
    if not event.home_team_name or not event.away_team_name:
        return [], True

    sport_ids, own_league_sport_ids = await _partition_foldable_sport_ids(db, sport_key)
    if not sport_ids:
        return [], True
    near_candidates = await _read_candidates(
        db, event.id, sport_ids, _commence_arms(commence)
    )
    same_day_claims: list = []
    if (
        sport_key in _REVERSED_SAME_DAY_ANCHORED_CLAIM_LEAGUES
        and own_league_sport_ids
        and _group_is_id_anchored([event])
    ):
        same_day_claims = await _read_candidates(
            db,
            event.id,
            own_league_sport_ids,
            _same_day_idless_claim_predicate(commence),
        )
    if not near_candidates and not same_day_claims:
        return [], True

    if same_day_claims:
        seen_ids = {row.id for row in near_candidates}
        candidates = list(near_candidates) + [
            row for row in same_day_claims if row.id not in seen_ids
        ]
    else:
        candidates = near_candidates

    try:
        fold = fold_twin_events([event, *candidates])
    except Exception:  # noqa: BLE001 — gotcha #42; an unfolded page is today's
        logger.exception("serve fold: fold failed for event %s", event.id)
        return [], False

    absorbed = {
        loser_id for loser_id, survivor_id in fold.survivor_of.items()
        if survivor_id == event.id
    }
    flipped_ids = set(getattr(fold, "flipped_loser_ids", None) or ())
    if not absorbed and (keep_page_survivor or not sport_key.endswith("_other")):
        winner_id = fold.survivor_of.get(event.id)
        winner = next((c for c in candidates if c.id == winner_id), None)
        winner_sk = loaded_sport_key(winner) if winner is not None else None
        event_status = _norm_status(event)
        winner_status = _norm_status(winner) if winner is not None else ""
        winner_outside_slice = (
            winner_sk is not None
            and (winner_sk != sport_key or winner_status != event_status)
        )
        if winner_sk and (
            (keep_page_survivor and winner_outside_slice)
            or (not sport_key.endswith("_other") and winner_sk.endswith("_other"))
        ):
            # Mirror `_keep_page_survivor`: list endpoints keep the page row
            # and fold the winning cluster onto it when the winner sits outside
            # the page's `(sport_key, status)` slice (same-league different
            # status #13768, cross-board #5774, or `*_other` catch-all #13508),
            # while same-league same-status losers yield to their in-slice
            # survivor on lists and stay unfolded on direct detail reads.
            by_id = {c.id: c for c in candidates}
            other_losers = [
                lid for lid, sid in fold.survivor_of.items()
                if sid == winner_id and lid != event.id
            ]
            if keep_page_survivor:
                same_slice_losers = [
                    by_id[lid] for lid in other_losers
                    if lid in by_id
                    and loaded_sport_key(by_id[lid]) == sport_key
                    and _norm_status(by_id[lid]) == event_status
                ]
            else:
                same_slice_losers = [
                    by_id[lid] for lid in other_losers
                    if lid in by_id and loaded_sport_key(by_id[lid]) == sport_key
                ]
            allow_absorb = (
                not same_slice_losers
                or max([event, *same_slice_losers], key=twin_identity_rank).id == event.id
            )
            if allow_absorb:
                other_members = [winner_id, *other_losers]
                event_flipped = event.id in flipped_ids
                absorbed = set(other_members)
                flipped_ids = {
                    mid for mid in other_members if (mid in flipped_ids) != event_flipped
                }
    rows = sorted(
        (row for row in candidates if row.id in absorbed), key=lambda row: row.id
    )
    for row in rows:
        if row.id in flipped_ids:
            setattr(row, "_serve_fold_corner_flipped", True)
    complete = (
        len(near_candidates) < CANDIDATE_CAP
        and len(same_day_claims) < CANDIDATE_CAP
    )
    return rows, complete


def _keep_page_survivor(
    page_events: list[Any],
    page_ids: set[int],
    inner: FoldResult,
    *,
    fold_fn=fold_twin_events,
) -> FoldResult:
    """Project an augmented ``fold_twin_events`` result back onto ``page_events``.

    Guarantees two invariants required on single-sport list endpoints:
    1. Only rows already present in ``page_events`` survive in ``events`` (an
       unmatched or elected ``*_other`` row can NEVER leak onto a league list or
       drop a league row that matched it).
    2. Original list ordering of ``page_events`` is preserved, and orientation
       gates (``flipped_loser_ids`` + ``flip_probability_sources``) stay intact
       when a twin is absorbed in either direction.
    """
    orig_index = {id(e): i for i, e in enumerate(page_events)}
    page_by_id = {int(e.id): e for e in page_events if getattr(e, "id", None) is not None}
    losers_by_surv: dict[int, list[int]] = {}
    for lid, sid in inner.survivor_of.items():
        losers_by_surv.setdefault(sid, []).append(lid)

    kept_events: list[Any] = []
    merged_sources: dict[int, dict] = {}
    merged_opening: dict[int, tuple] = {}
    survivor_of: dict[int, int] = {}
    dropped_ids: list[int] = []
    flipped_loser_ids: set[int] = set()

    for surv in inner.events:
        sid = getattr(surv, "id", None)
        if sid in page_ids:
            kept_events.append(surv)
            if sid in inner.merged_sources:
                merged_sources[sid] = inner.merged_sources[sid]
            if sid in inner.merged_opening:
                merged_opening[sid] = inner.merged_opening[sid]
            for lid in losers_by_surv.get(sid, ()):
                survivor_of[lid] = sid
                dropped_ids.append(lid)
                if lid in inner.flipped_loser_ids:
                    flipped_loser_ids.add(lid)
            continue

        # An extra candidate (e.g., `*_other` row) outscored its page twin in
        # `_elect`. Retain the page row so the single-sport list never swaps in
        # a catch-all row, while still absorbing the twin's sources & IDs.
        cluster_losers = losers_by_surv.get(sid, ())
        page_losers = [lid for lid in cluster_losers if lid in page_ids]
        if not page_losers:
            continue
        if len(page_losers) == 1:
            kept_ev = page_by_id[page_losers[0]]
        else:
            kept_ev = fold_fn([page_by_id[pid] for pid in page_losers]).events[0]
        kept_events.append(kept_ev)

        surv_is_flipped_vs_kept = kept_ev.id in inner.flipped_loser_ids
        raw_surv_sources = (
            inner.merged_sources.get(sid)
            if sid in inner.merged_sources
            else getattr(surv, "win_probability_sources", None)
        )
        if raw_surv_sources:
            if surv_is_flipped_vs_kept:
                ok, oriented_bag = flip_probability_sources(raw_surv_sources)
                oriented_bag = oriented_bag if ok else None
            else:
                oriented_bag = raw_surv_sources
            if oriented_bag:
                kept_own = getattr(kept_ev, "win_probability_sources", None)
                combined = merge_probability_sources(
                    kept_own,
                    [(sid, oriented_bag)],
                    event_status=getattr(kept_ev, "status", None),
                )
                if combined != dict(kept_own or {}):
                    merged_sources[kept_ev.id] = combined

        if (
            not surv_is_flipped_vs_kept
            and getattr(kept_ev, "opening_home_probability", None) is None
            and getattr(kept_ev, "opening_away_probability", None) is None
        ):
            opening_pair = inner.merged_opening.get(sid) or (
                getattr(surv, "opening_home_probability", None),
                getattr(surv, "opening_away_probability", None),
            )
            if opening_pair[0] is not None and opening_pair[1] is not None:
                if hasattr(kept_ev, "_sa_instance_state"):
                    set_committed_value(kept_ev, "opening_home_probability", opening_pair[0])
                    set_committed_value(kept_ev, "opening_away_probability", opening_pair[1])
                else:
                    kept_ev.opening_home_probability = opening_pair[0]
                    kept_ev.opening_away_probability = opening_pair[1]
                merged_opening[kept_ev.id] = (opening_pair[0], opening_pair[1])

        other_ids = [sid, *[lid for lid in cluster_losers if lid != kept_ev.id]]
        for other_id in other_ids:
            survivor_of[other_id] = kept_ev.id
            dropped_ids.append(other_id)
            if (other_id in inner.flipped_loser_ids) != surv_is_flipped_vs_kept:
                flipped_loser_ids.add(other_id)

    kept_events.sort(key=lambda e: orig_index.get(id(e), 0))
    return FoldResult(
        events=kept_events,
        merged_sources=merged_sources,
        dropped_ids=dropped_ids,
        survivor_of=survivor_of,
        merged_opening=merged_opening,
        flipped_loser_ids=flipped_loser_ids,
    )


async def fold_list_with_catchall_twins(
    db: Any,
    events: list[Any],
    sport_key: str | None,
    *,
    fold_fn=fold_twin_events,
) -> FoldResult:
    """Fold ``events`` plus any unlinked catch-all / sibling twins on single-sport lists.

    Matches :func:`serve_fold_absorbed_rows` for list endpoints: on a scoped
    league query (e.g. ``?sport=soccer_efl_champ``), an untagged venue twin in
    ``soccer_other`` or a cross-board sibling was excluded by the `Sport.key`
    filter and therefore missed by in-page ``fold_twin_events``. Reads only the
    catch-all / cross-board sport IDs inside the page's commence-time envelope
    and folds them cleanly into ``events``.

    Runs zero extra DB queries when ``sport_key`` is omitted, is already a
    ``*_other`` catch-all key, or has no foldable sibling sport rows.
    """
    if not events or not sport_key or sport_key.endswith("_other"):
        return fold_fn(events)

    extra_keys = _extra_foldable_sport_keys(sport_key)
    if not extra_keys:
        return fold_fn(events)

    commence_times = [
        ct for e in events if isinstance((ct := getattr(e, "commence_time", None)), datetime)
    ]
    if not commence_times:
        return fold_fn(events)

    time_pred = _coalesced_list_time_predicate(commence_times)
    page_ids = {int(e.id) for e in events if getattr(e, "id", None) is not None}
    rows = await _read_candidates(
        db,
        sorted(page_ids),
        None,
        time_pred,
        sport_keys=extra_keys,
        extra_filters=(
            Event.status.notin_(list(RETIRED_STATUSES)),
            _has_priced_signal_predicate(),
        ),
        limit=CANDIDATE_CAP * 3,
        order_by_id=False,
    )
    extra_candidates = [
        r for r in rows if getattr(r, "id", None) is not None and int(r.id) not in page_ids
    ]
    if not extra_candidates:
        return fold_fn(events)

    inner = fold_fn(list(events) + extra_candidates)
    return _keep_page_survivor(events, page_ids, inner, fold_fn=fold_fn)
