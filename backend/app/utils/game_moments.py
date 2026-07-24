"""THE MOMENTS ENGINE — the pure join (#1168).

DataGolf's lesson (architecture, not UI): a "key moment" is a JOIN of two
timestamped streams — the real-world EVENT stream (scoring plays) and the
PROBABILITY stream (win-prob snapshots) — not an inference. This module owns the
pure, deterministic math: given an event's scoring plays and its WP snapshot
series, attach each play to the win-probability swing it caused and score a
CONFIDENCE from the #871 explainability gate.

Alex's #871 ruling governs: *no confident cause → NO annotation* (nothing beats
unhelpful). A moment is a confident cause only if the swing is (a) in the right
DIRECTION for the scoring team, (b) big enough to matter, and (c) the UNIQUE
scoring play in its measurement window. The offline task stores every raw moment
(the event happened) but the history payload surfaces only rows at/above the gate.

Zero heavy imports — safe to unit-test with synthetic dicts (no DB, no network).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

# --- tuning knobs (deltas are on the 0..1 win-prob scale) -------------------
MIN_DELTA = 0.03  # < 3 points: the play didn't move the needle → not a moment
FULL_MAGNITUDE_DELTA = 0.15  # a 15-point swing earns the full magnitude bonus
CONFIDENCE_GATE = 0.5  # #871: rows below this are stored but never surfaced
_AMBIGUITY_PENALTY = 0.7  # another scoring play shares the window → discount


def _norm_team(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def _team_matches(a: str, b: str) -> bool:
    """Containment-tolerant team match — ESPN's play displayName ("New York
    Yankees") vs our Event team name ("Yankees") need not be byte-equal."""
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _to_prob(v) -> Optional[float]:
    """Coerce a probability that may arrive as a % (0..100) or a fraction (0..1)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f > 1.0:
        f = f / 100.0
    if f < 0.0 or f > 1.0:
        return None
    return f


def _moment_type(description: str, play_type: Optional[str]) -> str:
    d = (description or "").lower()
    if "home run" in d or "homer" in d or "homers" in d or "grand slam" in d:
        return "home_run"
    if play_type:
        return play_type
    return "score"


def _confidence(delta: float, direction_ok: bool, ambiguous: bool) -> Optional[float]:
    """#871 gate. Direction-inconsistent → no confident cause → None (no
    annotation). Otherwise base plausibility + a magnitude bonus, discounted when
    the window holds another candidate play (ambiguous attribution)."""
    if not direction_ok:
        return None
    mag = min(max(delta, 0.0) / FULL_MAGNITUDE_DELTA, 1.0)
    conf = 0.5 + 0.5 * mag
    if ambiguous:
        conf *= _AMBIGUITY_PENALTY
    return round(conf, 3)


def _format_label(
    team_display: Optional[str],
    delta: float,
    moment_type: str,
    player: Optional[str],
) -> str:
    """Deterministic, source-data-only label (#871: name the mover, no LLM).
    e.g. "Yankees home run — win prob +12.3 pts"."""
    pts = f"+{delta * 100:.1f} pts"
    verb = {
        "home_run": "home run",
        "goal": "goal",
        "touchdown": "touchdown",
    }.get(moment_type, "score")
    who = player or team_display or "Team"
    return f"{who} {verb} — win prob {pts}"


def _find_transition(
    snapshots: list[dict], home_score: Optional[int], away_score: Optional[int]
) -> Optional[int]:
    """Index of the first snapshot whose game score first REACHES (home, away).
    That snapshot carries the post-play probability; the score is the bridge
    between the two streams (MLB/ESPN snapshots carry game_state scores)."""
    if home_score is None or away_score is None:
        return None
    for i, s in enumerate(snapshots):
        if s.get("home_score") == home_score and s.get("away_score") == away_score:
            return i
    return None


def compute_moments(
    scoring_plays: list[dict],
    snapshots: list[dict],
    home_team: Optional[str],
    away_team: Optional[str],
    *,
    source: str = "espn",
    min_delta: float = MIN_DELTA,
) -> list[dict]:
    """Join scoring plays to win-prob swings.

    scoring_plays: dicts with home_score, away_score, team (or team_name),
        description, period, player_name/player, type/play_type.
    snapshots: WP series sorted ascending by ts — dicts with ts (datetime),
        home_prob (0..1 or 0..100), home_score, away_score.
    Returns moment dicts ready to persist (see GameMoment columns). Direction is
    judged against home/away team names; prob_delta is the magnitude on the
    scoring team's side. Rows whose cause isn't confident carry confidence=None.
    """
    snaps = [
        s
        for s in snapshots
        if isinstance(s.get("ts"), datetime) and _to_prob(s.get("home_prob")) is not None
    ]
    snaps.sort(key=lambda s: s["ts"])
    home_n, away_n = _norm_team(home_team), _norm_team(away_team)

    # Pre-index the (home,away) score → first-reaching snapshot for ambiguity check.
    play_scores = [
        (p.get("home_score"), p.get("away_score")) for p in scoring_plays
    ]

    moments: list[dict] = []
    for idx, play in enumerate(scoring_plays):
        h, a = play.get("home_score"), play.get("away_score")
        ti = _find_transition(snaps, h, a)
        if ti is None or ti == 0:
            # No matched snapshot, or the score was already there at the first
            # snapshot (no measurable pre-state) → keep the event but no join.
            continue
        post = _to_prob(snaps[ti].get("home_prob"))
        pre = _to_prob(snaps[ti - 1].get("home_prob"))
        if post is None or pre is None:
            continue
        ts = snaps[ti]["ts"]
        delta_home = post - pre

        team = _norm_team(play.get("team") or play.get("team_name"))
        # Direction: the scoring team's own win prob should rise.
        if team and _team_matches(team, home_n):
            signed = delta_home
        elif team and _team_matches(team, away_n):
            signed = -delta_home
        else:
            # Unknown scoring team — infer from which score advanced vs prev play.
            signed = abs(delta_home)
        delta = abs(signed)
        direction_ok = signed >= 0 and delta >= min_delta

        # Ambiguity: another scoring play maps to a snapshot within ±1 index.
        ambiguous = False
        for j, (ph, pa) in enumerate(play_scores):
            if j == idx:
                continue
            tj = _find_transition(snaps, ph, pa)
            if tj is not None and abs(tj - ti) <= 1:
                ambiguous = True
                break

        conf = _confidence(delta, direction_ok, ambiguous)
        mtype = _moment_type(play.get("description", ""), play.get("type") or play.get("play_type"))
        team_display = play.get("team") or play.get("team_name")
        player = play.get("player_name") or play.get("player")
        label = (
            _format_label(team_display, delta, mtype, player)
            if conf is not None
            else None
        )
        moments.append(
            {
                "ts": ts,
                "moment_type": mtype,
                "description": play.get("description") or "",
                "actor_team": team_display,
                "actor_player": player,
                "period": play.get("period"),
                "home_score": h,
                "away_score": a,
                "source": source,
                "prob_delta": round(delta, 4),
                "confidence": conf,
                "label": label,
                "dedupe_key": _dedupe_key(source, h, a, play.get("description")),
            }
        )
    return moments


def _dedupe_key(source: str, h, a, description: Optional[str]) -> str:
    desc = (description or "")[:40].strip().lower().replace(" ", "_")
    return f"{source}:{h}-{a}:{desc}"[:120]


def synth_scoring_plays_from_snapshots(
    snapshots: list[dict],
    home_team: Optional[str],
    away_team: Optional[str],
) -> list[dict]:
    """Derive scoring plays from win-prob snapshot SCORE transitions.

    MLB's ESPN box_score_data.scoring_plays is empty (the provider doesn't emit
    baseball scoring plays), but our mlb/stat_model snapshots carry game_state
    scores AND a wall-clock ts. Each snapshot where the score advances is a scoring
    event: the team whose score rose is the actor. These synthesized plays feed the
    same score-matched join + #871 gate as real plays. Descriptions are honest and
    source-data-only ("Phillies scored — now 3-2"); richer play text (the batter)
    is a v1.1 enrichment from the MLB per-at-bat feed."""
    snaps = [
        s
        for s in snapshots
        if isinstance(s.get("ts"), datetime)
        and s.get("home_score") is not None
        and s.get("away_score") is not None
    ]
    snaps.sort(key=lambda s: s["ts"])
    plays: list[dict] = []
    prev_h = prev_a = None
    for s in snaps:
        h, a = s["home_score"], s["away_score"]
        if prev_h is not None and (h != prev_h or a != prev_a):
            if h > prev_h and a == prev_a:
                team, runs = home_team, h - prev_h
            elif a > prev_a and h == prev_h:
                team, runs = away_team, a - prev_a
            else:
                team, runs = None, 0  # simultaneous/correction — ambiguous actor
            if team:
                plural = "s" if runs != 1 else ""
                plays.append(
                    {
                        "home_score": h,
                        "away_score": a,
                        "team": team,
                        "description": f"{team} scored {runs} run{plural} — now {a}-{h}",
                        "period": s.get("period"),
                        "type": "score",
                    }
                )
        prev_h, prev_a = h, a
    return plays


def confident_moments(moments: list[dict], gate: float = CONFIDENCE_GATE) -> list[dict]:
    """The subset the history payload surfaces: cause confident enough to help."""
    out = [
        m
        for m in moments
        if m.get("confidence") is not None and float(m["confidence"]) >= gate
    ]
    out.sort(key=lambda m: (m.get("ts") or datetime.min))
    return out


def _desc_tokens(text: Optional[str]) -> set[str]:
    """Distinctive (len>=4, alpha) description tokens — player surnames, verbs like
    "homers"/"doubles" — for cross-source play matching."""
    import re

    return {
        t
        for t in re.split(r"[^a-z]+", (text or "").lower())
        if len(t) >= 4
    }


def agreement_rate(our_moments: list[dict], mlb_entries: list[dict]) -> dict:
    """MLB ground-truth validation gate (#1168). Compare our confident moments
    against MLB's OWN per-at-bat win probability (the source attributes WP to each
    play). MLB's series carries a description + WP per at-bat but no score, so we
    match on play DESCRIPTION overlap: agreement = for each confident moment, does
    an MLB at-bat whose description shares a distinctive token ALSO show a
    ≥MIN_DELTA win-prob swing?

    mlb_entries: dicts with ``description`` and ``home_win_probability`` (0..1),
        ordered by at-bat. Returns {checked, agreed, rate}. Poor agreement is the
        signal to ship the TABLE but HOLD the annotations."""
    confident = confident_moments(our_moments)
    if not confident:
        return {"checked": 0, "agreed": 0, "rate": None}

    # Per-at-bat MLB home-prob swings paired with their description tokens.
    mlb_swings: list[tuple[set[str], float]] = []
    prev = None
    for e in mlb_entries:
        hp = _to_prob(e.get("home_win_probability"))
        if hp is not None and prev is not None:
            mlb_swings.append((_desc_tokens(e.get("description")), abs(hp - prev)))
        if hp is not None:
            prev = hp

    agreed = 0
    for m in confident:
        mtok = _desc_tokens(m.get("description"))
        if not mtok:
            continue
        for toks, mag in mlb_swings:
            if mag >= MIN_DELTA and (mtok & toks):
                agreed += 1
                break
    checked = len(confident)
    return {
        "checked": checked,
        "agreed": agreed,
        "rate": round(agreed / checked, 3) if checked else None,
    }
