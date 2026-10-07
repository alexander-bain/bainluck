"""Read local Watch package structure and supplied, hash-bound entitlement evidence.

This never verifies signatures, profiles, distribution readiness or installation.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import stat
import tempfile
import zipfile

from watch_companion_archive import (
    PHONE, WATCH, COMPLICATION, inspect_archive, read_platform, read_plist,
    require, safe_path,
)

WIDGET = PHONE + ".BainLuckWidget"
GROUP = "group.com.bainluck.watch"
MAX_ENTRIES = 20000
MAX_MEMBER = 512 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
LIMITS = {key: "UNVERIFIED" for key in (
    "signature_authenticity", "provisioning_profiles", "distribution",
    "apple_processing", "physical_install", "source_coverage",
)}


def normalize_ipa(ipa, root):
    """Normalize only a bounded, regular-file Payload into an archive layout."""
    with zipfile.ZipFile(ipa) as package:
        entries = package.infolist()
        require(0 < len(entries) <= MAX_ENTRIES, "IPA entry limit exceeded")
        seen = set()
        total = 0
        for item in entries:
            name = item.filename
            path = PurePosixPath(name)
            require(name and path.parts and not path.is_absolute() and ".." not in path.parts
                    and "\\" not in name and "\x00" not in name
                    and str(path) == name.rstrip("/"), "Unsafe IPA path")
            require(str(path) not in seen, "Duplicate IPA path")
            seen.add(str(path))
            mode = item.external_attr >> 16
            require(not stat.S_ISLNK(mode), "IPA symlink rejected")
            require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR), "IPA special file rejected")
            require(not item.flag_bits & 1, "Encrypted IPA rejected")
            require(item.file_size <= MAX_MEMBER, "IPA member size limit exceeded")
            total += item.file_size
            require(total <= MAX_TOTAL, "IPA total size limit exceeded")
        require(any(PurePosixPath(i.filename).parts[0] == "Payload" for i in entries), "IPA lacks Payload")
        for item in entries:
            path = PurePosixPath(item.filename)
            if path.parts[0] != "Payload":
                continue
            target = root / "Products/Applications" / Path(*path.parts[1:])
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as source, target.open("xb") as destination:
                copied = 0
                while block := source.read(1024 * 1024):
                    copied += len(block)
                    require(copied <= item.file_size and copied <= MAX_MEMBER, "IPA expanded size limit exceeded")
                    destination.write(block)
                require(copied == item.file_size, "IPA size mismatch")
    apps = list((root / "Products/Applications").glob("*.app"))
    require(len(apps) == 1, "IPA must contain exactly one phone app")
    (root / "Info.plist").write_bytes(plistlib.dumps({"ApplicationProperties": {
        "ApplicationPath": "Applications/" + apps[0].name,
    }}))


def inspect_package(artifact, manifest, platform_reader=read_platform):
    artifact = Path(artifact)
    require(not artifact.is_symlink(), "Symlink artifact rejected")
    require(artifact.suffix in (".ipa", ".xcarchive"), "Expected .ipa or .xcarchive")
    with tempfile.TemporaryDirectory(prefix="watch-package-") as scratch:
        root = artifact
        if artifact.suffix == ".ipa":
            root = Path(scratch)
            normalize_ipa(artifact, root)
        receipt = inspect_archive(root, platform_reader=platform_reader)
        properties = read_plist(root, Path("Info.plist"))["ApplicationProperties"]
        phone_path = Path("Products") / properties["ApplicationPath"]
        plugins = safe_path(root, phone_path / "PlugIns")
        widgets = []
        for candidate in plugins.glob("*.appex"):
            relative = candidate.relative_to(root)
            info = read_plist(root, relative / "Info.plist")
            if info.get("CFBundleIdentifier") == WIDGET:
                widgets.append((relative, info))
        require(len(widgets) == 1, "Missing or duplicate phone widget")
        relative, info = widgets[0]
        require(info.get("CFBundleSupportedPlatforms") == ["iPhoneOS"], "Wrong phone widget platform")
        require(info.get("CFBundleShortVersionString") == receipt["version"]
                and info.get("CFBundleVersion") == receipt["build"], "Phone widget version mismatch")
        extension = info.get("NSExtension")
        require(isinstance(extension, dict) and extension.get("NSExtensionPointIdentifier") == "com.apple.widgetkit-extension", "Wrong phone widget extension type")
        name = info.get("CFBundleExecutable")
        require(isinstance(name, str) and name not in ("", ".", "..") and Path(name).name == name, "Invalid widget executable")
        binary = safe_path(root, relative / name)
        require(binary.is_file() and binary.stat().st_size > 0, "Missing widget executable")
        require(platform_reader(binary) == "IOS", "Wrong phone widget executable platform")
        receipt["applications"].append({"bundle_id": WIDGET, "platform": "IOS",
            "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()})
        require(isinstance(manifest, dict) and manifest.get("version") == 1, "Unsupported entitlement evidence manifest")
        supplied = manifest.get("applications")
        require(isinstance(supplied, list) and len(supplied) == 4, "Require four supplied entitlement records")
        indexed = {}
        teams = set()
        for record in supplied:
            require(isinstance(record, dict), "Malformed entitlement record")
            bid = record.get("bundle_id")
            require(isinstance(bid, str) and bid not in indexed, "Duplicate or malformed entitlement identity")
            indexed[bid] = record
        require(set(indexed) == {PHONE, WIDGET, WATCH, COMPLICATION}, "Unexpected supplied bundle identities")
        for app in receipt["applications"]:
            record = indexed[app["bundle_id"]]
            require(record.get("executable_sha256") == app["executable_sha256"], "Supplied entitlement executable hash mismatch")
            entitlements = record.get("entitlements")
            require(isinstance(entitlements, dict), "Missing supplied entitlements")
            team = entitlements.get("com.apple.developer.team-identifier")
            require(isinstance(team, str) and team.strip() == team and bool(team), "Missing supplied team identity")
            require(entitlements.get("application-identifier") == team + "." + app["bundle_id"], "Supplied application identity mismatch")
            teams.add(team)
            if app["bundle_id"] in (WATCH, COMPLICATION):
                groups = entitlements.get("com.apple.security.application-groups")
                require(isinstance(groups, list) and all(isinstance(g, str) for g in groups)
                        and GROUP in groups, "Missing required supplied Watch AppGroup")
        require(len(teams) == 1, "Supplied team identities disagree")
        receipt.update(LIMITS)
        receipt["verdict"] = "PACKAGE_AND_SUPPLIED_EVIDENCE_CONSISTENT"
        receipt["entitlements_evidence"] = "SUPPLIED_HASH_BOUND_NOT_CRYPTOGRAPHICALLY_VERIFIED"
        receipt["artifact_kind"] = artifact.suffix[1:]
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--entitlements-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Never let receipt output overwrite an input or a file within the archive.
    output = args.output.resolve()
    for source in (args.artifact.resolve(), args.entitlements_evidence.resolve()):
        require(output != source and source not in output.parents, "Receipt output overlaps input")
        require(not (output.exists() and source.exists() and output.samefile(source)),
                "Receipt output is hardlinked to input")
    try:
        require(args.entitlements_evidence.stat().st_size <= 1024 * 1024, "Entitlement evidence exceeds size limit")
        manifest = json.loads(args.entitlements_evidence.read_text())
        receipt = inspect_package(args.artifact, manifest)
        code = 0
    except (ValueError, OSError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        receipt = dict(LIMITS, verdict="UNPAID", reason=str(error))
        code = 1
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
