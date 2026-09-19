"""#4872 — a live game with nothing on the screen does not lead Discover.

THE SPECIMENS, dated and served. `GET /api/feed?limit=20&offset=0&event_pct=0.15`
at 2026-09-10 19:20Z — the parameters `app/discover/page.tsx` itself sends:

    slot 0  Vuelta a España 2026 (concept)          80   "General classification winner"
    slot 1  RC Lens @ Slavia Praha                  90   "Virtually even"
    slot 2  Bodø/Glimt @ Bayern Munich              35   ""      <- 0-0, no clock, 96/4
    slot 3  Sabah FK @ Manchester United            35   ""      <- 0-0, no clock, 97/3
    slot 4  Houston Astros @ Philadelphia Phillies  98   "Houston Astros odds shifted 24%"
    slot 5  Amgen Irish Open (tournament)          100   "Joaquin Niemann leads at 21.4%"

Two cards scoring **35 — the demotion cap, the score the ranker gives a game it
has judged non-exceptional — seated above a 98 and a 100.** Each rendered as a
green card, one grey placeholder box (#4862: one crest missing on both), the word
"Live", 0-0, no clock, and no sentence.

They are two of the five slots the ranking eval's first row counted as naming no
entity (`ARTIFACT-M-20260910-RANKING-EVAL.md`, 1825Z: 0/10 overlap against ESPN,
Yahoo, Kalshi and Polymarket; hard check FAILS; *"marquee cannot surface until
those slots do"*).

═══ WHY THE SHIPPED RULE DID NOT CATCH THEM ═══

`feed_market_quality.is_wholly_silent_card` is the rule for a card that does not
speak, and it opens `if item.get("type") != "futures": return False`. That scope
is deliberate and reasoned: *"a game card renders two team names, two scores and
two logos"*. **The premise is true of the card it was written about and false of
these** — a just-kicked-off game has 0-0 and no clock, and per #4862 one crest in
two is missing. Widening the futures predicate would collide with #4681 and
notice 27, which require a settled marquee final (no caption, story is the score)
to reach page one. So the game-card test lives beside the pass that SEATS these
cards, and the futures predicate is untouched.

The floor could not have corrected it either way: `compose_lead` runs at
`routes/feed.py:1711` and the floor at `:1733`, and the floor preserves the lead
prefix (C185) unless the lead card is itself an offender — which, being an event,
it never is. And it is NOT the live hoist, which fills the WORST window slots
walking backwards and cannot produce a slot-2 seating.

═══ THIS NARROWS ALEX'S OWN CRITERION, AND SAYS SO ═══

"Every event with status **live and a price**" (`live_first_page.py`) becomes
"live, priced, and with something on the screen". Recorded in #4872 with the four
options and the recommendation, rather than slipped in as a guard.

═══ RED ARM — five mutations run, five red; counts MEASURED ═══

Counted over this file plus the three suites whose fixtures this ship touched:
`test_tonights_games.py`, `tests/evals/test_discover_lead_order_contract.py` and
`test_feed_marquee_pin.py` (M5 over this file and `test_tonights_games.py`).

* the live arm returning `True` again — **the parent commit** — : **2 red**, and
  they are exactly this file's two ship assertions. Worth stating plainly rather
  than rounding up: nothing else in the repo notices, which is the whole reason
  the eval caught this and the suite did not.
* `headline` admitted as a door: **9 red**. Every live card's headline is the
  literal string `"Live"`, so this is the survivor a "just check all the text
  fields" version leaves behind — and it is why the door list omits it.
* `s > 0` relaxed to `s is not None` on the score doors: **9 red**. 0-0 with no
  clock is an unstarted game, not a scoreless one.
* the `bool` exclusion dropped from the score test: **1 red** — `True` would
  read as the number 1 and put a phantom goal on the board.
* the substance test widened to the `scheduled` arm: **7 red**, including
  `test_a_game_starting_soon_also_leads` and the whole pre-game slate. This is
  the mutation that shows the scoping is load-bearing and not timidity.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.tonights_games import (
    MAX_LEAD,
    compose_lead,
    live_game_card_has_substance,
    select_tonights_games,
)

NOW = datetime(2026, 9, 10, 19, 20, 0, tzinfo=timezone.utc)


def _game(
    *,
    event_id: int,
    name: str,
    status: str = "live",
    reason: str = "",
    context_summary: str = "",
    home_score=0,
    away_score=0,
    game_clock=None,
    period=None,
    score: int = 35,
    media: bool = True,
    commence: datetime | None = None,
) -> dict:
    away, _, home = name.partition(" @ ")
    data = {
        "id": event_id,
        "status": status,
        "away_team": away,
        "home_team": home,
        "home_score": home_score,
        "away_score": away_score,
        "game_clock": game_clock,
        "period": period,
        "commence_time": (commence or NOW - timedelta(minutes=20)).isoformat(),
        "current_odds": {"home_probability": 0.96, "away_probability": 0.04},
    }
    if media:
        # ONE crest, matching the specimens: `_is_eligible`'s media bar is `or`,
        # so a half-crested card passes it. #4862 is why that is the real shape.
        data["home_team_data"] = {"logo": "h"}
    return {
        "type": "event",
        "score": score,
        "_rank_score": float(score),
        "_sort_time": 0,
        "headline": "Live",
        "reason": reason,
        "context_summary": context_summary,
        "data": data,
    }


def _filler(i: int, score: float) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"f{i}",
        "reason": f"reason {i}",
        "data": {"id": 9000 + i, "name": f"market {i}"},
    }


BAYERN = dict(event_id=15311001, name="Bodø/Glimt @ Bayern Munich")
UNITED = dict(event_id=15311002, name="Sabah FK @ Manchester United")
LENS = dict(
    event_id=15311003,
    name="RC Lens @ Slavia Praha",
    reason="Virtually even",
    score=90,
)


# ─────────────────────────────────────────────────────────────────────────────
class TestTheTwoSpecimensDoNotLead:
    """The ship. Both assertions are false on the parent commit."""

    def test_neither_silent_card_is_selected_for_the_lead(self):
        assert select_tonights_games([_game(**BAYERN), _game(**UNITED)], NOW) == []

    def test_they_do_not_take_slots_2_and_3_from_a_98_and_a_100(self):
        """The served page, reconstructed at the point `compose_lead` sees it.

        THE INPUT IS SCORE-SORTED, and that is load-bearing rather than tidy:
        `routes/feed.py` sorts by `_rank_key` before this pass, so a 35 arrives
        BELOW a 98 and only the lead can put it back on top. Handing this
        function an unsorted list makes it pass on the parent commit — the two
        silent cards keep their input position and the test proves nothing.
        """
        items = [
            _filler(2, 100.0),
            _filler(1, 98.0),
            _game(**LENS),
            _game(**BAYERN),
            _game(**UNITED),
        ]
        led = compose_lead(items, include_tonights_games=True, now=NOW)
        order = [(i.get("data") or {}).get("id") for i in led]
        the_98, the_100 = 9001, 9002  # `_filler`'s ids
        assert order.index(BAYERN["event_id"]) > order.index(the_98)
        assert order.index(BAYERN["event_id"]) > order.index(the_100)
        assert order.index(UNITED["event_id"]) > order.index(the_98)
        assert order.index(UNITED["event_id"]) > order.index(the_100)
        # …and the one live game that DOES speak still leads the deck.
        assert order[0] == LENS["event_id"]

    def test_nothing_is_dropped_when_a_card_is_refused(self):
        """`compose_lead` re-orders and never removes — the property the whole
        module rests on, and the reason a rejection here cannot empty anything
        (#1091, gotcha #43). Asserted rather than trusted."""
        items = [_filler(1, 98.0), _game(**LENS), _game(**BAYERN), _game(**UNITED)]
        led = compose_lead(items, include_tonights_games=True, now=NOW)
        assert len(led) == len(items)
        assert {id(i) for i in led} == {id(i) for i in items}


class TestALiveGameThatSaysSomethingStillLeads:
    """The other direction, and the one that matters most: this must not empty
    the lead. #1091 is the standing lesson — a rule that protects a surface by
    emptying it has traded one defect for a worse one."""

    def test_a_live_game_with_a_reason_leads(self):
        assert len(select_tonights_games([_game(**LENS)], NOW)) == 1
        led = compose_lead(
            [_filler(1, 99.0), _game(**LENS)], include_tonights_games=True, now=NOW
        )
        assert (led[0].get("data") or {}).get("id") == LENS["event_id"]

    def test_a_live_game_with_a_clock_leads_even_with_no_sentence(self):
        """A genuine 0-0 in the 60th minute is a game a reader can watch. The
        clock is the substance; no caption is needed."""
        ticking = _game(**BAYERN, game_clock="60'")
        assert live_game_card_has_substance(ticking) is True
        led = compose_lead([_filler(1, 99.0), ticking], include_tonights_games=True, now=NOW)
        assert (led[0].get("data") or {}).get("id") == BAYERN["event_id"]

    def test_a_live_game_with_a_score_on_the_board_leads(self):
        scoring = _game(**BAYERN, home_score=2, away_score=1)
        assert live_game_card_has_substance(scoring) is True

    def test_a_period_counts_as_substance(self):
        assert live_game_card_has_substance(_game(**BAYERN, period="2nd Half")) is True

    def test_a_context_summary_counts_as_substance(self):
        assert (
            live_game_card_has_substance(_game(**BAYERN, context_summary="Upset brewing"))
            is True
        )


class TestTheDoorsAreTheRightDoors:
    def test_the_headline_is_not_a_door(self):
        """Every live card's headline is the literal string "Live" — the silent
        ones included. Admitting it would make the predicate true for the whole
        population it exists to catch."""
        silent = _game(**BAYERN)
        assert silent["headline"] == "Live"
        assert live_game_card_has_substance(silent) is False

    def test_zero_zero_with_no_clock_is_not_a_score(self):
        """An unstarted game, not a scoreless one. Both specimens read 0-0."""
        assert live_game_card_has_substance(_game(**BAYERN, home_score=0, away_score=0)) is False

    @pytest.mark.parametrize("junk", [True, False])
    def test_a_boolean_score_is_not_a_goal(self, junk):
        """`bool` is an `int` subclass, so `True` would read as the number 1 and
        put a phantom goal on the board."""
        assert live_game_card_has_substance(_game(**BAYERN, home_score=junk)) is False

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_a_blank_sentence_is_not_a_sentence(self, blank):
        assert live_game_card_has_substance(_game(**BAYERN, reason=blank)) is False

    @pytest.mark.parametrize("item", [None, "event", 7, [], {"type": "event"}])
    def test_a_malformed_item_has_no_substance_and_does_not_raise(self, item):
        assert live_game_card_has_substance(item) is False


class TestThePreGameLeadSurvives:
    """The substance test is scoped to the LIVE arm. A scheduled game has no
    clock and no score because it has not started; its substance is its start
    time. Applying the test there deletes the pre-game half of the lead."""

    def test_a_scheduled_game_inside_the_window_still_leads(self):
        soon = _game(
            **BAYERN,
            status="scheduled",
            commence=NOW + timedelta(hours=1),
        )
        selected = select_tonights_games([soon], NOW)
        assert [(i.get("data") or {}).get("id") for i in selected] == [
            BAYERN["event_id"]
        ]

    def test_a_whole_pre_game_slate_still_leads(self):
        slate = [
            _game(
                event_id=15312000 + n,
                name=f"Away {n} @ Home {n}",
                status="scheduled",
                commence=NOW + timedelta(hours=1, minutes=n),
            )
            for n in range(MAX_LEAD)
        ]
        assert len(select_tonights_games(slate, NOW)) == MAX_LEAD
