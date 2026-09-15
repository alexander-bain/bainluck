"""When a synthesized settlement point on a futures chart is stamped (#6360).

`routes/futures.py::_apply_settled_winner_freeze` (#1177) draws the graded
champion's line up to 1.0 at settlement by SYNTHESIZING a terminal chart point —
read-side only, no snapshot is written (gotcha #21). That point needs a
timestamp, and the timestamp is a claim: *this is when the question was
answered*, on a chart whose whole job is when things moved.

WHAT WAS WRONG. The freeze asked one column and fell through to the clock:

    settle_ts = now
    rd = market.resolution_date
    if rd is not None:
        settle_ts = min(rd, now)      # clamp future close-times (gotcha #14)

`resolution_date` is a SCHEDULE — `models.py` says so in as many words, "when
this market is due to close", not an observation — and on Kalshi it is routinely
in the FUTURE for a market that has already settled (gotcha #14). The clamp then
returns `now`, so the champion's point is stamped with the moment of the request.
Measured on production 2026-09-15: `/api/futures/58675941/history` (Vuelta a
España 2026, settled 14 September) served the champion's single point at
`11:32:56Z` and, 28 seconds later, at `11:33:24Z`. A dot that always sits at
"now" is 34 days right of where every other rider's series ends, and it is a
false answer to the one question the chart exists to answer.

**8,773 resolved markets holding a graded winner take that arm** (7,070 with a
future `resolution_date`, 1,275 with none, 428 with neither that nor any other
witness). 593,549 sit on a past `resolution_date` and are untouched here.

WHY `settled_at` IS NOT THE ANSWER, THOUGH IT LOOKS LIKE ONE. The row carries
`settled_at` — "WHEN status became 'resolved'" — and for the Vuelta it is
exactly right (2026-09-14T11:31:56Z). But it records when WE SAW the transition,
not when the market resolved, and the sweeps that write it use
`COALESCE(settled_at, NOW())`, so a market first noticed years late is stamped
years late. Measured over the markets settled in the trailing 30 days that hold
both columns: **98,325 have `settled_at` more than 240 h after `resolution_date`,
the worst 28,176 h — 3.2 years.** Preferring it wherever it exists would have
moved ~98k champion dots to the right by up to years: the same defect, frozen
instead of moving. So it is the LAST witness consulted, not the first.

THE ORDER, AND WHAT EACH ARM CLAIMS.

  1. `resolution_date`, when it is in the past — today's behaviour, unchanged,
     and the arm 593,549 markets already take. No measured defect; preferring
     anything else here would move them on an argument rather than on evidence.
  2. the market's LAST REAL OBSERVATION, when the chart holds one — the honest
     anchor when the schedule has not happened yet: the champion's line resolves
     where the data we actually have ends. This is gotcha #22's rule for chart
     domains ("completed-event times are not game-end times — use the last real
     snapshot") applied to the point rather than to the axis, and it is immune to
     the observation lag above because it is not an observation of settlement at
     all: it is the end of the journey.
  3. `settled_at`, when it is in the past — reached only when there is no past
     schedule AND no charted point anywhere, i.e. nothing else is known. A lagged
     stamp beats no stamp when the alternative is the clock.
  4. `now` — the only fabricated arm left, and it fires only when the row holds
     no evidence of any kind.

The basis is RETURNED, not logged: "which witness answered" is a fact a test
must be able to assert, and a bare datetime collapses four different claims into
one (the `mirror_is_servable` precedent in `game_markets_cache.py`).
"""

from __future__ import annotations

from datetime import datetime, timezone

#: The four witnesses, in the order `settled_point_timestamp` consults them.
#: Named so a caller or a test can say which one it expects without repeating
#: the strings.
BASIS_RESOLUTION_DATE = "resolution_date"
BASIS_LAST_OBSERVATION = "last_observation"
BASIS_SETTLED_AT = "settled_at"
BASIS_CLOCK = "clock"


def as_past_utc(value, now: datetime) -> datetime | None:
    """`value` as a tz-aware UTC datetime at or before `now`, else None.

    Three refusals, all deliberate:

    * anything that is not a `datetime` — the callers are ORM rows and test
      doubles, and a `MagicMock` attribute or a stray ISO string must not be
      compared against a real clock;
    * a naive datetime is ASSUMED UTC rather than refused (every timestamp this
      codebase stores is UTC, and refusing would drop a real witness);
    * a datetime in the FUTURE — the defect this module exists to end is a
      future schedule being clamped into the present. A witness that has not
      happened yet is not a witness, so it is skipped rather than clamped, and
      the next arm gets its turn.
    """
    if not isinstance(value, datetime):
        return None
    stamped = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return stamped if stamped <= now else None


def last_charted_timestamp(outcome_history) -> datetime | None:
    """The latest real point on the chart, across every series, or None.

    Takes the route's `outcome_history` map (`{outcome_id: {"history": [...]}}`)
    and reads the LAST entry of each series — they are built in ascending
    timestamp order by the caller, so the tail is the max and there is no reason
    to walk the whole series.

    🔴 Read this BEFORE the freeze touches the champion's entry. A synthesized
    settlement point is a member of `outcome_history` the moment it is appended,
    so a later read of this function would let the point become its own witness
    and walk the champion's dot forward on every request — the defect, rebuilt.

    An unparseable timestamp is skipped rather than raised on: this feeds a
    render decision, and one malformed stamp must not take the chart down
    (gotcha #42).
    """
    latest: datetime | None = None
    for entry in (outcome_history or {}).values():
        history = (entry or {}).get("history") or []
        if not history:
            continue
        raw = (history[-1] or {}).get("timestamp")
        try:
            parsed = datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if latest is None or parsed > latest:
            latest = parsed
    return latest


def settled_point_timestamp(
    *,
    resolution_date,
    last_observed,
    settled_at,
    now: datetime,
) -> tuple[datetime, str]:
    """When to stamp a synthesized settlement point. Returns `(timestamp, basis)`.

    Pure: every input is a value, `now` included, so the whole ladder is
    testable without a clock (gotcha #44 — a test anchor that reads the clock
    cannot pin a rule about the clock).
    """
    for value, basis in (
        (resolution_date, BASIS_RESOLUTION_DATE),
        (last_observed, BASIS_LAST_OBSERVATION),
        (settled_at, BASIS_SETTLED_AT),
    ):
        stamped = as_past_utc(value, now)
        if stamped is not None:
            return stamped, basis
    return now, BASIS_CLOCK
