#!/usr/bin/env python3
"""native / mac — verify that a macOS build in App Store Connect is VALID and INSTALLABLE.

WHY THIS EXISTS
---------------
`tools/asc-testflight-installability.py` inspects `/builds?filter[app]={app_id}`
without joining `preReleaseVersion` or checking `platform`. Because iOS and macOS
share the universal App Store Connect app record (`com.bainluck.Bain-Luck`,
id `6759871755`), an unscoped check (or a build-number lookup when numbers are
examined without platform filtering) reads an `IOS` build as `VERDICT: INSTALLABLE`
while proving nothing about macOS (#10878).

This companion preserves `tools/asc-testflight-installability.py` untouched for
the iPhone/Watch lane and enforces macOS-specific installability checks:
  1. Exact ASC build ID (`data.id`) is printed and bound to all downstream queries.
  2. Platform identity (`preReleaseVersion.attributes.platform` /
     `appStoreVersion.attributes.platform`) MUST explicitly equal `"MAC_OS"`.
     - Same-numbered `IOS` / `VISION_OS` builds are refused.
     - Builds missing `preReleaseVersion`/`appStoreVersion` platform metadata or
       carrying conflicting platform metadata are refused.
  3. Expected marketing version (`--marketing-version`, default `1.0.4`) and
     build number (`--build <N>` or positional `<N>`) must match.
  4. `processingState == "VALID"` and `expired is False`.
  5. Export compliance is satisfied and `internalBuildState` is in
     `{"READY_FOR_BETA_TESTING", "IN_BETA_TESTING"}`.
  6. The intended internal group (`Bain Luck testers`, `isInternalGroup == True`)
     specifically holds this exact ASC build ID and has at least 1 tester.

READ-ONLY BY CONSTRUCTION. Every call is a GET.

USAGE
  python3 tools/asc-mac-testflight-installability.py --build 81
  python3 tools/asc-mac-testflight-installability.py --marketing-version 1.0.4 --build 81
  python3 tools/asc-mac-testflight-installability.py --self-check
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "asc_builds",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "asc-builds.py"),
)
_asc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_asc)

BUNDLE_ID = _asc.BUNDLE_ID
get = _asc.get
token = _asc.token
die = _asc.die

INSTALLABLE_STATES = {"READY_FOR_BETA_TESTING", "IN_BETA_TESTING"}
REQUIRED_PLATFORM = "MAC_OS"
DEFAULT_MARKETING_VERSION = "1.0.4"
DEFAULT_INTERNAL_GROUP = "Bain Luck testers"


def resolve_build_platform_and_train(
    row: dict[str, Any],
    pre_by_id: dict[str, dict[str, Any]],
    asv_by_id: dict[str, dict[str, Any]],
) -> tuple[str | None, str | None, str | None]:
    """Return (platform, marketing_version, error_reason) for a build resource."""
    rels = row.get("relationships") or {}
    pre_rel = (rels.get("preReleaseVersion") or {}).get("data")
    asv_rel = (rels.get("appStoreVersion") or {}).get("data")

    pre_info = pre_by_id.get(pre_rel["id"]) if isinstance(pre_rel, dict) and pre_rel.get("id") else None
    asv_info = asv_by_id.get(asv_rel["id"]) if isinstance(asv_rel, dict) and asv_rel.get("id") else None

    if pre_rel and pre_info is None:
        return None, None, f"preReleaseVersion {pre_rel.get('id')!r} missing from included payload"
    if asv_rel and asv_info is None:
        return None, None, f"appStoreVersion {asv_rel.get('id')!r} missing from included payload"

    pre_plat = (pre_info or {}).get("platform")
    asv_plat = (asv_info or {}).get("platform")
    if pre_plat and asv_plat and pre_plat != asv_plat:
        return (
            None,
            None,
            f"ambiguous platform metadata: preReleaseVersion={pre_plat!r} vs appStoreVersion={asv_plat!r}",
        )

    platform = pre_plat or asv_plat
    if not platform:
        return (
            None,
            None,
            "missing platform metadata (neither preReleaseVersion nor appStoreVersion supplied attributes.platform)",
        )

    pre_ver = (pre_info or {}).get("version")
    asv_ver = (asv_info or {}).get("versionString")
    if pre_ver and asv_ver and pre_ver != asv_ver:
        return (
            platform,
            None,
            f"ambiguous marketing version metadata: preReleaseVersion={pre_ver!r} vs appStoreVersion={asv_ver!r}",
        )

    train = pre_ver or asv_ver
    if not train:
        return platform, None, "missing marketing version (train) in preReleaseVersion/appStoreVersion"

    return platform, train, None


def evaluate_mac_build_installability(
    builds_payload: dict[str, Any],
    *,
    want_build: str | None,
    want_marketing_version: str = DEFAULT_MARKETING_VERSION,
    want_group_name: str = DEFAULT_INTERNAL_GROUP,
    fetch_beta_detail: Callable[[str], dict[str, Any]],
    fetch_groups: Callable[[], list[dict[str, Any]]],
    fetch_testers: Callable[[str], list[dict[str, Any]]],
    fetch_group_builds: Callable[[str], list[dict[str, Any]]],
    fetch_group_testers: Callable[[str], list[dict[str, Any]]],
) -> tuple[bool, list[str], list[str]]:
    """Evaluate macOS TestFlight installability using real production rules.

    Returns (ok, output_lines, gap_or_refusal_reasons).
    """
    lines: list[str] = []
    gaps: list[str] = []

    rows = builds_payload.get("data") or []
    included = builds_payload.get("included") or []

    pre_by_id: dict[str, dict[str, Any]] = {}
    asv_by_id: dict[str, dict[str, Any]] = {}
    for item in included:
        itype = item.get("type")
        iid = item.get("id")
        iattrs = item.get("attributes") or {}
        if itype == "preReleaseVersions" and iid:
            pre_by_id[iid] = iattrs
        elif itype == "appStoreVersions" and iid:
            asv_by_id[iid] = iattrs

    if not rows:
        return False, lines, ["Apple holds no builds for this app"]

    selected_row: dict[str, Any] | None = None
    selected_platform: str | None = None
    selected_train: str | None = None

    if want_build is not None:
        matching_number = [
            r for r in rows if str((r.get("attributes") or {}).get("version")) == str(want_build)
        ]
        if not matching_number:
            return False, lines, [f"Apple holds no build numbered {want_build} for this app"]

        mac_matches: list[tuple[dict[str, Any], str, str]] = []
        non_mac_reasons: list[str] = []
        for r in matching_number:
            rid = r.get("id", "?")
            plat, train, err = resolve_build_platform_and_train(r, pre_by_id, asv_by_id)
            if err:
                non_mac_reasons.append(f"build {want_build} (id {rid}) refused: {err}")
            elif plat != REQUIRED_PLATFORM:
                non_mac_reasons.append(
                    f"build {want_build} (id {rid}, train {train}) has platform={plat!r}, "
                    f"expected {REQUIRED_PLATFORM!r} — refusing non-macOS build"
                )
            else:
                mac_matches.append((r, plat, train or "?"))

        if not mac_matches:
            return False, lines, non_mac_reasons
        if len(mac_matches) > 1:
            ids = ", ".join(m[0].get("id", "?") for m in mac_matches)
            return (
                False,
                lines,
                [f"ambiguous: multiple MAC_OS builds share build number {want_build} (ids: {ids})"],
            )
        selected_row, selected_platform, selected_train = mac_matches[0]
    else:
        mac_rows: list[tuple[dict[str, Any], str, str]] = []
        observed_non_mac: list[str] = []
        for r in rows:
            rid = r.get("id", "?")
            rver = (r.get("attributes") or {}).get("version", "?")
            plat, train, err = resolve_build_platform_and_train(r, pre_by_id, asv_by_id)
            if err:
                observed_non_mac.append(f"{rver} (id {rid}: {err})")
            elif plat == REQUIRED_PLATFORM:
                mac_rows.append((r, plat, train or "?"))
            else:
                observed_non_mac.append(f"{train} ({rver}) [id {rid}, platform={plat}]")
        if not mac_rows:
            sample = ", ".join(observed_non_mac[:3]) if observed_non_mac else "none"
            return (
                False,
                lines,
                [
                    f"Apple holds {len(rows)} build(s) for {BUNDLE_ID}, but 0 have "
                    f"platform={REQUIRED_PLATFORM!r} (newest observed: {sample})"
                ],
            )
        selected_row, selected_platform, selected_train = mac_rows[0]

    bid = selected_row.get("id")
    if not bid:
        return False, lines, ["selected build is missing its ASC resource id"]

    attrs = selected_row.get("attributes") or {}
    version = str(attrs.get("version") or "?")
    proc_state = attrs.get("processingState")
    expired = bool(attrs.get("expired"))
    uploaded_date = attrs.get("uploadedDate")
    ls_min = attrs.get("lsMinimumSystemVersion")

    lines.append(f"asc_build_id            : {bid}")
    lines.append(f"platform                : {selected_platform}")
    lines.append(
        f"build                   : {selected_train} ({version})  {proc_state}"
        f"{' EXPIRED' if expired else ''}  uploaded {uploaded_date}"
        f"  lsMinimumSystemVersion={ls_min!r}"
    )

    if selected_platform != REQUIRED_PLATFORM:
        gaps.append(f"platform is {selected_platform!r}, expected {REQUIRED_PLATFORM!r}")

    if want_marketing_version and selected_train != want_marketing_version:
        gaps.append(
            f"marketing version (train) is {selected_train!r}, expected {want_marketing_version!r}"
        )

    if want_build is not None and version != str(want_build):
        gaps.append(f"build version is {version!r}, expected {str(want_build)!r}")

    if proc_state != "VALID":
        gaps.append(f"processingState is {proc_state!r}, expected 'VALID'")

    if expired:
        gaps.append("build is EXPIRED")

    detail = fetch_beta_detail(bid) or {}
    d_attrs = detail.get("attributes") or {}
    internal = d_attrs.get("internalBuildState")
    external = d_attrs.get("externalBuildState")
    auto_notify = d_attrs.get("autoNotifyEnabled")
    lines.append(f"testflight internal     : {internal}")
    lines.append(f"testflight external     : {external}")
    lines.append(f"auto-notify testers     : {auto_notify}")

    compliance_missing = "MISSING_EXPORT_COMPLIANCE" in {internal, external}
    uses_enc = attrs.get("usesNonExemptEncryption")
    lines.append(
        f"usesNonExemptEncryption : {uses_enc!r}"
        f"{'  (unanswered)' if uses_enc is None else ''}"
    )
    if compliance_missing:
        gaps.append(
            "EXPORT COMPLIANCE unanswered — Apple is holding the build. "
            "Set ITSAppUsesNonExemptEncryption or answer in App Store Connect."
        )
    if internal not in INSTALLABLE_STATES:
        gaps.append(
            f"internal TestFlight state is {internal!r}; TestFlight hands a build "
            f"out only in {sorted(INSTALLABLE_STATES)}"
        )

    groups = fetch_groups()
    testers = fetch_testers(bid)
    lines.append(f"beta groups on app      : {len(groups)}")
    lines.append(f"individual testers      : {len(testers)}")

    target_group_found = False
    target_group_internal = False
    target_group_holds = False
    target_group_testers = 0

    for g in groups:
        gid = g.get("id", "")
        ga = g.get("attributes") or {}
        gname = ga.get("name")
        is_internal = bool(ga.get("isInternalGroup"))
        g_builds = fetch_group_builds(gid)
        holds = any(b.get("id") == bid for b in g_builds)
        n_testers = len(fetch_group_testers(gid))
        kind = "internal" if is_internal else "external"
        lines.append(
            f"  group {gname!r} ({kind}): {n_testers} tester(s), "
            f"holds this build: {'YES' if holds else 'no'}"
        )
        if gname == want_group_name:
            target_group_found = True
            target_group_internal = is_internal
            target_group_holds = holds
            target_group_testers = n_testers

    if not target_group_found:
        gaps.append(f"intended internal group {want_group_name!r} was not found on this app")
    else:
        if not target_group_internal:
            gaps.append(f"group {want_group_name!r} is not marked isInternalGroup=True")
        if not target_group_holds:
            gaps.append(
                f"internal group {want_group_name!r} does NOT hold macOS build "
                f"{selected_train} ({version}) [id {bid}]"
            )
        if target_group_testers <= 0:
            gaps.append(f"internal group {want_group_name!r} has 0 testers")

    return len(gaps) == 0, lines, gaps


def self_check() -> None:
    """Offline controls proving platform discrimination and gate enforcement."""
    assert INSTALLABLE_STATES == {"READY_FOR_BETA_TESTING", "IN_BETA_TESTING"}
    assert callable(get) and callable(token)

    def _beta_ok(_bid: str) -> dict[str, Any]:
        return {
            "id": _bid,
            "attributes": {
                "internalBuildState": "IN_BETA_TESTING",
                "externalBuildState": "READY_FOR_BETA_SUBMISSION",
                "autoNotifyEnabled": True,
            },
        }

    def _groups_ok() -> list[dict[str, Any]]:
        return [
            {
                "id": "grp-1",
                "attributes": {"name": DEFAULT_INTERNAL_GROUP, "isInternalGroup": True},
            }
        ]

    # 1. Same-numbered IOS build (e.g. build 80) MUST be refused.
    ios_only_payload = {
        "data": [
            {
                "id": "ios-build-80-uuid",
                "type": "builds",
                "attributes": {
                    "version": "80",
                    "processingState": "VALID",
                    "expired": False,
                    "uploadedDate": "2026-10-23T10:57:00Z",
                    "usesNonExemptEncryption": False,
                },
                "relationships": {
                    "preReleaseVersion": {"data": {"type": "preReleaseVersions", "id": "pre-ios-104"}}
                },
            }
        ],
        "included": [
            {
                "id": "pre-ios-104",
                "type": "preReleaseVersions",
                "attributes": {"version": "1.0.4", "platform": "IOS"},
            }
        ],
    }
    ok, _lines, gaps = evaluate_mac_build_installability(
        ios_only_payload,
        want_build="80",
        want_marketing_version="1.0.4",
        fetch_beta_detail=_beta_ok,
        fetch_groups=_groups_ok,
        fetch_testers=lambda _b: [],
        fetch_group_builds=lambda _g: [{"id": "ios-build-80-uuid"}],
        fetch_group_testers=lambda _g: [{"id": "t1"}, {"id": "t2"}],
    )
    assert not ok, "IOS build with matching build number must be refused"
    assert any("platform='IOS'" in g and "expected 'MAC_OS'" in g for g in gaps), gaps

    # 2. Build missing platform metadata / missing preReleaseVersion MUST be refused.
    missing_platform_payload = {
        "data": [
            {
                "id": "mystery-build-81",
                "type": "builds",
                "attributes": {
                    "version": "81",
                    "processingState": "VALID",
                    "expired": False,
                    "usesNonExemptEncryption": False,
                },
                "relationships": {},
            }
        ],
        "included": [],
    }
    ok, _lines, gaps = evaluate_mac_build_installability(
        missing_platform_payload,
        want_build="81",
        want_marketing_version="1.0.4",
        fetch_beta_detail=_beta_ok,
        fetch_groups=_groups_ok,
        fetch_testers=lambda _b: [],
        fetch_group_builds=lambda _g: [{"id": "mystery-build-81"}],
        fetch_group_testers=lambda _g: [{"id": "t1"}],
    )
    assert not ok, "Build missing platform metadata must be refused"
    assert any("missing platform metadata" in g for g in gaps), gaps

    # 3. Conflicting preReleaseVersion vs appStoreVersion platform metadata MUST be refused.
    ambiguous_platform_payload = {
        "data": [
            {
                "id": "ambig-build-81",
                "type": "builds",
                "attributes": {"version": "81", "processingState": "VALID", "expired": False},
                "relationships": {
                    "preReleaseVersion": {"data": {"type": "preReleaseVersions", "id": "pre-mac"}},
                    "appStoreVersion": {"data": {"type": "appStoreVersions", "id": "asv-ios"}},
                },
            }
        ],
        "included": [
            {
                "id": "pre-mac",
                "type": "preReleaseVersions",
                "attributes": {"version": "1.0.4", "platform": "MAC_OS"},
            },
            {
                "id": "asv-ios",
                "type": "appStoreVersions",
                "attributes": {"versionString": "1.0.4", "platform": "IOS"},
            },
        ],
    }
    ok, _lines, gaps = evaluate_mac_build_installability(
        ambiguous_platform_payload,
        want_build="81",
        want_marketing_version="1.0.4",
        fetch_beta_detail=_beta_ok,
        fetch_groups=_groups_ok,
        fetch_testers=lambda _b: [],
        fetch_group_builds=lambda _g: [{"id": "ambig-build-81"}],
        fetch_group_testers=lambda _g: [{"id": "t1"}],
    )
    assert not ok, "Ambiguous platform metadata must be refused"
    assert any("ambiguous platform metadata" in g for g in gaps), gaps

    # 4. Valid MAC_OS build that is NOT held by 'Bain Luck testers' MUST fail group gate.
    mac_payload = {
        "data": [
            ios_only_payload["data"][0],
            {
                "id": "mac-build-81-uuid",
                "type": "builds",
                "attributes": {
                    "version": "81",
                    "processingState": "VALID",
                    "expired": False,
                    "uploadedDate": "2026-10-23T15:00:00Z",
                    "usesNonExemptEncryption": False,
                    "lsMinimumSystemVersion": "14.0",
                },
                "relationships": {
                    "preReleaseVersion": {"data": {"type": "preReleaseVersions", "id": "pre-mac-104"}}
                },
            },
        ],
        "included": [
            ios_only_payload["included"][0],
            {
                "id": "pre-mac-104",
                "type": "preReleaseVersions",
                "attributes": {"version": "1.0.4", "platform": "MAC_OS"},
            },
        ],
    }
    ok, _lines, gaps = evaluate_mac_build_installability(
        mac_payload,
        want_build="81",
        want_marketing_version="1.0.4",
        fetch_beta_detail=_beta_ok,
        fetch_groups=_groups_ok,
        fetch_testers=lambda _b: [],
        fetch_group_builds=lambda _g: [{"id": "ios-build-80-uuid"}],  # does not hold mac-build-81-uuid
        fetch_group_testers=lambda _g: [{"id": "t1"}, {"id": "t2"}],
    )
    assert not ok, "MAC_OS build not assigned to 'Bain Luck testers' must fail"
    assert any("does NOT hold macOS build" in g for g in gaps), gaps

    # 5. Valid MAC_OS build 1.0.4 (81) held by 'Bain Luck testers' MUST pass and bind exact build id.
    ok, out_lines, gaps = evaluate_mac_build_installability(
        mac_payload,
        want_build="81",
        want_marketing_version="1.0.4",
        fetch_beta_detail=_beta_ok,
        fetch_groups=_groups_ok,
        fetch_testers=lambda _b: [],
        fetch_group_builds=lambda _g: [{"id": "mac-build-81-uuid"}],
        fetch_group_testers=lambda _g: [{"id": "t1"}, {"id": "t2"}],
    )
    assert ok, f"Expected valid MAC_OS build to pass, got gaps: {gaps}"
    assert any("asc_build_id            : mac-build-81-uuid" in ln for ln in out_lines), out_lines
    assert any("platform                : MAC_OS" in ln for ln in out_lines), out_lines

    print(
        "self-check: OK (refuses same-numbered IOS build, refuses missing/ambiguous platform, "
        "enforces 'Bain Luck testers' assignment, and binds exact MAC_OS build ID)"
    )


def main() -> None:
    want_build: str | None = None
    want_marketing = DEFAULT_MARKETING_VERSION
    want_group = DEFAULT_INTERNAL_GROUP

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--self-check":
            self_check()
            return
        if arg == "--build":
            i += 1
            if i >= len(argv):
                die("--build requires a build number argument")
            want_build = argv[i]
        elif arg == "--marketing-version":
            i += 1
            if i >= len(argv):
                die("--marketing-version requires a version string argument")
            want_marketing = argv[i]
        elif arg == "--group":
            i += 1
            if i >= len(argv):
                die("--group requires a beta group name")
            want_group = argv[i]
        elif arg in ("-h", "--help"):
            print(__doc__.strip())
            return
        elif not arg.startswith("-"):
            want_build = arg
        else:
            die(f"unknown argument: {arg}")
        i += 1

    bearer = token()
    apps = get(f"/apps?filter[bundleId]={BUNDLE_ID}", bearer).get("data", [])
    if not apps:
        die(f"no app with bundleId {BUNDLE_ID} on this key's team")
    app_id = apps[0]["id"]

    builds_payload = get(
        f"/builds?filter[app]={app_id}&limit=50&sort=-version"
        "&include=preReleaseVersion,appStoreVersion",
        bearer,
    )

    ok, lines, gaps = evaluate_mac_build_installability(
        builds_payload,
        want_build=want_build,
        want_marketing_version=want_marketing,
        want_group_name=want_group,
        fetch_beta_detail=lambda bid: get(f"/builds/{bid}/buildBetaDetail", bearer).get("data") or {},
        fetch_groups=lambda: get(f"/betaGroups?filter[app]={app_id}&limit=200", bearer).get("data", []),
        fetch_testers=lambda bid: get(f"/builds/{bid}/individualTesters?limit=200", bearer).get("data", []),
        fetch_group_builds=lambda gid: get(f"/betaGroups/{gid}/builds?limit=200", bearer).get("data", []),
        fetch_group_testers=lambda gid: get(f"/betaGroups/{gid}/betaTesters?limit=200", bearer).get("data", []),
    )

    for ln in lines:
        print(ln)
    if lines:
        print()
    if not ok:
        print("VERDICT: NOT INSTALLABLE FOR MACOS")
        for g in gaps:
            print(f"  GAP: {g}")
        sys.exit(1)

    print(
        f"VERDICT: INSTALLABLE ON MACOS — internal group {want_group!r} holds "
        f"MAC_OS {want_marketing} ({want_build or 'latest'})."
    )


if __name__ == "__main__":
    main()
