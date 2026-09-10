"""#4080 clause (d) — a page-one card that names nothing that HAPPENED yields it.

The third and widest class the first-page floor screens on, after the ladder
(#1958) and the wholly silent card (#4695).

The gap it closes: `explanation-coverage@20` asks whether a card said ANYTHING,
and every card on the page passes it. A reader still cannot tell why any of them
is here THIS MORNING, because the copy is one of three standing facts — a count
of inventory ("2 related markets"), provenance ("across 2 sources"), or a
leader ("Los Angeles Dodgers leads at 29%", as true last Tuesday as today).
Measured on the live page one of 2026-09-10 09:55Z: 4 of the first 10 cards
carried a why-now.

Two things make this class different from its two siblings, and both are pinned
below:

  * **It is POSITION-DEPENDENT.** It governs the first ten slots, not the twenty
    the other classes screen. At twenty the swap drags the futures tail forward
    and page one becomes a futures monoculture — the thing the why-now oracle
    exists to prevent, arriving through the window instead (gotcha #43, #1091).
  * **It is SCOPED BY CARD TYPE.** #4695's predicate shipped unscoped and
    CERT-2481 blocked it for demoting the finished marquee final that #4681 and
    standing notice 27 exist to surface. Both directions are asserted here.

THE FIXTURES ARE VERBATIM, from `GET /api/feed?limit=120` on 2026-09-10 ~09:55Z,
trimmed to the fields the control reads and not otherwise tidied.
"""

import pytest

from app.utils.feed_market_quality import (
    FIRST_PAGE_WHY_NOW_WINDOW,
    enforce_first_page_quality_floor,
    lacks_a_why_now,
)

# ── Specimens that say nothing that happened ─────────────────────────────────

#: Slot 1 of the live page one. It speaks — so #4695 does not touch it — and
#: what it says is a standing fact.
DODGERS_LEADS = {
    "type": "futures",
    "score": 85,
    "headline": "Los Angeles Dodgers leads at 29%",
    "reason": "Los Angeles Dodgers (29%) leads MLB World Series Winner",
    "context_summary": "Los Angeles Dodgers leads at 29%",
    "data": {"name": "MLB World Series Winner", "hook_description": None},
}

#: A bundle's own copy is its shared question — a "what", never a "why now" —
#: so it passes or fails on its MEMBERS' signals. Both of this one's members
#: print a standing leader.
BUNDLE_NO_WHY_NOW = {
    "type": "bundle",
    "score": 80,
    "headline": "2028 Election",
    "reason": "Who wins in 2028?",
    "context_summary": None,
    "data": {
        "name": "2028 Election",
        "items": [
            {
                "headline": "J.D. Vance leads at 23%",
                "context_summary": "J.D. Vance leads at 23%",
            },
            {
                "headline": "Jon Ossoff leads at 17%",
                "context_summary": "Jon Ossoff leads at 17%",
            },
        ],
    },
}

# ── Specimens that DO name something that happened ───────────────────────────

BUNDLE_WITH_WHY_NOW = {
    "type": "bundle",
    "score": 80,
    "headline": "AI",
    "reason": "Which AI model comes out on top?",
    "context_summary": None,
    "data": {
        "name": "AI",
        "items": [
            {
                "headline": "Claude leads at 58%",
                "context_summary": "Claude leads at 58%",
            },
            {
                "headline": "New favorite: Claude (84%)",
                "context_summary": "New favorite: Claude (84%)",
            },
        ],
    },
}

SPEAKING_TAIL_CARD = {
    "type": "futures",
    "score": 40,
    "headline": "Kalshi up 6.0 points today",
    "reason": "Kalshi moved up 6.0 points today",
    "context_summary": "Kalshi up 6.0 points today",
    "data": {"name": "Kalshi IPO in 2026?", "hook_description": None},
}

# ── The exempt types: substance that no caption field holds ──────────────────

#: A game card's story is its score. #4681 and standing notice 27 REQUIRE a
#: finished marquee final to reach page one, and it carries no caption at all.
FINISHED_GAME = {
    "type": "event",
    "score": 90,
    "headline": None,
    "reason": "",
    "context_summary": "",
    "data": {"name": "Seattle Seahawks 13, New England Patriots 10"},
}

#: Slot 0 of the live page one. A concept card renders the matchup and, when the
#: thing is happening, the most time-anchored word the feed prints.
LIVE_CONCEPT = {
    "type": "concept",
    "score": 95,
    "headline": "Live",
    "reason": "General classification winner",
    "context_summary": None,
    "data": {"name": "Vuelta a España 2026"},
}

#: A concept card that is NOT live still renders its matchup, and is still
#: exempt — the exemption is about where a card's substance lives, not about
#: whether it happens to hold a marker.
UPCOMING_CONCEPT = {
    "type": "concept",
    "score": 70,
    "headline": "Van vs Pantoja",
    "reason": "Flyweight title bout",
    "context_summary": None,
    "data": {"name": "UFC 320"},
}


def _speaking(key: str) -> dict:
    """A clean futures card carrying a why-now, for filling a tail."""
    return {
        "type": "futures",
        "score": 30,
        "headline": f"{key} up 4.0 points today",
        "reason": f"{key} moved up 4.0 points today",
        "context_summary": f"{key} up 4.0 points today",
        "data": {"name": f"Market {key}", "hook_description": None},
    }


def _mute(key: str) -> dict:
    """A clean-but-reasonless futures card: speaks, says nothing that happened."""
    return {
        "type": "futures",
        "score": 30,
        "headline": f"{key} leads at 22%",
        "reason": f"{key} (22%) leads Market {key}",
        "context_summary": f"{key} leads at 22%",
        "data": {"name": f"Market {key}", "hook_description": None},
    }


class TestThePredicate:
    def test_a_standing_leader_is_not_a_why_now(self):
        assert lacks_a_why_now(DODGERS_LEADS) is True

    def test_a_bundle_passes_on_its_members_signals(self):
        assert lacks_a_why_now(BUNDLE_WITH_WHY_NOW) is False

    def test_a_bundle_whose_members_only_stand_still_does_not(self):
        assert lacks_a_why_now(BUNDLE_NO_WHY_NOW) is True

    def test_a_card_that_names_a_move_is_kept(self):
        assert lacks_a_why_now(SPEAKING_TAIL_CARD) is False

    @pytest.mark.parametrize(
        "card",
        [FINISHED_GAME, LIVE_CONCEPT, UPCOMING_CONCEPT],
        ids=["finished_game", "live_concept", "upcoming_concept"],
    )
    def test_the_exempt_types_are_never_judged(self, card):
        """Gotcha #43, and the CERT-2481 BLOCK: state the card-type scope.

        `FINISHED_GAME` carries no caption whatsoever, so an unscoped predicate
        demotes exactly the card #4681 and notice 27 require on page one.
        """
        assert lacks_a_why_now(card) is False

    def test_absence_of_capture_is_not_absence_of_a_reason(self):
        """A fixture reduced past the oracle's doors must not read as reasonless.

        The #1958 corpus carries none of them. A predicate testing values alone
        would call all 49 of its cards offenders and hand the floor a page with
        nothing clean to swap in — the same trap `is_wholly_silent_card`
        documents (#4695).
        """
        reduced = {"type": "futures", "score": 50, "data": {"name": "Reduced"}}
        assert lacks_a_why_now(reduced) is False


class TestTheFloorAndTheMetricShareOneOracle:
    def test_the_floor_calls_the_metrics_own_function_4080(self):
        """The control and the metric cannot drift, because they are one object.

        Three handshake failures in a week (#4695, #4708, CERT-2473) were all a
        producer and a consumer agreeing on a vocabulary with nothing testing the
        join. If a local copy of the why-now vocabulary is ever introduced here,
        this fails.
        """
        import inspect

        from app.utils import feed_market_quality
        from app.utils.feed_quality_debug import (
            TEMPORAL_HEADLINE_WHY_NOWS,
            WHY_NOW_MARKERS,
            _card_why_now,
        )

        # 1. No second copy of the vocabulary. A local list is how the two
        #    halves start agreeing on paper and disagreeing in production.
        floor_source = inspect.getsource(feed_market_quality)
        assert "WHY_NOW_MARKERS = (" not in floor_source
        assert "TEMPORAL_HEADLINE_WHY_NOWS = (" not in floor_source

        # 2. The join itself, driven over the ORACLE'S OWN vocabulary rather
        #    than a hand-written sample of it: every phrase the metric credits,
        #    the floor must also credit. If a marker is added to one side only,
        #    this fails on that marker by name.
        for marker in WHY_NOW_MARKERS:
            card = dict(DODGERS_LEADS)
            card["context_summary"] = f"Something {marker} happened"
            assert _card_why_now(card) is not None, marker
            assert lacks_a_why_now(card) is False, marker

        for headline in TEMPORAL_HEADLINE_WHY_NOWS:
            card = dict(DODGERS_LEADS)
            card["headline"] = headline
            card["context_summary"] = None
            card["reason"] = ""
            assert _card_why_now(card) is not None, headline
            assert lacks_a_why_now(card) is False, headline

        # 3. And the refusals agree too — a selection fact is not a why-now on
        #    either side.
        assert _card_why_now(DODGERS_LEADS) is None
        assert lacks_a_why_now(DODGERS_LEADS) is True


class TestTheWindowIsTen:
    def test_the_why_now_window_is_ten_4080(self):
        """The number is the decision. Measured over the live pool 2026-09-10:

            window 10 -> 6 offenders, 47 replacements, page one 40% futures
            window 20 -> 13 offenders, 38 replacements, page one 75% futures

        At twenty the swap drags the futures tail forward and page one becomes
        the monoculture the oracle was written to prevent. If this constant is
        ever widened, that regression ships silently — so it is pinned.
        """
        assert FIRST_PAGE_WHY_NOW_WINDOW == 10

    def test_the_route_passes_the_window_explicitly(self):
        """Not inherited from `first_page_size`, which is twenty."""
        import inspect

        from app.routes import feed as feed_route

        source = inspect.getsource(feed_route)
        assert "why_now_window=FIRST_PAGE_WHY_NOW_WINDOW" in source

    def test_clause_d_governs_the_first_ten_slots_only(self):
        """A reasonless card inside the window yields; the same card outside it
        keeps its place. This is what makes the class position-dependent."""
        inside = [DODGERS_LEADS] + [_speaking(f"c-{n}") for n in range(19)]
        inside += [_speaking(f"t-{n}") for n in range(5)]  # a tail to swap from
        out, meta = enforce_first_page_quality_floor(inside, first_page_size=20)
        assert meta["no_why_now_in_window"] == 1
        assert meta["demoted"] == 1
        assert out[0] is not DODGERS_LEADS

        # Slot 12: inside the twenty-card first page, outside clause (d)'s ten.
        outside = [_speaking(f"c-{n}") for n in range(12)]
        outside += [DODGERS_LEADS]
        outside += [_speaking(f"t-{n}") for n in range(10)]
        out, meta = enforce_first_page_quality_floor(outside, first_page_size=20)
        assert meta["no_why_now_in_window"] == 0
        assert meta["demoted"] == 0
        assert out[12] is DODGERS_LEADS

    def test_the_window_never_exceeds_the_page_it_governs(self):
        """At `limit=5` the first page IS five cards; a ten-slot clause would
        screen slots that do not exist."""
        items = [DODGERS_LEADS] + [_speaking(f"c-{n}") for n in range(9)]
        _, meta = enforce_first_page_quality_floor(items, first_page_size=5)
        assert meta["why_now_window"] == 5


class TestTheSwap:
    def test_the_replacement_must_itself_carry_a_why_now(self):
        """The bar is position-dependent, so the candidate list cannot be
        computed once. A reasonless tail card is not a legal replacement for a
        top-ten slot — swapping one for another would be a no-op that reported
        itself as a fix."""
        items = [DODGERS_LEADS] + [_speaking(f"c-{n}") for n in range(9)]
        items += [_mute(f"m-{n}") for n in range(5)]  # tail: speaks, no why-now
        items += [SPEAKING_TAIL_CARD]  # the only legal replacement

        out, meta = enforce_first_page_quality_floor(items, first_page_size=10)

        assert meta["demoted"] == 1
        assert out[0] is SPEAKING_TAIL_CARD
        assert meta["clean_replacements_available"] == 1

    def test_it_demotes_and_never_drops(self):
        """Ruling (d): named Alex exclusions are the only hard-drops."""
        items = [DODGERS_LEADS] + [_speaking(f"c-{n}") for n in range(11)]

        out, _ = enforce_first_page_quality_floor(items, first_page_size=10)

        assert len(out) == len(items)
        assert any(i is DODGERS_LEADS for i in out)

    def test_no_score_is_touched(self):
        items = [DODGERS_LEADS] + [_speaking(f"c-{n}") for n in range(11)]
        before = {id(i): i["score"] for i in items}

        out, _ = enforce_first_page_quality_floor(items, first_page_size=10)

        assert {id(i): i["score"] for i in out} == before

    def test_the_shortfall_is_loud(self):
        """gotcha #53 — a short page is a worse failure than a boring one, so
        the offender STAYS and the meta says so."""
        # Two offenders lead a window otherwise full of clean cards, and the
        # whole tail is reasonless — so there is nothing legal to swap in.
        items = [DODGERS_LEADS, BUNDLE_NO_WHY_NOW]
        items += [_speaking(f"c-{n}") for n in range(8)]
        items += [_mute(f"m-{n}") for n in range(4)]

        out, meta = enforce_first_page_quality_floor(items, first_page_size=10)

        assert meta["offenders_in_window"] == 2
        assert meta["demoted"] == 0
        assert meta["unreplaced"] == 2
        assert meta["clean_replacements_available"] == 0
        assert len(out) == len(items)

    def test_the_marquee_final_survives_a_page_of_offenders(self):
        """The collision CERT-2481 caught, at the level the reader experiences.

        A finished marquee final sits at slot 0 while clause (d) clears the rest
        of the window around it. It must still be at slot 0 afterwards.
        """
        items = [FINISHED_GAME] + [_mute(f"m-{n}") for n in range(9)]
        items += [_speaking(f"t-{n}") for n in range(9)]

        out, meta = enforce_first_page_quality_floor(items, first_page_size=10)

        assert out[0] is FINISHED_GAME
        assert meta["no_why_now_in_window"] == 9
        assert meta["demoted"] == 9

    def test_the_hook_only_card_yields_under_clause_d(self):
        """The other half of `test_the_hook_only_control_keeps_its_slot`.

        A hook is editorial framing ("As President Trump gears up…") — a "what".
        It makes the card audible, so #4695 leaves it alone; it names nothing
        that happened, so clause (d) takes the slot. Measured before shipping:
        of 120 served cards, 23 carried a hook and ZERO of them held a why-now
        marker the oracle misses, so this rule demotes no card that was telling
        the reader something timely (2026-09-10; re-measure before widening).
        """
        from tests.test_silent_first_page_cards_yield_the_slot_4695 import HOOK_ONLY

        items = [HOOK_ONLY] + [_speaking(f"c-{n}") for n in range(12)]

        out, meta = enforce_first_page_quality_floor(items, first_page_size=10)

        assert meta["silent_in_window"] == 0
        assert meta["no_why_now_in_window"] == 1
        assert out[0] is not HOOK_ONLY
