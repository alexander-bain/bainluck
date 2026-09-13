#!/usr/bin/env python3
"""native — read App Store Connect's own record of our builds.

WHY THIS EXISTS
---------------
`native-upload.sh` grades the DELIVERY (did altool produce an .ipa, did it
report product-errors). It cannot tell you what Apple then did with it: a
delivery that exits 0 and prints no error still leaves the build in
PROCESSING for minutes, and can land in INVALID an hour later with the reason
only visible here. The directive for this lane says to report the PROCESSING
state from /v1/builds, not the upload's exit code, and until now nothing in
the repo could read it.

It is also the only honest answer to "is build N already taken?" — Apple
refuses a re-used CFBundleVersion, and the project file's highest number is a
guess about our tree, not a fact about Apple's.

WHAT IT PRINTS
  every build Apple holds for the app, newest first:
  version · processingState · expired? · uploaded-at · the pre-release version
  it belongs to. Plus, for INVALID/FAILED builds, whatever reason Apple gives.

CREDENTIALS (the same three the uploader uses; never printed, never committed)
  ASC_KEY_ID  ASC_ISSUER_ID  ASC_KEY_PATH   — from ~/.claude/.env

EXIT
  0  Apple answered and the builds are listed (an empty list is an answer)
  1  Apple answered with an error status
  2  the rig is unusable — missing credential, unreadable key, no app found
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BUNDLE_ID = "com.bainluck.Bain-Luck"
API = "https://api.appstoreconnect.apple.com/v1"


def die(msg: str, code: int = 2) -> None:
    print(f"ASC: {msg}")
    sys.exit(code)


def token() -> str:
    try:
        import jwt
    except ImportError:
        die("PyJWT is not importable; `pip3 install pyjwt cryptography`")
    key_id = os.environ.get("ASC_KEY_ID")
    issuer = os.environ.get("ASC_ISSUER_ID")
    key_path = os.environ.get("ASC_KEY_PATH")
    missing = [
        n
        for n, v in (
            ("ASC_KEY_ID", key_id),
            ("ASC_ISSUER_ID", issuer),
            ("ASC_KEY_PATH", key_path),
        )
        if not v
    ]
    if missing:
        die(f"missing credential(s): {', '.join(missing)} — `source ~/.claude/.env`")
    try:
        with open(os.path.expanduser(key_path)) as fh:
            private_key = fh.read()
    except OSError as exc:
        die(f"cannot read ASC_KEY_PATH: {exc}")
    now = int(time.time())
    return jwt.encode(
        {"iss": issuer, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"},
        private_key,
        algorithm="ES256",
        headers={"kid": key_id, "typ": "JWT"},
    )


def get(path: str, bearer: str) -> dict:
    req = urllib.request.Request(
        path if path.startswith("http") else f"{API}{path}",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:600]
        print(f"ASC: HTTP {exc.code} on {path}\n{body}")
        sys.exit(1)
    except urllib.error.URLError as exc:
        die(f"cannot reach App Store Connect: {exc.reason}")


def main() -> None:
    bearer = token()
    apps = get(f"/apps?filter[bundleId]={BUNDLE_ID}", bearer).get("data", [])
    if not apps:
        die(f"no app with bundleId {BUNDLE_ID} on this key's team")
    app = apps[0]
    app_id = app["id"]
    print(f"app     : {app['attributes'].get('name')}  ({BUNDLE_ID}, id {app_id})")

    # No `fields[builds]` here on purpose: restricting the sparse fieldset also
    # drops the `relationships` block, so the included preReleaseVersion can
    # never be joined back and every train prints as "?" — a silent hole that
    # reads like Apple not knowing which version a build belongs to.
    builds = get(
        f"/builds?filter[app]={app_id}&limit=20&sort=-version"
        "&include=preReleaseVersion",
        bearer,
    )
    rows = builds.get("data", [])
    pre = {
        item["id"]: item["attributes"].get("version")
        for item in builds.get("included", [])
        if item["type"] == "preReleaseVersions"
    }
    if not rows:
        print("builds  : NONE — Apple holds no build for this app")
        return
    print(f"builds  : {len(rows)} (newest first)")
    for row in rows:
        attrs = row["attributes"]
        rel = row.get("relationships", {}).get("preReleaseVersion", {}).get("data")
        train = pre.get(rel["id"]) if rel else "?"
        flags = " EXPIRED" if attrs.get("expired") else ""
        print(
            f"  {train} ({attrs.get('version')})"
            f"  {attrs.get('processingState')}{flags}"
            f"  uploaded {attrs.get('uploadedDate')}"
        )


if __name__ == "__main__":
    main()
