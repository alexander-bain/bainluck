"""
Line movement detection and analysis.

Detects significant odds movements from historical snapshots and prepares
context for LLM-powered explanations of why lines moved.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# Detection thresholds
SIGNIFICANT_MOVE_THRESHOLD = 0.05  # 5% probability change
MAJOR_MOVE_THRESHOLD = 0.10        # 10% probability change
MIN_DURATION_MINUTES = 3           # Ignore moves shorter than 3 min
MAX_MOVEMENTS_PER_EVENT = 5        # Cap to avoid noise


@dataclass
class LineMovement:
    """A detected significant line movement."""
    timestamp_start: datetime
    timestamp_end: datetime
    home_prob_before: float
    home_prob_after: float
    change: float  # Signed: positive = home team gained
    magnitude: float  # Absolute change
    direction: str  # "toward_home", "toward_away", "evening_out", "pulling_away"
    context: str  # Human-readable context about the movement
    is_major: bool = False
    bookmaker_count_before: int = 0
    bookmaker_count_after: int = 0


@dataclass
class LineMovementAnalysis:
    """Complete analysis of line movements for an event."""
    event_id: int
    movements: list[LineMovement] = field(default_factory=list)
    total_swing: float = 0.0  # Net probability change from opening
    max_single_move: float = 0.0
    movement_count: int = 0
    summary_context: str = ""  # Context string for LLM


def detect_line_movements(
    snapshots: list[dict],
    opening_home_prob: Optional[float] = None,
    event_status: str = "scheduled",
    home_team: str = "",
    away_team: str = "",
    sport_key: str = "",
) -> LineMovementAnalysis:
    """
    Detect significant line movements from time-bucketed odds snapshots.

    Args:
        snapshots: List of dicts with keys:
            - timestamp (datetime or ISO string)
            - home_probability (float)
            - bookmaker_count (int, optional)
        opening_home_prob: Opening probability for home team
        event_status: Current event status
        home_team: Home team name
        away_team: Away team name
        sport_key: Sport key for context

    Returns:
        LineMovementAnalysis with detected movements and context.
    """
    analysis = LineMovementAnalysis(event_id=0)

    if len(snapshots) < 2:
        return analysis

    # Parse timestamps if needed and sort chronologically
    parsed = []
    for s in snapshots:
        ts = s.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        prob = s.get("home_probability")
        if ts and prob is not None:
            parsed.append({
                "timestamp": ts,
                "home_probability": float(prob),
                "bookmaker_count": s.get("bookmaker_count", 0),
            })

    parsed.sort(key=lambda x: x["timestamp"])

    if len(parsed) < 2:
        return analysis

    # Detect movements using a sliding window approach
    # We look for sustained directional moves (not just single-poll noise)
    movements = []
    i = 0

    while i < len(parsed) - 1:
        start = parsed[i]
        # Look ahead to find the end of a directional move
        j = i + 1
        while j < len(parsed):
            current_change = parsed[j]["home_probability"] - start["home_probability"]
            # Check if the move is still going in the same direction
            if j + 1 < len(parsed):
                next_change = parsed[j + 1]["home_probability"] - start["home_probability"]
                # If direction reverses significantly, stop here
                if abs(next_change) < abs(current_change) * 0.5 and abs(current_change) > 0.02:
                    break
            j += 1

        end = parsed[min(j, len(parsed) - 1)]
        change = end["home_probability"] - start["home_probability"]
        magnitude = abs(change)

        if magnitude >= SIGNIFICANT_MOVE_THRESHOLD:
            duration = (end["timestamp"] - start["timestamp"]).total_seconds() / 60

            if duration >= MIN_DURATION_MINUTES:
                # Determine direction
                if change > 0:
                    if start["home_probability"] < 0.5:
                        direction = "evening_out"
                    else:
                        direction = "pulling_away" if magnitude > 0.08 else "toward_home"
                else:
                    if start["home_probability"] > 0.5:
                        direction = "evening_out"
                    else:
                        direction = "pulling_away" if magnitude > 0.08 else "toward_away"

                context = _build_movement_context(
                    change=change,
                    home_prob_before=start["home_probability"],
                    home_prob_after=end["home_probability"],
                    home_team=home_team,
                    away_team=away_team,
                    event_status=event_status,
                )

                movement = LineMovement(
                    timestamp_start=start["timestamp"],
                    timestamp_end=end["timestamp"],
                    home_prob_before=start["home_probability"],
                    home_prob_after=end["home_probability"],
                    change=change,
                    magnitude=magnitude,
                    direction=direction,
                    context=context,
                    is_major=magnitude >= MAJOR_MOVE_THRESHOLD,
                    bookmaker_count_before=start.get("bookmaker_count", 0),
                    bookmaker_count_after=end.get("bookmaker_count", 0),
                )
                movements.append(movement)

        i = max(j, i + 1)

    # Sort by magnitude (most significant first) and cap
    movements.sort(key=lambda m: m.magnitude, reverse=True)
    movements = movements[:MAX_MOVEMENTS_PER_EVENT]

    # Build analysis summary
    analysis.movements = movements
    analysis.movement_count = len(movements)
    analysis.max_single_move = max((m.magnitude for m in movements), default=0.0)

    # Calculate total swing from opening
    if opening_home_prob is not None and parsed:
        analysis.total_swing = parsed[-1]["home_probability"] - opening_home_prob

    # Build summary context for LLM
    analysis.summary_context = _build_summary_context(
        movements=movements,
        opening_home_prob=opening_home_prob,
        current_home_prob=parsed[-1]["home_probability"] if parsed else None,
        home_team=home_team,
        away_team=away_team,
        sport_key=sport_key,
        event_status=event_status,
    )

    return analysis


def _build_movement_context(
    change: float,
    home_prob_before: float,
    home_prob_after: float,
    home_team: str,
    away_team: str,
    event_status: str,
) -> str:
    """Build human-readable context for a single movement."""
    pct_before = round(home_prob_before * 100, 1)
    pct_after = round(home_prob_after * 100, 1)
    pct_change = round(abs(change) * 100, 1)

    beneficiary = home_team if change > 0 else away_team
    shifted_from = f"{pct_before}%" if change > 0 else f"{round((1-home_prob_before)*100, 1)}%"
    shifted_to = f"{pct_after}%" if change > 0 else f"{round((1-home_prob_after)*100, 1)}%"

    phase = "Pre-game" if event_status == "scheduled" else "In-game"

    return (
        f"{phase}: {beneficiary} odds improved by {pct_change}% "
        f"({shifted_from} → {shifted_to})"
    )


def _build_summary_context(
    movements: list[LineMovement],
    opening_home_prob: Optional[float],
    current_home_prob: Optional[float],
    home_team: str,
    away_team: str,
    sport_key: str,
    event_status: str,
) -> str:
    """Build full context string for LLM explanation."""
    parts = []

    # Sport context
    sport_name = sport_key.replace("_", " ").title() if sport_key else "game"
    parts.append(f"Sport: {sport_name}")
    parts.append(f"Matchup: {away_team} at {home_team}")
    parts.append(f"Status: {event_status}")

    # Opening vs current
    if opening_home_prob is not None and current_home_prob is not None:
        opening_pct = round(opening_home_prob * 100, 1)
        current_pct = round(current_home_prob * 100, 1)
        swing = round((current_home_prob - opening_home_prob) * 100, 1)
        parts.append(
            f"Opening odds: {home_team} {opening_pct}% / {away_team} {round(100-opening_pct, 1)}%"
        )
        parts.append(
            f"Current odds: {home_team} {current_pct}% / {away_team} {round(100-current_pct, 1)}%"
        )
        if abs(swing) >= 1:
            direction = home_team if swing > 0 else away_team
            parts.append(f"Net swing: {abs(swing)}% toward {direction}")

    # Movement descriptions
    if movements:
        parts.append(f"\nSignificant movements detected ({len(movements)}):")
        for i, m in enumerate(movements[:3], 1):
            time_str = m.timestamp_start.strftime("%H:%M UTC")
            parts.append(f"  {i}. At {time_str}: {m.context}")

    return "\n".join(parts)


def build_llm_prompt(
    analysis: LineMovementAnalysis,
    injuries: Optional[list[dict]] = None,
    news_headlines: Optional[list[str]] = None,
    game_context: Optional[dict] = None,
) -> str:
    """
    Build the LLM prompt to explain line movements.

    Args:
        analysis: The line movement analysis with summary_context
        injuries: List of injury dicts with player_name, team_name, status, injury_type
        news_headlines: List of recent news headline strings
        game_context: Dict with home_team, away_team, home_score, away_score, period, clock

    Returns a prompt string ready to send to GPT-4o-mini.
    """
    # Build context sections
    context_sections = []

    if injuries:
        lines = ["Known injury report:"]
        for inj in injuries[:10]:  # Cap at 10 to keep prompt manageable
            parts = [f"  - {inj['player_name']} ({inj['team_name']}): {inj['status']}"]
            if inj.get("injury_type") and inj["injury_type"] != "Unknown":
                parts[0] += f" — {inj['injury_type']}"
            lines.append(parts[0])
        context_sections.append("\n".join(lines))

    if news_headlines:
        lines = ["Recent headlines:"]
        for headline in news_headlines[:5]:
            lines.append(f"  - {headline}")
        context_sections.append("\n".join(lines))

    if game_context:
        home = game_context.get("home_team", "Home")
        away = game_context.get("away_team", "Away")
        h_score = game_context.get("home_score")
        a_score = game_context.get("away_score")
        period = game_context.get("period")
        clock = game_context.get("clock")
        parts = []
        if h_score is not None and a_score is not None:
            parts.append(f"Score: {home} {h_score} - {away} {a_score}")
        if period:
            parts.append(f"Period: {period}")
        if clock:
            parts.append(f"Clock: {clock}")
        if parts:
            context_sections.append("Live game state: " + " | ".join(parts))

    extra_context = ""
    if context_sections:
        extra_context = "\n\n" + "\n\n".join(context_sections) + "\n"

    return f"""You are a sports betting analyst explaining odds movements to casual fans who want to understand what's happening, not get betting advice.

Given the following odds movement data, explain WHY the line likely moved.

{analysis.summary_context}{extra_context}

Instructions:
- Write 2-3 concise sentences explaining the most likely reason(s) for the movement
- Focus on the single biggest movement if there are multiple
- Use the injury and news information provided when explaining the movement. Only reference specific injuries/news if they are listed above. Do not fabricate injury information.
- Be specific to the sport and teams when possible
- Use language casual fans understand (avoid jargon like "steam move" or "RLM")
- If the movement is during a live game, focus on in-game factors (scoring runs, momentum, key plays)
- If pre-game, focus on news/injury/lineup factors
- Do NOT give betting advice or suggest what users should bet on
- Do NOT use phrases like "I think" or "In my opinion"
- Start directly with the explanation (no preamble)

Explanation:"""
