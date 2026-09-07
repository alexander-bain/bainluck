"""Container assembly: membership proved, gaps visible. #2927 Phases 2-4.

The register gatherer and the ordering/cycle helpers are pure, so they are
graded here against the REAL committed US Open register rather than a fixture
that agrees with them by construction. The database half (edge upsert, receipt
write, dangling-edge check) needs a server and is graded in
`tests/integration/test_container_assembly_real_postgres.py`.

THE MEASUREMENT THAT SHAPED THIS FILE. Running the gatherer over the committed
register on 2026-09-05 found that **448 `reaches` rows carry only 336 market
ids and 124 `matchups` rows carry only 116** — 120 rows the hub renders today
that the graph, on its own, would not. That gap is the reason `RegisterHarvest`
has an `unpriced` list at all, and the reason several tests below assert it is
non-empty: a version of this code that returned only the candidates would have
reported 458 happy members and hidden the 120, which is exactly the silent loss
the program exists to end.
"""

import pytest

from app.tasks.container_assembly import (
    BOOTSTRAP_UNDO_LINE,
    SOURCE_CONFIDENCE,
    TENNIS_DRAWS,
    Candidate,
    RegisterHarvest,
    container_chain_has_cycle,
    gather_register_candidates,
    plan_container_tree,
)
from app.routes.containers import CLASS_ORDER, order_classes
from app.utils.container_class import classify_member
from app.utils.container_graph import (
    ASSEMBLY_WRITABLE_KINDS,
    CLASS_UNCLASSIFIED,
    EDGE_CLASSES,
    EDGE_SOURCES,
)
from app.utils.match_receipts import (
    PHASE_CONTAINER_ASSEMBLY,
    PHASES,
    REJECT_CONTAINER_ATTEMPT_ERROR,
    REJECT_CONTAINER_CHILD_MISSING,
    REJECT_CONTAINER_NOT_A_MEMBER,
    REJECT_CONTAINER_NO_ANCHOR,
    REJECT_REASONS,
    MatchReceipt,
)
from app.utils.tournament_register import load_register


@pytest.fixture(scope="module")
def register():
    reg = load_register("us-open", "2026")
    assert reg is not None, "the committed US Open register must be readable"
    return reg


@pytest.fixture(scope="module")
def harvest(register) -> RegisterHarvest:
    return gather_register_candidates(register)


class TestTheRegisterGathererIsIdKeyed:
    """Membership keys on provider ids, never on names (spec §6).

    Name matching is what the register does today and artifact I measured its
    cost: 340 unmatched rows, 79 doubles slash-teams that never match 2-name
    rows, token-fallback catching 30+ false doubles→singles hits.
    """

    def test_every_candidate_carries_one_of_our_own_market_ids(self, harvest):
        assert harvest.candidates
        for candidate in harvest.candidates:
            assert candidate.child_type == "market"
            assert isinstance(candidate.child_id, int)
            assert candidate.child_id > 0

    def test_no_candidate_is_produced_from_a_name_alone(self, register):
        """Strip every id from the register and the gatherer must yield NOTHING.

        This is the load-bearing test in the file. A gatherer that fell back to
        name matching when an id was missing would still return members here —
        and they would be exactly the wrong ones, because the rows with no id
        are the rows we hold no market for.
        """
        import copy

        stripped = copy.deepcopy(register)
        for key in ("matchups", "reaches"):
            for row in stripped.get(key) or []:
                for block in row.get("sources") or []:
                    block.pop("market_id", None)
        for prop in stripped.get("props") or []:
            prop.pop("market_id", None)
            for block in prop.get("markets") or []:
                block.pop("market_id", None)

        result = gather_register_candidates(stripped)
        assert result.candidates == []
        # …and every row it could not use is REPORTED, not dropped.
        assert len(result.unpriced) == (
            len(register["matchups"]) + len(register["reaches"]) + len(register["props"])
        )

    def test_candidates_are_unique_by_market(self, harvest):
        ids = [c.child_id for c in harvest.candidates]
        assert len(ids) == len(set(ids))

    def test_the_source_is_the_register(self, harvest):
        assert {c.source for c in harvest.candidates} == {"register"}
        assert "register" in EDGE_SOURCES


class TestTheGapIsVisible:
    """Spec §5 M4: assembly yielding less than the register is a RED."""

    def test_unpriced_rows_are_reported_not_dropped(self, harvest):
        """Measured on the committed register: 8 matchups + 112 reaches.

        The exact numbers are not pinned — the register is re-versioned by
        hand and a pinned count would fail for the wrong reason. What IS
        pinned is that the gap is non-zero and is broken down by kind, because
        a gatherer that reported `unpriced: []` while dropping 120 rows is the
        defect this list exists to prevent.
        """
        summary = harvest.summary()
        assert summary["candidates"] > 0
        assert summary["unpriced_by_kind"], (
            "the committed register pins rows we hold no market for; a report "
            "of zero means the gatherer is dropping them silently"
        )
        assert set(summary["unpriced_by_kind"]) <= {"matchup", "reach", "prop"}

    def test_unpriced_is_exactly_the_rows_with_no_market_id(self, register, harvest):
        """Nothing falls between the two lists — cross-checked against the JSON.

        Counted independently here, straight off the register, rather than
        derived from the gatherer's own output: `total - len(unpriced)` would
        be tautological and would agree with a gatherer that had miscounted
        both halves the same way.

        NOTE ON THE ARITHMETIC, because the obvious assertion is wrong. The
        candidate count is NOT bounded by the row count: one register row can
        legitimately pin more than one market — a `prop` carries both a
        singular `market_id` and a plural `markets[]`, and on the committed
        register that produces 458 candidates from 457 yielding rows. Asserting
        `candidates <= rows` looks right and fails on real data; the property
        that actually holds is the one below.
        """

        def has_market(row, key="sources"):
            return any(
                isinstance(b, dict) and b.get("market_id")
                for b in (row.get(key) or [])
            )

        expected_unpriced = 0
        for row in register["matchups"]:
            expected_unpriced += 0 if has_market(row) else 1
        for row in register["reaches"]:
            expected_unpriced += 0 if has_market(row) else 1
        for row in register["props"]:
            priced = row.get("market_id") or has_market(row, "markets")
            expected_unpriced += 0 if priced else 1

        assert len(harvest.unpriced) == expected_unpriced
        assert harvest.candidates, "the register does price members; zero is a bug"

    def test_each_unpriced_entry_is_diagnosable(self, harvest):
        for row in harvest.unpriced:
            assert row["kind"] in {"matchup", "reach", "prop"}
            assert "key" in row and "draw" in row


class TestClassificationOfTheRealRegister:
    def test_every_candidate_classifies_into_the_vocabulary(self, harvest):
        for candidate in harvest.candidates:
            assert classify_member(candidate.evidence) in EDGE_CLASSES

    def test_the_three_register_kinds_produce_three_sections(self, harvest):
        produced = {classify_member(c.evidence) for c in harvest.candidates}
        assert {"match_winner", "advancement", "side_question"} <= produced

    def test_nothing_in_the_register_lands_unclassified(self, harvest):
        """The register's rows all carry a kind, so none should fall through.

        If this ever fails it is a finding, not a flake: it means a register
        list grew a shape the gatherer passes through without a `register_kind`,
        and those members would render in the trailing section instead of their
        own.
        """
        unclassified = [
            c for c in harvest.candidates
            if classify_member(c.evidence) == CLASS_UNCLASSIFIED
        ]
        assert not unclassified, [c.name for c in unclassified[:5]]


class TestAssemblyNeverAbsorbs:
    """Ruling 048 is enforced, not promised."""

    def test_assembly_may_write_only_contains(self):
        assert ASSEMBLY_WRITABLE_KINDS == {"contains"}

    def test_every_source_confidence_is_a_probability(self):
        for source, confidence in SOURCE_CONFIDENCE.items():
            assert source in EDGE_SOURCES, source
            assert 0.0 <= confidence <= 1.0

    def test_id_keyed_sources_are_full_confidence(self):
        """Both gatherers key on an id, so neither is a guess.

        Stated as a test so that a future gatherer which DOES guess cannot be
        added at 1.0 without this failing and someone thinking about it.
        """
        assert SOURCE_CONFIDENCE["register"] == 1.0
        assert SOURCE_CONFIDENCE["venue_grouping"] == 1.0


class TestTheReceiptVocabularyIsRegistered:
    """A typo'd reason is a silently uncountable row — `reject()` raises."""

    @pytest.mark.parametrize(
        "reason",
        [
            REJECT_CONTAINER_CHILD_MISSING,
            REJECT_CONTAINER_NOT_A_MEMBER,
            REJECT_CONTAINER_NO_ANCHOR,
            REJECT_CONTAINER_ATTEMPT_ERROR,
        ],
    )
    def test_each_container_reason_is_in_the_enum(self, reason):
        assert reason in REJECT_REASONS
        assert reason.startswith("container_"), (
            "the prefix is what lets `GROUP BY reject_reason` separate the two "
            "deciders without a join"
        )

    def test_the_assembly_phase_is_registered(self):
        assert PHASE_CONTAINER_ASSEMBLY in PHASES

    def test_a_container_reason_can_actually_be_written(self):
        receipt = MatchReceipt(
            market_id=1,
            source="kalshi",
            external_id="KXATPMATCH-26SEP02AUGKHA",
            market_name="FAA vs Khachanov",
            phase=PHASE_CONTAINER_ASSEMBLY,
            attempted_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
            container_id=7,
        )
        receipt.reject(REJECT_CONTAINER_CHILD_MISSING, child_id=999)
        row = receipt.to_row()
        assert row["reject_reason"] == REJECT_CONTAINER_CHILD_MISSING
        assert row["container_id"] == 7
        assert row["phase"] == PHASE_CONTAINER_ASSEMBLY

    def test_an_ordinary_matcher_receipt_still_carries_no_container(self):
        """The column is additive: every receipt the matcher writes is NULL."""
        receipt = MatchReceipt(
            market_id=1,
            source="kalshi",
            external_id="X",
            market_name="Y",
            phase="pass1_ticker",
            attempted_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
        )
        assert receipt.to_row()["container_id"] is None


class TestTheContainerTreePlan:
    """One parent, one child per draw, slugs DERIVED and never typed."""

    def test_the_us_open_plan_is_a_root_plus_five_draws(self):
        plan = plan_container_tree("us-open", "2026", "US Open 2026")
        assert len(plan) == 6
        assert plan[0].slug == "us-open-2026"
        assert plan[0].parent_slug is None
        assert all(p.parent_slug == "us-open-2026" for p in plan[1:])

    def test_doubles_draws_are_present_and_are_their_own_containers(self):
        """The whole point: Men's Doubles gets its own anchor and its own status.

        `status` is authority-set (D27), and one container per draw is what lets
        Men's Doubles go `final` while Mixed is still `live`. A single container
        with a `draw` facet could not express that.
        """
        slugs = {p.slug for p in plan_container_tree("us-open", "2026", "US Open 2026")}
        assert {
            "us-open-2026-mens-doubles",
            "us-open-2026-womens-doubles",
            "us-open-2026-mixed-doubles",
        } <= slugs

    def test_slugs_are_derived_so_a_rerun_is_idempotent(self):
        a = plan_container_tree("us-open", "2026", "US Open 2026")
        b = plan_container_tree("us-open", "2026", "US Open 2026")
        assert [p.slug for p in a] == [p.slug for p in b]

    def test_the_same_tournament_in_two_seasons_does_not_collide(self):
        """The slug is the public URL and the unique key.

        If the season were dropped from the slug, 2027's bootstrap would find
        2026's rows already present, write nothing, and silently attach next
        year's markets to last year's hub.
        """
        y26 = {p.slug for p in plan_container_tree("us-open", "2026", "US Open 2026")}
        y27 = {p.slug for p in plan_container_tree("us-open", "2027", "US Open 2027")}
        assert not (y26 & y27)

    def test_a_different_tournament_does_not_collide(self):
        uso = {p.slug for p in plan_container_tree("us-open", "2026", "US Open 2026")}
        wim = {p.slug for p in plan_container_tree("wimbledon", "2026", "Wimbledon 2026")}
        assert not (uso & wim)

    def test_the_root_comes_first_so_one_pass_can_apply_it(self):
        for tournament in ("us-open", "wimbledon", "roland-garros"):
            plan = plan_container_tree(tournament, "2026", "X")
            seen = set()
            for planned in plan:
                if planned.parent_slug is not None:
                    assert planned.parent_slug in seen, planned.slug
                seen.add(planned.slug)

    def test_every_planned_container_uses_a_real_kind(self):
        from app.utils.container_graph import validate_container_kind

        for planned in plan_container_tree("us-open", "2026", "US Open 2026"):
            assert validate_container_kind(planned.kind) == planned.kind

    def test_the_draw_list_is_the_only_hand_written_list(self):
        """A named check on the program's own promise.

        The spec's claim is that nobody writes a list of MEMBERS — not that
        nobody names the draws a Slam has. `TENNIS_DRAWS` is that one exception
        and it is five entries long; if it ever grows toward the size of a
        member list, this test is where someone will notice.
        """
        assert len(TENNIS_DRAWS) == 5
        assert all(len(entry) == 2 for entry in TENNIS_DRAWS)


class TestTheBootstrapUndoIsNarrow:
    def test_the_undo_refuses_to_delete_a_populated_container(self):
        """D51's undo must not be able to delete a working hub.

        Asserted on the statement rather than by executing it, because the
        property is structural: the `NOT EXISTS` on `event_edges` is what stops
        a re-run-then-undo from removing a container assembly has since filled.
        The real-Postgres file exercises it.
        """
        assert "NOT EXISTS" in BOOTSTRAP_UNDO_LINE
        assert "event_edges" in BOOTSTRAP_UNDO_LINE
        assert ":created_slugs" in BOOTSTRAP_UNDO_LINE
        # Scoped to the slugs the apply REPORTED creating — never to everything
        # that happens to be empty, and never to `existing`.
        assert "slug = ANY(:created_slugs)" in BOOTSTRAP_UNDO_LINE


class TestTheCycleGuard:
    """One hop is a CHECK constraint; longer chains live in the job (spec §1)."""

    def test_a_straight_chain_is_not_a_cycle(self):
        assert container_chain_has_cycle({2: 1, 3: 2}, 3) is False

    def test_a_root_is_not_a_cycle(self):
        assert container_chain_has_cycle({}, 1) is False

    def test_a_two_hop_cycle_is_caught(self):
        assert container_chain_has_cycle({1: 2, 2: 1}, 1) is True

    def test_a_three_hop_cycle_is_caught(self):
        """The case a CHECK constraint provably cannot express."""
        assert container_chain_has_cycle({1: 2, 2: 3, 3: 1}, 1) is True

    def test_a_cycle_reached_from_outside_it_is_caught(self):
        """A container hanging off a cycle must not hang the walk either."""
        assert container_chain_has_cycle({4: 1, 1: 2, 2: 3, 3: 1}, 4) is True

    def test_a_long_legitimate_chain_terminates(self):
        parent_of = {i: i - 1 for i in range(2, 500)}
        assert container_chain_has_cycle(parent_of, 499) is False


class TestSectionOrdering:
    """The hub renders sections in policy order, and never hides one."""

    def test_the_draw_comes_before_the_props(self):
        order = order_classes({"prop", "match_winner", "advancement"})
        assert order.index("match_winner") < order.index("advancement")
        assert order.index("advancement") < order.index("prop")

    def test_unclassified_is_always_last(self):
        order = order_classes({CLASS_UNCLASSIFIED, "match_winner", "prop"})
        assert order[-1] == CLASS_UNCLASSIFIED

    def test_unclassified_is_never_dropped(self):
        assert order_classes({CLASS_UNCLASSIFIED}) == [CLASS_UNCLASSIFIED]

    def test_a_class_missing_from_the_order_list_still_renders(self):
        """Adding a class must not be a silent way to hide a whole section.

        A future class that nobody adds to `CLASS_ORDER` renders at the end,
        before `unclassified` — never dropped.
        """
        order = order_classes({"match_winner", "brand_new_class", CLASS_UNCLASSIFIED})
        assert order == ["match_winner", "brand_new_class", CLASS_UNCLASSIFIED]

    def test_every_named_class_has_a_position(self):
        """`CLASS_ORDER` covers the whole vocabulary except `unclassified`."""
        assert set(CLASS_ORDER) == EDGE_CLASSES - {CLASS_UNCLASSIFIED}

    def test_empty_in_empty_out(self):
        assert order_classes(set()) == []


class TestTheReadRouteIsFlagged:
    def test_the_flag_defaults_to_off(self, monkeypatch):
        from app.routes import containers

        monkeypatch.delenv("CONTAINERS_READ_ENABLED", raising=False)
        assert containers.containers_read_enabled() is False

    def test_the_flag_is_read_at_call_time_not_import_time(self, monkeypatch):
        """A flag you must restart a dyno to flip is a flag nobody flips."""
        from app.routes import containers

        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
        assert containers.containers_read_enabled() is True
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "false")
        assert containers.containers_read_enabled() is False

    def test_the_route_is_mounted(self):
        """Mounted in BOTH main.py and routes/__init__.py (gotcha #2)."""
        from app.main import app

        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/containers/{slug}" in paths
