"""Link each new StatPal tennis fixture to our row, as StatPal publishes it. #2867.

**SHIP: a live tennis card can show the real score line — sets, games, points,
who is serving — because the match on screen is now joined to the StatPal match
that carries them.** (Pillar: TRUTH.)

D59 (Alex, 2026-09-03): a live tennis card's whole score line comes from StatPal
when the match is LINKED, and from ESPN when it is not, never mixed. The live
lane can only build that branch if "linked" has a representation. Measured on
production the same day: **0 of 30,115 tennis rows carried a StatPal id** and no
tennis anchor existed, so the branch had one arm.

`scripts/link_tennis_statpal_anchors_2867.py` writes the link for the matches the
measurement bus already swept (the past, 204 rows, once). **This is the forward
half**: the recurring task that links each fixture as StatPal publishes it, so
the coverage the sweep bought does not decay to zero over the next tournament.

WHAT IT READS, AND WHY ALL THREE
════════════════════════════════
`daily/d1`, `daily/d2` and `livescores`, through the authority door
(`get_schedule_fixtures` / `get_live_fixtures`) so a failed read raises instead
of arriving as an empty slate.

**There is no `daily/d0`** — it answers HTTP 500, not 404 and not an empty
envelope (ARTIFACT-AUTHORITY-20260903-TENNIS §1a). Today's order of play is
unobtainable from `daily`, and today is exactly when a live card needs its link.
`livescores` is the only endpoint that knows a match on the day it is played, so
it is not an optimisation here; it is the arm that covers the day the ship is
about.

`d1`/`d2` are the forward reach and it is genuinely shallow — 70 fixtures on d1,
1 on d2, 0 beyond, because the draw past the next round does not exist yet. A
linker that only looked forward would link tomorrow and never today.

HOW A LINK IS DECIDED
═════════════════════
Normalized player pair (`app/utils/tennis_name_matching`) plus a date window.
Nothing else, and specifically **not** the tournament: our own `sports.key` is
not reliable enough to filter on — a live US Open singles match was sitting under
`tennis_other` on the day this was written — so the tournament is recorded in the
receipt and never used to exclude a candidate.

**±36 hours, and the width is forced.** StatPal stamps `15:00` UTC as a session
placeholder for tennis and backfills the true minute only after the match is
played; we carry our own midnight-UTC placeholder on unlinked rows. Two
placeholders that do not coincide are not a disagreement about when the match is,
and a tight window would read them as one. Measured over 75 real StatPal singles
against 1,026 of our tennis rows on 2026-09-03: 74 matched 1:1, 1 ambiguous, 0
unmatched.

**Exactly one candidate, or nothing is written.** Two candidates is not a tie to
break — it is two of our rows for one match, which is a duplicate, and picking
one hides the finding while stamping half of it. It is reported and left alone
(D35: matching symptoms are filed until lane1/#2693 lands; this task is not
allowed to fix them).

**Doubles are refused before the question is asked.** StatPal writes a pair as
`"Galloway/ Goransson"`; the sweep's token fallback caught 30+ false
doubles-to-singles hits before doubles were excluded. All 32 doubles fixtures on
the measurement day matched nothing.

WHAT IT WRITES
══════════════
Per link, both shapes, for the reason
`scripts/link_tennis_statpal_anchors_2867.py` documents at length: an anchor over
a NULL `events.statpal_fixture_id` is refused as STALE by
`anchor_channel.anchor_is_current` on every read, so writing only the anchor
stamps nothing.

    events.statpal_fixture_id = '2631673'
    event_provider_anchors      ('statpal', 'tennis:2631673', 'game')

The qualifier is `tennis:`, not our `sports.key` — `provider_anchor_keys.
statpal_id_space` carries the argument. Writes go through
`anchor_channel.record_anchor`, so a fixture already claimed by a DIFFERENT event
comes back as `COLLISION` and is reported rather than overwritten.

It never re-links a row that already holds a StatPal id, and it never touches a
row outside tennis.

**A link is both shapes or neither.** Only `WROTE` and `CONFIRMED` mean the anchor
names this event; every other anchor outcome rolls the column write back and is
receipted. Committing on "not a COLLISION" was a whitelist written as a
blacklist, and it let `STALE_INCUMBENT` and `NO_KEY` leave a row whose column
says linked while the anchor table says nothing — a disagreement no reader can
see and the D51 restore does not know about (CERT-871 FOLLOW-UP
`AUTHORITY-006-LINK-WRITE-OUTCOMES`).

**"Already linked" is not "unmatched".** A fixture linked on an earlier pass has
no candidate by construction, so it has to be recognised rather than receipted as
a miss; otherwise a task running every 10 minutes buries the handful of real
misses under its own successes (CERT-871 FOLLOW-UP
`AUTHORITY-006-ALREADY-LINKED-RECEIPTS`).

**And "already linked" is not "we hold the integer" either.** That recognition
originally asked one question — *does any row carry this scalar?* — which is the
same evidence the paragraph above refuses to WRITE a link on. Reading a link out
of it while refusing to write one into it is the same file disagreeing with
itself, and the disagreement always resolves the flattering way: a half-written
row and a cross-sport collision both report as successes. So the lookup checks
BOTH shapes, and a scalar without its `tennis:<id>` anchor lands in `unpaired`
with the reason named — `UNANCHORED`, `FOREIGN_SPORT` or `MULTIPLE_HOLDERS`
(CERT-883 FOLLOW-UP `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED`). Measured on
production 2026-09-04 the day this shipped: 213 tennis scalars, 213 anchors, so
the new bucket is empty and no count moves — it is the NEXT half-link it exists
to catch, and 10,941 non-tennis rows already carry a StatPal scalar for the
cross-sport arm to eventually collide with.

**And the question is asked FIRST, not on the miss path** (CERT-895). Putting it
inside the unmatched arm looked safe — a fixture we hold cannot be its own
candidate, because `CANDIDATES` filters `statpal_fixture_id IS NULL`. That is
true of the HOLDER and silent about every other row: a second row matching the
same two players IS a candidate, so the loop would stamp the scalar onto it and
manufacture the two-rows-for-one-id duplicate this task exists to report. If we
hold the id in any form, this pass writes nothing for that fixture. For the same
reason a LOST race re-reads the pair instead of assuming the winner finished:
losing the `IS NULL` guard proves somebody claimed the column, not that anybody
anchored it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.services.anchor_channel import (
    COLLISION,
    CONFIRMED,
    WROTE,
    record_anchor,
)
from app.services.authority_ledger import record_agreement_day
from app.services.statpal_api import StatPalFixture, get_statpal_service
from app.utils.authority_agreement import Side
from app.utils.authority_tennis_agreement import (
    build_tennis_agreements,
    tennis_measurement_bounds,
)
from app.utils.provider_anchor_keys import (
    STATPAL_ID_SPACE_TENNIS,
    statpal_anchor_key,
    statpal_id_space,
)
from app.utils.tennis_name_matching import DOUBLES_MARKER, pair_matches

logger = logging.getLogger(__name__)

#: The three reads. `d0` is absent because StatPal has no `d0` — see the module
#: docstring. Forward reach beyond `d2` is empty upstream (measured), so asking
#: for it spends a call to learn nothing.
SCHEDULE_DAY_OFFSETS: tuple[int, ...] = (1, 2)


def statpal_read_span(now: datetime) -> tuple[datetime, datetime]:
    """The UTC span StatPal's tennis side was actually REQUESTED over (#3644).

    Not the dates the returned fixtures carry — the dates some call we make is
    *scoped to*. Those were the same thing for the team sports, whose StatPal
    side is one `season-schedule` call, and they were never the same thing here.

    THE DEFECT THIS EXISTS TO KILL. `livescores` is a state query, not a day's
    schedule, and it keeps returning matches for several days after they finish.
    Measured 2026-09-06: it dragged the published span's start back to
    `2026-09-04T11:10Z`, two days whose schedule `SCHEDULE_DAY_OFFSETS` never
    asks for. Every row of ours in that stretch was then counted as a miss
    *inside StatPal's span* — a disagreement with a list nobody requested — and
    `tennis_singles.identity.ours_covered_in_span_pct` published 13.91% as
    though it were a coverage verdict.

    THE LINE, stated so the next reader can disagree with it deliberately: a day
    is READ when a request we make is scoped to it. `livescores` is scoped to
    now, so today counts. `daily/dN` is scoped to `now + N`. Days before today
    are scoped to by NOTHING — they appear only as `livescores` residue, and
    residue is not a read.

    KNOWN AND NARROWER, on purpose: today is covered by `livescores` (plus `d1`,
    which spills — measured, 1 of its 22 fixtures was dated today), and
    `livescores` favours live and recently-finished matches. A match early today
    that finished before this pass could still be absent, and would land
    `inside` this span. That is a real residual and it is roughly two orders of
    magnitude smaller than the two whole unrequested days this removes; the
    alternative — dropping today from the span — throws away the one day that
    carries the live matches, and it is a bigger lie than the one it fixes.

    Derived FROM `SCHEDULE_DAY_OFFSETS` rather than written out, so a change to
    what we ask for cannot leave the span claiming what we used to ask for.
    `test_the_read_span_tracks_the_offsets_it_is_derived_from` holds that.
    """
    day = now.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # `0` for `livescores`. Not in `SCHEDULE_DAY_OFFSETS` because StatPal has no
    # `d0` token to request (see that constant) — but the day IS read, by a
    # different call, and the span is about days read rather than tokens sent.
    offsets = (0,) + tuple(SCHEDULE_DAY_OFFSETS)
    first = day + timedelta(days=min(offsets))
    # End-INCLUSIVE, to the last instant of the last day read. `+ N days` alone
    # would end at that day's midnight and exclude all but the first instant of
    # it, quietly shrinking the span by a whole day at the far end — where the
    # unplayed fixtures `d2` exists to serve actually sit.
    last = day + timedelta(days=max(offsets) + 1) - timedelta(microseconds=1)
    return first, last

#: How far apart a StatPal start time and ours may be and still be one match.
#:
#: Wide on purpose and NOT a threshold to tune. Both sides carry placeholder
#: start times — StatPal's `15:00` session stamp, our midnight-UTC row — so the
#: honest reading of a gap inside this window is "neither side has committed to a
#: minute yet". Narrowing it would not buy precision; it would silently drop the
#: unplayed fixtures, which are most of what `d1` serves. Precision comes from
#: the name pair and from refusing every ambiguity, not from the clock.
MATCH_WINDOW = timedelta(hours=36)

#: Every tennis row in the window that has no StatPal id yet, with its sport key.
#:
#: `statpal_fixture_id IS NULL` is the whole of the re-link guard: a row that
#: already carries an id is not revisited, so a task that runs every 10 minutes
#: does not re-derive 30,000 rows' worth of decisions to write nothing. The cost
#: of that guard is `SCALAR_HOLDERS` below — an already-linked fixture finds
#: no candidate here and has to be told apart from a genuine miss somewhere else.
CANDIDATES = """
SELECT e.id, s.key, e.home_team_name, e.away_team_name, e.commence_time,
       e.sport_id
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key LIKE 'tennis%'
   AND e.statpal_fixture_id IS NULL
   AND e.commence_time >= :window_start
   AND e.commence_time <= :window_end
"""

#: Every tennis row in the MEASUREMENT span, linked or not, with what its column
#: holds.
#:
#: A different question from `CANDIDATES` and therefore a different statement.
#: That one asks "what may this pass write to?" and so excludes rows that already
#: carry an id — correctly. This one asks "of the matches we list, does StatPal
#: have them?", and a row we linked last week is squarely part of that
#: population. Reusing the write pool would give a denominator that shrinks every
#: time the linker succeeds, and a seven-day count is a comparison between days.
#:
#: `statpal_fixture_id` comes back so the row can report the id join
#: (`anchors`), which is the number that says the join is usable and is never the
#: agreement number.
MEASUREMENT_ROWS = """
SELECT e.id, s.key, e.home_team_name, e.away_team_name, e.commence_time,
       e.statpal_fixture_id, e.status
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key LIKE 'tennis%'
   AND e.commence_time >= :window_start
   AND e.commence_time <= :window_end
"""

SET_FIXTURE_ID = """
UPDATE events
   SET statpal_fixture_id = :fixture_id
 WHERE id = :event_id
   AND statpal_fixture_id IS NULL
"""

#: Which of this pass's fixture ids are ALREADY on one of our rows, and whether
#: the row that holds one holds the ANCHOR too.
#:
#: CERT-871 FOLLOW-UP `AUTHORITY-006-ALREADY-LINKED-RECEIPTS`. The candidate
#: query deliberately excludes rows that already carry a StatPal id, so a fixture
#: linked on an earlier pass finds no candidate and used to be reported as
#: UNMATCHED — i.e. as *"StatPal has this match and we do not"*, which is the
#: opposite of what happened. On a task that runs every 10 minutes that is not a
#: cosmetic mislabel: within a day the unmatched receipts are almost entirely
#: successes, and the genuine misses — the ones worth a person's attention — are
#: buried in them.
#:
#: CERT-883 FOLLOW-UP `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED` adds the LEFT
#: JOIN. The scalar ALONE was the whole answer, and the scalar alone is the one
#: piece of evidence this task has already decided is not enough to call a link:
#: `COMMITTABLE_OUTCOMES` refuses to WRITE a scalar without its anchor, and then
#: this lookup turned around and READ one as a finished link. The two halves of
#: the same file disagreed about what "linked" means.
#:
#: What the join buys, in the two shapes the disagreement takes:
#:
#:   * **A half-link.** A tennis row whose scalar was written before CERT-883
#:     closed the whitelist — column set, anchor absent. It reports as a quiet
#:     success forever, which is the one report under which nobody repairs it.
#:   * **A cross-sport scalar.** `statpal_fixture_id` is not sport-scoped and
#:     10,941 non-tennis rows carry one (measured 2026-09-04). The ranges do not
#:     overlap TODAY — non-tennis 7-digit ids run 1003106-1033541, tennis
#:     2629657-2631979 — but nothing keeps them apart, and on the day they touch,
#:     a real tennis miss reports as `already_linked` because an NFL row happens
#:     to hold the integer.
#:
#: The anchor rows are LEFT JOINed unfiltered by key and the key is rebuilt in
#: Python from `statpal_anchor_key`, deliberately: composing `'tennis:' || id` in
#: SQL would be a second implementation of D55's key rule, free to drift from the
#: one in `provider_anchor_keys`. The server finds the anchors; the helper that
#: writes keys is the only thing that says what a key looks like.
#:
#: One statement for the whole batch rather than a lookup per miss: ~70 ids, one
#: indexed `= ANY`, asked once. Fan-out is one row per statpal `game` anchor on
#: each holder, which is 0 or 1 in every measured case.
SCALAR_HOLDERS = """
SELECT e.statpal_fixture_id, e.id, s.key, a.source_id
  FROM events e
  JOIN sports s ON s.id = e.sport_id
  LEFT JOIN event_provider_anchors a
         ON a.event_id = e.id
        AND a.source = 'statpal'
        AND a.id_kind = 'game'
 WHERE e.statpal_fixture_id = ANY(:fixture_ids)
"""


@dataclass
class LinkRun:
    """What one pass did, in terms a receipt can be written from.

    Every fixture the task looked at lands in exactly one bucket. A run that
    reports only its successes cannot tell "StatPal published nothing" from "we
    matched nothing", and those need different fixes.
    """

    fixtures_read: int = 0
    doubles_skipped: int = 0
    already_linked: int = 0
    linked: int = 0
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    unmatched: list[dict[str, Any]] = field(default_factory=list)
    collisions: list[dict[str, Any]] = field(default_factory=list)
    #: Fixtures whose candidate was found and whose column write went through,
    #: but whose ANCHOR write refused. Rolled back, never committed. CERT-871
    #: FOLLOW-UP `AUTHORITY-006-LINK-WRITE-OUTCOMES`.
    write_refusals: list[dict[str, Any]] = field(default_factory=list)
    #: Fixtures whose id one of our rows ALREADY holds as a bare scalar, with no
    #: matching anchor — a half-link, a cross-sport collision, or two holders.
    #: Not a link and not a miss: we hold the id and cannot prove it names the
    #: match. CERT-883 FOLLOW-UP `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED`.
    unpaired: list[dict[str, Any]] = field(default_factory=list)
    sources_read: list[str] = field(default_factory=list)
    read_failures: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "fixtures_read": self.fixtures_read,
            "doubles_skipped": self.doubles_skipped,
            "already_linked": self.already_linked,
            "linked": self.linked,
            "ambiguous": len(self.ambiguous),
            "unmatched": len(self.unmatched),
            "collisions": len(self.collisions),
            "write_refusals": len(self.write_refusals),
            "unpaired": len(self.unpaired),
            "sources_read": self.sources_read,
            "read_failures": self.read_failures,
        }


def _is_doubles(fixture: StatPalFixture) -> bool:
    return DOUBLES_MARKER in (fixture.home_team or "") or DOUBLES_MARKER in (
        fixture.away_team or ""
    )


#: `_link_one`'s own outcome for "the column was already claimed between the
#: candidate query and the write". Not an anchor outcome — `anchor_channel` never
#: returns it — so it is named here rather than borrowed from there.
LOST_RACE = "LOST_RACE"

#: The ONLY two anchor outcomes that mean the anchor names this event, so the
#: only two under which the column write may be committed. A whitelist, not a
#: blacklist: a new outcome added to `anchor_channel` must be considered here
#: explicitly, and until it is, it refuses and is receipted (CERT-871
#: FOLLOW-UP `AUTHORITY-006-LINK-WRITE-OUTCOMES`).
COMMITTABLE_OUTCOMES = frozenset({WROTE, CONFIRMED})

#: What a fixture id ALREADY sitting on one of our rows turned out to be.
#:
#: CERT-883 FOLLOW-UP `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED`. Only the first
#: of these is a link. The other three are the shapes a scalar-without-a-pair
#: takes, and they are named apart rather than lumped because they need three
#: different repairs — and because a count called `already_linked` that includes
#: them is a success number with failures inside it.
PRIOR_PAIRED = "PAIRED"
#: A tennis row holds the scalar but carries no `tennis:<id>` anchor. The exact
#: half-written state CERT-883 stopped this task from CREATING; a row already in
#: it (written by an older pass, or by any other writer) must still be found.
PRIOR_UNANCHORED = "UNANCHORED"
#: A row OUTSIDE tennis holds this tennis fixture's integer. Not our link, and
#: not evidence that the fixture is linked — the fixture is still missing.
PRIOR_FOREIGN_SPORT = "FOREIGN_SPORT"
#: Two or more of our rows hold the same scalar. `events.statpal_fixture_id` has
#: a plain index, not a unique one, so nothing at the schema level forbids it.
PRIOR_MULTIPLE_HOLDERS = "MULTIPLE_HOLDERS"
#: We LOST the column race and then nobody held the id at all (CERT-895 repair).
#: Produced by the post-rollback re-read, never by `classify_prior` — it is not a
#: property of a holder, it is the absence of one where a holder just was. The
#: honest reading is "the winner wrote the scalar and then rolled back", i.e. its
#: anchor was refused. Not a link, and not a miss we can fix on this pass.
PRIOR_VANISHED = "VANISHED"

#: The one prior state that means the fixture is genuinely linked and this pass
#: has nothing to do. A whitelist for the same reason `COMMITTABLE_OUTCOMES` is
#: one: a fourth prior state added above must be classified here on purpose.
PRIOR_STATES_THAT_ARE_A_LINK = frozenset({PRIOR_PAIRED})

#: The four things one fixture can be. A verdict, not a score.
VERDICT_DOUBLES = "DOUBLES"
VERDICT_LINK = "LINK"
VERDICT_AMBIGUOUS = "AMBIGUOUS"
VERDICT_UNMATCHED = "UNMATCHED"


def classify_fixture(
    fixture: StatPalFixture, pool: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """Which of our rows, if any, is this StatPal fixture?

    Pure: no session, no clock, no network. This is the whole decision the task
    makes, hoisted so it can be driven by real StatPal payloads and real event
    rows rather than by a mock that agrees with whatever it is told.

    Returns the verdict and the candidates it was reached on — `AMBIGUOUS`
    carries all of them, because "two rows matched" without saying which two is
    a count, and the receipt has to be actionable.
    """
    if _is_doubles(fixture):
        return VERDICT_DOUBLES, []

    if fixture.start_time is None:
        # No start time is not a wide window, it is no window. Matching on names
        # alone across a whole tournament would pair a first-round match with the
        # same two players' meeting a year later.
        return VERDICT_UNMATCHED, []

    matches = [
        c
        for c in pool
        if c.get("commence_time") is not None
        and abs(c["commence_time"] - fixture.start_time) <= MATCH_WINDOW
        and pair_matches(
            (fixture.home_team, fixture.away_team), (c["home"], c["away"])
        )
    ]
    if not matches:
        return VERDICT_UNMATCHED, []
    if len(matches) > 1:
        return VERDICT_AMBIGUOUS, matches
    return VERDICT_LINK, matches


def _receipt(fixture: StatPalFixture, **extra: Any) -> dict[str, Any]:
    """One unmatched or ambiguous fixture, with enough to act on it.

    The directive asks for receipts for every unmatched row, and a receipt that
    says "2631673 did not match" is not one. The two names and the start time are
    what a person needs to decide whether the miss is our gap or StatPal's.
    """
    return {
        "statpal_id": fixture.fixture_id,
        "players": [fixture.home_team, fixture.away_team],
        "start_time": fixture.start_time.isoformat() if fixture.start_time else None,
        "tournament": fixture.league,
        "status": fixture.status,
        **extra,
    }


async def _read_fixtures(service, run: LinkRun) -> list[StatPalFixture]:
    """Every tennis fixture StatPal will tell us about right now, deduped by id.

    Each source is read in its own try/except so one endpoint failing does not
    cost the others (gotcha #42) — but the failure is RECORDED, not swallowed. A
    run that read one of three endpoints and linked what it could is a different
    fact from a run that read all three, and only the receipt can say which one
    happened.
    """
    from app.services.statpal_api import StatPalUpstreamError

    seen: set[str] = set()
    fixtures: list[StatPalFixture] = []

    async def _collect(label: str, coro) -> None:
        try:
            batch = await coro
        except StatPalUpstreamError as e:
            run.read_failures.append(f"{label}: {e}")
            logger.warning("StatPal tennis %s unreadable: %s", label, e)
            return
        run.sources_read.append(label)
        for f in batch:
            if not f.fixture_id or f.fixture_id in seen:
                continue
            seen.add(f.fixture_id)
            fixtures.append(f)

    await _collect("livescores", service.get_live_fixtures("tennis"))
    for offset in SCHEDULE_DAY_OFFSETS:
        await _collect(
            f"daily/d{offset}", service.get_schedule_fixtures("tennis", offset)
        )

    run.fixtures_read = len(fixtures)
    return fixtures


def fixture_side(fixture: StatPalFixture) -> Side:
    """A StatPal tennis fixture in the shared comparison shape."""
    return Side(
        ref=str(fixture.fixture_id),
        home=fixture.home_team,
        away=fixture.away_team,
        start=fixture.start_time,
        label=fixture.league,
    )


async def _measurement_rows(session, now: datetime) -> list[Side]:
    """Our tennis inventory over the measurement span, as comparison sides.

    The span is `tennis_measurement_bounds`', not the linker's ±36h write window:
    a row of ours past the edge of what StatPal serves has to be INSIDE the
    population to be reported as `beyond_statpal_last`, and read out of it by SQL
    it would simply never be counted at all (CERT-962).
    """
    start, end = tennis_measurement_bounds((now, now), now=now)
    rows = (
        await session.execute(
            text(MEASUREMENT_ROWS), {"window_start": start, "window_end": end}
        )
    ).fetchall()
    return [
        Side(
            ref=str(r[0]),
            home=r[2],
            away=r[3],
            start=r[4],
            # Tennis's `label` is the SPORT KEY, never a status — which is
            # precisely why #3226's exclusion reads `event_status` and not
            # `label`. Added to `MEASUREMENT_ROWS` for this; nothing else uses
            # it, and without it every retired tennis row would stay counted.
            label=r[1],
            held_id=r[5],
            event_status=r[6],
        )
        for r in rows
    ]


async def _candidates(session, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(CANDIDATES), {"window_start": start, "window_end": end}
        )
    ).fetchall()
    return [
        {
            "id": r[0],
            "sport_key": r[1],
            "home": r[2],
            "away": r[3],
            "commence_time": r[4],
            "sport_id": r[5],
        }
        for r in rows
    ]


def classify_prior(fixture_id: str, holders: list[dict[str, Any]]) -> dict[str, Any]:
    """What a fixture id already sitting on our rows actually IS.

    CERT-883 FOLLOW-UP `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED`. Pure on
    purpose — the server's job is to find the holders, and the decision about
    what a holder means is the part worth testing without one.

    `holders` is one entry per row carrying the scalar:
    `{"event_id": int, "sport_key": str, "anchors": set[str]}`, where `anchors`
    holds the `source_id` of every StatPal `game` anchor on that row.
    """
    if len(holders) > 1:
        return {
            "state": PRIOR_MULTIPLE_HOLDERS,
            "event_ids": sorted(h["event_id"] for h in holders),
        }

    holder = holders[0]
    space = statpal_id_space(holder["sport_key"])
    detail = {
        "event_id": holder["event_id"],
        "sport_key": holder["sport_key"],
    }

    if space != STATPAL_ID_SPACE_TENNIS:
        # Includes `space is None`, an unknown sport key. Both mean the same
        # thing here: whatever holds this integer, it is not this task's link.
        return {**detail, "state": PRIOR_FOREIGN_SPORT, "id_space": space}

    # Rebuilt through the writer's own helper rather than composed here, so the
    # read and the write cannot disagree about what a key looks like (D55).
    expected = statpal_anchor_key(fixture_id, space)
    if expected is not None and expected.source_id in holder["anchors"]:
        return {**detail, "state": PRIOR_PAIRED}
    return {
        **detail,
        "state": PRIOR_UNANCHORED,
        "expected_anchor": expected.source_id if expected else None,
    }


def _record_prior(run: LinkRun, fixture: StatPalFixture, prior: dict[str, Any]) -> None:
    """Count a fixture we ALREADY hold the id for, in the bucket it belongs to.

    CERT-895 repair. Shared by the two places that reach this conclusion — the
    top of the loop, and the re-read after a lost race — so the two cannot drift
    into disagreeing about which prior states are a link.
    """
    if prior["state"] in PRIOR_STATES_THAT_ARE_A_LINK:
        run.already_linked += 1
    else:
        run.unpaired.append(_receipt(fixture, **prior))


async def _already_linked(
    session, fixtures: list[StatPalFixture]
) -> dict[str, dict[str, Any]]:
    """`{fixture_id: prior}` for the fixtures one of our rows already holds.

    CERT-871 FOLLOW-UP `AUTHORITY-006-ALREADY-LINKED-RECEIPTS`. Asked once per
    pass, over the ids this pass actually read.

    CERT-883 FOLLOW-UP `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED`: each answer
    now carries a `state` from `classify_prior`, and only `PAIRED` means linked.
    The caller must branch on it — a truthy prior is no longer a success.
    """
    ids = [f.fixture_id for f in fixtures if f.fixture_id]
    if not ids:
        return {}
    rows = (
        await session.execute(text(SCALAR_HOLDERS), {"fixture_ids": ids})
    ).fetchall()

    # One entry per (fixture id, holding row); the anchor LEFT JOIN fans a
    # holder out over its anchors, so they are folded back together first.
    holders: dict[str, dict[int, dict[str, Any]]] = {}
    for fixture_id, event_id, sport_key, anchor_source_id in rows:
        by_event = holders.setdefault(str(fixture_id), {})
        holder = by_event.setdefault(
            event_id,
            {"event_id": event_id, "sport_key": sport_key, "anchors": set()},
        )
        if anchor_source_id is not None:
            holder["anchors"].add(anchor_source_id)

    return {
        fixture_id: classify_prior(fixture_id, list(by_event.values()))
        for fixture_id, by_event in holders.items()
    }


async def _link_one(session, fixture: StatPalFixture, candidate: dict) -> str:
    """Write both shapes for one match. Returns the anchor outcome.

    The column is written FIRST and guarded by `statpal_fixture_id IS NULL`, so
    two concurrent passes cannot both claim it: the loser's UPDATE touches no row
    and it stops before writing an anchor for a link it did not make.
    """
    result = await session.execute(
        text(SET_FIXTURE_ID),
        {"event_id": candidate["id"], "fixture_id": fixture.fixture_id},
    )
    if not (result.rowcount or 0):
        return LOST_RACE

    key = statpal_anchor_key(
        fixture.fixture_id, statpal_id_space(candidate["sport_key"])
    )
    written = await record_anchor(
        session,
        event_id=candidate["id"],
        key=key,
        claim_context={
            "written_by": "link_tennis_statpal_fixtures",
            "tournament": fixture.league,
            "statpal_start_time": (
                fixture.start_time.isoformat() if fixture.start_time else None
            ),
        },
    )
    return written.outcome


async def _run_link_tennis_statpal_fixtures(
    *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    """One pass. `apply=False` plans and writes nothing — the dark-run arm."""
    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)
    run = LinkRun()

    service = get_statpal_service()
    try:
        fixtures = await _read_fixtures(service, run)
    finally:
        await service.close()

    if not fixtures:
        # Loud, not silent. Zero fixtures with no read failure means StatPal has
        # no tennis at all — a real off-season answer. Zero WITH failures means
        # we could not ask, and reporting those identically is gotcha #53.
        logger.warning(
            "StatPal tennis linker read 0 fixtures (sources=%s, failures=%s)",
            run.sources_read,
            run.read_failures,
        )
        # A zero yield is a ROW, not a skip (spec rule 6). Zero fixtures with no
        # read failure is a real answer — a Monday between tournaments. Zero WITH
        # failures means we could not ask. Both carry the streak unchanged and
        # they are different facts, and returning early without banking either
        # would leave the ledger unable to tell them apart (gotcha #53).
        #
        # OUR side is still measured on a successful empty read, and that is the
        # CERT-1904 repair. Banking `rows=[]` published denominator 0 — "nobody
        # lists anything" — on a day when our own tennis inventory was nonempty
        # and StatPal's was not. That is the strongest `statpal_only` finding the
        # row can make, and the first version erased it into a zero that looks
        # like a quiet day. A READ FAILURE is different and skips the query: the
        # row is READ-FAILED and carries no counts whatever we measure, so asking
        # would spend a query to publish nothing.
        measured_rows: list[Side] = []
        if not run.read_failures:
            async with get_task_session() as session:
                measured_rows = await _measurement_rows(session, now)

        empty = build_tennis_agreements(
            fixtures=[],
            rows=measured_rows,
            read_failures=run.read_failures,
            sources_read=run.sources_read,
            measurement_window=(
                None if run.read_failures else tennis_measurement_bounds((now, now), now=now)
            ),
            # Stated on the no-fixtures path too. The span is what we ASKED
            # over, so it is known even when the answer was empty — and this is
            # the path where a reader most needs to see it, because "no
            # fixtures" and "no fixtures on the days we asked about" are the
            # two readings a bare zero cannot separate (gotcha #53).
            statpal_read_span=(
                None if run.read_failures else statpal_read_span(now)
            ),
        )
        for row in empty.values():
            await record_agreement_day(row, at=now, apply=apply)
        return {
            **run.summary(),
            "rows_measured": len(measured_rows),
            "agreements": empty,
        }

    starts = [f.start_time for f in fixtures if f.start_time]
    window_start = (min(starts) if starts else now) - MATCH_WINDOW
    window_end = (max(starts) if starts else now) + MATCH_WINDOW

    async with get_task_session() as session:
        pool = await _candidates(session, window_start, window_end)
        linked_already = await _already_linked(session, fixtures)

        for fixture in fixtures:
            verdict, matches = classify_fixture(fixture, pool)

            if verdict == VERDICT_DOUBLES:
                run.doubles_skipped += 1
                continue

            # ── ASKED BEFORE THE CANDIDATE IS CONSIDERED, not only on the miss
            # path (CERT-895 repair). ─────────────────────────────────────────
            #
            # This used to sit inside the `VERDICT_UNMATCHED` arm, on the
            # reasoning that an already-linked fixture has no candidate BY
            # CONSTRUCTION: `CANDIDATES` filters `statpal_fixture_id IS NULL`, so
            # the row holding the id cannot be offered back. That reasoning is
            # true about THE HOLDER and says nothing about any OTHER row.
            #
            # A second row matching the same two players inside ±36h is a
            # candidate, and the loop would link the fixture to it — writing the
            # scalar onto a second row while the first still holds it. The
            # outcome is a MULTIPLE_HOLDERS duplicate, MANUFACTURED by the task
            # whose new job is to report that state, and reported as
            # `linked: 1, unpaired: 0`. The half-link case is worse still: the
            # broken row stays broken and now has a twin.
            #
            # So the question is asked FIRST. If we already hold this id in any
            # form, this pass writes nothing for this fixture — it reports what
            # it holds. Repairing a half-link is not this task's to do (D35,
            # #2693); manufacturing a second one certainly is not.
            prior = linked_already.get(fixture.fixture_id)
            if prior is not None:
                _record_prior(run, fixture, prior)
                continue

            if verdict == VERDICT_UNMATCHED:
                # Nobody holds this id and nothing matched: a genuine miss, which
                # is the signal the classification above exists to keep clean.
                run.unmatched.append(_receipt(fixture))
                continue
            if verdict == VERDICT_AMBIGUOUS:
                # Two of our rows for one StatPal match. A duplicate, proven by
                # something better than a name window — and not this task's to
                # resolve (D35, #2693). Write nothing; say exactly which rows.
                run.ambiguous.append(
                    _receipt(
                        fixture,
                        candidates=[
                            {
                                "event_id": c["id"],
                                "sport_key": c["sport_key"],
                                "teams": [c["home"], c["away"]],
                                "commence_time": c["commence_time"].isoformat(),
                            }
                            for c in matches
                        ],
                    )
                )
                continue

            candidate = matches[0]
            if not apply:
                run.linked += 1
                continue

            try:
                outcome = await _link_one(session, fixture, candidate)
            except Exception as e:  # one bad row never wipes the pass (#42)
                await session.rollback()
                logger.exception(
                    "StatPal tennis link failed for fixture %s -> event %s: %s",
                    fixture.fixture_id, candidate["id"], e,
                )
                run.unmatched.append(_receipt(fixture, error=str(e)))
                continue

            if outcome == LOST_RACE:
                # CERT-895 repair. Losing the `IS NULL` guard proves only that
                # SOMETHING claimed the column between our candidate query and
                # our write. It does not prove the winner finished the job.
                #
                # Counting it as `already_linked` unconditionally asserted a pair
                # we never looked at, and the winner has three other endings: it
                # committed both shapes (a real link), it wrote the scalar and
                # rolled back on a refused anchor (then nobody holds it and this
                # is not a link either), or a third writer left a half-link. So
                # the pair is RE-READ after the rollback and classified like any
                # other prior — the one place in this task that learns something
                # by asking twice, because the state genuinely changed underneath.
                await session.rollback()
                reread = await _already_linked(session, [fixture])
                _record_prior(
                    run,
                    fixture,
                    reread.get(fixture.fixture_id)
                    or {"state": PRIOR_VANISHED, "event_id": candidate["id"]},
                )
                continue

            if outcome not in COMMITTABLE_OUTCOMES:
                # CERT-871 FOLLOW-UP `AUTHORITY-006-LINK-WRITE-OUTCOMES`.
                #
                # Only WROTE and CONFIRMED mean the anchor names this event. The
                # branch used to name COLLISION alone and commit everything else,
                # which is a whitelist written as a blacklist: `STALE_INCUMBENT`
                # and `NO_KEY` both fell through to the commit and left the
                # column set with NO ANCHOR AT ALL.
                #
                # That row is worse than an unlinked one. `events.statpal_fixture_id`
                # says linked, the anchor table says nothing, and the two
                # disagree silently — a reader that consults the column believes
                # the link and ruling 048's drain clause never sees it. It is
                # also invisible to the D51 restore, which only knows the rows
                # the one-time apply wrote.
                #
                # Rolled back and receipted, carrying the outcome that caused it,
                # so a new anchor outcome arrives as a named finding rather than
                # as a half-written link nobody counted.
                await session.rollback()
                run.write_refusals.append(
                    _receipt(fixture, event_id=candidate["id"], outcome=outcome)
                )
                if outcome == COLLISION:
                    run.collisions.append(
                        _receipt(fixture, event_id=candidate["id"], outcome=outcome)
                    )
                continue

            await session.commit()
            run.linked += 1
            # The pool is per-pass, so a row linked by this pass must not be
            # offered to the next fixture — otherwise two StatPal matches can
            # both "match" it and the second one silently loses the race
            # instead of being reported as the ambiguity it is.
            pool = [c for c in pool if c["id"] != candidate["id"]]
            if outcome != WROTE:
                logger.info(
                    "StatPal tennis anchor for fixture %s on event %s: %s",
                    fixture.fixture_id, candidate["id"], outcome,
                )

        # Measured in the SAME session as the write pool so both describe one
        # moment (precedent D46), and read SEPARATELY from it. `CANDIDATES`
        # filters `statpal_fixture_id IS NULL`, which is right for deciding what
        # to write and wrong for deciding what to measure: a denominator that
        # shrinks every time the task succeeds cannot be compared to yesterday's,
        # and the seven-day count is exactly that comparison.
        measured_rows = await _measurement_rows(session, now)

    agreements = build_tennis_agreements(
        fixtures=[fixture_side(f) for f in fixtures],
        rows=measured_rows,
        read_failures=run.read_failures,
        sources_read=run.sources_read,
        window=(window_start, window_end),
        measurement_window=tennis_measurement_bounds((now, now), now=now),
        statpal_read_span=statpal_read_span(now),
    )
    for row in agreements.values():
        # Both populations gate PENDING-NO-GOVERNING-NUMBER, so neither advances
        # anything — the day is recorded anyway, exactly as MLB's is. A carried
        # day is a measured day, and the history has to exist before the ruling
        # that would score it, or the ruling arrives to an empty ledger.
        await record_agreement_day(row, at=now, apply=apply)

    summary = run.summary()
    logger.info("StatPal tennis linker: %s", summary)
    return {
        **summary,
        "rows_measured": len(measured_rows),
        # PLURAL, and keyed by population. One task banks two rows, because
        # singles and doubles are two draws that must never share a denominator
        # (`authority_agreement.MEASUREMENT_POPULATIONS`). The endpoint reads
        # `agreements[sport_key]`; `agreement` stays absent rather than holding
        # one of the two, because a reader that took the singular here would get
        # whichever draw this file happened to list first.
        "agreements": agreements,
        "ambiguous_receipts": run.ambiguous,
        "unmatched_receipts": run.unmatched,
        "collision_receipts": run.collisions,
        "write_refusal_receipts": run.write_refusals,
        "unpaired_receipts": run.unpaired,
    }
