"""Execute and independently validate the pinned read-only child verifier.

Observations do not establish P-EXCL, late-command closure or provider behavior.
No API accepts a supplied receipt as proof that this verifier ran.
"""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
from uuid import UUID

from app.services.dnpl_operation_hold import OperationHoldRefused

VERIFIER = Path(__file__).with_name("dnpl_writer_verifier.py")
VERIFIER_SHA256 = "7522af71e87fe8af046f09c2ae44e41e7f21463d77c31340086208e8f5e67cb5"
FRESHNESS_NS = 120_000_000_000
CLOCK_SKEW_NS = 1_000_000_000
MAX_BYTES = 1048576
APPS = ("bainluck", "bainluck-heavy")
NONWRITERS = {
    "web",
    "worker-realtime",
    "worker-background",
    "worker-heavy",
    "scheduler",
}
READ_NAMES = tuple(
    app + "-" + kind
    for app in APPS
    for kind in ("releases", "slug", "formation", "dynos")
)


def _require(condition, reason):
    if not condition:
        raise OperationHoldRefused(reason)


def _bytes(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        _require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid()
            and info.st_size <= MAX_BYTES,
            "invalid raw observation file",
        )
        with os.fdopen(os.dup(fd), "rb") as raw:
            data = raw.read(MAX_BYTES + 1)
        _require(len(data) <= MAX_BYTES, "raw observation too large")
        return data
    finally:
        os.close(fd)


def validate_payloads(binding, payloads):
    """Re-derive all conclusions from raw reads, not child summary booleans."""
    _require(set(binding["apps"]) == set(APPS), "exact apps required")
    _require(
        binding["apps"][APPS[0]]["commit"] == binding["apps"][APPS[1]]["commit"],
        "heavy must be converged",
    )
    for app in APPS:
        expected = binding["apps"][app]
        _require(
            set(expected) == {"release", "slug", "commit"},
            "exact release binding required",
        )
        _require(
            type(expected["release"]) is int and expected["release"] > 0,
            "invalid release",
        )
        _require(
            re.fullmatch(r"[0-9a-f]{40}", expected["commit"]) is not None,
            "invalid source commit",
        )
        _require(
            str(UUID(expected["slug"])) == expected["slug"], "canonical slug required"
        )
        releases = payloads[app + "-releases"]
        _require(
            isinstance(releases, list) and bool(releases), "release response empty"
        )
        release = releases[0]
        _require(
            release.get("current") is True
            and release.get("status") == "succeeded"
            and release.get("version") == expected["release"]
            and release.get("slug", {}).get("id") == expected["slug"],
            "release binding changed",
        )
        slug = payloads[app + "-slug"]
        _require(
            slug.get("id") == expected["slug"]
            and slug.get("commit") == expected["commit"],
            "slug source changed",
        )
        formation = payloads[app + "-formation"]
        _require(isinstance(formation, list), "formation response is not a list")
        seen = set()
        for row in formation:
            kind, quantity = row.get("type"), row.get("quantity")
            _require(
                isinstance(kind, str)
                and kind not in seen
                and type(quantity) is int
                and quantity >= 0,
                "malformed formation",
            )
            seen.add(kind)
            _require(
                kind in NONWRITERS or quantity == 0, "writer formation is not stopped"
            )
        _require("worker-ws" in seen, "worker formation missing")
        dynos = payloads[app + "-dynos"]
        _require(isinstance(dynos, list), "dyno response is not a list")
        for dyno in dynos:
            kind, name = dyno.get("type"), dyno.get("name")
            _require(
                kind in NONWRITERS
                and isinstance(name, str)
                and name.startswith(kind + "."),
                "writer or unknown dyno present",
            )
            _require(
                dyno.get("release", {}).get("version") == expected["release"],
                "dyno release changed",
            )


@dataclass(frozen=True)
class Observation:
    directory: Path
    binding_json: str
    result_json: str
    invoke_wall_ns: int
    invoke_mono_ns: int

    def validate(self):
        now_wall, now_mono = time.time_ns(), time.monotonic_ns()
        wall_elapsed = now_wall - self.invoke_wall_ns
        mono_elapsed = now_mono - self.invoke_mono_ns
        _require(
            0 <= wall_elapsed <= FRESHNESS_NS
            and 0 <= mono_elapsed <= FRESHNESS_NS
            and abs(wall_elapsed - mono_elapsed) <= CLOCK_SKEW_NS,
            "collection stale or wrapper clock changed",
        )
        binding, result = json.loads(self.binding_json), json.loads(self.result_json)
        _require(
            set(result) == {"binding", "reads"} and result["binding"] == binding,
            "verifier binding mismatch",
        )
        _require(
            isinstance(result["reads"], list)
            and len(result["reads"]) == len(READ_NAMES),
            "incomplete observations",
        )
        previous = self.invoke_wall_ns
        payloads = {}
        for name, record in zip(READ_NAMES, result["reads"], strict=True):
            _require(
                set(record) == {"name", "sha256", "start_ns", "end_ns"}
                and record["name"] == name,
                "observation identity changed",
            )
            start, end = record["start_ns"], record["end_ns"]
            _require(
                type(start) is int
                and type(end) is int
                and 0 <= previous <= start <= end <= now_wall < 2**63,
                "invalid observation time",
            )
            previous = end
            data = _bytes(self.directory / (name + ".json"))
            _require(
                hashlib.sha256(data).hexdigest() == record["sha256"],
                "raw observation changed",
            )
            payloads[name] = json.loads(data)
        validate_payloads(binding, payloads)
        return binding


def execute_verifier(
    run_dir, *, run_id, step, expected_authority, expected_primary, apps
):
    """Only this function creates observations used by the future command runner."""
    _require(
        hashlib.sha256(VERIFIER.read_bytes()).hexdigest() == VERIFIER_SHA256,
        "verifier source changed",
    )
    UUID(run_id)
    nonce = secrets.token_hex(16)
    directory = run_dir / ("verify-" + nonce)
    directory.mkdir(mode=0o700)  # Must not pre-exist; no supplied observation path.
    binding = {
        "run_id": run_id,
        "step": step,
        "nonce": nonce,
        "expected_authority": expected_authority,
        "expected_primary": expected_primary,
        "apps": apps,
    }
    binding_json = json.dumps(
        binding, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
    )
    _require(len(binding_json) <= 8192, "binding too large")
    invoke_wall, invoke_mono = time.time_ns(), time.monotonic_ns()
    output = run_dir / ("verify-" + nonce + ".stdout")
    with output.open("xb") as raw:
        os.chmod(output, 0o600)
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(VERIFIER),
                "--binding",
                binding_json,
                "--directory",
                str(directory),
            ],
            stdout=raw,
            stderr=subprocess.DEVNULL,
            timeout=100,
            # This read-only child needs no database/Redis credentials, CLI,
            # HOME, proxies or ambient application configuration.
            env={
                key: os.environ[key]
                for key in ("HEROKU_API_KEY", "SSL_CERT_FILE", "SSL_CERT_DIR")
                if key in os.environ
            },
        )
    _require(result.returncode == 0, "verifier did not complete")
    _require(
        hashlib.sha256(VERIFIER.read_bytes()).hexdigest() == VERIFIER_SHA256,
        "verifier source changed during execution",
    )
    observation = Observation(
        directory, binding_json, _bytes(output).decode(), invoke_wall, invoke_mono
    )
    observation.validate()
    return observation
