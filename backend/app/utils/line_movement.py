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


def _format_probability(probability: float) -> str:
    """Format a probability as a one-decimal percentage."""
    return f"{round(probability * 100, 1)}%"


def _format_movement_window(movement: LineMovement) -> str:
    """Format movement timing for prompt context."""
    start = movement.timestamp_start.strftime("%H:%M UTC")
    end = movement.timestamp_end.strftime("%H:%M UTC")
    if start == end:
        return start
    return f"{start}-{end}"


def _movement_beneficiary(movement: LineMovement, home_team: str, away_team: str) -> str:
    """Return the team whose win probability improved."""
    if movement.change > 0:
        return home_team or "home team"
    return away_team or "away team"


def _build_movement_detail(
    movement: LineMovement,
    home_team: str,
    away_team: str,
) -> str:
    """Build a compact, factual movement description for LLM context."""
    beneficiary = _movement_beneficiary(movement, home_team, away_team)
    magnitude = round(movement.magnitude * 100, 1)
    time_window = _format_movement_window(movement)

    if movement.change > 0:
        before = _format_probability(movement.home_prob_before)
        after = _format_probability(movement.home_prob_after)
    else:
        before = _format_probability(1 - movement.home_prob_before)
        after = _format_probability(1 - movement.home_prob_after)

    return (
        f"{time_window}: {magnitude}pp toward {beneficiary} "
        f"({before} to {after})"
    )


def _parse_context_timestamp(value: object) -> Optional[datetime]:
    """Parse optional context timestamps when source data provides them."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _minutes_from_movement(timestamp: datetime, movement: LineMovement) -> float:
    """Return distance in minutes from a timestamp to a movement window."""
    start = movement.timestamp_start
    end = movement.timestamp_end
    if start.tzinfo is None and timestamp.tzinfo is not None:
        start = start.replace(tzinfo=timestamp.tzinfo)
        end = end.replace(tzinfo=timestamp.tzinfo)
    elif start.tzinfo is not None and timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=start.tzinfo)

    if start <= timestamp <= end:
        return 0.0
    return min(
        abs((timestamp - start).total_seconds()),
        abs((timestamp - end).total_seconds()),
    ) / 60


def _rank_scoring_plays(
    scoring_plays: list[dict],
    movement: Optional[LineMovement],
) -> list[tuple[dict, Optional[float]]]:
    """Prefer scoring plays closest to the largest movement when timestamps exist."""
    ranked = []
    untimed = []

    for index, play in enumerate(scoring_plays):
        timestamp = _parse_context_timestamp(
            play.get("timestamp") or play.get("captured_at") or play.get("created_at")
        )
        if timestamp and movement:
            ranked.append((play, _minutes_from_movement(timestamp, movement), index))
        else:
            untimed.append((play, None, index))

    if not ranked:
        return [(play, distance) for play, distance, _index in untimed]

    ranked.sort(key=lambda item: (item[1], item[2]))
    return [(play, distance) for play, distance, _index in ranked + untimed]


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
        largest = movements[0]
        parts.append(
            "\nLargest movement: "
            + _build_movement_detail(largest, home_team, away_team)
        )
        parts.append(f"Direction label: {largest.direction}")
        parts.append(f"Major movement: {'yes' if largest.is_major else 'no'}")

        parts.append(f"\nAll significant movements ({len(movements)}, largest first):")
        for i, m in enumerate(movements[:3], 1):
            parts.append(f"  {i}. {_build_movement_detail(m, home_team, away_team)}")
            parts.append(f"     Context label: {m.context}")

    return "\n".join(parts)


def build_llm_prompt(
    analysis: LineMovementAnalysis,
    injuries: Optional[list[dict]] = None,
    news_headlines: Optional[list[str]] = None,
    game_context: Optional[dict] = None,
    team_stats: Optional[dict] = None,
    scoring_plays: Optional[list[dict]] = None,
) -> str:
    """
    Build the LLM prompt to explain line movements.

    Args:
        analysis: The line movement analysis with summary_context
        injuries: List of injury dicts with player_name, team_name, status, injury_type
        news_headlines: List of recent news headline strings
        game_context: Dict with home_team, away_team, home_score, away_score, period, clock
        team_stats: Dict with home_stats and away_stats dicts (season stats like ppg, opp_ppg)
        scoring_plays: List of scoring play dicts with timestamp, description, team, period, clock, home_score, away_score

    Returns a prompt string ready to send to GPT-4o-mini.
    """
    largest_movement = analysis.movements[0] if analysis.movements else None
    if largest_movement:
        focus_line = _build_movement_detail(
            largest_movement,
            _extract_home_team(analysis.summary_context),
            _extract_away_team(analysis.summary_context),
        )
    else:
        focus_line = "No qualifying movement was detected."

    # Build context sections — scoring plays first, then game state, then injuries/news
    context_sections = []

    if scoring_plays:
        lines = ["Key game moments:", "Nearby source context:"]
        for play, distance in _rank_scoring_plays(scoring_plays, largest_movement)[:15]:
            period = play.get("period", "")
            clock = play.get("clock", "")
            team = play.get("team", "")
            desc = play.get("description", "")
            h_score = play.get("home_score")
            a_score = play.get("away_score")
            time_label = f"{period} {clock}".strip() if period or clock else ""
            nearby_label = (
                f"{round(distance)} min from focus movement"
                if distance is not None
                else ""
            )
            score_label = f"({h_score} - {a_score})" if h_score is not None and a_score is not None else ""
            parts = [p for p in [nearby_label, time_label, team, desc, score_label] if p]
            lines.append(f"  - {' '.join(parts)}")
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

    if injuries:
        lines = ["Known injury report:", "Nearby source context:"]
        for inj in injuries[:5]:  # Cap at 5 to focus on most impactful
            parts = [f"  - {inj['player_name']} ({inj['team_name']}): {inj['status']}"]
            if inj.get("injury_type") and inj["injury_type"] != "Unknown":
                parts[0] += f" — {inj['injury_type']}"
            if inj.get("detail"):
                parts[0] += f" ({inj['detail']})"
            lines.append(parts[0])
        context_sections.append("\n".join(lines))

    if news_headlines:
        lines = ["Recent headlines:", "Nearby source context:"]
        for headline in news_headlines[:5]:
            lines.append(f"  - {headline}")
        context_sections.append("\n".join(lines))

    if team_stats:
        stats_lines = ["Season stats:"]
        home_s = team_stats.get("home_stats")
        away_s = team_stats.get("away_stats")
        home_name = team_stats.get("home_team", "Home")
        away_name = team_stats.get("away_team", "Away")
        for label, stats in [(home_name, home_s), (away_name, away_s)]:
            if stats:
                stat_parts = []
                for key, val in list(stats.items())[:8]:
                    stat_parts.append(f"{key}: {val}")
                if stat_parts:
                    stats_lines.append(f"  {label}: {', '.join(stat_parts)}")
        if len(stats_lines) > 1:
            context_sections.append("\n".join(stats_lines))

    extra_context = ""
    if context_sections:
        extra_context = "\n\n" + "\n\n".join(context_sections) + "\n"

    # Determine how much context we actually have
    has_scoring_plays = bool(scoring_plays)
    has_injuries = bool(injuries)
    has_news = bool(news_headlines)
    has_game_state = bool(game_context and game_context.get("home_score") is not None)
    has_any_context = has_scoring_plays or has_injuries or has_news or has_game_state or bool(team_stats)

    # Context-aware instructions:
    # Scoring plays get the richest prompt — correlate odds shifts with game moments.
    if has_scoring_plays:
        context_instructions = """- Write 2-3 concise sentences explaining the largest movement first, then any useful supporting context
- Reference specific scoring plays and game moments when explaining movements. Correlate timing of odds shifts with plays that happened around the same time.
- State facts directly. Do NOT use "likely due to", "probably because", or any speculative hedging language.
- BAD: "likely due to their strong performance leading to a significant lead"
- GOOD: "A 12-0 run in Q3 pushed Detroit from 55% to 78%. Cade Cunningham hit back-to-back threes."
- Only mention injuries if they directly relate to an odds movement. Don't list the full injury report — focus on players actually missing from the game.
- If the provided game moments do not clearly explain the timing, describe them as nearby context instead of forcing a cause.
- If the game is completed, describe how the odds evolved through the game, not just the final state."""
    elif has_injuries or has_news:
        context_instructions = """- Write 2-3 concise sentences explaining the largest movement first
- Name the team that benefited, the size of the move, and the before/after probabilities
- Use the injury and news information provided when explaining the movement. Only reference specific injuries/news if they are listed above. Do not fabricate injury information.
- State facts directly. Do NOT use "likely due to", "probably because", "has severely impacted", or any speculative hedging language.
- BAD: "likely due to their strong performance leading to a significant lead"
- GOOD: "The Hawks lead 75-58 at halftime. Portland is missing Lillard and Williams."
- BAD: "has severely impacted their ability to compete effectively"
- GOOD: "With Portland down 3 starters, Atlanta has pulled away."
- Do not pad with generic market language like "bettors reacted", "market confidence", or "momentum shifted" unless the source context directly supports it.
- If the movement is during a live game, reference the current score and game state
- If pre-game, focus on news/injury/lineup factors"""
    elif has_game_state:
        context_instructions = """- Write 2-3 concise sentences describing the largest movement and current game state
- Name the team that benefited, the size of the move, and the before/after probabilities
- Reference the current score and period/quarter to give context for the shift
- State the score and odds factually. No filler, no speculation.
- BAD: "This movement may reflect momentum changes during the game."
- BAD: "The shift could indicate strong performance by the home team."
- BAD: "likely due to their strong performance leading to a significant lead"
- GOOD: "Hawks lead 75-58 at halftime. Their odds climbed from 66% to 93%."
- Do NOT speculate about specific causes (key plays, scoring runs, momentum swings) unless that information was provided above
- Do NOT say "possibly due to", "likely because of", "has severely impacted" — describe the situation, not guesses"""
    else:
        context_instructions = """- Write 1-2 concise sentences describing the movement factually (which direction, which team benefited, how large the shift was)
- Do NOT speculate about causes. Do not say "likely due to" or "probably because" — we don't have enough data to explain why.
- Do NOT mention scoring runs, key plays, injuries, lineup changes, or any other cause unless that information was provided above.
- Simply describe what happened to the odds. Example: "The line shifted 8% toward the Lakers over the past hour, moving from a toss-up to a clear Lakers lean."
- It's OK to note that the reason is unclear — that's better than guessing."""

    return f"""You are a direct, factual sports reporter. State what happened — scores, injuries, odds shifts. No speculation, no hedging, no filler phrases. Write like a ticker update, not an essay.

Given the following odds movement data, describe what happened and provide context.

Focus movement: {focus_line}

{analysis.summary_context}{extra_context}

Instructions:
{context_instructions}
- Use language casual fans understand (avoid jargon like "steam move" or "RLM")
- Do NOT give betting advice or suggest what users should bet on
- Do NOT use phrases like "I think" or "In my opinion"
- Start directly with the explanation (no preamble)

Explanation:"""


def _extract_home_team(summary_context: str) -> str:
    """Best-effort home team extraction from summary context for manual analyses."""
    for line in summary_context.splitlines():
        if line.startswith("Matchup: ") and " at " in line:
            return line.rsplit(" at ", 1)[1].strip()
    return "home team"


def _extract_away_team(summary_context: str) -> str:
    """Best-effort away team extraction from summary context for manual analyses."""
    for line in summary_context.splitlines():
        if line.startswith("Matchup: ") and " at " in line:
            return line.removeprefix("Matchup: ").split(" at ", 1)[0].strip()
    return "away team"
