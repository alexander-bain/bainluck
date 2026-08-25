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
            newest: Optional[datetime] = None
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
                source_views.append(
                    {
                        "source": block.get("source"),
                        "probability": round(probability, 6),
                        "observed_at": observed_at.isoformat() if observed_at else None,
                    }
                )
                if isinstance(block.get("outcome_id"), int):
                    contributors.append((str(block.get("source")), block["outcome_id"]))
                if observed_at is not None and (newest is None or observed_at > newest):
                    newest = observed_at

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

            age = _age_hours(newest, now)
            row_state = price_state(age)
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
                    "observed_at": newest.isoformat() if newest else None,
                    "age_hours": round(age, 2) if age is not None else None,
                    "price_state": row_state,
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

        observed = [
            datetime.fromisoformat(r["observed_at"])
            for r in rows
            if r.get("observed_at")
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
