"""L2-173 — team-cluster adjudication flow guard tests.

Covers the three verdict paths (MERGE via the rail, KEEP SEPARATE persist+suppress,
DEFER), the merge safety gate (only genuine cluster edges fold; never an arbitrary
two-team merge), and that the merge goes through ``team_merge._apply_merge`` rather
than raw FK SQL in this module.
"""
import pathlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routes import admin_team_clusters as tc


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #

def test_cluster_key_is_stable_and_order_independent():
    a = tc.cluster_key("nba", [3, 1, 2])
    b = tc.cluster_key("nba", [2, 3, 1])
    assert a == b == "nba:1-2-3"


def test_cluster_key_hashes_when_too_long():
    key = tc.cluster_key("baseball_ncaa", list(range(1000, 1100)))
    assert key.startswith("baseball_ncaa:h")
    assert len(key) < 60  # hashed, not the raw id run


def test_verdict_decision_map_is_complete():
    assert set(tc._VERDICT_DECISION) == {"merge", "keep_separate", "defer"}
    assert tc._VERDICT_DECISION["merge"] == "merged"
    assert tc._VERDICT_DECISION["keep_separate"] == "rejected"
    assert tc._VERDICT_DECISION["defer"] == "deferred"


def _m(id, name, recent=0, total=0, mappings=0):
    return {"id": id, "name": name, "slug": f"s{id}", "recent_events": recent,
            "total_events": total, "mappings": mappings}


def test_recommend_incoherent_names_keep_separate():
    # Kent State ⊄ Ohio State — the catastrophic espn_id collision case.
    rec = tc._recommend("skip_incoherent",
                        [_m(1, "Ohio State Buckeyes", recent=5, total=40),
                         _m(2, "Kent State", recent=3, total=30)])
    assert rec["action"] == "keep_separate"


def test_recommend_no_current_events_defer():
    rec = tc._recommend("skip_no_current",
                        [_m(1, "Boston"), _m(2, "Boston Bruins")])
    assert rec["action"] == "defer"


def test_recommend_live_team_plus_dead_stub_merge():
    # One live franchise + a thin dead duplicate with no identity → advise merge.
    rec = tc._recommend("skip_no_stub",
                        [_m(1, "Philadelphia Union", recent=6, total=30, mappings=4),
                         _m(2, "Philadelphia", recent=0, total=8, mappings=0)])
    assert rec["action"] == "merge"
    assert rec["canonical_id"] == 1
    assert rec["fold_ids"] == [2]


def test_recommend_two_real_teams_keep_separate():
    # The non-canonical member has its OWN mappings/events → a real distinct team.
    rec = tc._recommend("skip_no_stub",
                        [_m(1, "New York", recent=5, total=30, mappings=3),
                         _m(2, "New York City FC", recent=4, total=25, mappings=2)])
    assert rec["action"] == "keep_separate"


# --------------------------------------------------------------------------- #
# "never raw merge SQL" — the merge must go through the rail
# --------------------------------------------------------------------------- #

def test_module_does_not_reimplement_the_merge_sql():
    src = pathlib.Path(tc.__file__).read_text()
    assert "_apply_merge(" in src, "merge must call the team_merge rail"
    # The FK re-point + stub delete belong to _apply_merge alone.
    assert "UPDATE events" not in src
    assert "DELETE FROM teams" not in src


# --------------------------------------------------------------------------- #
# Verdict flow — direct-call with a fake async session
# --------------------------------------------------------------------------- #

class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    """Minimal async session: routes execute() by the statement's target table."""

    def __init__(self, team_rows=None, existing_override=None):
        self.team_rows = team_rows or []
        self.existing_override = existing_override
        self.added = []
        self.deleted = []
        self.committed = False
        self.rolled_back = False
        self.executed = []

    async def execute(self, stmt, params=None):
        s = str(stmt)
        self.executed.append((s, params))
        if "teams" in s.lower() and "matching_overrides" not in s.lower():
            return _Result(rows=self.team_rows)
        if "matching_overrides" in s.lower():
            return _Result(scalar=self.existing_override)
        return _Result()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)


def _body(**over):
    defaults = dict(cluster_key="nba:1-2", verdict="keep_separate", sport_key="nba",
                    canonical_id=None, fold_ids=[], member_ids=[1, 2], reason=None)
    defaults.update(over)
    return tc.VerdictRequest(**defaults)


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-secret")


async def test_keep_separate_persists_a_rejected_override():
    sess = _FakeSession()
    res = await tc.team_clusters_verdict(
        request=None, body=_body(verdict="keep_separate"), secret="test-secret", db=sess
    )
    assert res["decision"] == "rejected"
    assert sess.committed
    assert len(sess.added) == 1
    row = sess.added[0]
    assert row.override_type == tc.OVERRIDE_TYPE
    assert row.decision == "rejected"
    assert row.source_name == "nba:1-2"


async def test_defer_persists_a_deferred_override():
    sess = _FakeSession()
    res = await tc.team_clusters_verdict(
        request=None, body=_body(verdict="defer"), secret="test-secret", db=sess
    )
    assert res["decision"] == "deferred"
    assert sess.added[0].decision == "deferred"


async def test_invalid_verdict_rejected():
    with pytest.raises(HTTPException) as ei:
        await tc.team_clusters_verdict(
            request=None, body=_body(verdict="bogus"), secret="test-secret", db=_FakeSession()
        )
    assert ei.value.status_code == 400


async def test_merge_requires_canonical_and_folds():
    with pytest.raises(HTTPException) as ei:
        await tc.team_clusters_verdict(
            request=None, body=_body(verdict="merge", canonical_id=None, fold_ids=[]),
            secret="test-secret", db=_FakeSession(),
        )
    assert ei.value.status_code == 400


async def test_merge_refuses_non_cluster_member(monkeypatch):
    # canonical + a fold that shares NEITHER espn_id NOR normalized name → refused.
    rows = [
        SimpleNamespace(id=1, name="Ohio State Buckeyes", slug="osu", alternate_names=[],
                        sport_id=9, espn_id="108", sport_key="baseball_ncaa"),
        SimpleNamespace(id=2, name="Kent State", slug="kent", alternate_names=[],
                        sport_id=9, espn_id="108", sport_key="baseball_ncaa"),
    ]
    # espn_id matches here (108) so the gate would PASS on espn — flip the fold's
    # espn to force the name+espn mismatch path.
    rows[1].espn_id = "999"
    sess = _FakeSession(team_rows=rows)
    apply_spy = _AsyncSpy()
    monkeypatch.setattr(tc, "_apply_merge", apply_spy)
    with pytest.raises(HTTPException) as ei:
        await tc.team_clusters_verdict(
            request=None,
            body=_body(verdict="merge", canonical_id=1, fold_ids=[2], member_ids=[1, 2],
                       sport_key="baseball_ncaa", cluster_key="baseball_ncaa:1-2"),
            secret="test-secret", db=sess,
        )
    assert ei.value.status_code == 400
    assert apply_spy.calls == 0  # never touched the rail on a refused merge


class _AsyncSpy:
    def __init__(self):
        self.calls = 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        return {"stub_id": args[2].id, "canonical_id": args[1].id}


async def test_merge_calls_the_rail_and_records_merged(monkeypatch):
    rows = [
        SimpleNamespace(id=1, name="Philadelphia Union", slug="union", alternate_names=[],
                        sport_id=5, espn_id="200", sport_key="usa_mls"),
        SimpleNamespace(id=2, name="Philadelphia", slug="philly", alternate_names=[],
                        sport_id=5, espn_id="200", sport_key="usa_mls"),
    ]
    sess = _FakeSession(team_rows=rows)
    spy = _AsyncSpy()
    monkeypatch.setattr(tc, "_apply_merge", spy)

    res = await tc.team_clusters_verdict(
        request=None,
        body=_body(verdict="merge", canonical_id=1, fold_ids=[2], member_ids=[1, 2],
                   sport_key="usa_mls", cluster_key="usa_mls:1-2"),
        secret="test-secret", db=sess,
    )
    assert spy.calls == 1                       # the rail folded the one stub
    assert res["decision"] == "merged"
    assert sess.committed
    assert sess.added[0].decision == "merged"
    assert sess.added[0].target_name == "Philadelphia Union"


async def test_undo_deletes_the_override_and_reports_reversibility():
    # keep-separate is reversible
    ov = SimpleNamespace(decision="rejected")
    sess = _FakeSession(existing_override=ov)
    res = await tc.team_clusters_undo(
        request=None, body=tc.UndoRequest(cluster_key="nba:1-2"), secret="test-secret", db=sess
    )
    assert res["reverted_decision"] == "rejected"
    assert res["reversible"] is True
    assert sess.deleted == [ov]

    # a merge is NOT reversible (data already re-pointed)
    ov2 = SimpleNamespace(decision="merged")
    sess2 = _FakeSession(existing_override=ov2)
    res2 = await tc.team_clusters_undo(
        request=None, body=tc.UndoRequest(cluster_key="usa_mls:1-2"), secret="test-secret", db=sess2
    )
    assert res2["reversible"] is False


async def test_undo_404_when_no_verdict():
    with pytest.raises(HTTPException) as ei:
        await tc.team_clusters_undo(
            request=None, body=tc.UndoRequest(cluster_key="none:0"), secret="test-secret",
            db=_FakeSession(existing_override=None),
        )
    assert ei.value.status_code == 404
