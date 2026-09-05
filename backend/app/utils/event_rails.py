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
from app.utils.event_completion import RECENT_RAIL_STATUSES, UPCOMING_GRACE


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
    return case(
        (and_(Event.status == "live", Event.commence_time <= now), 0),
        else_=1,
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
    """
    return and_(
        Event.commence_time >= now - lookback,
        Event.status.in_(RECENT_RAIL_STATUSES),
    )


def unreported_rail_condition(now, *, lookback: timedelta):
    """What should have happened, and nobody told us how it went.

    A row that still says ``scheduled`` more than
    :data:`~app.utils.event_completion.UPCOMING_GRACE` past its own kickoff. It
    has the same standing as a ``suspended`` one — its clock ran out and nothing
    reported an ending — and it ages off on the same lookback for the reason
    :data:`~app.utils.event_completion.RECENT_RAIL_STATUSES` argues at length:
    the upcoming rail's grace excludes it by construction, and a lookback ages
    it off exactly where the Final it never got would have, rather than leaving
    it on an open floor forever.

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
        Event.status == "scheduled",
        Event.commence_time < now - UPCOMING_GRACE,
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
