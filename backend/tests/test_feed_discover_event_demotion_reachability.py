"""#4504 — the Discover event demotion exception must be able to FIRE.

Discover page one served **zero** game cards across a full MLB slate, live
US Open tennis, a UFC card and the UCL window. Not a thinned slate — an empty
one, which is the standing "game events are never capped into an empty tab"
rule (#1091, CLAUDE.md) recurring on page one.

The cause was not a threshold set too high. It was that
``_is_discover_event_demotion_exception`` read its excitement signal from
``data["ei"]``, and ``build_event_feed_data`` writes ``ei`` **only** for
``completed``/``closed`` events — which ``_filter_discover_event_noise`` then
drops. Three of the four arms were therefore unreachable for anything that
could reach a reader, and the fourth named four words
(``elimination``/``buzzer``/``walk-off``/``historic``) that ``get_highlight_label``
cannot emit. Measured against the live 15:00 PT feed: the predicate fired for
10 of 10 completed events and **0 of 35** noise-filter survivors.

These are reachability guards. The three threshold tests in
``test_feed_discover_event_demotion.py`` pin what stays demoted; this file pins
that something can survive, which is the half that was silently false.
"""

import ast
import inspect

import pytest

from app.routes.feed import (
    _DISCOVER_EVENT_EXCEPTION_KEYWORDS,
    _demote_non_exceptional_discover_events,
    _filter_discover_event_noise,
    _is_discover_event_demotion_exception,
    apply_discover_display_chain,
    PersonalizationContext,
)
from app.utils.feed_market_quality import _DISCOVER_FIRST_PAGE_CATEGORY_CAPS
from app.utils.highlights import get_highlight_label

# One `llm_sport_category` per first-page category group, EXCEPT `sports_culture`
# — that is the group game cards land in, so stocking it with futures would
# crowd them out legitimately and the page-one guard would fail for a reason
# that has nothing to do with the demotion. The remaining seven groups cap at
# 23 slots between them, comfortably more than the 20-card first page.
_NON_EVENT_CATEGORIES = {
    "politics": "politics",
    "geopolitics": "geopolitics",
    "economics": "economics",
    "tech": "tech",
    "entertainment": "entertainment",
    "weather_health": "weather",
    "other": "misc",
}


def _event(
    *,
    score: int,
    headline: str,
    sport: str = "baseball_mlb",
    status: str = "scheduled",
    event_tags: list[str] | None = None,
    ei_score: int | None = None,
) -> dict:
    data = {
        "id": abs(hash((score, headline, sport, status))) % 100000,
        "sport": sport,
        "status": status,
        "event_tags": event_tags if event_tags is not None else ["tier:1"],
        "home_team": "Home",
        "away_team": "Away",
        "home_team_data": {"logo": "h"},
        "away_team_data": {"logo": "a"},
    }
    if ei_score is not None:
        data["ei"] = {"score": ei_score}
    return {
        "type": "event",
        "score": score,
        "_rank_score": float(score),
        "_sort_time": 0,
        "headline": headline,
        "data": data,
    }


def _futures(i: int, score: float, category: str) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"f{i}",
        "data": {
            "id": 10_000 + i,
            "name": f"market {i}",
            "llm_sport_category": category,
            "outcomes": [{"name": "Yes", "probability": 0.5}],
        },
    }


class TestTheExceptionCanFireOnAReachableEvent:
    """The bug in one assertion, at three statuses."""

    @pytest.mark.parametrize("status", ["scheduled", "live"])
    def test_a_high_scoring_major_league_game_with_no_ei_is_exceptional(self, status):
        # The exact specimen from #4504: Guardians @ Orioles, MLB, scored 98 by
        # the feed's own scorer, headline "Close matchup", `ei` absent because
        # the game has not finished. Before the fix this returned False and the
        # card was capped to 35.
        item = _event(score=98, headline="Close matchup", status=status)

        assert _discover_ei_is_absent(item)
        assert _is_discover_event_demotion_exception(item) is True

        _demote_non_exceptional_discover_events([item])
        assert item["score"] == 98

    def test_the_predicate_is_not_anti_correlated_with_surviving_the_noise_filter(self):
        # The shape of the defect: every event the predicate accepted was one
        # the noise filter was about to delete. A pool where the ONLY
        # exceptional events are completed is the bug, not a slate.
        pool = [
            _event(score=98, headline="Close matchup", status="scheduled"),
            _event(score=82, headline="Momentum shift", status="live"),
            _event(score=44, headline="Recent upset", status="completed", ei_score=99),
        ]

        survivors = _filter_discover_event_noise(pool)
        exceptional_survivors = [
            i for i in survivors if _is_discover_event_demotion_exception(i)
        ]

        assert survivors, "noise filter dropped everything — fixture is wrong"
        assert exceptional_survivors, (
            "no event that survives the noise filter can be exceptional; the "
            "exception is keyed on a field only deleted events carry (#4504)"
        )


class TestWhatStaysDemoted:
    """The fix is additive, not a surrender of the demotion."""

    def test_a_routine_major_league_game_is_still_demoted(self):
        # Discover is not the scoreboard. A tier:1 game that the scorer itself
        # rates middling must still lose to "Will China invade Taiwan?".
        item = _event(score=50, headline="Live", status="live")

        _demote_non_exceptional_discover_events([item])

        assert item["score"] == 35

    def test_a_high_scoring_obscure_league_game_is_still_demoted(self):
        # Gotcha #24: demotion exceptions are tier-gated. A 95 in a tier:4
        # league is a scoring artefact, not a story.
        item = _event(
            score=95,
            headline="Upset brewing",
            sport="soccer_brazil_campeonato",
            status="live",
            event_tags=["tier:4"],
        )

        _demote_non_exceptional_discover_events([item])

        assert item["score"] == 35

    def test_a_settled_event_exceptional_on_ei_stays_exceptional(self):
        # Strictly additive: the settled path is unchanged, including the
        # ungated `ei >= 85` arm that the finished rail depends on.
        item = _event(
            score=44,
            headline="Recent upset",
            sport="soccer_brazil_campeonato",
            status="completed",
            event_tags=["tier:4"],
            ei_score=99,
        )

        assert _is_discover_event_demotion_exception(item) is True


class TestTheKeywordsExistInTheVocabulary:
    """The class of bug: a keyword list naming words nothing can emit."""

    def test_every_exception_keyword_is_reachable_from_a_real_highlight_label(self):
        # `get_highlight_label` is the closed set of headlines an event card can
        # wear. The arm used to match on "elimination", "buzzer", "walk-off" and
        # "historic" — none of which it can return — so the arm was decoration.
        #
        # Read the labels from the function's own `return` nodes via `ast`, not
        # by grepping its source: a docstring that merely NAMES a label would
        # make a substring scan pass while the code emits nothing (the
        # source-scan blinding trap).
        tree = ast.parse(inspect.getsource(get_highlight_label))
        labels = {
            node.value.value.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Return)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        }
        assert len(labels) > 5, f"parsed too few labels ({labels}) — parse is wrong"

        unreachable = [
            kw
            for kw in _DISCOVER_EVENT_EXCEPTION_KEYWORDS
            if not any(kw in label for label in labels)
        ]

        assert not unreachable, (
            f"exception keywords no highlight label can contain: {unreachable}. "
            f"An unmatched keyword is a dead arm. Labels: {sorted(labels)}"
        )


class TestPageOneKeepsAGame:
    """The ship, end to end: a reader on a full slate sees a game."""

    def test_a_full_slate_puts_at_least_one_game_on_page_one(self):
        # 23 non-event cards scoring 79-89 is what the live feed actually
        # carried; every one of them outscores the 35 cap, so the cap acted as
        # an exclusion rather than a demotion and page one held no game at all.
        #
        # The futures pool must be able to FILL all 20 slots on its own or this
        # guard cannot fail: `diversify_discover_first_page` relaxes its
        # per-category caps progressively when it comes up short, and a thin
        # pool lets demoted games in through that fallback. An earlier draft of
        # this fixture used five categories (18 slots at cap) and passed against
        # the unfixed predicate. `_NON_EVENT_CATEGORIES` covers every group in
        # `_DISCOVER_FIRST_PAGE_CATEGORY_CAPS`, 23 slots at cap.
        futures = _saturating_futures_pool()
        games = [
            _event(score=98, headline="Close matchup", status="scheduled"),
            _event(score=93, headline="Close matchup", status="scheduled"),
            _event(score=82, headline="Momentum shift", status="live"),
        ]

        items, _meta = apply_discover_display_chain(
            futures + games,
            limit=20,
            ctx=PersonalizationContext(),
            event_pct=0.15,
        )

        first_page = items[:20]
        games_on_page = [i for i in first_page if i.get("type") == "event"]
        undemoted = [i for i in games_on_page if i["score"] > 35]

        # NOT `any(type == "event")`. Lead composition pins a game to slot 0
        # even when the demotion has flattened it, so mere presence is true on
        # the unfixed code — the first draft of this assertion passed against
        # the bug. What is false on the unfixed code, and what the reader
        # actually cares about, is whether that card is a live 98 or a husk
        # capped to 35.
        assert undemoted, (
            "every game on Discover page one is capped at 35 — the "
            "'game events are never capped into an empty tab' rule (#1091). "
            f"page-one games: {[i['score'] for i in games_on_page]}"
        )

    def test_page_one_is_still_mostly_not_games(self):
        # The other direction: the fix must not turn Discover into /sports.
        # The `sports_culture` first-page cap is what bounds this.
        futures = _saturating_futures_pool()
        games = [
            _event(score=90 + i, headline="Close matchup", status="scheduled")
            for i in range(10)
        ]

        items, _meta = apply_discover_display_chain(
            futures + games,
            limit=20,
            ctx=PersonalizationContext(),
            event_pct=0.15,
        )

        first_page = items[:20]
        event_count = sum(1 for i in first_page if i.get("type") == "event")
        assert event_count <= 5, (
            f"{event_count} of {len(first_page)} page-one cards are games; "
            "Discover is not the scoreboard"
        )


def _saturating_futures_pool() -> list[dict]:
    """A non-event pool deep enough to fill page one without any relaxation.

    Every category group in `_DISCOVER_FIRST_PAGE_CATEGORY_CAPS`, each stocked
    past its cap, all scoring above the 35 demotion floor — the live shape that
    made the cap an exclusion rather than a demotion.
    """
    pool: list[dict] = []
    for group, cat in _NON_EVENT_CATEGORIES.items():
        cap = _DISCOVER_FIRST_PAGE_CATEGORY_CAPS.get(group, 3)
        for n in range(cap + 2):
            pool.append(_futures(len(pool), 79.0 + (len(pool) % 11), category=cat))
    return pool


def _discover_ei_is_absent(item: dict) -> bool:
    data = item.get("data") or {}
    return not data.get("ei") and not data.get("pulse")
