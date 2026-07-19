"""Live AI commentary for THE OPEN CHAMPIONSHIP event-concept page (only).

Same-day live feature (Alex, 2026-07-19): a short, AI-generated commentary box at
the TOP of The Open's concept page that calls out what's moving in interesting
ways — a golfer charging up the win-probability board, a hard swing, a notable
position. It is grounded STRICTLY in the numeric leaderboard/win-probability data
already fused onto the event envelope (``app.utils.event_concept``); the model is
never allowed to invent scores, names, or events, and the numbers are framed as
win probabilities, never odds.

Scope is deliberately tiny. This is a live-day test for ONE tournament:
``is_open_championship()`` gates every entry point so no other golf event (or any
other domain) ever renders the box or triggers an OpenAI call.

Cost + latency control: the OpenAI call happens ONLY in the background Celery task
``app.tasks.golf_commentary.refresh_open_commentary`` (every
``COMMENTARY_REFRESH_SECONDS``), which writes the result to Redis. The request
path (``build_event``) only ever READS that Redis key — it never calls OpenAI —
mirroring the house rule "never run LLM calls inside a GET".

The pure helpers here (scope guard, mover selection, prompt builder) carry no DB
or network dependency so they are unit-tested directly.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scope + cadence constants
# ---------------------------------------------------------------------------

# The concept slug for The Open Championship (clean_slug("The Open Championship")).
# This is the ONLY event the commentary box is enabled for.
OPEN_SLUG = "the-open-championship"

# How often the background task regenerates commentary. A hard cost ceiling: at
# most one OpenAI call per this interval while the tournament is live. The Redis
# key is written with 2x this as its TTL so the box self-expires (stops rendering)
# if the task ever stops running — a stale blurb never lingers on a live page.
COMMENTARY_REFRESH_SECONDS = 180  # 3 minutes

# Redis key the task writes and the request path reads.
def commentary_redis_key(slug: str) -> str:
    return f"bainluck:golf_commentary:{slug}"


def is_open_championship(slug: Optional[str], event_name: Optional[str] = None) -> bool:
    """True ONLY for The Open Championship.

    Primary guard is the exact concept slug; the event name is a secondary,
    non-widening confirmation (an exact normalized match, so it can never catch
    "US Open", "U.S. Women's Open", etc.).
    """
    if slug and slug.strip().lower() == OPEN_SLUG:
        return True
    if event_name and event_name.strip().lower() == "the open championship":
        return True
    return False


# ---------------------------------------------------------------------------
# Data selection (pure)
# ---------------------------------------------------------------------------

# Only surface a probability swing this large (in win-probability POINTS) as a
# "mover" — below this it's leaderboard noise, not a story.
_MIN_MOVE_POINTS = 1.5


def _to_num(v) -> Optional[float]:
    """Coerce an int/float/numeric-string to float, else None.

    The fused live leaderboard is NOT type-consistent: DataGolf returns some
    fields (notably ``thru``) as strings ("9") and others as ints (-7). Every
    numeric gate/format below routes through this so a string never silently
    defeats a comparison (which was dropping real movers from the commentary).
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except (ValueError, AttributeError):
            return None
    return None


def _pct(prob: Optional[float]) -> Optional[int]:
    """0-1 win probability -> integer percent, or None."""
    n = _to_num(prob)
    if n is None:
        return None
    return round(n * 100)


def select_commentary_data(competitors: list[dict]) -> dict:
    """Pick the leaders + the notable movers from the fused live competitor list.

    Pure. Reads only fields the live-fusion step (``fuse_golf_live`` /
    ``golf_live_deltas``) already set on each competitor: ``name``,
    ``probability`` (0-1 win prob), ``position``, ``thru``, ``today_score``,
    ``score_to_par``, ``prob_delta_live`` (win-probability points moved today).

    Returns ``{"leaders": [...], "charging": [...], "sliding": [...]}`` where each
    entry is a compact dict of the numbers to ground the prompt in. ``charging`` /
    ``sliding`` only include golfers who are actively on the course (``thru`` > 0)
    with a move of at least ``_MIN_MOVE_POINTS`` — an overnight leader who hasn't
    teed off is a leader, not a mover.
    """
    ranked = [
        c
        for c in (competitors or [])
        if isinstance(c.get("probability"), (int, float))
    ]
    ranked.sort(key=lambda c: c["probability"], reverse=True)

    def _row(c: dict) -> dict:
        return {
            "name": c.get("name"),
            "win_pct": _pct(c.get("probability")),
            "position": c.get("position"),
            "thru": c.get("thru"),
            "today_score": c.get("today_score"),
            "score_to_par": c.get("score_to_par"),
            "delta": c.get("prob_delta_live"),
        }

    leaders = [_row(c) for c in ranked[:4] if _row(c)["name"]]

    def _is_playing(c: dict) -> bool:
        thru = _to_num(c.get("thru"))
        return thru is not None and thru > 0

    # Precompute the numeric delta once (the field can be a string) so the gate
    # and sort never trip over a type mismatch.
    movers = []
    for c in ranked:
        d = _to_num(c.get("prob_delta_live"))
        if (
            c.get("name")
            and _is_playing(c)
            and d is not None
            and abs(d) >= _MIN_MOVE_POINTS
        ):
            movers.append((d, c))
    charging = sorted(
        [(d, c) for d, c in movers if d > 0], key=lambda t: t[0], reverse=True
    )[:3]
    sliding = sorted([(d, c) for d, c in movers if d < 0], key=lambda t: t[0])[:2]

    return {
        "leaders": leaders,
        "charging": [_row(c) for _, c in charging],
        "sliding": [_row(c) for _, c in sliding],
    }


def _fmt_par(v: Optional[float]) -> Optional[str]:
    """Score-to-par -> golf notation ('-7' -> '7 under', '3' -> '3 over',
    0 -> 'even'). None-safe; accepts numeric strings."""
    n = _to_num(v)
    if n is None:
        return None
    iv = int(n)
    if iv < 0:
        return f"{abs(iv)} under par"
    if iv > 0:
        return f"{iv} over par"
    return "even par"


def _fmt_competitor_line(row: dict) -> str:
    """One grounded, labeled line for a golfer — only fields that are present."""
    parts = [f"{row['name']}:"]
    if row.get("win_pct") is not None:
        parts.append(f"win probability {row['win_pct']}%")
    if row.get("delta") is not None:
        d = row["delta"]
        sign = "+" if d > 0 else ""
        parts.append(f"({sign}{d} pts today)")
    if row.get("position"):
        parts.append(f"position {row['position']}")
    par = _fmt_par(row.get("score_to_par"))
    if par:
        parts.append(f"total {par}")
    today = _fmt_par(row.get("today_score"))
    if today is not None and row.get("today_score") is not None:
        parts.append(f"today {today}")
    thru = _to_num(row.get("thru"))
    if thru is not None and thru > 0:
        parts.append(f"through {int(thru)} holes")
    return " ".join(parts)


def build_commentary_prompt(event_name: Optional[str], data: dict) -> Optional[str]:
    """Build the numeric-only user prompt. Pure.

    Returns None when there is not enough grounded data to say anything
    (no leaders) — the caller then generates NO commentary.
    """
    leaders = data.get("leaders") or []
    if not leaders:
        return None

    name = event_name or "The Open Championship"
    lines = [f"Live data for {name} (numbers only — use nothing else):", ""]

    lines.append("LEADERBOARD (top by win probability):")
    for row in leaders:
        lines.append(f"  - {_fmt_competitor_line(row)}")

    charging = data.get("charging") or []
    if charging:
        lines.append("")
        lines.append("BIGGEST WIN-PROBABILITY GAINERS (on the course now):")
        for row in charging:
            lines.append(f"  - {_fmt_competitor_line(row)}")

    sliding = data.get("sliding") or []
    if sliding:
        lines.append("")
        lines.append("BIGGEST WIN-PROBABILITY DROPS (on the course now):")
        for row in sliding:
            lines.append(f"  - {_fmt_competitor_line(row)}")

    lines.append("")
    lines.append(
        "Write 2-3 sentences on what is moving. Lead with the biggest win-"
        "probability gainer if there is one. Use only the names and numbers "
        "above."
    )
    return "\n".join(lines)


def generate_commentary(
    event_name: Optional[str],
    competitors: list[dict],
    status: str,
) -> Optional[str]:
    """Generate the commentary string, or None.

    LIVE-ONLY: returns None (no OpenAI call) unless ``status == 'live'``. Also
    returns None when there is no usable data or the LLM is unavailable/errors —
    every None path degrades to NO box.

    This performs the actual (synchronous) OpenAI call, so it must only run inside
    the background task, never on the request path.
    """
    if status != "live":
        return None
    if not competitors:
        return None

    data = select_commentary_data(competitors)
    prompt = build_commentary_prompt(event_name, data)
    if not prompt:
        return None

    try:
        from app.services.llm import generate_golf_live_commentary

        text = generate_golf_live_commentary(prompt)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("generate_commentary failed: %s", exc)
        return None

    if not text or not text.strip():
        return None
    return text.strip()
