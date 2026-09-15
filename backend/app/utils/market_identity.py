"""Does a market's OWN id agree with the event it is linked to? (#1902, queue 363)

Lifted OUT of ``scripts/census_settlement_contamination.py``, where queue 362
first wrote it, because Alex ruled that the 2,069 date-disagreement outcomes are
**QUARANTINED from published calibration curves as under review until
identity-verified** — and a predicate that lives in a script cannot be consumed
by the payload that publishes the curve.

Lifting rather than copying is deliberate, and it is the standing lesson from two
separate divergences inside one week: the concept-eligibility rule (web behind
iOS, #1924) and the label-pass live derivation (native behind web, #1933). Both
were scoped to the endpoint that happened to carry the bug report rather than to
the class, and both then diverged. **A shared eligibility predicate gets ONE
implementation.** The census script now imports this module; there is no second
copy to drift.

## Why the quarantine keys on the PREDICATE, never on the 2,069

The tempting shortcut is to freeze the reviewed ids and exclude that list. It is
the same mistake the population-2 census refused when it refused RE-KEY: a count
(or a frozen list) is a claim about the world's current state, which the ordinary
pipeline repairs on its own, so it expires while nothing is wrong.

A cruder re-measurement makes the point concretely. A raw ``-YYMONDD`` regex over
``KXMLB%`` tickers returns **more than a thousand** markets, not 165 — because
gotcha #14 is real: many Kalshi tickers carry a CLOSE date, not a game date, and
a regex cannot tell the two apart. :func:`ticker_game_date` returning ``None`` on
anything it cannot read as a game date is what keeps this predicate honest, and
it is why the quarantine must be evaluated, not remembered.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

__all__ = [
    "ticker_game_date",
    "market_identity_disputed",
    "eastern_game_date",
    "market_identity_disputed_sql",
    "market_identity_disputed_from_date_sql",
    "ticker_game_date_sql",
    "QUARANTINE_REASON",
    "QUARANTINE_RULE_TEXT",
    "QUARANTINE_READER_REASON",
]

#: The reason string a quarantined row carries into the payload. Named, because a
#: row dropped without a reason is indistinguishable from a row that was never
#: there — and a calibration page that silently sheds rows is exactly the
#: dishonesty Alex's ruling forbids.
QUARANTINE_REASON = "market_identity_disputed"

#: The method sentence, for the payload's machine-readable note. It does NOT
#: print on the page (notice 34: method belongs in the artifact or a tooltip,
#: never in the page body) — the page prints :data:`QUARANTINE_READER_REASON`.
QUARANTINE_RULE_TEXT = (
    "A market whose own ticker names a game date different from the US-Eastern "
    "game date of the event it is linked to is bound to the wrong game, so the "
    "truth it would be graded against is some other game's. Excluded from every "
    "published curve as under review until identity-verified (#1902, queue 363)."
)

#: What a reader sees. Plain words, no ticker/identity jargon, because the page
#: renders this string verbatim as the row label.
QUARANTINE_READER_REASON = (
    "Markets whose own ID names a different game day than the game they are attached to"
)

_TICKER_DATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    )
}


def ticker_game_date(external_id: str | None) -> date | None:
    """The date the MARKET says it is about, from its own ticker. ``None`` if absent.

    Kalshi game tickers carry ``YYMONDD`` immediately after the series prefix
    (``KXMLBTOTAL-26AUG051940MINKC`` -> 2026-08-05), in US Eastern, and gotcha #14
    says to trust it over ``commence_time`` for game matching — the venue's
    ``commence_time`` is frequently the close time.

    Returning ``None`` for an unparseable ticker is deliberate and load-bearing: a
    market whose identity we cannot read is NOT thereby in agreement with its
    event. It is unknown, and :func:`market_identity_disputed` must not mark it
    certain.
    """
    if not external_id:
        return None
    m = _TICKER_DATE_RE.search(external_id)
    if not m:
        return None
    yy, mon, dd = m.group(1), m.group(2), m.group(3)
    month = _MONTHS.get(mon)
    if month is None:
        return None
    try:
        return date(2000 + int(yy), month, int(dd))
    except ValueError:
        return None


def eastern_game_date(commence_time) -> date | None:
    """The event's game-date in US Eastern, which is the calendar the ticker uses.

    Comparing against the UTC date would manufacture a disagreement for every
    night game — a 19:40 ET first pitch is the NEXT UTC day — and a census that
    cries wolf on most of its population teaches its reader to skip it.
    """
    if isinstance(commence_time, str):
        try:
            commence_time = datetime.fromisoformat(commence_time)
        except ValueError:
            return None
    if not isinstance(commence_time, datetime):
        return None
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    return commence_time.astimezone(ZoneInfo("America/New_York")).date()


def market_identity_disputed(external_id: str | None, commence_time) -> bool:
    """True when the market's OWN id names a different game-date than its event.

    QUEUE 362, and it is the ordering ruling arriving a FOURTH time — market
    identity is identity too.

    The specimen: outcome rows ``217508565``-``217508571`` sit on market
    ``58609021``, whose ticker is ``KXMLBTOTAL-26AUG051940MINKC`` — the **Aug 5**
    MIN@KC game. It is linked to event ``15187509``, which is soundly and
    correctly the **Aug 6** game, and that event stores 8-2, which is the **Aug
    4** game's score. Three games in one grade. Nothing about the EVENT is
    disputed, so the old ``disputed`` check waved it through as "identity
    certain" and the census declared 3 of its rows adjudicable — computing a
    grade for the Aug 5 market from the Aug 6 game's truth.

    A market bound to the wrong game is exactly as un-adjudicable as an event
    wearing the wrong id, and for the same reason: the truth we would pair it
    with is some other game's.
    """
    ticker_date = ticker_game_date(external_id)
    if ticker_date is None or commence_time is None:
        return False
    event_date = eastern_game_date(commence_time)
    if event_date is None:
        return False
    return ticker_date != event_date


# =============================================================================
# The SQL twin (#6275).
#
# Alex's ruling (queue 363 item 4, #1902) is that these outcomes are excluded
# from the PUBLISHED curves — and the published population is assembled entirely
# in SQL, in one CTE chain, over millions of rows. Pulling that population into
# Python to run the predicate row-by-row is not available at that size, so the
# predicate needs a SQL form.
#
# It lives HERE, beside the Python, and not in the calibration task, for exactly
# the reason the lift happened in the first place: a shared eligibility
# predicate gets ONE home. Two forms in one file that a differential test pins
# to each other is one predicate; the same two forms in two files is the drift
# the module docstring was written about.
#
# `tests/test_market_identity_quarantine_q363.py` runs both forms over a shared
# corpus of tickers — including the ones where a naive translation diverges —
# and fails if they ever disagree. The traps that corpus exists for:
#
#   * `to_date('26FEB30','YYMONDD')` does NOT raise in PostgreSQL, it rolls over
#     to March 2. Python's `date(2026, 2, 30)` raises and the predicate returns
#     None. So the day is validated by round-trip, never trusted.
#   * `to_date`'s `YY` maps 70-99 into the 1900s; Python's `2000 + int(yy)` does
#     not. The year is therefore built arithmetically, not parsed.
#   * A three-letter group that is not a month ('-26XYZ05') makes `to_date`
#     RAISE, which would take the whole beat down. `make_date` is strict, so a
#     NULL month number propagates to NULL instead — no error path, and no
#     reliance on CASE short-circuit order.
#   * Python's `re.search` takes the FIRST `-\d\d[A-Z]{3}\d\d`, then validates
#     the month. A SQL regex that enumerated the twelve months would instead
#     SKIP a bad first match and find a later one. The regex below is kept
#     deliberately generic so both forms stop at the same token.
# =============================================================================

#: The generic token pattern, kept byte-identical in intent to ``_TICKER_DATE_RE``:
#: first ``-YYMONDD``-shaped group, month validated afterwards, never inside the
#: pattern. POSIX character classes because PostgreSQL's ``substring(... from ...)``
#: takes a POSIX regex, not a PCRE.
_TICKER_DATE_SQL_RE = "-([0-9]{2}[A-Z]{3}[0-9]{2})"


def ticker_game_date_sql(external_id_expr: str) -> str:
    """SQL for :func:`ticker_game_date`: a ``date`` expression, or ``NULL``.

    ``external_id_expr`` is interpolated as SQL, so it must be a column
    reference or other trusted expression the caller composed — never user
    input. Every caller in the tree passes a literal column name.
    """
    tok = f"substring({external_id_expr} FROM '{_TICKER_DATE_SQL_RE}')"
    month_num = " ".join(
        f"WHEN '{mon}' THEN {num}" for mon, num in _MONTHS.items()
    )
    return f"""(
                    SELECT CASE
                        WHEN tg.cand IS NULL THEN NULL
                        -- Round-trip, because PostgreSQL rolls a bad day over
                        -- (Feb 30 -> Mar 2) where Python raises and returns None.
                        WHEN EXTRACT(DAY FROM tg.cand) = tg.dd
                         AND EXTRACT(MONTH FROM tg.cand) = tg.mm
                        THEN tg.cand
                        ELSE NULL
                    END
                    FROM (
                        SELECT t.mm, t.dd,
                            -- `make_date` is strict, so a non-month (mm IS NULL)
                            -- yields NULL rather than raising. Day arithmetic
                            -- rather than `make_date(y, m, d)` for the same
                            -- reason: d comes from a regex and can be 00 or 45,
                            -- and `make_date` would RAISE on those.
                            (make_date(t.yy, t.mm, 1)
                                + make_interval(days => t.dd - 1))::date AS cand
                        FROM (
                            SELECT
                                2000 + substring(tg0.tok FROM 1 FOR 2)::int AS yy,
                                CASE substring(tg0.tok FROM 3 FOR 3)
                                    {month_num}
                                    ELSE NULL
                                END AS mm,
                                substring(tg0.tok FROM 6 FOR 2)::int AS dd
                            FROM (SELECT {tok} AS tok) tg0
                        ) t
                    ) tg
                )"""


def market_identity_disputed_from_date_sql(
    ticker_date_expr: str, commence_time_expr: str
) -> str:
    """The disagreement test, over an ALREADY-DERIVED ticker date.

    This is the form the calibration population uses, and the reason it exists
    is cost, measured rather than assumed. :func:`ticker_game_date_sql` is a
    four-deep scalar subquery; spelling the predicate as
    ``ticker_game_date_sql(...) IS NOT NULL AND ticker_game_date_sql(...) <> ...``
    makes PostgreSQL derive the date TWICE per row, and that form timed out at
    10 s against the resolved-market population (correlation 315c2af809de). The
    population derives the date once, as a ``market_info`` column, and this
    predicate is then two comparisons.

    The comparison RULE still lives in one place — :func:`market_identity_disputed_sql`
    is written in terms of this function, so the convenience form and the
    pipeline form cannot drift apart into two different notions of "disputed".
    """
    return f"""(
                {ticker_date_expr} IS NOT NULL
                AND {commence_time_expr} IS NOT NULL
                AND {ticker_date_expr}
                    <> ({commence_time_expr} AT TIME ZONE 'America/New_York')::date
            )"""


def market_identity_disputed_sql(
    external_id_expr: str, commence_time_expr: str
) -> str:
    """SQL for :func:`market_identity_disputed`: a boolean expression.

    Mirrors the Python's refusals exactly. An unreadable ticker and a missing
    ``commence_time`` are both ``false`` — NOT disputed — because a market whose
    identity we cannot read is unknown, not in disagreement, and quarantining
    the unknown would shrink the curve on a guess.

    ``commence_time`` is ``timestamptz``, so ``AT TIME ZONE`` converts it to the
    US-Eastern wall clock the ticker is written in. Comparing UTC dates would
    manufacture a dispute for every night game (:func:`eastern_game_date`).

    Self-contained, so it costs two derivations per row. Fine for a test corpus
    or an ad-hoc read; the published population uses
    :func:`market_identity_disputed_from_date_sql` over a derived column.
    """
    return market_identity_disputed_from_date_sql(
        ticker_game_date_sql(external_id_expr), commence_time_expr
    )


#: The three CTE names the quarantine block defines. Named as a constant so the
#: calibration chain and the tests agree on them without either hard-coding a
#: string the other could rename out from under it.
IDENTITY_TOKEN_CTE = "identity_ticker_token"
IDENTITY_PARSED_CTE = "identity_ticker_parsed"
IDENTITY_DISPUTED_CTE = "identity_disputed_markets"


def identity_quarantine_ctes(
    *,
    source_relation: str,
    commence_time_col: str,
    market_id_col: str = "market_id",
    external_id_col: str = "external_id",
) -> str:
    """The quarantine as a FLAT CTE chain: the form the published curve uses.

    Returns three comma-separated CTE definitions (no leading ``WITH``, no
    trailing comma), the last of which — :data:`IDENTITY_DISPUTED_CTE` — is one
    row per market whose own ticker disagrees with its event's game date.

    🔴 ``commence_time_col`` IS REQUIRED, AND IT USED TO CARRY THE DEFAULT
    ``"commence_time"`` (#6275, CERT-2902). That default is the whole defect and
    it is an instance of a class worth naming: a default that is a REAL,
    resolvable value stores a plausible wrong answer instead of raising. The one
    caller that decides the published curve renders over ``market_info``, which
    has a column literally called ``commence_time`` — the MARKET's own copy of
    the start time — so the default bound cleanly, the SQL was valid, every test
    was green, and the predicate compared the ticker's date against a date
    COPIED FROM THAT SAME TICKER. On the specimen the ruling is written about
    (market 58609021, linked to event 15187509) both are Aug 5 Eastern while the
    linked EVENT is Aug 6, so the row the quarantine exists to hold was the one
    row it declared clean.

    The date this predicate means is always the LINKED EVENT's. There is no
    caller for which the market's own copy is the right operand, so there is no
    default that is safe to have.

    WHY A CHAIN AND NOT THE ONE-LINE EXPRESSION. :func:`ticker_game_date_sql` is
    a three-deep scalar subquery, and PostgreSQL does not flatten it: over the
    309,964 resolved Kalshi markets a bare ``COUNT(*)`` runs in 2.7 s, the regex
    alone in 4.6 s, and the scalar-subquery predicate did not finish inside the
    endpoint's ceiling (correlations 69ad04cb7e87, 5aded3bb158e). Split into
    three plain projections the planner flattens them into one pass, and the
    cost is the regex and nothing else.

    The two forms are the SAME predicate — the differential test runs this chain
    and :func:`market_identity_disputed` over one corpus and fails on any
    disagreement — so the expression form stays available for tests and ad-hoc
    reads without the population paying for it.
    """
    month_num = " ".join(f"WHEN '{mon}' THEN {num}" for mon, num in _MONTHS.items())
    return f"""{IDENTITY_TOKEN_CTE} AS (
                -- Step 1: the date token the market carries in its own id, if it
                -- has one. The regex
                -- is deliberately GENERIC (not month-enumerated) so it stops at
                -- the same token the Python re.search stops at. A pattern that
                -- listed the twelve months would skip an invalid first match and
                -- find a later one, and the two forms would then disagree on a
                -- ticker like -26ZZZ05-26AUG05.
                --
                -- NO SEMICOLONS IN THESE COMMENTS. The admin db-query guard
                -- splits statements without understanding SQL comments, so a
                -- semicolon inside a -- comment makes every ad-hoc read of this
                -- chain fail as "Multi-statement queries not allowed" -- which
                -- reads as a broken query rather than as a punctuation mark.
                -- Postgres itself does not care. The probe path does.
                SELECT src.{market_id_col} AS market_id,
                    src.{commence_time_col} AS commence_time,
                    substring(src.{external_id_col} FROM '{_TICKER_DATE_SQL_RE}') AS tok
                FROM {source_relation} src
            ),
            {IDENTITY_PARSED_CTE} AS (
                -- Step 2: the parts of that token, and the candidate date.
                --
                -- The year is arithmetic, not parsed: to_date maps a YY of 70-99
                -- into the 1900s, and 2000 + int(yy) in the Python does not.
                --
                -- `make_date` is STRICT, so a three-letter group that is not a
                -- month yields NULL rather than raising -- which `to_date`
                -- would do, taking the whole beat down on one odd ticker. The
                -- day is added as an interval for the same reason: it comes
                -- from a regex and can be 00 or 45, and `make_date(y, m, 45)`
                -- raises.
                SELECT t.market_id, t.commence_time, p.mm, p.dd,
                    (make_date(p.yy, p.mm, 1) + make_interval(days => p.dd - 1))::date
                        AS cand
                FROM {IDENTITY_TOKEN_CTE} t
                CROSS JOIN LATERAL (
                    SELECT 2000 + substring(t.tok FROM 1 FOR 2)::int AS yy,
                        CASE substring(t.tok FROM 3 FOR 3)
                            {month_num}
                            ELSE NULL
                        END AS mm,
                        substring(t.tok FROM 6 FOR 2)::int AS dd
                ) p
                WHERE t.tok IS NOT NULL
            ),
            {IDENTITY_DISPUTED_CTE} AS (
                -- Step 3: the disagreement. The round-trip check is what rejects
                -- a rolled-over date (PostgreSQL turns Feb 30 into Mar 2 where
                -- the Python raises and returns None), so an unreadable date
                -- stays UNKNOWN
                -- and is not quarantined -- refusing the unknown would shrink
                -- the curve on a guess.
                SELECT p.market_id
                FROM {IDENTITY_PARSED_CTE} p
                WHERE p.cand IS NOT NULL
                  AND EXTRACT(DAY FROM p.cand) = p.dd
                  AND EXTRACT(MONTH FROM p.cand) = p.mm
                  AND p.commence_time IS NOT NULL
                  AND p.cand
                      <> (p.commence_time AT TIME ZONE 'America/New_York')::date
            )"""
