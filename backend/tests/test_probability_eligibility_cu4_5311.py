"""CU-4 (#5311) — the eligibility record that makes a stored reading gradeable.

THE DEFECT THIS GUARDS, stated as the thing that is missing rather than a thing
that is wrong. `admissible_as_blend_speaker` (#5031) is a WRITER-side gate: it is
called from exactly two places, both inside `live_blend.py`. Serving does not go
near it — `compute_aggregate_probability` re-weights `win_probability_sources`
JSONB at request time and does no query at all. So once a reading is stamped, an
entry written by the gated writer and an entry written by an ungated one are
indistinguishable: the stored shape is `{"value": x, "updated_at": "..."}` and it
names neither the market the number came from nor the rule that let it speak.

#5031's own specimen — event 15301219 holding 0.070 off an Exact Score `2 - 2`
leg while Kalshi read 0.705 — was not found in the column. It was found by
re-deriving the reading from the markets, because the column cannot say. That is
what makes the ticket's acceptance criterion ("zero ineligible probability inputs
in the served payload") unanswerable, and it is Alex's "stale JSONB cannot bypass
it" clause on #5273.

The evidence already exists at the write moment and is thrown away:
`BlendReading` carries the market that spoke, and `_phase2_persist_group_reading`
writes it into the SNAPSHOT's `game_state` ("why did the blend say that has to
name the one that said it") while stamping only value+time onto the reading. The
snapshot is a different table, written only when `write_snapshot=True`, and no
serve-time reader joins it.

THE TWO PROPERTIES THAT MATTER, and they pull in opposite directions:

  * The record must be MINTED BY THE GATE and name the SPEAKER, not the group's
    primary. Those differ exactly on the rows #5031 is about, and a record
    naming the primary would be worse than no record — it would substantiate a
    reading with a market that did not produce it (`TestTheRecordNamesTheSpeaker`).
  * The record must be ADDITIVE. The live population is entirely record-free, so
    a gate that refused the unrecorded would blank every hero on the site. A
    reading with no record must compute bit-for-bit what it computes today
    (`TestAbsenceChangesNothing`). Widening that is CU-1R's attended repair.
"""

from datetime import datetime, timezone

import pytest

from app.utils.aggregation import (
    compute_aggregate_probability,
    parse_source_entry,
    stamp_source_reading,
)
from app.utils.live_blend import (
    BLEND_ADMISSION_RULE,
    MarketOutcomes,
    compute_source_home_probability,
    select_primary_market,
)
from app.utils.probability_eligibility import (
    ELIGIBILITY_KEY,
    ELIGIBILITY_RECORD_VERSION,
    INELIGIBLE,
    NOT_APPLICABLE,
    SCOPE_FULL_EVENT_WINNER,
    UNVERIFIED,
    VERIFIED,
    from_entry,
    grade_entry,
    grade_sources,
    ineligible_record,
    is_refused,
    verified_record,
)


NOW = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)

HOME = "St. Louis City SC"
AWAY = "Minnesota United FC"


class _Market:
    def __init__(self, mid, name, *, source="polymarket", external_id=None):
        self.id = mid
        self.name = name
        self.source = source
        self.external_id = external_id


class _Outcome:
    current_yes_bid = current_yes_ask = None

    def __init__(self, rank, name, probability):
        self.rank = rank
        self.name = name
        self.current_probability = probability


class _EventRow:
    """Only the attributes `compute_aggregate_probability` actually reads."""

    def __init__(self, wps=None, *, status=None, espn=None, opening=None):
        self.win_probability_sources = wps
        self.status = status
        self.espn_win_prob_home = espn
        self.opening_home_probability = opening


def _entry(value, record=None):
    """A `win_probability_sources` entry in the shape the writers produce."""
    out = {"value": value, "updated_at": NOW.isoformat()}
    if record is not None:
        out[ELIGIBILITY_KEY] = record.to_entry()
    return out


# =============================================================================
# The record is minted by the gate, and names the row that actually spoke
# =============================================================================


class TestTheRecordNamesTheSpeaker:
    """CERT-767's lesson, now load-bearing for the audit trail as well.

    `select_primary_market`'s tie-break among equals is "lowest market id", and
    `is_game_winner_market` is hard-False for every non-Kalshi source — so for
    Polymarket "primary" degrades to "oldest row", and Polymarket mints its
    derivative books before the match-winner child. The blend therefore falls
    through the group, and the row that speaks is routinely not the primary.
    """

    def _group(self):
        # id 1 is the OLDEST row and an Exact Score derivative: the shape that
        # wins `select_primary_market` and loses `admissible_as_blend_speaker`.
        derivative = MarketOutcomes(
            market=_Market(1, f"{HOME} vs. {AWAY} - Exact Score"),
            outcomes=[
                _Outcome(0, f"{HOME} 2 - 2 {AWAY}", 0.07),
                _Outcome(1, "Other", 0.93),
            ],
        )
        winner = MarketOutcomes(
            market=_Market(9, f"{HOME} vs. {AWAY}", external_id="0xa85e"),
            outcomes=[_Outcome(0, HOME, 0.62), _Outcome(1, AWAY, 0.38)],
        )
        return [derivative, winner]

    def test_the_fixture_really_does_split_primary_from_speaker(self):
        """Not vacuous: the primary must genuinely be the row that cannot speak.

        Without this the whole class could pass on a group whose primary IS the
        winner, and it would be asserting nothing.
        """
        group = self._group()
        assert select_primary_market(group).market.id == 1

        reading = compute_source_home_probability(group, HOME, AWAY)
        assert reading is not None
        assert reading.market.id == 9

    def test_the_record_names_the_speaker_not_the_primary(self):
        reading = compute_source_home_probability(self._group(), HOME, AWAY)

        record = reading.eligibility
        assert record is not None
        assert record.status == VERIFIED
        assert record.market_id == 9, "named the primary — substantiates the wrong row"
        assert record.source_market_id == "0xa85e"

    def test_the_record_carries_the_scope_and_the_rule_that_admitted_it(self):
        """A bare "winner" is insufficient — set winner and match winner are
        winners of different things (T15 admission rule 4), so the scope is
        stated rather than implied. The rule is qualified by its issue so a
        stored record stays legible after the function is edited."""
        reading = compute_source_home_probability(self._group(), HOME, AWAY)

        assert reading.eligibility.scope == SCOPE_FULL_EVENT_WINNER
        assert reading.eligibility.rule == BLEND_ADMISSION_RULE
        assert "5031" in BLEND_ADMISSION_RULE

    def test_a_group_that_cannot_speak_mints_no_record(self):
        """The gate refusing is not the same event as the gate admitting. A
        record here would be an assertion about a reading that does not exist."""
        only_a_derivative = [
            MarketOutcomes(
                market=_Market(1, f"{HOME} vs. {AWAY} - Total Corners"),
                outcomes=[_Outcome(0, "Over 9.5", 0.5), _Outcome(1, "Under 9.5", 0.5)],
            )
        ]
        assert compute_source_home_probability(only_a_derivative, HOME, AWAY) is None


# =============================================================================
# The stamp carries it, and never silently drops what a sibling writer wrote
# =============================================================================


class TestStampSourceReadingCarriesTheRecord:
    def test_the_record_round_trips_through_the_column(self):
        stamped = stamp_source_reading(
            {}, "polymarket", 0.62, now=NOW,
            eligibility=verified_record(rule="r@1", market_id=9, source_market_id="0xa85e"),
        )

        record = from_entry(stamped["polymarket"])
        assert record is not None
        assert (record.status, record.market_id, record.source_market_id) == (
            VERIFIED, 9, "0xa85e",
        )
        # The old readers must be untouched by the new key.
        assert parse_source_entry(stamped["polymarket"]) == (0.62, NOW)

    def test_omitting_the_record_does_not_clear_one_a_sibling_writer_wrote(self):
        """The writers run at different cadences over the same event — the
        15-minute matcher, the 120-second poll, the WS fast lane. A writer that
        passed `eligibility=None` and CLEARED the key would make the column
        oscillate between substantiated and not, at whichever cadence is faster,
        and the census would measure the race rather than the coverage.
        """
        first = stamp_source_reading(
            {}, "polymarket", 0.62, now=NOW,
            eligibility=verified_record(rule="r@1", market_id=9),
        )
        second = stamp_source_reading(first, "polymarket", 0.63, now=NOW)

        assert second["polymarket"]["value"] == 0.63
        assert from_entry(second["polymarket"]).market_id == 9

    def test_the_record_is_a_sibling_of_value_never_inside_it(self):
        """#4120's shape. iOS `WinProbValue` accepts Double or String and THROWS
        on anything else, and the whole `EventDetail` fails with it — so a record
        nested inside `value` would take the app's event page down."""
        stamped = stamp_source_reading(
            {}, "kalshi", 0.7, now=NOW, eligibility=verified_record(rule="r@1"),
        )

        assert isinstance(stamped["kalshi"]["value"], float)
        assert ELIGIBILITY_KEY in stamped["kalshi"]

    def test_stamping_preserves_unrelated_sibling_keys(self):
        existing = {"kalshi": {"value": 0.5, "weight": 0.8, "home_probability": 0.5}}
        stamped = stamp_source_reading(
            existing, "kalshi", 0.7, now=NOW, eligibility=verified_record(rule="r@1"),
        )

        assert stamped["kalshi"]["weight"] == 0.8
        assert stamped["kalshi"]["home_probability"] == 0.5


# =============================================================================
# Reading a record can never be the thing that takes a page down
# =============================================================================


class TestFromEntryNeverRaises:
    @pytest.mark.parametrize(
        "raw",
        [
            None,
            0.62,
            "0.62",
            [],
            {},
            {"value": 0.62},                                   # legacy stamped shape
            {"value": 0.62, ELIGIBILITY_KEY: None},
            {"value": 0.62, ELIGIBILITY_KEY: "verified"},      # not a dict
            {"value": 0.62, ELIGIBILITY_KEY: {}},              # no version
            {"value": 0.62, ELIGIBILITY_KEY: {"v": "1", "status": VERIFIED}},
            {"value": 0.62, ELIGIBILITY_KEY: {"v": True, "status": VERIFIED}},
            {"value": 0.62, ELIGIBILITY_KEY: {"v": 1}},        # no status
            {"value": 0.62, ELIGIBILITY_KEY: {"v": 1, "status": "made_up"}},
        ],
    )
    def test_an_unreadable_record_is_no_assertion_rather_than_an_exception(self, raw):
        """The monotone default, exactly as an unparseable `updated_at` degrades
        to full weight. This runs on the request path over a column that provably
        holds several shapes at once."""
        assert from_entry(raw) is None
        assert is_refused(raw) is False

    def test_a_future_version_reads_as_no_assertion_not_as_verified(self):
        """A rolling deploy puts an old reader in front of a new writer as a
        matter of course. A reader cannot substantiate what it cannot interpret,
        and guessing VERIFIED would be the one direction that is unsafe."""
        future = {
            "value": 0.62,
            ELIGIBILITY_KEY: {
                "v": ELIGIBILITY_RECORD_VERSION + 1,
                "status": VERIFIED,
                "market_id": 9,
            },
        }
        assert from_entry(future) is None
        assert grade_entry("polymarket", future) == UNVERIFIED

    def test_a_future_version_refusal_is_also_not_honoured(self):
        """The same rule in the other direction, stated because it is the one a
        reader is tempted to make an exception for: honouring a refusal we cannot
        interpret would let a newer writer blank a source through a field this
        reader does not understand."""
        future_refusal = {
            "value": 0.62,
            ELIGIBILITY_KEY: {"v": ELIGIBILITY_RECORD_VERSION + 1, "status": INELIGIBLE},
        }
        assert is_refused(future_refusal) is False


# =============================================================================
# The grade, and what it means for a source that never had the defect
# =============================================================================


class TestTheGrade:
    def test_a_market_derived_source_with_no_record_is_unverified(self):
        assert grade_entry("polymarket", {"value": 0.62}) == UNVERIFIED
        assert grade_entry("kalshi", {"value": 0.62}) == UNVERIFIED

    @pytest.mark.parametrize(
        "source", ["betting", "espn", "stat_model", "mlb", "final_result"]
    )
    def test_a_source_that_cannot_pick_the_wrong_sibling_is_not_applicable(self, source):
        """None of these selects among sibling questions: each is a model, a
        purpose-built consensus over one market key, or the resolved score. There
        is no wrong sibling to pick, so the ABSENCE of a record is expected.
        Grading them UNVERIFIED would bury the two sources that matter under five
        that never had the defect."""
        assert grade_entry(source, {"value": 0.62}) == NOT_APPLICABLE

    def test_a_record_present_on_such_a_source_is_still_read_on_its_merits(self):
        entry = _entry(0.62, verified_record(rule="r@1", market_id=3))
        assert grade_entry("betting", entry) == VERIFIED

    def test_grade_sources_grades_every_key_it_is_given(self):
        """A denominator built by skipping rows is how a recut "improves" by
        shrinking. The decision about what counts belongs to the census."""
        graded = grade_sources(
            {
                "polymarket": {"value": 0.62},
                "betting": {"value": 0.31},
                "kalshi": _entry(0.70, verified_record(rule="r@1", market_id=9)),
                "statpal_injuries": [],
            }
        )
        assert graded == {
            "polymarket": UNVERIFIED,
            "betting": NOT_APPLICABLE,
            "kalshi": VERIFIED,
            "statpal_injuries": NOT_APPLICABLE,
        }

    def test_grade_sources_tolerates_a_column_that_is_not_a_dict(self):
        assert grade_sources(None) == {}
        assert grade_sources([]) == {}


# =============================================================================
# The read-side gate: narrow on purpose, and inert on today's population
# =============================================================================


class TestAbsenceChangesNothing:
    """The additive claim, pinned to concrete numbers rather than to a diff.

    The live population carries no records at all, so if this class can fail the
    ship blanks heroes across the site.
    """

    def test_an_unrecorded_event_computes_what_it_computes_today(self):
        """0.35 is espn, and it is espn because of #1829's SHARE CAP: betting's
        base 3.0 is 56.6% of the 5.3 total, so it would straddle the midpoint by
        itself and the cap stops it. Pinned to that number rather than to
        "whatever betting says" precisely because the naive expectation here is
        0.31 — a guard that encoded the naive answer would fail for the right
        reason and be "fixed" by loosening it."""
        event = _EventRow(
            {
                "betting": {"value": 0.31, "updated_at": NOW.isoformat()},
                "kalshi": {"value": 0.70, "updated_at": NOW.isoformat()},
                "espn": {"value": 0.35, "updated_at": NOW.isoformat()},
            }
        )
        assert compute_aggregate_probability(event) == 0.35

    def test_the_legacy_bare_float_shape_is_untouched(self):
        assert compute_aggregate_probability(_EventRow({"betting": 0.42})) == 0.42

    def test_a_verified_record_does_not_move_the_number_either(self):
        """A record is evidence, not a weight. Admission is binary here: an
        admitted reading counts exactly as much as it counted before anyone
        wrote down why it was admitted."""
        bare = _EventRow({"kalshi": {"value": 0.70}, "betting": {"value": 0.31}})
        recorded = _EventRow(
            {
                "kalshi": _entry(0.70, verified_record(rule="r@1", market_id=9)),
                "betting": {"value": 0.31},
            }
        )
        assert compute_aggregate_probability(recorded) == compute_aggregate_probability(bare)


class TestAPositiveRefusalIsHonoured:
    """#5031's shape: a Polymarket derivative's price sitting beside Kalshi's
    real winner line, both at weight 0.8, the derivative dragging the hero.

    The pair is deliberately 30 points apart and not 63: the divergence gate
    (ruling (b)) fires at 40 and would return Kalshi's number on its own, which
    would make the refusal LOOK effective while proving nothing about it.
    """

    ADMITTED = {
        "kalshi": {"value": 0.60, "updated_at": NOW.isoformat()},
        "polymarket": {"value": 0.30, "updated_at": NOW.isoformat()},
    }

    def test_the_leg_is_load_bearing_when_it_is_admitted(self):
        """Not vacuous: without this, the refusal test below could pass on an
        entry that never moved the number in the first place."""
        assert compute_aggregate_probability(_EventRow(dict(self.ADMITTED))) == 0.30

    def test_a_refused_reading_does_not_reach_the_hero(self):
        refused = dict(self.ADMITTED)
        refused["polymarket"] = _entry(
            0.30, ineligible_record(rule="cu1r@5310", reason="exact_score_leg"),
        )
        # Kalshi alone: the refused leg contributes no weight and no value.
        assert compute_aggregate_probability(_EventRow(refused)) == 0.60

    def test_the_refusal_and_deleting_the_key_agree(self):
        """A refused entry must behave as though the source said nothing —
        not as a zero, not as a half-weight vote."""
        refused = dict(self.ADMITTED)
        refused["polymarket"] = _entry(0.30, ineligible_record(rule="cu1r@5310"))
        deleted = {"kalshi": dict(self.ADMITTED["kalshi"])}

        assert compute_aggregate_probability(
            _EventRow(refused)
        ) == compute_aggregate_probability(_EventRow(deleted))

    def test_refusing_every_tier1_reading_falls_through_rather_than_returning_none(self):
        """A refusal removes a source; it must not remove the event. Tier 2 and
        tier 3 are the honest answers once tier 1 has nothing left."""
        event = _EventRow(
            {"polymarket": _entry(0.07, ineligible_record(rule="cu1r@5310"))},
            espn=0.44,
        )
        assert compute_aggregate_probability(event) == 0.44

    def test_an_unverified_reading_is_admitted(self):
        """The gate is POSITIVE refusals only. "We have not asked" is not "no" —
        collapsing the two would take the site dark to fix a defect measured at
        ~10 events, and the wider gate is CU-1R's attended repair with a backup
        and a one-command undo."""
        event = _EventRow({"polymarket": {"value": 0.07, "updated_at": NOW.isoformat()}})
        assert compute_aggregate_probability(event) == 0.07


# =============================================================================
# The served payload — driven through the real serializer, not a source scan
# =============================================================================


def _serve(sources):
    """`_format_event`'s `win_probability_sources` block, for real.

    A source scan (`"is_refused" in inspect.getsource(...)`) would pass on a
    call that is present and unreachable, and on one whose result is discarded.
    The serializer is cheap to drive with an unsaved ORM instance, so drive it.
    """
    from app.models.models import Event
    from app.routes.events import _format_event

    event = Event(
        id=1,
        external_id="cu4",
        home_team_name="H",
        away_team_name="A",
        commence_time=NOW,
        win_probability_sources=sources,
    )
    return _format_event(event).get("win_probability_sources") or {}


class TestTheServedPayload:
    def test_a_refused_leg_is_not_served_as_a_source_row(self):
        """This loop reads the JSONB directly rather than through
        `_tier1_readings`, so without its own refusal the hero would be computed
        WITHOUT the entry while the source list printed it — one screen
        contradicting itself with a number nothing on the page stands behind."""
        served = _serve(
            {
                "kalshi": _entry(0.60),
                "polymarket": _entry(0.30, ineligible_record(rule="cu1r@5310")),
            }
        )
        assert set(served) == {"kalshi"}

    def test_the_same_leg_is_served_when_nothing_refuses_it(self):
        """Not vacuous: the row must be one the serializer would otherwise emit."""
        served = _serve({"kalshi": _entry(0.60), "polymarket": _entry(0.30)})
        assert set(served) == {"kalshi", "polymarket"}

    def test_every_served_source_carries_an_evidence_status(self):
        """Emitted even for the sources that can never carry a record. An absent
        key would be ambiguous between "this server predates CU-4" and "this
        source is not applicable", and a census that collapses those counts a
        deployment gap as a clean result."""
        served = _serve({"betting": _entry(0.31), "polymarket": _entry(0.30)})

        assert served["betting"]["evidence_status"] == NOT_APPLICABLE
        assert served["polymarket"]["evidence_status"] == UNVERIFIED

    def test_a_verified_leg_serves_its_scope_and_contract_version(self):
        served = _serve(
            {
                "kalshi": _entry(
                    0.70,
                    verified_record(
                        rule=BLEND_ADMISSION_RULE, market_id=9, source_market_id="KX",
                    ),
                )
            }
        )
        assert served["kalshi"]["evidence_status"] == VERIFIED
        assert served["kalshi"]["verified_scope"] == SCOPE_FULL_EVENT_WINNER
        assert served["kalshi"]["contract_version"] == BLEND_ADMISSION_RULE

    def test_the_new_fields_are_purely_additive_for_an_old_client(self):
        """The acceptance criterion's "old-client decoding fixture passes", in
        the form the server can own. iOS types this `[String: WinProbSource]`
        and `WinProbValue` THROWS on a non-Double/String inside `value`, while a
        Swift `Decodable` struct ignores an unknown SIBLING — which is exactly
        how `updated_at` was added safely in #1829. So the guard is: every key
        an old client reads is unchanged, and nothing new is nested under
        `value`.
        """
        row = _serve({"betting": _entry(0.31)})["betting"]

        assert isinstance(row["value"], float)
        assert row["value"] == 0.31
        assert row["updated_at"] == NOW.isoformat()
        assert row["display_name"] and row["type"] and row["color"]
        assert set(row) - {
            "value", "updated_at", "display_name", "type", "color",
        } == {"evidence_status"}, "a new key beyond the additive eligibility set"

    def test_a_refused_leg_does_not_manufacture_discover_disagreement(self):
        """Eligibility BEFORE ranking, which is the ticket's stated ordering.

        `_numeric_source_probs` feeds `cross_source_agreement` (`max - min <=
        0.10`) and thence `compute_confidence_score`. A refused derivative at
        0.30 beside a real winner line at 0.60 makes the spread 0.30 and the
        verdict False — so the Discover card of the very event whose hero
        excluded that number would take a "sources disagree" penalty FOR it.
        That is #4120's arithmetic in a second costume.
        """
        from app.routes.feed import _numeric_source_probs

        admitted = {"kalshi": _entry(0.60), "polymarket": _entry(0.30)}
        refused = {
            "kalshi": _entry(0.60),
            "polymarket": _entry(0.30, ineligible_record(rule="cu1r@5310")),
        }

        # Not vacuous: the leg is one that WOULD have widened the spread.
        assert sorted(_numeric_source_probs(admitted)) == [0.30, 0.60]
        assert _numeric_source_probs(refused) == [0.60]

    def test_a_malformed_record_does_not_lose_the_source_row(self):
        """The serializer's own history is a payload key taking the iOS event
        page down on 89 events (#4120). An unreadable record must cost the
        reader nothing more than the record."""
        served = _serve(
            {"kalshi": {"value": 0.6, ELIGIBILITY_KEY: "not-a-dict"}}
        )
        assert served["kalshi"]["value"] == 0.6
        assert served["kalshi"]["evidence_status"] == UNVERIFIED
