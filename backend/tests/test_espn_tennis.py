"""ESPN tennis results — the score behind a decided match (UX-P139, item 9).

    "Decided-match scores come from the ESPN API we already use for other
    scores — wire it; 'no data behind it' is not accepted."

Pure over a decoded payload, so the whole join is testable without a network.
Every case below is a shape ESPN's US Open feed actually returns, measured
2026-08-26: 625 competitions across five groupings, 203 final, 184 with a
complete set score, 19 doubles competitions naming a team rather than an
athlete.
"""

from __future__ import annotations

from app.services.espn_tennis import (
    DRAW_SLUGS,
    completion_of,
    current_set_label,
    format_score,
    normalize_name,
    pair_key,
    parse_results,
    play_refutes_upcoming,
    sets_with_play,
)


def _competitor(name, *, winner, sets, athlete=True):
    entry = {
        "id": "1",
        "winner": winner,
        "linescores": [{"value": value} for value in sets],
    }
    if athlete:
        entry["athlete"] = {"displayName": name}
    return entry


def _competition(
    a,
    b,
    *,
    state="post",
    comp_id="1",
    round_name="Qualifying 1st Round",
    detail="Final",
    period=None,
):
    status = {"type": {"state": state, "detail": detail}}
    if period is not None:
        # ESPN carries the set number BESIDE `type`, not inside it.
        status["period"] = period
    return {
        "id": comp_id,
        "date": "2026-08-24T15:05Z",
        "status": status,
        "competitors": [a, b],
        "round": {"displayName": round_name},
    }


def _payload(competitions, *, slug="mens-singles", name="US Open"):
    return {
        "events": [
            {
                "id": "189-2026",
                "name": name,
                "groupings": [
                    {"grouping": {"slug": slug}, "competitions": competitions}
                ],
            }
        ]
    }


# ---------------------------------------------------------------------------
# The join key
# ---------------------------------------------------------------------------

class TestTheJoinKey:
    def test_the_pair_is_unordered(self):
        """Two players meet at most once in a knockout draw, so the PAIR is a
        key. A single name is not, and a single-name join is how a first-round
        result lands on a quarter-final card."""
        assert pair_key(["A B", "C D"]) == pair_key(["C D", "A B"])

    def test_names_fold_the_way_the_register_folds_them(self):
        # ESPN writes `Felix Auger-Aliassime`, Polymarket writes `Felix Auger
        # Aliassime`. Spaces are dropped, not merely punctuation.
        assert normalize_name("Felix Auger-Aliassime") == normalize_name(
            "Felix Auger Aliassime"
        )
        assert normalize_name("Anna Bondár") == normalize_name("Anna Bondar")

    def test_distinct_players_do_not_collide(self):
        assert normalize_name("Jannik Sinner") != normalize_name("Jack Draper")


# ---------------------------------------------------------------------------
# The score
# ---------------------------------------------------------------------------

class TestTheScore:
    def test_winner_first_set_by_set(self):
        """A card that says 'Fearnley won' over '3-6, 6-7' asks the reader to
        reverse it in their head, and half of them will not."""
        score = format_score([
            _competitor("Loser", winner=False, sets=[6, 3]),
            _competitor("Winner", winner=True, sets=[7, 6]),
        ])
        assert score == "7-6, 6-3"

    def test_three_sets_read_in_order(self):
        score = format_score([
            _competitor("Winner", winner=True, sets=[4, 6, 6]),
            _competitor("Loser", winner=False, sets=[6, 3, 3]),
        ])
        assert score == "4-6, 6-3, 6-3"

    def test_an_unequal_read_yields_no_score_rather_than_half_of_one(self):
        """Unequal set counts is a mid-match read. A partial score printed as a
        final one is a stale price printed as live.

        ⚠️ UX-P147 renamed this from ``..._a_retirement_...``, because that is
        not what it proves and the mismatch was hiding a live defect. A REAL
        retirement reports EQUAL set counts — ESPN fills the abandoned set in on
        both sides — so it never reaches this branch. See
        ``TestHowAMatchEnded`` for the eight production rows this test was
        wrongly believed to cover.
        """
        assert format_score([
            _competitor("W", winner=True, sets=[6, 2]),
            _competitor("L", winner=False, sets=[4]),
        ]) is None

    def test_a_missing_set_value_yields_no_score(self):
        assert format_score([
            {"winner": True, "linescores": [{"value": None}]},
            {"winner": False, "linescores": [{"value": 3}]},
        ]) is None

    def test_no_line_scores_yields_no_score(self):
        assert format_score([
            {"winner": True, "linescores": []},
            {"winner": False, "linescores": []},
        ]) is None

    def test_a_doubles_team_of_one_competitor_yields_no_score(self):
        assert format_score([_competitor("Solo", winner=True, sets=[6])]) is None


# ---------------------------------------------------------------------------
# HOW a match ended (UX-P147, Alex's item 5)
# ---------------------------------------------------------------------------
#
# Alex, on the UX-P146 artifact: one row printed "no score", and he asked for
# the root cause — ingest gap or render fallback.  Measured against the live
# ESPN scoreboard 2026-08-28T00:4xZ it is neither.  Competition 184769,
# "Qualifying Final", is ``STATUS_WALKOVER`` with the note "Grigor Dimitrov
# (BUL) bt Otto Virtanen (FIN) w/o" and NO ``linescores`` on either competitor.
# Virtanen withdrew before a ball was struck; there was never a score to ingest.
#
# The same census over all 1,250 US Open competitions on that scoreboard:
#
#     STATUS_FINAL      434   line scores both sides
#     STATUS_RETIRED      8   line scores both sides, EQUAL LENGTH
#     STATUS_WALKOVER     2   no line scores at all
#     STATUS_SCHEDULED  806   (792 unplayed + 14 in progress; `state` filters)
#
# So there are two defects, not one: we could not say "walkover", and we were
# printing eight partial scores as finished ones.

class TestHowAMatchEnded:
    def test_a_walkover_is_named_rather_than_shrugged_at(self):
        parsed = parse_results(
            [
                _payload([
                    {
                        "id": "184769",
                        "date": "2026-08-27T16:30Z",
                        # ESPN's real shape for this fixture: a winner flag, and
                        # no `linescores` key at all on either competitor.
                        "status": {"type": {
                            "state": "post",
                            "name": "STATUS_WALKOVER",
                            "detail": "Walkover",
                        }},
                        "competitors": [
                            {"winner": True, "athlete": {"displayName": "Grigor Dimitrov"}},
                            {"winner": False, "athlete": {"displayName": "Otto Virtanen"}},
                        ],
                        "round": {"displayName": "Qualifying Final"},
                    }
                ])
            ],
            event_name="US Open",
        )
        found = parsed["draws"]["mens-singles"][
            pair_key(["Grigor Dimitrov", "Otto Virtanen"])
        ]
        assert found["score"] is None
        assert found["completion"] == "walkover"
        assert parsed["stats"]["walkovers"] == 1

    def test_a_retirement_keeps_its_real_score_and_is_marked(self):
        """The eight rows nobody had looked at.

        ``Dusan Lajovic (SER) bt SoonWoo Kwon (KOR) 4-6 7-5 3-1 ret`` — equal
        set counts, so ``format_score`` returns ``4-6, 7-5, 3-1``, which is not
        a scoreline a completed tennis match can have.  The score is TRUE and
        is kept; the completion is what makes it honest.
        """
        parsed = parse_results(
            [
                _payload([
                    {
                        "id": "184600",
                        "date": "2026-08-24T15:05Z",
                        "status": {"type": {
                            "state": "post",
                            "name": "STATUS_RETIRED",
                            "detail": "Retired",
                        }},
                        "competitors": [
                            _competitor("Dusan Lajovic", winner=True, sets=[4, 7, 3]),
                            _competitor("SoonWoo Kwon", winner=False, sets=[6, 5, 1]),
                        ],
                        "round": {"displayName": "Qualifying 1st Round"},
                    }
                ])
            ],
            event_name="US Open",
        )
        found = parsed["draws"]["mens-singles"][
            pair_key(["Dusan Lajovic", "SoonWoo Kwon"])
        ]
        assert found["score"] == "4-6, 7-5, 3-1"
        assert found["completion"] == "retired"
        assert parsed["stats"]["retirements"] == 1
        assert parsed["stats"]["walkovers"] == 0

    def test_an_ordinary_final_says_so(self):
        parsed = parse_results(
            [_payload([_competition(
                _competitor("Winner", winner=True, sets=[7, 6]),
                _competitor("Loser", winner=False, sets=[6, 3]),
            )])],
            event_name="US Open",
        )
        found = next(iter(parsed["draws"]["mens-singles"].values()))
        # `_competition`'s status carries no `name`, exactly like a payload from
        # before this field was read — and that must NOT become a confident
        # "final". Inventing a completion is the same defect in the other
        # direction from failing to read one.
        assert found["completion"] == "unknown"
        assert parsed["stats"]["walkovers"] == 0
        assert parsed["stats"]["retirements"] == 0

    def test_an_unrecognised_status_degrades_to_unknown_not_to_final(self):
        assert completion_of({"name": "STATUS_FINAL"}) == "final"
        assert completion_of({"name": "STATUS_RETIRED"}) == "retired"
        assert completion_of({"name": "STATUS_WALKOVER"}) == "walkover"
        assert completion_of({"name": "STATUS_SOMETHING_ESPN_ADDS_IN_2027"}) == "unknown"
        assert completion_of({}) == "unknown"
        # Keyed on the ENUM, never on the display text, which can be reworded
        # or localised without notice.
        assert completion_of({"detail": "Walkover"}) == "unknown"


# ---------------------------------------------------------------------------
# Parsing a scoreboard
# ---------------------------------------------------------------------------

class TestParsing:
    def test_a_final_competition_becomes_a_result(self):
        parsed = parse_results(
            [
                _payload([
                    _competition(
                        _competitor("Jacob Fearnley", winner=True, sets=[7, 6]),
                        _competitor("Roberto Carballes Baena", winner=False, sets=[6, 3]),
                    )
                ])
            ],
            event_name="US Open",
        )
        [result] = parsed["draws"]["mens-singles"].values()
        assert result["score"] == "7-6, 6-3"
        assert result["winner_name"] == "Jacob Fearnley"
        assert result["espn_round"] == "Qualifying 1st Round"
        assert parsed["stats"]["final"] == 1
        assert parsed["stats"]["scored"] == 1

    def test_an_in_progress_match_is_NOT_a_result(self):
        """It has line scores too. Printing them as a result is
        settled-means-settled broken in the direction that matters."""
        parsed = parse_results(
            [
                _payload([
                    _competition(
                        _competitor("A", winner=False, sets=[3]),
                        _competitor("B", winner=False, sets=[6]),
                        state="in",
                    )
                ])
            ],
            event_name="US Open",
        )
        assert parsed["draws"] == {}
        assert parsed["stats"]["competitions"] == 1
        assert parsed["stats"]["final"] == 0

    def test_another_tournament_on_the_same_scoreboard_is_ignored(self):
        """The day's scoreboard also carries Winston-Salem and Monterrey. A
        tournament is selected because somebody named it, never because a
        scorer picked it."""
        parsed = parse_results(
            [
                _payload(
                    [
                        _competition(
                            _competitor("A", winner=True, sets=[6, 6]),
                            _competitor("B", winner=False, sets=[3, 4]),
                        )
                    ],
                    name="Winston-Salem Open",
                )
            ],
            event_name="US Open",
        )
        assert parsed["draws"] == {}

    def test_both_tours_return_the_same_event_and_it_counts_once(self):
        """The US Open appears under BOTH atp and wta with the same competition
        ids. Fetching one would be a silent single point of failure; counting
        the duplicate twice would inflate every number in the section."""
        page = _payload([
            _competition(
                _competitor("A", winner=True, sets=[6, 6]),
                _competitor("B", winner=False, sets=[3, 4]),
                comp_id="184607",
            )
        ])
        parsed = parse_results([page, page], event_name="US Open")
        assert parsed["stats"]["competitions"] == 1
        assert len(parsed["draws"]["mens-singles"]) == 1

    def test_a_doubles_team_is_counted_as_unpaired_not_dropped(self):
        """19 of the day's competitions name a TEAM rather than an athlete.
        Counted, so the doubles section's coverage is a number and not a shrug."""
        parsed = parse_results(
            [
                _payload(
                    [
                        _competition(
                            _competitor(None, winner=True, sets=[6, 6], athlete=False),
                            _competitor(None, winner=False, sets=[3, 4], athlete=False),
                        )
                    ],
                    slug="mens-doubles",
                )
            ],
            event_name="US Open",
        )
        assert parsed["draws"] == {}
        assert parsed["stats"]["unpaired"] == 1

    def test_an_unknown_grouping_is_skipped_rather_than_guessed(self):
        parsed = parse_results(
            [
                _payload(
                    [
                        _competition(
                            _competitor("A", winner=True, sets=[6]),
                            _competitor("B", winner=False, sets=[3]),
                        )
                    ],
                    slug="boys-singles",
                )
            ],
            event_name="US Open",
        )
        assert parsed["draws"] == {}

    def test_an_empty_payload_is_an_empty_result_not_a_crash(self):
        parsed = parse_results([{}], event_name="US Open")
        assert parsed["draws"] == {}
        assert parsed["stats"]["competitions"] == 0


class TestDrawVocabulary:
    def test_the_singles_slugs_are_the_registers_own_names(self):
        """No mapping table, no gender inference, nothing that touches
        `llm_gender` (dead) or `llm_sport_category` (files every US Open match
        under table tennis)."""
        assert DRAW_SLUGS["mens-singles"] == "mens-singles"
        assert DRAW_SLUGS["womens-singles"] == "womens-singles"

    def test_all_three_doubles_draws_are_carried(self):
        """Item 12: no doubles MARKET exists at either source, but the RESULTS
        do — 63 men's, 63 women's, 21 mixed competitions on 2026-08-26."""
        for slug in ("mens-doubles", "womens-doubles", "mixed-doubles"):
            assert DRAW_SLUGS[slug] == slug


# ---------------------------------------------------------------------------
# THE ORDER OF PLAY (Q463)
#
# `parse_results` threw away every competition that was not `post` — 806 of the
# 1,250 on the US Open scoreboard — and among them was the answer to "what is on
# right now". The slate had no other source for it and read "No matches
# scheduled" through the whole of opening day.
# ---------------------------------------------------------------------------

class TestTheOrderOfPlay:
    def _card(self, competitions):
        return parse_results([_payload(competitions)], event_name="US Open")

    def test_an_unplayed_competition_is_published_instead_of_discarded(self):
        parsed = self._card([
            _competition(
                _competitor("A B", winner=False, sets=[]),
                _competitor("C D", winner=False, sets=[]),
                state="pre", comp_id="182655",
            )
        ])
        assert parsed["stats"]["final"] == 0
        entry = parsed["order_of_play"]["182655"]
        assert entry["state"] == "upcoming"
        assert entry["start_at"] == "2026-08-24T15:05Z"
        assert entry["draw"] == "mens-singles"
        assert parsed["stats"]["upcoming"] == 1

    def test_in_progress_is_its_own_state_and_not_collapsed_into_upcoming(self):
        """The one row an elapsed-time rule cannot keep, and the most
        interesting one on the page."""
        parsed = self._card([
            _competition(
                _competitor("A B", winner=False, sets=[6]),
                _competitor("C D", winner=False, sets=[4]),
                state="in", comp_id="182675",
            )
        ])
        assert parsed["order_of_play"]["182675"]["state"] == "in_progress"
        assert parsed["stats"]["in_progress"] == 1
        assert parsed["stats"]["upcoming"] == 0

    def test_a_decided_competition_is_named_decided_rather_than_left_out(self):
        """CERT-517: the map must say `post`, not imply it by omission.

        Q463 left these out and let the slate read absence as "finished". That
        made a live fixture on a failed tour — omitted for an entirely different
        reason — indistinguishable from this one. Naming the state costs one
        dict entry and makes absence mean only "the scoreboard did not say".

        A decided competition is STILL a result: it goes on both, and the slate
        drops it on the word.
        """
        parsed = self._card([
            _competition(
                _competitor("A B", winner=True, sets=[6, 6]),
                _competitor("C D", winner=False, sets=[3, 4]),
                state="post", comp_id="184607",
            )
        ])
        assert parsed["order_of_play"]["184607"]["state"] == "decided"
        assert parsed["stats"]["decided"] == 1
        # Unchanged: it is still parsed into the results section.
        assert parsed["stats"]["final"] == 1
        assert parsed["draws"]["mens-singles"]

    def test_an_espn_state_we_have_no_word_for_is_not_published_but_IS_counted(self):
        """An unknown state is not evidence, and inventing a word for it would
        be the same absence-as-truth mistake pointing the other way. It is left
        out, and the slate's clock fallback — not a DECIDED inference — applies.

        CERT-526: but it must be COUNTED, or the map is silently short while
        `order_of_play_complete` still says it is the whole scoreboard. A pinned
        fixture in that hole then loses its exemption and the clock drops it on
        the midnight placeholder — the empty card, again.
        """
        parsed = self._card([
            _competition(
                _competitor("A B", winner=False, sets=[]),
                _competitor("C D", winner=False, sets=[]),
                state="postponed", comp_id="182699",
            )
        ])
        assert parsed["order_of_play"] == {}
        assert parsed["stats"]["decided"] == 0
        assert parsed["stats"]["upcoming"] == 0
        assert parsed["stats"]["unknown_state"] == 1

    def test_a_fully_understood_card_reports_no_unknown_states(self):
        """The counter is a signal, so it must be able to read zero."""
        parsed = self._card([
            _competition(
                _competitor("A B", winner=False, sets=[]),
                _competitor("C D", winner=False, sets=[]),
                state="pre", comp_id="182700",
            )
        ])
        assert parsed["stats"]["unknown_state"] == 0
        assert parsed["stats"]["events"] == 1

    def test_a_tbd_placeholder_is_flagged_and_its_template_detail_dropped(self):
        """`detail` on a TBD row is an unsubstituted format string — "M/d -
        'TBD'" — and its `date` is midnight local. Printing either as a start is
        the smaller version of the defect that emptied the card."""
        competition = _competition(
            _competitor("A B", winner=False, sets=[]),
            _competitor("C D", winner=False, sets=[]),
            state="pre", comp_id="182659",
        )
        competition["date"] = "2026-08-31T04:00Z"
        competition["status"]["type"] = {
            "state": "pre", "detail": "M/d - 'TBD'", "shortDetail": "TBD",
        }
        entry = self._card([competition])["order_of_play"]["182659"]
        assert entry["start_is_tbd"] is True
        assert entry["status_detail"] is None
        # The placeholder itself is kept — it is honest DATA, flagged.
        assert entry["start_at"] == "2026-08-31T04:00Z"

    def test_a_scheduled_competition_keeps_its_real_time_and_words(self):
        competition = _competition(
            _competitor("A B", winner=False, sets=[]),
            _competitor("C D", winner=False, sets=[]),
            state="pre", comp_id="182661",
        )
        competition["status"]["type"] = {
            "state": "pre",
            "detail": "Mon, August 31st at 11:00 AM EDT",
            "shortDetail": "8/31 - 11:00 AM EDT",
        }
        entry = self._card([competition])["order_of_play"]["182661"]
        assert entry["start_is_tbd"] is False
        assert entry["status_detail"] == "Mon, August 31st at 11:00 AM EDT"

    def test_another_tournament_on_the_same_scoreboard_is_not_on_our_card(self):
        """`event_name` selects, here as everywhere else on this page."""
        parsed = parse_results(
            [_payload([
                _competition(
                    _competitor("A B", winner=False, sets=[]),
                    _competitor("C D", winner=False, sets=[]),
                    state="pre", comp_id="777",
                )
            ], name="Winston-Salem Open")],
            event_name="US Open",
        )
        assert parsed["order_of_play"] == {}


# ---------------------------------------------------------------------------
# lane1/054 — WHEN ESPN'S STATE CONTRADICTS ESPN'S OWN SCOREBOARD
#
# Measured on the live US Open scoreboards, 2026-09-02T18:50Z, both tours
# deduped: 238 `pre` competitions with no games on the board (genuinely
# upcoming), 5 `pre` competitions with games (all in progress), 10 `in`, 371
# `post` with games, 2 `post` without (walkovers).
#
# The worked case is Carlos Taberner v Zizou Bergs (competition 182685): 6-3,
# 3-6, 6-2 and into a fourth set, while ESPN still said `STATUS_SCHEDULED`,
# "Wed, September 2nd at 3:30 PM EDT". The hub printed "12:30 PM" over it.
# ---------------------------------------------------------------------------

_TABERNER_BERGS_DETAIL = "Wed, September 2nd at 3:30 PM EDT"


def _taberner_bergs(*, state="pre", comp_id="182685"):
    """The refuting shape, exactly as the scoreboard returned it."""
    return _competition(
        _competitor("Carlos Taberner", winner=False, sets=[3, 6, 2, 1]),
        _competitor("Zizou Bergs", winner=False, sets=[6, 3, 6, 2]),
        state=state,
        comp_id=comp_id,
        detail=_TABERNER_BERGS_DETAIL,
        period=4,
    )


class TestSetsWithPlay:
    def test_no_linescores_is_no_play(self):
        assert sets_with_play(
            _competition(
                _competitor("A B", winner=False, sets=[]),
                _competitor("C D", winner=False, sets=[]),
            )
        ) == 0

    def test_the_last_set_holding_a_game_is_the_answer(self):
        assert sets_with_play(_taberner_bergs()) == 4

    def test_a_trailing_love_set_is_a_changeover_and_not_a_set(self):
        """ESPN writes the next set's line at 0-0 the instant one ends. Counting
        presence rather than games would call that changeover a played set."""
        assert sets_with_play(
            _competition(
                _competitor("A B", winner=False, sets=[6, 0]),
                _competitor("C D", winner=False, sets=[4, 0]),
            )
        ) == 1

    def test_one_side_holding_the_only_game_still_counts_that_set(self):
        assert sets_with_play(
            _competition(
                _competitor("A B", winner=False, sets=[0, 0, 1]),
                _competitor("C D", winner=False, sets=[0, 0, 0]),
            )
        ) == 3

    def test_an_unreadable_line_is_skipped_rather_than_crashing(self):
        competition = _competition(
            _competitor("A B", winner=False, sets=[6]),
            _competitor("C D", winner=False, sets=[]),
        )
        competition["competitors"][1]["linescores"] = [{"value": None}, {}]
        assert sets_with_play(competition) == 1


class TestCurrentSetLabel:
    def test_every_set_a_grand_slam_can_reach_has_espns_own_words(self):
        assert [current_set_label(n) for n in range(1, 6)] == [
            "1st Set", "2nd Set", "3rd Set", "4th Set", "5th Set",
        ]

    def test_a_period_we_have_no_ordinal_for_is_silence_not_a_guess(self):
        """Silence falls back to ESPN's detail, and the client to "LIVE" — both
        better than a sixth set invented to fill the slot."""
        assert current_set_label(6) is None
        assert current_set_label(0) is None
        assert current_set_label(None) is None
        assert current_set_label("4th") is None


class TestPlayRefutesUpcoming:
    def test_games_on_the_board_refute_upcoming(self):
        assert play_refutes_upcoming("upcoming", _taberner_bergs()) is True

    def test_an_unplayed_fixture_is_never_refuted(self):
        """THE CONTROL, and the whole reason the rule is safe: not one of the
        238 genuinely-upcoming competitions carries a game."""
        assert play_refutes_upcoming(
            "upcoming",
            _competition(
                _competitor("A B", winner=False, sets=[]),
                _competitor("C D", winner=False, sets=[]),
                state="pre",
            ),
        ) is False

    def test_a_decided_match_is_not_refutable_although_it_has_games(self):
        """`post` plus a linescore is the ordinary shape of 371 finished
        matches, not a contradiction. Only `upcoming` is refutable."""
        assert play_refutes_upcoming("decided", _taberner_bergs(state="post")) is False

    def test_an_already_live_match_is_not_refutable(self):
        assert play_refutes_upcoming("in_progress", _taberner_bergs(state="in")) is False

    def test_an_unpublished_state_is_not_refutable(self):
        assert play_refutes_upcoming(None, _taberner_bergs()) is False


class TestAMatchBeingPlayedNeverAdvertisesAStart:
    def _card(self, competitions):
        return parse_results([_payload(competitions)], event_name="US Open")

    def test_a_scheduled_competition_with_games_on_the_board_is_in_progress(self):
        """THE DEFECT. Before this rule the entry said `upcoming` and carried
        "Wed, September 2nd at 3:30 PM EDT", and the hub rendered 12:30 PM over
        a match three sets deep."""
        entry = self._card([_taberner_bergs()])["order_of_play"]["182685"]
        assert entry["state"] == "in_progress"

    def test_it_says_which_set_rather_than_the_schedule_sentence(self):
        """The set comes from `period`, because `detail` on a refuted row is
        still the schedule — and a date inside a live pill is what
        `liveMatchLabel` refuses on the client."""
        entry = self._card([_taberner_bergs()])["order_of_play"]["182685"]
        assert entry["status_detail"] == "4th Set"
        assert _TABERNER_BERGS_DETAIL not in str(entry["status_detail"])

    def test_the_refutation_is_counted_so_the_source_lagging_is_visible(self):
        parsed = self._card([_taberner_bergs()])
        assert parsed["stats"]["upcoming_refuted_by_play"] == 1
        assert parsed["stats"]["in_progress"] == 1
        assert parsed["stats"]["upcoming"] == 0

    def test_an_unplayed_fixture_keeps_its_state_its_words_and_its_time(self):
        """THE CONTROL, through the whole parse. Green before this rule and
        after it — the 238-row population the rule must not reach."""
        competition = _competition(
            _competitor("A B", winner=False, sets=[]),
            _competitor("C D", winner=False, sets=[]),
            state="pre",
            comp_id="182661",
            detail="Mon, August 31st at 11:00 AM EDT",
            period=1,
        )
        parsed = self._card([competition])
        entry = parsed["order_of_play"]["182661"]
        assert entry["state"] == "upcoming"
        assert entry["status_detail"] == "Mon, August 31st at 11:00 AM EDT"
        assert entry["start_at"] == "2026-08-24T15:05Z"
        assert parsed["stats"]["upcoming"] == 1
        assert parsed["stats"]["upcoming_refuted_by_play"] == 0

    def test_a_finished_match_stays_a_result_and_is_not_dragged_back_live(self):
        """THE CONTROL that matters most: 371 of the 383 `post` competitions
        carry games, so a rule that read the linescore without reading the state
        would empty the results section onto the live board."""
        parsed = self._card([_taberner_bergs(state="post", comp_id="182684")])
        assert parsed["order_of_play"]["182684"]["state"] == "decided"
        assert parsed["stats"]["upcoming_refuted_by_play"] == 0
        assert parsed["stats"]["decided"] == 1

    def test_an_in_progress_match_keeps_espns_own_words_for_the_set(self):
        """Untouched: ESPN's `detail` is already "3rd Set" on a row it has
        caught up with, and the derived label must not displace it."""
        competition = _competition(
            _competitor("Ignacio Buse", winner=False, sets=[3, 6, 4]),
            _competitor("Marcos Giron", winner=False, sets=[6, 3, 3]),
            state="in", comp_id="182750", detail="3rd Set", period=3,
        )
        entry = self._card([competition])["order_of_play"]["182750"]
        assert entry["state"] == "in_progress"
        assert entry["status_detail"] == "3rd Set"

    def test_a_refuted_row_with_no_usable_period_falls_back_to_the_detail(self):
        """`current_set_label` returning None must leave the entry publishable —
        the client's own guard then prints LIVE rather than the date."""
        competition = _taberner_bergs(comp_id="182686")
        competition["status"].pop("period")
        entry = self._card([competition])["order_of_play"]["182686"]
        assert entry["state"] == "in_progress"
        assert entry["status_detail"] == _TABERNER_BERGS_DETAIL

    def test_the_whole_days_card_sorts_the_way_the_scoreboard_measured(self):
        """The four shapes together, in the proportions production returned."""
        parsed = self._card([
            _taberner_bergs(),
            _competition(
                _competitor("E F", winner=False, sets=[]),
                _competitor("G H", winner=False, sets=[]),
                state="pre", comp_id="900", detail="Wed at 7:00 PM EDT",
            ),
            _competition(
                _competitor("I J", winner=False, sets=[2]),
                _competitor("K L", winner=False, sets=[3]),
                state="in", comp_id="901", detail="1st Set", period=1,
            ),
            _competition(
                _competitor("M N", winner=True, sets=[6, 6]),
                _competitor("O P", winner=False, sets=[1, 2]),
                state="post", comp_id="902",
            ),
        ])
        assert parsed["stats"]["upcoming"] == 1
        assert parsed["stats"]["in_progress"] == 2
        assert parsed["stats"]["decided"] == 1
        assert parsed["stats"]["upcoming_refuted_by_play"] == 1
