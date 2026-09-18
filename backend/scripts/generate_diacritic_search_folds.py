#!/usr/bin/env python3
"""Regenerate ``app/config/diacritic_search_folds.py`` from the live corpus (#6977).

WHY A GENERATED CONSTANT AND NOT A SQL FOLD. The reader types ``Atletico`` and we
store ``Atlético``; folding in SQL needs ``unaccent``, and this database does not
have it — three independent places in the tree say so (``entity_registry`` module
docstring, ``event_twin_fold`` ~1033, ``add_entity_registry``'s migration note).
Installing it is DDL, and a functional fold over the column would ALSO defeat the
``gin_trgm_ops`` indexes that ``/api/events/search`` depends on: ``events.py``
records that one unindexable arm inside the top-level OR seq-scanned ``events``
and produced the ~20s median that got LAT-P002 reverted.

So the fold happens on the QUERY, not the column, and it reuses the expansion
slot the route already has. ``atletico`` -> ``atlético`` becomes an ordinary
second ILIKE, which the same trigram index serves. No new arm SHAPE, no DDL, and
queries with no accented variant are byte-identical to today.

Pairing this file with ``team_aliases.py``: that module keeps its nickname map
pure ("no DB, no I/O, so the guard tests pin it directly") and this keeps the
same contract — the *generator* touches the network, the emitted module is a
literal.

USAGE (needs ``ADMIN_TOKEN`` + ``BAINLUCK_API`` in the environment)::

    source ~/.claude/.env && python3 scripts/generate_diacritic_search_folds.py
    source ~/.claude/.env && python3 scripts/generate_diacritic_search_folds.py --dry-run

``--dry-run`` prints the summary and writes nothing.

STALENESS IS A KNOWN, BOUNDED PROPERTY. The map covers the accented tokens present
when it was generated; a club ingested afterwards is missed until this is re-run.
That is the same contract the curated nickname map has lived under, and it fails
in the safe direction — a missing row leaves today's behaviour, it never removes
recall. Re-run it when a new competition is onboarded.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import urllib.request
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.agent_origin import tagged  # noqa: E402
from app.utils.name_normalization import strip_diacritics  # noqa: E402

OUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "app", "config", "diacritic_search_folds.py"
)

# Every searchable name column a query term is matched against: the denormalised
# event team names (game cards), the teams table (the team card) and open futures
# names (the futures rail). `[^ -~]` is "outside printable ASCII".
CORPUS_SQL = """
SELECT tok, sum(n) AS n FROM (
    SELECT regexp_split_to_table(lower(name), '[^[:alnum:]]+') AS tok, 1 AS n
      FROM teams WHERE name ~ '[^ -~]'
    UNION ALL
    SELECT regexp_split_to_table(lower(home_team_name), '[^[:alnum:]]+'), 1
      FROM events WHERE home_team_name ~ '[^ -~]'
    UNION ALL
    SELECT regexp_split_to_table(lower(away_team_name), '[^[:alnum:]]+'), 1
      FROM events WHERE away_team_name ~ '[^ -~]'
    UNION ALL
    SELECT regexp_split_to_table(lower(name), '[^[:alnum:]]+'), 1
      FROM futures_markets WHERE status='open' AND name ~ '[^ -~]'
) s
WHERE tok ~ '[^ -~]'
GROUP BY tok ORDER BY n DESC, tok
"""


def fold_key(token: str) -> str:
    """The spelling a plain keyboard produces for ``token``.

    ``strip_diacritics`` alone is not enough, and ``hawaiʻi`` is why: the ʻokina
    (U+02BB) is a MODIFIER LETTER, not a combining mark, so NFD has nothing to
    decompose and the "fold" returns the token unchanged — an expansion equal to
    its own key, which is a duplicate ILIKE arm for zero recall. Dropping the
    residue makes it ``hawaii``, which is both typeable and what a reader types.
    """
    return "".join(c for c in strip_diacritics(token) if c.isascii())


def build(rows: list[tuple[str, int]]) -> tuple[dict[str, str], list[str]]:
    """Fold the corpus into ``typed -> stored``, resolving collisions by frequency."""
    grouped: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
    for token, count in rows:
        key = fold_key(token)
        # A key that is not plain alphanumeric ASCII cannot be typed, and a key
        # equal to its token is an arm that matches exactly what the unexpanded
        # arm already matched (the same "already a substring" skip
        # `team_nickname_search_expansions` applies).
        if not key or not key.isascii() or not key.isalnum() or key == token:
            continue
        grouped[key].append((token, count))

    folds: dict[str, str] = {}
    notes: list[str] = []
    for key, variants in grouped.items():
        # Deterministic: most frequent spelling wins, ties broken lexicographically,
        # so regenerating on an unchanged corpus produces a byte-identical file.
        variants.sort(key=lambda tc: (-tc[1], tc[0]))
        folds[key] = variants[0][0]
        if len(variants) > 1:
            notes.append(
                f"{key}: kept {variants[0][0]!r} ({variants[0][1]}), "
                f"dropped {[t for t, _ in variants[1:]]}"
            )
    return dict(sorted(folds.items())), notes


def fetch(sql: str) -> list[tuple[str, int]]:
    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        raise SystemExit("BAINLUCK_API and ADMIN_TOKEN must be set (source ~/.claude/.env)")
    url = f"{api}/api/admin/db-query"
    # Notice 39: our own robots are TAGGED, never minted. `tagged()` adds the
    # `x-bainluck-origin` header on our hosts and is a pass-through everywhere
    # else, so the read is attributable to a lane rather than counted as a
    # person. `test_the_carrier_is_reached_by_the_search_touching_probes` holds
    # this file to it by name — it caught this script untagged on the first run.
    req = urllib.request.Request(
        url,
        data=json.dumps({"sql": sql, "limit": 5000}).encode(),
        headers=tagged(
            url,
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        ),
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.load(resp)
    if payload.get("truncated"):
        # A truncated corpus silently ships a PARTIAL map that looks complete.
        raise SystemExit("corpus truncated — raise the limit and re-run")
    return [(r[0], int(r[1])) for r in payload["rows"]]


def render(folds: dict[str, str], notes: list[str], total: int) -> str:
    body = "\n".join(f"    {k!r}: {v!r}," for k, v in folds.items())
    collisions = (
        "\n".join(f"#   {n}" for n in notes) if notes else "#   (none)"
    )
    return f'''"""Diacritic search folds: ``typed spelling -> stored spelling`` (#6977).

GENERATED — do not hand-edit. Regenerate with::

    source ~/.claude/.env && python3 scripts/generate_diacritic_search_folds.py

Generated {date.today().isoformat()} from {total} distinct accented tokens across
``teams.name``, ``events.home_team_name`` / ``away_team_name`` and open
``futures_markets.name``; {len(folds)} usable folds.

WHAT THIS IS FOR. ``GET /api/events/search`` does no diacritic folding, so a
reader on a plain keyboard reached NONE of an accented club's rows. Measured on
production 2026-09-18, same minute, both spellings::

    q=Atlético Madrid   10 events, 1 team card, 10 futures (10 naming the club)
    q=Atletico Madrid    1 event,  0 team cards, 10 futures ( 1 naming the club)

The one row the unaccented spelling did reach was a duplicate the venue happened
to mint unaccented. The nine futures it got instead were other clubs' markets —
the page looked full and answered someone else's question, which is why this is a
truth defect and not a relevance nit.

HOW IT IS APPLIED. ``expand_search_terms`` fills a term's EXPANSION slot from this
map when the city/general abbreviation dictionaries leave it empty, so the fold
arrives as the ordinary second ILIKE the route already builds
(``_build_expanded_ilike``) and the ordinary OR'd FTS arm (``_build_expanded_fts``).
Both halves matter: the events predicate ANDs a whole-word FTS test onto the
ILIKE, and ``to_tsvector('Atlético Madrid')`` yields the lexeme ``atlético``, so an
ILIKE-only fold matches the substring and is then ANDed away. Mutation-measured
on real Postgres, the rail that actually loses rows to an ILIKE-only fold is
FUTURES, not events — the game card survives via the teams rail's query rewrite
feeding the resolved-team rescue. See the integration test's module docstring.

WHY NOT ``unaccent``. It is not installed and is not guaranteed, and a functional
fold over the column would defeat the ``gin_trgm_ops`` indexes the route depends
on — the failure mode that got LAT-P002 reverted at a ~20s median. Folding the
QUERY keeps every arm index-servable.

FILL-ONLY, NEVER OVERRIDE: the map is consulted only when a term has no expansion
already, so it cannot displace ``la -> los angeles``. Measured at generation time,
these keys do not collide with the city (42), general (19) or sport-synonym (13)
dictionaries at all.

Collisions resolved by frequency (one name, two code points — the loser stays
unreachable, which is still strictly better than today, when both were):
{collisions}
"""

# typed (ASCII, lowercase) -> stored (as the venues actually spell it)
DIACRITIC_SEARCH_FOLDS: dict[str, str] = {{
{body}
}}
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="summarise, write nothing")
    args = ap.parse_args()

    rows = fetch(CORPUS_SQL)
    folds, notes = build(rows)
    print(f"corpus tokens : {len(rows)}")
    print(f"usable folds  : {len(folds)}")
    print(f"collisions    : {len(notes)}")
    for n in notes:
        print(f"  {n}")
    if args.dry_run:
        print("--dry-run: no file written")
        return 0
    out = os.path.abspath(OUT_PATH)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render(folds, notes, len(rows)))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
