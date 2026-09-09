"""When ESPN goes dark for a sport, who serves it — and why the answer is usually "still ESPN". #3473, D50.

**SHIP: when ESPN goes dark for a sport, the site keeps showing that sport's
games instead of freezing on last-known state.** (Pillar: MATCHING. Program
step 7, the last one, riding the lane's ship: *every game exists on the site
before any market lists it; nothing goes blank when ESPN does.*)

THE SEAM, AND THE DISTINCTION THAT WAS BEING THROWN AWAY
════════════════════════════════════════════════════════
`services/espn_api.get_scoreboard` is careful, and says so in its own docstring:
it returns `None` when ESPN did not answer — *"the authority is dark: an event's
absence from the board proves NOTHING"* — and `[]` when ESPN answered and the
slate is genuinely empty. lane1/045 carried that distinction into
`_sync_espn_live_events`, leaving a dark sport's key ABSENT from `espn_data`
rather than setting it to `[]`, and counting it as `authority_dark_sports`.

Thirty lines later the consumer collapsed it:

    espn_events = espn_data.get(sport_key, [])
    if not espn_events:
        continue

`.get(sport_key, [])` maps an outage and an empty Tuesday onto the same `[]` and
the same `continue`. The producer's disambiguation survived into a counter and
died in the control flow — a distinction that reaches a gauge but not the branch
that would act on it is not a distinction the system has. :func:`espn_reading`
is that branch's missing question, and it is the reason this module leads with
readings rather than with the switch.

WHY THIS IS BESIDE `authority_for`, NOT INSIDE IT
═════════════════════════════════════════════════
Two different questions, and folding them into one function would make the
answer to both unsayable:

  * `config.authority_by_sport.authority_for` answers **"who is the source of
    record for this sport?"** — a standing fact, changed by a human editing one
    line under D50, and true whether or not anything is happening right now.
  * :func:`decide` answers **"who is serving this sport on this pass?"** — a
    temporary override that exists only while a provider is silent, and that
    must end the instant the silence does.

So a row can say both, and they can disagree without either being wrong:
`current: espn, serving: statpal (ESPN dark since …)`. A single function
returning one string would force the caller to guess which of the two it had
been given, and the guess is only wrong during an outage — the exact moment
nobody is reading carefully.

THE FAILOVER NEVER LATCHES, AND THAT IS THE WHOLE DEACTIVATION DESIGN
═════════════════════════════════════════════════════════════════════
:func:`decide` is a pure function of *this pass's* readings. There is no "in
failover since T" flag, no cool-down, no consecutive-empties threshold.
Deactivation is therefore not a mechanism at all: the pass where ESPN answers
returns `ESPN_ANSWERED`, and the override is over because it was never stored.

Both of the obvious alternatives are traps this repo has already paid for:

  * **A latched flag cleared on ESPN success.** A gate fed by a measurement that
    only *success* refreshes can never reopen — and ESPN's recovery is not
    always a success-shaped event. ESPN coming back with a genuinely empty
    Tuesday slate is indistinguishable, at the flag, from ESPN still being dark,
    so the latch would outlive the outage by however long the sport is out of
    season.
  * **A threshold on N consecutive empty passes.** That is a bound derived from
    a measured maximum, and the next quiet stretch refutes it. It also cannot
    tell an outage from an off-season at all, which is the one thing the caller
    needs.

Ending a failover is therefore strictly cheaper than starting one: starting
needs a gate, a standby read and a served pass; ending needs nothing to happen.

THE GATE IS `flip_permitted`, UNCHANGED — SO THIS SHIPS DARK
════════════════════════════════════════════════════════════
A failover may only fire for a sport that would already pass D50's measured
half. It is the same gate, the same seven days and the same
`config.authority_by_sport.flip_permitted` that a permanent flip needs; this
module does not define a second, softer bar for the temporary case. A source
trusted enough to serve a sport during an outage is trusted enough to serve it,
and an outage is the *worst* moment to be running on a provider that had not
cleared the bar.

**This mechanism is live as of D104 = A4 (Alex, 2026-09-09).** It was built and
proven in every state while `flip_permitted` still refused every sport; that
window has closed. `americanfootball_nfl` is now permitted without a
certification streak, so the serving paths through :func:`decide` are reachable
in production for football and a dark-ESPN pass will call StatPal. The remaining
sports are one release each under #2867 — read
`config.authority_by_sport.FLIP_RULED_WITHOUT_STREAK` for the current set rather
than trusting this paragraph, which is prose and rots.

WHAT THIS IS WORTH, GIVEN THAT THE COVERAGE ALREADY EXISTS
══════════════════════════════════════════════════════════
lane1/130 measured the outage coverage per sport
(`tests/test_espn_dark_fallback_coverage_2867.py`) and the answer is that for
the sports a failover could fire on at all, **StatPal already serves them
through beats that do not depend on ESPN**: `transition-event-statuses` (60s,
no API client, which is what keeps `status='live'` reachable during an outage),
`sync-statpal-livescores` (30s), `sync-statpal-schedules-*` (1h). They also
rejected the original sketch for this step — routing StatPal fixtures through
the ESPN passes — as a twin factory, correctly.

That coverage is why the serving act was nearly argued away, and CERT-2050 was
right to refuse the argument. Earlier presentations dispatched the StatPal tasks
and described the act as cadence rather than coverage — pulling an hourly
schedule sync forward — which made it sound like the smallest part of this
module's value and left what remained as observability. It is not, on either
count. A caller that DECIDES a sport is unserved and then serves nothing has
shipped a receipt; *"a measurement is not progress"* (CLAUDE.md). And the act is
no longer a dispatch: `espn_sync._act_on_failovers` awaits the StatPal writers
in-line, inside the pass, so the work does not wait on a queue at the one moment
a queue is the wrong thing to be waiting on.

So the act is first. What the surrounding machinery adds is three more things:

  1. **The distinction the consumer had lost** — `espn_data.get(sport_key, [])`
     (see above), which lane1/045 fixed at the producer and which died at the
     branch.
  2. **A receipt per silent sport per pass.** Nothing recorded an ESPN outage
     per sport with a reason before this; the counter said how many, never
     which or why.
  3. **:data:`LIVE_PATH_DARK` — the state where the site DOES go blank.** ESPN
     silent AND StatPal's `livescores` dark means no source can say what is
     happening in a game that is on, and nothing was watching for it. The
     beats lane1 counted all keep running greenly through it.

"NEVER FOR STATE DISAGREEMENTS" IS A PROPERTY OF THE INPUT, NOT A RULE ON TOP
═════════════════════════════════════════════════════════════════════════════
Program step 7 says the failover fires on an outage and *never* for state
disagreements. That is not enforced by a check here; it falls out of the
signature. Every input to :func:`decide` is a *reading* — did the provider
answer, and does it have fixtures — and a reading is a count of games, never
their contents. A score mismatch, a status disagreement or a wrong period cannot
reach this function, because there is no parameter they could arrive in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

from app.config.authority_by_sport import (
    ESPN,
    STATPAL,
    authority_for,
    flip_permitted,
)

# --- Readings: what one provider told us about one sport, on one pass --------
#
# Three states, not two. The whole defect this module rides on is a caller that
# had two.

#: The provider did not answer. Its silence proves nothing about the sport —
#: no game may be settled, voided or completed on the strength of it.
DARK = "dark"

#: The provider answered, and has no fixtures for this sport. A real claim: it
#: is asserting there are no games, and on most days it is right.
EMPTY = "empty"

#: The provider answered, and has fixtures.
FIXTURES = "fixtures"

#: The caller did not ask. Distinct from :data:`DARK` on purpose — "we have no
#: answer because we did not look" and "we have no answer because the provider
#: went quiet" are opposite facts, and a value domain that shared one symbol
#: between them would let the cheaper one masquerade as the graver one.
NOT_READ = "not-read"

#: The standby HAS no endpoint that could answer about this window, so there is
#: no question to put to it. Like :data:`NOT_READ` this is a fact about our
#: integration and not a reading of the provider, and it is separate from
#: :data:`NOT_READ` because that one is a bug and this one is a boundary.
#:
#: **The case is soccer and tennis (#4320).** Their schedule is served one
#: calendar board at a time and *there is no d0* — tennis's answers HTTP 500,
#: soccer's `offset=0` is `matches/live` wearing a schedule URL. Nor do the
#: neighbouring boards close over today: a board runs ~25.5h from 23:00Z the
#: previous day to 00:30–00:45Z the next, so `d-1` ends ~00:45Z today and `d1`
#: begins ~23:00Z today, leaving ~22 hours of today reachable from no board at
#: all. :func:`reading_in_window`'s window is `[now - 6h, now]` and always lies
#: inside that gap.
#:
#: **Why it may not be reported as :data:`DARK`.** DARK routes to
#: :data:`STANDBY_DARK`, which is in :data:`BLANK_CODES` — the refusals an actor
#: logs at ERROR because the provider failed. Reporting a permanent property of
#: StatPal's product as an outage sends an operator to look at a StatPal that is
#: answering perfectly, and does it for nine of the fourteen mapped sports at
#: once. **Nor as :data:`EMPTY`**, which asserts StatPal has no games — the
#: forged reading, and the one #3800 was filed on.
NO_SCHEDULE_BOARD = "no-schedule-board"


def espn_reading(espn_data: Mapping[str, Any], sport_key: str) -> str:
    """ESPN's reading for `sport_key`, from `_sync_espn_live_events`'s own dict.

    The dict's shape *is* the signal, and it is the one the caller was
    discarding: the fetch loop leaves a dark sport's key ABSENT and stores `[]`
    for an empty slate, so absence and emptiness are already two different
    things by the time this is called. `espn_data.get(sport_key, [])` is exactly
    the line that undoes it.
    """
    if sport_key not in espn_data:
        return DARK
    return FIXTURES if espn_data[sport_key] else EMPTY


def reading_from_fixtures(fixtures: Optional[Iterable[Any]]) -> str:
    """A standby provider's reading, from a client that returns `None` when dark.

    `None` and `[]` mean different things here for the same reason they do in
    `get_scoreboard`, and every StatPal read this feeds on follows that
    convention. A client that cannot express the difference must not be turned
    into a reading by guessing which one it meant.

    **Counts whatever it is handed, so the caller owns the window.** Handing it
    an unfiltered season schedule is the defect :func:`reading_in_window`
    exists to prevent; see that function before using this one on a standby.
    """
    if fixtures is None:
        return DARK
    return FIXTURES if list(fixtures) else EMPTY


#: How far back a standby fixture may have started and still count as a game the
#: site should be showing right now.
#:
#: **Not a chosen number.** It is `_sync_espn_live_events`'s own
#: `recently_completed_cutoff` — the sync's existing definition of "recent
#: enough that this pass still cares" — restated here so the failover's window
#: and the pass's window cannot drift apart. A bound invented for this
#: comparison would be a bound from a guess, and the next sport with a longer
#: game would refute it.
WINDOW_BACK = timedelta(hours=6)


def reading_in_window(
    fixtures: Optional[Iterable[Any]],
    *,
    now: datetime,
    back: timedelta = WINDOW_BACK,
) -> tuple[str, dict[str, Any]]:
    """A standby's reading over the window ESPN's silence was measured in.

    **THE COMPARISON HAS TO BE OVER MATCHED WINDOWS, AND THIS IS THE FUNCTION
    THAT MAKES IT ONE.** `get_scoreboard` answers about *today*;
    `get_schedule_fixtures` answers with a whole season — 321 NFL games from
    August to February, 1,206 NBA, 1,404 NHL. Counting the season against
    today's board says "StatPal has fixtures and ESPN does not" on every quiet
    day there has ever been, which would turn `BOTH_QUIET` — the state that
    exists precisely so an empty board is not read as a failure — into a state
    the system could never enter. (Found by CERT-2040 against the first cut of
    this ship, which did exactly that.)

    THE WINDOW IS `[now - back, now]`, AND ITS FORWARD EDGE IS `now` ON PURPOSE.
    A fixture that has not started yet cannot be the blank this ship is about: a
    scheduled game is on the site from the odds and StatPal schedule beats
    whether or not ESPN ever mentions it. What goes blank when ESPN goes dark is
    a game that is **already under way or has just finished** and stops being
    updated. So the forward edge needs no invented bound — there is nothing to
    put there.

    A fixture with no `start_time` is UNPLACEABLE and does not count. It cannot
    be shown to be in the window, and counting it would let an undated season
    row trigger the very failover this function exists to prevent. Reported in
    the detail rather than dropped silently.

    Returns `(reading, detail)`; the detail is receipt material, so an operator
    reading `EMPTY` can see it was 0 of 321 rather than 0 of 0.
    """
    if fixtures is None:
        return DARK, {"read": "dark"}

    rows = list(fixtures)
    start = now - back
    in_window = 0
    undated = 0
    for row in rows:
        when = getattr(row, "start_time", None)
        if when is None:
            undated += 1
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if start <= when <= now:
            in_window += 1

    detail = {
        "read": "ok",
        "total": len(rows),
        "in_window": in_window,
        "undated": undated,
        "window": [start.isoformat(), now.isoformat()],
    }
    return (FIXTURES if in_window else EMPTY), detail


#: Schedule statuses that mean a fixture is over or was never played, so
#: `livescores` is under no obligation to carry it. `StatPalFixture.status` is
#: already normalised to this vocabulary by the client's parsers.
TERMINAL_FIXTURE_STATUSES = frozenset({"finished", "cancelled", "postponed"})


def active_fixtures(
    fixtures: Optional[Iterable[Any]],
    *,
    now: datetime,
    back: timedelta = WINDOW_BACK,
) -> list[Any]:
    """The in-window fixtures `livescores` is expected to be carrying right now.

    In-window (see :func:`reading_in_window`) AND not terminal. A game StatPal's
    own schedule calls `finished` has legitimately dropped off the live board,
    and demanding it be there would make readiness permanently false for the six
    hours after every game ends.
    """
    rows = [] if fixtures is None else list(fixtures)
    start = now - back
    out = []
    for row in rows:
        when = getattr(row, "start_time", None)
        if when is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if not (start <= when <= now):
            continue
        if str(getattr(row, "status", "") or "").lower() in TERMINAL_FIXTURE_STATUSES:
            continue
        out.append(row)
    return out


def live_reading_for(
    active: Iterable[Any],
    live_rows: Optional[Iterable[Any]],
    *,
    key: Any,
    bears_state: Any,
) -> tuple[str, dict[str, Any]]:
    """Is StatPal reporting live on THE GAMES AT RISK — not merely answering?

    **This is CERT-2046's repair, and it is the third and last tightening of the
    same claim.** Readiness used to accept any successful `livescores` response,
    including `[]`, as proof the live path worked. It is not: a schedule saying
    a game kicked off an hour ago and a `livescores` carrying nothing are two
    readings from the same provider that CONTRADICT each other, and the first
    cut treated the contradiction as health. The dispatched writer then skipped
    immediately on the empty list, so nothing was written while the receipt said
    StatPal was serving.

    So readiness is now evidence about the specific games at risk. Every active
    fixture must appear on the live board; one missing is a refusal.

    **A MATCHING ROW IS NOT ENOUGH; IT HAS TO CARRY STATE** (CERT-2047, the
    fourth and last turn of this same screw). A live row for the right teams
    marked `scheduled`, with no scores and no period, matches on the key and
    advances nothing: the writer's every state-bearing branch is guarded on
    `home_score`/`away_score` being present or a `raw_status` richer than
    "live". Accepting it declared StatPal to be serving over a pass that would
    write nothing at all.

    **BOTH PREDICATES ARE PASSED IN, AND BOTH BELONG TO THE WRITER.** The caller
    passes `statpal_sync._fixture_match_key` and
    `statpal_sync.live_row_bears_state` — the writer's own matching function and
    a predicate that lives in the writer's own module beside the loop it
    describes. That is the whole design, arrived at the hard way over four
    reviews: readiness and the writer cannot disagree about "same game" or
    "useful row", because there is one definition of each and readiness borrows
    it. A game readiness counts as covered is exactly a game the writer will
    find AND advance.

    Returns `(reading, detail)`. `DARK` is not produced here — a transport
    failure is the caller's to catch, because a raise and a gap are different
    facts and this function only ever sees the second.
    """
    active = list(active)
    if live_rows is None:
        return DARK, {"read": "dark"}

    rows = list(live_rows)
    stateless = sum(1 for r in rows if not bears_state(r))
    live_keys = {
        key(getattr(r, "home_team", "") or "", getattr(r, "away_team", "") or "")
        for r in rows
        if bears_state(r)
    }
    missing = [
        r
        for r in active
        if key(getattr(r, "home_team", "") or "", getattr(r, "away_team", "") or "")
        not in live_keys
    ]

    detail = {
        "read": "ok",
        "active": len(active),
        "live_rows": len(rows),
        "state_bearing": len(live_keys),
        # Counted and published rather than silently filtered: a board that is
        # all `scheduled` rows is a specific, diagnosable thing, and an operator
        # reading `missing: 1` deserves to know the row was THERE and empty
        # rather than absent.
        "stateless_rows": stateless,
        "missing": len(missing),
        "missing_keys": sorted(
            key(
                getattr(r, "home_team", "") or "",
                getattr(r, "away_team", "") or "",
            )
            for r in missing
        )[:5],
    }
    # No active fixtures at all: nothing is at risk, and a quiet live board is
    # then genuinely quiet. The schedule half has already reported EMPTY in that
    # case, so `decide` never reaches this reading — but answering FIXTURES
    # rather than EMPTY keeps "no games" from ever looking like "cannot serve".
    return (EMPTY if missing else FIXTURES), detail


# --- Decision codes ----------------------------------------------------------
#
# Eight, because "no failover" has six meanings here and only one of them is a
# defect. Returning a bare False for all six is how the sport that needs a build
# step gets waited on instead — the failure `flip_permitted` was written to stop,
# and the same discipline applies to the same question asked per-pass.

#: The sport has already flipped: StatPal is its source of record standing, not
#: as an override. Not a failover, and must never be counted as one.
STANDING_STATPAL = "STANDING-STATPAL"

#: ESPN answered with fixtures. The ordinary case, and also the only
#: deactivation there is: nothing has to be undone, because nothing was stored.
ESPN_ANSWERED = "ESPN-ANSWERED"

#: ESPN is silent and this sport could not be failed over anyway, because it has
#: not cleared D50's measured half.
#:
#: **No longer every sport (D104 = A4, 2026-09-09).** Football is exempt from the
#: certification streak and reaches the serving paths below; what still lands
#: here is a sport refused for a STRUCTURAL reason — no shadow stamper, no
#: working discovery pass, no governing identity number (`baseball_mlb` today),
#: a measurement population rather than a sport key — or one that simply has not
#: been ruled yet (NBA, NHL). Read the `why`: it carries which.
NOT_GATED = "NO-FAILOVER-NOT-GATED"

#: Both providers answered and neither has a game. A quiet slate, not an outage
#: — and the reason ESPN's `[]` may never be read as a failure on its own.
BOTH_QUIET = "NO-FAILOVER-BOTH-QUIET"

#: ESPN did not answer AND the standby has no fixtures. The outage is real and
#: unexplained, but there is nothing to keep showing, so failing over would
#: change nothing except what the row claims.
NOTHING_TO_SERVE = "NO-FAILOVER-NOTHING-TO-SERVE"

#: The standby did not answer either. Failing over to a source we could not read
#: trades a known silence for an unknown one.
STANDBY_DARK = "NO-FAILOVER-STANDBY-DARK"

#: StatPal has the fixtures but its LIVE path is dark — so it can say a game
#: exists and cannot say what is happening in it.
#:
#: **This is the state where the site actually goes blank, and it is the one
#: nothing was watching.** (CERT-2044.) Two StatPal endpoints serve two halves:
#: `get_schedule_fixtures` says a game exists, `livescores` carries its score,
#: clock and status. Readiness read only the first, so a schedule-healthy /
#: live-dark StatPal reported `serving: statpal` while score and clock stayed
#: frozen — the failover claiming to serve down a path it had never checked.
LIVE_PATH_DARK = "NO-FAILOVER-LIVE-PATH-DARK"

#: `livescores` answered, and is not carrying a game its own schedule says is
#: under way. StatPal contradicting itself.
#:
#: **CERT-2046.** Distinct from :data:`LIVE_PATH_DARK` for the same reason DARK
#: and EMPTY are distinct everywhere else in this module: one is a transport
#: failure and the other is a provider that replied and had nothing to say about
#: the game at risk. Both refuse, and an operator needs to know which — the
#: first is StatPal being down, the second is StatPal being wrong.
#:
#: This is the state that made presentation three wrong: `[]` from a healthy
#: endpoint was read as health, the failover declared, and the dispatched writer
#: then skipped immediately on the empty list — writing no score, no period and
#: no snapshot while the receipt said StatPal was serving.
LIVE_PATH_SILENT_ON_THE_GAME = "NO-FAILOVER-LIVE-PATH-SILENT-ON-THE-GAME"

#: The caller reached the standby question without reading the standby. A caller
#: bug, reported rather than raised — a `KeyError` out of this path would be an
#: outage in the sport we were trying to protect.
STANDBY_NOT_READ = "NO-FAILOVER-STANDBY-NOT-READ"

#: The standby has no endpoint that covers the window, so it could not be asked
#: (:data:`NO_SCHEDULE_BOARD`). Soccer and tennis, permanently — nine of the
#: fourteen mapped sports.
#:
#: **Benign, and deliberately NOT in :data:`BLANK_CODES`.** The set's own rule is
#: that a blank code is a provider FAULT; the benign refusals it names are "a
#: quiet slate, a sport with no shadow stamper, a streak that has not run yet" —
#: facts about the day or about our build state. This is the second kind. StatPal
#: is answering; we have nothing to ask it that would bear on this window, and
#: that is a property of its product rather than an event on this pass. It reads
#: like :data:`NOT_GATED`, not like :data:`STANDBY_DARK`.
STANDBY_CANNOT_COVER_WINDOW = "NO-FAILOVER-STANDBY-CANNOT-COVER-WINDOW"

#: ESPN did not answer, the standby has fixtures, and the gate permits it.
FAILOVER_ESPN_DARK = "FAILOVER-ESPN-DARK"

#: ESPN answered, claimed no games, and the standby has fixtures for the same
#: window. The empty-200 trap caught: an answer that looks like a slate and is
#: actually a silence.
FAILOVER_ESPN_SILENT = "FAILOVER-ESPN-SILENT"

#: The two codes under which the site is being served by the standby *because
#: of an outage*. Named as a set so a caller counting failovers cannot
#: accidentally include :data:`STANDING_STATPAL`, which is a flip.
FAILOVER_CODES = frozenset({FAILOVER_ESPN_DARK, FAILOVER_ESPN_SILENT})

#: The refusals that are a FAULT rather than a fact about the day.
#:
#: ESPN is silent and the standby cannot cover for it, so nothing can say what
#: is happening in a game that is on — **the state in which the site actually
#: goes blank.** Every other refusal is benign: a quiet slate, a sport with no
#: shadow stamper, a streak that has not run yet.
#:
#: Named as a set so the actor can log these at ERROR and count them apart,
#: instead of a caller re-deciding which refusals are bad news.
BLANK_CODES = frozenset({LIVE_PATH_DARK, LIVE_PATH_SILENT_ON_THE_GAME, STANDBY_DARK})


@dataclass(frozen=True)
class FailoverDecision:
    """Who serves `sport_key` on this pass, and the reason in an operator's words.

    `why` is the point of the type. A bare `serving` string is enough to act on
    and useless to review: the six refusals differ in whether they describe a
    wait, a build step, a quiet Tuesday or a genuine outage nobody can do
    anything about, and only the reason separates them.
    """

    sport_key: str
    code: str
    serving: str
    failed_over: bool
    why: str

    def as_receipt(self) -> dict[str, Any]:
        """The receipt shape a task summary carries.

        An outage the site rode out silently is indistinguishable from an outage
        that never happened, so every pass that is not the ordinary
        :data:`ESPN_ANSWERED` publishes one of these.
        """
        return {
            "sport_key": self.sport_key,
            "code": self.code,
            "serving": self.serving,
            "failed_over": self.failed_over,
            "why": self.why,
        }


def decide(
    sport_key: str,
    *,
    espn: str,
    gate: tuple[bool, str],
    statpal: str = NOT_READ,
    statpal_live: str = NOT_READ,
    standing: Optional[str] = None,
) -> FailoverDecision:
    """Who serves `sport_key` on this pass?

    `espn` and `statpal` are readings (:data:`DARK` / :data:`EMPTY` /
    :data:`FIXTURES`; the standby's may also be :data:`NOT_READ` or
    :data:`NO_SCHEDULE_BOARD`, the two that are facts about us rather than about
    it). `gate` is `config.authority_by_sport.flip_permitted`'s own
    `(permitted, why)` — **passed in rather than computed**, for two reasons: it
    needs the sport's durable ledger, which a pure function must not reach for;
    and a test can then put this function in states production will not reach
    for months, including the ones after a flip.

    `standing` defaults to `authority_for(sport_key)`. This is the read that
    makes `config.authority_by_sport` a live switch rather than an admin
    ornament: a sport whose source of record is already StatPal does not need,
    and must not be reported as being in, a failover.

    THE ORDER OF THE QUESTIONS IS LOAD-BEARING, and one of them is out of the
    order a reader expects. The gate is asked **before** the standby's reading,
    so a caller can leave `statpal` unread until it knows the answer could
    matter — the cheapest refusal first.

    Until D104 that meant no StatPal call was ever made on ESPN's dark path,
    because the gate refused every sport. **It no longer does.** A dark pass over
    a gate-permitted sport now costs one StatPal schedule read and one livescore
    read, which is the price of the ship and is paid only on a pass where ESPN
    has already gone silent for that sport. Every other sport still refuses
    before the network, so a quiet slate costs nothing new.

    Total: every combination of inputs has an answer and none of them raise.
    """
    standing_authority = authority_for(sport_key) if standing is None else standing

    if standing_authority == STATPAL:
        return FailoverDecision(
            sport_key=sport_key,
            code=STANDING_STATPAL,
            serving=STATPAL,
            failed_over=False,
            why=(
                f"{sport_key} has already flipped: StatPal is its source of "
                "record standing, not as an outage override, so this pass's "
                "silence from ESPN is not an outage for it and nothing here is "
                "a failover. NOTE THE LIMIT — the flip is not yet a serving "
                "path: on a pass where ESPN DOES answer, this sport is "
                "processed by the ordinary ESPN loops exactly as before, "
                "because they select on what ESPN returned and not on this "
                "switch. `switch_wiring_note` carries the same caveat for the "
                "operator; do not read `serving: statpal` here as ESPN having "
                "been suppressed"
            ),
        )

    if espn == FIXTURES:
        return FailoverDecision(
            sport_key=sport_key,
            code=ESPN_ANSWERED,
            serving=ESPN,
            failed_over=False,
            why=f"ESPN answered with fixtures for {sport_key}",
        )

    permitted, gate_why = gate
    if not permitted:
        return FailoverDecision(
            sport_key=sport_key,
            code=NOT_GATED,
            serving=ESPN,
            failed_over=False,
            why=(
                f"ESPN is {espn} for {sport_key} and it cannot be failed over, "
                f"because it has not cleared D50's measured half: {gate_why}. "
                "An outage is the worst moment to start trusting a provider "
                "that had not earned it"
            ),
        )

    if NOT_READ in (statpal, statpal_live):
        return FailoverDecision(
            sport_key=sport_key,
            code=STANDBY_NOT_READ,
            serving=ESPN,
            failed_over=False,
            why=(
                f"ESPN is {espn} for {sport_key} and the gate permits a "
                "failover, but the caller did not read the standby "
                f"(schedule={statpal}, live={statpal_live}). This is a caller "
                "bug, not a fact about either provider — nothing failed over "
                "and nothing may be concluded about StatPal's coverage. BOTH "
                "halves are required: one endpoint says a game exists, the "
                "other says what is happening in it"
            ),
        )

    if NO_SCHEDULE_BOARD in (statpal, statpal_live):
        return FailoverDecision(
            sport_key=sport_key,
            code=STANDBY_CANNOT_COVER_WINDOW,
            serving=ESPN,
            failed_over=False,
            why=(
                f"ESPN is {espn} for {sport_key} and the gate permits a "
                "failover, but StatPal publishes no schedule board that covers "
                "the window this comparison is made over. Its schedule is one "
                "calendar board at a time and there is no board for today, so "
                "the question cannot be put — this is a boundary of StatPal's "
                "product, NOT an outage and NOT a claim that it has no games. "
                "Serving this sport from the standby needs a second source for "
                "today's fixture list, not a retry"
            ),
        )

    if statpal == DARK:
        return FailoverDecision(
            sport_key=sport_key,
            code=STANDBY_DARK,
            serving=ESPN,
            failed_over=False,
            why=(
                f"ESPN is {espn} for {sport_key} and StatPal did not answer "
                "either. Failing over to a source we could not read trades a "
                "known silence for an unknown one"
            ),
        )

    if statpal == EMPTY:
        if espn == EMPTY:
            return FailoverDecision(
                sport_key=sport_key,
                code=BOTH_QUIET,
                serving=ESPN,
                failed_over=False,
                why=(
                    f"both sources answered for {sport_key} and neither has a "
                    "fixture. This is a quiet slate, not an outage, and it is "
                    "the case an empty ESPN board must never be read as a "
                    "failure on its own"
                ),
            )
        return FailoverDecision(
            sport_key=sport_key,
            code=NOTHING_TO_SERVE,
            serving=ESPN,
            failed_over=False,
            why=(
                f"ESPN did not answer for {sport_key} — a real, unexplained "
                "silence — but StatPal has no fixtures for it either, so there "
                "is nothing to keep showing. Recorded rather than failed over"
            ),
        )

    if statpal_live == EMPTY:
        # StatPal answered and is not carrying a game its own schedule says is
        # under way. The writer keys live rows to events by team pair and would
        # skip every one of them, so declaring a failover here banks a receipt
        # saying "serving" over a pass that writes nothing (CERT-2046).
        return FailoverDecision(
            sport_key=sport_key,
            code=LIVE_PATH_SILENT_ON_THE_GAME,
            serving=ESPN,
            failed_over=False,
            why=(
                f"ESPN is {espn} for {sport_key}, StatPal's schedule says a "
                "game is under way, and StatPal's own live board is not "
                "carrying it. The two halves of the standby contradict each "
                "other, so it cannot serve this sport however healthy either "
                "endpoint looks on its own — and the writer, which keys live "
                "rows to events by the same team pair, would skip it and write "
                "nothing"
            ),
        )

    if statpal_live == DARK:
        # The half readiness used to skip. StatPal can name the game and cannot
        # say what is happening in it, so declaring it the server would freeze
        # score, clock and status behind a row that reads `serving: statpal`.
        # Refused loudly rather than served: this is the state in which the
        # site genuinely does go blank, so it is the one worth an alarm.
        return FailoverDecision(
            sport_key=sport_key,
            code=LIVE_PATH_DARK,
            serving=ESPN,
            failed_over=False,
            why=(
                f"ESPN is {espn} for {sport_key} AND StatPal's live path is "
                "dark. StatPal has fixtures in the window, so it can say the "
                "game exists — but `livescores` did not answer, so it cannot "
                "say what is happening in it, and score, clock and status "
                "would freeze behind a row claiming to be served. BOTH "
                "providers are now silent about live state for a sport that "
                "has a game on: this is the blank, not a failover away from it"
            ),
        )

    code = FAILOVER_ESPN_DARK if espn == DARK else FAILOVER_ESPN_SILENT
    detail = (
        "ESPN did not answer"
        if espn == DARK
        else (
            "ESPN answered and claimed no games, which StatPal contradicts — an "
            "answer shaped like a slate and behaving like a silence"
        )
    )
    return FailoverDecision(
        sport_key=sport_key,
        code=code,
        serving=STATPAL,
        failed_over=True,
        why=(
            f"{detail} for {sport_key}, StatPal has fixtures for the same "
            f"window, and the gate permits it: {gate_why}. StatPal serves this "
            "sport until the pass on which ESPN answers again"
        ),
    )


def would_fail_over_now(
    sport_key: str, gate: tuple[bool, str], *, standing: Optional[str] = None
) -> FailoverDecision:
    """If ESPN went dark for `sport_key` right now, would anything happen?

    The question an operator deciding whether to flip a line actually has, and
    the step-7 analogue of the `switch_note` disclosure #3442 put on the same
    row: satisfying every visible condition and changing nothing is the failure
    mode both exist to make impossible to walk into.

    Answered by running the REAL decision against the most favourable
    hypothetical — ESPN dark, and BOTH halves of the standby healthy — rather
    than by a second reading of the same rules. A disclosure that re-derives its
    subject's logic is a disclosure that can disagree with it, and this one
    cannot: if it says nothing would happen, nothing would happen, because it
    just asked.

    "Most favourable" has to include the live path since CERT-2044, or the
    disclosure would answer a question the decision no longer asks.
    """
    return decide(
        sport_key,
        espn=DARK,
        statpal=FIXTURES,
        statpal_live=FIXTURES,
        gate=gate,
        standing=standing,
    )


def gate_on_unreadable_ledger(sport_key: str, ledger_why: str) -> tuple[bool, str]:
    """The gate, asked when the durable ledger could not be READ at all. #4443.

    `read_ledger_days` returning `None` is not `[]`. `[]` is "measured, nothing
    there"; `None` is "we could not look" — a degraded snapshot store.

    This used to be `(False, ledger_why)` unconditionally, with the comment "an
    outage in the snapshot store can never open this gate". **That was correct
    before D104 and is not correct after it.** Before D104 the ledger WAS the
    evidence, so no ledger honestly meant no permission. After D104 the ledger
    is a MONITOR for a ruled sport: Alex retired the proof days on 2026-09-09
    and kept the daily fold running as an observation. Refusing football
    because the monitor's store is degraded refuses on the monitor rather than
    on evidence — and it does so in the exact hour the ruling exists for, since
    ESPN going dark and the snapshot store going away are not independent
    events. One broad incident produces both.

    SO WHY NOT `if sport_key in FLIP_RULED_WITHOUT_STREAK: return True, ...`?
    Because that is a second copy of "which sports are exempt", living in the
    caller, free to drift from the gate. Instead the gate is asked with an
    EMPTY ledger, and the answer is taken as given. That is sound because of a
    property of `flip_permitted` that is worth stating out loud: **`[]` can
    permit a ruled sport and nothing else.** Every other route to `True` in
    that function runs through `compute_streak`, and an empty ledger makes it
    return `None`, which refuses. `flip_permitted` already renders this case
    correctly too — its D104 branch is asked BEFORE the `streak is None`
    refusal. The pure function was right all along; only its callers never let
    it answer. `test_only_a_ruled_sport_can_pass_the_gate_on_an_empty_ledger`
    pins the property against every measured sport, so adding a fifth re-checks
    it rather than inheriting it.

    The failed read stays in the reported `why` on BOTH arms. Ignoring the
    monitor as an authority is the ruling; dropping it from the receipt would
    make an outage indistinguishable from a healthy monitor in every record we
    keep.

    **WHY IT LIVES HERE RATHER THAN IN THE RUNTIME THAT FIRST NEEDED IT (#4531).**
    It was born private in `tasks/espn_sync`, which is the only place that ACTS
    on it — and that is exactly how the admin projection came to disagree with
    the runtime. `routes/admin_providers` answers "if ESPN went dark right now,
    would anything happen?" by running the real decision (:func:`would_fail_over_now`
    immediately above), but it built the `gate` argument itself with the very
    `(False, ledger_why)` line D104 retired. So on a pass where the monitor was
    unreadable the disclosure said `would_fire_if_espn_went_dark: false` for a
    ruled sport while the runtime failed over — the disclosure contradicting the
    behaviour it discloses, in the one place a human checks before ruling on a
    flip.

    A disclosure may not re-derive its subject's logic, and "the gate" is not
    only `flip_permitted` — it is `flip_permitted` **plus how its argument is
    built when the ledger will not read**. Both halves have to be shared for the
    two answers to be the same answer, so this half moved next to
    :func:`would_fail_over_now`, where the discloser already looks.
    """
    permitted, why = flip_permitted(sport_key, [])
    if not permitted:
        # Byte for byte the behaviour before #4443 for every unruled sport:
        # refused, carrying the ledger's own reason rather than a streak verdict
        # that was never computed.
        return False, ledger_why
    return True, f"{why}. NOTE — the monitor could not be read on this pass: {ledger_why}"
