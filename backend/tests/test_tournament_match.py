"""Guards for the match detail page (UX-P149).

The suite is organised around the ONE thing on this surface that is inferred
rather than pinned — which player is a Polymarket sub-market's ``Yes`` — and
around the refusals that bound it.  Everything else here is arithmetic and
copy, and it is tested because copy on this page is load-bearing (the design
bar is "legible next to the match probabilities, jargon-free, *probability*
never *price*").

``test_the_yes_side_rule_holds_on_every_register_pin`` is the important one.
It replays the attribution rule against a committed capture of the real
Polymarket titles for the 28 matchups the register pins — the one market class
where the answer is independently known, because the register established it
offline from the source's own ordered labels.  If Polymarket ever stops putting
the ``Yes`` player first, that test goes red on real data rather than the page
quietly printing a number under the wrong name.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.tournament_match import (
    attribute_yes_side,
    build_match_detail,
    build_prop,
    classify_prop,
    group_ladders,
    handicap_label,
    name_tokens,
    threshold_labels,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "usopen_match_titles_2026-08-28.json"
)
NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
FRESH = NOW - timedelta(minutes=20)


@pytest.fixture(scope="module")
def titles() -> dict:
    return json.loads(FIXTURE.read_text())


# ───────────────────────── the inferred rule ─────────────────────────


def test_the_yes_side_rule_holds_on_every_register_pin(titles):
    """28 of 28, on real titles, against independently-pinned truth.

    This is the measurement the whole surface rests on, kept executable. The
    register's ``sides`` map was built offline from Polymarket's own ordered
    labels, so ``yes_entity_key`` here is not this rule's own output — it is a
    second, better source for the same fact, and the test asserts they agree.
    """
    pins = titles["winner_pins"]
    assert len(pins) >= 28, "the capture lost rows; re-capture before trusting this"

    violations = []
    for pin in pins:
        yes_key, no_key, refusal = attribute_yes_side(pin["title"], pin["players"])
        if refusal is not None or yes_key != pin["yes_entity_key"] or no_key != pin["no_entity_key"]:
            violations.append((pin["title"], yes_key, pin["yes_entity_key"], refusal))
    assert violations == []


def test_every_real_prop_title_attributes_or_refuses_cleanly(titles):
    """No prop title may attribute BOTH players to the same position.

    205 real titles. The rule is allowed to refuse any of them; it is not
    allowed to return a key that is not one of the two registered players, and
    it is not allowed to return the same player twice.
    """
    for prop in titles["prop_titles"]:
        keys = {p["entity_key"] for p in prop["players"]}
        yes_key, no_key, refusal = attribute_yes_side(prop["title"], prop["players"])
        if refusal is not None:
            assert yes_key is None and no_key is None
            continue
        assert yes_key in keys and no_key in keys
        assert yes_key != no_key


def test_no_real_prop_title_is_refused_today(titles):
    """The refusal path is a guard, not the normal case.

    A rule that refuses everything is trivially safe and ships an empty page.
    Measured at capture: 0 of 205 titles refused. If a change makes the rule
    stricter, this is where the cost shows up.
    """
    refused = [
        prop["title"]
        for prop in titles["prop_titles"]
        if attribute_yes_side(prop["title"], prop["players"])[2] is not None
    ]
    assert refused == []


def test_it_reads_the_props_own_title_not_the_winner_markets():
    """Five real Set Handicap titles name the players in the opposite order.

    Inheriting the winner market's order would have mis-attributed every one of
    them — the favoured side goes first in a handicap. This is the specimen,
    from production: the winner market is "Priscilla Hon vs Joanna Garland" and
    the handicap is "Set Handicap: Garland (-1.5) vs Hon (+1.5)".
    """
    players = [
        {"entity_key": "priscilla-hon", "display_name": "Priscilla Hon"},
        {"entity_key": "joanna-garland", "display_name": "Joanna Garland"},
    ]
    winner = attribute_yes_side(
        "US Open, Qualification WTA: Priscilla Hon vs Joanna Garland", players
    )
    handicap = attribute_yes_side(
        "Set Handicap: Garland (-1.5) vs Hon (+1.5)", players
    )
    assert winner[0] == "priscilla-hon"
    assert handicap[0] == "joanna-garland"


def test_a_shared_surname_refuses_rather_than_picking_one():
    players = [
        {"entity_key": "maria-sanchez", "display_name": "Maria Sanchez"},
        {"entity_key": "ana-sanchez", "display_name": "Ana Sanchez"},
    ]
    yes_key, no_key, refusal = attribute_yes_side(
        "Set 1 Winner: Sanchez vs Sanchez", players
    )
    assert (yes_key, no_key) == (None, None)
    assert refusal == "PLAYER_NOT_IN_TITLE"


def test_a_player_missing_from_the_title_refuses():
    players = [
        {"entity_key": "a-one", "display_name": "Aziz Dougaz"},
        {"entity_key": "b-two", "display_name": "Andrea Guerrieri"},
    ]
    assert attribute_yes_side("Set 1 Winner: Dougaz vs Someone", players)[2] == (
        "PLAYER_NOT_IN_TITLE"
    )


def test_accented_spellings_still_match():
    players = [
        {"entity_key": "a", "display_name": "Darja Semeništaja"},
        {"entity_key": "b", "display_name": "Alexandra Shubladze"},
    ]
    assert attribute_yes_side("Set 1 Winner: Semenistaja vs Shubladze", players)[0] == "a"


def test_two_letter_surnames_are_findable():
    """`Ku` was refused by a three-character floor and is not any more."""
    players = [
        {"entity_key": "yeon-woo-ku", "display_name": "Yeon-Woo Ku"},
        {"entity_key": "storm-hunter", "display_name": "Storm Hunter"},
    ]
    assert attribute_yes_side("Set 1 Winner: Ku vs Hunter", players)[0] == "yeon-woo-ku"


def test_title_vocabulary_is_never_treated_as_a_name():
    assert "vs" not in name_tokens("Set vs Match")
    assert "set" not in name_tokens("Set Winner")
    assert "dougaz" in name_tokens("Aziz Dougaz")


# ───────────────────────── the questions ─────────────────────────


@pytest.mark.parametrize(
    "title,family,question",
    [
        ("Set 1 Winner: Dougaz vs Guerrieri", "set_winner", "Who wins set 1"),
        ("Set 2 Winner: Dougaz vs Guerrieri", "set_winner", "Who wins set 2"),
        ("Dougaz vs. Guerrieri: Match O/U 22.5", "total", "Total games in the match"),
        (
            "Aziz Dougaz vs. Andrea Guerrieri: Total Sets O/U 2.5",
            "total",
            "Total sets in the match",
        ),
        ("Dougaz vs. Guerrieri: Set 1 Games O/U 9.5", "total", "Games in set 1"),
        (
            "Set Handicap: Dougaz (-1.5) vs Guerrieri (+1.5)",
            "handicap",
            "Winning margin, in sets",
        ),
        (
            "Game Spread: Dougaz (-0.5) vs Guerrieri (+0.5)",
            "handicap",
            "Winning margin, in games",
        ),
    ],
)
def test_real_titles_become_plain_questions(title, family, question):
    shape = classify_prop(title)
    assert shape["family"] == family
    assert shape["question"] == question


def test_every_captured_prop_title_is_classified(titles):
    """No real title may fall through to the source's own wording today.

    The ``other`` family exists so an unknown market still renders; a title in
    the measured corpus landing there means a family regressed.
    """
    unclassified = sorted(
        {
            prop["title"]
            for prop in titles["prop_titles"]
            if classify_prop(prop["title"])["family"] == "other"
        }
    )
    assert unclassified == []


def test_no_user_facing_question_says_price_or_odds(titles):
    """UX-P146's product-wide ruling, enforced where the copy is generated."""
    banned = ("price", "odds", "o/u", "handicap", "spread", "line")
    for prop in titles["prop_titles"]:
        question = classify_prop(prop["title"])["question"].lower()
        for word in banned:
            assert word not in question, f"{question!r} carries {word!r}"


def test_threshold_labels_are_exact_english():
    assert threshold_labels(22.5, "game") == (
        "More than 22 games",
        "22 games or fewer",
    )
    assert threshold_labels(2.5, "set") == ("More than 2 sets", "2 sets or fewer")
    assert threshold_labels(1.5, "set") == ("More than 1 set", "1 set or fewer")


def test_a_whole_number_line_is_refused_not_rounded():
    """An integer line can push, so its two sides are not complements."""
    assert threshold_labels(22.0, "game") is None


def test_handicap_labels_read_as_sentences():
    assert handicap_label("Dougaz", 1.5, "set") == "Dougaz by 2 sets or more"
    assert handicap_label("Dougaz", 0.5, "game") == "Dougaz wins more games"
    assert handicap_label("Dougaz", 3.5, "game") == "Dougaz by 4 games or more"


# ───────────────────────── the cards ─────────────────────────


def _market(market_id, name, yes_p, no_p, *, open_yes=None, open_no=None, observed=FRESH):
    outcomes = [
        {"outcome_id": market_id * 10 + 1, "name": "Yes", "external_id": "0xabc_yes"},
        {"outcome_id": market_id * 10 + 2, "name": "No", "external_id": "0xabc_no"},
    ]
    prices = {
        market_id * 10 + 1: {
            "probability": yes_p,
            "opening_probability": open_yes,
            "observed_at": observed,
        },
        market_id * 10 + 2: {
            "probability": no_p,
            "opening_probability": open_no,
            "observed_at": observed,
        },
    }
    return {"market_id": market_id, "name": name, "outcomes": outcomes}, prices


PLAYERS = [
    {"entity_key": "aziz-dougaz", "display_name": "Aziz Dougaz"},
    {"entity_key": "andrea-guerrieri", "display_name": "Andrea Guerrieri"},
]


def test_a_duel_prop_names_the_players_never_yes_and_no():
    market, prices = _market(1, "Set 1 Winner: Dougaz vs Guerrieri", 0.53, 0.47)
    prop, refusal = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert refusal is None
    labels = [answer["label"] for answer in prop["answers"]]
    assert labels == ["Aziz Dougaz", "Andrea Guerrieri"]
    assert "Yes" not in labels and "No" not in labels
    assert prop["answers"][0]["entity_key"] == "aziz-dougaz"


def test_an_incoherent_pair_prints_no_number():
    """0.90 + 0.60 is two stale readings, not a 60/40 (gotcha #23)."""
    market, prices = _market(2, "Set 1 Winner: Dougaz vs Guerrieri", 0.90, 0.60)
    prop, _ = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert prop["coherent"] is False
    assert [answer["probability"] for answer in prop["answers"]] == [None, None]


def test_an_unpriced_prop_still_renders():
    """lane1's caveat: a leg can be untradeable beside a priced sibling."""
    market, prices = _market(3, "Set 1 Winner: Dougaz vs Guerrieri", None, None)
    prop, refusal = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert refusal is None
    assert prop["price_state"] == "unpriced"
    assert prop["answers"][0]["probability"] is None
    assert prop["answers"][0]["label"] == "Aziz Dougaz"


def test_a_handicap_with_the_plus_first_is_refused():
    market, prices = _market(4, "Set Handicap: Dougaz (+1.5) vs Guerrieri (-1.5)", 0.34, 0.66)
    prop, refusal = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert prop is None
    assert refusal == "HANDICAP_SIDE_UNCLEAR"


def test_a_handicap_reads_as_a_margin_sentence():
    market, prices = _market(5, "Set Handicap: Dougaz (-1.5) vs Guerrieri (+1.5)", 0.34, 0.66)
    prop, _ = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert [answer["label"] for answer in prop["answers"]] == [
        "Aziz Dougaz by 2 sets or more",
        "Anything else",
    ]


def test_a_threshold_needs_no_player_at_all():
    market, prices = _market(6, "Dougaz vs. Guerrieri: Match O/U 22.5", 0.485, 0.515)
    prop, _ = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert [answer["label"] for answer in prop["answers"]] == [
        "More than 22 games",
        "22 games or fewer",
    ]
    assert all(answer["entity_key"] is None for answer in prop["answers"])


def test_the_opening_pair_is_normalized_on_its_own_sum():
    market, prices = _market(
        7, "Set 1 Winner: Dougaz vs Guerrieri", 0.53, 0.47, open_yes=0.51, open_no=0.51
    )
    prop, _ = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert prop["opening_coherent"] is True
    assert prop["answers"][0]["opening_probability"] == pytest.approx(0.5)
    assert prop["opening_raw_sum"] == pytest.approx(1.02)


def test_a_cards_freshness_is_the_and_over_its_legs():
    """One live leg may not make a card live (UX-P135, CERT-411 round 2)."""
    market, prices = _market(8, "Set 1 Winner: Dougaz vs Guerrieri", 0.53, 0.47)
    prices[82]["observed_at"] = NOW - timedelta(days=6)
    prop, _ = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert prop["price_state"] == "dark"
    assert prop["probability_is_live"] is False
    assert prop["mixed_freshness"] is True


# ───────────────────────── the ladder ─────────────────────────


def test_three_strikes_collapse_into_one_card():
    props = []
    prices: dict = {}
    for index, (line, over) in enumerate([(21.5, 0.55), (22.5, 0.485), (23.5, 0.43)]):
        market, chunk = _market(
            20 + index, f"Dougaz vs. Guerrieri: Match O/U {line}", over, 1 - over
        )
        prices.update(chunk)
        prop, _ = build_prop(market, players=PLAYERS, prices=chunk, now=NOW)
        props.append(prop)

    cards = group_ladders(props)
    assert len(cards) == 1
    card = cards[0]
    assert card["kind"] == "ladder"
    assert [answer["label"] for answer in card["answers"]] == [
        "More than 21 games",
        "More than 22 games",
        "More than 23 games",
    ]
    # Ascending line order, so the numbers fall down the card. A ladder whose
    # probabilities do not descend is a data problem the reader can see.
    values = [answer["probability"] for answer in card["answers"]]
    assert values == sorted(values, reverse=True)
    assert len(card["market_ids"]) == 3


def test_a_single_strike_keeps_both_sides():
    market, prices = _market(30, "Dougaz vs. Guerrieri: Total Sets O/U 2.5", 0.405, 0.595)
    prop, _ = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    cards = group_ladders([prop])
    assert len(cards) == 1
    assert len(cards[0]["answers"]) == 2
    assert cards[0]["kind"] == "threshold"


def test_cards_are_ordered_match_question_first():
    built = []
    prices: dict = {}
    for index, name in enumerate([
        "Dougaz vs. Guerrieri: Match O/U 22.5",
        "Set Handicap: Dougaz (-1.5) vs Guerrieri (+1.5)",
        "Set 1 Winner: Dougaz vs Guerrieri",
    ]):
        market, chunk = _market(40 + index, name, 0.5, 0.5)
        prices.update(chunk)
        prop, _ = build_prop(market, players=PLAYERS, prices=chunk, now=NOW)
        built.append(prop)
    assert [card["family"] for card in group_ladders(built)] == [
        "set_winner",
        "handicap",
        "total",
    ]


# ───────────────────────── the page ─────────────────────────


REGISTER = {
    "schema_version": "tournament-register/v1",
    "tournament": "us-open",
    "season": "2026",
    "version": 1,
    "generated_at": "2026-08-28T00:00:00Z",
    "draw_released": True,
    "players": [
        {
            "entity_key": "aziz-dougaz",
            "display_name": "Aziz Dougaz",
            "draw": "mens-singles",
            "role": "participant",
            "seed": None,
            "country": "TUN",
        },
        {
            "entity_key": "andrea-guerrieri",
            "display_name": "Andrea Guerrieri",
            "draw": "mens-singles",
            "role": "participant",
            "seed": None,
            "country": "ITA",
        },
    ],
    "matchups": [
        {
            "matchup_key": "mens-singles:aziz-dougaz-vs-andrea-guerrieri:2026-08-27",
            "draw": "mens-singles",
            "round": "qualifying",
            "scheduled_date": "2026-08-27T23:05:00Z",
            "players": ["aziz-dougaz", "andrea-guerrieri"],
            "sources": [
                {
                    "source": "polymarket",
                    "kind": "match",
                    "market_id": 900,
                    "outcome_id": 9001,
                    "status": "live",
                    "sides": {
                        "aziz-dougaz": {
                            "outcome_id": 9001,
                            "outcome_external_id": "0xwin_yes",
                            "source_label": "Aziz Dougaz",
                        },
                        "andrea-guerrieri": {
                            "outcome_id": 9002,
                            "outcome_external_id": "0xwin_no",
                            "source_label": "Andrea Guerrieri",
                        },
                    },
                }
            ],
        }
    ],
    "props": [],
    "reaches": [],
    "broadcasts": [],
}

MATCH_KEY = "mens-singles:aziz-dougaz-vs-andrea-guerrieri:2026-08-27"


def _page(prop_markets=None, prices=None, result=None):
    base = {
        9001: {"probability": 0.535, "opening_probability": 0.52, "observed_at": FRESH},
        9002: {"probability": 0.465, "opening_probability": 0.48, "observed_at": FRESH},
    }
    base.update(prices or {})
    return build_match_detail(
        REGISTER,
        MATCH_KEY,
        prop_markets=prop_markets or [],
        prices=base,
        result=result,
        now=NOW,
    )


def test_an_unknown_matchup_key_is_none_never_a_nearest_match():
    assert build_match_detail(
        REGISTER, "mens-singles:someone-vs-nobody:2026-08-27",
        prop_markets=[], prices={}, result=None, now=NOW,
    ) is None


def test_the_hero_is_the_match_winner_market():
    page = _page()
    assert page["match"]["matchup_key"] == MATCH_KEY
    assert page["match"]["coherent"] is True
    assert [side["display_name"] for side in page["match"]["sides"]] == [
        "Aziz Dougaz",
        "Andrea Guerrieri",
    ]


def test_a_started_match_still_has_a_page():
    """`build_slate` drops it; a page ABOUT one fixture must not.

    The registered start is 2026-08-27 and `NOW` is a day later, which is well
    past the slate's six-hour window. If this ever 404s, every finished match
    on the tournament loses its page at the exact moment its result exists.
    """
    assert _page() is not None


def test_props_hang_off_the_match_and_are_counted():
    markets = []
    prices: dict = {}
    for index, name in enumerate([
        "Set 1 Winner: Dougaz vs Guerrieri",
        "Dougaz vs. Guerrieri: Match O/U 22.5",
    ]):
        market, chunk = _market(50 + index, name, 0.5, 0.5)
        markets.append(market)
        prices.update(chunk)
    page = _page(prop_markets=markets, prices=prices)
    assert page["props_count"] == 2
    assert page["props_dropped"] == {}


def test_refusals_are_counted_never_silent():
    market, prices = _market(60, "Set 1 Winner: Nobody vs Nobodyelse", 0.5, 0.5)
    page = _page(prop_markets=[market], prices=prices)
    assert page["props_count"] == 0
    assert page["props_dropped"] == {"PLAYER_NOT_IN_TITLE": 1}


def test_decided_is_espns_verdict_not_the_clock():
    assert _page()["decided"] is False
    assert _page(result={"score": "4-6, 6-4", "completion": "final"})["decided"] is True


def test_an_unknown_market_with_yes_no_sides_is_refused_not_printed():
    """The seam stays open; the jargon does not come through it.

    An unrecognised family is allowed to render under the source's own title —
    a page that omits a question because nobody wrote a sentence for it is
    quietly incomplete. But `Yes 53%` under that title is the register's first
    refusal ("never print Yes/No") reappearing one market class along, so a
    card whose sides are the source's structural words is dropped and counted.
    """
    market, prices = _market(70, "Coin Toss: Dougaz vs Guerrieri", 0.5, 0.5)
    prop, refusal = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert prop is None
    assert refusal == "UNREADABLE_SIDES"


def test_an_unknown_market_with_readable_sides_still_renders():
    market, prices = _market(71, "Coin Toss: Dougaz vs Guerrieri", 0.5, 0.5)
    market["outcomes"][0]["name"] = "Heads"
    market["outcomes"][1]["name"] = "Tails"
    prop, refusal = build_prop(market, players=PLAYERS, prices=prices, now=NOW)
    assert refusal is None
    assert [answer["label"] for answer in prop["answers"]] == ["Heads", "Tails"]
    assert prop["question"] == "Coin Toss: Dougaz vs Guerrieri"
