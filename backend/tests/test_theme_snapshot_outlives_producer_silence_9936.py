"""#9936 L1: silence changes nothing a reader sees — not even the page store.

PILLARS TRUTH / DISCOVER. SHIP: a direct or shared link to a published theme
collection (AI, Oscars 2027) keeps opening its last good page while assembly is
switched off or failing, instead of turning into "Couldn't load this collection"
about 72 hours after the last pass. Nothing a person withdrew comes back.

``SNAPSHOT_TTL_S`` is a BOUND, not durability: past it, or after Redis loses the
key, the page answers "building" as before. The pure half is Fable's fixture
(2026-10-23, ``artifacts/fable-containers-survive-corrections-20261023/slice``).
The second half drives the real pass, correction and rebuild (``_FakeDB`` from
``test_theme_assembly_9935``) and the route's own read. Against the old
``3 * 86400`` five tests fail (outlives, both resumed, the withdrawal-while-off
read of the stored page, carried completeness); the bound, old-TTL-key and
superseded tests are relative to the constant and hold either way.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.routes import containers as routes
from app.routes.containers import parse_theme_snapshot, theme_page_window
from app.tasks import theme_assembly as ta
from app.utils.container_presentation import MEMBER_MARKET
from tests.test_theme_assembly_9935 import (  # noqa: F401 — `db` is a fixture
    CLAUDE_6,
    OPENAI_IPO,
    _assemble,
    _container,
    db,
)

HOUR = 3600.0
DAY = 24 * HOUR
OLD_TTL_S = 3 * 86400  # the value before #9936, as keys written by it still carry
AI = 10
IDS = [108231, 108474, 108484, 108559, 109194, 109230, 115348, 13793200]  # retained AI ids


class ClockedStore:
    """``SET NX EX`` / ``GET`` / ``EXPIRE`` with expiry on a settable clock."""

    def __init__(self) -> None:
        self.now = 0.0
        self.values: dict = {}
        self.deadline: dict = {}

    def _alive(self, key) -> bool:
        if key in self.values and self.deadline.get(key) is not None and self.now >= self.deadline[key]:
            del self.values[key]
            del self.deadline[key]
        return key in self.values

    def set(self, key, value, nx=False, ex=None, **kwargs):
        if nx and self._alive(key):
            return None
        self.values[key] = value if isinstance(value, bytes) else str(value).encode()
        self.deadline[key] = self.now + ex if ex else None
        return True

    def get(self, key):
        return self.values[key] if self._alive(key) else None

    def expire(self, key, seconds):
        if not self._alive(key):
            return False
        self.deadline[key] = self.now + seconds
        return True

    def live_keys(self) -> set:
        return {k for k in list(self.values) if self._alive(k)}


def _snapshot(revision: int, shown: list) -> ta.ThemeSnapshot:
    return ta.ThemeSnapshot(
        container_id=AI, slug="ai", name="AI", revision=revision, inventory_complete=True,
        shown_ids=tuple(shown), folded_ids=(), withheld={k: () for k in ta.SNAPSHOT_WITHHOLDS},
        shown_count=len(shown), eligible_count=len(shown),
    )


def _serve(store: ClockedStore, live_revision: int):
    """The route's read: ONLY the live revision's key (routes/containers.py _serve_theme_page)."""
    snap = parse_theme_snapshot(store.get(ta.snapshot_key(AI, live_revision)), container_id=AI, revision=live_revision)
    if snap is None:
        return None  # 503 "building"
    return theme_page_window(snap["shown_ids"], {i: "side_question" for i in IDS}, cursor_key=None, limit=50)


def _assembled_then_quiet(store: ClockedStore, snap: ta.ThemeSnapshot) -> None:
    for hour in range(-24, 1):  # the hourly pass, identical bytes each time
        store.now = hour * HOUR
        assert ta.publish_snapshot(store, snap) in ("written", "refreshed")


# ---------------------------------------------------------------------------
# Pure: publish_snapshot and the route's parse on a clocked store
# ---------------------------------------------------------------------------


def test_live_page_outlives_a_quiet_producer():
    store = ClockedStore()
    _assembled_then_quiet(store, _snapshot(69, IDS))
    for hours in (73, 7 * 24, 29 * 24):
        store.now = hours * HOUR
        page = _serve(store, 69)
        assert page is not None, f"published page unavailable after {hours} h without a pass"
        assert page[0] == IDS


def test_the_bound_is_explicit():
    store = ClockedStore()
    _assembled_then_quiet(store, _snapshot(69, IDS))
    store.now = ta.SNAPSHOT_TTL_S + HOUR
    assert _serve(store, 69) is None  # past the bound the page answers "building", as before


def test_a_correction_during_silence_never_serves_the_old_page():
    store = ClockedStore()
    _assembled_then_quiet(store, _snapshot(69, IDS))
    store.now = 48 * HOUR  # inside the old 72 h too, so this control holds before and after
    # A person withdraws 115348: the correction moves the live revision to 70 and
    # writes no page (the rebuild is skipped while assembly is off).
    assert _serve(store, 70) is None
    # Revision 69's page still exists, and the reader must never fall back to it:
    # it lists the member the person just withdrew.
    assert 115348 in parse_theme_snapshot(store.get(ta.snapshot_key(AI, 69)), container_id=AI, revision=69)["shown_ids"]


def test_a_resumed_publish_finds_its_page_and_moves_no_revision():
    store = ClockedStore()
    snap = _snapshot(69, IDS)
    _assembled_then_quiet(store, snap)
    store.now = 10 * DAY  # assembly comes back after ten quiet days, nothing changed
    stored = store.get(ta.snapshot_key(AI, 69))
    assert ta.choose_revision(membership_changed=False, stored=stored, candidate_at_current=snap) == (False, "identical")
    assert ta.publish_snapshot(store, snap) == "refreshed"  # readers' cursors are not reset by the outage


def test_a_key_written_under_the_old_ttl_keeps_it_until_a_pass_refreshes_it():
    """Deploying the constant extends nothing already stored: a stopped
    assembler gains no protection until one publish or refresh runs."""
    snap = _snapshot(69, IDS)
    key = ta.snapshot_key(AI, 69)

    untouched = ClockedStore()
    untouched.set(key, snap.payload(), nx=True, ex=OLD_TTL_S)  # written before the deploy
    untouched.now = OLD_TTL_S + HOUR
    assert _serve(untouched, 69) is None

    refreshed = ClockedStore()
    refreshed.set(key, snap.payload(), nx=True, ex=OLD_TTL_S)
    refreshed.now = 2 * DAY  # the first pass after the deploy, then silence
    assert ta.publish_snapshot(refreshed, snap) == "refreshed"
    refreshed.now = 2 * DAY + ta.SNAPSHOT_TTL_S - HOUR
    assert _serve(refreshed, 69) is not None
    refreshed.now = 2 * DAY + ta.SNAPSHOT_TTL_S + HOUR
    assert _serve(refreshed, 69) is None


def test_a_superseded_page_ages_out_on_the_same_clock_and_is_never_served():
    store = ClockedStore()
    _assembled_then_quiet(store, _snapshot(69, IDS))
    store.now = HOUR  # the next pass changes membership: revision 70, 69 is never refreshed again
    assert ta.publish_snapshot(store, _snapshot(70, IDS[:-1])) == "written"
    assert _serve(store, 70)[0] == IDS[:-1]
    store.now = ta.SNAPSHOT_TTL_S - HOUR  # 69 was last refreshed at 0
    assert store.live_keys() == {ta.snapshot_key(AI, 69), ta.snapshot_key(AI, 70)}
    store.now = ta.SNAPSHOT_TTL_S + 30  # past 69's bound, inside 70's
    assert store.live_keys() == {ta.snapshot_key(AI, 70)}


# ---------------------------------------------------------------------------
# Through the real pass, correction, rebuild and route read
# ---------------------------------------------------------------------------


@pytest.fixture
def clocked(monkeypatch):
    store = ClockedStore()
    monkeypatch.setattr(ta, "_redis_client", lambda: store)

    class _Async:
        async def get(self, key):
            return store.get(key)

    async def _shared():
        return _Async()

    import app.utils.request_cache

    monkeypatch.setattr(app.utils.request_cache, "get_shared_async_redis", _shared)
    return store


@pytest.mark.asyncio
async def test_a_pass_after_ten_quiet_days_moves_no_revision(db, clocked):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    r = db.revision("ai")

    clocked.now = 10 * DAY
    report = _container(await _assemble(), "ai")
    assert (report["bumped"], report["revision_reason"], report["snapshot"]) == (
        False, "identical", "refreshed")
    assert db.revision("ai") == r
    page = await routes._read_theme_snapshot(db.container_id("ai"), r)
    assert page is not None and sorted(page["shown_ids"]) == sorted([OPENAI_IPO.id, CLAUDE_6.id])


@pytest.mark.asyncio
async def test_a_withdrawal_while_off_answers_building_never_the_withdrawn_page(
    db, clocked, monkeypatch
):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    cid, r = db.container_id("ai"), db.revision("ai")

    monkeypatch.delenv(ta.THEME_ASSEMBLY_ENABLED_ENV)  # the off switch is not bypassed
    clocked.now = 5 * DAY
    live = db.withdraw("ai", CLAUDE_6.id)
    rebuilt = await ta._run_rebuild_theme_snapshot(cid)
    assert rebuilt["reason"] == "theme_assembly_disabled"

    old = await routes._read_theme_snapshot(cid, r)
    assert old is not None and CLAUDE_6.id in old["shown_ids"]  # still stored under the bound
    # The route reads only the live revision, even for a reader holding the old
    # one. Membership is the live published read: the withdrawn member is gone.
    members = [{"container_id": cid, "type": MEMBER_MARKET, "id": i, "class": c}
               for i, c in db.theme_edges("ai").items()]
    assert [m["id"] for m in members] == [OPENAI_IPO.id]
    published = SimpleNamespace(container_id=cid, revision=live, members=members)
    for held in (None, str(r)):
        response = await routes._serve_theme_page(
            None, published, {}, revision=held, cursor=None, limit=None
        )
        assert response.status_code == 503
        assert json.loads(response.body) == {"detail": {"state": "building"}}


@pytest.mark.asyncio
async def test_a_rebuild_after_a_late_correction_still_carries_completeness(db, clocked):
    """Assembly on, passes failing before they publish for ten days, then a
    person withdraws one member: the rebuild's lineage reads the last producer
    page, so it publishes a COMPLETE page without the member, not an
    incomplete one Discover would stop linking to."""
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    cid, r = db.container_id("ai"), db.revision("ai")

    clocked.now = 10 * DAY
    live = db.withdraw("ai", CLAUDE_6.id)
    rebuilt = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]
    assert rebuilt["inventory_complete"] is True
    assert rebuilt["completeness_basis"] == {"revision": r, "corrections_since": 1}
    assert rebuilt["revision_after"] == live + 1

    page = await routes._read_theme_snapshot(cid, db.revision("ai"))
    assert page["shown_ids"] == [OPENAI_IPO.id]
    assert page["inventory_complete"] is True

