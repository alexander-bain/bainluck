"""Reviewed person aliases reach both actual search handlers (#11617).

Recording DB checks cover recall and extra-query cost, not real PG execution
or reader acceptance. No temporary resolver adapter replaces production wiring.
"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import person_aliases
from app.routes import events as ev
from tests.test_search_club_short_forms_9834 import (
    _recording_db,
    _search,
    _tables_asked_for,
)
from tests.test_search_detail_parity_11616 import FixedDatetime


@pytest.fixture(autouse=True)
def fixed_inputs(monkeypatch):
    monkeypatch.setattr(ev, "datetime", FixedDatetime)
    monkeypatch.setattr(
        ev,
        "time",
        SimpleNamespace(
            monotonic=lambda: 1000.0,
            perf_counter=lambda: 1000.0,
        ),
    )
    monkeypatch.setattr(ev, "_record_search_query", MagicMock())


async def call(endpoint, query, seen):
    # Empty roster stays cold in each comparison so the same reads are counted.
    with patch.object(ev, "_roster_index_expires_at", 0):
        if endpoint == "search":
            return await _search(query, seen)
        redis = MagicMock()
        redis.get.return_value = None
        request = MagicMock()
        request.headers = {}
        with patch(
            "app.tasks.redis_state.get_redis_client", return_value=redis
        ), patch.object(ev, "_record_trending", MagicMock()):
            return await ev.typeahead_search(
                q=query,
                debug_evidence=False,
                debug_timing=False,
                db=_recording_db(seen),
                request=request,
            )


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
async def test_reviewed_alias_reaches_every_recall_rail_and_keeps_raw_query(endpoint):
    seen = []
    body = await call(endpoint, "SGA", seen)
    assert body["query"] == "SGA"
    assert _tables_asked_for(seen, "shai") == {"teams", "events", "futures"}
    full_name_reads = []
    await call(endpoint, "Shai Gilgeous-Alexander", full_name_reads)
    assert len(seen) == len(full_name_reads), "alias must add no separate DB lookup"


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
async def test_conflicting_reviewed_identity_does_not_choose_a_person(
    endpoint, monkeypatch
):
    first = person_aliases.REVIEWED_PERSON_ALIASES[0]
    monkeypatch.setattr(
        person_aliases,
        "REVIEWED_PERSON_ALIASES",
        (
            first,
            replace(first, provider_id="different-person"),
        ),
    )
    seen = []
    body = await call(endpoint, "SGA", seen)
    assert body["query"] == "SGA"
    assert not _tables_asked_for(seen, "shai")
    assert _tables_asked_for(seen, "sga")


@pytest.mark.parametrize("endpoint", ["search", "typeahead"])
@pytest.mark.parametrize(
    "query",
    [
        "Zacharia",
        "Zachariah Branch",
        "ai",
        "ipo",
        "weather",
        "man utd",
        "SG",
        "SGAR",
        "SGA MVP",
    ],
)
async def test_unrelated_or_partial_query_retains_identical_bindings(
    endpoint, query, monkeypatch
):
    seen = []
    body = await call(endpoint, query, seen)
    monkeypatch.setattr(person_aliases, "REVIEWED_PERSON_ALIASES", ())
    control_seen = []
    control_body = await call(endpoint, query, control_seen)
    assert body == control_body
    assert seen == control_seen
