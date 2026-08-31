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
    format_score,
    normalize_name,
    pair_key,
    parse_results,
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


def _competition(a, b, *, state="post", comp_id="1", round_name="Qualifying 1st Round"):
    return {
        "id": comp_id,
        "date": "2026-08-24T15:05Z",
        "status": {"type": {"state": state, "detail": "Final"}},
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

    def test_a_decided_competition_gets_no_entry(self):
        """Absence IS the signal the slate reads. A `post` competition in this
        map would put a finished match back on the day's card."""
        parsed = self._card([
            _competition(
                _competitor("A B", winner=True, sets=[6, 6]),
                _competitor("C D", winner=False, sets=[3, 4]),
                state="post", comp_id="184607",
            )
        ])
        assert parsed["order_of_play"] == {}
        assert parsed["stats"]["final"] == 1

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
