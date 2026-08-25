"""#1948 — the warm envelope contained the leader and the feed still shipped no leader.

THE SEAM, AND WHY THREE CYCLES OF UNIT TESTS COULD NOT SEE IT.

Every component on this path had its own green suite. The warmer built 21 of 21
keys with zero errors. The served and warmed populations were identical. The
envelope for `event:cycling:vuelta-2026` carried thirty riders with Pogacar at
0.751. `_resolve_concept_leader` picks the max of a competitor list and has
seventeen tests proving it. And `GET /api/feed` returned sixteen concept cards
with **zero** leaders, three cycles running.

The defect was between two of those green components, in a fact neither of them
holds on its own: **one producer writes two Redis slots and the consumer read
only the short-lived one.** `write_payload` writes the primary at
`ENVELOPE_TTL` = 60s and a 24h mirror; `_read_cached_concept_envelope` read
`f"{CACHE_PREFIX}{key}"`, which is the primary and nothing else.

Photographed on production 2026-08-18, twenty-one seconds apart, same bytes and
the same `created_at` in both reads:

    19:18:13  detail `availability: live`      GET /api/feed -> 4/4 leaders
    19:18:34  detail `availability: stale_ok`  GET /api/feed -> 0/4 leaders

`warm_event_concepts` logged 112 successes in 24h, each leaving a 60-second
primary behind it, so the slot the feed read was alive for about **8% of the
day**. Every probe in cycles 89, 90 and 91 landed in the other 92%.

WHAT THIS FILE DOES DIFFERENTLY FROM `test_feed_concept_leader.py`. That suite's
fixture is key-agnostic: it stubs `bounded_redis_call` to hand back one canned
payload whatever key is asked for, so no test in it could ever observe WHICH slot
the reader addresses. It is the right shape for "pick the favourite out of this
list" and the wrong shape for a seam. So here:

  * the envelope is written by the REAL producer (`write_payload` +
    `cache_keys` + `stamp_envelope`) into a key-addressed fake Redis that
    honours TTLs, so the slot NAMES are production's, not the test's;
  * `bounded_redis_call` is NOT stubbed — the real one runs, which closes the
    third candidate on cycle 91's shortlist (`not is_ok` under the request path);
  * the entry point is `_score_event_concepts`, the feed's own card builder, so
    the call site, the whathit exclusivity gate, the resolver and the read are
    all on the wire together. Only the DB enumeration is stubbed.

Drive it end to end, expire the primary the way Redis does, and the card must
still lead with Pogacar.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

import app.routes.feed as feed_mod
from app.routes.feed import _resolve_concept_leader, _score_event_concepts
from app.utils.event_concept_cache import (
    ENVELOPE_TTL,
    STALE_TTL,
    cache_keys,
    stamp_envelope,
    write_payload,
)

CONCEPT_KEY = "event:cycling:vuelta-2026"

#: Verbatim from the production envelope cycle 91 read out of the warm cache —
#: `primary.competitors`, 30 riders, favourite-first. Trimmed to the head of the
#: field; the point is the shape and the number, not the length.
VUELTA_COMPETITORS = [
    {"name": "Tadej Pogacar", "probability": 0.751},
    {"name": "Jonas Vingegaard", "probability": 0.121},
    {"name": "Primoz Roglic", "probability": 0.049},
    {"name": "Juan Ayuso", "probability": 0.021},
]


class _FakeRedis:
    """Key-addressed, TTL-honouring, on a clock the test owns.

    Only the four methods the production write path actually calls. A key whose
    TTL has elapsed is GONE, which is the entire subject of this file — a fake
    that ignores TTLs would reproduce the bug's invisibility rather than the bug.
    """

    def __init__(self):
        self.now = 0.0
        self._store: dict[str, tuple[str, float | None]] = {}

    # -- clock ------------------------------------------------------------
    def advance(self, seconds: float) -> None:
        self.now += seconds

    # -- sync surface used by `write_payload` -----------------------------
    def setex(self, key, ttl, value):
        self._store[key] = (value, self.now + ttl)

    def delete(self, key):
        self._store.pop(key, None)

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and self.now >= expires_at:
            del self._store[key]
            return None
        return value

    def live_keys(self):
        return sorted(k for k in list(self._store) if self.get(k) is not None)


class _AsyncView:
    """What `get_shared_async_redis()` hands the reader."""

    def __init__(self, fake: _FakeRedis):
        self._fake = fake
        self.mget_calls: list[list[str]] = []

    async def mget(self, keys):
        self.mget_calls.append(list(keys))
        return [self._fake.get(k) for k in keys]

    async def get(self, key):
        return self._fake.get(key)


@pytest.fixture
def warm_cache(monkeypatch):
    """A real producer write into a real key-addressed store, wired to the reader."""
    import app.utils.request_cache as rc

    fake = _FakeRedis()
    view = _AsyncView(fake)

    async def _shared():
        return view

    monkeypatch.setattr(rc, "get_shared_async_redis", _shared)
    # `bounded_redis_call` is deliberately NOT patched.
    return fake, view


def _warm(fake: _FakeRedis, *, key=CONCEPT_KEY, age_seconds=30.0, competitors=None):
    """Write one concept envelope exactly the way the warmer writes it.

    `age_seconds` is an OFFSET from the real clock, never a pinned hour
    (gotcha #44) — the mirror tier is age-bounded, so a fixture that pinned a
    date would decide its own verdict differently every day it ran.
    """
    payload = stamp_envelope(
        {
            "primary": {
                "kind": "field",
                "competitors": (
                    VUELTA_COMPETITORS if competitors is None else competitors
                ),
            }
        },
        created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        lifecycle_watermark=None,
    )
    write_payload(fake, cache_keys(key), payload)
    return payload


class TestTheProducerAndTheConsumerAddressTheSameCache:
    """The seam itself, stated as an assertion rather than left to inspection."""

    def test_the_producer_writes_a_slot_that_outlives_the_one_the_feed_reads(self):
        # Not a tautology: it is the arithmetic that makes the rest of this file
        # necessary. If these two ever become equal, the mirror read below stops
        # being load-bearing and this suite should be re-argued, not deleted.
        assert ENVELOPE_TTL == 60
        assert STALE_TTL > ENVELOPE_TTL * 100

    async def test_the_reader_asks_for_both_slots_by_their_producer_names(
        self, warm_cache
    ):
        fake, view = warm_cache
        _warm(fake)
        await _resolve_concept_leader(None, CONCEPT_KEY)
        keys = cache_keys(CONCEPT_KEY)
        assert view.mget_calls, "the reader never reached Redis"
        assert view.mget_calls[0] == [keys.primary, keys.stale], (
            "the consumer must address the slots the producer writes, by the "
            "producer's own key derivation — a hand-rolled f-string here is how "
            "#1948 outlived three cycles"
        )

    async def test_one_round_trip_serves_both_slots(self, warm_cache):
        # The mirror must not cost the hot feed path a second Redis op: the whole
        # reason the primary-only read survived review is that consulting a second
        # key looked expensive. It is one `mget`.
        fake, view = warm_cache
        _warm(fake)
        await _resolve_concept_leader(None, CONCEPT_KEY)
        assert len(view.mget_calls) == 1


class TestTheProductionSpecimen:
    """4/4 at 19:18:13 and 0/4 at 19:18:34, reproduced."""

    async def test_a_live_primary_resolves_the_leader(self, warm_cache):
        fake, _ = warm_cache
        _warm(fake)
        leader = await _resolve_concept_leader(None, CONCEPT_KEY)
        assert leader is not None
        assert leader["name"] == "Tadej Pogacar"
        assert leader["probability"] == pytest.approx(0.751)
        assert leader["field_size"] == 4

    async def test_an_expired_primary_still_resolves_from_the_mirror(self, warm_cache):
        """THE SPECIMEN. This is the assertion #1948 fails without the fix."""
        fake, _ = warm_cache
        _warm(fake)
        keys = cache_keys(CONCEPT_KEY)

        # Exactly what Redis does 60 seconds after the warmer's write, and what
        # production was doing for ~92% of the day.
        fake.advance(ENVELOPE_TTL + 1)
        assert fake.get(keys.primary) is None, "the primary must be gone"
        assert fake.get(keys.stale) is not None, "the mirror must still hold it"

        leader = await _resolve_concept_leader(None, CONCEPT_KEY)
        assert leader is not None, (
            "the leader is in the mirror the detail page is serving right now; "
            "a feed card that shows no favourite here is #1948"
        )
        assert leader["name"] == "Tadej Pogacar"
        assert leader["probability"] == pytest.approx(0.751)

    async def test_the_primary_wins_when_both_slots_are_present(self, warm_cache):
        """Freshest-first. The mirror is a fallback, never a preference."""
        fake, _ = warm_cache
        _warm(fake, competitors=[{"name": "Stale Rider", "probability": 0.9}])
        # A newer build overwrites both slots; then only the primary is replaced
        # with a distinguishable payload so the preference is observable.
        newer = stamp_envelope(
            {"primary": {"competitors": [{"name": "Fresh Rider", "probability": 0.6}]}},
            created_at=datetime.now(timezone.utc),
            lifecycle_watermark=None,
        )
        from app.utils.event_concept_cache import encode_payload

        fake.setex(cache_keys(CONCEPT_KEY).primary, ENVELOPE_TTL, encode_payload(newer))

        leader = await _resolve_concept_leader(None, CONCEPT_KEY)
        assert leader["name"] == "Fresh Rider"

    async def test_a_cold_cache_still_yields_no_leader_and_never_builds(
        self, warm_cache, monkeypatch
    ):
        """UX-P089's constraint survives: nothing here may build on the feed path."""
        import app.utils.event_concept as ec

        built = []

        class _Adapter:
            async def build_event(self, slug, db):
                built.append(slug)
                return {"primary": {"competitors": VUELTA_COMPETITORS}}

        monkeypatch.setattr(ec, "get_adapter", lambda domain: _Adapter())
        assert await _resolve_concept_leader(None, CONCEPT_KEY) is None
        assert built == [], "the cache-only rule (#1934) must not be softened by this fix"


class TestTheMirrorIsBoundedRatherThanTrusted:
    """A card cannot print `availability: stale_ok`, so it bounds the age itself."""

    async def test_a_mirror_within_the_bound_is_served(self, warm_cache):
        fake, _ = warm_cache
        _warm(fake, age_seconds=feed_mod.CONCEPT_MIRROR_MAX_AGE_SECONDS - 60)
        fake.advance(ENVELOPE_TTL + 1)
        assert await _resolve_concept_leader(None, CONCEPT_KEY) is not None

    async def test_a_mirror_past_the_bound_falls_back_to_the_count(self, warm_cache):
        fake, _ = warm_cache
        _warm(fake, age_seconds=feed_mod.CONCEPT_MIRROR_MAX_AGE_SECONDS + 60)
        fake.advance(ENVELOPE_TTL + 1)
        assert await _resolve_concept_leader(None, CONCEPT_KEY) is None

    async def test_the_bound_resolves_at_call_time(self, warm_cache, monkeypatch):
        """Ruling 084: an overridable threshold is read where it is used.

        Bound as a default argument it would freeze at import and no operator
        change could reach it — cycle 89's specimen, and the reason this is an
        assertion rather than a comment.
        """
        fake, _ = warm_cache
        _warm(fake, age_seconds=7200)
        fake.advance(ENVELOPE_TTL + 1)
        assert await _resolve_concept_leader(None, CONCEPT_KEY) is None
        monkeypatch.setattr(feed_mod, "CONCEPT_MIRROR_MAX_AGE_SECONDS", 86400)
        assert await _resolve_concept_leader(None, CONCEPT_KEY) is not None

    async def test_the_age_bound_is_stricter_than_the_producers_mirror(self):
        # The feed must never be the LOOSER of the two, which would mean a card
        # leading with a probability the detail page has already stopped serving.
        assert feed_mod.CONCEPT_MIRROR_MAX_AGE_SECONDS < STALE_TTL


class TestFeedToResolverToWarmedKey:
    """The end-to-end specimen: the feed's own card builder, not the resolver alone."""

    @pytest.fixture
    def one_concept(self, monkeypatch):
        import app.utils.event_concept_population as pop

        now = datetime.now(timezone.utc)

        async def _list_all(db, sport_filter=None, statuses=None):
            return [
                {
                    "key": CONCEPT_KEY,
                    "name": "Vuelta a Espana 2026",
                    "domain": "cycling",
                    "status": "upcoming",
                    "start_date": (now + timedelta(days=2)).date().isoformat(),
                    "latest_commence": now + timedelta(days=2),
                    "is_major": True,
                    "fight_count": 0,
                    "entry_count": 30,
                }
            ]

        monkeypatch.setattr(pop, "list_all_concepts", _list_all)
        return now

    async def _cards(self, now):
        return await _score_event_concepts(None, now, None)

    async def test_the_card_leads_with_the_favourite_off_an_expired_primary(
        self, warm_cache, one_concept
    ):
        """feed -> resolver -> warmed key, with the primary gone. The whole seam."""
        fake, _ = warm_cache
        _warm(fake)
        fake.advance(ENVELOPE_TTL + 1)

        cards = await self._cards(one_concept)

        assert len(cards) == 1, f"expected one concept card, got {len(cards)}"
        data = cards[0]["data"]
        assert data["key"] == CONCEPT_KEY
        assert data["marquee_whathit"] is False
        leader = data.get("leader")
        assert leader is not None, (
            "16 built / 0 leaders is what this assertion is for — the card must "
            "not be a directory entry when the probability is one Redis key away"
        )
        assert leader["name"] == "Tadej Pogacar"
        assert leader["probability"] == pytest.approx(0.751)

    async def test_the_card_falls_back_honestly_when_nothing_is_warm(
        self, warm_cache, one_concept
    ):
        # Nothing written at all.
        #
        # Q407 Item 3 (Alex directive, 2026-08-24) CHANGED this contract. It used
        # to read "the card still ships, without a fabricated probability (the
        # L2-159 contract)" — ship it honestly rather than invent a number. That
        # half still holds and always will: nothing here fabricates anything.
        #
        # What changed is the other half. L2-159 predates the fail-closed
        # suppression rules (#1486 / #1935), under which BOTH surfaces return
        # `empty_concept` for exactly this card and drop it. So "ships honestly"
        # had quietly stopped meaning "reaches a reader" and started meaning
        # "occupies a page slot on the way to being discarded". The directive
        # settles it: *a card that cannot show a probability does not ship to the
        # feed*. Honest is still honest — it is now honest one layer earlier,
        # where the freed slot can be refilled by a card that can answer
        # something.
        cards = await self._cards(one_concept)
        assert cards == [], (
            "with nothing warm the concept cannot show a probability, so it must "
            f"not ship. Emitted: {[c['data']['key'] for c in cards]}"
        )

    async def test_the_card_recovers_across_a_full_warm_cadence(
        self, warm_cache, one_concept
    ):
        """The duty-cycle argument, as a test.

        `warm_event_concepts` measured ~13 minutes between runs against a 60s
        primary. Walk that interval: under the old primary-only read the card is
        dark for all but the first minute of it.
        """
        fake, _ = warm_cache
        _warm(fake)
        seen = []
        for _ in range(13):
            cards = await self._cards(one_concept)
            seen.append(cards[0]["data"].get("leader") is not None)
            fake.advance(60)
        assert all(seen), (
            "a card's probability must not depend on landing inside a 60-second "
            f"window: {seen}"
        )


def test_the_reader_names_its_slots_through_cache_keys():
    """A regression guard on the shape, not the behaviour.

    The fix is only durable while the reader derives its keys from `cache_keys`.
    A future edit that goes back to an f-string would pass every behavioural test
    above the moment somebody also updates the fake — so the source is asserted,
    the way ruling 078's contract tests assert the call per surface by name.
    """
    import ast
    import inspect
    import textwrap

    fn = ast.parse(
        textwrap.dedent(inspect.getsource(feed_mod._read_cached_concept_envelope))
    ).body[0]
    # Scan the BODY, not the docstring. The docstring quotes the deleted line on
    # purpose — a source guard that cannot tell an explanation from an
    # implementation grades the wrong text (ruling 084's own species).
    if (
        fn.body
        and isinstance(fn.body[0], ast.Expr)
        and isinstance(fn.body[0].value, ast.Constant)
        and isinstance(fn.body[0].value.value, str)
    ):
        fn.body = fn.body[1:]
    src = ast.unparse(fn)

    assert "cache_keys(key)" in src, "derive the slot names from the producer"
    assert "keys.primary" in src and "keys.stale" in src
    assert 'f"{CACHE_PREFIX}{key}"' not in src, (
        "the hand-rolled primary-only key is #1948; it does not come back"
    )


def test_time_is_not_the_oracle():
    """This file must not be one of the clock-anchored suites (gotcha #44)."""
    import inspect

    src = inspect.getsource(_FakeRedis)
    assert "time.time" not in src and "datetime.now" not in src, (
        "the TTL clock is owned by the test, not by the wall clock"
    )
    # `time` is imported for readers who expect a monotonic source here and find
    # a counter instead; keep the reference honest.
    assert time is not None
