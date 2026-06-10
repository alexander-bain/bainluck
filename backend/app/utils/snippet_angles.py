"""Snippet angle selection for Discover cards.

Pure functions — no I/O, no DB, no API calls. Deterministic angle
selection with template strings. The LLM phrasing pass (slice 2)
takes these payloads and rewrites in wire-service voice.

Angle priority (pick FIRST qualifying):
1. Fresh move (24h movement >= 5pts)
2. Big shift from open (current vs opening >= 10pts)
3. Cross-source disagreement (delta >= 5pts)
4. Deadline pressure (resolves <= 72h, probability 15-85%)
5. Volume surge (24h volume >= $50K)
6. Leader change (rank changed in 24h)
7. Sibling action (group sibling fired angle 1-2)
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class MarketContext:
    """Input context for angle selection — populated from DB fields."""

    name: str
    probability: Optional[float] = None
    opening_probability: Optional[float] = None
    movement_24h: Optional[float] = None
    outcome_name: Optional[str] = None
    resolution_date: Optional[datetime] = None
    volume_24h: Optional[float] = None
    cross_source_delta: Optional[float] = None
    cross_source_names: Optional[tuple[str, str]] = None
    rank_change_24h: Optional[int] = None
    sibling_angle: Optional[str] = None
    sibling_movement: Optional[float] = None
    now: Optional[datetime] = None


@dataclass
class AngleResult:
    """Output of angle selection."""

    angle_type: str
    payload: dict
    template: str


def select_angle(ctx: MarketContext) -> Optional[AngleResult]:
    """Pick the highest-priority qualifying angle for this market.

    Returns None if no angle qualifies (keep existing deterministic headline).
    """
    now = ctx.now or datetime.now(timezone.utc)

    # 1. Fresh move
    if ctx.movement_24h is not None and abs(ctx.movement_24h) >= 0.05:
        pts = round(abs(ctx.movement_24h) * 100, 1)
        direction = "Up" if ctx.movement_24h > 0 else "Down"
        outcome = ctx.outcome_name or "Yes"
        return AngleResult(
            angle_type="fresh_move",
            payload={"direction": direction, "pts": pts, "outcome": outcome},
            template=f"{direction} {pts} pts today.",
        )

    # 2. Big shift from open
    if (
        ctx.probability is not None
        and ctx.opening_probability is not None
        and round(abs(ctx.probability - ctx.opening_probability), 4) >= 0.10
    ):
        shift = round((ctx.probability - ctx.opening_probability) * 100, 1)
        direction = "up" if shift > 0 else "down"
        outcome = ctx.outcome_name or "Yes"
        opening_pct = round(ctx.opening_probability * 100)
        return AngleResult(
            angle_type="big_shift",
            payload={
                "direction": direction,
                "shift_pts": abs(shift),
                "outcome": outcome,
                "opening_pct": opening_pct,
            },
            template=f"{outcome} side {direction} {abs(shift)} pts from its opening {opening_pct}%.",
        )

    # 3. Cross-source disagreement
    if (
        ctx.cross_source_delta is not None
        and ctx.cross_source_delta >= 0.05
        and ctx.cross_source_names
    ):
        delta_pts = round(ctx.cross_source_delta * 100, 1)
        src_a, src_b = ctx.cross_source_names
        return AngleResult(
            angle_type="cross_source",
            payload={"delta_pts": delta_pts, "source_a": src_a, "source_b": src_b},
            template=f"{src_a} and {src_b} are {delta_pts} pts apart on this.",
        )

    # 4. Deadline pressure
    if (
        ctx.resolution_date is not None
        and ctx.probability is not None
        and 0.15 <= ctx.probability <= 0.85
    ):
        hours_left = (ctx.resolution_date - now).total_seconds() / 3600
        if 0 < hours_left <= 72:
            pct = round(ctx.probability * 100)
            complement = 100 - pct
            day_name = ctx.resolution_date.strftime("%A")
            return AngleResult(
                angle_type="deadline",
                payload={
                    "hours_left": round(hours_left, 1),
                    "day_name": day_name,
                    "pct": pct,
                    "complement": complement,
                },
                template=f"Resolves {day_name} with the market still split {pct}/{complement}.",
            )

    # 5. Volume surge
    if ctx.volume_24h is not None and ctx.volume_24h >= 50_000:
        if ctx.volume_24h >= 1_000_000:
            vol_str = f"${ctx.volume_24h / 1_000_000:.1f}M"
        else:
            vol_str = f"${ctx.volume_24h / 1_000:.0f}K"
        return AngleResult(
            angle_type="volume_surge",
            payload={"volume_24h": ctx.volume_24h, "volume_str": vol_str},
            template=f"{vol_str} traded in 24h.",
        )

    # 6. Leader change
    if ctx.rank_change_24h is not None and ctx.rank_change_24h != 0:
        outcome = ctx.outcome_name or "Leader"
        return AngleResult(
            angle_type="leader_change",
            payload={"outcome": outcome, "rank_change": ctx.rank_change_24h},
            template=f"{outcome} took the lead this week.",
        )

    # 7. Sibling action
    if ctx.sibling_angle and ctx.sibling_movement is not None:
        pts = round(abs(ctx.sibling_movement) * 100, 1)
        direction = "jumped" if ctx.sibling_movement > 0 else "dropped"
        return AngleResult(
            angle_type="sibling_action",
            payload={"sibling_angle": ctx.sibling_angle, "pts": pts, "direction": direction},
            template=f"A related market {direction} {pts} pts.",
        )

    return None
