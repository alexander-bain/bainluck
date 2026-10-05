"""Read-only evidence that an unsigned iPhone archive actually carries its Watch app."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import subprocess

PHONE = "com.bainluck.Bain-Luck"
WATCH = PHONE + ".watchkitapp"
ACTIVITY = "com.bainluck.view-game"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(root, path):
    require(not path.is_absolute() and ".." not in path.parts, "Unsafe archive-relative path")
    current = root
    require(not root.is_symlink(), "Symlink archive root")
    for part in path.parts:
        current = current / part
        require(not current.is_symlink(), f"Symlink in evidence path: {current.name}")
    return current


def read_plist(root, path):
    try:
        result = plistlib.loads(safe_path(root, path).read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError) as error:
        raise ValueError(f"Unreadable plist: {path}") from error
    require(isinstance(result, dict), f"Not a plist dictionary: {path}")
    return result


def read_platform(binary):
    try:
        output = subprocess.check_output(["xcrun", "vtool", "-show-build", str(binary)], text=True, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Cannot inspect executable build platform") from error
    platforms = re.findall(r"^\s*platform\s+(\S+)\s*$", output, re.MULTILINE)
    require(bool(platforms) and len(set(platforms)) == 1, "Missing or mixed executable platforms")
    return platforms[0]


def inspect_archive(archive: Path, platform_reader=read_platform):
    archive = Path(archive)
    properties = read_plist(archive, Path("Info.plist")).get("ApplicationProperties", {})
    require(isinstance(properties, dict), "Missing archive application properties")
    application_path = properties.get("ApplicationPath")
    require(isinstance(application_path, str) and bool(application_path), "Missing archive application path")
    relative = Path(application_path)
    require(len(relative.parts) == 2 and relative.parts[0] == "Applications", "Expected one application in archive Applications")
    phone_path = Path("Products") / relative
    phone = safe_path(archive, phone_path)
    applications = safe_path(archive, Path("Products/Applications"))
    require(list(applications.glob("*.app")) == [phone], "Archive must contain exactly the phone app")
    watch_folder = safe_path(archive, phone_path / "Watch")
    watches = list(watch_folder.glob("*.app"))
    require(len(watches) == 1, "iPhone archive must embed exactly one Watch app")
    watch_path = watches[0].relative_to(archive)
    watch = safe_path(archive, watch_path)
    phone_info = read_plist(archive, phone_path / "Info.plist")
    watch_info = read_plist(archive, watch_path / "Info.plist")
    evidence = []
    for folder, relative_folder, info, bundle_id, plist_platform, binary_platform in [
        (phone, phone_path, phone_info, PHONE, "iPhoneOS", "IOS"),
        (watch, watch_path, watch_info, WATCH, "WatchOS", "WATCHOS"),
    ]:
        require(info.get("CFBundleIdentifier") == bundle_id, "Unexpected application identity")
        require(info.get("CFBundleSupportedPlatforms") == [plist_platform], "Simulator or wrong-platform plist")
        require(ACTIVITY in info.get("NSUserActivityTypes", []), "Missing Handoff registration")
        name = info.get("CFBundleExecutable")
        require(isinstance(name, str) and name not in ("", ".", "..") and Path(name).name == name, "Invalid executable name")
        binary = safe_path(archive, relative_folder / name)
        require(binary.is_file() and binary.stat().st_size > 0, "Missing or empty executable")
        require(platform_reader(binary) == binary_platform, "Simulator or wrong-platform executable")
        evidence.append({"bundle_id": bundle_id, "platform": binary_platform,
                         "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()})
    require(watch_info.get("WKCompanionAppBundleIdentifier") == PHONE, "Wrong phone companion")
    require(watch_info.get("WKWatchOnly", False) is False, "Watch-only app cannot pass companion packaging")
    require(watch_info.get("WKRunsIndependentlyOfCompanionApp") is True, "Public Watch app must run independently")
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        require(isinstance(phone_info.get(key), str) and bool(phone_info[key]), f"Missing phone {key}")
        require(phone_info[key] == watch_info.get(key), f"Phone/Watch {key} mismatch")
    return {"verdict": "PACKAGED_UNSIGNED_CANDIDATE", "physical_install": "UNVERIFIED",
            "distribution": "UNVERIFIED", "signing": "UNVERIFIED", "applications": evidence,
            "version": phone_info["CFBundleShortVersionString"], "build": phone_info["CFBundleVersion"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        receipt = inspect_archive(args.archive)
        code = 0
    except (ValueError, OSError, TypeError) as error:
        receipt = {"verdict": "UNPAID", "reason": str(error), "physical_install": "UNVERIFIED", "distribution": "UNVERIFIED"}
        code = 1
    receipt["sha"] = args.sha
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
