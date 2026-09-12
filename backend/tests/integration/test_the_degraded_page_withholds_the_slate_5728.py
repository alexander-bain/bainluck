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


class TestADegradedBuildDoesNotOutliveItsRequest:
    """These are about the LINK overlay, so the scoreboard must be healthy.

    There is no Redis on a test box, so `_espn_results` raises here and the
    build is degraded before the overlay is even reached — which would make
    both tests below pass for the wrong reason and the control impossible. It
    is pinned to the clean-miss shape (keys absent, Redis answering), leaving
    the overlay as the only thing under test.
    """

    @pytest.fixture(autouse=True)
    def _scoreboard_is_fine(self, monkeypatch):
        monkeypatch.setattr(tournaments, "_espn_results", _espn("unavailable"))

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
        passes on a route that simply stopped caching."""
        written = {}

        async def _set(slug, payload, group=tournaments.SECTION_FIRST):
            written[group] = payload

        monkeypatch.setattr(tournaments, "_cache_set", _set)

        assert (await client.get(URL)).status_code == 200
        assert written, "a healthy build stopped being cached"
