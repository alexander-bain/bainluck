"""Team detail page API."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from app.utils.event_rails import (
    commence_time_was_never_a_kickoff,
    live_first_order,
    recent_or_unreported_condition,
    upcoming_rail_condition,
)
from app.utils.event_twin_fold import fold_twin_events, team_name_fold_key
from app.utils.aggregation import compute_aggregate_probability
from app.utils.lifecycle import served_event_status
from app.utils.season_variant_team import (
    choose_parent_league_row,
    wants_parent_league_row,
)
from app.utils.sport_keys import league_family_identity, sport_display_name
from app.utils.standings_shape import public_standings

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.models import Team, Event, Sport, FuturesMarket, FuturesOutcome, TeamIdentityMapping
from app.services import get_db
from app.utils import season_windows
from app.utils.proven_duplicates import (
    FoldedBlendView,
    folded_probability_sources_batch,
    not_a_proven_duplicate,
)

logger = logging.getLogger(__name__)

router = APIRouter()

#: Cards per rail on the team page. Was a bare `5` inline on both queries; the
#: fold below has to reason about it, so it gets a name.
EVENT_CARD_LIMIT = 5

#: How many raw rows to ask the DB for so the fold can still fill the rail.
#: Doubling is exactly enough whenever a fixture has at most TWO rows, which is
#: the whole measured population (one row per supplier). A fixture carrying
#: three rows could still shrink a full rail by one card — strictly better than
#: today, where it shows three cards, and it degrades by losing a card rather
#: than by failing.
_EVENT_FETCH_LIMIT = EVENT_CARD_LIMIT * 2


def _fold_rail(rows: list, rail: str, team_slug: str) -> list:
    """One fixture, one card — the team-page half of #4100.

    WHY THIS ROUTE NEEDED ITS OWN CALL. `/api/feed` and `GET /api/events` have
    folded twin rows since `ac6eb2c1`/#4100, but the team page is served by
    `GET /api/teams/{identifier}`, which never called the helper. Measured on
    production 2026-09-12 03:4xZ: `/api/teams/boston-red-sox` returned BOTH
    `15310368` (espn_id set, 188 odds snapshots) and `15305549`
    (statpal_fixture_id set, 0 snapshots) for the same 20:10:00Z fixture
    against Kansas City, while `/api/events?sport=baseball_mlb` — same minute,
    same teams, folded — returned only `15310368`. Two cards, one game, on the
    page Alex opens.

    The proven-duplicate filter is already on both queries and cannot help
    here: it reads a `provenance:duplicate-of:` tag that only a prover writes,
    and neither row carries one. (Named without its parentheses on purpose —
    `test_the_team_page_rails` counts the literal call text in this file, so a
    mention in prose reads to it as a third rail and reddens CI on a comment.)
    Ruling 048 (gotcha #32) is why the registry itself
    correctly refuses to merge them — each row is anchored to a different
    provider's game id, so there is no shared id to absorb on. The durable
    repair is that shared id (#2693 / #1946); this is the serve-time fold that
    keeps the bug off the reader's page until it lands, and it claims nothing
    more than that.

    🔴 THE CAP IS APPLIED AFTER THE FOLD HERE, WHICH IS THE OPPOSITE OF
    `list_events`, AND THE DIFFERENCE IS REASONED, NOT INHERITED. That route
    folds after its `limit` because it is OFFSET-PAGINATED: over-fetching would
    make page one consume more raw rows than `limit`, so `offset=limit` would
    re-serve rows page one already showed. This route has no `offset` and no
    cursor — it is a fixed five-card rail — so that hazard cannot arise, and
    folding after a DB `limit` of 5 would instead silently spend a card slot on
    a row it then drops: a twin pair at the top would leave the reader FOUR
    upcoming games instead of five. So the query over-fetches and the fold's
    output is truncated to the cap.

    `set_committed_value` delivers the union onto the hydrated row WITHOUT
    marking it dirty, so no later flush can persist a serve-time blend into
    `events` (gotcha #4's neighbourhood). A plain assignment here would be a
    write waiting for a commit.

    Gotcha #42 applied to a whole stage: the fold improves the rail, it is
    never a precondition for having one. If it raises, the unfolded rail is
    served — today's bug — rather than no page at all.
    """
    try:
        fold = fold_twin_events(rows)
        if fold.dropped_ids:
            for survivor_id, merged in fold.merged_sources.items():
                survivor = next(e for e in fold.events if e.id == survivor_id)
                set_committed_value(survivor, "win_probability_sources", merged)
            logger.info(
                "team page twin fold: %s/%s collapsed %d duplicate event rows, "
                "%d rows gained a venue (dropped=%s)",
                team_slug,
                rail,
                fold.folded_count,
                len(fold.merged_sources),
                fold.dropped_ids[:20],
            )
        rows = fold.events
    except Exception:
        logger.exception(
            "team page twin fold failed for %s/%s; serving the unfolded rail",
            team_slug,
            rail,
        )
    return rows[:EVENT_CARD_LIMIT]


async def _club_row_identity(
    db, team: Team, family_sport_ids: list
) -> tuple[frozenset, frozenset]:
    """Every team ROW that is this club, as (ids, names) for the event filter.

    ## A club is not one row, and the page could only reach one of them (#7929)

    `/team/montreal-canadiens` printed "vs Ottawa Senators · Sep 21 · W 3–2"
    with no "we had them at X%", while the SAME game on the Senators page read
    42%. Three team rows spell one club:

        568    Montreal Canadiens    icehockey_nhl            espn_id 10
        3706   Montréal Canadiens    icehockey_nhl            espn_id 10
        19692  Montréal Canadiens    icehockey_nhl_preseason  espn_id NULL

    The filter matched `home_team_id == 568` or the exact string
    "Montreal Canadiens", so every row the providers spelled with the accent
    was invisible to the page the URL resolves to. Measured on production
    2026-09-22 over 09-01..10-22: the club's own page was missing FOUR of its
    eight rows — both completed games' pre-match line (0.5108 and 0.5830, each
    on the accented twin the fold never saw) and two upcoming fixtures
    outright (Oct 3 at Pittsburgh, Oct 6 vs Carolina, both bound to 3706).

    ## Why the key is the FOLD's key and not an identifier

    The obvious anchor is `espn_id`, and it is POISONED for this: measured the
    same day, 382 same-sport pairs share one `espn_id` while disagreeing on
    name, and they include rows that are not one club — `New York Islanders`
    (54) and `New Jersey` (12716) both carry espn_id 12, `Portland Timbers`
    and `Portland Timbers 2` both carry 9723. Keying on it would put a rival's
    and a reserve side's games on a club's page: a truth defect traded for a
    missing caption. The preseason rows have no `espn_id` at all, so it could
    not have reached this specimen anyway.

    So the key is `team_name_fold_key` — the twin fold's OWN squash, imported
    rather than reimplemented. It folds diacritics and punctuation and nothing
    else, which is why it reads `Montréal Canadiens` as 568's club and still
    reads `Portland Timbers 2`, `Columbus Crew 2` and `Borussia Dortmund (Res)`
    as separate sides. It is also the key the fold downstream already uses to
    decide which rows are one fixture, so a row this admits is a row that fold
    can collapse — the two halves cannot drift, because they are one function.

    ## Scope, cost and how it fails

    Scoped to the team's own league FAMILY for #5491's reason: `Djurgardens IF`
    (soccer) and `Djurgårdens IF` (ice hockey) fold alike and are not one
    schedule. Measured over the same window, the same-family population is six
    clubs — Montréal Canadiens, CF Montréal, Borussia Mönchengladbach,
    CS Marítimo and two MMA fighters — so this is a narrow repair, not a
    widening of the name fallback.

    One extra query, `(id, name)` over the family: 11ms measured on the largest
    family there is (tennis_wta, 1,563 rows) against a page that takes ~1.2s,
    so it is not cached — a cache here would be state bought for 1% of a page.

    Fails to TODAY'S ANSWER, loudly: on any error the club is just its own row,
    which is exactly the behaviour before this repair. The rails are this
    page's core (#1197 / #1239) and must not 500 for a widening.
    """
    club_ids = {team.id}
    club_names = {team.name}
    if not family_sport_ids:
        return frozenset(club_ids), frozenset(club_names)
    try:
        key = team_name_fold_key(team.name)
        if not key:
            return frozenset(club_ids), frozenset(club_names)
        rows = (
            await db.execute(
                select(Team.id, Team.name).where(Team.sport_id.in_(family_sport_ids))
            )
        ).all()
        for row_id, row_name in rows:
            if team_name_fold_key(row_name) == key:
                club_ids.add(row_id)
                club_names.add(row_name)
    except Exception:
        logger.exception(
            "team page: club row identity failed for team %s; serving its own "
            "row only",
            team.id,
        )
    return frozenset(club_ids), frozenset(club_names)


@router.get("/{identifier}")
async def get_team(identifier: str, debug_timing: bool = False, db: AsyncSession = Depends(get_db)):
    """Get a team page with upcoming/recent games, futures, and championship path."""
    _t = {}
    _t0 = time.perf_counter()

    def _mark(label):
        nonlocal _t0
        _t[label] = round((time.perf_counter() - _t0) * 1000)
        _t0 = time.perf_counter()

    # Try integer ID first, then slug
    team_filter = Team.slug == identifier
    try:
        team_id = int(identifier)
        team_filter = or_(Team.id == team_id, Team.slug == identifier)
    except ValueError:
        pass

    result = await db.execute(
        select(Team).options(selectinload(Team.sport)).where(team_filter)
    )
    team = result.scalars().first()
    if not team:
        # #1204: legacy-slug redirect. A slug retired by a team-identity merge is
        # registered in team_identity_mapping (source='legacy_slug') pointing at the
        # canonical franchise, so a bookmarked old slug (e.g. /teams/boston) resolves
        # to the live row instead of 404-ing (redirect, not 404).
        legacy_id = (await db.execute(
            select(TeamIdentityMapping.team_id).where(
                TeamIdentityMapping.source == "legacy_slug",
                TeamIdentityMapping.source_id == identifier,
            ).limit(1)
        )).scalar_one_or_none()
        if legacy_id is not None:
            team = (await db.execute(
                select(Team).options(selectinload(Team.sport)).where(Team.id == legacy_id)
            )).scalars().first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # #2498: A CLUB'S PAGE IS ITS LEAGUE'S ROW, NOT ITS SPRING ROW.
    #
    # `boston-red-sox` was the `baseball_mlb_preseason` row (853) — 13-15,
    # `standings_data` NULL, breadcrumb "MLB PRESEASON" — while the club playing
    # a pennant race sat one slug away at `boston-red-sox-mlb` (10709, 80-67,
    # division East). All 30 MLB preseason clubs held the clean slug that way.
    #
    # The swap is ID-ANCHORED and only that: the candidate query is keyed on a
    # shared `espn_id`, so this never matches on a name or a kickoff time and
    # ruling 048 is not in play. It writes nothing and merges nothing — both
    # rows survive; one of them stops being what a URL resolves to.
    #
    # NFL and NBA are untouched by construction: their variant rows carry no
    # `espn_id` at all, so the query below returns nothing for them.
    if wants_parent_league_row(getattr(team.sport, "key", None)) and getattr(team, "espn_id", None):
        siblings = (await db.execute(
            select(Team.id, Sport.key)
            .join(Sport, Sport.id == Team.sport_id)
            .where(Team.espn_id == team.espn_id, Team.id != team.id)
        )).all()
        parent_id = choose_parent_league_row(team.sport.key, siblings)
        if parent_id is not None:
            parent = (await db.execute(
                select(Team).options(selectinload(Team.sport)).where(Team.id == parent_id)
            )).scalars().first()
            # Only on a row we actually loaded. A `None` here would 404 a page
            # that was serving a moment ago — a worse page beats no page.
            if parent is not None:
                team = parent

    now = datetime.now(timezone.utc)

    # --- Events: upcoming + recent ---
    # The two NAME arms are a FALLBACK for rows whose team binding never landed,
    # and a fallback must not cross leagues (#5491). A Polymarket-derived row in
    # the `baseball_other` catch-all bearing the string "Boston Red Sox" was
    # reaching the MLB club's page as "vs Texas Rangers — No result reported":
    # a real matchup, ingested with no anchor, no team binding, and the INGEST
    # time in `commence_time` (all 18 specimens sat at 13:00:3x-5x UTC).
    #
    # The guard is scoped to rows with NO binding on either side, which is the
    # only population the name arms serve. That scoping is what keeps it
    # surgical: a `baseball_mlb` game reaching a `baseball_mlb_preseason` club
    # (#2498 — 1,604 rows) and an EPL match reaching a club registered under
    # `soccer_england_efl_cup` both carry real team ids, so neither is tested at
    # all. Measured over a +/-21-day window on production 2026-09-12: 4,521 rows
    # excluded, 4,447 of them (98.4%) from a `*_other` catch-all bucket.
    #
    # The comparison is `league_family_identity`, NEVER `sport_id` — a row id is
    # not a league (#1798/#4945: every MLB club has a preseason row too), and a
    # tennis player registered under `tennis_atp_us_open` must keep their
    # `tennis_atp` matches.
    team_family = league_family_identity(getattr(team.sport, "key", None))
    family_sport_ids: list[int] = []
    if team_family is not None:
        family_sport_ids = [
            sport_id
            for sport_id, sport_key in (
                await db.execute(select(Sport.id, Sport.key))
            ).all()
            if league_family_identity(sport_key) == team_family
        ]

    club_ids, club_names = await _club_row_identity(db, team, family_sport_ids)

    # Sorted at the query boundary: a set's iteration order is not stable
    # between processes, and an `IN` list that reorders is a different cache
    # key for the same question. The frozensets stay sets for the membership
    # tests in the card formatter, where order is nothing.
    club_id_list, club_name_list = sorted(club_ids), sorted(club_names)

    name_arm = or_(
        Event.home_team_name.in_(club_name_list),
        Event.away_team_name.in_(club_name_list),
    )
    if team_family is not None:
        # An empty list would exclude every unbound row, so only constrain when
        # the team's own sport resolved — `.in_([])` is a false predicate, and
        # failing OPEN here costs a stale card while failing closed costs a
        # club its whole schedule.
        if family_sport_ids:
            name_arm = and_(
                name_arm,
                or_(
                    Event.home_team_id.isnot(None),
                    Event.away_team_id.isnot(None),
                    Event.sport_id.in_(family_sport_ids),
                ),
            )

    base_event_filter = or_(
        Event.home_team_id.in_(club_id_list),
        Event.away_team_id.in_(club_id_list),
        name_arm,
    )

    upcoming_q = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            base_event_filter,
            # The status × time half is `utils.event_rails` (#3211) — it was
            # these same two lines on the league page, and the pair of rails is
            # only correct as a pair. See that module for why `live` no longer
            # carries a `now - 2h` floor.
            upcoming_rail_condition(now),
            # #2263: one game, one card. A row the registry proved is a second
            # copy of another row is not a second fixture on this team's schedule.
            not_a_proven_duplicate(),
        )
        .order_by(
            # Q438: the same live-AND-started predicate the league rail uses —
            # the pair is only correct as a pair.
            live_first_order(now),
            Event.commence_time.asc(),
        )
        # Over-fetched so the twin fold can still fill the rail — see `_fold_rail`.
        .limit(_EVENT_FETCH_LIMIT)
    )

    recent_q = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            base_event_filter,
            # #1204: include 'closed'-settled, not just 'completed' — a settled
            # doubleheader game (and every source that closes rather than completes)
            # was orphaned from recent games (only 1 of 2 surfaced).
            #
            # 🔴 AND `suspended` — live/056, the same omission #1204 describes
            # one state later. `upcoming_q` above is live/scheduled gated on
            # `now - 2h`; a match is suspended precisely because hours have
            # passed. Between the two, a rain-delayed match was on NEITHER of
            # its two teams' pages. `RecentGameCard` was taught the state in the
            # same change — without that it would have graded the PARTIAL score
            # as a result ("L 1–2"), which is the false Final live/048 removed,
            # printed by a different component.
            #
            # 🔴 AND a `scheduled` row past its own kickoff — #3211, the third
            # state through the same hole and the one that cost 171 US Open
            # matches on the league pages. `RecentGameCard` needs no further
            # teaching: such a row has no score at all, so the state it renders
            # is the score-less arm of the one live/056 already gave it.
            #
            # The 30-day lookback is PASSED, not assumed — a team plays less
            # often than its league does, and that difference is this page's
            # decision rather than the shared module's.
            #
            # 🔴 ONE LIST HERE, THREE RAILS ON THE LEAGUE PAGE, and the asymmetry
            # is reasoned rather than inherited: that page's cap spans every
            # concurrent match in a league (hundreds, during a Grand Slam), so
            # result-less rows starved the Finals out of all eight slots. This
            # cap spans ONE team's own schedule, where a result-less game is one
            # fixture among the handful the rail was sized for. Comparable
            # populations, no starvation. `unreported_rail_condition` carries the
            # measurement and this call site is named in it.
            recent_or_unreported_condition(now, lookback=timedelta(days=30)),
            not_a_proven_duplicate(),  # #2263, as above
        )
        .order_by(Event.commence_time.desc())
        # Over-fetched so the twin fold can still fill the rail — see `_fold_rail`.
        .limit(_EVENT_FETCH_LIMIT)
    )

    _mark("resolve_team")
    upcoming_r, recent_r = await db.execute(upcoming_q), await db.execute(recent_q)
    # Row fold FIRST, then the blend fold below. Two different folds with two
    # different jobs: this one decides HOW MANY CARDS the rail has (one per
    # fixture), `_folded_briefs` decides WHAT NUMBER each surviving card
    # prints. Running the row fold first also means the batch lookup in
    # `_folded_briefs` runs over deduped rows, and lets the union this fold
    # writes onto the survivor be the fallback that lookup degrades to.
    upcoming_rows = _fold_rail(list(upcoming_r.scalars().all()), "upcoming", team.slug)
    # ── #6346 on the OTHER surface that spends `recent_or_unreported_condition` ──
    #
    # #6346 took "Liverpool — Manchester United · No result reported" off
    # `/sport/soccer/epl` and left it on `/api/teams/liverpool`, which is the same
    # card about the same row. MEASURED 2026-09-15 12:5xZ, after that fix was live
    # on production (`fd5326559` is an ancestor of the deployed sha): the league
    # page served `unreported_games: 0` while the Liverpool team page was still
    # serving `15302967` and `15302968` — the Manchester United and Everton
    # season-matchup containers, two of the five the league page had just stopped
    # showing.
    #
    # Not a second policy: `commence_time_was_never_a_kickoff` is #6346's own
    # helper, called here rather than reimplemented, so the tolerance and the
    # source set cannot drift between the two readers of one rail condition.
    #
    # BEFORE `_fold_rail`, for the reason the league page gives for going before
    # its own fold: a container must never be elected the survivor of a fold
    # against the real row it shadows. The team page has no
    # `kalshi_occurrence_start` recovery in front of it, so placement is a
    # correctness margin here rather than the whole fix.
    #
    # Wrapped, because this rail is Priority #3 and the file's own rule two
    # paragraphs down is that an optional step never takes the page with it.
    _recent_raw = list(recent_r.scalars().all())
    try:
        _recent_raw = [e for e in _recent_raw if not commence_time_was_never_a_kickoff(e)]
    except Exception:  # noqa: BLE001 — a gate may not cost a reader their rail
        # The team ID and not the slug: the slug reaches this route as a path
        # parameter, and a new log line carrying one is a `py/log-injection`
        # finding that notice 32 refuses — the same call the league page's own
        # withhold log records making.
        logger.exception(
            "team page: invented-kickoff gate failed for team %s; serving "
            "the recent rail unfiltered",
            team.id,
        )
    # ── #7051: the rail and the record must describe the SAME season ─────────
    #
    # `/team/washington-commanders`, production 2026-09-22: the header reads
    # `0-2`, and one of the three cards under RECENT RESULTS is `@ Baltimore
    # Ravens, Aug 28, L 3-41`. Denver reads `1-1` over a 34-6 win on Aug 29.
    # Those are August exhibitions, played by backups, rendered in the same card
    # as a real result and carrying our own probability caption. The record is
    # not the thing that is wrong — it comes from the standings and correctly
    # counts two games. MEASURED over all 32 NFL team payloads that morning:
    # 32/32 pages print a record, and 36 of their 100 recent cards are pre-floor
    # exhibitions. Every page contradicts itself.
    #
    # ⚠️ NOT a preseason-key filter. The rows are misfiled under
    # `americanfootball_nfl` itself (51 of them, duplicated again under
    # `americanfootball_nfl_preseason`), so `sport_key` cannot see them — and
    # `league_family_identity` deliberately treats preseason as the same family.
    # The floor is the calendar instead: `season_start` is derived from the
    # league's own band, so it costs no ingest change and no new column.
    #
    # ⚠️ NOT twins-first, which is what #7051's escalation ordered. `_fold_rail`
    # already folds the NFL pair (both providers store the kick-off on the exact
    # hour), so no NFL page serves an exhibition twice; the duplicates are real
    # in the table and invisible here. An id-less claim never absorbs (ruling
    # 048 / gotcha #32) and D35 files matching symptoms rather than fixing them
    # until #2693 lands, so the serve-time rule is the whole of what is honest.
    #
    # Deliberately admits, rather than empties. On this date the NHL floor is
    # LAST October's, so the September exhibitions on an NHL rail stay — that
    # league's page prints no record for them to contradict (#6266) and an empty
    # rail would be the worse answer. The NHL and NBA equivalents of this cut
    # arrive with their own openers, 2026-10-04 and 2026-10-20.
    try:
        _recent_raw = _rail_within_declared_season(
            _recent_raw, team.sport.key if team.sport else None, now
        )
    except Exception:  # noqa: BLE001 — a gate may not cost a reader their rail
        logger.exception(
            "team page: season-floor gate failed for team %s; serving "
            "the recent rail unfiltered",
            team.id,
        )
    recent_rows = _fold_rail(_recent_raw, "recent", team.slug)
    upcoming_events, recent_events = await _folded_briefs(
        db, team, upcoming_rows, recent_rows, club_ids=club_ids, club_names=club_names
    )
    _mark("events")

    # #1197 / #1239: the team page is Priority #3 and must NEVER hard-500 on a
    # failure in an optional enrichment section (a slow/failing futures query, a
    # season-descriptor edge case, a championship-path exception). Each optional
    # section degrades to its empty value and the core page (identity + games)
    # always renders. A cache/DB blip on a sub-section is not allowed to take the
    # whole page down.
    sport_key = team.sport.key if team.sport else None
    league_slug = _league_slug_for_sport_key(sport_key)

    # --- Team futures (championship, conference, division, awards) ---
    futures_items: list = []
    _ftime: dict = {}
    try:
        from app.routes.user import _query_team_futures
        futures_data = await _query_team_futures(
            [team.id], db, limit=30, timings=_ftime if debug_timing else None
        )
        futures_items = futures_data.get("items", [])
    except Exception:
        logger.exception("team page: futures section failed for team %s", team.id)
    _mark("futures")
    if debug_timing:
        _t["futures_detail"] = _ftime

    # --- Season context (every team-page number declares its season) ---
    season_ctx = None
    try:
        season_ctx = (
            season_windows.season_descriptor(league_slug, now) if league_slug else None
        )
    except Exception:
        logger.exception("team page: season descriptor failed for team %s", team.id)
    _mark("season")

    # --- Championship path (tier 1/2/4 probabilities) ---
    champ_path: list = []
    try:
        champ_path = await _get_championship_path(
            team.id, db, league_slug=league_slug, now=now
        )
    except Exception:
        logger.exception("team page: championship path failed for team %s", team.id)
    _mark("championship")

    resp = {
        # `now` is the route's own clock (one read, at the top), so the record
        # and the season descriptor beside it cannot disagree about the date.
        "team": _format_team(team, now=now),
        "season": season_ctx,
        "upcoming_events": upcoming_events,
        "recent_events": recent_events,
        "futures": futures_items,
        "championship_path": champ_path,
    }
    if debug_timing:
        resp["_timings_ms"] = _t
    return resp


# Map an Odds-API sport_key ("basketball_nba") to the season_windows league slug
# ("nba"). Only the four leagues season_windows models have a season string;
# everything else returns None (no year-based season filtering, graded-winner
# exclusion still applies).
_SPORT_KEY_TO_LEAGUE = {
    "basketball_nba": "nba",
    "baseball_mlb": "mlb",
    "americanfootball_nfl": "nfl",
    "icehockey_nhl": "nhl",
}


def _league_slug_for_sport_key(sport_key: str | None) -> str | None:
    return _SPORT_KEY_TO_LEAGUE.get((sport_key or "").strip().lower())


def _played_before_season_start(event, floor: datetime) -> bool:
    """True when this row was played before ``floor``, the first day of the
    season the page is describing. #7051 — the rail's half of the rule.

    Keyed on the row's kick-off and nothing else. Status is deliberately not
    read: the Broncos rail carries the exhibition's score-less `suspended` twin
    at 2026-08-28 04:00Z beside the scored 08-29 row, 21 hours apart, so no fold
    bound reaches it (#3601) — and a card that says "no result reported" about
    an exhibition three weeks before kickoff is the same lie in a quieter voice.

    ⚠️ `Event.commence_time` is `DateTime(timezone=True)` but a row can still
    reach here naive — normalise rather than assume, the same call
    `commence_time_was_never_a_kickoff` makes one gate above for the same
    column. A row with no kick-off at all is KEPT: this gate can only ever
    remove a card, so the unreadable case must serve it.
    """
    commence = getattr(event, "commence_time", None)
    if commence is None:
        return False
    if commence.tzinfo is None:
        commence = commence.replace(tzinfo=timezone.utc)
    return commence < floor


def _rail_within_declared_season(rows: list, sport_key: str | None, now: datetime) -> list:
    """The past-results rail, restricted to the season the page is describing.

    Both halves of the rule live here so a test can spend it without a session:
    which season this club's league is in (the clock, injected by the caller),
    and which rows fall outside it. A league the calendar does not model — every
    soccer league, tennis, golf, and the preseason sport keys themselves — has no
    floor and is returned untouched, which is the same fall-through
    :func:`_league_slug_for_sport_key` gives every other seasonal read on this
    page.
    """
    floor = season_windows.season_start(_league_slug_for_sport_key(sport_key), now)
    if floor is None:
        return list(rows)
    return [e for e in rows if not _played_before_season_start(e, floor)]


# ── #6266: a record must belong to the season the page declares ──────────────
#
# `teams.current_record` is a bare `String(20)` stamped by the ESPN sync when a
# game completes (`utils/espn_helpers.py:921`), and `standings_data` carries no
# season field of any kind. So neither the column nor the row can say WHICH
# season a record describes, and a label ("2025-26 record") is not derivable
# from stored state — lane1b/426 eliminated that option on #6266. What IS
# derivable is whether the league has played a game of the season the page
# names, and that is enough for the only honest answer left: print nothing
# (notice 34 — leave the space empty rather than explain it).
#
# MEASURED on production 2026-09-22 over the four modelled leagues, with the two
# in-season ones as the control:
#
#   nhl  offseason  43 rows carry a record. TWENTY are non-zero and they are
#                   wrong in two different ways at once, which is why the
#                   championship grid reads MIXED rather than uniformly stale.
#                   Ten are EXHIBITION records stamped this week — Montreal
#                   serves `2-0-0` built from the two games on its own payload,
#                   Sep 19 at Toronto and Sep 21 vs Ottawa, September dates the
#                   2026-27 season has not reached. Ten still hold last season's
#                   finished 82 on a duplicate club row (`montreal-nhl`
#                   `41-21-10`, `toronto-nhl` `32-35-14`), so one club is served
#                   two seasons on two slugs. The remaining 23 have rolled over
#                   to `0-0-0` and are already right.
#   nba  offseason  34 rows, every one non-zero and every one a completed
#                   season (`brooklyn-nets` `18-59`) under a page naming 2026-27.
#   mlb  in_season  untouched — 31 rows, in progress and correct.
#   nfl  in_season  untouched — 32 rows, week 3 and correct.
#
# So 77 pages change and 54 of them were printing a non-zero record for a season
# with no games played. That is #6266's own control table reproduced exactly —
# NBA and NHL wrong, MLB and NFL right — which is the check on the sizing.
#
# The StatPal board agrees independently: every NHL and NBA row reads `wins 0,
# losses 0`, stamped the same morning. Two sources say zero games played and
# only this column says otherwise.
#
# NOT `standings_shape.record_text`, which is the other consumer of this exact
# column pair (`routes/events.py:25635`) and the obvious call site to route onto.
# Simulated with the real helper over all 137 production rows carrying both
# columns, same day: it moves 52 and FIVE GO THE WRONG WAY — Toronto's honest
# `0-0-0` becomes last season's `32-36` — because its "fewer games means stale"
# clause cannot tell a rollover to zero from a lag. Routing this call site there
# would import a defect rather than retire one; recorded on #6266 for the hero.
#
# Deliberately narrow in three directions, so this withholds only what it can
# demonstrate: a mid-season BREAK is not an offseason (February NHL games have
# been played, so the All-Star band keeps its record); a league with no modelled
# band falls through untouched, which includes `icehockey_nhl_preseason` — it is
# not in `_SPORT_KEY_TO_LEAGUE`; and a failure in the calendar costs the hero its
# record, never the page (this route is Priority #3, the rule two sections up).
def _record_for_declared_season(team: Team, now: datetime | None = None) -> str | None:
    record = team.current_record
    if not record:
        return None
    sport = team.sport
    league = _league_slug_for_sport_key(sport.key if sport else None)
    if not league:
        return record
    try:
        if season_windows.is_offseason(league, now):
            return None
    except Exception:  # noqa: BLE001 — a calendar edge may not cost a reader the page
        # The team ID and not the slug, for the reason the invented-kickoff gate
        # above gives: a log line carrying a path parameter is a
        # `py/log-injection` finding that notice 32 refuses.
        logger.exception(
            "team page: season gate failed for team %s; serving the record "
            "unfiltered",
            getattr(team, "id", None),
        )
    return record


def _format_team(team: Team, now: datetime | None = None) -> dict:
    sport = team.sport
    return {
        "id": team.id,
        "slug": team.slug,
        "name": team.name,
        "abbreviation": team.abbreviation,
        "sport_key": sport.key if sport else None,
        # #6444: a team in an uncurated league used to have its own machine key
        # read back to it as a league name — `/api/teams/alabama-state-hornets`
        # served `sport_name: "basketball_other"`. The helper rejects exactly one
        # value, the key itself, so the 162 branded rows pass through untouched.
        "sport_name": sport_display_name(sport.key, sport.name) if sport else None,
        "location": team.location,
        "primary_color": team.primary_color,
        "secondary_color": team.secondary_color,
        "logo_small": team.logo_url_small,
        "logo_large": team.logo_url_large,
        # #6266: withheld out of season — see `_record_for_declared_season`.
        "record": _record_for_declared_season(team, now),
        # `public_standings` drops write-dead keys (#4811): a pre-#4732
        # `conf_rank` is a division place wearing a conference label, and this
        # is the payload the team-page hero reads.
        "standings": public_standings(team.standings_data),
        "season_stats": team.season_stats,
        "roster": team.roster_players,
    }


async def _folded_briefs(
    db, team: Team, *rails, club_ids=None, club_names=None
) -> list[list[dict]]:
    """Each rail's rows as briefs, with ONE twin fold across ALL of them (#5382).

    🔴 THE HALF THE FIRST PRESENTATION MISSED. Reading the canonical blend
    instead of the never-existing ``aggregate`` key fixes every row that OWNS
    readings. It cannot fix a row that owns none — and the team rails are
    exactly where that row is common, because both queries above carry the
    proven-duplicate filter (#2263): the survivor is printed and its suppressed
    twin is not, so when the venue price landed on the twin the card had
    nothing to blend. The event page has folded that twin since #3810 and reads
    a number off it. Same fixture, two answers, one blank — which is the
    divergence the fold exists to close, arriving on a second surface.

    (That filter is named here without its parentheses on purpose:
    ``test_the_team_page_rails`` counts the literal call text in this file, so a
    mention in prose reads to it as a third rail and reddens CI on a comment.)

    ONE lookup for BOTH rails, not one per rail and certainly not one per row.
    The rails are capped at 5 each, so the N+1 here would be small — but the
    reason to batch is not this page's size, it is that
    ``folded_probability_sources_batch`` is the shared, measured form (#3937)
    and a second hand-rolled fold is how two implementations of one meaning
    start to drift. ``test_one_lookup_serves_both_rails`` pins the count.

    DEGRADES TO TODAY'S ANSWER, LOUDLY. The module's own rule is that fold
    errors are not swallowed, and its stated reason is a page that "silently
    loses its prices" (gotcha #53). Neither half applies to this call: the
    fallback is each row's OWN ``win_probability_sources``, so no price is
    lost — the card prints exactly what it printed before this repair — and
    ``logger.exception`` makes it the opposite of silent. What IS at stake is
    that these are the CORE rail of a Priority-#3 page (#1197 / #1239): the
    rows are already in hand, so a throw here would replace a working team page
    with a 500 for the sake of a number a reader would otherwise still see.
    """
    rows = [event for rail in rails for event in rail]
    folded: dict[int, dict] = {}
    try:
        folded = await folded_probability_sources_batch(db, rows)
    except Exception:
        logger.exception("team page: twin fold failed for team %s", team.id)

    return [
        [
            # The row's OWN sources are the default, never ``None``: the batch
            # promises an entry per event, but a miss must degrade to today's
            # unfolded answer rather than to a card whose number vanishes.
            _format_event_brief(
                FoldedBlendView(
                    event, folded.get(int(event.id), event.win_probability_sources)
                ),
                team,
                club_ids,
                club_names,
            )
            for event in rail
        ]
        for rail in rails
    ]


def _format_event_brief(
    event: Event, team: Team, club_ids=None, club_names=None
) -> dict:
    """Compact event format for team page game lists."""
    sport = event.sport
    # THE SIDE IS READ AGAINST THE WHOLE CLUB, NOT THE URL'S ROW (#7929).
    #
    # Once the filter admits a row bound to a sibling team row, asking
    # `home_team_id == team.id` here answers the wrong question: Montréal's
    # Oct 6 home game against Carolina is `home_team_id 3706`, so the card
    # would have printed it as an AWAY fixture — a widening that repairs a
    # missing card by mislabelling it is not a repair.
    #
    # The two defaults keep the pre-existing callers (the #5382 unit tests
    # construct a team and an event and nothing else) reading exactly as they
    # did, so the identity is an ADDITION to the question, never a replacement.
    ids = club_ids if club_ids is not None else {team.id}
    names = club_names if club_names is not None else {team.name}
    is_home = (event.home_team_id in ids) or (event.home_team_name in names)
    opponent = event.away_team_name if is_home else event.home_team_name

    # #5382: this used to read `win_probability_sources["aggregate"]` — the same
    # read #1776 found and fixed in `league_futures.py::_event_probability`, left
    # unfixed in this second file. THAT KEY HAS NEVER EXISTED (measured: 0 of
    # 52,975 events with a non-null column carry it); the schema is
    # `{source: {value, updated_at, …}}` and the blend is COMPUTED, never stored.
    # So `wp` was None on every row of every team page, including a LIVE game
    # holding five sources whose own event-page hero read 99%.
    #
    # Calls the canonical blend rather than rolling a mean over the sources here:
    # one number per question, and `status` travels on the event, so a completed
    # game drops Kalshi/Polymarket inside `_tier1_readings` without this
    # formatter re-deriving a settled-language rule of its own.
    #
    # The isinstance guard is KEPT, for league_futures' reason: the blend does
    # `.items()` on the column, so a truthy NON-dict (a list, a bare string)
    # raises AttributeError — and in a per-item formatter a throw does not blank
    # one row, it empties the whole rail (gotcha #42).
    wp = None
    if isinstance(event.win_probability_sources, (dict, type(None))):
        wp = compute_aggregate_probability(event)
        # The blend states the HOME side's probability; this brief is
        # team-relative ("we had them at 72%"), so an away row is the
        # complement — the same orientation `pregame_win_probability` gets for
        # free by picking between two stored columns. Safe because our
        # probabilities are two-way normalised in every sport, draw leagues
        # included: measured 2026-09-11, `opening_home + opening_away` sums to
        # 1.0000 with 0 exceptions across all 60 sport keys, soccer among them.
        if wp is not None and not is_home:
            wp = 1.0 - wp

    # L2-174 Item 3e — the recents expectation grammar ("we had them at 72%",
    # L2-158) never fired because this brief never emitted the pre-game line or the
    # settled timestamp; the frontend render (TeamGameCards) is league-agnostic and
    # gates silently on the missing field. The team-relative OPENING probability is
    # exactly "what we had them at" before the game; completed_at dates the result.
    pre = event.opening_home_probability if is_home else event.opening_away_probability

    return {
        "id": event.id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "home_score": event.home_score,
        "away_score": event.away_score,
        # #1779 family: never render live before the row's own start time.
        "status": served_event_status(
            event.status, event.commence_time, datetime.now(timezone.utc)
        ),
        "commence_time": event.commence_time.isoformat() if event.commence_time else None,
        "sport_key": sport.key if sport else None,
        "is_home": is_home,
        "opponent": opponent,
        "win_probability": round(wp, 3) if wp is not None else None,
        "pregame_win_probability": round(float(pre), 3) if pre is not None else None,
        "completed_at": event.completed_at.isoformat() if event.completed_at else None,
    }


_CHAMP_YEAR_RE = re.compile(r"\b(202[4-9]|2030)\b")
_CHAMP_SEASON_HYPHEN_RE = re.compile(r"\b(202[4-9])-(2[4-9]|30)\b")


def _is_future_season(market_name: str, max_year: int) -> bool:
    """Return True if the market name references a season beyond max_year.

    Markets without any year reference pass through (return False).
    """
    years: set[int] = set()
    for match in _CHAMP_SEASON_HYPHEN_RE.finditer(market_name or ""):
        base = int(match.group(1))
        suffix = int(match.group(2))
        years.add(base)
        years.add(base // 100 * 100 + suffix)
    for match in _CHAMP_YEAR_RE.finditer(market_name or ""):
        years.add(int(match.group(1)))
    if not years:
        return False
    return any(y > max_year for y in years)


def _extract_championship_season(market) -> str | None:
    """Season string for a futures market: prefer canonical_market_key
    ({sport}:{league}:{category}:{season}), fall back to a year in the name."""
    key = getattr(market, "canonical_market_key", None)
    if key:
        parts = key.split(":")
        if len(parts) >= 4 and parts[3]:
            return parts[3]
    name = market.name or ""
    m = _CHAMP_SEASON_HYPHEN_RE.search(name)
    if m:
        return m.group(0)
    m2 = _CHAMP_YEAR_RE.search(name)
    if m2:
        return m2.group(0)
    return None


def _season_base_year(season: str | None) -> int | None:
    """First 4-digit year in a season string ("2025-26" → 2025, "2026" → 2026)."""
    if not season:
        return None
    m = _CHAMP_YEAR_RE.search(season)
    return int(m.group(0)) if m else None


# Markets whose question is not the one their tier claims (#1752). `market_tier`
# is semantic — 1=championship, 2=conference, 3=awards, 4=division — but it is
# mis-assigned for whole families, and the path prints the TIER as the label
# ("Win Division 99%"), so a mis-tiered market renders as a title claim the team
# never made. Measured on production 2026-09-19 over the 892 legs this query
# selects: 63 single-market cells carried a "Playoff Qualifiers" market at tier 4
# (Boston is 99.5% to qualify and 1% to win the AL East — the step would have
# read "Win Division 99%"), award markets ("NL Reliever of the Year Winner?",
# "Bear Bryant Coach of the Year Winner") sat at tier 1 beside real championship
# markets, and a "Championship Halftime Show: Headliner" market sat at tier 1.
#
# Excluding them is fail-closed and matches withhold-never-rewrite: a step we
# cannot label truthfully is dropped, never relabelled. The mis-tiering itself is
# upstream of this route and is filed separately.
_NOT_A_TITLE_QUESTION: tuple[str, ...] = (
    "playoff qualifier",  # qualifying for the playoffs is not winning a title
    "of the year",  # awards are tier 3's question, not a championship
    "halftime",  # entertainment markets carrying a football tier
)


def _answers_its_tier(market_name: str | None) -> bool:
    """False when a market's question is not the one its tier would label it with."""
    lowered = (market_name or "").lower()
    return not any(fragment in lowered for fragment in _NOT_A_TITLE_QUESTION)


# The averaging below assumes every candidate in a tier is the SAME question
# priced by different sources ("MLB World Series Champion 2026" and "Pro Baseball
# Champion" agree to 0.4pp). When candidates disagree they are different
# questions — or, measured on production, different TEAMS sharing one team_id
# ("New York Y" and "New York M" both resolve to 6610) — and nothing in the row
# says which one the tier is about, so the step is withheld rather than averaged
# into a number that describes neither.
_TIER_AGREEMENT_BAR = 0.05


def _tier_candidates_agree(probabilities: list[float]) -> bool:
    """True when every source priced this tier's question within the bar.

    The spread is rounded to the 6 decimals ``current_probability`` is stored
    with before it meets the bar: binary floats put ``0.10`` and ``0.15`` a
    hair's breadth either side of a 0.05 bar depending on which two values
    produced them, which would make the boundary decide by rounding error.
    """
    if not probabilities:
        return False
    spread = round(max(probabilities) - min(probabilities), 6)
    return spread <= _TIER_AGREEMENT_BAR


def _championship_path_stmt(team_id: int):
    """The tier-1/2/4 selection for a team's championship path.

    Hoisted out of :func:`_get_championship_path` so a test can COMPILE it. The
    caller swallows every exception into an empty path, so a statement that
    cannot compile is indistinguishable from a team with no markets — which is
    how #1752 stayed invisible while the section was dark on every team page.
    """
    # Markets with a graded winner are settled (gotcha #33: status stays 'open').
    # `.correlate(FuturesMarket)` is load-bearing (#1752): without it SQLAlchemy
    # auto-correlates BOTH entities, the subquery is left with no FROM clause and
    # the whole statement raises InvalidRequestError at compile time.
    graded = (
        select(FuturesOutcome.id)
        .where(
            FuturesOutcome.market_id == FuturesMarket.id,
            FuturesOutcome.is_winner.is_(True),
        )
        .correlate(FuturesMarket)
    )

    return (
        select(FuturesOutcome, FuturesMarket)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesOutcome.team_id == team_id,
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),
            FuturesMarket.market_tier.in_([1, 2, 4]),
            ~graded.exists(),
        )
        .order_by(FuturesMarket.market_tier.asc())
    )


async def _get_championship_path(
    team_id: int,
    db: AsyncSession,
    league_slug: str | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Get championship/conference/division probabilities for a team.

    The championship path is FORWARD-looking, so it must exclude:
      1. Settled markets — a graded winner exists even while Kalshi keeps the
         market ``status='open'`` (gotcha #33). A settled prior-season market
         with a graded outcome near 100% was leaking into next season's path as
         a bogus "99.5% Division" number (Queue #242 Item 1).
      2. Prior-season markets — the market's season is numerically before the
         league's current season.
      3. Future-season markets (e.g. "2027 Champion" when it is 2025-26).
      4. Markets whose question is not the one their tier labels them with
         (#1752) — see :data:`_NOT_A_TITLE_QUESTION`.

    Averages probabilities when multiple sources provide markets at the same
    tier, and stamps each entry with the season it describes. A tier whose
    candidates DISAGREE is withheld rather than averaged (#1752): the averaging
    premise is "one question, several sources", and when it fails the mean
    describes none of them.
    """
    now = now or datetime.now(timezone.utc)

    result = await db.execute(_championship_path_stmt(team_id))

    # Current-season cutoff: the maximum year that counts as "this season".
    # For a 2025-26 season the cutoff is 2026; a market referencing 2027 is
    # future-season and should be excluded.
    max_year = now.year

    # Current-season base year for prior-season exclusion (e.g. a settled 2025-26
    # market must not show up once the 2026-27 season's markets are the truth).
    current_season = (
        season_windows.season_string(league_slug, now) if league_slug else None
    )
    current_base = _season_base_year(current_season)

    tier_labels = {1: "Championship", 2: "Conference", 4: "Division"}

    # Collect all valid outcomes per tier, then pick the best per tier.
    # dict: tier → list of (probability, outcome, market) tuples
    tier_candidates: dict[int, list[tuple[float, object, object]]] = {}

    for outcome, market in result.all():
        # Skip future-season markets (same fix as #471 for championship grid)
        if _is_future_season(market.name or "", max_year):
            continue

        # Skip markets whose question is not the one this tier would label them
        # with (#1752) — a qualification or award market rendered as "Win
        # Division" / "Win Championship" is a claim the team never made.
        if not _answers_its_tier(market.name):
            continue

        # Skip prior-season markets: the market's own season predates the current
        # league season. Markets with no year in their name pass through.
        if current_base is not None:
            mkt_season = _extract_championship_season(market)
            mkt_base = _season_base_year(mkt_season)
            if mkt_base is not None and mkt_base < current_base:
                continue

        prob = float(outcome.current_probability) if outcome.current_probability else None
        if prob is None:
            continue

        tier = market.market_tier
        tier_candidates.setdefault(tier, []).append((prob, outcome, market))

    path = []
    for tier in sorted(tier_candidates.keys()):
        candidates = tier_candidates[tier]

        # Withhold a step whose sources disagree (#1752). Measured on every
        # candidate the tier holds, BEFORE the group_id dedupe below, so the
        # check sees the full disagreement rather than whichever member of a
        # group survived deduplication.
        if not _tier_candidates_agree([p for p, _, _ in candidates]):
            logger.info(
                "team page: withholding championship-path tier %s for team %s — "
                "%d candidates disagree beyond %.2f (%s)",
                tier,
                team_id,
                len(candidates),
                _TIER_AGREEMENT_BAR,
                ", ".join(
                    f"{(m.name or '?')[:40]}={p:.3f}" for p, _, m in candidates
                ),
            )
            continue

        # Deduplicate by group_id: if multiple outcomes share the same
        # group_id, keep only the one with the highest probability (they
        # are from the same underlying market, just different sub-markets).
        seen_groups: set[str] = set()
        deduped: list[tuple[float, object, object]] = []
        for prob, outcome, market in candidates:
            gid = market.group_id
            if gid and gid in seen_groups:
                continue
            if gid:
                seen_groups.add(gid)
            deduped.append((prob, outcome, market))

        if not deduped:
            continue

        # Average probability across sources for robustness; use the
        # market with the highest probability for display metadata.
        avg_prob = sum(p for p, _, _ in deduped) / len(deduped)
        best_prob, best_outcome, best_market = max(deduped, key=lambda x: x[0])

        # Sanity check: if the averaged probability exceeds 1.0, log a warning
        if avg_prob > 1.0:
            logger.warning(
                "Championship path tier %d for team %d has probability %.3f > 1.0 "
                "(from %d candidates); clamping to 1.0",
                tier, team_id, avg_prob, len(deduped),
            )
            avg_prob = 1.0

        path.append({
            "tier": tier,
            "label": tier_labels.get(tier, "Other"),
            "market_name": best_market.name,
            "market_id": best_market.id,
            "probability": round(avg_prob, 4),
            "rank": best_outcome.rank,
            "movement": float(best_outcome.probability_change_24h) if best_outcome.probability_change_24h else None,
            # Season this number describes (Queue #242 Item 1) — prefer the
            # market's own season, fall back to the league's current season.
            "season": _extract_championship_season(best_market) or current_season,
        })

    return path
