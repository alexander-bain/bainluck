"""Feed event scoring — pure functions for ranking events by interestingness.

Extracted from routes/feed.py `_score_events` to make scoring logic
independently testable. These functions take pre-fetched data and return
scores/dicts — no database access, no side effects.
"""

from datetime import datetime

from app.utils.game_state import normalize_live_game_state
from app.utils.graded_card import rendered_duel_percents
from app.utils.prematch_reading import resolve_prematch_reading


# Tag-based scoring boosts (LLM taxonomy enrichment)
TAG_BOOSTS = {
    "stakes:elimination": 12,
    "stakes:clinch": 10,
    "stakes:title_defense": 10,
    "stakes:must_win": 8,
    "stakes:record_chase": 8,
    "stakes:seeding": 5,
    "stakes:playoff_race": 3,
    "narrative:rivalry": 8,
    "narrative:historic_rivalry": 10,
    "narrative:cinderella": 8,
    "narrative:comeback": 8,
    "narrative:revenge_game": 6,
    "narrative:upset_alert": 6,
    "narrative:rematch": 5,
    "narrative:farewell_tour": 5,
    "narrative:david_vs_goliath": 3,
    "audience:national_interest": 5,
    "audience:crossover_appeal": 3,
    "audience:viral_potential": 3,
}


# === Completed-event freshness decay ===
#
# Everything a finished game earns — `recent_finish`, `recent_finish_upset`, the
# EI boost, the comeback and lead-change bonuses — was age-blind, gated only by
# `is_recently_finished`, a BINARY 24-hour flag. A game that ended sixty seconds
# ago and one that ended twenty-three hours ago scored identically, so as a
# night's slate finished it displaced everything unplayed: measured 2026-09-06,
# the Sports feed's first page carried 14 finished games out of 20 (7 at 10pm,
# 8 at 11pm, 14 by 12:26am) while the only two live games scored 35 and 40.
#
# The decay is MULTIPLICATIVE, not a flat subtraction, because the score that
# actually orders the feed (`_rank_score` in routes/feed.py) is UNCAPPED — a card
# displaying the capped 98 can rank on a considerably larger number, and a fixed
# penalty would barely move it. A proportional cut is scale-invariant and can
# never drive a score negative.
# 1.5h of full credit, then a ramp to the maximum cut at 6h. The endpoint is set
# off the measured slate, not taste: the Saturday MLB games that were still
# holding page one at 12:26am PT had ended 4.7-7.1 hours earlier, and a result
# that old is yesterday's news to someone opening the app tonight. A game still
# inside the fresh window is the WHAT-HIT card and keeps every point it earned.
COMPLETED_FRESH_HOURS = 1.5
COMPLETED_DECAY_HOURS = 6.0
COMPLETED_MAX_DECAY = 0.55
# A completed event is RE-RANKED, never removed. `routes/feed.py` drops an event
# scoring under `min_score` (30 for an anonymous reader), so an unbounded decay
# would silently empty the recent-results content instead of reordering it —
# the #1091 class. 35 is the established "survives but ranks below interesting
# futures" floor already used for the demotion cap and the championship
# override, and it sits above every min_score gate.
COMPLETED_DECAY_FLOOR = 35


def compute_completed_freshness_factor(
    event_status: str,
    hours_since_finish: float | None,
) -> float:
    """Return the multiplier a finished game's score keeps, given its age.

    1.0 for anything not completed, for an unknown age, and for the first
    ``COMPLETED_FRESH_HOURS`` after the final whistle — a game that just ended is
    the product, not clutter. Then a linear ramp down to
    ``1 - COMPLETED_MAX_DECAY`` at ``COMPLETED_DECAY_HOURS``, flat thereafter.

    A negative age (a clock skew, or a finish reference in the future) keeps the
    full score rather than inverting the ramp.
    """
    if event_status not in ("completed", "closed"):
        return 1.0
    if hours_since_finish is None or hours_since_finish <= COMPLETED_FRESH_HOURS:
        return 1.0

    span = COMPLETED_DECAY_HOURS - COMPLETED_FRESH_HOURS
    ramp = (hours_since_finish - COMPLETED_FRESH_HOURS) / span
    ramp = min(1.0, max(0.0, ramp))
    return 1.0 - (COMPLETED_MAX_DECAY * ramp)


def apply_completed_freshness_decay(
    score: int,
    event_status: str,
    hours_since_finish: float | None,
) -> tuple[int, list[str]]:
    """Age-decay a finished game's score. Returns (new_score, reasons)."""
    factor = compute_completed_freshness_factor(event_status, hours_since_finish)
    if factor >= 1.0 or score <= COMPLETED_DECAY_FLOOR:
        return score, []

    decayed = max(COMPLETED_DECAY_FLOOR, int(score * factor))
    if decayed >= score:
        return score, []
    return decayed, ["stale_result"]


def compute_content_richness_penalty(
    event_status: str,
    raw_ei: float | None,
    home_score: int | None,
    away_score: int | None,
    source_count: int | None,
    game_progress: float | None,
    sport_key: str | None,
) -> tuple[int, list[str]]:
    """Penalize live events with flat/thin content so they don't outrank interesting games.

    Returns (adjustment, reasons) where adjustment is typically negative.
    Only applies to live events — scheduled/completed are unaffected.
    Combined penalty is capped at -20.
    """
    if event_status != "live":
        return 0, []

    penalty = 0
    bonus = 0
    reasons: list[str] = []
    progress = game_progress or 0.0

    # Signal A: Probability stasis (flat EI)
    # Gate on progress >= 0.25 — EI is naturally 0 at game start
    if progress >= 0.25:
        if raw_ei is None or raw_ei == 0.0:
            penalty -= 10
            reasons.append("flat_line")
        elif raw_ei < 0.05:
            penalty -= 5
            reasons.append("low_movement")

    # Signal B: Score stasis (0-0 deep into game)
    # Exempt soccer and hockey where 0-0 is normal/tense
    is_low_score_sport = sport_key and (
        sport_key.startswith("soccer_") or sport_key.startswith("icehockey_")
    )
    if (
        not is_low_score_sport
        and progress >= 0.5
        and home_score is not None
        and away_score is not None
        and home_score == 0
        and away_score == 0
    ):
        penalty -= 8
        reasons.append("scoreless_stalemate")

    # Signal C: Data thinness (source count)
    if source_count is not None:
        if source_count == 0:
            penalty -= 8
            reasons.append("no_sources")
        elif source_count == 1:
            penalty -= 5
            reasons.append("thin_data")
        elif source_count >= 4:
            bonus += 3
            reasons.append("rich_data")

    # Cap the penalty at -20 (bonus is separate)
    penalty = max(penalty, -20)

    return penalty + bonus, reasons


def compute_base_score(
    highlight_score: int,
    highlight_reasons: list[str],
    home_champ_prob: float,
    away_champ_prob: float,
    sport_key: str | None,
    now: datetime,
    event_tags: list[str],
    event_status: str,
    raw_ei: float | None,
    get_season_multiplier_fn=None,
    get_league_tier_fn=None,
    home_score: int | None = None,
    away_score: int | None = None,
    source_count: int | None = None,
    game_progress: float | None = None,
    ei_metadata: str | dict | None = None,
    volume_24h: int | None = None,
    volume_7d_avg: float | None = None,
    hours_since_finish: float | None = None,
) -> tuple[int, list[str]]:
    """Compute the base interestingness score for a feed event.

    Returns (score, additional_reasons). Pure function — no DB access.

    Score components:
    - Highlight score (closeness, upset, lead change, etc.)
    - Stakes weighting (championship contender boost)
    - Season context (late-season major league boost)
    - LLM tag boosts (rivalry, elimination, narrative, etc.)
    - EI boost for completed high-excitement games
    - Freshness decay for completed games (applied last, to the whole stack)
    """
    score = highlight_score
    reasons = list(highlight_reasons)

    # Stakes weighting
    max_champ_prob = max(home_champ_prob, away_champ_prob)
    if max_champ_prob >= 0.15:
        score += 15
        reasons.append("high_stakes")
    elif max_champ_prob >= 0.05:
        score += 8
        reasons.append("contender")
    elif max_champ_prob >= 0.01:
        score += 3

    # Season context
    if sport_key and get_season_multiplier_fn and get_league_tier_fn:
        season_mult = get_season_multiplier_fn(sport_key, now)
        if season_mult != 1.0:
            tier = get_league_tier_fn(sport_key)
            if tier in (1, 2):
                tier_weight = 20 if tier == 1 else 10
                season_bonus = int(tier_weight * (season_mult - 1.0))
                score += season_bonus

    # LLM tag boosts
    tag_set = set(event_tags)
    tag_bonus = sum(pts for tag, pts in TAG_BOOSTS.items() if tag in tag_set)
    if tag_bonus > 0:
        score += tag_bonus
        reasons.append("llm_tags")

    # EI boost for completed events
    if event_status in ("completed", "closed") and raw_ei is not None:
        ei_score = max(1, min(100, round(raw_ei * 100)))
        if ei_score >= 80:
            score += 25
            reasons.append("high_ei")
        elif ei_score >= 60:
            score += 15
            reasons.append("good_ei")

        # Wild-ending boost — miracle comebacks and lead-change fests
        if ei_metadata:
            import json as _json
            meta = _json.loads(ei_metadata) if isinstance(ei_metadata, str) else ei_metadata
            comeback = meta.get("comeback_factor", 1.0)
            leads = meta.get("lead_changes", 0)
            if comeback <= 0.10:
                score += 30
                reasons.append("miracle_comeback")
            elif comeback <= 0.20:
                score += 20
                reasons.append("big_comeback")
            if leads >= 4:
                score += 10
                reasons.append("wild_swings")

    # Volume scoring (prediction market trading activity)
    if volume_24h is not None and volume_24h > 0:
        if volume_24h >= 50_000:
            score += 15
            reasons.append("high_volume")
        elif volume_24h >= 5_000:
            score += 8
            reasons.append("moderate_volume")

    # Volume velocity (current vs 7-day average)
    if (
        volume_24h is not None
        and volume_7d_avg is not None
        and volume_7d_avg > 0
    ):
        velocity = volume_24h / volume_7d_avg
        if velocity >= 3.0:
            score += 12
            reasons.append("volume_spike")
        elif velocity >= 1.5:
            score += 5
            reasons.append("volume_uptick")

    # Content richness penalty for live events with thin/flat data
    richness_adj, richness_reasons = compute_content_richness_penalty(
        event_status=event_status,
        raw_ei=raw_ei,
        home_score=home_score,
        away_score=away_score,
        source_count=source_count,
        game_progress=game_progress,
        sport_key=sport_key,
    )
    if richness_adj != 0:
        score += richness_adj
        reasons.extend(richness_reasons)

    # Freshness decay for finished games. LAST, deliberately: it scales the whole
    # post-game stack (highlight + EI + comeback + volume), which is the only way
    # to reach a score that is mostly age-blind bonuses.
    score, staleness_reasons = apply_completed_freshness_decay(
        score=score,
        event_status=event_status,
        hours_since_finish=hours_since_finish,
    )
    reasons.extend(staleness_reasons)

    return score, reasons


def format_event_data(
    event_id: int,
    external_id: str | None,
    sport_key: str | None,
    sport_name: str | None,
    home_team: str | None,
    away_team: str | None,
    commence_time: datetime,
    status: str,
    home_score: int | None,
    away_score: int | None,
    current_home_prob: float | None,
    current_away_prob: float | None,
    opening_home_prob: float | None,
    opening_away_prob: float | None,
    opening_favorite: str | None,
    win_probability_sources: dict | None,
    prob_source: str | None,
    game_clock: str | None,
    period: str | None,
    broadcast_info: str | None,
    highlight_label: str | None,
    raw_ei: float | None,
    inline_tags: list[str],
    ended_at: datetime | None,
    prematch_by_source: dict[str, tuple] | None = None,
) -> dict:
    """Build the compact event data dict for the feed response.

    Pure function — takes all data as arguments, returns a dict.
    """
    data: dict = {
        "id": event_id,
        "external_id": external_id,
        "sport": sport_key,
        "sport_name": sport_name,
        "home_team": home_team,
        "away_team": away_team,
        "commence_time": commence_time.isoformat(),
        "status": status,
        "home_score": home_score,
        "away_score": away_score,
    }

    if win_probability_sources:
        data["win_probability_sources"] = win_probability_sources

    if status == "live":
        display_period, display_clock = normalize_live_game_state(
            sport_key,
            period,
            game_clock,
        )
        espn_data = {}
        if display_clock:
            espn_data["game_clock"] = display_clock
        if display_period:
            espn_data["period"] = display_period
        if broadcast_info:
            espn_data["broadcast"] = broadcast_info
        if espn_data:
            data["espn"] = espn_data

    if current_home_prob is not None:
        # UX-P114: the card prints BOTH of these side by side, and `feed.py` derives
        # the away side as `1 - home`, so they are an exact complement pair — which
        # made every client that rounds them independently print 101 whenever the
        # blend landed on a half-percent (34 of 414 live/upcoming events, 2026-08-21).
        #
        # The decision is made ONCE, here, rather than in each of the four surfaces
        # that draw this strip: web `EventCard`, native `DiscoverEventCard`, the
        # macOS menu bar, and the home-screen widget — the last two read this very
        # payload and re-derive `1 - home` themselves. Ruling 021: share the
        # DECISION, not the ingredient. The probabilities below are UNCHANGED; these
        # are two extra integers, so nothing that ranks or filters on a probability
        # can see this change at all.
        away_pct, home_pct = rendered_duel_percents(current_away_prob, current_home_prob)
        odds_data = {
            "home_probability": current_home_prob,
            "away_probability": current_away_prob,
            "home_rendered_percent": home_pct,
            "away_rendered_percent": away_pct,
        }
        if prob_source:
            odds_data["source"] = prob_source
        data["current_odds"] = odds_data

    if opening_home_prob is not None:
        data["opening_odds"] = {
            "home_probability": opening_home_prob,
            "away_probability": opening_away_prob,
            "favorite": opening_favorite,
        }

    # ── THE PER-TEAM PRE-MATCH READING (ux/1036 Tier A) ─────────────────────
    #
    # `opening_odds` above is the SPORTSBOOK number and nothing else — the only
    # writer of `Event.opening_*` is `_maybe_set_opening_odds`, a median across
    # the books still quoting. It is served unlabelled, and the card printed it
    # as a bare "Opened 40/60" footnote that does not say which team is the 40.
    #
    # This is the same number when the books are all we hold, plus the two
    # prediction-market rungs above them, plus the one thing the card cannot
    # work out for itself: WHICH VENUE said it. `opening_odds` is left exactly as
    # it was — the highlight/upset logic, the confidence signal and three
    # clients read it, and none of them are asking this question.
    #
    # Emitted whenever a reading exists, for any status. A live card still shows
    # "Opened X/Y" and does not read this key; the reason to send it anyway is
    # that a status is a moment and the payload is cached, so a card that turns
    # FINAL between two feed pulls must not lose its prior in the process.
    prematch = resolve_prematch_reading(
        by_source=prematch_by_source,
        books_home=opening_home_prob,
        books_away=opening_away_prob,
    )
    if prematch is not None:
        # UX-P114's rule, third instance: the settled card prints BOTH of these
        # in fixed positions beside the two team names, so they are one duel and
        # they are rounded once, here, rather than independently on each of the
        # surfaces that draw them.
        pre_away_pct, pre_home_pct = rendered_duel_percents(
            prematch["away_probability"], prematch["home_probability"]
        )
        data["prematch_odds"] = {
            "home_probability": prematch["home_probability"],
            "away_probability": prematch["away_probability"],
            "home_rendered_percent": pre_home_pct,
            "away_rendered_percent": pre_away_pct,
            "source": prematch["source"],
        }

    if ended_at:
        data["ended_at"] = ended_at.isoformat()

    if highlight_label:
        data["highlight"] = {"label": highlight_label}

    if status in ("completed", "closed") and raw_ei is not None:
        raw_score = max(1, min(100, round(raw_ei * 100)))
        from app.routes.feed import _ei_label
        ei_data = {"score": raw_score, "label": _ei_label(raw_score)}
        data["ei"] = ei_data
        data["pulse"] = ei_data

    data["event_tags"] = inline_tags

    return data
