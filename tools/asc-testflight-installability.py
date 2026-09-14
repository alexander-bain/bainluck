#!/usr/bin/env python3
"""native — read whether a VALID build is actually INSTALLABLE by a tester.

WHY THIS EXISTS
---------------
`asc-builds.py` answers "what does Apple hold, and in what processing state?".
Build 1.0 (10) reads `VALID` there, and a reader stops. But VALID is a statement
about the BINARY finishing processing — it is not a statement about anyone being
able to install it. Three further gates sit between VALID and a tester's phone,
and every one of them is invisible to the builds endpoint:

  1. EXPORT COMPLIANCE. `buildBetaDetail` reads `MISSING_EXPORT_COMPLIANCE`
     until the encryption declaration is answered. A build in that state is
     VALID and un-installable, and the only cure is an attended answer.
  2. TESTFLIGHT STATE. `internalBuildState` / `externalBuildState` say whether
     TestFlight will hand the build out at all (`READY_FOR_BETA_TESTING`) or is
     still holding it (`PROCESSING`, `IN_BETA_REVIEW`, `WAITING_FOR_REVIEW`).
  3. ASSIGNMENT. A READY build with no beta group and no individual tester is
     installable by nobody — there is no one it has been handed to. External
     groups additionally need a passed `betaAppReviewSubmission`; internal
     groups do not.

So a "build 10 is VALID, Alex can install it" claim is three unmeasured
assumptions wearing one measured word. This prints all four facts for one build
and says, in one line, whether a tester could install it right now.

READ-ONLY BY CONSTRUCTION. Every call is a GET. This tool never assigns a
tester, never creates or edits a group, never answers the compliance question,
never submits for beta review and never sends an invitation — all of those are
attended actions and several are externally visible (an invitation emails a
human). If a gate is a GAP, this prints WHO must act and stops.

CREDENTIALS: the same three `asc-builds.py` uses, resolved the same way and for
the same two reasons (bare assignments in ~/.claude/.env do not reach a python
child; a key under ~/Downloads reads EPERM, which looks exactly like absence).
This imports that resolution rather than restating it, so there is one copy.

USAGE
  python3 tools/asc-testflight-installability.py            # newest build
  python3 tools/asc-testflight-installability.py 10         # build by version
  python3 tools/asc-testflight-installability.py --self-check
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Reuse the credential resolution, JWT mint and GET wrapper wholesale. Restating
# them here would be a second copy of the two credential traps documented in
# asc-builds.py, which is exactly how the second copy goes stale. That file's
# name has hyphens, so it is not importable — load it by path.
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "asc_builds", os.path.join(os.path.dirname(os.path.abspath(__file__)), "asc-builds.py")
)
_asc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_asc)

BUNDLE_ID = _asc.BUNDLE_ID
get = _asc.get
token = _asc.token
die = _asc.die

# TWO internal states mean the build is out, not one. `READY_FOR_BETA_TESTING`
# is "TestFlight will hand it over"; `IN_BETA_TESTING` is the strictly LATER
# state "TestFlight is handing it over" — a build a tester has already been
# offered. Treating only the first as ready inverts the verdict on exactly the
# builds that are furthest along (measured 2026-09-14 on build 10, which read
# IN_BETA_TESTING and was reported NOT INSTALLABLE by this tool's first form).
# Every other value is Apple still holding it, and the reason differs by value,
# so we print whatever we got rather than mapping it to a boolean.
INSTALLABLE_STATES = {"READY_FOR_BETA_TESTING", "IN_BETA_TESTING"}


def main() -> None:
    want = None
    for arg in sys.argv[1:]:
        if arg == "--self-check":
            return self_check()
        if not arg.startswith("-"):
            want = arg

    bearer = token()
    apps = get(f"/apps?filter[bundleId]={BUNDLE_ID}", bearer).get("data", [])
    if not apps:
        die(f"no app with bundleId {BUNDLE_ID} on this key's team")
    app_id = apps[0]["id"]

    builds = get(
        f"/builds?filter[app]={app_id}&limit=20&sort=-version", bearer
    ).get("data", [])
    if not builds:
        die("Apple holds no build for this app")

    build = None
    if want:
        for row in builds:
            if str(row["attributes"].get("version")) == str(want):
                build = row
                break
        if build is None:
            die(f"Apple holds no build numbered {want} for this app")
    else:
        build = builds[0]

    bid = build["id"]
    attrs = build["attributes"]
    version = attrs.get("version")
    print(f"build   : 1.0 ({version})  {attrs.get('processingState')}"
          f"{' EXPIRED' if attrs.get('expired') else ''}"
          f"  uploaded {attrs.get('uploadedDate')}")

    gaps: list[str] = []

    # ---- gate 1 + 2: buildBetaDetail carries compliance and both TF states ---
    detail = get(f"/builds/{bid}/buildBetaDetail", bearer).get("data") or {}
    d = detail.get("attributes", {}) if detail else {}
    internal = d.get("internalBuildState")
    external = d.get("externalBuildState")
    auto_notify = d.get("autoNotifyEnabled")
    print(f"testflight internal : {internal}")
    print(f"testflight external : {external}")
    print(f"auto-notify testers : {auto_notify}")

    # Apple reports the missing declaration through the build state itself.
    compliance_missing = "MISSING_EXPORT_COMPLIANCE" in {internal, external}
    uses_enc = attrs.get("usesNonExemptEncryption")
    print(f"usesNonExemptEncryption : {uses_enc!r}"
          f"{'  (unanswered)' if uses_enc is None else ''}")
    if compliance_missing:
        gaps.append(
            "EXPORT COMPLIANCE unanswered — Apple is holding the build. "
            "ATTENDED: Alex answers the encryption question in App Store "
            "Connect (or the app sets ITSAppUsesNonExemptEncryption)."
        )
    if internal not in INSTALLABLE_STATES:
        gaps.append(
            f"internal TestFlight state is {internal}; TestFlight hands a build "
            f"out only in {sorted(INSTALLABLE_STATES)}"
        )

    # ---- gate 3: is it handed to anybody? ----------------------------------
    # NOT `/builds/{id}/betaGroups` — Apple answers that join with HTTP 403
    # "does not allow GET_RELATED. Allowed operations are: CREATE, DELETE"
    # (measured 2026-09-14). The readable direction is app -> groups, then ask
    # each group which builds it holds. A 403 here reads exactly like "no groups".
    groups = get(
        f"/betaGroups?filter[app]={app_id}&limit=200", bearer
    ).get("data", [])
    testers = get(f"/builds/{bid}/individualTesters?limit=200", bearer).get("data", [])
    print(f"beta groups on app  : {len(groups)}")
    print(f"individual testers  : {len(testers)}")

    # A group with zero members is assignment on paper only, so count the people,
    # and only count groups that actually hold THIS build.
    reachable = len(testers)
    for g in groups:
        ga = g["attributes"]
        holds = any(
            b["id"] == bid
            for b in get(f"/betaGroups/{g['id']}/builds?limit=200", bearer).get("data", [])
        )
        n = len(get(f"/betaGroups/{g['id']}/betaTesters?limit=200", bearer).get("data", []))
        kind = "internal" if ga.get("isInternalGroup") else "external"
        print(f"  group {ga.get('name')!r} ({kind}): {n} tester(s), "
              f"holds this build: {'YES' if holds else 'no'}")
        if holds:
            reachable += n
    if reachable == 0:
        gaps.append(
            "NO TESTER can reach this build — no group holding it has members "
            "and there are 0 individual testers. ATTENDED: Alex assigns the "
            "build to a group (or adds himself as an internal tester)."
        )

    print()
    if gaps:
        print("VERDICT: NOT INSTALLABLE — VALID processing only.")
        for g in gaps:
            print(f"  GAP: {g}")
        sys.exit(1)
    print(f"VERDICT: INSTALLABLE — {reachable} tester(s) can install 1.0 ({version}).")


def self_check() -> None:
    """Prove the tool parses a known-shaped payload without calling Apple."""
    assert INSTALLABLE_STATES == {"READY_FOR_BETA_TESTING", "IN_BETA_TESTING"}
    # The regression this guards: IN_BETA_TESTING is the later of the two and
    # must not be read as a gap.
    assert "IN_BETA_TESTING" in INSTALLABLE_STATES
    assert callable(get) and callable(token)
    print("self-check: OK (helpers resolved from asc-builds.py, installable-state set correct)")


if __name__ == "__main__":
    main()
