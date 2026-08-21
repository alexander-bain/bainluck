"""A reasoned Bad must become routable defect evidence (UX-P117, #2060 item 1).

── WHAT THIS SUITE IS GUARDING AGAINST, MEASURED ────────────────────────────────

Production 2026-08-21: 88 ``ranking_judgments``, **zero** carrying
``label_metadata.fixable_interest``, and 71 of them ``bad``/``kill`` WITH reason
tags. ``_build_fixable_clusters`` skips any row without that key, so both cluster
endpoints had returned an empty list for the life of the store while Alex had
flagged ``stale`` 35 separate times.

The regression this suite exists to catch is therefore not "the mapping is wrong".
It is **the route silently going back to zero** — which looks exactly like a quiet
week, produces no error, and is invisible in every test that only asserts a label
was written.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.discover_reason_tags import canonical_reason_tag
from app.utils.gold_label_store import structured_label_metadata
from app.utils.label_reasons import (
    BAD_REASON_CHIPS,
    BAD_REASON_TAGS,
    NON_DEFECT_REASONS,
    REASON_FIX_TYPE,
    defect_route,
    reason_fix_type,
)


CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "bad_reason_chips.json")
    .read_text()
)


class TestContract:
    """Python's arm of `contracts/bad_reason_chips.json` (ruling 021).

    Three runtimes draw this chip row and no import spans them, so the shared unit
    is the table. Swift's arm is `LabelingNudgeContractTests`; the drift check that
    keeps Swift's inlined copy equal to the contract runs in CI as
    `frontend/__tests__/lib/badReasonChipsContract.test.ts`.
    """

    def test_chips_match_the_contract_exactly_and_in_order(self):
        expected = [(row["tag"], row["display"]) for row in CONTRACT["chips"]]
        assert list(BAD_REASON_CHIPS) == expected

    def test_every_contract_route_is_the_implemented_route(self):
        for row in CONTRACT["chips"]:
            assert reason_fix_type(row["tag"]) == row["fix_type"], row["tag"]

    def test_every_contract_alias_folds_where_the_contract_says(self):
        for spelling, canonical in CONTRACT["aliases"].items():
            assert canonical_reason_tag(spelling) == canonical, spelling

    def test_the_notification_ids_are_the_ones_the_server_sends(self):
        from app.utils.morning_digest import (
            LABELING_DEEP_LINK,
            LABELING_NOTIFICATION_CATEGORY,
        )

        assert LABELING_NOTIFICATION_CATEGORY == CONTRACT["notification"]["category"]
        assert LABELING_DEEP_LINK == CONTRACT["notification"]["deep_link"]


class TestChipVocabulary:
    def test_every_chip_stores_a_canonical_spelling(self):
        """A chip that mints a new spelling splits the tally it exists to grow.

        The two that would have: "Confusing" (the store says ``unclear``, 16 rows)
        and "Boring" (the store says ``low_stakes``, 6 rows).
        """
        for tag, _display in BAD_REASON_CHIPS:
            assert canonical_reason_tag(tag) == tag, (
                f"chip {tag!r} is not its own canonical form — it would store as "
                f"{canonical_reason_tag(tag)!r} and fork the tally"
            )

    def test_every_chip_routes_somewhere(self):
        """The whole promise of item 1: no chip is a dead end."""
        for tag, display in BAD_REASON_CHIPS:
            assert reason_fix_type(tag) is not None, (
                f"chip {display!r} ({tag}) routes nowhere — it is a sixth way to "
                "be ignored"
            )

    def test_chips_are_six_and_distinct(self):
        assert len(BAD_REASON_CHIPS) == 6
        assert len(set(BAD_REASON_TAGS)) == 6

    def test_the_web_spellings_alex_already_used_fold_onto_chips(self):
        """`/admin/labeling` writes these; native must not create rivals."""
        assert canonical_reason_tag("boring") == "low_stakes"
        assert canonical_reason_tag("confusing") == "unclear"
        assert canonical_reason_tag("bad image") == "bad_image"
        assert canonical_reason_tag("niche") == "too_niche"
        # The ReviewTab's two, never canonical until this queue.
        assert canonical_reason_tag("too_high") == "wrong_probability"
        assert canonical_reason_tag("too_low") == "wrong_probability"


class TestDefectRoute:
    @pytest.mark.parametrize(
        "tag,expected",
        [
            ("stale", "staleness"),
            ("duplicate", "duplicate_variant"),
            ("bad_image", "bad_image"),
            ("wrong_probability", "data_bug"),
            ("unclear", "missing_context"),
            ("low_stakes", "ranking_rule"),
        ],
    )
    def test_each_chip_lands_on_its_fix_type(self, tag, expected):
        route = defect_route(label="bad", reason_tags=[tag])
        assert route is not None
        assert route["fix_type"] == expected

    def test_kill_routes_too(self):
        assert defect_route(label="kill", reason_tags=["stale"])["fix_type"] == "staleness"

    @pytest.mark.parametrize("label", ["love", "fine", "skip", "", None])
    def test_a_ROUTABLE_tag_on_a_positive_label_files_no_defect(self, label):
        """The label gate, exercised with a tag that WOULD route on a Bad.

        ** THIS ASSERTION REPLACES A VACUOUS ONE, AND MUTATION M1 IS HOW IT WAS
        FOUND. ** The original passed `love` + `public_story` — but
        `public_story` is in `NON_DEFECT_REASONS`, so it routes nowhere whatever
        the label is. Adding `love` to `NEGATIVE_LABELS` therefore left the test
        green: it was asserting the TAG gate while claiming to assert the LABEL
        gate, and deleting the label gate entirely would not have failed it.
        `stale` is the discriminating tag, because it is the one that routes.
        """
        assert defect_route(label=label, reason_tags=["stale"]) is None

    def test_a_praise_tag_on_a_love_files_no_defect(self):
        """The corpus holds a `love` + `public_story` row. Both gates, together."""
        assert defect_route(label="love", reason_tags=["public_story"]) is None

    def test_a_positive_tag_on_a_bad_files_no_defect(self):
        """`bad` + "high stakes" is a complaint about the card, not about stakes."""
        assert defect_route(label="bad", reason_tags=["high_stakes"]) is None

    def test_no_tags_is_no_route(self):
        assert defect_route(label="bad", reason_tags=[]) is None
        assert defect_route(label="bad", reason_tags=None) is None

    def test_historical_spellings_route_without_being_rewritten(self):
        """The 2 production `boring` rows route identically to a new `low_stakes`.

        Folding on READ is what makes the fix retroactive with no data migration.
        """
        assert defect_route(label="bad", reason_tags=["boring"])["fix_type"] == "ranking_rule"
        assert defect_route(label="bad", reason_tags=["confusing"])["fix_type"] == "missing_context"

    def test_one_fix_type_even_when_several_tags_route(self):
        """`_cluster_identity` keys on ONE fix_type; a row cannot be two clusters."""
        route = defect_route(label="bad", reason_tags=["bad_image", "stale"])
        assert route["fix_type"] == "bad_image"
        assert route["reason_tags_routed"] == ["bad_image", "stale"]

    def test_non_routing_tags_do_not_consume_the_slot(self):
        """A leading praise tag must not shadow the complaint behind it."""
        route = defect_route(label="bad", reason_tags=["high_stakes", "stale"])
        assert route["fix_type"] == "staleness"
        assert route["reason_tags_routed"] == ["stale"]

    def test_comma_string_form(self):
        """The route accepts the query-param spelling the endpoint also accepts."""
        route = defect_route(label="kill", reason_tags="stale,duplicate")
        assert route["fix_type"] == "staleness"

    def test_route_declares_that_it_was_inferred(self):
        route = defect_route(label="bad", reason_tags=["stale"])
        assert route["derived_from"] == "reason_tags"

    def test_it_never_proposes_an_issue(self):
        """71 auto-candidates on the first backfill is the cried-wolf failure."""
        route = defect_route(label="bad", reason_tags=["stale"])
        assert "create_issue_candidate" not in route

    def test_positive_vocabulary_routes_nowhere_as_a_class(self):
        for tag in NON_DEFECT_REASONS:
            assert reason_fix_type(tag) is None, f"{tag} is praise, not a defect"

    def test_no_reason_is_both_praise_and_a_defect(self):
        assert not (set(REASON_FIX_TYPE) & NON_DEFECT_REASONS)


class TestSharedEnvelope:
    """The route lives in the envelope BOTH write paths call, not in one route.

    The standing trap on this queue, and #1873's actual history: a fix scoped to
    the surface that carried the bug report left native serving cards the web pass
    had already learned to withhold.
    """

    def test_envelope_routes_a_reasoned_bad(self):
        metadata = structured_label_metadata(
            {}, None, label="bad", reason_tags=["stale"]
        )
        assert metadata["fixable_interest"]["fix_type"] == "staleness"

    def test_envelope_writes_nothing_for_a_love(self):
        metadata = structured_label_metadata(
            {}, None, label="love", reason_tags=["public_story"]
        )
        assert metadata is None or "fixable_interest" not in metadata

    def test_an_explicit_fix_type_always_wins(self):
        """A human's ReviewTab choice outranks an inference from a chip tap.

        Turning the inference on must not reclassify a single row somebody had
        already classified by hand.
        """
        metadata = structured_label_metadata(
            {"fix_type": "wrong_entity_rank"},
            None,
            label="bad",
            reason_tags=["stale"],
        )
        assert metadata["fixable_interest"]["fix_type"] == "wrong_entity_rank"

    def test_an_explicit_metadata_fix_type_also_wins(self):
        """The other explicit source — `label_metadata.fixable_interest`."""
        metadata = structured_label_metadata(
            {},
            {"fixable_interest": {"fix_type": "wrong_entity_rank"}},
            label="bad",
            reason_tags=["stale"],
        )
        assert metadata["fixable_interest"]["fix_type"] == "wrong_entity_rank"

    def test_derived_keys_survive_beside_an_explicit_one(self):
        """Precedence is per-key, so the audit trail is not lost to the override."""
        metadata = structured_label_metadata(
            {"fix_type": "wrong_entity_rank"},
            None,
            label="bad",
            reason_tags=["stale"],
        )
        assert metadata["fixable_interest"]["reason_tags_routed"] == ["stale"]

    def test_callers_that_pass_no_label_are_unchanged(self):
        """Back-compat: the label-pass path passed nothing before this queue."""
        metadata = structured_label_metadata({"card_snapshot": {"name": "x"}}, None)
        assert metadata is None or "fixable_interest" not in metadata
