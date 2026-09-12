"""CU-1 clause (2) (#5273) — a market's KIND is written down, and it is additive.

WHAT THIS CLAUSE IS. Clause (4) taught `PolymarketMarket` to retain Gamma's own
`sportsMarketType`. Measured against Gamma itself (100 markets, 2026-09-12), the
field is real, it is an OPEN SET of 13 values, and it is ABSENT on 21 of them.
It travelled on the DTO and was persisted NOWHERE, so no reader downstream of
the poller could see it. This clause stores it, beside our own reading of the
question, at `market_metadata['content_understanding_v1']`.

🔴 THE SPECIMEN THIS SUITE EXISTS FOR: `child_moneyline`. It is winner-SHAPED
and it is NOT the contest's winner — the observed row is
`Counter-Strike: Nemiga vs Just Players - Map 1 Winner`. Our title recognizer
reads it as a winner (it carries the word "Winner"); Gamma calls it
`child_moneyline`; and the two disagreeing is the signal. Publishing that row's
price as the match winner is the same defect class as #5432 and #5311, where a
derivative's price was served as the match result.

WHY THE VENUE'S LABEL MAY NEVER GATE. It is absent on 21% of markets, and
`is_full_contest_winner_type` returns False for a missing label. Reading that
False as "the venue says no" would fail closed on a fifth of the population, so
absence is UNCONFIRMED and is never evidence against a market.
`TestAbsenceIsNotDisagreement` is that rule, pinned.

WHAT THIS CLAUSE DOES NOT DO. It does not gate: no market is refused, no
admission changes, no published number moves. It writes an understanding down so
that a quarantine consumer can later be built on a measured population.
`TestNothingAboutAdmissionChanges` is that boundary.
"""

import ast
import inspect

import pytest

import app.tasks.polymarket as polymarket_task
from app.utils.content_understanding import (
    CONTENT_UNDERSTANDING_KEY,
    CONTENT_UNDERSTANDING_VERSION,
    CONTRADICTED,
    CORROBORATED,
    UNCONFIRMED,
    build_content_understanding,
    is_disputed,
    record_semantic_type,
    semantic_type_for_market,
    understanding_from_metadata,
)
from app.utils.live_blend import (
    MarketOutcomes,
    admissible_as_blend_speaker,
    compute_source_home_probability,
)
from app.utils.probability_eligibility import from_entry, verified_record

HOME = "St. Louis City SC"
AWAY = "Minnesota United FC"

# The measured Counter-Strike row, by name, with its own two competitors — a
# soccer outcome pair under this title would never resolve, and the test would
# be reporting the matchup miss as a gate.
MAP_WINNER = "Counter-Strike: Nemiga vs Just Players - Map 1 Winner"
CS_HOME = "Nemiga"
CS_AWAY = "Just Players"


# =============================================================================
# Fakes — only the attributes the code under test actually reads
# =============================================================================


class _Market:
    def __init__(self, mid, name, *, source="polymarket", external_id=None,
                 market_metadata=None):
        self.id = mid
        self.name = name
        self.source = source
        self.external_id = external_id
        self.market_metadata = market_metadata


class _Outcome:
    current_yes_bid = current_yes_ask = None

    def __init__(self, rank, name, probability):
        self.rank = rank
        self.name = name
        self.current_probability = probability


def _entry(mid, name, outcomes=(), **kw):
    return MarketOutcomes(
        market=_Market(mid, name, **kw),
        outcomes=[_Outcome(r, n, p) for r, n, p in outcomes],
    )


# =============================================================================


class TestTheVenueLabelCorroboratesOrContradicts:
    """Our classifier proposes; Gamma's own label confirms or contradicts."""

    def test_a_real_moneyline_is_corroborated(self):
        u = build_content_understanding(
            name=f"{HOME} vs. {AWAY}", sports_market_type="moneyline"
        )
        assert u["semantic_type"] == "moneyline"
        assert u["venue_type"] == "moneyline"
        assert u["agreement"] == CORROBORATED

    def test_child_moneyline_map_winner_is_CONTRADICTED(self):
        """🔴 The specimen. Winner-shaped title, venue says it is a map winner.

        A containment test (`"moneyline" in "child_moneyline"`) would call this
        corroborated and hand a map winner to the winner slot.
        """
        u = build_content_understanding(
            name=MAP_WINNER, sports_market_type="child_moneyline"
        )
        assert u["semantic_type"] == "moneyline", (
            "our title recognizer reads the word 'Winner' — that is the whole "
            "reason a second, independent signal is needed"
        )
        assert u["venue_type"] == "child_moneyline"
        assert u["agreement"] == CONTRADICTED

    def test_a_derivative_both_signals_reject_is_corroborated(self):
        """Agreement is agreement on the WINNER question, in both directions."""
        u = build_content_understanding(
            name=f"{HOME} vs. {AWAY} - Exact Score",
            sports_market_type="soccer_exact_score",
        )
        assert u["semantic_type"] != "moneyline"
        assert u["agreement"] == CORROBORATED

    def test_venue_says_winner_and_we_do_not_is_also_a_contradiction(self):
        """The disagreement is symmetric: a winner we failed to recognise is
        just as much a contradiction as a derivative we wrongly admitted."""
        u = build_content_understanding(
            name=f"{HOME} vs. {AWAY} - Total Corners",
            sports_market_type="moneyline",
        )
        assert u["semantic_type"] != "moneyline"
        assert u["agreement"] == CONTRADICTED

    @pytest.mark.parametrize(
        "venue_type",
        # The measured open set, minus `moneyline`. None of these is a
        # full-contest winner, so none may corroborate a winner reading.
        [
            "soccer_exact_score", "spreads", "soccer_team_totals",
            "first_half_totals", "totals", "soccer_first_to_score",
            "first_half_spreads", "soccer_first_half_team_totals",
            "both_teams_to_score", "total_corners", "child_moneyline",
            "soccer_first_half_total_corners",
        ],
    )
    def test_no_observed_value_but_moneyline_corroborates_a_winner(self, venue_type):
        """An open set means the fence is the ALLOWED list, never a denylist."""
        u = build_content_understanding(
            name=f"{HOME} vs. {AWAY}", sports_market_type=venue_type
        )
        assert u["agreement"] == CONTRADICTED


class TestAbsenceIsNotDisagreement:
    """🔴 The field is absent on 21% of markets. Absence may never refuse."""

    def test_an_absent_label_is_unconfirmed_not_contradicted(self):
        u = build_content_understanding(name=f"{HOME} vs. {AWAY}")
        assert u["agreement"] == UNCONFIRMED
        assert u["agreement"] != CONTRADICTED

    def test_an_absent_label_stores_no_venue_type_key(self):
        """A stored null would be a claim that the venue said something.

        gotcha #53 in miniature: a placeholder satisfies a census while
        pointing at nothing, turning a countable gap into an invisible one.
        """
        u = build_content_understanding(name=f"{HOME} vs. {AWAY}")
        assert "venue_type" not in u

    def test_an_unconfirmed_winner_is_not_disputed(self):
        """The 21% must keep a clean type, or a fifth of the population reads
        as disputed and the marker stops meaning anything."""
        u = build_content_understanding(name=f"{HOME} vs. {AWAY}")
        assert record_semantic_type(u) == "moneyline"
        assert not is_disputed(record_semantic_type(u))

    def test_absence_and_a_derivative_label_are_NOT_the_same_answer(self):
        """`is_full_contest_winner_type` is False for both, and the whole point
        of this clause is that those two are different claims."""
        absent = build_content_understanding(name=f"{HOME} vs. {AWAY}")
        present = build_content_understanding(
            name=f"{HOME} vs. {AWAY}", sports_market_type="child_moneyline"
        )
        assert absent["agreement"] != present["agreement"]

    def test_an_unnamed_market_stamps_nothing(self):
        """`None`, not `{}` — the caller merges this into existing metadata and
        an empty object would overwrite a populated key on re-ingest."""
        for empty in (None, ""):
            assert build_content_understanding(name=empty) is None


class TestTheStoredRecordIsReadBack:
    """The reader never raises, and never over-reads."""

    @pytest.mark.parametrize(
        "raw",
        [
            None, "string", 42, [], {},
            {CONTENT_UNDERSTANDING_KEY: None},
            {CONTENT_UNDERSTANDING_KEY: "not a dict"},
            {CONTENT_UNDERSTANDING_KEY: []},
            {CONTENT_UNDERSTANDING_KEY: {}},
            {CONTENT_UNDERSTANDING_KEY: {"v": "1", "semantic_type": "moneyline"}},
            {CONTENT_UNDERSTANDING_KEY: {"v": True, "semantic_type": "moneyline"}},
            {CONTENT_UNDERSTANDING_KEY: {"v": 1}},
            {CONTENT_UNDERSTANDING_KEY: {"v": 1, "semantic_type": ""}},
            {CONTENT_UNDERSTANDING_KEY: {"v": 1, "semantic_type": 7}},
        ],
    )
    def test_a_malformed_record_degrades_to_absent_and_never_raises(self, raw):
        """Request path, over a column that provably holds several shapes at
        once. A malformed subkey must not take down a page."""
        assert understanding_from_metadata(raw) is None

    def test_a_future_version_reads_as_absent(self):
        """A rolling deploy routinely puts an old reader in front of a new
        writer. This reader cannot substantiate what it cannot interpret."""
        assert understanding_from_metadata({
            CONTENT_UNDERSTANDING_KEY: {
                "v": CONTENT_UNDERSTANDING_VERSION + 1,
                "semantic_type": "moneyline",
            }
        }) is None

    def test_a_real_write_round_trips(self):
        u = build_content_understanding(
            name=f"{HOME} vs. {AWAY}", sports_market_type="moneyline"
        )
        assert understanding_from_metadata({CONTENT_UNDERSTANDING_KEY: u}) == u

    def test_the_key_is_top_level(self):
        """The census idiom is jsonb `?`, which does not see nested keys."""
        u = build_content_understanding(name=f"{HOME} vs. {AWAY}")
        assert understanding_from_metadata({"shape": {CONTENT_UNDERSTANDING_KEY: u}}) is None


class TestTheDisputedEncodingCannotDrift:
    """Writer and reader of the `:disputed` marker, pinned to each other."""

    def test_a_contradicted_type_is_reported_as_disputed(self):
        u = build_content_understanding(
            name=MAP_WINNER, sports_market_type="child_moneyline"
        )
        assert record_semantic_type(u) == "moneyline:disputed"
        assert is_disputed(record_semantic_type(u))

    def test_a_corroborated_type_is_reported_plain(self):
        u = build_content_understanding(
            name=f"{HOME} vs. {AWAY}", sports_market_type="moneyline"
        )
        assert record_semantic_type(u) == "moneyline"
        assert not is_disputed(record_semantic_type(u))

    def test_the_reader_agrees_with_the_writer_on_every_agreement_state(self):
        """A round trip through the real writer, so the suffix cannot be
        changed on one side only."""
        cases = [
            (build_content_understanding(name=MAP_WINNER,
                                         sports_market_type="child_moneyline"), True),
            (build_content_understanding(name=f"{HOME} vs. {AWAY}",
                                         sports_market_type="moneyline"), False),
            (build_content_understanding(name=f"{HOME} vs. {AWAY}"), False),
        ]
        for understanding, expected in cases:
            assert is_disputed(record_semantic_type(understanding)) is expected

    def test_no_understanding_is_no_type(self):
        assert record_semantic_type(None) is None
        assert record_semantic_type({}) is None
        assert not is_disputed(None)

    def test_semantic_type_for_a_market_without_metadata_is_none(self):
        """Every row until the poller has re-served it. The field stays absent
        rather than acquiring a fabricated default."""
        assert semantic_type_for_market(_Market(1, "x")) is None
        assert semantic_type_for_market(object()) is None


class TestTheProducerActuallyStampsIt:
    """🔴 The decision function is guarded above; this guards the thing that
    BUILDS its input. A suite that only drives `build_content_understanding`
    with hand-made arguments leaves the ingest free to stop passing them."""

    def test_the_ingest_metadata_builder_carries_the_key(self):
        u = build_content_understanding(
            name=f"{HOME} vs. {AWAY}", sports_market_type="moneyline"
        )
        meta = polymarket_task.sub_market_metadata(
            event_id=42, matchup_title=f"{HOME} vs. {AWAY}", content_understanding=u,
        )
        assert meta is not None
        assert meta[CONTENT_UNDERSTANDING_KEY] == u

    def test_no_understanding_stamps_no_key(self):
        meta = polymarket_task.sub_market_metadata(event_id=42, matchup_title="A vs B")
        assert CONTENT_UNDERSTANDING_KEY not in (meta or {})

    def test_the_understanding_alone_is_enough_to_stamp_metadata(self):
        """It must not depend on another key being present to survive the
        `meta or None` return."""
        u = build_content_understanding(name=f"{HOME} vs. {AWAY}")
        meta = polymarket_task.sub_market_metadata(
            event_id=None, matchup_title=None, content_understanding=u,
        )
        assert meta is not None and meta[CONTENT_UNDERSTANDING_KEY] == u

    def test_the_poller_call_site_passes_the_understanding(self):
        """The wiring guard. `sub_market_metadata` gaining the parameter proves
        nothing if the ingest never fills it — that gap is invisible to every
        test above, because they all pass it by hand.
        """
        tree = ast.parse(inspect.getsource(polymarket_task))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "sub_market_metadata"
        ]
        assert calls, "the ingest no longer calls sub_market_metadata"
        assert any(
            kw.arg == "content_understanding"
            and isinstance(kw.value, ast.Call)
            and getattr(kw.value.func, "id", None) == "build_content_understanding"
            for call in calls
            for kw in call.keywords
        ), (
            "the poller must build the understanding at the call site — it is "
            "the only place the parsed market and Gamma's label are both in hand"
        )

    def test_the_call_site_feeds_it_the_venue_label(self):
        """Building the understanding without `sports_market_type` would store
        a permanently UNCONFIRMED blob and quietly retire clause (4)."""
        tree = ast.parse(inspect.getsource(polymarket_task))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "build_content_understanding"
            ):
                assert {kw.arg for kw in node.keywords} >= {
                    "name", "sports_market_type"
                }
                return
        raise AssertionError("the poller never builds a content understanding")


class TestTheEligibilityRecordCarriesIt:
    """The mint, driven through the real blend function."""

    def test_a_speaking_market_records_its_semantic_type(self):
        understanding = build_content_understanding(
            name=f"{HOME} vs. {AWAY}", sports_market_type="moneyline"
        )
        group = [
            _entry(
                1, f"{HOME} vs. {AWAY}",
                [(1, HOME, 0.705), (2, AWAY, 0.295)],
                market_metadata={CONTENT_UNDERSTANDING_KEY: understanding},
            )
        ]
        reading = compute_source_home_probability(group, HOME, AWAY)

        assert reading is not None
        assert reading.eligibility.semantic_type == "moneyline"

    def test_a_market_with_no_understanding_mints_the_record_it_mints_today(self):
        """Additive: the key is simply absent until the poller re-serves the
        row, and `to_entry` drops it."""
        group = [_entry(1, f"{HOME} vs. {AWAY}", [(1, HOME, 0.705), (2, AWAY, 0.295)])]
        reading = compute_source_home_probability(group, HOME, AWAY)

        assert reading is not None
        assert reading.eligibility.semantic_type is None
        assert "semantic_type" not in reading.eligibility.to_entry()

    def test_the_type_round_trips_through_the_stored_entry(self):
        record = verified_record(rule="r", market_id=7, semantic_type="moneyline:disputed")
        entry = record.to_entry()
        assert entry["semantic_type"] == "moneyline:disputed"
        assert from_entry({"eligibility": entry}).semantic_type == "moneyline:disputed"

    def test_verified_record_still_defaults_to_none(self):
        """Every caller that does not supply it writes exactly what it writes
        today — the proof that this clause is additive."""
        assert verified_record(rule="r", market_id=1).semantic_type is None
        assert "semantic_type" not in verified_record(rule="r", market_id=1).to_entry()


class TestNothingAboutAdmissionChanges:
    """The boundary: this clause records, it does not decide."""

    def test_a_contradicted_market_is_still_admitted_and_still_speaks(self):
        """Quarantine is a later consumer built on a measured population. If
        this clause started refusing, it would move published numbers on a
        population nobody has measured — and on the 21% it cannot see at all.
        """
        assert admissible_as_blend_speaker(
            _Market(1, MAP_WINNER), is_primary=True
        ) is True, (
            "clause (2) must not gate — it writes the disagreement down so a "
            "quarantine can be built on it later, on a measured population"
        )
        # ...and the same is true of the row when it is not the primary, which
        # is the stricter of the two burdens.
        assert admissible_as_blend_speaker(
            _Market(1, MAP_WINNER), is_primary=False
        ) is True

    def test_a_contradicted_market_that_speaks_records_the_disagreement(self):
        """The other half: admitting it is not the same as trusting it silently.

        The specimen is a map-winner child wearing a BARE MATCHUP title, which
        is both a real Polymarket shape and the one that resolves — the
        `Counter-Strike: … - Map 1 Winner` string above never reaches a reading
        at all, because `extract_matchup_with_ticker_fallback` returns None for
        it. That is a pre-existing title-parse limit, not this gate, and a test
        that read its `None` as a refusal would be reporting the wrong fact.
        """
        understanding = build_content_understanding(
            name=f"{CS_HOME} vs {CS_AWAY}", sports_market_type="child_moneyline"
        )
        assert understanding["agreement"] == CONTRADICTED
        group = [
            _entry(
                1, f"{CS_HOME} vs {CS_AWAY}",
                [(1, CS_HOME, 0.62), (2, CS_AWAY, 0.38)],
                market_metadata={CONTENT_UNDERSTANDING_KEY: understanding},
            )
        ]
        reading = compute_source_home_probability(group, CS_HOME, CS_AWAY)

        assert reading is not None, "the market is admitted, so it still speaks"
        assert reading.eligibility.semantic_type == "moneyline:disputed", (
            "the record must carry the venue's disagreement, or a reader "
            "auditing the number sees a clean 'moneyline' on exactly the rows "
            "where the two signals disagree"
        )

    def test_the_clause_never_writes_futures_markets_market_type(self):
        """🔴 `market_type` is Queue #194's presentation shape, read by
        `precompute_calibration`. Writing this orthogonal question there would
        silently retype the calibration input.

        Asserted on what the ingest actually BUILDS, not on the source text: a
        substring scan here matches the very docstring that warns against it,
        which is a guard aimed at its own comment rather than at the defect.
        """
        u = build_content_understanding(
            name=f"{HOME} vs. {AWAY}", sports_market_type="moneyline"
        )
        meta = polymarket_task.sub_market_metadata(
            event_id=42, matchup_title=f"{HOME} vs. {AWAY}", content_understanding=u,
        )
        # The understanding lives under its own key and nowhere else, and it
        # never introduces a `market_type` key into the metadata a market row
        # carries.
        assert "market_type" not in meta
        assert set(u) <= {"v", "semantic_type", "venue_type", "agreement", "rule"}

    def test_the_ingest_sets_market_type_from_nothing_this_clause_added(self):
        """The insert/update for a sub-market must not have acquired a
        `market_type` write on the back of this clause."""
        tree = ast.parse(inspect.getsource(polymarket_task))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "build_content_understanding"
            ):
                assert all(
                    kw.arg != "market_type" for kw in node.keywords
                ), "this clause must never touch the presentation-shape column"


# =============================================================================
# CERT-2733's repair — the one-market event
# =============================================================================


class _PolyMarketDTO:
    """Only what the ingest reads off a parsed Gamma market."""

    def __init__(self, *, question=None, sports_market_type=None, condition_id=None):
        self.question = question
        self.sports_market_type = sports_market_type
        self.condition_id = condition_id


class _PolyEventDTO:
    def __init__(self, *, event_id="1007524", title=None, markets=()):
        self.id = event_id
        self.title = title
        self.markets = list(markets)


#: The live Gamma shape CERT-2733 found: active, non-neg-risk, ONE market.
PPA_TITLE = "PPA - Women's Singles: Hannah Blatt vs Polina Libo"
PPA_HOME = "Hannah Blatt"
PPA_AWAY = "Polina Libo"
#: The same fixture as Polymarket also titles one-market events — a bare
#: matchup, which is the shape our own recognizer reads.
PPA_BARE = f"{PPA_HOME} vs. {PPA_AWAY}"


def _single_market_event(*, title=PPA_BARE, venue_type="moneyline", question=None):
    return _PolyEventDTO(
        title=title,
        markets=[
            _PolyMarketDTO(
                question=question if question is not None else title,
                sports_market_type=venue_type,
                condition_id="0xabc",
            )
        ],
    )


class TestTheParentRowIsAPricedRowInEveryShape:
    """🔴 CERT-2733. Clause (2) typed the decomposed CHILDREN — and
    `_parent_outcome_data(event)` runs BEFORE the decomposition branch, so the
    parent carries outcomes in every shape, and sub-markets are written for only
    one of the three (`not neg_risk and len(markets) > 1`). A one-market event
    and a negrisk game group therefore have no children at all: the parent IS
    the row that speaks. All of it went through the typed path and came out
    untyped, on every poll, forever, because the poll is the only writer.
    """

    def test_single_market_event_persists_semantic_type_into_blend_record_5273(self):
        """Ingest → stored metadata → the eligibility record that rides the
        served number. The named repair, end to end."""
        event = _single_market_event()

        understanding = polymarket_task.parent_content_understanding(
            event, sport="tennis"
        )
        assert understanding is not None, (
            "a one-market event must be typed on the parent — no child will do "
            "it, because the sub-market loop never runs for it"
        )
        assert understanding["semantic_type"] == "moneyline"
        assert understanding["agreement"] == CORROBORATED

        # The dict the parent insert/update actually writes to the column.
        stored = {
            "polymarket_event_id": event.id,
            "event_title": event.title,
            CONTENT_UNDERSTANDING_KEY: understanding,
        }

        group = [
            _entry(
                1, PPA_BARE,
                [(1, PPA_HOME, 0.58), (2, PPA_AWAY, 0.42)],
                external_id=event.id,
                market_metadata=stored,
            )
        ]
        reading = compute_source_home_probability(group, PPA_HOME, PPA_AWAY)

        assert reading is not None
        assert reading.eligibility.semantic_type == "moneyline", (
            "the record substantiating the served number must name the kind of "
            "question that produced it"
        )
        assert reading.eligibility.to_entry()["semantic_type"] == "moneyline"

    def test_the_parent_is_typed_on_its_own_name_not_the_markets_question(self):
        """🔴 The row a reader sees, and the row `admissible_as_blend_speaker`
        judges, is named `event.title`. Typing the market's `question` instead
        would store an understanding of a string that is on no row.
        """
        event = _single_market_event(
            title=f"{CS_HOME} vs {CS_AWAY}",
            question="Will Nemiga win Map 1?",
            venue_type=None,
        )
        understanding = polymarket_task.parent_content_understanding(event)

        assert understanding["semantic_type"] == "moneyline", (
            "the bare matchup is the parent row's name; the question is not"
        )

    def test_a_re_ingest_refreshes_the_understanding_when_the_venue_relabels(self):
        """The parent write rebuilds `market_metadata` every poll, so a venue
        relabel must land — a stored blob that could only be written once would
        pin the first reading forever."""
        first = polymarket_task.parent_content_understanding(
            _single_market_event(venue_type="moneyline")
        )
        assert first["agreement"] == CORROBORATED
        assert record_semantic_type(first) == "moneyline"

        relabelled = polymarket_task.parent_content_understanding(
            _single_market_event(venue_type="child_moneyline")
        )
        assert relabelled["venue_type"] == "child_moneyline"
        assert relabelled["agreement"] == CONTRADICTED
        assert record_semantic_type(relabelled) == "moneyline:disputed"
        assert is_disputed(record_semantic_type(relabelled))

    def test_the_stamp_sits_beside_the_other_keys_the_parent_row_carries(self):
        """Preservation: the understanding is one top-level key among the
        parent's own, not a replacement for them — the census idiom is jsonb
        `?`, which cannot see a nested key."""
        event = _single_market_event()
        stored = {
            "polymarket_event_id": event.id,
            "event_title": event.title,
            "clob_token_ids": ["123"],
        }
        stored[CONTENT_UNDERSTANDING_KEY] = (
            polymarket_task.parent_content_understanding(event)
        )

        assert set(stored) == {
            "polymarket_event_id",
            "event_title",
            "clob_token_ids",
            CONTENT_UNDERSTANDING_KEY,
        }
        assert understanding_from_metadata(stored)["semantic_type"] == "moneyline"
        assert semantic_type_for_market(
            _Market(1, PPA_BARE, market_metadata=stored)
        ) == "moneyline"

    def test_the_certs_own_gamma_specimen_now_agrees_with_the_venue(self):
        """🔴 The exact live row CERT-2733 named — and the clause paying out.

        `PPA - Women's Singles: Hannah Blatt vs Polina Libo` IS the match
        winner and Gamma says so (`sportsMarketType=moneyline`), while our title
        recognizer answered `other` on the tournament-and-draw prefix alone. The
        clause's whole job is to write that disagreement down instead of
        swallowing it, and it did: the row stored `other:disputed`, the
        contradiction was filed as #5660, and #5660 fixed the recognizer.

        So this assertion flips from `contradicted` to `corroborated` BY DESIGN.
        It is the receipt that clause (2) is a working instrument and not
        decoration — a disagreement it recorded is a disagreement that got
        closed. #5660's acceptance criterion is this exact line.
        """
        understanding = polymarket_task.parent_content_understanding(
            _single_market_event(title=PPA_TITLE), sport="tennis"
        )
        assert understanding["semantic_type"] == "moneyline"
        assert understanding["venue_type"] == "moneyline"
        assert understanding["agreement"] == CORROBORATED
        assert record_semantic_type(understanding) == "moneyline"

    def test_a_negrisk_parent_is_typed_because_it_is_the_row_that_speaks(self):
        """🔴 The bigger half of the same hole. Sub-markets are written only for
        `not neg_risk and len(markets) > 1`, so a negrisk game group's legs are
        FLATTENED onto the parent — which is then the row holding
        `[home, away, draw]` and the row the blend reads. Measured 2026-09-12:
        67,855 negrisk rows, 9,340 open, against 13,956 single-market rows.
        """
        event = _PolyEventDTO(
            title=f"{HOME} vs. {AWAY}",
            markets=[
                _PolyMarketDTO(question=f"Will {HOME} win?", sports_market_type="moneyline"),
                _PolyMarketDTO(question=f"Will {AWAY} win?", sports_market_type="moneyline"),
                _PolyMarketDTO(question="Draw?", sports_market_type="moneyline"),
            ],
        )
        understanding = polymarket_task.parent_content_understanding(event)

        assert understanding["semantic_type"] == "moneyline"
        assert understanding["venue_type"] == "moneyline", (
            "three legs of one question carry one label, and the parent's label "
            "is the one they agree on"
        )
        assert understanding["agreement"] == CORROBORATED

    def test_markets_that_disagree_leave_the_parent_UNCONFIRMED(self):
        """🔴 Disagreement reads as ABSENCE, never as a pick. Taking the first
        child's label — or the modal one — would put a venue claim on the parent
        that the venue never made about it, and `agreement` would then compare
        our reading against something we invented."""
        event = _PolyEventDTO(
            title=f"{HOME} vs. {AWAY}",
            markets=[
                _PolyMarketDTO(question="A", sports_market_type="moneyline"),
                _PolyMarketDTO(question="B", sports_market_type="spread"),
            ],
        )
        understanding = polymarket_task.parent_content_understanding(event)

        assert "venue_type" not in understanding
        assert understanding["agreement"] == UNCONFIRMED
        assert understanding["semantic_type"] == "moneyline"

        # One label missing is disagreement too — a partially-labelled group
        # cannot corroborate anything.
        event.markets[1].sports_market_type = None
        assert polymarket_task.parent_venue_market_type(event) is None

    def test_a_group_the_venue_never_labelled_is_unconfirmed_not_contradicted(self):
        """The 21%. `is_full_contest_winner_type(None)` is False, so a group of
        unlabelled markets must never reach the comparison."""
        event = _PolyEventDTO(
            title=f"{HOME} vs. {AWAY}",
            markets=[_PolyMarketDTO(question="A"), _PolyMarketDTO(question="B")],
        )
        assert polymarket_task.parent_venue_market_type(event) is None
        assert polymarket_task.parent_content_understanding(event)["agreement"] == (
            UNCONFIRMED
        )

    def test_an_unnamed_or_marketless_event_stamps_nothing(self):
        """`None`, never `{}`: the caller writes this straight into the column,
        and an empty object would overwrite a populated key on re-ingest."""
        assert polymarket_task.parent_content_understanding(
            _single_market_event(title=None)
        ) is None
        assert polymarket_task.parent_content_understanding(
            _PolyEventDTO(title=PPA_TITLE, markets=[])
        ) is None

    def test_nothing_to_say_stamps_no_key_at_all(self):
        """🔴 Not "stamps a null". The census idiom is jsonb `?`, which sees a
        key holding JSON `null` and counts the row as understood; and the parent
        write REPLACES the column, so a stamped null would also erase a good
        understanding from the poll before it."""
        meta = {"polymarket_event_id": "1007524"}
        returned = polymarket_task.stamp_parent_content_understanding(
            meta, _single_market_event(title=None)
        )
        assert returned is meta
        assert CONTENT_UNDERSTANDING_KEY not in meta

        polymarket_task.stamp_parent_content_understanding(
            meta, _PolyEventDTO(title=PPA_BARE, markets=[])
        )
        assert CONTENT_UNDERSTANDING_KEY not in meta

        polymarket_task.stamp_parent_content_understanding(
            meta, _single_market_event(), sport="tennis"
        )
        assert meta[CONTENT_UNDERSTANDING_KEY]["semantic_type"] == "moneyline"
        assert meta["polymarket_event_id"] == "1007524"

    def test_the_ingest_stamps_the_parent_key_through_that_helper(self):
        """🔴 The wiring guard, and the mutation this suite exists to kill: the
        helper passing its own tests proves nothing if the poll never calls it.
        Asserted on the AST — the call, and the dict it is handed — rather than
        on a substring of the source, which would match the comment that
        explains it."""
        tree = ast.parse(inspect.getsource(polymarket_task))

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None)
            == "stamp_parent_content_understanding"
        ]
        assert calls, "the poll never stamps the parent's understanding"
        assert any(
            node.args and getattr(node.args[0], "id", None) == "poly_metadata"
            for node in calls
        ), (
            "the understanding must be stamped into the dict the PARENT row is "
            "written from — anywhere else and the one-market row stays untyped"
        )
