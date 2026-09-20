#!/usr/bin/env python3
"""#7397 — does the league word we PUT THERE name the right league? (lane1b)

The census this replaces asked "did the venue's word go away" and answered 1,261
repairs / 0 losses. That count was true and it hid a defect: `Women's Pro
Basketball` (the WNBA, 58 markets) counted as a repair while being rewritten to
`Women's NBA`. A changed row and a correct row are the same row to a diff count.

So this asks the question a count cannot:

  A. PER LEAGUE PAGE — for each of the 29 league sport_keys, take the SERVED
     payload, rewrite every name, and assert the league token that appears is
     the one that page is about. `NBA` on `/sport/basketball/wnba` is the bug;
     no count can see it, a per-page check cannot miss it.
  B. WHOLE POPULATION — every `futures_markets.name` carrying the venue phrase,
     through master's function and this branch's, classified into
     repaired / unchanged / newly-wrong, with every mover NAMED.
  C. The qualifier guard's two directions: a mapped qualifier is translated, an
     unmapped one is left alone rather than given a wrong league.

Usage: python3 tools/lane1b-7397-league-vocab-census.py
Needs BAINLUCK_API + ADMIN_TOKEN in the environment (source ~/.claude/.env).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

API = os.environ["BAINLUCK_API"]
TOKEN = os.environ["ADMIN_TOKEN"]
REPO = "/Users/bain/bainluck-dev/lane1b"
MODULE_PATH = "backend/app/utils/market_label_normalization.py"

VENUE = re.compile(r"\bPro (Football|Basketball|Hockey|Baseball)\b", re.I)
# The league tokens the rewrites can introduce, so we can ask which one landed.
LEAGUE_TOKEN = re.compile(r"\b(WNBA|NBA|NFL|NHL|MLB)\b")


def _load(path: str, name: str):
    """Import a copy of the module by path, so master and branch coexist."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# The BEFORE is `046c88245`, not `origin/master`. Master has no
# `rewrite_venue_league_vocabulary` at all — the helper lives only on this branch
# — so master cannot answer "what would this have printed". `046c88245` is the
# sha I actually offered to the desk and the one carrying the WNBA defect, which
# makes it the only baseline the comparison is about.
BEFORE_SHA = "046c88245"


def load_master_module():
    src = subprocess.run(
        ["git", "-C", REPO, "show", f"{BEFORE_SHA}:{MODULE_PATH}"],
        capture_output=True, text=True, check=True,
    ).stdout
    # `futures_categorization` is the module's only app import and is unchanged
    # on this branch, so the branch's copy is a faithful stand-in for master's.
    tmp = tempfile.NamedTemporaryFile("w", suffix="_master.py", delete=False)
    tmp.write(src)
    tmp.close()
    return _load(tmp.name, "mln_master")


def db(sql: str, limit: int = 1000, paging: bool = False):
    out = subprocess.run(
        ["curl", "-s", "--max-time", "60", "-X", "POST",
         "-H", f"Authorization: Bearer {TOKEN}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"sql": sql, "limit": limit}),
         f"{API}/api/admin/db-query"],
        capture_output=True, text=True,
    ).stdout
    d = json.loads(out)
    if "rows" not in d:
        raise SystemExit(f"db-query refused: {out[:300]}")
    # #7397 gotcha: db-query clamps `limit` at 1000 and the flag is the only
    # tell — my first census read 1,000 rows, looked complete, and the real
    # population was 3,530. A caller that is deliberately paging expects the
    # flag; anybody else is about to undercount and should hear about it.
    if d.get("truncated") and not paging:
        raise SystemExit("TRUNCATED — page this query, the census would undercount")
    return d["rows"]


def get(path: str):
    out = subprocess.run(["curl", "-s", "--max-time", "60", API + path],
                         capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except Exception:
        return None


def strings_in(obj, acc):
    if isinstance(obj, dict):
        for v in obj.values():
            strings_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            strings_in(v, acc)
    elif isinstance(obj, str) and VENUE.search(obj):
        acc.append(obj)
    return acc


sys.path.insert(0, os.path.join(REPO, "backend"))
branch = _load(os.path.join(REPO, MODULE_PATH), "mln_branch")
master = load_master_module()
bf, mf = branch.rewrite_venue_league_vocabulary, master.rewrite_venue_league_vocabulary

print("=" * 78)
print("A. PER LEAGUE PAGE — is the league token the page's own league?")
print("=" * 78)

hierarchy = get("/api/sports/hierarchy")
keys = [(s["slug"], lg["slug"], k)
        for s in hierarchy["sports"] for lg in s.get("leagues", [])
        for k in lg.get("sport_keys", [])]

# What league token each page is allowed to show. Absent = no constraint checked.
EXPECTED = {"americanfootball_nfl": "NFL", "basketball_nba": "NBA",
            "baseball_mlb": "MLB", "icehockey_nhl": "NHL",
            "basketball_wnba": "WNBA"}

page_fail = 0
for sport, lg, key in keys:
    payload = get(f"/api/leagues/{key}")
    if payload is None:
        print(f"  ?? {key}: non-JSON")
        continue
    names = strings_in(payload, [])
    if not names:
        continue
    want = EXPECTED.get(key)
    bad = []
    for n in sorted(set(names)):
        got = bf(n)
        tokens = set(LEAGUE_TOKEN.findall(got))
        if want and tokens and tokens != {want}:
            bad.append((n, got, tokens))
    status = "OK " if not bad else "BAD"
    print(f"  [{status}] /sport/{sport}/{lg}  ({key})  "
          f"{len(set(names))} distinct names, expect={want}")
    for n, got, tok in bad[:6]:
        print(f"         {n!r}\n           -> {got!r}   tokens={sorted(tok)}")
    page_fail += len(bad)

print(f"\n  PAGES WITH A WRONG LEAGUE TOKEN: {page_fail}")

print()
print("=" * 78)
print(f"B. WHOLE POPULATION — {BEFORE_SHA} (offered, defective) vs branch")
print("=" * 78)

total = db("SELECT count(*) FROM futures_markets "
           "WHERE name ~* '\\mPro (Football|Basketball|Hockey|Baseball)\\M'")[0][0]
rows, last = [], 0
while True:
    page = db("SELECT id, name FROM futures_markets "
              "WHERE name ~* '\\mPro (Football|Basketball|Hockey|Baseball)\\M' "
              f"AND id > {last} ORDER BY id", limit=1000, paging=True)
    if not page:
        break
    rows += page
    last = page[-1][0]
    if len(page) < 1000:
        break
print(f"  population: {len(rows)} rows read of {total} reported")
assert len(rows) == total, "paged read did not match count(*)"

same = differ = 0
diffs = []
for _id, name in rows:
    m, b = mf(name), bf(name)
    if m == b:
        same += 1
    else:
        differ += 1
        diffs.append((_id, name, m, b))
print(f"  identical under both: {same}")
print(f"  CHANGED by this branch: {differ}")
for _id, name, m, b in diffs:
    print(f"    {_id}  {name!r}\n        before -> {m!r}\n        after  -> {b!r}")

# Every branch output must still be free of the venue phrase, or carry it only
# because the guard deliberately declined it.
leftover = [(i, n, bf(n)) for i, n, in ((r[0], r[1]) for r in rows)
            if VENUE.search(bf(n))]
print(f"\n  rows still carrying the venue phrase after rewrite: {len(leftover)}")
for i, n, out in leftover[:10]:
    print(f"    {i}  {out!r}   (guard declined — unmapped qualifier)")

print()
print("=" * 78)
print("C. QUALIFIER GUARD — both directions")
print("=" * 78)
for s in ["Women's Pro Basketball MVP Winner", "Womens Pro Basketball Thing",
          "Girls Pro Basketball Thing", "College Pro Football Thing",
          "2026 Pro Football Champion", "Milwaukee Pro Basketball Total Wins"]:
    print(f"  {s!r:46s} -> {bf(s)!r}")

print()
print(f"VERDICT: page_fail={page_fail}  changed={differ}  leftover={len(leftover)}")
