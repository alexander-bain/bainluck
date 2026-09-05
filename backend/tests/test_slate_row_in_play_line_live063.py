"""THE HUB'S LIVE ROW SHOWS THE GAMES IT IS BEING PLAYED TO (live/063, #2746).

Measured on production 2026-09-05T21:2xZ, not hypothesised.  ``GET
/api/tournaments/us-open`` returned 18 slate rows, **all 18 with
``pairing_source: "scoreboard"``** — the register holds one round and the
tournament is past it — and the one match on court read::

    ● 1ST SET · MEN'S SINGLES
    Arthur Gea      +9  56%
    Michael Zheng   -9  44%

``status_detail: "1st Set"``, and no score of any kind.  Two columns to the
right, the FINISHED panel was printing ``6-3, 6-2, 6-4`` against every match
that had ended.  So the page could say what a match FINISHED at and not what
one is AT — the reader who most needs the number was the only one denied it.

Nothing had to be fetched to fix it.  ``espn_tennis.competition_sides`` already
parses the per-set games out of the same scoreboard payload that produces
``state`` and ``status_detail``; ``parse_results`` simply threw them away when
it built its ``order_of_play`` entry, and ``scoreboard_competitions`` — a
second reader of the same board — was already publishing them under the same
key.  So this ships one new field upstream and one derived key on the row.

WHAT THIS FILE PINS, and the last two are as load-bearing as the first:

1. ``parse_results`` publishes ``sides``, so the slate has something to orient.
2. A live scoreboard-path row carries the line.  THROUGH ``build_slate``, not
   through the helper — CERT-913 blocked exactly this ship once because the
   helper was green and the path that builds every real row never called it.
3. A row with nothing to say says nothing: an upcoming fixture contributes NO
   ``linescore`` KEY, not a null and not a line of zeroes.
4. The columns NAME THEIR OWNER.  ``home``/``away`` is positional and the hub
   re-sorts sides favourite-first, so a line that could not be re-pointed by id
   downstream is an inverted score nothing contradicts.
5. A ragged read — the two sides reporting different set counts, which is a
   scoreboard caught mid-write — is refused rather than paired off.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.espn_tennis import parse_results
from app.utils.tournament_register import SCHEMA_VERSION
from app.utils.tournament_slate import build_slate

NOW = datetime(2026, 9, 5, 21, 30, tzinfo=timezone.utc)
START = "2026-09-05T20:00:00+00:00"
COMP = "182775"

GEA_ID = 5001
ZHENG_ID = 5002
GEA_KEY = f"espn:athlete:{GEA_ID}"
ZHENG_KEY = f"espn:athlete:{ZHENG_ID}"


def _listed(
    *,
    state="in_progress",
    gea_games=(6, 2),
    zheng_games=(4, 1),
    order=(1, 2),
):
    """ESPN's ``order_of_play`` entry for the match that was on court.

    ``sides`` is what :func:`espn_tennis.competition_sides` produces and what
    this ship added to the map; ``order`` is ESPN's own top-to-bottom, which is
    the sequence ``authority_match_row`` builds its sides in.
    """
    gea_order, zheng_order = order
    return {COMP: {
        "espn_competition_id": COMP,
        "draw": "mens-singles",
        "state": state,
        "start_at": START,
        "start_is_tbd": False,
        "status_detail": "1st Set",
        "espn_round": "Round of 32",
        "players": ["Arthur Gea", "Michael Zheng"],
        "competitors": [
            {"espn_athlete_id": GEA_ID, "name": "Arthur Gea", "determined": True,
             "country": "France", "flag_url": "fra.png", "order": gea_order},
            {"espn_athlete_id": ZHENG_ID, "name": "Michael Zheng", "determined": True,
             "country": "United States", "flag_url": "usa.png", "order": zheng_order},
        ],
        "sides": [
            {"name": "Arthur Gea", "sets_won": 0,
             "games": list(gea_games), "winner": None},
            {"name": "Michael Zheng", "sets_won": 0,
             "games": list(zheng_games), "winner": None},
        ],
    }}


def _empty_register():
    """A register that claims nothing, so every row comes from the scoreboard.

    This is the production shape for a tournament past its first round, and it
    is the shape that made CERT-913's helper-only proof worthless.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 9,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": [],
        "matchups": [],
    }


def _register_with_the_fixture():
    """The register holding this same fixture, pinned and priced.

    Used only by the register-path test — the two builders orient against
    different orders (pinned pairing vs ESPN's top-to-bottom) and neither can
    borrow the other's, so each needs its own proof.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 9,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": [
            {"entity_key": "arthur-gea", "display_name": "Arthur Gea",
             "draw": "mens-singles", "sources": []},
            {"entity_key": "michael-zheng", "display_name": "Michael Zheng",
             "draw": "mens-singles", "sources": []},
        ],
        "matchups": [{
            "matchup_key": "mens-singles:arthur-gea-vs-michael-zheng:2026-09-05",
            "draw": "mens-singles",
            "round": "R32",
            "scheduled_date": START,
            "players": ["arthur-gea", "michael-zheng"],
            "evidence": {"espn_competition_id": COMP},
            "sources": [{
                "source": "kalshi", "kind": "match", "status": "live",
                "market_id": 60006342, "outcome_id": 700001,
                "market_external_id": "KXATPMATCH-26SEP05GEAZHE",
                "terminal_result": None,
                "evidence": {"kind": "draw-census", "espn_competition_id": COMP},
                "sides": {
                    "arthur-gea": {"outcome_id": 700001},
                    "michael-zheng": {"outcome_id": 700002},
                },
            }],
        }],
    }


def _prices():
    observed = NOW - timedelta(minutes=5)
    return {
        700001: {"probability": 0.56, "opening_probability": 0.48,
                 "observed_at": observed},
        700002: {"probability": 0.44, "opening_probability": 0.52,
                 "observed_at": observed},
    }


def _slate(register, listed, prices=None):
    return build_slate(
        register,
        prices=prices or {},
        now=NOW,
        order_of_play=listed,
    )


def _row(slate):
    rows = slate["matches"]
    assert len(rows) == 1, f"expected one row, got {len(rows)}"
    return rows[0]


# ---------------------------------------------------------------------------
# 1. The upstream field
# ---------------------------------------------------------------------------

class TestTheBoardPublishesTheGames:
    """``parse_results`` has to hand the slate something to orient."""

    @staticmethod
    def _payload():
        def competitor(name, athlete_id, sets):
            return {
                "id": str(athlete_id),
                "athlete": {"displayName": name},
                "winner": None,
                "linescores": [{"value": value} for value in sets],
            }

        return {"events": [{
            "id": "189-2026",
            "name": "US Open",
            "groupings": [{
                "grouping": {"slug": "mens-singles"},
                "competitions": [{
                    "id": COMP,
                    "date": START,
                    "status": {"type": {"state": "in", "detail": "1st Set"}},
                    "round": {"displayName": "Round of 32"},
                    "competitors": [
                        competitor("Arthur Gea", GEA_ID, [6, 2]),
                        competitor("Michael Zheng", ZHENG_ID, [4, 1]),
                    ],
                }],
            }],
        }]}

    def test_the_order_of_play_entry_carries_the_per_set_games(self):
        parsed = parse_results([self._payload()], event_name="US Open")
        listed = parsed["order_of_play"][COMP]

        assert listed["state"] == "in_progress"
        assert listed["sides"] == [
            {"name": "Arthur Gea", "sets_won": 0, "games": [6, 2], "winner": None},
            {"name": "Michael Zheng", "sets_won": 0, "games": [4, 1], "winner": None},
        ]

    def test_the_pairing_fields_are_untouched_by_it(self):
        """The line rides ALONGSIDE the pairing, it does not reshape it."""
        listed = parse_results(
            [self._payload()], event_name="US Open"
        )["order_of_play"][COMP]

        assert listed["players"] == ["Arthur Gea", "Michael Zheng"]
        assert [c["name"] for c in listed["competitors"]] == [
            "Arthur Gea", "Michael Zheng"
        ]
        assert listed["status_detail"] == "1st Set"

    def test_a_decided_competition_pays_nothing_for_a_line_nobody_reads(self):
        """The map is cached JSON in a shared 100MB LRU, so scope is a cost.

        Measured against the live US Open board 2026-09-05, 625 competitions:
        publishing ``sides`` on all of them grew the map 362,985 -> 462,920
        bytes, and **81,191 of the 99,935 added bytes were decided
        competitions** — not one of which the slate can read, because
        ``build_match_row`` returns ``DECIDED`` for them and ``build_slate``'s
        scoreboard pass skips them outright.  Scoped to in-play the same board
        costs 692 bytes.

        Pinned because it is a DECISION and not an accident: a reader who finds
        the key missing on a finished match and 'fixes' it re-spends the 81KB.
        """
        payload = self._payload()
        competition = payload["events"][0]["groupings"][0]["competitions"][0]
        competition["status"]["type"] = {"state": "post", "detail": "Final"}
        for competitor, won in zip(competition["competitors"], (True, False)):
            competitor["winner"] = won

        listed = parse_results([payload], event_name="US Open")["order_of_play"]

        assert listed[COMP]["state"] == "decided"
        assert "sides" not in listed[COMP]

    def test_the_board_feeds_the_slate_end_to_end(self):
        """No hand-written ``sides`` anywhere: board payload in, line out.

        Every other test in this file builds its ``order_of_play`` by hand, so
        exactly one of them has to close the loop — otherwise the two halves of
        this ship could each be green while the key they agree on is spelled
        differently.
        """
        parsed = parse_results([self._payload()], event_name="US Open")
        row = _row(_slate(_empty_register(), parsed["order_of_play"]))

        assert row["linescore"]["sets"] == [[6, 4], [2, 1]]


# ---------------------------------------------------------------------------
# 2-3. The row, through the whole slate
# ---------------------------------------------------------------------------

class TestTheLiveRowShowsTheLine:

    def test_the_scoreboard_path_row_carries_it(self):
        row = _row(_slate(_empty_register(), _listed()))

        assert row["pairing_source"] == "scoreboard"
        assert row["status_detail"] == "1st Set"
        assert row["linescore"]["sets"] == [[6, 4], [2, 1]]
        assert row["linescore"]["home_games"] == 8
        assert row["linescore"]["away_games"] == 5

    def test_the_register_path_row_carries_it_too(self):
        row = _row(_slate(
            _register_with_the_fixture(), _listed(), prices=_prices()
        ))

        # No `pairing_source` at all is the REGISTER row's signature — the key
        # exists only on the two authority paths.
        assert "pairing_source" not in row
        assert row["matchup_key"].startswith("mens-singles:")
        assert row["linescore"]["sets"] == [[6, 4], [2, 1]]
        # Oriented to the REGISTER's pinned pairing, whose order is its own.
        assert row["linescore"]["home_entity_key"] == "arthur-gea"
        assert row["linescore"]["away_entity_key"] == "michael-zheng"

    def test_an_upcoming_row_contributes_no_key_at_all(self):
        """Not a null. A draw that has not started is 96 rows of nothing."""
        row = _row(_slate(
            _empty_register(),
            _listed(state="upcoming", gea_games=(), zheng_games=()),
        ))

        assert row["live_state"] == "upcoming"
        assert "linescore" not in row

    def test_a_started_match_the_board_has_not_scored_yet_says_nothing(self):
        """``in_progress`` with an empty line is the first game of every match.

        The refusal is ``no-line`` and it must read as silence, not as 0-0 —
        which is the same number a row would print for a set nobody has won.
        """
        row = _row(_slate(
            _empty_register(), _listed(gea_games=(), zheng_games=())
        ))

        assert row["live_state"] == "in_progress"
        assert "linescore" not in row


# ---------------------------------------------------------------------------
# 4. The columns name their owner
# ---------------------------------------------------------------------------

class TestTheColumnsNameTheirOwner:
    """``home``/``away`` is positional, and the hub re-sorts sides."""

    def test_the_anchors_are_the_rows_own_two_entity_keys(self):
        row = _row(_slate(_empty_register(), _listed()))

        assert [s["entity_key"] for s in row["sides"]] == [GEA_KEY, ZHENG_KEY]
        assert row["linescore"]["home_entity_key"] == GEA_KEY
        assert row["linescore"]["away_entity_key"] == ZHENG_KEY

    def test_reversing_espns_order_reverses_both_together(self):
        """The row's sides and its line must move as ONE.

        If they could move independently the score would be attributed to the
        wrong player — and a `6-4, 2-1` against the man who is losing is worse
        than no score, because nothing on the card contradicts it.
        """
        row = _row(_slate(_empty_register(), _listed(order=(2, 1))))

        assert [s["entity_key"] for s in row["sides"]] == [ZHENG_KEY, GEA_KEY]
        assert row["linescore"]["home_entity_key"] == ZHENG_KEY
        assert row["linescore"]["away_entity_key"] == GEA_KEY
        # Zheng's games lead now, because Zheng leads the row.
        assert row["linescore"]["sets"] == [[4, 6], [1, 2]]
        assert row["linescore"]["home_games"] == 5
        assert row["linescore"]["away_games"] == 8


# ---------------------------------------------------------------------------
# 5. What it refuses
# ---------------------------------------------------------------------------

class TestWhatItRefuses:

    def test_a_ragged_read_is_refused_rather_than_paired_off(self):
        """Two sides, different set counts: a board caught mid-write.

        Pairing the common prefix would print a set the other player has not
        been credited with — ``authority_games_line``'s ``ragged-line``, and
        ``format_score`` refuses the same shape for the same reason.
        """
        row = _row(_slate(
            _empty_register(), _listed(gea_games=(6, 2), zheng_games=(4,))
        ))

        assert row["live_state"] == "in_progress"
        assert "linescore" not in row

    def test_a_line_it_cannot_orient_is_refused_not_guessed(self):
        """Neither ESPN name resolves to a side, so no column has an owner."""
        listed = _listed()
        listed[COMP]["sides"] = [
            {"name": "Somebody Else", "sets_won": 0, "games": [6, 2],
             "winner": None},
            {"name": "Another Person", "sets_won": 0, "games": [4, 1],
             "winner": None},
        ]
        row = _row(_slate(_empty_register(), listed))

        assert "linescore" not in row

    def test_a_broken_board_entry_costs_the_line_and_never_the_row(self):
        """gotcha #42, on the only card the US Open has.

        The line is an enrichment on a row that was complete without it, and
        the scoreboard is now the source of every row on this card. An
        unguarded raise would blank the whole hub mid-tournament to avoid
        printing one set score.
        """
        listed = _listed()
        listed[COMP]["sides"] = "not a list at all"
        slate = _slate(_empty_register(), listed)
        row = _row(slate)

        assert row["status_detail"] == "1st Set"
        assert [s["entity_key"] for s in row["sides"]] == [GEA_KEY, ZHENG_KEY]
        assert "linescore" not in row
