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

import pytest

from app.routes import tournaments
from app.tasks.tournament_matchup_linker import LINKS_PREFIX

SLUG = "us-open"
URL = f"/api/tournaments/{SLUG}"

#: What production served at 19:51:18Z on 2026-09-12. Named because a test that
#: asserts "not 96" against a slate that happens to be empty for some other
#: reason is not asserting anything.
PRODUCTION_DEFECT_COUNT = 96


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
