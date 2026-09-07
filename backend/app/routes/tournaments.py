"""Tournament hub endpoint — the US Open championship boards.

``GET /api/tournaments/{slug}``

The register is the single source of page truth (US Open charter, 2026-08-25).
This route therefore does exactly three things: resolve the slug to a committed
register, load prices for the identities that register pins, and hand both to
``app.utils.tournament_board``.  There is no matching, no fuzzy lookup and no
name normalization on this path — which is the entire point of the register
pattern, and what makes the page immune to the ``llm_sport_category`` /
``llm_gender`` contamination the Day-1 census measured (#2200).

**The slug does not infer.**  An unregistered slug is a 404, never a
best-effort nearest tournament.  Ruling 031's disease — choosing a different
tournament because its draw was bigger — cost the US Open its own page once
already (#1793); the floor that prevents it is the absence of a fallback, not a
cleverer scorer.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sqlfunc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
from app.services import get_db
from app.utils.latest_observation import load_latest_observed_at
from app.utils.market_liquidity import grade_liquidity
from app.utils.tournament_advancement import build_advancement
from app.utils.tournament_board import TREND_DAYS, build_boards
from app.utils.tournament_event_link import (
    resolve_espn_competition_events,
    resolve_matchup_events,
)
from app.utils.tournament_grid import build_grids
from app.tasks.tournament_matchup_linker import apply_resolved_links, read_links
from app.utils.tournament_match import build_match_detail
from app.utils.tournament_register import TournamentRegister, load_register
from app.utils.tournament_slate import (
    apply_books_prematch,
    apply_espn_event_links,
    apply_event_blend_slate,
    event_blend_view,
    build_bracket,
    build_props,
    build_results,
    build_slate,
    slate_competition_ids,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Explicit, not derived. A tournament is servable because someone committed a
# register for it and wrote the season down here — never because a slug parsed.
REGISTERED_TOURNAMENTS: dict[str, dict[str, Any]] = {
    "us-open": {
        "season": "2026",
        "title": "US Open 2026",
        "subtitle": "Flushing Meadows",
        # ESPN's own name for this tournament on the tennis scoreboard, used to
        # select it out of a day that also carries Winston-Salem and Monterrey.
        # Named here rather than matched: same posture as the slug itself.
        "espn_event_name": "US Open",
        # WHICH `events` ROWS BELONG TO THIS CONTAINER (UX-P152). Named, never
        # inferred from the slug — same posture as `espn_event_name` above.
        # This is what makes the "is this event in a tournament" question cost
        # one indexed read for the ~99.99% of events whose answer is no; an
        # event page for a Lakers game must not pay for the US Open being on.
        # Measured 2026-08-28: 47 + 47 main-draw singles events under these two
        # keys, created by the Odds API ingest on 2026-08-27.
        "sport_keys": ("tennis_atp_us_open", "tennis_wta_us_open"),
        # The main-draw ceremony, in the tournament's own local time. Alex's
        # item 1: the pre-draw panel must say WHEN, not just that it has not
        # happened. Register-adjacent rather than register-owned because it is
        # a fact about the calendar, not about a market identity.
        "draw_release_at": "2026-08-27T12:00:00-04:00",
        "draw_release_label": "Thursday 27 August, 12:00 ET",
        "main_draw_starts_at": "2026-08-30T11:00:00-04:00",
        "main_draw_label": "Sunday 30 August",
    },
}

# Where `sync_tournament_results` writes and this route reads. The TTL is
# generous relative to the 3-minute refresh so a single missed task run does not
# blank the section; a genuinely dead task lets it expire, which is the honest
# outcome (an empty section with a stated reason beats an hour-old result
# presented as current).
RESULTS_TTL_SECONDS = 900
RESULTS_PREFIX = "bainluck:tournament-results:"

# And the hour-long shadow of that key (#3304). Written by the same task, only
# for a clean complete read; the reasoning for its existence and its TTL is on
# `RESULTS_LAST_GOOD_TTL_SECONDS` in `tasks/tournament_price_refresh.py`. Read
# here ONLY when the primary is gone.
RESULTS_LAST_GOOD_PREFIX = "bainluck:tournament-results-last-good:"

# Short, and deliberately not a 24h mirror. #1767 shipped a league route that
# rebuilt once per 24h and served the stale copy for the other 23h55m; a page
# whose whole subject is freshness must not inherit that shape. Sixty seconds
# absorbs a burst without ever being the reason a number is old.
CACHE_TTL_SECONDS = 60
CACHE_PREFIX = "bainluck:tournament:"

# Bounds the per-request series scan. The register pins ~160 outcomes; at hourly
# capture over TREND_DAYS that is well inside this, and the cap is here so a
# capture-rail change cannot silently turn this route into a table scan.
MAX_SERIES_ROWS = 20000

#: Bounds one match page's sibling scan. A Polymarket tennis event carries ~12
#: sub-markets and ~33 outcome rows; 400 is generous by an order of magnitude
#: and exists so a source that starts listing hundreds cannot turn a page
#: request into an unbounded read. Truncation is reported, never silent —
#: `build_match_detail` counts it as `OVER_CAP`.
MAX_MATCH_GROUP_ROWS = 400

# ── THE TWO HALVES OF THIS PAGE (latency/135, #2846) ────────────────────────
#
# Alex, 2026-09-03, on the felt table: the hub is the slowest tab of every tab
# we measure — p50 0.93 s, worst 1.69 s — and *"the first screen needs the slate
# + live rows; grids/bracket/results can arrive second"*.
#
# MEASURED ON PRODUCTION THE SAME AFTERNOON, one response decomposed by
# top-level key (902,423 bytes uncompressed / 86,838 gzipped):
#
#     grids    377,074  41.8%   the Bracket TAB — not on screen at all until a tap
#     results  315,108  34.9%   260 finished matches, below the fold on a phone
#     boards   126,665  14.0%   the chart, which IS the first element
#     slate     59,989   6.6%   the day's matches
#     the rest  23,587   2.6%
#
# So two thirds of this payload renders nothing a reader can see on the first
# screen, and on a cold build it is also two thirds of the price list: `first`
# needs 356 of the register's pinned outcome ids, `rest` adds the grid's 336
# reaches.
#
# `?sections=first` and `?sections=rest` are those two halves. **No parameter
# means both, byte-for-byte the payload this route has always served** — the
# native app, `/by-event/{id}` and every existing test are on that path and this
# change is invisible to them.
#
# THE SPLIT IS NOT FREE AND IT IS NOT PRETENDED TO BE. Two requests build the
# register twice and load ~956 outcome prices between them against 692 for one
# combined build. That is ~38% more server work in total, bought deliberately:
# the second build overlaps the reader's first screen, which is the only clock
# a reader has.
SECTION_FIRST = "first"
SECTION_REST = "rest"
SECTION_GROUPS: tuple[str, ...] = (SECTION_FIRST, SECTION_REST)

#: The keys `rest` owns. Named so the guard suite can assert the split is
#: exhaustive in BOTH directions — no key may go missing from the full response,
#: and no first-screen key may drift into the second request.
REST_SECTION_KEYS: tuple[str, ...] = ("grids", "results")


def _cache_key(slug: str, group: str = SECTION_FIRST) -> str:
    # Per-group, because the whole point is that a first-screen request never
    # touches the grid's 377 KB — including in Redis. One key holding both would
    # mean every `sections=first` read still transferred and `json.loads`-ed the
    # full payload out of Redis to throw two thirds of it away.
    return f"{CACHE_PREFIX}{slug}:{group}"


async def _cache_get(slug: str, group: str = SECTION_FIRST) -> Optional[dict[str, Any]]:
    try:
        from app.tasks.redis_state import get_async_redis_client

        raw = await get_async_redis_client().get(_cache_key(slug, group))
        if raw:
            return json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — cache is an optimisation, never a gate
        logger.warning("tournament cache read failed for %s/%s: %s", slug, group, exc)
    return None


async def _cache_set(
    slug: str, payload: dict[str, Any], group: str = SECTION_FIRST
) -> None:
    try:
        from app.tasks.redis_state import get_async_redis_client

        await get_async_redis_client().setex(
            _cache_key(slug, group),
            CACHE_TTL_SECONDS,
            json.dumps(payload, default=str),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("tournament cache write failed for %s/%s: %s", slug, group, exc)


def _merge_fragment(payload: dict[str, Any], fragment: dict[str, Any]) -> None:
    """Fold one section group's fragment into the response being assembled.

    FIRST WINS ON A COLLISION, and only meta keys can collide: both fragments
    carry `slug` and `generated_at` so that either one is self-describing when
    served alone.  When the two are built in one call they share a single `now`
    and the rule is a no-op; when `first` came off a warm cache and `rest` was
    just built, the reader gets the stamp belonging to the numbers it is
    actually looking at rather than a fresher one describing a section below
    the fold.

    `event_links` is the one structural exception.  Its two channels are built
    by different halves — `by_matchup` prices the day's card (`first`),
    `by_espn` dereferences the finished list's competition ids (`rest`) — and a
    plain overwrite would drop whichever landed first.  They are merged, so the
    full response carries both channels exactly as it always has.
    """
    for key, value in fragment.items():
        if key == "event_links" and isinstance(value, dict):
            existing = payload.get("event_links")
            if isinstance(existing, dict):
                existing.update(value)
                continue
            payload["event_links"] = dict(value)
            continue
        payload.setdefault(key, value)


async def _espn_results(slug: str) -> dict[str, Any]:
    """ESPN tennis results for one tournament — READ FROM CACHE, never fetched.

    THE SHAPE MATTERS MORE THAN THE FEATURE.  Everything else on this page comes
    out of our own database; results do not, because nothing in our database
    holds the result of a tennis match (checked 2026-08-26: zero ``events`` rows
    for any of the register's matchups).  So there is a fetch — and it does not
    live here.

    The first draft fetched inside the request, with a Redis cache in front of
    it.  That is the same shape the feed's standing rule forbids by name
    ("never run LLM calls inside ``GET /api/feed``"), and for the same reasons:
    the first request after every TTL expiry pays a third-party round trip, a
    slow ESPN makes a slow page for somebody, and a route contract test starts
    making live network calls.  ``sync_tournament_results`` (every 3 minutes,
    background queue) does the fetching; this only reads.

    A cold or empty cache yields an empty results section and the rest of the
    page.  Never a partial page, never a 503, and never a fabricated score.

    ═══ #3304: AN ABSENT SCOREBOARD IS NOT A QUIET DAY ═══

    That last paragraph describes what this function RETURNS.  It was not true
    of what the page then DID with it, and the gap is gotcha #53 in its purest
    form: the miss path below and a successful fetch on a day with no tennis
    produced the same bytes, so no consumer could tell them apart.

    `build_slate` is the consumer that cannot afford the confusion.  Its only
    route to `DECIDED` requires the scoreboard to NAME the fixture, so an empty
    map retires nothing, and the pinned-fixture clock exemption (CERT-544) then
    prints the whole decided main draw as the day's card.  Measured on
    production 2026-09-05 at 19:04Z, mid-tournament: **96 rows, 0 in progress, 0
    results, 12.2h-old prices**, recovered by 19:25Z.  Reproduced exactly by
    passing `order_of_play={}` to `build_slate` with the real register.

    So a miss now reaches for the last scoreboard we were sure of before it
    gives up.  Three states, and they are deliberately distinguishable:

    * **primary hit** — `scoreboard: "live"`, as always.
    * **last-good hit** — `scoreboard: "last_good"`.  The answer to "who is on"
      is up to an hour old; every PRICE on the page is current, because prices
      come from our own database and never from this key.  The cost is bounded
      and named: a match that finished within the hour lingers on the card
      instead of moving to results, which is the direction CERT-544 already
      ruled is the right one to be wrong in.
    * **neither** — `scoreboard: "unavailable"`, and the behaviour is exactly
      what it has always been.  This is not a fix for a sustained outage and
      does not pretend to be one; it removes the fifteen-minute cliff.

    The stamp is set here, on the payload, rather than returned alongside it,
    because `_espn_results` has two call sites and a flag that only one of them
    threads is a flag the other one silently loses.
    """
    from app.tasks.redis_state import get_async_redis_client

    for prefix, state in (
        (RESULTS_PREFIX, "live"),
        (RESULTS_LAST_GOOD_PREFIX, "last_good"),
    ):
        try:
            raw = await get_async_redis_client().get(f"{prefix}{slug}")
        except Exception as exc:  # noqa: BLE001 — a results section is not a gate
            logger.warning("tournament results cache read failed for %s: %s", slug, exc)
            continue
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception as exc:  # noqa: BLE001 — a corrupt slot is a miss
            logger.warning("tournament results cache decode failed for %s: %s", slug, exc)
            continue
        if not isinstance(payload, dict):
            continue
        if state == "last_good":
            logger.warning(
                "tournament results primary cache missing for %s — "
                "serving the last-good scoreboard (#3304)",
                slug,
            )
        payload["scoreboard"] = state
        return payload

    logger.warning(
        "tournament results unavailable for %s — no primary and no last-good "
        "scoreboard; the slate falls back to the register (#3304)",
        slug,
    )
    return {"draws": {}, "stats": {}, "errors": [], "scoreboard": "unavailable"}


def _hours_since(stamp: datetime | None, at: datetime) -> float | None:
    """How long ago, in hours, or ``None`` if there is nothing to measure from.

    Naive stamps are read as UTC — every writer of ``volume_updated_at`` uses
    ``func.now()`` on a UTC database, and a naive value here means the driver
    dropped the tzinfo, not that somebody meant local time.  Getting that wrong
    would silently shift an age by the server's offset and either invent or
    suppress a mark.

    A stamp in the FUTURE returns a negative number and is deliberately not
    clamped: ``grade_liquidity`` refuses it, because two clocks disagreeing is
    not an observation, and the honest response to "we cannot tell when this
    was measured" is the same as to "we never measured it".
    """
    if stamp is None:
        return None
    return (at - _as_utc(stamp)).total_seconds() / 3600.0


def _as_utc(stamp: datetime) -> datetime:
    """A naive stamp read as UTC, an aware one untouched.

    Shared by the two things here that compare timestamps, for the reason
    ``_hours_since`` gives above: a naive value out of this database means the
    driver dropped the tzinfo, never that somebody meant local time.  Two copies
    of that rule is one copy too many — an age and a max must not be able to
    disagree about what a naive stamp means.
    """
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


def _price_observed_at(
    *,
    history_at: datetime | None,
    touched_at: datetime | None,
    probability: Any,
) -> datetime | None:
    """The newer of the two lower bounds on "when did we last see this price".

    Split out of :func:`_load_prices` so the rule can be stated once and tested
    without a database or a route.  The full reasoning, and the two production
    measurements that make it a max rather than a choice, are in that function's
    docstring — read them before changing this.

    Three refusals, each of which has a row that needs it:

    * **No price, no observation.**  ``last_updated`` is ``NOT NULL`` with
      ``server_default=func.now()``, so an unpriced outcome minted a minute ago
      would otherwise claim a fresh reading of nothing.  The history clock is
      still honoured in that case — ``load_latest_observed_at`` only returns ids
      that have a PRICED snapshot, so its presence is itself the evidence.
    * **Naive stamps are made UTC before comparing.**  ``max()`` over a mixed
      naive/aware pair raises ``TypeError``, and this runs inside the dict
      comprehension that builds EVERY price, so the raise would empty the whole
      hub rather than one cell — the Hot List's "one bad item must never wipe a
      scoring pass".  Both columns are ``timezone=True`` in the model, so this
      is belt-and-braces against a caller — a test fake, a SQLite gate — that
      hands over naive datetimes.
    * **``None`` is absence, never "now".**  Either clock may be missing; both
      missing means no observation, which is what ``price_state`` reads as
      ``dark``, and that is the correct reading.
    """
    stamps = []
    if history_at is not None:
        stamps.append(_as_utc(history_at))
    if touched_at is not None and probability is not None:
        stamps.append(_as_utc(touched_at))
    return max(stamps) if stamps else None


async def _load_prices(
    session: AsyncSession, outcome_ids: list[int], *, now: datetime | None = None
) -> dict[int, dict[str, Any]]:
    """Current price + the time it was last actually OBSERVED, per outcome.

    🔴 **FRESHNESS IS THE NEWER OF TWO CLOCKS, AND BOTH HALVES ARE MEASURED
    (#3243 / #2898).**  This loader used to read
    ``futures_odds_snapshots.captured_at`` and say, in this docstring, "never
    from ``futures_outcomes.last_updated``".  That sentence was not a
    preference, it was the Day-1 census: ``last_updated`` measured a month stale
    on the Polymarket men's field while its snapshots ran current.  It is still
    true.  It is also only half the population.

    Measured on production 2026-09-05 15:38-15:53Z, the 18 Kalshi ``duel``
    markets behind the Round-of-32 slate, the exact inverse:

        futures_outcomes.last_updated       15:53:00Z  (moving every ~30 s)
        futures_odds_snapshots.captured_at  06:53:42Z  (8.9 h, and IDENTICAL
                                                        to the microsecond on
                                                        all 18 — one batch)

    so the page rendered "⚠ Updates paused … these are the last probabilities we
    saw, not live ones" over a number that had changed 40 seconds earlier, while
    the sibling event page said "live · 42s ago" in the same minute.

    Neither clock is wrong; each is a **lower bound** written by a writer that
    had just read the venue, and each has a population the other covers:

    * ``captured_at`` is the HISTORY clock.  Its writers are the polls and the
      candlestick backfills.  ``kalshi_ws`` — which flushes every 2 s and is the
      only thing pricing an in-play match — writes the price columns and *no
      snapshot row at all*, by design (see its own comment: it "owes both stamps
      the polls owe").  So this clock can never describe a WS-priced market,
      however healthy ingest is.
    * ``last_updated`` is the TOUCH stamp — "when did a poller last SEE this
      row".  It carries no ``onupdate``; every price writer stamps it
      explicitly, which is exactly the shape gotcha #155 prescribes and the
      reason this is not an "any write" column.  It is also what the *sibling*
      surfaces already answer this question with: the event page reads
      ``win_probability_sources[*].updated_at`` and
      Discover reads ``price_polled_at = MAX(last_updated)``
      (``utils/futures_market_snapshot.py``).

    Because both are lower bounds and neither can be stamped without a writer
    having looked, **the newer of the two is the honest answer and taking it
    cannot regress either measured case**: Day-1's month-stale ``last_updated``
    loses to its current snapshot, today's 8.9 h snapshot loses to its live
    ``last_updated``.  Do not collapse this back to one column in either
    direction — each collapse has already shipped once and lied.

    The price guard is what keeps the max honest.  ``last_updated`` carries
    ``server_default=func.now()``, so an outcome created minutes ago and never
    priced would otherwise report a fresh observation of a price that does not
    exist.  A row with no ``current_probability`` contributes no touch stamp.

    ⚠ **THIS DOES NOT CLOSE THE HISTORY HOLE, and that is a separate defect
    (#3247), deliberately still visible in the data.**  Those 18 markets have no
    observation row since 06:53:42Z because every snapshot-writing rail excludes
    them — the committed register (v12, generated 2026-08-27) pins 462 market
    ids and none of the 18, ``futures_price_refresh``'s class arm wants tier 1
    and they are tier 5, and ``poll_kalshi_markets`` (2 h) is deadline-truncated.
    Their charts have a nine-hour gap during play.  Fixing the banner must not
    be read as fixing that.

    **AND THE BOOK THE PRICE CAME OFF**, since UX-P157.  This one loader feeds
    every surface on the hub — boards, grid, bracket, slate, props — so a fact
    added here reaches all five without five opinions about it, and a fact added
    anywhere else would be a sixth.  ``liquidity`` is graded once, by
    ``utils.market_liquidity``, and travels with the number it describes.
    """
    if not outcome_ids:
        return {}

    # Passed by both callers, which already hold one. Defaulted rather than
    # required so a third caller cannot accidentally grade against no clock at
    # all — and read ONCE here, not per row, so every cell in one response is
    # aged against the same instant.
    at = now or datetime.now(timezone.utc)

    rows = (
        await session.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesOutcome.current_probability,
                # The SCRIPT. Loaded here rather than in a second query because
                # the slate's move is only meaningful against the same row's own
                # opening price.
                FuturesOutcome.opening_probability,
                # ── THE BOOK (UX-P157, #2256).
                #
                # This read had a named dependency on **PR #2259 (Q428)**, which
                # merged 2026-08-29 02:49Z and deployed. UX-P158 re-measured the
                # thing UX-P157 was owed to re-measure, and the premise HOLDS
                # where the rail runs:
                #
                #   before  320 of 325 comparable ladder markets held a stored
                #           book differing from Gamma's live one
                #   after   138 of 325 — and the split is the whole story. Of
                #           the 221 rows the 10-minute rail had refreshed within
                #           the hour, 187 of 219 comparable are book-IDENTICAL
                #           to live and the rest are quotes that moved between
                #           the two reads. Of the 115 rows the rail does NOT
                #           write, 0 of 106 match: their book is frozen at the
                #           2026-08-25 full poll, 83 hours old.
                #
                # THE 115 ARE NOT A REGISTER GAP — all 336 are pinned, and the
                # rail's own summary says why (2026-08-29 05:35Z, read from
                # task-metrics, not inferred): `conditions_requested: 366,
                # markets_returned: 328, unpriced: 107`. 336 - 328 = 8 Gamma no
                # longer serves, and 107 are Q428's DECLINE — a book it will not
                # publish a price from. 8 + 107 = 115, exactly. So the rows with
                # the stalest books are the ones Q428 judged untradeable, which
                # is the same population this mark exists to describe. That is
                # why UX-P158 writes the volume observation for every market
                # Gamma RETURNS rather than every market it prices.
                FuturesOutcome.current_yes_bid,
                FuturesOutcome.current_yes_ask,
                # The venue's own 24h figure, market-level: Kalshi and
                # Polymarket both report volume per MARKET, not per outcome, so
                # both legs of a binary share it. Joined rather than a second
                # round trip — one extra column on an existing index lookup.
                FuturesMarket.volume_24h,
                # ── AND WHEN WE ASKED FOR IT (UX-P158).
                #
                # Without this column a NULL `volume_24h` is unreadable, and the
                # mark's whole second grade turns on reading it: Gamma omits a
                # zero rather than serving one (328/328 against the trade tape),
                # so "asked, and no figure came back" is a measured zero while
                # "never asked" is nothing at all. Same shape as `observed_at`
                # below — a number and the time it was taken travel together or
                # they are not a measurement.
                FuturesMarket.volume_updated_at,
                # ── AND THE OTHER FRESHNESS CLOCK (#3243).
                #
                # The touch stamp, riding the SELECT that is already fetching
                # this row rather than a second round trip. The same call was
                # measured in `utils/futures_market_snapshot.py`: a separate
                # `MAX(last_updated) … GROUP BY` over the same ids is a second
                # bitmap heap scan of the same rows and cost 423 ms there, while
                # one more column on a statement already reading them is inside
                # its own run-to-run noise. See the docstring for why BOTH
                # clocks are read and why the newer one wins.
                FuturesOutcome.last_updated,
            )
            # OUTER, and it matters: an INNER join would drop the whole price
            # row if a market were ever missing, and a dropped price does not
            # render as "no liquidity data" — it renders as `unlinked`, the
            # grid's red alarm. A liquidity signal must not be able to blank a
            # number. Worst case here is a `None` volume, which grades as
            # unknown and draws nothing.
            .outerjoin(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
            .where(FuturesOutcome.id.in_(outcome_ids))
        )
    ).all()

    # LAT-P147 (#2328). This was `max(captured_at) ... GROUP BY outcome_id`, and
    # an aggregate cannot skip: it read 342,059 index tuples and 175,754 buffer
    # blocks to return 514 numbers, which is 87-93% of this page's whole cold
    # build. The register bounds the id list, so the same answer is one top-1
    # index probe per outcome — 1,766 ms -> 118 ms, 514 rows, 0 diffs, measured
    # on production. Why it is spelled the way it is (and why `NULLS LAST` is
    # 19x worse) lives in `utils/latest_observation`, next to the statement.
    observed_by_id = await load_latest_observed_at(session, outcome_ids)

    return {
        row.id: {
            "probability": (
                float(row.current_probability)
                if row.current_probability is not None
                else None
            ),
            "opening_probability": (
                float(row.opening_probability)
                if row.opening_probability is not None
                else None
            ),
            "observed_at": _price_observed_at(
                history_at=observed_by_id.get(row.id),
                touched_at=row.last_updated,
                probability=row.current_probability,
            ),
            "source_name": row.name,
            # {"level": ..., "reasons": [...]}. Graded here, once, so no
            # builder downstream can hold a second opinion about the same book.
            "liquidity": grade_liquidity(
                bid=row.current_yes_bid,
                ask=row.current_yes_ask,
                volume_24h=row.volume_24h,
                volume_observed_age_hours=_hours_since(row.volume_updated_at, at),
            ),
        }
        for row in rows
    }


async def _load_series(
    session: AsyncSession, outcome_ids: list[int], *, now: datetime
) -> dict[int, list[tuple[str, float]]]:
    """Daily mean per outcome — the raw material for an unsmoothed trend line.

    Meaning within one outcome-day is a summary of *one source's own readings*,
    which is not a cross-source blend and does not touch the blend rule. The
    cross-source step happens once, in ``tournament_board``, so there is exactly
    one place where "the number" is decided.
    """
    if not outcome_ids:
        return {}

    cutoff = now - timedelta(days=TREND_DAYS)
    day = sqlfunc.date_trunc("day", FuturesOddsSnapshot.captured_at).label("day")
    rows = (
        await session.execute(
            select(
                FuturesOddsSnapshot.outcome_id,
                day,
                sqlfunc.avg(FuturesOddsSnapshot.probability).label("probability"),
            )
            .where(
                FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
                FuturesOddsSnapshot.captured_at >= cutoff,
                FuturesOddsSnapshot.probability.isnot(None),
            )
            .group_by(FuturesOddsSnapshot.outcome_id, day)
            .order_by(FuturesOddsSnapshot.outcome_id, day)
            .limit(MAX_SERIES_ROWS)
        )
    ).all()

    series: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        if row.probability is None or row.day is None:
            continue
        series[row.outcome_id].append((row.day.date().isoformat(), float(row.probability)))
    return dict(series)


async def _with_link_overlay(
    slug: str, register: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """The Q426 link overlay, applied to the match page as well as the hub.

    ═══ WHY THIS IS HERE AND NOT ONLY IN `get_tournament` ═══

    Lane1's Q426 ships `tournament_matchup_linker`: the draw census ran once, at
    the ceremony, and recorded ``status: "missing"`` against all 96 R128
    fixtures because nobody quotes a first round before qualifying finishes. By
    the next morning Kalshi quoted every one of them.  The linker re-asks on a
    beat and the hub reads what it finds.

    **A match page that did not read the same overlay would contradict the list
    it was reached from.**  On those 96 fixtures the hub would print a
    probability and the match's own page would say "no market has put a
    probability on this match yet" — two surfaces disagreeing about one
    question, which is the divergence the standing ruling exists to prevent, on
    the main draw, in the week it starts.  It is also the worse half of the
    disagreement: the reader arrives at the detail page expecting MORE.

    ═══ WHY THE IMPORT IS INSIDE THE `try` ═══

    Not defensiveness — an honest statement of what this branch holds.  The
    linker and `apply_resolved_links` are lane1's, on master, and are NOT in
    this branch's tree; this queue is not going to vendor a copy of them to
    make an import statement look tidy.  Inside the `try`, the call degrades to
    the committed register here and starts working the moment the two branches
    meet, with no further edit.  That is the same posture `get_tournament`'s own
    wrapper takes for the same overlay, and for the same reason: **the overlay
    is an optimisation over the committed truth and must never be a gate.**

    Returns the register (never mutated in place — gotcha #6: a module-level
    cached dict edited in place leaks one request's overlay into the next) and
    how many blocks were filled.
    """
    try:
        from app.tasks.tournament_matchup_linker import (  # noqa: PLC0415
            apply_resolved_links,
            read_links,
        )

        links = (await read_links(slug)).get("links") or {}
        return apply_resolved_links(register, links)
    except Exception as exc:  # noqa: BLE001 — an overlay is never a gate
        logger.warning("tournament link overlay unavailable for %s: %s", slug, exc)
        return register, 0


async def _load_match_group(
    session: AsyncSession, *, winner_market_id: int
) -> tuple[Optional[str], list[dict[str, Any]]]:
    """The sibling markets that share this match's group — id-anchored, no matching.

    ONE HOP, AND IT IS AN INDEX LOOKUP ON A PRIMARY KEY FOLLOWED BY ONE ON
    ``group_id`` (indexed).  The register pins the match-winner market's id; the
    source has already put every prop for that match in the same group.  There
    is no name comparison, no time window and no category test on this path,
    which is the same posture as the register and the reason lane1 could hand
    the surface over without handing over a matching problem with it.

    TWO MARKETS ARE EXCLUDED, FOR DIFFERENT REASONS:

    * **The match-winner market itself** — it is the hero above, not a prop.
    * **The event container.**  Every Polymarket event carries a synthetic
      parent holding one outcome per member, so rendering it would print the
      whole page a second time as a single field.  It is identified by the id
      equality ``group_id == "{source}:{external_id}"`` — exact, and immune to
      the classifier drift that makes ``market_type == 'field'`` the wrong
      test (a genuine Exact Score prop is also a field).
    """
    group_id = (
        await session.execute(
            select(FuturesMarket.group_id).where(FuturesMarket.id == winner_market_id)
        )
    ).scalar_one_or_none()
    if not group_id:
        return None, []

    rows = (
        await session.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.source,
                FuturesMarket.external_id,
                FuturesOutcome.id.label("outcome_id"),
                FuturesOutcome.name.label("outcome_name"),
                FuturesOutcome.external_id.label("outcome_external_id"),
            )
            .join(FuturesOutcome, FuturesOutcome.market_id == FuturesMarket.id)
            .where(FuturesMarket.group_id == group_id)
            .order_by(FuturesMarket.id, FuturesOutcome.id)
            .limit(MAX_MATCH_GROUP_ROWS)
        )
    ).all()

    markets: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.id == winner_market_id:
            continue
        if group_id == f"{row.source}:{row.external_id}":
            continue
        entry = markets.setdefault(
            row.id, {"market_id": row.id, "name": row.name, "outcomes": []}
        )
        entry["outcomes"].append({
            "outcome_id": row.outcome_id,
            "name": row.outcome_name,
            "external_id": row.outcome_external_id,
        })
    return group_id, list(markets.values())


@router.get("/by-event/{event_id}")
async def get_event_tournament(
    event_id: int, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """A standard event's tournament extensions — advancement, and the props.

    ``GET /api/tournaments/by-event/{event_id}``

    ═══ WHY THIS REPLACED A MATCH-PAGE ROUTE ═══

    Alex, 2026-08-28, on the UX-P149 artifact: *"It seems like we're reinventing
    the event page here"*, and then the architecture note: *"I thought that
    tournaments were containers for related events."*

    That is the ruled model and it is what the database holds.  UX-P149 built a
    bespoke match surface on the premise that a tennis matchup has no ``events``
    row; that premise expired at **2026-08-27 21:05 UTC**, when the Odds API
    began carrying US Open main-draw singles and 94 standard events appeared for
    the 96 registered R128 fixtures.  So there is no match page: a match is an
    event, it renders on ``/events/{id}`` with the probability-over-time graph
    and every other thing an event page does, and the tournament adds two
    sections **to** that page.  This endpoint is those two sections.

    ═══ THE CHEAP NO ═══

    The event page asks this about every event it renders, so the ``no`` has to
    cost almost nothing.  One indexed read of the event's sport key answers it:
    a sport key no registered tournament claims returns ``{"tournament": null}``
    without loading a register, building a hub payload, or touching Redis.  A
    Lakers game must not pay for the US Open being on.

    ``{"tournament": null}`` and not a 404: "this event is not part of a
    tournament" is the ordinary answer for almost every event on the site, and
    an error status for the ordinary answer is how a health check learns to
    ignore a real one.
    """
    from app.models.models import Event, Sport  # noqa: PLC0415

    row = (
        await db.execute(
            select(Sport.key, Event.home_team_name, Event.away_team_name)
            .join(Event, Event.sport_id == Sport.id)
            .where(Event.id == event_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    sport_key, home_team_name, away_team_name = row

    slug = next(
        (
            s for s, spec in REGISTERED_TOURNAMENTS.items()
            if sport_key in spec.get("sport_keys", ())
        ),
        None,
    )
    if slug is None:
        return {"event_id": event_id, "tournament": None}

    spec = REGISTERED_TOURNAMENTS[slug]

    # THE CONTAINER AND THE FIXTURE ARE TWO DIFFERENT QUESTIONS (#3697).
    #
    # *Which container is this event in?* is answered by the sport key, three
    # lines up: `tennis_atp_us_open` is claimed by exactly one registered
    # tournament and `slug` is already in hand. *Which registered fixture is
    # it?* is what the register pins, below. Until #3697 both bail-outs below
    # returned `tournament: None` — throwing away the fact that WAS proven in
    # order to report the one that was not — and the cost was that 141 of the
    # 245 US Open match pages, every remaining round including the final, lost
    # the back link #2448 shipped. `tournament` therefore rides every answer
    # from here on; `advancement` and `props` do not, because those really do
    # need the pinned matchup.
    container = {
        "slug": slug,
        "title": spec["title"],
        "url": f"/tournaments/{slug}",
    }

    hub = await _hub_payload(slug, spec, db)

    matchup_key = ((hub.get("event_links") or {}).get("by_event") or {}).get(
        str(event_id)
    )
    if not matchup_key:
        # The tournament is on and this event is one of its sport keys, but no
        # registered fixture dereferences to it — which for a second-week match
        # is the ordinary state of affairs, not a fault: `tournament_slate`
        # mints `espn:{competition_id}` as the matchup key PRECISELY when the
        # register no longer holds the pairing, so a R16 event is linked
        # through `event_links.by_espn` and absent from `by_event` by design.
        #
        # Naming the container here is still not a guess. It rests on the sport
        # key alone, and the slate's ESPN-competition-id channel agrees through
        # a second, independent id. Never a name match on the two player names
        # sitting right there — that is precisely the shortcut
        # `tournament_event_link` exists to refuse, and it is not what this is.
        return {
            "event_id": event_id,
            "tournament": container,
            "reason": "NOT_IN_REGISTER",
        }

    register = load_register(slug, spec["season"])
    if register is None:
        logger.error("registered tournament %s has no readable register", slug)
        raise HTTPException(status_code=503, detail="Tournament register unavailable")
    register, _linked = await _with_link_overlay(slug, register)

    reg = TournamentRegister(register)
    matchup = next(
        (m for m in reg.matchups if str(m.get("matchup_key")) == matchup_key), None
    )
    if matchup is None:
        # The cached hub and the freshly loaded register disagree — the register
        # was replaced between the two reads. Not an error and not a guess.
        logger.warning(
            "event %s maps to matchup %s which the register no longer holds",
            event_id, matchup_key,
        )
        # Same split as above (#3697): the register moved under the fixture, not
        # under the container. The sport key still says which tournament this is.
        return {
            "event_id": event_id,
            "tournament": container,
            "reason": "REGISTER_MOVED",
        }

    # ── EACH PLAYER'S CHANCE OF REACHING EACH LATER ROUND (Alex's item 2) ──
    # A slice of the hub's own `grids`, so this strip and the tournament page's
    # playoff grid cannot print different numbers for one cell.
    advancement = build_advancement(
        hub.get("grids") or {},
        matchup=matchup,
        event_id=event_id,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        tournament_title=spec["title"],
        tournament_slug=slug,
    )

    # ── THE MATCH'S OTHER QUESTIONS (Alex's item 3) ──
    # UX-P149's grouping, kept whole: the register pins the match-winner
    # market's id, the source has already put every prop for the match in the
    # same `group_id`, and one indexed lookup returns them. No name comparison,
    # no time window, no category test.
    block = next(
        (
            b for b in (matchup.get("sources") or [])
            if isinstance(b, dict) and b.get("status") == "live"
        ),
        None,
    )
    winner_market_id = (block or {}).get("market_id")

    prop_markets: list[dict[str, Any]] = []
    if isinstance(winner_market_id, int):
        _group_id, prop_markets = await _load_match_group(
            db, winner_market_id=winner_market_id
        )

    outcome_ids = sorted(
        {
            side.get("outcome_id")
            for side in ((block or {}).get("sides") or {}).values()
            if isinstance(side, dict) and isinstance(side.get("outcome_id"), int)
        }
        | {
            outcome["outcome_id"]
            for market in prop_markets
            for outcome in market["outcomes"]
            if isinstance(outcome.get("outcome_id"), int)
        }
    )
    now = datetime.now(timezone.utc)
    prices = await _load_prices(db, outcome_ids, now=now)

    decided = build_results(
        register, results=await _espn_results(slug), prices=prices
    )
    result = next(
        (r for r in decided["matches"] if r.get("matchup_key") == matchup_key), None
    )

    detail = build_match_detail(
        register,
        matchup_key,
        prop_markets=prop_markets,
        prices=prices,
        result=result,
        now=now,
    )

    return {
        "event_id": event_id,
        # The SAME object the two bail-outs return (#3697), so the back link a
        # reader gets on a second-week match and the one they get on a R128
        # match cannot drift apart into two different URLs.
        "tournament": container,
        "matchup_key": matchup_key,
        "round": matchup.get("round"),
        "draw_label": (hub.get("grids") or {}).get(matchup.get("draw"), {}).get("label"),
        "advancement": advancement,
        # `detail` is None only when the register holds the matchup but cannot
        # render it as a row (an unmapped side). The extensions then carry the
        # advancement alone rather than 404-ing a page that is otherwise fine —
        # this is a SECTION of an event page, not the page.
        "props": (detail or {}).get("props") or [],
        "props_count": (detail or {}).get("props_count") or 0,
        "props_dropped": (detail or {}).get("props_dropped") or {},
        "decided": bool((detail or {}).get("decided")),
        "result": (detail or {}).get("result"),
        "broadcasts": reg.broadcasts,
        "generated_at": now.isoformat(),
    }


async def _hub_payload(
    slug: str,
    spec: dict[str, Any],
    db: AsyncSession,
    *,
    groups: tuple[str, ...] = SECTION_GROUPS,
) -> dict[str, Any]:
    """The tournament hub payload — built once, read by every tournament surface.

    Extracted from ``get_tournament`` by UX-P152 so the event page's tournament
    extensions come out of **the same object** the hub renders, rather than out
    of a second assembly that agrees today.  The advancement strip on
    ``/events/{id}`` is a slice of ``payload["grids"]``; if it were built from a
    second read of the register, one surface could print a cell the other did
    not, which is the divergence the standing ruling exists to prevent.

    It also means the extensions endpoint costs a dict lookup on a warm cache
    instead of a second full build.

    ``groups`` selects which section groups to assemble — see ``SECTION_FIRST``
    / ``SECTION_REST``.  Each is cached on its own key, so the phone's first
    screen never reads the grid out of Redis to throw it away, and the default
    is both: every caller that does not ask gets the whole payload it always
    got.
    """
    fragments: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for group in groups:
        cached = await _cache_get(slug, group)
        if cached is None:
            missing.append(group)
        else:
            fragments[group] = cached

    if missing:
        for group, fragment in (
            await _build_sections(slug, spec, db, groups=tuple(missing))
        ).items():
            await _cache_set(slug, fragment, group)
            fragments[group] = fragment

    # Merged in GROUP ORDER, never in the order the fragments were resolved —
    # `_merge_fragment` gives the earlier group the shared meta keys and that
    # rule only means anything if the sequence is fixed.
    payload: dict[str, Any] = {}
    for group in groups:
        fragment = fragments.get(group)
        if fragment:
            _merge_fragment(payload, fragment)
    return payload


async def _build_sections(
    slug: str,
    spec: dict[str, Any],
    db: AsyncSession,
    *,
    groups: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Assemble the requested section groups — one register read, shared.

    Returns ``{group: fragment}``.  Asking for both is one build with one
    ``now``, exactly as this route has always worked; asking for one builds only
    what that half needs.

    WHAT EACH HALF COSTS, IN THE ONLY CURRENCY THAT MATTERS HERE — the id list
    ``_load_prices`` and ``load_latest_observed_at`` walk (one top-1 index probe
    per outcome), measured against the committed 2026 register:

        board   118    both halves (the grid is keyed on the board's own rows)
        slate   232    both halves (a decided result prints its opening price)
        props     6    first
        reach   336    rest — the grid, and nothing else on the page

    So ``first`` is 356 probes and ``rest`` is ~600, against 692 for the whole
    page.  The saving on the FIRST request is the ship; the overlap is the price
    and it is stated in ``SECTION_FIRST``'s comment rather than hidden here.
    """
    want_first = SECTION_FIRST in groups
    want_rest = SECTION_REST in groups

    register = load_register(slug, spec["season"])
    if register is None:
        # A slug we claim to serve whose register will not load. Honest empty,
        # never a partial page assembled from whatever the database happened to
        # have — that is precisely what the register pattern replaces.
        logger.error("registered tournament %s has no readable register", slug)
        raise HTTPException(status_code=503, detail="Tournament register unavailable")

    # THE FIXTURES THE CENSUS FOUND NO MARKET FOR, LINKED SINCE (Q426).
    #
    # The draw census ran once, at the ceremony, and recorded `status:
    # "missing"` against all 96 R128 fixtures because nobody quotes a first
    # round before qualifying finishes. By the next morning Kalshi quoted every
    # one of them and the register still said there was no market, so the cards
    # rendered blank while we held the prices.
    #
    # `tournament_matchup_linker` re-asks that question on a beat and writes
    # what it finds; this reads it. Two properties make it safe to apply here
    # rather than being the fuzzy request-time matching this module's docstring
    # forbids: the resolution already happened in a task (this is a dict lookup
    # of a pinned `(market_id, outcome_id)`, the same kind of read as the
    # committed file), and `apply_resolved_links` may only replace a block the
    # register itself marked `missing`. A curated pin is untouchable from here.
    # Wrapped, and the bare `except` is the point: the overlay is an
    # optimisation over the committed truth and must never be a gate. Falling
    # back leaves the page exactly as the register wrote it, which is where it
    # stood before this existed — a linker outage costs numbers on some cards,
    # never the tournament page.
    linked = 0
    # THE AUTHORITY HALF OF THE SAME OVERLAY (lane1/047). One Redis read serves
    # both: `links` fills register blocks the census marked `missing`, and
    # `authority_links` prices the rows Q505 substitutes for a register pairing
    # the scoreboard contradicts. They are kept apart because
    # `apply_resolved_links` may only ever touch a register block, and an
    # authority link belongs to no register matchup.
    authority_links: dict[str, Any] = {}
    try:
        overlay = await read_links(slug)
        links = overlay.get("links") or {}
        raw_authority = overlay.get("authority_links")
        if isinstance(raw_authority, dict):
            authority_links = raw_authority
        register, linked = apply_resolved_links(register, links)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tournament link overlay failed for %s: %s", slug, exc)

    reg = TournamentRegister(register)
    board_outcome_ids = sorted(
        {
            block["outcome_id"]
            for player in reg.players
            for block in (player.get("sources") or [])
            if isinstance(block, dict) and isinstance(block.get("outcome_id"), int)
        }
    )
    # The slate's identities are pinned on the MATCHUPS, not on player entries —
    # a qualifying participant has no player-level source by construction. Both
    # sets are bounded by the register, so this stays two id-list lookups rather
    # than becoming a scan.
    slate_outcome_ids = reg.matchup_outcome_ids()
    # The outcome ids an AUTHORITY row will read (lane1/047). Not in the
    # register by construction — that is what makes the row an authority row —
    # so without this the resolved link would name a price the request never
    # loaded and the card would stay blank for a second, subtler reason.
    # Bounded by the overlay, which is bounded by the scoreboard.
    authority_outcome_ids = sorted(
        {
            outcome_id
            for block in authority_links.values()
            if isinstance(block, dict)
            for side in (block.get("sides") or {}).values()
            if isinstance(side, dict)
            for outcome_id in [side.get("outcome_id")]
            if isinstance(outcome_id, int) and not isinstance(outcome_id, bool)
        }
    )
    prop_outcome_ids = reg.prop_outcome_ids()
    # The playoff grid's 336 pinned reach identities (UX-P139). Bounded by the
    # register like every other set here, so adding a whole grid to this page
    # adds one more id list to an `IN (...)` and never a scan.
    reach_outcome_ids = reg.reach_outcome_ids()

    now = datetime.now(timezone.utc)
    # ONLY WHAT THE REQUESTED HALVES WILL READ (latency/135). The board and
    # slate ids are in both: the grid is keyed on the board's own rows, and a
    # decided result prints the opening price of its matchup. The 336 reaches
    # belong to the grid alone, and a first-screen request must not pay for
    # them — that is the largest single line in this build.
    wanted_ids: set[int] = set(board_outcome_ids) | set(slate_outcome_ids)
    if want_first:
        wanted_ids |= set(prop_outcome_ids) | set(authority_outcome_ids)
    if want_rest:
        wanted_ids |= set(reach_outcome_ids)
    prices = await _load_prices(db, sorted(wanted_ids), now=now)
    # Trend lines are a board feature. Loading series for the slate's ~130
    # outcomes would triple the per-request scan to draw nothing.
    #
    # And the GRID does not draw one. `build_playoff_grid` reads a board row's
    # identity and rank, never its trend, so a `rest`-only build skips this
    # query outright rather than loading 15 days of snapshots to serialise
    # nothing — see the guard in `test_tournament_sections_split.py`.
    series = (
        await _load_series(db, board_outcome_ids, now=now) if want_first else {}
    )

    # Re-key the loaded prices onto the register's identity tuple. Anything the
    # query returned that the register does not pin simply has no key here and
    # cannot reach a board.
    by_identity: dict[tuple, dict[str, Any]] = {}
    for player in reg.players:
        for block in player.get("sources") or []:
            if not isinstance(block, dict):
                continue
            loaded = prices.get(block.get("outcome_id"))
            if loaded is None:
                continue
            by_identity[
                (block.get("source"), block.get("market_id"), block.get("outcome_id"))
            ] = loaded

    # WHICH `events` ROW EACH FIXTURE IS (UX-P152, Alex's architecture note:
    # "I thought that tournaments were containers for related events"). One
    # id-anchored query, resolved BEFORE the slate is built so a match row
    # carries its event id and the card can route to the standard event page
    # like any other game card. Never a name match — see
    # `utils/tournament_event_link`.
    #
    # FIRST-SCREEN ONLY. Its consumer is the slate row's `event_id`; the
    # finished list reaches its events through `by_espn`, which `rest` resolves
    # for itself off the ids `build_results` produces.
    event_links = (
        await resolve_matchup_events(db, register)
        if want_first
        else {"by_event": {}, "by_matchup": {}, "reason_counts": {}}
    )

    # ONE READ, BOTH HALVES OF THE DAY (Q463). The cached ESPN payload carries
    # the decided matches AND the ones still to play; hoisted above the slate
    # because the slate needs the second half to know what is on. Still a single
    # Redis read — the order of play costs no fetch, no key and no beat, because
    # `sync_tournament_results` was already discarding it.
    espn = await _espn_results(slug)

    # BOTH HALVES NEED THE BOARDS, AND ONLY ONE OF THEM SERVES THEM. The grid is
    # keyed on the board's own rows — that is the "one ranking" property
    # `build_playoff_grid` documents — so a `rest`-only build still assembles
    # them, and then emits nothing but `grids` and `results`. It is pure Python
    # over prices already loaded; the query it would have added (the trend
    # series) is the one skipped above.
    base = build_boards(
        register, prices=by_identity, series_by_outcome=series, now=now
    )

    fragments: dict[str, dict[str, Any]] = {}

    if want_first:
        # ── THE FIRST SCREEN. The chart, the day's card, and the meta the page
        # frames them with. Everything a phone renders above the fold before a
        # reader has scrolled or tapped a tab.
        first: dict[str, Any] = dict(base)
        first["slate"] = build_slate(
            register,
            prices=prices,
            now=now,
            event_ids=event_links["by_matchup"],
            order_of_play=espn.get("order_of_play") or {},
            # THE COMPLETENESS CONTEXT, NOT DISCARDED (CERT-517). The cached
            # payload has always carried it; this route used to throw it away,
            # which is what let a half-read scoreboard pass itself off as the
            # whole one. A cached payload written before the flag existed reads
            # as `False` — the safe side, since an unknown-completeness map is
            # exactly the case where absence must not be trusted.
            order_of_play_complete=espn.get("order_of_play_complete") is True,
            authority_links=authority_links,
        )
        # WHICH SCOREBOARD THE CARD ABOVE WAS BUILT FROM (#3304). `live`,
        # `last_good` or `unavailable` — set by `_espn_results`, stamped here so
        # it travels on the same object as the counts it explains.
        #
        # `order_of_play_listed: 0` was already the empty-card alarm and it is
        # still ambiguous by itself: it reads the same whether the scoreboard
        # was silent or was never reached, and only the second one is anybody's
        # emergency. This says which, on the payload, without a log.
        first["slate"]["scoreboard"] = espn.get("scoreboard") or "unavailable"
        # THE FIXTURE SWAP (UX-P134). Empty until the draw ceremony latches
        # `draw_released`; populated by the same `ingest_tournament_draw.py` run,
        # so Thursday is a data change and not a deploy.
        #
        # First-screen despite the name: `lib/matchList.ts` joins these draw
        # slots with the slate into the ONE match list ruling 4 requires, so a
        # bracket arriving late would mean the day's card rendered twice — once
        # short, once complete. It costs 39 bytes.
        first["props"] = build_props(register, prices=prices, now=now)
        # THE FIXTURE SWAP (UX-P134). Empty until the draw ceremony latches
        # `draw_released`; populated by the same `ingest_tournament_draw.py` run,
        # so Thursday is a data change and not a deploy.
        #
        # First-screen despite the name: `lib/matchList.ts` joins these draw
        # slots with the slate into the ONE match list ruling 4 requires, so a
        # bracket arriving late would mean the day's card rendered twice — once
        # short, once complete. It costs 39 bytes.
        first["bracket"] = {
            draw: build_bracket(register, prices=prices, draw=draw)
            for draw in ("mens-singles", "womens-singles")
        }
        # Where to watch — a static per-tournament mapping, register-owned so it
        # can be corrected without a deploy. Served verbatim; there is nothing to
        # compute and nothing to get wrong at request time.
        first["broadcasts"] = reg.broadcasts
        # How many blank fixtures the overlay filled this request. Reported
        # rather than inferred: a page whose cards are dark because no market
        # exists and one whose cards are dark because the linker died look
        # identical from the outside, and that is the exact confusion that let
        # this ship broken for a day (gotcha #53).
        first["auto_linked_matchups"] = linked
        first["slug"] = slug
        first["title"] = spec["title"]
        first["subtitle"] = spec["subtitle"]
        # WHEN THE DRAW HAPPENS (Alex's item 1). The pre-draw panel says the date
        # and the time, not just that it has not happened yet.
        first["draw_release_at"] = spec["draw_release_at"]
        first["draw_release_label"] = spec["draw_release_label"]
        first["main_draw_starts_at"] = spec["main_draw_starts_at"]
        first["main_draw_label"] = spec["main_draw_label"]
        # NO SILENT CAPS. `by_event` is what `/by-event/{id}` reads; the reason
        # counts are what makes a fixture with no click-through a named gap
        # rather than a row that quietly stopped being a link.
        first["event_links"] = {
            # JSON has no integer keys and this payload round-trips through
            # Redis, so the id side is stringified HERE rather than at each
            # reader.
            "by_event": {str(k): v for k, v in event_links["by_event"].items()},
            "by_matchup": event_links["by_matchup"],
            "linked": len(event_links["by_matchup"]),
            "unresolved": event_links["reason_counts"],
        }

    if want_rest:
        # ── WHAT ARRIVES SECOND. 76% of this page's bytes and none of its first
        # screen: the playoff grid lives behind a tab tap, and the finished list
        # is below the day's card on every viewport we render.
        rest: dict[str, Any] = {
            # Self-describing when served alone. `_merge_fragment` gives `first`
            # the collision, so these two never displace the stamp on the
            # numbers a reader is looking at.
            "slug": slug,
            "generated_at": now.isoformat(),
        }
        # THE PLAYOFF GRID (UX-P139). Built server-side, from `reaches` and the
        # boards, because the amendment makes cell provenance a correctness
        # property: the grid must read the register and only the register, and a
        # client assembling cells from three payload sections cannot be held to
        # that. It also puts the two evals — column sums and monotonicity — next
        # to the data they judge instead of in a component.
        rest["grids"] = build_grids(
            register, boards=base.get("boards") or [], prices=prices, now=now
        )
        # DECIDED MATCHES, WITH THE SCORE (UX-P139, Alex's item 9). A separate
        # section rather than a field on the slate, because a slate structurally
        # cannot hold a finished match — see `build_results`.
        # `prices` so a finished match can print what the market said BEFORE it
        # (UX-P146, Alex on the UX-P145 artifact). No extra query: the matchup
        # outcome ids are already in the one `IN (...)` above, and the number
        # used is `opening_probability`, which is loaded on the same row.
        rest["results"] = build_results(register, results=espn, prices=prices)
    # ── THE ESPN COMPETITION CHANNEL, RESOLVED ONCE FOR THE HALVES BUILT ────
    #
    # TWO SHIPS MEET HERE, and the meeting is the whole of this rebase
    # (latency/135 onto ux/1048, 2026-09-03).
    #
    # #2693 step 2 built this channel for the FINISHED list: `build_slate`
    # retires a matchup the moment its match starts, so a finished match usually
    # has no matchup left to pin a market on, but its ESPN competition id
    # survives and `Event.espn_id` gives it a row to dereference to.
    #
    # ux/1048 then made the same channel answer for TODAY'S CARD. ux/1033's slate
    # walks the order of play, so a second-round match reaches the card the
    # ceremony register could never have held — and every one of those rows
    # carried `event_id: None`. Replayed over the live scoreboard at
    # 2026-09-03T20:16Z: **40 rows, 8 in play, 0 linked.** The reader was shown
    # the live match they were watching and then refused the tap.
    #
    # 🔴 THOSE TWO POPULATIONS LIVE IN DIFFERENT FRAGMENTS, which is why this
    # phase sits after both blocks instead of inside either one. The slate is the
    # first screen; the finished list is `rest`. Resolving inside `rest` — where
    # #2693 left it, and where this branch had it before the rebase — would mean
    # a `sections=first` request never stamped today's rows, and the tap ux/1048
    # exists to restore would be dead again for exactly the readers this split
    # was built to make faster. That is the silent failure of the merge and it is
    # what these two `if`s prevent.
    #
    # It asks about exactly the rows the REQUESTED groups published: a
    # first-screen request must not pay to dereference the finished list's ids,
    # and a `rest`-only request must not pay for the card's.
    #
    # ONE ID LIST, NOT TWO CALLS, when both halves are built together. ux/1048's
    # reason survives the split intact and matters more after it, not less: a
    # second round trip would buy nothing but a second chance to disagree with
    # the first about which event a fixture is.
    _comp_ids: list[Any] = []
    if want_first:
        _comp_ids += slate_competition_ids(first["slate"])
    if want_rest:
        _comp_ids += [
            match.get("espn_competition_id")
            for match in (rest["results"].get("matches") or [])
        ]
    espn_links = await resolve_espn_competition_events(
        db, _comp_ids, spec.get("sport_keys") or ()
    )

    if want_first:
        # Stamped straight away, so nothing between here and the response can
        # read a slate row's `event_id` and get the pre-link answer.
        apply_espn_event_links(first["slate"], espn_links["by_espn"])
        # HOW MANY OF TODAY'S ROWS THAT CHANNEL ACTUALLY OPENED (ux/1048).
        # `espn_linked` counts the map, and the map is resolved for the finished
        # list AND the slate together — so it can be healthy while every row on
        # the card still dead-ends. This is the one that answers the reader's
        # question, and `slate.scoreboard_pairings` is its denominator: the two
        # far apart during play is the alarm.
        #
        # It rides `first`, because the rows it counts do. A phone that asks only
        # for its first screen still gets the number that describes what it was
        # served, rather than a count arriving with the half below the fold.
        first["event_links"]["slate_linked"] = first["slate"].get(
            "scoreboard_linked", 0
        )

        # A BLANK ROW FALLS BACK TO THE NUMBER ITS OWN MATCH PAGE SHOWS (#3729).
        #
        # The two US Open quarterfinals rendered blank on 2026-09-07 while the
        # event page each one links to printed the sportsbook consensus of 7
        # books — `priced` meant "a prediction market was pinned to this
        # matchup", and a quarterfinal's market is pinned LAST because its
        # feeders have to resolve first. `apply_event_blend_slate` says why that
        # makes the deepest round of every tournament the likeliest to be empty.
        #
        # THE NUMBER IS RESOLVED HERE, THROUGH THE HERO'S OWN FUNCTION.
        # `compute_aggregate_probability(event, event.status)` is what
        # `/api/events/{id}` calls, so the card and the page it links to cannot
        # answer the same question differently — which is the whole defect,
        # arriving from the other side. `effective_source_weights` names the
        # readings that fed it: an empty list means the blend came from a
        # fallback tier (ESPN's model, or `opening_*`) and the rung refuses.
        #
        # BOUNDED BY THE ROWS THAT ARE ACTUALLY BLANK, and by the ids the link
        # phase above ALREADY resolved — nothing is queried to FIND an event. On
        # the payload that prompted this, 2 rows of 13; a card with nothing blank
        # on it pays for no query at all.
        _blank_event_ids = sorted(
            {
                int(row["event_id"])
                for row in (first["slate"].get("matches") or [])
                if not row.get("priced") and isinstance(row.get("event_id"), int)
            }
        )
        _slate_events: dict[int, dict[str, Any]] = {}
        if _blank_event_ids:
            _blank_rows = await db.execute(
                select(Event).where(Event.id.in_(_blank_event_ids))
            )
            _slate_events = {
                int(_event.id): event_blend_view(_event)
                for _event in _blank_rows.scalars().all()
            }
        apply_event_blend_slate(
            first["slate"], rows_by_event=_slate_events, now=now
        )

    if want_rest:
        # THE BOOKS RUNG OF THE PRE-MATCH LADDER (#2747, ux/1036 Tier A).
        #
        # Alex: "opening = Kalshi -> Polymarket -> sportsbook blend, labelled by
        # source. Never blank when any pre-match reading exists." ux/1034 A3
        # shipped the honesty half and left the number, because `opening_*` lives
        # on the EVENT and `by_matchup` cannot reach a row the register no longer
        # carries a matchup for — which is the row Alex read.
        #
        # `by_espn` above IS that missing channel, and it landed for a different
        # reason (#2693 step 2, the finished list's dead-end links). Nothing new
        # is queried to FIND the events; this loads the two opening columns off
        # the ids that channel already resolved, bounded by them.
        #
        # BOUNDED BY THE RESULTS' OWN IDS, NOT THE WHOLE MAP (ux/1048). `by_espn`
        # now answers for the slate too, and `apply_books_prematch` below reads it
        # only for `results.matches` — so taking `.values()` wholesale would load
        # ~40 more event rows per request that nothing reads, and would keep
        # growing with the card. The map is a lookup table here; the population is
        # the finished list.
        #
        # The filter is NOT redundant just because a `rest`-only build resolves
        # only the finished list's ids. On the default request — the one every
        # existing caller makes — the map carries the card as well, so removing
        # this would silently restore the cost ux/1048 measured and removed.
        _result_comps = {
            str(match.get("espn_competition_id"))
            for match in (rest["results"].get("matches") or [])
            if match.get("espn_competition_id")
        }
        _opening_ids = sorted(
            {
                int(event_id)
                for comp_id, event_id in espn_links["by_espn"].items()
                if comp_id in _result_comps
            }
        )
        _openings: dict[int, dict[str, Any]] = {}
        if _opening_ids:
            _rows = await db.execute(
                select(
                    Event.id,
                    Event.home_team_name,
                    Event.away_team_name,
                    Event.opening_home_probability,
                    Event.opening_away_probability,
                ).where(Event.id.in_(_opening_ids))
            )
            for _id, _home, _away, _oh, _oa in _rows.all():
                _openings[int(_id)] = {
                    "home_team_name": _home,
                    "away_team_name": _away,
                    "opening_home_probability": _oh,
                    "opening_away_probability": _oa,
                }
        apply_books_prematch(
            rest["results"], by_espn=espn_links["by_espn"], openings=_openings
        )
        # THE SECOND CHANNEL, KEPT SEPARATE. Not folded into `by_matchup`: the
        # two are keyed on different identifiers, and a reader (or a sentinel)
        # asking "how many finished matches link, and through what" must be able
        # to tell an authority-id link from a market link. Its refusals are
        # counted on their own terms for the same reason — `ESPN_ID_AMBIGUOUS`
        # above zero is a step-2 regression, and it would be invisible summed
        # into a total.
        #
        # It travels in the SAME fragment as the list it addresses. That is why
        # `_merge_fragment` merges `event_links` rather than overwriting it: the
        # finished list and its links must never be able to arrive apart.
        #
        # These three keys and `first`'s five are DISJOINT, which is what makes
        # the shallow merge correct. `by_espn` must not be split across both
        # fragments — `_merge_fragment` would overwrite rather than union it, and
        # the finished list would lose whichever half arrived first.
        rest["event_links"] = {
            "by_espn": espn_links["by_espn"],
            "espn_linked": len(espn_links["by_espn"]),
            "espn_unresolved": espn_links["reason_counts"],
        }

    # ASSEMBLED LAST, after the link phase above has finished with both halves.
    # `fragments` would hold these same dict objects either way, so inserting
    # them earlier also "works" — but then the correctness of this function would
    # rest on aliasing, and the first person to write `dict(first)` above would
    # break the slate's `event_id` stamping with a change that reads as a no-op.
    if want_first:
        fragments[SECTION_FIRST] = first
    if want_rest:
        fragments[SECTION_REST] = rest

    return fragments


def _requested_groups(sections: Optional[str]) -> tuple[str, ...]:
    """Parse `?sections=` — absent means the whole payload, as it always has.

    An unknown name is a **400 and not a shrug**. The two consumers of this
    parameter are our own document boot script and our own page effect; a
    typo'd section that silently served the full payload would look like a
    working split in every measurement while shipping none of the saving
    (gotcha #53 — a response shape that cannot tell "everything" from "you asked
    for something I do not have").
    """
    if sections is None:
        return SECTION_GROUPS
    names = tuple(part.strip() for part in sections.split(",") if part.strip())
    unknown = [name for name in names if name not in SECTION_GROUPS]
    if unknown or not names:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown section(s) {unknown or ['']}; "
                f"valid: {', '.join(SECTION_GROUPS)}"
            ),
        )
    # Deduplicated, and always in build order so the merge rule is stable
    # whatever order the caller wrote them in.
    return tuple(group for group in SECTION_GROUPS if group in names)


@router.get("/{slug}")
async def get_tournament(
    slug: str,
    sections: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    spec = REGISTERED_TOURNAMENTS.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"No registered tournament '{slug}'")
    return await _hub_payload(slug, spec, db, groups=_requested_groups(sections))
