"""Select one architecture supported by both exact, available UI destinations."""

import argparse
import json
from pathlib import Path
import re


def available_architectures(log, udid, platform):
    available = False
    found = set()
    for line in log.splitlines():
        if (
            "Available destinations for" in line
            or "Destinations compatible with" in line
        ):
            available = True
        elif (
            "Ineligible destinations for" in line
            or "Destinations incompatible with" in line
        ):
            available = False
        if not available or "{" not in line or "}" not in line:
            continue
        fields = dict(re.findall(r"(?:\{|,)\s*(\w+):\s*([^,}]+)", line))
        if fields.get("id", "").strip() != udid:
            continue
        if fields.get("platform", "").strip() != platform:
            raise ValueError("Selected destination has the wrong simulator platform")
        if "error" in fields:
            raise ValueError("Selected simulator destination reports an error")
        architecture = fields.get("arch", "").strip()
        if architecture not in {"arm64", "x86_64"}:
            raise ValueError(
                "Selected simulator architecture is missing or unsupported"
            )
        found.add(architecture)
    if not found:
        raise ValueError("Exact simulator is not an available Xcode destination")
    return found


def select(watch_log, watch_id, phone_log, phone_id):
    if not watch_id or not phone_id or watch_id == phone_id:
        raise ValueError("Two distinct exact simulator IDs are required")
    watch = available_architectures(watch_log, watch_id, "watchOS Simulator")
    phone = available_architectures(phone_log, phone_id, "iOS Simulator")
    shared = watch & phone
    if len(shared) != 1:
        raise ValueError("Selected pair must have one unambiguous shared architecture")
    return {
        "verdict": "PASS",
        "architecture": next(iter(shared)),
        "watch_id": watch_id,
        "phone_id": phone_id,
        "watch_architectures": sorted(watch),
        "phone_architectures": sorted(phone),
        "scope": "Only the selected simulator pair; device and archive gates are separate",
    }


def select_runtime_pair(info, pairs, watch_id, phone_id, products):
    if not watch_id or not phone_id or watch_id == phone_id:
        raise ValueError("Two distinct exact runtime devices are required")
    bindings = [
        p
        for p in pairs["pairs"].values()
        if p["watch"]["udid"] == watch_id
        and p["phone"]["udid"] == phone_id
        and p["state"].startswith("(active,")
    ]
    if len(bindings) != 1:
        raise ValueError("Exact prepared pair is not active")
    observations = []
    supported = []
    for udid, platform, family, sdk in [
        (watch_id, "watchOS", "Apple Watch", products["toolchain"]["watch_sdk"]),
        (phone_id, "iOS", "iPhone", products["toolchain"]["phone_sdk"]),
    ]:
        matches = [
            (runtime, device)
            for runtime in info["runtimes"]
            for device in info["devices"].get(runtime["identifier"], [])
            if device["udid"] == udid
        ]
        if len(matches) != 1:
            raise ValueError("Exact runtime device is missing or ambiguous")
        runtime, device = matches[0]
        if (
            not runtime.get("isAvailable")
            or not device.get("isAvailable")
            or device.get("state") != "Booted"
            or runtime.get("platform") != platform
            or tuple((runtime["version"].split(".") + ["0", "0"])[:3])
            != tuple((sdk.split(".") + ["0", "0"])[:3])
        ):
            raise ValueError("Unavailable, unbooted or incompatible simulator runtime")
        types = [
            kind
            for kind in runtime.get("supportedDeviceTypes", [])
            if kind["identifier"] == device.get("deviceTypeIdentifier")
            and kind.get("productFamily") == family
        ]
        if len(types) != 1:
            raise ValueError("Runtime does not support the exact device platform/type")
        if platform == "watchOS":
            for support in products.get("runtime_support", []):
                if support.get("runtime") != runtime["identifier"] or support.get(
                    "runtime_build"
                ) != runtime.get("buildversion"):
                    raise ValueError(
                        "Copied runtime support differs from exact Watch runtime build"
                    )
        architectures = set(runtime.get("supportedArchitectures", []))
        if not architectures or not architectures <= {"arm64", "x86_64"}:
            raise ValueError("Runtime architecture missing or unsupported")
        supported.append(architectures)
        observations.append(
            {
                "udid": udid,
                "runtime": runtime["identifier"],
                "platform": platform,
                "version": runtime["version"],
                "runtime_build": runtime.get("buildversion"),
                "architectures": sorted(architectures),
            }
        )
    shared = supported[0] & supported[1]
    if len(shared) != 1 or shared != {products["architecture"]}:
        raise ValueError("Runtime/product architecture mismatch or ambiguous pair")
    return {
        "verdict": "PASS",
        "architecture": products["architecture"],
        "watch_id": watch_id,
        "phone_id": phone_id,
        "destinations": observations,
        "scope": "Exact active booted pair and runtime-supported architectures; product binaries verified separately",
    }


def _version(value):
    # Exact dotted numeric version; "27" and "27.0.0" both mean 27.0.0.
    parts = value.split(".") if isinstance(value, str) else []
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() and p.isascii() for p in parts):
        raise ValueError("Runtime or SDK version is missing or malformed")
    return tuple(int(p) for p in parts + ["0"] * (3 - len(parts)))


def select_build_runtime_pair(
    info,
    watch_runtime_id,
    phone_runtime_id,
    watch_sdk,
    phone_sdk,
    watch_device_type=None,
    phone_device_type=None,
):
    """Producer-only build architecture from exact runtime metadata.

    Reads no device, pair or host state and creates nothing; the consumer's
    select_runtime_pair still verifies the actual booted pair it executes on.
    """
    if (
        not isinstance(watch_runtime_id, str)
        or not isinstance(phone_runtime_id, str)
        or not watch_runtime_id
        or not phone_runtime_id
        or watch_runtime_id == phone_runtime_id
    ):
        raise ValueError("Two distinct exact runtime identifiers are required")
    runtimes = info.get("runtimes") if isinstance(info, dict) else None
    if not isinstance(runtimes, list) or not all(isinstance(r, dict) for r in runtimes):
        raise ValueError("Simulator runtime list is missing or malformed")
    observations = []
    supported = []
    for runtime_id, platform, family, sdk, device_type in [
        (watch_runtime_id, "watchOS", "Apple Watch", watch_sdk, watch_device_type),
        (phone_runtime_id, "iOS", "iPhone", phone_sdk, phone_device_type),
    ]:
        matches = [r for r in runtimes if r.get("identifier") == runtime_id]
        if len(matches) != 1:
            raise ValueError("Exact runtime record is missing or duplicated")
        runtime = matches[0]
        if (
            runtime.get("isAvailable") is not True
            or runtime.get("platform") != platform
            or _version(runtime.get("version")) != _version(sdk)
        ):
            raise ValueError("Unavailable, wrong-platform or SDK-mismatched runtime")
        kinds = runtime.get("supportedDeviceTypes")
        if not isinstance(kinds, list) or not all(isinstance(k, dict) for k in kinds):
            raise ValueError("Runtime device types are missing or malformed")
        kinds = [
            k
            for k in kinds
            if k.get("productFamily") == family
            and (device_type is None or k.get("identifier") == device_type)
        ]
        if not kinds or (device_type is not None and len(kinds) != 1):
            raise ValueError("Runtime does not support the exact device family/type")
        listed = runtime.get("supportedArchitectures")
        if (
            not isinstance(listed, list)
            or not listed
            or len(set(listed)) != len(listed)
            or not all(isinstance(a, str) for a in listed)
            or not set(listed) <= {"arm64", "x86_64"}
        ):
            raise ValueError("Runtime architecture missing, malformed or unsupported")
        supported.append(set(listed))
        observations.append(
            {
                "runtime": runtime_id,
                "platform": platform,
                "version": runtime["version"],
                "sdk": sdk,
                "runtime_build": runtime.get("buildversion"),
                "device_type": device_type,
                "architectures": sorted(listed),
            }
        )
    shared = supported[0] & supported[1]
    if len(shared) != 1:
        raise ValueError("Runtimes must share one unambiguous architecture")
    return {
        "verdict": "PASS",
        "architecture": next(iter(shared)),
        "watch_runtime": watch_runtime_id,
        "phone_runtime": phone_runtime_id,
        "runtimes": observations,
        "scope": "Producer build architecture from exact runtime metadata only; no device, pair or execution accepted",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-pair", action="store_true")
    parser.add_argument("--simulators", type=Path)
    parser.add_argument("--pairs", type=Path)
    parser.add_argument("--products", type=Path)
    parser.add_argument("--watch-destinations", type=Path)
    parser.add_argument("--watch-id")
    parser.add_argument("--phone-destinations", type=Path)
    parser.add_argument("--phone-id")
    parser.add_argument("--build-runtime-pair", action="store_true")
    parser.add_argument("--watch-runtime")
    parser.add_argument("--phone-runtime")
    parser.add_argument("--watch-sdk")
    parser.add_argument("--phone-sdk")
    parser.add_argument("--watch-device-type")
    parser.add_argument("--phone-device-type")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_fields = [
        args.simulators,
        args.watch_runtime,
        args.phone_runtime,
        args.watch_sdk,
        args.phone_sdk,
    ]
    if args.build_runtime_pair:
        # The producer selector reads runtimes only; a device id here is a misuse.
        if args.runtime_pair or args.watch_id or args.phone_id:
            parser.error("--build-runtime-pair reads runtimes only, never device ids")
        if not all(build_fields):
            parser.error(
                "--build-runtime-pair requires --simulators, --watch-runtime, "
                "--phone-runtime, --watch-sdk and --phone-sdk"
            )
    elif args.watch_id is None or args.phone_id is None:
        parser.error("the following arguments are required: --watch-id, --phone-id")
    try:
        if args.build_runtime_pair:
            result = select_build_runtime_pair(
                json.loads(args.simulators.read_text()),
                args.watch_runtime,
                args.phone_runtime,
                args.watch_sdk,
                args.phone_sdk,
                args.watch_device_type,
                args.phone_device_type,
            )
        elif args.runtime_pair:
            result = select_runtime_pair(
                json.loads(args.simulators.read_text()),
                json.loads(args.pairs.read_text()),
                args.watch_id,
                args.phone_id,
                json.loads(args.products.read_text()),
            )
        else:
            result = select(
                args.watch_destinations.read_text(),
                args.watch_id,
                args.phone_destinations.read_text(),
                args.phone_id,
            )
    except (OSError, ValueError, KeyError, TypeError) as error:
        args.output.write_text(
            json.dumps({"verdict": "UNPAID", "reason": str(error)}, indent=2) + "\n"
        )
        raise SystemExit(str(error))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(result["architecture"])


if __name__ == "__main__":
    main()
