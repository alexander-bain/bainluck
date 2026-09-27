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
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.models.models import Event, Sport
from app.utils.event_twin_fold import _catchall_sport_prefix, fold_twin_events
from app.utils.kalshi_occurrence_start import loaded_sport_key
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


async def _foldable_sport_ids(db, sport_key: str) -> list[int]:
    """Sport rows the fold could pair a row of ``sport_key`` with.

    The same league (season variants included, via `league_identity`), plus the
    sport's `*_other` catch-all; a catch-all row itself can meet any league of
    its sport (`_merge_catchall_leagues`). The `sports` table is small.
    """
    prefix = _sport_prefix(sport_key)
    own_identity = league_identity(sport_key)
    own_is_catchall = _catchall_sport_prefix(sport_key) is not None
    rows = (
        await db.execute(select(Sport.id, Sport.key).where(Sport.key.like(f"{prefix}%")))
    ).all()
    ids = []
    for sport_id, key in rows:
        if not key or _sport_prefix(key) != prefix:
            continue
        if (
            own_is_catchall
            or _catchall_sport_prefix(key) is not None
            or league_identity(key) == own_identity
        ):
            ids.append(sport_id)
    return ids


def _commence_arms(commence: datetime) -> Any:
    lo_pad, hi_pad = PAD_BAND
    midnight = datetime.combine(commence.date(), time(0), tzinfo=commence.tzinfo)
    return or_(
        Event.commence_time.between(commence - NEAR, commence + NEAR),
        Event.commence_time.between(commence + lo_pad, commence + hi_pad),
        Event.commence_time.between(commence - hi_pad, commence - lo_pad),
        Event.commence_time == midnight,
    )


async def serve_fold_absorbed_rows(db, event) -> list:
    """Rows `fold_twin_events` drops into ``event``, ascending id; ``[]`` if none.

    ``event`` must carry `Event.sport` loaded (every event-page route loads it);
    a row whose sport is not in memory cannot be keyed by league and folds
    nothing, which is today's page.

    The candidate read is not wrapped: it is two indexed statements, and a
    failure there is the database failing (the reasoning `folded_event_ids`
    gives, gotcha #53). The fold itself is pure and is wrapped — gotcha #42: a
    fold that cannot run leaves the page exactly as it was.
    """
    sport_key = loaded_sport_key(event)
    commence = getattr(event, "commence_time", None)
    if not sport_key or commence is None or event.sport_id is None:
        return []
    if not event.home_team_name or not event.away_team_name:
        return []

    sport_ids = await _foldable_sport_ids(db, sport_key)
    if not sport_ids:
        return []
    candidates = list(
        (
            await db.execute(
                select(Event)
                .options(selectinload(Event.sport))
                .where(
                    and_(
                        Event.id != event.id,
                        Event.sport_id.in_(sport_ids),
                        _commence_arms(commence),
                    )
                )
                .order_by(Event.id)
                .limit(CANDIDATE_CAP)
            )
        )
        .scalars()
        .all()
    )
    if not candidates:
        return []

    try:
        fold = fold_twin_events([event, *candidates])
    except Exception:  # noqa: BLE001 — gotcha #42; an unfolded page is today's
        logger.exception("serve fold: fold failed for event %s", event.id)
        return []

    absorbed = {
        loser_id for loser_id, survivor_id in fold.survivor_of.items()
        if survivor_id == event.id
    }
    return sorted(
        (row for row in candidates if row.id in absorbed), key=lambda row: row.id
    )
