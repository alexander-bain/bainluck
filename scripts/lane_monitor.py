#!/usr/bin/env python3
"""Bounded, read-only collection outside the model sandbox. Exit 75: no new work."""

import hashlib
import json
import datetime as dt
import subprocess
from pathlib import Path
import sys
import time
import urllib.request

URLS = {
    "health": "https://api.bainluck.com/health",
    "calibration": "https://api.bainluck.com/api/calibration",
    "discover": "https://api.bainluck.com/api/feed?limit=40",
    "sports": "https://api.bainluck.com/api/feed?mode=sports&limit=40",
}


def heavy_release():
    result = subprocess.run(
        ["heroku", "releases", "--app", "bainluck-heavy", "--num", "1", "--json"],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    releases = json.loads(result.stdout)
    if not isinstance(releases, list) or not releases:
        raise ValueError("No heavy release returned")
    return {
        k: releases[0].get(k)
        for k in ("version", "description", "status", "created_at")
    }


def collect(root, fetch=None, heavy_fetch=heavy_release):
    root.mkdir(parents=True, exist_ok=True)
    now = time.time()
    state_path = root / "state.json"
    old = json.loads(state_path.read_text()) if state_path.exists() else {}
    if now - old.get("checked_at", 0) < 300:
        return 75

    def get(url):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "BainLuck-fleet-monitor/1",
                "X-Bainluck-Origin": "measurement",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                raise ValueError("response exceeds bounded collection limit")
            return json.loads(raw)

    fetch = fetch or get
    data, errors = {}, {}
    for name, url in URLS.items():
        try:
            data[name] = fetch(url)
        except Exception as exc:
            errors[name] = str(exc)[:300]
    try:
        data["heavy"] = heavy_fetch()
    except Exception as exc:
        errors["heavy"] = str(exc)[:300]
    snapshot = {"collected_at": now, "urls": URLS, "data": data, "errors": errors}
    snapshot_path = root / "latest.json"
    snapshot_path.write_text(json.dumps(snapshot))

    # A changed release, new feed membership/state or recovery deserves interpretation.
    # Price/timestamp-only churn does not. Calibration raw data remains available.
    def stable(value):
        if isinstance(value, dict):
            result = {
                k: stable(v)
                for k, v in value.items()
                if k
                in {
                    "id",
                    "event_id",
                    "market_id",
                    "status",
                    "items",
                    "cards",
                    "events",
                    "feed",
                    "type",
                    "commit",
                    "version",
                    "description",
                    "data",
                    "state",
                    "is_resolved",
                    "is_completed",
                    "discover_marquee_final",
                }
            }
            if value.get("resolution_date"):
                try:
                    resolution = dt.datetime.fromisoformat(
                        str(value["resolution_date"]).replace("Z", "+00:00")
                    )
                    result["past_resolution"] = resolution.timestamp() < now
                except (ValueError, TypeError):
                    result["past_resolution"] = "unknown"
            return result
        if isinstance(value, list):
            return [stable(v) for v in value[:100]]
        return value

    fingerprint = hashlib.sha256(
        json.dumps(
            {k: stable(v) for k, v in data.items() if k != "calibration"},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    result = {
        "checked_at": now,
        "fingerprint": fingerprint,
        "unavailable": bool(errors),
    }
    state_path.write_text(json.dumps(result))
    if errors:
        print(
            "Monitoring unavailable: "
            + "; ".join(f"{k}: {v}" for k, v in errors.items())
        )
        return 69
    if old.get("reviewed_fingerprint") == fingerprint and not old.get("unavailable"):
        result["reviewed_fingerprint"] = fingerprint
        state_path.write_text(json.dumps(result))
        print(
            "Collection healthy; no new release or feed membership/state. No model needed."
        )
        return 75
    print("New monitoring input: " + str(snapshot_path))
    return 0


def acknowledge(root):
    p = root / "state.json"
    d = json.loads(p.read_text())
    d["reviewed_fingerprint"] = d["fingerprint"]
    p.write_text(json.dumps(d))


if __name__ == "__main__":
    root = Path(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2] == "ack":
        acknowledge(root)
    else:
        sys.exit(collect(root))
