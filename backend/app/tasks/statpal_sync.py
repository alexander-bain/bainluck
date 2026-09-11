"""StatPal sync task — schedules, injuries, standings and game times.

StatPal serves as the canonical source for:
1. **Event schedules** — fixture lists with accurate start times (corrects The Odds API time errors)
2. **Injuries** — structured injury reports for "Why Did the Line Move?" context
3. **Game start/end times** — authoritative window for when markets should be open/close
4. **Standings** — league tables

The cadences, which are `beat_schedule`'s to state and are quoted here only as
a map (that file is the authority, gotcha #12):
- Schedules: hourly, per sport — upserts fixtures, corrects commence_time, populates end_time
- Injuries: hourly at :20 — injury reports feed into line movement analysis
- Livescores: every 30s — real-time scores for live games

RETIRED 2026-09-09 by #2907 (CERT-2381/2387), and named here because their
absence is the point: **rosters, team-stats and play-by-play**. The venue does
not publish any of them under our key — `/teams`, `/injuries`,
`/teams/{id}/roster` and `fixtures/{id}/playbyplay` all 404 — and the three
beats banked hundreds of successes a day writing zero rows for their whole
lives. See `RETIRED_VENUE_PATHS` in `services/statpal_api.py` before adding a
caller back.

WHAT A RUN OF THIS MODULE CLAIMS. Every task here returns a `terminal` and is
enrolled in `task_verdict.ENFORCED_TASKS`, because the failure mode this module
actually has is not a crash — it is a green row. `_get` turns every upstream
failure into `None`, callers turned `None` into `[]`, and `[]` is also what "no
games today" looks like (gotcha #53). A schedule pass that could not reach the
venue must not report the same thing as one that correctly wrote nothing.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from itertools import zip_longest
from typing import Collection, Optional, Sequence

from sqlalchemy import select, update, or_, func

from app.tasks.base import get_task_session
from app.tasks.config import STATPAL_SPORT_MAPPING
from app.utils.sport_keys import STATPAL_LIVE_ANCHOR_FIELD
from app.utils.team_binding_invariant import accept_team_binding
from app.utils.game_pairing import Pairing, live_write_is_premature, pair_verdict

logger = logging.getLogger(__name__)


def statpal_provided_an_id(value: Optional[str]) -> bool:
    """Did StatPal actually give us an id for this fixture? (#2963)

    Hoisted and named because it is a judgement, not a null check, and because
    the two values it has to reject are the two that have already shipped as
    defects on this column:

    * ``None`` — the field was absent.
    * ``''`` — what ``_parse_single_fixture`` produces when it recognises none of
      ``id`` / ``contestid`` / ``fixture_id``. **A blank is not an absence, it is
      an unusable linkage**: 8,272 rows once carried ``''`` for exactly this
      reason, and every reader that tests ``statpal_fixture_id IS NOT NULL``
      counted every one of them as linked.

    Whitespace is stripped before the test for the same reason: a provider that
    serves ``' '`` has told us nothing, and a truthiness check would disagree.
    """
    return bool(str(value or "").strip())


def row_for_statpal_id(
    rows: Sequence,
    *,
    sport_ids: Collection[int],
) -> tuple[Optional[object], bool, list]:
    """Which of the rows carrying one StatPal id is THE game? (#4307, #4322)

    Returns ``(row, collided, foreign)``. ``collided`` is the same-sport finding;
    ``foreign`` is the cross-sport one; ``row`` is ``None`` whenever there is not
    exactly one candidate inside ``sport_ids``.

    ``sport_ids`` IS REQUIRED, AND IT IS THE SET FOR A **STATPAL** SPORT (#4322)
    ═══════════════════════════════════════════════════════════════════════════
    StatPal scopes its fixture ids by its own sport, so one token can name an NFL
    fixture and an MLB one. CERT-853 measured exactly that — *"an NFL claim for
    StatPal fixture ``280445`` returned the MLB event of the same token"* — which
    is why ``event_registry._find_statpal_row_in_sport`` bounds the identical
    column and why this, the last unbounded reader of it, now does too.

    **Not the caller's single ``sport_id``.** ``STATPAL_SPORT_MAPPING`` is
    many-to-one: seven of our league keys map to StatPal ``soccer``, so a fixture
    fetched during ``soccer_epl``'s iteration legitimately belongs to an event
    whose sport is ``soccer_italy_serie_a``. Bounding on the loop's own sport
    would refuse those — a false miss on every soccer league but one. The bound
    is the id space StatPal actually scopes by, which is the set of our sports
    mapping to this StatPal sport.

    Keyword-only and mandatory on purpose: a bound that defaults to "unbounded"
    is the defect wearing a parameter, and the next caller would inherit it
    silently.

    The partition is done here rather than in SQL, matching
    ``_find_statpal_row_in_sport``'s shape, for its reason: a ``WHERE`` clause
    would make the foreign row *invisible*, and D55 requires a collision to raise
    or tag and never to silently no-op. The caller warns with both id sets.

    Hoisted and named for the same reason ``statpal_provided_an_id`` was: the
    interesting case is a judgement, not a lookup. ``statpal_fixture_id`` is
    supposed to name one game, and in production it does not always — seven ids
    were carried by two rows each on 2026-09-09 (NHL 3, MLB 2, NBA 2), every one
    of them a twin.

    THE DEFECT THIS REPLACES
    ════════════════════════
    The call site read ``fid_result.scalar_one_or_none()``, which **raises**
    ``MultipleResultsFound`` on two rows. ``get_task_session`` commits only on a
    clean exit and rolls back on any exception, and ``_sync_statpal_schedules``
    has no intermediate commit — so one ambiguous fixture discarded the whole
    sport's pass, including every fixture already processed before it. Measured:
    7 of ~9.6 MLB passes dead in a 9.56h window, 21 Sentry events in 24h
    (``BAINLUCK-16X``), from 2026-09-08 01:03Z. Gotcha #42 — one bad item must
    never wipe a pass.

    WHY NOT ``.first()``
    ════════════════════
    Because it answers a question we cannot answer. The two rows are a twin: one
    is the game and one is a ghost, and which is which is not knowable from the
    id they share — it is precisely what they disagree about. ``.first()`` would
    enrich an arbitrary one of them, silently, and stamping the twin deepens it.
    D55: a collision raises or tags, never silently no-ops. Skipping tags it —
    the caller counts the refusal and names both rows in the log — and leaves
    the twin to the matching lane (D35, #2693), which is the only lane that may
    repair it.

    So a collision costs one fixture's enrichment for one pass. The raise cost
    every fixture's, every pass.
    """
    own: list = []
    foreign: list = []
    for row in rows:
        # `is None` is not folded into the membership test: a row with no
        # sport_id at all is not "in some other sport", it is unclassifiable,
        # and enriching it on a shared token is the write this refuses.
        bucket = own if getattr(row, "sport_id", None) in sport_ids else foreign
        bucket.append(row)

    if len(own) > 1:
        return None, True, foreign
    return (own[0] if own else None), False, foreign


async def _sync_statpal_schedules(sport_key: Optional[str] = None) -> dict:
    """Sync fixture schedules from StatPal for all mapped sports.

    For each sport, fetches today's + upcoming fixtures and:
    - Corrects commence_time on existing events (The Odds API sometimes has wrong times)
    - Populates end_time for finished games (market close window)
    - Stores StatPal fixture ID on events for later play-by-play lookups

    Args:
        sport_key: If provided, only sync this sport. Otherwise syncs all mapped sports.

    Returns:
        Summary dict with counts per sport.
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    # #2907: `terminal: skipped` rather than a bare `skipped` flag. Both of
    # these are deliberate no-ops, but without the terminal they classified as
    # `_LEGACY` — a non-authoritative `unknown` indistinguishable from a run
    # that fell over. `no_work` is the vocabulary `task_verdict` already reads.
    if not is_available():
        return {"terminal": "skipped", "skipped": True, "reason": "STATPAL_API_KEY not set"}

    if sport_key:
        sport_keys = [sport_key] if sport_key in STATPAL_SPORT_MAPPING else []
    else:
        sport_keys = list(STATPAL_SPORT_MAPPING.keys())

    if not sport_keys:
        return {
            "terminal": "skipped",
            "skipped": True,
            "reason": f"sport_key {sport_key!r} not in STATPAL_SPORT_MAPPING",
        }

    service = StatPalAPIService()
    total_updated = 0
    # #4775. TWO counts, and they are not the same quantity. `fixtures_served`
    # is what the venue handed us; `fixtures_in_window` is the subset inside the
    # `-1d/+7d` filter below. Until now only the second one existed and it was
    # published as `total_fixtures_fetched`, standing in one payload beside a
    # per-sport `fixtures_fetched` that meant the other thing — 16 against 374
    # for the same NFL pass on 2026-09-10, with `live_games` also 16 so the
    # wrong reading looked corroborated. Both names now say which pool they
    # counted.
    #
    # The served total is DERIVED from `details` at the return rather than
    # carried in its own counter, so the two can never drift: a sport whose loop
    # exits early adds nothing to either side of the reconciliation, and there
    # is no second place to forget to increment.
    fixtures_in_window = 0
    details = []

    total_created = 0

    # #1918. A refusal here means an upstream index proposed a club that is not the
    # one this row names — previously invisible, because the write simply succeeded.
    # Surfaced in the task result so a spike is a finding rather than a log line
    # nobody reads (the same treatment `refused_anchored` got on the merge rail).
    binding_stats: dict = {}

    # #1945/#1947. Both counters are surfaced in the task result for the same
    # reason `binding_stats` is: a refusal that only logs is a refusal nobody
    # measures, and these two are the ones that stand between a live score and a
    # game that has not been played yet.
    live_pair_refused = 0
    premature_live_skipped = 0
    # Q438: creations this path DOWNGRADED to 'scheduled' because the game had
    # not started. Always present; 0 is a reading, not an absence (gotcha #53).
    premature_live_created_as_scheduled = 0
    # #2963. Live fixtures this path REFUSED to create because StatPal served no
    # id for them. Always present; 0 is a reading, and 0 is what NFL should read
    # now that `contestid` is parsed — a non-zero here names a sport whose live
    # payload has no id field we know about, which is a finding, not a shrug.
    live_created_refused_no_provider_id = 0
    # #2963, the schedule-path twin. Expected to stay 0 — no row in production has
    # ever carried a `statpal_<home>_<away>` value — and it is reported anyway so
    # that "has never fired" stays a measured claim.
    schedule_created_refused_no_provider_id = 0
    # #4307. Past fixtures this path declined to enrich because their StatPal id
    # named more than one event row. Always present; 0 is a reading, and a
    # non-zero here is a TWIN COUNT — the same population #3093/#3463 track from
    # the other side — surfaced where the pass that trips over it can be seen.
    schedule_fid_collision_skipped = 0

    # #4322. The other half of the same judgement, kept as its OWN number so the
    # twin count stays a twin count. A cross-sport hit is not a twin — it is one
    # provider's id space reused across two of its sports — and folding it into
    # the count above would corrupt the population #3093/#3463 read from there.
    # Always present; 0 is a reading (gotcha #53), and today it is the expected
    # one: zero cross-sport collisions exist in production (2026-09-09).
    schedule_fid_cross_sport_skipped = 0

    # #2907 acceptance bullet 2. The sports this pass could not READ, as opposed
    # to the sports that had nothing to report — `[]` is both, and this task is
    # #2867's ship, so a silently dark venue is the one outcome it must never
    # bank as a success. Always present; `[]` is the reading (gotcha #53).
    fetch_failures: list[dict] = []
    #: Denominator for the terminal below: a pass that asked nobody is not a
    #: pass that heard from everybody. Counts sports actually ASKED, not sports
    #: looped over — see the `fetch.asked` gate below.
    sports_asked = 0
    #: Mapped sports this pass named and could not ask, with the reason. Named
    #: rather than merely uncounted: a terminal that says "nothing happened" is
    #: only useful if the summary also says WHICH sports went unasked, and the
    #: difference between `sports_asked` and `len(sport_keys)` is otherwise a
    #: subtraction the reader has to do and cannot attribute.
    sports_unasked: list[dict] = []

    # Track StatPal fixture IDs already processed in this run
    # to prevent duplicates across soccer league iterations
    # (all map to StatPal sport="soccer" but have different sport_ids)
    seen_fixture_ids: set[str] = set()

    try:
        async with get_task_session() as session:
            from app.models import Event, Sport

            # #4322. The id space StatPal scopes its fixture ids by is its OWN
            # sport, and our league keys are many-to-one onto it. Resolved
            # through `_statpal_sport_key_filter` — the SAME predicate the
            # injury attach uses — so soccer's space is every `soccer%` sport
            # the hourly stamper writes to, not just the seven the schedule map
            # names. Built once per pass, and for EVERY StatPal sport rather
            # than only this run's, because a single-sport run still has to
            # recognise a sibling league's event as same-sport.
            statpal_sport_ids: dict[str, set[int]] = {}
            for _statpal_sport in set(STATPAL_SPORT_MAPPING.values()):
                statpal_sport_ids[_statpal_sport] = set(
                    (
                        await session.execute(
                            select(Sport.id).where(
                                _statpal_sport_key_filter(_statpal_sport)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )

            for our_key in sport_keys:
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                # Find the Sport record
                sport_result = await session.execute(
                    select(Sport.id).where(Sport.key == our_key)
                )
                sport_row = sport_result.first()
                if not sport_row:
                    details.append({"sport": our_key, "status": "sport_not_found"})
                    # #4710. The OTHER way a mapped sport goes unasked, and the
                    # one the #2907 repair missed: this branch `continue`s above
                    # the fetch, so before this append the summary named only
                    # `no_day_token` sports and left a `sport_not_found` sport to
                    # be inferred by subtracting `sports_asked` from the key
                    # count — an attribution the reader cannot actually make.
                    # The terminal was already right (this arm never reaches
                    # `sports_asked += 1`), but "correct terminal, unattributed
                    # summary" is the shape gotcha #53 exists to stop, and the
                    # two reasons want opposite responses: a missing `sports`
                    # row is a gap we can close by minting one, `no_day_token`
                    # is a permanent property of StatPal's product.
                    sports_unasked.append({
                        "sport": our_key,
                        "statpal_sport": statpal_sport,
                        "reason": "sport_not_found",
                    })
                    continue

                sport_id = sport_row.id

                # Fetch schedule — season-schedule returns full season for v1 sports
                # We'll filter to a useful window (yesterday to +7 days) in the loop
                #
                # `_result`, not the list: a dark venue and a sport with no games
                # both hand back `[]`, and this task exists to make games EXIST
                # (#2867). Reporting "could not ask" as "nothing to do" is the
                # one failure it must not have (#2907, gotcha #53).
                fetch = await service.get_fixtures_result(statpal_sport)
                fixtures = fetch.fixtures
                if fetch.is_alarm:
                    fetch_failures.append({
                        "sport": our_key,
                        "statpal_sport": statpal_sport,
                        "reason": fetch.reason,
                        "endpoint": fetch.endpoint,
                    })
                    logger.error(
                        "StatPal schedules %s: %s — not an empty schedule (#2907)",
                        our_key, fetch.reason,
                    )

                # #2907 repair `2907-NO-DAY-TOKEN-IS-NOT-A-SUCCESS`. This counter
                # used to increment here unconditionally, one line below a result
                # object carrying `asked` for precisely this question.
                #
                # `no_day_token` is not an alarm and must not be — it is a
                # permanent property of StatPal's product, not an outage, and
                # `is_alarm` is right to exclude it. But "not an alarm" is not
                # "asked". The day-board sports cannot be reached through this
                # method at all, so counting them here made `sports_asked` a
                # count of sports we LOOPED OVER, and the terminal that reads it
                # then called a pass complete on the strength of sports nobody
                # spoke to. That is this issue's own defect a third time: first
                # `[]` for a dark venue, then `complete` for a pass that asked
                # nobody, now `complete` for a pass that asked nobody it named.
                #
                # NINE of the thirteen mapped keys are day-board (soccer ×7,
                # tennis ×2), so the all-sports form of this call reaches here
                # unasked far more often than it ever reached `sport_not_found`.
                if not fetch.asked:
                    sports_unasked.append({
                        "sport": our_key,
                        "statpal_sport": statpal_sport,
                        "reason": fetch.reason,
                    })
                    logger.info(
                        "StatPal schedules %s: %s — not asked, not a schedule (#2907)",
                        our_key, fetch.reason,
                    )
                    continue

                sports_asked += 1

                # Also fetch live scores to get current game state
                live = await service.get_live_scores(statpal_sport)
                live_by_teams = {}
                for f in live:
                    key = _fixture_match_key(f.home_team, f.away_team)
                    live_by_teams[key] = f

                sport_updated = 0
                sport_created = 0
                now = datetime.now(timezone.utc)
                window_start = now - timedelta(days=1)
                window_end = now + timedelta(days=7)

                for fixture in fixtures:
                    if not fixture.home_team or not fixture.away_team:
                        continue

                    # Filter to relevant window — skip fixtures outside -1d to +7d
                    if fixture.start_time:
                        if fixture.start_time < window_start or fixture.start_time > window_end:
                            continue

                    # #4775. Counted INSIDE the window filter, which is exactly
                    # why it may not be published under a name reading "fetched".
                    fixtures_in_window += 1

                    # Dedup: skip if this StatPal fixture was already processed
                    # in a prior sport key iteration (e.g., soccer_epl and soccer_usa_mls
                    # both query StatPal sport="soccer" and get identical fixtures)
                    if fixture.fixture_id:
                        if fixture.fixture_id in seen_fixture_ids:
                            continue
                        seen_fixture_ids.add(fixture.fixture_id)

                    # Find matching event in our DB by team names + time proximity
                    match_key = _fixture_match_key(fixture.home_team, fixture.away_team)
                    live_data = live_by_teams.get(match_key)
                    # #1945: `live_by_teams` is keyed on the team pair ALONE. In a
                    # 3-4 game MLB series every fixture in this -1d/+7d window
                    # shares that key with tonight's live game, so an unchecked
                    # `live_data` writes tonight's score onto a row dated two days
                    # out. The team pair is a matchup; only matchup + instant is a
                    # game. UNKNOWN (a live row with no start time) is NOT trusted
                    # here — the premature guard at the write site below is the
                    # unconditional backstop, so refusing costs a score update we
                    # could not justify, never one we could.
                    if live_data is not None and pair_verdict(
                        fixture.start_time, getattr(live_data, "start_time", None),
                    ) is not Pairing.SAME:
                        live_pair_refused += 1
                        live_data = None

                    # ── Unified event matching via Event Registry ──
                    # Only create events for future games
                    if not fixture.start_time or fixture.start_time <= now:
                        # For past fixtures, try to find existing event to enrich
                        event = None
                        if fixture.fixture_id:
                            fid_result = await session.execute(
                                select(Event).where(
                                    Event.statpal_fixture_id == fixture.fixture_id
                                )
                            )
                            # #4307. `scalar_one_or_none()` here RAISED on the
                            # seven ids production carries on two rows each, and
                            # the raise rolled back the whole sport's pass (see
                            # `row_for_statpal_id`). Ambiguity is now a counted
                            # refusal for one fixture instead of a lost hour.
                            candidates = fid_result.scalars().all()
                            # #4322. Bounded by the StatPal sport's id space, not
                            # by `sport_id` — seven of our keys are `soccer`.
                            allowed_sport_ids = statpal_sport_ids.get(
                                statpal_sport
                            ) or {sport_id}
                            event, collided, foreign = row_for_statpal_id(
                                candidates, sport_ids=allowed_sport_ids,
                            )
                            if foreign:
                                # D55: tagged, never invisible. Reported whether
                                # or not it changed the outcome, because a token
                                # shared across two of StatPal's sports is a
                                # finding on its own (CERT-853).
                                logger.warning(
                                    "StatPal schedule-enrich: fixture id %s is also "
                                    "carried by event(s) %s in sport(s) %s, outside "
                                    "this pass's StatPal sport %r (sport_ids %s). "
                                    "Cross-sport id reuse, NOT a twin — refusing to "
                                    "enrich them (#4322, CERT-853).",
                                    fixture.fixture_id,
                                    # Both sorts tolerate a None: a log line that
                                    # raises inside the pass would re-create the
                                    # very failure #4307 just retired.
                                    sorted(
                                        (getattr(r, "id", None) for r in foreign),
                                        key=lambda v: (v is None, v),
                                    ),
                                    sorted(
                                        {getattr(r, "sport_id", None) for r in foreign},
                                        key=lambda v: (v is None, v),
                                    ),
                                    statpal_sport,
                                    sorted(allowed_sport_ids),
                                )
                                if event is None and not collided:
                                    # Every candidate was foreign, so the old
                                    # unbounded read would have enriched another
                                    # sport's row. Counted apart from the twins.
                                    schedule_fid_cross_sport_skipped += 1
                            if collided:
                                schedule_fid_collision_skipped += 1
                                logger.warning(
                                    "StatPal schedule-enrich refused: fixture id %s "
                                    "names %d event rows (%s) for %s vs %s (%s). Two "
                                    "rows for one game — filed as a matching symptom, "
                                    "not repaired here (D35, #2693). Skipping this "
                                    "fixture so the pass survives (#4307).",
                                    fixture.fixture_id, len(candidates),
                                    ", ".join(str(getattr(c, "id", "?")) for c in candidates),
                                    fixture.away_team, fixture.home_team, our_key,
                                )
                                continue
                        if not event:
                            continue  # Past game, no existing event — skip
                    else:
                        from app.services.event_registry import (
                            find_or_create_event, EventIdentity, EventClaim,
                            STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
                        )
                        # #2963, the schedule-path twin of the live-path refusal
                        # below. This read
                        #
                        #     claim_id = fixture.fixture_id or f"statpal_{home}_{away}"
                        #
                        # and the comment under it already conceded the fallback
                        # "was never an anchor either — a label wearing an id's
                        # clothing, ruling 042". A label wearing an id's clothing is
                        # not a thing to keep passing to the registry.
                        #
                        # MEASURED before changing it: zero rows in production have
                        # ever carried a `statpal_<home>_<away>` value (census
                        # 2026-09-05 and again 2026-09-06, whole-table, by prefix).
                        # This branch has never once fabricated, so refusing costs
                        # nothing that has ever happened — unlike its live-path twin,
                        # which had fired 48 times.
                        #
                        # AND IF IT EVER DOES FIRE, the loss is visible rather than
                        # silent: a future fixture we decline to create is exactly a
                        # `statpal_only` receipt on the authority-agreement row ("the
                        # venue has a game we don't"), which is the finding this lane
                        # exists to surface. Minting it with a fabricated anchor
                        # instead would erase the finding AND poison the column — the
                        # row would then be classified POLLUTED_COLUMN forever and
                        # could never receive its real id.
                        if not statpal_provided_an_id(fixture.fixture_id):
                            schedule_created_refused_no_provider_id += 1
                            logger.warning(
                                "StatPal schedule-create refused: no provider id for "
                                "%s vs %s (%s, start %s). A row is not created from a "
                                "fabricated id (#2963).",
                                fixture.away_team, fixture.home_team, our_key,
                                fixture.start_time.isoformat() if fixture.start_time else None,
                            )
                            continue
                        claim_id = fixture.fixture_id
                        identity = EventIdentity(
                            sport_key=our_key,
                            home_team_name=fixture.home_team,
                            away_team_name=fixture.away_team,
                            commence_time=fixture.start_time,
                            # Ruling 048: NOT arm B. `get_fixtures(sport)` is a
                            # season-schedule LISTING — we asked by sport and got
                            # rows back — so a fixture id arriving alongside its
                            # teams and date is co-arrival, not dereference.
                            # Measured 54/54 wrong-game absorptions on this site.
                            # (The synthesized `statpal_<home>_<away>` fallback id
                            # was never an anchor either — a label wearing an id's
                            # clothing, ruling 042 — so nothing is lost by no
                            # longer distinguishing the two.)
                            claim=EventClaim(
                                "statpal", claim_id,
                                schedule_derived=STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
                            ),
                            commence_time_source="statpal",
                            status="scheduled",
                        )
                        event, was_created = await find_or_create_event(
                            session, identity,
                        )
                        if was_created:
                            sport_created += 1

                    updated = False

                    # Resolve and register team identities for future indexed lookups
                    from app.services.team_identity import team_identity_service
                    home_team = await team_identity_service.resolve_team(
                        session, "statpal", our_key,
                        source_name=fixture.home_team,
                    )
                    away_team = await team_identity_service.resolve_team(
                        session, "statpal", our_key,
                        source_name=fixture.away_team,
                    )
                    # #1918: `resolve_team` reads `team_identity_mapping`, and 15 of
                    # the 30 statpal/baseball_mlb rows in that table name one club and
                    # point at another (one poisoned batch, 2026-03-25, never updated
                    # since). The exact-source_name hit is step 2 — the service's
                    # highest-confidence path — so nothing downstream doubts it, and
                    # this line wrote ~5 wrong-club sides a day. Dereference before
                    # binding; on refusal leave the column NULL for a name-keyed
                    # binder to fill correctly next cycle.
                    if not event.home_team_id and accept_team_binding(
                        side="home",
                        row_name=event.home_team_name,
                        team=home_team,
                        event_sport_id=event.sport_id,
                        source="statpal",
                        event_id=event.id,
                        stats=binding_stats,
                    ):
                        event.home_team_id = home_team.id
                        updated = True
                    if not event.away_team_id and accept_team_binding(
                        side="away",
                        row_name=event.away_team_name,
                        team=away_team,
                        event_sport_id=event.sport_id,
                        source="statpal",
                        event_id=event.id,
                        stats=binding_stats,
                    ):
                        event.away_team_id = away_team.id
                        updated = True

                    # Correct commence_time if StatPal has a different (likely more accurate) time
                    if fixture.start_time and event.commence_time:
                        diff = abs((fixture.start_time - event.commence_time).total_seconds())
                        # Only correct if >5 min difference (avoids timezone rounding)
                        if diff > 300:
                            logger.info(
                                f"StatPal: correcting commence_time for event {event.id} "
                                f"({event.home_team_name} vs {event.away_team_name}): "
                                f"{event.commence_time} -> {fixture.start_time}"
                            )
                            event.commence_time = fixture.start_time
                            if hasattr(event, "commence_time_source"):
                                event.commence_time_source = "statpal"
                            updated = True
                    if fixture.fixture_id and not _get_statpal_id(event):
                        _set_statpal_id(event, fixture.fixture_id)
                        updated = True

                    # Populate end_time for finished games
                    if fixture.end_time and fixture.status == "finished":
                        # Write to dedicated column
                        if hasattr(event, "statpal_end_time") and not event.statpal_end_time:
                            event.statpal_end_time = fixture.end_time
                            updated = True
                        # Also write to JSONB for backward compatibility
                        sources = event.win_probability_sources or {}
                        if "statpal_end_time" not in sources:
                            sources["statpal_end_time"] = fixture.end_time.isoformat()
                            event.win_probability_sources = sources
                            updated = True
                        # BR76: also transition status to completed
                        if event.status == "live":
                            event.status = "completed"
                            if not event.completed_at:
                                event.completed_at = fixture.end_time
                            updated = True

                    # Update scores from live data if available.
                    # #1945/#1947: a row whose own commence_time is still in the
                    # future cannot hold a live score, whatever the provider says —
                    # it is describing a different game. This is the guard ESPN has
                    # carried since #1207 and StatPal did not; same predicate, one
                    # implementation (`app/utils/game_pairing.py`).
                    if live_data and live_data.status == "live":
                        if live_write_is_premature(event.commence_time, now):
                            premature_live_skipped += 1
                            logger.warning(
                                "StatPal premature-live guard: refused live score on "
                                "event %d (%s vs %s) — commence_time %s is still in "
                                "the future (now %s) (#1945)",
                                event.id, event.home_team_name, event.away_team_name,
                                event.commence_time.isoformat() if event.commence_time else None,
                                now.isoformat(),
                            )
                        else:
                            if live_data.home_score is not None:
                                event.home_score = live_data.home_score
                            if live_data.away_score is not None:
                                event.away_score = live_data.away_score
                            updated = True

                    if updated:
                        sport_updated += 1

                # Create events for live games missing from DB (playoff gap fix).
                # StatPal season-schedule doesn't include playoffs, but livescores does.
                from app.services.event_registry import (
                    find_or_create_event, EventIdentity, EventClaim,
                    STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
                )
                live_created = 0
                for live_fix in live:
                    if not live_fix.home_team or not live_fix.away_team:
                        continue
                    if not live_fix.start_time:
                        continue
                    key = _fixture_match_key(live_fix.home_team, live_fix.away_team)
                    # Check if we already have this game
                    existing = await session.execute(
                        select(Event.id).where(
                            Event.sport_id == sport_id,
                            func.lower(Event.home_team_name) == live_fix.home_team.lower(),
                            func.lower(Event.away_team_name) == live_fix.away_team.lower(),
                            Event.commence_time.between(
                                live_fix.start_time - timedelta(hours=6),
                                live_fix.start_time + timedelta(hours=6),
                            ),
                        ).limit(1)
                    )
                    if existing.scalar_one_or_none():
                        continue
                    # Create the missing event.
                    #
                    # ── #2963. NO ID, NO ROW. This used to read
                    #
                    #     claim_id = live_fix.fixture_id or f"statpal_live_{home}_{away}"
                    #
                    # and that `or` fabricated a provider id out of two team names on
                    # every live fixture StatPal served without one. It fired 48 times
                    # between 2026-05-15 and 2026-08-26 — every NFL row this path has
                    # ever created — because NFL's payload keys its id `contestid` and
                    # the parser only read `id`, so `fixture_id` was `''` and falsy.
                    #
                    # WHY A FABRICATED ID IS WORSE THAN NO ROW, which is the whole of
                    # the judgment here:
                    #
                    #   * `EventClaim.anchor_source_id` is documented as "the id an
                    #     anchor key must be built from — the provider's, never ours",
                    #     and it returns `provider_id or source_id`. A synthesized
                    #     `source_id` with no `provider_id` therefore hands the anchor
                    #     channel a game key made of team names — the one shape that
                    #     can merge two real fixtures (gotcha #32, ruling 048).
                    #   * It is unrepairable in place. `stamp_nfl_statpal_fixtures`
                    #     classifies such a row POLLUTED_COLUMN and deliberately will
                    #     not write to it, so the row can never receive its real
                    #     contest id while the fabricated one sits there.
                    #   * ~11 readers treat `statpal_fixture_id IS NOT NULL` as "this
                    #     event is linked to StatPal". A fabricated value makes all of
                    #     them report a linkage that does not exist.
                    #
                    # Refusing costs nothing measured. All 48 rows this branch created
                    # were created BEFORE their own commence_time (the Q438 note
                    # below), so it has never once filled the live playoff gap it
                    # exists for; and since the parser learned `contestid` every NFL
                    # live fixture carries a real id, so this branch should now be
                    # unreachable for the only sport that ever reached it. The refusal
                    # is counted rather than silent precisely so "unreachable" stays a
                    # measured claim instead of an assumption.
                    if not statpal_provided_an_id(live_fix.fixture_id):
                        live_created_refused_no_provider_id += 1
                        logger.warning(
                            "StatPal live-create refused: no provider id for %s vs %s "
                            "(%s, start %s). A row is not created from a fabricated "
                            "id (#2963); StatPal serving no id for this sport's live "
                            "payload is the finding.",
                            live_fix.away_team, live_fix.home_team, our_key,
                            live_fix.start_time.isoformat() if live_fix.start_time else None,
                        )
                        continue
                    # #1945/Q438 — the row is created either way (the playoff gap
                    # this path exists to fill is real), but it may only be
                    # created LIVE once its own start time has arrived. Same
                    # predicate as the score write above; one implementation.
                    #
                    # 🔴 MEASURED on production 2026-08-29: this path had created
                    # **48 events since 2026-05-15, and all 48 were created
                    # BEFORE their own commence_time** — it has never once
                    # created a game that was actually in progress. 46 have since
                    # rolled to `completed`; the two still sitting `live` were
                    # 15292756 (Colts vs Lions) and 15292757 (Titans vs Bears),
                    # minted 2026-08-26 for an 2026-08-29 kickoff and badged LIVE
                    # on the NFL league page for three days.
                    premature_create = live_write_is_premature(
                        live_fix.start_time, now
                    )
                    if premature_create:
                        premature_live_created_as_scheduled += 1
                        logger.warning(
                            "StatPal premature-live guard: creating %s vs %s (%s) as "
                            "'scheduled', not 'live' — start_time %s is still in the "
                            "future (now %s) (#1945/Q438)",
                            live_fix.home_team, live_fix.away_team, our_key,
                            live_fix.start_time.isoformat() if live_fix.start_time else None,
                            now.isoformat(),
                        )
                    claim_id = live_fix.fixture_id
                    identity = EventIdentity(
                        sport_key=our_key,
                        home_team_name=live_fix.home_team,
                        away_team_name=live_fix.away_team,
                        commence_time=live_fix.start_time,
                        # Ruling 048: NOT arm B — see the season-schedule site
                        # above. `get_live_scores(sport)` is a listing too. This
                        # is the WORSE of the two sites: the ±6h pre-check just
                        # above strips the same-game case, so everything that
                        # reached the ±28h matcher was the adjacent game in the
                        # series — measured 8/8 wrong-game, at +21.9h/−24h/+4h/
                        # −24h/+22h/−20h/−20h/−20h.
                        claim=EventClaim(
                            "statpal", claim_id,
                            schedule_derived=STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
                        ),
                        commence_time_source="statpal",
                        status="scheduled" if premature_create else "live",
                    )
                    event, was_created = await find_or_create_event(
                        session, identity,
                    )
                    if was_created:
                        live_created += 1
                        # The status downgrade above and the score are the SAME
                        # claim — a game that has not started has no score to
                        # carry either, and writing one would restore the exact
                        # contradiction (`scheduled` + a live score) one field
                        # over. The sibling score path 100 lines up refuses on
                        # this predicate; so does this one.
                        if not premature_create:
                            if live_fix.home_score is not None:
                                event.home_score = live_fix.home_score
                            if live_fix.away_score is not None:
                                event.away_score = live_fix.away_score
                        logger.info(
                            "Created event from live StatPal: %s vs %s (%s) as %s",
                            live_fix.away_team, live_fix.home_team, our_key,
                            "scheduled (premature)" if premature_create else "live",
                        )
                sport_created += live_created

                total_updated += sport_updated
                total_created += sport_created
                details.append({
                    "sport": our_key,
                    "fixtures_fetched": len(fixtures),
                    "events_updated": sport_updated,
                    "events_created": sport_created,
                    "live_games": len(live),
                    "live_created": live_created,
                })

                # Rate limit between sports
                await asyncio.sleep(0.5)

    finally:
        await service.close()

    # #2907. `failed` only when EVERY sport we asked about was TOTALLY
    # unreadable. A `partial_fetch` is an alarm but it is not an outage — soccer
    # reads two boards and a pass that got one of them did read a schedule, so
    # counting it towards `failed` would overstate what happened. Anything with
    # an alarm short of that is `partial`.
    #
    # A pass where every venue answered is `complete` HOWEVER FEW ROWS IT WROTE:
    # 374 fetched and 0 created is what a season already complete from ESPN/The
    # Odds API looks like, and it must stay green or the alarm stops being read.
    #
    # And a pass that asked NOBODY is `no_work`, never `complete`. The `else`
    # below used to swallow it: `sports_asked == 0` means nothing was read and
    # nothing was written, while the summary said the same word as a healthy
    # quiet pass. That is this issue's own defect one layer above the venue.
    #
    # A sport reaches "unasked" two ways, and BOTH are counted here:
    #
    #   `sport_not_found`  the key resolves to no `sports` row, so the loop drops
    #                      it before the fetch. `golf_pga` was the production
    #                      specimen until #4691 retired the key. Counted here
    #                      only since #4710 — this comment described BOTH arms
    #                      from the day it was written, but the `continue` above
    #                      the fetch appended nothing, so the summary named one.
    #   `no_day_token`     the sport IS rowed and IS mapped, but its schedule is
    #                      served one calendar board at a time and cannot be
    #                      reached through this method at all. NINE of the
    #                      thirteen mapped keys — soccer ×7, tennis ×2.
    #
    # The second is the repair `2907-NO-DAY-TOKEN-IS-NOT-A-SUCCESS`. It is much
    # the larger of the two: the all-sports form of this call has nine unasked
    # sports on every single run, and before the gate above it counted all nine
    # towards `sports_asked` and then reported `complete`.
    #
    # A MIXED pass is `partial`, not `complete`. Four sports read and nine never
    # spoken to is a real, useful pass — it is not `failed` and it is not
    # `no_work` — but calling it `complete` says the schedule sync covered the
    # sports it names, and it did not. `partial` is already this task's word for
    # "something real happened and something is missing", and an operator who
    # sees it can read `sports_unasked` for which sports and why.
    #
    # #4710 moves ONE terminal, deliberately, and only on the all-sports form:
    # a pass that asked somebody AND dropped a `sport_not_found` sport used to
    # read `complete` and now reads `partial`, because the rule two paragraphs
    # up always said it should and the missing append was why it didn't. No
    # BEAT terminal moves: all four beats pass a single explicit `sport_key`
    # (`sync-statpal-schedules-{nba,nhl,mlb,nfl}`), as does the #4434 in-line
    # failover, so `sports_asked` is 0 or 1 there and a one-sport pass that
    # cannot find its row reads `no_work` before and after.
    #
    # `no_work` is authoritative UNKNOWN in `task_verdict` — not a failure,
    # because nothing upstream is broken, and emphatically not a success.
    total_failures = sum(1 for f in fetch_failures if f["reason"] == "fetch_failed")
    if not sports_asked:
        terminal = "no_work"
    elif total_failures == sports_asked:
        terminal = "failed"
    elif fetch_failures or sports_unasked:
        terminal = "partial"
    else:
        terminal = "complete"

    return {
        "terminal": terminal,
        # Always present; `[]` is the reading, not an absence.
        "fetch_failures": fetch_failures,
        "sports_asked": sports_asked,
        # Always present; `[]` is the reading, not an absence — same rule as
        # `fetch_failures`, and for the same reason.
        "sports_unasked": sports_unasked,
        "events_updated": total_updated,
        "events_created": total_created,
        # #4775. `total_fixtures_fetched` is now what the venue actually served
        # — the sum of the per-sport `fixtures_fetched` rows below, so an
        # operator reading the top line and an operator reading the sport rows
        # cannot reach different conclusions about the same pass. The filtered
        # count keeps its own key and names the pool it counted.
        #
        # `.get(..., 0)`, not `[...]`: `details` also carries the #4710
        # `sport_not_found` rows, which have no `fixtures_fetched` because
        # nothing was ever asked for them. A strict read here raised `KeyError`
        # and took the whole all-sports pass down with it — the one form of this
        # task that reaches that arm.
        "total_fixtures_fetched": sum(
            d.get("fixtures_fetched", 0) for d in details
        ),
        "total_fixtures_in_window": fixtures_in_window,
        "sports": details,
        # Always present, and 0 is the meaningful reading — an absent key would make
        # "the guard found nothing" indistinguishable from "the guard did not run".
        "team_binding_refused": binding_stats.get("team_binding_refused", 0),
        "team_binding_refused_detail": {
            k: v for k, v in binding_stats.items() if k != "team_binding_refused"
        },
        # #1945/#1947 — same rule: always present, 0 is a reading.
        "live_pair_refused": live_pair_refused,
        "premature_live_skipped": premature_live_skipped,
        "premature_live_created_as_scheduled": premature_live_created_as_scheduled,
        # #2963 — same rule again: always present, and 0 is the reading that says
        # the fabricator is unreachable rather than merely unobserved.
        "live_created_refused_no_provider_id": live_created_refused_no_provider_id,
        "schedule_created_refused_no_provider_id": schedule_created_refused_no_provider_id,
        # #4307 — same rule: always present, and 0 is the reading that says no
        # fixture in this window is claimed by two rows.
        "schedule_fid_collision_skipped": schedule_fid_collision_skipped,
        # #4322 — same rule, and its own key so the twin count above stays a twin
        # count. 0 is the expected reading today: production carries zero
        # cross-sport fixture ids (measured 2026-09-09, and the generator of the
        # only known one — #3094's mis-stamped MLB ids — was cleared).
        "schedule_fid_cross_sport_skipped": schedule_fid_cross_sport_skipped,
    }


#: Which of OUR sport keys can receive a given StatPal sport's injuries.
#:
#: `STATPAL_SPORT_MAPPING` lists seven soccer keys because those are the ones we
#: pull SCHEDULES for. StatPal's injury product is one call covering twenty
#: leagues, and 105 of the 168 soccer events in the attach window on 2026-09-06
#: sat under keys the map does not name (`soccer_brazil_campeonato`,
#: `soccer_mexico_ligamx`, `soccer_other`, …). Restricting the attach to the
#: schedule map would throw away most of the coverage for no reason: the pair
#: rule decides what belongs to what, not the league key.
#:
#: Widening `STATPAL_SPORT_MAPPING` itself would change what the schedule sync
#: CREATES, which is a different ship with a different blast radius. Nothing
#: here touches that: both readers below only decide which EXISTING rows a
#: StatPal sport may be resolved against.
#:
#: #4322 — SECOND READER, SAME RULE. The schedule sync's fixture-id bound
#: (`_statpal_sport_key_filter`) needs the identical question answered, for the
#: identical reason, so it shares this constant instead of re-deriving it from
#: the seven-key map. That drift is not hypothetical: the first cut of #4322 did
#: bound on the map's seven soccer keys, and it would have called a
#: `soccer_efl_champ` row FOREIGN — refusing an enrichment the unbounded reader
#: got right — because the hourly soccer stamper (`stamp_v1_statpal_fixtures`,
#: live since `dd753773`) writes `statpal_fixture_id` across every `soccer%`
#: sport: 34 of them in production on 2026-09-09, all inside ONE StatPal id
#: band (9.29M-9.55M). `sport_keys.STATPAL_SHADOW_ANCHOR_SPORT_PREFIXES` cites
#: this constant by name for the same reason; it is now the third.
_INJURY_EVENT_SPORT_PREFIX: dict[str, str] = {"soccer": "soccer"}


def _statpal_sport_key_filter(statpal_sport: str):
    """Which of OUR sports share THIS StatPal sport's id space? (#4322)

    A prefix where the StatPal sport has one, else the schedule map's keys —
    the rule :data:`_INJURY_EVENT_SPORT_PREFIX` documents. Returned as a
    SQLAlchemy predicate on ``Sport.key`` so both readers are transcriptions of
    one rule rather than two readings of it.

    Tennis is deliberately NOT prefixed here. The map names ``tennis_atp`` and
    ``tennis_wta`` while production's rows sit on ``tennis_atp_us_open`` and
    friends, so tennis has the same latent narrowness soccer had — but the
    schedule sync has no tennis beat (the four beat entries are nba/nhl/mlb/nfl)
    and the injury attach's tennis behaviour would move with it. Adding
    ``"tennis": "tennis"`` above is the whole fix when a caller needs it; doing
    it now would change a live path to buy nothing.
    """
    # Imported here, not at module scope, matching every other reader in this
    # file: `app.models` is not import-safe from task modules at load time.
    from app.models import Sport

    prefix = _INJURY_EVENT_SPORT_PREFIX.get(statpal_sport)
    if prefix:
        return Sport.key.like(f"{prefix}%")
    return Sport.key.in_(
        [k for k, v in STATPAL_SPORT_MAPPING.items() if v == statpal_sport]
    )


def _interleave_sides(injuries: list) -> list:
    """Home, away, home, away … so a 10-cap cannot silence one whole team.

    A shared cap over two unequal populations empties the smaller one first. In
    the 2026-09-06 payload, 22 of 146 fixtures carried more than ten sidelined
    players and **4 of them would have shown only one side** in vendor order —
    and the reader that consumes this list attributes a line move to the team
    that FELL, so a game where only the home side survived the cap can never
    explain an away-side drop, however many away players are hurt.

    Order within a side is preserved; nothing is dropped here, only reordered.
    """
    home = [inj for inj in injuries if inj.is_home]
    away = [inj for inj in injuries if not inj.is_home]
    ordered = []
    for pair in zip_longest(home, away):
        ordered.extend(inj for inj in pair if inj is not None)
    return ordered


async def _sync_statpal_injuries(sport_key: Optional[str] = None) -> dict:
    """Sync injury reports from StatPal onto events for line-movement context.

    Injuries land in `Event.win_probability_sources['statpal_injuries']`, which
    `routes/events.py` merges with ESPN's (ESPN wins a name collision) to ground
    the "Why did the line move?" explanation.

    Three things here are load-bearing and each replaced something that made the
    task incapable of producing a row:

    * **One fetch per StatPal sport, not per Odds-API key.** Seven of our keys
      map to `soccer`; the old loop asked for the same 224 KB payload seven times
      an hour and attributed each copy to one league.
    * **`get_injuries_result`, not `get_injuries`.** "The venue has no injury
      product for this sport", "we asked and it broke" and "nobody is hurt" were
      the same empty list (gotcha #53). Only the middle one is an alarm, and the
      terminal below now says which happened.
    * **A Core `update()` for the JSONB write.** Gotcha #4.

    Args:
        sport_key: If provided, only sync the StatPal sport this key maps to.

    Returns:
        Summary dict carrying a `terminal` — `statpal_injuries` is enrolled in
        `task_verdict.ENFORCED_TASKS`, so a run that could not read the venue
        reads NOT-GREEN instead of looking like a quiet day.
    """
    from app.services.statpal_api import StatPalAPIService, is_available
    from app.utils.statpal_injury_attach import Fixture, choose_fixture

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set", "terminal": "skipped"}

    if sport_key:
        statpal_sports = (
            [STATPAL_SPORT_MAPPING[sport_key]] if sport_key in STATPAL_SPORT_MAPPING else []
        )
    else:
        # dict.fromkeys: dedupe, order preserved — seven soccer keys, one fetch.
        statpal_sports = list(dict.fromkeys(STATPAL_SPORT_MAPPING.values()))

    if not statpal_sports:
        return {
            "skipped": True,
            "reason": f"sport_key {sport_key!r} not in STATPAL_SPORT_MAPPING",
            "terminal": "skipped",
        }

    service = StatPalAPIService()
    total_injuries = 0
    total_events_enriched = 0
    total_events_cleared = 0
    details = []
    fetch_failures = []

    try:
        async with get_task_session() as session:
            from app.models import Event, Sport

            for statpal_sport in statpal_sports:
                fetch = await service.get_injuries_result(statpal_sport)

                if not fetch.asked:
                    # Not a failure and not a quiet day: the venue publishes no
                    # injury path for this sport at all (#2907). Recorded so the
                    # absence is legible without re-probing.
                    details.append({
                        "statpal_sport": statpal_sport,
                        "reason": fetch.reason,
                        "injuries_fetched": 0,
                        "events_enriched": 0,
                    })
                    continue

                if fetch.is_alarm:
                    fetch_failures.append(
                        {"statpal_sport": statpal_sport, "endpoint": fetch.endpoint}
                    )
                    details.append({
                        "statpal_sport": statpal_sport,
                        "reason": fetch.reason,
                        "injuries_fetched": 0,
                        "events_enriched": 0,
                    })
                    await asyncio.sleep(0.3)
                    continue

                injuries = fetch.injuries
                total_injuries += len(injuries)

                # Group by the FIXTURE the player's team is playing, keeping both
                # sides of it — the attach decision needs the pair, not the team.
                by_fixture: dict[str, list] = {}
                fixtures: dict[str, Fixture] = {}
                for inj in injuries:
                    home, away = (
                        (inj.team, inj.opponent) if inj.is_home
                        else (inj.opponent, inj.team)
                    )
                    # `main_id` is present on 1,002 of the 1,004 rows served on
                    # 2026-09-06; one fixture published only a fallback. The
                    # last-resort key is built from HOME|AWAY, never
                    # team|opponent, or the two sides of one match key
                    # differently and split it into two fixtures.
                    key = (
                        inj.fixture_main_id
                        or (inj.fixture_fallback_ids[0] if inj.fixture_fallback_ids else None)
                        or f"{home}|{away}|{inj.fixture_date}"
                    )
                    by_fixture.setdefault(key, []).append(inj)
                    if key not in fixtures:
                        fixtures[key] = Fixture(
                            key=key,
                            home=home,
                            away=away,
                            fixture_date=(
                                inj.fixture_date.date() if inj.fixture_date else None
                            ),
                        )

                # #4322: hoisted verbatim into `_statpal_sport_key_filter` and
                # now shared with the schedule sync's fixture-id bound. Same
                # predicate, same constant, no behaviour change here.
                sport_filter = _statpal_sport_key_filter(statpal_sport)

                now = datetime.now(timezone.utc)
                window_start = now - timedelta(hours=6)
                window_end = now + timedelta(days=2)

                result = await session.execute(
                    select(
                        Event.id,
                        Event.home_team_name,
                        Event.away_team_name,
                        Event.commence_time,
                        Event.win_probability_sources,
                    )
                    .join(Sport, Sport.id == Event.sport_id)
                    .where(
                        sport_filter,
                        Event.commence_time.between(window_start, window_end),
                        Event.status.in_(["scheduled", "live"]),
                    )
                )
                events = result.all()

                enriched = 0
                cleared = 0
                candidates = list(fixtures.values())
                for event in events:
                    chosen = choose_fixture(
                        event.home_team_name,
                        event.away_team_name,
                        event.commence_time.date() if event.commence_time else None,
                        candidates,
                    )

                    sources = dict(event.win_probability_sources or {})

                    if not chosen:
                        # A SUCCESSFUL snapshot that does not list this fixture is
                        # current information: there is nobody sidelined for it
                        # now. Writing only additively would leave yesterday's
                        # list in place forever, and `routes/events.py` reads it
                        # with no freshness check — so a recovered player would
                        # keep being printed as the cause of a line move. This
                        # branch is reachable ONLY on `ok`/`empty`; a
                        # `fetch_failed` sport returned long before here, so a
                        # bad upstream day never deletes what we already know.
                        if "statpal_injuries" not in sources:
                            continue
                        sources.pop("statpal_injuries", None)
                        sources.pop("statpal_injuries_updated", None)
                        cleared += 1
                    else:
                        sources["statpal_injuries"] = [
                            {
                                "player": inj.player_name,
                                "team": inj.team,
                                "status": inj.status,
                                "type": inj.injury_type,
                                "detail": inj.detail,
                            }
                            for inj in _interleave_sides(by_fixture[chosen])[:10]
                        ]
                        sources["statpal_injuries_updated"] = now.isoformat()
                        enriched += 1

                    # Core update, not ORM attribute assignment (gotcha #4).
                    await session.execute(
                        update(Event)
                        .where(Event.id == event.id)
                        .values(win_probability_sources=sources)
                    )

                total_events_enriched += enriched
                total_events_cleared += cleared
                details.append({
                    "statpal_sport": statpal_sport,
                    "reason": fetch.reason,
                    "injuries_fetched": len(injuries),
                    "fixtures_with_injuries": len(by_fixture),
                    "events_considered": len(events),
                    "events_enriched": enriched,
                    "events_cleared": cleared,
                })

                await asyncio.sleep(0.3)

    finally:
        await service.close()

    # A run that could not read a supported venue path is FAILED, not a quiet
    # day — that confusion is the whole reason this task wrote nothing for as
    # long as it existed and nothing said so.
    terminal = "failed" if fetch_failures else "complete"

    return {
        "terminal": terminal,
        "total_injuries": total_injuries,
        "events_enriched": total_events_enriched,
        "events_cleared": total_events_cleared,
        "fetch_failures": fetch_failures,
        "sports": details,
    }


async def _sync_statpal_livescores() -> dict:
    """Poll StatPal livescores for real-time game state updates.

    StatPal updates livescores every 15 seconds across all 13 sports.
    This task runs every 30 seconds and updates:
    - Current score (home_score, away_score)
    - Game period/status via ScoreSnapshot enrichment
    - Event status transitions (live → completed)

    Unlike the hourly schedule sync, this is a lightweight call that only
    hits the livescores endpoint (not the full season schedule).
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set"}

    service = StatPalAPIService()
    total_updated = 0
    total_score_snaps = 0
    details = []
    # #1945: a refusal that only logs is a refusal nobody measures.
    premature_live_skipped = 0
    _now = datetime.now(timezone.utc)

    # Only poll sports that are likely to have live games right now.
    # We check which sports have live events in our DB first, then
    # only call StatPal livescores for those sports.
    try:
        async with get_task_session() as session:
            from app.models import Event, Sport
            from app.models.models import ScoreSnapshot

            # Find which StatPal sports have live events
            live_sport_result = await session.execute(
                select(Sport.key, Sport.id).join(
                    Event, Event.sport_id == Sport.id
                ).where(
                    Event.status == "live"
                ).distinct()
            )
            live_sports = {
                row.key: row.id
                for row in live_sport_result.all()
                if row.key in STATPAL_SPORT_MAPPING
            }

            if not live_sports:
                return {"skipped": True, "reason": "no live events for StatPal sports"}

            # Deduplicate StatPal sport identifiers (multiple leagues → same sport)
            seen_statpal_sports: set[str] = set()

            for our_key, sport_id in live_sports.items():
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                # Skip if we already polled this StatPal sport (e.g., multiple soccer leagues)
                if statpal_sport in seen_statpal_sports:
                    continue
                seen_statpal_sports.add(statpal_sport)

                live_fixtures = await service.get_live_scores(statpal_sport)
                if not live_fixtures:
                    continue

                # Build lookup by team names
                fixture_by_teams: dict[str, object] = {}
                for f in live_fixtures:
                    key = _fixture_match_key(f.home_team, f.away_team)
                    fixture_by_teams[key] = f

                # Find our live events for ALL sport keys that map to this StatPal sport
                matching_sport_keys = [
                    k for k, v in STATPAL_SPORT_MAPPING.items()
                    if v == statpal_sport and k in live_sports
                ]
                sport_ids = [live_sports[k] for k in matching_sport_keys]

                events_result = await session.execute(
                    select(Event).where(
                        Event.sport_id.in_(sport_ids),
                        Event.status == "live",
                    )
                )
                live_events = events_result.scalars().all()

                sport_updated = 0
                sport_snaps = 0
                sport_anchor_skips = 0

                for event in live_events:
                    match_key = _fixture_match_key(
                        event.home_team_name or "",
                        event.away_team_name or "",
                    )
                    fixture = fixture_by_teams.get(match_key)
                    if not fixture:
                        continue

                    # #1945: this is the third site keyed on the team pair alone,
                    # and it is the PROPAGATOR — the `status='live'` query above has
                    # no time bound, so once a future-dated row has been flipped
                    # live it keeps being fed tonight's score every 60s. A row that
                    # has not started cannot be live; refuse and let the row's own
                    # status transition fix it, rather than keep it plausible.
                    if live_write_is_premature(event.commence_time, _now):
                        premature_live_skipped += 1
                        logger.warning(
                            "StatPal premature-live guard: refused live score on "
                            "event %d (%s vs %s) — commence_time %s is still in the "
                            "future (now %s) (#1945)",
                            event.id, event.home_team_name, event.away_team_name,
                            event.commence_time.isoformat() if event.commence_time else None,
                            _now.isoformat(),
                        )
                        continue

                    updated = False

                    # Update period/clock from StatPal raw_status (e.g., "Q3", "1H", "HT")
                    #
                    # #5017: compose the SAME string ESPN writes, so a flipped
                    # sport reads identically to an unflipped one. ESPN sets
                    # `event.period = ee.status_detail`, which is the compound
                    # `'14:53 - 3rd Quarter'`; StatPal serves the two halves
                    # separately (`timer` + `status`), so joining them gives
                    # byte-identical output and the front end needs no change
                    # (`trustedLiveClock` suppresses the duplicate clock only
                    # when the period spells it out, which this does).
                    #
                    # The clock is written BESIDE the period deliberately. A
                    # period-only fix would advance the quarter while
                    # `game_clock` stayed frozen at whatever ESPN last wrote
                    # before the flip — and a frozen label reads as stale, but a
                    # frozen clock reads as CURRENT. That is worse than the bug.
                    # `getattr`: this writer consumes duck-typed fixtures from
                    # several construction paths, and the line below already
                    # reads `raw_status` defensively for the same reason.
                    fixture_clock = getattr(fixture, "game_clock", None)
                    if fixture.raw_status and fixture.raw_status not in ("live", "Live"):
                        # Guard on the clock being non-empty, not on liveness:
                        # halftime is genuinely live and genuinely has no clock,
                        # so one guard is not enough (#5017).
                        new_period = (
                            f"{fixture_clock} - {fixture.raw_status}"
                            if fixture_clock
                            else fixture.raw_status
                        )
                        if event.period != new_period:
                            event.period = new_period
                            updated = True

                        # CLEAR THE CLOCK WHEN THE VENUE CLEARS IT (CERT-2569).
                        #
                        # This assignment is deliberately NOT guarded on
                        # `fixture_clock` being truthy. On a row the venue is
                        # actively labelling as in-progress, the venue is
                        # authoritative for the clock INCLUDING its absence:
                        # halftime and the terminal both arrive with no timer
                        # (measured — `'Halftime'` and `'Final'` both carry
                        # `timer=''`).
                        #
                        # Guarding on truthiness reintroduces, at halftime, the
                        # exact bug this ship exists to fix: the period would
                        # advance to `'Halftime'` while `game_clock` kept the
                        # last quarter's value, and `trustedLiveClock` preserves
                        # both — so the reader sees a running-looking clock the
                        # venue had already cleared. A stale label degrades
                        # visibly; a stale clock lies quietly. Where we cannot
                        # write a true clock, NULL is the honest value.
                        if event.game_clock != fixture_clock:
                            event.game_clock = fixture_clock
                            updated = True

                    # Update scores
                    if fixture.home_score is not None and fixture.home_score != event.home_score:
                        event.home_score = fixture.home_score
                        updated = True
                    if fixture.away_score is not None and fixture.away_score != event.away_score:
                        event.away_score = fixture.away_score
                        updated = True

                    # Write ScoreSnapshot for score enrichment (feeds Score Differential chart)
                    if updated and fixture.home_score is not None and fixture.away_score is not None:
                        # Check if this score is different from the last snapshot
                        last_snap_result = await session.execute(
                            select(ScoreSnapshot.home_score, ScoreSnapshot.away_score)
                            .where(ScoreSnapshot.event_id == event.id)
                            .order_by(ScoreSnapshot.captured_at.desc())
                            .limit(1)
                        )
                        last_snap = last_snap_result.first()
                        if (
                            not last_snap
                            or last_snap.home_score != fixture.home_score
                            or last_snap.away_score != fixture.away_score
                        ):
                            session.add(ScoreSnapshot(
                                event_id=event.id,
                                home_score=fixture.home_score,
                                away_score=fixture.away_score,
                            ))
                            sport_snaps += 1

                    # Link StatPal fixture ID if not already linked.
                    #
                    # #3094: from the LIVE endpoint, and for MLB the live `id` is
                    # a third id space that dereferences to nothing on the
                    # schedule — see `STATPAL_LIVE_ANCHOR_FIELD`. Take the field
                    # that sport declares, not the one the parser happened to
                    # find first. The SCHEDULE writer above is deliberately NOT
                    # changed: `get_fixtures` reads `season-schedule` for MLB,
                    # whose `id` already IS the anchor.
                    anchor_id = _live_anchor_id(fixture, statpal_sport)
                    if anchor_id and not _get_statpal_id(event):
                        _set_statpal_id(event, anchor_id)
                        updated = True
                    elif (
                        not anchor_id
                        and fixture.fixture_id
                        and not _get_statpal_id(event)
                    ):
                        # The sport declares an anchor field and this row does
                        # not carry it — 3 of 16 live MLB rows have `oddsid: ""`.
                        # Leave the column NULL rather than filling it with the
                        # live id: an empty column is a row the schedule pass can
                        # still anchor correctly, while a wrong-space id is a
                        # linkage that reads as authoritative and joins to
                        # nothing. Counted, because a silent skip is how 364 rows
                        # accumulated in the first place.
                        sport_anchor_skips += 1

                    if updated:
                        sport_updated += 1

                total_updated += sport_updated
                total_score_snaps += sport_snaps
                detail = {
                    "sport": statpal_sport,
                    "live_fixtures": len(live_fixtures),
                    "events_updated": sport_updated,
                    "score_snapshots": sport_snaps,
                }
                # #3094: reported only for the sports that declare an anchor
                # field, so the key's presence says "this sport has a second id
                # space" and its value says how many live rows could not be
                # anchored from it this pass. Emitting a 0 for every other sport
                # would make the number look like a general health metric it is
                # not. The residue is expected and bounded — 3 of 16 live MLB
                # rows carried `oddsid: ""` when it was measured — so this is a
                # figure to watch, not an error to raise.
                if statpal_sport in STATPAL_LIVE_ANCHOR_FIELD:
                    detail["anchor_field"] = STATPAL_LIVE_ANCHOR_FIELD[statpal_sport]
                    detail["anchor_skipped_no_field"] = sport_anchor_skips
                details.append(detail)

    finally:
        await service.close()

    return {
        "events_updated": total_updated,
        "score_snapshots_created": total_score_snaps,
        "sports_polled": len(details),
        "sports": details,
        "premature_live_skipped": premature_live_skipped,
    }


# =============================================================================
# Helper functions
# =============================================================================


def live_row_bears_state(fixture) -> bool:
    """Can `_sync_statpal_livescores` advance an event's SCORE or PERIOD from this row?

    #3473 / CERT-2047. Lives here, beside the writer whose behaviour it
    describes, and is exported for `utils/authority_failover`'s readiness check
    — because a failover that accepts a row the writer will skip declares
    StatPal to be serving over a pass that writes nothing. Readiness and the
    writer have to answer "is this row useful?" the same way, and the only
    reliable way to make two answers agree is to have one.

    It mirrors, exactly, the three conditions the loop above sets `updated` on
    that touch game state:

      * `fixture.home_score is not None` / `away_score is not None`;
      * a `raw_status` that is not the bare literal `live`/`Live` — the loop
        writes `event.period` only from a raw status that says something more
        than "this is a live game" (`Q3`, `1H`, `HT`).

    It deliberately does NOT count the fourth `updated` branch, the
    `fixture_id` backfill. That link is an id repair, not live state: it would
    let a `scheduled` row with no scores and no period read as "StatPal is
    serving this game", which is the precise mistake CERT-2047 caught.

    Proven against the writer rather than asserted:
    `test_a_stateless_live_row_advances_nothing_through_the_real_writer` runs
    the real task over a row this rejects and shows score and period unmoved.
    """
    if getattr(fixture, "home_score", None) is not None:
        return True
    if getattr(fixture, "away_score", None) is not None:
        return True
    raw = getattr(fixture, "raw_status", None)
    return bool(raw and raw not in ("live", "Live"))


def _fixture_match_key(home: str, away: str) -> str:
    """Create a normalized key for matching fixtures to events."""
    import unicodedata

    def _normalize(s: str) -> str:
        s = "".join(
            c for c in unicodedata.normalize("NFD", s)
            if unicodedata.category(c) != "Mn"
        )
        return s.lower().strip()

    return f"{_normalize(home)}|{_normalize(away)}"


async def _find_matching_event(session, Event, sport_id: int, fixture) -> Optional:
    """Find a matching Event record for a StatPal fixture.

    Uses token-overlap name matching + time proximity (±6 hours) to find the best match.
    """
    from app.utils.name_normalization import token_overlap_score, normalize_name

    if not fixture.home_team or not fixture.away_team:
        return None

    home_lower = normalize_name(fixture.home_team)
    away_lower = normalize_name(fixture.away_team)

    # Build time window
    if fixture.start_time:
        window_start = fixture.start_time - timedelta(hours=6)
        window_end = fixture.start_time + timedelta(hours=6)
    else:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=1)
        window_end = now + timedelta(days=7)

    # Query for candidates — broader filter using multiple last-word tokens
    # to catch more candidates for scoring
    from sqlalchemy import func as sqlfunc

    # Use last meaningful word from each team (skip 1-char words)
    home_words = [w for w in home_lower.split() if len(w) > 2]
    away_words = [w for w in away_lower.split() if len(w) > 2]
    home_last = home_words[-1] if home_words else home_lower.split()[-1]
    away_last = away_words[-1] if away_words else away_lower.split()[-1]

    result = await session.execute(
        select(Event).where(
            Event.sport_id == sport_id,
            Event.commence_time.between(window_start, window_end),
            or_(
                sqlfunc.lower(Event.home_team_name).contains(home_last),
                sqlfunc.lower(Event.away_team_name).contains(away_last),
                sqlfunc.lower(Event.home_team_name).contains(home_words[0] if home_words else home_last),
                sqlfunc.lower(Event.away_team_name).contains(away_words[0] if away_words else away_last),
            ),
        ).limit(20)
    )
    candidates = result.scalars().all()

    if not candidates:
        return None

    # Score candidates using token_overlap_score for robust name matching
    best = None
    best_score = -1.0

    for event in candidates:
        home_score = token_overlap_score(fixture.home_team, event.home_team_name)
        away_score = token_overlap_score(fixture.away_team, event.away_team_name)

        # Require both teams to match at some level
        if home_score < 0.4 or away_score < 0.4:
            continue

        score = home_score + away_score  # 0.0 - 2.0

        # Time proximity bonus (up to 0.3)
        if fixture.start_time and event.commence_time:
            diff_hours = abs((fixture.start_time - event.commence_time).total_seconds()) / 3600
            if diff_hours < 1:
                score += 0.3
            elif diff_hours < 3:
                score += 0.2
            elif diff_hours < 6:
                score += 0.1

        if score > best_score:
            best_score = score
            best = event

    # Require minimum combined score of 1.0 (both teams at least partially match)
    return best if best_score >= 1.0 else None


def _get_statpal_id(event) -> Optional[str]:
    """Get the StatPal fixture ID stored on an event."""
    # Prefer the dedicated column, fall back to JSONB
    if hasattr(event, "statpal_fixture_id") and event.statpal_fixture_id:
        return event.statpal_fixture_id
    sources = event.win_probability_sources or {}
    return sources.get("statpal_fixture_id")


def _live_anchor_id(fixture, statpal_sport: str) -> Optional[str]:
    """The id a LIVE StatPal fixture may be anchored by, for this sport (#3094).

    Returns `None` when the sport declares an anchor field and this row does not
    carry it. `None` means *write nothing*, and that is the point: the caller
    must not fall back to `fixture.fixture_id`, because for a sport in
    `STATPAL_LIVE_ANCHOR_FIELD` that value is the id space the anchor must not
    be in. An empty column is a row the schedule pass can still anchor
    correctly; a wrong-space id is a linkage that reads as authoritative and
    dereferences to nothing.

    Sports not in the map keep the parser's answer unchanged — this is a
    declaration for the measured exception, not a new rule for everyone. See
    `STATPAL_LIVE_ANCHOR_FIELD` for why MLB is that exception and why the space
    cannot be told from the number's shape.
    """
    field = STATPAL_LIVE_ANCHOR_FIELD.get(statpal_sport)
    if field is None:
        return str(getattr(fixture, "fixture_id", "") or "").strip() or None
    return str(getattr(fixture, field, "") or "").strip() or None


def _set_statpal_id(event, fixture_id: str):
    """Store the StatPal fixture ID on an event."""
    # Write to dedicated column
    if hasattr(event, "statpal_fixture_id"):
        event.statpal_fixture_id = fixture_id
    # Also write to JSONB for backward compatibility during migration
    sources = event.win_probability_sources or {}
    sources["statpal_fixture_id"] = fixture_id
    event.win_probability_sources = sources


# =============================================================================
# Standings sync
# =============================================================================


#: The key between `standings` and `league[]` is NOT constant across StatPal's
#: own sports. Measured against the venue 2026-09-10 (all four HTTP 200, #4732):
#:
#:     nfl   standings.category.league[].division[].team[]    32 teams
#:     mlb   standings.category.league[].division[].team[]    30 teams
#:     nba   standings.tournament.league[].division[].team[]  30 teams
#:     nhl   standings.tournament.league[].division[].team[]  32 teams
#:
#: Navigating `tournament` alone cost NFL and MLB every standings row they have
#: ever had — both read zero from inception, in season, on mornings their two
#: siblings wrote successfully. One wrapper key, two whole leagues.
STANDINGS_WRAPPER_KEYS = ("tournament", "category")


def _standings_league_node(inner: dict) -> Optional[dict]:
    """Return the node under `standings` that carries `league[]`, or None.

    Known wrapper names are tried first and in a fixed order so the reading is
    deterministic. The structural fallback exists because #4732 was a whole
    sport lost to a key NAME: any child dict carrying `league` is the node we
    were looking for, whatever the vendor decided to call it, and finding it
    that way costs nothing when the name is already known.
    """
    if not isinstance(inner, dict):
        return None
    if "league" in inner:
        return inner
    for key in STANDINGS_WRAPPER_KEYS:
        node = inner.get(key)
        if isinstance(node, dict) and "league" in node:
            return node
    for value in inner.values():
        if isinstance(value, dict) and "league" in value:
            return value
    return None


async def _sync_statpal_standings(sport_key: Optional[str] = None) -> dict:
    """Sync league standings from StatPal and store on Team records.

    Args:
        sport_key: If provided, only sync this sport.

    Returns:
        Summary dict with update counts.
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return {"terminal": "skipped", "skipped": True, "reason": "STATPAL_API_KEY not set"}

    if sport_key:
        sport_keys = [sport_key] if sport_key in STATPAL_SPORT_MAPPING else []
    else:
        sport_keys = list(STATPAL_SPORT_MAPPING.keys())

    service = StatPalAPIService()
    total_updated = 0
    details = []
    now = datetime.now(timezone.utc)

    # Terminal accounting, ported from the schedules task (#2907, #4710). This
    # task had NO terminal fields at all — `task_verdict` read it as
    # `not_enforced(unknown:no_terminal_fields)` — so a pass that wrote 62 rows
    # for two off-season sports and 0 for the two in season banked the same
    # green as a pass that got everything (#4732).
    fetch_failures: list[dict] = []
    sports_asked = 0
    #: TWO arms reach "unasked" here, and both are appended below — the count is
    #: stated because #4710 was a comment that enumerated two arms while the code
    #: implemented one, and the comment is exactly what stopped anybody checking:
    #:
    #:   `sport_not_found`     the key resolves to no `sports` row, so the loop
    #:                         drops it before the fetch.
    #:   `no_venue_path`       the sport IS rowed and IS mapped, but StatPal
    #:                         serves no standings product for it — soccer and
    #:                         tennis both answer HTTP 404 (measured 2026-09-10).
    #:                         NINE of the thirteen mapped keys: soccer ×7,
    #:                         tennis ×2.
    #:
    #: The second is much the larger, exactly as `no_day_token` is on the
    #: schedules side, and for the same reason: it is a permanent property of the
    #: vendor's product, so it must not be counted as asked and must not alarm.
    sports_unasked: list[dict] = []

    try:
        async with get_task_session() as session:
            from app.models import Team, Sport

            for our_key in sport_keys:
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                sport_result = await session.execute(
                    select(Sport.id).where(Sport.key == our_key)
                )
                sport_row = sport_result.first()
                if not sport_row:
                    details.append({"sport": our_key, "status": "sport_not_found"})
                    sports_unasked.append({
                        "sport": our_key,
                        "statpal_sport": statpal_sport,
                        "reason": "sport_not_found",
                    })
                    continue

                sport_id = sport_row.id

                # Fetch standings from StatPal. The result object, not the bare
                # payload: `None` alone cannot tell "no standings product"
                # (permanent, 9 of 13 keys) from "we asked and it broke"
                # (gotcha #53), and this task banked green on both.
                fetch = await service.get_standings_result(statpal_sport)
                standings_data = fetch.data

                if not fetch.asked:
                    details.append({"sport": our_key, "status": fetch.reason})
                    sports_unasked.append({
                        "sport": our_key,
                        "statpal_sport": statpal_sport,
                        "reason": fetch.reason,
                    })
                    continue

                # Counted BEFORE the failure branch, not after: a sport we asked
                # and could not read is still a sport we asked, and the `failed`
                # terminal is "every sport I asked was unreadable". Incrementing
                # after the `continue` made a wholly dark pass read `no_work` —
                # authoritative UNKNOWN — which is the one thing an outage must
                # not look like.
                sports_asked += 1

                if fetch.is_alarm or not standings_data:
                    details.append({"sport": our_key, "status": "no_standings"})
                    fetch_failures.append({
                        "sport": our_key,
                        "statpal_sport": statpal_sport,
                        "reason": fetch.reason,
                        "endpoint": fetch.endpoint,
                    })
                    continue

                # Get our DB teams for matching
                result = await session.execute(
                    select(Team).where(Team.sport_id == sport_id)
                )
                db_teams = result.scalars().all()

                # Build name lookup (lowercase name → Team)
                db_by_name: dict[str, Team] = {}
                for t in db_teams:
                    db_by_name[t.name.lower()] = t
                    if t.alternate_names:
                        for alt in t.alternate_names:
                            db_by_name[alt.lower()] = t

                sport_updated = 0

                # Parse standings — StatPal returns nested format:
                # {"standings": {"tournament": {"league": [{"division": [{"team": [...]}]}]}}}
                teams_list = []
                if isinstance(standings_data, list):
                    teams_list = standings_data
                elif isinstance(standings_data, dict):
                    inner = standings_data.get("standings", standings_data)
                    if isinstance(inner, list):
                        teams_list = inner
                    elif isinstance(inner, dict):
                        # Navigate: <wrapper>.league[].division[].team[]
                        tournament = _standings_league_node(inner)
                        if tournament is not None:
                            leagues = tournament.get("league", [])
                            if isinstance(leagues, dict):
                                leagues = [leagues]
                            for league in leagues:
                                if not isinstance(league, dict):
                                    continue
                                league_name = league.get("name", "")
                                divisions = league.get("division", [])
                                if isinstance(divisions, dict):
                                    divisions = [divisions]
                                for div in divisions:
                                    if not isinstance(div, dict):
                                        continue
                                    div_name = div.get("name", "")
                                    div_teams = div.get("team", [])
                                    if isinstance(div_teams, dict):
                                        div_teams = [div_teams]
                                    for t in div_teams:
                                        if isinstance(t, dict):
                                            # Inject conference/division from structure
                                            t["_conference"] = league_name
                                            t["_division"] = div_name
                                            t["_rank_scope"] = "division"
                                            # The team's `position` is scoped by
                                            # the node it hangs under, and here
                                            # that is ALWAYS a division. Recorded
                                            # at the point the structure is still
                                            # in hand — by the time the field map
                                            # below runs, a flat dict cannot say
                                            # what its own rank was counted over.
                                            teams_list.append(t)
                        # Fallback: groups/teams patterns
                        if not teams_list:
                            if "groups" in inner:
                                for group in inner.get("groups", []):
                                    teams_list.extend(group.get("teams", []))
                            elif "teams" in inner:
                                teams_list = inner["teams"]
                    if not teams_list:
                        # This line existed through every one of #4732's silent
                        # months and could not have caught it: it printed
                        # `standings_data.keys()`, which is `['standings']` for
                        # NFL, MLB, NBA and NHL alike — the one key the two
                        # broken sports shared with the two working ones. The
                        # keys that discriminate are one level in.
                        logger.warning(
                            "Standings for %s: parsed 0 teams — outer keys=%s inner keys=%s",
                            our_key,
                            sorted(standings_data),
                            sorted(inner) if isinstance(inner, dict) else type(inner).__name__,
                        )

                logger.info(f"Standings for {our_key}: parsed {len(teams_list)} teams")

                for team_entry in teams_list:
                    if not isinstance(team_entry, dict):
                        continue

                    # Try to match to our team
                    team_name = (team_entry.get("name") or team_entry.get("team_name") or "").strip()
                    if not team_name:
                        continue

                    db_team = db_by_name.get(team_name.lower())
                    if not db_team:
                        # Try suffix match (e.g., "Celtics" matches "Boston Celtics")
                        last_word = team_name.split()[-1].lower()
                        for key, t in db_by_name.items():
                            if key.endswith(last_word) or last_word in key:
                                db_team = t
                                break

                    if not db_team:
                        logger.debug(f"Standings: no match for '{team_name}' in {our_key}")
                        continue

                    # Extract standings fields — map StatPal names to our canonical names
                    parsed = {}
                    # StatPal uses "won"/"lost", we normalize to "wins"/"losses"
                    wins = team_entry.get("won") or team_entry.get("wins")
                    losses = team_entry.get("lost") or team_entry.get("losses")
                    if wins is not None:
                        parsed["wins"] = int(wins)
                    if losses is not None:
                        parsed["losses"] = int(losses)

                    # WHERE THE RANK IS COUNTED, AND WHY IT IS NOT `conf_rank`.
                    #
                    # `position` used to be stored as `conf_rank` unconditionally.
                    # It is read off a team nested under `league[].division[]`,
                    # so it is the team's place IN ITS DIVISION — and both
                    # renderers say "conference" when they see `conf_rank`
                    # (`events.py` `_standings_context` prints "#1 Eastern
                    # Conference"; `RelatedFutures.tsx`'s `StandingsCard` puts
                    # the number against `standings.conference`).
                    #
                    # Measured on production 2026-09-10, and it is not a
                    # judgement call — a conference has exactly one #1, so a
                    # conference-scoped rank cannot repeat within a conference:
                    #
                    #   26 (conference, conf_rank) pairs are shared by >1 team.
                    #   FOUR NBA teams read "#1 Eastern Conference" at once —
                    #   Boston (Atlantic), Detroit (Central), and two more.
                    #
                    # That is a live TRUTH defect on the 75 NBA/NHL teams that
                    # have standings today, and #4732 would have extended it to
                    # NFL and MLB. The number was always right; the word beside
                    # it was wrong. `div_rank` is the field both renderers pair
                    # with `division`, so the fix is the label, not the value.
                    #
                    # NO CONFERENCE RANK IS SYNTHESISED. It is derivable-looking
                    # — sort a conference's teams by win pct — and that is the
                    # trap: NFL and NBA seeding turn on tiebreakers we do not
                    # model, so a computed "#3 AFC" would be a fabricated
                    # authority wearing the venue's credibility. A conference
                    # rank needs a conference-scoped source. Until one exists
                    # the claim is simply not made.
                    #
                    # Consequence, deliberate: `_standings_context`'s "Top seed
                    # matchup" reads `conf_rank` and stops firing. It was firing
                    # on this mislabel — two teams third in their own divisions
                    # scored as a top-seed game — so this removes a false
                    # signal, and `test_top_seed_stakes_is_not_claimed_from_a_
                    # division_rank` pins that it stays removed. Its sibling
                    # "Division rivals" reads `div_rank`, has been unreachable
                    # for as long as nothing wrote that key (0 rows in
                    # production), and starts working for the first time.
                    rank_field = "div_rank" if team_entry.get("_rank_scope") == "division" else "league_rank"

                    # Direct fields — numeric
                    for src, dst in [
                        ("draws", "draws"), ("ties", "ties"),
                        ("points", "points"),
                        ("goals_for", "goals_for"), ("goals_against", "goals_against"),
                        ("goal_difference", "goal_difference"),
                        ("position", rank_field),
                    ]:
                        val = team_entry.get(src)
                        if val is not None:
                            try:
                                parsed[dst] = int(val)
                            except (ValueError, TypeError):
                                parsed[dst] = val

                    # Direct fields — string/mixed
                    for src, dst in [
                        ("gb", "games_behind"),
                        ("streak", "streak"),
                        ("last_10", "last_10"),
                        ("home_record", "home_record"),
                        ("road_record", "road_record"),
                    ]:
                        val = team_entry.get(src)
                        if val is not None:
                            parsed[dst] = val

                    # Win percentage — use StatPal's "percentage" or compute
                    pct = team_entry.get("percentage") or team_entry.get("pct")
                    if pct:
                        parsed["pct"] = str(pct)
                    elif "wins" in parsed and "losses" in parsed:
                        w, l = parsed["wins"], parsed["losses"]
                        if w + l > 0:
                            parsed["pct"] = f".{round(1000 * w / (w + l)):03d}"

                    # Conference/division from structure (injected during parsing)
                    if team_entry.get("_conference"):
                        parsed["conference"] = team_entry["_conference"]
                    if team_entry.get("_division"):
                        parsed["division"] = team_entry["_division"]

                    if parsed:
                        db_team.standings_data = parsed
                        db_team.standings_updated_at = now
                        sport_updated += 1

                total_updated += sport_updated
                details.append({
                    "sport": our_key,
                    "teams_in_standings": len(teams_list),
                    "teams_updated": sport_updated,
                })

                # The venue answered and we stored nothing. This is #4732's own
                # defect: NFL and MLB reached here on every run since inception,
                # in season, with a 200 and a full table in hand, and the pass
                # still banked `success` on the strength of the two off-season
                # siblings beside them. A zero here is never routine — the only
                # sports that get this far are the four WITH a standings
                # product, and those tables are not empty during a season.
                if not teams_list:
                    fetch_failures.append({
                        "sport": our_key,
                        "statpal_sport": statpal_sport,
                        "reason": "parsed_zero_teams",
                        "endpoint": fetch.endpoint,
                    })
                elif not sport_updated:
                    fetch_failures.append({
                        "sport": our_key,
                        "statpal_sport": statpal_sport,
                        "reason": "matched_zero_teams",
                        "endpoint": fetch.endpoint,
                    })

                await asyncio.sleep(0.3)

    finally:
        await service.close()

    # Terminal, read the way the schedules task reads its own (#2907), with ONE
    # deliberate divergence spelled out below. `total_teams_updated` cannot carry
    # this alone: 62 is a healthy-looking number and it is precisely the number
    # NFL and MLB were entirely absent from.
    #
    # THE DIVERGENCE. On the schedules side ANY entry in `sports_unasked` makes a
    # pass `partial`. Here only the `sport_not_found` arm does. The difference is
    # the BEAT, not the principle:
    #
    #   * every scheduled `sync-statpal-schedules-*` beat passes an explicit
    #     `sport_key`, so that task's unasked list is empty in production and
    #     `partial` stays a signal;
    #   * `sync-statpal-standings-daily` passes NO `sport_key` — the all-sports
    #     form is the only form it ever runs.
    #
    # So counting the nine permanent `no_venue_path` keys would put this task in
    # `partial` on every run it will ever make. A terminal that is always amber
    # cannot report the day a table goes empty, and that day is the whole of
    # #4732. `no_venue_path` is still REPORTED in `sports_unasked` — the choice
    # is between grading it and hiding it, and this hides nothing.
    #
    # `sport_not_found` still grades, because that arm is our own config being
    # wrong and is fixable — #4691 was exactly that, and it sat for months.
    #
    # Only `fetch_failed` counts towards `failed`. A parse gap is a real pass
    # with a real hole in it — `partial` — because something WAS read and stored,
    # and what an operator needs is which sport came back empty, not a red light
    # over the whole task.
    misconfigured = [u for u in sports_unasked if u["reason"] == "sport_not_found"]
    total_failures = sum(1 for f in fetch_failures if f["reason"] == "fetch_failed")
    if not sports_asked:
        terminal = "no_work"
    elif total_failures == sports_asked:
        terminal = "failed"
    elif fetch_failures or misconfigured:
        terminal = "partial"
    else:
        terminal = "complete"

    return {
        "terminal": terminal,
        # Always present; `[]` is the reading, not an absence — same rule as the
        # schedules task, and for the same reason.
        "fetch_failures": fetch_failures,
        "sports_asked": sports_asked,
        "sports_unasked": sports_unasked,
        "total_teams_updated": total_updated,
        "details": details,
    }
