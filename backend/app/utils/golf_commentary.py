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


# Redis key holding the PREVIOUS state snapshot, diffed each run by the change-
# detector (task-only; never read on the request path).
def state_redis_key(slug: str) -> str:
    return f"bainluck:golf_commentary_state:{slug}"


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


# ===========================================================================
# Change-detector + scoring correlation (Alex, 2026-07-19 redesign)
# ---------------------------------------------------------------------------
# Restating the same win probabilities every 3 minutes isn't useful. Instead the
# beat SNAPSHOTS the whole event state (leaderboard + every prop market's outcome
# probabilities) to Redis each run and DIFFS against the previous run, so the box
# reports WHAT JUST MOVED — and, where a golfer's scoring change lines up with a
# market move in the same window, ties them together ("as Cameron Young picked up
# a shot, the U.S. region-to-win rose 40%->42%").
#
# Everything here is pure (no DB / no network) so the diff + correlation logic is
# unit-tested directly; the task owns the Redis read/write and the OpenAI call.
# ===========================================================================

# A prop-outcome probability move of at least this many POINTS is a "move".
_PROP_MOVE_POINTS = 3.0
# Per-golfer finish markets to track for movement (source field on the competitor
# -> display label). These are DataGolf, 0-100, and update at the live cadence, so
# a birdie/bogey visibly shifts them — the reliable fast correlation surface.
_FINISH_MARKETS = [
    ("top_5_prob", "Top 5"),
    ("top_10_prob", "Top 10"),
    ("top_20_prob", "Top 20"),
]
# A finish-probability move of at least this many points is worth mentioning
# (a hair higher than the group-prop bar — finish props are noisier hole-to-hole).
_FINISH_MOVE_POINTS = 5.0
# Win-probability move (leaderboard) of at least this many points is notable.
_WIN_MOVE_POINTS = 1.5
# Only snapshot prop outcomes at/above this probability (bounds the Redis blob and
# ignores longshot noise — a 0.2% outcome wobbling is not a story).
_SNAPSHOT_PROB_FLOOR = 0.05
# Per-market outcome cap in the snapshot (Round-1-Scores has 128 near-static rows).
_SNAPSHOT_OUTCOMES_PER_MARKET = 14


def _norm(s: Optional[str]) -> str:
    """Diacritic-stripped, lowercased, whitespace-collapsed name key so a golfer
    matches across the leaderboard and a prop's outcome list ("Ludvig Åberg" ==
    "Ludvig Aberg")."""
    import re
    import unicodedata

    base = re.sub(r"\s+", " ", (s or "").strip().lower())
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", base) if not unicodedata.combining(ch)
    )


# Group/region prop names → the region label a member golfer belongs to. Used to
# correlate a golfer's scoring move with the "Region to Win" market. Data-driven:
# the golfer→region map is built from these props' OWN outcome lists, no hardcoded
# nationality database. Keys are lowercase substrings of the market name.
_GROUP_PROP_REGION = {
    "top american golfer": "United States",
    "top european golfer": "Europe",
    "top asian/oceanic golfer": "Asia/Oceania",
    "top liv golfer": None,  # LIV is a tour, not a region — membership only
}


def _market_key(child: dict) -> Optional[str]:
    mid = child.get("market_id")
    if isinstance(mid, int):
        return f"m{mid}"
    name = child.get("market_name") or child.get("name")
    return f"n{_norm(name)}" if name else None


def snapshot_state(envelope: dict) -> dict:
    """Compact, JSON-serializable snapshot of the current event state for diffing.

    Pure. Captures per-golfer leaderboard scoring/win-prob and every prop market's
    (bounded) outcome probabilities, plus a golfer→region map derived from the
    group props. The task stamps ``ts`` and stores this in Redis; the next run
    diffs against it.
    """
    competitors = (envelope.get("primary") or {}).get("competitors") or []
    leaderboard: dict[str, dict] = {}
    for c in competitors:
        name = c.get("name")
        if not name:
            continue
        # Per-golfer FINISH probabilities (DataGolf, 0-100) update at the live
        # cadence — these are the fast-moving "props" a birdie/bogey shifts, far
        # richer than restating win%. Normalize to 0-1 and keep only those present.
        fin: dict[str, float] = {}
        for src, label_key in _FINISH_MARKETS:
            v = _to_num(c.get(src))
            if v is not None:
                fin[label_key] = round(v / 100.0, 4)
        leaderboard[_norm(name)] = {
            "name": name,
            "today": _to_num(c.get("today_score")),
            "thru": _to_num(c.get("thru")),
            "pos": c.get("position"),
            "win": _to_num(c.get("probability")),  # 0-1
            "fin": fin,
        }

    props: dict[str, dict] = {}
    labels: dict[str, str] = {}
    golfer_region: dict[str, str] = {}
    for child in envelope.get("children") or []:
        key = _market_key(child)
        outs = child.get("outcomes") or []
        if not key or not outs:
            continue
        label = child.get("market_name") or child.get("name") or ""
        labels[key] = label
        # Keep the strongest outcomes only (bounded, longshot floor).
        ranked = sorted(
            (
                (o.get("name"), _to_num(o.get("probability")))
                for o in outs
                if o.get("name") and _to_num(o.get("probability")) is not None
            ),
            key=lambda t: t[1],
            reverse=True,
        )
        kept = {
            nm: round(p, 4)
            for nm, p in ranked[:_SNAPSHOT_OUTCOMES_PER_MARKET]
            if p >= _SNAPSHOT_PROB_FLOOR
        }
        if kept:
            props[key] = kept

        # Build golfer -> region from the group props' membership.
        label_l = label.lower()
        for frag, region in _GROUP_PROP_REGION.items():
            if frag in label_l and region:
                for o in outs:
                    nm = o.get("name")
                    if nm:
                        golfer_region.setdefault(_norm(nm), region)

    return {
        "leaderboard": leaderboard,
        "props": props,
        "labels": labels,
        "golfer_region": golfer_region,
    }


def _scoring_label(shots_gained: float, thru_advanced: Optional[float]) -> tuple[str, bool]:
    """(human label, is_single_hole) for a net score change over the interval.

    Only a single-hole advance (thru +1) with a clean ±1/±2 lets us name the hole;
    a multi-hole advance is reported as a shot count without a hole.
    """
    g = int(round(shots_gained))
    single = thru_advanced is not None and int(round(thru_advanced)) == 1
    if single:
        return (
            {2: "eagle", 1: "birdie", -1: "bogey", -2: "double bogey", -3: "triple bogey"}.get(
                g, ("gained" if g > 0 else "dropped") + f" {abs(g)} shots"
            ),
            True,
        )
    if g > 0:
        return (f"gained {g} shot{'s' if g != 1 else ''}", False)
    return (f"dropped {abs(g)} shot{'s' if abs(g) != 1 else ''}", False)


def diff_state(prev: Optional[dict], cur: dict) -> dict:
    """Diff two snapshots into scoring moves + prop moves. Pure.

    ``scoring``: golfers whose round score changed (a birdie/bogey happened) or
    whose win probability moved notably since the previous snapshot — each with a
    from->to and, when derivable (single-hole advance), the hole number.
    ``props``: prop outcomes whose probability moved at least ``_PROP_MOVE_POINTS``.
    Empty (both lists) when there is no previous snapshot or nothing moved.
    """
    out = {"scoring": [], "props": []}
    if not prev:
        return out

    prev_lb = prev.get("leaderboard") or {}
    cur_lb = cur.get("leaderboard") or {}
    for key, cnow in cur_lb.items():
        cprev = prev_lb.get(key)
        if not cprev:
            continue
        t_from, t_to = cprev.get("today"), cnow.get("today")
        thru_from, thru_to = cprev.get("thru"), cnow.get("thru")
        w_from, w_to = cprev.get("win"), cnow.get("win")
        score_changed = (
            t_from is not None and t_to is not None and int(round(t_to - t_from)) != 0
        )
        win_move = (
            round((w_to - w_from) * 100, 1)
            if (w_from is not None and w_to is not None)
            else None
        )
        # Per-golfer finish-market moves (Top 5/10/20) since the previous snapshot.
        fin_from, fin_to = cprev.get("fin") or {}, cnow.get("fin") or {}
        market_moves = []
        for label, p_to in fin_to.items():
            p_from = fin_from.get(label)
            if p_from is None:
                continue
            d = round((p_to - p_from) * 100, 1)
            if abs(d) >= _FINISH_MOVE_POINTS:
                market_moves.append(
                    {
                        "label": label,
                        "from_pct": _pct(p_from),
                        "to_pct": _pct(p_to),
                        "delta_pts": d,
                    }
                )
        market_moves.sort(key=lambda m: abs(m["delta_pts"]), reverse=True)

        notable_win = win_move is not None and abs(win_move) >= _WIN_MOVE_POINTS
        if not score_changed and not notable_win and not market_moves:
            continue
        entry = {
            "name": cnow.get("name"),
            "win_from_pct": _pct(w_from),
            "win_to_pct": _pct(w_to),
            "win_move_pts": round(win_move, 1) if win_move is not None else None,
            "made": None,
            "hole": None,
            "thru_to": int(thru_to) if thru_to is not None else None,
            "score_to_par": None,
            "market_moves": market_moves[:2],
        }
        if score_changed:
            thru_adv = (
                thru_to - thru_from
                if (thru_from is not None and thru_to is not None)
                else None
            )
            made, single = _scoring_label(-(t_to - t_from), thru_adv)
            entry["made"] = made
            entry["hole"] = int(thru_to) if (single and thru_to is not None) else None
            entry["score_to_par"] = int(t_to) if t_to is not None else None
        out["scoring"].append(entry)

    prev_props = prev.get("props") or {}
    cur_props = cur.get("props") or {}
    labels = cur.get("labels") or {}
    for key, outcomes in cur_props.items():
        base = prev_props.get(key) or {}
        for nm, p_to in outcomes.items():
            p_from = base.get(nm)
            if p_from is None:
                continue
            # Round before the threshold test — otherwise an exact 3.0-pt move
            # (0.43-0.40 == 2.9999999996 in float) is silently dropped.
            delta = round((p_to - p_from) * 100, 1)
            if abs(delta) >= _PROP_MOVE_POINTS:
                out["props"].append(
                    {
                        "market": labels.get(key, key),
                        "outcome": nm,
                        "from_pct": _pct(p_from),
                        "to_pct": _pct(p_to),
                        "delta_pts": delta,
                    }
                )

    # Biggest moves first; bound what reaches the prompt. A scoring event (birdie/
    # bogey) and a finish-market swing both raise a golfer's newsworthiness.
    def _score_weight(e: dict) -> float:
        w = abs(e.get("win_move_pts") or 0)
        w += 3 if e.get("made") else 0
        mm = e.get("market_moves") or []
        w += max((abs(m["delta_pts"]) for m in mm), default=0)
        return w

    out["scoring"].sort(key=_score_weight, reverse=True)
    out["props"].sort(key=lambda p: abs(p["delta_pts"]), reverse=True)
    out["scoring"] = out["scoring"][:5]
    out["props"] = out["props"][:6]
    return out


def correlate_moves(diff: dict, cur: dict) -> list[dict]:
    """Link prop moves to a golfer's scoring/win move in the same window. Pure.

    A prop move is correlated when a moved golfer is (a) a named outcome of that
    same prop, or (b) a member of the region the prop is about (Region-to-Win via
    the golfer→region map). Only same-direction pairs are kept (a golfer gaining
    shots explaining an outcome rising), so the narrative is honest co-occurrence.
    """
    scoring = diff.get("scoring") or []
    props = diff.get("props") or []
    if not scoring or not props:
        return []

    by_name = {_norm(s["name"]): s for s in scoring if s.get("name")}
    golfer_region = cur.get("golfer_region") or {}
    correlations: list[dict] = []
    seen: set = set()

    for pm in props:
        outcome_norm = _norm(pm["outcome"])
        market_l = (pm["market"] or "").lower()
        gained_dir = 1 if pm["delta_pts"] > 0 else -1
        match = None

        # (a) direct membership: the outcome IS a moved golfer.
        s = by_name.get(outcome_norm)
        if s:
            match = s
        # (b) region prop (e.g. "Region to Win" -> "United States"): find a moved
        # golfer of that region whose move direction matches.
        elif "region" in market_l or "win" in market_l:
            region = pm["outcome"]
            for sn, srec in by_name.items():
                if golfer_region.get(sn) == region:
                    sdir = 1 if (srec.get("win_move_pts") or 0) >= 0 else -1
                    if not srec.get("win_move_pts") or sdir == gained_dir:
                        match = srec
                        break

        if not match:
            continue
        # Same-direction guard for the direct case: a golfer gaining shots should
        # correspond to their outcome RISING (not falling).
        sdir = 1
        if match.get("win_move_pts") is not None:
            sdir = 1 if match["win_move_pts"] >= 0 else -1
        elif match.get("made"):
            sdir = 1 if match["made"] in ("birdie", "eagle") or "gained" in match["made"] else -1
        if sdir != gained_dir:
            continue

        dedup = (pm["market"], pm["outcome"], match["name"])
        if dedup in seen:
            continue
        seen.add(dedup)
        correlations.append({**pm, "golfer": match})

    return correlations[:4]


def build_digest_prompt(
    event_name: Optional[str],
    diff: dict,
    correlations: list[dict],
    seed: dict,
) -> Optional[str]:
    """Build the 'what just moved' prompt. Pure.

    Prefers correlated scoring+market moves, then other market moves, then a brief
    leaderboard anchor. Falls back to the ``seed`` (current standings + today's
    movers) when there is nothing new to report (first run / quiet stretch), so
    the box is never empty on a live page.
    """
    name = event_name or "The Open Championship"
    scoring = diff.get("scoring") or []
    props = diff.get("props") or []

    if not scoring and not props:
        # Nothing changed since last update — seed a current-state summary instead.
        return build_commentary_prompt(event_name, seed)

    lines = [
        f"Live update for {name}. Report ONLY what changed since the last "
        f"snapshot (~3 minutes ago). Numbers only — use nothing else.",
        "",
    ]

    def _golfer_ctx(s: dict) -> str:
        bits = []
        if s.get("made") and s.get("hole"):
            bits.append(f"made {s['made']} at hole {s['hole']}")
        elif s.get("made"):
            bits.append(s["made"])
        if s.get("thru_to") is not None:
            bits.append(f"through {s['thru_to']} holes")
        if s.get("score_to_par") is not None:
            par = _fmt_par(s["score_to_par"])
            if par:
                bits.append(f"now {par}")
        # Include the win-probability line only when it actually moved notably, or
        # when there's no other market signal — otherwise "0%->0%" is pure noise.
        wm = s.get("win_move_pts")
        win_notable = wm is not None and abs(wm) >= _WIN_MOVE_POINTS
        mm = s.get("market_moves") or []
        if (
            s.get("win_from_pct") is not None
            and s.get("win_to_pct") is not None
            and (win_notable or not mm)
        ):
            bits.append(
                f"win probability {s['win_from_pct']}%->{s['win_to_pct']}%"
            )
        for m in mm:
            bits.append(f"{m['label']} chances {m['from_pct']}%->{m['to_pct']}%")
        return ", ".join(bits)

    if correlations:
        lines.append("SCORING EVENTS THAT MOVED A MARKET (report these first):")
        for c in correlations:
            g = c["golfer"]
            lines.append(
                f"  - {g['name']} {_golfer_ctx(g)}; the '{c['market']}' market "
                f"outcome '{c['outcome']}' moved {c['from_pct']}%->{c['to_pct']}% "
                f"({'+' if c['delta_pts'] > 0 else ''}{c['delta_pts']} pts)"
            )
        lines.append("")

    correlated_pairs = {(c["market"], c["outcome"]) for c in correlations}
    other_props = [p for p in props if (p["market"], p["outcome"]) not in correlated_pairs]
    if other_props:
        lines.append("OTHER MARKET MOVES:")
        for p in other_props:
            lines.append(
                f"  - '{p['market']}' — '{p['outcome']}': {p['from_pct']}%->"
                f"{p['to_pct']}% ({'+' if p['delta_pts'] > 0 else ''}{p['delta_pts']} pts)"
            )
        lines.append("")

    correlated_golfers = {_norm(c["golfer"]["name"]) for c in correlations}
    other_scoring = [
        s for s in scoring if _norm(s.get("name")) not in correlated_golfers
    ]
    if other_scoring:
        lines.append("GOLFER MOVES (scoring + finish-market probabilities):")
        for s in other_scoring:
            lines.append(f"  - {s['name']}: {_golfer_ctx(s)}")
        lines.append("")

    leaders = seed.get("leaders") or []
    if leaders:
        lead = leaders[0]
        anchor = _fmt_competitor_line(lead)
        lines.append(f"CURRENT LEADER (context): {anchor}")
        lines.append("")

    lines.append(
        "Write 2-4 sentences on what just moved. Lead with a scoring event that "
        "shifted a golfer's chances (connect them with 'as'/'after', give the "
        "from->to numbers, name the hole ONLY if a hole number is given). Prefer "
        "moves tied to scoring over a bare win-probability number. Use only the "
        "names, numbers, holes, and markets above."
    )
    return "\n".join(lines)


def generate_from_snapshots(
    event_name: Optional[str],
    cur: dict,
    prev: Optional[dict],
    status: str,
    competitors: list[dict],
) -> Optional[str]:
    """Change-detector entry point (the task calls this). Returns the update text,
    or None.

    LIVE-ONLY: no OpenAI call unless ``status == 'live'``. Diffs cur vs prev,
    correlates scoring with market moves, and generates the 'what just moved'
    digest. On a quiet stretch (or the very first run with no prev) it falls back
    to a current-state summary so the box is never empty. Any failure -> None.
    """
    if status != "live":
        return None

    diff = diff_state(prev, cur)
    correlations = correlate_moves(diff, cur)
    seed = select_commentary_data(competitors)
    prompt = build_digest_prompt(event_name, diff, correlations, seed)
    if not prompt:
        return None

    try:
        from app.services.llm import generate_golf_live_commentary

        text = generate_golf_live_commentary(prompt)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("generate_from_snapshots failed: %s", exc)
        return None

    if not text or not text.strip():
        return None
    return text.strip()


def has_new_moves(diff: dict) -> bool:
    """True if the diff contains any scoring or prop move worth regenerating for.
    A quiet stretch (no moves) lets the task skip the OpenAI call and just refresh
    the existing blurb's TTL."""
    return bool((diff.get("scoring") or []) or (diff.get("props") or []))


def generate_commentary(
    event_name: Optional[str],
    competitors: list[dict],
    status: str,
) -> Optional[str]:
    """Seed/first-run generator (current standings + today's movers).

    Retained as the no-previous-snapshot fallback and for direct unit tests.
    LIVE-ONLY; returns None on any unavailable/empty/error path (-> no box).
    Performs the synchronous OpenAI call, so task-only.
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
