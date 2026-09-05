"""The Kalshi resolution-window sweep — the repair, in the app, on a beat.

CAL-P998 / D47. Moved verbatim out of
``backend/scripts/backfill_kalshi_resolution_window.py``; that script is now the
attended CLI over this module and restates nothing. The move is what makes the
last open line of #2771 buildable:

    > **The sweep is scheduled, not attended.** The population refills daily; a
    > one-off cannot hold it. That half is NOT in this branch.

A Celery task cannot import from ``scripts/`` — it is not on the dyno's path —
so as long as the repair lived there the only way to run it was for a human to
run it, and the measurement says nobody did: 5,143 sealed rows on 2026-09-03
05:00Z, **5,137** at 22:0xZ the same day. The population is not draining, and
every one of those rows renders a dead last-trade price as a live probability
the moment the venue finalizes it (gotcha #33, #2660's card).

WHAT THE SWEEP IS FOR, in one sentence: settled-at-the-venue is a fact
regardless of what date we are holding, and the row we hold must converge onto
the venue's ``close_time`` rather than sit forever on its legal backstop.

Everything about the predicate, the ordering, the retention floor and the
zero-yield discipline is documented at its definition below and was ratified by
CERT-766 / CAL-P992 — none of it is re-argued here, because none of it changed
in this move. What is NEW in this module is only :func:`run_sweep`: the bound,
unattended entry point the beat calls, and the terminal truth it returns.

CAL-P1019 / #2722 — THE SWEEP NOW READS THE VENUE'S STATUS, NOT ONLY ITS DATES.
Every candidate's event is already fetched with its nested markets, and every
leg of that payload carries the venue's own ``status``. It was being discarded.
That is the only signal that reaches the 20% of the settled cohort Kalshi
finalises EARLY — measured at the venue 2026-09-02, 10 of 49 sampled settled
markets still hold a FUTURE ``close_time``, so no date field and no date
predicate can ever select them, and the row goes on claiming to be open. The
write is at :data:`UPDATE_SQL`: ``status`` and ``settled_at``, on the venue's
word only, and never a grade (#1852's line is unchanged).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import text

# `KalshiAPIService` — NOT `KalshiAPIClient`, which has never existed in
# `app.services.kalshi_api`. CERT-766 caught the wrong name as an ImportError
# raised before argparse ran, so the script could not select a row, let alone
# write one, and the catch-up this whole ship depends on was a no-op.
from app.services.kalshi_api import KalshiAPIService
from app.utils.kalshi_resolution_window import (
    derive_resolution_window,
    derive_venue_settlement,
)
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

# The band's calendar. Reused rather than restated: this is the SAME Eastern
# reading the ticker parser uses, so the day the band asks for and the day the
# ticker names cannot drift apart into a second implementation.
from app.utils.market_identity import eastern_game_date

#: What ONE unattended beat run may touch.
#:
#: 500 is the limit every attended run of this repair has used (CAL-P989's
#: catch-up, CAL-P992's re-runs), so the beat inherits a batch size whose venue
#: cost and wall time are already observed rather than picking a fresh one on
#: the day it becomes unattended. At 500/day against the 6,302 rows eligible on
#: 2026-09-03 the population is reached in ~13 runs — and because the ordering
#: is `updated_at ASC` and every write refreshes that stamp, the sweep rotates
#: rather than re-reading the same head (the starvation CAL-P992 measured).
SWEEP_BATCH_LIMIT = 500

#: Concurrent venue reads. Matches the attended default; Kalshi's rate limit has
#: never been the binding constraint at this width and a beat is not the place
#: to find out where it is.
SWEEP_CONCURRENCY = 6

#: How far back the played-game band reaches, in days — #3284 / CAL-P1016.
#:
#: It is `PROVABLY_PURGED_AGE_DAYS`, READ and not retuned (the same discipline
#: #3257 kept on the sibling drain). The band exists to rank rows the venue can
#: still answer for, and beyond this age the venue answers for nothing, so a
#: wider band would only promote rows that cannot be written. It is deliberately
#: the same constant the purge floor already uses rather than a second number
#: that could drift away from it.
PAST_EVENT_BAND_DAYS = PROVABLY_PURGED_AGE_DAYS

@dataclass
class _Leg:
    close_time: Optional[datetime]
    expiration_time: Optional[datetime]


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


#: A row is a candidate while the date we hold for it is still PROVISIONAL, i.e.
#: while the venue has not yet told us when trading actually stopped.
#:
#: `expiration_time IS NULL` alone — the original marker — is "have I ever touched
#: this row", and CAL-P992 measured what that costs. Kalshi sets `close_time` equal
#: to the backstop while a market is ACTIVE and rewrites it to the settlement
#: instant on finalize. So a row swept while its market was still trading is written
#: with `resolution_date == expiration_time`, which stamps the backstop column and
#: makes the row permanently unselectable — and then the market finalizes and the
#: open-market poll can never re-enumerate it (gotcha #33). The row keeps a future
#: date forever and no run of this script can reach it. Measured on production
#: 2026-09-02: 5,143 `status='open'` rows already sealed this way, five of them
#: (US Open `KXWTASETWINNER` / `KXATPEXACTMATCH` legs) finalized at the venue within
#: an hour of the sweep that sealed them.
#:
#: `resolution_date >= expiration_time` is the provisional test and it is a
#: PROVENANCE read, not a proxy: it is true exactly while `resolution_date` is still
#: a backstop. Once the venue rewrites `close_time`, `resolution_date` moves strictly
#: earlier, the row converges out, and it stays out — the same convergence the old
#: marker gave, keyed on the fact that makes the row done rather than on the fact
#: that we looked at it.
#:
#: `LIKE 'KX%'` rather than `~ '^KX'`: identical semantics for a left-anchored
#: literal prefix, sargable, and executable by the guard in
#: `tests/test_kalshi_resolution_backfill_script_989.py`, which runs this exact
#: string against a seeded table. A regex operator would have made the starvation
#: guard un-runnable, and an un-runnable guard is how the post-LIMIT floor shipped
#: in the first place. (It also excludes 211 legacy non-`KX` rows — all measured as
#: genuinely-future 2027-2032 political/macro markets, so not a dead-card source
#: today; named in #2773 rather than widened here.)
#:
#: ORDERING — `updated_at ASC`, NOT `market_tier ASC`. Tier-first is what the
#: original backlog wanted, but on the provisional population it starves: measured
#: 2026-09-02, tier 1+2 hold 2,951 provisional rows and tier 5 holds 2,038, so a
#: `--limit 500` run ordered by tier never reaches tier 5 at all — and tier 5 is
#: where the settled prop legs live. `updated_at ASC` is not a tie-break dressed up:
#: on a `status='open'` Kalshi row the 2h poller bumps `updated_at` only while the
#: venue still enumerates the market as open, so the moment Kalshi finalizes it the
#: stamp FREEZES (gotcha #33 read forwards). Least-recently-enumerated first is
#: therefore a direct observation of "most likely already settled", and it rotates,
#: so no row can be starved behind a prefix. `commence_time` cannot do this job:
#: 4,954 of the 5,143 sealed rows carry `commence_time = expiration_time`, the same
#: poisoned backstop, so a "has it commenced" gate would have missed all five of the
#: rows that motivated this change.
SELECT_SQL = """
    SELECT id, external_id, resolution_date, commence_time, market_tier
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND (expiration_time IS NULL
           OR resolution_date IS NULL
           OR resolution_date >= expiration_time)
      AND (commence_time IS NULL OR commence_time >= :purge_floor)
    ORDER BY updated_at ASC NULLS FIRST,
             market_tier ASC NULLS LAST,
             commence_time DESC NULLS LAST
    LIMIT :limit OFFSET :offset
"""

# ---------------------------------------------------------------------------
# The played-game band — #3284 / CAL-P1016
# ---------------------------------------------------------------------------
#
# WHAT THE BEAT'S FIRST UNATTENDED RUN MEASURED (2026-09-05 04:20Z, production,
# `task-metrics?task=kalshi_resolution_window`): 500 candidates, 125 written,
# 121 of those `unchanged` because the venue still reports the backstop, and
# **`newly_past = 4`**. Five hundred venue reads bought four corrected dead
# prices. At a 500-row batch against ~7,000 eligible rows the cycle is ~14
# nights, so a market that finalises just after its slot keeps a live-looking
# price and a fabricated future date for up to a fortnight. That is #2660's card
# ("a golf round that settled five days ago") as a standing mechanism.
#
# WHY `updated_at ASC` ALONE CANNOT FIND THEM. CAL-P992 chose that ordering on
# the argument that the 2h open-market poll bumps `updated_at` only while the
# venue still lists a market, so a frozen stamp detects finalisation. Measured
# 2026-09-05: of 8,879 `status='open'` KX rows only 237 were touched in the last
# 3 hours and 1,428 in the last 26 — the poller's COVERAGE, not the venue's
# listing, dominates the stamp. Four rows sampled from the stale band and
# checked against Kalshi's own API were two genuinely active (2027 midterms,
# Hannover mayor) and two finalised days ago. The stamp does not separate them.
#
# THE SIGNAL THAT DOES is already in the row and gotcha #14 already prefers it
# over `commence_time`: the ticker's own `YYMONDD` segment
# (`app/utils/market_identity.py:ticker_game_date`). `commence_time` cannot do
# this job — 4,954 of the 5,143 sealed rows carry `commence_time` equal to the
# same poisoned backstop (#2771).
#
# MEASURED YIELD, at the venue (12 rows sampled from the band, Kalshi public
# API, 2026-09-05): **8 finalised with a `close_time` months earlier than the
# date we store** — they converge on read — 3 purged/no markets (#2723's
# stranded cohort), 1 genuinely active. ~67% against the beat's measured 0.8%.
#
# IT IS AN ORDER, NEVER A PREDICATE, and the 12th sample is why: `KXMYSLGAME-
# 26SEP04BRUJOH` is a season market whose ticker date is its opener, so a FILTER
# on the band would wrongly promote-and-exclude it while a SORT merely
# mis-orders it. :func:`banded_select_sql` therefore reuses `SELECT_SQL`'s own
# text and rewrites only its ORDER BY — `test_the_band_changes_only_the_order`
# proves the predicate is byte-identical rather than asserting it in prose.
#
# PORTABLE ON PURPOSE. The band is a bounded list of literal day tokens built in
# Python, matched with plain `LIKE`, because the guards for this SQL execute it
# against SQLite and Postgres has no shared regex/`strpos` spelling with it. The
# bound is what makes the list finite: only days the venue can still answer for
# are worth ranking, so the token list is at most `PAST_EVENT_BAND_DAYS` long.

_BAND_MONTHS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)


def past_event_band_tokens(
    now: datetime, *, days: int = PAST_EVENT_BAND_DAYS
) -> list[str]:
    """`LIKE` patterns for every ticker day-stamp whose game has been played.

    Strictly BEFORE today and no older than ``days``. Strictly-before matches
    the measured cohort (604 rows on 2026-09-05) and keeps a game that is being
    played right now out of the band, where it would only spend a venue read to
    be told the backstop again.

    TODAY IS THE VENUE'S DAY, NOT UTC's — #3293 / CAL-P1017, CERT-1939's named
    follow-up, and it is not cosmetic. The ticker's ``YYMONDD`` is a US Eastern
    trading day
    (:func:`app.utils.market_identity.ticker_game_date`), while the beat fires at
    04:20Z. Under EDT that instant is 00:20 ET on the SAME calendar day and the
    two readings agree, which is why the 2026-09-05 measurement could not see
    this. Under EST it is 23:20 ET on the day BEFORE, so a UTC reading of
    "strictly before today" admits the Eastern day still in progress. Measured on
    production 2026-09-05, that day is the *largest* cohort in the whole band —
    785 eligible rows on `26SEP05` against 212 on the finished `26SEP04` — so at
    rank 0 it would fill the entire 500-row batch with games that have not
    finished, and the batch would never reach a played day at all. The band
    would invert into the starvation it was built to end, on 2026-11-01, with no
    code change to blame.

    ``purge_floor`` deliberately stays on the UTC clock: it is an age in absolute
    time, not a position in the venue's calendar.

    Newest first, so the caller can also read the list as the order in which the
    band's days became answerable.
    """
    today = eastern_game_date(now)
    if today is None:
        raise TypeError(
            "past_event_band_tokens needs a datetime to read the venue's day; "
            f"got {type(now).__name__}"
        )
    tokens: list[str] = []
    for back in range(1, max(0, int(days)) + 1):
        d = today - timedelta(days=back)
        tokens.append(f"%-{d.year % 100:02d}{_BAND_MONTHS[d.month - 1]}{d.day:02d}%")
    return tokens


def band_bind_params(tokens: list[str]) -> dict:
    """``{'band_0': '%-26SEP04%', ...}`` — one bind per token, never interpolated.

    The tokens are machine-built from a clock and could not carry an injection
    today, but a SQL string that concatenates values is a habit that outlives
    the day its inputs were safe.
    """
    return {f"band_{i}": tok for i, tok in enumerate(tokens)}


def band_rank_sql(n_tokens: int) -> str:
    """The leading sort key: DAYS SINCE THE GAME, and ``n_tokens`` for the rest.

    Graded rather than binary, and the grading is not a refinement — it is what
    makes the band's head answerable. Measured on production 2026-09-05: under a
    binary rank the band's first 14 rows probed at the venue as 4 convergeable,
    3 still active and **7 purged**, because the inherited `updated_at ASC`
    tie-break sorts the oldest — hence deadest — stamps to the front of the
    band. A random sample from the same band was 8 convergeable of 12. The
    difference is entirely the within-band order.

    :func:`past_event_band_tokens` yields newest-first, so the token's own index
    IS its age in days and one `CASE` expresses both facts. Non-band rows take
    ``n_tokens`` — strictly larger than every band rank, so they follow the
    whole band and their inherited ordering is untouched among themselves.

    ``n_tokens == 0`` yields ``NULL``, not ``0``: an empty band must leave the
    inherited ordering exactly as it was, a `CASE` with no arms is not valid
    SQL, and a bare integer in an ORDER BY is an ORDINAL COLUMN REFERENCE in
    both SQLite and Postgres — `ORDER BY 0` is "term out of range", which is how
    the zero case would have failed in production rather than in a guard.
    """
    if n_tokens <= 0:
        return "NULL"
    arms = " ".join(
        f"WHEN external_id LIKE :band_{i} THEN {i}" for i in range(n_tokens)
    )
    return f"CASE {arms} ELSE {n_tokens} END"


def banded_select_sql(n_tokens: int) -> str:
    """`SELECT_SQL` with the band rank prefixed onto its ORDER BY, nothing else.

    Built by surgery on `SELECT_SQL` itself rather than by restating it, so the
    two cannot drift: if the predicate changes, this changes with it, and if
    this ever stops being a pure re-ordering the guard that compares the two
    heads fails.
    """
    head, sep, tail = SELECT_SQL.partition("ORDER BY")
    if not sep:  # pragma: no cover — a SELECT_SQL with no ORDER BY is a bug
        raise ValueError("SELECT_SQL has no ORDER BY to prefix")
    return f"{head}ORDER BY {band_rank_sql(n_tokens)},\n             {tail.lstrip()}"


def row_is_in_band(external_id: Optional[str], tokens: list[str]) -> bool:
    """The Python reading of the same membership, for the run's own report.

    The batch's band count is computed here rather than by a second query: one
    selection, one answer. The tokens carry `LIKE`'s ``%`` wildcards, so strip
    them to get the literal the ticker must contain.
    """
    if not external_id:
        return False
    return any(tok.strip("%") in external_id for tok in tokens)


#: What the batch does NOT cover. Reported every run so a bounded sweep can never
#: read as a complete one. `never_swept` / `provisional_recheck` split the eligible
#: population by which of the two selection reasons put the row there, because they
#: behave differently: the never-swept tail can only shrink (the poller writes
#: `expiration_time` on every upsert), while the provisional set refills every time
#: a market is swept before it settles.
COUNT_SQL = """
    SELECT
        count(*) AS eligible_total,
        count(*) FILTER (
            WHERE commence_time IS NOT NULL AND commence_time < :purge_floor
        ) AS excluded_purged,
        count(*) FILTER (WHERE expiration_time IS NULL) AS never_swept,
        count(*) FILTER (
            WHERE expiration_time IS NOT NULL
              AND (resolution_date IS NULL OR resolution_date >= expiration_time)
        ) AS provisional_recheck
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND (expiration_time IS NULL
           OR resolution_date IS NULL
           OR resolution_date >= expiration_time)
"""

#: `updated_at` is BOUND, not `now()`: the two date columns and the stamp then come
#: from one instant the caller controls, so the guard can assert on the exact
#: parameters that reach the driver instead of on a value the database invents.
#:
#: THE STATUS HALF — CAL-P1019 / #2722. Until this change the only way a Kalshi row
#: could stop claiming to be open was a DATE predicate going past
#: (`status <> 'resolved' AND resolution_date < now()`, #1818's repair). Measured at
#: the venue 2026-09-02: of 49 sampled markets Kalshi had already settled, **10 (20%)
#: still carry a future `close_time`** because they finalised EARLY, so no date field
#: reaches them — ever. Meanwhile this sweep was reading `status` off every leg of
#: every candidate and throwing it away.
#:
#: So the write is conditional on the VENUE's own word (`derive_venue_settlement`),
#: never on a clock: `venue_settled` is true only when the event has legs and every
#: one of them is `settled`/`finalized`. `ELSE status` — not a plain assignment —
#: because this statement also runs for the rows the venue still lists as open, and
#: those must come out of it byte-identical.
#:
#: IT WRITES `status` AND `settled_at`, AND NOTHING THAT IS A GRADE. #1852's line is
#: unchanged and #2722 restates it: `is_winner`, prices and probabilities are a
#: different defect with a different rail, and moving a date and a grade in one pass
#: is how #1852 happened. `test_the_update_never_writes_a_grade` holds that boundary
#: against the statement text.
#:
#: The two dates became COALESCE for one reason: a settled row the venue gives no
#: derivable date for must still be able to stop looking open. Its write arrives with
#: `resolution_date = None`, and a plain assignment would blank a date we already
#: hold in order to record a status. For every row that HAS a derived date the two
#: spellings are identical, so no existing behaviour moves.
UPDATE_SQL = """
    UPDATE futures_markets
    SET resolution_date = COALESCE(:resolution_date, resolution_date),
        expiration_time = COALESCE(:expiration_time, expiration_time),
        status = CASE WHEN :venue_settled THEN 'resolved' ELSE status END,
        settled_at = CASE WHEN :venue_settled
                          THEN COALESCE(settled_at, :updated_at)
                          ELSE settled_at END,
        updated_at = :updated_at
    WHERE id = :id
"""


async def run_backfill(
    *,
    session_maker: Callable,
    client_factory: Callable[[], object],
    limit: int = 200,
    offset: int = 0,
    apply: bool = False,
    concurrency: int = 6,
    now: Optional[datetime] = None,
) -> dict:
    """Select, derive and (optionally) write. Every dependency is a parameter.

    `session_maker` and `client_factory` are injected rather than imported at the
    call site so the composed guard can drive this whole path — selection,
    derivation, and the two-column UPDATE — against a seeded table and a faked
    venue. `now` is a parameter for the same reason the derivation takes no clock
    (gotcha #44): the retention floor must not move under a test.
    """
    now = now or datetime.now(timezone.utc)
    purge_floor = now - timedelta(days=PROVABLY_PURGED_AGE_DAYS)
    band_tokens = past_event_band_tokens(now)

    async with session_maker() as session:
        rows = (
            await session.execute(
                text(banded_select_sql(len(band_tokens))),
                {
                    "purge_floor": purge_floor,
                    "limit": limit,
                    "offset": offset,
                    **band_bind_params(band_tokens),
                },
            )
        ).all()
        totals = (
            await session.execute(text(COUNT_SQL), {"purge_floor": purge_floor})
        ).first()

    eligible_total = int(totals[0]) if totals else -1
    excluded_purged = int(totals[1]) if totals else -1
    never_swept = int(totals[2]) if totals else -1
    provisional_recheck = int(totals[3]) if totals else -1

    stats = {
        "eligible_total": eligible_total,
        "excluded_purged": excluded_purged,
        # The two selection reasons, reported apart. `never_swept` is the original
        # backlog and can only shrink; `provisional_recheck` is the population that
        # refills whenever a market is swept before the venue settles it, and is the
        # reason this sweep is not a one-off (CAL-P992).
        "never_swept": never_swept,
        "provisional_recheck": provisional_recheck,
        "candidates": len(rows),
        # #3284: how much of this batch the played-game band actually supplied.
        # The band is an ORDER, so this is the number that says whether it is
        # working: a batch that is mostly band is a batch of rows the venue can
        # answer for, and when the band drains this falls and the sweep is back
        # to walking the population — which is the correct steady state, not a
        # regression. Reported beside `newly_past` so the yield is auditable run
        # to run without re-deriving the cohort.
        "band_days": len(band_tokens),
        "candidates_in_band": sum(1 for r in rows if row_is_in_band(r[1], band_tokens)),
        "moved_earlier": 0,
        "unchanged": 0,
        "newly_past": 0,
        "fallback_no_close_time": 0,
        "unresolvable_at_venue": 0,
        "errors": 0,
        # #2722, the settlement half. `venue_settled` is the yield that matters
        # now: rows this batch stopped calling open because Kalshi says they are
        # over. `venue_partially_settled` is reported beside it so an event
        # settling leg by leg reads as the expected state it is rather than as a
        # miss, and `settled_without_date` counts the rows that could only be
        # reached this way — the date columns had nothing to say about them.
        "venue_settled": 0,
        "venue_partially_settled": 0,
        "settled_without_date": 0,
    }
    samples: list[dict] = []

    if not rows:
        # Not a success. Either the migration has not run, or the floor has
        # excluded everything left — two very different facts, so print both
        # numbers rather than one word.
        stats["writes_prepared"] = 0
        stats["writes_applied"] = 0
        return {
            "mode": "APPLY" if apply else "DRY_RUN",
            "measured_at": now.isoformat(),
            "purge_floor": purge_floor.isoformat(),
            "zero_yield": True,
            "zero_yield_reason": (
                f"no candidates at offset {offset}: {eligible_total} rows still "
                f"eligible ({never_swept} never swept, {provisional_recheck} holding "
                f"a provisional date), {excluded_purged} of them past the purge "
                "floor. If eligible_total is 0 the migration may not have run; if it "
                "equals excluded_purged the recoverable population is exhausted."
            ),
            "stats": stats,
            "newly_past_samples": [],
        }

    sem = asyncio.Semaphore(concurrency)
    client = client_factory()

    async def handle(row) -> Optional[dict]:
        market_id, ticker, stored_rd, commence, tier = row

        async with sem:
            try:
                event = await client.get_event(ticker, with_nested_markets=True)
            except Exception:
                stats["errors"] += 1
                return None

        markets = (event or {}).get("markets") or []
        if not markets:
            # 200-with-no-markets and 404 are NOT the same fact, but neither
            # yields a date. Counted apart from errors so a zero-yield run
            # cannot read as a clean one.
            stats["unresolvable_at_venue"] += 1
            return None

        # #2722 — the venue's own word, off the payload we already have. Read
        # BEFORE the date derivation and independently of it, because that is
        # the whole point: settlement must not be reachable only through a date.
        settlement = derive_venue_settlement([m.get("status") for m in markets])
        if settlement.settled:
            stats["venue_settled"] += 1
        elif settlement.reason == "partially_settled":
            stats["venue_partially_settled"] += 1

        window = derive_resolution_window(
            [
                _Leg(_parse(m.get("close_time")), _parse(m.get("expiration_time")))
                for m in markets
            ]
        )
        if window.resolution_date is None:
            stats["unresolvable_at_venue"] += 1
            if not settlement.settled:
                return None
            # Settled at the venue with no date we can derive. The row still
            # stops claiming to be open: "Kalshi says this is over" is a fact
            # about the market, not about our date columns, and the COALESCEd
            # UPDATE leaves whatever date we hold exactly where it is.
            stats["settled_without_date"] += 1
            return {
                "id": market_id,
                "resolution_date": None,
                "expiration_time": None,
                "venue_settled": True,
                "updated_at": now,
            }
        if window.used_expiration_fallback:
            stats["fallback_no_close_time"] += 1

        if stored_rd is not None and window.resolution_date < stored_rd:
            stats["moved_earlier"] += 1
            if stored_rd > now >= window.resolution_date:
                stats["newly_past"] += 1
                if len(samples) < 15:
                    samples.append(
                        {
                            "id": market_id,
                            "ticker": ticker,
                            "tier": tier,
                            "was": stored_rd.isoformat(),
                            "now": window.resolution_date.isoformat(),
                        }
                    )
        else:
            stats["unchanged"] += 1

        return {
            "id": market_id,
            "resolution_date": window.resolution_date,
            "expiration_time": window.expiration_time,
            "venue_settled": settlement.settled,
            "updated_at": now,
        }

    try:
        results = await asyncio.gather(*(handle(r) for r in rows))
    finally:
        # `BaseAPIClient` exposes `close()` and no `__aenter__`, so `async with`
        # on the service raises AttributeError. Explicit try/finally instead.
        close = getattr(client, "close", None)
        if close is not None:
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe

    writes = [r for r in results if r]
    stats["writes_prepared"] = len(writes)

    if apply and writes:
        async with session_maker() as session:
            for chunk_start in range(0, len(writes), 500):
                chunk = writes[chunk_start : chunk_start + 500]
                for w in chunk:
                    await session.execute(text(UPDATE_SQL), w)
                await session.commit()
        stats["writes_applied"] = len(writes)
    else:
        stats["writes_applied"] = 0

    report = {
        "mode": "APPLY" if apply else "DRY_RUN",
        "measured_at": now.isoformat(),
        "purge_floor": purge_floor.isoformat(),
        "offset": offset,
        "zero_yield": len(writes) == 0,
        "stats": stats,
        "newly_past_samples": samples,
    }
    if stats["unresolvable_at_venue"] == len(rows) and not writes:
        # Every slot in the batch went to a row this script may not write. Those
        # rows keep their slot, so an unattended re-run selects them again.
        report["batch_fully_unresolvable"] = (
            f"all {len(rows)} selected rows were unresolvable at the venue and "
            "none can be written (a missing date is not a status change). "
            f"Re-running at --offset {offset} selects the same rows; advance the "
            "offset to reach the recoverable tail."
        )
    return report


# ---------------------------------------------------------------------------
# The rotating cursor — CAL-P998, measured on the first unattended-shaped run
# ---------------------------------------------------------------------------

#: Where the next batch starts. A ROTATING cursor, and it exists because the
#: first production run of this sweep under CAL-P998 selected 500 rows and wrote
#: zero.
#:
#: WHAT WAS MEASURED (2026-09-03 16:17 PT, `heroku run:detached`, `--limit 500
#: --apply`). Before and after on the exact selected batch: 411 rows with a NULL
#: `expiration_time` before and 411 after, 89 sealed before and 89 after, 0
#: converged. `pg_stat_statements` confirms the run happened and what it did:
#: `SELECT_SQL` **1 call, 500 rows, 185 ms**, `COUNT_SQL` 1 call — and **no
#: matching UPDATE statement recorded at all.** (The dyno's stdout is not
#: readable from the agent sandbox — `heroku logs` returns EPERM — so the
#: distinction between "ran and yielded nothing" and "never ran" was settled by
#: a second signal rather than assumed. Gotcha #53.)
#:
#: WHY, off the head of the batch itself:
#:
#:     KXTXPRIMARY-31D26   commence_time 2027-11-03   resolution_date 2027-11-03
#:                         expiration_time NULL       updated_at 2026-06-20
#:
#: `commence_time` equals the backstop — the poisoned-column shape #2771 named
#: (4,954 of 5,143 sealed rows carry `commence_time = expiration_time`). So the
#: retention floor, which is a `commence_time` test, reads these as recent and
#: admits them, while the venue purged them months ago and returns no markets.
#: They yield no date, and a row this script may not write is a row whose
#: `updated_at` is never refreshed — so under `ORDER BY updated_at ASC` it stays
#: at the head **forever**.
#:
#: #2771's rotation argument ("every write refreshes the stamp, so the sweep
#: rotates") is true only of rows that get written. Unwritable rows do not
#: rotate, and 500 of them are enough to jam the entire beat: 5,143 sealed rows
#: at 05:00Z became 5,137 seventeen hours later, which is what a jam looks like
#: from outside.
#:
#: The script's own docstring already names the remedy for a human — *"`--offset`
#: exists so an operator can advance past a stuck prefix rather than re-running
#: into it"*. An unattended beat has no operator, so it must do that itself.
#:
#: 🔴 **CERT-863 BLOCK (2026-09-04) — the offset alone could not wrap, so the
#: jam it skipped was never re-reached.** The cursor held TWO facts in one
#: number and they diverge. `offset` answers *"how far past the stuck prefix am
#: I"*; the wrap needs *"how much of the population has this cycle seen"*, and
#: on a stable, fully-writable suffix the first stops moving while the second
#: must keep going. The cert's exact-head reproduction — a 1,500-row population
#: whose first 500 are stranded, then three clean batches — printed
#: ``0 -> 500 -> 500 -> 500 -> 500``. Every clean batch strands nothing, so
#: `offset + stranded` re-returns 500 forever, the wrap test never fires, and
#: the only thing that ever sends the sweep back to the head is the 30-day TTL
#: below. A market that is unresolvable in September and finalized in October
#: therefore keeps rendering its dead last-trade price for up to a month — which
#: is the exact failure this whole ship claims to end, so the claim did not hold.
#:
#: The two facts are now stored as two, and the pair travels together in ONE
#: Redis value (``"<offset>:<scanned>"``) rather than two keys: a half-written
#: pair is a cursor that says a cycle is further along than the offset it
#: carries, which skips rows silently — the failure mode this repair exists to
#: remove. A legacy bare ``"500"`` left in Redis by the pre-repair beat parses as
#: ``(500, 0)``, so the first run after deploy starts where the old cursor
#: pointed and begins counting its cycle from there.
#:
#: 🔁 **VERSIONED at `:v2` by #3284.** An offset is a position in an ORDER, and
#: the played-game band changes that order — `375` under the old ordering names
#: a different 500 rows than `375` under the new one, so resuming on it would
#: skip an arbitrary slice of the population on the first run after deploy and
#: nothing would ever report that it had. Bumping the key retires the old value
#: without deleting it (it expires on its own TTL) and starts one clean cycle at
#: the head, which is exactly where the band is. Any future change to the ORDER
#: BY must bump this again for the same reason.
SWEEP_CURSOR_KEY = "bainluck:kalshi_resolution_sweep:offset:v2"

#: 30 days. Long enough that a fortnight of failed beats does not silently reset
#: the sweep to the jammed head; short enough that a stale cursor left behind by
#: a retired population expires instead of skipping rows forever.
#:
#: It is a BACKSTOP and must never be the mechanism. Before CERT-863's repair it
#: was the mechanism — expiry was the only path back to offset 0 — and a backstop
#: doing load-bearing work is how a 30-day dead-price window looked like a
#: working nightly sweep. The cycle wrap in :func:`next_cursor` now returns to
#: the head in ``ceil(eligible_total / limit)`` runs; at the measured 6,302
#: eligible rows and a 500-row batch that is ~13 nights, comfortably inside this.
SWEEP_CURSOR_TTL_S = 60 * 60 * 24 * 30


async def _read_cursor() -> tuple[int, int]:
    """``(offset, scanned)`` to start at. An unreadable cursor is the head.

    ``(0, 0)`` is the pre-cursor behaviour, so a Redis outage degrades this sweep
    to exactly what it did before the cursor existed rather than taking it down.

    A bare integer is the pre-CERT-863 encoding and is read as ``(offset, 0)``:
    the offset is still true, and starting that cycle's traversal count at zero
    only makes the first wrap after deploy late by at most one cycle. Guessing a
    `scanned` to match would be inventing a measurement.
    """
    try:
        from app.tasks.redis_state import get_async_redis_client

        raw = await get_async_redis_client().get(SWEEP_CURSOR_KEY)
        if isinstance(raw, bytes):
            raw = raw.decode()
        offset_s, _, scanned_s = str(raw).partition(":")
        return max(0, int(offset_s)), max(0, int(scanned_s or 0))
    except Exception:  # noqa: BLE001 — a missing cursor is a start, not a failure
        return 0, 0


async def _write_cursor(offset: int, scanned: int) -> bool:
    """Persist the pair. Returns whether it landed — the caller reports it.

    Swallowing this would be the worst option available: the run would look
    clean, the cursor would stay where it was, and the next beat would re-enter
    the same jam. So the boolean travels onto the summary and into the terminal.

    One key, one round trip, both numbers — see :data:`SWEEP_CURSOR_KEY` for why
    the pair must not be split across two keys.
    """
    try:
        from app.tasks.redis_state import get_async_redis_client

        await get_async_redis_client().set(
            SWEEP_CURSOR_KEY,
            f"{int(offset)}:{int(scanned)}",
            ex=SWEEP_CURSOR_TTL_S,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def next_cursor(
    *, offset: int, scanned: int, candidates: int, applied: int, eligible_total: int
) -> tuple[int, int]:
    """The next ``(offset, scanned)``, given what this batch could not move.

    ## The offset half — where the next batch starts

    ``candidates - applied`` is exactly the number of rows that KEPT their slot:
    a written row rotates to the back of `updated_at ASC` on its own (the write
    refreshes the stamp), an unwritten one does not. Advancing by that number —
    not by ``limit`` — is what makes the cursor track the jam rather than a
    batch size, so a run that writes 470 of 500 advances 30 and a run that
    writes none advances a full batch.

    A CLEAN BATCH HOLDS ITS OFFSET; IT DOES NOT RESET. This is the correction
    that the offset-500 measurement forced, and it is worth spelling out because
    the reset is the obvious first implementation and it re-enters the jam every
    other night. Measured 2026-09-03: offset 0 is 500 unwritable rows last
    touched in June, and offset 500 is 500 rows the poller touched today which
    all write cleanly. Under "reset to 0 when nothing was stranded" the sweep
    alternates jam / productive / jam / productive and burns half its nights.
    Holding the offset is also simply correct: when 500 rows rotate to the back,
    the row that was at position 1,000 is now at position 500, so the same
    offset points at fresh content.

    ## The scanned half — CERT-863, and why the offset cannot also do this job

    Holding the offset is right, and it is exactly what made the wrap
    unreachable: a run of clean batches strands nothing, so an offset-only
    cursor is CORRECTLY motionless while the cycle is in fact advancing through
    a rotating suffix. The two facts had to be separated. ``scanned`` accumulates
    ``candidates`` — the rows this cycle has actually looked at — and it is a
    fair count of traversal precisely BECAUSE the suffix rotates: a clean batch
    at a held offset reads 500 rows it has not read before this cycle.

    IT WRAPS ON TRAVERSAL, NOT ON ARITHMETIC LUCK. Once ``scanned + candidates``
    reaches the eligible population the cycle is done: offset and scanned both
    return to 0 and the next run re-reads the head — the stranded prefix
    included. That is the promise the module made and could not keep. The venue
    publishes `close_time` on finalize, so September's unresolvable row is
    October's necessary write, and it is now re-offered every
    ``ceil(eligible_total / limit)`` runs instead of once a month by expiry.

    The old walk-off-the-end guard is kept beside it rather than replaced.
    ``offset <= scanned`` holds for any cursor this function produces (stranded
    is never more than candidates), so on a consistent cursor the traversal test
    always fires first — but a legacy bare offset, or a population that shrank
    under the cursor, can present a high offset with a low scanned, and then the
    offset test is the one that saves the run from selecting nothing forever.
    """
    if candidates == 0:
        # Nothing at this offset: either the cursor is past the end of a
        # population that shrank, or the population is empty. Both are the end
        # of a cycle, not a failure — start the next one at the head.
        return 0, 0

    traversed = scanned + candidates
    advanced = offset + max(0, candidates - applied)

    if eligible_total <= 0 or traversed >= eligible_total or advanced >= eligible_total:
        return 0, 0
    return advanced, traversed


# ---------------------------------------------------------------------------
# The unattended entry point
# ---------------------------------------------------------------------------


async def run_sweep(
    *,
    limit: int = SWEEP_BATCH_LIMIT,
    concurrency: int = SWEEP_CONCURRENCY,
    apply: bool = True,
    offset: Optional[int] = None,
    session_maker: Optional[Callable] = None,
    client_factory: Optional[Callable[[], object]] = None,
) -> dict:
    """One bounded beat run, with terminal truth attached.

    THE TERMINAL IS THE POINT, not decoration. ``_tracked_run`` classifies this
    summary through ``app.utils.task_verdict``, and a summary with no terminal
    field is recorded as a success merely because the invocation returned —
    which is how three calibration tasks reported ``health: healthy`` while
    producing nothing (#1515). This sweep has a zero-yield mode that is a
    perfectly normal return value, so it must say which zero it is:

    * **complete** — the batch wrote what the venue gave it, OR nothing is
      eligible at all (the population really is drained).
    * **partial** — rows were selected and NOTHING could be written. The batch
      spent its whole slot on rows the venue would not resolve; the population
      did not move and the next run selects the same head. Never green.
    * **failed** — every selected row errored at the venue. That is an outage,
      not a drained population, and it must not read as either of the above.

    ``apply`` defaults to TRUE here and FALSE in ``run_backfill``, deliberately:
    the CLI's default must be the harmless one because a human types it, and the
    beat's default must be the useful one because nobody is there to pass a flag.

    ``offset`` defaults to the rotating cursor. Pass an explicit one only to pin
    a run; see :data:`SWEEP_CURSOR_KEY` for the measurement that made the cursor
    necessary — without it this beat writes zero rows every night, forever, and
    looks healthy doing it.
    """
    from app.services.database import async_session_maker

    if offset is None:
        start, scanned = await _read_cursor()
    else:
        # An explicitly pinned run is a probe of one batch, not a step in the
        # cycle, so it starts that cycle's traversal count at zero rather than
        # crediting the pin against a cycle it did not walk.
        start, scanned = max(0, int(offset)), 0

    report = await run_backfill(
        session_maker=session_maker or async_session_maker,
        client_factory=client_factory or KalshiAPIService,
        limit=limit,
        offset=start,
        apply=apply,
        concurrency=concurrency,
    )

    stats = report.get("stats") or {}
    candidates = int(stats.get("candidates") or 0)
    applied = int(stats.get("writes_applied") or 0)
    errors = int(stats.get("errors") or 0)
    eligible = int(stats.get("eligible_total") or 0)

    nxt, nxt_scanned = next_cursor(
        offset=start,
        scanned=scanned,
        candidates=candidates,
        applied=applied,
        eligible_total=eligible,
    )
    # BOTH halves must be unchanged to skip the write. The offset alone standing
    # still is the normal healthy case (a clean batch holds it) and it is exactly
    # when `scanned` is moving — skipping the write on the offset alone is how
    # cycle progress would be dropped every productive night, which is the
    # CERT-863 defect rebuilt inside the optimisation that was meant to be free.
    unchanged = nxt == start and nxt_scanned == scanned
    persisted = True if unchanged else await _write_cursor(nxt, nxt_scanned)

    report["offset"] = start
    report["next_offset"] = nxt
    report["scanned_before"] = scanned
    report["next_scanned"] = nxt_scanned
    # The cycle closed on this run: the next beat re-reads the head, stranded
    # prefix included. Named on the summary because "the sweep went back to 0"
    # must be legible as a completed traversal rather than as a lost cursor.
    report["cycle_wrapped"] = nxt == 0 and nxt_scanned == 0 and start != 0
    report["stranded"] = max(0, candidates - applied)
    report["cursor_persisted"] = persisted

    if not persisted:
        # Progress may have been made and it is silently unresumable: the next
        # beat re-enters this exact batch and the jam returns. The typeahead
        # index builder makes the same call for the same reason (#1866).
        report["terminal"] = "failed"
        report["terminal_reason"] = (
            f"cursor not persisted — the next run repeats offset {start} "
            f"instead of advancing to {nxt}"
        )
    elif candidates and errors >= candidates:
        report["terminal"] = "failed"
        report["terminal_reason"] = f"all {candidates} selected rows errored at the venue"
    elif candidates and applied == 0:
        report["terminal"] = "partial"
        report["terminal_reason"] = (
            f"{candidates} rows selected, 0 written — "
            f"{stats.get('unresolvable_at_venue')} unresolvable at the venue; "
            f"cursor advanced {start} -> {nxt} so the next run does not re-enter it"
        )
    else:
        report["terminal"] = "complete"

    # The population this run did NOT reach, carried on the summary so a bounded
    # sweep can never be read as a finished one — the same reason `run_backfill`
    # reports `eligible_total` beside `candidates`.
    report["remaining_after_batch"] = max(0, eligible - applied)
    return report
