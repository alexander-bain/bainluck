"""Default-off suspended-phone update task; no Apple credentials at import time."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
import re

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.activitykit_apns import ActivityKitAPNsTransport
from app.services.activitykit_observation import ActivityKitObservationAdapter
from app.services.activitykit_runtime import RuntimePolicy
from app.services.activitykit_runtime_caller import run_serialized_page
from app.services.activitykit_worker import DurableActivityKitWorker
from app.tasks.base import _get_task_engine
from app.utils.activitykit_delivery_state import RetryPolicy


@dataclass(frozen=True)
class ProviderConfiguration:
    bundle_id: str
    environment: str
    team_id: str
    key_id: str
    private_key: object = field(repr=False)

    @classmethod
    def from_environment(cls, environ):
        # Explicit dedicated settings only. No filesystem/keychain discovery,
        # Firebase token reuse, sandbox fallback or inferred bundle identity.
        bundle = environ.get("ACTIVITYKIT_APNS_BUNDLE_ID", "")
        environment = environ.get("ACTIVITYKIT_APNS_ENVIRONMENT", "")
        team = environ.get("ACTIVITYKIT_APNS_TEAM_ID", "")
        key_id = environ.get("ACTIVITYKIT_APNS_KEY_ID", "")
        pem = environ.get("ACTIVITYKIT_APNS_PRIVATE_KEY", "")
        try:
            if (
                not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", bundle)
                or environment not in {"sandbox", "production"}
                or not re.fullmatch(r"[A-Z0-9]{10}", team)
                or not re.fullmatch(r"[A-Z0-9]{10}", key_id)
                or not 1 <= len(pem) <= 16384
            ):
                raise ValueError()
            signer = serialization.load_pem_private_key(pem.encode(), password=None)
            if not isinstance(signer, ec.EllipticCurvePrivateKey) or not isinstance(
                signer.curve, ec.SECP256R1
            ):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Invalid ActivityKit provider configuration") from None
        return cls(bundle, environment, team, key_id, signer)

    async def provider_token(self):
        # A fresh ES256 token per finite page; never store/log the JWT or key.
        return jwt.encode(
            {"iss": self.team_id, "iat": int(datetime.now(timezone.utc).timestamp())},
            self.private_key,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )


async def run_activitykit_runtime():
    if os.environ.get("ACTIVITYKIT_RUNTIME_ENABLED") != "true":
        return {"status": "disabled", "terminal": "skipped"}
    engine = transport = None
    result = {"status": "configuration_failed", "terminal": "failed"}
    try:
        config = ProviderConfiguration.from_environment(os.environ)
        engine = _get_task_engine(statement_timeout_ms=5000, lock_timeout_ms=2000)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        transport = ActivityKitAPNsTransport(
            bundle_id=config.bundle_id, environment=config.environment
        )
        worker = DurableActivityKitWorker(
            sessions,
            retry_policy=RetryPolicy(
                tuple(timedelta(seconds=n) for n in (30, 60, 120))
            ),
        )
        result = await run_serialized_page(
            engine,
            sessions,
            ActivityKitObservationAdapter(engine),
            worker,
            transport,
            config.provider_token,
            policy=RuntimePolicy(enabled=True),
        )
    except Exception:
        # Never pass credential-bearing exception strings to Celery/Sentry.
        result = {"status": "runtime_setup_failed", "terminal": "failed"}
    finally:
        for resource in (transport, engine):
            if resource is None:
                continue
            try:
                async with asyncio.timeout(5):
                    if resource is transport:
                        await transport.aclose()
                    else:
                        await engine.dispose()
            except Exception:
                result = {"status": "cleanup_failed", "terminal": "failed"}
    return result
