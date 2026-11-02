#!/usr/bin/env python3
"""TestFlight selection, next build number and artifact checks for the release loop."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import plistlib
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.0.5"
BUNDLE_ID = "com.bainluck.Bain-Luck"
START = datetime(2026, 11, 3, tzinfo=ZoneInfo("America/Los_Angeles"))


def eligible(files, now):
    return now >= START and any(path.startswith("ios/") for path in files)


def master_floor(project):
    values = re.findall(r"CURRENT_PROJECT_VERSION\s*=\s*([0-9]+)\s*;", project)
    assignments = re.findall(r"CURRENT_PROJECT_VERSION\s*=\s*([^;]+);", project)
    if not values or len(values) != len(assignments):
        raise ValueError(
            "Cannot read every build number from master project; refusing to guess"
        )
    return max(map(int, values))


def release_version(project):
    values = re.findall(r"MARKETING_VERSION\s*=\s*([0-9]+(?:\.[0-9]+)*)\s*;", project)
    if not values:
        raise ValueError("Cannot read marketing version from source project")
    return max([VERSION] + values, key=lambda value: tuple(map(int, value.split("."))))


def next_build(apple_numbers, master_number):
    numbers = [99, int(master_number)]
    for number in apple_numbers:
        if not re.fullmatch(r"[0-9]+", str(number)):
            raise ValueError(
                "Unexpected App Store Connect build number; refusing to reuse a number"
            )
        numbers.append(int(number))
    return max(numbers) + 1


def apple_builds(get, app_id, version):
    path = f"/builds?filter[app]={app_id}&limit=200&include=preReleaseVersion"
    rows = []
    seen = set()
    while path:
        if path in seen:
            raise ValueError("App Store Connect pagination loop")
        seen.add(path)
        document = get(path)
        trains = {
            item["id"]: item["attributes"]["version"]
            for item in document.get("included", [])
            if item["type"] == "preReleaseVersions"
        }
        for row in document["data"]:
            identifier = (
                row.get("relationships", {})
                .get("preReleaseVersion", {})
                .get("data", {})
                .get("id")
            )
            if identifier not in trains:
                raise ValueError(
                    "App Store Connect omitted a build version; refusing a partial number list"
                )
            if trains[identifier] == version:
                rows.append(row)
        path = document.get("links", {}).get("next")
        if path:
            url = urlparse(path)
            if (
                url.scheme != "https"
                or url.netloc != "api.appstoreconnect.apple.com"
                or not url.path.startswith("/v1/")
            ):
                raise ValueError("App Store Connect pagination left its API origin")
    return rows


def apple_client():
    spec = importlib.util.spec_from_file_location(
        "existing_asc_builds", ROOT / "tools" / "asc-builds.py"
    )
    asc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(asc)

    # Mint per request: long processing checks must not keep an expired JWT.
    def get(path):
        return asc.get(path, asc.token())

    apps = get(f"/apps?filter[bundleId]={BUNDLE_ID}")["data"]
    if len(apps) != 1:
        raise ValueError("App Store Connect did not return exactly one Bain Luck app")
    return get, apps[0]["id"]


def verify_bundles(root, version, build):
    apps = list(Path(root).glob("*.app"))
    if len(apps) != 1:
        raise ValueError("Expected one main .app; build output is missing or ambiguous")
    app = apps[0]
    bundles = [app] + [
        p for p in app.rglob("*") if p.is_dir() and p.suffix in {".app", ".appex"}
    ]
    for bundle in bundles:
        with (bundle / "Info.plist").open("rb") as source:
            info = plistlib.load(source)
        if (
            str(info.get("CFBundleVersion")) != str(build)
            or info.get("CFBundleShortVersionString") != version
        ):
            raise ValueError(f"{bundle.name} does not carry {version} ({build})")
    return app


def verify_delivery(document):
    if document.get("product-errors") or not document.get("success-message"):
        raise ValueError(
            "App Store Connect delivery did not report success without errors"
        )


def confirm(build, version, source, receipt):
    get, app_id = apple_client()
    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        matching = [
            row
            for row in apple_builds(get, app_id, version)
            if row["attributes"]["version"] == str(build)
        ]
        if len(matching) > 1:
            raise ValueError("App Store Connect returned duplicate build numbers")
        if matching:
            row = matching[0]
            state = row["attributes"]["processingState"]
            if state == "VALID":
                document = {
                    "source_sha": source,
                    "version": version,
                    "build": int(build),
                    "asc_build_id": row["id"],
                    "processing_state": state,
                    "confirmed_at": datetime.now(timezone.utc).isoformat(),
                }
                Path(receipt).write_text(json.dumps(document, indent=2) + "\n")
                print(f"TestFlight accepted {version} ({build}) from {source}")
                return
            if state in {"FAILED", "INVALID"}:
                raise ValueError(f"App Store Connect processing failed: {state}")
        print(
            f"Waiting for App Store Connect to finish processing {version} ({build})",
            flush=True,
        )
        time.sleep(30)
    raise TimeoutError("App Store Connect did not confirm VALID within thirty minutes")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=["scope", "reserve", "bundles", "delivery", "confirm"]
    )
    parser.add_argument("--before")
    parser.add_argument("--source", default=os.environ.get("GITHUB_SHA"))
    parser.add_argument("--master-project")
    parser.add_argument("--root")
    parser.add_argument("--log")
    parser.add_argument("--build", type=int)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--receipt")
    args = parser.parse_args()
    if args.command == "scope":
        files = (
            subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(ROOT),
                    "diff",
                    "--name-only",
                    "-z",
                    args.before,
                    args.source,
                ]
            )
            .decode()
            .split("\0")
        )
        result = eligible(files, datetime.now(timezone.utc))
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write("eligible=" + str(result).lower() + "\n")
        print("TestFlight eligible: " + str(result).lower())
    elif args.command == "reserve":
        source_project = (
            ROOT / "ios" / "Bain Luck" / "Bain Luck.xcodeproj" / "project.pbxproj"
        ).read_text()
        args.version = release_version(source_project)
        get, app_id = apple_client()
        numbers = [
            row["attributes"]["version"]
            for row in apple_builds(get, app_id, args.version)
        ]
        number = next_build(
            numbers, master_floor(Path(args.master_project).read_text())
        )
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"build={number}\nversion={args.version}\n")
        print(f"Next TestFlight build: {args.version} ({number})")
    elif args.command == "bundles":
        print(verify_bundles(Path(args.root), args.version, args.build))
    elif args.command == "delivery":
        verify_delivery(json.loads(Path(args.log).read_text()))
    elif args.command == "confirm":
        confirm(args.build, args.version, args.source, args.receipt)


if __name__ == "__main__":
    main()
