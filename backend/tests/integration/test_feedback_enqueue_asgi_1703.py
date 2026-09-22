"""#1703 — the reader's 200 must leave the app while a blocked publisher is
still blocked, and the rest of the app must keep serving.

Why this file exists as well as ``tests/test_feedback_enqueue.py``: every test
there stubs the broker with something that returns immediately, so "the enqueue
was scheduled, not called inline" is all they can show. The defect was never
about *whether* the publish happened — it was about how long the reader waited
for it. A stub that never blocks cannot fail the old code either.

So the measurement here is made against a publisher that genuinely blocks, and
it is taken at the ASGI boundary rather than through httpx.

  `httpx`'s ASGITransport awaits the WHOLE `app(scope, receive, send)` call
  before it hands back a response, and Starlette runs background tasks inside
  that call. A real uvicorn worker writes the body to the socket the moment
  `send` is invoked, long before the background task finishes. So an httpx
  client would report the response as arriving only after the blocked publisher
  released — measuring its own transport, not production. Driving the app
  directly and watching `send` is the only way to see what the reader sees.

Nothing here reaches a broker, a database or the network: `app.tasks` is a stub
module in `sys.modules`, the DB dependencies are overridden, and the "publish"
is a `threading.Event.wait` under a hard cap.
"""

import asyncio
import json
import sys
import threading
import types

import pytest

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

#: How long the fake publish will sit blocked before giving up. The test always
#: releases it explicitly; the cap only exists so a regression cannot hang CI.
PUBLISH_BLOCK_CAP_S = 10.0

#: Budgets for the things that must happen WHILE the publisher is blocked. Each
#: is generous by three orders of magnitude for the passing path — the response
#: is sent in milliseconds — and comfortably under the cap so a regression fails
#: rather than deadlocks.
RESPONSE_DEADLINE_S = 4.0
PUBLISHER_ENTRY_DEADLINE_S = 4.0
UNRELATED_REQUEST_DEADLINE_S = 4.0


class _BlockingPublisher:
    """A `send_task` that parks the calling thread until it is released."""

    def __init__(self):
        self.entered = threading.Event()
        self._release = threading.Event()
        self.calls = []
        self.gave_up = False

    def send_task(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.entered.set()
        if not self._release.wait(timeout=PUBLISH_BLOCK_CAP_S):
            # Recorded rather than raised: an exception in a background task
            # surfaces as a confusing secondary failure, and the assertion that
            # reads this flag says plainly what went wrong.
            self.gave_up = True

    def release(self):
        self._release.set()


@pytest.fixture
def blocking_publisher(monkeypatch):
    publisher = _BlockingPublisher()
    stub_tasks = types.ModuleType("app.tasks")
    stub_tasks.celery_app = publisher
    monkeypatch.setitem(sys.modules, "app.tasks", stub_tasks)
    try:
        yield publisher
    finally:
        # Never leave a parked thread behind, whatever the test did.
        publisher.release()


@pytest.fixture
def asgi_app(mock_db, monkeypatch):
    """The real FastAPI app — full middleware stack — with the DB stubbed out."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    async def _mock_get_db():
        yield mock_db

    async def _mock_get_optional_user():
        return None

    def _assign_id(report):
        report.id = 456

    mock_db.add = _assign_id
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def _post_scope(payload: bytes) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/feedback/bug-report",
        "raw_path": b"/api/feedback/bug-report",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"test"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode()),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }


def _get_scope(path: str) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test")],
        "client": ("127.0.0.1", 12346),
        "server": ("test", 80),
    }


class _Capture:
    """Collects ASGI `send` messages and flags the end of the response body."""

    def __init__(self):
        self.messages = []
        self.body_complete = asyncio.Event()

    async def send(self, message):
        self.messages.append(message)
        if message["type"] == "http.response.body" and not message.get(
            "more_body", False
        ):
            self.body_complete.set()

    @property
    def status(self):
        for message in self.messages:
            if message["type"] == "http.response.start":
                return message["status"]
        return None

    @property
    def body(self) -> bytes:
        return b"".join(
            m.get("body", b"")
            for m in self.messages
            if m["type"] == "http.response.body"
        )


def _receiver(payload: bytes):
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


async def test_response_is_fully_sent_while_the_publisher_is_still_blocked(
    asgi_app, blocking_publisher
):
    """The whole 200 leaves the app before the enqueue finishes (#1703).

    The old code awaited nothing and published inline, so the body could not be
    emitted until the publish returned: under this publisher the event loop
    itself would be parked and `body_complete` would not arrive inside the
    deadline.
    """
    payload = json.dumps({"description": "Something broke"}).encode()
    capture = _Capture()
    call = asyncio.create_task(
        asgi_app(_post_scope(payload), _receiver(payload), capture.send)
    )

    try:
        await asyncio.wait_for(
            capture.body_complete.wait(), timeout=RESPONSE_DEADLINE_S
        )

        # The publisher is a background task, so it starts after the send above.
        # Wait (off the loop) for it to actually be parked, so the assertions
        # below are about a genuinely blocked publish and not a race we won.
        entered = await asyncio.wait_for(
            asyncio.to_thread(
                blocking_publisher.entered.wait, PUBLISHER_ENTRY_DEADLINE_S
            ),
            timeout=PUBLISHER_ENTRY_DEADLINE_S + 1,
        )
        assert entered, "the scheduled enqueue never ran"

        # This is the whole claim: the reader has the complete response in hand
        # while the app call itself is still parked on the publish.
        assert not call.done()
        assert capture.status == 200
        assert json.loads(capture.body) == {
            "status": "ok",
            "id": 456,
            "category": "other",
        }
    finally:
        blocking_publisher.release()
        await asyncio.wait_for(call, timeout=RESPONSE_DEADLINE_S)

    assert not blocking_publisher.gave_up
    assert len(blocking_publisher.calls) == 1


async def test_an_unrelated_request_is_served_while_the_publisher_is_blocked(
    asgi_app, blocking_publisher
):
    """A parked publish does not park the event loop.

    The publish runs in Starlette's threadpool, so an unrelated request through
    the same app — full middleware stack — is served normally. Stated no larger
    than it is: this shows one blocked publisher does not stall the loop, NOT
    that concurrent requests can never be delayed. The threadpool is shared and
    finite, so enough simultaneous blocked publishes will still make other
    threadpool work queue.
    """
    payload = json.dumps({"description": "Something broke"}).encode()
    submission = _Capture()
    call = asyncio.create_task(
        asgi_app(_post_scope(payload), _receiver(payload), submission.send)
    )

    try:
        await asyncio.wait_for(
            submission.body_complete.wait(), timeout=RESPONSE_DEADLINE_S
        )
        entered = await asyncio.wait_for(
            asyncio.to_thread(
                blocking_publisher.entered.wait, PUBLISHER_ENTRY_DEADLINE_S
            ),
            timeout=PUBLISHER_ENTRY_DEADLINE_S + 1,
        )
        assert entered, "the scheduled enqueue never ran"
        assert not call.done()

        unrelated = _Capture()

        async def _empty_receive():
            return {"type": "http.disconnect"}

        await asyncio.wait_for(
            asgi_app(_get_scope("/"), _empty_receive, unrelated.send),
            timeout=UNRELATED_REQUEST_DEADLINE_S,
        )

        assert unrelated.status == 200
        assert json.loads(unrelated.body)["name"] == "Bain Luck API"
        # …and the publisher was still parked for the whole of it.
        assert not call.done()
    finally:
        blocking_publisher.release()
        await asyncio.wait_for(call, timeout=RESPONSE_DEADLINE_S)

    assert not blocking_publisher.gave_up
