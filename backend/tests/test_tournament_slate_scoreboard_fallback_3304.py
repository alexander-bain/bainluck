"""#3304 — an absent scoreboard must not print the whole draw as the day's card.

MEASURED ON PRODUCTION, 2026-09-05 19:04Z, US Open finals weekend
(`.claude/handoff/ARTIFACT-M-R-USOPEN-20260905-19.md`): one sample of
`/api/tournaments/us-open` returned **96 slate rows, 0 in progress, 0 results**
with 12.2h-old prices. Samples at 19:25Z and 19:32Z were healthy — 22/5/1 and
21/4/1 — so the page had briefly replaced today's order of play with the entire
decided main draw, presented as what was on.

THE CHAIN, and every link of it is load-bearing:

1. `sync_tournament_results` writes `bainluck:tournament-results:us-open` on a
   3-minute beat with a 900s TTL. Five missed runs — or an eviction from the
   shared LRU Redis — and the key is gone.
2. `_espn_results` returned `{"draws": {}, "stats": {}, "errors": []}` on a
   miss, **byte-identical to a successful fetch on a day with no tennis**. That
   is gotcha #53: an empty 200 is a response shape, not an absence.
3. `build_slate` therefore saw `order_of_play={}`. Its only route to `DECIDED`
   requires the scoreboard to NAME the fixture (`tournament_slate.py`, "ESPN
   SAYS SO, IN A WORD"), so an empty map can retire nothing.
4. Pinned main-draw fixtures are exempt from the clock rule inside the ceremony
   window (CERT-544). All 96 of them printed.

CERT-544 chose "a stale row is a smaller lie than a draw that vanishes", and
that is right for a PER-MATCH ambiguity on a working scoreboard. It was never
argued for a TOTAL outage. CERT-532 had already named the class in prose — "a
consumer reading ABSENCE from the map as a fact about the match" — and this is
its largest instance.

THE FIX CHANGES NO PER-MATCH RULE. `build_slate` is untouched, so no CERT-517 /
532 / 544 / 548 precedent moves. The scoreboard simply gets an hour-long shadow
copy, so a blip costs an hour-old answer to "who is on" instead of the collapse
of the question. Prices are unaffected either way — they come from our own
database and never from this key.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.routes.tournaments import (
    RESULTS_LAST_GOOD_PREFIX,
    RESULTS_PREFIX,
    _espn_results,
)
from app.tasks.tournament_price_refresh import (
    RESULTS_LAST_GOOD_TTL_SECONDS,
    RESULTS_TTL_SECONDS,
    _is_last_good,
    _sync_tournament_results,
)
from app.utils.tournament_register import TournamentRegister, load_register
from app.utils.tournament_slate import build_slate, espn_competition_id

#: Inside the US Open's ceremony window, which is what makes the pinned-fixture
#: exemption live. A `now` outside it would retire the draw by the far-end clock
#: and the bug could not reproduce — the test would pass for the wrong reason.
NOW = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)

#: How many of the register's 96 pinned fixtures the synthetic scoreboard leaves
#: on court. Four is what production actually had at 19:32Z.
LIVE_FIXTURES = 4


def _register() -> dict:
    raw = load_register("us-open", "2026")
    assert raw, "the us-open 2026 register must be loadable — the whole file needs it"
    return raw


def _pinned_ids(raw: dict) -> list[str]:
    ids = [espn_competition_id(m) for m in TournamentRegister(raw).matchups]
    return [i for i in ids if i]


def _scoreboard(raw: dict, *, live: int = LIVE_FIXTURES) -> dict[str, dict]:
    """A healthy order-of-play map: everything decided but the last few.

    Minimal on purpose. `pairing_agrees` reads a missing competitor list as
    silence and returns True, so a bare `state` is enough to exercise the one
    branch this file is about — which fixtures the scoreboard retires.
    """
    ids = _pinned_ids(raw)
    assert len(ids) > live, "need more pinned fixtures than live ones to have a card"
    decided, on_court = ids[:-live], ids[-live:]
    listed: dict[str, dict] = {i: {"state": "decided"} for i in decided}
    listed.update(
        {
            i: {
                "state": "in_progress",
                "start_at": (NOW - timedelta(hours=1)).isoformat(),
            }
            for i in on_court
        }
    )
    return listed


class _Redis:
    """A Redis whose contents the test states outright, with per-key TTLs kept."""

    def __init__(self, contents: dict[str, str] | None = None):
        self.contents = dict(contents or {})
        self.writes: list[tuple[str, int, str]] = []
        self.get_raises: Exception | None = None

    async def get(self, key):
        if self.get_raises is not None:
            raise self.get_raises
        return self.contents.get(key)

    async def setex(self, key, ttl, value):
        self.writes.append((key, ttl, value))
        self.contents[key] = value
        return True


@pytest.fixture
def redis(monkeypatch):
    import app.tasks.redis_state as redis_state

    client = _Redis()
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: client)
    return client


class TestTheDefectItself:
    """The 96 rows, pinned. This asserts UNCHANGED `build_slate` behaviour — it
    is the thing the fallback exists to keep out of reach, not a thing the fix
    repairs. If a later change makes an empty map harmless on its own, this test
    is the one that should be deleted, deliberately, with that change."""

    def test_an_empty_scoreboard_prints_the_whole_decided_draw(self):
        raw = _register()
        slate = build_slate(
            raw, prices={}, now=NOW, order_of_play={}, order_of_play_complete=False
        )

        # The measured shape: every pinned fixture on the card, nobody playing.
        assert slate["count"] == len(_pinned_ids(raw)) == 96
        assert slate["in_progress"] == 0
        assert slate["order_of_play_listed"] == 0
        # And not one of them retired as decided, which is the mechanism.
        assert "DECIDED" not in slate["dropped"]

    def test_the_same_register_and_clock_print_a_day_card_with_a_scoreboard(self):
        """The control. Same register, same `now` — only the map differs, so the
        96 above is attributable to the empty map and to nothing else."""
        raw = _register()
        slate = build_slate(
            raw,
            prices={},
            now=NOW,
            order_of_play=_scoreboard(raw),
            order_of_play_complete=True,
        )

        assert slate["count"] == LIVE_FIXTURES
        assert slate["in_progress"] == LIVE_FIXTURES
        assert slate["dropped"]["DECIDED"] == 96 - LIVE_FIXTURES


class TestOnlyAScoreboardWorthKeepingBecomesTheFallback:
    """A partial read written for fifteen minutes is a caveat. The same read
    kept for an hour is a lie about a whole tour."""

    def test_a_clean_complete_read_qualifies(self):
        assert _is_last_good(
            {"order_of_play": {"1": {"state": "decided"}}, "order_of_play_complete": True}
        )

    def test_a_partial_read_never_qualifies(self):
        """`order_of_play_complete` is False exactly when a tour failed — and the
        tour it failed on could be the one with the women's final on it."""
        assert not _is_last_good(
            {
                "order_of_play": {"1": {"state": "decided"}},
                "order_of_play_complete": False,
            }
        )

    def test_an_empty_map_never_qualifies_however_complete_the_request(self):
        """Completeness is a fact about the REQUEST, emptiness about the ANSWER
        (CERT-548 draws that line for the slate; it holds here). Storing an empty
        map as the last good one would preserve the defect for an hour instead of
        preventing it for an hour."""
        assert not _is_last_good({"order_of_play": {}, "order_of_play_complete": True})

    def test_a_payload_from_before_this_shipped_never_qualifies(self):
        assert not _is_last_good({"draws": {}, "stats": {}, "errors": []})


class TestTheWriter:
    @staticmethod
    def _arm(monkeypatch, results):
        import app.services.espn_tennis as espn

        async def _fetch(event_name):
            return results

        monkeypatch.setattr(espn, "fetch_tournament_results", _fetch)

    async def test_a_clean_read_writes_both_slots_with_their_own_ttls(
        self, monkeypatch, redis
    ):
        results = {
            "draws": {},
            "errors": [],
            "order_of_play": {"182655": {"state": "decided"}},
            "order_of_play_complete": True,
        }
        self._arm(monkeypatch, results)

        stats = await _sync_tournament_results([("us-open", "US Open")])

        assert stats["terminal"] == "complete"
        assert stats["written"] == 1
        assert stats["last_good_written"] == 1

        by_key = {key: (ttl, value) for key, ttl, value in redis.writes}
        assert by_key[f"{RESULTS_PREFIX}us-open"][0] == RESULTS_TTL_SECONDS
        assert (
            by_key[f"{RESULTS_LAST_GOOD_PREFIX}us-open"][0]
            == RESULTS_LAST_GOOD_TTL_SECONDS
        )
        # The fallback must outlive the key it shadows, or it can never be read.
        assert RESULTS_LAST_GOOD_TTL_SECONDS > RESULTS_TTL_SECONDS
        # Same bytes in both, so the two slots can never disagree about a match.
        assert (
            by_key[f"{RESULTS_PREFIX}us-open"][1]
            == by_key[f"{RESULTS_LAST_GOOD_PREFIX}us-open"][1]
        )

    async def test_a_partial_read_writes_the_primary_only(self, monkeypatch, redis):
        """Still written — half the tours beats none for fifteen minutes, and
        that behaviour is unchanged. It just does not become the hour-long copy."""
        self._arm(
            monkeypatch,
            {
                "draws": {},
                "errors": ["womens scoreboard 500"],
                "order_of_play": {"182655": {"state": "decided"}},
                "order_of_play_complete": False,
            },
        )

        stats = await _sync_tournament_results([("us-open", "US Open")])

        assert stats["written"] == 1
        assert "last_good_written" not in stats
        written = [key for key, _, _ in redis.writes]
        assert written == [f"{RESULTS_PREFIX}us-open"]

    async def test_a_stale_fallback_is_not_refreshed_by_a_partial_read(
        self, monkeypatch, redis
    ):
        """The hour is measured from the last read we trusted, never from the
        last read we made. A partial fetch every three minutes must not hold a
        dead scoreboard alive indefinitely by touching its TTL."""
        redis.contents[f"{RESULTS_LAST_GOOD_PREFIX}us-open"] = json.dumps(
            {"order_of_play": {"182655": {"state": "decided"}}}
        )
        self._arm(
            monkeypatch,
            {"draws": {}, "errors": ["both tours 500"], "order_of_play_complete": False},
        )

        await _sync_tournament_results([("us-open", "US Open")])

        assert all(
            key != f"{RESULTS_LAST_GOOD_PREFIX}us-open" for key, _, _ in redis.writes
        )


class TestTheReader:
    async def test_the_primary_wins_and_the_fallback_is_not_consulted(self, redis):
        redis.contents[f"{RESULTS_PREFIX}us-open"] = json.dumps({"draws": {"a": 1}})
        redis.contents[f"{RESULTS_LAST_GOOD_PREFIX}us-open"] = json.dumps(
            {"draws": {"b": 2}}
        )

        payload = await _espn_results("us-open")

        assert payload["draws"] == {"a": 1}
        assert payload["scoreboard"] == "live"

    async def test_a_missing_primary_falls_back_and_says_so(self, redis):
        redis.contents[f"{RESULTS_LAST_GOOD_PREFIX}us-open"] = json.dumps(
            {"draws": {"b": 2}, "order_of_play": {"182655": {"state": "decided"}}}
        )

        payload = await _espn_results("us-open")

        assert payload["order_of_play"] == {"182655": {"state": "decided"}}
        assert payload["scoreboard"] == "last_good"

    async def test_neither_slot_is_the_old_behaviour_named(self, redis):
        """No regression for a sustained outage — the shape is what it always
        was. It just no longer reads the same as a quiet day."""
        payload = await _espn_results("us-open")

        assert payload["draws"] == {}
        assert payload["errors"] == []
        assert payload["scoreboard"] == "unavailable"

    async def test_a_corrupt_slot_is_a_miss_and_not_a_500(self, redis):
        redis.contents[f"{RESULTS_PREFIX}us-open"] = "{not json"
        redis.contents[f"{RESULTS_LAST_GOOD_PREFIX}us-open"] = json.dumps(
            {"order_of_play": {"182655": {"state": "decided"}}}
        )

        payload = await _espn_results("us-open")

        assert payload["scoreboard"] == "last_good"

    async def test_a_dead_redis_still_serves_the_page(self, redis):
        redis.get_raises = RuntimeError("redis down")

        payload = await _espn_results("us-open")

        assert payload["scoreboard"] == "unavailable"


class TestTheShip:
    """End to end, on the real register: the primary key is gone and the card is
    still today's card."""

    async def test_the_card_survives_the_primary_key_expiring(self, redis):
        raw = _register()
        redis.contents[f"{RESULTS_LAST_GOOD_PREFIX}us-open"] = json.dumps(
            {
                "draws": {},
                "errors": [],
                "order_of_play": _scoreboard(raw),
                "order_of_play_complete": True,
            }
        )

        espn = await _espn_results("us-open")
        slate = build_slate(
            raw,
            prices={},
            now=NOW,
            order_of_play=espn.get("order_of_play") or {},
            order_of_play_complete=espn.get("order_of_play_complete") is True,
        )

        # The ship, stated as the number that was wrong on production.
        assert slate["count"] == LIVE_FIXTURES
        assert slate["count"] != 96
        assert slate["in_progress"] == LIVE_FIXTURES
        assert slate["dropped"]["DECIDED"] == 96 - LIVE_FIXTURES

    async def test_without_the_fallback_the_same_read_prints_96(self, redis):
        """The positive control for the test above. Same register, same clock,
        same call path — only the fallback slot is missing, and the defect is
        back. Without this, `test_the_card_survives...` would still pass if the
        fallback were never read at all."""
        raw = _register()

        espn = await _espn_results("us-open")
        slate = build_slate(
            raw,
            prices={},
            now=NOW,
            order_of_play=espn.get("order_of_play") or {},
            order_of_play_complete=espn.get("order_of_play_complete") is True,
        )

        assert espn["scoreboard"] == "unavailable"
        assert slate["count"] == 96
