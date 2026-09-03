"""#2693 step 2 — one game, one authority id.

Every case here is a REAL production group, named and dated, because the
interesting property of this decider is not that it has branches but that its
branches match what ESPN actually says about rows we actually hold. A synthetic
"team A v team B" fixture would pass every version of this module, including the
two that were withdrawn during the build:

  * the team-id version, which merged three different fixtures into
    Florida State v Miami because ``teams.espn_id`` is itself colliding;
  * the row-versus-authority time gate, which refused four MLB groups whose two
    rows sit at the same hour as each other and nineteen hours from ESPN.

Both are pinned below as regression arms.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.authority_id_collisions import (
    MAX_TWIN_DELTA,
    AuthorityRecord,
    CandidateRow,
    authority_names,
    decide_group,
    summarize,
)


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def record(home, away, *, starts_at=None, home_id=None, away_id=None, key="1"):
    return AuthorityRecord(
        authority_id=key,
        home_names=frozenset(home),
        away_names=frozenset(away),
        home_team_id=home_id,
        away_team_id=away_id,
        starts_at=starts_at,
        label="ESPN",
    )


def row(event_id, home, away, *, at=None, weight=0, external=False, team_ids=(None, None)):
    return CandidateRow(
        event_id=event_id,
        sport_key="baseball_ncaa",
        home_team_name=home,
        away_team_name=away,
        commence_time=at,
        home_team_authority_id=team_ids[0],
        away_team_authority_id=team_ids[1],
        weight=weight,
        has_external_id=external,
    )


# ---------------------------------------------------------------------------
# The vocabulary. ESPN's own names, exactly, and nothing looser.
# ---------------------------------------------------------------------------


class TestAuthorityNames:
    def test_reads_every_name_espn_publishes_for_a_competitor(self):
        names = authority_names({
            "team": {
                "displayName": "Ole Miss Rebels",
                "shortDisplayName": "Ole Miss",
                "location": "Ole Miss",
                "name": "Rebels",
                "abbreviation": "MISS",
            }
        })
        assert "ole miss rebels" in names
        assert "ole miss" in names
        assert "rebels" in names
        assert "miss" in names

    def test_blank_fields_are_dropped_not_kept_as_an_empty_name(self):
        # An empty string in the set would match every row whose team name
        # normalizes to nothing, which is a wildcard by another route.
        assert "" not in authority_names({"team": {"displayName": "", "name": "Rebels"}})

    def test_reads_a_competitor_that_is_its_own_team_block(self):
        assert "rebels" in authority_names({"displayName": "Rebels"})


# ---------------------------------------------------------------------------
# The single-keeper case, and the false positives that must NOT happen.
# ---------------------------------------------------------------------------


class TestExactMatchDecidesOneKeeper:
    def test_401847094_alabama_keeps_the_id_and_north_alabama_hands_it_back(self):
        """The charter case. ESPN: Alabama Crimson Tide v Ole Miss Rebels."""
        espn = record(
            {"alabama crimson tide", "alabama", "crimson tide", "ala"},
            {"ole miss rebels", "ole miss", "rebels", "miss"},
            starts_at=utc("2026-05-14T23:00:00"),
        )
        decision = decide_group(
            espn,
            [
                row(14683176, "Alabama Crimson Tide", "Ole Miss Rebels",
                    at=utc("2026-05-14T23:00:00"), external=True),
                row(14707075, "North Alabama", "Ole Miss",
                    at=utc("2026-05-14T23:00:00")),
            ],
            authority_id="401847094",
        )
        assert decision.outcome == "RESOLVED_ONE"
        assert decision.keep_event_id == 14683176
        assert decision.unstamp_event_ids == (14707075,)
        # NOT a twin — it is a different fixture, and the follow-ups differ.
        assert decision.twin_event_ids == ()

    def test_kansas_is_not_a_wildcard_for_kansas_state(self):
        """A prefix rule would accept this. That rule is how 401849966 broke."""
        espn = record(
            {"ucf knights", "ucf", "knights"},
            {"kansas state wildcats", "kansas state", "wildcats", "ksu"},
            starts_at=utc("2026-05-14T22:00:00"),
        )
        decision = decide_group(
            espn,
            [
                row(1, "UCF Knights", "Kansas State Wildcats", at=utc("2026-05-14T22:00:00")),
                row(2, "UCF", "Kansas", at=utc("2026-05-14T22:00:00")),
            ],
            authority_id="401849966",
        )
        assert decision.keep_event_id == 1
        assert decision.unstamp_event_ids == (2,)

    def test_trailing_state_abbreviation_is_the_same_team(self):
        """"Florida St Seminoles" and ESPN's "Florida State Seminoles"."""
        espn = record(
            {"florida state seminoles"}, {"miami hurricanes"},
            starts_at=utc("2026-05-14T22:00:00"),
        )
        decision = decide_group(
            espn,
            [row(1, "Florida St Seminoles", "Miami Hurricanes", at=utc("2026-05-14T22:00:00"))],
            authority_id="401847945",
        )
        assert decision.rows[0].verdict == "AGREES"

    def test_the_pair_may_be_inverted_and_the_inversion_is_recorded(self):
        espn = record({"uic flames"}, {"murray state racers"})
        decision = decide_group(
            espn, [row(1, "Murray State Racers", "UIC Flames")], authority_id="401872150"
        )
        assert decision.keep_event_id == 1
        assert decision.rows[0].inverted is True


# ---------------------------------------------------------------------------
# THE WITHDRAWN TEAM-ID CHANNEL. This arm is the regression guard.
# ---------------------------------------------------------------------------


class TestTeamIdsAreObservedNeverConsulted:
    def test_401847945_ball_state_does_not_agree_on_florida_states_team_id(self):
        """``teams.espn_id`` 72 is worn by Florida State AND Ball State.

        The withdrawn draft decided on this channel and merged Ball State v
        Miami (OH), Indiana State v Miami (FL) and Florida State v Miami into
        one fixture. Measured 2026-09-02: 1,204 of the 1,469 team rows carrying
        an espn_id sit in a colliding (sport, espn_id).
        """
        espn = record(
            {"florida state seminoles"}, {"miami hurricanes"},
            starts_at=utc("2026-05-14T22:00:00"), home_id="72", away_id="176",
        )
        decision = decide_group(
            espn,
            [
                row(14683163, "Florida State Seminoles", "Miami Hurricanes",
                    at=utc("2026-05-14T22:00:00"), team_ids=("72", "176")),
                row(14706470, "Ball State", "Miami (OH)",
                    at=utc("2026-05-14T22:00:00"), team_ids=("72", "176")),
                row(14707921, "Indiana State", "Miami (FL)",
                    at=utc("2026-05-14T22:00:00"), team_ids=("72", "176")),
            ],
            authority_id="401847945",
        )
        assert decision.keep_event_id == 14683163
        assert set(decision.unstamp_event_ids) == {14706470, 14707921}
        assert decision.twin_event_ids == ()

    def test_the_channel_reported_is_the_channel_used(self):
        espn = record({"a team"}, {"b team"}, home_id="1", away_id="2")
        decision = decide_group(
            espn, [row(1, "A Team", "B Team", team_ids=("1", "2"))], authority_id="x"
        )
        # Agreeing team ids must not change the answer OR the label — a run
        # graded on the name channel and delivered on another is a swap.
        assert decision.rows[0].channel == "team_name"


# ---------------------------------------------------------------------------
# Twins, and the clustering that finds them.
# ---------------------------------------------------------------------------


class TestTwins:
    def test_401816672_name_variant_twins_keep_one_and_the_other_hands_it_back(self):
        espn = record(
            {"st louis cardinals"}, {"baltimore orioles"},
            starts_at=utc("2026-08-25T23:45:00"),
        )
        decision = decide_group(
            espn,
            [
                row(15201232, "St.Louis Cardinals", "Baltimore Orioles",
                    at=utc("2026-08-25T23:45:00")),
                row(15291558, "St. Louis Cardinals", "Baltimore Orioles",
                    at=utc("2026-08-25T23:45:00"), weight=40, external=True),
            ],
            authority_id="401816672",
        )
        assert decision.outcome == "RESOLVED_MERGE"
        # The heavier row keeps the id — in a TWIN group both rows are the same
        # game, so weight is the right tie-break and cannot pick a wrong game.
        assert decision.keep_event_id == 15291558
        assert decision.twin_event_ids == (15201232,)
        assert decision.unstamp_event_ids == (15201232,)

    def test_401856210_twins_nineteen_hours_from_espn_are_still_twins(self):
        """Both rows sit at the same hour as EACH OTHER. The withdrawn
        row-versus-authority gate refused this group; the disagreement is
        between us and ESPN uniformly, not between the two rows."""
        espn = record(
            {"cal poly mustangs"}, {"long beach state beach", "long beach state"},
            starts_at=utc("2026-05-15T05:00:00"),
        )
        decision = decide_group(
            espn,
            [
                row(14683203, "Cal Poly Mustangs", "Long Beach State Beach",
                    at=utc("2026-05-14T10:00:00")),
                row(14787413, "Cal Poly Mustangs", "Long Beach State",
                    at=utc("2026-05-14T10:00:00")),
            ],
            authority_id="401856210",
        )
        assert decision.outcome == "RESOLVED_MERGE"
        assert decision.twin_event_ids == (14787413,)

    def test_rows_exactly_max_twin_delta_apart_are_one_cluster(self):
        espn = record({"a team"}, {"b team"})
        start = utc("2026-05-14T10:00:00")
        decision = decide_group(
            espn,
            [
                row(1, "A Team", "B Team", at=start),
                row(2, "A Team", "B Team", at=start + MAX_TWIN_DELTA),
            ],
        )
        assert decision.outcome == "RESOLVED_MERGE"

    def test_rows_beyond_max_twin_delta_are_two_fixtures(self):
        espn = record({"a team"}, {"b team"}, starts_at=utc("2026-05-14T10:00:00"))
        start = utc("2026-05-14T10:00:00")
        decision = decide_group(
            espn,
            [
                row(1, "A Team", "B Team", at=start),
                row(2, "A Team", "B Team", at=start + MAX_TWIN_DELTA + timedelta(minutes=1)),
            ],
        )
        assert decision.outcome == "RESOLVED_ONE"
        assert decision.keep_event_id == 1
        assert decision.unstamp_event_ids == (2,)


# ---------------------------------------------------------------------------
# The doubleheader / wrong-day case, where weight would pick the WRONG row.
# ---------------------------------------------------------------------------


class TestTheAuthoritySelectsTheClusterAndWeightDoesNot:
    def test_401816574_keeps_the_empty_row_on_espns_date_over_the_heavy_next_day_row(self):
        """The case that rewrote this module.

        ESPN 401816574 is the 8/18 Orioles v Yankees. We hold two rows: the 8/19
        game (30 markets, 3,682 snapshots, a real score) wearing this id, and
        the 8/18 game (nothing on it, clock four hours out). Weight picks the
        first and is wrong. ESPN's own calendar date picks the second.
        """
        espn = record(
            {"baltimore orioles"}, {"new york yankees"},
            starts_at=utc("2026-08-18T22:35:00"),
        )
        decision = decide_group(
            espn,
            [
                row(15200817, "Baltimore Orioles", "New York Yankees",
                    at=utc("2026-08-19T22:35:00"), weight=3712, external=True),
                row(15201192, "Baltimore Orioles", "New York Yankees",
                    at=utc("2026-08-18T18:35:00")),
            ],
            authority_id="401816574",
        )
        assert decision.outcome == "RESOLVED_ONE"
        assert decision.keep_event_id == 15201192
        assert decision.unstamp_event_ids == (15200817,)
        verdicts = {v.event_id: v.verdict for v in decision.rows}
        assert verdicts[15200817] == "TIME_DISAGREES"

    def test_a_row_inside_the_window_outranks_a_row_merely_on_the_date(self):
        espn = record({"a team"}, {"b team"}, starts_at=utc("2026-05-14T20:00:00"))
        decision = decide_group(
            espn,
            [
                row(1, "A Team", "B Team", at=utc("2026-05-14T02:00:00")),
                row(2, "A Team", "B Team", at=utc("2026-05-14T21:00:00")),
            ],
        )
        assert decision.keep_event_id == 2

    def test_two_clusters_on_the_authoritys_own_date_is_a_refusal_not_a_tie_break(self):
        """A real doubleheader. Nothing here can say which half ESPN meant."""
        espn = record({"a team"}, {"b team"}, starts_at=utc("2026-05-14T20:00:00"))
        decision = decide_group(
            espn,
            [
                row(1, "A Team", "B Team", at=utc("2026-05-14T02:00:00")),
                row(2, "A Team", "B Team", at=utc("2026-05-14T12:00:00")),
            ],
        )
        assert decision.outcome == "AMBIGUOUS"
        assert decision.keep_event_id is None
        assert decision.unstamp_event_ids == ()


# ---------------------------------------------------------------------------
# Refusals. The two outcomes that write nothing.
# ---------------------------------------------------------------------------


class TestRefusals:
    def test_a_dark_authority_is_not_a_verdict(self):
        """401504210 returns a 502 today. An absent answer must not unstamp."""
        decision = decide_group(
            None,
            [
                row(14794949, "Winnipeg Blue Bombers", "Toronto Argonauts"),
                row(14970487, "Winnipeg Blue Bombers", "Toronto Argonauts"),
            ],
            authority_id="401504210",
        )
        assert decision.outcome == "AUTHORITY_UNAVAILABLE"
        assert decision.unstamp_event_ids == ()
        assert decision.keep_event_id is None

    def test_a_half_populated_record_decides_nothing(self):
        decision = decide_group(
            record({"a team"}, set()), [row(1, "A Team", "B Team")]
        )
        assert decision.outcome == "AUTHORITY_UNAVAILABLE"

    def test_401882924_now_resolves_because_the_vocabulary_gap_closed(self):
        """ESPN publishes "Osasuna"; we hold "CA Osasuna". #2792 closed that gap.

        This case used to assert ``NO_ROW_AGREES``, and that refusal was the
        DEFECT rather than the rule: two rows wore one id, ESPN said which date
        the game is, and the only thing stopping the rail resolving it was a
        leading club initialism. With ``canonical_forms`` both rows now agree on
        teams, the clock separates them, and the row on ESPN's date keeps the id
        while the other hands it back.

        Unstamped, never deleted (ruling 079) — the loser gives up its claim to
        the id, not its existence.
        """
        espn = record({"celta vigo"}, {"osasuna"}, starts_at=utc("2026-08-31T19:00:00"))
        decision = decide_group(
            espn,
            [
                row(14970077, "Celta Vigo", "CA Osasuna", at=utc("2026-08-20T19:00:00")),
                row(15198264, "Celta Vigo", "CA Osasuna", at=utc("2026-08-31T19:00:00")),
            ],
            authority_id="401882924",
        )
        assert decision.outcome == "RESOLVED_ONE"
        assert decision.keep_event_id == 15198264
        assert decision.unstamp_event_ids == (14970077,)

    def test_a_vocabulary_gap_no_structural_rule_reaches_still_refuses(self):
        """The refusal this class is really about, on a gap #2792 does NOT close.

        ESPN calls them "Athletic Club"; we hold "Athletic Bilbao". That is a
        genuine synonym, not punctuation or an affix, and no reduction reaches
        it — deliberately, because the rule that would is the rule that also
        concludes Ohio State and Texas State are one school. It stays a refusal
        and writes nothing, which is the safe direction.
        """
        espn = record({"athletic club"}, {"elche"}, starts_at=utc("2026-08-31T19:00:00"))
        decision = decide_group(
            espn,
            [row(15298237, "Athletic Bilbao", "Elche CF", at=utc("2026-08-31T19:00:00"))],
            authority_id="401882925",
        )
        assert decision.outcome == "NO_ROW_AGREES"
        assert decision.unstamp_event_ids == ()

    def test_a_blank_team_name_never_matches(self):
        espn = record({"a team"}, {"b team"})
        decision = decide_group(espn, [row(1, "", "B Team")])
        assert decision.outcome == "NO_ROW_AGREES"

    def test_no_writing_outcome_reports_writes_false(self):
        for decision in (
            decide_group(None, [row(1, "A", "B")]),
            decide_group(record({"a team"}, {"b team"}), [row(1, "X", "Y")]),
        ):
            assert decision.writes is False


# ---------------------------------------------------------------------------
# The keeper's tie-break, and the stability a re-run depends on.
# ---------------------------------------------------------------------------


class TestKeeperOrdering:
    def test_most_dependents_wins_then_sourced_then_oldest(self):
        espn = record({"a team"}, {"b team"})
        rows = [
            row(300, "A Team", "B Team", weight=0),
            row(100, "A Team", "B Team", weight=5),
            row(200, "A Team", "B Team", weight=5, external=True),
        ]
        assert decide_group(espn, rows).keep_event_id == 200

    def test_the_same_input_picks_the_same_keeper_whatever_the_row_order(self):
        """A second pass after a partial apply must not undo the first."""
        espn = record({"a team"}, {"b team"})
        rows = [
            row(300, "A Team", "B Team"),
            row(100, "A Team", "B Team"),
            row(200, "A Team", "B Team"),
        ]
        first = decide_group(espn, rows).keep_event_id
        second = decide_group(espn, list(reversed(rows))).keep_event_id
        assert first == second == 100

    def test_a_timeless_row_beside_timed_ones_refuses_instead_of_joining_one(self):
        """An absent clock is not evidence of belonging to any cluster."""
        espn = record({"a team"}, {"b team"}, starts_at=utc("2026-05-14T20:00:00"))
        decision = decide_group(
            espn,
            [
                row(1, "A Team", "B Team", at=utc("2026-05-14T20:00:00")),
                row(2, "A Team", "B Team", at=None),
            ],
        )
        assert decision.keep_event_id == 1
        assert decision.unstamp_event_ids == (2,)

    def test_rows_none_of_which_carry_a_clock_are_twins_not_an_ambiguity(self):
        """One cluster per row here would manufacture a refusal out of a field
        none of them has."""
        espn = record({"a team"}, {"b team"}, starts_at=utc("2026-05-14T20:00:00"))
        decision = decide_group(
            espn,
            [row(1, "A Team", "B Team", at=None), row(2, "A Team", "B Team", at=None)],
        )
        assert decision.outcome == "RESOLVED_MERGE"
        assert decision.keep_event_id == 1


# ---------------------------------------------------------------------------
# The census the bus re-derives.
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_counts_outcomes_verdicts_and_the_two_write_totals(self):
        espn = record({"a team"}, {"b team"}, starts_at=utc("2026-05-14T10:00:00"))
        decisions = [
            decide_group(espn, [
                row(1, "A Team", "B Team", at=utc("2026-05-14T10:00:00")),
                row(2, "A Team", "B Team", at=utc("2026-05-14T10:00:00")),
            ]),
            decide_group(espn, [
                row(3, "A Team", "B Team", at=utc("2026-05-14T10:00:00")),
                row(4, "Other", "Rows", at=utc("2026-05-14T10:00:00")),
            ]),
            decide_group(None, [row(5, "A Team", "B Team")]),
        ]
        stats = summarize(decisions)
        assert stats["groups"] == 3
        assert stats["outcomes"]["RESOLVED_MERGE"] == 1
        assert stats["outcomes"]["RESOLVED_ONE"] == 1
        assert stats["outcomes"]["AUTHORITY_UNAVAILABLE"] == 1
        assert stats["rows_to_unstamp"] == 2
        assert stats["rows_that_are_twins"] == 1
        assert stats["row_verdicts"]["AGREES_TWIN"] == 1

    def test_groups_unresolved_is_what_blocks_the_unique_index(self):
        espn = record({"a team"}, {"b team"})
        stats = summarize([
            decide_group(espn, [row(1, "A Team", "B Team")]),
            decide_group(None, [row(2, "A Team", "B Team")]),
            decide_group(espn, [row(3, "X", "Y")]),
        ])
        assert stats["groups_unresolved"] == 2


# ---------------------------------------------------------------------------
# The plan's content address, which the apply is bound to.
# ---------------------------------------------------------------------------


class TestPlanHash:
    def test_the_hash_is_over_the_work_and_not_over_the_clock(self):
        from app.tasks.repair_authority_id_collisions import plan_hash_for

        base = [{"event_id": 1, "contested_espn_id": "9", "verdict": "AGREES_TWIN"}]
        decorated = [dict(base[0], matchup="A v B", dependents=7, espn="ESPN")]
        # A reviewer who re-runs the dry run to look again must be handed a hash
        # that still opens the plan they read.
        assert plan_hash_for(base) == plan_hash_for(decorated)

    def test_a_different_work_list_is_a_different_hash(self):
        from app.tasks.repair_authority_id_collisions import plan_hash_for

        assert plan_hash_for(
            [{"event_id": 1, "contested_espn_id": "9", "verdict": "AGREES_TWIN"}]
        ) != plan_hash_for(
            [{"event_id": 2, "contested_espn_id": "9", "verdict": "AGREES_TWIN"}]
        )

    def test_an_empty_plan_still_has_an_address(self):
        from app.tasks.repair_authority_id_collisions import plan_hash_for

        assert len(plan_hash_for([])) == 32


# ---------------------------------------------------------------------------
# ESPN's summary body -> the record. The absence/answer split.
# ---------------------------------------------------------------------------


class TestRecordFromSummary:
    def _payload(self):
        return {
            "header": {
                "competitions": [{
                    "date": "2026-05-14T23:00Z",
                    "competitors": [
                        {"homeAway": "home", "team": {
                            "id": "148", "displayName": "Alabama Crimson Tide",
                            "location": "Alabama", "name": "Crimson Tide"}},
                        {"homeAway": "away", "team": {
                            "id": "92", "displayName": "Ole Miss Rebels",
                            "location": "Ole Miss", "name": "Rebels"}},
                    ],
                }]
            }
        }

    def test_reads_both_sides_the_start_and_the_team_ids(self):
        from app.tasks.repair_authority_id_collisions import record_from_summary

        got = record_from_summary("401847094", self._payload())
        assert got is not None and got.usable
        assert "alabama crimson tide" in got.home_names
        assert "ole miss" in got.away_names
        assert got.home_team_id == "148"
        assert got.starts_at == utc("2026-05-14T23:00:00")

    @pytest.mark.parametrize("payload", [None, {}, {"header": {}}, {"header": {"competitions": []}}])
    def test_an_absent_body_is_none_and_never_a_blank_record(self, payload):
        from app.tasks.repair_authority_id_collisions import record_from_summary

        # A blank record would reach `decide_group` as an authority that names
        # nobody; `None` reaches it as AUTHORITY_UNAVAILABLE, which is the truth.
        assert record_from_summary("1", payload) is None
