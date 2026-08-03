"""Queue 300B Item 1 — a calibration backend must be able to say who it is.

The incident this closes (#1479): two backends have been holding xmin on the
production database since 2026-08-02. Their ``application_name`` is empty, so
the only evidence of ownership available was ``client_addr`` (a recycled dyno
IP) and age — and age as authority is the exact thing C127's containment
contract refuses, because "running a long time" does not distinguish a wedged
orphan from a slow current beat. The result is a correct refusal and a stuck
incident.

These tests grade the classification rules against STATIC fixture rows, the way
C127 grades its own corpus. That is deliberate: the acceptance criterion is that
a current beat, a predeploy run and an unrelated web query are distinguishable
in a ``pg_stat_activity`` row *without* consulting client address or age, and the
only way to prove that is to hand the classifier rows that contain neither.
"""

from __future__ import annotations

import pytest

from app.utils.db_session_identity import (
    APPLICATION_NAME_MAX,
    CURRENT,
    KIND_CURRENT_BEAT,
    KIND_FOREIGN,
    KIND_PREDEPLOY_RUN,
    KIND_SUPERSEDED_RUN,
    KIND_UNCLASSIFIED,
    PREDEPLOY,
    SUPERSEDED,
    UNKNOWN_BUILD,
    build_session_tag,
    classify_activity_row,
    current_build_id,
    parse_session_tag,
)

MAIN = "precompute_calibration_main"
BUILD_NOW = "a1b2c3d4e5f6"
BUILD_OLD = "999888777666"
RUN_NOW = 1_754_200_000_000
RUN_OLD = 1_754_100_000_000
OWNER_NOW = "worker.3:41221"
OWNER_OLD = "worker.1:4080483"


def _row(application_name: str) -> dict:
    """A pg_stat_activity row carrying ONLY what the contract allows as authority.

    No ``client_addr``, no ``backend_start``, no ``age_s`` — if the classifier
    needed any of them these tests could not pass, which is the point.
    """
    return {"application_name": application_name, "state": "active", "pid": 4080483}


# ---------------------------------------------------------------------------
# The headline acceptance: three rows, three answers, no forbidden evidence
# ---------------------------------------------------------------------------


def test_current_beat_predeploy_and_web_are_distinguishable():
    current = _row(
        build_session_tag(
            task=MAIN, build=BUILD_NOW, run_generation=RUN_NOW, owner=OWNER_NOW
        )
    )
    predeploy = _row(
        build_session_tag(
            task=MAIN, build=BUILD_OLD, run_generation=RUN_OLD, owner=OWNER_OLD
        )
    )
    web = _row("")  # what an untagged pooled web session looks like today

    kw = dict(current_build=BUILD_NOW, current_run=RUN_NOW, current_owner=OWNER_NOW)

    assert classify_activity_row(current, **kw).kind == KIND_CURRENT_BEAT
    assert classify_activity_row(current, **kw).current_beat is True
    assert classify_activity_row(current, **kw).generation_relation == CURRENT

    assert classify_activity_row(predeploy, **kw).kind == KIND_PREDEPLOY_RUN
    assert classify_activity_row(predeploy, **kw).current_beat is False
    assert classify_activity_row(predeploy, **kw).generation_relation == PREDEPLOY

    assert classify_activity_row(web, **kw).kind == KIND_FOREIGN
    assert classify_activity_row(web, **kw).is_ours is False
    assert classify_activity_row(web, **kw).generation_relation is None


def test_the_task_name_survives_the_round_trip():
    """C127 allowlists by fingerprint; a named task beats guessing at query text.

    ``precompute_calibration_main`` is the longest name that MUST survive whole —
    the field budget in ``db_session_identity`` is sized around exactly this.
    """
    tag = build_session_tag(
        task=MAIN, build=BUILD_NOW, run_generation=RUN_NOW, owner=OWNER_NOW
    )
    assert classify_activity_row(_row(tag)).task == MAIN


def test_an_earlier_beat_of_the_same_deploy_is_superseded_not_current():
    """Two beats from one slug: only one of them is 'now'."""
    older = _row(
        build_session_tag(
            task=MAIN, build=BUILD_NOW, run_generation=RUN_OLD, owner=OWNER_OLD
        )
    )
    out = classify_activity_row(
        older, current_build=BUILD_NOW, current_run=RUN_NOW, current_owner=OWNER_NOW
    )
    assert out.kind == KIND_SUPERSEDED_RUN
    assert out.generation_relation == SUPERSEDED
    assert out.current_beat is False


def test_same_run_different_owner_is_superseded():
    """Generation collisions are possible (epoch-ms); the owner breaks the tie."""
    twin = _row(
        build_session_tag(
            task=MAIN, build=BUILD_NOW, run_generation=RUN_NOW, owner=OWNER_OLD
        )
    )
    out = classify_activity_row(
        twin, current_build=BUILD_NOW, current_run=RUN_NOW, current_owner=OWNER_NOW
    )
    assert out.kind == KIND_SUPERSEDED_RUN


# ---------------------------------------------------------------------------
# Failing toward "do not touch"
# ---------------------------------------------------------------------------


def test_an_unknown_build_refuses_to_classify_rather_than_guessing():
    """No generation authority is an answer. Defaulting to 'predeploy' is a bug.

    A row that cannot be placed must make C127 raise
    ``GENERATION_AUTHORITY_UNKNOWN`` and refuse, not quietly become a
    cancellation candidate.
    """
    untagged_build = _row(
        build_session_tag(task=MAIN, build=None, run_generation=RUN_OLD, owner=OWNER_OLD)
    )
    out = classify_activity_row(untagged_build, current_build=BUILD_NOW)
    assert out.kind == KIND_UNCLASSIFIED
    assert out.generation_relation is None
    assert out.current_beat is False


def test_an_observer_that_cannot_name_the_current_build_also_refuses():
    tag = build_session_tag(
        task=MAIN, build=BUILD_OLD, run_generation=RUN_OLD, owner=OWNER_OLD
    )
    out = classify_activity_row(_row(tag), current_build=None)
    assert out.generation_relation is None


def test_same_build_with_no_known_current_run_is_treated_as_current():
    """Conservative on purpose: unproven means untouchable.

    Missing a cleanup costs a stuck xmin for another hour. Getting this backwards
    cancels a live build. They are not symmetric.
    """
    tag = build_session_tag(
        task=MAIN, build=BUILD_NOW, run_generation=RUN_OLD, owner=OWNER_OLD
    )
    out = classify_activity_row(_row(tag), current_build=BUILD_NOW)
    assert out.kind == KIND_CURRENT_BEAT
    assert out.current_beat is True


# ---------------------------------------------------------------------------
# Bounded
# ---------------------------------------------------------------------------


def test_the_tag_fits_postgres_even_at_worst_case_widths():
    """Postgres truncates ``application_name`` at 63 bytes SILENTLY.

    A truncated tag loses its tail, and the tail is the owner — so this is not a
    cosmetic bound. Sized for the worst case, not the typical one.
    """
    tag = build_session_tag(
        task="precompute_calibration_main_with_an_absurdly_long_suffix",
        build="0123456789abcdef0123456789abcdef",
        run_generation=9_999_999_999_999,
        owner="a-very-long-hostname.example.internal:4294967295",
    )
    assert len(tag) <= APPLICATION_NAME_MAX
    assert len(tag.encode("utf-8")) <= APPLICATION_NAME_MAX
    # Still parseable after all that bounding — a bounded tag that cannot be read
    # back is no better than no tag.
    assert parse_session_tag(tag) is not None


def test_every_field_present_even_when_every_input_is_missing():
    tag = build_session_tag(task=None)
    parsed = parse_session_tag(tag)
    assert parsed is not None
    assert parsed.task and parsed.build and parsed.run and parsed.owner
    assert parsed.build_known is False


# ---------------------------------------------------------------------------
# Redacted
# ---------------------------------------------------------------------------


def test_the_hostname_never_appears_in_the_tag():
    """The tag lands in logs and error reports; the ledger holds the plaintext."""
    tag = build_session_tag(
        task=MAIN,
        build=BUILD_NOW,
        run_generation=RUN_NOW,
        owner="prod-worker-07.internal:4080483",
    )
    assert "prod-worker-07" not in tag
    assert "internal" not in tag
    assert "4080483" not in tag


def test_the_owner_handle_is_stable_and_discriminating():
    def _owner(raw):
        return parse_session_tag(
            build_session_tag(task=MAIN, build=BUILD_NOW, run_generation=RUN_NOW, owner=raw)
        ).owner

    assert _owner("web.1:12345") == _owner("web.1:12345")
    # A prefix-truncated owner would collide these two; a hash does not.
    assert _owner("web.1:12345") != _owner("web.10:12345")


# ---------------------------------------------------------------------------
# Semantically inert
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        "'; DROP TABLE futures_outcomes; --",
        "x' || pg_sleep(60) || '",
        "a\nb\rc\td",
        "back\\slash",
        'quo"te',
        "semi;colon",
        "null\x00byte",
        "unicode-‮drawkcab",
        "%s %(name)s {brace}",
    ],
)
def test_a_hostile_component_cannot_escape_the_tag_grammar(hostile):
    """Defence in depth: the tag is a bind parameter, AND the charset is closed.

    Being a bind parameter is what actually makes injection impossible. The
    character restriction is here for everything downstream of Postgres — the log
    line, the error report, the operator's terminal — none of which are
    parameterized.
    """
    tag = build_session_tag(
        task=hostile, build=hostile, run_generation=RUN_NOW, owner=hostile
    )
    assert len(tag) <= APPLICATION_NAME_MAX
    for bad in ("'", '"', ";", "\\", "\n", "\r", "\t", "\x00", " ", "%", "{"):
        assert bad not in tag
    parsed = parse_session_tag(tag)
    assert parsed is not None, "sanitizing must not make the tag unreadable"


def test_the_tag_is_bound_never_interpolated():
    """Source-level: the applier must pass the tag as a parameter."""
    import inspect

    from app.tasks import base

    src = inspect.getsource(base.tag_task_session)
    # Strip the docstring: it NAMES ``SET application_name`` to explain why the
    # code does not use it, and a guard that trips on its own rationale is a
    # guard nobody keeps.
    body = src.split('"""')[-1]
    assert "set_config" in body
    assert ":tag" in body, "the tag must reach Postgres as a bind parameter"
    assert "SET application_name" not in body
    assert "f\"SELECT set_config" not in body


# ---------------------------------------------------------------------------
# Parsing anything that is not ours
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        123,
        "psql",
        "pgbouncer",
        "bl1",
        "bl1/only/three/parts",
        "bl1/a/b/c/d/e",
        "bl0/task/build/run/owner",  # a schema we do not know
        "bl1//b/c/d",  # empty field
        "gunicorn: worker",
    ],
)
def test_foreign_application_names_parse_to_nothing(value):
    assert parse_session_tag(value) is None
    assert classify_activity_row({"application_name": value}).kind == KIND_FOREIGN


# ---------------------------------------------------------------------------
# Build id resolution
# ---------------------------------------------------------------------------


def test_build_id_prefers_release_version_then_commit():
    assert current_build_id({"HEROKU_RELEASE_VERSION": "v3711"}) == "v3711"
    assert current_build_id({"HEROKU_SLUG_COMMIT": "ABCDEF0123456789"}) == "abcdef0123"
    assert current_build_id({"GIT_COMMIT": "deadbeef"}) == "deadbeef"
    assert (
        current_build_id(
            {"HEROKU_RELEASE_VERSION": "v9", "HEROKU_SLUG_COMMIT": "abc"}
        )
        == "v9"
    )


def test_no_build_env_is_honest_rather_than_invented():
    assert current_build_id({}) == UNKNOWN_BUILD
