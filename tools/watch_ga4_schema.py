#!/usr/bin/env python3
"""Idempotent GA4 reporting definitions for consented Watch events. No event sends.

Uses the existing GA4_PROPERTY_ID/FIREBASE_SERVICE_ACCOUNT_JSON configuration.
Default is a read-only plan. --apply creates only missing event-scoped definitions.
"""
import argparse
import base64
import json
import os
from pathlib import Path

DIMENSIONS = {
    "device_class": "Client device class",
    "surface": "Product surface",
    "app_build": "Originating app build",
    "action": "Product action",
    "outcome_class": "Operation outcome",
    "entry": "Screen entry temperature",
    "network_class": "Network class",
}
METRICS = {
    "first_card_ms": ("First content milliseconds", "MILLISECONDS"),
    "duration_ms": ("Operation milliseconds", "MILLISECONDS"),
    "transport_delay_ms": ("Companion relay milliseconds", "MILLISECONDS"),
    "card_count": ("Visible content count", "STANDARD"),
}


def plan(dimensions, metrics):
    existing_dimensions = {(v.get("parameterName"), v.get("scope")) for v in dimensions}
    existing_metrics = {(v.get("parameterName"), v.get("scope")) for v in metrics}
    result = []
    for name, display in DIMENSIONS.items():
        if (name, "EVENT") not in existing_dimensions:
            result.append(("customDimensions", {"parameterName": name, "displayName": display,
                "scope": "EVENT", "description": "Bounded diagnostics category; Watch events use device_class=watch."}))
    for name, (display, unit) in METRICS.items():
        if (name, "EVENT") not in existing_metrics:
            result.append(("customMetrics", {"parameterName": name, "displayName": display,
                "scope": "EVENT", "measurementUnit": unit,
                "description": "Watch diagnostics. Timing -1 means unmeasured; filter unknown values when reporting."}))
    return result


def credential_info(raw):
    """Match the existing GA setup input formats without logging their content."""
    value = raw.strip()
    if value.startswith("{"):
        return json.loads(value)
    if value.startswith(("/", "./", "../", "~")):
        return json.loads(Path(value).expanduser().read_text())
    return json.loads(base64.b64decode(value, validate=True).decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    prop = os.environ.get("GA4_PROPERTY_ID", "")
    if not prop.isdigit():
        raise SystemExit("A numeric GA4_PROPERTY_ID is required")
    raw = os.environ.get("GA4_ADMIN_CREDENTIALS") or os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise SystemExit("Existing GA4 credentials are not configured")
    # Never print credentials, access tokens, HTTP request headers or response bodies.
    try:
        info = credential_info(raw)
        creds = service_account.Credentials.from_service_account_info(info,
            scopes=["https://www.googleapis.com/auth/analytics.edit" if args.apply
                    else "https://www.googleapis.com/auth/analytics.readonly"])
        session = AuthorizedSession(creds)
        base = f"https://analyticsadmin.googleapis.com/v1beta/properties/{prop}/"
        def list_all(kind):
            rows, token = [], None
            while True:
                response = session.get(base + kind, params={"pageSize": 200, **({"pageToken": token} if token else {})}, timeout=20)
                if response.status_code != 200:
                    raise RuntimeError(f"GA4 {kind} read returned HTTP {response.status_code}")
                body = response.json()
                rows.extend(body.get(kind, [])); token = body.get("nextPageToken")
                if not token: return rows
        operations = plan(list_all("customDimensions"), list_all("customMetrics"))
        receipt = {"property": prop, "mode": "apply" if args.apply else "plan", "operations": []}
        for kind, body in operations:
            result = {"kind": kind, "parameter": body["parameterName"], "status": "planned"}
            if args.apply:
                response = session.post(base + kind, json=body, timeout=20)
                if response.status_code not in (200, 201):
                    result["status"] = f"failed_http_{response.status_code}"
                    receipt["operations"].append(result)
                    args.receipt.write_text(json.dumps(receipt, indent=2))
                    raise RuntimeError(f"GA4 definition write returned HTTP {response.status_code}")
                result["status"] = "created"
            receipt["operations"].append(result)
        if args.apply:
            missing = plan(list_all("customDimensions"), list_all("customMetrics"))
            receipt["readback_complete"] = not missing
            if missing: raise RuntimeError("GA4 definition readback incomplete")
        args.receipt.write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt))
    except Exception as exc:
        # Bound and redact failure reporting; provider exceptions may include secrets.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
