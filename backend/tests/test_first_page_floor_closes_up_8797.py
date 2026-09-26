"""#8797 — a page-one vacancy is filled from page one first, never by the tail.

`enforce_first_page_quality_floor` swaps every page-one offender (ladder,
silent card, or — inside the first ten — a card naming no why-now) out of the
page. Until #8797 the replacement was the first clean card from BEYOND page one,
dropped into the offender's exact slot. The tail is by construction the weakest
clean supply in the pool, so the best card from past slot twenty outranked every
clean card already on page one.

Production, 2026-09-26 04:35Z (anonymous `GET /api/feed`, cache miss): the
standing-leader card "J.D. Vance leads at 20%" (2028 winner, 95) yielded its
slot, and a 49-point esports LAN — "Chicken Coop 86%", one source, low
confidence — took slot 5, with a 45-point Obamacare card at 6, above Brazil,
China/Taiwan and the Iran ceasefire (95 each). The card texts below are
verbatim from that response, trimmed to the fields the floor reads.
"""

from app.utils.feed_market_quality import enforce_first_page_quality_floor


def _futures(name: str, score: int, headline: str, reason: str, context: str) -> dict:
    return {
        "type": "futures",
        "score": score,
        "headline": headline,
        "reason": reason,
        "context_summary": context,
        "data": {"name": name, "hook_description": None, "status": "open"},
    }


def _live_game(name: str) -> dict:
    return {
        "type": "event",
        "score": 35,
        "headline": "Live",
        "reason": "",
        "context_summary": None,
        "data": {"name": name, "status": "live"},
    }


def _scheduled_game(name: str) -> dict:
    """A game card that is NOT an anchor and names no why-now of its own."""
    return {
        "type": "event",
        "score": 70,
        "headline": None,
        "reason": "",
        "context_summary": None,
        "data": {"name": name, "status": "scheduled"},
    }


def _filler(key: str) -> dict:
    return _futures(
        f"Market {key}",
        90,
        f"Down 3 points since Sep {key}",
        f"Market {key}: 40% chance, down 3 points since Sep {key}",
        f"40% chance, down 3 points since Sep {key}",
    )


MLB_WS = _futures(
    "MLB World Series Winner",
    95,
    "Los Angeles Dodgers lead at 27%, Milwaukee Brewers up 11 points since Feb 2",
    "Milwaukee Brewers is up 11 points since Feb 2 in MLB World Series Winner",
    "Los Angeles Dodgers lead at 27%, Milwaukee Brewers up 11 points since Feb 2",
)
#: The offender: it speaks, and what it says is a standing fact.
US_2028 = _futures(
    "2028 U.S. Presidential Election winner?",
    95,
    "J.D. Vance leads at 20%",
    "J.D. Vance (20%) leads 2028 U.S. Presidential Election winner?",
    "J.D. Vance leads at 20%",
)
BRAZIL = _futures(
    "Brazil Presidential Election",
    95,
    "Flávio Bolsonaro leads; resolves within a month",
    "Brazil Presidential Election resolves within a month, Flávio Bolsonaro leads at 56%",
    "Flávio Bolsonaro leads at 56%; resolves within a month",
)
CHINA = _futures(
    "Will China invade Taiwan by end of 2026?",
    95,
    "Down 8 points since Feb 18",
    "Will China invade Taiwan by end of 2026: 4% chance, down 8 points since Feb 18",
    "4% chance, down 8 points since Feb 18",
)
IRAN = _futures(
    "US x Iran ceasefire continues through October 31?",
    95,
    "Down 19.5 points since Sep 17",
    "US x Iran ceasefire continues through October 31: 54% chance, down 19.5 points since Sep 17",
    "54% chance, down 19.5 points since Sep 17",
)
#: The tail's first clean card — the one that took slot 5.
ESPORTS_LAN = _futures(
    "iBUYPOWER Masters fl0m's Mythical LAN: Winner",
    49,
    "Resolving within a week",
    "iBUYPOWER Masters fl0m's Mythical LAN: Winner: 86% chance, resolving within a week",
    "86% chance, resolving within a week",
)
OBAMACARE = _futures(
    "Will Trump issue Obamacare rebates before Election Day?",
    45,
    "Down 4 points since Sep 9",
    "Will Trump issue Obamacare rebates before Election Day: 59% chance, down 4 points since Sep 9",
    "59% chance, down 4 points since Sep 9",
)

LEAD = [
    _live_game("Houston Astros @ Athletics"),
    _live_game("Brisbane Lions @ Fremantle Dockers"),
    _live_game("Clemson Tigers @ California Golden Bears"),
]


def _production_page() -> list[dict]:
    page = LEAD + [MLB_WS, US_2028, BRAZIL, CHINA, IRAN]
    page += [_filler(str(n)) for n in range(1, 13)]  # slots 8..19
    assert len(page) == 20
    return page + [ESPORTS_LAN, OBAMACARE] + [_filler(f"t{n}") for n in range(3)]


def _run(items: list[dict]):
    return enforce_first_page_quality_floor(items, first_page_size=20, why_now_window=10)


class TestTheProductionPage:
    def test_the_specimen_is_an_offender_and_the_tail_card_is_clean(self):
        # A fixture in which nothing yields proves nothing about where the
        # replacement goes.
        _out, meta = _run(_production_page())
        assert meta["offenders_in_window"] == 1
        assert meta["no_why_now_in_window"] == 1
        assert meta["demoted"] == 1
        assert meta["unreplaced"] == 0

    def test_the_weak_tail_card_does_not_reach_the_first_ten(self):
        out, _ = _run(_production_page())
        top_ten = [c["data"]["name"] for c in out[:10]]
        assert ESPORTS_LAN["data"]["name"] not in top_ten
        assert OBAMACARE["data"]["name"] not in top_ten

    def test_page_one_closes_up_over_the_vacancy(self):
        items = _production_page()
        out, _ = _run(items)
        # The three 95-point stories each move up one slot…
        assert out[4] is BRAZIL
        assert out[5] is CHINA
        assert out[6] is IRAN
        # …and the tail card enters at the bottom of page one.
        assert out[19] is ESPORTS_LAN
        assert out[:19] == items[:4] + items[5:20]

    def test_the_old_pairing_is_not_what_ships(self):
        # Strawman: the pre-#8797 swap, spelled out. If this ever equals the
        # served order again, the tail is outranking page one again.
        items = _production_page()
        old = list(items)
        old[4], old[20] = old[20], old[4]
        out, _ = _run(items)
        assert out != old
        assert old[4] is ESPORTS_LAN  # the strawman really is the defect

    def test_the_offender_is_demoted_not_dropped_and_no_score_moves(self):
        items = _production_page()
        before = {id(c): c["score"] for c in items}
        out, _ = _run(items)
        assert len(out) == len(items)
        assert sorted(map(id, out)) == sorted(map(id, items))
        assert all(c is not US_2028 for c in out[:20])
        assert {id(c): c["score"] for c in out} == before

    def test_the_lead_prefix_is_untouched(self):
        out, _ = _run(_production_page())
        assert out[:3] == LEAD


class TestWhatMayClimb:
    def test_an_anchor_further_down_is_never_lifted(self):
        """A live game's slot is somebody else's guarantee."""
        items = _production_page()
        anchor = _live_game("Kansas City Royals @ Seattle Mariners")
        items[5] = anchor  # directly beneath the vacancy
        out, _ = _run(items)
        assert out[5] is anchor
        assert out[4] is CHINA  # the climb skips over it

    def test_a_game_card_does_not_climb_into_a_why_now_vacancy(self):
        """A card lifted into a freed slot clears the promotion bar
        (`_is_reasonless`, type-agnostic): a slot freed for naming no reason is
        not filled by another card that names none."""
        items = _production_page()
        game = _scheduled_game("Washington Capitals @ Boston Bruins")
        items[5] = game
        out, _ = _run(items)
        assert out[4] is CHINA
        assert game in out[:20]

    def test_a_reasonless_card_below_slot_ten_is_not_pulled_above_it(self):
        items = _production_page()
        mute = _futures(
            "NFL Super Bowl Winner", 95,
            "Los Angeles Rams lead at 12%",
            "Los Angeles Rams (12%) leads NFL Super Bowl Winner",
            "Los Angeles Rams lead at 12%",
        )
        items[12] = mute
        out, meta = _run(items)
        assert meta["offenders_in_window"] == 1  # slot 12 is outside the ten
        assert out.index(mute) >= 10


class TestTheShortfallLeavesThePageAlone:
    def test_no_clean_tail_card_means_no_chain_moves(self):
        """gotcha #53: when the last opening cannot be filled, the offender
        stays AND nothing above it was shuffled on the way."""
        page = _production_page()[:20]
        tail = [
            dict(_filler(f"q{n}"), _quality_class="low_quality") for n in range(3)
        ]
        items = page + tail
        out, meta = _run(items)
        assert meta["demoted"] == 0
        assert meta["unreplaced"] == 1
        assert out == items
