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
    degen = [SimpleNamespace(id=15132461, sport_id=42,
                             home_team_name="Benoit Saint-Denis", commence_time=None)]
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
    degen = [SimpleNamespace(id=1, sport_id=42,
                             home_team_name="Kamaru Usman", commence_time=None)]
    candidates = [[SimpleNamespace(id=14792807, home_team_name="Dricus Du Plessis",
                                   away_team_name="Kamaru Usman")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["merged"] == 1
    assert out["sample"][0]["keep"] == 14792807


@pytest.mark.asyncio
async def test_no_real_counterpart_is_skipped(monkeypatch):
    degen = [SimpleNamespace(id=1, sport_id=42,
                             home_team_name="Ghost Fighter", commence_time=None)]
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
    degen = [SimpleNamespace(id=1, sport_id=42,
                             home_team_name="Benoit Saint-Denis", commence_time=None)]
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
    degen = [SimpleNamespace(id=15024173, sport_id=52108,
                             home_team_name="El Feky", commence_time=None)]
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
    degen = [SimpleNamespace(id=1, sport_id=42,
                             home_team_name="Benoit Saint-Denis", commence_time=None)]
    candidates = [[SimpleNamespace(id=9, home_team_name="Benoit Saint-Denis",
                                   away_team_name="Opp")]]
    session = _mock_session(degen, candidates)
    _patch_session(monkeypatch, session)

    out = await _merge_degenerate_combat_events_impl(dry_run=True)
    assert out["dry_run"] is True
    # Only the degen query + one candidate query — no UPDATE/DELETE/commit.
    assert session.execute.await_count == 2
    session.commit.assert_not_called()
