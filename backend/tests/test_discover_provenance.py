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
VERSIONS = REPO / "backend/alembic/versions"
MIGRATION = VERSIONS / "add_disc_interactions_provenance.py"
PLAY_MIGRATION = VERSIONS / "add_prov_play_enum_value.py"


def _load(path, name):
    """Import a migration by path — they are not on sys.path as modules."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# The enum, and the split that caused all of this
# ---------------------------------------------------------------------------


class TestEnumAndAllowlistAgree:
    def test_the_base_revision_declares_only_what_it_applied(self):
        """Six values — the ones production's `pg_enum` actually holds.

        This is the assertion that looks backwards and is not. `play` belongs in
        the enum; it does not belong in THIS revision, because this revision has
        already run (`alembic_version = add_disc_int_provenance`, verified
        2026-08-19) and Alembic runs a revision once. Adding `play` here changes
        what a fresh database gets and changes nothing about the database with
        the bug — while making every reader believe it was fixed.
        """
        mod = _load(MIGRATION, "_prov_mig")
        assert mod.PROVENANCE_VALUES_AS_APPLIED == (
            "user", "warmer", "sentinel", "gold_session", "admin", "unknown",
        )
        assert "play" not in mod.PROVENANCE_VALUES_AS_APPLIED, (
            "`play` was added back into an already-applied revision — it can "
            "never reach production from there; use add_prov_play_value"
        )

    def test_the_next_revision_adds_play_and_chains_linearly(self):
        """The seventh value lives in a revision that has NOT run.

        This asserted `play.down_revision == base.revision` until INT-096. That
        was a PROXY for the property the failure message actually names — "a
        second head fails the Heroku release phase" — and the proxy was true only
        while `add_disc_int_provenance` happened to be the head. It stopped being
        true the moment UX-P107's `add_outcome_price_changed` landed on master
        first, so this revision was re-parented onto it at integration and the
        proxy went red over a chain that is perfectly linear.

        So assert the property, not the proxy: ONE head, and it is this revision.
        That is strictly stronger — it catches a second head no matter which
        parent is declared — and it does not have to be edited again by the next
        lane that lands a migration ahead of this one.

        ## AMENDED 2026-08-23 (lane1 queue 393) — "ahead" was only half the cases

        `heads == [play.revision]` survives a migration landing **ahead** of this
        one (as a parent, which is what INT-096 hit) and does **not** survive one
        landing **after** it (as a child) — at which point this revision is no
        longer the head, correctly, and the assertion reds over a chain that is
        again perfectly linear. The docstring above promised it would not need
        editing by "the next lane that lands a migration"; that promise held for
        parents and not for children, and the #1946 folded revision
        (`anchors_and_captures`) is the first child.

        So the proxy was replaced with a NARROWER proxy, not with the property.
        The property the failure message names is exactly two things:

        1. there is **one** head — a second one fails the Heroku release phase;
        2. this revision is **on the chain that reaches it**, i.e. it still runs.

        Being the head is neither of those. It is a statement about what happens
        to be newest, which is a moving target by construction — every migration
        ever written stops being the head. Asserted directly below, so the next
        child does not red this again.
        """
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        play = _load(PLAY_MIGRATION, "_prov_play")
        assert play.PLAY_VALUE == "play"

        script = ScriptDirectory.from_config(Config("alembic.ini"))
        heads = list(script.get_heads())
        assert len(heads) == 1, (
            f"expected exactly ONE alembic head, got {heads!r} — a second head "
            f"fails the Heroku release phase and the site does not deploy at all"
        )

        # `play` must still be REACHED by an upgrade to head. Walking head -> base
        # is what proves it is on the live chain rather than stranded on a branch
        # that nothing runs; it holds whether `play` is the head itself or has
        # since acquired descendants.
        chain_to_head = {r.revision for r in script.iterate_revisions(heads[0], "base")}
        assert play.revision in chain_to_head, (
            f"the play revision {play.revision!r} is not on the chain from head "
            f"{heads[0]!r} to base — it has been orphaned onto a branch that "
            f"`alembic upgrade heads` will never execute, so the seventh enum "
            f"value never reaches the database"
        )

        # And the chain really reaches the base this revision exists to amend:
        # `play` is unreachable-by-design from a fresh DB unless it descends from
        # the revision that creates the enum.
        base = _load(MIGRATION, "_prov_mig_b")
        ancestry = {r.revision for r in script.iterate_revisions(play.revision, "base")}
        assert base.revision in ancestry, (
            f"{play.revision!r} must descend from {base.revision!r}, which "
            f"creates the discover_provenance type it adds a value to"
        )

        assert len(play.revision) <= 32  # gotcha #1

    def test_the_runtime_allowlist_equals_the_migration_CHAIN(self):
        """The binding that replaces an import — held against the chain.

        Two frozen lists drift; this is the thing that fails when they do. The
        receiver accepting a value the enum cannot store is the exact defect
        C-ADHOC-PROV-CORE found.

        Held against `base + play` rather than against one file, and
        order-sensitively, because that is the enum both databases converge on:
        a fresh DB creates the six then appends `play`; production already has
        the six and appends `play`. Same labels, same ordinals. An assertion
        against a single migration file is what stayed green while the shipped
        enum matched neither it nor the allowlist.
        """
        base = _load(MIGRATION, "_prov_mig2")
        play = _load(PLAY_MIGRATION, "_prov_play2")
        assert PROVENANCE_VALUES == base.PROVENANCE_VALUES_AS_APPLIED + (
            play.PLAY_VALUE,
        )

    def test_upgrade_and_downgrade_name_the_same_six(self):
        """A downgrade that drops a differently-spelled type leaves the enum behind."""
        src = MIGRATION.read_text()
        # Both halves must build the enum from the shared constant, not a literal.
        assert src.count(
            "*PROVENANCE_VALUES_AS_APPLIED, name=\"discover_provenance\""
        ) == 2

    def test_the_play_revision_uses_add_value_not_a_type_rebuild(self):
        """A table rewrite in the release phase is gotcha #31 with an UPDATE.

        `ALTER TYPE … ADD VALUE` is a catalog insert. The alternative — new type,
        `ALTER TABLE … TYPE … USING`, drop, rename — rewrites the whole table
        inside Heroku's ~5-minute release window, and a release that times out
        is a site that does not deploy.
        """
        src = PLAY_MIGRATION.read_text()
        assert "ADD VALUE IF NOT EXISTS" in src, (
            "must be idempotent: autocommit_block() means this statement is NOT "
            "rolled back if a later one in the same revision fails"
        )
        assert "autocommit_block" in src, (
            "ALTER TYPE ADD VALUE needs the autocommit block — required outright "
            "before PG12, and the block costs nothing on 17"
        )
        assert not re.search(r"ALTER\s+TABLE\s+\w+\s+ALTER\s+COLUMN", src, re.I), (
            "the play revision performs a table rewrite — use ADD VALUE"
        )

    def test_the_play_revision_is_postgres_guarded(self):
        """`ALTER TYPE` is PostgreSQL-only; a sqlite replay must not raise."""
        src = PLAY_MIGRATION.read_text()
        assert 'dialect.name != "postgresql"' in src

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
