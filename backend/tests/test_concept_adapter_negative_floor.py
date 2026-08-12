"""UX-P066 / #1793 — every concept adapter must have a NEGATIVE FLOOR.

A slug that names nothing we hold must resolve to `None`, so `/api/event/{key}`
404s. An adapter without that floor serves its nearest neighbour instead, and a
reader lands confidently on the wrong competition — the failure #1793 was filed
for, where `event:tennis:us-open-2026` served "Cincinnati Open".

The floor is also load-bearing for `horizon_sentinel`, which decides "does this
event have a page" by resolving `concept_key` and checking for a 200 with
content (`app/tasks/horizon_sentinel.py:304-325`). An adapter that always 200s
makes that alarm **vacuous for its entire domain**: it can never fire, including
for a marquee event with no page at all.

A production census on 2026-08-12 (v3788) probed all nine registered adapters
with two no-match slugs each: 8 of 9 already had a floor; tennis did not. This
test exists so the eight cannot regress and a tenth adapter cannot ship without
one. Re-run the live census with `backend/scripts/probe_adapter_floor.py`.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import app.utils.event_concept as concept_mod

# Slugs that cannot name a real competition in any domain, in any tolerant
# scheme. The second is not idle: its only surviving token was the generic word
# "tournament", and that is the probe that first exposed the tennis leak — it
# matched "Serena Williams to Win a Tournament in 2026".
NO_MATCH_SLUGS = ["zzqqxx-does-not-exist-9999", "not-a-tournament-zzq"]


class _EmptyResult:
    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return []

    def first(self):
        return None

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    def __iter__(self):
        return iter([])


class _EmptyDB:
    """A database that holds nothing. Whatever an adapter looks for, it is absent."""

    async def execute(self, *a, **k):
        return _EmptyResult()


def _domains():
    return sorted(concept_mod.registered_domains())


def test_the_registry_is_not_silently_empty():
    """Guard the guard: if the registry were empty the parametrised tests below
    would vacuously pass while asserting nothing about anything."""
    doms = _domains()
    assert len(doms) >= 9, f"expected the full adapter set, got {doms}"
    assert "tennis" in doms and "golf" in doms


@pytest.mark.parametrize("domain", _domains())
@pytest.mark.parametrize("slug", NO_MATCH_SLUGS)
async def test_adapter_returns_none_for_a_slug_that_names_nothing(domain, slug):
    adapter = concept_mod.get_adapter(domain)
    assert adapter is not None

    # Golf reaches its 404 by way of the golf route raising HTTPException(404);
    # every other adapter reads markets directly and finds none. Both paths must
    # arrive at the same answer: None.
    with patch(
        "app.routes.golf.get_golf_tournament",
        new=AsyncMock(side_effect=HTTPException(status_code=404)),
    ):
        built = await adapter.build_event(slug, _EmptyDB())

    assert built is None, (
        f"{domain} adapter served a page for {slug!r} — a slug that names nothing. "
        "This is the #1793 class: the reader gets a confident wrong competition, "
        "and horizon_sentinel's page-check goes vacuous for the whole domain."
    )


@pytest.mark.parametrize("domain", _domains())
def test_every_adapter_declares_its_domain(domain):
    """The registry keys on `adapter.domain`; a mismatch makes `get_adapter`
    return an adapter for a domain it does not serve."""
    assert concept_mod.get_adapter(domain).domain == domain
