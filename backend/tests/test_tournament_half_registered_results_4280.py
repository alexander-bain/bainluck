"""A REGISTERED PLAYER'S OWN RESULT STOPS DISAPPEARING BECAUSE OF THEIR OPPONENT.

live/121 · #4280 · PILLAR: TRUTH · SHIP: Swiatek's round of 16, Keys' third
round, Medvedev's and Paul's first rounds appear in the US Open finished list
instead of being dropped for the name on the other side of the net.

═══ WHAT WAS MEASURED ═══

Replayed through this repo's own reader against the live ESPN board on
2026-09-09 14:47Z (both tours, 625 competitions, 601 scored), joined against the
committed `us-open` 2026 register (378 players, singles only)::

    joined, both sides registered                 321
    dropped in a REGISTERED draw                  147   <- `unregistered_pairs`
      ... of those, exactly ONE side resolves     114
      ... of those, in the MAIN draw               19
      ... neither side resolves                    33
    rows built from the scoreboard alone (#4124)  137   all doubles

So the 147 was two populations under one name. The 33 are matches between two
people the register has never heard of; the 114 are matches we hold one side of
and lost anyway. The 19 main-draw ones are the reader-visible harm, and they
concentrate on ELEVEN unresolvable names — four are register players ESPN spells
differently (`Zheng Qinwen` for `Qinwen Zheng`, `Bu Yunchaokete` for
`Yunchaokete Bu`, `Chak Lam Coleman Wong` for `Coleman Wong`, `Tomas Barrios
Vera` for `Tomas Barrios`) and seven are real main-draw entrants the register
does not carry at all, including Arthur Gea, who reached the round of 16.

Those two causes are NOT what this ship fixes and must not be confused with it:
they are a name/id channel between the register and ESPN, which is matching, and
matching is lane1's under D35. This ship fixes the third thing — that either
cause cost us the OTHER player's row as well.

═══ WHAT THIS FILE GUARDS ═══

The ship: a decided match with one registered side is published with that side
pinned and the other named by the scoreboard (`source_pairing: "mixed"`).

The controls are as load-bearing as the ship, because this branch widens a list
Alex reads every morning and the strictness it relaxes exists for a real reason:

* ``test_a_match_with_neither_side_registered_is_still_dropped`` — the branch
  must open for ONE resolved side and not for zero. Without it the 33 come in
  too, under two names we cannot stand behind.
* ``test_a_half_row_is_refused_when_the_scoreboard_did_not_identify_the_other``
  — an unheld side with no ESPN identity is not "a player we lack", it is an
  unnamed side, and a score against nobody is the defect the strictness exists
  for. Same refusal `_scoreboard_result_row` already makes.
* ``test_a_half_row_is_refused_when_the_winner_matches_neither_side`` — the drop
  the registered path already makes, still made here.
* ``test_a_half_row_never_carries_a_pre_match_probability`` — the prior is keyed
  on the two REGISTER keys, so a half row has none to look up; printing the
  pinned side's alone would answer a two-sided question with one number.
* ``test_the_image_coverage_gate_counts_the_one_pinned_slot`` — ruling 8's gate
  is over REGISTER-PINNED slots. A half row pins one, so it contributes one.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.espn_tennis import parse_results
from app.utils.tournament_register import SCHEMA_VERSION
from app.utils.tournament_slate import build_results

NOW = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)

#: The real case, with the real ids: Swiatek is on our register, and ESPN spells
#: her round-of-16 opponent in the other name order, so the register misses her.
SWIATEK_ESPN_ID = 3936
ZHENG_ESPN_ID = 6048


def _singles_competitor(name, espn_id, order, *, winner=None, sets=None):
    """A singles competitor exactly as ESPN's scoreboard publishes one."""
    competitor = {
        "id": str(espn_id),
        "type": "athlete",
        "order": order,
        "athlete": {
            "displayName": name,
            "flag": {"href": "https://a.espncdn.com/f.png", "alt": "Poland"},
        },
    }
    if winner is not None:
        competitor["winner"] = winner
    if sets is not None:
        competitor["linescores"] = [{"value": v} for v in sets]
    return competitor


def _payload(*groupings):
    return {
        "events": [
            {
                "id": "189-2026",
                "name": "US Open",
                "groupings": [
                    {"grouping": {"slug": slug}, "competitions": comps}
                    for slug, comps in groupings
                ],
            }
        ]
    }


def _round_of_16(*, winner_name="Zheng Qinwen"):
    """Swiatek v Zheng, the real result: Zheng won 7-5, 6-3."""
    return {
        "id": "184901",
        "date": "2026-09-07T15:00Z",
        "round": {"displayName": "Round 4"},
        "status": {"type": {"state": "post", "name": "STATUS_FINAL", "detail": "Final"}},
        "competitors": [
            _singles_competitor(
                "Zheng Qinwen",
                ZHENG_ESPN_ID,
                1,
                winner=winner_name == "Zheng Qinwen",
                sets=[7, 6],
            ),
            _singles_competitor(
                "Iga Swiatek",
                SWIATEK_ESPN_ID,
                2,
                winner=winner_name == "Iga Swiatek",
                sets=[5, 3],
            ),
        ],
    }


def _register(*, players=None):
    """Singles only, and it carries Swiatek but not her opponent's spelling."""
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 12,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": [
            {
                "entity_key": "iga-swiatek",
                "display_name": "Iga Swiatek",
                "draw": "womens-singles",
                "role": "participant",
                "seed": 2,
                "image": {"url": "https://example.test/swiatek.jpg"},
                "sources": [],
            }
        ]
        if players is None
        else players,
        "matchups": [],
    }


def _build(register=None, competition=None):
    parsed = parse_results(
        [_payload(("womens-singles", [competition or _round_of_16()]))],
        event_name="US Open",
    )
    return parsed, build_results(register or _register(), results=parsed)


# ═══════════════════════════════════════════════════════════════════════════
# THE SHIP
# ═══════════════════════════════════════════════════════════════════════════

def test_a_match_with_one_registered_side_reaches_the_finished_list():
    """Swiatek's round of 16 is on the page. It was not, before this."""
    _parsed, built = _build()

    assert built["count"] == 1
    assert built["mixed_pairings"] == 1
    # THE POINT OF THE SPLIT: the row is no longer counted as a coverage gap,
    # because it is no longer a gap.
    assert built["unregistered_pairs"] == 0
    assert built["scoreboard_sourced"] == 0

    row = built["matches"][0]
    assert row["source_pairing"] == "mixed"
    assert row["round"] == "Round 4"
    assert row["score"] == "7-5, 6-3"
    assert row["completion"] == "final"


def test_the_held_side_is_pinned_and_the_other_is_named_by_the_scoreboard():
    """Each name comes from the source that is authoritative for it.

    And the ORDER is the scoreboard's, so the row reads the way the match did
    rather than putting whichever side we happen to hold first.
    """
    _parsed, built = _build()
    players = built["matches"][0]["players"]

    assert [p["display_name"] for p in players] == ["Zheng Qinwen", "Iga Swiatek"]
    assert [p["entity_key"] for p in players] == [
        f"espn:athlete:{ZHENG_ESPN_ID}",
        "iga-swiatek",
    ]
    unheld, pinned = players
    # The register's side keeps everything the register knows, through the same
    # `player_image` the board and the slate read.
    assert pinned["seed"] == 2
    assert pinned["image"]["url"] == "https://example.test/swiatek.jpg"
    # The scoreboard's side is honest about what it does not have: the renderer
    # turns a `None` image into initials, which is where an unpinned singles
    # slot already lands.
    assert unheld["seed"] is None
    assert unheld["image"] is None


def test_the_winner_is_the_side_the_scoreboard_says_won():
    """Including when it is the side we do NOT hold — Zheng beat Swiatek.

    The mutant this kills is "the pinned side won", which would pass every
    other assertion in this file and print the wrong player as the winner of
    every half row on the page.
    """
    _parsed, built = _build()
    row = built["matches"][0]

    assert row["winner_entity_key"] == f"espn:athlete:{ZHENG_ESPN_ID}"
    assert [p["display_name"] for p in row["players"] if p["is_winner"]] == [
        "Zheng Qinwen"
    ]

    # And the other way round, so the assertion is about the scoreboard and not
    # about which slot the fixture happens to put the winner in.
    _parsed, built = _build(competition=_round_of_16(winner_name="Iga Swiatek"))
    row = built["matches"][0]
    assert row["winner_entity_key"] == "iga-swiatek"
    assert [p["display_name"] for p in row["players"] if p["is_winner"]] == [
        "Iga Swiatek"
    ]


# ═══════════════════════════════════════════════════════════════════════════
# THE CONTROLS — each one is a refusal that must survive the relaxation
# ═══════════════════════════════════════════════════════════════════════════

def test_a_match_with_neither_side_registered_is_still_dropped():
    """THE CONTROL. One resolved side opens the branch; zero does not.

    33 of the 147 measured drops are between two people the register has never
    heard of. Publishing those would put a score under two names we cannot
    stand behind, which is exactly the strictness this ship is relaxing AROUND
    and not the strictness it is relaxing.

    THE REGISTER MUST STILL CARRY THE DRAW, and the first draft of this control
    did not make it: an EMPTY register makes `womens-singles` a draw the
    register has no opinion about, so #4124's scoreboard branch takes the row
    and publishes it — a pass that proves nothing about this ship's branch. The
    third player is load-bearing.
    """
    register = _register(
        players=[
            {
                "entity_key": "aryna-sabalenka",
                "display_name": "Aryna Sabalenka",
                "draw": "womens-singles",
                "role": "participant",
                "seed": 1,
                "sources": [],
            }
        ]
    )
    _parsed, built = _build(register=register)

    assert built["count"] == 0
    assert built["mixed_pairings"] == 0
    assert built["scoreboard_sourced"] == 0
    assert built["unregistered_pairs"] == 1


def test_a_half_row_is_refused_when_the_scoreboard_did_not_identify_the_other():
    """An unnamed side is not "a player we lack" — it is a score against nobody.

    Also the gotcha #53 shape #4124 guards: for up to one beat after a release
    the route reads a cached map with no `entity_keys` on it at all, and that
    must produce the OLD behaviour rather than a row with a `None` identity.
    """
    parsed, _built = _build()
    for found in parsed["draws"]["womens-singles"].values():
        found.pop("entity_keys")

    built = build_results(_register(), results=parsed)
    assert built["count"] == 0
    assert built["mixed_pairings"] == 0
    assert built["unregistered_pairs"] == 1


def test_a_half_row_is_refused_when_the_winner_matches_neither_side():
    """The drop the registered path already makes, still made here.

    A score whose winner we cannot attribute to one of the two named sides is
    the class of defect the register exists to make impossible, and it would
    look entirely plausible on the page.
    """
    parsed, _built = _build()
    for found in parsed["draws"]["womens-singles"].values():
        found["winner_normalized"] = "somebodyelse"

    built = build_results(_register(), results=parsed)
    assert built["count"] == 0
    assert built["mixed_pairings"] == 0
    assert built["unregistered_pairs"] == 1


def test_a_half_row_never_carries_a_pre_match_probability():
    """`_prematch_by_pair` is keyed on TWO register keys; a half row has one.

    Carrying the pinned side's prior alone would print one number against a
    two-sided question, which is worse than the absence the renderer already
    states honestly.
    """
    _parsed, built = _build()
    players = built["matches"][0]["players"]

    assert all(p["prematch_probability"] is None for p in players)
    assert all(p["prematch_source"] is None for p in players)
    assert built["with_prematch"] == 0


def test_the_image_coverage_gate_counts_the_one_pinned_slot():
    """Ruling 8's gate keeps asking the question it was built to ask.

    `player_slots` is "how many REGISTER-PINNED player slots are there". A half
    row pins ONE of its two, so it contributes one — counting two would report
    the gate failing on a slot it was never about, and counting zero would hide
    a pinned face from the coverage it belongs to.
    """
    _parsed, built = _build()

    assert built["count"] == 1
    assert built["player_slots"] == 1
    # Swiatek's register row carries a picture, so the pinned slot lands on the
    # face step rather than the flag or initials one.
    assert built["with_face"] == 1
    assert built["with_flag"] == 0


def test_a_fully_registered_match_is_untouched_by_the_new_branch():
    """THE OTHER CONTROL: the 321 rows that already worked still work.

    Both sides pinned, two slots counted, and `source_pairing` still says
    `register` — the branch must be reachable only from the drop path.
    """
    register = _register(
        players=[
            {
                "entity_key": "iga-swiatek",
                "display_name": "Iga Swiatek",
                "draw": "womens-singles",
                "role": "participant",
                "seed": 2,
                "image": {"url": "https://example.test/swiatek.jpg"},
                "sources": [],
            },
            {
                "entity_key": "qinwen-zheng",
                "display_name": "Zheng Qinwen",
                "draw": "womens-singles",
                "role": "participant",
                "seed": 5,
                "image": {"url": "https://example.test/zheng.jpg"},
                "sources": [],
            },
        ]
    )
    _parsed, built = _build(register=register)

    assert built["count"] == 1
    assert built["mixed_pairings"] == 0
    assert built["unregistered_pairs"] == 0
    row = built["matches"][0]
    assert row["source_pairing"] == "register"
    assert [p["entity_key"] for p in row["players"]] == ["qinwen-zheng", "iga-swiatek"]
    assert built["player_slots"] == 2
