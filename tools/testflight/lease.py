#!/usr/bin/env python3
"""Serialize TestFlight releases without Actions' single-pending-run cancellation.

The separate ref is a chain of lease-state commits, updated only by fast-forward.
Competing updates are siblings, so GitHub accepts exactly one of them. Never
force or delete this ref: doing either would let a stale waiter unlock a new owner.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request

REF = "heads/testflight-release-lock"
PROTOCOL = "bainluck-testflight-lease-v1"


class ApiError(RuntimeError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"GitHub lease API returned HTTP {status}")


class GitHub:
    def __init__(self):
        self.base = "https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GH_TOKEN"]

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise ApiError(error.code) from None

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body):
        return self.request("POST", path, body)

    def patch(self, path, body):
        return self.request("PATCH", path, body)


def state_commit(api, tree, parent, owner):
    message = json.dumps({"protocol": PROTOCOL, "owner": owner}, sort_keys=True)
    return api.post(
        "/git/commits", {"message": message, "tree": tree, "parents": [parent]}
    )["sha"]


def read_state(api):
    sha = api.get("/git/ref/" + REF)["object"]["sha"]
    commit = api.get("/git/commits/" + sha)
    state = json.loads(commit["message"])
    if state.get("protocol") != PROTOCOL:
        raise ValueError(
            "TestFlight lease ref contains an unknown protocol; refusing to overwrite it"
        )
    return sha, commit["tree"]["sha"], state["owner"]


def advance(api, current, tree, owner):
    candidate = state_commit(api, tree, current, owner)
    try:
        api.patch("/git/refs/" + REF, {"sha": candidate, "force": False})
        return candidate
    except ApiError as error:
        if error.status != 422:
            raise
        return None  # another waiter advanced first; its ownership is intact


def try_acquire(api, source, run_id, attempt):
    try:
        current, tree, owner = read_state(api)
    except ApiError as error:
        if error.status != 404:
            raise
        tree = api.get("/git/commits/" + source)["tree"]["sha"]
        initial = state_commit(api, tree, source, None)
        try:
            api.post("/git/refs", {"ref": "refs/" + REF, "sha": initial})
        except ApiError as conflict:
            if conflict.status != 422:
                raise
        current, tree, owner = read_state(api)
    wanted = {"run_id": int(run_id), "attempt": int(attempt), "source": source}
    if owner == wanted:
        return current
    if owner is not None:
        previous = api.get(
            f"/actions/runs/{owner['run_id']}/attempts/{owner['attempt']}"
        )
        if previous["status"] != "completed":
            return None
        # Fast-forward CAS makes concurrent recovery safe too.
        recovered = advance(api, current, tree, None)
        if recovered is None:
            return None
        current = recovered
    return advance(api, current, tree, wanted)


def release(api, token, run_id, attempt):
    current, tree, owner = read_state(api)
    if (
        current != token
        or owner is None
        or owner["run_id"] != int(run_id)
        or owner["attempt"] != int(attempt)
    ):
        raise ValueError(
            "Refusing to release a TestFlight lease owned by another run or attempt"
        )
    if advance(api, current, tree, None) is None:
        raise ValueError(
            "Lease changed while releasing; the newer owner was left intact"
        )


def validate(api, token, source, run_id, attempt):
    current, _, owner = read_state(api)
    wanted = {"run_id": int(run_id), "attempt": int(attempt), "source": source}
    if current != token or owner != wanted:
        raise ValueError(
            "This source and workflow attempt do not own the TestFlight lease"
        )


def release_if_owned(api, token, run_id, attempt):
    _, _, owner = read_state(api)
    if (
        owner is None
        or owner["run_id"] != int(run_id)
        or owner["attempt"] != int(attempt)
    ):
        return False
    release(api, token, run_id, attempt)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["acquire", "validate", "release"])
    parser.add_argument("--source", default=os.environ.get("GITHUB_SHA"))
    parser.add_argument("--token")
    parser.add_argument("--allow-unowned", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=5 * 60 * 60)
    args = parser.parse_args()
    api = GitHub()
    run_id = int(os.environ["GITHUB_RUN_ID"])
    attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
    if args.command == "validate":
        validate(api, args.token, args.source, run_id, attempt)
        print("Current workflow attempt owns this source release")
        return
    if args.command == "release":
        if args.allow_unowned:
            changed = release_if_owned(api, args.token, run_id, attempt)
        else:
            release(api, args.token, run_id, attempt)
            changed = True
        print(
            "TestFlight release lease returned"
            if changed
            else "No lease owned by this workflow attempt"
        )
        return
    if not 0 < args.wait_seconds <= 5 * 60 * 60:
        parser.error("wait-seconds must be positive and no greater than five hours")
    deadline = time.monotonic() + args.wait_seconds
    next_notice = 0
    while time.monotonic() < deadline:
        token = try_acquire(api, args.source, run_id, attempt)
        if token:
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write("token=" + token + "\n")
            print("TestFlight release lease acquired for " + args.source)
            return
        if time.monotonic() >= next_notice:
            print("Waiting for the active TestFlight release", flush=True)
            next_notice = time.monotonic() + 60
        time.sleep(15)
    raise RuntimeError("TestFlight ownership wait timed out; retry this failed run")


if __name__ == "__main__":
    main()
