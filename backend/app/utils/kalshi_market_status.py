"""What Kalshi's market ``status`` values actually are — measured, not assumed.

CAL-P049 (#1818). The sibling of ``kalshi_retention.py``: a Kalshi fact that four
separate modules each encoded from memory, three of them nearly right and one of
them — the only one that writes ``futures_markets.status`` on every poll — wrong
in a way that reverted every settlement fix the backfill made.

MEASUREMENT (2026-08-13, live public Kalshi API, no auth, ~2,000 nested markets
sampled across ``GET /events?status=open|closed|settled&with_nested_markets=true``):

    market.status   carries a ``result``?   n      meaning
    ----------------------------------------------------------------------------
    active          no  (result == "")      1,215  trading
    inactive        no  (result == "")        622  listed, not trading
    closed          NO  (result == "")        832  trading over, outcome NOT yet called
    determined      YES ("yes" / "no")        371  outcome called, not yet paid out
    finalized       YES ("yes" / "no")        246  outcome called and settled

    "settled" and "open" were NOT observed as market-level statuses at all.

TWO CONSEQUENCES, and the second is the defect this module was written for:

1. **Result presence is exactly ``determined`` | ``finalized``.** Those two, and
   only those two, ever carry a ``result``. Any predicate asking "has the venue
   declared this outcome?" is asking for :data:`RESULT_CARRYING_STATUSES`.

2. **The old tuple was inverted against live Kalshi.** ``_poll_kalshi_markets``
   derived market status from ``m.status in ("closed", "settled")``. Of those two
   values, ``settled`` does not exist and ``closed`` is precisely the state that
   carries NO result — so the predicate matched none of the settlements and one
   non-settlement. Since the poll UPSERTs ``status`` on every cycle, an event whose
   markets were all ``finalized`` was rewritten to ``'open'`` every ~2 hours,
   overwriting whatever ``_backfill_from_settled_events`` had just repaired. That
   is a REVERT LOOP, not starvation — the distinction #1818 asked to be named,
   because #1192 diagnosed the same symptom as rotation starvation and shipped a
   de-starvation boost that could not possibly have helped: no scan priority
   survives being overwritten two hours later.

WHY ``closed`` IS STILL IN :data:`TERMINAL_STATUSES` BELOW. Removing it is a
separate, real question — it marks result-less markets ``resolved``, which is a
false positive — but removing it here would make the poll flip an all-``closed``
event from ``resolved`` back to ``'open'``, i.e. re-create the exact churn this
module exists to end. It is left in deliberately, flagged in #1818, and must be
changed only with its own before/after census.
"""

from __future__ import annotations

#: Statuses that always carry a ``result`` — the venue has declared the outcome.
#: This is the authority for "is this market settled?", per ruling: the venue
#: defines settlement, not our status column.
RESULT_CARRYING_STATUSES: frozenset[str] = frozenset({"determined", "finalized"})

#: Statuses treated as terminal when deriving ``futures_markets.status``.
#: ``settled`` is retained though unobserved (it costs nothing and older Kalshi
#: surfaces used it); ``closed`` is retained for the churn reason in the module
#: docstring — see #1818 before touching it.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"closed", "settled"} | RESULT_CARRYING_STATUSES
)

#: Date the table above was measured. Re-probe with
#: ``scripts/probe_kalshi_market_status.py`` and update the table WITH the sets.
MEASURED_ON = "2026-08-13"


def is_terminal(status: str | None) -> bool:
    """True when a Kalshi market status means "no longer trading toward a result"."""
    return bool(status) and status in TERMINAL_STATUSES


def has_declared_result(status: str | None) -> bool:
    """True only when Kalshi has declared this market's outcome.

    Strictly narrower than :func:`is_terminal`: a ``closed`` market is terminal
    but has no result yet. Use this one wherever a result is about to be read.
    """
    return bool(status) and status in RESULT_CARRYING_STATUSES


def all_terminal(statuses) -> bool:
    """True when every status in ``statuses`` is terminal.

    Empty input is False: an event with no markets has not settled, it is
    unknown — the gotcha-#53 rule that an absence is not a fact.
    """
    statuses = list(statuses)
    return bool(statuses) and all(is_terminal(s) for s in statuses)
