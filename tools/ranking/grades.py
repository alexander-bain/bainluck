#!/usr/bin/env python3
"""#12095 Decide 37-B: fetch a captured slate, and make its grading sheet.

    # 1. Save a slate (newest by default) for the scorecard and the sheet:
    python3 tools/ranking/grades.py fetch [--slate latest|<slate id>] [--surface discover]

    # 2. Turn its opening ten into a grading sheet for one grader:
    python3 tools/ranking/grades.py sheet --slate evals/ranking/slates/<file>.json --grader alex
    python3 tools/ranking/grades.py sheet --slate ... --grader dexter --kid

``sheet`` prints the sheet as markdown and writes
``evals/ranking/grades/<date>-<surface>-<grader>.json`` with every ``grade``
empty: fill each with ``shareable``, ``interesting`` or ``neither`` (and an
optional ``note``). ``--kid`` records the grader as non-expert, which keeps
their grades out of the founder NDCG. An existing file is never overwritten.

Credentials for ``fetch``: ``BAINLUCK_API`` (default https://api.bainluck.com)
and ``ADMIN_TOKEN`` from the environment; when ``ADMIN_TOKEN`` is unset, it is
read from the Heroku app's config through the Platform API (``~/.netrc``) and
held in memory only. The token is never printed or written.
"""

from __future__ import annotations

import argparse
import json
import netrc
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SLATES_DIR = REPO / "evals" / "ranking" / "slates"
GRADES_DIR = REPO / "evals" / "ranking" / "grades"
GRADES = ("shareable", "interesting", "neither")
DEFAULT_API = "https://api.bainluck.com"
HEROKU_APP = "bainluck"


def _admin_token() -> str:
    token = os.environ.get("ADMIN_TOKEN")
    if token:
        return token
    auth = netrc.netrc().authenticators("api.heroku.com")
    if not auth:
        raise SystemExit("ADMIN_TOKEN unset and no api.heroku.com entry in ~/.netrc")
    req = urllib.request.Request(
        f"https://api.heroku.com/apps/{HEROKU_APP}/config-vars",
        headers={"Accept": "application/vnd.heroku+json; version=3", "Authorization": f"Bearer {auth[2]}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        token = json.load(resp).get("ADMIN_TOKEN")
    if not token:
        raise SystemExit("ADMIN_TOKEN is not set on the Heroku app")
    return token


def fetch_slate(ref: str, surface: str) -> dict:
    api = os.environ.get("BAINLUCK_API") or DEFAULT_API
    url = f"{api}/api/admin/ranking/slates/{urllib.parse.quote(ref, safe='')}?surface={urllib.parse.quote(surface)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_admin_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GET slate {ref!r}: HTTP {exc.code} {exc.read()[:300].decode(errors='replace')}")


def slate_filename(slate: dict) -> str:
    date = str(slate.get("captured_at") or "")[:10] or "undated"
    return f"{date}-{slate.get('surface')}-{slate.get('slate_id')}.json"


def grader_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise SystemExit("--grader needs a name")
    return slug[:40]


def build_sheet(slate: dict, *, grader: str, kid: bool, top: int = 10) -> dict:
    """The grading document for one grader: the slate's opening ``top`` with
    empty grades. The same shape the scorecard reads once filled in."""
    by_key = {c.get("item_key"): c for c in slate.get("candidates") or ()}
    items = []
    for position, key in enumerate((slate.get("served_order") or [])[:top], start=1):
        cand = by_key.get(key) or {}
        items.append(
            {
                "position": position,
                "item_key": key,
                "title": cand.get("title"),
                "probability": cand.get("probability"),
                "grade": None,
                "note": "",
            }
        )
    return {
        "slate_id": slate.get("slate_id"),
        "surface": slate.get("surface"),
        "captured_at": slate.get("captured_at"),
        "ranker_version": slate.get("ranker_version"),
        "grader": grader,
        "expert": not kid,
        "grades_allowed": list(GRADES),
        "items": items,
    }


def sheet_markdown(sheet: dict) -> str:
    lines = [
        f"### Grading sheet — {sheet['surface']} slate `{sheet['slate_id']}` · grader {sheet['grader']}"
        + ("" if sheet["expert"] else " (kid)"),
        "",
        "| # | Card | Probability | Grade (shareable / interesting / neither) | Note |",
        "|---|---|---|---|---|",
    ]
    for item in sheet["items"]:
        prob = item["probability"]
        shown = "—" if prob is None else f"{prob:.0%}"
        lines.append(f"| {item['position']} | {item['title'] or item['item_key']} | {shown} |  |  |")
    return "\n".join(lines) + "\n"


def validate_grades(doc: dict) -> list[str]:
    """Problems with a filled-in grades file (empty list = fine)."""
    problems = []
    if not doc.get("slate_id"):
        problems.append("no slate_id")
    if not doc.get("grader"):
        problems.append("no grader")
    for item in doc.get("items") or ():
        if item.get("grade") not in (*GRADES, None):
            problems.append(f"position {item.get('position')}: grade {item.get('grade')!r} not in {GRADES}")
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--slate", default="latest")
    f.add_argument("--surface", default="discover")
    f.add_argument("--out", type=Path, default=SLATES_DIR)
    s = sub.add_parser("sheet")
    s.add_argument("--slate", type=Path, required=True)
    s.add_argument("--grader", required=True)
    s.add_argument("--kid", action="store_true")
    s.add_argument("--out", type=Path, default=GRADES_DIR)
    v = sub.add_parser("check")
    v.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "fetch":
        slate = fetch_slate(args.slate, args.surface)
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / slate_filename(slate)
        path.write_text(json.dumps(slate, indent=1, sort_keys=True) + "\n")
        print(path)
        return 0
    if args.cmd == "sheet":
        slate = json.loads(args.slate.read_text())
        sheet = build_sheet(slate, grader=args.grader.strip(), kid=args.kid)
        date = str(slate.get("captured_at") or "")[:10] or "undated"
        path = args.out / f"{date}-{slate.get('surface')}-{grader_slug(args.grader)}.json"
        if path.exists():
            raise SystemExit(f"{path} exists; not overwriting a grader's file")
        args.out.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sheet, indent=1) + "\n")
        sys.stdout.write(sheet_markdown(sheet))
        print(f"\nwrote {path}")
        return 0
    bad = 0
    for path in args.files:
        for problem in validate_grades(json.loads(path.read_text())):
            print(f"{path}: {problem}")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
