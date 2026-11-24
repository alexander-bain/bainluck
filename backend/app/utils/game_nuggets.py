"""Game-page below-the-charts nugget ranker (#13511, Ruling 355: A).

Builds up to 12 ranked nuggets across six uniform kinds from existing
``/game-markets``, ``/related-futures``, and ``/team-progression`` payloads
without inventing per-sport components, padding sparse sports, leaking venue
names or American odds, or letting a game's own props masquerade as season
stakes.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Optional

NUGGET_KINDS: tuple[str, ...] = (
    "game_flow",
    "players",
    "teams",
    "moments",
    "stakes",
    "oddities",
)

NUGGET_KIND_LABELS: dict[str, str] = {
    "game_flow": "Game flow",
    "players": "Players",
    "teams": "Teams",
    "moments": "Moments",
    "stakes": "Stakes",
    "oddities": "Oddities",
}

NUGGET_KIND_TARGETS: dict[str, str] = {
    "game_flow": "totals-spreads",
    "players": "player-props",
    "teams": "team-totals",
    "moments": "period-markets",
    "stakes": "related-futures",
    "oddities": "other-markets",
}

NUGGET_FORMS: tuple[str, ...] = (
    "duel_bar",
    "ladder",
    "pregame_vs_now",
    "history_line",
    "faces_row",
)

NUGGET_FIRST_EIGHT = 8
NUGGET_DEFAULT_LIMIT = 12
NUGGET_MAX_PER_KIND_FIRST_EIGHT = 2
NUGGET_MAX_PER_KIND_EXTENDED = 3
NUGGET_MAX_OBSERVED_AGE_HOURS = 48.0
NUGGET_LIVE_MAX_OBSERVED_AGE_HOURS = 6.0

_VENUE_RE = re.compile(
    r"\b(?:kalshi|polymarket|draftkings|fanduel|betmgm|caesars|betrivers|espn\s*bet|fanatics|bet365|pinnacle|bovada)\b",
    re.IGNORECASE,
)
_QUESTION_WORD_RE = re.compile(r"\bquestions\b", re.IGNORECASE)
_QUESTION_SINGULAR_RE = re.compile(r"\bquestion\b", re.IGNORECASE)
_AMERICAN_ODDS_PAREN_RE = re.compile(r"\(\s*[+-]\d{3,5}\s*\)")
_AMERICAN_ODDS_INLINE_RE = re.compile(r"(?<!\w)[+-]\d{3,5}(?!\w)")
_MULTISPACE_RE = re.compile(r"\s{2,}")

_GAME_OWN_CATEGORIES = (
    "prop",
    "player_prop",
    "game_prop",
    "team_total",
    "spread",
    "total",
    "quarter",
    "half",
    "period",
    "moneyline",
    "game_line",
)
_GAME_OWN_NAME_HINT_RE = re.compile(
    r"\b(?:anytime touchdown|first touchdown|first score|passing yards|rushing yards|"
    r"receiving yards|receptions|three pointers|rebounds|assists|1q|2q|3q|4q|1h|2h|"
    r"o/u\s*\d|over/under\s*\d)\b",
    re.IGNORECASE,
)
_WINNER_NOISE_RE = re.compile(
    r"\b(?:moneyline|match winner|match result|3-way|three-way|full time result)\b",
    re.IGNORECASE,
)


def sanitize_nugget_text(text: str) -> str:
    """Enforce wording rules (#13511): no venue names, no 'question', no American odds."""
    if not text:
        return ""
    cleaned = _QUESTION_WORD_RE.sub("markets", text)
    cleaned = _QUESTION_SINGULAR_RE.sub("market", cleaned)
    cleaned = _AMERICAN_ODDS_PAREN_RE.sub("", cleaned)
    cleaned = _AMERICAN_ODDS_INLINE_RE.sub("", cleaned)
    cleaned = _VENUE_RE.sub("", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+([,.:;!?])", r"\1", cleaned)
    cleaned = _MULTISPACE_RE.sub(" ", cleaned).strip(" :-–—|")
    return cleaned


def _parse_iso_utc(raw: Any) -> Optional[datetime]:
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw.astimezone(timezone.utc)
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _valid_prob(val: Any) -> Optional[float]:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    f = float(val)
    if f <= 0.01 or f >= 0.99:
        return None
    return f


def _is_fresh_and_priced(
    row: Mapping[str, Any],
    *,
    prob: Any,
    now: datetime,
    max_age_hours: float,
    excluded_counts: Counter[str],
    timestamp_key: str = "observed_at",
) -> Optional[float]:
    sm = row.get("source_mark")
    if isinstance(sm, Mapping) and sm.get("state") in {"withheld", "none"}:
        excluded_counts["unpriced_or_extreme"] += 1
        return None
    p = _valid_prob(prob)
    if p is None:
        excluded_counts["unpriced_or_extreme"] += 1
        return None
    ts_raw = row.get(timestamp_key) or row.get("last_updated") or row.get("observed_at")
    ts = _parse_iso_utc(ts_raw)
    if ts is not None:
        age_hours = (now - ts).total_seconds() / 3600.0
        if age_hours > max_age_hours:
            excluded_counts["stale"] += 1
            return None
    return p


def _format_num(val: Any) -> str:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return ""
    f = float(val)
    if f.is_integer():
        return str(int(f))
    return f"{f:g}"


def _extract_movement(
    *,
    prob: float,
    pregame_mark: Any = None,
    change_24h: Any = None,
    allow_pregame_mark: bool = False,
) -> tuple[Optional[int], Optional[str], Optional[int]]:
    """Return ``(change_points, change_since, pregame_percent)`` using dated readings only.

    Never reads placeholder ``opening_probability``; ``pregame_mark`` is only
    honored on a game's own markets once kickoff has passed.
    """
    now_pct = int(round(prob * 100.0))
    if allow_pregame_mark and not isinstance(pregame_mark, bool) and isinstance(pregame_mark, (int, float)):
        ref = float(pregame_mark)
        if 0.0 <= ref <= 1.0:
            ref_pct = int(round(ref * 100.0))
            diff = now_pct - ref_pct
            return diff, "pregame", ref_pct
    if not isinstance(change_24h, bool) and isinstance(change_24h, (int, float)):
        diff = int(round(float(change_24h) * 100.0))
        return diff, "24h", None
    return None, None, None


def _select_nugget_form(
    *,
    change_points: Optional[int],
    change_since: Optional[str],
    default_form: str,
) -> str:
    if change_since == "pregame" and change_points is not None and abs(change_points) >= 3:
        return "pregame_vs_now"
    return default_form


def _closeness_score(prob: float) -> float:
    return max(0.0, 1.0 - 2.0 * abs(prob - 0.5))


def _compute_score(
    *,
    prob: float,
    change_points: Optional[int],
    change_since: Optional[str] = None,
    is_live: bool,
    source_count: int = 1,
    has_picture: bool = False,
    stakes_tier: Optional[int] = None,
    base_bonus: float = 0.0,
) -> tuple[float, str]:
    reasons: list[str] = []
    score = base_bonus

    move_abs = abs(change_points) if change_points is not None else 0
    if move_abs > 0:
        move_w = move_abs * (5.2 if is_live else 4.5)
        score += move_w
        sign = "+" if (change_points or 0) > 0 else ""
        pt_word = "point" if move_abs == 1 else "points"
        when = "since pregame" if change_since == "pregame" else "in 24h"
        reasons.append(f"Moved {sign}{change_points} {pt_word} {when}")

    close = _closeness_score(prob)
    score += close * 18.0
    if close >= 0.7:
        reasons.append("close to even")

    if is_live and 0.15 <= prob <= 0.85:
        score += 6.0
        reasons.append("live shift")

    if source_count >= 2:
        score += min(source_count, 5) * 3.0
        reasons.append("multi-source")

    if has_picture:
        score += 4.0

    if stakes_tier is not None and stakes_tier <= 2:
        score += 10.0 if stakes_tier == 1 else 6.0
        reasons.append("season stakes")

    if not reasons:
        reasons.append("top active market")

    return score, " · ".join(reasons[:3])


def _collect_game_market_ids(game_markets: Mapping[str, Any]) -> set[int]:
    ids: set[int] = set()
    for sec in ("totals", "spreads", "team_totals", "player_props", "period_markets", "other"):
        for row in game_markets.get(sec) or ():
            if isinstance(row, Mapping):
                mid = row.get("_market_id") or row.get("market_id")
                if isinstance(mid, int):
                    ids.add(mid)
    om_map = game_markets.get("outcome_market_ids")
    if isinstance(om_map, Mapping):
        for val in om_map.values():
            if isinstance(val, int):
                ids.add(val)
    for mid in game_markets.get("stream_market_ids") or ():
        if isinstance(mid, int):
            ids.add(mid)
    return ids


def _is_game_own_futures_row(
    row: Mapping[str, Any],
    *,
    game_market_ids: set[int],
    home_team: str,
    away_team: str,
) -> bool:
    mid = row.get("market_id")
    if isinstance(mid, int) and mid in game_market_ids:
        return True
    dc = str(row.get("display_category") or row.get("category") or "").strip().lower()
    if any(tok in dc for tok in _GAME_OWN_CATEGORIES):
        return True
    mname = str(row.get("market_name") or "")
    low_name = mname.lower()
    if _GAME_OWN_NAME_HINT_RE.search(mname):
        return True
    h_low = home_team.strip().lower()
    a_low = away_team.strip().lower()
    if h_low and a_low and h_low in low_name and a_low in low_name:
        if any(k in low_name for k in ("spread", "total", "quarter", "half", "winner", "prop")):
            return True
    return False


def _total_unit_word(sport: str) -> str:
    s = (sport or "").lower()
    if "soccer" in s:
        return "goals"
    if "hockey" in s or "nhl" in s:
        return "goals"
    if "baseball" in s or "mlb" in s:
        return "runs"
    return "points"


def _team_subject(
    team_name: str,
    *,
    home_team: str,
    away_team: str,
    home_logo: Optional[str],
    away_logo: Optional[str],
) -> dict[str, Any]:
    clean_name = team_name.strip() or home_team
    low = clean_name.lower()
    logo: Optional[str] = None
    if away_team and (low == away_team.lower() or away_team.lower() in low):
        logo = away_logo
        clean_name = away_team
    elif home_team and (low == home_team.lower() or home_team.lower() in low):
        logo = home_logo
        clean_name = home_team
    return {
        "name": clean_name,
        "image_url": logo,
        "image_kind": "logo" if logo else None,
    }


def _candidate_dict(
    *,
    nid: str,
    kind: str,
    subject: dict[str, Any],
    claim: str,
    prob: float,
    change_points: Optional[int],
    change_since: Optional[str],
    pregame_percent: Optional[int],
    form: str,
    rank_reason: str,
    score: float,
    observed_at: Optional[str],
    source_surface: str,
    source_market_id: Optional[int] = None,
    source_outcome_id: Optional[int] = None,
    dedup_key: Optional[str] = None,
) -> dict[str, Any]:
    clean_claim = sanitize_nugget_text(claim)
    clean_reason = sanitize_nugget_text(rank_reason)
    return {
        "id": nid,
        "kind": kind,
        "kind_label": NUGGET_KIND_LABELS[kind],
        "subject": subject,
        "claim": clean_claim,
        "probability": prob,
        "percent": int(round(prob * 100.0)),
        "change_points": change_points,
        "change_since": change_since,
        "pregame_percent": pregame_percent,
        "form": form,
        "rank_reason": clean_reason,
        "score": round(score, 2),
        "observed_at": observed_at,
        "source_surface": source_surface,
        "source_market_id": source_market_id,
        "source_outcome_id": source_outcome_id,
        "_dedup_key": dedup_key or nid,
    }


_MATCHUP_PREFIX_RE = re.compile(
    r"^[^:]+?\b(?:vs\.?|versus|@|at)\b[^:]*:\s*",
    re.IGNORECASE,
)
_PERIOD_TOKEN_RE = re.compile(
    r"\b(1Q|Q1|2Q|Q2|3Q|Q3|4Q|Q4|1H|H1|2H|H2|OT|1P|2P|3P|"
    r"1st\s+quarter|first\s+quarter|2nd\s+quarter|second\s+quarter|"
    r"3rd\s+quarter|third\s+quarter|4th\s+quarter|fourth\s+quarter|"
    r"1st\s+half|first\s+half|2nd\s+half|second\s+half|overtime)\b",
    re.IGNORECASE,
)
_OU_LINE_RE = re.compile(
    r"\b(?:o/u|over/under|total(?:\s+points|\s+goals|\s+runs)?)\b[^0-9+-]*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_PAREN_LINE_RE = re.compile(r"\(([+-]?[0-9]+(?:\.[0-9]+)?)\)")
_SIDE_PAREN_RE = re.compile(r"\(\s*(over|under)\s*\)", re.IGNORECASE)
_UNREADABLE_CLAIM_RE = re.compile(r"[:?]|\bo/u\b|\bover/under\b|\bvs\.?\b", re.IGNORECASE)


def _strip_matchup_prefix(raw: str) -> str:
    text = sanitize_nugget_text(raw or "")
    for _ in range(2):
        nxt = _MATCHUP_PREFIX_RE.sub("", text).strip(" :-–—|")
        if nxt == text:
            break
        text = nxt
    return text


def _plain_period_phrases(period_raw: str, market_name: str = "") -> Optional[tuple[str, str]]:
    for src in (period_raw, market_name):
        if not src:
            continue
        m = _PERIOD_TOKEN_RE.search(src)
        token = (m.group(1) if m else src).strip().lower()
        token = re.sub(r"\s+", " ", token)
        mapping = {
            "1q": ("in the first quarter", "the first quarter"),
            "q1": ("in the first quarter", "the first quarter"),
            "1st quarter": ("in the first quarter", "the first quarter"),
            "first quarter": ("in the first quarter", "the first quarter"),
            "2q": ("in the second quarter", "the second quarter"),
            "q2": ("in the second quarter", "the second quarter"),
            "2nd quarter": ("in the second quarter", "the second quarter"),
            "second quarter": ("in the second quarter", "the second quarter"),
            "3q": ("in the third quarter", "the third quarter"),
            "q3": ("in the third quarter", "the third quarter"),
            "3rd quarter": ("in the third quarter", "the third quarter"),
            "third quarter": ("in the third quarter", "the third quarter"),
            "4q": ("in the fourth quarter", "the fourth quarter"),
            "q4": ("in the fourth quarter", "the fourth quarter"),
            "4th quarter": ("in the fourth quarter", "the fourth quarter"),
            "fourth quarter": ("in the fourth quarter", "the fourth quarter"),
            "1h": ("in the first half", "the first half"),
            "h1": ("in the first half", "the first half"),
            "1st half": ("in the first half", "the first half"),
            "first half": ("in the first half", "the first half"),
            "2h": ("in the second half", "the second half"),
            "h2": ("in the second half", "the second half"),
            "2nd half": ("in the second half", "the second half"),
            "second half": ("in the second half", "the second half"),
            "ot": ("in overtime", "overtime"),
            "overtime": ("in overtime", "overtime"),
            "1p": ("in the first period", "the first period"),
            "2p": ("in the second period", "the second period"),
            "3p": ("in the third period", "the third period"),
        }
        if token in mapping:
            return mapping[token]
    return None


def _resolve_team_display(raw: str, *, home_team: str, away_team: str) -> str:
    clean = sanitize_nugget_text(raw or "").strip()
    low = clean.lower()
    if not clean:
        return ""
    if away_team and (low == away_team.lower() or low in away_team.lower() or away_team.lower() in low):
        return away_team
    if home_team and (low == home_team.lower() or low in home_team.lower() or home_team.lower() in low):
        return home_team
    return clean


def _looks_like_clean_claim(claim: str) -> bool:
    if not claim or len(claim.strip()) < 6:
        return False
    return not _UNREADABLE_CLAIM_RE.search(claim)


def _plain_moment_claim(
    row: Mapping[str, Any],
    *,
    home_team: str,
    away_team: str,
    unit: str,
) -> Optional[str]:
    period_raw = str(row.get("period") or "").strip()
    mname_clean = _strip_matchup_prefix(str(row.get("market_name") or ""))
    oname_clean = sanitize_nugget_text(str(row.get("outcome_name") or ""))
    side_paren = _SIDE_PAREN_RE.search(mname_clean)
    mname_no_side = _SIDE_PAREN_RE.sub("", mname_clean).strip()
    phrases = _plain_period_phrases(period_raw, mname_no_side)
    if phrases is None:
        return None
    period_in, period_noun = phrases

    # 1. Period totals (e.g. "3Q O/U 13.5" + Under -> "Under 13.5 points in the third quarter")
    side_word: Optional[str] = None
    for cand_side in (oname_clean, str(row.get("side") or ""), side_paren.group(1) if side_paren else ""):
        low_s = cand_side.strip().lower()
        if low_s.startswith("under"):
            side_word = "Under"
            break
        if low_s.startswith("over"):
            side_word = "Over"
            break
    ou_m = _OU_LINE_RE.search(mname_no_side)
    num_str = _format_num(row.get("threshold")) or (ou_m.group(1) if ou_m else "")
    if side_word and num_str:
        return f"{side_word} {num_str} {unit} {period_in}"

    # 2. Period spreads (e.g. "1Q Spread: Bengals (-0.5)" + "Cincinnati Bengals")
    low_m = mname_no_side.lower()
    if "spread" in low_m or row.get("threshold") is not None:
        paren_m = _PAREN_LINE_RE.search(mname_no_side)
        sp_num = _format_num(row.get("threshold")) or (paren_m.group(1) if paren_m else "")
        team_raw = oname_clean
        if not team_raw or team_raw.lower() in {"yes", "no"}:
            team_raw = _PAREN_LINE_RE.sub("", mname_no_side.split(":", 1)[-1]).strip()
        team_disp = _resolve_team_display(team_raw, home_team=home_team, away_team=away_team)
        if team_disp and sp_num:
            return f"{team_disp} cover {sp_num} {unit} {period_in}"

    # 3. Period winner / tie / moneyline
    if oname_clean:
        if oname_clean.lower() in {"draw", "tie"}:
            return f"Game is tied {period_in}"
        team_disp = _resolve_team_display(oname_clean, home_team=home_team, away_team=away_team)
        if team_disp.lower() not in {"yes", "no", "over", "under"} and any(
            tok in low_m for tok in ("winner", "moneyline", "result", "win", "lead", "quarter", "half", "period")
        ):
            return f"{team_disp} win {period_noun}"

    return None


def _plain_oddity_claim(
    row: Mapping[str, Any],
    *,
    home_team: str,
    away_team: str,
    unit: str,
) -> Optional[str]:
    mname = _strip_matchup_prefix(str(row.get("market_name") or ""))
    oname = sanitize_nugget_text(str(row.get("outcome_name") or ""))
    low_m = mname.lower()
    low_o = oname.lower()

    # Touchdown scorer markets ("1st Touchdown: Mike Gesicki", "Anytime Touchdown Scorer")
    if "touchdown" in low_m or "touchdown" in low_o:
        scorer = ""
        if ":" in mname:
            left, right = mname.split(":", 1)
            if "touchdown" in left.lower() and right.strip():
                scorer = right.strip()
        if not scorer and low_o not in {"yes", "no", "over", "under", ""}:
            scorer = oname
        if scorer and "total" not in low_m:
            if any(k in low_m for k in ("1st", "first")):
                return f"{scorer} scores the first touchdown"
            if "last" in low_m:
                return f"{scorer} scores the last touchdown"
            return f"{scorer} scores a touchdown"

    # Overtime
    if "overtime" in low_m:
        if low_o in {"yes", "overtime", ""}:
            return "Game goes to overtime"
        return None

    # Safety / two-point conversion
    if "safety" in low_m and low_o in {"yes", ""}:
        return "A safety is scored in the game"
    if any(k in low_m for k in ("two-point", "two point", "2-point", "2 point")) and low_o in {"yes", ""}:
        return "A two-point conversion succeeds"

    # Period-like O/U inside other section
    ou_m = _OU_LINE_RE.search(mname)
    if ou_m and low_o in {"over", "under"}:
        side = "Over" if low_o == "over" else "Under"
        phrases = _plain_period_phrases("", mname)
        if phrases is not None:
            return f"{side} {ou_m.group(1)} {unit} {phrases[0]}"
        return f"{side} {ou_m.group(1)} {unit}"

    # Fallback: only keep genuinely clean declarative text
    candidate = mname if low_o in {"yes", ""} else (f"{oname} {mname}" if mname else oname)
    candidate = _resolve_team_display(candidate, home_team=home_team, away_team=away_team)
    if _looks_like_clean_claim(candidate) and not candidate.lower().startswith("will "):
        return candidate
    return None


def _plain_stakes_claim(s_name: str, raw_label: str, out_name: str, *, is_player: bool = False) -> str:
    label = sanitize_nugget_text(raw_label or "").strip()
    out_clean = sanitize_nugget_text(out_name or "").strip()
    target = out_clean if (out_clean and out_clean.lower() not in {"yes", "no"}) else s_name
    win_verb = "wins" if is_player else "win"
    make_verb = "makes" if is_player else "make"
    be_verb = "is" if is_player else "are"
    if not label:
        return target
    low_l = label.lower()
    if low_l == "make playoffs":
        return f"{target} {make_verb} the playoffs"
    if low_l == "win division":
        return f"{target} {win_verb} the division"
    if "finalist" in low_l:
        award = re.sub(r"\bfinalists?\b", "", label, flags=re.I).strip()
        return f"{target} {be_verb} an {award} finalist" if award else f"{target} {be_verb} a finalist"
    if low_l.startswith("win "):
        return f"{target} {win_verb} {label[4:].strip()}"
    if low_l.startswith("make "):
        return f"{target} {make_verb} {label[5:].strip()}"
    if target.lower() in low_l:
        rest = re.sub(re.escape(target), "", label, flags=re.I).strip(" :-–—")
        if rest:
            return f"{target} {win_verb} {rest}"
        return label
    cleaned_label = re.sub(r"\bDivision Winner\b", "division", label, flags=re.I)
    cleaned_label = re.sub(r"\bChampion\b", "title", cleaned_label, flags=re.I)
    cleaned_label = _MULTISPACE_RE.sub(" ", re.sub(r"\bWinner\b", "", cleaned_label, flags=re.I)).strip(" :-–—")
    if not cleaned_label:
        return target
    return f"{target} {win_verb} {cleaned_label}"


def _extract_candidates(
    *,
    event_info: Mapping[str, Any],
    game_markets: Mapping[str, Any],
    related_futures: Mapping[str, Any],
    team_progression: Mapping[str, Any],
    now: datetime,
) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    excluded: Counter[str] = Counter()
    eligible_counts: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []

    home_team = str(event_info.get("home_team") or game_markets.get("home_team") or "Home").strip()
    away_team = str(event_info.get("away_team") or game_markets.get("away_team") or "Away").strip()
    sport = str(event_info.get("sport") or "")
    status = str(event_info.get("status") or game_markets.get("status") or "").lower()
    is_live = status in {"live", "in_progress"}
    is_post_kickoff = status in {"live", "in_progress", "completed"}
    max_age = NUGGET_LIVE_MAX_OBSERVED_AGE_HOURS if is_live else NUGGET_MAX_OBSERVED_AGE_HOURS

    home_logo = (
        event_info.get("home_logo")
        or ((team_progression.get("home_team") or {}).get("logo_url") if isinstance(team_progression.get("home_team"), Mapping) else None)
    )
    away_logo = (
        event_info.get("away_logo")
        or ((team_progression.get("away_team") or {}).get("logo_url") if isinstance(team_progression.get("away_team"), Mapping) else None)
    )
    matchup_label = f"{away_team} at {home_team}"
    unit = _total_unit_word(sport)

    # 1. game_flow: totals & spreads
    best_totals: dict[tuple[str, Any], dict[str, Any]] = {}
    for row in game_markets.get("totals") or ():
        if not isinstance(row, Mapping):
            continue
        p = _is_fresh_and_priced(
            row,
            prob=row.get("over_probability", row.get("probability")),
            now=now,
            max_age_hours=max_age,
            excluded_counts=excluded,
        )
        if p is None:
            continue
        eligible_counts["game_flow"] += 1
        thresh = row.get("threshold")
        out_name = sanitize_nugget_text(str(row.get("outcome_name") or "Over")).strip()
        low_out = out_name.lower()
        side_word = "Under" if "under" in low_out else ("Over" if "over" in low_out else out_name)
        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            change_24h=row.get("probability_change_24h", row.get("change_24h")),
            allow_pregame_mark=is_post_kickoff,
        )
        t_str = _format_num(thresh)
        if not t_str:
            ou_m = _OU_LINE_RE.search(str(row.get("market_name") or ""))
            t_str = ou_m.group(1) if ou_m else ""
        if t_str:
            claim = f"{side_word} {t_str} total {unit}".strip()
        else:
            fallback_m = _strip_matchup_prefix(str(row.get("market_name") or ""))
            claim = fallback_m or f"{side_word} total {unit}"
        form = _select_nugget_form(change_points=chg, change_since=since, default_form="duel_bar")
        sc, why = _compute_score(
            prob=p, change_points=chg, change_since=since, is_live=is_live, base_bonus=10.0
        )
        key = ("total", thresh)
        cand = _candidate_dict(
            nid=f"game_flow:total:{row.get('_market_id') or t_str}:{side_word.lower()}",
            kind="game_flow",
            subject={"name": matchup_label, "image_url": home_logo or away_logo, "image_kind": "logo" if (home_logo or away_logo) else None},
            claim=claim,
            prob=p,
            change_points=chg,
            change_since=since,
            pregame_percent=pre,
            form=form,
            rank_reason=why,
            score=sc,
            observed_at=row.get("observed_at"),
            source_surface="game_markets",
            source_market_id=row.get("_market_id"),
            dedup_key="game_flow:total",
        )
        if key not in best_totals or cand["score"] > best_totals[key]["score"]:
            best_totals[key] = cand
    candidates.extend(best_totals.values())

    best_spreads: dict[str, dict[str, Any]] = {}
    for row in game_markets.get("spreads") or ():
        if not isinstance(row, Mapping):
            continue
        p = _is_fresh_and_priced(
            row,
            prob=row.get("probability"),
            now=now,
            max_age_hours=max_age,
            excluded_counts=excluded,
        )
        if p is None:
            continue
        eligible_counts["game_flow"] += 1
        out_name = sanitize_nugget_text(str(row.get("outcome_name") or "")).strip()
        mname = _strip_matchup_prefix(str(row.get("market_name") or ""))
        subj = _team_subject(
            out_name or home_team,
            home_team=home_team,
            away_team=away_team,
            home_logo=home_logo,
            away_logo=away_logo,
        )
        thresh = row.get("threshold")
        t_str = _format_num(thresh)
        if t_str:
            claim = f"{subj['name']} cover {t_str} {unit}"
        elif mname and _looks_like_clean_claim(mname):
            claim = f"{out_name} on {mname}" if out_name and out_name.lower() not in mname.lower() else mname
        else:
            claim = f"{subj['name']} point spread"
        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            change_24h=row.get("probability_change_24h", row.get("change_24h")),
            allow_pregame_mark=is_post_kickoff,
        )
        form = _select_nugget_form(change_points=chg, change_since=since, default_form="duel_bar")
        sc, why = _compute_score(
            prob=p,
            change_points=chg,
            change_since=since,
            is_live=is_live,
            has_picture=bool(subj["image_url"]),
            base_bonus=9.5,
        )
        cand = _candidate_dict(
            nid=f"game_flow:spread:{row.get('_market_id') or mname}:{out_name.lower()}",
            kind="game_flow",
            subject=subj,
            claim=claim,
            prob=p,
            change_points=chg,
            change_since=since,
            pregame_percent=pre,
            form=form,
            rank_reason=why,
            score=sc,
            observed_at=row.get("observed_at"),
            source_surface="game_markets",
            source_market_id=row.get("_market_id"),
            dedup_key=f"game_flow:spread:{row.get('_market_id') or mname}",
        )
        dkey = cand["_dedup_key"]
        if dkey not in best_spreads or cand["score"] > best_spreads[dkey]["score"]:
            best_spreads[dkey] = cand
    candidates.extend(best_spreads.values())

    # 2. players: player_props grouped by (player, stat) keeping highest score per player+stat
    best_props: dict[tuple[str, str], dict[str, Any]] = {}
    for row in game_markets.get("player_props") or ():
        if not isinstance(row, Mapping):
            continue
        if str(row.get("side") or "").lower() == "under":
            continue
        raw_p = row.get("over_probability", row.get("probability"))
        p = _is_fresh_and_priced(
            row,
            prob=raw_p,
            now=now,
            max_age_hours=max_age,
            excluded_counts=excluded,
        )
        if p is None:
            continue

        player_field = row.get("player")
        stat_field = row.get("stat")
        line_field = row.get("line")
        line_label = (
            str(line_field.get("label") or "").strip()
            if isinstance(line_field, Mapping)
            else _format_num(row.get("threshold"))
        )
        if isinstance(player_field, Mapping):
            player_name = sanitize_nugget_text(str(player_field.get("name") or "")).strip()
            player_key = str(player_field.get("key") or player_name).lower()
            stat_label = (
                str(stat_field.get("label") or stat_field.get("key") or "props")
                if isinstance(stat_field, Mapping)
                else str(stat_field or "props")
            )
            stat_key = (
                str(stat_field.get("key") or stat_label).lower()
                if isinstance(stat_field, Mapping)
                else stat_label.lower()
            )
            if not player_name:
                continue
            if "touchdown" in stat_key and not line_label:
                claim = f"{player_name} scores a touchdown"
            elif line_label:
                claim = f"{player_name} {line_label} {stat_label.lower()}"
            else:
                claim = f"{player_name} {stat_label.lower()}"
        else:
            raw_out = sanitize_nugget_text(str(row.get("outcome_name") or "")).split(":")[0].strip()
            mname_clean = _strip_matchup_prefix(str(row.get("market_name") or ""))
            if raw_out and raw_out.lower() not in {"over", "under", "yes", "no"}:
                player_name = raw_out
                stat_label = (
                    str(stat_field.get("label") or stat_field.get("key") or "")
                    if isinstance(stat_field, Mapping)
                    else str(stat_field or "")
                ).strip()
                stat_key = stat_label.lower() or "prop"
                if not stat_label:
                    claim = mname_clean if _looks_like_clean_claim(mname_clean) else ""
                elif line_label:
                    claim = f"{player_name} {line_label} {stat_label.lower()}"
                else:
                    claim = f"{player_name} {stat_label.lower()}"
            elif mname_clean and _looks_like_clean_claim(mname_clean):
                # Untyped prop fallback: use clean market title ("Jayden Daniels 50+ rushing yards"),
                # never generic "Over 50 props".
                name_words = re.match(r"^([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,2})\s+(.+)$", mname_clean)
                if name_words:
                    player_name = name_words.group(1).strip()
                    rest = name_words.group(2).strip().lower()
                    claim = f"{player_name} {rest}"
                    stat_key = rest
                else:
                    excluded["unreadable_claim"] += 1
                    continue
            else:
                excluded["unreadable_claim"] += 1
                continue
            if not claim or not _looks_like_clean_claim(claim):
                excluded["unreadable_claim"] += 1
                continue
            player_key = player_name.lower()

        eligible_counts["players"] += 1

        headshot = row.get("player_headshot")
        if not headshot:
            side_tag = str(row.get("player_team") or "").lower()
            fallback_logo = home_logo if side_tag == "home" else (away_logo if side_tag == "away" else None)
            subj = {"name": player_name, "image_url": fallback_logo, "image_kind": "logo" if fallback_logo else None}
        else:
            subj = {"name": player_name, "image_url": headshot, "image_kind": "headshot"}

        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            change_24h=row.get("probability_change_24h", row.get("change_24h")),
            allow_pregame_mark=is_post_kickoff,
        )
        src_cnt = int(row.get("source_count") or 1)
        form = _select_nugget_form(
            change_points=chg,
            change_since=since,
            default_form="faces_row" if headshot else "ladder",
        )
        sc, why = _compute_score(
            prob=p,
            change_points=chg,
            change_since=since,
            is_live=is_live,
            source_count=src_cnt,
            has_picture=bool(headshot),
            base_bonus=8.0,
        )
        cand = _candidate_dict(
            nid=f"players:{row.get('_market_id') or player_key}:{stat_key}:{line_label}",
            kind="players",
            subject=subj,
            claim=claim,
            prob=p,
            change_points=chg,
            change_since=since,
            pregame_percent=pre,
            form=form,
            rank_reason=why,
            score=sc,
            observed_at=row.get("observed_at"),
            source_surface="game_markets",
            source_market_id=row.get("_market_id"),
            dedup_key=f"players:{player_key}:{stat_key}",
        )
        pair = (player_key, stat_key)
        if pair not in best_props or cand["score"] > best_props[pair]["score"]:
            best_props[pair] = cand
    candidates.extend(best_props.values())

    # 3. teams: team_totals grouped by team_side keeping strongest line per team
    best_team_totals: dict[str, dict[str, Any]] = {}
    for row in game_markets.get("team_totals") or ():
        if not isinstance(row, Mapping):
            continue
        p = _is_fresh_and_priced(
            row,
            prob=row.get("over_probability", row.get("probability")),
            now=now,
            max_age_hours=max_age,
            excluded_counts=excluded,
        )
        if p is None:
            continue
        eligible_counts["teams"] += 1
        t_name = str(row.get("team_name") or "").strip()
        if not t_name:
            t_name = away_team if row.get("team_side") == "away" else home_team
        subj = _team_subject(
            t_name,
            home_team=home_team,
            away_team=away_team,
            home_logo=home_logo,
            away_logo=away_logo,
        )
        t_str = _format_num(row.get("threshold"))
        tt_side = "under" if "under" in str(row.get("side") or row.get("outcome_name") or "").lower() else "over"
        if t_str:
            claim = f"{subj['name']} scores {tt_side} {t_str} {unit}"
        else:
            raw_tt = _strip_matchup_prefix(str(row.get("outcome_name") or row.get("market_name") or ""))
            claim = raw_tt or subj["name"]
        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            change_24h=row.get("probability_change_24h", row.get("change_24h")),
            allow_pregame_mark=is_post_kickoff,
        )
        form = _select_nugget_form(change_points=chg, change_since=since, default_form="ladder")
        sc, why = _compute_score(
            prob=p,
            change_points=chg,
            change_since=since,
            is_live=is_live,
            has_picture=bool(subj["image_url"]),
            base_bonus=7.5,
        )
        tkey = str(row.get("team_side") or subj["name"]).lower()
        cand = _candidate_dict(
            nid=f"teams:{row.get('_market_id') or tkey}:{t_str}",
            kind="teams",
            subject=subj,
            claim=claim,
            prob=p,
            change_points=chg,
            change_since=since,
            pregame_percent=pre,
            form=form,
            rank_reason=why,
            score=sc,
            observed_at=row.get("observed_at"),
            source_surface="game_markets",
            source_market_id=row.get("_market_id"),
            dedup_key=f"teams:{tkey}",
        )
        if tkey not in best_team_totals or cand["score"] > best_team_totals[tkey]["score"]:
            best_team_totals[tkey] = cand
    candidates.extend(best_team_totals.values())

    # 4. moments: period_markets grouped by market/period
    best_moments: dict[str, dict[str, Any]] = {}
    for row in game_markets.get("period_markets") or ():
        if not isinstance(row, Mapping):
            continue
        p = _is_fresh_and_priced(
            row,
            prob=row.get("probability", row.get("over_probability")),
            now=now,
            max_age_hours=max_age,
            excluded_counts=excluded,
        )
        if p is None:
            continue
        claim = _plain_moment_claim(row, home_team=home_team, away_team=away_team, unit=unit)
        if claim is None:
            excluded["unreadable_claim"] += 1
            continue
        eligible_counts["moments"] += 1
        period = str(row.get("period") or "").strip()
        mname = str(row.get("market_name") or "").strip()
        oname = str(row.get("outcome_name") or "").strip()
        subj = _team_subject(
            oname if oname.lower() in {home_team.lower(), away_team.lower()} else matchup_label,
            home_team=home_team,
            away_team=away_team,
            home_logo=home_logo,
            away_logo=away_logo,
        )
        if subj["name"] == matchup_label:
            subj = {"name": period or matchup_label, "image_url": home_logo or away_logo, "image_kind": "logo" if (home_logo or away_logo) else None}
        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            change_24h=row.get("probability_change_24h", row.get("change_24h")),
            allow_pregame_mark=is_post_kickoff,
        )
        form = _select_nugget_form(change_points=chg, change_since=since, default_form="duel_bar")
        sc, why = _compute_score(
            prob=p, change_points=chg, change_since=since, is_live=is_live, base_bonus=6.5
        )
        mkey = f"{row.get('_market_id') or mname}:{period}"
        cand = _candidate_dict(
            nid=f"moments:{mkey}:{oname.lower()}",
            kind="moments",
            subject=subj,
            claim=claim,
            prob=p,
            change_points=chg,
            change_since=since,
            pregame_percent=pre,
            form=form,
            rank_reason=why,
            score=sc,
            observed_at=row.get("observed_at"),
            source_surface="game_markets",
            source_market_id=row.get("_market_id"),
            dedup_key=f"moments:{period or mname}",
        )
        if cand["_dedup_key"] not in best_moments or cand["score"] > best_moments[cand["_dedup_key"]]["score"]:
            best_moments[cand["_dedup_key"]] = cand
    candidates.extend(best_moments.values())

    # 5. stakes: team_progression + related_futures (strictly excluding game's own props)
    game_market_ids = _collect_game_market_ids(game_markets)
    best_stakes: dict[str, dict[str, Any]] = {}

    for side_key, fallback_team, fallback_logo in (
        ("home_team", home_team, home_logo),
        ("away_team", away_team, away_logo),
    ):
        t_obj = team_progression.get(side_key)
        if not isinstance(t_obj, Mapping):
            continue
        t_name = str(t_obj.get("name") or fallback_team)
        t_logo = t_obj.get("logo_url") or fallback_logo
        subj = {"name": t_name, "image_url": t_logo, "image_kind": "logo" if t_logo else None}
        for stage in t_obj.get("stages") or ():
            if not isinstance(stage, Mapping):
                continue
            if stage.get("state") in {"won", "eliminated"}:
                excluded["unpriced_or_extreme"] += 1
                continue
            p = _valid_prob(stage.get("probability"))
            if p is None:
                excluded["unpriced_or_extreme"] += 1
                continue
            eligible_counts["stakes"] += 1
            s_key = str(stage.get("key") or stage.get("label") or "stage")
            s_label = str(stage.get("label") or s_key)
            chg, since, pre = _extract_movement(
                prob=p,
                change_24h=stage.get("trend_24h"),
                allow_pregame_mark=False,
            )
            src_cnt = len(stage.get("sources") or ())
            form = _select_nugget_form(change_points=chg, change_since=since, default_form="history_line")
            sc, why = _compute_score(
                prob=p,
                change_points=chg,
                change_since=since,
                is_live=is_live,
                source_count=src_cnt,
                has_picture=bool(t_logo),
                stakes_tier=1,
                base_bonus=7.5,
            )
            cand = _candidate_dict(
                nid=f"stakes:prog:{side_key}:{s_key}",
                kind="stakes",
                subject=subj,
                claim=_plain_stakes_claim(t_name, s_label, "", is_player=False),
                prob=p,
                change_points=chg,
                change_since=since,
                pregame_percent=pre,
                form=form,
                rank_reason=why,
                score=sc,
                observed_at=None,
                source_surface="team_progression",
                dedup_key=f"stakes:{t_name.lower()}:{s_label.lower()}",
            )
            if cand["_dedup_key"] not in best_stakes or cand["score"] > best_stakes[cand["_dedup_key"]]["score"]:
                best_stakes[cand["_dedup_key"]] = cand

    for fut_key, side_team, side_logo in (
        ("home_team_futures", home_team, home_logo),
        ("away_team_futures", away_team, away_logo),
        ("series_markets", matchup_label, home_logo or away_logo),
    ):
        for row in related_futures.get(fut_key) or ():
            if not isinstance(row, Mapping):
                continue
            if _is_game_own_futures_row(
                row,
                game_market_ids=game_market_ids,
                home_team=home_team,
                away_team=away_team,
            ):
                excluded["game_own_props_in_related"] += 1
                continue
            p = _is_fresh_and_priced(
                row,
                prob=row.get("probability"),
                now=now,
                max_age_hours=NUGGET_MAX_OBSERVED_AGE_HOURS,
                excluded_counts=excluded,
                timestamp_key="last_updated",
            )
            if p is None:
                continue
            eligible_counts["stakes"] += 1

            mp = row.get("matched_player")
            has_matched_player = isinstance(mp, Mapping) and bool(
                mp.get("name") or mp.get("headshot_url") or mp.get("image_url")
            )
            if has_matched_player and isinstance(mp, Mapping):
                s_name = str(mp.get("name") or row.get("outcome_name") or side_team)
                s_img = mp.get("headshot_url") or mp.get("image_url") or side_logo
                s_kind = "headshot" if (mp.get("headshot_url") or mp.get("image_url")) else ("logo" if s_img else None)
            else:
                s_name = side_team
                s_img = side_logo
                s_kind = "logo" if side_logo else None
            subj = {"name": s_name, "image_url": s_img, "image_kind": s_kind}

            label = str(row.get("clean_label") or row.get("market_name") or "").strip()
            out_name = str(row.get("outcome_name") or "").strip()
            is_player_stake = has_matched_player or (
                bool(out_name)
                and out_name.lower() not in {"yes", "no", home_team.lower(), away_team.lower()}
            )
            claim = _plain_stakes_claim(s_name, label, out_name, is_player=is_player_stake)

            chg, since, pre = _extract_movement(
                prob=p,
                change_24h=row.get("probability_change_24h", row.get("change_24h")),
                allow_pregame_mark=False,
            )
            tier = row.get("market_tier")
            tier_int = int(tier) if isinstance(tier, int) and not isinstance(tier, bool) else None
            books = int(row.get("bookmaker_count") or 1)
            form = _select_nugget_form(change_points=chg, change_since=since, default_form="history_line")
            sc, why = _compute_score(
                prob=p,
                change_points=chg,
                change_since=since,
                is_live=is_live,
                source_count=books,
                has_picture=bool(s_img),
                stakes_tier=tier_int,
                base_bonus=6.0 + float(row.get("relevance_score") or 0.0) * 0.05,
            )
            mid = row.get("market_id")
            oid = row.get("outcome_id")
            dkey = f"stakes:{mid or label.lower()}:{s_name.lower()}"
            cand = _candidate_dict(
                nid=f"stakes:rf:{mid}:{oid}",
                kind="stakes",
                subject=subj,
                claim=claim,
                prob=p,
                change_points=chg,
                change_since=since,
                pregame_percent=pre,
                form=form,
                rank_reason=why,
                score=sc,
                observed_at=row.get("last_updated"),
                source_surface="related_futures",
                source_market_id=mid if isinstance(mid, int) else None,
                source_outcome_id=oid if isinstance(oid, int) else None,
                dedup_key=dkey,
            )
            if dkey not in best_stakes or cand["score"] > best_stakes[dkey]["score"]:
                best_stakes[dkey] = cand
    candidates.extend(best_stakes.values())

    # 6. oddities: non-moneyline rows from game_markets["other"]
    best_oddities: dict[str, dict[str, Any]] = {}
    for row in game_markets.get("other") or ():
        if not isinstance(row, Mapping):
            continue
        mname = str(row.get("market_name") or "").strip()
        oname = str(row.get("outcome_name") or "").strip()
        if _WINNER_NOISE_RE.search(mname):
            continue
        if oname.lower() in {"no", "under"} and mname:
            # Prefer affirmative proposition over plain negation
            continue
        if oname.lower() in {home_team.lower(), away_team.lower(), "draw", "tie"} and not mname:
            continue
        p = _is_fresh_and_priced(
            row,
            prob=row.get("probability", row.get("over_probability")),
            now=now,
            max_age_hours=max_age,
            excluded_counts=excluded,
        )
        if p is None:
            continue
        claim = _plain_oddity_claim(row, home_team=home_team, away_team=away_team, unit=unit)
        if claim is None:
            excluded["unreadable_claim"] += 1
            continue
        eligible_counts["oddities"] += 1
        subj = {"name": matchup_label, "image_url": home_logo or away_logo, "image_kind": "logo" if (home_logo or away_logo) else None}
        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            change_24h=row.get("probability_change_24h", row.get("change_24h")),
            allow_pregame_mark=is_post_kickoff,
        )
        form = _select_nugget_form(change_points=chg, change_since=since, default_form="duel_bar")
        sc, why = _compute_score(
            prob=p, change_points=chg, change_since=since, is_live=is_live, base_bonus=5.5
        )
        mid = row.get("_market_id")
        dkey = f"oddities:{claim.lower()}"
        cand = _candidate_dict(
            nid=f"oddities:{mid or len(best_oddities)}:{oname.lower()}",
            kind="oddities",
            subject=subj,
            claim=claim,
            prob=p,
            change_points=chg,
            change_since=since,
            pregame_percent=pre,
            form=form,
            rank_reason=why,
            score=sc,
            observed_at=row.get("observed_at"),
            source_surface="game_markets",
            source_market_id=mid if isinstance(mid, int) else None,
            dedup_key=dkey,
        )
        if dkey not in best_oddities or cand["score"] > best_oddities[dkey]["score"]:
            best_oddities[dkey] = cand
    candidates.extend(best_oddities.values())

    return candidates, eligible_counts, excluded


def rank_game_nuggets(
    *,
    event_info: Mapping[str, Any],
    game_markets: Mapping[str, Any],
    related_futures: Mapping[str, Any],
    team_progression: Mapping[str, Any],
    limit: int = NUGGET_DEFAULT_LIMIT,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Rank up to ``limit`` (default 12) nuggets across the 6 kinds for one event."""
    clock_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    clamped_limit = max(1, min(int(limit), NUGGET_DEFAULT_LIMIT))

    candidates, eligible_counts, excluded_counts = _extract_candidates(
        event_info=event_info,
        game_markets=game_markets,
        related_futures=related_futures,
        team_progression=team_progression,
        now=clock_now,
    )

    # Deduplicate by internal key keeping highest score, then sort globally
    by_dedup: dict[str, dict[str, Any]] = {}
    for cand in candidates:
        dkey = cand["_dedup_key"]
        if dkey not in by_dedup or cand["score"] > by_dedup[dkey]["score"]:
            by_dedup[dkey] = cand
    pool = sorted(
        by_dedup.values(),
        key=lambda c: (-float(c["score"]), c["kind"], c["id"]),
    )

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    kind_counts: Counter[str] = Counter()
    seen_subject_kinds: set[tuple[str, str]] = set()

    def _take(item: dict[str, Any]) -> None:
        selected_ids.add(item["id"])
        kind_counts[item["kind"]] += 1
        seen_subject_kinds.add((item["kind"], str(item["subject"]["name"]).lower()))
        clean = {k: v for k, v in item.items() if k != "_dedup_key"}
        clean["position"] = len(selected) + 1
        selected.append(clean)

    # Pass 1 (variety guarantee): pick the top-scoring nugget from each available kind
    # in score order so >= 4 kinds always enter the first eight when data exists.
    top_per_kind: dict[str, dict[str, Any]] = {}
    for item in pool:
        k = item["kind"]
        if k not in top_per_kind:
            top_per_kind[k] = item
    for item in sorted(top_per_kind.values(), key=lambda c: (-float(c["score"]), c["kind"], c["id"])):
        if len(selected) >= min(clamped_limit, NUGGET_FIRST_EIGHT):
            break
        _take(item)

    # Pass 2 (first 8): fill remaining slots up to 8 respecting <= 2 per kind,
    # preferring distinct (kind, subject) before allowing a second item on the same subject.
    first_eight_cap = min(clamped_limit, NUGGET_FIRST_EIGHT)
    for avoid_same_subject in (True, False):
        if len(selected) >= first_eight_cap:
            break
        for item in pool:
            if len(selected) >= first_eight_cap:
                break
            if item["id"] in selected_ids:
                continue
            if kind_counts[item["kind"]] >= NUGGET_MAX_PER_KIND_FIRST_EIGHT:
                continue
            sk_pair = (item["kind"], str(item["subject"]["name"]).lower())
            if avoid_same_subject and sk_pair in seen_subject_kinds:
                continue
            _take(item)

    # Pass 3 (seats 9..limit): extend by score up to limit (<= 3 per kind, no padding).
    for item in pool:
        if len(selected) >= clamped_limit:
            break
        if item["id"] in selected_ids:
            continue
        if kind_counts[item["kind"]] >= NUGGET_MAX_PER_KIND_EXTENDED:
            continue
        _take(item)

    everything_map = [
        {
            "kind": k,
            "label": NUGGET_KIND_LABELS[k],
            "count": int(eligible_counts.get(k, 0)),
            "target_section": NUGGET_KIND_TARGETS[k],
        }
        for k in NUGGET_KINDS
    ]

    return {
        "event_id": event_info.get("event_id"),
        "home_team": event_info.get("home_team"),
        "away_team": event_info.get("away_team"),
        "sport": event_info.get("sport"),
        "status": event_info.get("status"),
        "commence_time": event_info.get("commence_time"),
        "nuggets": selected,
        "first_eight_kinds": len({n["kind"] for n in selected[:NUGGET_FIRST_EIGHT]}),
        "everything_map": everything_map,
        "excluded_counts": dict(excluded_counts),
        "generated_at": clock_now.isoformat(),
    }
