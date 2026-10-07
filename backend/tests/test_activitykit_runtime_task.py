"""Default-safe scheduling and explicit provider configuration; no APNs I/O."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

module = importlib.import_module("app.tasks.activitykit_runtime")


@pytest.fixture
def provider():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "ACTIVITYKIT_APNS_BUNDLE_ID": "com.example.test",
        "ACTIVITYKIT_APNS_ENVIRONMENT": "sandbox",
        "ACTIVITYKIT_APNS_TEAM_ID": "ABCDEFGHIJ",
        "ACTIVITYKIT_APNS_KEY_ID": "0123456789",
        "ACTIVITYKIT_APNS_PRIVATE_KEY": pem,
    }


@pytest.mark.asyncio
async def test_provider_signs_es256_with_explicit_identity_and_no_secret_repr(provider):
    config = module.ProviderConfiguration.from_environment(provider)
    token = await config.provider_token()
    claims = jwt.decode(token, config.private_key.public_key(), algorithms=["ES256"])
    assert claims["iss"] == "ABCDEFGHIJ"
    assert type(claims["iat"]) is int
    assert jwt.get_unverified_header(token)["kid"] == "0123456789"
    assert provider["ACTIVITYKIT_APNS_PRIVATE_KEY"] not in repr(config)


@pytest.mark.parametrize(
    "key", ["BUNDLE_ID", "ENVIRONMENT", "TEAM_ID", "KEY_ID", "PRIVATE_KEY"]
)
def test_missing_provider_setting_refuses_activation(provider, key):
    provider.pop("ACTIVITYKIT_APNS_" + key)
    with pytest.raises(ValueError, match="Invalid ActivityKit provider configuration"):
        module.ProviderConfiguration.from_environment(provider)


def test_wrong_curve_and_invalid_environment_refused(provider):
    key = ec.generate_private_key(ec.SECP384R1())
    provider["ACTIVITYKIT_APNS_PRIVATE_KEY"] = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    with pytest.raises(ValueError):
        module.ProviderConfiguration.from_environment(provider)
    provider["ACTIVITYKIT_APNS_ENVIRONMENT"] = "automatic"
    with pytest.raises(ValueError):
        module.ProviderConfiguration.from_environment(provider)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "false", "1", "TRUE", "yes"])
async def test_default_off_has_no_database_credentials_or_transport(monkeypatch, value):
    monkeypatch.delenv("ACTIVITYKIT_RUNTIME_ENABLED", raising=False)
    if value is not None:
        monkeypatch.setenv("ACTIVITYKIT_RUNTIME_ENABLED", value)
    factory = Mock(side_effect=AssertionError("must not construct"))
    monkeypatch.setattr(module, "_get_task_engine", factory)
    monkeypatch.setattr(module, "ActivityKitAPNsTransport", factory)
    assert (await module.run_activitykit_runtime())["status"] == "disabled"
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_enabled_composes_and_closes_owned_resources(monkeypatch, provider):
    for k, v in provider.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ACTIVITYKIT_RUNTIME_ENABLED", "true")
    engine = SimpleNamespace(dispose=AsyncMock())
    transport = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr(module, "_get_task_engine", Mock(return_value=engine))
    monkeypatch.setattr(module, "async_sessionmaker", Mock(return_value="sessions"))
    monkeypatch.setattr(
        module, "ActivityKitAPNsTransport", Mock(return_value=transport)
    )
    page = AsyncMock(return_value={"status": "complete", "terminal": "complete"})
    monkeypatch.setattr(module, "run_serialized_page", page)
    assert (await module.run_activitykit_runtime())["terminal"] == "complete"
    args = page.call_args.args
    assert args[0] is engine and args[4] is transport
    assert args[3].sessions == "sessions"
    assert [d.total_seconds() for d in args[3].retry_policy.delays] == [30, 60, 120]
    assert page.call_args.kwargs["policy"].enabled is True
    engine.dispose.assert_awaited_once()
    transport.aclose.assert_awaited_once()


def test_schedule_is_registered_bounded_and_partial_result_fails_task(monkeypatch):
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.deliver_activitykit_updates"]
    schedule = celery_app.conf.beat_schedule["activitykit-runtime"]
    assert schedule["task"] == task.name
    assert schedule["schedule"] == 30
    assert schedule["options"] == {"queue": "realtime", "expires": 25}
    assert (task.soft_time_limit, task.time_limit, task.max_retries) == (150, 180, 0)
    monkeypatch.setattr(
        module,
        "run_activitykit_runtime",
        AsyncMock(return_value={"status": "partial_failure", "terminal": "partial"}),
    )
    with pytest.raises(RuntimeError, match="ActivityKit runtime incomplete"):
        task.run()
