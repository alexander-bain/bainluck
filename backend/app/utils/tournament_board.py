"""Build the ``/tournaments/{slug}`` championship boards from a committed register.

Pure logic: every input is a plain dict or list, so the whole board — ranking,
blending, trend assembly and the freshness verdict — is testable without a
database.  The route in ``app/routes/tournaments.py`` does the loading and
nothing else.

Three doctrines are enforced here rather than documented:

1. **A market not in the register does not render.**  The board is built by
   walking the *register* and looking up loaded rows, never by walking loaded
   rows and looking up the register.  An outcome the register does not pin
   cannot reach a board even if the query returns it, and
   ``check_rendered_rows`` re-asserts that at the boundary rather than trusting
   the loop above it.

2. **The blend is the product.**  One number per player, produced by the
   repo's existing ``blend_with_verdict`` — not a second aggregator.  Sources
   travel with the row so the UI can whisper "2 sources"; they are never a
   comparison surface.

3. **Staleness is never rendered as a live number.**  This is the whole reason
   ``probability_is_live`` exists as a separate field from ``probability``.
   #2199 has the US Open outright fields price-dark for 8-32 days, and the
   failure mode that matters is not an empty board — it is a board that prints
   July's 52% in the same confident type it would print a live 52%.  So the
   payload carries the observation time on every row, the age on every board,
   and a boolean the client cannot round past.  We show that we do not know,
   rather than showing July and calling it now.

   **Freshness is a property of the WHOLE blend, so it is an AND over the
   contributors, not a MAX over their timestamps** (UX-P135, cert
   ``C-USOPEN-DAY3-TIER2``).  The first version of this module computed row
   freshness from the *newest* contributor while ``blend_with_verdict``
   consumed every contributor regardless of age, so a 1h Kalshi price beside a
   20d Polymarket price published a blended 0.42 as ``probability_is_live:
   true``.  The blended number is one hour old in none of its parts and twenty
   days old in one of them; "one hour ago" was never true of it.  A row is live
   only when *every* value inside its published blend is live, and the row's
   own ``observed_at`` / ``age_hours`` describe the **governing** (oldest)
   contributor — the strongest claim that is true of the number as printed.
   The freshest reading is still visible, as ``freshest_observed_at``, because
   suppressing it would hide that half the row moved today; it is an extra
   fact, never the verdict.

Trend lines are the real daily means and nothing else — no smoothing, no
interpolation across missing days, no curve fitting.  Movement IS the product
(charter design doctrine), and a smoother is a machine for hiding it.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from app.utils.futures_source_merge import blend_with_verdict
from app.utils.market_liquidity import LIQUIDITY_UNKNOWN, thinnest_liquidity
from app.utils.tournament_register import (
    STALE_PRICE_HOURS,
    TournamentRegister,
    check_rendered_rows,
    player_image,
    player_role,
)

logger = logging.getLogger(__name__)

# Past this the board is not merely stale, it is dark: nobody has seen a price
# in two days and the honest presentation stops being "as of 9 hours ago" and
# becomes "prices paused".  Both states suppress `probability_is_live`; the
# split exists so the UI can word them differently, not so one of them can be
# treated as live.
DARK_PRICE_HOURS = 48.0

# How much history a trend line may carry.  Bounded because the series query is
# per-request and the register pins up to ~160 outcomes.
TREND_DAYS = 30

# ── THE SECOND, FINER SERIES (ux/1144 (a), #4173) ────────────────────────────
#
# `trend` is one point per DAY and it always was.  On the 52px sparkline that is
# right; on the `ContenderChart` it is the whole defect ux reported — the men's
# leader draws 23 vertices across a month, the `1D` chip has one point and
# cannot draw at all, and a title race that moved 42pp in an afternoon renders
# as one step.  MEASURED on production 9 Sep: the four US Open outright markets
# hold 32,801 snapshots over 14 days for 143 outcomes — 260 readings per
# outcome, of which the daily mean publishes 15.  We were serving 6% of what we
# hold.
#
# So a second series, at the resolution the capture rail actually runs at.  The
# `:50` futures refresh writes both venues within the same minute (measured:
# 5,566 of 7,150 writes at minute 50, every one of the rest inside the same
# hour), so an HOUR bucket is a snapshot bucket — 260 readings collapse to 255
# buckets, not to 15.  Going finer than an hour would buy nothing but rows.
#
# Both series are kept because they are read by two different pictures, not
# because one is transitional: 250 vertices in a 52px sparkline is noise, and 15
# vertices in an 817px chart is a staircase.  One rule, two resolutions.
TREND_FINE_DAYS = 14

# The hard ceiling on points in one fine series, BY CONSTRUCTION rather than by
# a `[-N:]` slice: an hour bucket over `TREND_FINE_DAYS` cannot exceed this many
# points however often the venues are polled, so a capture-rail change that
# doubled the poll rate would not add a single point here.  A slice would have
# been a bound that only looks like one — the row cap in the route is where a
# scan is bounded, and the two are deliberately different mechanisms.
TREND_FINE_MAX_POINTS = TREND_FINE_DAYS * 24

# ── WHEN A DRAW IS DOWN TO TWO, THE BOARD IS NOT A SECOND OPINION (#5893) ────
#
# "Who wins the final" and "who wins the title" are the same question once two
# players are left, and on men's final day the hub answered it twice, three rows
# apart on one screen: NEXT UP said Zverev 58%, the Men's Singles board below it
# said 57%.  Both renders were faithful; the payload carried two numbers.
#
# THE CAUSE IS NOT ROUNDING AND IT IS NOT THE OVERROUND.  Measured on production
# 2026-09-13T11:14Z: the board's men's rows are the OUTRIGHT markets blended —
# kalshi 0.565 + polymarket 0.5795 → 0.57225 — while the slate's final carries
# the linked EVENT's blend, 0.575 over 3 sources, which is also what
# `/api/events/15310688` prints.  Renormalising the board does not reconcile
# them: 0.57225 / 1.00825 is 0.5676, still 57.  They are two different markets
# priced two different ways, and only one of them is the number the rest of the
# site answers this question with.
#
# So the board DEFERS.  Alex's standing ruling is one number per question and
# the blend is the product; the event blend is that number, the same one the
# match page and the card already show, so promoting it here removes a
# contradiction rather than inventing a third value.
#
# IT DEFERS ONLY WHEN THE MATCH NUMBER IS ITSELF LIVE.  Every field this
# overlay writes on the row — `price_state`, `stale_sources`, `mixed_freshness`
# — is then true by construction, and no metadata has to be invented for a
# number whose provenance the board can no longer describe.  A stale final
# leaves the board exactly as it was: two honestly-labelled numbers beat one
# confident wrong one, which is this module's whole doctrine.
#
# NOT IN SCOPE, STATED SO IT IS NOT MISTAKEN FOR AN OVERSIGHT: the playoff
# grid's `title` column is the same outright number and still reads 0.57225.
# It is built in the `rest` fragment, before the slate's blends are applied and
# on a request that need not build a slate at all, so reconciling it here would
# make the grid's answer depend on which sections a client asked for.  Recorded
# on #5893.
# The register's own key for a draw's last round (`tournament_register.ROUNDS`),
# which is also the vocabulary the slate publishes: `authority_round` maps
# ESPN's "Final" through `espn_round_key` before it reaches a card, so this is a
# compare against one spelling and not against a family of them. Written as a
# literal rather than as `ROUNDS[-1]` because a round appended after the final
# would silently redefine a derived one; the two records are held level by a
# guard test instead.
FINAL_ROUND = "F"

#: What a row's published probability is an answer to.  Machine-only: no client
#: renders it, and it exists so a probe (or the guard suite) can tell a deferred
#: row from an outright one without re-deriving the rule.
PROBABILITY_BASIS_OUTRIGHT = "outright"
PROBABILITY_BASIS_FINAL = "final-match"

DRAW_LABELS: dict[str, str] = {
    "mens-singles": "Men's Singles",
    "womens-singles": "Women's Singles",
    # All five draws render (#4124). ESPN carries all three doubles draws'
    # matches and results under these exact slugs, and the page shows them
    # behind its Doubles pill. No doubles OUTRIGHT market exists — measured
    # 2026-09-09, `KXMIXEDDOUBLES` is the only doubles "Tournament Champion"
    # series Kalshi runs and it has zero open markets — so a doubles draw has
    # matches and no championship board. (The line here used to read "No
    # doubles market exists at either source", censused 2026-08-26 before the
    # doubles draw was made. It was false within the week and read as a
    # standing fact for two.)
    "mens-doubles": "Men's Doubles",
    "womens-doubles": "Women's Doubles",
    "mixed-doubles": "Mixed Doubles",
}


def draw_label(draw: str) -> str:
    return DRAW_LABELS.get(draw, draw.replace("-", " ").title())


def _age_hours(observed_at: Optional[datetime], now: datetime) -> Optional[float]:
    if observed_at is None:
        return None
    return (now - observed_at).total_seconds() / 3600.0


def price_state(age_hours: Optional[float]) -> str:
    """``live`` | ``stale`` | ``dark`` — and ``dark`` is what "never seen" means.

    ``None`` age is not "fresh, unknown"; it is the strongest possible evidence
    that nothing has been observed.  Reading an absent timestamp as anything but
    dark is gotcha #53's shape — an empty answer taken for a good one.
    """
    if age_hours is None:
        return "dark"
    if age_hours <= STALE_PRICE_HOURS:
        return "live"
    if age_hours <= DARK_PRICE_HOURS:
        return "stale"
    return "dark"


def governing_age_hours(
    observed_ats: list[Optional[datetime]], now: datetime
) -> Optional[float]:
    """The age of the OLDEST contributor — ``None`` when any was never seen.

    This is the whole per-contributor AND, and it is one line because
    ``price_state`` is monotone in age: the oldest contributor is by
    construction the one in the worst state, and an absent timestamp is older
    than any timestamp (it reads ``dark``, gotcha #53).  So there is no
    severity table to keep in step with the thresholds — feeding this into
    ``price_state`` yields exactly ``worst(price_state(each))``.

    An empty list is ``None``: no contributors is not fresh.
    """
    if not observed_ats:
        return None
    if any(observed is None for observed in observed_ats):
        return None
    return max(_age_hours(observed, now) or 0.0 for observed in observed_ats)


def freshest_observation(
    observed_ats: list[Optional[datetime]],
) -> Optional[datetime]:
    """The newest reading among the contributors — an extra fact, not a verdict.

    Kept visible so a mixed row can say "one source moved an hour ago" while
    still refusing to call itself live.  It is deliberately a separate field
    from ``observed_at`` so that a client which reads only the obvious name
    gets the pessimistic answer.
    """
    seen = [observed for observed in observed_ats if observed is not None]
    return max(seen) if seen else None


def _merge_bucketed_series(
    series_by_outcome: dict[int, list[tuple[str, float]]],
    contributors: list[tuple[str, int]],
    *,
    key: str,
) -> list[dict[str, Any]]:
    """One point per BUCKET THAT WAS ACTUALLY OBSERVED, blended by the SAME rule.

    ``key`` names the field the bucket travels under — ``date`` for the daily
    series, ``at`` for the hourly one.  It is ONE function rather than two
    because the whole doctrine below is about there being one rule; a second
    copy for the finer bucket would be a second place for that rule to drift.
    The two callers differ in bucket width and in nothing else.

    Each day is run through ``blend_with_verdict`` exactly as the headline is,
    rather than meaned.  With two equal-weight sources the two rules agree
    numerically today, so this looks like a distinction without a difference —
    it is not.  The moment the divergence gate fires on a day, a mean would
    print a number the headline rule has explicitly refused to print, and the
    trend line would be a different KIND of value from the number above it.
    That is #1844's class: a raw figure and a blend rendered as if comparable.
    One question, one rule, at every point in time.

    Buckets with no reading are absent, not zero and not carried forward: a gap
    in the line is a gap in the data, and filling it would manufacture exactly
    the confidence this module exists to refuse.

    A bucket in which only SOME of the row's contributors reported still
    publishes — the same as the daily series has always done — and at hourly
    resolution that is a measured 31 of 267 buckets on Alcaraz, worth a median
    0.5pp step against a p95 real step of 2.0pp.  It is not filtered out,
    because an AND here would blank the whole line the day one venue's cadence
    shifted by a minute past the hour: a rule that can silently publish nothing
    is worse than a rule that publishes a half-pp wobble.  The row's own
    `sources` / `stale_sources` are where a reader learns which venues are
    behind it; a trend point is a shape, not a verdict.
    """
    by_bucket: dict[str, list[dict[str, Any]]] = {}
    for source, outcome_id in contributors:
        for bucket, value in series_by_outcome.get(outcome_id, []):
            by_bucket.setdefault(bucket, []).append(
                {"source": source, "probability": float(value)}
            )

    points: list[dict[str, Any]] = []
    for bucket, rows in sorted(by_bucket.items()):
        value = blend_with_verdict(rows)[0]
        if value is None:
            continue
        points.append({key: bucket, "probability": round(value, 6)})
    return points


def _rank_rows(rows: list[dict[str, Any]]) -> None:
    """Rank by the blend, highest first, stamping ``rank`` in place.

    Rows without a probability (settled) sort last — they are results, not
    standings.  One function because ``apply_final_match_blend`` can change the
    number a row is ranked on, and a second copy of this key is a second place
    for the ordering to drift.
    """
    rows.sort(key=lambda r: (r["probability"] is None, -(r["probability"] or 0.0)))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index


def _board_summary(rows: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """The board-level freshness verdict and its counts, from the rows as served.

    Shared with ``apply_final_match_blend`` rather than recomputed there: an
    overlay that changed a row's timestamps and left the banner describing the
    rows it replaced would be exactly the defect #5893's second half reported.

    The BOARD reports the newest thing anyone has seen — the strongest true
    claim about the page as a whole, and deliberately not an AND.  Rows carry
    their own verdict; making one 30-day row paint the banner over 43 live ones
    would retire the banner as a signal (the crying-wolf failure), and every row
    is individually honest already.  It reads ``freshest_observed_at`` because
    ``observed_at`` is the governing contributor's, which would make this a
    max-of-oldest.
    """
    observed = [
        datetime.fromisoformat(r["freshest_observed_at"])
        for r in rows
        if r.get("freshest_observed_at")
    ]
    board_newest = max(observed) if observed else None
    board_age = _age_hours(board_newest, now)
    return {
        # Quantified rather than described: how much of this board is not a live
        # number, and how much of it is a blend of legs of different ages. Both
        # are zero on a healthy board.
        "rows_not_live": sum(
            1
            for r in rows
            if r["probability"] is not None and not r["probability_is_live"]
        ),
        "mixed_freshness_rows": sum(1 for r in rows if r["mixed_freshness"]),
        "price_state": price_state(board_age),
        "newest_observed_at": board_newest.isoformat() if board_newest else None,
        "age_hours": round(board_age, 2) if board_age is not None else None,
    }


def _row_state(block: dict[str, Any]) -> str:
    """The register's status translated to the render contract's vocabulary."""
    status = block.get("status")
    if status == "settled":
        # "Settled means settled" — the terminal result IS the state, and the
        # render contract forbids a probability beside it.
        return str(block.get("terminal_result") or "settled")
    if status == "missing":
        return "missing"
    return "live"


def build_boards(
    register: dict[str, Any],
    *,
    prices: dict[tuple, dict[str, Any]],
    series_by_outcome: Optional[dict[int, list[tuple[str, float]]]] = None,
    fine_series_by_outcome: Optional[dict[int, list[tuple[str, float]]]] = None,
    now: datetime,
) -> dict[str, Any]:
    """Assemble the full page payload.

    ``prices`` is keyed by the register's own identity tuple
    ``(source, market_id, outcome_id)`` and carries ``{"probability": float |
    None, "observed_at": datetime | None}``.  Keying on the register's tuple
    rather than on a name is the point: there is no matching on the serving
    path, so there is nothing to get wrong at request time.
    """
    series_by_outcome = series_by_outcome or {}
    # Absent, not empty-as-a-value: a caller that loads no fine series (the
    # `rest`-only build) serves `trend_hourly: []`, exactly as it already serves
    # `trend: []`. Two shapes for "no points" would be one more thing a client
    # has to branch on.
    fine_series_by_outcome = fine_series_by_outcome or {}
    reg = TournamentRegister(register)

    boards: list[dict[str, Any]] = []
    rendered_rows: list[dict[str, Any]] = []

    # Draw order is the register's own, deduplicated — so a register that only
    # carries one draw produces one board rather than an empty second one.
    # CONTENDERS decide which boards exist: a draw present only as qualifying
    # participants has no championship board to build.
    draws: list[str] = []
    for player in reg.players:
        draw = player.get("draw")
        if (
            isinstance(draw, str)
            and draw not in draws
            and player_role(player) == "contender"
        ):
            draws.append(draw)

    for draw in draws:
        rows: list[dict[str, Any]] = []
        unpriced = 0

        # `board_players`, never `draw_players`. After UX-P132's second
        # population pass the register carries qualifying participants whose
        # only price is P(wins this match); ranking one of those against
        # P(wins the tournament) would put a first-round qualifier above
        # Alcaraz on the men's board with a number that is not wrong so much
        # as an answer to a different question.
        for player in reg.board_players(draw):
            blend_rows: list[dict[str, Any]] = []
            source_views: list[dict[str, Any]] = []
            contributors: list[tuple[str, int]] = []
            # Every contributor's OWN observation time, in blend order. The
            # list — not a running max — is the fix: the verdict needs the
            # oldest, the display needs the newest, and a max destroys one of
            # them at the moment it is taken.
            contributor_times: list[Optional[datetime]] = []
            # And every contributor's OWN book grade, for the same reason: the
            # row is as solid as its THINNEST leg, so the list has to survive
            # long enough for `thinnest_liquidity` to take the worst of it.
            contributor_liquidity: list[Optional[str]] = []
            contributor_liquidity_reasons: set[str] = set()
            settled_result: Optional[str] = None

            for block in player.get("sources") or []:
                if not isinstance(block, dict):
                    continue
                state = _row_state(block)
                identity = (
                    block.get("source"),
                    block.get("market_id"),
                    block.get("outcome_id"),
                )
                loaded = prices.get(identity) or {}
                probability = loaded.get("probability")
                observed_at = loaded.get("observed_at")

                if state == "missing":
                    # A registered identity with nothing behind it. It is not a
                    # zero and it is not an error; it simply has no number.
                    rendered_rows.append(
                        {
                            "entity_key": player.get("entity_key"),
                            "source": block.get("source"),
                            "state": "missing",
                            "probability": None,
                        }
                    )
                    continue

                if state != "live":
                    settled_result = state
                    rendered_rows.append(
                        {
                            "entity_key": player.get("entity_key"),
                            "source": block.get("source"),
                            "state": state,
                            "probability": None,
                        }
                    )
                    continue

                if probability is None:
                    # Registered live, but the load returned no price. Do not
                    # invent one and do not let it into the blend.
                    continue

                probability = float(probability)
                rendered_rows.append(
                    {
                        "entity_key": player.get("entity_key"),
                        "source": block.get("source"),
                        "state": "live",
                        "probability": probability,
                    }
                )
                blend_rows.append(
                    {"source": block.get("source"), "probability": probability}
                )
                source_age = _age_hours(observed_at, now)
                source_views.append(
                    {
                        "source": block.get("source"),
                        "probability": round(probability, 6),
                        "observed_at": observed_at.isoformat() if observed_at else None,
                        # Each contributor answers for its own freshness. The
                        # row's verdict is the AND of these, and a UI that
                        # wants to name the stale one reads them here rather
                        # than re-deriving a threshold client-side.
                        "age_hours": round(source_age, 2) if source_age is not None else None,
                        "price_state": price_state(source_age),
                        # How thin THIS venue's book is (UX-P157). Per source for
                        # the same reason `price_state` is: the row's verdict is
                        # the worst of them, and a UI that wants to name the thin
                        # leg reads it here rather than re-deriving it.
                        "liquidity": (loaded.get("liquidity") or {}).get("level"),
                    }
                )
                contributor_liquidity.append((loaded.get("liquidity") or {}).get("level"))
                contributor_liquidity_reasons.update(
                    (loaded.get("liquidity") or {}).get("reasons") or []
                )
                if isinstance(block.get("outcome_id"), int):
                    contributors.append((str(block.get("source")), block["outcome_id"]))
                contributor_times.append(observed_at)

            if settled_result is not None and not blend_rows:
                # Settled means settled: a result, never a probability.
                rows.append(
                    {
                        "entity_key": player.get("entity_key"),
                        "display_name": player.get("display_name"),
                        "seed": player.get("seed"),
                        "country": player.get("country"),
                        "image": player_image(player),
                        "state": settled_result,
                        "probability": None,
                        # No probability, so nothing to be an answer to. Present
                        # rather than absent so every row has one shape.
                        "probability_basis": None,
                        "probability_is_live": False,
                        "observed_at": None,
                        "age_hours": None,
                        "price_state": "dark",
                        "freshest_observed_at": None,
                        "freshest_age_hours": None,
                        "stale_sources": [],
                        "mixed_freshness": False,
                        "source_count": 0,
                        "sources": [],
                        "blend_rule": None,
                        "divergent": False,
                        "trend": [],
                        "trend_hourly": [],
                        "trend_delta": None,
                        # Settled means settled: there is no live book behind a
                        # result to grade, and `unknown` draws nothing. Present
                        # rather than absent so every row has one shape.
                        "liquidity": LIQUIDITY_UNKNOWN,
                        "liquidity_reasons": [],
                    }
                )
                continue

            if not blend_rows:
                unpriced += 1
                continue

            blend, divergence, rule = blend_with_verdict(blend_rows)
            if blend is None:
                unpriced += 1
                continue

            # THE AND. `age` is the governing (oldest) contributor's, so
            # `row_state` is the worst contributor's state and the row cannot
            # read live while any value inside its blend is stale or dark.
            age = governing_age_hours(contributor_times, now)
            row_state = price_state(age)
            newest = freshest_observation(contributor_times)
            freshest_age = _age_hours(newest, now)
            stale_sources = [
                view["source"]
                for view in source_views
                if view["price_state"] != "live"
            ]
            trend = _merge_bucketed_series(
                series_by_outcome, contributors, key="date"
            )
            # `trend_delta` stays the DAILY series' end-to-end move and is not
            # recomputed from the finer one. It is the number beside the
            # sparkline it belongs to, and a delta measured over a 14-day window
            # printed next to a 30-day line would be two spans on one row.
            trend_hourly = _merge_bucketed_series(
                fine_series_by_outcome, contributors, key="at"
            )
            trend_delta = (
                round(trend[-1]["probability"] - trend[0]["probability"], 6)
                if len(trend) >= 2
                else None
            )

            rows.append(
                {
                    "entity_key": player.get("entity_key"),
                    "display_name": player.get("display_name"),
                    "seed": player.get("seed"),
                    "country": player.get("country"),
                    "image": player_image(player),
                    "state": "live",
                    "probability": round(blend, 6),
                    # "Who wins the title", priced by this draw's outright
                    # markets — until `apply_final_match_blend` says otherwise.
                    "probability_basis": PROBABILITY_BASIS_OUTRIGHT,
                    # The field the client cannot round past. See module docstring.
                    "probability_is_live": row_state == "live",
                    # GOVERNING, not newest: "as of when is this whole number
                    # true". A row whose Polymarket leg is 20 days old is a
                    # 20-day-old number, however recently Kalshi moved.
                    "observed_at": (
                        min(t for t in contributor_times if t is not None).isoformat()
                        if age is not None
                        else None
                    ),
                    "age_hours": round(age, 2) if age is not None else None,
                    "price_state": row_state,
                    # The freshest reading, kept visible so partial movement is
                    # not hidden — an extra fact beside the verdict, never it.
                    "freshest_observed_at": newest.isoformat() if newest else None,
                    "freshest_age_hours": (
                        round(freshest_age, 2) if freshest_age is not None else None
                    ),
                    # Named, so the UI can say WHICH leg is old rather than
                    # muting the row with no explanation.
                    "stale_sources": stale_sources,
                    "mixed_freshness": 0 < len(stale_sources) < len(source_views),
                    "source_count": len(blend_rows),
                    "sources": source_views,
                    "blend_rule": rule,
                    "divergent": divergence is not None,
                    "trend": trend,
                    # ux/1144 (a). Same rule, same gaps, one point per HOUR
                    # observed — `at` is a full ISO-8601 instant, deliberately
                    # NOT named `date`, so a client that reuses the day parser
                    # `new Date(`${p.date}T00:00:00Z`)` fails at the type
                    # boundary instead of quietly producing `Invalid Date`.
                    "trend_hourly": trend_hourly,
                    "trend_delta": trend_delta,
                    # ── HOW THIN THE MARKET BEHIND THIS ROW IS (UX-P157,
                    # #2256). The AND over contributors, exactly like `age`
                    # above: one number, answering for every book inside it.
                    "liquidity": thinnest_liquidity(contributor_liquidity),
                    "liquidity_reasons": sorted(contributor_liquidity_reasons),
                }
            )

        _rank_rows(rows)

        boards.append(
            {
                "draw": draw,
                "label": draw_label(draw),
                "rows": rows,
                "contenders": len(rows),
                "unpriced": unpriced,
                # How many rows on this board publish the final's blend instead
                # of their own outright (#5893). Zero here BY CONSTRUCTION —
                # `build_boards` has no slate to read — and present rather than
                # absent so "the overlay ran and promoted nothing" and "the
                # overlay never ran" are not the same payload (gotcha #53).
                "final_deferred_rows": 0,
                **_board_summary(rows, now),
            }
        )

    # The register's own render-boundary check, run on the rows we are about to
    # serve rather than on a description of them. A finding here means this
    # module built something the register forbids; it is our bug, so it is loud.
    findings = check_rendered_rows(register, rendered_rows)
    if findings:
        logger.error(
            "tournament board render-contract findings for %s-%s: %s",
            reg.tournament,
            reg.season,
            findings,
        )

    return {
        "tournament": reg.tournament,
        "season": reg.season,
        "register_version": reg.version,
        "register_generated_at": reg.generated_at,
        "draw_released": reg.draw_released,
        "boards": boards,
        "render_findings": findings,
        "generated_at": now.isoformat(),
    }


def _aware(stamp: Any) -> Optional[datetime]:
    """Parse a published ISO-8601 instant, or ``None``.

    A NAIVE stamp is refused rather than assumed to be UTC: the board's own
    stamps are timezone-aware, and one naive value among them makes ``max()``
    raise — a 500 on the hub for a payload that merely mislabelled a timestamp.
    """
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _live_final_sides(
    match: dict[str, Any],
) -> Optional[list[tuple[dict[str, Any], float]]]:
    """``[(side, probability), (side, probability)]``, or ``None`` to refuse.

    Every clause is a refusal, and each one is the difference between promoting
    a number and fabricating one:

    * ``priced`` / ``price_state`` / ``probability_is_live`` — the match's own
      published verdict.  An unpriced or stale final has nothing better to
      offer than the outright the board already shows, and promoting it would
      hand the row a freshness this overlay cannot describe.
    * ``observed_at`` present, parseable and timezone-aware — a live verdict
      with no timestamp behind it is gotcha #53's shape, and the row's stamp is
      recomputed from it.
    * exactly two DISTINCT keys, each with a real number — "down to two" is the
      entire premise.  A one-sided, three-sided or self-paired row is a pairing
      defect upstream; it is not this overlay's to interpret.  Counted on the
      keys rather than on ``len(sides)`` so one check does both jobs.
    """
    if match.get("priced") is not True:
        return None
    if match.get("price_state") != "live" or match.get("probability_is_live") is not True:
        return None
    if _aware(match.get("observed_at")) is None:
        return None
    sides = match.get("sides")
    if not isinstance(sides, list):
        return None
    priced_sides: list[tuple[dict[str, Any], float]] = []
    keys: set[str] = set()
    for side in sides:
        if not isinstance(side, dict):
            return None
        key = side.get("entity_key")
        probability = side.get("probability")
        if not isinstance(key, str) or not key:
            return None
        # `bool` is an `int`; a True that reached a probability field is a bug
        # upstream, not a 1.0.
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            return None
        keys.add(key)
        priced_sides.append((side, float(probability)))
    # One side, three sides, or two sides naming the same player: none of those
    # is a final, and the distinct-key count refuses all three at once.
    if len(priced_sides) != 2 or len(keys) != 2:
        return None
    return priced_sides


def _finals_by_draw(slate: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The one final per draw the slate is serving — draws with two are refused.

    A draw cannot have two finals.  When the card shows two rows claiming to be
    one, that is a pairing defect and there is no tie to break: neither is
    promoted and the board keeps its own numbers.
    """
    finals: dict[str, dict[str, Any]] = {}
    refused: set[str] = set()
    for match in (slate or {}).get("matches") or []:
        if not isinstance(match, dict) or match.get("round") != FINAL_ROUND:
            continue
        draw = match.get("draw")
        if not isinstance(draw, str) or not draw:
            continue
        if draw in finals or draw in refused:
            finals.pop(draw, None)
            refused.add(draw)
            continue
        finals[draw] = match
    return finals


def _resolve_targets(
    rows: list[dict[str, Any]],
    sides: list[tuple[dict[str, Any], float]],
) -> Optional[list[tuple[dict[str, Any], float]]]:
    """Match the final's two sides to two board rows, or refuse.

    ═══ THE TWO KEY SPACES (measured, and the reason this is not a dict get) ═══

    A board row's ``entity_key`` is the REGISTER's — ``alexander-zverev``.  A
    slate side's is whatever built that row: the register's key on a
    register-matchup row, and ESPN's ``espn:athlete:2375`` on a scoreboard row,
    which is every round the ceremony register never carried — including, on
    production 2026-09-13, the men's final itself (``pairing_source:
    "scoreboard"``).  A join on ``entity_key`` alone therefore looks correct,
    passes a fixture that uses one space for both, and fires on nothing.

    So: the id first, and the register's own normalized name as the fallback —
    ``espn_tennis.normalize_name``, which is ``tournament_register``'s rule
    restated, and the same index ``build_progress`` already bridges these two
    spaces with.  The name arm is deliberately narrow:

    * it only sees the rows of ONE draw's board, which is at most a few dozen
      players, never the whole tournament;
    * a normalized name carried by more than one row on that board is dropped
      from the index rather than resolved to the first — an ambiguous name
      promotes nothing;
    * both sides must resolve, to two DIFFERENT rows.  One side resolving is
      the disagreement moved one row deeper, and both resolving to the same row
      is a join that has proved itself wrong.
    """
    from app.services.espn_tennis import normalize_name

    by_key: dict[str, dict[str, Any]] = {}
    by_name: dict[str, Optional[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("entity_key")
        if isinstance(key, str) and key:
            by_key[key] = row
        name = normalize_name(row.get("display_name"))
        if name:
            # `None` marks an ambiguous name: seen twice, resolvable to neither.
            by_name[name] = None if name in by_name else row

    targets: list[tuple[dict[str, Any], float]] = []
    for side, probability in sides:
        row = by_key.get(str(side.get("entity_key")))
        if row is None:
            row = by_name.get(normalize_name(side.get("display_name")))
        # The two state clauses coincide in every row `build_boards` produces —
        # a settled row is published with `probability: None` — and both are
        # written because this overlay must not depend on that invariant
        # holding in another module. Settled means settled either way.
        if (
            row is None
            or row.get("state") != "live"
            or row.get("probability") is None
        ):
            return None
        targets.append((row, probability))

    if len({id(row) for row, _ in targets}) != len(targets):
        return None
    return targets


def apply_final_match_blend(
    boards: list[dict[str, Any]],
    slate: Optional[dict[str, Any]],
    *,
    now: datetime,
) -> int:
    """Promote a live final's blend onto its two board rows, in place (#5893).

    Returns how many rows were changed, and stamps the same count per board as
    ``final_deferred_rows`` so the zero case is a fact on the payload rather
    than an absence.

    The whole rationale is at ``FINAL_ROUND`` above.  Three things this does
    NOT do, each load-bearing:

    * **It never resurrects a settled row.**  Both rows must still be
      ``state: "live"`` with a probability of their own; settled means settled,
      and a result may not be overwritten with a price.
    * **It never promotes onto a board that does not carry both players.**  If
      either side is missing from the board, or the two resolve to one row,
      neither side moves — see ``_resolve_targets``, which also explains why
      the two sides are not in the same key space.
    * **It leaves the trend lines alone.**  They are the outright series and
      they remain it: a sparkline is a shape, and redrawing 30 days of one
      market's history from another market's last reading would be the
      fabrication this module exists to refuse.  The published number is the
      match blend; the line under it is where that player's title price has
      been.
    """
    finals = _finals_by_draw(slate)
    if not finals:
        return 0

    changed = 0
    for board in boards:
        if not isinstance(board, dict):
            continue
        match = finals.get(board.get("draw"))
        if match is None:
            continue
        prices = _live_final_sides(match)
        if prices is None:
            continue

        rows = board.get("rows") or []
        targets = _resolve_targets(rows, prices)
        if targets is None:
            continue

        # Re-derived from the parsed instants against THIS request's `now`,
        # never copied from the match's published `age_hours`: the row's age and
        # the board banner computed over it have to be one clock's answer.
        governing = _aware(match.get("observed_at"))
        if governing is None:  # refused by `_live_final_sides`; belt and braces
            continue
        freshest = _aware(match.get("freshest_observed_at")) or governing
        governing_age = _age_hours(governing, now)
        freshest_age = _age_hours(freshest, now)
        # THE BOARD'S OWN THRESHOLD, NOT THE SLATE'S VERDICT. The two modules
        # grade freshness against their own constants, and a row stamped
        # `price_state: "live"` at an age this module calls stale would be a
        # contradiction inside one payload — so the match's live verdict is
        # necessary and this is the sufficient half.
        if price_state(governing_age) != "live":
            continue

        for row, probability in targets:
            row.update(
                {
                    "probability": round(probability, 6),
                    "probability_basis": PROBABILITY_BASIS_FINAL,
                    # True by construction: `_live_final_sides` refused anything
                    # the match itself does not call live.
                    "probability_is_live": True,
                    "price_state": "live",
                    "observed_at": governing.isoformat(),
                    "age_hours": (
                        round(governing_age, 2) if governing_age is not None else None
                    ),
                    "freshest_observed_at": freshest.isoformat() if freshest else None,
                    "freshest_age_hours": (
                        round(freshest_age, 2) if freshest_age is not None else None
                    ),
                    "stale_sources": [],
                    "mixed_freshness": False,
                    # The match's own provenance, because the match's number is
                    # what is printed. `sources` is emptied rather than left
                    # behind: the outright legs it lists are no longer what this
                    # row is showing, and a per-source breakdown that does not
                    # add up to the headline is #1844's class.
                    "source_count": match.get("source_count") or 0,
                    "sources": [],
                    "liquidity": match.get("liquidity") or LIQUIDITY_UNKNOWN,
                    "liquidity_reasons": list(match.get("liquidity_reasons") or []),
                }
            )
            changed += 1

        board["final_deferred_rows"] = len(targets)
        # The promoted rows carry a different number and a different stamp, so
        # the ranking and the banner are both re-derived from the rows as they
        # will now be served.
        _rank_rows(rows)
        board.update(_board_summary(rows, now))

    return changed
