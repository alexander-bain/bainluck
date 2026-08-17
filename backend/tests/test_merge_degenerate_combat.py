"""#175 Item 3 — degenerate combat-event merge decision logic.

The CI harness has no live DB, so these drive ``_merge_degenerate_combat_events_impl``
with a sequenced mock session (degen query, then one candidate query per
degenerate) and pin the matcher's contract: a degenerate home==away fight event
merges into the ONE real event that shares its single fighter (either
orientation), and never merges on 0 or ambiguous (>1) matches. Functional proof
(orphaned Kalshi markets repointing onto the real event) is the production run.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks.sports import _merge_degenerate_combat_events_impl


def _result(rows):
    r = MagicMock()
    r.all.return_value = list(rows)
    return r


def _degen(id, sport_id, home_team_name, commence_time=None, *,
           external_id=None, espn_id=None, statpal_fixture_id=None,
           home_team_id=None, away_team_id=None):
    """A degenerate (``home==away``) row as the rail actually selects it.

    The five keyword fields default to None because that IS the artifact's
    signature — a genuine single-participant corruption has no provider anchor
    and no resolved participants, which is precisely what makes it safe to
    delete. Tests that want a REAL row wearing a degenerate-looking label pass
    them explicitly (R7 / C-CERT-1801-R6).
    """
    return SimpleNamespace(
        id=id, sport_id=sport_id, home_team_name=home_team_name,
        commence_time=commence_time, external_id=external_id, espn_id=espn_id,
        statpal_fixture_id=statpal_fixture_id, home_team_id=home_team_id,
        away_team_id=away_team_id,
    )


def _mock_session(degen_rows, candidate_batches):
    """Session whose execute() returns the degen query, then one candidate batch
    per degenerate, in order. dry_run makes no further calls."""
    session = AsyncMock()
    seq = [_result(degen_rows)] + [_result(b) for b in candidate_batches]
    session.execute.side_effect = seq
    return session


def _patch_session(monkeypatch, session):
    class _Ctx:
        async def __aenter__(self_):
            return session

        async def __aexit__(self_, *a):
            return False

    # The impl does `from app.tasks.base import get_task_session` at call time,
    # so patch the source module.
    monkeypatch.setattr("app.tasks.base.get_task_session", lambda: _Ctx())


@pytest.mark.asyncio
async def test_merges_degenerate_into_single_real_event(monkeypatch):
    degen = [_degen(15132461, 42, "Benoit Saint-Denis")]
    candidates = [[SimpleNamespace(id=999, home_team_name="Benoit Saint-Denis",
                                   away_team_name="Paddy Pimblett")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["merged"] == 1
    assert out["sample"][0] == {"orphan": 15132461, "keep": 999,
                                "fighter": "Benoit Saint-Denis"}


@pytest.mark.asyncio
async def test_matches_swapped_orientation(monkeypatch):
    # The degenerate's fighter is the real event's AWAY competitor.
    degen = [_degen(1, 42, "Kamaru Usman")]
    candidates = [[SimpleNamespace(id=14792807, home_team_name="Dricus Du Plessis",
                                   away_team_name="Kamaru Usman")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["merged"] == 1
    assert out["sample"][0]["keep"] == 14792807


@pytest.mark.asyncio
async def test_no_real_counterpart_is_skipped(monkeypatch):
    degen = [_degen(1, 42, "Ghost Fighter")]
    candidates = [[SimpleNamespace(id=2, home_team_name="Someone Else",
                                   away_team_name="Another Person")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["merged"] == 0
    assert out["skipped_no_match"] == 1


@pytest.mark.asyncio
async def test_ambiguous_two_reals_is_skipped(monkeypatch):
    # Same fighter appears in two distinct real events in the window → never guess.
    degen = [_degen(1, 42, "Benoit Saint-Denis")]
    candidates = [[
        SimpleNamespace(id=10, home_team_name="Benoit Saint-Denis", away_team_name="A B"),
        SimpleNamespace(id=11, home_team_name="C D", away_team_name="Benoit Saint-Denis"),
    ]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["merged"] == 0
    assert out["skipped_ambiguous"] == 1


@pytest.mark.asyncio
async def test_domain_agnostic_non_combat_merges(monkeypatch):
    """#180 Item 2 — the matcher is NOT combat-gated. A non-combat degenerate
    (e.g. an esports/baseball ``Team A vs Team A``) merges into its unique real
    ``Team A vs Team B`` counterpart exactly like a fight event. This pins the
    domain-agnostic contract so a future 'combat-only' regression is caught."""
    degen = [_degen(15024173, 52108, "El Feky")]
    candidates = [[SimpleNamespace(id=77, home_team_name="El Feky",
                                   away_team_name="Al Ahly")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["merged"] == 1
    assert out["sample"][0] == {"orphan": 15024173, "keep": 77,
                                "fighter": "El Feky"}


@pytest.mark.asyncio
async def test_dry_run_does_not_write(monkeypatch):
    degen = [_degen(1, 42, "Benoit Saint-Denis")]
    candidates = [[SimpleNamespace(id=9, home_team_name="Benoit Saint-Denis",
                                   away_team_name="Opp")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["dry_run"] is True
    # Only the degen query + one candidate query — no UPDATE/DELETE/commit.
    assert session.execute.await_count == 2
    session.commit.assert_not_called()


# =============================================================================
# R7 (#1801) — deletion requires evidence of the artifact, not the shape of one
#
# C-CERT-1801-R6 returned BLOCK on this rail. It reasoned that
# `home_team_name == away_team_name` cannot be a fixture, therefore the row is
# a corrupt ingest artifact, therefore it may be deleted once a unique real
# counterpart is found. The premise is true and the conclusion does not follow:
# `Event` carries `home_team_id` and `away_team_id` as separate nullable FKs and
# nothing says equal DISPLAY LABELS mean the same participant. Two distinct
# clubs share a short name ("United", "City"), and a provider filling the label
# from the wrong field yields a row that looks degenerate while being real.
#
# The cert executed it: event 9001, three provider anchors, two distinct
# participants, `merged=1`, `DELETE ... 9001`, committed. Ruling 042's class —
# label equality read as identity.
# =============================================================================


@pytest.mark.asyncio
async def test_an_anchored_row_with_distinct_participants_is_never_deleted(
    monkeypatch,
):
    """The cert's exact specimen. Fails-first: the shipped rail deleted this.

    Three anchors AND two distinct participant IDs — either half alone is
    already disqualifying, so this row is refused twice over. It is also given
    a perfectly good unique counterpart, so nothing but the identity check
    stands between it and deletion.
    """
    degen = [_degen(
        9001, 42, "United",
        external_id="odds-api-9001", espn_id="espn-9001",
        statpal_fixture_id="statpal-9001",
        home_team_id=101, away_team_id=202,
    )]
    candidates = [[SimpleNamespace(id=9002, home_team_name="United",
                                   away_team_name="City")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=False)

    assert out["merged"] == 0, (
        "a provider-anchored row with two distinct participants was merged — "
        "the rail is reading label equality as identity (ruling 042)"
    )
    assert out["refused_anchored"] == 1
    session.commit.assert_not_called()
    executed = " ".join(
        str(c.args[0]) for c in session.execute.await_args_list
    )
    assert "DELETE FROM events" not in executed, (
        "a DELETE was issued against a real, anchored event"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,kwargs",
    [
        ("external_id alone", {"external_id": "odds-api-1"}),
        ("espn_id alone", {"espn_id": "espn-1"}),
        ("statpal_fixture_id alone", {"statpal_fixture_id": "statpal-1"}),
        ("distinct participants alone", {"home_team_id": 5, "away_team_id": 6}),
    ],
)
async def test_any_single_disqualifier_is_enough(monkeypatch, label, kwargs):
    """Each half of the test refuses on its own.

    Asserted separately because the cert's specimen carried all four at once,
    and a conjunction bug (requiring ALL anchors before refusing) would pass
    that one case while still deleting a row anchored by only one provider —
    which is the common shape, not the rare one.
    """
    degen = [_degen(1, 42, "United", **kwargs)]
    candidates = [[SimpleNamespace(id=2, home_team_name="United",
                                   away_team_name="City")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=False)
    assert out["merged"] == 0, f"not refused on {label}"
    assert out["refused_anchored"] == 1
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_the_same_participant_twice_is_still_an_artifact(monkeypatch):
    """The repair must survive the fix, or this is a no-op dressed as a guard.

    `home_team_id == away_team_id` is the artifact wearing resolved IDs: one
    participant recorded on both sides. Participant IDs that are PRESENT but
    IDENTICAL are evidence FOR the artifact reading, not against it — so this
    row still merges. Without this case the P1 fix could have been written as
    "any participant IDs disqualify" and every test above would still pass.
    """
    degen = [_degen(1, 42, "Benoit Saint-Denis", home_team_id=7, away_team_id=7)]
    candidates = [[SimpleNamespace(id=9, home_team_name="Benoit Saint-Denis",
                                   away_team_name="Paddy Pimblett")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["merged"] == 1, (
        "a genuine single-participant artifact was refused — the guard has "
        "turned the rail into the permanent no-op it was written to avoid"
    )
    assert out["refused_anchored"] == 0


@pytest.mark.asyncio
async def test_a_refusal_does_not_stop_the_scan(monkeypatch):
    """One bad row must not cost the whole pass (gotcha #42).

    The refused row is FIRST, so a `return`/`break` instead of `continue` would
    silently drop the healthy sibling behind it and still report a clean run.

    Only ONE candidate batch is supplied for two degenerates, and that is the
    assertion, not an oversight: the identity check runs BEFORE the ±28h window
    scan, so a refused row never issues a candidate query at all. A row that may
    not be deleted should not have a deletion candidate computed for it. If the
    check is ever moved below the scan, this fixture starves and the test goes
    red — which is the correct signal.
    """
    degen = [
        _degen(9001, 42, "United", external_id="odds-api-9001"),
        _degen(15132461, 42, "Benoit Saint-Denis"),
    ]
    candidates = [
        [SimpleNamespace(id=999, home_team_name="Benoit Saint-Denis",
                         away_team_name="Paddy Pimblett")],
    ]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["refused_anchored"] == 1
    assert out["merged"] == 1, "the healthy row behind the refusal was dropped"
    assert out["refused_sample"][0]["id"] == 9001
    assert out["refused_sample"][0]["anchors"] == ["external_id"]
