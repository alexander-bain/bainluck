#!/usr/bin/env python3
"""Does the widened identity rule fuse any two real teams? #2792. Read-only.

``app/utils/authority_name_forms`` widens what counts as the same team name.
The cases that motivated a widening can never test it — you already know their
answers. **The test is the whole entity field**: every distinct team name we
hold, per sport, reduced through :func:`canonical_forms`, with every collision
between two DIFFERENT names reported.

That method is not general caution; it is what caught a one-letter token acting
as a wildcard in the US Open pairing check (378 players, 71k pairs, one real
collision). Here it is cheaper than pairwise: names are bucketed BY their
canonical forms, so a collision is a bucket holding two names that did not
already agree. O(n), not O(n²).

A collision is not automatically a bug — ``Hawaii``/``Hawai'i`` colliding is the
point. It is a bug when the two names are different TEAMS. The script cannot
know which, so it prints them all and the judgment stays with a person; the
answers are then pinned in ``tests/test_authority_name_forms.py`` so a future
loosening has to survive them.

Reads through ``/api/admin/db-query`` in hash-modulus chunks (that endpoint caps
at 1,000 rows and the corpus is ~24,000). Writes nothing.

    source ~/.claude/.env
    python3 scripts/audit_authority_name_forms.py
    python3 scripts/audit_authority_name_forms.py --sport americanfootball_ncaaf
    python3 scripts/audit_authority_name_forms.py --dump-corpus /tmp/corpus.json

═══ WHAT IT MEASURED THE DAY IT WAS WRITTEN (2026-09-03) ═══

See the docstring of ``tests/test_authority_name_forms.py`` — the verdicts are
pinned there rather than here, because a number in a script's docstring is a
claim nobody re-checks and a number in a test is one CI re-checks every push.

═══ EXIT CODES ═══

``0`` swept, no collision outside the pinned allowlist · ``1`` a new collision
between two different names · ``2`` no ``ADMIN_TOKEN``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.authority_name_forms import canonical_forms  # noqa: E402
from app.utils.name_normalization import normalize_team_name_for_matching  # noqa: E402
from app.utils.sport_keys import SPORT_LEAGUE_MAP  # noqa: E402

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")
TOKEN = os.environ.get("ADMIN_TOKEN", "")

#: ``/api/admin/db-query`` caps a result at 1,000 rows and reports ``truncated``
#: rather than paging, so the corpus is read in hash-modulus slices. Chosen so
#: each slice lands comfortably under the cap for the largest sport.
CHUNKS = 48


def db_query(sql: str, limit: int = 1000) -> list[dict]:
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = Request(
        f"{API}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=90) as resp:
            payload = json.load(resp)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"db-query {exc.code}: {detail}") from None
    if payload.get("truncated"):
        raise RuntimeError(
            "db-query truncated a chunk — raise CHUNKS. A silently short corpus "
            "is a sweep that proves nothing."
        )
    return [dict(zip(payload["columns"], row)) for row in payload["rows"]]


def load_corpus(sport: str | None) -> dict[str, set[str]]:
    """``{sport_key: {every distinct team name we hold}}``, ESPN-mapped sports.

    Scoped to ``SPORT_LEAGUE_MAP`` because those are the sports the rule can be
    asked about at all; a collision in a sport the authority rails never reach
    is not a finding about this rule.
    """
    keys = [sport] if sport else sorted(SPORT_LEAGUE_MAP)
    key_list = ", ".join(f"'{k}'" for k in keys)
    corpus: dict[str, set[str]] = defaultdict(set)
    for chunk in range(CHUNKS):
        rows = db_query(f"""
            SELECT DISTINCT s.key AS sport, n.nm AS name
            FROM events e
            JOIN sports s ON s.id = e.sport_id
            CROSS JOIN LATERAL (VALUES (e.home_team_name), (e.away_team_name)) AS n(nm)
            WHERE n.nm IS NOT NULL AND n.nm <> ''
              AND s.key IN ({key_list})
              AND abs(hashtext(s.key || '|' || n.nm)) % {CHUNKS} = {chunk}
            """)
        for row in rows:
            corpus[row["sport"]].add(row["name"])
    return dict(corpus)


def collisions(names: set[str]) -> list[tuple[str, list[str]]]:
    """Buckets where a canonical form is reached by two names that differ.

    "Differ" means their *base* normalized forms differ — two spellings that
    already agreed before this module existed are not a new collision, they are
    the same string.
    """
    buckets: dict[str, set[str]] = defaultdict(set)
    for name in names:
        base = normalize_team_name_for_matching(name)
        if not base:
            continue
        for form in canonical_forms(name):
            buckets[form].add(base)
    found = [(form, sorted(bases)) for form, bases in buckets.items() if len(bases) > 1]
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sport", default=None)
    parser.add_argument(
        "--dump-corpus", default=None, help="Write the corpus to a JSON file"
    )
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    corpus = load_corpus(args.sport)
    if args.dump_corpus:
        with open(args.dump_corpus, "w") as handle:
            json.dump(
                {k: sorted(v) for k, v in sorted(corpus.items())}, handle, indent=1
            )

    total_names = sum(len(v) for v in corpus.values())
    total_hits = 0
    for sport in sorted(corpus):
        hits = collisions(corpus[sport])
        if not hits:
            continue
        total_hits += len(hits)
        print(f"\n{sport} ({len(corpus[sport])} names) — {len(hits)} collision(s):")
        for form, bases in hits:
            print(f"  {form!r}  <-  {bases}")

    print(
        f"\nswept {total_names} distinct team names across {len(corpus)} sports; "
        f"{total_hits} canonical form(s) reached by more than one name"
    )
    return 1 if total_hits else 0


if __name__ == "__main__":
    sys.exit(main())
