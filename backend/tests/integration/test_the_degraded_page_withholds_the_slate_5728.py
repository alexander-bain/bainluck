"""#5728 end to end: the ROUTE, not a hand-rebuilt call path.

The unit tests beside this one prove `_withheld_slate` empties a slate and that
`_hub_payload` declines to cache a degraded build. Neither of them touches the
line that decides to CALL the first of those — and a mutation sweep found
exactly that gap: deleting the route's `if scoreboard == degraded: withhold`
survived every unit test while restoring the production defect in full.

So these drive the real endpoint. The claim is the one a reader would make: on
finals day, when the scoreboard read raises, the page does not show me the
opening round of a tournament that finished a fortnight ago.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from app.routes import tournaments
from app.routes.tournaments import REGISTERED_TOURNAMENTS
from app.tasks.tournament_matchup_linker import LINKS_PREFIX
from app.utils.tournament_register import load_register
from app.utils.tournament_slate import (
    CEREMONY_STAMP_COVERS_THE_TOURNAMENT_HOURS,
    MATCH_STALE_AFTER_HOURS,
)

SLUG = "us-open"
URL = f"/api/tournaments/{SLUG}"

#: What production served at 19:51:18Z on 2026-09-12. Named because a test that
#: asserts "not 96" against a slate that happens to be empty for some other
#: reason is not asserting anything.
PRODUCTION_DEFECT_COUNT = 96


def _registered_starts() -> list[datetime]:
    """Every ``scheduled_date`` the register carries, as UTC instants."""
    season = REGISTERED_TOURNAMENTS[SLUG]["season"]
    return [
        datetime.fromisoformat(
            m["scheduled_date"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        for m in (load_register(SLUG, season).get("matchups") or [])
        if m.get("scheduled_date")
    ]


def _ceremony_stamp() -> datetime:
    """The opening instant of the draw these tests run against, read from the
    register they actually serve — never written down here.

    ``build_slate`` stamps a whole draw ceremony with one value: 96 of the 124
    US Open matchups carry ``2026-08-30T04:00:00+00:00``. That single instant is
    what both ends of the register's relevance window are measured from, so it
    is the only honest origin for this file's clock. Reading it back out of the
    register means a re-generated register moves the tests with it instead of
    silently ageing them out.
    """
    season = REGISTERED_TOURNAMENTS[SLUG]["season"]
    stamps = Counter(
        m.get("scheduled_date")
        for m in (load_register(SLUG, season).get("matchups") or [])
        if m.get("scheduled_date")
    )
    assert stamps, (
        f"the {SLUG} register carries no scheduled dates, so this file has no "
        "anchor to derive — every test below would be measuring an empty draw"
    )
    raw, _ = stamps.most_common(1)[0]
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


#: The instant every test in this file is served at: a day into the draw the
#: register describes.
#:
#: ⏰ THIS FILE USED TO READ THE WALL CLOCK AND IT WAS A BOMB ON A FUSE (#7464).
#: The register is a committed file with real dates in it; ``now`` was the real
#: ``datetime.now``. The gap between them therefore grew by a day every day, and
#: at ``ceremony + 21d + 6h`` — 2026-09-20T10:00:00Z, to the minute — it crossed
#: the far end of the register's relevance window and the positive control below
#: went red on master with no diff at all. One sha measured twice: green at
#: 09:26Z, red at 10:25Z. It blocked every lane's merge, because a PR's CI runs
#: on the merge ref and inherits master's red.
#:
#: Gotcha #44, in its purest form: OFFSET FIRST, THEN TRUNCATE. The anchor is an
#: offset from the fixture's own stamp, so the distance under test is fixed
#: forever and no hour of any day can change a verdict here.
#:
#: 24 hours in, and the choice is load-bearing in both directions —
#: ``test_the_anchor_exercises_the_exemption_it_claims_to`` is the guard that
#: says so. It must be past ``MATCH_STALE_AFTER_HOURS`` or the control would
#: never enter the clock's branch and would pass for a reason it does not claim,
#: and well inside ``CEREMONY_STAMP_COVERS_THE_TOURNAMENT_HOURS`` or the draw is
#: retired as a finished tournament, which is the red this repairs.
A_DAY_INTO_THE_DRAW = _ceremony_stamp() + timedelta(hours=24)


class _TheRegistersClock(datetime):
    """``datetime`` with ``now`` pinned, and every other classmethod intact.

    A subclass rather than a stub on purpose: the route parses stamps with
    ``fromisoformat`` and builds windows with ``timedelta`` off the same name,
    and a bare fake would break those instead of freezing them.
    """

    @classmethod
    def now(cls, tz=None):  # noqa: D102 - stdlib signature
        return A_DAY_INTO_THE_DRAW if tz else A_DAY_INTO_THE_DRAW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _served_a_day_into_the_draw(monkeypatch):
    """Every request below is served at :data:`A_DAY_INTO_THE_DRAW`."""
    monkeypatch.setattr(tournaments, "datetime", _TheRegistersClock)


def test_the_anchor_exercises_the_exemption_it_claims_to():
    """The draw is in the clock's reach at the anchor, and survives it anyway.

    The control below is only worth its name if the rows it counts are rows the
    clock had an OPINION about. Two ways to lose that, and neither shows up as a
    red anywhere else in this file:

    * Drag the anchor back under ``MATCH_STALE_AFTER_HOURS`` and every test
      still passes — the fixtures are merely upcoming, the clock never reaches
      them, and the control has quietly stopped proving that a pinned fixture
      survives retirement, which is the one thing it exists for.
    * Push it past the far end and the control goes red, which is #7464.

    So this is measured over the register's OWN rows rather than against
    :func:`_ceremony_stamp`. Asserting elapsed hours against that function
    instead was the first draft, and a mutant killed it: change the derivation
    to take the earliest fixture rather than the ceremony's own stamp and the
    anchor moves with the thing measuring it, so the check reads "24h" and
    passes while the whole main draw has slid into the future. A guard may not
    key its verification on the same value it is verifying.
    """
    starts = _registered_starts()
    #: Asserted with slack on both sides, because an anchor that satisfies this
    #: exactly on a bound is the same bomb with a shorter fuse: #7464 was green
    #: at one bound and red an hour later. A margin as wide as the staleness
    #: bound itself is the smallest one that cannot be reached by rounding.
    margin = timedelta(hours=MATCH_STALE_AFTER_HOURS)

    for jitter in (-margin, timedelta(0), margin):
        at = A_DAY_INTO_THE_DRAW + jitter
        cutoff = at - timedelta(hours=MATCH_STALE_AFTER_HOURS)
        far_end = cutoff - timedelta(hours=CEREMONY_STAMP_COVERS_THE_TOURNAMENT_HOURS)

        in_reach = [s for s in starts if far_end <= s < cutoff]
        assert len(in_reach) >= PRODUCTION_DEFECT_COUNT, (
            f"only {len(in_reach)} of {len(starts)} registered fixtures are "
            f"inside the clock's reach at {at.isoformat()} (cutoff "
            f"{cutoff.isoformat()}, far end {far_end.isoformat()}, jitter "
            f"{jitter}) — fewer than the {PRODUCTION_DEFECT_COUNT} the control "
            "counts, so it is passing on fixtures the clock never had an "
            "opinion about, or it is sitting on a bound"
        )


def _espn(scoreboard):
    async def _result(slug):
        return {
            "draws": {}, "stats": {}, "errors": [], "scoreboard": scoreboard,
        }

    return _result


@pytest.fixture(autouse=True)
def _cold(monkeypatch):
    """Never answered by a cache another test warmed; never writing to one."""

    async def _miss(slug, group=tournaments.SECTION_FIRST):
        return None

    async def _noop(slug, payload, group=tournaments.SECTION_FIRST):
        return None

    monkeypatch.setattr(tournaments, "_cache_get", _miss)
    monkeypatch.setattr(tournaments, "_cache_set", _noop)


class TestTheReaderNeverSeesTheOpeningRound:
    async def test_a_raised_scoreboard_read_withholds_the_card(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(
            tournaments, "_espn_results", _espn(tournaments.SCOREBOARD_DEGRADED)
        )
        body = (await client.get(URL)).json()
        slate = body["slate"]

        assert slate["matches"] == []
        assert slate["count"] == 0
        assert slate["count"] != PRODUCTION_DEFECT_COUNT
        assert slate["withheld_reason"] == "scoreboard_read_failed"
        assert slate["scoreboard"] == tournaments.SCOREBOARD_DEGRADED

    async def test_the_rest_of_the_page_still_renders(self, client, monkeypatch):
        """Withholding the card is not 503-ing the tournament.

        Results, grids and boards come from our own database and were never in
        doubt. At 20:21Z production still had all 590 results while the card was
        wrong — emptying the whole page would be a worse answer than the bug.
        """
        monkeypatch.setattr(
            tournaments, "_espn_results", _espn(tournaments.SCOREBOARD_DEGRADED)
        )
        resp = await client.get(URL)

        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] and body["boards"]
        assert "results" in body and "grids" in body

    async def test_THE_CONTROL_a_merely_absent_scoreboard_still_gets_the_card(
        self, client, monkeypatch
    ):
        """The positive control, and without it the test above proves nothing.

        A quiet day must keep #3304's behaviour: the register fallback is the
        right answer when we KNOW there is nothing on, and the whole point of
        #5728 is that the two cases stopped sharing a word. If this ever goes
        red the fix has over-fired and is emptying real cards.
        """
        monkeypatch.setattr(
            tournaments, "_espn_results", _espn("unavailable")
        )
        slate = (await client.get(URL)).json()["slate"]

        assert slate["matches"], "the register fallback was suppressed too"
        assert "withheld_reason" not in slate


class _FakeRedis:
    """A client that drops the LINK key and answers every other key normally.

    Keyed on the prefix on purpose. A fake that failed every `get` would make
    the whole request degrade for reasons other than the overlay, and the test
    resting on it would be green for the wrong one — the failure mode this
    whole ship is about.
    """

    def __init__(self, fail_links: bool):
        self._fail_links = fail_links
        self.asked: list[str] = []
        self.link_reads = 0

    async def get(self, key):
        self.asked.append(key)
        if key.startswith(LINKS_PREFIX):
            self.link_reads += 1
            if self._fail_links:
                raise RuntimeError("redis connection dropped")
        return None  # every key is a clean miss


class _LinkOverlayRig:
    """Shared scaffolding: a healthy scoreboard, and a Redis we can break.

    There is no Redis on a test box, so `_espn_results` raises here and the
    build is degraded before the overlay is even reached — which would make
    every test below pass for the wrong reason and the controls impossible. It
    is pinned to the clean-miss shape, leaving the overlay as the only thing
    under test.
    """

    @pytest.fixture(autouse=True)
    def _scoreboard_is_fine(self, monkeypatch):
        monkeypatch.setattr(tournaments, "_espn_results", _espn("unavailable"))

    @staticmethod
    def _install_redis(monkeypatch, *, fail_links: bool) -> _FakeRedis:
        """Inject beneath the real `read_links`, never in place of it."""
        from app.tasks import redis_state

        fake = _FakeRedis(fail_links=fail_links)
        monkeypatch.setattr(
            redis_state, "get_async_redis_client", lambda *a, **k: fake
        )
        return fake


class TestADegradedBuildDoesNotOutliveItsRequest(_LinkOverlayRig):
    """These are about the LINK overlay, so the scoreboard must be healthy.

    The RAISE path. `read_links` does not raise on a dead Redis — that is
    CERT-2766's finding and `TestTheRealAccessorFailing` below is where the
    production path is proven — but `apply_resolved_links` beneath it is real
    work over a payload another process wrote, so the raise path is reachable
    and still has to refuse the cache.
    """

    async def test_a_raising_link_overlay_stops_the_cache_write(
        self, client, monkeypatch
    ):
        """The 20:21:05Z event, end to end.

        The overlay failing is enough on its own: the scoreboard was fine, the
        slate was right, and the payload still carried `blend_linked: 0` with
        `incoherent: 2` over two rows both reporting `coherent: true`. It was
        written to the 60s cache and served to five readers.
        """
        written = {}

        async def _set(slug, payload, group=tournaments.SECTION_FIRST):
            written[group] = payload

        async def _boom(slug):
            raise RuntimeError("redis down")

        monkeypatch.setattr(tournaments, "_cache_set", _set)
        monkeypatch.setattr(tournaments, "read_links", _boom)

        assert (await client.get(URL)).status_code == 200
        assert not written, "a payload built without the overlay was cached"

    async def test_THE_CONTROL_a_healthy_build_is_cached(self, client, monkeypatch):
        """Same route, same call, overlay working. Without this the test above
        passes on a route that simply stopped caching.

        🔴 THIS CONTROL USED TO PASS BY THE DEFECT (CERT-2766). It installed no
        Redis, so on a test box the link read hit a refused connection — and
        because `read_links` returned the clean-miss bytes for a failure, the
        route could not tell, cached the page, and the control went green
        calling it "healthy". It was asserting the bug. The fake is now
        explicit: the key is ABSENT, which is a real healthy build.
        """
        written = {}

        async def _set(slug, payload, group=tournaments.SECTION_FIRST):
            written[group] = payload

        monkeypatch.setattr(tournaments, "_cache_set", _set)
        self._install_redis(monkeypatch, fail_links=False)

        assert (await client.get(URL)).status_code == 200
        assert written, "a healthy build stopped being cached"


class TestTheRealAccessorFailing(_LinkOverlayRig):
    """CERT-2766. The test above stubs `read_links` to RAISE; it does not.

    That is the whole finding. The real accessor catches its own Redis
    exception and returns `{"links": {}}` — the same bytes as a cold cache — so
    the route's `except` was dead on the only path production takes: the ledger
    stayed empty and the incomplete page was cached and served for the TTL.

    So these fail the Redis dependency BENEATH the real `read_links`, and the
    route's own wiring is what is under test. Nothing here stubs the accessor.
    """

    async def test_real_link_accessor_failure_must_not_cache_5728(
        self, client, monkeypatch
    ):
        written = {}

        async def _set(slug, payload, group=tournaments.SECTION_FIRST):
            written[group] = payload

        monkeypatch.setattr(tournaments, "_cache_set", _set)
        fake = self._install_redis(monkeypatch, fail_links=True)

        assert (await client.get(URL)).status_code == 200

        # Vacuity guard FIRST. If the overlay key was never read — an import
        # moved, the route short-circuited — then `not written` below would be
        # green while proving nothing at all.
        assert fake.link_reads == 1, (
            f"the real accessor never read the overlay key (asked: {fake.asked}); "
            "this test would otherwise pass vacuously"
        )
        assert not written, (
            "a page built on a FAILED link read was written to the cache — this "
            "is the 20:21:05Z event, five readers on one `generated_at`"
        )

    async def test_THE_CONTROL_a_clean_absence_still_caches(
        self, client, monkeypatch
    ):
        """The same rig with the key merely ABSENT, which must still cache.

        Without this the test above passes on a route that stopped caching, or
        on a rig whose fake Redis broke every read. A cold cache is the ordinary
        state of this key and it may never cost the reader a cached page.
        """
        written = {}

        async def _set(slug, payload, group=tournaments.SECTION_FIRST):
            written[group] = payload

        monkeypatch.setattr(tournaments, "_cache_set", _set)
        fake = self._install_redis(monkeypatch, fail_links=False)

        assert (await client.get(URL)).status_code == 200
        assert fake.link_reads == 1, "the control did not exercise the same path"
        assert written, "a clean absence stopped being cached — the fix over-fired"

    async def test_the_accessor_reports_its_own_verdict(self, monkeypatch):
        """The contract the two tests above rest on, asserted directly.

        Both outcomes still return a usable `{"links": {}}` — the overlay is
        never a gate and this still never raises — but they no longer return
        the SAME thing.
        """
        from app.tasks.tournament_matchup_linker import LINKS_DEGRADED, read_links

        self._install_redis(monkeypatch, fail_links=True)
        failed = await read_links(SLUG)
        assert failed[LINKS_DEGRADED] is True
        assert failed["links"] == {}

        self._install_redis(monkeypatch, fail_links=False)
        absent = await read_links(SLUG)
        assert absent[LINKS_DEGRADED] is False
        assert absent["links"] == {}
