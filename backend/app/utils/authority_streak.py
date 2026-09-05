"""The seven-day count that gates a StatPal flip, counted by the system (#2867).

**SHIP: nobody hand-counts the days any more.** D50 says nothing user-visible
flips until a sport has *seven consecutive daily rows* clearing its bar. Until
now that "seven" was a number a person kept: the stamper computed one row per
pass, banked it in Redis task metrics, and the next pass overwrote it. The only
history was `streak=<k>/7` typed into whichever handoff artifact that morning's
bus mission happened to write — four different files by 2026-09-04, and already
wrong in one of them (an NFL day measured at 99.38, i.e. `BELOW`, is recorded as
`streak=1/7`).

Two facts make that untenable rather than merely untidy:

* **The evidence is generated hourly and thrown away.** `last_result_summary`
  holds the LAST pass only, on a shared 100MB LRU Redis. A day nobody
  transcribed is not recoverable from anywhere — you cannot go back and ask
  StatPal what it served yesterday.
* **The numbers move.** NFL read 99.38 (`BELOW`) on 9/4 and 99.69 (`MEETS`) on
  9/5. Which day a streak actually started is exactly the fact a flip proposal
  turns on, and it is the fact a hand tally is worst at.

So the fold lives here, pure and table-driven, and the day it produces is
persisted by `app.services.authority_ledger`. This module knows nothing about a
database, a task or an endpoint.

WHAT COUNTS AS A DAY
════════════════════
A day is a **UTC calendar date**, and its verdict is the verdict of the LAST
pass banked that date. The stampers run hourly, so most days hold 12–24 passes
of the same sport; taking the last one keeps the spec's daily-sample semantics
("one line per sport per day", ledger spec §Row format) instead of inventing a
new aggregate.

Taking the last pass is a choice with a failure mode, so the day says when it
happened: `passes` counts them and `unstable` is true when they did not all
score the same gate. A day that was `BELOW` for twenty hours and `MEETS` at
23:00 still scores `MEETS` — and says `unstable: true`, and the sport's streak
lists it under `unstable_days`, so a flip proposal built on it can be
challenged. Silently picking the favourable sample is what this refuses to do;
silently picking the *unfavourable* one would be just as arbitrary and would
also make an honest mid-ingest blip fatal.

HOW THE STREAK WALKS
════════════════════
Backwards from the most recent recorded day, one calendar day at a time:

  * `MEETS` — counts, and the walk continues.
  * `BELOW` — stops the walk. This is the reset the spec means.
  * `NO-SCORE`, `PENDING-NO-GOVERNING-NUMBER`, `READ-FAILED` — carry: they
    neither count nor stop (spec rule 6 / gotcha #53 — a failed read must not
    reset a streak, because "we could not look" is not "we looked and
    disagreed"). They are listed in `carried_days` so a reader can see that a
    "7-day" streak spanned nine calendar days.
  * **no row at all for that date** — stops the walk, with `kind:
    "missing-day"`. A day we have no row for is not a day we measured, and a
    streak may not be claimed across it. This is deliberately harsher than
    `READ-FAILED`: a failed read is evidence that we looked, and a missing day
    is the absence of evidence (gotcha #53 again, from the other side).

`READ-FAILED` is a fifth day-state, not a fourth gate: a failed read produces a
row with no `identity` block at all, so there is no `gate` to read off it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from app.utils.authority_agreement import (
    FLIP_BAR_PCT,
    GATE_BELOW,
    GATE_MEETS,
    GATES_CARRY_STREAK,
    READ_FAILED,
)

#: Contract version of the stored ledger payload. Bumped when the shape of a
#: `days[]` entry changes; `durable_state.decode_envelope` refuses a payload
#: written under a different one rather than reading it as if it matched.
LEDGER_SCHEMA_VERSION = "authority-agreement-ledger/1"

#: Consecutive daily rows a sport needs before a flip may even be PROPOSED
#: (D50). Named here rather than written as `7` at each reader.
REQUIRED_STREAK_DAYS = 7

#: How many days of history one sport's ledger keeps. Seven is what the gate
#: needs; the rest is so a broken streak can show what broke it and when,
#: without the payload growing without bound. At ~200 bytes a day this is a
#: ~9KB JSONB value per sport — small enough that the durable row stays a
#: single-key lookup of a bounded payload, which is the condition under which
#: `durable_state_snapshots` is the right substrate at all.
LEDGER_RETAINED_DAYS = 45

#: A day whose verdict neither advances nor resets the streak. `READ_FAILED`
#: joins the two carrying gate states here because it reaches this module as a
#: day-state rather than as a gate.
DAY_STATES_CARRY = frozenset(GATES_CARRY_STREAK | {READ_FAILED})

#: Why the walk backwards stopped. Published on the streak so "why is it only
#: 3?" is answered by the payload instead of by re-deriving it from `days[]`.
STOP_BELOW = "below"
STOP_MISSING_DAY = "missing-day"
STOP_NO_EARLIER_ROW = "no-earlier-row"


def utc_day(at: datetime) -> str:
    """The UTC calendar date a pass belongs to, as `YYYY-MM-DD`.

    Naive input is read as UTC rather than as local time: every producer here
    stamps in UTC, and guessing a timezone would silently move passes near
    midnight into the wrong day — which is the one place a day boundary bug
    changes a streak.
    """
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.astimezone(timezone.utc).date().isoformat()


def empty_ledger(sport_key: str) -> dict[str, Any]:
    """A ledger with no history yet — distinct from "could not be read"."""
    return {"sport_key": sport_key, "days": [], "streak": None}


def day_state(row: dict[str, Any]) -> str:
    """The day-state of one agreement row: a gate, or `READ-FAILED`.

    A row whose read failed carries no `identity` block, so there is nothing to
    ask for a gate. A row that has an `identity` but no `governing.gate` is a
    shape this module does not recognise and must not score — it is reported as
    `READ-FAILED`'s neighbour rather than defaulted to anything, because a
    default here silently advances or silently resets a real streak.
    """
    if row.get("read") == READ_FAILED or row.get("read_failures"):
        return READ_FAILED
    governing = (row.get("identity") or {}).get("governing") or {}
    gate = governing.get("gate")
    return gate if isinstance(gate, str) and gate else READ_FAILED


def day_entry(row: dict[str, Any], *, at: datetime) -> dict[str, Any]:
    """One pass, reduced to what the ledger keeps about the day it lands in.

    Deliberately narrow. The full row stays on the endpoint, where it is
    recomputed hourly; what history needs is the verdict, the numbers it was
    reached on, and enough context to tell a quiet day from a measured one.
    """
    governing = (row.get("identity") or {}).get("governing") or {}
    identity = row.get("identity") or {}
    return {
        "day": utc_day(at),
        "state": day_state(row),
        "numbers": list(governing.get("numbers") or []),
        "values": dict(governing.get("values") or {}),
        "bar_pct": governing.get("bar_pct", FLIP_BAR_PCT),
        "denominator": row.get("denominator"),
        "both": identity.get("both"),
        "read": row.get("read"),
        "read_failures": list(row.get("read_failures") or []),
        "passes": 1,
        "states_seen": [day_state(row)],
        "unstable": False,
        "first_pass_at": at.isoformat(),
        "last_pass_at": at.isoformat(),
    }


def _merge_into_day(existing: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    """Fold today's newer pass into today's existing entry — last pass wins.

    Everything the newer pass measured replaces what the older one measured,
    because it is a later look at the same day. The two things that do NOT get
    replaced are the ones that describe the day rather than the pass: how many
    passes there were, and whether they agreed.
    """
    states = list(existing.get("states_seen") or [])
    if fresh["state"] not in states:
        states.append(fresh["state"])
    merged = dict(fresh)
    merged["passes"] = int(existing.get("passes") or 0) + 1
    merged["states_seen"] = states
    merged["unstable"] = len(states) > 1
    merged["first_pass_at"] = existing.get("first_pass_at") or fresh["first_pass_at"]
    return merged


def fold_day(
    ledger: dict[str, Any],
    row: dict[str, Any],
    *,
    at: datetime,
    retain_days: int = LEDGER_RETAINED_DAYS,
) -> dict[str, Any]:
    """Fold one agreement row into a sport's ledger and recount the streak.

    Pure: takes the stored ledger, returns a new one. The caller decides whether
    the result is worth persisting — which matters, because a fold computed on a
    ledger that could not be READ would overwrite real history with an empty
    one, and that is the one irreversible mistake available here.
    """
    fresh = day_entry(row, at=at)
    days = [dict(d) for d in (ledger.get("days") or []) if isinstance(d, dict)]

    by_day = {d.get("day"): d for d in days if d.get("day")}
    if fresh["day"] in by_day:
        by_day[fresh["day"]] = _merge_into_day(by_day[fresh["day"]], fresh)
    else:
        by_day[fresh["day"]] = fresh

    ordered = [by_day[k] for k in sorted(by_day)]
    if retain_days > 0:
        ordered = ordered[-retain_days:]

    return {
        "sport_key": ledger.get("sport_key") or row.get("sport_key"),
        "days": ordered,
        "streak": compute_streak(ordered),
        "updated_at": at.isoformat(),
    }


def _prev_day(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def compute_streak(days: Iterable[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Consecutive clearing days, ending at the most recent recorded day.

    Returns `None` only for a ledger with no days at all — "not measured yet",
    which is not a streak of zero (gotcha #53: an empty answer and a zero answer
    are different answers, and the flip gate must never read the first as the
    second).
    """
    ordered = [d for d in days if isinstance(d, dict) and d.get("day")]
    if not ordered:
        return None
    ordered.sort(key=lambda d: d["day"])
    by_day = {d["day"]: d for d in ordered}

    as_of = ordered[-1]["day"]
    count = 0
    since: Optional[str] = None
    carried: list[str] = []
    unstable: list[str] = []
    # Every path out of the walk below sets this. Initialised anyway, because a
    # streak that published no reason for its own length is the thing this
    # module exists to stop.
    stopped_by: dict[str, Any] = {
        "kind": STOP_NO_EARLIER_ROW,
        "day": None,
        "detail": "the ledger holds nothing earlier.",
    }

    cursor = as_of
    while True:
        entry = by_day.get(cursor)
        if entry is None:
            stopped_by = {
                "kind": STOP_MISSING_DAY,
                "day": cursor,
                "detail": (
                    f"no agreement row is stored for {cursor}, so no streak can be "
                    "claimed across it. A day we did not measure is not a day we "
                    "agreed on."
                ),
            }
            break

        state = entry.get("state")
        if entry.get("unstable"):
            unstable.append(cursor)

        if state == GATE_MEETS:
            count += 1
            since = cursor
        elif state == GATE_BELOW:
            stopped_by = {
                "kind": STOP_BELOW,
                "day": cursor,
                "detail": (
                    f"{cursor} scored {GATE_BELOW} on "
                    f"{', '.join(entry.get('numbers') or []) or 'its governing number'}"
                    f" — the streak restarts after it."
                ),
            }
            break
        elif state in DAY_STATES_CARRY:
            carried.append(cursor)
        else:
            # An unrecognised state is not silently carried and not silently
            # counted: it stops the walk and says so by name, so a fifth state
            # added upstream cannot quietly extend a streak (D55's shape — a
            # gap tags loudly, it never no-ops).
            stopped_by = {
                "kind": STOP_BELOW,
                "day": cursor,
                "detail": f"{cursor} carries an unrecognised state {state!r}",
            }
            break

        earlier = _prev_day(cursor)
        if earlier < ordered[0]["day"]:
            stopped_by = {
                "kind": STOP_NO_EARLIER_ROW,
                "day": earlier,
                "detail": (
                    "the ledger holds nothing earlier — the streak is as long as "
                    "the history, not necessarily as long as the agreement."
                ),
            }
            break
        cursor = earlier

    return {
        "days": count,
        "required_days": REQUIRED_STREAK_DAYS,
        "meets_flip_gate": count >= REQUIRED_STREAK_DAYS,
        "since": since,
        "through": as_of,
        "as_of_day": as_of,
        "bar_pct": FLIP_BAR_PCT,
        "carried_days": sorted(carried),
        "unstable_days": sorted(unstable),
        "stopped_by": stopped_by,
        "note": (
            "Consecutive UTC days ending at `through`, each scored on that "
            "sport's governing number (D63). `carried_days` neither advanced "
            "nor reset it; a day with no stored row stops it. Seven here is "
            "necessary for a flip and not sufficient — D50 also requires a "
            "YOUR-TURN entry Alex has seen, and the denominator those days were "
            "measured over is on each entry in `days[]`."
        ),
    }
