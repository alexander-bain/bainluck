"""Explicit, unmounted ActivityKit HTTP/2 transport for #10542.

No credential lookup, token acquisition, implicit retries, or production caller.
Use the transport directly: AsyncClient's ordinary INFO request log includes the
device token in the URL. Results contain only fixed classifications, never URLs,
headers, response bodies, or exceptions that may contain credentials.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import re
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.utils.activitykit_delivery_state import DeliveryCommand
from app.utils.activitykit_payload import MAX_PAYLOAD_BYTES


@dataclass(frozen=True)
class APNsResult:
    outcome: Literal["accepted", "retry", "unavailable", "rejected"]
    reason: str
    retry_after_seconds: int | None = None
    retry_at: datetime | None = None


class ActivityKitAPNsTransport:
    """One bounded request per dispatch; delivery state owns every retry.

    The future authorized worker supplies a current provider JWT and registered
    activity token. An APNs acceptance is not a device receipt. A 410 is a token
    invalidation signal; topic/environment/auth errors must not revoke tokens.
    """

    def __init__(
        self,
        *,
        bundle_id: str,
        environment: Literal["sandbox", "production"],
        timeout_seconds: float = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(bundle_id, str) or not re.fullmatch(
            r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", bundle_id
        ):
            raise ValueError("An explicit app bundle identity is required")
        if environment not in {"sandbox", "production"}:
            raise ValueError("An explicit APNs environment is required")
        if (
            type(timeout_seconds) not in {int, float}
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 30
        ):
            raise ValueError("Transport deadline must be in (0, 30] seconds")
        self._host = (
            "api.sandbox.push.apple.com"
            if environment == "sandbox"
            else "api.push.apple.com"
        )
        self._topic = bundle_id + ".push-type.liveactivity"
        self._timeout = timeout_seconds
        self._transport = transport or httpx.AsyncHTTPTransport(
            http2=True,
            verify=True,
            trust_env=False,
            retries=0,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )

    async def aclose(self) -> None:
        await self._bounded_close(self._transport)

    async def _bounded_close(
        self, resource: httpx.AsyncBaseTransport | httpx.Response
    ) -> None:
        try:
            async with asyncio.timeout(min(1, self._timeout)):
                await resource.aclose()
        except (TimeoutError, httpx.HTTPError):
            # Do not replace an in-progress cancellation with a cleanup error.
            # External CancelledError still propagates, including during cleanup.
            pass

    async def send(
        self,
        command: DeliveryCommand,
        *,
        activity_token: str,
        provider_token: str,
    ) -> APNsResult:
        if (
            not isinstance(activity_token, str)
            or not 2 <= len(activity_token) <= 1024
            or len(activity_token) % 2
            or not re.fullmatch(r"[0-9a-fA-F]+", activity_token)
            or not isinstance(provider_token, str)
            or len(provider_token) > 4096
            or not re.fullmatch(
                r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", provider_token
            )
        ):
            return APNsResult("rejected", "invalid_credentials")
        if (
            not isinstance(command, DeliveryCommand)
            or not command.command_id
            or not isinstance(command.push.body, bytes)
            or not 0 < len(command.push.body) <= MAX_PAYLOAD_BYTES
        ):
            return APNsResult("rejected", "invalid_command")
        headers = {
            **command.push.headers,
            "authorization": "bearer " + provider_token,
            "apns-topic": self._topic,
            "apns-id": str(
                uuid5(NAMESPACE_URL, "bainluck:activitykit:" + command.command_id)
            ),
            "content-type": "application/json",
        }
        request = httpx.Request(
            "POST",
            f"https://{self._host}/3/device/{activity_token.lower()}",
            headers=headers,
            content=command.push.body,
            extensions={
                "timeout": dict.fromkeys(
                    ("connect", "read", "write", "pool"), self._timeout
                )
            },
        )
        try:
            async with asyncio.timeout(self._timeout):
                response = await self._transport.handle_async_request(request)
                try:
                    # Do not retain/parse a server body: its status is sufficient
                    # for this bounded sender, and arbitrary body text is unsafe.
                    size = 0
                    async for chunk in response.aiter_raw():
                        size += len(chunk)
                        if size > MAX_PAYLOAD_BYTES:
                            return APNsResult("rejected", "oversized_response")
                    if response.http_version != "HTTP/2":
                        return APNsResult("rejected", "unexpected_protocol")
                    status = response.status_code
                    if status == 200:
                        return APNsResult("accepted", "apns_accepted")
                    if status == 410:
                        return APNsResult("unavailable", "token_unregistered")
                    if status == 429 or 500 <= status <= 599:
                        raw_delay = response.headers.get("retry-after", "")
                        delay = (
                            int(raw_delay)
                            if raw_delay.isascii()
                            and raw_delay.isdecimal()
                            and len(raw_delay) <= 8
                            else None
                        )
                        retry_at = None
                        if delay is None and len(raw_delay) <= 128:
                            try:
                                retry_at = parsedate_to_datetime(raw_delay)
                                retry_at = (
                                    retry_at.astimezone(timezone.utc)
                                    if retry_at.utcoffset() is not None
                                    else None
                                )
                            except (ValueError, TypeError, OverflowError):
                                pass
                        return APNsResult("retry", "apns_transient", delay, retry_at)
                    return APNsResult("rejected", "apns_rejected")
                finally:
                    await self._bounded_close(response)
        except (TimeoutError, httpx.HTTPError):
            # Includes exceptions containing request URLs. Never log or return them.
            return APNsResult("retry", "transport_unavailable")
