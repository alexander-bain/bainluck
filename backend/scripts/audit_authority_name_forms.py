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
answers already judged are pinned in
:data:`~app.utils.authority_name_forms.EXPECTED_COLLISIONS`, which this script
and ``tests/test_authority_name_forms.py`` share rather than fork, so a future
loosening has to survive them and the two can never disagree about what is
already known.

**The exit code reports NEW collisions, not collisions.** It used to return
``1`` whenever any collision existed at all, and 50 of them are pinned and
benign — so a perfectly healthy corpus exited ``1``, every run, and the exit
code carried no signal for anything automated to read. Now ``0`` means "the
sweep found nothing that is not already judged".

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

``0`` swept, every collision found is pinned and unchanged · ``1`` a NEW
collision, or a pinned one that now reaches a name it did not before · ``2`` no
``ADMIN_TOKEN``.

A pinned collision that has VANISHED is reported and does not fail: the corpus
is live, and a club we no longer hold cannot collide with anything.
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

from app.utils.authority_name_forms import (  # noqa: E402
    EXPECTED_COLLISIONS,
    canonical_forms,
    synonym_forms,
)
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


def collisions(names: set[str], sport: str) -> list[tuple[str, list[str]]]:
    """Buckets where a canonical form is reached by two names that differ.

    "Differ" means their *base* normalized forms differ — two spellings that
    already agreed before this module existed are not a new collision, they are
    the same string.

    Sweeps the synonym table too (#2823), which is why it needs the sport: an
    entry is a hand-written claim that two spellings are one club, and a
    hand-written claim is exactly the kind this sweep exists to check. Every
    alias that fires here shows up as a collision to be judged and pinned,
    which is the table documenting its own effect.
    """
    buckets: dict[str, set[str]] = defaultdict(set)
    for name in names:
        base = normalize_team_name_for_matching(name)
        if not base:
            continue
        for form in canonical_forms(name) | synonym_forms(name, sport):
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
    new: list[tuple[str, str, list[str]]] = []
    widened: list[tuple[str, str, list[str]]] = []
    seen_pinned: set[str] = set()

    for sport in sorted(corpus):
        hits = collisions(corpus[sport], sport)
        if not hits:
            continue
        total_hits += len(hits)
        print(f"\n{sport} ({len(corpus[sport])} names) — {len(hits)} collision(s):")
        for form, bases in hits:
            if form not in EXPECTED_COLLISIONS:
                mark = "NEW"
                new.append((sport, form, bases))
            elif set(bases) != EXPECTED_COLLISIONS[form]:
                mark = "WIDENED"
                widened.append((sport, form, bases))
                seen_pinned.add(form)
            else:
                mark = "known"
                seen_pinned.add(form)
            print(f"  [{mark:7}] {form!r}  <-  {bases}")

    print(
        f"\nswept {total_names} distinct team names across {len(corpus)} sports; "
        f"{total_hits} canonical form(s) reached by more than one name "
        f"({len(new)} new, {len(widened)} widened, "
        f"{total_hits - len(new) - len(widened)} pinned and unchanged)"
    )

    # A pinned form the sweep no longer reaches is reported, not failed: the
    # corpus is live, and a club we stopped holding cannot collide. Only
    # meaningful on a full sweep — a --sport slice cannot see the other sports'
    # pinned forms, so it would report all of them as vanished.
    if not args.sport:
        vanished = sorted(set(EXPECTED_COLLISIONS) - seen_pinned)
        if vanished:
            print(
                f"\n{len(vanished)} pinned collision(s) no longer present "
                f"(not a failure; prune when it settles): {vanished}"
            )

    if new:
        print(
            f"\nFAIL: {len(new)} collision(s) nobody has judged. Each is either two "
            "spellings of one team — judge it and add it to EXPECTED_COLLISIONS in "
            "app/utils/authority_name_forms.py — or the widening fusing two teams."
        )
    if widened:
        print(
            f"\nFAIL: {len(widened)} pinned collision(s) now reach a name they did "
            "not when they were judged. The judgment covered the old set only."
        )
    return 1 if (new or widened) else 0


if __name__ == "__main__":
    sys.exit(main())
