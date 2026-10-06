"""HTTP wire behavior through fake transport only; never contact Apple."""

import asyncio
from datetime import datetime, timezone
import logging

import httpx
import pytest

from app.services.activitykit_apns import ActivityKitAPNsTransport
from app.utils.activitykit_delivery_state import DeliveryCommand
from app.utils.activitykit_payload import GameActivitySnapshot, build_activitykit_update

TOKEN = "ab" * 32
JWT = "header.payload.signature"


def command():
    push = build_activitykit_update(
        GameActivitySnapshot(42, "Home", "Away", "live", home_rendered_percent=60),
        sent_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
    )
    return DeliveryCommand("one-activity:1:123:update", "update", push)


def response(status=200, *, headers=None, content=b"", protocol=b"HTTP/2"):
    return httpx.Response(
        status,
        headers=headers,
        stream=httpx.ByteStream(content),
        extensions={"http_version": protocol},
    )


def sender(handler, **kwargs):
    return ActivityKitAPNsTransport(
        bundle_id="com.example.bainluck",
        environment="sandbox",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


async def send(service, value=None, **kwargs):
    return await service.send(
        value or command(),
        activity_token=kwargs.get("token", TOKEN),
        provider_token=kwargs.get("jwt", JWT),
    )


async def test_exact_wire_stable_retry_identity_no_source_clock_changes_or_secret_logs(
    caplog,
):
    requests = []

    def handle(request):
        requests.append(request)
        return response()

    caplog.set_level(logging.DEBUG)
    service = sender(handle)
    value = command()
    assert (await send(service, value)).outcome == "accepted"
    assert (await send(service, value)).outcome == "accepted"
    first, second = requests
    assert first.method == "POST"
    assert first.url.host == "api.sandbox.push.apple.com"
    assert first.url.path == "/3/device/" + TOKEN
    assert first.headers["authorization"] == "bearer " + JWT
    assert first.headers["apns-topic"] == "com.example.bainluck.push-type.liveactivity"
    assert first.headers["apns-id"] == second.headers["apns-id"]
    assert first.headers["apns-push-type"] == "liveactivity"
    assert first.headers["apns-priority"] == "5"
    assert first.headers["apns-expiration"] == "0"
    assert first.content == second.content == value.push.body
    assert TOKEN not in caplog.text and JWT not in caplog.text
    await service.aclose()


@pytest.mark.parametrize(
    "status,outcome",
    [
        (200, "accepted"),
        (410, "unavailable"),
        (400, "rejected"),
        (403, "rejected"),
        (404, "rejected"),
        (302, "rejected"),
        (429, "retry"),
        (500, "retry"),
        (503, "retry"),
    ],
)
async def test_classification_does_not_revoke_for_configuration_error_or_follow_redirect(
    status, outcome
):
    seen = []

    def handle(request):
        seen.append(request)
        return response(
            status, headers={"location": "https://example.org/"}, content=TOKEN.encode()
        )

    result = await send(sender(handle))
    assert result.outcome == outcome
    assert TOKEN not in repr(result)
    assert len(seen) == 1


@pytest.mark.parametrize(
    "raw,seconds,date",
    [
        ("120", 120, None),
        (
            "Mon, 05 Oct 2026 20:30:00 GMT",
            None,
            datetime(2026, 10, 5, 20, 30, tzinfo=timezone.utc),
        ),
        ("secret-token", None, None),
        ("-1", None, None),
    ],
)
async def test_retry_after_is_preserved_without_changing_observation_dates(
    raw, seconds, date
):
    result = await send(
        sender(lambda request: response(429, headers={"retry-after": raw}))
    )
    assert result.retry_after_seconds == seconds and result.retry_at == date


@pytest.mark.parametrize(
    "kwargs", [{"token": "../token"}, {"jwt": "secret\nheader"}, {"token": "ab1"}]
)
async def test_invalid_credential_never_reaches_transport(kwargs):
    def forbidden(request):
        pytest.fail("invalid credentials reached transport")

    result = await send(sender(forbidden), **kwargs)
    assert result.reason == "invalid_credentials"


async def test_transport_error_containing_credentials_is_sanitized(caplog):
    def fail(request):
        raise httpx.ReadTimeout(TOKEN + JWT + str(request.url), request=request)

    result = await send(sender(fail))
    assert result.outcome == "retry"
    assert TOKEN not in repr(result) + caplog.text
    assert JWT not in repr(result) + caplog.text


async def test_deadline_and_external_cancellation_are_distinct():
    async def hang(request):
        await asyncio.Event().wait()

    service = sender(hang, timeout_seconds=0.01)
    assert (await send(service)).reason == "transport_unavailable"
    task = asyncio.create_task(send(sender(hang)))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_oversized_response_and_http1_are_not_acceptance():
    assert (
        await send(sender(lambda request: response(content=b"x" * 4097)))
    ).reason == "oversized_response"
    assert (
        await send(sender(lambda request: response(protocol=b"HTTP/1.1")))
    ).reason == "unexpected_protocol"


async def test_response_and_pool_cleanup_are_bounded():
    class SlowClose(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b""

        async def aclose(self):
            await asyncio.Event().wait()

    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(
                200, stream=SlowClose(), extensions={"http_version": b"HTTP/2"}
            )

        async def aclose(self):
            await asyncio.Event().wait()

    service = ActivityKitAPNsTransport(
        bundle_id="com.example.app",
        environment="production",
        timeout_seconds=0.01,
        transport=SlowTransport(),
    )
    assert (await asyncio.wait_for(send(service), timeout=0.2)).outcome == "retry"
    await asyncio.wait_for(service.aclose(), timeout=0.2)


async def test_cancelled_read_remains_cancelled_when_response_cleanup_times_out():
    reading = asyncio.Event()

    class HangingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            reading.set()
            await asyncio.Event().wait()
            yield b"unreachable"

        async def aclose(self):
            await asyncio.Event().wait()

    service = sender(
        lambda request: httpx.Response(
            200, stream=HangingStream(), extensions={"http_version": b"HTTP/2"}
        ),
        timeout_seconds=0.03,
    )
    task = asyncio.create_task(send(service))
    await reading.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"environment": "other"},
        {"bundle_id": "bad/path"},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": True},
    ],
)
def test_configuration_requires_explicit_bounded_safe_values(kwargs):
    with pytest.raises(ValueError):
        ActivityKitAPNsTransport(
            **{"bundle_id": "com.example.app", "environment": "production", **kwargs}
        )
