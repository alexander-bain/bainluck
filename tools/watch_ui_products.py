"""Immutable, relocatable simulator products; never resolve packages or build here."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import subprocess
import tarfile

GROUP = "group.com.bainluck.watch"
XCTEST = "BainLuckWatchUITests"
WATCH = "BainLuckWatch Watch App"
XCTENTS = {
    WATCH: WATCH + ".app-Simulated.xcent",
    "BainLuckComplication": "BainLuckComplication.appex-Simulated.xcent",
}
PINS = "ios/Bain Luck/Bain Luck.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def relative(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe product path: " + name)
    return path


def inventory(root):
    records = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        relative(name)
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).is_absolute() or os.path.commonpath(
                [path.resolve(), root.resolve()]
            ) != str(root.resolve()):
                raise ValueError("Product symlink escapes package: " + name)
            if not path.exists():
                raise ValueError("Broken product symlink: " + name)
            records[name] = {"kind": "symlink", "target": target, "mode": mode}
        elif path.is_file():
            records[name] = {"kind": "file", "sha256": digest(path), "mode": mode}
        elif not path.is_dir():
            raise ValueError("Unsupported product entry: " + name)
    return records


def version_tuple(value):
    return tuple(int(part) for part in (value.split(".") + ["0", "0"])[:3])


def check_layout(payload, environment=None, carrier_stubs=None):
    carrier_stubs = carrier_stubs or {}
    runs = list((payload / "watch/Build/Products").glob("*.xctestrun"))
    if len(runs) != 1:
        raise ValueError("Expected one xctestrun")
    run = runs[0]
    data = plistlib.loads(run.read_bytes())
    if set(data) != {XCTEST, "__xctestrun_metadata__"}:
        raise ValueError("Unexpected xctestrun targets")
    target = data[XCTEST]
    expected = {
        "TestHostPath": "__TESTROOT__/Debug-watchsimulator/BainLuckWatchUITests-Runner.app",
        "TestBundlePath": "__TESTHOST__/PlugIns/BainLuckWatchUITests.xctest",
        "UITargetAppPath": "__TESTROOT__/Debug-watchsimulator/BainLuckWatch Watch App.app",
    }
    for key, value in expected.items():
        if target.get(key) != value:
            raise ValueError("Unexpected xctestrun " + key)
    host = run.parent / target["TestHostPath"].replace("__TESTROOT__/", "")

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            for part in value.split(":"):
                if part.startswith(("__TESTROOT__", "__TESTHOST__")):
                    token, suffix = part.split("/", 1)
                    relative(suffix)
                    resolved = (
                        run.parent if token == "__TESTROOT__" else host
                    ) / suffix
                    # PackageFrameworks search directories may legitimately be empty.
                    if not resolved.exists() and resolved.name != "PackageFrameworks":
                        raise ValueError("Missing xctestrun product: " + part)
                elif part.startswith("__PLATFORMS__/"):
                    relative(part.removeprefix("__PLATFORMS__/"))
                elif part.startswith("/") and part != "/usr/lib/libRPAC.dylib":
                    raise ValueError("External absolute xctestrun path: " + part)

    walk(target)
    dependencies = target.get("DependentProductPaths", [])
    required = [
        "__TESTROOT__/Debug-watchsimulator/BainLuckComplication.appex",
        expected["UITargetAppPath"],
        expected["TestHostPath"],
        expected["TestHostPath"] + "/PlugIns/BainLuckWatchUITests.xctest",
    ]
    if set(dependencies) != set(required):
        raise ValueError("Incomplete xctestrun dependent products")
    for name, filename in XCTENTS.items():
        xcent = (
            payload
            / "watch/Build/Intermediates.noindex/Bain Luck.build/Debug-watchsimulator"
            / (name + ".build")
            / filename
        )
        if GROUP not in plistlib.loads(xcent.read_bytes()).get(
            "com.apple.security.application-groups", []
        ):
            raise ValueError("Generated xcent lacks shared Watch group")
    phone = payload / "phone/Bain Luck.app"
    products = [
        (phone, "com.bainluck.Bain-Luck", "iPhoneSimulator"),
        (
            phone / "Watch/BainLuckWatch Watch App.app",
            "com.bainluck.Bain-Luck.watchkitapp",
            "WatchSimulator",
        ),
        (
            run.parent / "Debug-watchsimulator/BainLuckWatch Watch App.app",
            "com.bainluck.Bain-Luck.watchkitapp",
            "WatchSimulator",
        ),
        (
            run.parent / "Debug-watchsimulator/BainLuckComplication.appex",
            "com.bainluck.Bain-Luck.watchkitapp.SavedGlance",
            "WatchSimulator",
        ),
    ]
    for product, bundle, platform in products:
        info = plistlib.loads((product / "Info.plist").read_bytes())
        if info.get("CFBundleIdentifier") != bundle or platform not in info.get(
            "CFBundleSupportedPlatforms", []
        ):
            raise ValueError("Product identity/platform mismatch: " + str(product))
        if environment is not None:
            sdk = environment[
                "phone_sdk" if platform == "iPhoneSimulator" else "watch_sdk"
            ]
            minimum = info.get("MinimumOSVersion")
            if not minimum or version_tuple(minimum) > version_tuple(sdk):
                raise ValueError("Product minimum OS exceeds matched runtime/SDK")
    if environment is not None:
        for info_path in payload.rglob("Info.plist"):
            info = plistlib.loads(info_path.read_bytes())
            if not info.get("CFBundleExecutable"):
                continue
            watch_product = (
                "watch" in info_path.relative_to(payload).parts
                or "Watch" in info_path.relative_to(payload).parts
            )
            platform = "WatchSimulator" if watch_product else "iPhoneSimulator"
            sdk = environment["watch_sdk" if watch_product else "phone_sdk"]
            minimum = info.get("MinimumOSVersion")
            if platform not in info.get("CFBundleSupportedPlatforms", []):
                raise ValueError("Executable bundle platform mismatch")
            if (
                not minimum or version_tuple(minimum) > version_tuple(sdk)
            ) and info_path.relative_to(payload).as_posix() not in carrier_stubs:
                raise ValueError("Executable minimum OS exceeds matched runtime/SDK")
    return run.relative_to(payload).as_posix()


def checker_aliases(path):
    """Only macOS's /var spelling of the selected /private/var checker."""
    aliases = {path}
    if path.startswith("/private/var/"):
        aliases.add(path.removeprefix("/private"))
    elif path.startswith("/var/"):
        aliases.add("/private" + path)
    return aliases


def runtime_support(payload, runtime):
    """Copy only the selected runtime's known checker, retaining diagnostics."""
    runs = list((payload / "watch/Build/Products").glob("*.xctestrun"))
    if len(runs) != 1:
        raise ValueError("Expected one xctestrun before normalization")
    run = runs[0]
    original = run.read_bytes()
    data = plistlib.loads(original)
    target = data[XCTEST]
    known = str(Path(runtime["runtimeRoot"]) / "usr/lib/libMainThreadChecker.dylib")
    replacement = "__TESTROOT__/RuntimeSupport/libMainThreadChecker.dylib"
    changes = []
    originals = set()
    aliases = checker_aliases(known)
    for section in (
        "EnvironmentVariables",
        "TestingEnvironmentVariables",
        "UITargetAppEnvironmentVariables",
    ):
        environment = target.get(section, {})
        raw = environment.get("DYLD_INSERT_LIBRARIES", "")
        parts = raw.split(":")
        matched = set(parts) & aliases
        if matched:
            # A spelling resemblance is insufficient: both paths must exist and
            # identify the exact checker belonging to the selected runtime.
            for part in matched:
                if not Path(part).samefile(known):
                    raise ValueError("Checker alias is not the selected runtime file")
            environment["DYLD_INSERT_LIBRARIES"] = ":".join(
                replacement if part in matched else part for part in parts
            )
            originals.update(matched)
            changes.append(section)
    if not changes:
        return []
    if not runtime.get("isAvailable") or runtime.get("platform") != "watchOS":
        raise ValueError("Checker must come from the selected available Watch runtime")
    support = run.parent / "RuntimeSupport/libMainThreadChecker.dylib"
    support.parent.mkdir()
    shutil.copy2(known, support)
    provenance = payload / "provenance/original.xctestrun"
    provenance.parent.mkdir()
    provenance.write_bytes(original)
    run.write_bytes(plistlib.dumps(data))
    return [
        {
            "original_path": sorted(originals)[0],
            "original_paths": sorted(originals),
            "runtime_checker_path": known,
            "replacement": replacement,
            "sections": changes,
            "runtime": runtime["identifier"],
            "runtime_version": runtime["version"],
            "runtime_build": runtime["buildversion"],
            "sha256": digest(support),
            "original_xctestrun_sha256": digest(provenance),
        }
    ]


def verify_runtime_support(payload, mapping, environment):
    if not mapping:
        return
    if len(mapping) != 1:
        raise ValueError("Unexpected runtime support mapping")
    item = mapping[0]
    if (
        not item["original_path"].endswith(
            "/RuntimeRoot/usr/lib/libMainThreadChecker.dylib"
        )
        or item["replacement"]
        != "__TESTROOT__/RuntimeSupport/libMainThreadChecker.dylib"
        or item["runtime_version"] != environment["watch_sdk"]
    ):
        raise ValueError("Unexpected runtime checker provenance")
    original_paths = item.get("original_paths", [item["original_path"]])
    if (
        not isinstance(original_paths, list)
        or not original_paths
        or any(not isinstance(path, str) for path in original_paths)
        or len(set(original_paths)) != len(original_paths)
        or item["original_path"] not in original_paths
        or not set(original_paths) <= checker_aliases(item["original_path"])
        or item.get("runtime_checker_path", item["original_path"])
        not in checker_aliases(item["original_path"])
    ):
        raise ValueError("Unexpected runtime checker alias provenance")
    original = payload / "provenance/original.xctestrun"
    run = next((payload / "watch/Build/Products").glob("*.xctestrun"))
    support = run.parent / "RuntimeSupport/libMainThreadChecker.dylib"
    if (
        digest(original) != item["original_xctestrun_sha256"]
        or digest(support) != item["sha256"]
    ):
        raise ValueError("Runtime checker provenance hash mismatch")
    expected = plistlib.loads(original.read_bytes())
    observed_paths = set()
    for section in item["sections"]:
        if section not in {
            "EnvironmentVariables",
            "TestingEnvironmentVariables",
            "UITargetAppEnvironmentVariables",
        }:
            raise ValueError("Unexpected checker injection setting")
        parts = expected[XCTEST][section]["DYLD_INSERT_LIBRARIES"].split(":")
        matched = set(parts) & set(original_paths)
        if not matched:
            raise ValueError("Checker mapping does not match original setting")
        observed_paths.update(matched)
        expected[XCTEST][section]["DYLD_INSERT_LIBRARIES"] = ":".join(
            item["replacement"] if part in matched else part for part in parts
        )
    if observed_paths != set(original_paths):
        raise ValueError("Checker alias mapping was not present in original settings")
    if expected != plistlib.loads(run.read_bytes()):
        raise ValueError("xctestrun changed beyond exact checker path relocation")


def toolchain():
    def read(*command):
        return subprocess.check_output(command, text=True, timeout=30).strip()

    return {
        "xcode": read("xcodebuild", "-version"),
        "swift": read("xcrun", "swiftc", "--version"),
        "watch_sdk": read("xcrun", "--sdk", "watchsimulator", "--show-sdk-version"),
        "phone_sdk": read("xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"),
        "watch_sdk_build": read(
            "xcrun", "--sdk", "watchsimulator", "--show-sdk-build-version"
        ),
        "phone_sdk_build": read(
            "xcrun", "--sdk", "iphonesimulator", "--show-sdk-build-version"
        ),
    }


def source_fingerprint(repo):
    paths = (
        subprocess.check_output(
            [
                "git",
                "-C",
                str(repo),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "ios",
            ]
        )
        .decode()
        .split("\0")
    )
    records = {name: digest(repo / name) for name in paths if name}
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def verify_manifest(root, sha, environment, pins_hash, source_hash):
    path = root / "manifest.json"
    manifest = json.loads(path.read_text())
    if (
        manifest.get("schema") != 1
        or manifest.get("sha") != sha
        or manifest.get("configuration") != "Debug"
    ):
        raise ValueError("Wrong simulator product source/schema")
    if manifest.get("source_fingerprint") != source_hash:
        raise ValueError("Simulator product source fingerprint mismatch")
    if manifest.get("toolchain") != environment:
        raise ValueError("Simulator product toolchain/SDK mismatch")
    if manifest.get("pins_sha256") != pins_hash:
        raise ValueError("Simulator product package pins mismatch")
    if manifest.get("architecture") not in {"arm64", "x86_64"}:
        raise ValueError("Unsupported simulator product architecture")
    if inventory(root / "payload") != manifest.get("files"):
        raise ValueError("Product hash/mode/inventory mismatch")
    verify_runtime_support(
        root / "payload", manifest.get("runtime_support", []), environment
    )
    carriers = classify_carrier_stubs(root / "payload", environment)
    if carriers != manifest.get("carrier_stubs", {}):
        raise ValueError("Carrier framework classification changed")
    if check_layout(root / "payload", environment, carriers) != manifest.get(
        "xctestrun"
    ):
        raise ValueError("Manifest xctestrun mismatch")
    return manifest


def macho_files(payload):
    magics = {
        bytes.fromhex(value)
        for value in (
            "feedface",
            "cefaedfe",
            "feedfacf",
            "cffaedfe",
            "cafebabe",
            "bebafeca",
            "cafebabf",
            "bfbafeca",
        )
    }
    binaries = set()
    for path in payload.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                if stream.read(4) in magics:
                    binaries.add(path)
    return sorted(binaries)


def load_references(text):
    references = []
    command = None
    for line in text.splitlines():
        match = re.match(r"\s*cmd (LC_\w+)", line)
        if match:
            command = match.group(1)
        name = re.match(r"\s*name (.+) \(offset \d+\)", line)
        if name and command in {
            "LC_LOAD_DYLIB",
            "LC_LOAD_WEAK_DYLIB",
            "LC_REEXPORT_DYLIB",
            "LC_LAZY_LOAD_DYLIB",
            "LC_LOAD_UPWARD_DYLIB",
        }:
            references.append(name.group(1))
    return references


def classify_carrier_stubs(payload, environment):
    # Xcode injects empty ios100.0 carrier binaries into these static Firebase
    # frameworks. They are not executable dependencies, proven below on bytes.
    names = {
        "FirebaseAnalytics",
        "GoogleAppMeasurement",
        "GoogleAppMeasurementIdentitySupport",
        "GoogleAdsOnDeviceConversion",
    }
    candidates = {}
    for name in sorted(names):
        info_path = (
            payload
            / "phone/Bain Luck.app/Frameworks"
            / (name + ".framework/Info.plist")
        )
        if not info_path.exists():
            continue
        info = plistlib.loads(info_path.read_bytes())
        if version_tuple(info.get("MinimumOSVersion", "0")) != (100, 0, 0):
            continue
        if (
            info.get("CFBundleExecutable") != name
            or info.get("CFBundlePackageType") != "FMWK"
            or info.get("CFBundleSupportedPlatforms") != ["iPhoneSimulator"]
        ):
            raise ValueError("Unexpected carrier framework identity/platform")
        candidates[name] = info_path
    if not candidates:
        return {}
    binaries = macho_files(payload)
    links = {}
    for binary in binaries:
        raw = subprocess.check_output(
            ["otool", "-l", str(binary)], text=True, timeout=30
        )
        links[binary.relative_to(payload).as_posix()] = load_references(raw)
    result = {}
    for name, info_path in candidates.items():
        binary = info_path.parent / name
        if binary not in binaries:
            raise ValueError("Carrier framework executable missing")
        for references in links.values():
            if any(
                ("/" + name + ".framework/") in ref and ref.endswith("/" + name)
                for ref in references
            ):
                raise ValueError(
                    "Future-minimum carrier framework is a loaded dependency"
                )
        arches = subprocess.check_output(
            ["lipo", "-archs", str(binary)], text=True, timeout=30
        ).split()
        slices = []
        for architecture in arches:
            build = subprocess.check_output(
                ["xcrun", "vtool", "-show-build", "-arch", architecture, str(binary)],
                text=True,
                timeout=30,
            )
            if (
                not re.search(r"platform IOSSIMULATOR\s", build)
                or not re.search(r"minos 100\.0\s", build)
                or not re.search(r"\bsdk (\S+)", build)
                or re.search(r"\bsdk (\S+)", build).group(1) != environment["phone_sdk"]
                or "Load command" not in build
            ):
                raise ValueError(
                    "Carrier binary is not an exact simulator ios100.0 stub"
                )
            exports = subprocess.check_output(
                ["nm", "-arch", architecture, "-gU", str(binary)],
                text=True,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            if exports.strip():
                raise ValueError(
                    "Future-minimum carrier framework exports executable symbols"
                )
            slices.append(
                {
                    "architecture": architecture,
                    "build": build[build.index("Load command") :],
                    "exports": [],
                }
            )
        if not slices:
            raise ValueError("Carrier framework has no verified slices")
        result[info_path.relative_to(payload).as_posix()] = {
            "classification": "empty unreferenced Xcode static-framework carrier",
            "sha256": digest(binary),
            "slices": slices,
            "load_closure": links,
            "scope": "MinimumOSVersion exception only; platform, architecture, signature and hashes remain required",
        }
    return result


def verify_binaries(payload, architecture):
    # Include standalone debug dylibs without Info.plist.
    binaries = macho_files(payload)
    if not binaries:
        raise ValueError("No Mach-O products in simulator package")
    for binary in sorted(binaries):
        arches = subprocess.check_output(
            ["lipo", "-archs", str(binary)], text=True, timeout=30
        ).split()
        if architecture not in arches or not set(arches) <= {
            "arm64",
            "arm64e",
            "x86_64",
        }:
            raise ValueError("Unexpected executable architecture: " + str(binary))
        subprocess.run(
            ["codesign", "--verify", "--strict", str(binary)],
            check=True,
            capture_output=True,
            timeout=30,
        )
    for info_path in payload.rglob("Info.plist"):
        info = plistlib.loads(info_path.read_bytes())
        executable = info.get("CFBundleExecutable")
        if not executable:
            continue
        if info_path.parent / executable not in binaries:
            raise ValueError(
                "Missing or non-Mach-O bundle executable: " + str(info_path)
            )
        subprocess.run(
            ["codesign", "--verify", "--strict", str(info_path.parent)],
            check=True,
            capture_output=True,
            timeout=30,
        )


def pack(watch, phone, destination, sha, architecture, repo, runtime):
    if destination.exists():
        raise ValueError("Product package must be fresh")
    if architecture not in {"arm64", "x86_64"}:
        raise ValueError("Unsupported product architecture")
    payload = destination / "payload"
    shutil.copytree(
        watch / "Build/Products", payload / "watch/Build/Products", symlinks=True
    )
    for name, filename in XCTENTS.items():
        rel = (
            Path("Build/Intermediates.noindex/Bain Luck.build/Debug-watchsimulator")
            / (name + ".build")
            / filename
        )
        target = payload / "watch" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(watch / rel, target)
    shutil.copytree(
        phone / "Build/Products/Debug-iphonesimulator/Bain Luck.app",
        payload / "phone/Bain Luck.app",
        symlinks=True,
    )
    support = runtime_support(payload, runtime)
    environment = toolchain()
    carriers = classify_carrier_stubs(payload, environment)
    manifest = {
        "carrier_stubs": carriers,
        "runtime_support": support,
        "schema": 1,
        "sha": sha,
        "architecture": architecture,
        "source_fingerprint": source_fingerprint(repo),
        "toolchain": environment,
        "pins_sha256": digest(repo / PINS),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "configuration": "Debug",
        "xctestrun": check_layout(payload),
        "files": inventory(payload),
    }
    if any(record["kind"] != "file" for record in manifest["files"].values()):
        raise ValueError("Product archive currently requires regular files only")
    verify_binaries(payload, architecture)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    verify_manifest(
        destination,
        sha,
        manifest["toolchain"],
        manifest["pins_sha256"],
        manifest["source_fingerprint"],
    )
    return manifest


def unpack(archive, destination):
    if destination.exists():
        raise ValueError("Extraction destination must be fresh")
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        names = set()
        for member in members:
            relative(member.name)
            if member.name in names:
                raise ValueError("Duplicate archive member")
            names.add(member.name)
            # Payloads currently contain no symlinks. Refuse rather than silently
            # traverse archive links; the packer also rejects external links.
            if not (member.isfile() or member.isdir()):
                raise ValueError("Unsupported archive link or special entry")
        destination.mkdir(parents=True)
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["pack", "verify", "unpack"])
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--watch", type=Path)
    parser.add_argument("--phone", type=Path)
    parser.add_argument("--architecture")
    parser.add_argument("--sha")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--simulators", type=Path)
    parser.add_argument("--watch-runtime")
    args = parser.parse_args()
    if args.mode == "unpack":
        unpack(args.archive, args.output)
    elif args.mode == "pack":
        runtimes = [
            r
            for r in json.loads(args.simulators.read_text())["runtimes"]
            if r["identifier"] == args.watch_runtime
        ]
        if len(runtimes) != 1:
            raise ValueError("Exact producer Watch runtime is missing or ambiguous")
        pack(
            args.watch,
            args.phone,
            args.output,
            args.sha,
            args.architecture,
            args.repo,
            runtimes[0],
        )
        with tarfile.open(args.archive, "w:gz") as bundle:
            for path in sorted(args.output.rglob("*")):
                if path.is_file():
                    bundle.add(path, path.relative_to(args.output), recursive=False)
    else:
        manifest = verify_manifest(
            args.output,
            args.sha,
            toolchain(),
            digest(args.repo / PINS),
            source_fingerprint(args.repo),
        )
        verify_binaries(args.output / "payload", manifest["architecture"])
        print(
            json.dumps(
                {
                    "sha": args.sha,
                    "verdict": "PASS",
                    "manifest_sha256": digest(args.output / "manifest.json"),
                    "architecture": manifest["architecture"],
                    "xctestrun": manifest["xctestrun"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
