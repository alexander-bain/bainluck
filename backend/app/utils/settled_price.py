"""#5246 — the price a settled contract is worth, written wherever it is graded.

A contract the venue has resolved is worth exactly 1 or exactly 0. Nothing else
can ever write those two values: `futures_price_refresh` refuses anything outside
`0 < prob < 1` by construction, and the venue stops quoting a `finalized` market
altogether (measured 2026-09-11 17:2xZ — every `finalized` leg of
`KXATP-26USO` returns `yes_bid: null, yes_ask: null, last_price: null`). So a
settled leg's price is not stale, it is UNREACHABLE, and the grader is the only
writer that will ever know it.

WHY THIS IS A SHARED CLAUSE AND NOT A LINE AT ONE CALL SITE (CERT-2637). The
first version of #5246 added the price to the settling UPDATEs in
`_resolve_winners_only` — which is RETIRED. The live graders are elsewhere:
`_backfill_kalshi_winners`, `_backfill_kalshi_winners_targeted`,
`_backfill_kalshi_winners_via_markets`, and the four-times-daily
`kalshi._backfill_from_settled_events`. Every one of them stamped
`api_settlement` and left the price behind, so the ship was inert on every path
a reader's row actually travels — and worse than inert once the price-refresh
refusal landed, because that made the residue those paths keep creating
permanently unreachable.

The lesson is the reason this module exists rather than a fourth copy of two
lines: **a settlement writer is a population, not a place.** Grep for the grade
(`api_settlement`), not for the statement you happened to read first, and give
the population one clause so a new writer inherits it instead of forgetting it.

`current_american_odds` goes to NULL rather than to a number: american odds for a
resolved contract are not a long price, they are undefined, and
`futures_price_refresh._KALSHI_RETIRE_DELISTED_SQL` already nulls the pair
together for the same reason.

NO CALIBRATION TRUTH MOVES. `opening_probability` and `calibration_probability`
are the curve's inputs (gotcha #144: the curve price is
`COALESCE(calibration_probability, opening_probability)`), neither is touched
here, and `futures_odds_snapshots` keeps the full price history either way. This
writes the one column that answers "what is this worth NOW", for a contract whose
answer is now known exactly.
"""

from __future__ import annotations

#: The stored type of `FuturesOutcome.current_probability`. Comparisons happen at
#: the precision the database actually keeps — see
#: `app/utils/price_change_stamp.py`, which exists because a provider float and
#: its rounded stored form are otherwise never equal.
_PRICE_TYPE = "numeric(7,6)"

#: The only two prices a settled contract can hold.
SETTLED_YES_PRICE = "1.0"
SETTLED_NO_PRICE = "0.0"

#: The grade these two prices belong to. Spelled here rather than imported so
#: this module keeps its empty import list, and pinned to
#: `kalshi_market_status.VENUE_SETTLEMENT_SOURCE` by a guard test so the copy
#: cannot drift away from the constant the graders write.
SETTLED_SOURCE = "api_settlement"


def settled_price_set_sql(price: str, alias: str = "fo") -> str:
    """SQL set-clause fragment writing the terminal price for a settled leg.

    Spliced into an `UPDATE futures_outcomes` that is already writing
    `is_winner` and `resolution_source = 'api_settlement'`, so the grade and the
    price land in one statement and cannot diverge.

    `price_changed_at` is maintained inline rather than through
    `price_change_stamp.price_changed_at_value` because these are raw `text()`
    UPDATEs, not Core set-clauses. The predicate is deliberately the same one —
    cast both sides to the column's stored type and stamp only when the write
    would actually change what is stored — so a leg already sitting at the
    settlement price is graded without being advertised as freshly moved (#2024).

    :param price: :data:`SETTLED_YES_PRICE` or :data:`SETTLED_NO_PRICE`. The value
        is interpolated, so the set of legal literals is closed by the raise
        below — including against a future caller that decides to pass a
        "probability we are fairly confident about".
    :param alias: the table alias the statement uses for `futures_outcomes`, or
        ``""`` for an unaliased `UPDATE futures_outcomes SET ...`. Postgres
        refuses a qualified column on the LEFT of a SET assignment, so only the
        read side is ever prefixed.
    """
    if price not in (SETTLED_YES_PRICE, SETTLED_NO_PRICE):
        raise ValueError(f"settlement price must be 0.0 or 1.0, got {price!r}")
    ref = f"{alias}.current_probability" if alias else "current_probability"
    stamp = f"{alias}.price_changed_at" if alias else "price_changed_at"
    return f"""
        current_probability={price},
        current_american_odds=NULL,
        price_changed_at=CASE
            WHEN {ref} IS DISTINCT FROM CAST({price} AS {_PRICE_TYPE})
            THEN NOW() ELSE {stamp} END
    """


def settlement_pending_sql(price: str, alias: str = "fo") -> str:
    """WHERE fragment: this row does NOT already hold exactly this settlement.

    #7767. A settling UPDATE wants to skip rows it has already written — but
    the obvious way to express that, `resolution_source <> 'api_settlement'`,
    keys the skip on the ONE column a half-finished settlement already got
    right. `_sync_polymarket_resolved_status` writes the grade and the price in
    one statement and guarded it that way, so any row that arrived at
    `api_settlement` by some OTHER route — graded by a writer that wrote no
    price, or minted at the last trade — was sealed out of the only rail that
    reads `outcomePrices` and could have corrected it. A repair rail whose
    lookup keys on the same column as the damage can never repair that column.

    Measured on production 2026-09-21: 217 Polymarket legs on 96 open boards
    carry `api_settlement` + `is_winner = false` over a live-looking price, 27
    of them at 20% or more. `/futures/113360` ("How many different countries
    will Israel strike in 2026?") printed **100%** as the board's hero for leg
    `0`, which Gamma resolved NO (`closed: true`, `outcomePrices ["0","1"]`) —
    while its `lastTradePrice` stayed `1` against a `0.001` ask.

    So the skip tests the whole settlement rather than its stamp: a row is left
    alone only when the grade, the side AND the price already agree with what
    this statement would write. `IS DISTINCT FROM` and not `<>`, because
    `current_probability` and `is_winner` are both nullable and a NULL on either
    side of `<>` is NULL — which is not TRUE, so the row would be skipped for
    being unreadable, i.e. exactly backwards.

    Pairs with :func:`settled_price_set_sql`; the same `price` literal drives
    both, so the side the WHERE tests for is by construction the side the SET
    writes and the two cannot be given different answers.

    :param price: :data:`SETTLED_YES_PRICE` or :data:`SETTLED_NO_PRICE`.
    :param alias: the table alias, or ``""`` for an unaliased statement.
    """
    if price not in (SETTLED_YES_PRICE, SETTLED_NO_PRICE):
        raise ValueError(f"settlement price must be 0.0 or 1.0, got {price!r}")
    won = "true" if price == SETTLED_YES_PRICE else "false"
    ref = f"{alias}." if alias else ""
    return f"""(
        COALESCE({ref}resolution_source, '') <> '{SETTLED_SOURCE}'
        OR {ref}current_probability IS DISTINCT FROM CAST({price} AS {_PRICE_TYPE})
        OR {ref}is_winner IS DISTINCT FROM {won}
    )"""


def ungraded_settlement_withdraw_sql(ticker_param: str = "tickers") -> str:
    """UPDATE: take the fossil price off a settled leg the venue gave no verdict for.

    #7987, and it is this module's own lesson turned around. The clauses above
    answer "what is a settled contract worth" for the legs the venue graded; this
    answers it for the legs on the SAME board that it did not. Both are the same
    fact — the venue has stopped quoting this contract — and the answer differs
    only because one of them has a side and the other has none.

    THE `continue` IS THE DEFECT. All four Kalshi graders in `backfill_winners`
    read `kms.gradeable_winner`, correctly refuse to invent a loss when it
    returns None (#1852), count the refusal, and `continue` — leaving the price
    exactly where it was. That is "a gate that only refuses to WRITE leaves the
    old number exactly where it was", the lesson #5031, #5273 and #5771 each paid
    for and which `futures_price_refresh._KALSHI_WITHDRAW_PRE_KICKOFF_SQL`
    records in those words. The refusal to grade is right; the price surviving it
    is not.

    :func:`app.utils.kalshi_market_status.settled_without_verdict` decides WHICH
    legs; this decides what happens to them. The split is deliberate — the
    predicate is a fact about the venue's answer and is unit-testable without a
    database, and the statement is a fact about our rows.

    NOTHING IS GRADED AND NOTHING IS UNGRADED. `is_winner` and
    `resolution_source` are absent from the SET list, so a leg the venue settled
    on a number stays exactly as ungraded as it was; only the number a reader
    reads goes away. `is_winner IS NULL` in the WHERE is the other half of that:
    a leg any rail has already graded — including one graded between the venue
    read and this write — is never touched, which is gotcha #21 and #5246's
    "never un-price a settled row" in its stricter form (this asks for no verdict
    at all, not merely "not a winner").

    🔴 NO CALIBRATION TRUTH MOVES, AND HERE THAT IS MEASURED RATHER THAN ASSERTED.
    `precompute_calibration` states that `resolution_source IS NOT NULL` — not
    `is_winner IS NOT NULL` — is "this repository's canonical grade predicate",
    and that an ungraded outcome "never reaches ``ranked_outcomes`` at all".
    Every one of the 2,656 legs this statement can reach on production
    (2026-09-22 09:5xZ, Kalshi legs with no verdict and a price on a resolved
    board with a graded sibling) carries `resolution_source IS NULL`, so none of
    them is in the curve to begin with. `opening_probability` and
    `calibration_probability` — the curve's two inputs, gotcha #144 — are not in
    the SET list either, and `futures_odds_snapshots` keeps the price history
    regardless.

    This is where it DIVERGES from #7582's clear, which refuses a row whose
    `calibration_probability` is set. That clear fires on OPEN boards, where a
    closing line may still be pending capture and `current_probability` is the
    value the capture will read. Here the board is settled, the capture window is
    shut, and the graders beside this statement already overwrite
    `current_probability` unconditionally at settlement (:func:`settled_price_values`).
    Borrowing the guard would have refused 798 of the 2,656 for no benefit.

    STAMPED, for the reason #7582's clear is stamped and
    `_KALSHI_RETIRE_DELISTED_SQL` is not: the rule is consistency with the writes
    BESIDE it. Every Kalshi grader in `backfill_winners` writes
    `last_updated = NOW()`, so an unstamped withdrawal would be the only unstamped
    write on the path. `price_changed_at` moves unconditionally because the WHERE
    already requires `current_probability IS NOT NULL` — the value is always
    really changing, and a price going away IS a change (#2024).

    :param ticker_param: name of the bind holding the leg tickers, so a call site
        that already binds ``:t`` does not have to rename it and risk binding two
        different lists.
    """
    return f"""
        UPDATE futures_outcomes fo
           SET current_probability = NULL,
               current_american_odds = NULL,
               current_yes_bid = NULL,
               current_yes_ask = NULL,
               probability_change_24h = NULL,
               last_updated = NOW(),
               price_changed_at = NOW()
          FROM futures_markets fm
         WHERE fo.market_id = fm.id
           AND fm.source = 'kalshi'
           AND fo.external_id = ANY(:{ticker_param})
           AND fo.is_winner IS NULL
           AND fo.current_probability IS NOT NULL
     RETURNING fo.id
    """


def settled_price_values(is_winner: bool) -> dict:
    """The same clause for a Core/ORM `.values()` update.

    `price_changed_at` is NOT included: a Core update has
    `price_change_stamp.price_changed_at_value` available and that helper is the
    single maintained copy of the change predicate (#2024, "five price-writing
    sites across three poll tasks"). Callers on this path add it themselves so
    there is never a second Python implementation of it.
    """
    return {
        "current_probability": 1.0 if is_winner else 0.0,
        "current_american_odds": None,
    }


def priceless_leg_keeps_its_row(outcome, *, event_is_finished: bool) -> bool:
    """Does a leg with no price still deserve its row on the board? (#8044)

    THE SERVE-SIDE OTHER HALF OF THIS MODULE. The withdrawal above is a WRITER:
    it correctly takes the fossil price off a leg the venue answered on a number
    (#7987). The residue it leaves is a row whose `current_probability` is NULL,
    and `/api/events/{id}/game-markets` dropped exactly those rows before they
    could reach the payload. So the write was right and the reader lost the row:
    *1st Touchdown* on event 14780545 served **25 of 28** runners, and Puka
    Nacua, Jordan Whittington and CJ Daniels were absent rather than shown
    without a number. A reader cannot tell a scratched runner from a quietly
    dropped one, and every adjacent ship in this area — #7537, #7747, #8011 —
    keeps the row and removes only the number.

    ** BOTH CONDITIONS ARE LOAD-BEARING, and each was measured on production
    2026-09-22 over the trailing 30 days. ** 14,743 priceless legs sit on 586
    finished events; serving all of them would not repair a board, it would
    rewrite one.

    * **`opening_probability is not None` — "we HAD a price and withdrew it".**
      That is the statement the restored row makes. A leg that never carried a
      price is not withheld, it is UNLISTED, and showing it is new content
      rather than a repaired row: **11,327 of the 14,743** are that cohort and
      stay hidden. All three specimens carry one (0.100 / 0.020 / 0.015), which
      is what makes them separable at all.
    * **`event_is_finished` — the dropped-row guard predates #7987** and is
      reached by live boards too, where a priceless leg has never been shown.
      The **1,814** once-priced-now-null legs on unfinished events are
      deliberately out of scope: a live board's missing number is a liveness
      question, not a settled-rendering one, and this ship may not answer it by
      introducing rows to a surface that never carried them.

    A leg that HAS a price is not this predicate's business and returns False —
    the caller reaches it only when the price is absent, and answering True for
    a priced leg would state something this function has not checked.

    THE ROW CARRIES NO VERDICT WITH IT. These legs have `resolution_source`
    NULL, so `_settled_grade_fields` already returns `is_winner: None` and the
    renderer prints no verdict (#4788) — restoring the row cannot crown or bury
    anybody. The payload's `probability` is already nullable, so the row arrives
    as a name with no number, which is the presentation this class has
    everywhere else.
    """
    if getattr(outcome, "current_probability", None) is not None:
        return False
    if not event_is_finished:
        return False
    return getattr(outcome, "opening_probability", None) is not None
