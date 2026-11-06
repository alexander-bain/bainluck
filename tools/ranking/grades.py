#!/usr/bin/env python3
"""#12095 Decide 37-B: fetch a captured slate, and make its grading sheet.

    # 1. Save a slate (newest by default) for the scorecard and the sheet:
    python3 tools/ranking/grades.py fetch [--slate latest|<slate id>] [--surface discover]

    # 3. Copy grades made on the /grade page into the same store:
    python3 tools/ranking/grades.py export [--slate <slate id>] [--days 14]

    # 2. Turn its opening ten into a grading sheet for one grader:
    python3 tools/ranking/grades.py sheet --slate evals/ranking/slates/<file>.json --grader alex
    python3 tools/ranking/grades.py sheet --slate ... --grader kid1 --kid

``sheet`` prints the sheet as markdown and writes
``evals/ranking/grades/<date PT>-<surface>-<slate id>-<grader>.json`` with every
``grade`` empty: fill each with ``shareable``, ``interesting`` or ``neither``
(and an optional ``note``). ``--kid`` records the grader as non-expert, which
keeps their grades out of the founder NDCG. **A kid's grader id is a pseudonym
(``kid1``, ``kid2``…), never a name: this directory is committed to a public
repository.** An existing file is never overwritten.

Credentials for ``fetch``: ``BAINLUCK_API`` (default https://api.bainluck.com)
and ``ADMIN_TOKEN`` from the environment; when ``ADMIN_TOKEN`` is unset, it is
read from the Heroku app's config through the Platform API (``~/.netrc``) and
held in memory only. The token is never printed or written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import netrc
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
SLATES_DIR = REPO / "evals" / "ranking" / "slates"
GRADES_DIR = REPO / "evals" / "ranking" / "grades"
GRADES = ("shareable", "interesting", "neither")
PT = ZoneInfo("America/Los_Angeles")
#: A kid's grader id: ``kid1`` (hand sheets) or ``kid-<6 hex>`` (export's
#: pseudonym for a name typed on the /grade page). Never a child's name.
KID_ID = re.compile(r"^kid(?:[0-9]+|-[0-9a-f]{6})$")


def kid_pseudonym(name: str) -> str:
    """The stable public id for a kid's typed name (the name stays in the DB)."""
    return "kid-" + hashlib.sha256(" ".join(name.lower().split()).encode()).hexdigest()[:6]


def pt_date(stamp: Optional[str]) -> str:
    """A UTC ISO stamp's calendar date in Pacific time ("undated" if none)."""
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(PT).date().isoformat()
    except (TypeError, ValueError):
        return "undated"


def pt_label(stamp: Optional[str]) -> str:
    try:
        at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(PT)
    except (TypeError, ValueError):
        return "an unknown time"
    return at.strftime("%a %b %-d, %-I:%M %p PT")
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


def _admin_get(path: str) -> dict:
    api = os.environ.get("BAINLUCK_API") or DEFAULT_API
    req = urllib.request.Request(f"{api}{path}", headers={"Authorization": f"Bearer {_admin_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GET {path.split('?')[0]}: HTTP {exc.code} {exc.read()[:300].decode(errors='replace')}")


def fetch_slate(ref: str, surface: str) -> dict:
    return _admin_get(
        f"/api/admin/ranking/slates/{urllib.parse.quote(ref, safe='')}?surface={urllib.parse.quote(surface)}"
    )


#: Marks a grades file written by ``export`` (the /grade page's grades), so a
#: re-export refreshes it and never overwrites a hand-filled sheet.
EXPORT_SOURCE = "grade-page"


def export_documents(grades: list[dict]) -> list[dict]:
    """The /grade page's grades as grades files: one per (slate, grader), the
    same shape ``sheet`` makes, in position order."""
    docs: dict[tuple, dict] = {}
    for g in grades:
        expert = g.get("expert") is True
        # A kid's typed name never reaches the public repo: it becomes a pseudonym.
        grader = g["grader"] if expert else kid_pseudonym(g["grader"])
        key = (g["slate_id"], grader)
        doc = docs.setdefault(
            key,
            {
                "slate_id": g["slate_id"],
                "surface": g.get("surface") or "discover",
                "grader": grader,
                "expert": expert,
                "source": EXPORT_SOURCE,
                "date": pt_date(g.get("graded_at")),
                "items": [],
            },
        )
        doc["items"].append(
            {"position": g["position"], "item_key": g["item_key"], "grade": g["grade"], "note": g.get("note") or ""}
        )
    for doc in docs.values():
        doc["items"].sort(key=lambda i: i["position"])
    return list(docs.values())


def export_path(out: Path, doc: dict) -> Path:
    """``<PT date>-<surface>-<slate id>-<grader>.json``; ``-web`` is added when a
    hand-filled sheet already holds that name (never overwritten)."""
    stem = f"{doc['date']}-{doc['surface']}-{doc['slate_id']}-{grader_slug(doc['grader'])}"
    path = out / f"{stem}.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except ValueError:
            existing = {}
        if existing.get("source") != EXPORT_SOURCE:
            path = out / f"{stem}-web.json"
    return path


def slate_filename(slate: dict) -> str:
    return f"{pt_date(slate.get('captured_at'))}-{slate.get('surface')}-{slate.get('slate_id')}.json"


def grades_filename(slate: dict, grader: str) -> str:
    """One file per grader per slate: two captures on one day never collide."""
    return f"{pt_date(slate.get('captured_at'))}-{slate.get('surface')}-{slate.get('slate_id')}-{grader_slug(grader)}.json"


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
        f"Captured {pt_label(sheet.get('captured_at'))}.",
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
    """Problems with a filled-in grades file (empty list = fine). Grades are
    compared trimmed and lower-cased; ``expert`` must be an explicit bool; a
    non-expert grader must be a pseudonym."""
    problems = []
    if not doc.get("slate_id"):
        problems.append("no slate_id")
    if not doc.get("grader"):
        problems.append("no grader")
    if not isinstance(doc.get("expert"), bool):
        problems.append("`expert` must be true or false")
    elif doc["expert"] is False and not KID_ID.match(str(doc.get("grader") or "")):
        problems.append(f"kid grader {doc.get('grader')!r} must be a pseudonym like kid1")
    for item in doc.get("items") or ():
        raw = item.get("grade")
        grade = str(raw).strip().lower() if raw is not None else None
        if grade and grade not in GRADES:
            problems.append(f"position {item.get('position')}: grade {raw!r} not in {GRADES}")
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
    e = sub.add_parser("export")
    e.add_argument("--slate", default=None)
    e.add_argument("--days", type=int, default=14)
    e.add_argument("--out", type=Path, default=GRADES_DIR)
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
        grader = args.grader.strip()
        if args.kid and not KID_ID.match(grader):
            raise SystemExit(f"--kid grader {grader!r} must be a pseudonym like kid1 (the grades are public)")
        sheet = build_sheet(slate, grader=grader, kid=args.kid)
        path = args.out / grades_filename(slate, grader)
        if path.exists():
            raise SystemExit(f"{path} exists; not overwriting a grader's file")
        args.out.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sheet, indent=1) + "\n")
        sys.stdout.write(sheet_markdown(sheet))
        print(f"\nwrote {path}")
        return 0
    if args.cmd == "export":
        query = f"?days={args.days}" + (f"&slate_id={urllib.parse.quote(args.slate)}" if args.slate else "")
        args.out.mkdir(parents=True, exist_ok=True)
        for doc in export_documents(_admin_get(f"/api/admin/ranking/grades{query}")["grades"]):
            path = export_path(args.out, doc)
            path.write_text(json.dumps(doc, indent=1) + "\n")
            print(f"{path} ({len(doc['items'])} grades)")
        return 0
    bad = 0
    for path in args.files:
        for problem in validate_grades(json.loads(path.read_text())):
            print(f"{path}: {problem}")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
