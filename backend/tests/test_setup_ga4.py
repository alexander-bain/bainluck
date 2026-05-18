import pytest

from scripts.setup_ga4 import (
    AUDIENCES,
    CUSTOM_DIMENSIONS,
    KEY_EVENTS,
    ConfigError,
    load_config,
    plan_custom_dimensions,
    plan_named_resources,
)


def test_load_config_requires_property_id_and_credentials():
    with pytest.raises(ConfigError, match="GA4_PROPERTY_ID, GA4_ADMIN_CREDENTIALS"):
        load_config({})


def test_load_config_requires_numeric_property_id():
    with pytest.raises(ConfigError, match="numeric property ID"):
        load_config(
            {
                "GA4_PROPERTY_ID": "properties/123",
                "GA4_ADMIN_CREDENTIALS": "/tmp/service-account.json",
            }
        )


def test_load_config_accepts_required_env_vars():
    config = load_config(
        {
            "GA4_PROPERTY_ID": "123456789",
            "GA4_ADMIN_CREDENTIALS": "/tmp/service-account.json",
        }
    )

    assert config.property_id == "123456789"
    assert config.property_name == "properties/123456789"
    assert config.credentials == "/tmp/service-account.json"


def test_custom_dimension_plan_skips_existing_display_or_parameter_names():
    plan = plan_custom_dimensions(
        CUSTOM_DIMENSIONS,
        existing_display_names=["Sport"],
        existing_parameter_names=["league"],
    )

    actions = {operation.name: operation.action for operation in plan}
    assert actions["Sport"] == "skip"
    assert actions["League"] == "skip"
    assert actions["Event ID"] == "create"


def test_key_event_plan_is_idempotent_by_event_name():
    plan = plan_named_resources(
        "key_events",
        (spec.event_name for spec in KEY_EVENTS),
        existing_names=["sign_up", "prediction_submit"],
    )

    actions = {operation.name: operation.action for operation in plan}
    assert actions["sign_up"] == "skip"
    assert actions["prediction_submit"] == "skip"
    assert actions["challenge_start"] == "create"


def test_audience_plan_is_idempotent_by_display_name_case_insensitive():
    plan = plan_named_resources(
        "audiences",
        (spec.display_name for spec in AUDIENCES),
        existing_names=["sports enthusiasts", "Power Users"],
    )

    actions = {operation.name: operation.action for operation in plan}
    assert actions["Sports Enthusiasts"] == "skip"
    assert actions["Power Users"] == "skip"
    assert actions["Prediction Players"] == "create"
