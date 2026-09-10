"""#4681 — the finished marquee game of the night reaches Discover.

THE SPECIMEN, dated: the NFL season opener, event 14780138, **SEA 13, NE 10**,
final ``2026-09-10T03:26:32Z``. ESPN and Yahoo led with it. Discover did not
carry it — not below the fold, not at rank 100. Measured at 06:26Z, three hours
after the whistle:

* ``GET /api/feed?limit=250`` returned 115 items of which **one** was an event,
  a live MLS fixture at position 2;
* the DB window held **217** event candidates, including exactly one
  ``completed / americanfootball_nfl`` — the specimen, ``tier:1``,
  ``class:pro_major``, ``timing:primetime``, EI 64, crests on both sides.

So 217 candidates reached the scorer and one reached the page. Not a ranking
outcome and not a window outcome: ``_filter_discover_event_noise`` dropped every
``completed``/``closed`` event unconditionally. The rule was written for a real
reason — "Discover is not the sports scoreboard" — but it could not tell last
night's Super Bowl from a Tuesday Superettan fixture, so it answered both the
same way. Standing notice 27: the finished marquee event of the night stays
page-one material for hours.

═══ WHY THE ARM IS NARROW, AND EACH BOUND MEASURED ═══

Both directions were measured on ``GET /api/feed?mode=sports&limit=250`` at
2026-09-10 06:3xZ, which served 39 finished games:

* **tier<=2 would have offered ten cards, NINE of them MLS.** That is a Major
  League Soccer results page, and several of those rows outscored the NFL one.
  ``tier:1`` is the marquee line and it is what the arm uses.
* **``has_team_media`` is not what bounds the population, and must not be
  mistaken for it.** All 15 completed MLB rows carry ``home_team_data = None``
  (Astros @ Phillies, Cubs @ Brewers — real clubs, no crest), so *today* that
  condition alone hides a full MLB slate. That is a media gap, not a policy, and
  it stops bounding anything the day the gap is fixed. ``_DISCOVER_RECENT_FINAL_
  SLOTS`` is the bound; the media check only keeps an unrenderable card out.
* **The age bound is borrowed, not invented.** ``client_deletes_finished_card``
  mirrors ``frontend/lib/discover/feedFreshness.ts`` and is CI-guarded against
  it, so a slot cannot be spent on a card the browser deletes before paint
  (#3836).

═══ THE REASON LINE IS NOT PART OF THIS SHIP, DELIBERATELY ═══

The NOTE asked for "a reason that is now true — *Seahawks held on 13-10*, not
*Upset brewing*". The danger it names is real and it is already handled, by a
ruling this ship must not walk back: #4094 removed the settled sentence on
purpose, because a finished card already says the result three ways (the Final
chip, the score with the winner bolded, each side's dimmed pre-game percentage —
all three are in ``components/discover/EventCard.tsx``), and the sentence it
replaced was the scoreboard restated. ``generate_event_reason`` returns ``""``
for a finished game and never a live-tense one; that is pinned below rather than
overwritten, because readmitting these cards is exactly the change that would
make a live-tense reason reachable if one ever appeared.
"""

from datetime import datetime, timedelta, timezone

from app.routes.feed import (
    _DISCOVER_RECENT_FINAL_SLOTS,
    _filter_discover_event_noise,
    _recent_marquee_final_ids,
    apply_discover_display_chain,
    PersonalizationContext,
)
from app.utils.feed_market_quality import _DISCOVER_FIRST_PAGE_CATEGORY_CAPS
from app.utils.feed_reasons import generate_event_reason
from app.utils.sports_first_page_rails import CLIENT_COMPLETED_MAX_AGE_HOURS

# Fixed anchor, and no branch on the clock anywhere below (gotcha #44): every
# fixture offsets from this and the chain is handed it explicitly.
NOW = datetime(2026, 9, 10, 6, 26, 0, tzinfo=timezone.utc)

_NON_EVENT_CATEGORIES = {
    "politics": "politics",
    "geopolitics": "geopolitics",
    "economics": "economics",
    "tech": "tech",
    "entertainment": "entertainment",
    "weather_health": "weather",
    "other": "misc",
}


def _game(
    *,
    event_id: int,
    score: int,
    status: str = "completed",
    tier: str = "tier:1",
    ei: int | None = 64,
    hours_since_kickoff: float = 6.1,
    media: bool = True,
    sport: str = "americanfootball_nfl",
    headline: str | None = None,
) -> dict:
    data = {
        "id": event_id,
        "sport": sport,
        "status": status,
        "event_tags": [tier, "status:" + status],
        "home_team": "Seattle Seahawks",
        "away_team": "New England Patriots",
        "home_score": 13,
        "away_score": 10,
        "commence_time": (
            NOW - timedelta(hours=hours_since_kickoff)
        ).isoformat().replace("+00:00", "Z"),
    }
    if media:
        data["home_team_data"] = {"logo": "h"}
        data["away_team_data"] = {"logo": "a"}
    if ei is not None:
        data["ei"] = {"score": ei}
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


def _saturating_futures_pool() -> list[dict]:
    """Deep enough to fill page one on its own.

    Same construction, and the same reason, as
    ``test_feed_discover_event_demotion_reachability.py``: a thin pool lets
    demoted games onto the page through `diversify_discover_first_page`'s
    progressive relaxation, so a page-one guard over a thin pool passes without
    the fix.
    """
    pool: list[dict] = []
    for group, cat in _NON_EVENT_CATEGORIES.items():
        cap = _DISCOVER_FIRST_PAGE_CATEGORY_CAPS.get(group, 3)
        for _ in range(cap + 2):
            pool.append(_futures(len(pool), 79.0 + (len(pool) % 11), category=cat))
    return pool


def _chain(items):
    return apply_discover_display_chain(
        items,
        limit=20,
        ctx=PersonalizationContext(),
        event_pct=0.15,
        now=NOW,
    )[0]


# ─────────────────────────────────────────────────────────────────────────────
class TestTheOpenersFinalReachesTheReader:
    """The ship. Each of these is false on the parent commit."""

    def test_the_nfl_opener_is_on_page_one_after_the_final(self):
        page = _chain(_saturating_futures_pool() + [_game(event_id=14780138, score=67)])[
            :20
        ]
        finals = [i for i in page if (i.get("data") or {}).get("id") == 14780138]
        assert finals, (
            "the finished NFL opener is not on Discover page one — the defect "
            "#4681 was filed for (notice 27)"
        )
        # NOT mere presence. The demotion caps a non-exceptional event to 35,
        # which on a page of 79+ futures is an exclusion wearing a score; and
        # lead composition can pin a game to slot 0 even when flattened. What
        # the reader cares about is whether the card is a real 67 or a husk.
        assert finals[0]["score"] > 35, (
            f"the final is on the page but capped to {finals[0]['score']} — "
            "surviving the noise filter alone buys the card nothing"
        )

    def test_the_specimen_is_selected_by_the_arm_itself(self):
        # The unit under the page test: the page test can pass for composition
        # reasons, this cannot.
        specimen = _game(event_id=14780138, score=67)
        assert _recent_marquee_final_ids([specimen], NOW) == {14780138}

    def test_the_noise_filter_keeps_exactly_what_it_is_handed(self):
        specimen = _game(event_id=14780138, score=67)
        assert _filter_discover_event_noise([specimen], {14780138}) == [specimen]
        # …and drops it when it is not selected, which is what makes the
        # selection load-bearing rather than decorative.
        assert _filter_discover_event_noise([specimen], set()) == []


class TestTheScoreboardStaysOut:
    """The other direction, and the reason the arm is narrow."""

    def test_an_mls_final_is_not_admitted(self):
        # Measured: nine of the ten tier<=2 finals in the window were MLS.
        mls = _game(event_id=15298475, score=94, tier="tier:2", ei=70,
                    sport="soccer_usa_mls")
        assert _recent_marquee_final_ids([mls], NOW) == set()

    def test_a_final_the_client_would_delete_is_not_admitted(self):
        stale = _game(
            event_id=15308043,
            score=67,
            hours_since_kickoff=CLIENT_COMPLETED_MAX_AGE_HOURS + 1,
        )
        assert _recent_marquee_final_ids([stale], NOW) == set()

    def test_a_final_at_exactly_the_client_bound_IS_admitted(self):
        # The client's comparison is strict `>`; a card at the threshold is
        # rendered. Both edges of the interval are walked so the bound cannot
        # drift to `>=` unnoticed.
        edge = _game(
            event_id=15308044,
            score=67,
            hours_since_kickoff=CLIENT_COMPLETED_MAX_AGE_HOURS,
        )
        assert _recent_marquee_final_ids([edge], NOW) == {15308044}

    def test_a_crestless_final_is_not_admitted(self):
        # Today's whole completed-MLB population. Kept out because it renders
        # as a nameless card, NOT because it is baseball.
        crestless = _game(event_id=15308046, score=67, ei=93, media=False,
                          sport="baseball_mlb")
        assert _recent_marquee_final_ids([crestless], NOW) == set()

    def test_at_most_two_finals_are_kept_however_many_qualify(self):
        # The bound that survives the MLB media gap being fixed: five qualifying
        # tier-1 finals, two slots.
        slate = [
            _game(event_id=1500 + n, score=67, ei=90 - n, sport="baseball_mlb")
            for n in range(5)
        ]
        kept = _recent_marquee_final_ids(slate, NOW)
        assert len(kept) == _DISCOVER_RECENT_FINAL_SLOTS == 2
        # …and they are the two most exciting, not the first two seen.
        assert kept == {1500, 1501}

    def test_page_one_does_not_become_a_results_page(self):
        slate = [
            _game(event_id=1600 + n, score=90, ei=95 - n, sport="baseball_mlb")
            for n in range(8)
        ]
        page = _chain(_saturating_futures_pool() + slate)[:20]
        finals = [
            i
            for i in page
            if i.get("type") == "event"
            and (i["data"].get("status") or "") == "completed"
        ]
        assert len(finals) <= _DISCOVER_RECENT_FINAL_SLOTS, (
            f"{len(finals)} finished games on page one — Discover is the "
            "scoreboard again, which is what the blanket drop was protecting"
        )


class TestNothingElseMoved:
    """Controls. A narrow arm that quietly widens is the same defect back."""

    def test_a_live_game_is_untouched(self):
        live = _game(event_id=1700, score=69, status="live", ei=None)
        assert _recent_marquee_final_ids([live], NOW) == set()
        # Still served — the live arm below the completed one, unchanged.
        assert _filter_discover_event_noise([live], set()) == [live]

    def test_an_ordinary_scheduled_game_is_still_demoted(self):
        # Score 50, and that matters: #4504's first arm keeps ANY event scoring
        # >= 85, so a 98 here would be an exception on its own account and the
        # assertion would fail against correct code. "Ordinary" has to mean
        # ordinary to the predicate, not just to the reader.
        page = _chain(
            _saturating_futures_pool()
            + [_game(event_id=1800, score=50, status="scheduled", ei=None)]
        )[:20]
        ordinary = [i for i in page if (i.get("data") or {}).get("id") == 1800]
        assert not ordinary or ordinary[0]["score"] <= 35, (
            "a routine scheduled game kept its score — the demotion this ship "
            "carves ONE exception out of has stopped applying"
        )

    def test_a_futures_card_is_never_selected(self):
        assert _recent_marquee_final_ids([_futures(1, 90.0, "politics")], NOW) == set()

    def test_the_selection_is_stable_across_calls(self):
        # Ties are broken by event id, so two requests over one pool cannot
        # disagree about which finals the reader gets.
        slate = [_game(event_id=1900 + n, score=67, ei=70) for n in range(4)]
        assert _recent_marquee_final_ids(slate, NOW) == _recent_marquee_final_ids(
            list(reversed(slate)), NOW
        )


class TestTheFinishedCardSaysNothingUntrue:
    """#4094's rule, pinned by the ship that makes these cards reachable.

    Readmitting finished games to Discover is precisely the change that would
    make a live-tense reason visible if one existed. It does not — and the
    empty string is the deliberate answer, not an omission.
    """

    def test_a_finished_game_carries_no_reason_sentence(self):
        assert (
            generate_event_reason(
                home_team="Seattle Seahawks",
                away_team="New England Patriots",
                status="completed",
                highlight_reasons=["major_prob_swing"],
                home_score=13,
                away_score=10,
                opening_home_prob=0.61,
            )
            == ""
        )

    def test_a_finished_game_never_borrows_the_live_sentence(self):
        # The NOTE's actual worry: "Upset brewing" on a game that is over. The
        # live branch's sentence is keyed on `favorite_switched`; a finished
        # game carrying that flag must not reach it.
        reason = generate_event_reason(
            home_team="Seattle Seahawks",
            away_team="New England Patriots",
            status="completed",
            highlight_reasons=["favorite_switched"],
            home_score=13,
            away_score=10,
            opening_home_prob=0.61,
        )
        assert "leading" not in reason.lower()
        assert "brewing" not in reason.lower()
