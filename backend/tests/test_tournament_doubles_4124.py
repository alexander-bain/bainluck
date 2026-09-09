"""THE TOURNAMENT PAGE STOPS PRETENDING THE DOUBLES DO NOT EXIST.

lane1b/101 · #4124 · PILLAR: TRUTH · SHIP: `/tournaments/us-open` shows the
doubles — today's quarter-finals and the 137 matches already played — instead of
nothing at all.

═══ WHAT WAS MEASURED ═══

Alex's issue: the tournament page carried **0 occurrences of the substring
"oubles" in its 935 KB payload** while `/hub/tennis` showed twelve live US Open
doubles matches. Not "present but unrendered" — the payload had none.

Replayed against the live ESPN board 2026-09-09 (all five draws, 625
competitions) through this repo's own reader::

    order_of_play entries                 625   147 of them doubles
    ... naming two identified sides       474   ALL singles, ZERO doubles
    finished results parsed               468   ALL singles
    `unpaired`, counted and dropped       137   ALL doubles

Every "who is playing" read in `services/espn_tennis.py` went to
``competitor["athlete"]["displayName"]``, and a doubles competitor has no
``athlete`` key. It has a ``roster``::

    id      "1013-2319"        the two athlete ids, joined
    type    "team"
    roster  displayName "Marcelo Melo / John Peers"

So nothing was filtering the doubles out. **They never acquired a name**, and
every gate downstream — `determined`, `authority_match_row`'s two-identified-
sides rule, `build_results`' both-players-registered rule — correctly refused a
side it had been handed as an empty string. The gates were right; the read was
blind.

═══ WHAT THIS FILE GUARDS, AND THE TWO CONTROLS ═══

The ship is four steps and each has a test below: the pair gets a NAME, it gets
an IDENTITY, it reaches the day's CARD with the right round, and it reaches the
FINISHED list. Two controls are as load-bearing as the ship:

* ``test_a_singles_pair_the_register_does_not_carry_is_still_unregistered`` —
  the results path opens a scoreboard-sourced branch, and it must open for a
  draw the register has never heard of and NOT for a singles qualifier the
  register merely failed to pin. Without this control the branch would quietly
  add 157 unreviewed singles rows to a list Alex reads.
* ``test_round_two_still_needs_a_draw_size`` — `authority_round` stops requiring
  a draw size, which it needed for "Round 2" and never needed for
  "Quarterfinal". The relaxation must not reach the case it was written for.

And one agreement test, ``test_the_linker_and_the_slate_mint_the_same_key``,
because the price for a doubles match is written under an entity key in
`tasks/tournament_matchup_linker` and read back under one in
`utils/tournament_slate`. Those were two independent f-strings. A shared
constant formatted in two files is a contract with nothing holding it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.espn_tennis import (
    PAIR_ENTITY_PREFIX,
    _competitor_view,
    competitor_entity_key,
    competitor_name,
    pair_athlete_ids,
    parse_results,
)
from app.tasks.tournament_matchup_linker import _authority_competitions
from app.utils.tournament_register import SCHEMA_VERSION
from app.utils.tournament_slate import authority_round, build_results, build_slate

NOW = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)

#: Men's doubles quarter-final, on court tonight. Real ids, real names.
QF_COMP = "182892"
GRANOLLERS_ZEBALLOS = "espn:pair:698-1513"
RAM_SALISBURY = "espn:pair:841-3335"


def _pair_competitor(display, ids, order, *, winner=None, sets=None):
    """A doubles competitor exactly as ESPN's scoreboard publishes one."""
    competitor = {
        "id": "-".join(str(i) for i in ids),
        "type": "team",
        "order": order,
        "roster": {
            "displayName": display,
            "athletes": [
                {"displayName": part.strip(), "flag": {"href": "x", "alt": "Spain"}}
                for part in display.split("/")
            ],
        },
    }
    if winner is not None:
        competitor["winner"] = winner
    if sets is not None:
        competitor["linescores"] = [{"value": v} for v in sets]
    return competitor


def _singles_competitor(name, espn_id, order, *, winner=None, sets=None):
    competitor = {
        "id": str(espn_id),
        "type": "athlete",
        "order": order,
        "athlete": {
            "displayName": name,
            "flag": {"href": "https://a.espncdn.com/f.png", "alt": "Spain"},
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


def _upcoming_doubles_qf():
    return {
        "id": QF_COMP,
        "date": "2026-09-09T22:00Z",
        "round": {"displayName": "Quarterfinal"},
        "status": {
            "type": {"state": "pre", "detail": "Wed at 6:00 PM EDT"},
            "period": 0,
        },
        "competitors": [
            _pair_competitor("Rajeev Ram / Joe Salisbury", (841, 3335), 1),
            _pair_competitor("Marcel Granollers / Horacio Zeballos", (698, 1513), 2),
        ],
    }


def _finished_doubles():
    return {
        "id": "182878",
        "date": "2026-09-03T15:00Z",
        "round": {"displayName": "Round 1"},
        "status": {"type": {"state": "post", "name": "STATUS_FINAL", "detail": "Final"}},
        "competitors": [
            _pair_competitor(
                "Marcelo Melo / John Peers", (1013, 2319), 1, winner=True, sets=[3, 7, 6]
            ),
            _pair_competitor(
                "James Duckworth / Miomir Kecmanovic",
                (1857, 2874),
                2,
                winner=False,
                sets=[6, 5, 4],
            ),
        ],
    }


def _register(*, doubles_players=()):
    """The ceremony's register: singles only, which is the whole point."""
    players = [
        {
            "entity_key": "carlos-alcaraz",
            "display_name": "Carlos Alcaraz",
            "draw": "mens-singles",
            "role": "participant",
            "seed": 1,
            "sources": [],
        },
        *doubles_players,
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 12,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": players,
        "matchups": [],
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — the pair gets a name
# ═══════════════════════════════════════════════════════════════════════════

def test_a_doubles_competitor_is_named_by_its_roster():
    competitor = _pair_competitor("Marcelo Melo / John Peers", (1013, 2319), 1)
    assert competitor_name(competitor) == "Marcelo Melo / John Peers"


def test_an_athlete_still_wins_where_there_is_one():
    # The fallback must not reorder the ordinary case: 474 singles competitions
    # a day read through this function.
    competitor = _singles_competitor("Carlos Alcaraz", 3782, 1)
    competitor["roster"] = {"displayName": "SHOULD NOT BE READ"}
    assert competitor_name(competitor) == "Carlos Alcaraz"


def test_pair_ids_are_sorted_so_the_key_is_the_pairs_and_not_the_payloads():
    # ESPN publishes the ids in ROSTER order. The roster is a property of one
    # payload; the pair is the thing we key on, and it must survive ESPN listing
    # the same two people the other way round in the next round.
    assert pair_athlete_ids({"id": "2319-1013"}) == [1013, 2319]
    assert pair_athlete_ids({"id": "1013-2319"}) == [1013, 2319]


def test_pair_ids_refuse_everything_that_is_not_exactly_two_positive_ids():
    for bad in ("3782", "", "1013-2319-4", "1013-", "abc-def", "0-2319"):
        assert pair_athlete_ids({"id": bad}) == [], bad


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — the pair gets an identity
# ═══════════════════════════════════════════════════════════════════════════

def test_a_doubles_pair_is_determined_and_carries_a_pair_key():
    view = _competitor_view(
        _pair_competitor("Marcel Granollers / Horacio Zeballos", (698, 1513), 2)
    )
    assert view["determined"] is True
    assert view["name"] == "Marcel Granollers / Horacio Zeballos"
    assert view["entity_key"] == GRANOLLERS_ZEBALLOS
    assert view["entity_key"].startswith(PAIR_ENTITY_PREFIX)
    # A pair has TWO countries. Printing either one tells the reader something
    # false about the other player, so it prints neither.
    assert view["flag_url"] is None
    assert view["country"] is None
    assert view["espn_athlete_id"] is None


def test_a_singles_view_is_unchanged():
    view = _competitor_view(_singles_competitor("Carlos Alcaraz", 3782, 1))
    assert view["determined"] is True
    assert view["espn_athlete_id"] == 3782
    assert view["entity_key"] == "espn:athlete:3782"
    assert view["country"] == "Spain"
    assert "espn_pair_id" not in view


def test_a_tbd_slot_is_still_silence():
    # An unfilled later-round slot names "TBD" with a non-positive id. The
    # doubles read must not turn a placeholder into a competitor.
    view = _competitor_view({"id": "-1", "type": "athlete", "athlete": {"displayName": "TBD"}})
    assert view["determined"] is False
    assert competitor_entity_key(view) is None


def test_an_undetermined_view_has_no_key():
    assert competitor_entity_key({"determined": False, "espn_athlete_id": 7}) is None
    assert competitor_entity_key({}) is None


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — the pair reaches the day's card
# ═══════════════════════════════════════════════════════════════════════════

def test_the_scoreboard_publishes_a_doubles_fixture_with_both_sides_named():
    parsed = parse_results(
        [_payload(("mens-doubles", [_upcoming_doubles_qf()]))], event_name="US Open"
    )
    listed = parsed["order_of_play"][QF_COMP]
    assert listed["draw"] == "mens-doubles"
    assert listed["players"] == [
        "Rajeev Ram / Joe Salisbury",
        "Marcel Granollers / Horacio Zeballos",
    ]
    assert [c["entity_key"] for c in listed["competitors"]] == [
        RAM_SALISBURY,
        GRANOLLERS_ZEBALLOS,
    ]
    assert parsed["stats"]["unpaired"] == 0


def test_a_doubles_quarter_final_reaches_the_slate_named_and_rounded():
    parsed = parse_results(
        [_payload(("mens-doubles", [_upcoming_doubles_qf()]))], event_name="US Open"
    )
    slate = build_slate(
        _register(), prices={}, now=NOW, order_of_play=parsed["order_of_play"]
    )
    assert slate["count"] == 1
    row = slate["matches"][0]
    assert row["draw"] == "mens-doubles"
    assert row["draw_label"] == "Men's Doubles"
    # THE ROUND, and it is the reason `authority_round` was relaxed. The
    # register carries no doubles matchup, so `first_round_size` returns None;
    # under the old guard this published `round: null` and the client's
    # `slateRoundKey` files an unrecognised round under **Qualifying** — the
    # quarter-final of a Slam, on the card, under the qualifying heading.
    assert row["round"] == "QF"
    assert [side["display_name"] for side in row["sides"]] == [
        "Rajeev Ram / Joe Salisbury",
        "Marcel Granollers / Horacio Zeballos",
    ]
    assert [side["entity_key"] for side in row["sides"]] == [
        RAM_SALISBURY,
        GRANOLLERS_ZEBALLOS,
    ]
    assert row["pairing_source"] == "scoreboard"


def test_a_named_round_needs_no_draw_size():
    assert authority_round({"espn_round": "Quarterfinal"}, None) == "QF"
    assert authority_round({"espn_round": "Semifinal"}, None) == "SF"
    assert authority_round({"espn_round": "Final"}, None) == "F"


def test_round_two_still_needs_a_draw_size():
    # THE CONTROL for the relaxation above. "Round 2" is `R64` in a 128-draw and
    # `R32` in a 64-draw; without a size it is not a round, and publishing a
    # guess is the wrong-question defect the register exists to refuse.
    assert authority_round({"espn_round": "Round 2"}, None) is None
    assert authority_round({"espn_round": "Round 2"}, 128) == "R64"


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — the pair reaches the finished list
# ═══════════════════════════════════════════════════════════════════════════

def test_a_finished_doubles_match_renders_with_its_score_and_its_winner():
    parsed = parse_results(
        [_payload(("mens-doubles", [_finished_doubles()]))], event_name="US Open"
    )
    built = build_results(_register(), results=parsed)

    assert built["count"] == 1
    assert built["scoreboard_sourced"] == 1
    assert built["unregistered_pairs"] == 0
    row = built["matches"][0]
    assert row["draw"] == "mens-doubles"
    assert row["draw_label"] == "Men's Doubles"
    assert row["source_pairing"] == "scoreboard"
    assert row["score"] == "3-6, 7-5, 6-4"
    winners = [p["display_name"] for p in row["players"] if p["is_winner"]]
    assert winners == ["Marcelo Melo / John Peers"]
    assert row["winner_entity_key"] == "espn:pair:1013-2319"
    # Honest about what a scoreboard row does not have.
    assert all(p["seed"] is None and p["image"] is None for p in row["players"])
    assert all(p["prematch_probability"] is None for p in row["players"])


def test_a_cache_written_before_this_ship_degrades_to_the_old_behaviour():
    """The three minutes after the deploy, and gotcha #53's shape.

    ``_espn_results`` serves a payload `sync_tournament_results` wrote — every
    180s, so for up to one beat after a release the route is reading a map with
    no ``entity_keys`` on it at all. That must produce the OLD page (no doubles
    rows), not a row with two `None` identities, which would render two blank
    names under a real score.
    """
    parsed = parse_results(
        [_payload(("mens-doubles", [_finished_doubles()]))], event_name="US Open"
    )
    for found in parsed["draws"]["mens-doubles"].values():
        found.pop("entity_keys")

    built = build_results(_register(), results=parsed)
    assert built["count"] == 0
    assert built["scoreboard_sourced"] == 0
    assert built["unregistered_pairs"] == 1


def test_a_singles_pair_the_register_does_not_carry_is_still_unregistered():
    """THE CONTROL. The new branch must not widen the singles list.

    A singles qualifier the register failed to pin is a COVERAGE gap in a draw
    the register has an opinion about, and it is counted, not rendered. Only a
    draw the register carries no player in at all falls through to the
    scoreboard. Without this the branch would silently add 157 unreviewed rows
    to the finished list of a draw Alex reads every morning.
    """
    finished_singles = {
        "id": "184607",
        "date": "2026-08-24T15:00Z",
        "round": {"displayName": "Qualifying 1st Round"},
        "status": {"type": {"state": "post", "name": "STATUS_FINAL", "detail": "Final"}},
        "competitors": [
            _singles_competitor("Jacob Fearnley", 11685, 1, winner=True, sets=[7, 6]),
            _singles_competitor(
                "Roberto Carballes Baena", 2012, 2, winner=False, sets=[6, 3]
            ),
        ],
    }
    parsed = parse_results(
        [_payload(("mens-singles", [finished_singles]))], event_name="US Open"
    )
    built = build_results(_register(), results=parsed)

    assert built["count"] == 0
    assert built["unregistered_pairs"] == 1
    assert built["scoreboard_sourced"] == 0


def test_the_image_coverage_gate_counts_register_slots_only():
    """Ruling 8's gate keeps asking the question it was built to ask.

    ``player_slots`` is "how many REGISTER-PINNED player slots are there", and
    ``with_face``/``with_flag`` say how many of them have a picture. A doubles
    pair is not a person with a headshot, so counting its two slots in the
    denominator would report the gate failing on rows it was never about.
    """
    parsed = parse_results(
        [_payload(("mens-doubles", [_finished_doubles()]))], event_name="US Open"
    )
    built = build_results(_register(), results=parsed)
    assert built["count"] == 1
    assert built["player_slots"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# THE AGREEMENT — two files, one key
# ═══════════════════════════════════════════════════════════════════════════

def test_the_linker_and_the_slate_mint_the_same_key():
    """A price filed under one key and read under another is a blank card.

    ``tournament_matchup_linker`` writes the resolved outcome id under a side's
    entity key; ``authority_match_row`` looks it up by the key it puts on the
    row. Both formatted that string independently until #4124, so the day one of
    them learned about pairs the other would have kept reading
    ``espn:athlete:None`` and every doubles card would have printed no number
    while we held the market.
    """
    parsed = parse_results(
        [_payload(("mens-doubles", [_upcoming_doubles_qf()]))], event_name="US Open"
    )
    order_of_play = parsed["order_of_play"]

    written = _authority_competitions(order_of_play)
    assert len(written) == 1
    written_keys = {p["entity_key"] for p in written[0]["players"]}

    slate = build_slate(
        _register(), prices={}, now=NOW, order_of_play=order_of_play
    )
    read_keys = {side["entity_key"] for side in slate["matches"][0]["sides"]}

    assert written_keys == read_keys == {RAM_SALISBURY, GRANOLLERS_ZEBALLOS}


def test_the_candidate_pool_can_see_a_doubles_market_at_all():
    """THE LAST LINK, and the one that makes every other one look broken.

    ``WATCHED`` is an explicit allowlist of Kalshi series, and it named the two
    SINGLES series. A doubles card can be named, identified, rounded, rendered
    and looked up under exactly the right key, and it still prints no number if
    the resolver's pool never contained a doubles market — and every symptom of
    that is indistinguishable from "nobody quotes the doubles" (gotcha #53).

    ``KXMIXEDDOUBLESMATCH`` and NOT ``KXMIXEDDOUBLES``: the latter is the mixed
    doubles *Tournament Champion* series. An outright in a match-market pool is
    a market that can bind to a fixture and answer a different question.
    """
    from app.tasks.tournament_matchup_linker import WATCHED

    series = dict(WATCHED[0])["kalshi_series"]
    assert set(series) == {
        "KXATPMATCH",
        "KXWTAMATCH",
        "KXATPDOUBLES",
        "KXWTADOUBLES",
        "KXMIXEDDOUBLESMATCH",
    }
    assert "KXMIXEDDOUBLES" not in series


def test_the_pool_query_reaches_every_watched_series():
    """And the statement that RUNS asks for them, not just the constant.

    ux/1033's lesson on this exact query: every test of this task stubs
    ``_load_candidates`` whole, which is how an unordered ``LIMIT`` over 5,113
    rows went six months unnoticed. So this asserts the compiled SQL.
    """
    from datetime import timedelta

    from app.tasks.tournament_matchup_linker import WATCHED, candidate_query

    series = dict(WATCHED[0])["kalshi_series"]
    sql = str(
        candidate_query(series, now=NOW).compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    for name in series:
        assert f"{name}-%" in sql, name
    # The bounds ux/1033 put there stay there.
    assert "ORDER BY futures_markets.id DESC" in sql
    assert "LIMIT 2000" in sql
    assert str((NOW - timedelta(days=14)).date()) in sql


def test_a_resolved_doubles_price_reaches_the_card():
    """And the number arrives, which is the point of the agreement above."""
    parsed = parse_results(
        [_payload(("mens-doubles", [_upcoming_doubles_qf()]))], event_name="US Open"
    )
    slate = build_slate(
        _register(),
        prices={
            901: {"probability": 0.62, "opening_probability": 0.60, "observed_at": NOW},
            902: {"probability": 0.38, "opening_probability": 0.40, "observed_at": NOW},
        },
        now=NOW,
        order_of_play=parsed["order_of_play"],
        authority_links={
            f"espn:{QF_COMP}|kalshi": {
                "sides": {
                    RAM_SALISBURY: {"outcome_id": 901},
                    GRANOLLERS_ZEBALLOS: {"outcome_id": 902},
                }
            }
        },
    )
    row = slate["matches"][0]
    assert row["priced"] is True
    assert [side["probability"] for side in row["sides"]] == [0.62, 0.38]
