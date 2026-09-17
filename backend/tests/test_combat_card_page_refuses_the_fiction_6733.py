"""#6733 — a combat card suppressed from Discover stops keeping its own PAGE.

═══ THE DEFECT ═══

#4485 taught `list_card_concepts` to refuse a card whose own bout rows prove it
is not a schedule. It shipped, and it worked: production `/api/feed` went from
9 UFC concepts to 7, and `27jan01` and `27apr25` left the list.

`27jan01` kept its page. Measured on production 2026-09-17 13:5xZ, release
v4678, `GET /api/event/event:ufc:27jan01` still answered 200 with:

    name     Tom Aspinall vs Ciryl Gane        status   upcoming
    start    2027-01-01T03:00:00+00:00         children 7, every one `source: events`

        Tom Aspinall vs Ciryl Gane
        Sean Strickland vs Khamzat Chimaev
        Sean Strickland vs Nassourdine Imavov      <- Strickland twice
        Khamzat Chimaev vs Paulo Henrique Costa    <- Chimaev twice
        Alexandre Pantoja vs Joshua Van
        Merab Dvalishvili vs Petr Yan
        Max Holloway vs Paddy Pimblett

Seven rumoured bouts on one instant, two fighters booked twice — the exact rows
#4485's predicate reads — rendered as a real card with a date and a percentage.

═══ WHY IT SURVIVED ═══

The list and the page are two different readers of one roster:

    GET /api/feed          -> list_card_concepts          GATED by #4485
    GET /api/event/<key>   -> CombatEventAdapter.build_event   UNGATED

Both have an events-only branch (no Kalshi markets for the token) and both build
from `_list_event_bouts`, so the page reached the rows the lister had refused.
No symbol grep finds this pair: the feed reaches its lister through a
string-keyed registry, and the adapter is reached through another.

═══ WHAT IS ASSERTED ═══

The fix is one condition, deliberately IDENTICAL to the lister's — the same
predicate on the same events-only branch — so the arms here are about the two
layers AGREEING, not about the predicate, which is `#4485`'s own suite
(`test_combat_card_is_not_a_schedule_4485.py`) and is not re-litigated:

  1. the page refuses the fiction (`None` -> the route's 404)
  2. the page still builds a REAL events-only card (the population holds; arm 1
     alone passes on an adapter that refuses everything)
  3. lister and page return the SAME verdict on the SAME rows — the property
     that failed, stated directly and over both directions
  4. venue corroboration still wins: a card Kalshi lists is never judged by the
     roster predicate on either layer, so the escape hatch #4485 built survives
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import list_card_concepts
from app.utils.event_ufc import UFC_CONFIG, UFCEventAdapter

_IDS = itertools.count(1)


def _bout(home, away, when):
    """An Event row for one fight. `id` matters — `bout_order_key` orders on it,
    and `_build_events_envelope` renders it as each child's key."""
    return SimpleNamespace(
        id=next(_IDS),
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status="scheduled",
        win_probability_sources=None,
    )


def _far(days: int, hour: int = 3) -> datetime:
    """A fixed instant `days` out. Offset FIRST, then truncate (gotcha #44)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


def _token(when: datetime) -> str:
    """The card date-token the adapter resolves a slug to, e.g. `27jan01`."""
    from app.utils.event_combat import event_commence_token

    return event_commence_token(when)


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    """Dispatch on the statement text, never one shared list.

    `build_event` reads `futures_markets` and then `events`; `list_card_concepts`
    reads `events` and then `futures_outcomes`. Answering every query from one
    list feeds Event rows to a market reader, which raises inside its own
    catch-all and silently skips — the arm then passes for the wrong reason.
    """

    def __init__(self, events=(), markets=()):
        self._events = list(events)
        self._markets = list(markets)

    async def execute(self, statement, *_a, **_k):
        sql = str(statement)
        if "futures_outcomes" in sql:
            return _FakeResult([])
        if "futures_markets" in sql:
            return _FakeResult(self._markets)
        return _FakeResult(self._events)


# The two rosters every arm below shares: one fabricated, one real. Both are
# events-only (no Kalshi markets), which is the branch the defect lived on.
_FICTION_WHEN = _far(106, hour=3)
_FICTION = [
    _bout("Tom Aspinall", "Ciryl Gane", _FICTION_WHEN),
    _bout("Sean Strickland", "Khamzat Chimaev", _FICTION_WHEN),
    _bout("Sean Strickland", "Nassourdine Imavov", _FICTION_WHEN),
    _bout("Khamzat Chimaev", "Paulo Henrique Costa", _FICTION_WHEN),
]

_REAL_WHEN = _far(9, hour=18)
_REAL = [
    _bout("Darren Till", "Yoel Romero", _REAL_WHEN),
    _bout("Natalia Silva", "Wang Cong", _REAL_WHEN + timedelta(hours=1)),
]


@pytest.mark.asyncio
class TestThePageRefusesIt:
    async def test_the_fabricated_card_has_no_page(self):
        """`None` is the adapter's "no such card": `build_and_cache` writes the
        negative marker and `GET /api/event/{key}` raises its 404."""
        built = await UFCEventAdapter().build_event(
            _token(_FICTION_WHEN), _FakeDB(events=_FICTION)
        )
        assert built is None, f"the fabricated card must have no page; got {built}"

    async def test_a_real_events_only_card_still_builds(self):
        """The population holds. Arm 1 passes on an adapter that refuses
        everything, so it proves nothing on its own — this is the arm that
        catches a gate applied one branch too wide."""
        built = await UFCEventAdapter().build_event(
            _token(_REAL_WHEN), _FakeDB(events=_REAL)
        )
        assert built is not None, "a real events-only card must keep its page"
        names = {c["market_name"] for c in built["children"]}
        assert names == {
            "Darren Till vs Yoel Romero",
            "Natalia Silva vs Wang Cong",
        }, names

    async def test_the_list_and_the_page_agree_in_both_directions(self):
        """THE PROPERTY THAT FAILED. Same rows, same roster, one verdict — a
        card is either served on both layers or on neither. Asserted over both
        cards in one call so neither direction can pass by vacuity."""
        db_rows = _FICTION + _REAL

        listed = await list_card_concepts(UFC_CONFIG, _FakeDB(events=db_rows), rows=[])
        listed_tokens = {c["key"].rsplit(":", 1)[-1] for c in listed}

        for when, label in ((_FICTION_WHEN, "fabricated"), (_REAL_WHEN, "real")):
            token = _token(when)
            on_page = (
                await UFCEventAdapter().build_event(token, _FakeDB(events=db_rows))
            ) is not None
            in_list = token in listed_tokens
            assert on_page == in_list, (
                f"the {label} card ({token}) is served on one layer and not the "
                f"other: list={in_list}, page={on_page}"
            )

        # ...and the pair is not two Falses or two Trues: the fiction is gone and
        # the real card is there, on both layers.
        assert _token(_REAL_WHEN) in listed_tokens
        assert _token(_FICTION_WHEN) not in listed_tokens


@pytest.mark.asyncio
class TestVenueCorroborationStillWins:
    async def test_a_card_kalshi_lists_is_never_judged_by_its_roster(self):
        """#4485's escape hatch, which this change must not narrow: the roster
        predicate reads our own events table, so a card the VENUE lists has
        corroboration it cannot overrule. Gated on the events-only branch on
        both layers — here the SAME fabricated roster, with Kalshi fights on the
        token, keeps its page.
        """
        token = _token(_FICTION_WHEN)
        market = SimpleNamespace(
            id=9001,
            external_id=f"KXUFCFIGHT-{token.upper()}-ASPGAN",
            name="Tom Aspinall vs Ciryl Gane",
            source="kalshi",
            status="open",
            commence_time=_FICTION_WHEN,
            market_metadata={"event_title": "UFC 330"},
            outcomes=[
                SimpleNamespace(name="Tom Aspinall", current_probability=0.62),
                SimpleNamespace(name="Ciryl Gane", current_probability=0.38),
            ],
        )

        built = await UFCEventAdapter().build_event(
            token, _FakeDB(events=_FICTION, markets=[market])
        )
        assert built is not None, (
            "a card the venue lists must keep its page — the roster predicate "
            "may only ever decide an events-only card"
        )


# ═══════════════════════════════════════════════════════════════════════════
# The reach half. The adapter's refusal only becomes a 404 the reader sees if
# the cache tier stops answering from the mirror behind it.
#
# MEASURED on production 2026-09-17 14:0xZ, BEFORE this change, six reads of
# `/api/event/event:ufc:27jan01` twelve seconds apart:
#
#     stale_ok | live | live | live | live | stale_ok
#
# The mirror is served at every 60s TTL boundary. So a refusal that armed only
# the 60s negative would have left the page alternating [one serving of the
# fiction, 60s of 404] for the mirror's whole 24h life — ~98% inert at the
# reader, and an after-check landing on either state by luck.
# ═══════════════════════════════════════════════════════════════════════════


class _FakeRedis:
    """In-memory Redis — get / setex / delete over a dict, the idiom this
    tier's sibling suites already use."""

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)


class TestARefusalReachesTheReader:
    def test_the_refusal_drops_the_mirror_behind_it(self):
        from app.utils.event_concept_cache import (
            cache_keys,
            has_negative,
            write_negative,
            write_payload,
        )

        keys = cache_keys("event:ufc:27jan01")
        rc = _FakeRedis()
        # Arranged through the tier's OWN writer, so the mirror is whatever this
        # module actually stores. Asserted on the raw slot rather than through
        # `read_slot`, which additionally requires a current-generation `cache`
        # stamp: a decoder-level miss is not the same fact as an absent key, and
        # only the absent key proves the delete landed.
        write_payload(rc, keys, {"event": {"name": "Tom Aspinall vs Ciryl Gane"}})
        assert rc.get(keys.stale) is not None, "arrange failed: no mirror stored"

        write_negative(rc, keys)

        assert has_negative(rc, keys), "the negative must still be armed"
        assert rc.get(keys.stale) is None, (
            "the mirror behind a refused key must be gone — the route serves it "
            "the moment the 60s negative lapses, and the page flaps"
        )

    def test_a_key_that_resolves_again_clears_the_negative(self):
        """The other direction of the same pair, which already existed and must
        keep working: a successful build un-refuses the key."""
        from app.utils.event_concept_cache import (
            cache_keys,
            has_negative,
            write_negative,
            write_payload,
        )

        keys = cache_keys("event:ufc:26sep19")
        rc = _FakeRedis()
        write_negative(rc, keys)
        assert has_negative(rc, keys)

        write_payload(rc, keys, {"event": {"name": "Real Card"}})

        assert not has_negative(rc, keys), "a key that resolves must lose its negative"
        assert rc.get(keys.stale) is not None, "and must publish a mirror"

    def test_a_redis_failure_never_raises(self):
        """Best-effort, like the rest of the tier: the refusal path runs on the
        request thread, so a Redis fault degrades to today's behaviour rather
        than 500-ing a page."""
        from app.utils.event_concept_cache import cache_keys, write_negative

        class _BrokenRedis:
            def setex(self, *_a, **_k):
                raise RuntimeError("redis down")

            def delete(self, *_a, **_k):
                raise RuntimeError("redis down")

        write_negative(_BrokenRedis(), cache_keys("event:ufc:27jan01"))
