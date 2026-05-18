#!/usr/bin/env python3
"""Idempotently configure GA4 Admin resources for Bain Luck.

Required environment:
  GA4_PROPERTY_ID=<numeric GA4 property id>
  GA4_ADMIN_CREDENTIALS=<service-account json path, raw json, or base64 json>
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


ANALYTICS_EDIT_SCOPE = "https://www.googleapis.com/auth/analytics.edit"


class ConfigError(RuntimeError):
    """Raised when required GA4 setup configuration is missing or invalid."""


class DependencyError(RuntimeError):
    """Raised when the optional GA4 Admin SDK dependency is unavailable."""


@dataclass(frozen=True)
class SetupConfig:
    property_id: str
    credentials: str

    @property
    def property_name(self) -> str:
        return f"properties/{self.property_id}"


@dataclass(frozen=True)
class CustomDimensionSpec:
    display_name: str
    parameter_name: str
    scope: str
    description: str


@dataclass(frozen=True)
class KeyEventSpec:
    event_name: str


@dataclass(frozen=True)
class AudienceSpec:
    display_name: str
    description: str
    membership_duration_days: int
    event_name: str | None = None
    dimension_name: str | None = None
    dimension_value: str | None = None


@dataclass(frozen=True)
class PlannedOperation:
    kind: str
    name: str
    action: str
    reason: str


@dataclass
class RunSummary:
    created: dict[str, list[str]]
    skipped: dict[str, list[str]]
    unsupported: dict[str, list[str]]

    @classmethod
    def empty(cls) -> "RunSummary":
        return cls(created={}, skipped={}, unsupported={})

    def add(self, action: str, kind: str, name: str) -> None:
        bucket = getattr(self, action)
        bucket.setdefault(kind, []).append(name)


CUSTOM_DIMENSIONS: tuple[CustomDimensionSpec, ...] = (
    CustomDimensionSpec(
        "Sport", "sport", "EVENT", "Sport key for event and market analytics."
    ),
    CustomDimensionSpec(
        "League", "league", "EVENT", "League key for event and market analytics."
    ),
    CustomDimensionSpec("Event ID", "event_id", "EVENT", "Bain Luck event identifier."),
    CustomDimensionSpec(
        "Event Status",
        "event_status",
        "EVENT",
        "Scheduled, live, or completed event status.",
    ),
    CustomDimensionSpec(
        "Source Section",
        "source_section",
        "EVENT",
        "UI section where the event originated.",
    ),
    CustomDimensionSpec(
        "Position Index",
        "position_index",
        "EVENT",
        "Zero-based card/list position shown to the user.",
    ),
    CustomDimensionSpec(
        "Is Live",
        "is_live",
        "EVENT",
        "Whether the event was live at interaction time.",
    ),
    CustomDimensionSpec(
        "Is Close Game",
        "is_close_game",
        "EVENT",
        "Whether the event qualified as close at interaction time.",
    ),
    CustomDimensionSpec(
        "Platform", "platform", "USER", "Client platform such as web, iOS, or macOS."
    ),
    CustomDimensionSpec(
        "App Version",
        "app_version",
        "USER",
        "Native app version for client-side analytics.",
    ),
    CustomDimensionSpec(
        "Days Since Install",
        "days_since_install",
        "USER",
        "User age in days since install or first use.",
    ),
)

KEY_EVENTS: tuple[KeyEventSpec, ...] = (
    KeyEventSpec("sign_up"),
    KeyEventSpec("onboarding_complete"),
    KeyEventSpec("event_detail_view"),
    KeyEventSpec("prediction_submit"),
    KeyEventSpec("challenge_start"),
)

AUDIENCES: tuple[AudienceSpec, ...] = (
    AudienceSpec(
        "Sports Enthusiasts",
        "Users with event_detail_view activity; intended threshold: at least 3 in 7 days.",
        7,
        event_name="event_detail_view",
    ),
    AudienceSpec(
        "NBA Fans",
        'Users engaging with NBA content; intended threshold: sport = "basketball_nba" '
        "and 5+ sessions.",
        30,
        dimension_name="customEvent:sport",
        dimension_value="basketball_nba",
    ),
    AudienceSpec(
        "Power Users",
        "Highly active users; intended threshold: 5+ sessions in 7 days.",
        7,
        event_name="session_start",
    ),
    AudienceSpec(
        "Prediction Players",
        "Users with prediction_submit activity; intended threshold: at least 3 in 7 days.",
        7,
        event_name="prediction_submit",
    ),
    AudienceSpec(
        "Discover Browsers",
        "Users browsing Discover; intended threshold: page_view on / or /discover "
        "at least 5 times in 7 days.",
        7,
        event_name="page_view",
    ),
)


def load_config(env: Mapping[str, str] | None = None) -> SetupConfig:
    env = os.environ if env is None else env
    property_id = (env.get("GA4_PROPERTY_ID") or "").strip()
    credentials = (env.get("GA4_ADMIN_CREDENTIALS") or "").strip()

    missing = [
        name
        for name, value in (
            ("GA4_PROPERTY_ID", property_id),
            ("GA4_ADMIN_CREDENTIALS", credentials),
        )
        if not value
    ]
    if missing:
        raise ConfigError(f"Missing required environment variable(s): {', '.join(missing)}")
    if not property_id.isdigit():
        raise ConfigError(
            "GA4_PROPERTY_ID must be the numeric property ID from GA4 Property Settings"
        )

    return SetupConfig(property_id=property_id, credentials=credentials)


def plan_custom_dimensions(
    desired: Iterable[CustomDimensionSpec],
    existing_display_names: Iterable[str],
    existing_parameter_names: Iterable[str],
) -> list[PlannedOperation]:
    existing_names = _normalized_set(existing_display_names)
    existing_params = _normalized_set(existing_parameter_names)
    plan: list[PlannedOperation] = []

    for spec in desired:
        if spec.display_name.casefold() in existing_names:
            plan.append(
                PlannedOperation(
                    "custom_dimensions",
                    spec.display_name,
                    "skip",
                    "display name exists",
                )
            )
        elif spec.parameter_name.casefold() in existing_params:
            plan.append(
                PlannedOperation(
                    "custom_dimensions",
                    spec.display_name,
                    "skip",
                    "parameter name exists",
                )
            )
        else:
            plan.append(
                PlannedOperation(
                    "custom_dimensions", spec.display_name, "create", "missing"
                )
            )

    return plan


def plan_named_resources(
    kind: str,
    desired_names: Iterable[str],
    existing_names: Iterable[str],
) -> list[PlannedOperation]:
    existing = _normalized_set(existing_names)
    return [
        PlannedOperation(
            kind,
            name,
            "skip" if name.casefold() in existing else "create",
            "name exists" if name.casefold() in existing else "missing",
        )
        for name in desired_names
    ]


def import_admin_sdk() -> Any:
    try:
        from google.analytics import admin_v1alpha as admin
    except ImportError as exc:
        raise DependencyError(
            "Missing dependency: google-analytics-admin. Install it in the execution environment "
            "before running backend/scripts/setup_ga4.py."
        ) from exc
    return admin


def build_client(config: SetupConfig, admin: Any) -> Any:
    try:
        from google.oauth2 import service_account
    except ImportError as exc:
        raise DependencyError(
            "Missing dependency: google-auth service account support. It is normally installed with "
            "google-analytics-admin."
        ) from exc

    info = _load_credentials_info(config.credentials)
    if info is None:
        credentials_path = Path(config.credentials).expanduser()
        if not credentials_path.exists():
            raise ConfigError(
                "GA4_ADMIN_CREDENTIALS must be an existing service-account JSON path, raw JSON, or base64 JSON"
            )
        credentials = service_account.Credentials.from_service_account_file(
            str(credentials_path),
            scopes=[ANALYTICS_EDIT_SCOPE],
        )
    else:
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=[ANALYTICS_EDIT_SCOPE],
        )

    return admin.AnalyticsAdminServiceClient(credentials=credentials)


def setup_ga4(client: Any, admin: Any, property_name: str, dry_run: bool = False) -> RunSummary:
    summary = RunSummary.empty()
    _setup_custom_dimensions(client, admin, property_name, summary, dry_run)
    _setup_key_events(client, admin, property_name, summary, dry_run)
    _setup_audiences(client, admin, property_name, summary, dry_run)
    return summary


def print_summary(summary: RunSummary) -> None:
    for action in ("created", "skipped", "unsupported"):
        print(f"\n{action.upper()}")
        bucket = getattr(summary, action)
        if not bucket:
            print("  none")
            continue
        for kind in sorted(bucket):
            names = ", ".join(bucket[kind])
            print(f"  {kind}: {names}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure GA4 Admin resources for Bain Luck.")
    parser.add_argument("--dry-run", action="store_true", help="List planned changes without creating resources.")
    args = parser.parse_args()

    try:
        config = load_config()
        admin = import_admin_sdk()
        client = build_client(config, admin)
        summary = setup_ga4(client, admin, config.property_name, dry_run=args.dry_run)
    except (ConfigError, DependencyError) as exc:
        print(f"ERROR: {exc}")
        return 2

    print_summary(summary)
    return 0


def _setup_custom_dimensions(
    client: Any, admin: Any, property_name: str, summary: RunSummary, dry_run: bool
) -> None:
    if not _has_methods(
        client, "list_custom_dimensions", "create_custom_dimension"
    ) or not hasattr(admin, "CustomDimension"):
        _mark_unsupported(
            summary,
            "custom_dimensions",
            (spec.display_name for spec in CUSTOM_DIMENSIONS),
        )
        return

    existing = list(_list_resources(client.list_custom_dimensions, parent=property_name))
    plan = plan_custom_dimensions(
        CUSTOM_DIMENSIONS,
        (getattr(item, "display_name", "") for item in existing),
        (getattr(item, "parameter_name", "") for item in existing),
    )
    specs_by_name = {spec.display_name: spec for spec in CUSTOM_DIMENSIONS}
    for operation in plan:
        if operation.action == "skip":
            summary.add("skipped", operation.kind, operation.name)
            continue
        if not dry_run:
            client.create_custom_dimension(
                parent=property_name,
                custom_dimension=_build_custom_dimension(
                    admin, specs_by_name[operation.name]
                ),
            )
        summary.add("created", operation.kind, operation.name)


def _setup_key_events(
    client: Any, admin: Any, property_name: str, summary: RunSummary, dry_run: bool
) -> None:
    methods = _key_event_methods(client, admin)
    if methods is None:
        _mark_unsupported(summary, "key_events", (spec.event_name for spec in KEY_EVENTS))
        return

    list_method_name, create_method_name, resource_type_name = methods
    existing = list(_list_resources(getattr(client, list_method_name), parent=property_name))
    plan = plan_named_resources(
        "key_events",
        (spec.event_name for spec in KEY_EVENTS),
        (getattr(item, "event_name", "") for item in existing),
    )
    resource_type = getattr(admin, resource_type_name)
    for operation in plan:
        if operation.action == "skip":
            summary.add("skipped", operation.kind, operation.name)
            continue
        if not dry_run:
            getattr(client, create_method_name)(
                parent=property_name,
                **{_snake_case(resource_type_name): resource_type(event_name=operation.name)},
            )
        summary.add("created", operation.kind, operation.name)


def _setup_audiences(
    client: Any, admin: Any, property_name: str, summary: RunSummary, dry_run: bool
) -> None:
    if not _has_methods(client, "list_audiences", "create_audience") or not hasattr(
        admin, "Audience"
    ):
        _mark_unsupported(summary, "audiences", (spec.display_name for spec in AUDIENCES))
        return

    existing = list(_list_resources(client.list_audiences, parent=property_name))
    plan = plan_named_resources(
        "audiences",
        (spec.display_name for spec in AUDIENCES),
        (getattr(item, "display_name", "") for item in existing),
    )
    specs_by_name = {spec.display_name: spec for spec in AUDIENCES}
    for operation in plan:
        if operation.action == "skip":
            summary.add("skipped", operation.kind, operation.name)
            continue
        try:
            audience = _build_audience(admin, specs_by_name[operation.name])
        except (AttributeError, TypeError, ValueError):
            summary.add("unsupported", operation.kind, operation.name)
            continue
        if not dry_run:
            client.create_audience(parent=property_name, audience=audience)
        summary.add("created", operation.kind, operation.name)


def _build_custom_dimension(admin: Any, spec: CustomDimensionSpec) -> Any:
    scope = getattr(admin.CustomDimension.DimensionScope, spec.scope)
    return admin.CustomDimension(
        display_name=spec.display_name,
        parameter_name=spec.parameter_name,
        scope=scope,
        description=spec.description,
    )


def _build_audience(admin: Any, spec: AudienceSpec) -> Any:
    filter_expression: dict[str, Any]
    if spec.dimension_name and spec.dimension_value:
        match_type = getattr(admin.AudienceDimensionOrMetricFilter.StringFilter.MatchType, "EXACT")
        filter_expression = {
            "dimension_or_metric_filter": {
                "field_name": spec.dimension_name,
                "string_filter": {
                    "match_type": match_type,
                    "value": spec.dimension_value,
                },
            }
        }
    elif spec.event_name:
        filter_expression = {"event_filter": {"event_name": spec.event_name}}
    else:
        raise ValueError("Audience spec must include an event or dimension filter")

    return admin.Audience(
        display_name=spec.display_name,
        description=spec.description,
        membership_duration_days=spec.membership_duration_days,
        filter_clauses=[
            {
                "clause_type": getattr(admin.AudienceFilterClause.AudienceClauseType, "INCLUDE"),
                "simple_filter": {
                    "scope": getattr(admin.AudienceFilterScope, "ACROSS_ALL_SESSIONS"),
                    "filter_expression": filter_expression,
                },
            }
        ],
    )


def _key_event_methods(client: Any, admin: Any) -> tuple[str, str, str] | None:
    if _has_methods(client, "list_key_events", "create_key_event") and hasattr(
        admin, "KeyEvent"
    ):
        return ("list_key_events", "create_key_event", "KeyEvent")
    if _has_methods(
        client, "list_conversion_events", "create_conversion_event"
    ) and hasattr(admin, "ConversionEvent"):
        return ("list_conversion_events", "create_conversion_event", "ConversionEvent")
    return None


def _list_resources(method: Any, **kwargs: Any) -> Iterable[Any]:
    try:
        return method(**kwargs)
    except TypeError:
        request_type = _request_type_for(method)
        if request_type is None:
            raise
        return method(request=request_type(**kwargs))


def _request_type_for(method: Any) -> Any | None:
    module = getattr(method, "__module__", "")
    name = getattr(method, "__name__", "")
    if not module or not name:
        return None
    try:
        components = module.split(".")
        root = __import__(".".join(components[:-1]), fromlist=[components[-1]])
        request_name = "".join(part.capitalize() for part in name.split("_")) + "Request"
        return getattr(root, request_name, None)
    except ImportError:
        return None


def _load_credentials_info(value: str) -> dict[str, Any] | None:
    stripped = value.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    try:
        decoded = base64.b64decode(stripped, validate=True).decode("utf-8")
    except Exception:
        return None
    if decoded.lstrip().startswith("{"):
        return json.loads(decoded)
    return None


def _normalized_set(values: Iterable[str]) -> set[str]:
    return {value.casefold() for value in values if value}


def _has_methods(obj: Any, *names: str) -> bool:
    return all(callable(getattr(obj, name, None)) for name in names)


def _mark_unsupported(summary: RunSummary, kind: str, names: Iterable[str]) -> None:
    for name in names:
        summary.add("unsupported", kind, name)


def _snake_case(name: str) -> str:
    output = []
    for index, char in enumerate(name):
        if char.isupper() and index:
            output.append("_")
        output.append(char.lower())
    return "".join(output)


if __name__ == "__main__":
    raise SystemExit(main())
