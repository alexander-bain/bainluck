"""Card integrity: #1872 (anonymized), #1873 (stale snapshot), #1874 (all-100%).

One rule, three surfaces: **a card is derived from live state, and a field that
cannot be computed coherently is withheld rather than printed.**
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.card_integrity import (
    INCOHERENT_FIELD_SUM,
    card_defects,
    count_anonymized,
    field_coherence,
    is_anonymized_market,
    is_anonymized_outcome_name,
)

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


class TestAnonymizedNames:
    """#1872 — Polymarket serves these itself; we suppress rather than rewrite."""

    @pytest.mark.parametrize(
        "name",
        ["Person B", "Person K", "person k", "Candidate 3", "Option A",
         "Player C", "Team D", " Nominee F "],
    )
    def test_placeholder_shapes_match(self, name):
        assert is_anonymized_outcome_name(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "Kamala Harris",
            "Person of the Year",        # placeholder word, real phrase
            "Candidate with most votes",
            "Team USA",                  # a real team, not "Team D"
            "Jerome Powell",
            "Yes",
            "No",
            "",
            None,
        ],
    )
    def test_real_names_do_not_match(self, name):
        assert is_anonymized_outcome_name(name) is False

    def test_a_fully_anonymized_field_is_anonymized(self):
        assert is_anonymized_market(["Person B", "Person C", "Person M"]) is True

    def test_a_majority_anonymized_field_is_anonymized(self):
        """A partly-disclosed field is just as unreadable, and looks worse:
        it appears to have real content."""
        assert is_anonymized_market(["Trump", "Person B", "Person C"]) is True

    def test_a_mostly_real_field_is_not(self):
        assert is_anonymized_market(["Trump", "Harris", "Person B"]) is False

    def test_an_empty_field_is_not_anonymized(self):
        """Empty is a different defect with a different owner."""
        assert is_anonymized_market([]) is False
        assert is_anonymized_market([None, ""]) is False

    def test_count_is_reported_for_the_census(self):
        assert count_anonymized(["Person B", "Harris", "Person C"]) == 2


class TestFieldCoherence:
    """#1874 — a rendered card must never show every option at 100%."""

    def test_alexs_exact_shape_is_incoherent(self):
        result = field_coherence([1.0, 1.0, 1.0, 1.0])
        assert result["coherent"] is False
        assert result["all_certain"] is True
        assert result["reason"] == "all_outcomes_certain"

    def test_a_normal_vigged_field_is_coherent(self):
        """Measured mean sum across 361 live Polymarket markets is 1.147."""
        assert field_coherence([0.62, 0.31, 0.21])["coherent"] is True

    def test_a_clean_two_way_is_coherent(self):
        assert field_coherence([0.55, 0.45])["coherent"] is True

    def test_a_sum_over_the_threshold_is_incoherent(self):
        result = field_coherence([0.9, 0.9])
        assert result["coherent"] is False
        assert result["reason"] == "sum_exceeds_one"
        assert result["sum"] == pytest.approx(1.8)

    def test_the_threshold_sits_clear_of_ordinary_vig(self):
        assert INCOHERENT_FIELD_SUM > 1.25

    def test_a_single_certain_outcome_is_not_flagged_certain(self):
        """A resolved one-sided binary is a legitimate 1.0, not a broken field."""
        assert field_coherence([1.0])["all_certain"] is False

    def test_no_prices_is_incoherent_not_a_crash(self):
        result = field_coherence([None, None])
        assert result["coherent"] is False
        assert result["reason"] == "no_priced_outcomes"
        assert result["sum"] is None

    def test_junk_values_never_raise(self):
        assert field_coherence(["", "abc", None, object()])["coherent"] is False


class TestCardDefects:
    def test_a_clean_market_has_none(self):
        assert card_defects(
            outcome_names=["Harris", "Trump"],
            outcome_probabilities=[0.52, 0.5],
        ) == []

    def test_both_defects_are_reported_not_just_the_first(self):
        defects = card_defects(
            outcome_names=["Person B", "Person C"],
            outcome_probabilities=[1.0, 1.0],
        )
        assert "anonymized_outcomes" in defects
        assert any(d.startswith("incoherent_field") for d in defects)
        assert len(defects) == 2


class TestDiscoverSuppression:
    """#1872 on the feed side — the same predicate, one import not two."""

    def test_an_anonymized_market_is_suppressed(self):
        from app.utils.feed_market_quality import classify_market_quality

        quality = classify_market_quality(
            "Who will be the next Secretary General of the United Nations?",
            sport_category="politics",
            outcome_names=["Person K", "Person B", "Person M"],
        )
        assert quality.quality_class == "suppress"
        assert "anonymized_outcomes" in quality.reasons

    def test_the_same_market_with_real_names_survives(self):
        """The suppression must be about the NAMES, not the subject."""
        from app.utils.feed_market_quality import classify_market_quality

        quality = classify_market_quality(
            "Who will be the next Secretary General of the United Nations?",
            sport_category="politics",
            outcome_names=["Rebeca Grynspan", "Rafael Grossi", "Michelle Bachelet"],
        )
        assert quality.quality_class != "suppress"

    def test_discover_and_the_label_queue_share_one_predicate(self):
        """Two surfaces suppressing slightly different sets is the failure."""
        import inspect

        from app.utils import feed_market_quality

        src = inspect.getsource(feed_market_quality)
        assert "from app.utils.card_integrity import is_anonymized_market" in src
        # The regex must not be restated locally.
        assert "Person|Candidate" not in src


class TestLabelPassSuppression:
    """The sampler must not spend a label on a card Discover would not serve."""

    @staticmethod
    def _proposal(pid=1, item_id="101", created=NOW, gen="g1"):
        return SimpleNamespace(
            id=pid, item_type="futures", item_id=str(item_id),
            item_name="Market", category="politics", archetype=None,
            decision="llm_proposed_promote", admin_notes=None,
            features={"generation": gen, "evidence_generation": gen},
            created_at=created,
        )

    @staticmethod
    def _market(mid=101):
        return SimpleNamespace(
            id=mid, status="open",
            resolution_date=NOW + timedelta(days=30),
            llm_sport_category="politics", market_tier=1, volume_24h=1000,
        )

    @staticmethod
    def _outcomes(pairs):
        return [
            SimpleNamespace(name=n, current_probability=p, id=i)
            for i, (n, p) in enumerate(pairs)
        ]

    def test_an_anonymized_market_never_reaches_the_label_queue(self):
        from app.routes.admin_label_pass import _partition_candidates

        part = _partition_candidates(
            [self._proposal()],
            {101: self._market()},
            NOW,
            {101: self._outcomes([("Person B", 0.4), ("Person C", 0.3)])},
        )
        assert part["actionable"] == []
        assert part["suppressed_reasons"] == {"anonymized_outcomes": 1}

    def test_an_all_100_percent_market_never_reaches_the_label_queue(self):
        from app.routes.admin_label_pass import _partition_candidates

        part = _partition_candidates(
            [self._proposal()],
            {101: self._market()},
            NOW,
            {101: self._outcomes([("Harris", 1.0), ("Trump", 1.0)])},
        )
        assert part["actionable"] == []
        assert list(part["suppressed_reasons"]) == [
            "incoherent_field:all_outcomes_certain"
        ]

    def test_a_clean_market_still_gets_labelled(self):
        """The suppressions must not empty the queue (gotcha #43, both
        directions)."""
        from app.routes.admin_label_pass import _partition_candidates

        part = _partition_candidates(
            [self._proposal()],
            {101: self._market()},
            NOW,
            {101: self._outcomes([("Harris", 0.55), ("Trump", 0.45)])},
        )
        assert [p.id for p, _ in part["actionable"]] == [1]
        assert part["suppressed_reasons"] == {}

    def test_an_expired_proposal_is_retired_even_when_lifecycle_says_current(self):
        from app.routes.admin_label_pass import (
            MAX_PROPOSAL_AGE_DAYS,
            _partition_candidates,
        )

        old = self._proposal(created=NOW - timedelta(days=MAX_PROPOSAL_AGE_DAYS + 1))
        part = _partition_candidates(
            [old],
            {101: self._market()},
            NOW,
            {101: self._outcomes([("Harris", 0.55), ("Trump", 0.45)])},
        )
        assert part["actionable"] == []
        assert part["retired_reasons"] == {"proposal_expired": 1}

    def test_a_fresh_proposal_inside_the_cap_survives(self):
        from app.routes.admin_label_pass import (
            MAX_PROPOSAL_AGE_DAYS,
            _partition_candidates,
        )

        recent = self._proposal(
            created=NOW - timedelta(days=MAX_PROPOSAL_AGE_DAYS - 1)
        )
        part = _partition_candidates(
            [recent],
            {101: self._market()},
            NOW,
            {101: self._outcomes([("Harris", 0.55), ("Trump", 0.45)])},
        )
        assert [p.id for p, _ in part["actionable"]] == [1]

    def test_a_poison_row_cannot_empty_the_queue(self):
        """gotcha #42: one bad item must never wipe a whole pass."""
        from app.routes.admin_label_pass import _partition_candidates

        poison = SimpleNamespace(name=None, current_probability=object())
        part = _partition_candidates(
            [self._proposal(1, 101), self._proposal(2, 102)],
            {101: self._market(101), 102: self._market(102)},
            NOW,
            {
                101: [poison],
                102: self._outcomes([("Harris", 0.55), ("Trump", 0.45)]),
            },
        )
        assert 2 in [p.id for p, _ in part["actionable"]]


class TestLiveDerivation:
    """#1873 — the card is built from live rows, not replayed from a snapshot."""

    @staticmethod
    def _market():
        return SimpleNamespace(
            id=101, status="open",
            resolution_date=NOW + timedelta(days=30),
            llm_sport_category="politics", market_tier=1, volume_24h=4242,
        )

    def test_live_values_override_the_write_time_snapshot(self):
        from app.routes.admin_label_pass import _live_features

        proposal = SimpleNamespace(
            features={"probability": 0.95, "volume_24h": 11, "category": "sports"}
        )
        outcomes = [
            SimpleNamespace(name="Harris", current_probability=0.55, id=1),
            SimpleNamespace(name="Trump", current_probability=0.45, id=2),
        ]
        features = _live_features(proposal, self._market(), outcomes)

        assert features["probability"] == pytest.approx(0.55)
        assert features["volume_24h"] == 4242
        assert features["category"] == "politics"

    def test_the_stale_snapshot_is_preserved_not_discarded(self):
        """The evidence for the fix's own necessity must survive the fix."""
        from app.routes.admin_label_pass import _live_features

        proposal = SimpleNamespace(features={"probability": 0.95})
        outcomes = [SimpleNamespace(name="Harris", current_probability=0.55, id=1)]
        features = _live_features(proposal, self._market(), outcomes)

        assert features["snapshot_at_write"] == {"probability": 0.95}
        assert features["snapshot_disagrees"] is True

    def test_an_agreeing_snapshot_is_not_flagged(self):
        from app.routes.admin_label_pass import _live_features

        proposal = SimpleNamespace(features={"probability": 0.56})
        outcomes = [SimpleNamespace(name="Harris", current_probability=0.55, id=1)]
        features = _live_features(proposal, self._market(), outcomes)
        assert features["snapshot_disagrees"] is False

    def test_an_incoherent_field_is_withheld_with_a_reason(self):
        """Honest-empty (ruling 027): say nothing rather than say 100%."""
        from app.routes.admin_label_pass import _live_features

        proposal = SimpleNamespace(features={})
        outcomes = [
            SimpleNamespace(name="A", current_probability=1.0, id=1),
            SimpleNamespace(name="B", current_probability=1.0, id=2),
        ]
        features = _live_features(proposal, self._market(), outcomes)

        assert features["probability"] is None
        assert features["outcomes"] is None
        assert features["field_coherent"] is False
        assert features["field_withheld_reason"] == "all_outcomes_certain"

    def test_a_coherent_field_carries_its_options(self):
        from app.routes.admin_label_pass import _live_features

        proposal = SimpleNamespace(features={})
        outcomes = [
            SimpleNamespace(name="Harris", current_probability=0.55, id=1),
            SimpleNamespace(name="Trump", current_probability=0.45, id=2),
        ]
        features = _live_features(proposal, self._market(), outcomes)

        assert features["field_coherent"] is True
        assert [o["name"] for o in features["outcomes"]] == ["Harris", "Trump"]

    def test_the_route_no_longer_renders_the_raw_snapshot(self):
        import inspect

        from app.routes.admin_label_pass import label_pass_pending

        src = inspect.getsource(label_pass_pending)
        assert "_live_features(" in src
        assert "features = dict(p.features or {})" not in src, (
            "the write-time snapshot is being rendered again — that is #1873"
        )
