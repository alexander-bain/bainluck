"""#10090 — one bounded Heroku Platform API call. Token from ~/.netrc, never printed.

usage: heroku_api.py METHOD PATH [JSON_BODY] [JSON_EXTRA_HEADERS]
Prints the HTTP status on line 1 and the JSON response after it.

A config-vars response carries every secret on the app, so it is REDACTED in memory before anything is printed:
only the non-secret settings named in `NON_SECRET` keep their values (docs/live-settings.md lists them); every
other key is counted, never shown.
"""
import json
import netrc
import os
import sys
import urllib.error
import urllib.request

NON_SECRET = (
    "SPEED_SWITCH_TRIALS", "LIVE_BLEND_PREVIEW_RESERVATIONS", "LIVE_BLEND_PREVIEW_MAX_UNCOMMITTED_S",
    "PREVIEW_AT_RECEIPT_VENUES", "POLYMARKET_WS_OPEN_SCOPE", "VENUE_POLL_30S_ENABLED", "VENUE_POLL_30S_PM_SOURCE",
    "PM_WS_REPEAT_SKIP_MS", "PM_WS_UPCOMING_HOURS", "PM_WS_PROPS_TO_POLL", "STAMP_HELD_OWED_FRESH",
    "ADMITTED_LIVE_BATCH", "ADMITTED_STAMP_BATCH", "STAMP_WRITE_UNDER_QUEUED", "FEED_SPORTS_METADATA_REUSE",
    "BUSY_DB_DEFER_HEAVY_SCANS", "WS_CONSUMER_POOL_PRE_PING", "PM_WS_BLEND_FLOOR_SECONDS",
    "FRESH_FLUSH_PENDING_ATTEMPTS", "KALSHI_WS_DIRECT_BOOK", "KALSHI_WS_PRICE_FLUSH_SECONDS",
    "PM_WS_PRICE_FLUSH_SECONDS", "CONTAINERS_READ_ENABLED", "CONTAINER_COLLECTIONS_ENABLED", "COLLECTIONS_ENABLED",
    "CONTAINER_DISCOVERY_ENABLED", "SPEED_SWITCH_TODAY_PREVIEW_AT_RECEIPT", "SPEED_SWITCH_TODAY_HANDOVER_FRESH",
    "SPEED_SWITCH_TODAY_OWED_PAST_WITHDRAWAL",
)


def token() -> str:
    return netrc.netrc(os.path.expanduser("~/.netrc")).authenticators("api.heroku.com")[2]


def call(method: str, path: str, body=None, extra=None):
    headers = {"Accept": "application/vnd.heroku+json; version=3", "Authorization": "Bearer " + token()}
    if extra:
        headers.update(extra)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request("https://api.heroku.com" + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code, out = r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        code, out = e.code, {"http_error": e.code, "body": e.read().decode()[:500]}
    if path.rstrip("/").endswith("/config-vars"):
        if isinstance(out, dict) and "http_error" not in out:
            out = {"redacted_key_count": len(out), **{k: out[k] for k in NON_SECRET if k in out}}
        else:
            out = {"http_error": code, "body": "(redacted)"}
    return code, out


if __name__ == "__main__":
    method, path = sys.argv[1], sys.argv[2]
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
    extra = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
    code, out = call(method, path, body, extra)
    print(code)
    print(json.dumps(out, indent=1))
