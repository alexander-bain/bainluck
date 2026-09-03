"""#2747 / ux/1036 — the hub's finished list stops blanking a prior it holds.

Alex, on the live US Open hub 2026-09-02: Shelton–Hurkacz shows no pre-match
number. It has one — ``opening_odds`` 68/32 from sportsbooks. His rule:
*"opening = Kalshi → Polymarket → sportsbook blend, labelled by source. Never
blank when any pre-match reading exists."*

ux/1034 A3 could not reach that number: ``opening_*`` is per-EVENT and the only
id-anchored path was ``event_links.by_matchup``, which covers only pairs the
register still carries a matchup for. Shelton–Hurkacz is keyed ``espn:182730``.
**#2693 step 2 built the channel** — ``Event.espn_id`` — and this is the rung
riding it.

Verified against production 2026-09-03: ``espn_id = '182730'`` resolves to event
15299858, Ben Shelton v Hubert Hurkacz, ``opening_home_probability = 0.6792``.
Those are the values below.
"""

from app.utils.tournament_slate import apply_books_prematch


SHELTON = "p:ben-shelton"
HURKACZ = "p:hubert-hurkacz"

# The production row `espn_id = '182730'` resolves to.
EVENT_15299858 = {
    "home_team_name": "Ben Shelton",
    "away_team_name": "Hubert Hurkacz",
    "opening_home_probability": 0.6792,
    "opening_away_probability": 0.3208,
}


def _results(**over):
    row = {
        "matchup_key": "espn:182730",
        "espn_competition_id": "182730",
        "players": [
            {"entity_key": SHELTON, "display_name": "Ben Shelton",
             "is_winner": True, "prematch_probability": None},
            {"entity_key": HURKACZ, "display_name": "Hubert Hurkacz",
             "is_winner": False, "prematch_probability": None},
        ],
        "winner_entity_key": SHELTON,
    }
    row.update(over.pop("row", {}))
    out = {"matches": [row], "count": 1, "with_prematch": 0}
    out.update(over)
    return out


def _apply(results):
    return apply_books_prematch(
        results,
        by_espn={"182730": 15299858},
        openings={15299858: EVENT_15299858},
    )


def _by_key(results):
    return {p["entity_key"]: p for p in results["matches"][0]["players"]}


def test_the_row_alex_read_shows_sixty_eight_percent_beside_shelton():
    """#2747's headline acceptance, on the numbers production actually holds."""
    players = _by_key(_apply(_results()))

    assert round(players[SHELTON]["prematch_probability"] * 100) == 68
    assert round(players[HURKACZ]["prematch_probability"] * 100) == 32


def test_it_is_labelled_as_a_sportsbook_opening_and_not_as_a_market_one():
    """Alex: labelled by source. "The market opened him at 68%" and "the books
    opened him at 68%" are different claims, and ux/1034 A3 is the standing
    lesson about printing the second as the first on this exact list."""
    players = _by_key(_apply(_results()))

    assert players[SHELTON]["prematch_source"] == "books"
    assert players[HURKACZ]["prematch_source"] == "books"


def test_a_kalshi_prior_is_never_displaced_by_the_books_one():
    """The ladder is ordered, not merged. A row that already has an upper rung
    is untouched — including its source label."""
    results = _results(row={"players": [
        {"entity_key": SHELTON, "display_name": "Ben Shelton", "is_winner": True,
         "prematch_probability": 0.55, "prematch_source": "kalshi"},
        {"entity_key": HURKACZ, "display_name": "Hubert Hurkacz", "is_winner": False,
         "prematch_probability": 0.45, "prematch_source": "kalshi"},
    ]})

    players = _by_key(_apply(results))

    assert players[SHELTON]["prematch_probability"] == 0.55
    assert players[SHELTON]["prematch_source"] == "kalshi"


def test_the_orientation_is_refused_rather_than_guessed():
    """THE ONE THING THIS FUNCTION MUST NEVER DO is put 68% on the wrong player
    — wrong in the most confident possible way, and it looks right. If the two
    event names do not land on the two players one each, the column stays empty."""
    stranger = dict(EVENT_15299858, away_team_name="Somebody Else")

    results = apply_books_prematch(
        _results(), by_espn={"182730": 15299858}, openings={15299858: stranger}
    )

    players = _by_key(results)
    assert players[SHELTON]["prematch_probability"] is None
    assert players[HURKACZ]["prematch_probability"] is None


def test_the_benign_name_variants_are_matched_and_not_refused():
    """`names_agree`, not `espn_tennis.normalize_name`.

    The strict normalizer concatenates, so it calls `Shang Juncheng` and
    `Juncheng Shang` two different people. Measured over the served payload
    2026-09-03 that one choice refused 7 of the 63 linkable rows, every one a
    benign variant — and a false disagreement here DELETES A REAL PRIOR from the
    card. All three shapes, from that measurement:
    """
    variants = [
        # reversed word order
        ("Zhang Shuai", "Leylah Fernandez", "Shuai Zhang", "Leylah Fernandez"),
        # dropped second surname
        ("Daniel Merida", "Andrey Rublev", "Daniel Merida Aguilar", "Andrey Rublev"),
        # reversed order again, other draw
        ("Wang Xiyu", "Iga Swiatek", "Xiyu Wang", "Iga Swiatek"),
    ]
    for ours_home, ours_away, event_home, event_away in variants:
        results = {
            "matches": [{
                "espn_competition_id": "1",
                "players": [
                    {"entity_key": "a", "display_name": ours_home, "prematch_probability": None},
                    {"entity_key": "b", "display_name": ours_away, "prematch_probability": None},
                ],
            }],
            "count": 1,
        }
        apply_books_prematch(
            results,
            by_espn={"1": 9},
            openings={9: {
                "home_team_name": event_home, "away_team_name": event_away,
                "opening_home_probability": 0.65, "opening_away_probability": 0.35,
            }},
        )
        players = {p["display_name"]: p for p in results["matches"][0]["players"]}
        assert players[ours_home]["prematch_probability"] == 0.65, ours_home
        assert players[ours_away]["prematch_probability"] == 0.35, ours_away


def test_two_players_sharing_a_surname_are_still_refused():
    """The tolerance above must not become a wildcard. `names_agree`'s own sweep
    keeps this strict, and this asserts the strictness survives at THIS call
    site, where the failure mode is a number on the wrong player."""
    results = {
        "matches": [{
            "espn_competition_id": "1",
            "players": [
                {"entity_key": "a", "display_name": "Francisco Cerundolo", "prematch_probability": None},
                {"entity_key": "b", "display_name": "Juan Manuel Cerundolo", "prematch_probability": None},
            ],
        }],
        "count": 1,
    }
    apply_books_prematch(
        results,
        by_espn={"1": 9},
        openings={9: {
            # An event naming only the surname cannot say WHICH Cerundolo.
            "home_team_name": "Cerundolo", "away_team_name": "Cerundolo",
            "opening_home_probability": 0.65, "opening_away_probability": 0.35,
        }},
    )
    assert all(
        p["prematch_probability"] is None
        for p in results["matches"][0]["players"]
    )


def test_a_row_with_no_espn_link_is_left_alone():
    """The channel is id-anchored or it is nothing. No link, no number — the
    empty space ux/1034 A3 made honest stays honest."""
    results = apply_books_prematch(_results(), by_espn={}, openings={})

    assert _by_key(results)[SHELTON]["prematch_probability"] is None


def test_an_event_with_no_opening_yields_nothing():
    """"We hold the fixture and caught no opening" is a real state and the
    footnote counts it. It must not become a fabricated number."""
    blank = dict(EVENT_15299858, opening_home_probability=None,
                 opening_away_probability=None)

    results = apply_books_prematch(
        _results(), by_espn={"182730": 15299858}, openings={15299858: blank}
    )

    assert _by_key(results)[SHELTON]["prematch_probability"] is None


def test_a_settled_price_that_leaked_into_the_opening_column_is_refused():
    """1.0 is the result read back, not a forecast. Shared with the game cards:
    this goes through `resolve_prematch_reading`, not a local float cast."""
    settled = dict(EVENT_15299858, opening_home_probability=1.0,
                   opening_away_probability=0.0)

    results = apply_books_prematch(
        _results(), by_espn={"182730": 15299858}, openings={15299858: settled}
    )

    assert _by_key(results)[SHELTON]["prematch_probability"] is None


def test_the_counts_the_footnote_prints_are_kept_true():
    """`with_prematch` drives "shown on N of M", and a books rung that filled a
    row without incrementing it would make the page understate itself. The books
    count is named separately because the label's question — how many of these
    are a sportsbook median — cannot be answered from a total."""
    results = _apply(_results())

    assert results["with_prematch"] == 1
    assert results["with_prematch_books"] == 1
