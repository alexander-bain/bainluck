#!/usr/bin/env python3
"""CAL-P991 — the id-range sweep the cell folds share, with the two failure
shapes kept apart.

WHY THIS EXISTS AS ITS OWN MODULE. Every sharded fold in ``backend/scripts``
carries its own copy of "run a range, bisect it if the server says no". The copy
is where the bug lives: **the server says no for two unrelated reasons and only
one of them is about the range.**

  * ``statement_timeout`` is a fact about the RANGE — it holds too many rows for
    the 10 s row-path budget. Splitting it is the correct and only repair.
  * ``Rate limit exceeded: 300/minute`` is a fact about the CALLER — the range
    is fine and the next request would have answered it. Splitting DOUBLES the
    request rate against the limit that just refused, so a single throttled
    range becomes a bisect storm that walks all the way to the floor and stamps
    perfectly good ranges IRREDUCIBLE. Measured 2026-09-03: one such fold
    emitted 14 IRREDUCIBLE ranges in 90 s, every one of them clean when re-asked
    alone. An IRREDUCIBLE range taints the run (gotcha #53), so a throttle
    misread this way does not merely slow the fold down — it silently converts a
    complete census into an incomplete one that still prints a table.

The same distinction ``calibration_cell_exact.py``'s transport retry draws
between an ``HTTPError`` and its ``RemoteDisconnected`` sibling, one layer up.

THE ORDERING IS THE CONTRACT, and it is the part that fails silently: throttle
must be tested BEFORE the generic not-ok branch, because a throttle that reaches
the split arm still produces a table. ``tests/test_sharded_sweep.py`` asserts the
order directly rather than only asserting the outcomes.
"""

from __future__ import annotations

import time
from typing import Callable

#: Substrings that identify a caller-side throttle rather than a range that is
#: too big. Matched case-insensitively against the recorded ``reason``.
THROTTLE_MARKERS = ("rate limit", "too many requests", "429")

#: Substrings that identify the READ GUARD refusing the STATEMENT. This is the
#: third thing a not-ok answer can mean and it is the one no amount of splitting
#: can repair: the same text is refused at every width, so bisecting it emits a
#: hundred IRREDUCIBLE ranges and buries the one fact that matters — the SQL is
#: malformed. Measured 2026-09-03: an apostrophe inside a ``--`` comment ("the
#: CAPTURE's, not the writer's") makes the guard's quote scanner read the rest
#: of the statement as a string literal and answer "Only SELECT queries are
#: allowed"; the sweep bisected to the floor and returned a table.
REFUSAL_MARKERS = (
    "only select queries are allowed",
    "refused",
    "not allowed",
    "read guard",
)


class SweepRefused(RuntimeError):
    """The read guard refused the STATEMENT — no range will ever answer it."""

#: Backoff schedule for a throttled range, in seconds. The endpoint's window is
#: a minute, so the last wait clears a full one rather than nibbling at it.
THROTTLE_BACKOFF_S = (5.0, 20.0, 65.0)


def is_throttle(reason: str | None) -> bool:
    """True when the server refused the CALLER, not the range."""
    low = (reason or "").lower()
    return any(marker in low for marker in THROTTLE_MARKERS)


def is_sql_refusal(reason: str | None) -> bool:
    """True when the read guard refused the STATEMENT, not the range.

    A throttle is checked first and wins: ``429`` bodies routinely carry the
    word "refused" from the recorder, and mistaking one for the other would
    abort a sweep that only needed to wait.
    """
    low = (reason or "").lower()
    if is_throttle(low):
        return False
    return any(marker in low for marker in REFUSAL_MARKERS)


def sweep(
    sql_tmpl: str,
    lo: int,
    hi: int,
    chunk: int,
    timeout_ms: int,
    rows: list,
    irreducible: list,
    *,
    runner: Callable[[str, int], dict],
    floor: int,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> None:
    """Walk ``[lo, hi)`` in ``chunk``-wide id ranges, appending result rows.

    ``sql_tmpl`` is formatted with ``lo`` / ``hi`` per shard. A range that is too
    big is SPLIT; a range refused by the throttle is RE-ASKED unchanged after a
    backoff; a range that is still too big at ``floor`` is recorded IRREDUCIBLE
    and never dropped. A truncated answer is treated as too big, because a
    truncated aggregate is a wrong answer rather than a short one.
    """
    pending = [(a, min(a + chunk, hi)) for a in range(lo, hi, chunk)]
    while pending:
        a, b = pending.pop(0)
        for attempt, wait in enumerate((0.0,) + THROTTLE_BACKOFF_S):
            if wait:
                log(f"  [{a}..{b}) throttled — waiting {wait}s, re-asking the "
                    f"SAME range ({attempt}/{len(THROTTLE_BACKOFF_S)})")
                sleep(wait)
            res = runner(sql_tmpl.format(lo=a, hi=b), timeout_ms)
            reason = res.get("reason")
            # ORDERING: throttle first. A throttle that falls through to the
            # split arm still produces a table, so this branch is the one a
            # test has to pin by position and not only by outcome.
            if res.get("status") != "ok" and is_throttle(reason):
                continue
            break
        else:  # every backoff exhausted and it is still the throttle
            log(f"  [{a}..{b}) IRREDUCIBLE (throttle survived backoff)")
            irreducible.append([a, b, "throttled"])
            continue

        if res.get("status") == "ok" and not res.get("truncated"):
            got = res.get("rows") or []
            log(f"  [{a}..{b}) ok rows={len(got)} {res.get('duration_ms')}ms")
            rows.extend(got)
            continue

        why = "truncated" if res.get("status") == "ok" else (
            reason or res.get("status"))
        # The statement, not the range. Splitting cannot help and would hide it.
        if res.get("status") != "ok" and is_sql_refusal(why):
            raise SweepRefused(
                f"the read guard refused the statement at [{a}..{b}): {why}. "
                "Every range would be refused identically, so the sweep stops "
                "here instead of bisecting to the floor."
            )
        if b - a <= floor:
            log(f"  [{a}..{b}) IRREDUCIBLE ({why})")
            irreducible.append([a, b, why])
            continue
        mid = (a + b) // 2
        log(f"  [{a}..{b}) {why} — split at {mid}")
        pending[:0] = [(a, mid), (mid, b)]
