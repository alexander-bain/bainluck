"""C-1 (worker audit 2026-11-06; Speed): cadence trims on `worker-background`.

Each section pins one trim and the reader-facing age it states.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.tasks import event_concept_warmer as concepts


# --- B-4: golf majors every 30 min, leaders still every 5 -------------------


def test_the_majors_ride_the_run_that_opens_each_half_hour():
    base = 1_762_473_600  # 2025-11-07 00:00:00Z, a whole hour
    due = [m for m in range(0, 60, 5) if concepts.majors_due(base + m * 60 + 7)]
    assert due == [0, 30]
    assert concepts.MAJORS_EVERY_MINUTES == 30
    assert concepts.BEAT_PERIOD_MINUTES == 5


def test_the_beat_the_slot_arithmetic_mirrors_is_still_every_5_minutes():
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["warm-event-concepts"]
    assert entry["schedule"].minute == set(range(0, 60, concepts.BEAT_PERIOD_MINUTES))


@pytest.mark.parametrize("due", [True, False])
async def test_an_off_slot_run_warms_the_leaders_and_never_the_majors(due):
    from app.config.event_concept_warm_keys import WARM_CONCEPT_KEYS

    built: list[str] = []

    async def _population():
        return ("leader-a", "leader-b")

    async def _build(key, *, token, timeout=None):
        built.append(key)
        return {"key": key, "ok": True, "reason": "built", "seconds": 0.1}

    with patch.object(concepts, "majors_due", lambda now: due), \
         patch.object(concepts, "_leader_population", _population), \
         patch.object(concepts, "_build_one", _build), \
         patch("app.utils.event_concept_cache.get_client", lambda: object()), \
         patch("app.utils.event_concept_cache.acquire_refresh_lock", lambda rc, keys: "tok"):
        summary = await concepts._warm_event_concepts()

    majors = set(WARM_CONCEPT_KEYS)
    assert built[:2] == ["leader-a", "leader-b"]  # leaders first, every run
    assert bool(majors & set(built)) is due
    assert summary["majors_tier"] is due
    assert summary["total"] == 2 + (len(WARM_CONCEPT_KEYS) if due else 0)
    assert summary["terminal"] == "complete"
