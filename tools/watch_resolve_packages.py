"""Bounded package-resolution preparation; never a build or test verdict."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import time


# The observed dependency error arrived about 859 seconds after setup began.
# Allow that diagnostic to arrive while keeping each setup attempt bounded.
ATTEMPT_TIMEOUT_SECONDS = 900
RETRY_DELAY_SECONDS = 5
_RESOLUTION_ERROR = "xcodebuild: error: Could not resolve package dependencies:"
# Only the two transport messages actually observed on hosted Firebase binary
# downloads (d118 timeout, 37508835672 lost connection); no generic network class.
_DOWNLOAD_TIMEOUT = re.compile(
    r"failed downloading '[^'\n]+' which is required by binary target '[^'\n]+': "
    r'downloadError\("(?:The request timed out|The network connection was lost)\."\)'
)


def retryable_download_timeout(exit_code: int, log: str) -> bool:
    """Recognize only the observed exit-74 transient binary-download diagnostics."""
    if exit_code != 74 or log.count(_RESOLUTION_ERROR) != 1:
        return False
    # The final diagnostic must contain only transient binary-download failures
    # and the observed SwiftPM fatalError terminator. Anything else fails closed.
    tail = log.split(_RESOLUTION_ERROR, 1)[1]
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    downloads = [line for line in lines if _DOWNLOAD_TIMEOUT.fullmatch(line)]
    if not downloads or any(
        line != "fatalError" and not _DOWNLOAD_TIMEOUT.fullmatch(line)
        for line in lines
    ):
        return False
    # A mixed failure earlier in the log must not become retryable just because
    # the last diagnostic mentions a timeout.
    remainder = _DOWNLOAD_TIMEOUT.sub("", log.split(_RESOLUTION_ERROR, 1)[0])
    if re.search(
        r"checksum|configuration error|permission denied|unauthorized|"
        r"authentication failed|downloadError\(|(?:^|\n)[^\n]*\berror:",
        remainder,
        re.IGNORECASE,
    ):
        return False
    return True


def run_resolution(command, output_dir, runner=subprocess.run, sleep=time.sleep):
    """Run at most two setup attempts, returning and saving a setup receipt."""
    command = list(command)
    actions = {"build", "build-for-testing", "test", "test-without-building", "archive",
               "clean", "analyze", "install", "installhdrs", "installsrc"}
    is_xcodebuild = bool(command) and (
        Path(command[0]).name == "xcodebuild"
        or (Path(command[0]).name == "xcrun" and len(command) > 1
            and command[1] == "xcodebuild")
    )
    if (not is_xcodebuild or "-resolvePackageDependencies" not in command
            or any(argument in actions for argument in command)):
        raise ValueError("Only xcodebuild -resolvePackageDependencies setup is permitted")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "scope": "package_resolution_setup_only",
        "verdict": "FAILED",
        "exit_code": None,
        "attempt_timeout_seconds": ATTEMPT_TIMEOUT_SECONDS,
        "attempts": [],
    }
    for number in (1, 2):
        log_path = output_dir / f"attempt-{number}.log"
        timed_out = False
        with log_path.open("w") as log_file:
            try:
                result = runner(
                    command,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    timeout=ATTEMPT_TIMEOUT_SECONDS,
                    check=False,
                )
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = 124
                log_file.write("\nPackage resolution exceeded its 900-second setup limit.\n")
            except OSError as error:
                exit_code = 127
                log_file.write(f"\nCould not start package resolution: {error}\n")
        retryable = not timed_out and retryable_download_timeout(
            exit_code, log_path.read_text(errors="replace")
        )
        receipt["attempts"].append({
            "attempt": number,
            "log": str(log_path),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "retryable_download_timeout": retryable,
        })
        receipt["exit_code"] = exit_code
        receipt["verdict"] = (
            "TIMED_OUT" if timed_out else "RESOLVED" if exit_code == 0 else "FAILED"
        )
        (output_dir / "resolution-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n"
        )
        if exit_code == 0 or not retryable or number == 2:
            return receipt
        sleep(RETRY_DELAY_SECONDS)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Supply the xcodebuild package-resolution command after --")
    try:
        receipt = run_resolution(command, args.output_dir)
    except ValueError as error:
        parser.error(str(error))
    print(f"Package resolution setup: {receipt['verdict']} ({len(receipt['attempts'])} attempt(s))")
    code = receipt["exit_code"]
    raise SystemExit(code if code >= 0 else 128 - code)


if __name__ == "__main__":
    main()
