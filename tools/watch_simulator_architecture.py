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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch-destinations", type=Path, required=True)
    parser.add_argument("--watch-id", required=True)
    parser.add_argument("--phone-destinations", type=Path, required=True)
    parser.add_argument("--phone-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = select(
            args.watch_destinations.read_text(),
            args.watch_id,
            args.phone_destinations.read_text(),
            args.phone_id,
        )
    except (OSError, ValueError) as error:
        args.output.write_text(
            json.dumps({"verdict": "UNPAID", "reason": str(error)}, indent=2) + "\n"
        )
        raise SystemExit(str(error))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(result["architecture"])


if __name__ == "__main__":
    main()
