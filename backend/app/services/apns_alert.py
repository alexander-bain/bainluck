"""Direct HTTP/2 APNs plain-alert sender for 1.0.8 game alerts (#13081).

Reuses the provider ES256 JWT from ``ProviderConfiguration`` (`ACTIVITYKIT_APNS_*`)
and sends standard notifications (`apns-push-type: alert`, no Time Sensitive
interruption level per Ruling 261: A) to both main-app and App Clip topics.

No device token or provider JWT is ever logged, returned, or retained in errors.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
import json
import math
import re
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.services.activitykit_apns import APNsResult
from app.utils.activitykit_payload import MAX_PAYLOAD_BYTES

AlertTriggerKind = Literal["start", "close_late", "final"]

_TOPIC_RE = re.compile(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
_HEX_TOKEN_RE = re.compile(r"^[0-9a-fA-F]+$")
_JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class GameAlertPush:
    """One plain APNs alert payload for a pinned game (Rulings 258-261: A).

    Standard interruption level only: never sets ``interruption-level`` to
    ``time-sensitive`` (261: A). Carries ``event_id`` and ``trigger_kind`` in
    top-level userInfo so tapping opens the game page directly.
    """

    event_id: int
    trigger_kind: AlertTriggerKind
    title: str
    body: str
    command_id: str
    expiration_epoch: int

    def to_apns_dict(self) -> dict[str, object]:
        return {
            "aps": {
                "alert": {
                    "title": self.title,
                    "body": self.body,
                },
                "sound": "default",
            },
            "event_id": self.event_id,
            "trigger_kind": self.trigger_kind,
        }

    def to_apns_body(self) -> bytes:
        raw = json.dumps(
            self.to_apns_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(raw) <= MAX_PAYLOAD_BYTES:
            return raw
        # Graceful trim if an unusually long team/matchup title ever overflows 4 KB.
        trimmed_title = self.title[:160]
        trimmed_body = self.body[:240]
        return json.dumps(
            {
                "aps": {
                    "alert": {"title": trimmed_title, "body": trimmed_body},
                    "sound": "default",
                },
                "event_id": self.event_id,
                "trigger_kind": self.trigger_kind,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")


class APNsAlertTransport:
    """Bounded HTTP/2 APNs client for plain ``apns-push-type: alert`` pushes."""

    def __init__(
        self,
        *,
        environment: Literal["sandbox", "production"],
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
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
            pass

    async def send(
        self,
        push: GameAlertPush,
        *,
        device_token: str,
        topic: str,
        provider_token: str,
    ) -> APNsResult:
        if (
            not isinstance(device_token, str)
            or not 2 <= len(device_token) <= 1024
            or len(device_token) % 2
            or not _HEX_TOKEN_RE.fullmatch(device_token)
            or not isinstance(topic, str)
            or not _TOPIC_RE.fullmatch(topic)
            or not isinstance(provider_token, str)
            or len(provider_token) > 4096
            or not _JWT_RE.fullmatch(provider_token)
        ):
            return APNsResult("rejected", "invalid_credentials")
        if not isinstance(push, GameAlertPush) or not push.command_id:
            return APNsResult("rejected", "invalid_command")
        body = push.to_apns_body()
        if not 0 < len(body) <= MAX_PAYLOAD_BYTES:
            return APNsResult("rejected", "invalid_command")

        headers = {
            "authorization": "bearer " + provider_token,
            "apns-push-type": "alert",
            "apns-priority": "10",
            "apns-topic": topic,
            "apns-expiration": str(max(0, int(push.expiration_epoch))),
            "apns-id": str(
                uuid5(NAMESPACE_URL, "bainluck:game-alert:" + push.command_id)
            ),
            "content-type": "application/json",
        }
        request = httpx.Request(
            "POST",
            f"https://{self._host}/3/device/{device_token.lower()}",
            headers=headers,
            content=body,
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
            return APNsResult("retry", "transport_unavailable")


class EnvAPNsAlertTransportPool:
    """Lazily holds up to two HTTP/2 APNs alert transports: production and sandbox."""

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds
        self._transports: dict[str, APNsAlertTransport] = {}

    def for_env(self, apns_env: str) -> APNsAlertTransport:
        env: Literal["sandbox", "production"] = (
            "sandbox" if apns_env == "sandbox" else "production"
        )
        transport = self._transports.get(env)
        if transport is None:
            transport = APNsAlertTransport(
                environment=env,
                timeout_seconds=self._timeout,
            )
            self._transports[env] = transport
        return transport

    async def aclose(self) -> None:
        for transport in self._transports.values():
            await transport.aclose()
        self._transports.clear()
