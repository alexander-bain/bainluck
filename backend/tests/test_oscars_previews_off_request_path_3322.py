"""#3322 — `GET /api/oscars` reads its previews; it never generates them.

Measured on production 2026-09-08 before the fix: **10.83s** cold, 0.59s warm, on a
public endpoint with a >2s investigate threshold. Six synchronous
`app/services/llm.py` calls sat inside the async handler, `asyncio.gather`ed — which
cannot interleave a blocking call, so they ran serially and each one parked the event
loop for every other request on that worker process.

These tests pin the three things that make the fix a fix rather than a move:

1. the request path calls no LLM helper, whatever the state of the cache;
2. the previews still reach the response, out of the shared store;
3. absence of previews degrades to a page without previews — never an error, and
   never a partial publish that blanks good text on one bad provider minute.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.utils.oscars_previews import (
    PREVIEWS_REFRESH_SECONDS,
    PREVIEWS_REDIS_KEY,
    PREVIEWS_TTL_SECONDS,
    build_previews_envelope,
    read_published_previews,
)

# ── The contract between the two sides ─────────────────────────────────


def test_the_ttl_outlives_the_beat_that_writes_it():
    """TTL must exceed the interval, or the previews blink out between runs.

    Twice, specifically: the golf-commentary precedent, so that a *stopped* beat
    clears the previews within one interval instead of leaving text that quotes a
    probability the page has moved past. These blurbs name percentages, so a frozen
    one is not stale, it is wrong.
    """
    assert PREVIEWS_TTL_SECONDS == PREVIEWS_REFRESH_SECONDS * 2
    assert PREVIEWS_TTL_SECONDS > PREVIEWS_REFRESH_SECONDS


def test_the_envelope_round_trips_through_a_redis_shaped_client():
    rc = MagicMock()
    rc.get.return_value = build_previews_envelope({"best_picture": "a blurb"}).encode()

    previews, generated_at = read_published_previews(rc)

    assert previews == {"best_picture": "a blurb"}
    assert generated_at is not None, "the envelope must carry its own age"
    rc.get.assert_called_once_with(PREVIEWS_REDIS_KEY)


@pytest.mark.parametrize(
    "raw",
    [
        None,  # never written, or expired
        b"",  # empty
        b"not json at all",  # corrupt
        b'["a", "list"]',  # right JSON, wrong shape
        b'{"previews": "a string"}',  # right key, wrong type
        b"{}",  # envelope with nothing in it
    ],
    ids=[
        "absent",
        "empty",
        "corrupt",
        "wrong_type",
        "previews_not_a_dict",
        "no_previews_key",
    ],
)
def test_every_unreadable_state_degrades_to_no_previews(raw):
    """Absence is a normal state. A decoration may not fail a page."""
    rc = MagicMock()
    rc.get.return_value = raw

    assert read_published_previews(rc) == ({}, None)


def test_a_redis_outage_degrades_instead_of_raising():
    rc = MagicMock()
    rc.get.side_effect = ConnectionError("redis is down")

    assert read_published_previews(rc) == ({}, None)


def test_a_malformed_entry_costs_only_its_own_preview():
    rc = MagicMock()
    rc.get.return_value = json.dumps(
        {
            "previews": {
                "best_picture": "good",
                "best_actor": 42,
                "best_director": None,
            },
            "generated_at": "2026-09-08T21:00:00+00:00",
        }
    )

    previews, _ = read_published_previews(rc)

    assert previews == {
        "best_picture": "good"
    }, "one bad entry took the whole set down with it"


# ── The request path ───────────────────────────────────────────────────


def test_the_route_module_imports_no_llm_generator():
    """The route may not even be able to reach a generator.

    The narrow version of this — 'does the handler call it' — is the widened AST
    guard's job (`tests/integration/test_route_line_movement_no_movements.py`).
    This is the blunter statement that the module's own source no longer names one.
    """
    import inspect

    from app.routes import oscars as oscars_module

    source = inspect.getsource(oscars_module)
    for helper in (
        "generate_oscars_category_preview",
        "generate_oscars_movers_summary",
    ):
        assert (
            f"{helper}(" not in source
        ), f"{helper} is still reachable from the oscars request path"


def test_the_route_module_no_longer_keeps_a_per_process_cache():
    """The old `_LLM_CACHE` could not hold: per worker PROCESS, so `WEB_CONCURRENCY=2`
    kept two copies per dyno and every merge emptied all of them (2 of 3 consecutive
    production calls missed it). A reintroduced module-global would look like it
    worked locally and miss in production exactly as before."""
    from app.routes import oscars as oscars_module

    assert not hasattr(oscars_module, "_LLM_CACHE")


@pytest.mark.asyncio
async def test_the_handler_reads_previews_and_calls_no_generator():
    """The whole ship, end to end: previews reach the response from the store."""
    from app.routes import oscars as oscars_module

    published = {"best_picture": "Sinners leads at 41%.", "biggest_movers": "Movers."}
    rc = MagicMock()
    rc.get.return_value = build_previews_envelope(published)

    built = {
        "ceremony_date": "2026-03-02T00:00:00-08:00",
        "ceremony_status": "post",
        "categories": [],
        "trivia": [],
        "total_categories": 0,
        "biggest_movers": [],
        "film_nominations": [],
    }

    with patch.object(
        oscars_module, "build_oscars_payload", return_value=built
    ), patch.object(oscars_module, "_previews_redis", return_value=rc), patch(
        "app.services.llm.generate_oscars_category_preview"
    ) as gen_cat, patch(
        "app.services.llm.generate_oscars_movers_summary"
    ) as gen_mov:
        body = await oscars_module.get_oscars(db=MagicMock())

    assert body["llm_previews"] == published
    assert body["llm_previews_generated_at"] is not None
    gen_cat.assert_not_called()
    gen_mov.assert_not_called()


@pytest.mark.asyncio
async def test_an_empty_store_still_serves_the_page():
    """A cold Redis — before the beat's first run — must not cost the response."""
    from app.routes import oscars as oscars_module

    rc = MagicMock()
    rc.get.return_value = None
    built = {"ceremony_status": "post", "categories": [], "biggest_movers": []}

    with patch.object(
        oscars_module, "build_oscars_payload", return_value=built
    ), patch.object(oscars_module, "_previews_redis", return_value=rc):
        body = await oscars_module.get_oscars(db=MagicMock())

    assert body["llm_previews"] == {}
    assert body["llm_previews_generated_at"] is None
    assert body["ceremony_status"] == "post", "the rest of the payload survived"


# ── The task that writes them ──────────────────────────────────────────


def _category(key, *, major=True):
    return {
        "key": key,
        "name": key.replace("_", " ").title(),
        "is_major": major,
        "nominees": [
            {
                "name": f"{key} nominee {i}",
                "probability": 0.3,
                "movement_24h": 0.01,
                "opening_probability": 0.2,
            }
            for i in range(3)
        ],
    }


@pytest.mark.asyncio
async def test_the_task_publishes_one_envelope_with_the_shared_ttl():
    from app.tasks import oscars_previews as task_module

    payload = {
        "categories": [_category("best_picture"), _category("sound", major=False)],
        "biggest_movers": [{"name": "x", "movement_24h": 0.2}],
    }
    rc = MagicMock()

    with patch.object(task_module, "_build_payload", return_value=payload), patch(
        "app.services.llm.generate_oscars_category_preview", return_value="cat blurb"
    ), patch(
        "app.services.llm.generate_oscars_movers_summary", return_value="mov blurb"
    ), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ):
        result = await task_module._refresh_oscars_previews()

    assert result["published"] is True
    key, ttl, body = rc.setex.call_args[0]
    assert key == PREVIEWS_REDIS_KEY
    assert ttl == PREVIEWS_TTL_SECONDS
    written = json.loads(body)["previews"]
    assert written == {
        "best_picture": "cat blurb",
        "biggest_movers": "mov blurb",
    }, "a non-major category was previewed, or a preview went missing"


@pytest.mark.asyncio
async def test_the_task_makes_no_llm_call_when_there_is_nothing_to_preview():
    """Self-gates on DATA, not on a ceremony date that goes stale.

    The ceremony is months past and the endpoint still serves; if the markets ever
    go away this must cost one query, not six OpenAI calls an hour forever.
    """
    from app.tasks import oscars_previews as task_module

    rc = MagicMock()
    with patch.object(
        task_module,
        "_build_payload",
        return_value={"categories": [], "biggest_movers": []},
    ), patch("app.services.llm.generate_oscars_category_preview") as gen_cat, patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ):
        result = await task_module._refresh_oscars_previews()

    assert result == {"skipped": "no_major_categories"}
    gen_cat.assert_not_called()
    rc.setex.assert_not_called()


@pytest.mark.asyncio
async def test_a_total_generation_failure_leaves_the_published_previews_alone():
    """Publishing `{}` here would blank good text on one bad provider minute.

    The existing envelope must be left to expire on its own instead.
    """
    from app.tasks import oscars_previews as task_module

    rc = MagicMock()
    with patch.object(
        task_module,
        "_build_payload",
        return_value={"categories": [_category("best_picture")], "biggest_movers": []},
    ), patch(
        "app.services.llm.generate_oscars_category_preview", return_value=None
    ), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ):
        result = await task_module._refresh_oscars_previews()

    assert result["skipped"] == "no_previews_generated"
    assert result["degraded"] is True
    rc.setex.assert_not_called()


@pytest.mark.asyncio
async def test_one_failing_category_does_not_lose_the_others():
    """Per-item isolation: one bad item must never wipe the pass."""
    from app.tasks import oscars_previews as task_module

    payload = {
        "categories": [_category("best_picture"), _category("best_actor")],
        "biggest_movers": [],
    }
    rc = MagicMock()

    def flaky(name, nominees):
        if name == "Best Actor":
            raise RuntimeError("provider blew up")
        return "survived"

    with patch.object(task_module, "_build_payload", return_value=payload), patch(
        "app.services.llm.generate_oscars_category_preview", side_effect=flaky
    ), patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        result = await task_module._refresh_oscars_previews()

    assert result["published"] is True
    written = json.loads(rc.setex.call_args[0][2])["previews"]
    assert written == {"best_picture": "survived"}


@pytest.mark.asyncio
async def test_a_hung_provider_is_bounded_and_does_not_stall_the_task():
    """Each call runs in a thread under a hard wait, so a hung provider costs one
    preview and not the worker (#1280 — a soft-limit breach SIGKILLs the prefork
    pool). Patched to a hair rather than the real 15s so the test is instant."""
    import asyncio

    from app.tasks import oscars_previews as task_module

    def never_returns(name, nominees):
        import time

        time.sleep(5)
        return "too late"

    rc = MagicMock()
    with patch.object(task_module, "_GENERATE_TIMEOUT_S", 0.05), patch.object(
        task_module,
        "_build_payload",
        return_value={"categories": [_category("best_picture")], "biggest_movers": []},
    ), patch(
        "app.services.llm.generate_oscars_category_preview", side_effect=never_returns
    ), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ):
        result = await asyncio.wait_for(
            task_module._refresh_oscars_previews(), timeout=3
        )

    assert result["skipped"] == "no_previews_generated"
    rc.setex.assert_not_called()


def test_the_beat_is_wired_to_the_shared_interval():
    """The schedule reads the constant, so the interval and the TTL cannot drift."""
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["refresh-oscars-previews"]
    assert entry["task"] == "app.tasks.refresh_oscars_previews"
    assert entry["schedule"] == float(PREVIEWS_REFRESH_SECONDS)
    assert (
        entry["options"]["queue"] == "background"
    ), "an OpenAI-calling aggregation may not sit on the realtime queue"
