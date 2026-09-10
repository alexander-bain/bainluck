"""#4794 — a finished game that can show a reader nothing is not a search result.

THE SHIP: searching a club stops returning cards that are two team names and the
words "No result reported". `/search?q=Galatasaray` at 390px returns 16 game
cards and **10 of them render nothing at all** — no date, no score, no
percentage. Six are real. The reader has to pick them out.

## The discriminator is in the payload, not in a judgement

Read from `GET /api/events/search?q=Galatasaray&limit=60` on production
2026-09-10 13:35Z, all 16 rows:

    the 6 that render     4 carry a score; every one of the 6 carries a
                          `betting` or `kalshi` entry in win_probability_sources
    the 10 that are blank none carries a score; 8 carry `{}` — an EMPTY bag —
                          and 2 carry `polymarket` alone

So a blank card is exactly a row with **no score and no probability reading**.
There is no threshold here and nothing to tune: the card is empty because the
fields behind it are empty. :func:`has_nothing_to_render` is that sentence and
nothing more.

## Why all four conditions, and why each one alone would be a bug

Each of the four is a legitimate row on its own, and dropping any condition from
the AND turns this predicate into a defect:

* **no `commence_time` bound** — an UPCOMING fixture has no score and often no
  odds yet, and is precisely what a reader searching a club wants. Suppressing
  it would empty the front door instead of cleaning it.
* **no status bound** — a game IN PROGRESS has no final score. The margin below
  is belt-and-braces beside the status test, because a row can carry a terminal
  status while its scoreboard is still settling.
* **no `home_score IS NULL` test** — a finished game with a score renders, and
  is the thing the page is for.
* **no probability test** — a past game with pre-match odds and no score still
  shows percentages and a "Pre-match · sportsbooks" line. It is not blank, and
  this predicate must not reach it. In practice this is the condition that
  carries most of the safety: a real fixture we tracked has pre-match odds, so
  it survives even when its score never backfilled.

## Suppressing these loses no information

The obvious objection is that the blank rows hold markets — measured on that
page, `15296921` holds 17, `15307090` and `15301449` hold 7 each. They do, and
the card does not render one of them. The search payload carries `futures`
alongside `results`, and those markets already surface there: the same response
lists `Trabzonspor vs. Galatasaray SK - More Markets`,
`Sporting CP vs Galatasaray: Second Half BTTS` and seven more. So the market
book is reachable with the blank card gone.

## 🔴 THIS IS NOT THE TWIN FOLD AND MUST NOT BE CITED AS ONE

The reason those rows are empty is that they are twins — one fixture carried
twice with the substance split down the middle. Measured on the same page:

    15291198 Galatasaray v Goztepe    3-2, 351 odds snapshots,  0 markets
    15297991 Galatasaray v Goztepe Izmir     no score,          1 market
    15200416 Erzurum BB v Galatasaray  0-4, 228 odds snapshots,  0 markets
    15192001 Erzurumspor FK v Galatasaray SK no score,          3 markets

Folding those is #2693, and under D35 it is filed, not fixed. This predicate
makes the front door readable while that lands. It is a SERVING rule about
whether a card has anything to say: it merges nothing, deletes nothing, and
asserts nothing about whether two rows are one game.

The sibling predicate in ``proven_duplicates.py`` is the one that speaks about
identity, and the division is deliberate — that one declines to print a row the
REGISTRY has proved is a second copy; this one declines to print a row that is
EMPTY, whoever else it may or may not duplicate. A row can be either, both or
neither, and neither predicate needs to know what the other decided.

## Null-safety, stated precisely rather than dramatically

``win_probability_sources`` is nullable and on production it is USUALLY null:
measured 2026-09-10 over the past-terminal-no-score population, **61,730 rows
carry SQL NULL, 1,094 carry ``{}`` and 0 carry JSON ``null``**. So the ``IS
NULL`` arm is not a hypothetical.

What it actually buys is worth being exact about, because the obvious claim —
"without it the endpoint empties" — is FALSE here and a reader who checks would
rightly stop trusting the rest of this file. ``not_a_blank_card`` is a ``NOT``
over an ``AND``, and a NULL in the last arm only propagates when the other three
are TRUE; that is precisely the fully-blank row, which ``NOT NULL`` → NULL →
"not selected" excludes anyway. **The suppression behaves identically with the
arm removed.** Verified by mutation, not by reasoning alone.

The arm earns its place on the OTHER export. ``has_nothing_to_render`` is used
positively — the partition test selects with it directly, and any future caller
that wants to COUNT or repair these rows will too — and there a NULL bag makes
the predicate return NULL and silently omit 61,730 of the 62,824 rows it is
supposed to name. That is the failure mode: not an empty page, a
quietly-98%-short census.

So every arm is two-valued by construction and the reason is symmetry between
the two exports:

* ``commence_time`` and ``status`` are ``NOT NULL`` in the model;
* ``home_score IS NULL`` is a null test, so it is always TRUE or FALSE;
* ``win_probability_sources`` leads with ``IS NULL`` so the cast is only ever
  evaluated on a non-null value.

🔴 A note for anyone writing a test against this: ``win_probability_sources=None``
through the ORM does **not** produce a SQL NULL. SQLAlchemy's JSON type
serialises Python ``None`` to the JSON text ``'null'``, so a fixture built the
obvious way exercises the 0-row shape and leaves the ``IS NULL`` arm untested —
a mutation deleting it passes the whole suite. ``test_blank_event_cards_4794``
forces the real shape with a ``text()`` UPDATE and asserts ``typeof()`` to prove
it did.

## The bag is tested for EMPTINESS, never for meaning

``win_probability_sources`` is a shared JSONB bag: besides readings it can carry
``statpal_plays``/``statpal_injuries`` arrays and ``_``-prefixed metadata, and a
key may be present holding JSON ``null`` (``merge_probability_sources`` exists
because of exactly that). So a row whose bag holds only metadata renders blank
and is NOT suppressed here.

That is deliberate and it is the safe direction: this predicate UNDER-reaches
rather than deciding, in SQL, which JSON keys count as a reading. Deciding that
is :func:`app.utils.aggregation.parse_source_entry`'s job, it is per-key, and
pulling it into a WHERE clause would put a second, dumber copy of the
aggregation rules in the query planner's hands. An under-reach costs one
uncleaned card; an over-reach hides a real game.

Measured cost of the under-reach on the specimen page: 8 of the 10 blank cards
are suppressed. The remaining 2 carry ``polymarket`` alone and render no
percentage anyway — a separate defect (a reading that exists and does not draw),
recorded on #4794 and not addressed here.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import String, and_, func, not_, or_

from app.models.models import Event
from app.utils.event_completion import EVENT_SUSPENDED

#: Statuses meaning "this game is not going to start again". `suspended` is in
#: the set for the reason `_SEARCH_STARTED_STATUSES` puts it there — the one
#: thing nothing disputes about a suspended match is that it has started — and
#: because it is the disposition the #4242 re-date leaves behind, which is what
#: six of the ten specimen rows wear.
#:
#: Imported, never re-typed: a string literal here would drift from live/048's
#: settled vocabulary silently.
TERMINAL_STATUSES = ("completed", "closed", EVENT_SUSPENDED)

#: How far past kickoff a row must be before "no score" is allowed to mean
#: "there will never be a score" rather than "it is still being played".
#:
#: Six hours covers the longest fixture this product carries plus a settling
#: margin (a five-set match, an extra-innings baseball game, a rain delay). It
#: is a SECOND line of defence and not the primary one — `TERMINAL_STATUSES`
#: already excludes a `live` or `scheduled` row — so it is deliberately generous
#: rather than tuned. Widening it only ever leaves more cards on the page.
FINISHED_MARGIN = timedelta(hours=6)

#: `win_probability_sources` rendered as text when it holds no readings at all.
#: `{}` is what Postgres' `jsonb::text` produces for the empty object, and
#: `null` is the JSON null a column can hold distinctly from SQL NULL.
#:
#: Measured on production 2026-09-10 over the past-terminal-no-score population:
#: 1,094 rows carry `{}` and 0 carry `null` (against 61,730 SQL NULL, which the
#: `IS NULL` arm handles). `null` is kept because SQLAlchemy's JSON type writes
#: Python `None` in exactly that form — so the 0 is a fact about how these
#: particular rows were written, not a guarantee about the next writer.
_EMPTY_SOURCE_BAGS = ("{}", "null")


def _has_no_probability_sources():
    """The bag is absent or empty. Null-safe: the ``IS NULL`` arm leads.

    Cast-and-compare rather than a JSONB operator, for the reason
    ``proven_duplicates`` gives one column over: the guard suite executes
    against SQLite, and a Postgres-only operator here would take these tests off
    it. Emptiness is a whole-value test — unlike containment it needs no index
    to be cheap, because it is only ever evaluated on rows the recall arms have
    already returned.
    """
    return or_(
        Event.win_probability_sources.is_(None),
        func.cast(Event.win_probability_sources, String).in_(_EMPTY_SOURCE_BAGS),
    )


def has_nothing_to_render(now):
    """TRUE for a row whose card would be two team names and nothing else.

    A finished game, with no score, and no probability reading. All four
    conditions together — see the module docstring for why each one alone would
    be a bug.

    ``now`` is passed in rather than read from the clock so that a caller's
    whole request is evaluated against ONE instant, and so the guard suite can
    fix it (gotcha #44: a test anchor that branches on the clock is not an
    anchor).
    """
    return and_(
        Event.commence_time < now - FINISHED_MARGIN,
        Event.status.in_(TERMINAL_STATUSES),
        Event.home_score.is_(None),
        _has_no_probability_sources(),
    )


def not_a_blank_card(now):
    """A predicate admitting every row EXCEPT the ones that can render nothing.

    Use it in any surface that prints one card per game. It is a plain ``WHERE``
    clause, so it composes with whatever the surface already filters on and
    costs no join.

    Like :func:`app.utils.proven_duplicates.not_a_proven_duplicate` this is
    SCOPE and not recall: it can only ever REMOVE a row the recall arms already
    reached, never add one. And it is a function rather than an expression
    pasted into call sites for the null-safety reason in the module docstring —
    every arm of the inner ``AND`` is two-valued, which is what makes this
    ``NOT`` safe, and that property is easy to break by editing a copy.
    """
    return not_(has_nothing_to_render(now))
