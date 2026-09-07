"""The RAILS every league and team surface splits its events into.

A league page and a team page each split their events into rails — what is on
now or still to come, and what has already happened. Both pages built that split
with hand-written status literals and hand-written time bounds, in two files,
and the split is only correct if it is **jointly exhaustive**: every row the
surface can reach lands on exactly one rail.

It was not, three times:

    #1204     ``closed`` was on no rail. A settled doubleheader vanished.
    live/056  ``suspended`` was on no rail. A rain-delayed match vanished.
    #3211     ``scheduled`` past its own kickoff was on no rail. **171 US Open
              matches** vanished — for the whole fortnight, permanently.

Each repair widened one literal in one file and left the structure that produced
it, so the next state fell through the same hole. This module is the structure:
the rails are built ONCE, both surfaces spend them, and
``tests/test_the_two_rails_are_jointly_exhaustive_3211.py`` executes the real
conditions over a status × time matrix and fails if any cell lands on no rail or
on two. A fourth state cannot fall through quietly, because the guard is written
over the vocabulary rather than over a list of remembered examples.

🔴 THERE ARE THREE CONDITIONS AND A LEAGUE PAGE RENDERS THREE RAILS. #3211's rows
could not simply join the settled rail: they outnumber it and sort above it, so
one shared cap starved the Finals out of existence. The measurement, and why the
TEAM page still renders two, is on :func:`unreported_rail_condition`.

🔴 WHAT IS DELIBERATELY OUTSIDE THE SPLIT, so the guard is not read as a claim
about it:

  * :data:`~app.utils.event_completion.RETIRED_STATUSES` — ``merged`` and
    ``voided`` mean "stop showing this row", and every rail is an allowlist, so
    they are excluded BY CONSTRUCTION rather than by a rule (lane1/132).
  * anything older than the lookback. That is a horizon, not a gap: it applies
    to a Final exactly as it applies to everything else, and it is the bound
    that keeps the past rails from growing without limit.

Every function takes ``now`` rather than reading the clock, so the guard can
sweep a matrix and no anchor can rot (gotcha #44).
"""

from datetime import timedelta

from sqlalchemy import and_, case, or_

from app.models.models import Event
from app.utils.event_completion import (
    EVENT_SUSPENDED,
    RECENT_RAIL_STATUSES,
    UPCOMING_GRACE,
)

#: The statuses that mean "this happened and we know how it went" — the settled
#: rail's whole vocabulary after #3748.
#:
#: DERIVED from :data:`~app.utils.event_completion.RECENT_RAIL_STATUSES` by
#: removing the one word that moved, rather than re-listed, so a fourth settled
#: word added to the vocabulary reaches this rail without anybody remembering
#: this line. Re-listing it is the exact failure mode this module's header is
#: about. ``RECENT_RAIL_STATUSES`` itself is unchanged and still names every
#: status that rides a PAST rail — which of the two past rails is what #3748
#: moved, and the guard sweep derives its status axis from that constant, so
#: narrowing it there would make the sweep blind to ``suspended`` entirely.
_SETTLED_ONLY_STATUSES = [s for s in RECENT_RAIL_STATUSES if s != EVENT_SUSPENDED]


def suspended_rows():
    """Every ``suspended`` row — they all ride the unreported rail. #3748.

    🔴 IT IS THE #3211 STARVATION AGAIN, POINTED AT THE THIRD STATUS.
    :func:`unreported_rail_condition` already says in as many words that a
    result-less ``scheduled`` row "has the same standing as a ``suspended``
    one — its clock ran out and nothing reported an ending". #3211 acted on
    that for ``scheduled`` and gave it a rail of its own. ``suspended`` was
    left on the settled rail, where it has the same midnight-UTC stamp
    (gotcha #14) and therefore the same behaviour under
    ``ORDER BY commence_time DESC LIMIT 8``: it sorts above every real Final.

    MEASURED on production 2026-09-06, simulating the real rail (duplicate-tag
    filter included) over all 29 leagues: **28 leagues** had at least one such
    row inside their eight visible Recent Results slots, and **thirteen of them
    had all eight** — KBO, NPB, MiLB, AFLW, boxing, MMA, Liiga and six more
    showed a "Recent Results" section containing not one result. Confirmed
    against the serving endpoint, not just the query: ``/api/leagues/baseball_kbo``
    and ``/api/leagues/baseball_npb`` each returned 8/8 scoreless ``suspended``
    rows **while their own unreported rail was EMPTY**. In the window there
    were 1,618 scoreless suspended rows against 54 with a score.

    🔴 THE FIX IS NOT A REORDER AND NOT A BIGGER CAP, for the reason
    :func:`unreported_rail_condition` already argues at length: one cap over two
    populations of very different size starves the smaller one whichever way it
    is sorted. Ordering settled-first would hide all 1,618 behind eight slots of
    Finals, which is #3211 inverted. Split the bound.

    🔴 EVERY SUSPENDED ROW, NOT ONLY THE SCORELESS ONES, and that is CERT-2167's
    correction to this lane's first attempt. The first version split ``suspended``
    on whether a scoreline existed and left the 54 scored rows on the settled
    rail, reasoning that they had something to show. **The rail a row sits on has
    to agree with the words its own card prints**, and the card is not ours to
    reinterpret here: ``eventState.hasNoReportedResult`` is true for EVERY
    suspended row, so all 54 rendered "No result reported · last score 1-2"
    under a heading that says "Recent Results". That is the same contradiction
    the issue was filed about, at 54 rows instead of 1,618 — a present defect,
    not a hypothetical, and those rows can still consume capped result slots.

    Nothing is lost by moving them: both rails render the same shared card
    through ``LeagueGameRail``, so a scored suspended row keeps its
    ``· last score 1-2`` label verbatim — it simply now sits under a heading
    that is true of it.

    Nor does this undo live/056, whose ship was that a suspended match is
    reachable AT ALL (it was on no rail and vanished; the unreported rail did
    not yet exist). It is still on its league page, once.
    """
    return Event.status == EVENT_SUSPENDED


def upcoming_rail_condition(now):
    """What is on now, or still to come — the status × time half of it.

    The caller adds its own scope (a league key, a team's four id/name columns)
    and its own ordering; this is only the part both callers had written twice.

    🔴 ``live`` LOSES THE ``now - 2h`` FLOOR, and that is a fix rather than a
    loosening. The floor was one expression over two populations — the mistake
    memory calls *one variable, two rates* — and it means something true of
    ``scheduled`` (a fixture two hours past its start time is not "upcoming"
    any more) and something false of ``live`` (a match is being played for
    exactly as long as it is being played). Measured on production 2026-09-05:
    fourteen rows were live and more than two hours past their commence — four
    NPB games, four fights on a UFC card, five soccer matches and a tennis
    match, none older than 5.6 hours — and every one of them was on its league
    page NOWHERE while it was happening.

    ``GET /api/events`` already gives ``live`` an open floor for this reason and
    says so in :func:`~app.routes.events.event_list_window_condition` — "live —
    regardless of when it started". Matching it is the point: two surfaces
    disagreeing about what ``live`` means is how a reader finds a match on the
    Sports feed and not on its own league page.

    The exposure that floor was accidentally covering is a row STUCK in
    ``live``, which would then sit at the top of this rail (the ORDER BY leads
    with ``live``) indefinitely. It is covered on purpose by the two staleness
    nets, which write :data:`~app.utils.event_completion.EVENT_SUSPENDED` once a
    row passes its sport's own maximum duration with no evidence it is still
    running — and the population says they work: across the WHOLE events table
    on 2026-09-05 there were 41 ``live`` rows and **not one** was older than 12
    hours. A suspended row rides a past rail, so the net moving it is also what
    takes it off this one.
    """
    return or_(
        Event.status == "live",
        and_(
            Event.status == "scheduled",
            Event.commence_time >= now - UPCOMING_GRACE,
        ),
    )


def started_live(now):
    """``live`` AND its own start time has passed — the SQL half of
    :func:`app.utils.lifecycle.served_event_status`.

    One definition, because the two ordering clauses below differ only in what
    they do with everything else. Two copies of this and a surface can sort on
    one reading while printing the other, which is the whole defect.
    """
    return and_(Event.status == "live", Event.commence_time <= now)


def live_first_order(now):
    """Put what is ACTUALLY being played at the top. The ORDER BY twin of
    :func:`upcoming_rail_condition`, and deliberately its neighbour.

    Every caller of that condition wrote ``case((Event.status == "live", 0),
    else_=1)`` underneath it — the raw column, with no time half. That is the
    same sentence :func:`app.utils.lifecycle.served_event_status` refuses on the
    display side, so a row could be relabelled ``scheduled`` for the reader and
    still be sorted as though it were live. The label and the position have to
    answer to one predicate or the page argues with itself.

    🔴 MEASURED on production 2026-09-05 (Q438 / #1207), and it is what the
    condition above says is covered when it is not. That docstring accepts one
    exposure — "a row STUCK in ``live`` … would then sit at the top of this rail
    indefinitely" — and banks on the staleness nets, which write
    ``EVENT_SUSPENDED`` once a row passes its sport's maximum duration. Those
    nets are ONE-SIDED: they measure age past commence, so they catch a row that
    is live too LONG and can never catch one that is live too EARLY.

    Event 14969919 (Chicago Fire vs Vancouver Whitecaps) is the specimen — DB
    ``live`` since 2026-06-30, kickoff 2026-10-06. It is not stale and never
    will be, so no net moves it, and on 09-05 it held the FIRST slot of
    ``/sport/soccer/mls`` above eight matches kicking off that evening, under a
    heading reading "LIVE & UPCOMING" for a league with nothing live in it.

    A genuinely live game is unaffected: it satisfies both halves and still
    leads the rail. A premature-live row simply takes its place in date order,
    which is where a fixture a month out belongs.
    """
    return case((started_live(now), 0), else_=1)


def live_scheduled_settled_order(now):
    """Live, then upcoming, then finished — the THREE-way twin of
    :func:`live_first_order`, for surfaces that also sort completed rows last.

    Same first branch, same predicate, one definition (:func:`started_live`).
    The second branch is what makes a premature-live row land where its own
    label puts it: it is served as ``scheduled``, so it sorts with the scheduled
    games rather than ahead of them. A row only reaches the ``live`` arm of
    branch two by having failed branch one, which is exactly the premature case.

    Found by CERT-1924 on the two-way clause's own presentation: the public
    futures "Games This Week" list (``get_related_events``) spelled this out as
    a MULTILINE ``case(...)`` on the raw column, so it survived both the repair
    and the source guard written to catch it — a future raw-live row was
    promoted ahead of nearer scheduled games and then serialized as
    ``scheduled``. The guard is now an AST scan for that reason.
    """
    return case(
        (started_live(now), 0),
        (Event.status.in_(("live", "scheduled")), 1),
        else_=2,
    )


def settled_rail_condition(now, *, lookback: timedelta):
    """What has already happened AND we know how it went.

    ``lookback`` is the surface's own horizon and is NOT shared: the league page
    shows 14 days and the team page 30, because a team plays less often than its
    league does. It is a parameter rather than a constant so that difference
    stays a decision each page makes, instead of becoming a number this module
    quietly imposes on both.

    Unchanged in meaning by #3211 — this is the rail that was always here, and
    keeping it exactly as narrow as it was is the point of
    :func:`unreported_rail_condition` existing beside it rather than inside it.

    NARROWED by #3748: ``suspended`` is no longer admitted at all. Every
    suspended row moved to the rail whose heading matches the words its own card
    prints — :func:`suspended_rows` carries the measurement and the argument.
    What is left here is exactly "we know how it went", which is what the
    docstring above always claimed and now is.
    """
    return and_(
        Event.commence_time >= now - lookback,
        Event.status.in_(_SETTLED_ONLY_STATUSES),
    )


def unreported_rail_condition(now, *, lookback: timedelta):
    """What should have happened, and nobody told us how it went.

    Two populations, and #3748 is the day the second one arrived:

      * a row that still says ``scheduled`` more than
        :data:`~app.utils.event_completion.UPCOMING_GRACE` past its own kickoff
        (#3211), and
      * every ``suspended`` row (:func:`suspended_rows`).

    They are one rail because they are one state. This docstring said so before
    either of them was on it — a result-less ``scheduled`` row "has the same
    standing as a ``suspended`` one — its clock ran out and nothing reported an
    ending" — and #3748 is simply that sentence finally applied to the status it
    names. The frontend has always agreed: ``eventState.hasNoReportedResult`` is
    one predicate over both.

    Both age off on the same lookback for the reason
    :data:`~app.utils.event_completion.RECENT_RAIL_STATUSES` argues at length:
    the upcoming rail's grace excludes them by construction, and a lookback ages
    them off exactly where the Final they never got would have, rather than
    leaving them on an open floor forever.

    🔴 WHY IT IS ITS OWN CONDITION AND ITS OWN RAIL, WHICH IS THE HALF WORTH
    ARGUING. The obvious repair is to widen the settled rail by one arm, and
    that is what this function first was. It is wrong, and measurably:

    ``/api/leagues/tennis_wta``'s results rail is ``ORDER BY commence_time DESC
    LIMIT 8``. The result-less rows are stamped midnight UTC of the CURRENT day
    (gotcha #14), so they sort ABOVE every real Final. Simulated against
    production on 2026-09-05, all eight visible slots went to result-less rows
    and every actual result — Sabalenka's included — was pushed off the page.
    That is not a repair; it is the same disappearance, pointed at the other
    population.

    It is the shared-cap-over-unequal-populations trap
    (memory: ``r_shared_cap_over_unequal_populations``), and its lesson is
    explicit: **raising or reordering the cap does not fix it — split the
    bound.** Ordering settled-first would have hidden all 19 result-less WTA
    rows behind 8 slots of Finals, which is #3211 again. Two rails, two caps,
    each declared.

    ⚠️ THE TEAM PAGE DELIBERATELY DOES NOT SPLIT, and that is not an oversight.
    The trap needs two populations of very different SIZE competing for one cap.
    A league page's cap spans every concurrent match in the league — hundreds,
    during a Grand Slam. A team page's spans one team's own schedule, where a
    result-less game is one fixture among the same handful of fixtures the rail
    was sized for. Comparable populations, no starvation; so ``teams`` spends
    :func:`recent_or_unreported_condition` and keeps one list.
    """
    return and_(
        Event.commence_time >= now - lookback,
        or_(
            and_(
                Event.status == "scheduled",
                Event.commence_time < now - UPCOMING_GRACE,
            ),
            # #3748. NO grace bound on this arm, and that asymmetry is the
            # point rather than an omission: the grace exists to let a
            # `scheduled` row that has not quite kicked off stay on the
            # upcoming rail, and a `suspended` row was never on the upcoming
            # rail to be held back from. Adding the bound here would put a
            # freshly-suspended row on NO rail for two hours, which is the
            # hole this whole module exists to close.
            suspended_rows(),
        ),
    )


def recent_or_unreported_condition(now, *, lookback: timedelta):
    """Both of the above, for a surface whose cap does not starve either.

    The team page. See the warning on :func:`unreported_rail_condition` for why
    one list is right there and wrong on a league page — and note that this is
    the ONLY way the two are combined, so "does this surface split?" is a
    question with one answer per call site rather than a flag.
    """
    return or_(
        settled_rail_condition(now, lookback=lookback),
        unreported_rail_condition(now, lookback=lookback),
    )
