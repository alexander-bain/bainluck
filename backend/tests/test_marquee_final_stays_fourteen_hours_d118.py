"""D118 — last night's big game is still on Discover with your coffee.

Alex, Thu 2026-09-10 10:35am PT, choosing (B) from three offered in
``alex-inbox/discover-038-last-nights-game-disappears-from-discover-before-you-
wake-up.md``: **fourteen hours**, at most two such cards.

═══ WHY THIS IS A SHIP AND NOT A CONSTANT BUMP ═══

#4681 readmitted the marquee final to Discover and #4776 moved its clock from
the kickoff to the whistle. Both landed, both were certed, and **neither put a
game in front of a reader.** The arithmetic is the whole argument:

    NFL season opener, event 14780138, SEA 13 NE 10
      kickoff  2026-09-10T00:20:00Z   (5:20pm PT)
      whistle  2026-09-10T03:26:32Z   (8:26pm PT)
      8h from the kickoff -> retired 08:20Z = 1:20am PT   (before #4776)
      8h from the whistle -> retired 11:26Z = 4:26am PT   (after  #4776)

4:26am is not a time anybody opens Discover. So the ship "the night's big game
is there in the morning" was undeliverable by any anchor change; only the window
itself could deliver it. Fourteen hours retires the same game at **17:26Z =
10:26am PT**, which is the answer Alex picked and the sentence he was given:
*"A game finishing at 8:30pm is still on the page at 10:30am."*

═══ WHY A SECOND CONSTANT, NOT A BIGGER FIRST ONE ═══

``COMPLETED_EVENT_MAX_AGE_HOURS`` is shared: ``/sports`` runs the same
``isStale`` through ``applyFinishedCardGuard``, and the backend's ``#3836`` swap
pass trades first-page slots on a mirror of it. Raising it would have moved all
three on a ruling that spoke about one. It would also have made false the exact
sentence Alex was sold — *"it only ever affects genuinely big finished games"* —
which is a promise about scope, so it is kept in code:

    the arm selects (at most two, tier:1, EI-ranked)
      -> the payload records the selection (`discover_marquee_final`)
        -> the client grants fourteen hours to what was selected, eight to
           everything else, and eight to anything unstamped.

The stamp is what makes the two sides agree. Selecting a card the browser
deletes at hour eight is the same nothing as never selecting it — that is #3836
read in the other direction — so the decision has to travel in the payload.

═══ RED ARM — twelve mutations run, twelve red; counts are MEASURED ═══

Counted over the three files this ship touches — this one,
``test_client_deletion_mirror_3836.py`` and
``test_finished_marquee_on_discover_4681.py`` — plus the client suite
``frontend/__tests__/lib/discoverFeedFreshness.test.ts`` for the last three.

* ``CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS = 8`` — the pre-ship state: **7 red**. Counted over
  ``test_finished_marquee_on_discover_4681.py`` ALONE it is **1 red**, and that one is
  ``test_the_bound_is_the_MARQUEE_window_and_not_the_ordinary_one``, added for this ship: without
  it #4681's own suite stays entirely green while the arm silently returns to eight hours.
* ``_stamp_marquee_finals`` deleted from the served chain: **1 red**,
  ``test_and_the_card_it_serves_tells_the_browser_to_keep_it``. Only one, and
  worth saying so plainly: the arm still selects the card and every selection
  test stays green while the browser throws it away on arrival. That single
  assertion is the entire difference between this ship and #4681's, which
  passed its whole suite and served nobody for a day.
* ``finished_card_max_age_hours`` reading truthiness instead of ``is True``:
  **5 red** — one test, its five parametrised payloads.
* the stamp written only for kept ids (``if id in kept: … = True``): **1 red**,
  ``test_an_unkept_final_is_stamped_false_not_left_alone`` — the stale-``True``
  hole gotcha #6 exists for.
* ``> window`` weakened to ``>= window``: **4 red**, across all three files —
  both bounds are walked on both sides, so neither can drift alone.
* the stamp applied to every event card rather than finished ones: **3 red**
  (``scheduled``/``live``/``suspended``).
* the FRONTEND constant dropped to 8 while the backend kept 14: **1 red**,
  ``test_the_marquee_window_mirrors_too`` — the silent one, and the reason the
  mirror grew a second seam rather than a comment.
* the frontend selector switched to truthiness: **1 red** in the mirror
  (source-read) and **5 red** in the client suite.
* ``isStale`` comparing against ``COMPLETED_EVENT_MAX_AGE_HOURS`` directly
  instead of calling the selector: **1 red** in the mirror, **2 red** in the
  client suite.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import (
    _DISCOVER_RECENT_FINAL_SLOTS,
    _recent_marquee_final_ids,
    _stamp_marquee_finals,
    apply_discover_display_chain,
    PersonalizationContext,
)
from app.utils.feed_market_quality import _DISCOVER_FIRST_PAGE_CATEGORY_CAPS
from app.utils.sports_first_page_rails import (
    CLIENT_COMPLETED_MAX_AGE_HOURS,
    CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS,
    client_deletes_finished_card,
    finished_card_max_age_hours,
)

# ═════════════════════════════════════════════════════════════════════════════
# THE SPECIMEN, and every clock below is an offset from it. No branch on the
# real clock anywhere in this file (gotcha #44): the anchor is the game, the
# readings are hours after it, and the chain is handed `now` explicitly.
OPENER_ID = 14780138
KICKOFF = datetime(2026, 9, 10, 0, 20, 0, tzinfo=timezone.utc)
WHISTLE = datetime(2026, 9, 10, 3, 26, 32, tzinfo=timezone.utc)

#: 10:00am Pacific — a reader with a coffee, 13.56h past the whistle.
#:
#: NOT 10:30am, and the four minutes are worth the comment. Alex's sentence was
#: *"a game finishing at 8:30pm is still on the page at 10:30am"*, which is
#: fourteen hours EXACTLY. This game finished at 8:26:32pm PT, so its own
#: fourteen hours expire at 10:26:32am — an anchor at 10:30 is four minutes
#: outside the window and would have made the ship's headline test red for a
#: reason that is not a defect. ``test_the_specimen_retires_at_twenty_six_
#: minutes_past_ten`` pins that boundary rather than hiding it.
COFFEE = datetime(2026, 9, 10, 17, 0, 0, tzinfo=timezone.utc)

_NON_EVENT_CATEGORIES = {
    "politics": "politics",
    "geopolitics": "geopolitics",
    "economics": "economics",
    "tech": "tech",
    "entertainment": "entertainment",
    "weather_health": "weather",
    "other": "misc",
}


def _iso(when: datetime) -> str:
    return when.isoformat().replace("+00:00", "Z")


def _final(
    *,
    event_id: int = OPENER_ID,
    score: int = 67,
    tier: str = "tier:1",
    ei: int = 64,
    status: str = "completed",
    commence_time: datetime = KICKOFF,
    ended_at: datetime | None = WHISTLE,
    media: bool = True,
    sport: str = "americanfootball_nfl",
) -> dict:
    data: dict = {
        "id": event_id,
        "sport": sport,
        "status": status,
        "event_tags": [tier, "status:" + status],
        "home_team": "Seattle Seahawks",
        "away_team": "New England Patriots",
        "home_score": 13,
        "away_score": 10,
        "commence_time": _iso(commence_time),
        "ei": {"score": ei},
    }
    if ended_at is not None:
        data["ended_at"] = _iso(ended_at)
    if media:
        data["home_team_data"] = {"logo": "h"}
        data["away_team_data"] = {"logo": "a"}
    return {
        "type": "event",
        "score": score,
        "_rank_score": float(score),
        "_sort_time": 0,
        "headline": None,
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
    """Deep enough to fill page one on its own — same construction and same
    reason as #4681's suite: a thin pool lets demoted games through the
    progressive relaxation, so a page-one guard over a thin pool passes without
    the fix."""
    pool: list[dict] = []
    for group, cat in _NON_EVENT_CATEGORIES.items():
        cap = _DISCOVER_FIRST_PAGE_CATEGORY_CAPS.get(group, 3)
        for _ in range(cap + 2):
            pool.append(_futures(len(pool), 79.0 + (len(pool) % 11), category=cat))
    return pool


def _chain(items, now):
    return apply_discover_display_chain(
        items,
        limit=20,
        ctx=PersonalizationContext(),
        event_pct=0.15,
        now=now,
    )[0]


# ─────────────────────────────────────────────────────────────────────────────
class TestTheOpenerSurvivesTheMorning:
    """The ship. Every assertion here is FALSE on the parent commit."""

    def test_the_opener_is_still_selected_at_half_past_ten_pacific(self):
        assert _recent_marquee_final_ids([_final()], COFFEE) == {OPENER_ID}

    def test_and_it_reaches_page_one_at_that_hour(self):
        """Selection is not the ship — a reader seeing the card is. The pool
        below fills page one with futures scoring 79+, so a card that is merely
        readmitted and then capped to 35 does not appear here."""
        page = _chain(_saturating_futures_pool() + [_final()], COFFEE)[:20]
        finals = [i for i in page if (i.get("data") or {}).get("id") == OPENER_ID]
        assert finals, (
            "the NFL opener is not on Discover page one at 10:30am Pacific — "
            "which is the whole of D118"
        )
        assert finals[0]["score"] > 35

    def test_and_the_card_it_serves_tells_the_browser_to_keep_it(self):
        """The half that made #4681 and #4776 deliver nothing. The arm can keep
        a card all it likes; `isStale` runs in the browser afterwards."""
        page = _chain(_saturating_futures_pool() + [_final()], COFFEE)[:20]
        card = next(i for i in page if (i.get("data") or {}).get("id") == OPENER_ID)
        assert card["data"]["discover_marquee_final"] is True
        assert client_deletes_finished_card(card, now=COFFEE) is False

    def test_the_eight_hour_window_is_what_used_to_retire_it(self):
        """Not a claim about the fix — a measurement of the defect, so the
        margin this ship bought is on the record and cannot be quietly given
        back. At 10:00am Pacific the game is 16.67h past kickoff and 13.56h past
        the whistle: outside BOTH pre-D118 windows, inside this one."""
        hours_past_whistle = (COFFEE - WHISTLE).total_seconds() / 3600
        assert hours_past_whistle > CLIENT_COMPLETED_MAX_AGE_HOURS
        assert hours_past_whistle < CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS
        unstamped = _final()
        assert client_deletes_finished_card(unstamped, now=COFFEE) is True

    def test_the_specimen_retires_at_twenty_six_minutes_past_ten(self):
        """Fourteen hours is fourteen hours from THIS game's whistle, not from a
        round hour of the morning. Pinned so nobody reads the sentence Alex was
        given ("still on the page at 10:30am") as a promise about the clock —
        an 8:26pm final leaves at 10:26am, and a 9pm final at 11am."""
        assert _recent_marquee_final_ids(
            [_final()], datetime(2026, 9, 10, 17, 26, 0, tzinfo=timezone.utc)
        ) == {OPENER_ID}
        assert (
            _recent_marquee_final_ids(
                [_final()], datetime(2026, 9, 10, 17, 27, 0, tzinfo=timezone.utc)
            )
            == set()
        )


class TestTheWindowStillCloses:
    """Fourteen hours is a window, not an amnesty."""

    def test_a_final_past_fourteen_hours_is_not_admitted(self):
        late = WHISTLE + timedelta(hours=CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS + 1)
        assert _recent_marquee_final_ids([_final()], late) == set()

    def test_exactly_fourteen_hours_is_still_admitted(self):
        """The client compares with a strict `>`, so the boundary card renders.
        Both edges are walked so the bound cannot drift to `>=` unnoticed."""
        edge = WHISTLE + timedelta(hours=CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS)
        assert _recent_marquee_final_ids([_final()], edge) == {OPENER_ID}

    def test_a_hair_past_fourteen_hours_is_not(self):
        hair = WHISTLE + timedelta(hours=CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS, seconds=60)
        assert _recent_marquee_final_ids([_final()], hair) == set()

    def test_the_cap_of_two_survives_the_wider_window(self):
        """The window got longer, so MORE finals qualify — which is exactly when
        a cap earns its keep. Alex was told there is "a separate limit of two
        such cards at a time, so Discover cannot turn into a scoreboard"; six
        qualifying tier-1 finals spread across the fourteen hours must still
        yield two, and the two with the highest EI."""
        slate = [
            _final(
                event_id=1500 + n,
                ei=90 - n,
                # 13, 12, 11, 10, 9, 8 hours past their own whistles: every one
                # of them outside the ordinary eight-hour window and inside this
                # one, so the six exist BECAUSE the window widened.
                commence_time=COFFEE - timedelta(hours=16.1 - n),
                ended_at=COFFEE - timedelta(hours=13 - n),
            )
            for n in range(6)
        ]
        kept = _recent_marquee_final_ids(slate, COFFEE)
        assert len(kept) == _DISCOVER_RECENT_FINAL_SLOTS == 2
        assert kept == {1500, 1501}

    def test_the_wider_window_does_not_readmit_the_scoreboard(self):
        """The other direction, re-run on the new window rather than assumed to
        carry over from #4681: a tier-2 MLS final well inside fourteen hours is
        still not a marquee final. The window moved; the line did not."""
        mls = _final(event_id=15298475, tier="tier:2", ei=95, sport="soccer_usa_mls")
        assert _recent_marquee_final_ids([mls], COFFEE) == set()


class TestTheStampIsAFunctionOfThisRequest:
    """`_stamp_marquee_finals`. The flag is a decision travelling to a browser,
    and every wrong shape of it either keeps a dead card or drops a live one."""

    def test_a_kept_final_is_stamped_true(self):
        items = [_final()]
        _stamp_marquee_finals(items, {OPENER_ID})
        assert items[0]["data"]["discover_marquee_final"] is True

    def test_an_unkept_final_is_stamped_false_not_left_alone(self):
        """Writing only the winners leaves a stale `True` reachable the moment a
        `data` dict outlives its request (gotcha #6). Both values are written so
        the flag cannot outlive the decision that set it."""
        items = [_final()]
        _stamp_marquee_finals(items, {OPENER_ID})
        _stamp_marquee_finals(items, set())
        assert items[0]["data"]["discover_marquee_final"] is False
        assert client_deletes_finished_card(items[0], now=COFFEE) is True

    @pytest.mark.parametrize("status", ["scheduled", "live", "suspended"])
    def test_a_scheduled_card_is_not_stamped_at_all(self, status):
        """An unfinished card never reaches the arm the flag feeds, and a
        scheduled game carrying a finished-card field is a payload lie."""
        items = [_final(status=status, ended_at=None)]
        _stamp_marquee_finals(items, {OPENER_ID})
        assert "discover_marquee_final" not in items[0]["data"]

    @pytest.mark.parametrize(
        "item",
        [
            {"type": "futures", "data": {"id": OPENER_ID, "status": "completed"}},
            {"type": "event", "data": None},
            {"type": "event"},
        ],
    )
    def test_a_card_that_is_not_a_finished_game_is_skipped_quietly(self, item):
        _stamp_marquee_finals([item], {OPENER_ID})
        data = item.get("data")
        if isinstance(data, dict):
            assert "discover_marquee_final" not in data


class TestTheWindowIsChosenPerCardNotPerCaller:
    """`finished_card_max_age_hours` — the mirror of `finishedEventMaxAgeHours`.

    Three states reach it and only one is evidence: stamped `True`, stamped
    `False`, and absent (a `/sports` payload, or a Discover payload cached
    before D118 shipped). The last two must behave exactly as they did before
    this ship, or a constant meant for two cards a night silently became the
    site's finished-card policy.
    """

    def test_a_stamped_final_gets_fourteen(self):
        assert finished_card_max_age_hours(
            {"discover_marquee_final": True}
        ) == float(CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS)

    @pytest.mark.parametrize("data", [{}, {"discover_marquee_final": False}, None])
    def test_everything_else_gets_eight(self, data):
        assert finished_card_max_age_hours(data) == float(
            CLIENT_COMPLETED_MAX_AGE_HOURS
        )

    @pytest.mark.parametrize("truthy", [1, "true", "yes", ["x"], {"a": 1}])
    def test_a_non_boolean_stamp_is_not_evidence(self, truthy):
        """`is True`, never truthiness. The expensive direction of this error is
        keeping a dead card on the page, and a payload that arrives with
        `discover_marquee_final: 1` is a payload nobody in this repo wrote."""
        assert finished_card_max_age_hours(
            {"discover_marquee_final": truthy}
        ) == float(CLIENT_COMPLETED_MAX_AGE_HOURS)

    def test_an_unstamped_finished_card_ages_exactly_as_it_did_before(self):
        """The regression that would make this ship a site-wide policy change.
        A `/sports` payload carries no stamp; at 9h past the whistle it must
        still be gone, and at 7h still be there."""
        nine = WHISTLE + timedelta(hours=9)
        seven = WHISTLE + timedelta(hours=7)
        assert client_deletes_finished_card(_final(), now=nine) is True
        assert client_deletes_finished_card(_final(), now=seven) is False

    def test_the_explicit_override_beats_the_stamp(self):
        """`_recent_marquee_final_ids` asks with an explicit window because it is
        deciding the very thing the stamp records — it must not be able to read
        a previous request's answer and agree with itself."""
        stale_true = _final()
        stale_true["data"]["discover_marquee_final"] = True
        late = WHISTLE + timedelta(hours=20)
        assert (
            client_deletes_finished_card(
                stale_true,
                now=late,
                max_age_hours=CLIENT_MARQUEE_FINAL_MAX_AGE_HOURS,
            )
            is True
        )
