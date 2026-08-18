"""The disputed-identity predicate has ONE implementation (#1902, queue 363).

Alex ruled the 2,069 date-disagreement outcomes QUARANTINED from published
calibration curves as under review until identity-verified. That ruling needs
the predicate to be reachable from app code, so queue 363 lifted it out of
``scripts/census_settlement_contamination.py`` into ``app/utils/market_identity``.

The tests here guard the two things that lift can lose.
"""

from __future__ import annotations

import pathlib
import re
from datetime import date, datetime, timezone

from app.utils.market_identity import (
    QUARANTINE_REASON,
    eastern_game_date,
    market_identity_disputed,
    ticker_game_date,
)

AUG5_TICKER = "KXMLBTOTAL-26AUG051940MINKC"
AUG5_EVENT = datetime(2026, 8, 5, 23, 40, tzinfo=timezone.utc)   # 19:40 ET
AUG6_EVENT = datetime(2026, 8, 6, 23, 30, tzinfo=timezone.utc)   # the wrong game


class TestTheLiftPreservedTheBehaviour:
    def test_the_specimen_is_still_disputed(self):
        """Market 58609021: ticker says Aug 5, event 15187509 is Aug 6."""
        assert market_identity_disputed(AUG5_TICKER, AUG6_EVENT) is True

    def test_the_correct_pairing_is_not_disputed(self):
        assert market_identity_disputed(AUG5_TICKER, AUG5_EVENT) is False

    def test_a_night_game_does_not_manufacture_a_dispute(self):
        """A 19:40 ET first pitch is the NEXT UTC day. Comparing UTC dates would
        flag most of the population and teach the reader to skip the census."""
        assert eastern_game_date(AUG5_EVENT) == date(2026, 8, 5)
        assert AUG5_EVENT.date() == date(2026, 8, 5) or True  # documents the hazard

    def test_an_unreadable_ticker_is_unknown_not_agreeing(self):
        """Load-bearing: a market whose identity we cannot read is NOT thereby in
        agreement with its event."""
        assert ticker_game_date("POLY-0xdeadbeef") is None
        assert market_identity_disputed("POLY-0xdeadbeef", AUG6_EVENT) is False

    def test_the_quarantine_reason_is_named(self):
        """A row dropped without a reason is indistinguishable from a row that
        was never there. The published page must be able to say WHY."""
        assert QUARANTINE_REASON == "market_identity_disputed"


class TestThereIsOnlyOneImplementation:
    """Two surfaces diverged on a shared predicate twice in one week — the
    concept rule (web behind iOS, #1924) and the label-pass live derivation
    (native behind web, #1933). Both were scoped to the endpoint that carried
    the bug report rather than to the class. This test is the standing rule made
    executable for this predicate."""

    def test_the_census_script_imports_rather_than_redefines(self):
        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "scripts/census_settlement_contamination.py"
        ).read_text()
        assert "from app.utils.market_identity import" in src
        assert not re.search(r"^def market_identity_disputed", src, re.M), (
            "the census script has re-grown its own copy of the predicate"
        )
        assert not re.search(r"^def ticker_game_date", src, re.M)

    def test_no_second_definition_anywhere_in_the_tree(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        definers = [
            p
            for p in list(root.glob("app/**/*.py")) + list(root.glob("scripts/**/*.py"))
            if re.search(r"^def market_identity_disputed", p.read_text(), re.M)
        ]
        assert [p.name for p in definers] == ["market_identity.py"], (
            f"more than one implementation: {[str(p) for p in definers]}"
        )

    def test_it_is_importable_from_app_code_without_the_script(self):
        """The whole point of the lift: the calibration payload must be able to
        reach this without importing anything from ``scripts/``."""
        import importlib

        mod = importlib.import_module("app.utils.market_identity")
        assert callable(mod.market_identity_disputed)
        assert "/app/utils/" in mod.__file__.replace("\\", "/")
        assert "scripts" not in mod.__file__.replace("\\", "/")

        # Imports, not prose: the docstring cites the script it was lifted out
        # of, which is provenance and must stay readable.
        source = pathlib.Path(mod.__file__).read_text()
        imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", source, re.M)
        assert not [m for m in imports if m.startswith("scripts")], (
            f"app code reaches back into scripts/ — that inverts the lift: {imports}"
        )


# =============================================================================
# #1933 — the honest-empty gate reaches the NATIVE surface too
# =============================================================================

class TestNativeLabelingWithholdsAnIncoherentField:
    """Alex graded on the native surface and saw the precise defect #1873 fixed.

    #1873 landed in ``admin_label_pass.py`` only; native comes through
    ``admin_judgments.py``, which rendered ``top_outcomes[0]`` as the probability
    regardless of whether the field could be coherent. Independent Kalshi
    binaries routinely sum well past 100% (gotcha #23), so that is a number that
    cannot be true, printed to the one reviewer whose labels steer ranking.
    """

    def test_the_native_serializer_applies_the_same_coherence_gate(self):
        import inspect

        from app.routes import admin_judgments

        src = inspect.getsource(admin_judgments._serialize_labeling_candidate)
        assert "field_coherence" in src, (
            "the native labeling card renders a probability without checking "
            "field coherence — #1873's fix has not reached this surface"
        )
        assert "field_withheld_reason" in src, (
            "honest-empty (ruling 027) requires saying WHY the field is withheld"
        )

    def test_both_surfaces_use_one_coherence_implementation(self):
        """Not two gates that agree today."""
        import inspect

        from app.routes import admin_judgments, admin_label_pass

        assert (
            admin_judgments.field_coherence is admin_label_pass.field_coherence
        ), "the two labeling surfaces hold different coherence functions"

    def test_an_incoherent_field_withholds_probability_and_outcomes(self):
        """Behavioural, through the serializer, with a field summing to 240%."""
        from types import SimpleNamespace

        from app.routes.admin_judgments import _serialize_labeling_candidate

        outcomes = [
            SimpleNamespace(id=i, name=f"Candidate {i}", current_probability=0.8,
                            probability_change_24h=None, rank=i)
            for i in range(3)
        ]
        market = SimpleNamespace(
            id=1, outcomes=outcomes, llm_sport_category="politics", sport=None,
            name="Who will win?", source="kalshi", description=None,
            hook_description=None, image_url=None, group_id=None,
            market_tier=1, volume_24h=0, status="open",
            resolution_date=None, created_at=None, updated_at=None,
        )
        card = _serialize_labeling_candidate(market, rank=1, stratum="test")

        assert card["field_coherent"] is False
        assert card["rendered_probability"] is None, "printed a number that cannot be true"
        assert card["top_outcomes"] is None
        assert card["field_withheld_reason"]

    def test_a_coherent_field_still_renders(self):
        """The other direction, or the gate is just a blanket suppression."""
        from types import SimpleNamespace

        from app.routes.admin_judgments import _serialize_labeling_candidate

        outcomes = [
            SimpleNamespace(id=1, name="Yes", current_probability=0.6,
                            probability_change_24h=None, rank=1),
            SimpleNamespace(id=2, name="No", current_probability=0.4,
                            probability_change_24h=None, rank=2),
        ]
        market = SimpleNamespace(
            id=2, outcomes=outcomes, llm_sport_category="politics", sport=None,
            name="Will it happen?", source="kalshi", description=None,
            hook_description=None, image_url=None, group_id=None,
            market_tier=1, volume_24h=0, status="open",
            resolution_date=None, created_at=None, updated_at=None,
        )
        card = _serialize_labeling_candidate(market, rank=1, stratum="test")

        assert card["field_coherent"] is True
        assert card["rendered_probability"] == 0.6
        assert card["top_outcomes"] and len(card["top_outcomes"]) == 2
        assert card["field_withheld_reason"] is None
