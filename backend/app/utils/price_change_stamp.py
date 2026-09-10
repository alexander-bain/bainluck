"""The futures-outcome price stamps, and the two expressions that maintain them.

`price_changed_at` (#2024) and `price_observed_at` (#3879) live in one module
ON PURPOSE. They are written at the same eleven call sites, from the same local
variable, and the failure that costs the most is not either expression being
wrong — it is a site that stamps one and forgets the other. Co-location is the
cheapest guard against that, and
`tests/test_price_observed_at.py::test_every_movement_stamp_has_an_observation_stamp`
is the expensive one.

── #2024 — `price_changed_at` ───────────────────────────────────────────────


UX-P106 audited `futures_outcomes.last_updated` and REFUSED the migration-free
fix. The finding, restated because it is the whole reason this module exists:

    `app/routes/playoffs.py` reads that column as a LIVENESS gate — an outcome
    whose stamp predates the cutoff is `continue`d and does not render. Making
    the stamp conditional would therefore blank every merely-STABLE price out of
    the playoff grid: a team parked at 3% for a week disappears. Meanwhile
    `app/routes/admin_judgments.py` reads the SAME column as a price-age floor.
    Two readings, one column, no value that satisfies both.

So the column is not narrowed. A new one is added beside it, this is what
writes it, and `last_updated` keeps meaning exactly what the playoff grid
already believes it means.

── WHY A SHARED HELPER AND NOT FIVE COPIES ──────────────────────────────────

There are five price-writing sites across three poll tasks, and #1951 is the
standing lesson about what a third copy of a predicate costs: that issue WAS a
third copy of the feed's admission rule, in no parity test, silently carrying a
stale arm. A change-detection predicate is worse than most, because a copy that
drifts does not throw — it just stops stamping, and the column quietly becomes
wrong for one provider while looking healthy for the others.

── THE PRECISION TRAP, WHICH IS THE REASON THIS IS NOT A ONE-LINER ──────────

`current_probability` is `Numeric(7, 6)`, so a price is stored ROUNDED to six
decimal places. The incoming value is a Python float from a provider, and
Polymarket midpoints in particular carry far more precision than that:

    stored     0.051235          (what the last poll rounded 0.0512345678 to)
    incoming   0.0512345678      (the same unchanged price, next poll)

Compared naively those are DISTINCT, so the column would stamp on every poll of
an unmoved market — reproducing, in a new column, the exact defect #2024 is
open on, while looking like it had been fixed. Both sides are therefore cast to
the column's own type before comparison, so the question asked is the only one
that can be answered honestly: *would this write change what is stored?*
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import Numeric, case, cast, func, literal

#: The stored type of `FuturesOutcome.current_probability`. Comparisons happen
#: at the precision the database actually keeps, never at the provider's.
PRICE_NUMERIC = Numeric(7, 6)

#: `PRICE_NUMERIC`'s scale, as the quantum a Python-side comparison rounds to.
#: The ORM helpers below cannot ask Postgres "would this write change what is
#: stored?", so they have to answer it themselves — at the same precision, or
#: they reintroduce the trap the module docstring describes.
PRICE_QUANTUM = Decimal("0.000001")


def price_changed_at_value(current_col: Any, stamp_col: Any, new_probability: Any) -> Any:
    """`price_changed_at` for an ON CONFLICT DO UPDATE / UPDATE set clause.

    ``func.now()`` when this write would change the stored price, otherwise the
    row's existing stamp — so the column answers "when did this price last
    MOVE", which is the question `last_updated` cannot answer.

    :param current_col: the existing row's price column (``FuturesOutcome.
        current_probability``). Inside an ``ON CONFLICT DO UPDATE`` a bare
        column reference renders as the EXISTING row, which is what is wanted;
        ``excluded.`` would render the proposed value and make the comparison
        vacuously false.
    :param stamp_col: ``FuturesOutcome.price_changed_at`` — the value to keep
        when nothing moved.
    :param new_probability: the price about to be written. May be ``None``: a
        price going away IS a change, and ``IS DISTINCT FROM`` says so without
        the NULL-swallowing that ``!=`` would introduce.
    """
    return case(
        (
            cast(current_col, PRICE_NUMERIC).is_distinct_from(
                cast(literal(new_probability), PRICE_NUMERIC)
            ),
            func.now(),
        ),
        else_=stamp_col,
    )


def price_observed_at_value(
    stamp_col: Any, new_probability: Any, *, observed_at: Any = None
) -> Any:
    """`price_observed_at` for an ON CONFLICT DO UPDATE / UPDATE set clause.

    #3879. "When did a writer last hold a REAL price for this outcome, from the
    venue" — the freshness question neither `last_updated` (a writer wrote the
    row) nor `price_changed_at` (the number moved) can answer. See
    `FuturesOutcome.price_observed_at` for the three-column table.

    ── THE THREE REFUSALS, each of which has a production row that needs it ──

    **1. No price is not an observation.** When ``new_probability`` is ``None``
    the existing stamp is kept, unmoved. The site this protects is
    `tasks/kalshi.py`'s unpriced-ticker null-out, which writes
    ``current_probability = None`` to legs the venue returned without a book:
    that write is a real event and it correctly moves `price_changed_at` (a
    price going away IS a change), but stamping it as an OBSERVATION would let
    a leg that has had no price for a month report itself freshly observed —
    the metric lying in the one direction that flatters us. It is the same
    refusal `routes/tournaments._price_observed_at` states as "no price, no
    observation", and it matters more here because `last_updated` carries
    ``server_default=func.now()``: an outcome minted and never priced would
    otherwise claim a fresh reading of nothing.

    **2. The stamp is the instant OBSERVED, not the instant WRITTEN.** Live
    writers leave ``observed_at`` unset and get ``func.now()``, which is what
    they mean. A writer replaying HISTORY — a candlestick backfill writing a
    snapshot whose ``captured_at`` is three days old — must pass that instant
    instead, or the column would date a stale price to the moment somebody
    happened to import it. There is no such caller today; the parameter exists
    so that the first one cannot get it wrong by default.

    **3. It never moves backwards.** ``GREATEST`` against the stored value, so
    a historical replay landing after a live poll cannot un-freshen a row.
    Without it, refusal 2's parameter would be a loaded gun: any out-of-order
    backfill would rewrite a current row as ancient. ``GREATEST`` in Postgres
    ignores NULL arguments, so a first-ever observation on a NULL column still
    takes the incoming value rather than collapsing to NULL — which is the
    opposite of what ``max()`` in Python would do and the reason this is SQL.

    :param stamp_col: ``FuturesOutcome.price_observed_at`` — the value to keep
        when there is nothing to observe, and the floor the new value must
        beat. Inside an ``ON CONFLICT DO UPDATE`` a bare column reference
        renders as the EXISTING row, which is what is wanted.
    :param new_probability: the price about to be written. ``None`` means the
        venue had no price for this outcome; see refusal 1.
    :param observed_at: the instant the price was READ, for a writer replaying
        history. Defaults to ``func.now()``, which is correct for every live
        price path.
    """
    return case(
        (
            literal(new_probability).is_not(None),
            func.greatest(stamp_col, observed_at if observed_at is not None else func.now()),
        ),
        else_=stamp_col,
    )


def price_observed_at_insert(new_probability: Any, *, observed_at: Any = None) -> Any:
    """`price_observed_at` for the INSERT half of an upsert.

    The same rule as :func:`price_observed_at_value` with the two clauses that
    only exist for an existing row removed: there is no stored value to keep
    when the price is ``None`` (so the answer is ``None``), and none to take a
    ``GREATEST`` against (referencing the column inside its own ``VALUES``
    clause is not a thing).

    🔴 **THE INSERT HALF IS NOT OPTIONAL, and omitting it is the quiet way to
    make this column lie.** Every price writer here is an upsert. Wire only the
    ``set_=`` half and a newly-created priced outcome reads NULL until its
    SECOND poll — so on any market the rails reach exactly once, and on every
    market during the hour after ingest, "never observed" would be indexing
    freshly-written prices. The census in #3879 reads NULL as "no rail reaches
    this leg"; that population must not be diluted with rows a rail reached on
    the way in.
    """
    if new_probability is None:
        return None
    return observed_at if observed_at is not None else func.now()


# ---------------------------------------------------------------------------
# The ORM half — the same two stamps for a writer that assigns attributes
# ---------------------------------------------------------------------------
#
# CERT-2302 blocked #3879's first presentation on exactly this gap, and the
# reason it got that far is worth stating: the four expressions above are for a
# `set_=` / `values()` clause, so every census written to police them looks for
# an upsert. A writer that does `outcome.current_probability = prob` is not an
# upsert, calls neither helper, and is therefore INVISIBLE to a census that asks
# "does this file call `price_changed_at_value`?" — `tasks/futures.py` passed
# that census on the strength of a DIFFERENT, wired, upsert twenty lines away,
# while its `if existing:` branch stamped nothing at all. `tasks/datagolf.py`
# passed by mentioning neither helper anywhere.
#
# So the ORM paths get their own entry points rather than open-coded datetime
# arithmetic at each site, for the reason the module docstring already gives
# about five copies of a predicate: a copy that drifts does not throw, it just
# stops stamping.
#
# ── WHY TWO FUNCTIONS AND NOT ONE WITH A FLAG ────────────────────────────────
#
# `tasks/futures.py`'s stale zeroing writes `current_probability = 0` to
# outcomes ABSENT from the API response for over 24 hours. Zero is a real
# number, so refusal 1's "is it None?" test cannot classify it — and it must not
# be stamped as an observation, because nothing was observed: the venue stopped
# returning the leg and we inferred a price from the silence. Stamping it would
# make an abandoned outcome the freshest row in the table.
#
# A boolean parameter puts that distinction in an argument a caller can get
# wrong by defaulting. Two named functions put it in the verb, where a reviewer
# reads it without looking anything up.


def _stored_price(value: Any) -> Decimal | None:
    """A price as the database would store it, for an honest comparison.

    The SQL helpers cast both sides to `PRICE_NUMERIC` so the question asked is
    "would this write change what is stored?". These do the same in Python,
    because the alternative — comparing a provider float to a stored `Decimal` —
    reports every poll of an unmoved Polymarket midpoint as a movement.
    """
    if value is None:
        return None
    return Decimal(str(value)).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def apply_observed_price(outcome: Any, new_probability: Any, *, observed_at: datetime) -> None:
    """Write a price the VENUE HANDED US to an ORM outcome, with both stamps.

    The ORM-attribute equivalent of pairing :func:`price_changed_at_value` with
    :func:`price_observed_at_value` in a `set_=` clause. Use this wherever a
    poll assigns a real, provider-supplied price to a loaded `FuturesOutcome`.

    🔴 **IT ASSIGNS THE PRICE ITSELF, AND THAT IS THE POINT.** Detecting
    movement means comparing against the value still in the row, so a
    stamp-only helper would be correct only when called BEFORE the assignment
    and silently wrong forever after somebody reordered two adjacent lines. The
    order cannot be got wrong if the caller does not own it.

    Both of :func:`price_observed_at_value`'s live refusals are kept: a ``None``
    price is not an observation (so the stamp is left where it is), and the
    stamp never moves backwards. The `GREATEST` is done with an explicit
    ``None`` check rather than :func:`max`, because `max(None, now)` raises
    where SQL's ``GREATEST`` ignores the NULL — the asymmetry refusal 3's
    docstring calls out.

    :param outcome: a loaded `FuturesOutcome`.
    :param new_probability: the price from the venue. ``None`` means the venue
        had no price; the row is still written, but nothing was observed.
    :param observed_at: the instant the price was READ. Required, and required
        to be timezone-aware: the column is `timestamptz`, and a naive value
        here raises on the `GREATEST` comparison the first time a row already
        carries a stamp — which is to say, not in the test that writes one row.
    """
    _assign_price(outcome, new_probability, observed_at)
    if new_probability is not None:
        previous = outcome.price_observed_at
        outcome.price_observed_at = (
            observed_at if previous is None else max(previous, observed_at)
        )


def apply_unobserved_price(outcome: Any, new_probability: Any, *, at: datetime) -> None:
    """Write a price we INFERRED, to an ORM outcome. Movement stamp only.

    For the two shapes that write a price nobody read: `tasks/futures.py`'s
    stale zeroing (`= 0` for a leg absent from the response for 24h) and
    `tasks/datagolf.py`'s stale nulling (`= None` for a player who dropped out
    of the field). Both are real writes and real movements — the stored number
    becomes a different number, and `price_changed_at` should say so — and
    neither is an observation of anything.

    There is deliberately no `observed_at` parameter. A caller who wants one is
    calling the wrong function.

    :param at: the instant of the write, used only to decide movement. Kept as a
        parameter rather than read from the clock so a test can pin it.
    """
    _assign_price(outcome, new_probability, at)


def _assign_price(outcome: Any, new_probability: Any, at: datetime) -> None:
    """Assign the price, moving `price_changed_at` iff the stored value changes.

    Shared by both entry points because the MOVEMENT rule is identical for an
    observed and an inferred price — it is only the FRESHNESS rule that
    distinguishes them.

    The stamp is the caller's instant, NOT `func.now()`, which is the one place
    these helpers deliberately diverge from their SQL counterparts. Assigning a
    SQL expression to an ORM attribute mixes Core into a unit-of-work flush
    (gotcha #5) and leaves the attribute holding a `Function` object in Python
    afterwards; every caller here already builds an aware `now` for
    `last_updated`, so using it keeps a row's three stamps consistent with each
    other and keeps this function testable without a database — which is what
    the executed coverage CERT-2302 asked for actually needs.
    """
    if _stored_price(outcome.current_probability) != _stored_price(new_probability):
        outcome.price_changed_at = at
    outcome.current_probability = new_probability
