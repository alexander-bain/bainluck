#!/usr/bin/env python3
"""Plan an App Store submission; write only after --submit and Alex's typed line.

Default: read Apple and print the plan. --self-check is entirely offline.
Credentials and readiness predicates come from asc-submission-readiness.py,
which imports asc-builds.py's credential resolver. No credentials are logged.
Receipts default to ~/.bainluck/asc-submit/; --receipts can select another file.
Exit 0: dry-run plan / submitted / self-check passed; 1: GAP or Apple error;
2: invalid arguments, confirmation, credentials or transport.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import functools
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

API = "https://api.appstoreconnect.apple.com/v1"
PT = ZoneInfo("America/Los_Angeles")
# Readiness can inspect an in-review record; this tool must never edit it.
WRITABLE = {
    "PREPARE_FOR_SUBMISSION",
    "DEVELOPER_REJECTED",
    "REJECTED",
    "METADATA_REJECTED",
    "INVALID_BINARY",
}
TERMINAL_SUBMISSIONS = {"COMPLETE", "CANCELED"}


class Refusal(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


@functools.cache
def readiness():
    path = Path(__file__).with_name("asc-submission-readiness.py")
    spec = importlib.util.spec_from_file_location("asc_readiness", path)
    if spec is None or spec.loader is None:
        raise Refusal(f"cannot load {path}", 2)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Client:
    def __init__(self, bearer: str, receipt: Path):
        self.bearer = bearer
        self.receipt = receipt.expanduser()
        self.write_enabled = False
        self.sequence = 0
        self.run_id = datetime.now(PT).isoformat()

    def record(self, **event) -> None:
        self.receipt.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.receipt, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(
                json.dumps(
                    {
                        "run_id": self.run_id,
                        "time_pt": datetime.now(PT).isoformat(),
                        **event,
                    }
                )
                + "\n"
            )

    def request(self, method: str, path: str, body=None, *, soft404=False) -> dict:
        if method != "GET" and not self.write_enabled:
            raise Refusal(
                "Apple writes require --submit and Alex's exact typed line", 2
            )
        url = path if path.startswith("https://") else API + path
        if not url.startswith(API + "/"):
            raise Refusal("refusing an App Store request outside the ASC API", 2)
        self.sequence += 1
        number = self.sequence
        print(f"{method} {path}")
        # Record the request before sending it, including attempts with no response.
        # Authorization is deliberately absent from the receipt.
        self.record(event="request", number=number, method=method, path=path, body=body)
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.bearer}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                status, raw = response.status, response.read().decode(
                    "utf-8", "replace"
                )
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.record(event="response", number=number, status=None, error=str(exc))
            raise Refusal(
                f"transport failed on {method} {path}; see receipts", 2
            ) from exc
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            self.record(event="response", number=number, status=status, response=raw)
            raise Refusal(
                f"non-JSON response on {method} {path}; see receipts", 2
            ) from exc
        self.record(event="response", number=number, status=status, response=result)
        if soft404 and status == 404:
            return {"data": None}
        if not 200 <= status < 300:
            raise Refusal(f"HTTP {status} on {method} {path}; see receipts")
        if not isinstance(result, dict):
            raise Refusal(f"non-object response on {method} {path}; see receipts", 2)
        return result

    def get(self, path: str, *, soft404=False) -> dict:
        return self.request("GET", path, soft404=soft404)

    def pages(self, path: str) -> dict:
        rows, included, seen = [], [], set()
        while path:
            if path in seen:
                raise Refusal("ASC pagination repeated a page", 2)
            seen.add(path)
            page = self.get(path)
            if not isinstance(page.get("data"), list):
                raise Refusal(f"ASC did not return a list for {path}", 2)
            rows.extend(page["data"])
            included.extend(page.get("included", []))
            path = (page.get("links") or {}).get("next")
        return {"data": rows, "included": included}


def version_key(value: str) -> tuple:
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", value):
        raise Refusal(f"invalid marketing version {value!r}", 2)
    parts = tuple(int(p) for p in value.split("."))
    return parts + (0,) * (3 - len(parts))


def choose_version(rows: list[dict], platform: str, wanted: str | None):
    mine = sorted(
        (r for r in rows if r["attributes"].get("platform") == platform),
        key=lambda r: version_key(r["attributes"]["versionString"]),
        reverse=True,
    )
    if wanted:
        version_key(wanted)
        matches = [
            r
            for r in mine
            if version_key(r["attributes"]["versionString"]) == version_key(wanted)
        ]
        if matches:
            if version_key(wanted) < version_key(
                mine[0]["attributes"]["versionString"]
            ):
                raise Refusal(
                    "cannot submit an obsolete version below Apple's latest record"
                )
            if matches[0]["attributes"].get("appStoreState") not in WRITABLE:
                raise Refusal(
                    f"{wanted} is {matches[0]['attributes'].get('appStoreState')}; cannot edit it"
                )
            return wanted, matches[0], matches[0]
        if mine and version_key(wanted) <= version_key(
            mine[0]["attributes"]["versionString"]
        ):
            raise Refusal("a new version must be newer than Apple's latest record")
        return wanted, None, mine[0] if mine else None
    editable = (
        mine[:1]
        if mine and mine[0]["attributes"].get("appStoreState") in WRITABLE
        else []
    )
    if editable:
        return editable[0]["attributes"]["versionString"], editable[0], editable[0]
    if not mine:
        raise Refusal(f"no {platform} version history; specify --version", 2)
    parts = mine[0]["attributes"]["versionString"].split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts), None, mine[0]


def identity(document: dict, kind: str) -> str:
    row = document.get("data") or {}
    if row.get("type") != kind or not row.get("id"):
        raise Refusal(f"ASC response has no {kind} identity", 2)
    return row["id"]


def metadata(client: Client, vid: str) -> dict:
    version = client.get(f"/appStoreVersions/{vid}?include=build")
    locs = client.pages(f"/appStoreVersions/{vid}/appStoreVersionLocalizations")["data"]
    sets = {
        loc["id"]: client.pages(
            f"/appStoreVersionLocalizations/{loc['id']}/appScreenshotSets?include=appScreenshots"
        )
        for loc in locs
    }
    detail = client.get(f"/appStoreVersions/{vid}/appStoreReviewDetail", soft404=True)
    return {
        "version": version,
        "localizations": locs,
        "screenshots": sets,
        "review": detail.get("data"),
    }


def app_info(client: Client, app_id: str) -> list[dict]:
    infos = client.pages(
        f"/apps/{app_id}/appInfos?include=primaryCategory,ageRatingDeclaration"
    )["data"]
    for info in infos:
        info["localizations"] = client.pages(
            f"/appInfos/{info['id']}/appInfoLocalizations"
        )["data"]
    return infos


def select_build(document: dict, number: str, platform: str, version: str):
    trains = {
        r["id"]: r["attributes"]
        for r in document.get("included", [])
        if r["type"] == "preReleaseVersions"
    }
    matches = []
    for row in document["data"]:
        rel = (
            row.get("relationships", {}).get("preReleaseVersion", {}).get("data") or {}
        )
        train = trains.get(rel.get("id"), {})
        if (
            row["attributes"].get("version") == number
            and train.get("platform") == platform
            and train.get("version") == version
        ):
            matches.append(row)
    return matches[0] if len(matches) == 1 else None


def gates(
    snapshot: dict,
    infos: list[dict],
    build: dict | None,
    *,
    locale: str,
    whats_new: str | None,
    review_notes: str | None,
) -> list[tuple]:
    """Use the readiness tool's actual predicates, on preflight or readback data."""
    ready = readiness()
    results = [
        (
            "submittable build",
            *ready.build_verdict(None if build is None else build["attributes"]),
        )
    ]
    locs = snapshot.get("localizations", [])
    results.append(("version localizations", bool(locs), "at least one localization"))
    results.append(
        (
            f"selected locale {locale}",
            any(loc["attributes"].get("locale") == locale for loc in locs),
            "locale exists",
        )
    )
    for loc in locs:
        lo = loc["attributes"].get("locale")
        results.append((f"version text [{lo}]", *ready.text_verdict(loc["attributes"])))
        doc = snapshot["screenshots"][loc["id"]]
        shots = {
            r["id"]: r["attributes"]
            for r in doc.get("included", [])
            if r["type"] == "appScreenshots"
        }
        results.append(
            (f"screenshot sets [{lo}]", bool(doc["data"]), "at least one set")
        )
        for row in doc["data"]:
            ids = [
                r["id"]
                for r in (
                    row.get("relationships", {}).get("appScreenshots", {}).get("data")
                    or []
                )
            ]
            results.append(
                (f"screenshots [{lo}]", *ready.screenshot_verdict(ids, shots))
            )
    results.append(
        (
            "review contact",
            *ready.contact_verdict(
                (snapshot.get("review") or {}).get("attributes", {})
            ),
        )
    )
    results.append(
        (
            "What's New",
            bool(whats_new and whats_new.strip()),
            "release-specific text supplied",
        )
    )
    results.append(
        (
            "review note",
            bool(review_notes and review_notes.strip()),
            "review note supplied",
        )
    )
    # Prefer the editable app-info record; do not silently grade a different one.
    editable = [
        i for i in infos if i.get("attributes", {}).get("appStoreState") in WRITABLE
    ]
    info = (editable or infos or [{}])[0]
    rels = info.get("relationships", {})
    results.append(
        (
            "primary category",
            bool(rels.get("primaryCategory", {}).get("data")),
            "category set",
        )
    )
    results.append(
        (
            "age rating",
            bool(rels.get("ageRatingDeclaration", {}).get("data")),
            "declaration exists",
        )
    )
    ilocs = info.get("localizations", [])
    results.append(("app info localizations", bool(ilocs), "at least one localization"))
    for loc in ilocs:
        attrs = loc["attributes"]
        results.append(
            (
                f"name+privacy [{attrs.get('locale')}]",
                bool(
                    (attrs.get("name") or "").strip()
                    and (attrs.get("privacyPolicyUrl") or "").strip()
                ),
                "name and privacy-policy URL set",
            )
        )
    return results


def require_pass(results: list[tuple]) -> None:
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'GAP'}] {name}: {detail}")
    gaps = [name for name, ok, _ in results if not ok]
    if gaps:
        raise Refusal("readiness refused: " + ", ".join(gaps))


def read_text(path: str | None) -> str | None:
    if path is None:
        return None
    text = Path(path).expanduser().read_text(encoding="utf-8").removesuffix("\n")
    if not text.strip() or len(text) > 4000:
        raise Refusal(f"{path}: text must contain 1–4000 characters", 2)
    return text


def confirm(submit: bool, version: str, stream) -> None:
    if not submit or not stream.isatty():
        raise Refusal(
            "submission needs --submit and Alex at an interactive terminal", 2
        )
    expected = f"submit {version}"
    print(
        f"Alex: type exactly {expected!r} to allow Apple writes: ", end="", flush=True
    )
    if stream.readline().removesuffix("\n").removesuffix("\r") != expected:
        raise Refusal("confirmation did not match; no Apple write", 2)


def plan_gets(vid: str, locale_id: str, app_id: str) -> list[str]:
    # Readbacks and final readiness use these same readers. Newly created IDs
    # are placeholders in a dry run, because making them would be an Apple write.
    return [
        f"/apps/{app_id}/appStoreVersions?limit=200&include=build",
        f"/apps/{app_id}/reviewSubmissions?filter[platform]=IOS&limit=200",
        f"/appStoreVersions/{vid}?include=build",
        f"/appStoreVersions/{vid}/appStoreVersionLocalizations",
        f"/appStoreVersionLocalizations/{locale_id}/appScreenshotSets?include=appScreenshots",
        f"/appStoreVersions/{vid}/appStoreReviewDetail",
        f"/appStoreVersions/{vid}/build",
        f"/appStoreVersionLocalizations/{locale_id}",
        f"/apps/{app_id}/appInfos?include=primaryCategory,ageRatingDeclaration",
        "/appInfos/<app-info-id>/appInfoLocalizations",
        "/reviewSubmissions/<submission-id>",
    ]


def execute(client: Client, args, stream=sys.stdin) -> str:
    ready = readiness()
    if args.build and not re.fullmatch(r"\d+(?:\.\d+){0,2}", args.build):
        raise Refusal("--build must be an Apple build number", 2)
    apps = client.pages(f"/apps?filter[bundleId]={ready.BUNDLE_ID}")["data"]
    if len(apps) != 1:
        raise Refusal("expected exactly one app for the configured bundle ID", 2)
    app_id = apps[0]["id"]
    versions_path = f"/apps/{app_id}/appStoreVersions?limit=200&include=build"
    versions = client.pages(versions_path)["data"]
    version, target, source = choose_version(versions, "IOS", args.version)
    print(
        f"IOS {version}: "
        + (
            f"editable version {target['id']}"
            if target
            else f"no editable version; would create {version}"
        )
    )
    if source:
        print(
            f"Source snapshot: IOS {source['attributes']['versionString']} {source['attributes'].get('appStoreState')}"
        )
    snapshot = metadata(client, source["id"]) if source else {}
    infos = app_info(client, app_id)
    submissions_path = (
        f"/apps/{app_id}/reviewSubmissions?filter[platform]=IOS&limit=200"
    )
    submissions = client.pages(submissions_path)["data"]
    build = None
    if args.build:
        builds = client.pages(
            f"/builds?filter[app]={app_id}&filter[version]={args.build}&include=preReleaseVersion&limit=200"
        )
        build = select_build(builds, args.build, "IOS", version)
    else:
        print(
            f"GET /builds?filter[app]={app_id}&filter[version]=<build-number>&include=preReleaseVersion&limit=200 (planned; supply --build)"
        )
    news, notes = read_text(args.whats_new_file), read_text(args.review_notes_file)
    vid = target["id"] if target else "<new-version-id>"
    loc = next(
        (
            loc
            for loc in snapshot.get("localizations", [])
            if loc["attributes"].get("locale") == args.locale
        ),
        None,
    )
    lid = loc["id"] if target and loc else "<version-localization-id>"
    print("\nDRY-RUN plan" if not args.submit else "\nSubmission plan")
    if not target:
        print(f"POST /appStoreVersions: IOS {version}, releaseType=AFTER_APPROVAL")
    print(
        f"PATCH /appStoreVersions/{vid}/relationships/build: {args.build or '<build-number>'}"
    )
    print(f"PATCH /appStoreVersionLocalizations/{lid}: What's New ({args.locale})")
    print("PATCH /appStoreReviewDetails/<review-detail-id>: review note")
    print(
        f"  What's New file: {args.whats_new_file or '<required for --submit>'}; review-note file: {args.review_notes_file or '<required for --submit>'}"
    )
    print(
        "Readiness gate before writes, then again on actual target before review submission."
    )
    print(
        "POST /reviewSubmissions; POST /reviewSubmissionItems; PATCH /reviewSubmissions/<submission-id>: submitted=true"
    )
    print(
        "GETs after confirmation / writes (pagination links are followed and printed):"
    )
    for path in plan_gets(vid, lid, app_id):
        print("  GET " + path)
    print(
        "  Screenshot-set GET repeats for every target localization; app-info localization GET for every appInfo."
    )
    if not args.submit:
        print(
            "DRY-RUN complete: no Apple write. Use --version, --build, --whats-new-file and --review-notes-file for submission."
        )
        return version
    if not args.version:
        raise Refusal("--submit requires an explicit --version", 2)
    preflight = gates(
        snapshot, infos, build, locale=args.locale, whats_new=news, review_notes=notes
    )
    if target:
        attrs = snapshot["version"]["data"]["attributes"]
        preflight.append(
            (
                "editable target",
                attrs.get("platform") == "IOS"
                and attrs.get("versionString") == version
                and attrs.get("appStoreState") in WRITABLE,
                "target is still editable",
            )
        )
    preflight.append(
        (
            "review submissions",
            all(
                s["attributes"].get("state") in TERMINAL_SUBMISSIONS
                for s in submissions
            ),
            "no unfinished review submission",
        )
    )
    require_pass(
        preflight
    )  # No Apple mutation or confirmation prompt before this passes.
    confirm(args.submit, version, stream)
    # Use Apple's current record, not a custom lock. Refuse if it moved while
    # Alex was reading the plan. Requests are not retried after any failure.
    if (
        client.pages(versions_path)["data"] != versions
        or client.pages(submissions_path)["data"] != submissions
    ):
        raise Refusal("Apple's version/review record changed; run the plan again")
    client.write_enabled = True
    if target is None:
        made = client.request(
            "POST",
            "/appStoreVersions",
            {
                "data": {
                    "type": "appStoreVersions",
                    "attributes": {
                        "platform": "IOS",
                        "versionString": version,
                        "releaseType": "AFTER_APPROVAL",
                    },
                    "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
                }
            },
        )
        vid = identity(made, "appStoreVersions")
    current = metadata(client, vid)
    actual = current["version"]["data"]["attributes"]
    if (
        actual.get("platform") != "IOS"
        or actual.get("versionString") != version
        or actual.get("appStoreState") not in WRITABLE
    ):
        raise Refusal("target version is not the confirmed editable IOS version")
    loc = next(
        (
            loc
            for loc in current["localizations"]
            if loc["attributes"].get("locale") == args.locale
        ),
        None,
    )
    detail = current.get("review")
    if loc is None or detail is None:
        raise Refusal(
            "GAP: new version did not inherit localization/review contact; resolve in App Store Connect"
        )
    require_pass(
        gates(
            current,
            app_info(client, app_id),
            build,
            locale=args.locale,
            whats_new=news,
            review_notes=notes,
        )
    )
    client.request(
        "PATCH",
        f"/appStoreVersions/{vid}/relationships/build",
        {"data": {"type": "builds", "id": build["id"]}},
    )
    attached = client.get(f"/appStoreVersions/{vid}/build")
    if identity(attached, "builds") != build["id"]:
        raise Refusal("attached build readback differs from the plan")
    lid = loc["id"]
    client.request(
        "PATCH",
        f"/appStoreVersionLocalizations/{lid}",
        {
            "data": {
                "type": "appStoreVersionLocalizations",
                "id": lid,
                "attributes": {"whatsNew": news},
            }
        },
    )
    if (
        client.get(f"/appStoreVersionLocalizations/{lid}")["data"]["attributes"].get(
            "whatsNew"
        )
        != news
    ):
        raise Refusal("What's New readback differs from the plan")
    rid = detail["id"]
    client.request(
        "PATCH",
        f"/appStoreReviewDetails/{rid}",
        {
            "data": {
                "type": "appStoreReviewDetails",
                "id": rid,
                "attributes": {"notes": notes},
            }
        },
    )
    if (
        client.get(f"/appStoreVersions/{vid}/appStoreReviewDetail")["data"][
            "attributes"
        ].get("notes")
        != notes
    ):
        raise Refusal("review-note readback differs from the plan")
    final = metadata(client, vid)
    final_loc = next(
        (
            loc
            for loc in final["localizations"]
            if loc["attributes"].get("locale") == args.locale
        ),
        {},
    )
    final_notes = (final.get("review") or {}).get("attributes", {}).get("notes")
    final_news = final_loc.get("attributes", {}).get("whatsNew")
    final_gates = gates(
        final,
        app_info(client, app_id),
        attached["data"],
        locale=args.locale,
        whats_new=final_news,
        review_notes=final_notes,
    )
    final_gates[0] = (
        "submittable build",
        *ready.build_gate(
            final["version"]["data"], final["version"].get("included", [])
        ),
    )
    va = final["version"]["data"]["attributes"]
    final_gates.extend(
        [
            (
                "target version",
                va.get("platform") == "IOS"
                and va.get("versionString") == version
                and va.get("appStoreState") in WRITABLE,
                "confirmed editable IOS version",
            ),
            (
                "metadata readback",
                final_news == news and final_notes == notes,
                "release text still matches the plan",
            ),
        ]
    )
    require_pass(final_gates)
    final_build = (
        final["version"]["data"].get("relationships", {}).get("build", {}).get("data")
        or {}
    )
    if final_build.get("id") != build["id"]:
        raise Refusal("target build changed before review submission")
    if client.pages(submissions_path)["data"] != submissions:
        raise Refusal("review submissions changed; refusing a duplicate")
    submission = client.request(
        "POST",
        "/reviewSubmissions",
        {
            "data": {
                "type": "reviewSubmissions",
                "attributes": {"platform": "IOS"},
                "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
            }
        },
    )
    sid = identity(submission, "reviewSubmissions")
    item = client.request(
        "POST",
        "/reviewSubmissionItems",
        {
            "data": {
                "type": "reviewSubmissionItems",
                "relationships": {
                    "reviewSubmission": {
                        "data": {"type": "reviewSubmissions", "id": sid}
                    },
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": vid}
                    },
                },
            }
        },
    )
    identity(item, "reviewSubmissionItems")
    client.request(
        "PATCH",
        f"/reviewSubmissions/{sid}",
        {
            "data": {
                "type": "reviewSubmissions",
                "id": sid,
                "attributes": {"submitted": True},
            }
        },
    )
    submitted = client.get(f"/reviewSubmissions/{sid}")["data"]["attributes"]
    if submitted.get("state") not in {
        "WAITING_FOR_REVIEW",
        "IN_REVIEW",
        "COMPLETE",
    } or not submitted.get("submittedDate"):
        raise Refusal(
            "submission readback did not confirm submission; inspect receipts before another attempt"
        )
    print(f"SUBMITTED IOS {version}: {submitted['state']}")
    return version


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="default; GET only")
    mode.add_argument(
        "--submit", action="store_true", help="needs Alex's exact typed confirmation"
    )
    mode.add_argument(
        "--self-check",
        action="store_true",
        help="offline tests; no credentials or network",
    )
    p.add_argument("--version")
    p.add_argument(
        "--build", help="processed build number for this IOS marketing version"
    )
    p.add_argument("--locale", default="en-US")
    p.add_argument("--whats-new-file")
    p.add_argument("--review-notes-file")
    stamp = datetime.now(PT).strftime("%Y%m%dT%H%M%S%z")
    p.add_argument(
        "--receipts", default=f"~/.bainluck/asc-submit/{stamp}-{os.getpid()}.jsonl"
    )
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.self_check:
        return self_check()
    try:
        # Exactly the readiness tool's credential/JWT path; never a second resolver.
        bearer = readiness().token()
        client = Client(bearer, Path(args.receipts))
        print(f"App Store plan — {datetime.now(PT):%Y-%m-%d %I:%M:%S %p %Z}")
        print(f"Receipts: {client.receipt}")
        execute(client, args)
        return 0
    except Refusal as exc:
        print(f"ASC: {exc}", file=sys.stderr)
        return exc.code
    except (OSError, ValueError, KeyError) as exc:
        print(f"ASC: unusable input/response: {exc}", file=sys.stderr)
        return 2


def self_check() -> int:
    """Exercise the real HTTP/submit path offline, including both write gates."""
    import contextlib
    import io
    import tempfile
    import unittest
    import unittest.mock as mock
    from urllib.parse import urlsplit

    class Response:
        def __init__(self, data, status=200):
            self.status = status
            self.raw = json.dumps(data).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return self.raw

    class Apple:
        def __init__(self):
            self.confirmed = False
            self.calls = []
            self.fault = None
            self.states = {"v5": "READY_FOR_SALE"}
            self.attached = {"v5": "old-build"}
            self.news, self.notes = {}, {}
            self.submissions = []
            self.contact = dict(
                contactFirstName="A",
                contactLastName="B",
                contactEmail="a@example.invalid",
                contactPhone="123",
            )

        def row(self, vid):
            return {
                "type": "appStoreVersions",
                "id": vid,
                "attributes": {
                    "platform": "IOS",
                    "versionString": "1.0.5" if vid == "v5" else "1.0.6",
                    "appStoreState": self.states[vid],
                },
                "relationships": {
                    "build": {
                        "data": (
                            {"type": "builds", "id": self.attached[vid]}
                            if vid in self.attached
                            else None
                        )
                    }
                },
            }

        def __call__(self, req, timeout):
            method, path = req.get_method(), urlsplit(req.full_url).path.removeprefix(
                "/v1"
            )
            body = json.loads(req.data) if req.data else None
            self.calls.append((method, path, body))
            if method != "GET":
                if not self.confirmed:
                    raise AssertionError("Apple write before Alex's typed line")
                data = body["data"]
                if path == "/appStoreVersions":
                    self.states["v6"] = "PREPARE_FOR_SUBMISSION"
                    return Response({"data": self.row("v6")}, 201)
                if path.endswith("/relationships/build"):
                    self.attached[path.split("/")[2]] = data["id"]
                    return Response({}, 204)
                if path.startswith("/appStoreVersionLocalizations/"):
                    self.news[path.split("/")[-1]] = data["attributes"]["whatsNew"]
                    return Response({"data": data})
                if path.startswith("/appStoreReviewDetails/"):
                    self.notes[path.split("/")[-1]] = data["attributes"]["notes"]
                    return Response({"data": data})
                if path == "/reviewSubmissions":
                    self.submissions = [
                        {
                            "id": "submission",
                            "type": "reviewSubmissions",
                            "attributes": {"state": "READY_FOR_REVIEW"},
                        }
                    ]
                    return Response({"data": self.submissions[0]}, 201)
                if path == "/reviewSubmissionItems":
                    return Response({"data": {**data, "id": "item"}}, 201)
                if path == "/reviewSubmissions/submission":
                    self.submissions[0]["attributes"] = {
                        "state": "WAITING_FOR_REVIEW",
                        "submittedDate": "2026-11-03T20:00:00Z",
                    }
                    return Response({"data": self.submissions[0]})
                raise AssertionError((method, path))
            if path == "/apps":
                return Response({"data": [{"type": "apps", "id": "app"}]})
            if path == "/apps/app/appStoreVersions":
                return Response({"data": [self.row(v) for v in self.states]})
            if path == "/apps/app/reviewSubmissions":
                return Response({"data": copy.deepcopy(self.submissions)})
            if path == "/builds":
                return Response(
                    {
                        "data": [
                            {
                                "id": "build",
                                "type": "builds",
                                "attributes": {
                                    "version": "5650",
                                    "processingState": (
                                        "PROCESSING"
                                        if self.fault == "processing"
                                        else "VALID"
                                    ),
                                    "expired": self.fault == "expired",
                                },
                                "relationships": {
                                    "preReleaseVersion": {"data": {"id": "train"}}
                                },
                            }
                        ],
                        "included": [
                            {
                                "id": "train",
                                "type": "preReleaseVersions",
                                "attributes": {
                                    "platform": (
                                        "MAC_OS" if self.fault == "platform" else "IOS"
                                    ),
                                    "version": (
                                        "1.0.5" if self.fault == "train" else "1.0.6"
                                    ),
                                },
                            }
                        ],
                    }
                )
            if path == "/apps/app/appInfos":
                return Response(
                    {
                        "data": [
                            {
                                "id": "info",
                                "attributes": {},
                                "relationships": {
                                    "primaryCategory": {
                                        "data": (
                                            None
                                            if self.fault == "category"
                                            else {"id": "SPORTS"}
                                        )
                                    },
                                    "ageRatingDeclaration": {
                                        "data": (
                                            None
                                            if self.fault == "age"
                                            else {"id": "age"}
                                        )
                                    },
                                },
                            }
                        ]
                    }
                )
            if path == "/appInfos/info/appInfoLocalizations":
                return Response(
                    {
                        "data": (
                            []
                            if self.fault == "app-localizations"
                            else [
                                {
                                    "attributes": {
                                        "locale": "en-US",
                                        "name": "Bain Luck",
                                        "privacyPolicyUrl": (
                                            ""
                                            if self.fault == "privacy"
                                            else "https://bainluck.com/privacy"
                                        ),
                                    }
                                }
                            ]
                        )
                    }
                )
            if path.startswith("/appStoreVersions/"):
                vid = path.split("/")[2]
                if path.endswith("/appStoreVersionLocalizations"):
                    return Response(
                        {
                            "data": [
                                {
                                    "id": "loc-" + vid,
                                    "attributes": {
                                        "locale": "en-US",
                                        "description": (
                                            ""
                                            if self.fault == "text"
                                            else "Description"
                                        ),
                                        "keywords": "sports",
                                        "whatsNew": self.news.get("loc-" + vid, "Old"),
                                    },
                                }
                            ]
                        }
                    )
                if path.endswith("/appStoreReviewDetail"):
                    return Response(
                        {
                            "data": {
                                "id": "review-" + vid,
                                "attributes": {
                                    **self.contact,
                                    "notes": self.notes.get("review-" + vid, "Old"),
                                },
                            }
                        }
                    )
                attrs = {
                    "version": "5650",
                    "processingState": "VALID",
                    "expired": self.fault == "late-expired"
                    and self.attached.get(vid) == "build",
                }
                build = {
                    "id": self.attached.get(vid, "missing"),
                    "type": "builds",
                    "attributes": attrs,
                }
                if path.endswith("/build"):
                    return Response({"data": build})
                return Response({"data": self.row(vid), "included": [build]})
            if path.startswith("/appStoreVersionLocalizations/"):
                lid = path.split("/")[2]
                if path.endswith("/appScreenshotSets"):
                    incomplete = self.fault == "screenshots" or (
                        self.fault == "late-gap" and lid == "loc-v6"
                    )
                    return Response(
                        {
                            "data": [
                                {
                                    "relationships": {
                                        "appScreenshots": {"data": [{"id": "shot"}]}
                                    }
                                }
                            ],
                            "included": [
                                {
                                    "id": "shot",
                                    "type": "appScreenshots",
                                    "attributes": {
                                        "assetDeliveryState": {
                                            "state": (
                                                "UPLOAD_COMPLETE"
                                                if incomplete
                                                else "COMPLETE"
                                            )
                                        }
                                    },
                                }
                            ],
                        }
                    )
                return Response(
                    {"data": {"attributes": {"whatsNew": self.news.get(lid)}}}
                )
            if path == "/reviewSubmissions/submission":
                return Response({"data": self.submissions[0]})
            raise AssertionError((method, path))

    class Terminal(io.StringIO):
        def __init__(self, apple, line, tty=True):
            super().__init__(line)
            self.apple, self.tty = apple, tty

        def isatty(self):
            return self.tty

        def readline(self, *args):
            self.apple.confirmed = True
            return super().readline(*args)

    class Checks(unittest.TestCase):
        def setUp(self):
            self.temp = tempfile.TemporaryDirectory()
            self.addCleanup(self.temp.cleanup)
            self.root = Path(self.temp.name)
            for name, text in [("news", "Release notes\n"), ("notes", "Review note\n")]:
                (self.root / name).write_text(text)

        def run_flow(self, apple, submit=False, line="submit 1.0.6\n", tty=True):
            argv = [
                "--version",
                "1.0.6",
                "--build",
                "5650",
                "--whats-new-file",
                str(self.root / "news"),
                "--review-notes-file",
                str(self.root / "notes"),
            ]
            if submit:
                argv.append("--submit")
            client = Client("OFFLINE-SECRET", self.root / "receipts.jsonl")
            output = io.StringIO()
            with mock.patch(
                "urllib.request.urlopen", side_effect=apple
            ), contextlib.redirect_stdout(output):
                result = execute(
                    client, parser().parse_args(argv), Terminal(apple, line, tty)
                )
            return result, output.getvalue()

        def test_version_platform_and_in_review(self):
            apple = Apple()
            apple.states["v5"] = "IN_REVIEW"
            mac = {
                "id": "mac",
                "attributes": {
                    "platform": "MAC_OS",
                    "versionString": "20.0",
                    "appStoreState": "PREPARE_FOR_SUBMISSION",
                },
            }
            version, target, source = choose_version(
                [mac, apple.row("v5")], "IOS", None
            )
            self.assertEqual((version, target, source["id"]), ("1.0.6", None, "v5"))
            obsolete = {
                "id": "v4",
                "attributes": {
                    "platform": "IOS",
                    "versionString": "1.0.4",
                    "appStoreState": "REJECTED",
                },
            }
            self.assertEqual(
                choose_version([obsolete, apple.row("v5")], "IOS", None)[0], "1.0.6"
            )
            with self.assertRaises(Refusal):
                choose_version([obsolete, apple.row("v5")], "IOS", "1.0.4")
            with self.assertRaises(Refusal):
                choose_version([apple.row("v5")], "IOS", "1.0.5")
            self.assertFalse(parser().parse_args([]).submit)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
                SystemExit
            ):
                parser().parse_args(["--dry-run", "--submit"])

        def test_dry_run_never_writes_and_lists_gets(self):
            apple = Apple()
            result, output = self.run_flow(apple)
            self.assertEqual(result, "1.0.6")
            self.assertIn("no editable version; would create 1.0.6", output)
            self.assertTrue(all(method == "GET" for method, _, _ in apple.calls))
            for method in [
                "POST /appStoreVersions",
                "relationships/build",
                "What's New",
                "review note",
                "/reviewSubmissionItems",
                "submitted=true",
                "GET /reviewSubmissions/<submission-id>",
            ]:
                self.assertIn(method, output)
            receipts = (self.root / "receipts.jsonl").read_text()
            self.assertNotIn("OFFLINE-SECRET", receipts)
            self.assertEqual(len(receipts.splitlines()), 2 * len(apple.calls))

        def test_both_confirmation_gates(self):
            for line, tty in [
                ("yes\n", True),
                ("submit 1.0.5\n", True),
                (" submit 1.0.6\n", True),
                ("submit 1.0.6\n", False),
                ("", True),
            ]:
                apple = Apple()
                with self.subTest(line=line, tty=tty), self.assertRaises(Refusal):
                    self.run_flow(apple, True, line, tty)
                self.assertTrue(all(method == "GET" for method, _, _ in apple.calls))
            client = Client("OFFLINE-SECRET", self.root / "blocked.jsonl")
            with self.assertRaises(Refusal):
                client.request("POST", "/appStoreVersions", {})

        def test_every_preflight_gap_refuses_before_apple_write(self):
            for fault in [
                "expired",
                "processing",
                "platform",
                "train",
                "text",
                "screenshots",
                "contact",
                "category",
                "age",
                "privacy",
                "app-localizations",
                "active-submission",
            ]:
                apple = Apple()
                apple.fault = fault
                if fault == "contact":
                    apple.contact["contactPhone"] = ""
                if fault == "active-submission":
                    apple.submissions = [{"attributes": {"state": "IN_REVIEW"}}]
                with self.subTest(fault=fault), self.assertRaises(Refusal):
                    self.run_flow(apple, True)
                self.assertFalse(apple.confirmed)
                self.assertTrue(all(method == "GET" for method, _, _ in apple.calls))

        def test_full_submission_after_gates_and_exact_typed_line(self):
            apple = Apple()
            result, _ = self.run_flow(apple, True)
            writes = [(m, p) for m, p, _ in apple.calls if m != "GET"]
            self.assertEqual(result, "1.0.6")
            self.assertEqual(
                writes,
                [
                    ("POST", "/appStoreVersions"),
                    ("PATCH", "/appStoreVersions/v6/relationships/build"),
                    ("PATCH", "/appStoreVersionLocalizations/loc-v6"),
                    ("PATCH", "/appStoreReviewDetails/review-v6"),
                    ("POST", "/reviewSubmissions"),
                    ("POST", "/reviewSubmissionItems"),
                    ("PATCH", "/reviewSubmissions/submission"),
                ],
            )
            self.assertEqual(
                apple.submissions[0]["attributes"]["state"], "WAITING_FOR_REVIEW"
            )

        def test_post_create_gap_cannot_submit_review(self):
            apple = Apple()
            apple.fault = "late-gap"
            with self.assertRaises(Refusal):
                self.run_flow(apple, True)
            self.assertIn("v6", apple.states)
            self.assertEqual(
                [(m, p) for m, p, _ in apple.calls if m != "GET"],
                [("POST", "/appStoreVersions")],
            )
            self.assertFalse(
                any(
                    m == "POST" and p == "/reviewSubmissions" for m, p, _ in apple.calls
                )
            )

        def test_a_build_expiring_after_preflight_cannot_submit_review(self):
            apple = Apple()
            apple.fault = "late-expired"
            with self.assertRaises(Refusal):
                self.run_flow(apple, True)
            self.assertFalse(
                any(
                    m == "POST" and p == "/reviewSubmissions" for m, p, _ in apple.calls
                )
            )

        def test_pagination_follows_each_get_and_refuses_cycles(self):
            client = Client("OFFLINE-SECRET", self.root / "pages.jsonl")
            pages = [
                Response({"data": [{"id": "one"}], "links": {"next": API + "/second"}}),
                Response({"data": [{"id": "two"}]}),
            ]
            with mock.patch(
                "urllib.request.urlopen", side_effect=pages
            ) as transport, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    client.pages("/first")["data"], [{"id": "one"}, {"id": "two"}]
                )
                self.assertEqual(transport.call_count, 2)
            with mock.patch(
                "urllib.request.urlopen",
                return_value=Response({"data": [], "links": {"next": "/first"}}),
            ), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(Refusal):
                client.pages("/first")

        def test_http_and_transport_failures_leave_receipts_without_retry(self):
            errors = [
                urllib.error.HTTPError(
                    API + "/apps",
                    503,
                    "unavailable",
                    {},
                    io.BytesIO(b'{"error":"unavailable"}'),
                ),
                urllib.error.URLError("unavailable"),
            ]
            for n, error in enumerate(errors):
                path = self.root / f"error-{n}.jsonl"
                client = Client("OFFLINE-SECRET", path)
                with mock.patch(
                    "urllib.request.urlopen", side_effect=error
                ) as transport, contextlib.redirect_stdout(
                    io.StringIO()
                ), self.assertRaises(
                    Refusal
                ):
                    client.get("/apps")
                self.assertEqual(transport.call_count, 1)
                records = [json.loads(s) for s in path.read_text().splitlines()]
                self.assertEqual([r["event"] for r in records], ["request", "response"])
                self.assertNotIn("OFFLINE-SECRET", path.read_text())

    # Any accidentally unmocked auth or HTTP call makes the offline suite fail.
    with mock.patch.object(
        readiness(),
        "token",
        side_effect=AssertionError("offline self-check called credentials"),
    ), mock.patch(
        "urllib.request.urlopen",
        side_effect=AssertionError("offline self-check called Apple"),
    ):
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
        )
    print(
        f"SELF-CHECK {'PASS' if result.wasSuccessful() else 'FAILED'} — {result.testsRun} offline tests"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
