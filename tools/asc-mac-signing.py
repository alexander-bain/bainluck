#!/usr/bin/env python3
"""native / mac — inspect and (when authorized) provision macOS App Store signing assets.

WHY THIS EXISTS
---------------
macOS TestFlight export (`xcodebuild -exportArchive` with `method=app-store-connect`)
produces a signed `.pkg` installer and requires:
  1. `Apple Distribution` certificate + private key in Keychain (already present:
     cert id `LJQ9K3973X`, serial `35FFB73025D2BB65A669130C81F55CF`, expires 2027-09-11).
  2. Two `MAC_APP_STORE` provisioning profiles (`.provisionprofile`, `Platform=OSX`)
     referencing `LJQ9K3973X`:
       - `com.bainluck.Bain-Luck` (bundleId resource `DSAW22CLG7`, `UNIVERSAL`)
       - `com.bainluck.Bain-Luck.BainLuckWidget` (bundleId resource `87A2TQ5M6K`, `UNIVERSAL`)
  3. A `3rd Party Mac Developer Installer` / `Mac Installer Distribution` certificate
     (`certificateType = MAC_INSTALLER_DISTRIBUTION`) + private key in Keychain so
     `productbuild` can sign `Bain Luck.pkg`.

SAFETY INVARIANTS
-----------------
- Default mode (`--status`) is 100% READ-ONLY (`GET` calls + local `security` reads).
- Never revokes, deletes, or replaces any existing certificate (`LJQ9K3973X`,
  `D2G632GUJF`, `UKGL2MYS2T`) or any existing `IOS_APP_STORE` profile
  (`BainLuck App AppStore 38`, `BainLuck Widget AppStore 38`, etc.).
- Never prints, logs, or commits private keys, CSRs, `.p8` contents, or bearer tokens.
- Mutation modes (`--provision-profiles`, `--provision-installer-cert`, `--provision-all`)
  are purely additive and only run when explicitly passed by the authorized Apple owner.

USAGE
  python3 tools/asc-mac-signing.py --self-check
  python3 tools/asc-mac-signing.py --status
  python3 tools/asc-mac-signing.py --provision-profiles
  python3 tools/asc-mac-signing.py --provision-installer-cert
  python3 tools/asc-mac-signing.py --provision-all
"""

from __future__ import annotations

import base64
import datetime
import glob
import importlib.util
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "asc_builds",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "asc-builds.py"),
)
_asc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_asc)

API = _asc.API
get = _asc.get
token = _asc.token
die = _asc.die

TEAM_ID = "J893F72P4R"
APP_BUNDLE_ID = "com.bainluck.Bain-Luck"
WIDGET_BUNDLE_ID = "com.bainluck.Bain-Luck.BainLuckWidget"
MAC_PROFILE_SPECS = [
    (APP_BUNDLE_ID, "BainLuck Mac App AppStore"),
    (WIDGET_BUNDLE_ID, "BainLuck Mac Widget AppStore"),
]
DEFAULT_PROFILE_DIR = os.path.expanduser(
    "~/Library/Developer/Xcode/UserData/Provisioning Profiles"
)


def post_json(path: str, payload: dict[str, Any], bearer: str) -> tuple[int, dict[str, Any]]:
    """POST JSON to App Store Connect API and return (http_status, parsed_json)."""
    url = path if path.startswith("http") else f"{API}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw_error": raw[:600]}
        return exc.code, parsed


def build_profile_create_payload(
    *,
    profile_name: str,
    bundle_id_resource_id: str,
    apple_distribution_cert_id: str,
) -> dict[str, Any]:
    """Construct an additive MAC_APP_STORE profile creation request."""
    if not profile_name or not bundle_id_resource_id or not apple_distribution_cert_id:
        raise ValueError("profile_name, bundle_id_resource_id, and apple_distribution_cert_id are required")
    return {
        "data": {
            "type": "profiles",
            "attributes": {
                "name": profile_name,
                "profileType": "MAC_APP_STORE",
            },
            "relationships": {
                "bundleId": {
                    "data": {
                        "type": "bundleIds",
                        "id": bundle_id_resource_id,
                    }
                },
                "certificates": {
                    "data": [
                        {
                            "type": "certificates",
                            "id": apple_distribution_cert_id,
                        }
                    ]
                },
            },
        }
    }


def build_installer_cert_create_payload(*, csr_pem_or_base64: str) -> dict[str, Any]:
    """Construct an additive MAC_INSTALLER_DISTRIBUTION certificate request."""
    lines = [
        ln.strip()
        for ln in csr_pem_or_base64.strip().splitlines()
        if ln.strip() and not ln.strip().startswith("-----")
    ]
    csr_body = "".join(lines)
    if not csr_body:
        raise ValueError("CSR content is empty")
    return {
        "data": {
            "type": "certificates",
            "attributes": {
                "certificateType": "MAC_INSTALLER_DISTRIBUTION",
                "csrContent": csr_body,
            },
        }
    }


def classify_signing_readiness(
    *,
    bundle_ids_data: list[dict[str, Any]],
    certs_data: list[dict[str, Any]],
    profiles_data: list[dict[str, Any]],
    keychain_codesign_output: str,
    keychain_all_output: str,
    local_mac_profiles: dict[str, str],
) -> dict[str, Any]:
    """Pure classifier for ASC + local Keychain Mac App Store signing readiness."""
    bundle_map = {
        (b.get("attributes") or {}).get("identifier"): b.get("id")
        for b in bundle_ids_data
        if (b.get("attributes") or {}).get("identifier")
    }

    dist_certs = [
        c
        for c in certs_data
        if (c.get("attributes") or {}).get("certificateType") in ("DISTRIBUTION", "MAC_APP_DISTRIBUTION")
    ]
    installer_certs = [
        c
        for c in certs_data
        if (c.get("attributes") or {}).get("certificateType") == "MAC_INSTALLER_DISTRIBUTION"
    ]
    asc_mac_profiles = [
        p
        for p in profiles_data
        if (p.get("attributes") or {}).get("profileType") == "MAC_APP_STORE"
        and (p.get("attributes") or {}).get("profileState") == "ACTIVE"
    ]

    has_local_apple_dist = "Apple Distribution" in keychain_codesign_output
    has_local_installer = (
        "3rd Party Mac Developer Installer" in keychain_all_output
        or "Mac Installer Distribution" in keychain_all_output
    )

    missing_items: list[str] = []
    if APP_BUNDLE_ID not in bundle_map:
        missing_items.append(f"ASC bundleId missing for {APP_BUNDLE_ID}")
    if WIDGET_BUNDLE_ID not in bundle_map:
        missing_items.append(f"ASC bundleId missing for {WIDGET_BUNDLE_ID}")
    if not dist_certs:
        missing_items.append("ASC DISTRIBUTION certificate missing")
    if not has_local_apple_dist:
        missing_items.append("Local Keychain missing 'Apple Distribution' identity")
    if not installer_certs:
        missing_items.append("ASC MAC_INSTALLER_DISTRIBUTION certificate missing")
    if not has_local_installer:
        missing_items.append(
            "Local Keychain missing '3rd Party Mac Developer Installer' / 'Mac Installer Distribution' identity"
        )
    for bid, _name in MAC_PROFILE_SPECS:
        if bid not in local_mac_profiles:
            missing_items.append(f"Local MAC_APP_STORE .provisionprofile missing for {bid}")

    return {
        "ready": len(missing_items) == 0,
        "app_bundle_resource_id": bundle_map.get(APP_BUNDLE_ID),
        "widget_bundle_resource_id": bundle_map.get(WIDGET_BUNDLE_ID),
        "apple_distribution_cert_id": dist_certs[0]["id"] if dist_certs else None,
        "asc_installer_cert_ids": [c["id"] for c in installer_certs],
        "asc_active_mac_profile_names": [
            (p.get("attributes") or {}).get("name") for p in asc_mac_profiles
        ],
        "has_local_apple_distribution": has_local_apple_dist,
        "has_local_mac_installer": has_local_installer,
        "local_mac_profiles": local_mac_profiles,
        "missing_items": missing_items,
    }


def scan_local_mac_store_profiles(profile_dir: str = DEFAULT_PROFILE_DIR) -> dict[str, str]:
    """Return {bundle_id: profile_name} for valid, unexpired OSX Store profiles on disk."""
    found: dict[str, str] = {}
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if not os.path.isdir(profile_dir):
        return found
    for p in sorted(glob.glob(os.path.join(profile_dir, "*.provisionprofile"))):
        proc = subprocess.run(["/usr/bin/security", "cms", "-D", "-i", p], capture_output=True)
        if proc.returncode != 0:
            continue
        try:
            pl = plistlib.loads(proc.stdout)
        except Exception:
            continue
        if "ProvisionedDevices" in pl:
            continue
        plats = pl.get("Platform") or []
        if "OSX" not in plats and "macOS" not in plats:
            continue
        exp = pl.get("ExpirationDate")
        if isinstance(exp, datetime.datetime):
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=datetime.timezone.utc)
            if exp < now_utc:
                continue
        ent = pl.get("Entitlements") or {}
        appid = ent.get("com.apple.application-identifier") or ""
        prefix = f"{TEAM_ID}."
        if appid.startswith(prefix):
            bid = appid[len(prefix) :]
            found[bid] = f"{pl.get('Name', os.path.basename(p))} ({os.path.basename(p)})"
    return found


def inspect_status(bearer: str) -> dict[str, Any]:
    bundle_ids_data = get("/bundleIds?limit=50", bearer).get("data", [])
    certs_data = get("/certificates?limit=50", bearer).get("data", [])
    profiles_data = get("/profiles?limit=50&include=bundleId,certificates", bearer).get("data", [])

    cs_out = subprocess.run(
        ["/usr/bin/security", "find-identity", "-v", "-p", "codesigning"],
        capture_output=True,
        text=True,
    ).stdout
    all_out = subprocess.run(
        ["/usr/bin/security", "find-identity", "-v"],
        capture_output=True,
        text=True,
    ).stdout
    local_profs = scan_local_mac_store_profiles()

    status = classify_signing_readiness(
        bundle_ids_data=bundle_ids_data,
        certs_data=certs_data,
        profiles_data=profiles_data,
        keychain_codesign_output=cs_out,
        keychain_all_output=all_out,
        local_mac_profiles=local_profs,
    )
    status["_raw_profiles"] = profiles_data
    return status


def provision_mac_profiles(bearer: str, status: dict[str, Any]) -> None:
    """Create or download additive MAC_APP_STORE profiles for app and widget."""
    cert_id = status.get("apple_distribution_cert_id")
    if not cert_id:
        die("cannot provision MAC_APP_STORE profiles: no DISTRIBUTION cert found in ASC")

    bid_to_res = {
        APP_BUNDLE_ID: status.get("app_bundle_resource_id"),
        WIDGET_BUNDLE_ID: status.get("widget_bundle_resource_id"),
    }
    os.makedirs(DEFAULT_PROFILE_DIR, exist_ok=True)

    existing_profiles = status.get("_raw_profiles") or []
    for bid, prof_name in MAC_PROFILE_SPECS:
        res_id = bid_to_res.get(bid)
        if not res_id:
            die(f"cannot provision MAC_APP_STORE profile for {bid}: bundleId resource not found")

        matched = None
        for p in existing_profiles:
            at = p.get("attributes") or {}
            rel_bid = ((p.get("relationships") or {}).get("bundleId") or {}).get("data") or {}
            if (
                at.get("profileType") == "MAC_APP_STORE"
                and at.get("profileState") == "ACTIVE"
                and rel_bid.get("id") == res_id
            ):
                matched = p
                break

        if matched is None:
            payload = build_profile_create_payload(
                profile_name=prof_name,
                bundle_id_resource_id=res_id,
                apple_distribution_cert_id=cert_id,
            )
            code, resp = post_json("/profiles", payload, bearer)
            if code not in (200, 201):
                die(f"POST /profiles for {bid} failed with HTTP {code}: {json.dumps(resp)}")
            matched = resp.get("data") or {}
            print(f"created ASC MAC_APP_STORE profile: {prof_name} (id {matched.get('id')})")
        else:
            print(
                f"reusing active ASC MAC_APP_STORE profile: "
                f"{(matched.get('attributes') or {}).get('name')} (id {matched.get('id')})"
            )

        at = matched.get("attributes") or {}
        uuid = at.get("uuid") or matched.get("id")
        content_b64 = at.get("profileContent")
        if not content_b64:
            die(f"ASC profile {matched.get('id')} carried no profileContent")
        out_path = os.path.join(DEFAULT_PROFILE_DIR, f"{uuid}.provisionprofile")
        with open(out_path, "wb") as fh:
            fh.write(base64.b64decode(content_b64))
        print(f"installed {out_path} for {bid}")


def provision_installer_cert(bearer: str) -> None:
    """Generate a local RSA-2048 CSR, mint MAC_INSTALLER_DISTRIBUTION in ASC, and import into login keychain."""
    tmp_dir = tempfile.mkdtemp(prefix="asc-mac-installer-")
    os.chmod(tmp_dir, 0o700)
    try:
        key_path = os.path.join(tmp_dir, "installer.key")
        csr_path = os.path.join(tmp_dir, "installer.csr")
        der_path = os.path.join(tmp_dir, "installer.cer")
        pem_path = os.path.join(tmp_dir, "installer.pem")
        p12_path = os.path.join(tmp_dir, "installer.p12")

        subprocess.run(
            [
                "/usr/bin/openssl",
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                key_path,
                "-out",
                csr_path,
                "-subj",
                "/CN=Alex Bain/O=Alex Bain/C=US",
            ],
            check=True,
            capture_output=True,
        )
        with open(csr_path, "r", encoding="utf-8") as fh:
            csr_text = fh.read()

        payload = build_installer_cert_create_payload(csr_pem_or_base64=csr_text)
        code, resp = post_json("/certificates", payload, bearer)
        if code not in (200, 201):
            die(f"POST /certificates (MAC_INSTALLER_DISTRIBUTION) failed with HTTP {code}: {json.dumps(resp)}")

        cert_data = resp.get("data") or {}
        cert_id = cert_data.get("id")
        cert_b64 = (cert_data.get("attributes") or {}).get("certificateContent")
        if not cert_b64:
            die(f"ASC certificate {cert_id} returned no certificateContent")

        with open(der_path, "wb") as fh:
            fh.write(base64.b64decode(cert_b64))

        subprocess.run(
            ["/usr/bin/openssl", "x509", "-inform", "DER", "-in", der_path, "-out", pem_path],
            check=True,
            capture_output=True,
        )
        p12_pass = base64.urlsafe_b64encode(os.urandom(18)).decode("ascii")
        subprocess.run(
            [
                "/usr/bin/openssl",
                "pkcs12",
                "-export",
                "-out",
                p12_path,
                "-inkey",
                key_path,
                "-in",
                pem_path,
                "-passout",
                f"pass:{p12_pass}",
            ],
            check=True,
            capture_output=True,
        )
        keychain = os.path.expanduser("~/Library/Keychains/login.keychain-db")
        imp = subprocess.run(
            [
                "/usr/bin/security",
                "import",
                p12_path,
                "-k",
                keychain,
                "-P",
                p12_pass,
                "-T",
                "/usr/bin/productbuild",
                "-T",
                "/usr/bin/pkgbuild",
                "-T",
                "/usr/bin/codesign",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if imp.returncode != 0:
            imp2 = subprocess.run(
                [
                    "/usr/bin/security",
                    "import",
                    p12_path,
                    "-k",
                    keychain,
                    "-P",
                    p12_pass,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if imp2.returncode != 0:
                die(
                    f"created ASC MAC_INSTALLER_DISTRIBUTION cert (id {cert_id}), "
                    f"but local keychain import failed: {(imp2.stderr or imp2.stdout).strip()}"
                )
        print(f"created and imported MAC_INSTALLER_DISTRIBUTION certificate (ASC id {cert_id})")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def self_check() -> None:
    """Offline assertions for payload builders and signing readiness classification."""
    p_payload = build_profile_create_payload(
        profile_name="BainLuck Mac App AppStore",
        bundle_id_resource_id="DSAW22CLG7",
        apple_distribution_cert_id="LJQ9K3973X",
    )
    assert p_payload["data"]["attributes"]["profileType"] == "MAC_APP_STORE"
    assert p_payload["data"]["relationships"]["bundleId"]["data"]["id"] == "DSAW22CLG7"
    assert p_payload["data"]["relationships"]["certificates"]["data"] == [
        {"type": "certificates", "id": "LJQ9K3973X"}
    ]

    c_payload = build_installer_cert_create_payload(
        csr_pem_or_base64="-----BEGIN CERTIFICATE REQUEST-----\nMIIB...TEST\n-----END CERTIFICATE REQUEST-----\n"
    )
    assert c_payload["data"]["attributes"]["certificateType"] == "MAC_INSTALLER_DISTRIBUTION"
    assert c_payload["data"]["attributes"]["csrContent"] == "MIIB...TEST"

    bundles = [
        {"id": "DSAW22CLG7", "attributes": {"identifier": APP_BUNDLE_ID, "platform": "UNIVERSAL"}},
        {"id": "87A2TQ5M6K", "attributes": {"identifier": WIDGET_BUNDLE_ID, "platform": "UNIVERSAL"}},
    ]
    certs_missing_inst = [
        {"id": "LJQ9K3973X", "attributes": {"certificateType": "DISTRIBUTION"}},
    ]
    profs_ios_only = [
        {"id": "5M3V56C2HC", "attributes": {"name": "BainLuck App AppStore 38", "profileType": "IOS_APP_STORE", "profileState": "ACTIVE"}},
    ]
    st_blocked = classify_signing_readiness(
        bundle_ids_data=bundles,
        certs_data=certs_missing_inst,
        profiles_data=profs_ios_only,
        keychain_codesign_output='1) ABCD "Apple Distribution: Alex Bain (J893F72P4R)"',
        keychain_all_output='1) ABCD "Apple Distribution: Alex Bain (J893F72P4R)"',
        local_mac_profiles={},
    )
    assert not st_blocked["ready"]
    assert st_blocked["apple_distribution_cert_id"] == "LJQ9K3973X"
    assert len(st_blocked["missing_items"]) == 4

    certs_full = certs_missing_inst + [
        {"id": "INST123", "attributes": {"certificateType": "MAC_INSTALLER_DISTRIBUTION"}},
    ]
    profs_full = profs_ios_only + [
        {"id": "MAC1", "attributes": {"name": "BainLuck Mac App AppStore", "profileType": "MAC_APP_STORE", "profileState": "ACTIVE"}},
        {"id": "MAC2", "attributes": {"name": "BainLuck Mac Widget AppStore", "profileType": "MAC_APP_STORE", "profileState": "ACTIVE"}},
    ]
    st_ready = classify_signing_readiness(
        bundle_ids_data=bundles,
        certs_data=certs_full,
        profiles_data=profs_full,
        keychain_codesign_output='1) ABCD "Apple Distribution: Alex Bain (J893F72P4R)"',
        keychain_all_output='1) ABCD "Apple Distribution: Alex Bain (J893F72P4R)"\n2) EF01 "3rd Party Mac Developer Installer: Alex Bain (J893F72P4R)"',
        local_mac_profiles={
            APP_BUNDLE_ID: "BainLuck Mac App AppStore",
            WIDGET_BUNDLE_ID: "BainLuck Mac Widget AppStore",
        },
    )
    assert st_ready["ready"], st_ready

    print(
        "self-check: OK (additive MAC_APP_STORE profile + MAC_INSTALLER_DISTRIBUTION cert payloads "
        "and readiness classifier verified)"
    )


def main() -> None:
    mode = "status"
    for arg in sys.argv[1:]:
        if arg == "--self-check":
            self_check()
            return
        if arg == "--status":
            mode = "status"
        elif arg == "--provision-profiles":
            mode = "provision-profiles"
        elif arg == "--provision-installer-cert":
            mode = "provision-installer-cert"
        elif arg == "--provision-all":
            mode = "provision-all"
        elif arg in ("-h", "--help"):
            print(__doc__.strip())
            return
        else:
            die(f"unknown argument: {arg}")

    bearer = token()
    status = inspect_status(bearer)

    if mode in ("provision-profiles", "provision-all"):
        provision_mac_profiles(bearer, status)
        status = inspect_status(bearer)

    if mode in ("provision-installer-cert", "provision-all"):
        if not status["has_local_mac_installer"]:
            provision_installer_cert(bearer)
            status = inspect_status(bearer)
        else:
            print("reusing existing local Mac Installer Distribution identity in Keychain")

    clean_out = {k: v for k, v in status.items() if not k.startswith("_")}
    print(json.dumps(clean_out, indent=2))
    if not status["ready"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
