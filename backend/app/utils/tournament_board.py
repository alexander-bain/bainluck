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
from app.utils.tournament_register import (
    STALE_PRICE_HOURS,
    TournamentRegister,
    check_rendered_rows,
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

DRAW_LABELS: dict[str, str] = {
    "mens-singles": "Men's Singles",
    "womens-singles": "Women's Singles",
    # Ready and unused (UX-P139, item 12). No doubles market exists at either
    # source; ESPN already carries all three draws' results under these slugs.
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


def _merge_daily_series(
    series_by_outcome: dict[int, list[tuple[str, float]]],
    contributors: list[tuple[str, int]],
) -> list[dict[str, Any]]:
    """One point per DAY THAT WAS ACTUALLY OBSERVED, blended by the SAME rule.

    Each day is run through ``blend_with_verdict`` exactly as the headline is,
    rather than meaned.  With two equal-weight sources the two rules agree
    numerically today, so this looks like a distinction without a difference —
    it is not.  The moment the divergence gate fires on a day, a mean would
    print a number the headline rule has explicitly refused to print, and the
    trend line would be a different KIND of value from the number above it.
    That is #1844's class: a raw figure and a blend rendered as if comparable.
    One question, one rule, at every point in time.

    Days with no reading are absent, not zero and not carried forward: a gap in
    the line is a gap in the data, and filling it would manufacture exactly the
    confidence this module exists to refuse.
    """
    by_day: dict[str, list[dict[str, Any]]] = {}
    for source, outcome_id in contributors:
        for day, value in series_by_outcome.get(outcome_id, []):
            by_day.setdefault(day, []).append(
                {"source": source, "probability": float(value)}
            )

    points: list[dict[str, Any]] = []
    for day, rows in sorted(by_day.items()):
        value = blend_with_verdict(rows)[0]
        if value is None:
            continue
        points.append({"date": day, "probability": round(value, 6)})
    return points


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
                    }
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
                        "state": settled_result,
                        "probability": None,
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
                        "trend_delta": None,
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
            trend = _merge_daily_series(series_by_outcome, contributors)
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
                    "state": "live",
                    "probability": round(blend, 6),
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
                    "trend_delta": trend_delta,
                }
            )

        # Rank by the blend, highest first. Rows without a probability (settled)
        # sort last — they are results, not standings.
        rows.sort(key=lambda r: (r["probability"] is None, -(r["probability"] or 0.0)))
        for index, row in enumerate(rows, start=1):
            row["rank"] = index

        # The BOARD reports the newest thing anyone has seen — the strongest
        # true claim about the page as a whole, and deliberately not an AND.
        # Rows carry their own verdict; making one 30-day row paint the banner
        # over 43 live ones would retire the banner as a signal (the
        # crying-wolf failure), and every row is individually honest already.
        # It reads `freshest_observed_at` because `observed_at` is now the
        # governing contributor's, which would make this a max-of-oldest.
        observed = [
            datetime.fromisoformat(r["freshest_observed_at"])
            for r in rows
            if r.get("freshest_observed_at")
        ]
        board_newest = max(observed) if observed else None
        board_age = _age_hours(board_newest, now)
        board_state = price_state(board_age)

        boards.append(
            {
                "draw": draw,
                "label": draw_label(draw),
                "rows": rows,
                "contenders": len(rows),
                "unpriced": unpriced,
                # Quantified rather than described: how much of this board is
                # not a live number, and how much of it is a blend of legs of
                # different ages. Both are zero on a healthy board.
                "rows_not_live": sum(
                    1 for r in rows if r["probability"] is not None and not r["probability_is_live"]
                ),
                "mixed_freshness_rows": sum(1 for r in rows if r["mixed_freshness"]),
                "price_state": board_state,
                "newest_observed_at": board_newest.isoformat() if board_newest else None,
                "age_hours": round(board_age, 2) if board_age is not None else None,
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
