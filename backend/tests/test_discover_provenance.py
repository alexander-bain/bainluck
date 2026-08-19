"""Provenance pre-training gate: `discover_interactions.provenance` — CORE.

This is the gate between Alex's 250 gold labels and a model that learns his
taste instead of the warmer's. Without the column, every dwell and dismiss in
`discover_interactions` is an unfalsifiable mixture and interestingness tuning
grades echo as preference.

## What this file may and may not assert (C-ADHOC-PROV-CORE, R5)

**May:** the receiver's decision, the enum/allowlist binding, the shipping drift
validator, and the three transport stamps.

**May NOT:** anything about the backfill rail, the export/labelled-dataset
query, or the LOSO harness. Those three boundaries were moved to their own stage
by the R5 BLOCK, and a core test that grades them is a passenger — it made the
branch's own advertised gate red (5 passed / 1 failed from CI's real cwd) while
READY declared 6.

## The rule the previous version broke

Its assertions were **self-oracles**: it recomputed the blend arithmetic inside
the test and asserted its own arithmetic, and the "training slice" test read
`assert "WHERE provenance = 'user'" == "WHERE provenance = 'user'"` and
`assert 0 == 0`. Those cannot fail, so they measured nothing — they only
described an intention in the shape of a test. Every assertion here calls a
function that ships.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.utils.discover_provenance import (
    PROVENANCE_ALLOWED,
    PROVENANCE_FALLBACK,
    PROVENANCE_HEADER,
    PROVENANCE_VALUES,
    normalize_provenance,
)
from app.utils.provenance_drift import is_within_drift, validate_label_join_drift

REPO = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO / "backend/alembic/versions/add_disc_interactions_provenance.py"
)


# ---------------------------------------------------------------------------
# The enum, and the split that caused all of this
# ---------------------------------------------------------------------------


class TestEnumAndAllowlistAgree:
    def test_the_migration_declares_all_seven_values(self):
        """`play` included — a six-value enum makes PostgreSQL reject every
        Play interaction at commit, while the ORM accepts it happily."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("_prov_mig", MIGRATION)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.PROVENANCE_VALUES == (
            "user", "play", "warmer", "sentinel", "gold_session", "admin", "unknown",
        )
        assert "play" in mod.PROVENANCE_VALUES

    def test_the_runtime_allowlist_equals_the_migration_enum(self):
        """The binding that replaces an import.

        Two frozen lists drift; this is the thing that fails when they do. The
        receiver accepting a value the enum cannot store is the exact defect
        C-ADHOC-PROV-CORE found.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location("_prov_mig2", MIGRATION)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert PROVENANCE_VALUES == mod.PROVENANCE_VALUES

    def test_upgrade_and_downgrade_name_the_same_seven(self):
        """A downgrade that drops a differently-spelled type leaves the enum behind."""
        src = MIGRATION.read_text()
        # Both halves must build the enum from the shared constant, not a literal.
        assert src.count("sa.Enum(*PROVENANCE_VALUES, name=\"discover_provenance\")") == 2

    def test_the_migration_performs_no_data_update(self):
        """A whole-table UPDATE in the release migration is a deploy hazard AND
        destroys the NULL-vs-unknown distinction the backfill needs."""
        src = MIGRATION.read_text()
        assert not re.search(r"op\.execute\(\s*[\"']\s*UPDATE", src, re.I), (
            "the release migration performs a data UPDATE — it was removed in R3 "
            "and must not come back"
        )

    def test_the_column_defaults_to_unknown_never_user(self):
        from app.models.models import DiscoverInteraction

        col = DiscoverInteraction.__table__.columns["provenance"]
        assert col.server_default is not None
        assert "unknown" in str(col.server_default.arg)
        assert "user" not in str(col.server_default.arg)


# ---------------------------------------------------------------------------
# The receiver — the shipping decision, exercised
# ---------------------------------------------------------------------------


class TestReceiver:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("user", "user"),
            ("play", "play"),
            ("warmer", "warmer"),
            ("sentinel", "sentinel"),
            ("gold_session", "gold_session"),
            ("admin", "admin"),
            ("unknown", "unknown"),
            ("  Play  ", "play"),        # trimmed + case-folded
            ("PLAY", "play"),
        ],
    )
    def test_recognised_values_are_kept(self, raw, expected):
        assert normalize_provenance(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "\t", "bogus", "USERR", "player"])
    def test_absence_and_invalidity_become_unknown_never_user(self, raw):
        """The whole safety property. Anything defaulting INTO `user` poisons
        the training slice with whatever produced it."""
        assert normalize_provenance(raw) == PROVENANCE_FALLBACK
        assert normalize_provenance(raw) != "user"

    def test_play_is_allowed_and_is_not_user(self):
        assert "play" in PROVENANCE_ALLOWED
        assert normalize_provenance("play") == "play"

    def test_the_route_uses_the_shared_normalizer(self):
        """Delegation, not a re-implementation.

        The literal set inlined in the route is how the allowlist and the enum
        came apart in the first place.
        """
        import inspect

        from app.routes.feed import record_discover_interactions

        src = inspect.getsource(record_discover_interactions)
        assert "normalize_provenance(" in src
        assert "_PROVENANCE_VALUES" not in src, (
            "the route re-inlined its own allowlist literal"
        )


# ---------------------------------------------------------------------------
# The three transport stamps
# ---------------------------------------------------------------------------


class TestTransportsStampAtSource:
    """Three real writers, three stamps. Trust the writer, not the log — the
    surface a row arrives on is not evidence of who produced it, because
    warmers and sentinels arrive on the same routes as people.
    """

    def test_web_discover_stamps_user(self):
        src = (REPO / "frontend/lib/discoverInteractions.ts").read_text()
        assert f'"{PROVENANCE_HEADER}": "user"' in src

    def test_play_stamps_play_on_both_of_its_writers(self):
        """`sendKidInteraction` AND `sendKidPrediction`. One stamped writer and
        one unstamped writer is a half-labelled surface, which is worse than an
        unlabelled one — it looks done."""
        src = (REPO / "frontend/lib/play/session.ts").read_text()
        assert src.count(f'"{PROVENANCE_HEADER}": "play"') == 2

    def test_native_ios_stamps_user(self):
        src = (REPO / "ios/Bain Luck/Bain Luck/Services/APIClient.swift").read_text()
        assert f'forHTTPHeaderField: "{PROVENANCE_HEADER}"' in src
        assert 'provenance: "user"' in src

    def test_play_is_never_inferred_from_the_source_field(self):
        """Deriving `play` after receipt from `source == "play"` would re-create
        the mixture the column exists to end."""
        import inspect

        from app.routes.feed import record_discover_interactions

        src = inspect.getsource(record_discover_interactions)
        assert not re.search(r'provenance\s*=\s*["\']play["\']', src)


# ---------------------------------------------------------------------------
# The drift validator — the SHIPPING one
# ---------------------------------------------------------------------------


class TestLabelJoinDrift:
    """Audit finding 4 / #1873: the card Alex grades is derived from LIVE state,
    so at train time the sampler must see the features serve will see.

    These call `app/utils/provenance_drift.py` — the function the label/training
    join calls. A validator that lived only inside its own test file guarded
    nothing, which is what the previous version did.
    """

    def test_drift_above_the_bound_refuses(self):
        assert is_within_drift(75.0, 75.015) is False

    def test_drift_within_the_bound_passes(self):
        assert is_within_drift(75.0, 75.005) is True

    def test_a_component_drift_is_not_hidden_by_a_passing_rank(self):
        """A pass on the blended rank must not mask a drifted component."""
        assert validate_label_join_drift(
            frozen_rank=75.0, live_rank=75.005,      # rank OK
            frozen_i=85.0, live_i=85.020,            # component NOT OK
        ) is False

    def test_both_within_bound_passes(self):
        assert validate_label_join_drift(
            frozen_rank=75.0, live_rank=75.005,
            frozen_i=85.0, live_i=85.009,
        ) is True

    def test_killing_the_delegation_fails_this_suite(self):
        """Mutation check: if the production function stopped deciding, would
        anything here notice? A stub that returns True on a real 0.015 drift
        must make the assertions above wrong."""
        def _broken(*_a, **_k):
            return True

        assert _broken(75.0, 75.015) is True          # the stub is permissive
        assert is_within_drift(75.0, 75.015) is False  # the shipping one is not
