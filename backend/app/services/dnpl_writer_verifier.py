"""Read-only child collector for an explicitly invoked recovery wrapper.

Not an authorization mechanism or a writer hold. This module is deliberately
standalone so the parent can hash and execute these exact bytes with -I.
Never invoked by startup. Source preparation does not authorize live invocation.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
from uuid import UUID

MAX_BYTES = 1048576
APPS = ("bainluck", "bainluck-heavy")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Platform redirect refused")


def collect(binding, directory):
    if set(binding) != {
        "run_id",
        "step",
        "nonce",
        "expected_authority",
        "expected_primary",
        "apps",
    }:
        raise ValueError("exact binding required")
    UUID(binding["run_id"])
    if not re.fullmatch(r"[0-9a-f]{32}", binding["nonce"]):
        raise ValueError("fresh nonce required")
    if set(binding["apps"]) != set(APPS) or any(directory.iterdir()):
        raise ValueError("fresh collection directory and exact apps required")
    token = os.environ["HEROKU_API_KEY"]
    opener = urllib.request.build_opener(NoRedirect)
    reads = []

    def record(name, *, command=None, endpoint=None):
        start = time.time_ns()
        path = directory / (name + ".json")
        with path.open("xb") as raw:
            os.chmod(path, 0o600)
            if command is not None:
                subprocess.run(
                    command,
                    stdout=raw,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=10,
                )
            else:
                request = urllib.request.Request(
                    "https://api.heroku.com" + endpoint,
                    headers={
                        "Accept": "application/vnd.heroku+json; version=3",
                        "Authorization": "Bearer " + token,
                    },
                )
                with opener.open(request, timeout=10) as response:
                    data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("Platform response too large")
                raw.write(data)
        end = time.time_ns()
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("CLI response too large")
        with path.open("rb") as raw:
            data = raw.read(MAX_BYTES + 1)
        json.loads(data)
        reads.append(
            {
                "name": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "start_ns": start,
                "end_ns": end,
            }
        )

    for app in APPS:
        source = binding["apps"][app]
        # The path is derived from a validated UUID, never caller URL text.
        slug = str(UUID(source["slug"]))
        record(
            app + "-releases",
            command=["heroku", "releases", "-a", app, "-n", "5", "--json"],
        )
        record(app + "-slug", endpoint=f"/apps/{app}/slugs/{slug}")
        record(app + "-formation", endpoint=f"/apps/{app}/formation")
        record(app + "-dynos", command=["heroku", "ps", "-a", app, "--json"])
    return {"binding": binding, "reads": reads}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        if len(args.binding) > 8192:
            raise ValueError("binding too large")
        result = collect(json.loads(args.binding), args.directory)
    except Exception as exc:
        print(json.dumps({"status": "REFUSED", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
