#!/usr/bin/env python3
"""native — read App Store Connect's own record of whether we could SUBMIT today.

WHY THIS EXISTS
---------------
`asc-builds.py` answers "what does Apple hold?" for BINARIES. It cannot answer
the question the ship actually turns on. Uploading build 9 puts a binary at
Apple; a binary is not a submission. A submission also needs a version record
in an editable state with an unexpired, VALID build attached to it (attached is
not enough — Apple keeps expired builds attached and VALID), per-locale
description and keywords, screenshots whose ASSETS have finished uploading, a
review contact, a
primary category, an age-rating declaration and a privacy-policy URL. Any one
missing is a hard stop that otherwise surfaces only when a human presses Submit
— and the expensive ones (screenshots) cost Alex real time to produce, so
finding them out AFTER the binary lands wastes exactly the lead time that
knowing early would buy.

So this prints every gate with a PASS/GAP verdict, measured from Apple's record
rather than assumed. A clean run is a real answer: nothing in Apple's record is
in the way, and what remains is the attended press of Submit.

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

CREDENTIALS  ASC_KEY_ID  ASC_ISSUER_ID  ASC_KEY_PATH
Resolved by `asc-builds.py`, imported — not re-implemented here. That resolver
already knows the two ways these read ABSENT while being perfectly fine: the
env file holds BARE assignments so a plain `source` never reaches a python
child, and the configured key path can be EPERM rather than missing. A second
copy of that knowledge in this file would drift, and the half that drifts is
the half that prints the remedy, so the reader is told to run something that
cannot work. One resolver, one self-test.

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


def build_verdict(attrs: dict | None) -> tuple[bool, str]:
    """Attached is not submittable: the build must also be VALID and UNEXPIRED.

    Apple expires a build ~90 days after upload and will not review it, but it
    stays attached to the version record and its processingState stays VALID —
    so a gate that only asks "is a build attached?" prints PASS on a binary
    that cannot ship. Measured 2026-09-14: the iOS 1.0 record still holds build
    7, uploaded in May, VALID and EXPIRED, while the unexpired build 8 is
    attached to nothing. That is precisely the state this tool is read in, so
    the false PASS lands on the one gate an attended attach decision turns on.
    """
    if attrs is None:
        return False, "no build attached to this version"
    if not attrs:
        # The relationship named a build the response did not include. That is
        # a hole in our read, not a missing build — never report it as either.
        return False, "attached build is not in Apple's response — cannot grade it"
    version = attrs.get("version")
    state = attrs.get("processingState")
    if attrs.get("expired"):
        return False, f"build {version} is EXPIRED — Apple will not review it"
    if state != "VALID":
        return False, f"build {version} is {state}, not VALID"
    return True, f"build {version} ({state})"


def build_gate(target: dict, included: list) -> tuple[bool, str]:
    """Join the version's build relationship to the included build rows, grade it.

    The join belongs inside the gate rather than in `main`. It is real logic
    that can fail on its own — the relationship is an id, the attributes live
    in a sibling `included` list, and picking the wrong list or filtering on
    the wrong type yields an empty attrs dict, which is a hole in OUR read and
    not a statement about Apple. Keeping it here is what lets --self-check
    grade it; left in `main` it would be exercised only by a run that has
    credentials and a network.
    """
    rel = target.get("relationships", {}).get("build", {}).get("data")
    if not rel:
        return build_verdict(None)
    by_id = {i["id"]: i for i in included if i.get("type") == "builds"}
    return build_verdict(by_id.get(rel["id"], {}).get("attributes", {}))


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
SIBLING = "asc-builds.py"


def asc_builds():
    """Import the sibling tool BY PATH, for its credential resolver.

    Its filename carries a hyphen, so it is not a legal module name and
    `import asc_builds` can never find it however the path is arranged — the
    loader below is not ceremony, it is the only way in. Loading it is safe:
    everything executable there sits behind `if __name__ == "__main__"`.

    It must be beside us. That is true in the repo and false for a copy taken
    out on its own (`git show <sha>:tools/... > /tmp/x.py` is a real habit in
    this lane's directives), so the failure names the path tried rather than
    dying somewhere later inside the resolver.
    """
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SIBLING)
    spec = importlib.util.spec_from_file_location("asc_builds", path)
    if spec is None or spec.loader is None:
        die(f"cannot load {path} — run this from the repo's tools/ directory")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except OSError as exc:
        die(f"cannot load {SIBLING} from {path}: {exc.strerror or exc}")
    return mod


def token() -> str:
    try:
        import jwt
    except ImportError:
        die("PyJWT is not importable; `pip3 install pyjwt cryptography`")
    builds = asc_builds()
    creds = builds.resolve_credentials()
    key_id = creds["ASC_KEY_ID"]
    issuer = creds["ASC_ISSUER_ID"]
    missing = [n for n in builds.CRED_NAMES if not creds[n]]
    if missing:
        die(
            f"missing credential(s): {', '.join(missing)} — not in the environment "
            f"and not in {builds.ENV_FILE}. That file holds BARE assignments, so "
            "plain `source` does not reach this process; use "
            "`set -a; source ~/.claude/.env; set +a`."
        )
    # Names every path it tried, each with its own errno, and exits 2 itself:
    # EPERM on the configured path and a genuinely absent key are different
    # bugs and must not collapse into one sentence.
    private_key, _used = builds.read_key(creds["ASC_KEY_PATH"], key_id)
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

    verdict("submittable build", *build_gate(target, versions.get("included", [])))

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
    print(
        "VERDICT: every gate PASS — nothing in Apple's record blocks a submission"
    )
    sys.exit(0)


# ---------------------------------------------------------------------------
def self_check() -> None:
    """Grade the pure verdict logic offline. Each case asserts BOTH directions
    so a predicate that always returns the same answer cannot pass.

    No network and no credentials. It does read the sibling tool off disk, so
    that the one thing this file no longer implements — resolving credentials —
    is proven reachable before a run needs it.
    """
    failures: list[str] = []
    ran = 0

    def check(name: str, got, want) -> None:
        # The summary line reports a COUNT, so count it here rather than typing
        # a number into the string that nothing keeps honest. The number this
        # replaces said 17 over 16 assertions.
        nonlocal ran
        ran += 1
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

    # Attached-but-expired is the live state, so it gets both directions and
    # the reason, not just a boolean: "EXPIRED" is what sends a reader to
    # attach a different build rather than to go hunting for metadata.
    valid = {"version": "9", "processingState": "VALID", "expired": False}
    check("build valid unexpired", build_verdict(valid)[0], True)
    check("build expired", build_verdict({**valid, "expired": True})[0], False)
    check("build expired says why", "EXPIRED" in build_verdict({**valid, "expired": True})[1], True)
    check("build still processing", build_verdict({**valid, "processingState": "PROCESSING"})[0], False)
    check("build invalid", build_verdict({**valid, "processingState": "INVALID"})[0], False)
    check("build none attached", build_verdict(None)[0], False)
    # A missing include row must not read as "no build attached" — that would
    # send a reader to upload a binary Apple already has.
    check("build not in response", build_verdict({})[0], False)
    check("build not in response says so", "not in Apple's response" in build_verdict({})[1], True)

    # The join, on the shape Apple actually returns — the live 2026-09-14 iOS
    # record: an expired build 7 reachable only through `included`.
    tgt = {"relationships": {"build": {"data": {"id": "b7"}}}}
    inc = [
        {"id": "other", "type": "appStoreVersions", "attributes": {}},
        {"id": "b7", "type": "builds", "attributes": {"version": "7", "processingState": "VALID", "expired": True}},
        {"id": "b9", "type": "builds", "attributes": {"version": "9", "processingState": "VALID", "expired": False}},
    ]
    check("gate joins the attached build", build_gate(tgt, inc)[0], False)
    check("gate grades the ATTACHED one, not the newest", "build 7" in build_gate(tgt, inc)[1], True)
    check("gate passes when the unexpired one is attached", build_gate({"relationships": {"build": {"data": {"id": "b9"}}}}, inc)[0], True)
    # Both of these are False, so the boolean alone cannot tell them apart —
    # and they send a reader to opposite places (upload a binary vs fix our
    # read). Assert the MESSAGE, or the two collapse into each other.
    check("gate with no relationship", build_gate({}, inc)[1], build_verdict(None)[1])
    check("no-relationship and bad-join differ", build_verdict(None)[1] != build_verdict({})[1], True)
    check("gate when the id is not included", build_gate({"relationships": {"build": {"data": {"id": "b8"}}}}, inc)[1], build_verdict({})[1])

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

    # --- the borrowed resolver is actually reachable --------------------------
    # Without this the import is only exercised by a run that has credentials
    # and a network, i.e. never by a gate — and a hyphenated-filename import is
    # exactly the kind that breaks silently when a file moves.
    builds = asc_builds()
    check("sibling exposes resolve_credentials", callable(getattr(builds, "resolve_credentials", None)), True)
    check("sibling exposes read_key", callable(getattr(builds, "read_key", None)), True)
    # token() reports missing names from CRED_NAMES and quotes ENV_FILE in the
    # remedy, so both must be there and the three names must be the three.
    check("sibling exposes CRED_NAMES", sorted(getattr(builds, "CRED_NAMES", ())), ["ASC_ISSUER_ID", "ASC_KEY_ID", "ASC_KEY_PATH"])
    check("sibling exposes ENV_FILE", bool(getattr(builds, "ENV_FILE", "")), True)
    # The sibling's main() is guarded by `__name__ == "__main__"`, so the name
    # we load it under is the whole mechanism keeping this import from calling
    # Apple. Assert the mechanism, not the arrival: reaching this line already
    # proves it did not run.
    check("loaded under a non-__main__ name", builds.__name__ != "__main__", True)

    if failures:
        print("SELF-CHECK FAILED")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    print(
        f"SELF-CHECK PASS — {ran} assertions over "
        "pick_version/text/screenshot/contact + the borrowed resolver"
    )
    sys.exit(0)


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    main()
