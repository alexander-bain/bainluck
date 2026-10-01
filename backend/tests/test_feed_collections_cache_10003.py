"""#10003 — the publication fingerprint a collection-bearing feed page is cached under."""

import hashlib
from contextlib import asynccontextmanager

import pytest

from app.utils import feed_collections as consumer
from app.utils.feed_cache import (
    FEED_PAGE_BASE_CACHE_PREFIX,
    FEED_RESPONSE_CACHE_PREFIX,
    feed_page_base_cache_key,
    feed_response_cache_key,
)

NATIVE = dict(limit=50, offset=0, event_pct=0.15)


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _Session:
    """Answers the fingerprint statement; records whether a SAVEPOINT held it."""

    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.statements = []
        self.in_savepoint = []
        self._nested = False

    @asynccontextmanager
    async def begin_nested(self):
        self._nested = True
        try:
            yield
        finally:
            self._nested = False

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        self.in_savepoint.append(self._nested)
        if self.error:
            raise self.error
        return _Result(self.value)


# ---------------------------------------------------------------------------
# The fingerprint
# ---------------------------------------------------------------------------


async def test_a_revision_bump_changes_the_fingerprint():
    before = await consumer.feed_collections_cache_fingerprint(_Session("4:1,7:2"))
    same = await consumer.feed_collections_cache_fingerprint(_Session("4:1,7:2"))
    bumped = await consumer.feed_collections_cache_fingerprint(_Session("4:1,7:3"))
    withdrawn = await consumer.feed_collections_cache_fingerprint(_Session("4:1"))
    nothing = await consumer.feed_collections_cache_fingerprint(_Session(""))
    assert before == same
    assert len({before, bumped, withdrawn, nothing}) == 4
    assert all(isinstance(fp, str) and fp for fp in (before, nothing))


async def test_the_read_is_one_statement_inside_a_savepoint():
    session = _Session("4:1")
    await consumer.feed_collections_cache_fingerprint(session)
    assert session.in_savepoint == [True]
    (sql, params), = session.statements
    assert "publication_state = 'published'" in sql
    assert "parent_container_id IS NULL" in sql
    assert "membership_revision" in sql
    assert "ORDER BY id" in sql
    assert params == {
        "slug_pattern": consumer.container_discovery.DISCOVERABLE_SLUG_PATTERN
    }


@pytest.mark.parametrize("value", [None, 7, b"4:1"])
async def test_an_answer_that_is_not_text_is_not_a_fingerprint(value):
    assert await consumer.feed_collections_cache_fingerprint(_Session(value)) is None


async def test_a_failed_read_means_do_not_cache():
    session = _Session(error=RuntimeError('column "membership_revision" does not exist'))
    assert await consumer.feed_collections_cache_fingerprint(session) is None
    assert session.in_savepoint == [True]


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def test_an_events_only_request_is_not_collection_eligible(monkeypatch):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    request = dict(mode=None, include_events=True, my_teams_only=False)
    assert consumer.feed_collections_enabled(**request)
    assert consumer.feed_collections_enabled(**request, include_futures=True)
    assert not consumer.feed_collections_enabled(**request, include_futures=False)


# ---------------------------------------------------------------------------
# The keys
# ---------------------------------------------------------------------------


def test_flag_off_keys_are_byte_identical_to_before():
    """No fingerprint ⇒ the string hashed is exactly the pre-#10003 one, so the
    deploy does not cold-start any flag-off key."""
    parts = "feed:anon:all:50:0:True:True::0.15:False:discover"
    assert feed_response_cache_key(**NATIVE) == (
        f"{FEED_RESPONSE_CACHE_PREFIX}:{hashlib.md5(parts.encode()).hexdigest()}"
    )
    assert feed_response_cache_key(**NATIVE, collections=None) == (
        feed_response_cache_key(**NATIVE)
    )
    base = "pagebase:all:50:True:True::0.15:False:discover"
    assert feed_page_base_cache_key(limit=50, event_pct=0.15) == (
        f"{FEED_PAGE_BASE_CACHE_PREFIX}:{hashlib.md5(base.encode()).hexdigest()}"
    )
    assert feed_page_base_cache_key(limit=50, event_pct=0.15, collections=None) == (
        feed_page_base_cache_key(limit=50, event_pct=0.15)
    )


def test_each_publication_state_has_its_own_response_and_base_key():
    plain = feed_response_cache_key(**NATIVE)
    a = feed_response_cache_key(**NATIVE, collections="aaaa")
    b = feed_response_cache_key(**NATIVE, collections="bbbb")
    assert len({plain, a, b}) == 3
    base_plain = feed_page_base_cache_key(limit=50, event_pct=0.15)
    base_a = feed_page_base_cache_key(limit=50, event_pct=0.15, collections="aaaa")
    base_b = feed_page_base_cache_key(limit=50, event_pct=0.15, collections="bbbb")
    assert len({base_plain, base_a, base_b}) == 3


def test_the_fingerprint_cannot_be_forged_through_another_free_text_field():
    """Length-delimited like ``category`` and ``edition``."""
    a = feed_response_cache_key(**NATIVE, collections="x", category="y")
    b = feed_response_cache_key(**NATIVE, collections="x|cat=1:y", category=None)
    assert a != b
