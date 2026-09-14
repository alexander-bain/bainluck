"""#1201 — MLB schedule-coverage check: the sentinel side of the schedule-diff.

Fetches the official MLB schedule for a date and reconciles it against our
events using the pure classifier in ``app/utils/schedule_diff.py``. The invariant
it asserts is **every official MLB game that day ↔ exactly one of our events**;
it also surfaces ``premature_settle`` (the #1193/#1201 rot) and ``postponed``
state divergences.

Read-only (it never mutates events — applying the transitions is a separate,
gated path). Fails soft: if statsapi is unreachable it returns ``skipped=True``,
never a false alarm. Exposed on-demand via the admin route so ops/Fable can prove
"today's slate clean" without waiting for a beat.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def run_mlb_schedule_coverage(date: Optional[str] = None) -> dict:
    """Reconcile the official MLB schedule for ``date`` (YYYY-MM-DD, default
    today UTC) against our events. Returns a verdict dict:

        {checked, passed, skipped, transitions: [...], counts: {...}, date}
    """
    from sqlalchemy import select, text  # noqa: F401

    from app.models.models import Event, Sport, Team
    from app.services.mlb_api import MLBAPIService
    from app.tasks.base import get_task_session
    from app.utils.schedule_diff import diff_schedule, normalize_official_game

    now = datetime.now(timezone.utc)
    day = date or now.strftime("%Y-%m-%d")

    service = MLBAPIService()
    try:
        raw_games = await service.get_todays_games(date=day)
    except Exception as exc:
        logger.warning("MLB schedule fetch failed for %s: %s", day, exc)
        return {"flow": "mlb_schedule_coverage", "date": day, "checked": 0,
                "passed": True, "skipped": True,
                "evidence": {"reason": f"statsapi unreachable: {str(exc)[:120]}"}}
    finally:
        await service.close()

    if not raw_games:
        # An empty official slate (off-day) is not a failure.
        return {"flow": "mlb_schedule_coverage", "date": day, "checked": 0,
                "passed": True, "skipped": True,
                "evidence": {"reason": "no official MLB games on this date"}}

    official = [normalize_official_game(g) for g in raw_games]

    # Our MLB events for the same UTC day (±18h to cover boundary crossings), the
    # same window audit_event_counts uses.
    day_noon = datetime.strptime(day, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
    our_events: list[dict] = []
    async with get_task_session() as s:
        rows = (await s.execute(
            select(Event.id, Event.status, Team.name.label("home"),
                   Sport.key.label("sport"))
            .join(Sport, Sport.id == Event.sport_id)
            .outerjoin(Team, Team.id == Event.home_team_id)
            .where(
                Sport.key.in_(["baseball_mlb", "baseball_mlb_preseason"]),
                Event.commence_time.between(day_noon - timedelta(hours=18),
                                            day_noon + timedelta(hours=18)),
            )
        )).all()
        # Second pass for away names (kept separate to avoid a double outerjoin alias).
        ev_map = {r.id: {"id": r.id, "status": r.status, "home_team": r.home or "",
                         "away_team": ""} for r in rows}
        if ev_map:
            away_rows = (await s.execute(
                select(Event.id, Team.name.label("away"))
                .outerjoin(Team, Team.id == Event.away_team_id)
                .where(Event.id.in_(list(ev_map.keys())))
            )).all()
            for ar in away_rows:
                if ar.id in ev_map:
                    ev_map[ar.id]["away_team"] = ar.away or ""
        our_events = list(ev_map.values())

    transitions = diff_schedule(official, our_events, now=now)
    counts: dict[str, int] = {}
    for t in transitions:
        counts[t.kind] = counts.get(t.kind, 0) + 1

    failures = [
        {"kind": t.kind, "detail": t.detail, "game_pk": t.game_pk,
         "event_ids": t.event_ids}
        for t in transitions
    ]
    return {
        "flow": "mlb_schedule_coverage",
        "date": day,
        "checked": len(official),
        "our_events": len(our_events),
        "passed": len(failures) == 0,
        "skipped": False,
        "counts": counts,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# #1201/#1193 self-heal — repair the standing inverted / future-settled MLB rows.
#
# The resolved_state Flow Sentinel goes RED on MLB events that are settled but
# violate ``completed_at >= commence_time`` (gotcha #32/#46): commence_time is in
# the FUTURE, or completed_at PRECEDES commence_time. These are cross-merged rows
# (an earlier game's terminal state folded onto a later sibling via a collapsed
# commence_time) or a postponed game closed by the staleness net and later
# rescheduled. The durable *prevention* already ships (the ESPN write-side fold
# guards + the un-settle-on-replay branch in ``espn_helpers.py``). This heals the
# rows corrupted BEFORE those guards existed, and — wired to the daily beat below
# — keeps healing any that slip through, using the free MLB Stats API as ground
# truth. It is the importable core; ``scripts/repair_inverted_mlb_events.py`` is a
# thin CLI over it. Bounded (MLB + invariant-violating rows only), evidence-logged
# per row, Core SQL, and never touches is_winner / calibration (gotcha #21).
# ---------------------------------------------------------------------------

# Settled MLB rows that violate the invariant: settled but commence in the future
# OR completed_at before commence_time. Pull scores + ids to classify scored-vs-
# empty and re-date via ground truth.
_INVERTED_CANDIDATE_SQL = """
    SELECT e.id, e.status, e.commence_time, e.completed_at,
           e.home_score AS hs, e.away_score AS aws,
           e.commence_time_source AS commence_source,
           ht.name AS home_team, at.name AS away_team
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    LEFT JOIN teams ht ON ht.id = e.home_team_id
    LEFT JOIN teams at ON at.id = e.away_team_id
    WHERE s.key IN ('baseball_mlb', 'baseball_mlb_preseason')
      AND e.status IN ('completed', 'closed')
      AND ({selector})
    ORDER BY e.commence_time
"""

#: The standing self-heal population: settled but commencing in the future, or
#: completed before it started (the #46 invariant violation).
_INVARIANT_ARM = """
          e.commence_time > (now() at time zone 'utc')
          OR (e.completed_at IS NOT NULL AND e.completed_at < e.commence_time)
"""

#: #2018: a row can be on the WRONG first pitch without being inverted.
#: Game 1 (`14788546`) commences 08-17 17:40Z and completed 08-18 01:37Z — a
#: perfectly ordinary ordering, so the invariant arm cannot see it, yet 17:40Z is
#: the OTHER half of a doubleheader (ESPN: `401873710` 17:40Z STL 2 @ CIN 1;
#: `401816567` 22:40Z STL 5 @ CIN 6/10). Widening the invariant arm to catch it
#: would pull in every correctly-ordered settled MLB row in the table, so the
#: reach is an explicit id list instead — a UNION with the invariant arm, never a
#: replacement of it. A rail that only does what it is told stops self-healing.
_EXPLICIT_ARM = "          e.id = ANY(:explicit_ids)"


def build_candidate_sql(explicit_ids: bool = False) -> str:
    """The candidate SQL, with the explicit-id arm unioned in on request."""
    selector = _INVARIANT_ARM
    if explicit_ids:
        selector = f"{_INVARIANT_ARM}          OR\n{_EXPLICIT_ARM}\n"
    return _INVERTED_CANDIDATE_SQL.format(selector=selector)


def authorize_redate(current_source, incoming_source) -> tuple[bool, str]:
    """May this rail move `commence_time` off `current_source`?

    Thin wrapper so the rail states its authority question in its own vocabulary
    while the RULE lives in exactly one place (`event_registry`). #2018: this
    write used to be unconditional — correct only because there was one caller.
    """
    from app.services.event_registry import commence_time_write_authorized

    return commence_time_write_authorized(current_source, incoming_source)


#: What this rail writes into `commence_time_source`, and therefore the authority
#: it claims. Named rather than inlined so the gate and the stamp cannot drift.
REPAIR_SOURCE = "mlb_schedule_repair"

#: How long after first pitch a nine-inning game is taken to have ended, when the
#: authority confirms the Final but hands us no end time (the MLB schedule never
#: carries one). Named rather than inlined because TWO rails now spend it — the
#: ``fix_end`` arm above and the frozen-settle arm below — and a completed_at that
#: two rails compute from two different literals is a row whose end time depends on
#: which pass reached it first.
MLB_NOMINAL_GAME_LENGTH = timedelta(hours=3, minutes=15)


def _repair_tokens(s) -> set:
    return set((s or "").lower().replace(".", "").split())


def _repair_teams_match(our_home, our_away, mlb_home, mlb_away) -> bool:
    """True if our (home, away) matches the MLB game in either orientation."""
    hh = bool(_repair_tokens(our_home) & _repair_tokens(mlb_home))
    aa = bool(_repair_tokens(our_away) & _repair_tokens(mlb_away))
    hswap = bool(_repair_tokens(our_home) & _repair_tokens(mlb_away))
    aswap = bool(_repair_tokens(our_away) & _repair_tokens(mlb_home))
    return (hh and aa) or (hswap and aswap)


def _repair_as_utc(dt):
    """Coerce a datetime to tz-aware UTC (naive -> assume UTC)."""
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _classify_scored_inverted(completed_at, commence_time, new_start) -> str:
    """Decide the repair action for a SCORED inverted row, given the confirmed MLB
    Final start (all args tz-aware UTC or None):

    * ``redate``  — commence was the wrong (future) field: the Final's start is
      <= completed_at, so re-dating commence to it restores the invariant.
    * ``fix_end`` — completed_at is the corrupt pre-first-pitch field: commence
      already matches the Final start (within 6h), so completed_at must move to the
      game end. The dominant standing class.
    * ``review``  — neither holds; unsafe to auto-repair.

    Pure and side-effect free so the boundary is unit-testable without a DB."""
    if completed_at is None or new_start <= completed_at:
        return "redate"
    if commence_time is not None and abs(
            (new_start - commence_time).total_seconds()) <= 6 * 3600:
        return "fix_end"
    return "review"


async def _mlb_final_for(service, home, away, hs, aws, around_date):
    """Find the real MLB game (Final) matching our teams + score within ±1 day of
    ``around_date``. Returns (game_datetime_iso, mlb_home, mlb_away) or None.

    Score match is orientation-aware: accept either {hs,aws} == {mlbHome,mlbAway}
    score set so a home/away swap in our row doesn't cause a miss."""
    want_scores = sorted([s for s in (hs, aws) if s is not None])
    for delta in (0, -1, 1):
        day = (around_date + timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            games = await service.get_todays_games(date=day)
        except Exception:
            continue
        for g in games:
            state = (g.get("status", {}) or {}).get("detailedState", "")
            if state not in ("Final", "Game Over", "Completed Early"):
                continue
            teams = g.get("teams", {}) or {}
            mh = (teams.get("home", {}) or {}).get("team", {}).get("name", "")
            ma = (teams.get("away", {}) or {}).get("team", {}).get("name", "")
            if not _repair_teams_match(home, away, mh, ma):
                continue
            mhs = (teams.get("home", {}) or {}).get("score")
            mas = (teams.get("away", {}) or {}).get("score")
            got_scores = sorted([s for s in (mhs, mas) if s is not None])
            if want_scores and got_scores and want_scores != got_scores:
                continue
            return (g.get("gameDate"), mh, ma)
    return None


async def repair_inverted_mlb_events(
    apply: bool = True,
    explicit_ids: list[int] | None = None,
) -> dict:
    """Heal (re-date / fix-completed_at / void) the standing inverted / future-
    settled MLB rows. Every write is gated on an MLB ground-truth Final matching
    the row's teams AND final score — never a blind write.

    ``explicit_ids`` (#2018) adds named rows to the candidate set that the
    invariant predicate cannot reach — a row on the WRONG first pitch is not
    necessarily an INVERTED row. **Naming a row selects it for consideration,
    never for a write:** the MLB ground-truth gate and the source-priority gate
    both still apply, unchanged, or "attended" would degrade into "typed an id".

    * SCORED, commence wrong -> re-date. completed_at + score belong to a REAL
      finished game; commence_time points at the wrong (future) sibling. The MLB
      Final's start is <= completed_at, so set commence_time to it and the invariant
      (completed_at >= commence_time) holds.
    * SCORED, completed_at wrong -> fix completed_at. commence_time + score already
      match the confirmed MLB Final (start within 6h of commence), but completed_at
      was set BEFORE first pitch (the dominant standing class — a stale/mis-merged
      terminal timestamp). Move completed_at to the game end (start + nominal 9-inning
      duration) so the invariant holds. Score / is_winner untouched (gotcha #21).
    * 0-0 / NULL-score rows -> void the settle (status->scheduled, completed_at/
      scores->NULL). The normal pipeline re-settles it once it actually plays.
    * Anything unverifiable vs MLB ground truth is LOGGED and SKIPPED.

    Returns ``{candidates, redate, fix_end, void, review, applied,
    void_refused_row_moved}``. Idempotent.

    #6056: ``void`` counts the rows DIAGNOSED as voidable;
    ``void_refused_row_moved`` counts how many of those the compare-and-write
    declined because another writer moved the row between the diagnosis and the
    write. The two are reported separately on purpose — a refusal is this rail
    working, not this rail failing, and folding it into ``void`` would make a
    correctly-declined write look like a completed one.
    """
    from sqlalchemy import text

    from app.services.mlb_api import MLBAPIService
    from app.tasks.base import get_task_session

    now = datetime.now(timezone.utc)
    service = MLBAPIService()

    redate: list = []   # (id, old_commence_iso, new_commence_iso, evidence)
    fix_end: list = []  # (id, old_completed_iso, new_completed_iso, evidence)
    void: list = []     # (id, reason, observed_status, observed_home, observed_away)
    review: list = []    # (id, reason)
    candidates = 0
    #: #6056. Always reported, never conditional — a refusal that nobody counts
    #: is indistinguishable from a pass with nothing to do, and that is how this
    #: class of defect stays invisible (gotcha #53).
    void_refused = 0

    try:
        async with get_task_session() as s:
            _ids = [int(i) for i in (explicit_ids or [])]
            rows = (await s.execute(
                text(build_candidate_sql(explicit_ids=bool(_ids))),
                {"explicit_ids": _ids} if _ids else {},
            )).all()
            candidates = len(rows)
            logger.info(
                "repair_inverted_mlb: %d resolved_state-failing MLB rows", candidates
            )

            for r in rows:
                scored = (r.hs is not None and r.aws is not None
                          and not (r.hs == 0 and r.aws == 0))
                if not scored:
                    # #6056: the void arm carries the columns its decision read,
                    # not just the id. The write below re-asserts every one of
                    # them, so they have to survive the minutes of MLB
                    # ground-truth fetching that happen in between.
                    #
                    # ALL FIVE, not the three about the score. The reason to
                    # void is two claims, not one: "settled with no real score"
                    # (`status`, `home_score`, `away_score`) AND "settled around
                    # a schedule that cannot be true" — and the second claim is
                    # `_INVARIANT_ARM`, which is written in terms of
                    # `commence_time` and `completed_at` and nothing else. A
                    # predicate over the score half alone re-asserts three of
                    # the five columns the SELECT consumed and lets the other
                    # two move underneath it.
                    #
                    # That gap is not symmetric, which is why it is worth the
                    # two extra binds: this write CLEARS `completed_at`. A
                    # column that is written but never arbitrated is the one
                    # place a compare-and-write still destroys another writer's
                    # work while reporting that it refused nothing. And the
                    # mover is real and now routine — `reconcile_anchor_schedule`
                    # and the #6073 kickoff sweep both re-date settled rows
                    # without touching status or score, so a row can stop being
                    # inverted (the whole reason it was diagnosed) in the
                    # window, and the score-only predicate would still match and
                    # still void it.
                    void.append((
                        r.id, "empty/0-0 score, settled before a real result",
                        {
                            "status": r.status,
                            "home_score": r.hs,
                            "away_score": r.aws,
                            # Coerced the way the scored branch below coerces the
                            # same two columns: identity on the tz-aware UTC that
                            # Postgres returns, so the predicate compares the row
                            # against the value the DB actually holds.
                            "commence_time": (
                                _repair_as_utc(r.commence_time)
                                if r.commence_time is not None else None
                            ),
                            "completed_at": (
                                _repair_as_utc(r.completed_at)
                                if r.completed_at is not None else None
                            ),
                        },
                    ))
                    continue

                # Find the real MLB Final for this matchup+score. Anchor on
                # completed_at first; when completed_at is the CORRUPT field the
                # Final sits at commence_time instead, so fall back to that anchor.
                res = await _mlb_final_for(
                    service, r.home_team, r.away_team, r.hs, r.aws,
                    _repair_as_utc(r.completed_at or now),
                )
                if not res and r.commence_time is not None:
                    res = await _mlb_final_for(
                        service, r.home_team, r.away_team, r.hs, r.aws,
                        _repair_as_utc(r.commence_time),
                    )
                if not res:
                    review.append((r.id, "scored but no matching MLB Final"))
                    continue
                new_start_iso, mh, ma = res
                new_start = datetime.fromisoformat(new_start_iso.replace("Z", "+00:00"))
                ev = f"MLB Final {mh} v {ma} @ {new_start_iso}"
                completed_utc = _repair_as_utc(r.completed_at) if r.completed_at else None
                commence_utc = _repair_as_utc(r.commence_time) if r.commence_time else None

                action = _classify_scored_inverted(completed_utc, commence_utc, new_start)
                if action == "redate":
                    # #2018: the SOURCE-PRIORITY gate. This write used to be
                    # unconditional, which was correct only because there was one
                    # caller — the #1980 manufacturer shape one table over.
                    _auth, _why = authorize_redate(
                        getattr(r, "commence_source", None), REPAIR_SOURCE
                    )
                    if not _auth:
                        review.append((r.id, f"redate REFUSED by source priority: {_why}"))
                        continue
                    # commence was the wrong (future) field; completed_at is a real
                    # post-game timestamp. Re-date commence to the confirmed start.
                    redate.append((r.id, r.commence_time.isoformat(), new_start_iso, ev))
                elif action == "fix_end":
                    # commence already matches the confirmed Final start — completed_at
                    # is the corrupt pre-first-pitch field. Move completed_at to the
                    # game end (start + nominal 9-inning duration). Score / is_winner
                    # untouched (gotcha #21).
                    new_end = new_start + MLB_NOMINAL_GAME_LENGTH
                    fix_end.append((r.id, r.completed_at.isoformat(), new_end.isoformat(),
                                    f"{ev}; commence correct, completed_at was pre-start"))
                else:
                    review.append((r.id, f"ambiguous: Final start {new_start_iso} "
                                          "neither after commence nor at commence"))

            ledger = {
                "candidates": candidates,
                "redate": len(redate),
                "fix_end": len(fix_end),
                "void": len(void),
                "review": len(review),
                "applied": False,
                # #6056. Present on every return, including the dry-run and the
                # nothing-to-do pass, so a reader can tell "no void lost a race"
                # from "this build does not count them".
                "void_refused_row_moved": 0,
            }

            if apply and (redate or fix_end or void):
                for eid, _old, new_iso, _ev in redate:
                    await s.execute(
                        text("UPDATE events SET commence_time = :c, "
                             "commence_time_source = :src WHERE id = :id"),
                        {"c": datetime.fromisoformat(new_iso.replace("Z", "+00:00")),
                         "id": eid, "src": REPAIR_SOURCE},
                    )
                for eid, _old, new_iso, _ev in fix_end:
                    await s.execute(
                        text("UPDATE events SET completed_at = :c WHERE id = :id"),
                        {"c": datetime.fromisoformat(new_iso.replace("Z", "+00:00")), "id": eid},
                    )
                # #6056: THE ONE WRITE ON THIS RAIL THAT CAN LAND ON A LIVE GAME.
                #
                # The other two arms move `commence_time`/`completed_at` — a
                # schedule correction, and nothing on a realtime queue competes
                # for those. This arm clears the SCORE and knocks `status` back
                # to `scheduled`, and it selects on `status IN ('completed',
                # 'closed')` — which is character-for-character the population
                # `espn_replay_unsettles` fires on (ESPN reports "in" on a row we
                # hold settled → un-settle to live and write the real score).
                # Two rails, two queues, one set of rows, by design.
                #
                # The gap is not incidental either: this loop makes an MLB
                # ground-truth HTTP call per SCORED row before it reaches here
                # (soft_time_limit 240s), so the distance between "I read 0-0 and
                # completed" and "I write NULL and scheduled" is minutes, and the
                # realtime ESPN pass runs every 60 seconds inside it. Losing that
                # race erases a real score off a game that is actually being
                # played and drops it off every live surface — #6056's symptom,
                # produced by a repair that was right when it looked.
                #
                # So the decision is re-asserted at write time on all five
                # columns it consumed. A row that moved is left alone: it is no
                # longer the row this repair diagnosed, and the next daily pass
                # re-diagnoses it from scratch.
                from types import SimpleNamespace

                from app.utils.live_state_write import write_row_if_unmoved

                for eid, _reason, _observed in void:
                    landed = await write_row_if_unmoved(
                        s,
                        SimpleNamespace(id=eid),
                        {
                            "status": "scheduled",
                            "completed_at": None,
                            "home_score": None,
                            "away_score": None,
                        },
                        # Built at diagnosis time, above — passed through rather
                        # than re-derived here, so this statement cannot read a
                        # column fresher than the decision it is re-asserting.
                        observed=_observed,
                        what="repair_inverted_mlb void",
                    )
                    if not landed:
                        void_refused += 1
                await s.commit()
                ledger["applied"] = True
                ledger["void_refused_row_moved"] = void_refused
                logger.info(
                    "repair_inverted_mlb: APPLIED re-date %d, fix-completed_at %d, void %d "
                    "(%d refused as moved, %d review, is_winner untouched)",
                    len(redate), len(fix_end), len(void) - void_refused,
                    void_refused, len(review))
            return ledger
    finally:
        await service.close()


# ---------------------------------------------------------------------------
# #5881 — THE SETTLED EDGE FOR AN MLB ROW FROZEN AT `suspended`.
#
# 59 finished MLB games print "No result reported" over a COMPLETE win-probability
# curve, a score-differential chart and a run-margin map that all know the game is
# over. `/events/15298127` (Red Sox @ Orioles, Sep 6) is the filed specimen.
#
# The cause is dated and is not a matching symptom. `odds_polling`'s wall-clock
# staleness arm used to write `closed`; `0ee26b711` (Sep 2, CERT-752) correctly
# changed it to `suspended` — *a quiet book is not a finished game* — and left no
# replacement writer for the settled edge on a row with no `espn_id`. Every other
# door is shut on this population, which #5881 measured door by door:
#
#   * `odds_polling`'s own `closed` arm needs `get_statpal_end_time()`, which
#     StatPal supplied for 0 of 116 finished events — widening its status filter
#     is INERT, and #5881 says so explicitly so nobody builds it;
#   * `statpal_sync`'s terminal arm needs that same end time AND `status='live'`;
#   * `espn_sync._settle_authority_stragglers` needs an `espn_id` (0 of 59 carry
#     one) and is bounded by `AUTHORITY_STRAGGLER_LOOKBACK`;
#   * the `suspended → live` resume arm is bounded by the same 48h;
#   * #5532's retirement door refuses them twice over — it requires every provider
#     id to be absent (all 59 carry a `statpal_fixture_id`) and no score (49 hold
#     one). That refusal is CORRECT: a row with a result is a row something
#     reached, and retiring it would hide a game we can still tell the truth about.
#
# So this arm supplies the missing edge from the one authority that is free, has no
# quota and IS the truth for this sport: the MLB Stats API, already the ground truth
# the inverted-row repair above runs on.
#
# 🔴 MEASURED ON THE REAL 59 BEFORE IT WAS WRITTEN (production ids, 2026-09-14
# 14:5xZ, statsapi.mlb.com read directly): **58 of 59 confirm a unique Final** —
# 48 where our score already equals MLB's final and 10 where we hold no score at
# all — and every one matched at the SAME MINUTE as our own kickoff (d=0m). Zero
# rows disagree with the authority's score; zero are side-swapped. The 59th is a
# doubleheader (`15294597`, Tigers @ Guardians, two Finals 305 minutes apart) and
# is refused as ambiguous, which is the behaviour this arm wants on that shape.
# ---------------------------------------------------------------------------

#: How close an MLB Final's first pitch must sit to our own kickoff before it can
#: be this row's game. The discriminator that matters: a ±1-day team match alone
#: cannot separate the games of a SERIES (the same two clubs play three days
#: running, all Final, all matching), which is why the first cut of this arm read
#: 57 of 59 as ambiguous. Anchored on the clock instead, 58 of 59 resolve to one
#: game. Sized off `_classify_scored_inverted`'s own 6h tolerance so this file
#: holds one notion of "the same game's start", not two.
FROZEN_FINAL_MATCH_WINDOW = timedelta(hours=6)

#: How far back the arm reaches. Bounds the work, not the truth: a row older than
#: this is not settled by any pass and stays exactly as it is.
FROZEN_SETTLE_HORIZON = timedelta(days=30)

#: Rows per pass. The population is a standing backlog that drains once and then
#: arrives at ~2/day, so the cap exists to bound a single beat (one MLB schedule
#: fetch per distinct game DATE, cached within the pass — 59 rows over 8 dates
#: cost 10 fetches, not 177), never to ration the repair.
FROZEN_SETTLE_CAP = 150

#: What the frozen-settle arm selects. `status = 'suspended'` and MLB only; the
#: floor and horizon arrive as bind parameters so the rail computes its own clock
#: in Python (and so a test can drive it without a Postgres `now()`).
#:
#: NO `espn_id IS NULL` PREDICATE, DELIBERATELY, even though 0 of the measured 59
#: carry one. Past the floor below, the ESPN door cannot select the row either —
#: so keying on the column that names that door would make the arm's reach depend
#: on a value that can be BACKFILLED LATER, and a row that acquired an `espn_id`
#: on Tuesday would silently leave this arm on Tuesday and re-strand itself.
_FROZEN_SUSPENDED_SQL = """
    SELECT e.id, e.status, e.commence_time, e.completed_at,
           e.home_score AS hs, e.away_score AS aws,
           e.home_team_name AS home_team, e.away_team_name AS away_team
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE s.key IN ('baseball_mlb', 'baseball_mlb_preseason')
      AND e.status = 'suspended'
      AND e.commence_time < :floor_ts
      AND e.commence_time > :horizon_ts
    ORDER BY e.commence_time DESC
    LIMIT :cap
"""


def frozen_settle_floor() -> timedelta:
    """How old a `suspended` MLB row must be before this arm may end it.

    DERIVED FROM THE TWO DOORS, NEVER RESTATED. Both ways out of `suspended` are
    bounded by the same 48h — `_settle_authority_stragglers`
    (`AUTHORITY_STRAGGLER_LOOKBACK`) and the `suspended → live` resume window — and
    `event_completion` already owns the day of slack on top of them
    (`UNREACHABLE_SUSPENDED_MARGIN`: a stalled beat, a long release, a queue
    backlog can all still land a late pass inside it). Spending those two names
    instead of writing `timedelta(hours=72)` is what stops this arm racing a door
    that is still open if either number ever moves.
    """
    from app.tasks.espn_sync import AUTHORITY_STRAGGLER_LOOKBACK
    from app.utils.event_completion import UNREACHABLE_SUSPENDED_MARGIN

    return AUTHORITY_STRAGGLER_LOOKBACK + UNREACHABLE_SUSPENDED_MARGIN


def frozen_club(name) -> Optional[str]:
    """The MLB franchise ``name`` names, or ``None`` when it cannot be pinned.

    THE ROSTER IS NOT WRITTEN HERE. `statpal_league_rosters.MLB_TEAM_NAMES` is the
    30 franchises as measured across BOTH vocabularies — ours and a provider's —
    and `normalize_team` is the fold that was measured with it: it is why
    `St.Louis Cardinals` and `St. Louis Cardinals` are one club rather than two,
    which is a split this arm's own population carries (#2867 / D50). A second
    table here would be the bug, not the fix.

    The prefix arm exists for one measured production shape: our rows carry the
    truncated `San Francisco Giant`, which is nobody's exact name. It resolves
    only when the prefix is UNIQUE across the 30, so `Chicago`, `New York` and
    `Los Angeles` — the names that would re-open the whole city-token hole —
    resolve to nothing and refuse. An unknown string (`Sacramento Athletics`)
    refuses too. Fail-closed is the only safe direction for a rail that writes a
    score onto a side.
    """
    from app.utils.nfl_team_matching import normalize_team
    from app.utils.statpal_league_rosters import MLB_TEAM_NAMES

    folded = normalize_team(name)
    if not folded:
        return None
    if folded in MLB_TEAM_NAMES:
        return folded
    hits = [c for c in MLB_TEAM_NAMES if c.startswith(folded) or folded.startswith(c)]
    return hits[0] if len(hits) == 1 else None


def frozen_final_orientation(our_home, our_away, mlb_home, mlb_away) -> str:
    """``"aligned"`` | ``"swapped"`` | ``"ambiguous"`` | ``"different_clubs"`` |
    ``"none"`` for one candidate Final.

    This arm WRITES A SCORE and therefore has to know which side is which — a
    matcher that answers "yes, in some orientation" is the right answer to the
    inverted-row repair's question and the wrong one to this rail's.

    ── WHY A TOKEN INTERSECTION CANNOT ANSWER THIS (CERT-2864, CERT-2867) ───────
    Two cuts of this function tried to decide club identity lexically and both
    were wrong in the same direction — they said YES to a game that was not ours.

    1. Asking the two raw intersections IN ORDER preferred `aligned` whenever both
       fitted, and for a same-city game both ALWAYS fit: Mets @ Yankees intersects
       Yankees @ Mets on ``{new, york}``. A genuinely SWAPPED row read `aligned`,
       and the real task then wrote `New York Mets 7 - New York Yankees 2` for a
       game the Yankees won 7-2.
    2. Breaking that tie on the tokens the two names do NOT share fixed the swap
       and left the wider hole open, because it only ran when both orientations
       fitted. **Mets @ Cubs against a same-hour Yankees @ White Sox fits exactly
       ONE way** — ``{new, york}`` on the home side, ``{chicago}`` on the away
       side — so it never reached the tie-break and settled one game with the
       other's score.

    The second case is not a harder version of the first; it is the proof that no
    local rule over these four strings can do it. Nothing in the letters of
    "New York Mets" and "New York Yankees" says they are different clubs. Only a
    ROSTER says that. So club identity is now REQUIRED — resolved through
    :func:`frozen_club` — and the token pair is kept for one job only: deciding
    whether this Final is even a candidate worth asking about.

    `different_clubs` is deliberately distinct from `none`. `none` means the
    authority's Final is some other game entirely and is dropped; `different_clubs`
    means it LOOKED like ours on names and the roster refutes it, which is a fact
    worth a counter (gotcha #53) rather than a silent skip that would be reported
    as "the authority reports no finished game here".
    """
    raw_aligned = bool(_repair_tokens(our_home) & _repair_tokens(mlb_home)) and bool(
        _repair_tokens(our_away) & _repair_tokens(mlb_away)
    )
    raw_swapped = bool(_repair_tokens(our_home) & _repair_tokens(mlb_away)) and bool(
        _repair_tokens(our_away) & _repair_tokens(mlb_home)
    )
    if not raw_aligned and not raw_swapped:
        return "none"

    our_h, our_a = frozen_club(our_home), frozen_club(our_away)
    mlb_h, mlb_a = frozen_club(mlb_home), frozen_club(mlb_away)
    if None in (our_h, our_a, mlb_h, mlb_a):
        return "different_clubs"
    club_aligned = our_h == mlb_h and our_a == mlb_a
    club_swapped = our_h == mlb_a and our_a == mlb_h
    if club_aligned and club_swapped:
        # All four names are one club, so there is no side to choose. Refused
        # under its own name rather than guessed at.
        return "ambiguous"
    if club_aligned:
        return "aligned"
    if club_swapped:
        return "swapped"
    return "different_clubs"


def choose_frozen_final(hs, aws, candidates) -> tuple:
    """Decide this row's fate from the Finals the authority offers. Pure.

    Returns ``(verdict, candidate_or_None)``:

    * ``settle``         — exactly one Final, our orientation, and the score
      either agrees with the authority or is absent on our side;
    * ``ambiguous``      — more than one Final survives (a doubleheader);
    * ``no_final``       — the authority reports no finished game here;
    * ``orientation``    — the one Final is side-swapped against our row. Refused
      rather than written through: a swapped row is a side-mapping defect and
      writing a score into it would bake the swap in as a result;
    * ``orientation_ambiguous`` — the one Final fits our row in BOTH directions
      and the club names cannot break the tie (CERT-2864). Kept apart from
      ``orientation`` because they are different facts: that one knows the row is
      swapped, this one knows only that it cannot tell — and a rail that writes a
      score must never spend a coin-flip. See `frozen_final_orientation`;
    * ``different_clubs`` — every Final the authority offers looked like our game
      on team-name tokens and the ROSTER refutes it (CERT-2867): Mets @ Cubs
      against a same-hour Yankees @ White Sox shares a city on each side and is
      not the same game. Counted rather than reported as ``no_final``, which
      would have said "the authority reports no finished game here" about a date
      on which it reported one;
    * ``score_conflict`` — we hold a score and the authority's differs. REFUSED
      and counted, not overwritten: this arm's warrant is "say the result we can
      confirm", and a row whose score contradicts the confirmed Final has not been
      confirmed — it may be a different game or a mid-game capture, and #6056 is
      the whole argument against writing a score you cannot justify. Measured 0 of
      59 today; the counter is what makes the class visible if that ever changes.
      Asked PER COMPONENT (CERT-2864's follow-up): a row holding one score and not
      the other used to skip this test entirely, because `ours_scored` demanded
      both — so the half we DID hold was never checked against the authority and
      was then overwritten by the write below. 0 of the 59 are partial today, which
      is exactly why the shape has to be right before one arrives;
    * ``no_authority_score`` — a Final with no score attached, so there is nothing
      to report.

    The score tie-break runs BEFORE the uniqueness test, not after: on the one
    doubleheader in the measured population both games match the teams and only
    the score separates them, and a row that holds no score cannot be separated at
    all — which is exactly when refusing is right.
    """
    if not candidates:
        return ("no_final", None)
    # CERT-2867. Asked FIRST and over the whole offer, so a date carrying several
    # city-lookalike Finals is one honest refusal rather than an `ambiguous` that
    # blames a doubleheader for a roster mismatch.
    cands = [c for c in candidates if c["orientation"] != "different_clubs"]
    if not cands:
        return ("different_clubs", None)
    ours_fully_scored = hs is not None and aws is not None
    if len(cands) > 1 and ours_fully_scored:
        narrowed = [
            c for c in cands
            if c["orientation"] == "aligned"
            and c["home_score"] == hs and c["away_score"] == aws
        ]
        if len(narrowed) == 1:
            cands = narrowed
    if len(cands) > 1:
        return ("ambiguous", None)
    cand = cands[0]
    if cand["orientation"] == "ambiguous":
        return ("orientation_ambiguous", cand)
    if cand["orientation"] != "aligned":
        return ("orientation", cand)
    if cand["home_score"] is None or cand["away_score"] is None:
        return ("no_authority_score", cand)
    if (hs is not None and cand["home_score"] != hs) or (
        aws is not None and cand["away_score"] != aws
    ):
        return ("score_conflict", cand)
    return ("settle", cand)


def frozen_completed_at(final_start, commence_time):
    """The end time to stamp on a row the authority confirms is over.

    ``max(...)`` of the two starts rather than the authority's alone, because
    `completed_at >= commence_time` is an INVARIANT (gotcha #46) and the two
    starts are only guaranteed to sit inside `FROZEN_FINAL_MATCH_WINDOW` of each
    other — a row whose own kickoff is the later of the two would otherwise be
    stamped as finishing before it started, which is the very rot the repair arm
    above exists to heal.
    """
    anchor = final_start
    if commence_time is not None and commence_time > anchor:
        anchor = commence_time
    return anchor + MLB_NOMINAL_GAME_LENGTH


async def _frozen_final_candidates(service, row, schedule_cache) -> list:
    """Every MLB Final that could be this row's game, deduped by ``gamePk``.

    ``schedule_cache`` is per-PASS, not per-row: a slate's worth of frozen rows
    share one game date, so the cache turns "one fetch per row per delta" into one
    fetch per distinct date. A date that fails to fetch is cached as empty for the
    pass — the row then reads `no_final` and is left exactly as it was, which is
    the same outcome as the arm never running.
    """
    commence = _repair_as_utc(row.commence_time)
    out: dict = {}
    for delta in (0, -1, 1):
        day = (commence + timedelta(days=delta)).strftime("%Y-%m-%d")
        if day not in schedule_cache:
            try:
                schedule_cache[day] = await service.get_todays_games(date=day)
            except Exception:
                schedule_cache[day] = []
        for game in schedule_cache[day] or []:
            state = (game.get("status", {}) or {}).get("detailedState", "")
            if state not in ("Final", "Game Over", "Completed Early"):
                continue
            raw_start = game.get("gameDate")
            if not raw_start:
                continue
            try:
                start = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
            except ValueError:
                continue
            if abs(start - commence) > FROZEN_FINAL_MATCH_WINDOW:
                continue
            teams = game.get("teams", {}) or {}
            home = (teams.get("home", {}) or {}).get("team", {}).get("name", "")
            away = (teams.get("away", {}) or {}).get("team", {}).get("name", "")
            orientation = frozen_final_orientation(
                row.home_team, row.away_team, home, away
            )
            if orientation == "none":
                continue
            pk = game.get("gamePk")
            out[pk if pk is not None else f"{day}:{raw_start}:{home}"] = {
                "start": start,
                "home": home,
                "away": away,
                "home_score": (teams.get("home", {}) or {}).get("score"),
                "away_score": (teams.get("away", {}) or {}).get("score"),
                "orientation": orientation,
            }
    return list(out.values())


async def settle_frozen_mlb_suspended(apply: bool = True) -> dict:
    """End an MLB game the authority finished and no writer of ours can reach (#5881).

    Writes, per confirmed row: ``status='completed'``, ``completed_at``, and — only
    where we hold no score at all — the authority's score. Never `is_winner`
    (gotcha #21), never `commence_time`, never a score over a different one.

    Compare-and-write on all five columns the decision consumed (#6056): this pass
    makes an HTTP call per distinct game date between reading a row and writing it,
    and a row that moved in that window is no longer the row that was diagnosed.
    A refusal is counted under its own name so a quiet pass and a lost race can
    never read the same (gotcha #53).

    Returns ``{candidates, settled, ambiguous, no_final, orientation,
    orientation_ambiguous, different_clubs, score_conflict, no_authority_score,
    refused_row_moved, applied}`` — every key present on every return, including the dry run and the
    nothing-to-do pass.
    """
    from types import SimpleNamespace

    from sqlalchemy import text

    from app.services.mlb_api import MLBAPIService
    from app.tasks.base import get_task_session
    from app.utils.live_state_write import write_row_if_unmoved

    now = datetime.now(timezone.utc)
    ledger = {
        "candidates": 0,
        "settled": 0,
        "ambiguous": 0,
        "no_final": 0,
        "orientation": 0,
        "orientation_ambiguous": 0,
        "different_clubs": 0,
        "score_conflict": 0,
        "no_authority_score": 0,
        "refused_row_moved": 0,
        "applied": False,
    }
    service = MLBAPIService()
    try:
        async with get_task_session() as session:
            rows = (await session.execute(
                text(_FROZEN_SUSPENDED_SQL),
                {
                    "floor_ts": now - frozen_settle_floor(),
                    "horizon_ts": now - FROZEN_SETTLE_HORIZON,
                    "cap": FROZEN_SETTLE_CAP,
                },
            )).all()
            ledger["candidates"] = len(rows)
            logger.info(
                "settle_frozen_mlb: %d suspended MLB rows past the floor", len(rows)
            )

            schedule_cache: dict = {}
            writes: list = []
            for row in rows:
                cands = await _frozen_final_candidates(service, row, schedule_cache)
                verdict, cand = choose_frozen_final(row.hs, row.aws, cands)
                if verdict != "settle":
                    ledger[verdict] += 1
                    continue
                values = {
                    "status": "completed",
                    "completed_at": frozen_completed_at(
                        cand["start"], _repair_as_utc(row.commence_time)
                    ),
                }
                # CERT-2864's follow-up is fixed in `choose_frozen_final`, NOT
                # here. Writing only the missing component reads like the obvious
                # second half of that repair, and it was written and then deleted:
                # mutation proved it an equivalence mutant. Anything reaching this
                # line has already agreed with the authority on every component we
                # hold — a disagreement is `score_conflict` and never arrives — so
                # "write both" and "write the gap" put the identical value in the
                # identical column. Unkillable code that looks like a guard is
                # worse than no code: the next reader would trust it to be the
                # protection, and the protection is the verdict above.
                if row.hs is None or row.aws is None:
                    values["home_score"] = cand["home_score"]
                    values["away_score"] = cand["away_score"]
                # EVERY COLUMN THE DECISION CONSUMED, built here at diagnosis
                # time — the lesson the void arm above learned the hard way
                # (`312737099`). The score half is not the whole decision:
                # `commence_time` is what chose this Final out of a series AND
                # what computes the `completed_at` being written, and
                # `completed_at` is a column this write SETS, so a row someone
                # else settled in the window would have their end time
                # overwritten by a pass that reported refusing nothing.
                # `reconcile_anchor_schedule` and the #6073 kickoff sweep both
                # re-date settled rows without touching status or score, so the
                # mover is routine.
                observed = {
                    "status": row.status,
                    "home_score": row.hs,
                    "away_score": row.aws,
                    "commence_time": (
                        _repair_as_utc(row.commence_time)
                        if row.commence_time is not None else None
                    ),
                    "completed_at": (
                        _repair_as_utc(row.completed_at)
                        if row.completed_at is not None else None
                    ),
                }
                writes.append((row, values, observed, cand))

            if apply and writes:
                for row, values, observed, cand in writes:
                    landed = await write_row_if_unmoved(
                        session,
                        SimpleNamespace(id=row.id),
                        values,
                        observed=observed,
                        what="settle_frozen_mlb",
                    )
                    if landed:
                        ledger["settled"] += 1
                        logger.info(
                            "settle_frozen_mlb: %s -> completed on MLB Final "
                            "%s %s @ %s %s (%s)",
                            row.id, cand["away"], cand["away_score"],
                            cand["home"], cand["home_score"],
                            cand["start"].isoformat(),
                        )
                    else:
                        ledger["refused_row_moved"] += 1
                await session.commit()
                ledger["applied"] = True
            else:
                # A dry run reports what it WOULD end, under the same name the
                # applied pass uses — a plan whose count lives under a different
                # key is a plan nobody can compare to the run.
                ledger["settled"] = len(writes)
            logger.info("settle_frozen_mlb: %s", ledger)
            return ledger
    finally:
        await service.close()


async def run_mlb_schedule_coverage_and_repair() -> dict:
    """Daily beat entry point (#1201/#1193/#1202/#5881): self-heal the standing
    inverted MLB rows, end the games frozen at `suspended` that no other writer can
    reach, then run the read-only coverage check so the 07:10 Flow Sentinel and the
    cockpit read a clean, freshly-reconciled slate. All three halves are
    best-effort and independent; a failure in one never suppresses the others."""
    result: dict = {}
    try:
        result["repair"] = await repair_inverted_mlb_events(apply=True)
    except Exception as exc:  # heal is best-effort; still run detection
        logger.warning("repair_inverted_mlb_events failed: %s", exc)
        result["repair"] = {"error": str(exc)[:200]}
    try:
        result["frozen_settle"] = await settle_frozen_mlb_suspended(apply=True)
    except Exception as exc:  # #5881: best-effort, like its two siblings
        logger.warning("settle_frozen_mlb_suspended failed: %s", exc)
        result["frozen_settle"] = {"error": str(exc)[:200]}
    try:
        result["coverage"] = await run_mlb_schedule_coverage()
    except Exception as exc:
        logger.warning("run_mlb_schedule_coverage failed: %s", exc)
        result["coverage"] = {"error": str(exc)[:200]}
    return result
