"""Queue 368 / C-APPLY-PRE-CREATE-R2 finding 1 — the create address must bind
``sport_id``, because the create WRITES it.

The hole: ``PlannedCreate.digest_line`` documented itself as "every field the
create WRITES" and then omitted ``sport_id``. So an artifact could have its
``sport_id`` edited, keep its stored ``plan_hash`` — still a correct address for
its own content, because the content the address covered had not changed — and
``decode_create_plan`` returned ``ok``. The decoder made it worse by reading the
field with ``row.get("sport_id")``, which never raises: a missing value decoded
as ``None`` and a garbage value decoded as itself.

Why it is not a theoretical hole. MLB carries TWO team registries — sport_id
33178 and 53232, with all 30 clubs duplicated across them (#1798). Both live
create plans name ``sport_id`` 53232 on every row. Flipping that one integer
creates every reviewed game against the other copy of the club registry, which
is the exact defect the whole rail exists to stop, arriving through the door
marked "approved".

Fixed together, as the finding required: the field is in the digest, the schema
is bumped to /v3 so a v2 artifact refuses with "the scheme moved" rather than
"somebody edited the file", and the decoder requires an int.
"""

import pytest

from app.utils.repair_apply_plan import (
    CREATE_PLAN_SCHEMA,
    REASON_PLAN_CORRUPT,
    build_create_plan,
    decode_create_plan,
)

# The two MLB registries. Every club exists in both (#1798).
MLB_REAL = 53232
MLB_TWIN = 33178


def _row(truth_id="401816572", sport_id=MLB_REAL, **kw):
    from app.utils.repair_apply_plan import PlannedCreate

    base = dict(
        truth_id=truth_id,
        provider="espn",
        home_team_id=870,
        away_team_id=10745,
        home_name="Pittsburgh Pirates",
        away_name="Detroit Tigers",
        commence_time="2026-08-18T22:40:00+00:00",
        sport_id=sport_id,
        label="Detroit Tigers @ Pittsburgh Pirates",
    )
    base.update(kw)
    return PlannedCreate(**base)


class TestSportIdIsInTheAddress:
    def test_flipping_the_registry_mints_a_different_address(self):
        real = build_create_plan([_row(sport_id=MLB_REAL)])
        twin = build_create_plan([_row(sport_id=MLB_TWIN)])
        assert real.plan_hash != twin.plan_hash, (
            "a create plan against the other MLB team registry is a DIFFERENT "
            "plan and must not share an address"
        )

    def test_the_rest_of_the_row_still_binds(self):
        """Guard against a fix that binds sport_id and loosens something else."""
        base = build_create_plan([_row()])
        for field, value in (
            ("truth_id", "401816573"),
            ("home_team_id", 871),
            ("away_team_id", 10746),
            ("home_name", "Pittsburgh Pirate"),
            ("away_name", "Detroit Tiger"),
            ("commence_time", "2026-08-19T16:35:00+00:00"),
            ("provider", "statpal"),
        ):
            other = build_create_plan([_row(**{field: value})])
            assert base.plan_hash != other.plan_hash, f"{field} fell out of the address"

    def test_label_is_still_outside_the_address(self):
        """Re-wording prose for a reviewer must not mint a new address."""
        a = build_create_plan([_row(label="Tigers at Pirates")])
        b = build_create_plan([_row(label="Detroit @ Pittsburgh")])
        assert a.plan_hash == b.plan_hash


class TestTheDecoderRefusesWhatTheDigestNowCovers:
    def test_a_mutated_sport_id_no_longer_decodes_clean(self):
        """THE SPECIMEN. Edit sport_id in a valid artifact, leave plan_hash as
        approved, and the decode must refuse. Before the fix it returned ok."""
        payload = build_create_plan([_row(sport_id=MLB_REAL)]).as_payload()
        approved_hash = payload["plan_hash"]

        payload["rows"][0]["sport_id"] = MLB_TWIN  # the only edit

        plan, reason = decode_create_plan(payload)
        assert plan is None
        assert reason == REASON_PLAN_CORRUPT
        assert payload["plan_hash"] == approved_hash, (
            "the point of the specimen: the attacker/typo does not touch the hash"
        )

    def test_a_missing_sport_id_is_corrupt_not_none(self):
        payload = build_create_plan([_row()]).as_payload()
        del payload["rows"][0]["sport_id"]
        plan, reason = decode_create_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    @pytest.mark.parametrize("junk", ["banana", None, [], {}])
    def test_a_garbage_sport_id_is_corrupt(self, junk):
        payload = build_create_plan([_row()]).as_payload()
        payload["rows"][0]["sport_id"] = junk
        plan, reason = decode_create_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT

    def test_an_untouched_artifact_still_round_trips(self):
        """Both directions — the refusal must not eat the honest case."""
        original = build_create_plan([_row("401816572"), _row("401816573")])
        plan, reason = decode_create_plan(original.as_payload())
        assert reason == "ok"
        assert plan is not None
        assert plan.plan_hash == original.plan_hash
        assert {r.sport_id for r in plan.rows} == {MLB_REAL}


class TestTheSchemaBumpRetiresV2:
    def test_schema_is_v3(self):
        assert CREATE_PLAN_SCHEMA == "event-create-from-truth-plan/v3"

    def test_a_v2_artifact_refuses_as_corrupt(self):
        """A v2 create artifact — including the two that were GREEN at queue 367
        — must refuse rather than be re-addressed under the new scheme."""
        payload = build_create_plan([_row()]).as_payload()
        payload["schema"] = "event-create-from-truth-plan/v2"
        plan, reason = decode_create_plan(payload)
        assert plan is None and reason == REASON_PLAN_CORRUPT
