"""C-APPLY-PRE-R2's two BLOCK findings, as specimens against shipping code.

The certification passed everything else and BLOCKed on two things. Both are about
the same property — *the artifact an operator approved is the artifact that gets
applied* — attacked from opposite ends: one corrupts the READING of the artifact,
the other corrupts its ADDRESS.

FINDING 1 — a torn artifact was reported as one that never existed
------------------------------------------------------------------

``decode_envelope`` classifies a checksum failure as ``malformed`` with
``error_class="ChecksumMismatch"``. One frame later ``_load_plan`` flattened every
non-ok read into the prose string ``"plan artifact unreadable: <status>"``, and
``bind_apply`` matched on the corrupt CONSTANT — so prose fell through to
``PLAN_ARTIFACT_MISSING``. The attended operator is then told the plan never
existed, and the documented response to that is *go generate another plan*: the
one action guaranteed to destroy the evidence of an edited store.

**Why the existing 60/60 suite could not see it.** Its corrupt-artifact test
monkeypatches ``_load_plan`` itself and hands the binder ``REASON_PLAN_CORRUPT``
directly. That asserts the binder behaves correctly *given* the right reason. The
defect is that nothing ever produced the right reason. A test that patches past
the boundary containing the bug is green by construction — the dead-oracle class,
arriving on the very rail that exists to stop unreviewed writes.

So the specimen here fakes only the TRANSPORT. The envelope is real, the tamper is
real, and the classification is produced by production ``decode_envelope``.

FINDING 2 — two differently-labelled approvals shared one content address
-------------------------------------------------------------------------

Every plan digest joined its fields with ``"|"``, which is not injective over free
text::

    before="Old|Club", after="New"      -> "...|Old|Club|New"
    before="Old",      after="Club|New" -> "...|Old|Club|New"

Same hash: ``a27569d499b4b1da5cb02d1827ebc670``. The ids were never at risk, and
that is exactly why it survived review — the fields it collapses are the ones a
HUMAN reads. The content address is the promise that what Alex approved is what
gets written; a collision in the club labels breaks that promise precisely where
the approval lives.

Applies to all three rails, because all three had the same ``"|".join``: the
calibration leg plan, the binding plan, and the create plan.
"""

import pytest

from app.tasks import repair_event_team_binding as rail
from app.tasks.repair_event_team_binding import repair
from app.utils import durable_state as ds
from app.utils.durable_state import DurableEnvelope, EnvelopeRead, decode_envelope
from app.utils.repair_apply_plan import (
    REASON_PLAN_CORRUPT,
    REASON_PLAN_MISSING,
    PlannedBinding,
    PlannedCreate,
    PlannedLeg,
    build_binding_plan,
    build_create_plan,
    build_plan,
)

# The three symbols the fix ADDS are imported inside the tests that need them,
# deliberately. Module-level they would turn every specimen in this file into a
# collection error against unfixed code — exit 2, "the gate never ran" (gotcha
# #54's amendment), which proves nothing about behaviour. Function-local, the
# specimens below fail as ASSERTIONS on the shipping surface, which is the only
# fails-first evidence worth quoting.

MLB = 53232


# ── finding 2: the content address ─────────────────────────────────────────


class TestTheAddressCoversTheLabels:
    """Two plans that differ ONLY in club labels must not share an address."""

    def _binding(self, before_name: str, after_name: str) -> PlannedBinding:
        return PlannedBinding(
            event_id=1001,
            side="away",
            expected_before_id=855,
            before_name=before_name,
            after_id=10709,
            after_name=after_name,
            defect="CROSS_CLUB",
            sport_id=MLB,
        )

    def test_the_certifications_exact_collision_is_gone(self):
        """The specimen Codex reported, verbatim.

        ``Old|Club`` -> ``New`` and ``Old`` -> ``Club|New`` are different approvals:
        a reviewer signing the first has not signed the second. Under the old digest
        both addressed as ``a27569d499b4b1da5cb02d1827ebc670``.
        """
        left = build_binding_plan([self._binding("Old|Club", "New")])
        right = build_binding_plan([self._binding("Old", "Club|New")])

        assert left.plan_hash != right.plan_hash
        assert left.plan_hash != "a27569d499b4b1da5cb02d1827ebc670"
        assert right.plan_hash != "a27569d499b4b1da5cb02d1827ebc670"

    def test_a_silently_swapped_club_name_moves_the_address(self):
        """The ordinary case the collision case is a proxy for."""
        approved = build_binding_plan([self._binding("Minnesota Twins", "Boston Red Sox")])
        swapped = build_binding_plan([self._binding("Minnesota Twins", "Boston Red Sox ")])

        assert approved.plan_hash != swapped.plan_hash

    def test_the_create_rail_has_the_same_property(self):
        """Same ``"|".join``, same defect, same fix — assert it on this rail too."""

        def _create(home: str, away: str) -> PlannedCreate:
            return PlannedCreate(
                provider="espn",
                truth_id="401816407",
                home_team_id=11625,
                home_name=home,
                away_team_id=10739,
                away_name=away,
                commence_time="2026-08-05T23:40:00+00:00",
            )

        left = build_create_plan([_create("Kansas City|Royals", "Minnesota")])
        right = build_create_plan([_create("Kansas City", "Royals|Minnesota")])

        assert left.plan_hash != right.plan_hash

    def test_the_calibration_leg_rail_was_safe_only_by_field_order(self):
        """Measured, not assumed: this rail had the same ``"|".join`` and did NOT
        collide — because a numeric field (``expected_is_winner``) happens to sit
        between its two free-text fields, so no content can bridge them.

        That is luck, not a property. Nothing declared it, nothing tested it, and
        adding one adjacent string field would have re-opened it silently. Under
        length-prefixing it is a property. The assertion is the ordinary one: the
        source label is inside the address.
        """
        def _leg(source: str) -> PlannedLeg:
            return PlannedLeg(
                leg_id=7,
                market_id=99,
                verdict="retract",
                expected_is_winner=False,
                expected_source=source,
            )

        assert build_plan([_leg("kalshi")]).plan_hash != build_plan([_leg("kalshi|api")]).plan_hash

    def test_the_encoding_is_injective_over_delimiter_bearing_fields(self):
        """The property, stated directly, rather than one lucky pair of it."""
        from app.utils.repair_apply_plan import digest_fields

        adversarial = [
            (["a|b", "c"], ["a", "b|c"]),
            (["", "a"], ["a", ""]),
            (["1:a"], ["a"]),
            (["|"], ["", ""]),
            (["2:xy"], ["xy"]),
        ]
        for left, right in adversarial:
            assert digest_fields(*left) != digest_fields(*right), (left, right)

    def test_equal_content_still_addresses_equally(self):
        """A content address that is not stable is not an address."""
        rows = [self._binding("Minnesota Twins", "Boston Red Sox")]
        assert build_binding_plan(rows).plan_hash == build_binding_plan(rows).plan_hash


# ── finding 1: could-not-read is not never-existed ─────────────────────────


def _tampered_envelope_read() -> EnvelopeRead:
    """A REAL checksum failure, classified by REAL production code.

    Build a valid envelope, then alter the payload without re-checksumming — a torn
    or edited store, which is the thing the checksum exists to catch. The status is
    whatever ``decode_envelope`` says it is; nothing here asserts it into being.
    """
    envelope = DurableEnvelope.build(
        identity="repair:event-team-binding:plan",
        schema_version="event-team-binding-apply-plan/v2",
        payload={"schema": "event-team-binding-apply-plan/v2", "rows": [], "plan_hash": "x"},
        complete=True,
        source="test",
    )
    raw = {
        "identity": envelope.identity,
        "schema_version": envelope.schema_version,
        "generation": envelope.generation,
        "generated_at": envelope.generated_at.isoformat(),
        "payload": {"schema": "event-team-binding-apply-plan/v2", "rows": [{"edited": True}]},
        "checksum": envelope.checksum,  # stale: belongs to the ORIGINAL payload
        "complete": True,
        "source": "test",
    }
    return decode_envelope(
        raw,
        tier="durable",
        expected_version="event-team-binding-apply-plan/v2",
        max_age_s=14 * 86400,
    )


class TestATornArtifactIsNotAnAbsentOne:
    def test_production_classifies_the_tamper_as_a_checksum_mismatch(self):
        """Premise check. If this drifts, the specimen below proves nothing."""
        read = _tampered_envelope_read()
        assert read.status == ds.MALFORMED
        assert read.error_class == "ChecksumMismatch"

    @pytest.mark.asyncio
    async def test_the_real_loader_reports_corrupt_not_missing(self, monkeypatch):
        """Through the shipping ``_load_plan`` — only the transport is faked.

        This is the exact input Codex used: a durable read of
        ``status="malformed", error_class="ChecksumMismatch"``. Before the fix it
        returned the prose ``"plan artifact unreadable: malformed"``, which
        ``bind_apply`` could not match and therefore called MISSING.
        """
        read = _tampered_envelope_read()

        async def _read(*_a, **_k):
            return read

        import app.services.durable_snapshots as snaps

        monkeypatch.setattr(snaps, "read_snapshot_standalone", _read)

        plan, reason = await rail._load_plan()

        assert plan is None
        assert reason == REASON_PLAN_CORRUPT

    @pytest.mark.asyncio
    async def test_the_apply_refuses_by_the_corrupt_name(self, monkeypatch):
        """The whole path: torn store -> shipping apply -> named refusal, no writes.

        ``repair(apply=True)`` is the surface an attended operator drives, so the
        reason code it returns is the one that decides their next action.
        """
        read = _tampered_envelope_read()

        async def _read(*_a, **_k):
            return read

        import app.services.durable_snapshots as snaps

        monkeypatch.setattr(snaps, "read_snapshot_standalone", _read)

        session = _NoWriteSession()
        out = await repair(session, apply=True, plan_hash="whatever-was-approved")

        assert out["refused"] is True
        assert out["reason_codes"] == [REASON_PLAN_CORRUPT]
        assert REASON_PLAN_MISSING not in out["reason_codes"]
        assert session.updates == []

    @pytest.mark.asyncio
    async def test_a_store_outage_is_neither_missing_nor_corrupt(self, monkeypatch):
        """An unreachable store must not read as 'no plan was ever approved'.

        Same class as the finding — the loader inventing a fact about the world
        from its own inability to look. Codex's fix-sketch asked for unavailable and
        genuinely-absent to keep their own honest readings; this is that half.
        """

        from app.utils.repair_apply_plan import REASON_PLAN_UNREADABLE

        async def _raise(*_a, **_k):
            raise ConnectionError("redis is down")

        import app.services.durable_snapshots as snaps

        monkeypatch.setattr(snaps, "read_snapshot_standalone", _raise)

        plan, reason = await rail._load_plan()

        assert plan is None
        assert reason == REASON_PLAN_UNREADABLE

        session = _NoWriteSession()
        out = await repair(session, apply=True, plan_hash="whatever-was-approved")
        assert out["reason_codes"] == [REASON_PLAN_UNREADABLE]
        assert session.updates == []

    @pytest.mark.asyncio
    async def test_a_genuinely_absent_artifact_still_reports_missing(self, monkeypatch):
        """The other direction. Widening 'corrupt' must not swallow real absence."""

        async def _read(*_a, **_k):
            return EnvelopeRead(status=ds.MISSING, tier="durable")

        import app.services.durable_snapshots as snaps

        monkeypatch.setattr(snaps, "read_snapshot_standalone", _read)

        plan, reason = await rail._load_plan()

        assert plan is None
        assert reason == REASON_PLAN_MISSING


class TestTheTranslatorIsTotal:
    """Every durable status maps to a refusal, and none of them invents absence."""

    def test_only_a_real_missing_maps_to_missing(self):
        from app.utils.repair_apply_plan import (
            REASON_PLAN_UNREADABLE,
            plan_reason_for_read,
        )

        assert plan_reason_for_read(ds.MISSING) == REASON_PLAN_MISSING
        for status in (ds.MALFORMED, ds.WRONG_TYPE, ds.WRONG_VERSION):
            assert plan_reason_for_read(status) == REASON_PLAN_CORRUPT
        for status in (ds.UNAVAILABLE, ds.STALE, "some-status-invented-later"):
            assert plan_reason_for_read(status) == REASON_PLAN_UNREADABLE

    def test_a_superseded_address_scheme_reads_as_corrupt_not_missing(self):
        """A v1 artifact after the queue-364 digest change.

        Bumping the schema is what makes this refusal legible: the operator is told
        the artifact cannot be trusted, not that their approval never happened.
        """
        from app.utils.repair_apply_plan import plan_reason_for_read

        assert plan_reason_for_read(ds.WRONG_VERSION) == REASON_PLAN_CORRUPT


# ── minimal double ─────────────────────────────────────────────────────────


class _NoWriteSession:
    """Records any write attempt. There must be none on a refusal path."""

    def __init__(self):
        self.updates: list = []

    async def execute(self, *args, **kwargs):  # pragma: no cover - must not run
        self.updates.append((args, kwargs))
        raise AssertionError("a refused apply must not touch the database")

    async def commit(self):  # pragma: no cover - must not run
        raise AssertionError("a refused apply must not commit")

    async def rollback(self):
        return None
