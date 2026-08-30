"""#2222 — ONE definition of "this futures market can still be priced".

WHY THIS FILE EXISTS
--------------------
``futures_price_refresh`` selects the markets to re-price and
``/api/admin/source-health/futures-price-freshness`` asserts that the same set
came back fresh. The module docstring of the task states the contract plainly:
*fix and guard cannot disagree about what they cover*. Until this file they
agreed only because the same six-line ``WHERE`` clause had been copied into six
places by hand — four in the route, two in the task, plus a third copy inside
the task's own ``remaining_stale`` census. Six copies of a predicate is not one
predicate; it is a drift waiting for the next clause.

#2222 is what the next clause looked like. Nineteen tier-1 markets — the
Champions League, Premier League and La Liga winner fields, Eurovision, the NBA
Coach of the Year, eight elections — sat permanently at the head of the refresh
queue, were attempted on every run, wrote zero, and held
``futures-price-freshness`` at ``red`` for a month. Every one of the nineteen
was **settled**. Not one of the liveness bounds could see it:

* ``status = 'open'`` — gotcha #33. A settled Kalshi market keeps
  ``status='open'`` in our database. It has never been a liveness test.
* ``resolution_date > NOW()`` — the task's docstring calls this "what actually
  keeps the dead out of the queue". Measured 2026-08-30, it does not: all
  nineteen carry a future ``resolution_date``, most of them one or two years
  past the date their own ticker encodes (``KXCOLOMBIAPRESR1-26MAY31`` →
  ``2027-05-31``; ``KXUCL-26``, a final played on 2026-05-30 → ``2028-05-29``).

TWO SIGNALS THAT DO KNOW, AND WERE BOTH BEING IGNORED
------------------------------------------------------
**1. Our own winner flag.** Sixteen of the nineteen already carry an outcome
with ``is_winner IS TRUE``. We had graded the contest and kept queueing it for a
price refresh. This is not new information arriving from anywhere — the writer
one level down already refuses to touch a settled outcome
(``_write_prices``), so the selector was queueing markets whose every
interesting outcome the writer was going to decline. The bound below is that
same refusal, moved to the place that can act on it.

``IS TRUE``, never ``= FALSE`` and never ``IS NOT NULL``: ``is_winner`` is
nullable with ``default=False``, so ``FALSE`` is ambiguous between "lost" and
"nobody has looked". ``TRUE`` is the only unambiguous arm and it is the only one
read here.

**2. The venue's own answer.** The remaining three have no winner recorded, and
for those the source says so directly:

* Kalshi returns the event with **no markets at all** — HTTP 200, book gone.
  That is the purge shape (gotcha #35: Kalshi EVENT data is permanent, MARKET
  data purges). Measured on all eighteen Kalshi rows: 200 with zero markets,
  unanimous, against a control (``KXSB-27``, live, 73M volume) that returns 32.
* Polymarket returns the Gamma event with ``closed: true`` on the event and on
  every one of its markets.

That answer is an *observation*, so it has to be recorded before it can be a
bound. The task stamps :data:`VENUE_SETTLED_KEY` on the market row the first
time a source says the market is over, and clears it the moment a price is
written again.

THE STAMP IS ON A CONFIRMATION DELAY, AND THAT IS THE SAFETY PROPERTY
----------------------------------------------------------------------
A single read must never retire a market. If Kalshi has a bad fifteen minutes
and answers "no markets" for a live event, an immediate exclusion would drop
that market out of BOTH the refresh set and the guard's denominator — it would
stop being priced and nothing would go red. That is the quiet direction, and it
is the one worth engineering against.

So the stamp does not exclude anything for :data:`VENUE_SETTLED_CONFIRM_HOURS`.
During that window the market stays fully eligible and keeps being retried; one
successful price clears the stamp and the clock. Only an absence that persists
across two days of hourly runs retires the row. The stamp is written **once**
(``WHERE ... IS NULL`` on the update), so the clock starts at first sighting and
a later run cannot keep pushing it forward.

THE COMPARISON IS TEXT, ON PURPOSE
-----------------------------------
The stamp is an ISO-8601 UTC string compared lexicographically against a
``to_char``-formatted cutoff, not a ``::timestamptz`` cast. ISO-8601 sorts in
time order, so the comparison is exact — and a cast cannot raise on a value some
other writer put there. The failure direction matters: a value that does not
parse as a date compares as text and, being alphabetically above a string
beginning with a year digit, leaves the row **eligible**. A corrupt stamp
therefore keeps a market live and noisy rather than silently retiring it.

WHAT THIS PREDICATE IS NOT
---------------------------
It is not a *settlement* authority and it writes nothing. It never sets
``status``, never grades an outcome, never deletes. It answers exactly one
question — *is it worth asking a venue for this market's price right now* — and
every caller that asks that question must ask it here.

Every measurement quoted above, the venue probes with their control, the
blast-radius table, and what was deliberately parked: ``docs/futures-price-dark-2222.md``.
"""

from __future__ import annotations

#: Hours a venue must keep saying "this market is over" before the market leaves
#: the refresh set. See the module docstring: the delay is the whole safety
#: property, and shortening it to zero is how a fifteen-minute upstream blip
#: retires a live market with nothing going red.
VENUE_SETTLED_CONFIRM_HOURS = 48

#: Top-level ``futures_markets.market_metadata`` key holding the first time a
#: source positively reported this market as over, as ``YYYY-MM-DDTHH:MM:SS``
#: UTC. Top level rather than nested: ``polymarket_event_id`` already
#: establishes that convention on this table, and a flat key is greppable and
#: needs no ``jsonb_set`` path handling.
VENUE_SETTLED_KEY = "price_refresh_venue_settled_since"

assert isinstance(VENUE_SETTLED_CONFIRM_HOURS, int)  # interpolated into SQL

#: SQL that formats "now, minus the confirmation window" in the same shape the
#: stamp is written in, so the two can be compared as text.
_VENUE_SETTLED_CUTOFF_SQL = (
    "to_char((NOW() AT TIME ZONE 'UTC')"
    f" - make_interval(hours => {VENUE_SETTLED_CONFIRM_HOURS}),"
    " 'YYYY-MM-DD\"T\"HH24:MI:SS')"
)

#: SQL that stamps the current UTC instant in the comparable shape.
VENUE_SETTLED_NOW_SQL = (
    "to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS')"
)

#: The two bounds #2222 added, on their own so a caller can report the
#: population they exclude rather than merely dropping it (see
#: ``SETTLED_EXCLUSION_REASON_SQL``).
#:
#: Written against the alias ``fm``. The winner sub-select uses ``fo_w`` so it
#: cannot collide with a caller's own ``fo``.
SETTLED_PREDICATE_SQL = f"""
       NOT EXISTS (
             SELECT 1 FROM futures_outcomes fo_w
              WHERE fo_w.market_id = fm.id
                AND fo_w.is_winner IS TRUE
           )
       AND (
             fm.market_metadata->>'{VENUE_SETTLED_KEY}' IS NULL
          OR fm.market_metadata->>'{VENUE_SETTLED_KEY}' > {_VENUE_SETTLED_CUTOFF_SQL}
           )
"""

#: The pre-#2222 bounds, kept verbatim and kept separate: they are the ones the
#: existing dashboards, CERT-404 G5 and the task's own comments describe.
BASE_LIVENESS_SQL = """
       fm.status = 'open'
       AND fm.source IN ('kalshi', 'polymarket')
       AND (fm.resolution_date IS NULL OR fm.resolution_date > NOW())
"""

#: The whole answer. Every selector and every guard that asks "can this market
#: be priced" composes THIS, and the guard test asserts they all do.
LIVE_MARKET_SQL = f"{BASE_LIVENESS_SQL}       AND {SETTLED_PREDICATE_SQL.strip()}\n"

#: Which of the two settled bounds retired a market, for the guard's exclusion
#: report. A market can satisfy both; the winner is named first because it is
#: our own reading and does not depend on an upstream being reachable.
SETTLED_EXCLUSION_REASON_SQL = """
        CASE WHEN EXISTS (
                  SELECT 1 FROM futures_outcomes fo_w
                   WHERE fo_w.market_id = fm.id AND fo_w.is_winner IS TRUE
                ) THEN 'has_winner'
             ELSE 'venue_settled' END
"""

#: The inverse of :data:`SETTLED_PREDICATE_SQL` — markets that pass every other
#: liveness bound and were retired only by #2222's two.
#:
#: A guard that silently shrinks its own denominator is a guard that can be
#: talked into green by the thing it measures. The freshness endpoint reports
#: this population and its reasons alongside its verdict, so "zero dark" always
#: arrives with "and here is what I ruled out, and why".
SETTLED_ONLY_SQL = f"NOT ({SETTLED_PREDICATE_SQL.strip()})"


def preserve_venue_settled(new_metadata, existing_column):
    """Carry the venue-settled stamp across a poll's wholesale metadata replace.

    🔴 THIS EXISTS BECAUSE THE BOUND WOULD OTHERWISE WORK BY ACCIDENT.

    Both ingest polls SET ``market_metadata`` to a freshly built dict on every
    upsert — ``"market_metadata": kalshi_metadata if kalshi_metadata else None``
    — which is a REPLACE, not a merge. Any key the poll does not know about is
    deleted the next time it touches the row, and the venue-settled stamp is
    exactly such a key.

    Measured 2026-08-30, the polls do not currently reach #2222's nineteen
    markets: ``updated_at`` on ``KXHOUSENJ11SPECIAL-26`` was unchanged across
    three hours, and the writer that HAD moved it is ``backfill_market_shapes``,
    which merges with ``||`` and is therefore safe. So the stamp survives today.

    It survives *because of the very starvation #2199 exists to fix*. The moment
    discovery coverage improves — which is the declared goal of the work this
    task belongs to — the poll reaches these rows, the blob is replaced, the
    clock resets to nothing, and #2222 comes back silently. A correctness
    property must not be held up by another bug, so the two update paths merge
    the key back instead.

    ``NULLIF(..., '{}')`` keeps the existing contract exactly: a poll with no
    metadata and no stamp to preserve still writes SQL NULL, not ``{}``. Both
    polls already collapse an empty dict to ``None`` before this point, so
    nothing that reads ``market_metadata IS NULL`` changes behaviour.

    ``existing_column`` is passed in rather than imported so this module keeps
    its zero-model-imports property. Inside an ``ON CONFLICT DO UPDATE`` set
    clause a bare column renders as the EXISTING row's value, which is what the
    merge needs (the same idiom ``tasks/polymarket.py`` already uses for its
    sub-market coalesce).
    """
    from sqlalchemy import cast, func
    from sqlalchemy.dialects.postgresql import JSONB

    kept = func.jsonb_strip_nulls(
        func.jsonb_build_object(
            VENUE_SETTLED_KEY, existing_column[VENUE_SETTLED_KEY]
        )
    )
    merged = func.coalesce(cast(new_metadata, JSONB), cast("{}", JSONB)).op("||")(kept)
    return func.nullif(merged, cast("{}", JSONB))
