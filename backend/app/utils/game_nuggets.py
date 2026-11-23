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
    opening_prob: Any = None,
    movement: Any = None,
    change_24h: Any = None,
) -> tuple[Optional[int], Optional[str], Optional[int]]:
    """Return ``(change_points, change_since, pregame_percent)``."""
    now_pct = int(round(prob * 100.0))
    for raw_ref, label in ((pregame_mark, "pregame"), (opening_prob, "pregame")):
        if not isinstance(raw_ref, bool) and isinstance(raw_ref, (int, float)):
            ref = float(raw_ref)
            if 0.0 <= ref <= 1.0:
                ref_pct = int(round(ref * 100.0))
                diff = now_pct - ref_pct
                return diff, label, ref_pct
    if not isinstance(movement, bool) and isinstance(movement, (int, float)):
        diff = int(round(float(movement) * 100.0))
        return diff, "pregame", None
    if not isinstance(change_24h, bool) and isinstance(change_24h, (int, float)):
        diff = int(round(float(change_24h) * 100.0))
        return diff, "24h", None
    return None, None, None


def _closeness_score(prob: float) -> float:
    return max(0.0, 1.0 - 2.0 * abs(prob - 0.5))


def _compute_score(
    *,
    prob: float,
    change_points: Optional[int],
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
        reasons.append(f"Moved {sign}{change_points} pts")

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
        out_name = str(row.get("outcome_name") or "Over").strip()
        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            movement=row.get("movement"),
        )
        t_str = _format_num(thresh)
        claim = (
            f"{out_name} {t_str} total {unit}".strip()
            if t_str
            else str(row.get("market_name") or f"{out_name} total {unit}")
        )
        form = "pregame_vs_now" if (chg is not None and abs(chg) >= 3) else "duel_bar"
        sc, why = _compute_score(prob=p, change_points=chg, is_live=is_live, base_bonus=10.0)
        key = ("total", thresh)
        cand = _candidate_dict(
            nid=f"game_flow:total:{row.get('_market_id') or t_str}:{out_name.lower()}",
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
        out_name = str(row.get("outcome_name") or "").strip()
        mname = str(row.get("market_name") or "").strip()
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
            claim = f"{out_name} to cover {t_str} points"
        elif mname:
            claim = f"{out_name} on {mname}" if out_name and out_name.lower() not in mname.lower() else mname
        else:
            claim = f"{out_name} point spread"
        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            movement=row.get("movement"),
        )
        form = "pregame_vs_now" if (chg is not None and abs(chg) >= 3) else "duel_bar"
        sc, why = _compute_score(prob=p, change_points=chg, is_live=is_live, has_picture=bool(subj["image_url"]), base_bonus=9.5)
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
        eligible_counts["players"] += 1

        player_field = row.get("player")
        if isinstance(player_field, Mapping):
            player_name = str(player_field.get("name") or "").strip()
            player_key = str(player_field.get("key") or player_name).lower()
        else:
            player_name = str(row.get("outcome_name") or "").split(":")[0].strip()
            player_key = player_name.lower()
        if not player_name:
            continue

        stat_field = row.get("stat")
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
        line_field = row.get("line")
        line_label = (
            str(line_field.get("label") or "").strip()
            if isinstance(line_field, Mapping)
            else _format_num(row.get("threshold"))
        )
        if "touchdown" in stat_key and not line_label:
            claim = f"{player_name} scores a touchdown"
        elif line_label:
            claim = f"{player_name} {line_label} {stat_label.lower()}"
        else:
            claim = f"{player_name} {stat_label.lower()}"

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
            opening_prob=row.get("opening_over_probability"),
            movement=row.get("movement"),
        )
        src_cnt = int(row.get("source_count") or 1)
        form = "pregame_vs_now" if (chg is not None and abs(chg) >= 3) else ("faces_row" if headshot else "ladder")
        sc, why = _compute_score(
            prob=p,
            change_points=chg,
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
        claim = f"{subj['name']} over {t_str} {unit}" if t_str else str(row.get("outcome_name") or row.get("market_name") or subj["name"])
        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            movement=row.get("movement"),
        )
        form = "pregame_vs_now" if (chg is not None and abs(chg) >= 3) else "ladder"
        sc, why = _compute_score(
            prob=p,
            change_points=chg,
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
        eligible_counts["moments"] += 1
        period = str(row.get("period") or "").strip()
        mname = str(row.get("market_name") or "").strip()
        oname = str(row.get("outcome_name") or "").strip()
        if oname and oname.lower() not in {"yes", "no", "over", "under"}:
            claim = f"{oname}: {mname}" if mname and oname.lower() not in mname.lower() else (mname or oname)
        else:
            claim = f"{mname} ({oname})" if mname and oname else (mname or oname)
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
            movement=row.get("movement"),
        )
        form = "pregame_vs_now" if (chg is not None and abs(chg) >= 3) else "duel_bar"
        sc, why = _compute_score(prob=p, change_points=chg, is_live=is_live, base_bonus=6.5)
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
            chg, since, pre = _extract_movement(prob=p, change_24h=stage.get("trend_24h"))
            src_cnt = len(stage.get("sources") or ())
            form = "pregame_vs_now" if (chg is not None and abs(chg) >= 3) else "history_line"
            sc, why = _compute_score(
                prob=p,
                change_points=chg,
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
                claim=f"{t_name}: {s_label}",
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
            if isinstance(mp, Mapping) and (mp.get("name") or mp.get("headshot_url") or mp.get("image_url")):
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
            if out_name and out_name.lower() not in {"yes", "no"} and out_name.lower() not in label.lower():
                claim = f"{out_name} — {label}" if label else out_name
            else:
                claim = f"{s_name}: {label}" if label and s_name.lower() not in label.lower() else (label or s_name)

            chg, since, pre = _extract_movement(
                prob=p,
                opening_prob=row.get("opening_probability"),
                change_24h=row.get("probability_change_24h"),
            )
            tier = row.get("market_tier")
            tier_int = int(tier) if isinstance(tier, int) and not isinstance(tier, bool) else None
            books = int(row.get("bookmaker_count") or 1)
            form = "pregame_vs_now" if (chg is not None and abs(chg) >= 3) else "history_line"
            sc, why = _compute_score(
                prob=p,
                change_points=chg,
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
        eligible_counts["oddities"] += 1
        claim = (
            f"{mname}: {oname}"
            if mname and oname and oname.lower() not in {"yes"} and oname.lower() not in mname.lower()
            else (mname or oname)
        )
        subj = {"name": matchup_label, "image_url": home_logo or away_logo, "image_kind": "logo" if (home_logo or away_logo) else None}
        chg, since, pre = _extract_movement(
            prob=p,
            pregame_mark=row.get("pregame_mark"),
            movement=row.get("movement"),
        )
        form = "pregame_vs_now" if (chg is not None and abs(chg) >= 3) else "duel_bar"
        sc, why = _compute_score(prob=p, change_points=chg, is_live=is_live, base_bonus=5.5)
        mid = row.get("_market_id")
        dkey = f"oddities:{mid or claim.lower()}"
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
