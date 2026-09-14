#!/usr/bin/env python3
"""native — read App Store Connect's own record of whether we could SUBMIT today.

WHY THIS EXISTS
---------------
`asc-builds.py` answers "what does Apple hold?" for BINARIES. It cannot answer
the question the ship actually turns on. Uploading build 9 puts a binary at
Apple; a binary is not a submission. A submission also needs a version record
in an editable state with that build attached, per-locale description and
keywords, screenshots whose ASSETS have finished uploading, a review contact, a
primary category, an age-rating declaration and a privacy-policy URL. Any one
missing is a hard stop that otherwise surfaces only when a human presses Submit
— and the expensive ones (screenshots) cost Alex real time to produce, so
finding them out AFTER the binary lands wastes exactly the lead time that
knowing early would buy.

So this prints every gate with a PASS/GAP verdict, measured from Apple's record
rather than assumed. A clean run is a real answer: it says the only thing
between us and a submission is a processed build.

THE TRAP THIS TOOL EXISTS TO NOT FALL INTO (measured 2026-09-14, native/157)
---------------------------------------------------------------------------
Apple holds a SEPARATE appStoreVersion PER PLATFORM and they sit in DIFFERENT
states. This app has three 1.0 records — IOS, MAC_OS and VISION_OS. Asking for
"the newest editable version" without naming a platform answered for MAC_OS,
which is an empty shell, and reported four GAPs (no build, no text, no
screenshots, no review contact) that are all FALSE of the iOS record we
actually ship. A wrong-platform answer does not look wrong; it looks like a
blocker list. Hence `pick_version` takes the platform as an argument and the
platform is printed on every run, never defaulted silently.

Same shape for screenshots: a screenshot ROW can exist while its bytes are
still uploading or have failed. `assetDeliveryState.state == "COMPLETE"` is the
only state that submits, so the count is COMPLETE/total and never just total.

READ-ONLY: every call is a GET. Nothing here creates, edits or submits.

USAGE
  python3 tools/asc-submission-readiness.py [IOS|MAC_OS|VISION_OS]   (default IOS)
  python3 tools/asc-submission-readiness.py --self-check   (no network; grades
      the pure verdict logic against fixtures, including the platform trap)

CREDENTIALS  ASC_KEY_ID  ASC_ISSUER_ID  ASC_KEY_PATH  — from ~/.claude/.env,
which holds them as SHELL vars and does NOT export them: a child process needs
`set -a; source ~/.claude/.env; set +a` or it reads them ABSENT and the missing
credential is misread as a broken key.

EXIT
  0  Apple answered and every gate read PASS (or --self-check passed)
  1  Apple answered and at least one gate read GAP (or --self-check failed)
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

# States in which a version record can still take a build and be submitted.
# A version that is READY_FOR_SALE or REPLACED_WITH_NEW_VERSION is history.
EDITABLE_STATES = {
    "PREPARE_FOR_SUBMISSION",
    "DEVELOPER_REJECTED",
    "REJECTED",
    "METADATA_REJECTED",
    "WAITING_FOR_REVIEW",
    "IN_REVIEW",
    "INVALID_BINARY",
}

GAPS: list[str] = []


def die(msg: str, code: int = 2) -> None:
    print(f"ASC: {msg}")
    sys.exit(code)


def verdict(gate: str, ok: bool, detail: str) -> None:
    print(f"  [{'PASS' if ok else 'GAP '}] {gate:<24} {detail}")
    if not ok:
        GAPS.append(gate)


# ---------------------------------------------------------------------------
# pure verdict logic — no network, exercised by --self-check
# ---------------------------------------------------------------------------
def pick_version(rows: list[dict], platform: str) -> dict | None:
    """The version record for THIS platform, preferring an editable one.

    Never falls back to another platform: answering for the wrong platform is
    worse than answering "none", because it looks like a blocker list.
    """
    mine = [r for r in rows if r.get("attributes", {}).get("platform") == platform]
    if not mine:
        return None
    for r in mine:
        if r["attributes"].get("appStoreState") in EDITABLE_STATES:
            return r
    return mine[0]


def text_verdict(attrs: dict) -> tuple[bool, str]:
    desc = (attrs.get("description") or "").strip()
    kw = (attrs.get("keywords") or "").strip()
    missing = [n for n, v in (("description", desc), ("keywords", kw)) if not v]
    detail = f"description {len(desc)} chars, keywords {len(kw)} chars"
    if missing:
        detail += f" — MISSING {', '.join(missing)}"
    return not missing, detail


def screenshot_verdict(ids: list[str], shots: dict) -> tuple[bool, str]:
    """COMPLETE/total, because a row can exist while its bytes are not there."""
    states = [
        (shots.get(i, {}).get("assetDeliveryState") or {}).get("state") for i in ids
    ]
    done = sum(1 for st in states if st == "COMPLETE")
    return bool(ids) and done == len(ids), f"{done}/{len(ids)} COMPLETE"


def contact_verdict(attrs: dict) -> tuple[bool, str]:
    needed = ("contactFirstName", "contactLastName", "contactEmail", "contactPhone")
    missing = [n for n in needed if not (attrs.get(n) or "").strip()]
    return not missing, "complete" if not missing else f"MISSING {', '.join(missing)}"


# ---------------------------------------------------------------------------
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
        die(
            f"missing credential(s): {', '.join(missing)} — these live in "
            "~/.claude/.env UNEXPORTED; run `set -a; source ~/.claude/.env; set +a`"
        )
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


def get(path: str, bearer: str, soft: bool = False) -> dict:
    """GET a path.

    `soft` returns the error instead of exiting: Apple 404s the sub-resources
    that simply do not exist yet (a version with no review detail), and that is
    a GAP to report, not a rig failure.
    """
    req = urllib.request.Request(
        path if path.startswith("http") else f"{API}{path}",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:400]
        if soft:
            return {"_http_error": exc.code, "_body": body}
        print(f"ASC: HTTP {exc.code} on {path}\n{body}")
        sys.exit(1)
    except urllib.error.URLError as exc:
        die(f"cannot reach App Store Connect: {exc.reason}")


PLATFORMS = ("IOS", "MAC_OS", "VISION_OS", "TV_OS")


def main() -> None:
    platform = (sys.argv[1] if len(sys.argv) > 1 else "IOS").upper()
    if platform not in PLATFORMS:
        die(f"unknown platform {platform!r} — one of {', '.join(PLATFORMS)}")
    bearer = token()
    apps = get(f"/apps?filter[bundleId]={BUNDLE_ID}", bearer).get("data", [])
    if not apps:
        die(f"no app with bundleId {BUNDLE_ID} on this key's team")
    app = apps[0]
    app_id = app["id"]
    print(f"app      : {app['attributes'].get('name')}  ({BUNDLE_ID}, id {app_id})")
    print(f"platform : {platform}")

    versions = get(
        f"/apps/{app_id}/appStoreVersions?limit=10&include=build", bearer
    )
    rows = versions.get("data", [])
    print(f"\nversion records Apple holds ({len(rows)}):")
    for row in rows:
        a = row["attributes"]
        mark = "*" if a.get("platform") == platform else " "
        print(
            f" {mark} {a.get('versionString')}  {a.get('appStoreState')}"
            f"  platform={a.get('platform')}"
        )

    target = pick_version(rows, platform)
    if target is None:
        print(f"\nno {platform} version record exists — nothing to submit a build into")
        verdict("version record", False, f"no appStoreVersion for {platform}")
        summarize()
        return

    vid = target["id"]
    vstate = target["attributes"].get("appStoreState")
    vstring = target["attributes"].get("versionString")
    print(f"\ngates for {platform} {vstring} ({vstate}):")
    verdict("version record", vstate in EDITABLE_STATES, f"{vstring} is {vstate}")

    build_rel = target.get("relationships", {}).get("build", {}).get("data")
    if build_rel:
        binc = {
            i["id"]: i for i in versions.get("included", []) if i["type"] == "builds"
        }
        b = binc.get(build_rel["id"], {}).get("attributes", {})
        verdict(
            "build attached", True, f"build {b.get('version')} ({b.get('processingState')})"
        )
    else:
        verdict("build attached", False, "no build attached to this version")

    locs = get(
        f"/appStoreVersions/{vid}/appStoreVersionLocalizations", bearer, soft=True
    )
    ldata = locs.get("data", [])
    if not ldata:
        verdict("version text", False, "no localizations on this version")
    for loc in ldata:
        lo = loc["attributes"].get("locale")
        ok, detail = text_verdict(loc["attributes"])
        verdict(f"version text [{lo}]", ok, detail)

        sets = get(
            f"/appStoreVersionLocalizations/{loc['id']}/appScreenshotSets"
            "?include=appScreenshots",
            bearer,
            soft=True,
        )
        sdata = sets.get("data", [])
        if not sdata:
            verdict(f"screenshots [{lo}]", False, "no screenshot sets")
            continue
        shots = {
            i["id"]: i["attributes"]
            for i in sets.get("included", [])
            if i["type"] == "appScreenshots"
        }
        for s in sdata:
            dtype = s["attributes"].get("screenshotDisplayType")
            ids = [
                d["id"]
                for d in (
                    s.get("relationships", {}).get("appScreenshots", {}).get("data")
                    or []
                )
            ]
            ok, detail = screenshot_verdict(ids, shots)
            verdict(f"screenshots [{lo}]", ok, f"{dtype}: {detail}")

    rd = get(f"/appStoreVersions/{vid}/appStoreReviewDetail", bearer, soft=True)
    if rd.get("_http_error") or not rd.get("data"):
        verdict("review contact", False, "no appStoreReviewDetail record")
    else:
        ok, detail = contact_verdict(rd["data"]["attributes"])
        verdict("review contact", ok, detail)

    infos = get(
        f"/apps/{app_id}/appInfos?include=primaryCategory,ageRatingDeclaration",
        bearer,
        soft=True,
    )
    idata = infos.get("data", [])
    if not idata:
        verdict("app info", False, "no appInfo record")
    else:
        info = idata[0]
        rels = info.get("relationships", {})
        prim = rels.get("primaryCategory", {}).get("data")
        verdict("primary category", bool(prim), prim["id"] if prim else "unset")
        age = rels.get("ageRatingDeclaration", {}).get("data")
        verdict("age rating", bool(age), "declared" if age else "not declared")

        ilocs = get(f"/appInfos/{info['id']}/appInfoLocalizations", bearer, soft=True)
        for il in ilocs.get("data", []):
            a = il["attributes"]
            lo = a.get("locale")
            name = (a.get("name") or "").strip()
            priv = (a.get("privacyPolicyUrl") or "").strip()
            verdict(
                f"name+privacy [{lo}]",
                bool(name) and bool(priv),
                f"name={name or 'MISSING'} privacyPolicyUrl="
                f"{'set' if priv else 'MISSING'}",
            )

    # App Review's own record of the last submission. Not a gate — the public
    # API does not expose Resolution Center message text — but an UNRESOLVED
    # submission is the difference between "upload and submit" and "upload,
    # then read Apple's rejection first", so it is never left unsaid.
    subs = m_reviewsubs(app_id, platform, bearer)
    print("\nlast App Review submission:")
    if not subs:
        print("  none on record for this platform")
    for s in subs:
        a = s["attributes"]
        print(f"  state={a.get('state')}  submitted={a.get('submittedDate')}")
        if a.get("state") in {"UNRESOLVED_ISSUES", "REJECTED"}:
            print(
                "  ^ the reason is Resolution-Center-only (not in the public API)"
                " — a human must read it in App Store Connect before resubmitting"
            )

    summarize()


def m_reviewsubs(app_id: str, platform: str, bearer: str) -> list[dict]:
    rs = get(
        f"/apps/{app_id}/reviewSubmissions?filter[platform]={platform}&limit=5",
        bearer,
        soft=True,
    )
    return [] if rs.get("_http_error") else rs.get("data", [])


def summarize() -> None:
    print()
    if GAPS:
        print(f"VERDICT: {len(GAPS)} GAP(s) — {', '.join(GAPS)}")
        sys.exit(1)
    print("VERDICT: every gate PASS — a processed build is the only thing missing")
    sys.exit(0)


# ---------------------------------------------------------------------------
def self_check() -> None:
    """Grade the pure verdict logic offline. Each case asserts BOTH directions
    so a predicate that always returns the same answer cannot pass."""
    failures: list[str] = []

    def check(name: str, got, want) -> None:
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    # The platform trap: the MAC_OS shell sorts first and is editable, so a
    # platform-blind pick returns it. pick_version must return the IOS row.
    rows = [
        {"id": "mac", "attributes": {"platform": "MAC_OS", "appStoreState": "PREPARE_FOR_SUBMISSION"}},
        {"id": "vis", "attributes": {"platform": "VISION_OS", "appStoreState": "PREPARE_FOR_SUBMISSION"}},
        {"id": "ios", "attributes": {"platform": "IOS", "appStoreState": "REJECTED"}},
    ]
    check("pick_version IOS", pick_version(rows, "IOS")["id"], "ios")
    check("pick_version MAC_OS", pick_version(rows, "MAC_OS")["id"], "mac")
    check("pick_version absent platform", pick_version(rows, "TV_OS"), None)
    # Prefers the editable record over a historical one on the same platform.
    hist = [
        {"id": "old", "attributes": {"platform": "IOS", "appStoreState": "READY_FOR_SALE"}},
        {"id": "new", "attributes": {"platform": "IOS", "appStoreState": "PREPARE_FOR_SUBMISSION"}},
    ]
    check("pick_version prefers editable", pick_version(hist, "IOS")["id"], "new")

    check("text full", text_verdict({"description": "d", "keywords": "k"})[0], True)
    check("text no desc", text_verdict({"description": "", "keywords": "k"})[0], False)
    check("text whitespace-only", text_verdict({"description": "   ", "keywords": "k"})[0], False)
    check("text no keywords", text_verdict({"description": "d", "keywords": None})[0], False)

    shots = {
        "a": {"assetDeliveryState": {"state": "COMPLETE"}},
        "b": {"assetDeliveryState": {"state": "UPLOAD_COMPLETE"}},
    }
    check("shots all complete", screenshot_verdict(["a"], shots)[0], True)
    check("shots one pending", screenshot_verdict(["a", "b"], shots)[0], False)
    check("shots empty set", screenshot_verdict([], shots)[0], False)
    check("shots counts COMPLETE", screenshot_verdict(["a", "b"], shots)[1], "1/2 COMPLETE")
    # An id with no asset row at all must not read as complete.
    check("shots missing row", screenshot_verdict(["zz"], shots)[0], False)

    full = {
        "contactFirstName": "A",
        "contactLastName": "B",
        "contactEmail": "e",
        "contactPhone": "p",
    }
    check("contact full", contact_verdict(full)[0], True)
    check("contact no phone", contact_verdict({**full, "contactPhone": ""})[0], False)
    check("contact none", contact_verdict({})[0], False)

    if failures:
        print("SELF-CHECK FAILED")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    print("SELF-CHECK PASS — 17 assertions over pick_version/text/screenshot/contact")
    sys.exit(0)


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    main()
