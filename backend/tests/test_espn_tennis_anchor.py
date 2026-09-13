"""lane1/057 STEP 0 — the tennis ESPN anchor, its receipts, and the revoke.

Every fixture below is shaped on a REAL competition read off the live US Open
scoreboard 2026-09-02T21:0xZ (competition 182712, Altmaier's fourth set), so a
payload-shape change breaks these rather than sailing past them.

The population claims in ``espn_tennis_anchor``'s docstring — 174 exact / 13
names-agree / 3 pairing-anchored / 4 refused over 194 events — are measured
against the live board by ``scripts/audit_tennis_espn_anchor.py``, which is the
needle and is not a unit test.  What is tested here is every RULE that produced
those numbers, and in both directions: each pass links what it should and
refuses what it must.
"""

from datetime import datetime, timezone

import pytest

from app.services.espn_tennis import (
    is_placeholder_pairing,
    scoreboard_competitions,
)
from app.utils.espn_tennis_anchor import (
    MATCH_EXACT_PAIR,
    MATCH_NAMES_AGREE,
    MATCH_PAIRING_ANCHORED,
    REJECT_AMBIGUOUS,
    REJECT_EMPTY_BOARD,
    REJECT_NO_CANDIDATE,
    REJECT_UNNAMED_EVENT,
    anchor_receipt,
    authority_write,
    pairing_anchors,
    pairing_matches,
    state_contradiction,
)
from app.utils.player_names import names_agree, shares_substantial_token


def _competitor(name, linescores=None, winner=None):
    competitor = {
        "id": "3203",
        "type": "athlete",
        "linescores": linescores or [],
        "athlete": {"displayName": name, "id": "3203"},
    }
    if winner is not None:
        competitor["winner"] = winner
    return competitor


def _competition(
    comp_id,
    names,
    *,
    state="pre",
    period=1,
    short_detail="",
    date="2026-09-02T16:40Z",
    linescores=None,
    winners=None,
    status_name="STATUS_SCHEDULED",
):
    """A competition in ESPN's real shape — see 182712 in the module docstring."""
    lines = linescores or [[], []]
    flags = winners or [None] * len(names)
    return {
        "id": comp_id,
        "date": date,
        "status": {
            "period": period,
            "type": {
                "name": status_name,
                "state": state,
                "detail": "detail",
                "shortDetail": short_detail,
            },
        },
        "competitors": [
            _competitor(name, line, flag)
            for name, line, flag in zip(names, lines, flags)
        ],
    }


def _payload(competitions, slug="mens-singles", event_name="US Open"):
    return {
        "events": [{
            "name": event_name,
            "groupings": [{
                "grouping": {"slug": slug},
                "competitions": competitions,
            }],
        }]
    }


def _games(*values):
    return [{"value": float(v)} for v in values]


# ── lines that carry ESPN's own per-set winner flag (lane1/064) ──
#
# `_games` predates the score write and deliberately keeps its flagless shape:
# it exists to prove `play_refutes_upcoming` fires on a game being on the board,
# which is a question about the VALUE. The score is counted off the FLAG, so the
# fixtures that exercise it have to carry one.


def _won(*values):
    """A side's line where it took every set listed."""
    return [{"value": float(v), "winner": True} for v in values]


def _lost(*values):
    return [{"value": float(v), "winner": False} for v in values]


def _mixed(*pairs):
    """``(games, won)`` per set — a retirement's line, where the abandoned set
    is flagged for nobody."""
    return [{"value": float(v), "winner": w} for v, w in pairs]


# ═══════════════════════════ the board read ═══════════════════════════


class TestScoreboardCompetitions:
    def test_enumerates_every_singles_competition_regardless_of_state(self):
        """`parse_results` drops `post` from its map deliberately; the anchor
        cannot, because the finished matches are most of what needs anchoring."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["A One", "B Two"], state="post"),
            _competition("2", ["C Three", "D Four"], state="pre"),
            _competition("3", ["E Five", "F Six"], state="in"),
        ])])
        assert {c["espn_competition_id"] for c in board} == {"1", "2", "3"}
        assert {c["state"] for c in board} == {"decided", "upcoming", "in_progress"}

    def test_is_not_scoped_to_a_tournament_name(self):
        """The anchor has no ESPN event string to filter on — our rows carry a
        sport key and two player names, never `"US Open"`."""
        board = scoreboard_competitions([
            _payload([_competition("1", ["A One", "B Two"])], event_name="Whatever Cup")
        ])
        assert [c["espn_competition_id"] for c in board] == ["1"]
        assert board[0]["event_name"] == "Whatever Cup"

    def test_doubles_are_excluded(self):
        """The anchor reads the two SINGLES groupings and nothing else.

        The reason used to be written as "a doubles competition names a TEAM and
        no athlete, which is a half-pair". That stopped being the reason at
        #4124 — a pair is a named, identified side now — and this test would
        still have passed, on the actual reason: ``scoreboard_competitions``
        defaults to :data:`SINGLES_SLUGS` and never looks in the doubles
        grouping. The anchor's scope is a deliberate choice, not a side effect
        of a read that could not see them."""
        board = scoreboard_competitions([
            _payload([_competition("1", ["A One", "B Two"])], slug="mens-doubles")
        ])
        assert board == []

    def test_duplicate_competition_across_tours_is_read_once(self):
        """The US Open appears under BOTH `atp` and `wta` with the same ids."""
        comp = _competition("1", ["A One", "B Two"])
        board = scoreboard_competitions([_payload([comp]), _payload([comp])])
        assert len(board) == 1

    def test_play_refutes_upcoming_is_already_folded_in(self):
        """lane1/054's clause, so the anchor consumer and the hub card cannot
        disagree about whether a match is being played."""
        board = scoreboard_competitions([_payload([
            _competition(
                "1", ["A One", "B Two"], state="pre", period=4,
                linescores=[_games(6, 3, 6, 2), _games(3, 6, 2, 1)],
            ),
        ])])
        assert board[0]["state"] == "in_progress"

    def test_upcoming_with_no_games_stays_upcoming(self):
        """The 238-row control: a fixture that has not started is not refutable."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["A One", "B Two"], state="pre"),
        ])])
        assert board[0]["state"] == "upcoming"

    def test_unknown_state_is_carried_as_none_not_dropped(self):
        """Identity does not depend on state — the row is still anchorable, and
        the authority write must be able to tell "a word we don't know" from
        "not on the board" (gotcha #53)."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["A One", "B Two"], state="halftime-of-tennis"),
        ])])
        assert len(board) == 1
        assert board[0]["state"] is None

    def test_carries_the_tbd_flag_off_short_detail(self):
        board = scoreboard_competitions([_payload([
            _competition("1", ["A One", "B Two"], short_detail="TBD"),
        ])])
        assert board[0]["start_is_tbd"] is True


# ═══════════════════════════ the three passes ═══════════════════════════


class TestAnchorPasses:
    def test_pass1_exact_pair_key(self):
        board = scoreboard_competitions([_payload([
            _competition("1", ["Jacob Fearnley", "Roberto Carballes Baena"]),
        ])])
        receipt = anchor_receipt(["Roberto Carballes Baena", "Jacob Fearnley"], board)
        assert receipt["espn_competition_id"] == "1"
        assert receipt["method"] == MATCH_EXACT_PAIR

    @pytest.mark.parametrize("ours,theirs", [
        # Word order — ESPN and Odds API genuinely disagree on the leading token.
        (["Iga Swiatek", "Xiyu Wang"], ["Wang Xiyu", "Iga Swiatek"]),
        (["Juncheng Shang", "Marco Trungelliti"], ["Marco Trungelliti", "Shang Juncheng"]),
        # A middle name one side drops.
        (["Aryna Sabalenka", "Maria Camila Osorio Serrano"], ["Camila Osorio", "Aryna Sabalenka"]),
        # A suffix.
        (["Martin Damm Jr.", "Frances Tiafoe"], ["Frances Tiafoe", "Martin Damm"]),
    ])
    def test_pass2_name_variants_that_are_one_person(self, ours, theirs):
        """All 13 real cases from the 2026-09-02 board reduce to these shapes."""
        board = scoreboard_competitions([_payload([_competition("1", theirs)])])
        receipt = anchor_receipt(ours, board)
        assert receipt["espn_competition_id"] == "1"
        assert receipt["method"] == MATCH_NAMES_AGREE

    @pytest.mark.parametrize("ours,theirs", [
        # A transliteration: neither is a prefix of the other.
        (["Dino Prizmic", "Alexander Shevchenko"], ["Aleksandr Shevchenko", "Dino Prizmic"]),
        # A diminutive.
        (["Anouk Koevermans", "Caty McNally"], ["Catherine McNally", "Anouk Koevermans"]),
    ])
    def test_pass3_pairing_rescues_what_no_name_rule_can(self, ours, theirs):
        board = scoreboard_competitions([_payload([_competition("1", theirs)])])
        receipt = anchor_receipt(ours, board)
        assert receipt["espn_competition_id"] == "1"
        assert receipt["method"] == MATCH_PAIRING_ANCHORED

    def test_pass3_does_not_rescue_a_shared_surname_alone(self):
        """The strong side must AGREE, not merely share a name-part — otherwise
        pass 3 would join two different people with the same surname."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["Francisco Cerundolo", "Casper Ruud"]),
        ])])
        receipt = anchor_receipt(["Juan Manuel Cerundolo", "Novak Djokovic"], board)
        assert receipt["espn_competition_id"] is None


class TestAnchorRefusals:
    def test_a_player_not_in_the_draw_is_named(self):
        """THE RECEIPT THAT MAKES A REFUSAL ACTIONABLE — all four real refusals
        on 2026-09-02 were this, e.g. Cerundolo v Ruud with Ruud absent."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["Arthur Gea", "Juan Manuel Cerundolo"]),
        ])])
        receipt = anchor_receipt(["Juan Manuel Cerundolo", "Casper Ruud"], board)
        assert receipt["espn_competition_id"] is None
        assert receipt["reason"] == REJECT_NO_CANDIDATE
        assert receipt["absent_players"] == ["Casper Ruud"]

    def test_a_fabricated_pairing_is_never_anchored_to_the_opponents_real_match(self):
        """The whole reason the matcher may not be loosened: anchoring here
        would let the authority write Gea's score onto our wrong fixture."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["Arthur Gea", "Juan Manuel Cerundolo"], state="post"),
        ])])
        assert anchor_receipt(
            ["Juan Manuel Cerundolo", "Casper Ruud"], board
        )["espn_competition_id"] is None

    def test_two_candidates_refuse_rather_than_pick(self):
        board = scoreboard_competitions([_payload([
            _competition("1", ["A Player", "B Player"]),
            _competition("2", ["A Player", "B Player"]),
        ])])
        receipt = anchor_receipt(["A Player", "B Player"], board)
        assert receipt["espn_competition_id"] is None
        assert receipt["reason"] == REJECT_AMBIGUOUS
        assert sorted(receipt["candidates"]) == ["1", "2"]

    def test_ambiguity_stops_the_search_and_does_not_fall_through(self):
        """A later pass is strictly more permissive, so it can only find MORE of
        the same collision. Falling through would turn two candidates into a
        coin flip."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["A Player", "B Player"]),
            _competition("2", ["A Player", "B Player"]),
            _competition("3", ["A Player", "B Playerson"]),
        ])])
        receipt = anchor_receipt(["A Player", "B Player"], board)
        assert receipt["reason"] == REJECT_AMBIGUOUS
        assert receipt["method"] == MATCH_EXACT_PAIR

    def test_draw_placeholders_never_collide_into_one_slot(self):
        """56 of the board's 478 singles competitions were `TBD v TBD` — the
        ONLY pair_key collision on it."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["Jacob Fearnley", "Dino Prizmic"]),
            _competition("2", ["TBD", "TBD"]),
            _competition("3", ["TBD", "TBD"]),
        ])])
        # Never anchored, and — the point — never ANCHORED TO EACH OTHER: the
        # two placeholders share a pair key and would otherwise be the board's
        # only collision.
        receipt = anchor_receipt(["TBD", "TBD"], board)
        assert receipt["espn_competition_id"] is None
        assert receipt["candidates"] == []
        # And the real fixture beside them is unaffected.
        assert anchor_receipt(
            ["Jacob Fearnley", "Dino Prizmic"], board
        )["espn_competition_id"] == "1"
        assert is_placeholder_pairing(["Qualifier", "Bye"]) is True

    def test_an_empty_board_is_authority_dark_not_a_bad_fixture(self):
        """gotcha #53 — a scoreboard we failed to fetch and a tournament with no
        matches produce the same empty list, and neither is evidence."""
        receipt = anchor_receipt(["A Player", "B Player"], [])
        assert receipt["reason"] == REJECT_EMPTY_BOARD
        assert receipt["absent_players"] == []

    def test_an_event_missing_a_name_says_so(self):
        board = scoreboard_competitions([_payload([
            _competition("1", ["A Player", "B Player"]),
        ])])
        assert anchor_receipt(["A Player", None], board)["reason"] == REJECT_UNNAMED_EVENT

    def test_a_half_named_competition_is_not_a_candidate(self):
        """`pairing_agrees` treats silence as agreement, which is right for
        contradiction and would make a matcher anchor to the first hole."""
        board = scoreboard_competitions([_payload([
            {
                "id": "1",
                "date": "2026-09-02T16:40Z",
                "status": {"period": 1, "type": {"name": "S", "state": "pre",
                                                 "detail": "d", "shortDetail": ""}},
                "competitors": [_competitor("A Player"), {"type": "team"}],
            },
        ])])
        assert anchor_receipt(["A Player", "B Player"], board)["reason"] == REJECT_EMPTY_BOARD


class TestNameComparators:
    def test_shares_substantial_token_is_exact_not_prefix(self):
        """The prefix rule is safe when BOTH names must agree and is a wildcard
        when only one does — pass 3's weaker half must not inherit it."""
        assert shares_substantial_token("Caty McNally", "Catherine McNally") is True
        assert shares_substantial_token("Marin Cilic", "Andrey Rublev") is False
        # `cil` is a PREFIX of `cilic` and would pass `token_covered`; exact
        # equality is what keeps pass 3's weaker half from being a wildcard.
        assert shares_substantial_token("Cil Xavier", "Cilic Xander") is False

    def test_short_tokens_cannot_anchor(self):
        assert shares_substantial_token("A B", "A B") is False

    def test_names_agree_survived_the_move_out_of_tournament_slate(self):
        assert names_agree("Bu Yunchaokete", "Yunchaokete Bu") is True
        assert names_agree("Francisco Cerundolo", "Juan Manuel Cerundolo") is False

    def test_pairing_matches_demands_two_real_names_on_both_sides(self):
        assert pairing_matches(["A One", "B Two"], ["B Two", "A One"]) is True
        assert pairing_matches(["A One", ""], ["B Two", "A One"]) is False
        assert pairing_matches(["A One"], ["A One", "B Two"]) is False

    def test_pairing_anchors_needs_a_substantial_token_on_the_strong_side_too(self):
        assert pairing_anchors(["Caty McNally", "Emma Navarro"],
                               ["Catherine McNally", "Emma Navarro"]) is True
        assert pairing_anchors(["A B", "Caty McNally"],
                               ["A B", "Catherine McNally"]) is False

    @pytest.mark.parametrize("ours", [
        ["Anouk Koevermans", "Caty McNally"],
        ["Caty McNally", "Anouk Koevermans"],
    ])
    @pytest.mark.parametrize("theirs", [
        ["Catherine McNally", "Anouk Koevermans"],
        ["Anouk Koevermans", "Catherine McNally"],
    ])
    def test_pairing_anchors_is_symmetric_in_both_sides(self, ours, theirs):
        """All four assignments, because the two sides play DIFFERENT roles here
        — one agrees, the other only shares a surname. The first version looped
        over `((0, 0), (0, 1))` and so only ever asked whether OUR FIRST name was
        the agreeing one: it linked this fixture written one way round and
        silently refused it written the other."""
        assert pairing_anchors(ours, theirs) is True


# ═══════════════════════════ the authority write ═══════════════════════════


class TestAuthorityWrite:
    def test_play_revokes_a_false_close(self):
        """THE CLAUSE THAT DID NOT EXIST ANYWHERE. `completed_at` was only ever
        written, never cleared — so nothing could say "the authority reports
        this match in progress, so the close was wrong"."""
        changes = authority_write(
            our_status="closed",
            our_completed_at="2026-09-02T09:00:00+00:00",
            our_commence_time=None,
            competition={"state": "in_progress", "date": None, "start_is_tbd": True},
        )
        assert changes["status"] == "live"
        assert changes["completed_at"] is None

    def test_the_live_and_completed_row_is_repaired(self):
        """Three US Open rows held both at 21:00Z (de Jong, Bergs, Jović). The
        serve layer resolves the pair as *completed*, which is how a card
        printed "Final" over a fourth set."""
        changes = authority_write(
            our_status="live",
            our_completed_at="2026-09-02T02:40:00+00:00",
            our_commence_time=None,
            competition={"state": "in_progress", "date": None, "start_is_tbd": True},
        )
        assert changes["completed_at"] is None
        assert "status" not in changes  # already live; only the close was wrong

    def test_decided_settles_an_unsettled_row(self):
        changes = authority_write(
            our_status="live", our_completed_at=None, our_commence_time=None,
            competition={"state": "decided", "date": None, "start_is_tbd": True},
        )
        assert changes["status"] == "completed"

    def test_decided_does_not_churn_closed_into_completed(self):
        """Both are settled; rewriting one as the other is history for no reader."""
        assert authority_write(
            our_status="closed", our_completed_at="2026-09-02T09:00:00+00:00",
            our_commence_time=None,
            competition={"state": "decided", "date": None, "start_is_tbd": True},
        ) == {}

    def test_decided_never_invents_completed_at_from_espns_start(self):
        """ESPN's `date` is when the match STARTED. A plausible end time is the
        value nothing ever questions (gotcha #22)."""
        changes = authority_write(
            our_status="live", our_completed_at=None, our_commence_time=None,
            competition={"state": "decided", "date": "2026-09-02T15:05Z",
                         "start_is_tbd": False},
        )
        assert "completed_at" not in changes

    def test_upcoming_never_demotes_a_live_row(self):
        """A match that has not begun and a match whose first game ESPN has not
        published are the same read — demoting on it would blank a real card."""
        changes = authority_write(
            our_status="live", our_completed_at=None,
            our_commence_time=None,
            competition={"state": "upcoming", "date": None, "start_is_tbd": True},
        )
        assert "status" not in changes

    def test_an_unknown_state_writes_nothing_at_all(self):
        """Not even the clock — a state we have no word for is not evidence."""
        assert authority_write(
            our_status="live", our_completed_at=None, our_commence_time=None,
            competition={"state": None, "date": "2026-09-02T15:05Z",
                         "start_is_tbd": False},
        ) == {}

    def test_commence_time_is_corrected_from_espns_clock(self):
        changes = authority_write(
            our_status="scheduled", our_completed_at=None,
            our_commence_time=_utc("2026-09-02T12:30:00+00:00"),
            competition={"state": "upcoming", "date": "2026-09-02T19:00Z",
                         "start_is_tbd": False},
        )
        assert changes["commence_time"] == _utc("2026-09-02T19:00:00+00:00")

    def test_the_tbd_placeholder_is_never_written_as_a_start(self):
        """04:00Z is midnight in Flushing Meadows — ESPN's stand-in for "some
        time that day", and what an elapsed-time rule then read as a start."""
        assert "commence_time" not in authority_write(
            our_status="scheduled", our_completed_at=None,
            our_commence_time=_utc("2026-09-02T12:30:00+00:00"),
            competition={"state": "upcoming", "date": "2026-08-30T04:00Z",
                         "start_is_tbd": True},
        )

    def test_a_correction_smaller_than_the_tolerance_does_not_churn(self):
        assert "commence_time" not in authority_write(
            our_status="scheduled", our_completed_at=None,
            our_commence_time=_utc("2026-09-02T19:01:00+00:00"),
            competition={"state": "upcoming", "date": "2026-09-02T19:00Z",
                         "start_is_tbd": False},
        )

    def test_a_correction_that_would_invert_the_completion_is_refused(self):
        """gotcha #46 — `completed_at >= commence_time` is an invariant, and
        manufacturing the violation here would trip the audit that hunts it."""
        assert "commence_time" not in authority_write(
            our_status="closed",
            our_completed_at=_utc("2026-09-02T10:00:00+00:00"),
            our_commence_time=_utc("2026-09-01T08:00:00+00:00"),
            competition={"state": "decided", "date": "2026-09-02T15:05Z",
                         "start_is_tbd": False},
        )

    def test_a_revoke_in_the_same_pass_frees_the_clock_correction(self):
        """The inversion guard must read the completion this row will HOLD, not
        the one it arrived with — otherwise a revoked close keeps blocking a
        correction that is no longer an inversion."""
        changes = authority_write(
            our_status="closed",
            our_completed_at=_utc("2026-09-02T10:00:00+00:00"),
            our_commence_time=_utc("2026-09-01T08:00:00+00:00"),
            competition={"state": "in_progress", "date": "2026-09-02T15:05Z",
                         "start_is_tbd": False},
        )
        assert changes["completed_at"] is None
        assert changes["commence_time"] == _utc("2026-09-02T15:05:00+00:00")


class TestStateContradiction:
    def test_live_and_completed_needs_no_authority(self):
        assert state_contradiction(
            "live", "2026-09-02T02:40:00+00:00", None
        ) == "live-and-completed"

    def test_settled_but_in_play_is_the_linette_row(self):
        """Served `closed` while ESPN scored her second set."""
        assert state_contradiction("closed", None, "in_progress") == "settled-but-in-play"

    def test_in_play_but_decided_is_a_stale_live_card(self):
        assert state_contradiction("live", None, "decided") == "in-play-but-decided"

    def test_agreement_is_silence(self):
        assert state_contradiction("live", None, "in_progress") is None
        assert state_contradiction("completed", "2026-09-02T02:40:00+00:00", "decided") is None
        assert state_contradiction("scheduled", None, "upcoming") is None

    def test_an_unknown_state_reports_no_authority_contradiction(self):
        assert state_contradiction("live", None, None) is None

    def test_but_the_self_contradiction_still_reports_without_a_state(self):
        """It needs no authority, so an unreadable board must not hide it."""
        assert state_contradiction(
            "live", "2026-09-02T02:40:00+00:00", None
        ) == "live-and-completed"


def _utc(value):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ═══════════════════ the tournament discriminator ═══════════════════


def _at(value):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class TestTournamentWindow:
    """The pair is a key WITHIN a draw, not across tournaments.

    Cerundolo and Gea met in Cincinnati AND at Flushing Meadows, so their pair
    key is one key for two matches. Ungated, 58 ESPN competitions were claimed
    by more than one of our events on 2026-09-02 — competition 182710 by four.
    """

    def test_same_pair_a_fortnight_earlier_is_a_different_match(self):
        board = scoreboard_competitions([_payload([
            _competition("182710", ["Arthur Gea", "Juan Manuel Cerundolo"],
                         date="2026-09-01T15:05Z"),
        ])])
        cincinnati = anchor_receipt(
            ["Juan Manuel Cerundolo", "Arthur Gea"], board,
            our_commence_time=_at("2026-08-18T15:05Z"),
        )
        assert cincinnati["espn_competition_id"] is None
        assert cincinnati["reason"] == "off-board"

    def test_the_same_match_still_anchors(self):
        board = scoreboard_competitions([_payload([
            _competition("182710", ["Arthur Gea", "Juan Manuel Cerundolo"],
                         date="2026-09-01T15:05Z"),
        ])])
        assert anchor_receipt(
            ["Juan Manuel Cerundolo", "Arthur Gea"], board,
            our_commence_time=_at("2026-09-01T17:30Z"),
        )["espn_competition_id"] == "182710"

    def test_the_widest_real_gap_is_kept(self):
        """Every one of the 190 US Open anchors sits within 1.47 days of ESPN's
        clock — the tail is the TBD placeholder at midnight ET."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["A One", "B Two"], date="2026-09-02T19:00Z"),
        ])])
        assert anchor_receipt(
            ["A One", "B Two"], board,
            our_commence_time=_at("2026-09-01T07:30Z"),  # 1.48 days
        )["espn_competition_id"] == "1"

    def test_an_unreadable_clock_never_narrows_the_pool(self):
        """A missing date is a fact about the read; letting it refuse would
        silently shrink the pool to nothing."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["A One", "B Two"], date=None),
        ])])
        assert anchor_receipt(
            ["A One", "B Two"], board, our_commence_time=_at("2026-01-01T00:00Z"),
        )["espn_competition_id"] == "1"

    def test_no_commence_time_disables_the_gate(self):
        board = scoreboard_competitions([_payload([
            _competition("1", ["A One", "B Two"], date="2026-09-02T19:00Z"),
        ])])
        assert anchor_receipt(
            ["A One", "B Two"], board, our_commence_time=None,
        )["espn_competition_id"] == "1"

    def test_off_board_is_reported_separately_from_a_fabricated_pairing(self):
        """Both players elsewhere = another tournament. One player absent while
        the opponent is right here = the fixture is wrong. Collapsing them is
        how 495 ordinary rows would read as 495 defects."""
        board = scoreboard_competitions([_payload([
            _competition("1", ["Arthur Gea", "Juan Manuel Cerundolo"]),
        ])])
        off = anchor_receipt(["Some Body", "Other Person"], board)
        assert off["reason"] == "off-board"
        fabricated = anchor_receipt(["Juan Manuel Cerundolo", "Casper Ruud"], board)
        assert fabricated["reason"] == REJECT_NO_CANDIDATE
        assert fabricated["absent_players"] == ["Casper Ruud"]


class TestAnchorableSportKeys:
    def test_only_buckets_naming_a_tournament_on_the_board(self):
        from app.utils.espn_tennis_anchor import anchorable_sport_keys

        board = scoreboard_competitions([_payload([
            _competition("1", ["A One", "B Two"]),
        ])])  # event_name defaults to "US Open"
        assert anchorable_sport_keys([
            "tennis_atp", "tennis_other", "tennis_wta",
            "tennis_atp_us_open", "tennis_wta_us_open",
            "tennis_atp_cincinnati_open",
        ], board) == ["tennis_atp_us_open", "tennis_wta_us_open"]

    def test_a_generic_bucket_names_no_tournament(self):
        from app.utils.espn_tennis_anchor import tournament_token

        assert tournament_token("tennis_atp") is None
        assert tournament_token("tennis_other") is None
        assert tournament_token("tennis_atp_us_open") == "usopen"
        assert tournament_token(None) is None

    def test_an_empty_board_anchors_no_bucket(self):
        from app.utils.espn_tennis_anchor import anchorable_sport_keys

        assert anchorable_sport_keys(["tennis_atp_us_open"], []) == []


# ═══════════════════ the task body: what actually gets written ═══════════════════


class _Event:
    """Just enough of an `events` row for the write path."""

    def __init__(self, id, home, away, status, commence_time, completed_at=None,
                 espn_id=None, home_score=None, away_score=None,
                 box_score_data=None, win_probability_sources=None,
                 commence_time_source=None):
        self.id = id
        self.home_team_name = home
        self.away_team_name = away
        self.status = status
        self.commence_time = commence_time
        self.completed_at = completed_at
        self.espn_id = espn_id
        # lane1/064: the score half of the authority write. Present on the stub
        # because the task READS them before deciding, so a row without them
        # would be swallowed by the per-row `except` and counted as a row error
        # rather than exercising anything.
        self.home_score = home_score
        self.away_score = away_score
        # live/073: the games line rides in `box_score_data`. On the stub for
        # the same reason the scores are — the task READS it before deciding,
        # and a stub without it turns every row of every test in this file into
        # a row error that the per-row `except` swallows.
        self.box_score_data = box_score_data
        # live/203: the #5324 authority hold rides in this JSONB, and the task
        # READS it before deciding — so it is on the stub for the third time
        # this class has learned the same lesson. Without it every row in this
        # file becomes an `AttributeError` the per-row `except` swallows, which
        # reads as a row error rather than as a missing column.
        self.win_probability_sources = win_probability_sources
        # live/204: the FOURTH column this class has learned the same lesson
        # about (#5971). The task reads it before deciding whether the clock
        # correction is even allowed, and writes it back beside the value — so
        # a stub without it makes every row an `AttributeError` the per-row
        # `except` swallows, which reads as a row error and not as the missing
        # column it is. That is exactly how it presented: seven tests in this
        # file went red with "fixture drifted", none of them naming the field.
        self.commence_time_source = commence_time_source


class _Result:
    def __init__(self, rows, scalar=True):
        self._rows = rows
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Session:
    """Answers the SELECTs the task makes: sport keys, events, then the
    `espn_id_holder` lookup `stamp_espn_id_if_unheld` runs per stamp.

    `holders` maps an espn_id to the event already holding it, so the
    database-level refusal can be exercised.
    """

    def __init__(self, sport_keys, events, holders=None):
        self._answers = [_Result([(k,) for k in sport_keys]), _Result(events)]
        self._holders = holders or {}
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, statement, *a, **kw):
        if self._answers:
            return self._answers.pop(0)
        # The holder probe: `select(Event.id).where(Event.espn_id == <id>)`.
        bound = [
            str(value)
            for value in statement.compile().params.values()
            if value is not None
        ]
        for value in bound:
            if value in self._holders:
                return _Result([self._holders[value]])
        return _Result([])

    async def commit(self):
        self.committed = True


def _install(monkeypatch, *, payloads, errors, sport_keys, events, holders=None):
    from app.services import espn_tennis as svc
    from app.tasks import espn_sync

    session = _Session(sport_keys, events, holders)
    monkeypatch.setattr(svc, "fetch_scoreboards", lambda dates=None: (payloads, errors))
    monkeypatch.setattr(espn_sync, "get_task_session", lambda: session)
    return session


class TestTennisSyncTask:
    async def test_the_revoke_reaches_the_database(self, monkeypatch):
        """END TO END for the ship: a row we call settled, which the authority is
        scoring, comes out live with its close cleared."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            15295881, "Magda Linette", "Francesca Jones", "closed",
            _at("2026-09-02T15:00Z"), completed_at=_at("2026-09-02T09:00Z"),
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182600", ["Magda Linette", "Francesca Jones"], state="pre", period=2,
                date="2026-09-02T15:00Z",
                linescores=[_games(6, 3), _games(4, 2)],  # play refutes `pre`
            )])],
            errors=[],
            sport_keys=["tennis_wta_us_open", "tennis_wta"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert event.espn_id == "182600"
        assert event.status == "live"
        assert event.completed_at is None
        assert stats["completions_revoked"] == 1
        assert stats["contradictions"] == {"settled-but-in-play": 1}

    async def test_the_blank_final_gets_its_score(self, monkeypatch):
        """END TO END for lane1/064's ship: a settled US Open row that printed
        nothing comes out holding the result, WITHOUT its status being churned.

        Shaped on 15293821 / ESPN 182705 — Alcaraz d. Safiullin 6-4, 6-4, 6-4,
        one of 37 rows on production `closed` and blank while the authority held
        the full result. Note the orientation: ESPN lists the WINNER first and
        our row has Safiullin at home, so a straight read publishes 3-0 to the
        man who lost.
        """
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            15293821, "Roman Safiullin", "Carlos Alcaraz", "closed",
            _at("2026-08-30T15:00Z"), completed_at=_at("2026-08-30T19:42Z"),
            espn_id="182705",
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182705", ["Carlos Alcaraz", "Roman Safiullin"], state="post",
                status_name="STATUS_FINAL", period=3,
                date="2026-08-30T19:30Z",
                linescores=[
                    _won(6, 6, 6),      # Alcaraz took all three
                    _lost(4, 4, 4),
                ],
                winners=[True, False],
            )])],
            errors=[],
            sport_keys=["tennis_atp_us_open"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert (event.home_score, event.away_score) == (0, 3)
        assert event.status == "closed"       # settled stays settled
        assert stats["score_writes"] == 1
        assert stats["score_blanks_filled"] == 1
        assert stats["score_corrections"] == 0
        assert stats["status_writes"] == 0

    async def test_a_row_that_already_agrees_is_left_alone(self, monkeypatch):
        """THE CONTROL for the test above — 122 of the 202 anchored rows are
        already right, and this pass runs every ten minutes."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            15293821, "Roman Safiullin", "Carlos Alcaraz", "completed",
            _at("2026-08-30T19:30Z"), completed_at=_at("2026-08-30T22:00Z"),
            espn_id="182705", home_score=0, away_score=3,
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182705", ["Carlos Alcaraz", "Roman Safiullin"], state="post",
                status_name="STATUS_FINAL", period=3,
                date="2026-08-30T19:30Z",
                linescores=[_won(6, 6, 6), _lost(4, 4, 4)],
                winners=[True, False],
            )])],
            errors=[],
            sport_keys=["tennis_atp_us_open"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert (event.home_score, event.away_score) == (0, 3)
        assert stats["score_writes"] == 0
        assert stats["score_refused"] == {}

    async def test_the_settled_row_gets_the_games_it_was_won_by(self, monkeypatch):
        """END TO END for live/073's ship: the same anchored row that gets its
        set score comes out holding the per-set GAMES, so the match page can
        stop saying "we did not record the games played".

        Note this fires on the row of the CONTROL above — a row whose set score
        the authority already agrees with, which writes nothing else.  That is
        the population: 207 of 211 settled tennis rows are anchored and 0 held
        a box score, and most of them are already correctly scored.  A line
        write gated on a score change would have reached almost none of them.
        """
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            15293821, "Roman Safiullin", "Carlos Alcaraz", "completed",
            _at("2026-08-30T19:30Z"), completed_at=_at("2026-08-30T22:00Z"),
            espn_id="182705", home_score=0, away_score=3,
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182705", ["Carlos Alcaraz", "Roman Safiullin"], state="post",
                status_name="STATUS_FINAL", period=3,
                date="2026-08-30T19:30Z",
                linescores=[_won(6, 6, 6), _lost(4, 4, 4)],
                winners=[True, False],
            )])],
            errors=[],
            sport_keys=["tennis_atp_us_open"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        # OUR order: Safiullin is home and lost every set 4-6.
        assert event.box_score_data == {"tennis": {
            "sets": [[4, 6], [4, 6], [4, 6]],
            "home_games": 12,
            "away_games": 18,
            "source": "espn",
        }}
        assert stats["line_writes"] == 1
        assert stats["score_writes"] == 0     # the control still holds

    async def test_the_second_pass_writes_the_line_again_to_nobody(
        self, monkeypatch
    ):
        """THE CONTROL for the ship. This pass runs on a beat; a row already
        holding the line must not be rewritten every cycle."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            15293821, "Roman Safiullin", "Carlos Alcaraz", "completed",
            _at("2026-08-30T19:30Z"), completed_at=_at("2026-08-30T22:00Z"),
            espn_id="182705", home_score=0, away_score=3,
            box_score_data={"tennis": {
                "sets": [[4, 6], [4, 6], [4, 6]],
                "home_games": 12,
                "away_games": 18,
                "source": "espn",
            }},
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182705", ["Carlos Alcaraz", "Roman Safiullin"], state="post",
                status_name="STATUS_FINAL", period=3,
                date="2026-08-30T19:30Z",
                linescores=[_won(6, 6, 6), _lost(4, 4, 4)],
                winners=[True, False],
            )])],
            errors=[],
            sport_keys=["tennis_atp_us_open"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["line_writes"] == 0
        assert stats["line_refused"] == {}

    async def test_a_retirement_the_authority_cannot_score_is_reported(
        self, monkeypatch
    ):
        """A refusal is a finding.  Shaped on 184685: the side ESPN flags as the
        winner holds NO set flags, so a set count published here names the man
        who lost as ahead."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            1, "Christopher O'Connell", "Zsombor Piros", "closed",
            _at("2026-08-26T15:00Z"), espn_id="184685",
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "184685", ["Christopher O'Connell", "Zsombor Piros"],
                state="post", status_name="STATUS_RETIRED", period=2,
                date="2026-08-26T15:30Z",
                linescores=[_mixed((7, True), (6, False)),
                            _mixed((5, False), (7, False))],
                winners=[False, True],
            )])],
            errors=[],
            sport_keys=["tennis_atp_us_open"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert event.home_score is None and event.away_score is None
        assert stats["score_writes"] == 0
        assert stats["score_refused"] == {"not-a-completed-result": 1}
        # live/073: THE LINE RIDES THE SCORE. A row the authority will not score
        # gets no games line either — a set-by-set line under a hero with no
        # result at all is half an answer, and the refusal is reported by the
        # same name rather than counted as a silent skip.
        assert event.box_score_data is None
        assert stats["line_writes"] == 0
        assert stats["line_refused"] == {"not-a-completed-result": 1}

    async def test_a_contested_competition_anchors_nobody(self, monkeypatch):
        """Writing the id on both twins would ARM `merge-duplicate-events`, which
        DELETEs the loser of any same-sport pair sharing a provider id."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        twin_a = _Event(1, "A One", "B Two", "scheduled", _at("2026-09-02T15:00Z"))
        twin_b = _Event(2, "A One", "B Two", "scheduled", _at("2026-09-02T15:30Z"))
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182600", ["A One", "B Two"], date="2026-09-02T15:00Z")])],
            errors=[],
            sport_keys=["tennis_atp_us_open"],
            events=[twin_a, twin_b],
        )

        stats = await _sync_tennis_from_espn()

        assert twin_a.espn_id is None and twin_b.espn_id is None
        assert stats["anchored"] == 0
        assert stats["contested_competitions"] == 1
        assert stats["contested_events"] == 2
        assert stats["contested_detail"] == {"182600": [1, 2]}

    async def test_a_dark_authority_touches_nothing(self, monkeypatch):
        """gotcha #53 — both tours failing is a fact about the read."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(1, "A One", "B Two", "live", _at("2026-09-02T15:00Z"),
                       completed_at=_at("2026-09-02T09:00Z"))
        _install(monkeypatch, payloads=[], errors=["atp: boom", "wta: boom"],
                 sport_keys=["tennis_atp_us_open"], events=[event])

        stats = await _sync_tennis_from_espn()

        assert stats["status"] == "authority_dark"
        assert event.completed_at is not None
        assert event.espn_id is None

    async def test_a_board_with_no_matching_bucket_writes_nothing(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        _install(
            monkeypatch,
            payloads=[_payload([_competition("1", ["A One", "B Two"])],
                               event_name="Laver Cup")],
            errors=[],
            sport_keys=["tennis_atp_us_open", "tennis_atp"],
            events=[],
        )
        stats = await _sync_tennis_from_espn()
        assert stats["status"] == "no_matching_bucket"

    async def test_one_bad_row_never_costs_the_pass_its_siblings(self, monkeypatch):
        """gotcha #42."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        class _Exploding(_Event):
            @property
            def home_team_name(self):
                raise RuntimeError("unreadable row")

            @home_team_name.setter
            def home_team_name(self, v):
                pass

        good = _Event(2, "A One", "B Two", "scheduled", _at("2026-09-02T15:00Z"))
        bad = _Exploding(1, "x", "y", "scheduled", _at("2026-09-02T15:00Z"))
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182600", ["A One", "B Two"], date="2026-09-02T15:00Z")])],
            errors=[],
            sport_keys=["tennis_atp_us_open"],
            events=[bad, good],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["row_errors"] == 1
        assert good.espn_id == "182600"

    async def test_a_twin_outside_this_pass_already_holding_the_id_refuses(
        self, monkeypatch
    ):
        """THE GAP THE IN-PASS CHECK CANNOT SEE, and the reason the write goes
        through `stamp_espn_id_if_unheld` (#2017, ruling 042).

        The contested pass only knows the rows THIS task selected, and a US Open
        row's twin lives in `tennis_atp` — a bucket the rail deliberately does
        not query. `ix_events_espn_id` is not UNIQUE, so nothing in the database
        would refuse the contradiction either.
        """
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(15293826, "A One", "B Two", "scheduled",
                       _at("2026-09-02T15:00Z"))
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182600", ["A One", "B Two"], date="2026-09-02T15:00Z")])],
            errors=[],
            sport_keys=["tennis_atp_us_open"],
            events=[event],
            holders={"182600": 99999},  # a `tennis_atp` twin already holds it
        )

        stats = await _sync_tennis_from_espn()

        assert event.espn_id is None
        assert stats["anchored"] == 0
        assert stats["stamp_refused"] == 1
        assert stats["stamp_refused_holders"] == {"15293826": 99999}
        # And no state was written through a link that does not exist.
        assert event.status == "scheduled"


class TestNotStartedIsAStatementNotASilence:
    """`upcoming` alone says nothing; `upcoming` with a future clock says a lot.

    Measured 2026-09-02T22:22Z: ESPN had 11 US Open singles in play and we called
    14 live. One was already decided; the other two — Wu Yibing v Duckworth and
    Navone v Berrettini — were both scheduled for 23:00Z with zero games on the
    board. We were showing two matches as live 37 minutes before they began.
    """

    NOW = None  # set in setup_method to a fixed instant, never the wall clock

    def setup_method(self):
        self.NOW = _at("2026-09-02T22:22Z")

    def _upcoming(self, date, tbd=False):
        return {"state": "upcoming", "date": date, "start_is_tbd": tbd}

    def test_a_future_start_demotes_a_live_row(self):
        changes = authority_write(
            our_status="live", our_completed_at=None, our_commence_time=None,
            competition=self._upcoming("2026-09-02T23:00Z"), now=self.NOW,
        )
        assert changes["status"] == "scheduled"

    def test_and_clears_a_completion_that_cannot_exist_yet(self):
        changes = authority_write(
            our_status="live", our_completed_at=_at("2026-09-02T09:00Z"),
            our_commence_time=None,
            competition=self._upcoming("2026-09-02T23:00Z"), now=self.NOW,
        )
        assert changes["completed_at"] is None

    def test_a_LAGGING_board_never_demotes(self):
        """THE CONTROL, and the reason this clause is safe. A match already under
        way that ESPN has not caught up on has a start in the PAST — the only
        shape the old, silence-based rule could not distinguish."""
        changes = authority_write(
            our_status="live", our_completed_at=None, our_commence_time=None,
            competition=self._upcoming("2026-09-02T21:00Z"), now=self.NOW,
        )
        assert "status" not in changes

    def test_a_tbd_placeholder_never_demotes(self):
        """04:00Z is midnight in Flushing Meadows, not a start."""
        changes = authority_write(
            our_status="live", our_completed_at=None, our_commence_time=None,
            competition=self._upcoming("2026-09-03T04:00Z", tbd=True), now=self.NOW,
        )
        assert "status" not in changes

    def test_no_clock_no_demotion(self):
        assert "status" not in authority_write(
            our_status="live", our_completed_at=None, our_commence_time=None,
            competition=self._upcoming("2026-09-02T23:00Z"), now=None,
        )

    def test_a_scheduled_row_is_left_alone(self):
        assert "status" not in authority_write(
            our_status="scheduled", our_completed_at=None, our_commence_time=None,
            competition=self._upcoming("2026-09-02T23:00Z"), now=self.NOW,
        )

    def test_the_contradiction_is_reported_on_the_same_rule(self):
        assert state_contradiction(
            "live", None, "upcoming",
            competition=self._upcoming("2026-09-02T23:00Z"), now=self.NOW,
        ) == "in-play-but-not-started"

    def test_and_stays_quiet_on_a_lagging_board(self):
        """A needle that cried wolf every session start would be turned off."""
        assert state_contradiction(
            "live", None, "upcoming",
            competition=self._upcoming("2026-09-02T21:00Z"), now=self.NOW,
        ) is None

    def test_without_a_clock_the_class_is_not_judged(self):
        assert state_contradiction("live", None, "upcoming") is None


class TestTheInPlayLineIsStampedByTheTask:
    """#3242 END TO END: the stamp is only worth anything if the PASS writes it.

    `games_line_write` takes `observed_at` as an optional argument, and an
    optional argument the one caller that matters forgets to pass is a feature
    that is green in every unit test and dead on the site. So this drives the
    real task and reads the column it wrote.
    """

    async def test_a_live_match_comes_out_of_the_pass_stamped(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            15303395, "Anastasia Potapova", "Amanda Anisimova", "live",
            _at("2026-09-05T15:04Z"), espn_id="182540",
            home_score=0, away_score=0,
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182540", ["Anastasia Potapova", "Amanda Anisimova"],
                state="in", status_name="STATUS_IN_PROGRESS", period=1,
                date="2026-09-05T15:04Z",
                # A set IN PROGRESS at 0-1: neither side has won it, so no
                # winner flag. That is the exact shape #3242 measured.
                linescores=[_mixed((0, None)), _mixed((1, None))],
            )])],
            errors=[],
            sport_keys=["tennis_wta_us_open", "tennis_wta"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        line = (event.box_score_data or {})["tennis"]
        assert line["sets"] == [[0, 1]]
        stamp = line.get("observed_at")
        assert stamp, (
            "the pass wrote a games line with no observation time, so the page "
            "has nothing to age and #3242's chip renders nothing"
        )
        # It is THIS pass's clock, not a leftover: parseable, timezone-aware,
        # and within a minute of now. Bounded rather than pinned because the
        # task reads the wall clock and a fixed assertion could not pass.
        parsed = datetime.fromisoformat(stamp)
        assert parsed.tzinfo is not None
        assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 60
        assert stats["line_writes"] == 1

    async def test_a_settled_match_comes_out_of_the_pass_unstamped(self, monkeypatch):
        """The control. A decided row must not be stamped, or every settled
        tennis page grows a freshness chip that ages forever."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            15293821, "Roman Safiullin", "Carlos Alcaraz", "closed",
            _at("2026-08-30T15:00Z"), completed_at=_at("2026-08-30T19:42Z"),
            espn_id="182705", home_score=0, away_score=3,
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182705", ["Carlos Alcaraz", "Roman Safiullin"],
                state="post", status_name="STATUS_FINAL", period=3,
                date="2026-08-30T19:30Z",
                linescores=[_won(6, 6, 6), _lost(4, 3, 2)],
                winners=[True, False],
            )])],
            errors=[],
            sport_keys=["tennis_atp_us_open", "tennis_atp"],
            events=[event],
        )

        await _sync_tennis_from_espn()

        line = (event.box_score_data or {}).get("tennis")
        assert line is not None, "fixture drifted: this row is supposed to get a line"
        assert "observed_at" not in line


# ═══════════ the authority hold reaches tennis (#5324, live/203) ═══════════


class TestTennisCarriesTheAuthorityHold:
    """The US Open men's final read LIVE 0-0 for ten and a half minutes.

    Measured on production 2026-09-13, event 15310688 (Zverev v Shelton),
    anchored ``espn_id`` 182677, with ESPN's own listing read in the same
    command as our row:

    ========================  ==========  ==========  ============
    time (UTC)                ours        ESPN        #5324 hold
    ========================  ==========  ==========  ============
    18:00:00 - 18:10:13       live 0-0    SCHEDULED   absent
    18:10:33 - 18:15:16       scheduled   SCHEDULED   absent
    18:15:38 - 18:17:09       live 0-0    SCHEDULED   absent
    ========================  ==========  ==========  ============

    ``#5324`` stamps the authority's statement into ``win_probability_sources``
    and ``_transition_event_statuses_impl`` honours it, but that stamp lived
    only in the main ESPN board loop.  Tennis comes through
    :func:`authority_write`, which wrote the status and nothing else — and a
    status-only demotion buys one minute, which is why the row above was
    demoted at 18:10:33 and promoted straight back at 18:15:38.

    The sport whose starts slide most was the one sport the hold could not
    reach.  These tests are that gap, in both directions.
    """

    _UPCOMING = {"state": "upcoming", "date": "2026-09-13T18:15Z",
                 "start_is_tbd": False}

    def test_THE_SPECIMEN_a_live_row_the_authority_says_has_not_begun_is_HELD(self):
        """The men's final at 18:00Z: demoted AND stamped, not demoted alone."""
        changes = authority_write(
            our_status="live", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:00:00+00:00"),
            competition=self._UPCOMING,
            now=_utc("2026-09-13T18:05:00+00:00"),
            our_sources={"kalshi": {"probability": 0.59}},
            our_home_score=0, our_away_score=0,
        )
        assert changes["status"] == "scheduled"
        assert "espn_not_started_at" in changes["win_probability_sources"]
        # The demotion must not cost the row its prices.
        assert changes["win_probability_sources"]["kalshi"] == {"probability": 0.59}

    def test_THE_REACH_the_stamp_this_writes_is_one_the_PROMOTER_honours(self):
        """The join that makes this a fix rather than a new dict key.

        A stamp the clock promoter does not read would leave the page exactly
        as it was, so this asserts against
        :func:`authority_not_started_holds` itself — the predicate
        ``_transition_event_statuses_impl`` actually calls — rather than
        against the string we just wrote.
        """
        from app.utils.espn_helpers import authority_not_started_holds

        now = _utc("2026-09-13T18:10:33+00:00")
        changes = authority_write(
            our_status="live", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:00:00+00:00"),
            competition=self._UPCOMING, now=now,
            our_sources={}, our_home_score=0, our_away_score=0,
        )
        # 18:15:38Z — the promoter's next pass, the one that re-promoted it.
        assert authority_not_started_holds(
            changes["win_probability_sources"],
            _utc("2026-09-13T18:15:38+00:00"),
            home_score=0, away_score=0, period=None, game_clock=None,
        ) is True

    def test_THE_CONTROL_without_the_stamp_the_promoter_does_NOT_hold(self):
        """Pre-fix behaviour, pinned: this is why the row came back live."""
        from app.utils.espn_helpers import authority_not_started_holds

        assert authority_not_started_holds(
            {"kalshi": {"probability": 0.59}},
            _utc("2026-09-13T18:15:38+00:00"),
            home_score=0, away_score=0, period=None, game_clock=None,
        ) is False

    def test_the_SECOND_upcoming_pass_refreshes_rather_than_expires(self):
        """CERT-2782's lesson, which cost #5324 a whole revision.

        The row is already ``scheduled`` — there is nothing left to demote — so
        a stamp written only beside a status change would never be renewed, and
        the hold would lapse at its TTL under an authority still saying the
        match has not begun.  The start on this specimen slid 18:00 -> 18:05 ->
        18:15, so the renewal is the thing keeping the hold alive.
        """
        first = authority_write(
            our_status="live", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:00:00+00:00"),
            competition=self._UPCOMING,
            now=_utc("2026-09-13T18:05:00+00:00"),
            our_sources={}, our_home_score=0, our_away_score=0,
        )
        second = authority_write(
            our_status="scheduled", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:15:00+00:00"),
            competition=self._UPCOMING,
            now=_utc("2026-09-13T18:11:00+00:00"),
            our_sources=first["win_probability_sources"],
            our_home_score=0, our_away_score=0,
        )
        assert "status" not in second, "already scheduled; nothing to demote"
        assert (
            second["win_probability_sources"]["espn_not_started_at"]
            != first["win_probability_sources"]["espn_not_started_at"]
        ), "the repeated observation must REFRESH the stamp, not leave it to rot"

    def test_a_row_that_shows_PLAY_is_never_held(self):
        """THE ONE DEFINITION (`play_evidence`). A set on the board is play, and
        a hold stamped over it would be a claim the row itself refutes."""
        changes = authority_write(
            our_status="live", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:00:00+00:00"),
            competition=self._UPCOMING,
            now=_utc("2026-09-13T18:05:00+00:00"),
            our_sources={}, our_home_score=1, our_away_score=0,
        )
        assert "win_probability_sources" not in changes

    def test_positive_play_RETRACTS_the_hold(self):
        """Only evidence that the match HAS begun may clear it."""
        changes = authority_write(
            our_status="scheduled", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:15:00+00:00"),
            competition={"state": "in_progress", "date": None,
                         "start_is_tbd": True},
            now=_utc("2026-09-13T18:20:00+00:00"),
            our_sources={"espn_not_started_at": "2026-09-13T18:11:00+00:00",
                         "kalshi": {"probability": 0.59}},
        )
        assert changes["status"] == "live"
        assert "espn_not_started_at" not in changes["win_probability_sources"]
        assert changes["win_probability_sources"]["kalshi"] == {"probability": 0.59}

    def test_a_decided_match_does_not_keep_saying_it_has_not_begun(self):
        changes = authority_write(
            our_status="live", our_completed_at=None, our_commence_time=None,
            competition={"state": "decided", "date": None, "start_is_tbd": True},
            now=_utc("2026-09-13T20:30:00+00:00"),
            our_sources={"espn_not_started_at": "2026-09-13T18:11:00+00:00"},
        )
        assert changes["status"] == "completed"
        assert "espn_not_started_at" not in changes["win_probability_sources"]

    def test_SILENCE_RETRACTS_NOTHING_an_unknown_state_leaves_the_hold(self):
        """gotcha #53: an absent answer is not a negative answer."""
        assert authority_write(
            our_status="scheduled", our_completed_at=None, our_commence_time=None,
            competition={"state": None, "date": "2026-09-13T18:15Z",
                         "start_is_tbd": False},
            now=_utc("2026-09-13T18:11:00+00:00"),
            our_sources={"espn_not_started_at": "2026-09-13T18:11:00+00:00"},
        ) == {}

    def test_a_LAGGING_board_whose_start_has_passed_writes_no_hold(self):
        """`upcoming` with a start in the PAST is the scoreboard trailing a match
        already under way — the guard the demotion has always had, and the stamp
        inherits it rather than restating it."""
        changes = authority_write(
            our_status="live", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:15:00+00:00"),
            competition=self._UPCOMING,
            now=_utc("2026-09-13T19:00:00+00:00"),
            our_sources={}, our_home_score=0, our_away_score=0,
        )
        assert "win_probability_sources" not in changes
        assert "status" not in changes

    def test_a_TBD_start_is_not_a_statement_and_writes_no_hold(self):
        """Midnight ET is ESPN's stand-in for "some time that day"."""
        changes = authority_write(
            our_status="live", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:00:00+00:00"),
            competition={"state": "upcoming", "date": "2026-09-14T04:00Z",
                         "start_is_tbd": True},
            now=_utc("2026-09-13T18:05:00+00:00"),
            our_sources={}, our_home_score=0, our_away_score=0,
        )
        assert "win_probability_sources" not in changes

    def test_an_ordinary_playing_row_issues_no_pointless_write(self):
        """`clear_authority_not_started` returns the ORIGINAL when there is
        nothing to clear, so a live pass over a live match must not add a
        `win_probability_sources` key and dirty the row every 60 seconds."""
        changes = authority_write(
            our_status="live", our_completed_at=None, our_commence_time=None,
            competition={"state": "in_progress", "date": None,
                         "start_is_tbd": True},
            now=_utc("2026-09-13T19:00:00+00:00"),
            our_sources={"kalshi": {"probability": 0.59}},
        )
        assert "win_probability_sources" not in changes


class TestTheClockCorrectionCarriesItsProvenance:
    """#5971 — the value and the stamp move together, or the row ping-pongs.

    THE DEFECT IS DECIDABLE FROM THE ROW ALONE. On 2026-09-13 event 15310688
    (the US Open men's final) was read holding ESPN's ``18:13:40`` under
    ``commence_time_source = 'odds_api'``. That pair cannot both be true, and
    it is not cosmetic: ``event_registry.commence_time_write_authorized`` reads
    the STAMP, so an ESPN value wearing an ``odds_api`` stamp is one The Odds
    API may still revise as "a provider correcting its own record" (q066b) —
    back to the session-start default it publishes before an order of play
    exists. Measured consequence: 18:00 -> 18:15 -> 18:00 -> 18:15 -> 18:13:40
    in seventeen minutes, and the ``Since Start`` chart, which filters on
    ``commence_time``, silently dropped the first twelve minutes of the final
    while it was still being played.
    """

    def test_the_correction_stamps_espn(self):
        changes = authority_write(
            our_status="scheduled", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:00:00+00:00"),
            our_commence_time_source="odds_api",
            competition={"state": "upcoming", "date": "2026-09-13T18:15Z",
                         "start_is_tbd": False},
            now=_utc("2026-09-13T18:10:00+00:00"),
        )
        assert changes["commence_time"] == _utc("2026-09-13T18:15:00+00:00")
        assert changes["commence_time_source"] == "espn"

    def test_the_stamp_is_what_actually_stops_the_ping_pong(self):
        """THE MECHANISM, NOT THE FIELD.

        Asserting "a key is present" would pass against a stamp that changed
        nothing. So this asks the REAL predicate — the registry's own, not a
        re-implementation of it — whether the next Odds poll may write the
        start back, and it asks in BOTH states: under the stamp this pass now
        writes, and under the one the row carried before it.
        """
        from app.services.event_registry import commence_time_write_authorized

        # BEFORE: the row holds ESPN's clock stamped `odds_api`, so the Odds
        # poll is revising its own record and is authorized. This is the
        # writer that put 18:00 back, five times in seventeen minutes.
        allowed, why = commence_time_write_authorized(
            "odds_api", "odds_api", same_record_revision=True,
        )
        assert allowed, (
            "if this is False the ping-pong had some other cause and this "
            f"whole fix is aimed at the wrong writer ({why})"
        )

        # AFTER: the same poll, the same claim, against the stamp the
        # correction now leaves behind. `espn` (3) outranks `odds_api` (1),
        # and a revision needs the sources to be EQUAL — so both arms refuse.
        allowed, _why = commence_time_write_authorized(
            "espn", "odds_api", same_record_revision=True,
        )
        assert not allowed

    def test_statpal_owns_the_start_and_is_not_overwritten(self):
        """The refusal both of ESPN's other write sites already make
        (`espn_helpers`, twice) and `anchor_schedule` calls REFUSED_STATPAL.

        Inert for tennis today — 0 tennis rows carried a `statpal` stamp in the
        census this shipped on — and written anyway, because adding the stamp
        WITHOUT it would newly move a column ESPN has never held here.
        """
        changes = authority_write(
            our_status="scheduled", our_completed_at=None,
            our_commence_time=_utc("2026-09-13T18:00:00+00:00"),
            our_commence_time_source="statpal",
            competition={"state": "upcoming", "date": "2026-09-13T18:15Z",
                         "start_is_tbd": False},
            now=_utc("2026-09-13T18:10:00+00:00"),
        )
        assert "commence_time" not in changes
        # Not merely un-stamped — UNTOUCHED. A refusal that left the value and
        # dropped the stamp would be the defect this file exists about.
        assert "commence_time_source" not in changes

    @pytest.mark.parametrize(
        "state,date,tbd,ours,source,completed",
        [
            # every branch that reaches the clock block, and several that
            # must not write at all
            ("upcoming", "2026-09-13T18:15Z", False, "2026-09-13T18:00:00+00:00", "odds_api", None),
            ("upcoming", "2026-09-13T18:02Z", False, "2026-09-13T18:00:00+00:00", "odds_api", None),
            ("upcoming", "2026-09-14T04:00Z", True, "2026-09-13T18:00:00+00:00", "odds_api", None),
            ("upcoming", "2026-09-13T18:15Z", False, "2026-09-13T18:00:00+00:00", "statpal", None),
            ("in_progress", "2026-09-13T18:15Z", False, "2026-09-13T18:00:00+00:00", None, None),
            ("in_progress", "2026-09-13T18:15Z", False, "2026-09-13T18:00:00+00:00", "espn", None),
            ("decided", "2026-09-13T18:15Z", False, "2026-09-13T18:00:00+00:00", "odds_api",
             "2026-09-13T21:00:00+00:00"),
            ("decided", "2026-09-13T22:15Z", False, "2026-09-13T18:00:00+00:00", "odds_api",
             "2026-09-13T21:00:00+00:00"),
            (None, "2026-09-13T18:15Z", False, "2026-09-13T18:00:00+00:00", "odds_api", None),
        ],
    )
    def test_neither_column_ever_moves_without_the_other(
        self, state, date, tbd, ours, source, completed,
    ):
        """THE INVARIANT, over every branch rather than the one that broke.

        The caller reads `changes["commence_time_source"]` off the same dict
        and would `KeyError` on a value without a stamp; a stamp without a
        value would re-provenance a start nobody moved. Both are the same
        mistake and this is the assertion that catches either.
        """
        changes = authority_write(
            our_status="scheduled", our_completed_at=_utc(completed) if completed else None,
            our_commence_time=_utc(ours),
            our_commence_time_source=source,
            competition={"state": state, "date": date, "start_is_tbd": tbd},
            now=_utc("2026-09-13T18:10:00+00:00"),
        )
        assert ("commence_time" in changes) == ("commence_time_source" in changes)


class TestTheClockCorrectionReachesTheDatabase:
    """END TO END, for the reason #3242's class above it exists: a pure
    function that returns the right dict is worth nothing if the pass does not
    apply it. This drives the real task and reads both columns off the row."""

    async def test_a_slid_start_comes_out_of_the_pass_stamped_espn(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            15310688, "Carlos Alcaraz", "Jannik Sinner", "scheduled",
            _at("2026-09-13T18:00Z"), espn_id="182677",
            home_score=0, away_score=0,
            # The provenance the live row actually carried.
            commence_time_source="odds_api",
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182677", ["Carlos Alcaraz", "Jannik Sinner"],
                state="pre", status_name="STATUS_SCHEDULED",
                date="2026-09-13T18:15Z",
            )])],
            errors=[],
            sport_keys=["tennis_atp_us_open", "tennis_atp"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert event.commence_time == _at("2026-09-13T18:15Z")
        assert event.commence_time_source == "espn", (
            "the pass moved the clock and left the old provenance, so the next "
            "Odds poll is still entitled to write 18:00 back — which is the "
            "whole of #5971"
        )
        assert stats["commence_writes"] == 1

    async def test_a_statpal_start_survives_the_pass_untouched(self, monkeypatch):
        """The control. Without it the test above passes just as well against a
        version that stamps `espn` on every row it can reach."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(
            15310688, "Carlos Alcaraz", "Jannik Sinner", "scheduled",
            _at("2026-09-13T18:00Z"), espn_id="182677",
            home_score=0, away_score=0,
            commence_time_source="statpal",
        )
        _install(
            monkeypatch,
            payloads=[_payload([_competition(
                "182677", ["Carlos Alcaraz", "Jannik Sinner"],
                state="pre", status_name="STATUS_SCHEDULED",
                date="2026-09-13T18:15Z",
            )])],
            errors=[],
            sport_keys=["tennis_atp_us_open", "tennis_atp"],
            events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert event.commence_time == _at("2026-09-13T18:00Z")
        assert event.commence_time_source == "statpal"
        assert stats["commence_writes"] == 0
