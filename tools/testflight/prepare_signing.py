#!/usr/bin/env python3
"""Stage Actions signing secrets outside the checkout, then import a private keychain."""
from __future__ import annotations

import base64
import io
import os
import plistlib
import re
import secrets
import subprocess
import zipfile
from pathlib import Path
from datetime import datetime, timezone

NAMES = (
    "ASC_KEY_ID",
    "ASC_ISSUER_ID",
    "ASC_PRIVATE_KEY",
    "IOS_SIGNING_P12_BASE64",
    "IOS_SIGNING_P12_PASSWORD",
    "IOS_PROVISIONING_PROFILES_BASE64",
)


def profile_files(encoded):
    result = {}
    with zipfile.ZipFile(
        io.BytesIO(base64.b64decode("".join(encoded.split()), validate=True))
    ) as archive:
        for item in archive.infolist():
            name = item.filename
            if (
                name != Path(name).name
                or not name.endswith(".mobileprovision")
                or name in result
            ):
                raise ValueError(
                    "Profiles secret must be a flat zip of uniquely named .mobileprovision files"
                )
            if not 0 < item.file_size < 10_000_000:
                raise ValueError("Provisioning profile is empty or unexpectedly large")
            result[name] = archive.read(item)
    if not result:
        raise ValueError("No provisioning profiles supplied")
    return result


def profile_bundle(info):
    if info.get("TeamIdentifier") != ["J893F72P4R"] or "ProvisionedDevices" in info:
        raise ValueError("Provisioning profile is not a Bain Luck App Store profile")
    expiry = info.get("ExpirationDate")
    if expiry is None or expiry.replace(tzinfo=timezone.utc) <= datetime.now(
        timezone.utc
    ):
        raise ValueError("Provisioning profile has expired")
    identifier = info.get("Entitlements", {}).get("application-identifier", "")
    if not identifier.startswith("J893F72P4R."):
        raise ValueError("Provisioning profile does not identify the Bain Luck team")
    return identifier.removeprefix("J893F72P4R.")


def private_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(content)


def main():
    missing = [name for name in NAMES if not os.environ.get(name)]
    if missing:
        raise ValueError("Missing Actions signing secrets: " + ", ".join(missing))
    key_id = os.environ["ASC_KEY_ID"]
    if not re.fullmatch("[A-Za-z0-9]+", key_id):
        raise ValueError("ASC_KEY_ID has an unexpected format")
    profiles = profile_files(os.environ["IOS_PROVISIONING_PROFILES_BASE64"])
    p12 = base64.b64decode(
        "".join(os.environ["IOS_SIGNING_P12_BASE64"].split()), validate=True
    )
    directory = Path(os.environ["RUNNER_TEMP"]) / "testflight-signing"
    directory.mkdir(mode=0o700)
    certificate = directory / "distribution.p12"
    private_file(certificate, p12)
    key = Path.home() / ".appstoreconnect" / "private_keys" / f"AuthKey_{key_id}.p8"
    private_file(key, os.environ["ASC_PRIVATE_KEY"].encode())
    profile_directory = (
        Path.home()
        / "Library"
        / "Developer"
        / "Xcode"
        / "UserData"
        / "Provisioning Profiles"
    )
    bundles = set()
    for name, content in profiles.items():
        path = profile_directory / name
        private_file(path, content)
        decoded = subprocess.check_output(["security", "cms", "-D", "-i", str(path)])
        bundles.add(profile_bundle(plistlib.loads(decoded)))
    required = {"com.bainluck.Bain-Luck", "com.bainluck.Bain-Luck.BainLuckWidget"}
    if not required <= bundles:
        raise ValueError(
            "Store profiles are missing for: " + ", ".join(sorted(required - bundles))
        )
    keychain = directory / "release.keychain-db"
    password = secrets.token_urlsafe(32)

    def security(*args):
        try:
            subprocess.run(["security", *args], check=True, stdout=subprocess.DEVNULL)
        except subprocess.CalledProcessError as error:
            # Never include argv: import/unlock commands contain passwords.
            raise RuntimeError(
                f"Signing tool {args[0]} failed with exit {error.returncode}"
            ) from None

    security("create-keychain", "-p", password, str(keychain))
    security("set-keychain-settings", "-lut", "21600", str(keychain))
    security("unlock-keychain", "-p", password, str(keychain))
    security(
        "import",
        str(certificate),
        "-k",
        str(keychain),
        "-P",
        os.environ["IOS_SIGNING_P12_PASSWORD"],
        "-T",
        "/usr/bin/codesign",
        "-T",
        "/usr/bin/security",
    )
    security(
        "set-key-partition-list",
        "-S",
        "apple-tool:,apple:,codesign:",
        "-s",
        "-k",
        password,
        str(keychain),
    )
    security("list-keychains", "-d", "user", "-s", str(keychain))
    identities = subprocess.check_output(
        ["security", "find-identity", "-v", "-p", "codesigning", str(keychain)]
    ).decode()
    if "Apple Distribution" not in identities:
        raise ValueError(
            "P12 does not provide a valid Apple Distribution signing identity"
        )
    with open(os.environ["GITHUB_ENV"], "a") as output:
        output.write(f"ASC_KEY_PATH={key}\nTESTFLIGHT_KEYCHAIN={keychain}\n")
    print("App Store Connect key and distribution signing assets prepared")


if __name__ == "__main__":
    main()
