"""W-1 (worker audit 2026-11-06 B-1 + B-2; Alex 53: A, 12:07 PM PT): the two
search warmers are sized to their readers.

Pinned here, each one a way the change silently stops being what was approved:

* `/search` head: warmer-written entries live 600 s while every reader-built
  answer keeps 180 s, on a 300 s floor and a 60 s beat;
* `/typeahead`: a residency pass of 8 terms every 15 s, the 30 s floor kept;
* the Flow Sentinel's gold set is warmed once at 07:05 UTC, five minutes before
  the 07:10 sentinel, and a fire that lands on a running pass is retried, not
  dropped.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from celery.schedules import crontab

from app.tasks import celery_app
from app.tasks import search_head_warmer as head
from app.tasks import typeahead_warmer as ta
from app.utils.search_cache import (
    SEARCH_HEAD_WARMER_TTL_SECONDS,
    SEARCH_RESPONSE_TTL_SECONDS,
    SEARCH_THIN_RESPONSE_TTL_SECONDS,
    search_response_ttl_seconds,
)


def test_only_the_warmers_own_writes_get_the_longer_life():
    assert (SEARCH_HEAD_WARMER_TTL_SECONDS, SEARCH_RESPONSE_TTL_SECONDS) == (600, 180)
    assert search_response_ttl_seconds("merged", warmer_rebuild=True) == 600
    assert search_response_ttl_seconds("shed", warmer_rebuild=True) == 600
    # A reader's answer is exactly as before: 180 complete, 30 thin.
    assert search_response_ttl_seconds("merged", warmer_rebuild=False) == 180
    assert (
        search_response_ttl_seconds("shed", warmer_rebuild=False)
        == SEARCH_THIN_RESPONSE_TTL_SECONDS
    )


def test_the_search_head_cadence_is_the_approved_one_and_still_resident():
    assert head.MIN_PASS_PERIOD_SECONDS == 300
    assert head.BEAT_PERIOD_SECONDS == 60.0
    assert celery_app.conf.beat_schedule["warm-search-head"]["schedule"] == 60.0
    assert head.effective_pass_period_s() == 300.0
    ok, why = head.residency_invariant()
    assert ok, why


def test_the_typeahead_pass_is_a_residency_pass_of_eight_every_15s():
    assert ta.DEFAULT_HEAD_SIZE == 8
    assert ta.MIN_PASS_PERIOD_SECONDS == 30
    assert celery_app.conf.beat_schedule["warm-typeahead"]["schedule"] == 15.0
    # The queued-fire window did not move: 8 messages x 15 s = 120 s.
    assert celery_app.conf.beat_schedule["warm-typeahead"]["options"]["expires"] == 120


def test_the_gold_set_is_the_sentinels_own_and_deduped():
    from app.tasks.flow_sentinel import GOLD_SET, GOLD_SET_TOP1

    terms = ta.flow_sentinel_gold_terms()
    every = {q for q, _ in GOLD_SET} | {q for q, _, _ in GOLD_SET_TOP1}
    assert set(terms) == every
    assert len(terms) == len(set(terms)) == 32  # 33 rows, `masters winner` twice
    assert terms[0] == GOLD_SET[0][0]


def test_the_gold_set_prewarm_fires_before_the_sentinel_on_background():
    entry = celery_app.conf.beat_schedule["warm-typeahead-gold-set"]
    assert entry["task"] == "app.tasks.warm_typeahead_gold_set"
    assert entry["schedule"] == crontab(hour=7, minute=5)
    assert entry["options"]["queue"] == "background"
    sentinel = celery_app.conf.beat_schedule["flow-sentinel-daily"]["schedule"]
    assert sentinel == crontab(hour=7, minute=10)


def _gold_task():
    return celery_app.tasks["app.tasks.warm_typeahead_gold_set"]


def test_a_gold_fire_that_lands_on_a_running_pass_is_retried():
    async def _skipped(queries=None, **_):
        return {"terminal": "skipped", "skip_reason": "lock", "total": 0}

    with patch.object(ta, "_warm_typeahead", _skipped):
        with pytest.raises(Retry):
            _gold_task().apply(throw=True).get()


def test_a_gold_pass_warms_exactly_the_gold_terms():
    seen: dict = {}

    async def _ran(queries=None, **_):
        seen["queries"] = list(queries or [])
        return {"terminal": "complete", "completed": len(seen["queries"]), "total": 32}

    with patch.object(ta, "_warm_typeahead", _ran):
        out = _gold_task().apply(throw=True).get()
    assert seen["queries"] == ta.flow_sentinel_gold_terms()
    assert out["terminal"] == "complete"
