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
needs a gate, a standby read and a dispatch; ending needs nothing to happen.

THE GATE IS `flip_permitted`, UNCHANGED — SO THIS SHIPS DARK
════════════════════════════════════════════════════════════
A failover may only fire for a sport that would already pass D50's measured
half. It is the same gate, the same seven days and the same
`config.authority_by_sport.flip_permitted` that a permanent flip needs; this
module does not define a second, softer bar for the temporary case. A source
trusted enough to serve a sport during an outage is trusted enough to serve it,
and an outage is the *worst* moment to be running on a provider that had not
cleared the bar.

`flip_permitted` refuses every sport today, so every path through :func:`decide`
that could dispatch anything is unreachable in production right now. That is the
point of building it before 2026-09-11 rather than after: the mechanism can be
written, reviewed and proven in every state while it is incapable of acting.

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
from typing import Any, Iterable, Mapping, Optional

from app.config.authority_by_sport import ESPN, STATPAL, authority_for

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
    """
    if fixtures is None:
        return DARK
    return FIXTURES if list(fixtures) else EMPTY


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
#: not cleared D50's measured half. **Every sport, today.**
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

#: The caller reached the standby question without reading the standby. A caller
#: bug, reported rather than raised — a `KeyError` out of this path would be an
#: outage in the sport we were trying to protect.
STANDBY_NOT_READ = "NO-FAILOVER-STANDBY-NOT-READ"

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
    standing: Optional[str] = None,
) -> FailoverDecision:
    """Who serves `sport_key` on this pass?

    `espn` and `statpal` are readings (:data:`DARK` / :data:`EMPTY` /
    :data:`FIXTURES`). `gate` is `config.authority_by_sport.flip_permitted`'s own
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
    matter. Today that means no StatPal call is ever made on ESPN's dark path,
    because the gate refuses every sport — the cheapest refusal first, and the
    reason this ships with no new per-pass network cost at all.

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
                "record standing, not as an outage override. Nothing here is a "
                "failover and ESPN's reading does not change what serves it"
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

    if statpal == NOT_READ:
        return FailoverDecision(
            sport_key=sport_key,
            code=STANDBY_NOT_READ,
            serving=ESPN,
            failed_over=False,
            why=(
                f"ESPN is {espn} for {sport_key} and the gate permits a "
                "failover, but the caller did not read the standby. This is a "
                "caller bug, not a fact about either provider — nothing failed "
                "over and nothing may be concluded about StatPal's coverage"
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
    hypothetical — ESPN dark, StatPal holding fixtures — rather than by a second
    reading of the same rules. A disclosure that re-derives its subject's logic
    is a disclosure that can disagree with it, and this one cannot: if it says
    nothing would happen, nothing would happen, because it just asked.
    """
    return decide(
        sport_key, espn=DARK, statpal=FIXTURES, gate=gate, standing=standing
    )
