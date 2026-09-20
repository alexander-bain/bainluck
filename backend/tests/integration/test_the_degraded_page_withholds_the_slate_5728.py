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

from datetime import datetime, timedelta, timezone

import pytest

from app.routes import tournaments
from app.tasks.tournament_matchup_linker import LINKS_PREFIX

SLUG = "us-open"
URL = f"/api/tournaments/{SLUG}"

#: What production served at 19:51:18Z on 2026-09-12. Named because a test that
#: asserts "not 96" against a slate that happens to be empty for some other
#: reason is not asserting anything.
PRODUCTION_DEFECT_COUNT = 96

#: How long before the request the re-anchored ceremony stamp is placed (#7464).
#:
#: `build_slate` retires a pinned fixture on
#: ``started < now - MATCH_STALE_AFTER_HOURS - CEREMONY_STAMP_COVERS_THE_TOURNAMENT_HOURS``
#: — 6h + 24×21h = **510h**. One day leaves ~20 days of margin at the far wall
#: and 18 hours at the near one, so neither is reachable by any clock jitter
#: between this fixture's `now` and the route's, which are milliseconds apart.
CEREMONY_STAMP_AGE = timedelta(days=1)


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


def _reanchored(register: dict) -> dict:
    """The committed register with every ``scheduled_date`` shifted as one.

    Rigidly, by a single delta, so the draw keeps its own shape — qualifiers
    still fall before the main draw, and the 96 main-draw fixtures still share
    the one ceremony instant that `tournament_slate` is written around. Only
    the tournament's position on the calendar moves.
    """
    stamps = {
        m["scheduled_date"]: datetime.fromisoformat(m["scheduled_date"])
        for m in register.get("matchups") or []
        if isinstance(m, dict) and isinstance(m.get("scheduled_date"), str)
    }
    if not stamps:
        # LOUD, never a silent no-op. A register this fixture cannot re-anchor
        # is one every test below would then measure against the wall clock,
        # which is the entire defect it exists to remove.
        raise AssertionError(
            f"{SLUG}: no datable matchup to re-anchor — the rig would silently "
            "hand the clock back to the tests it is meant to protect"
        )
    delta = (datetime.now(timezone.utc) - CEREMONY_STAMP_AGE) - max(stamps.values())
    shifted = {raw: (parsed + delta).isoformat() for raw, parsed in stamps.items()}
    return {
        **register,
        "matchups": [
            {**m, "scheduled_date": shifted[m["scheduled_date"]]}
            if isinstance(m, dict) and m.get("scheduled_date") in shifted
            else m
            for m in register.get("matchups") or []
        ],
    }


@pytest.fixture(autouse=True)
def _register_anchored_to_the_request(monkeypatch):
    """#7464: the committed register expires, so the CLOCK must not be an input.

    🔴 THE BOMB THIS DEFUSES, MEASURED. `us-open-2026.json` pins all 96
    main-draw fixtures at the single ceremony stamp ``2026-08-30T04:00:00Z``,
    and `build_slate` retires a pinned fixture 510 hours after it. The register
    fallback therefore yielded **96 rows at 2026-09-20T09:59:00Z and 0 at
    10:00:01Z** — and master's CI was green on `13a23384a` at 09:26:30Z and red
    on `288cb1140` at 10:00:12Z, twelve seconds the wrong side of that wall.
    Gotcha #44: the anchor was absolute while the rule it met was relative.

    ⭐ AND THE RED WAS HIDING A LIVE REGRESSION CHANNEL, measured. With the
    register retired, `test_a_raised_scoreboard_read_withholds_the_card`
    asserted `matches == []`, `count == 0` and `count != 96` against a slate
    that was empty regardless — three of its five assertions vacuous. Its
    `withheld_reason` pair still bit, so it is not that the arm proved nothing;
    it is that it stopped proving the thing this file is named for. Stop
    `_withheld_slate` emptying the rows while it still stamps the reason — the
    #5728 defect exactly, the reader back on the fortnight-old opening round —
    and the repaired file fails THIS arm, while the retired-register file
    passes it and fails only the control, for the clock reason it was failing
    for already. A genuine regression would have arrived looking like the red
    that was on the board anyway.

    The product rule is CORRECT and does not move: a tournament that ended
    three weeks ago *should* fall off "what's on". Only the fixture is wrong,
    so only the fixture is repaired — offset FIRST, from the request's own now.
    """
    real = tournaments.load_register

    def _anchored(tournament, season, **kwargs):
        register = real(tournament, season, **kwargs)
        return register if register is None else _reanchored(register)

    monkeypatch.setattr(tournaments, "load_register", _anchored)


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

        The count is pinned, not merely non-empty (#7464). This arm's job is to
        keep the `!= PRODUCTION_DEFECT_COUNT` above honest, and it can only do
        that by proving the fallback puts all 96 back on the page — "some rows"
        would let the draw quietly shrink to one and still read green.
        """
        monkeypatch.setattr(
            tournaments, "_espn_results", _espn("unavailable")
        )
        slate = (await client.get(URL)).json()["slate"]

        assert slate["matches"], "the register fallback was suppressed too"
        assert slate["count"] == PRODUCTION_DEFECT_COUNT, (
            f"the fallback served {slate['count']} of {PRODUCTION_DEFECT_COUNT} "
            "main-draw rows — the test above is now asserting against a number "
            "no path produces"
        )
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
