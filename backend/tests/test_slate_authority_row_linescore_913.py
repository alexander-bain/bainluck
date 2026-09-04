"""THE SEMI-FINAL'S ROW SHOWS THE SET SCORE, NOT JUST "4th Set".

CERT-913 repair · PILLAR: TRUTH · SHIP: a reader who opens the US Open hub
during the men's semi-finals sees ``6-4, 4-6, 2-1`` on the row.

═══ WHY live/061 MISSED ITS OWN HEADLINE CASE ═══

live/061 put the line on ``build_match_row``, which is the REGISTER path, and
stopped there.  The register is a ceremony artefact: ``ingest_tournament_draw``
runs once, at the draw, and pins the FIRST ROUND only (96 US Open R128 fixtures
plus 28 qualifiers).  It has no round two, and it will never have a semi-final.

Every later round is therefore synthesized by ``authority_match_row`` on its
``pairing_source="scoreboard"`` path — and that function's payload had no
``linescore`` key at all.  So the feature shipped working on exactly the rounds
that were already over, and absent on every round a reader would open the hub
to watch.  Graded against the real board, competition ``182775`` came back
``status_detail='4th Set'``, ``has_linescore: False``.

These tests drive the WHOLE of ``build_slate``, not the helper, because the
helper was never the broken part — the routing was.  A test that calls
``_slate_linescore`` directly passes on the pre-repair tree.

═══ GUARDED BOTH DIRECTIONS (gotcha #43) ═══

"The line does not appear" is loud.  "A line appears when ESPN states none" is
silent, and would hand every unstarted fixture on the card a scoreboard reading
of ``0-0``.  So the upcoming control is here beside the presence case, and it
asserts the KEY IS ABSENT — not null, absent, which is what a reader's browser
does not download.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.tournament_register import SCHEMA_VERSION
from app.utils.tournament_slate import build_slate

NOW = datetime(2026, 9, 4, 23, 40, tzinfo=timezone.utc)

#: The register's one pinned fixture, long since decided.
R1_COMP = "182703"
#: The men's semi-final. The register has never heard of it.
SEMI_COMP = "182775"
#: The other semi-final, not yet on court.
SOON_COMP = "182764"

FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/esp.png"


def _competitor(name, espn_id, order):
    return {
        "name": name,
        "espn_athlete_id": espn_id,
        "flag_url": FLAG,
        "country": "Spain",
        "determined": True,
        "order": order,
    }


def _side(name, games, winners, tiebreaks=None):
    """One side of an ESPN competition, in ``competition_sides`` shape."""
    tiebreaks = tiebreaks or [None] * len(games)
    return {
        "name": name,
        "sets_won": sum(1 for w in winners if w),
        "games": [g for g in games if g is not None],
        "sets": [
            {"games": g, "tiebreak": t, "winner": bool(w)}
            for g, t, w in zip(games, tiebreaks, winners)
        ],
        "winner": None,
    }


#: Alcaraz leads Djokovic 6-4, 4-6, 2-1 — the sentence the row should print.
ALCARAZ = _competitor("Carlos Alcaraz", 3782, 1)
DJOKOVIC = _competitor("Novak Djokovic", 1035, 2)
SEMI_SIDES = [
    _side("Carlos Alcaraz", [6, 4, 2], [True, False, False]),
    _side("Novak Djokovic", [4, 6, 1], [False, True, False]),
]


def _listed(comp_id, competitors, *, state="in_progress", start_at, sides=None, **over):
    entry = {
        "espn_competition_id": comp_id,
        "draw": "mens-singles",
        "state": state,
        "start_at": start_at,
        "start_is_tbd": False,
        "status_detail": "4th Set" if state == "in_progress" else "Fri at 7:00 PM EDT",
        "espn_round": "Semifinals",
        "completion": "unknown",
        "was_suspended": False,
        "players": [c["name"] for c in competitors],
        "competitors": competitors,
    }
    if sides is not None:
        entry["sides"] = sides
    entry.update(over)
    return entry


def _register():
    """One round, and it is over — the ceremony artefact, exactly."""
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 14,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": [
            {
                "entity_key": "rafael-jodar",
                "display_name": "Rafael Jodar",
                "draw": "mens-singles",
                "role": "participant",
                "seed": None,
                "country": "Spain",
                "draw_slot": None,
                "section": None,
                "sources": [],
            },
            {
                "entity_key": "bu-yunchaokete",
                "display_name": "Bu Yunchaokete",
                "draw": "mens-singles",
                "role": "participant",
                "seed": None,
                "country": "China",
                "draw_slot": None,
                "section": None,
                "sources": [],
            },
        ],
        "matchups": [
            {
                "matchup_key": "mens-singles:bu-yunchaokete-vs-rafael-jodar:2026-08-30",
                "draw": "mens-singles",
                "round": "R128",
                "scheduled_date": "2026-08-30T04:00:00+00:00",
                "players": ["rafael-jodar", "bu-yunchaokete"],
                "evidence": {
                    "kind": "draw-ceremony-espn",
                    "espn_competition_id": R1_COMP,
                    "espn_round": "Round 1",
                    "observed_at": NOW.isoformat(),
                },
                "sources": [],
            }
        ],
    }


def _order_of_play(**overrides):
    listed = {
        R1_COMP: _listed(
            R1_COMP,
            [_competitor("Rafael Jodar", 12657, 1), _competitor("Bu Yunchaokete", 4419, 2)],
            state="decided",
            start_at="2026-08-30T17:00:00+00:00",
            espn_round="Round 1",
        ),
        SEMI_COMP: _listed(
            SEMI_COMP,
            [ALCARAZ, DJOKOVIC],
            start_at="2026-09-04T23:00:00+00:00",
            sides=SEMI_SIDES,
        ),
        SOON_COMP: _listed(
            SOON_COMP,
            [_competitor("Jannik Sinner", 4381, 1), _competitor("Taylor Fritz", 3333, 2)],
            state="upcoming",
            start_at="2026-09-05T00:35:00+00:00",
        ),
    }
    listed.update(overrides)
    return listed


def _slate(order_of_play=None):
    return build_slate(
        _register(),
        prices={},
        now=NOW,
        order_of_play=_order_of_play() if order_of_play is None else order_of_play,
        order_of_play_complete=True,
    )


def _by_key(slate):
    return {row["matchup_key"]: row for row in slate["matches"]}


# ═══════════════════ DIRECTION 1 — THE LINE APPEARS ═══════════════════


def test_the_semi_finals_row_carries_the_set_line():
    """THE DEFECT, in one assertion, through the whole builder.

    This is CERT-913's exact reproduction: a later-round competition the
    register does not hold, in play, with a line on the board. Pre-repair the
    row came back with ``status_detail`` and no ``linescore`` key.
    """
    row = _by_key(_slate())[f"espn:{SEMI_COMP}"]

    assert row["pairing_source"] == "scoreboard"
    assert row["status_detail"] == "4th Set"
    assert "linescore" in row, "the row a reader opens the hub for has no set line"
    assert row["linescore"]["line"] == "6-4, 4-6, 2-1"


def test_the_line_is_oriented_to_the_sides_the_row_publishes():
    """Column order is only true relative to a `sides` list — so pin both.

    A swapped linescore is an inverted result that nothing downstream doubts,
    so this asserts the correspondence rather than the string alone.
    """
    row = _by_key(_slate())[f"espn:{SEMI_COMP}"]
    line = row["linescore"]

    assert [s["display_name"] for s in row["sides"]] == [
        "Carlos Alcaraz",
        "Novak Djokovic",
    ]
    assert line["home_entity_key"] == row["sides"][0]["entity_key"]
    assert line["away_entity_key"] == row["sides"][1]["entity_key"]
    # Alcaraz took the first set 6-4 and leads the third 2-1.
    assert [(s["home"], s["away"]) for s in line["sets"]] == [(6, 4), (4, 6), (2, 1)]
    assert line["sets_won"] == {"home": 1, "away": 1}
    assert line["games"] == {"home": 12, "away": 11}


def test_the_line_and_the_caption_come_off_one_board_read():
    """Atomicity: the set line and "4th Set" describe the same instant.

    Both are read from the SAME ``order_of_play`` entry inside one call, so
    there is no arrangement of the beat that can let them disagree. Advance the
    board and BOTH move together — a row that reported a new set label beside
    the previous set's line would be describing two moments of one match.

    Held inside ``in_progress`` deliberately: a ``decided`` competition is
    dropped from the slate by ``build_slate``'s own rule ("DECIDED belongs to
    ``build_results``"), so the finished-match line is the results builder's
    subject and not this card's.
    """
    before = _by_key(_slate())[f"espn:{SEMI_COMP}"]
    assert before["status_detail"] == "4th Set"
    assert before["linescore"]["line"] == "6-4, 4-6, 2-1"

    board = _order_of_play()
    board[SEMI_COMP] = _listed(
        SEMI_COMP,
        [ALCARAZ, DJOKOVIC],
        start_at="2026-09-04T23:00:00+00:00",
        sides=[
            _side("Carlos Alcaraz", [6, 4, 6, 1], [True, False, True, False]),
            _side("Novak Djokovic", [4, 6, 3, 2], [False, True, False, False]),
        ],
        status_detail="5th Set",
    )
    after = _by_key(_slate(board))[f"espn:{SEMI_COMP}"]

    assert after["status_detail"] == "5th Set"
    assert after["linescore"]["status_detail"] == "5th Set"
    assert after["linescore"]["line"] == "6-4, 4-6, 6-3, 1-2"
    assert after["linescore"]["current_set"] == 4


def test_a_suspended_match_still_prints_the_line_it_reached():
    """The line survives an interruption, and says so.

    ``was_suspended`` travels WITH the score rather than replacing it, so a
    card can print "6-4, 4-6, 2-1 · suspended" where it would otherwise print
    nothing at all.
    """
    board = _order_of_play()
    board[SEMI_COMP] = _listed(
        SEMI_COMP,
        [ALCARAZ, DJOKOVIC],
        start_at="2026-09-04T23:00:00+00:00",
        sides=SEMI_SIDES,
        status_detail="Interrupted",
        was_suspended=True,
    )
    row = _by_key(_slate(board))[f"espn:{SEMI_COMP}"]

    assert row["linescore"]["line"] == "6-4, 4-6, 2-1"
    assert row["linescore"]["was_suspended"] is True


# ═══════════════════ DIRECTION 2 — THE SILENCES ═══════════════════
#
# The louder half of the guard. A line that appears when ESPN states none ships
# without anybody noticing and puts a 0-0 on every fixture of a card that has
# not started.


def test_an_upcoming_row_carries_no_linescore_key_at_all():
    """THE CONTROL. Absent, not null — a null is 32 downloads that say nothing."""
    row = _by_key(_slate())[f"espn:{SOON_COMP}"]

    assert row["pairing_source"] == "scoreboard"
    assert row["live_state"] == "upcoming"
    assert "linescore" not in row


def test_a_live_row_whose_board_states_no_sets_stays_quiet():
    """In play, but ESPN has published no set line yet — the first seconds."""
    board = _order_of_play()
    board[SEMI_COMP] = _listed(
        SEMI_COMP,
        [ALCARAZ, DJOKOVIC],
        start_at="2026-09-04T23:00:00+00:00",
        sides=[
            _side("Carlos Alcaraz", [], []),
            _side("Novak Djokovic", [], []),
        ],
        status_detail="1st Set",
    )
    row = _by_key(_slate(board))[f"espn:{SEMI_COMP}"]

    assert row["status_detail"] == "1st Set"
    assert "linescore" not in row


def test_a_board_that_states_no_sides_at_all_stays_quiet():
    """No `sides` key is the walkover shape, and it is silence, not 0-0."""
    row = _by_key(_slate())[f"espn:{SEMI_COMP}"]
    assert "linescore" in row  # control: the fixture above DOES carry one

    board = _order_of_play()
    board[SEMI_COMP] = _listed(
        SEMI_COMP, [ALCARAZ, DJOKOVIC], start_at="2026-09-04T23:00:00+00:00"
    )
    quiet = _by_key(_slate(board))[f"espn:{SEMI_COMP}"]
    assert "linescore" not in quiet


def test_a_board_naming_two_other_people_refuses_rather_than_guesses():
    """Orientation unresolved is a refusal, not a coin flip.

    A line whose columns cannot be tied to these two sides is exactly the
    inverted result the whole feature refuses to risk.
    """
    board = _order_of_play()
    board[SEMI_COMP] = _listed(
        SEMI_COMP,
        [ALCARAZ, DJOKOVIC],
        start_at="2026-09-04T23:00:00+00:00",
        sides=[
            _side("Lorenzo Musetti", [6, 4, 2], [True, False, False]),
            _side("Casper Ruud", [4, 6, 1], [False, True, False]),
        ],
    )
    row = _by_key(_slate(board))[f"espn:{SEMI_COMP}"]

    assert row["status_detail"] == "4th Set"
    assert "linescore" not in row


def test_a_broken_board_entry_costs_the_line_and_never_the_card(monkeypatch):
    """gotcha #42 — one bad item must not wipe the pass.

    Since this repair the scoreboard is the ONLY source of every round after
    the first, so an unguarded raise while building one set line would blank
    the entire hub mid-semi-final to avoid printing one score. The row keeps
    its two names, its clock and its state; it loses only the line.
    """
    import app.utils.tennis_linescore as tennis_linescore

    real = tennis_linescore.authority_linescore

    def _explode(ours, competition, *, observed_at):
        if competition.get("espn_competition_id") == SEMI_COMP:
            raise ValueError("board entry is malformed")
        return real(ours, competition, observed_at=observed_at)

    monkeypatch.setattr(tennis_linescore, "authority_linescore", _explode)

    rows = _by_key(_slate())

    # The card survives, and so does the row itself.
    assert f"espn:{SEMI_COMP}" in rows
    assert f"espn:{SOON_COMP}" in rows
    broken = rows[f"espn:{SEMI_COMP}"]
    assert [s["display_name"] for s in broken["sides"]] == [
        "Carlos Alcaraz",
        "Novak Djokovic",
    ]
    assert broken["status_detail"] == "4th Set"
    assert "linescore" not in broken
