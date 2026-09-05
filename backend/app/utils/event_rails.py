"""The TWO RAILS every league and team surface splits its events into.

A league page and a team page each render one pair of lists — what is on now or
still to come, and what has already happened. Both pages built that pair with
hand-written status literals and hand-written time bounds, in two files, and the
pair is only correct if the two halves are **jointly exhaustive**: every row the
surface can reach must satisfy exactly one of them.

They were not, three times:

    #1204     ``closed`` was in neither. A settled doubleheader vanished.
    live/056  ``suspended`` was in neither. A rain-delayed match vanished.
    #3211     ``scheduled`` past its own kickoff is in neither. **171 US Open
              matches** vanished — for the whole fortnight, permanently.

Each repair widened one literal in one file and left the structure that produced
it, so the next state fell through the same hole. This module is the structure:
the pair is built ONCE, both surfaces spend it, and
``tests/test_the_two_rails_are_jointly_exhaustive_3211.py`` executes both
conditions over a status × time matrix and fails if any cell lands in neither
rail or in both. A fourth state cannot fall through quietly, because the guard
is written over the vocabulary rather than over a list of remembered examples.

🔴 WHAT IS DELIBERATELY OUTSIDE THE PAIR, so the guard is not read as a claim
about them:

  * :data:`~app.utils.event_completion.RETIRED_STATUSES` — ``merged`` and
    ``voided`` mean "stop showing this row", and both rails are allowlists, so
    they are excluded BY CONSTRUCTION rather than by a rule (lane1/132).
  * anything older than the recent rail's lookback. That is a horizon, not a
    gap: it applies to a Final exactly as it applies to everything else, and it
    is the bound that keeps the recent rail from growing without limit.

Both functions take ``now`` rather than reading the clock, so the guard can
sweep a matrix and no anchor can rot (gotcha #44).
"""

from datetime import timedelta

from sqlalchemy import and_, or_

from app.models.models import Event
from app.utils.event_completion import RECENT_RAIL_STATUSES, UPCOMING_GRACE


def upcoming_rail_condition(now):
    """ "What is on now, or still to come" — the status × time half of it.

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
    hours. A suspended row rides the recent rail, so the net moving it is also
    what takes it off this one.
    """
    return or_(
        Event.status == "live",
        and_(
            Event.status == "scheduled",
            Event.commence_time >= now - UPCOMING_GRACE,
        ),
    )


def recent_rail_condition(now, *, lookback: timedelta):
    """ "What has already happened" — the status × time half of it.

    ``lookback`` is the surface's own horizon and is NOT shared: the league page
    shows 14 days and the team page 30, because a team plays less often than its
    league does. It is a parameter rather than a constant so that difference
    stays a decision each page makes, instead of becoming a number this module
    quietly imposes on both.

    The second arm is #3211's repair and it is the mirror of the first. A row
    that still says ``scheduled`` more than
    :data:`~app.utils.event_completion.UPCOMING_GRACE` past its own kickoff has
    the same standing as a ``suspended`` one — its clock ran out and nothing
    reported an ending — and it goes on the same rail for the reason
    :data:`~app.utils.event_completion.RECENT_RAIL_STATUSES` already argues at
    length: the upcoming rail's grace excludes it by construction, and this
    rail's lookback ages it off exactly where the Final it never got would have,
    rather than leaving it on an open floor forever.

    🔴 THE TWO ARMS SHARE THE ``scheduled`` WORD AND ARE STILL DISJOINT FROM THE
    UPCOMING RAIL, which is the property to check when reading this. Both rails
    now name ``scheduled``; the grace boundary is what separates them, and it is
    the SAME expression on both sides (``now - UPCOMING_GRACE``, one constant)
    so they cannot drift into overlapping or into leaving a sliver between them.
    ``test_league_rails_query_plan`` used to assert the recent rail never names
    ``'live'`` or ``'scheduled'`` as a copy-paste tripwire; it now asserts the
    disjointness directly, because the literal absence stopped being the thing
    that was true.

    The rail's TITLE still says "Recent Results" over a row that has none. That
    is answered where ``suspended`` answers it — the shared card prints
    ``No result reported`` and withholds the score block, the chips and the
    projection (``lib/eventState.ts``). A heading over a card that states its
    own state is not the lie; an absent match is.
    """
    return and_(
        Event.commence_time >= now - lookback,
        or_(
            Event.status.in_(RECENT_RAIL_STATUSES),
            and_(
                Event.status == "scheduled",
                Event.commence_time < now - UPCOMING_GRACE,
            ),
        ),
    )
