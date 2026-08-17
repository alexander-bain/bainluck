#!/usr/bin/env python3
"""Derive the widened team_identity_mapping repair plan (#1918, queue 363).

Alex ruled the 158-row mapping repair APPROVED, same pattern as the CREATE rail.
The reason he widened it from queue 362's staged 15 is sound and is worth
restating: repairing 15 rows while 143 keep feeding ``resolve_team`` step 3 --
which filters by sport prefix, NOT by source, and then AUTO-REGISTERS its hit --
is a mop under a second running tap.

DRY RUN ONLY. No apply mode exists in this file.

## What the census found that the approval did not know

The approved number was 158. Re-derived live it is **159** -- and, more
importantly, it is **not one population**. The strict predicate ("source_name IS
another club's canonical name in the same sport") collects three different
defects, and only the first is repairable by re-pointing ``team_id``:

* ``CROSS_CLUB_poison`` -- the real thing. A ``San Diego Padres`` mapping whose
  ``team_id`` points at the Chicago White Sox row (espn 25 vs espn 4). Distinct
  clubs, distinct provider ids, no reading under which the mapping is right.

* ``SAME_CLUB_dup_row`` -- the mapping is CORRECT and the ``teams`` table is
  duplicated: both rows carry the SAME ``espn_id`` (``Jacksonville St Gamecocks``
  and ``Jacksonville State Gamecocks``, both espn 73). Re-pointing these would
  move mappings between two rows for one club -- churn at best, and at worst it
  moves a mapping off the row live events actually bind to. This is #1204's
  duplicate-team class, not #1918's poisoned-index class.

* ``SAME_CLUB_review`` -- the mapping looks right and the collision is with a
  similarly-named row carrying a DIFFERENT provider id (``Florida`` -> ``Florida
  Gators`` espn 75, while another row named ``Florida`` holds espn 296). Which
  row is canonical is a judgement, so these go to review rather than to a plan.

Inside ``SAME_CLUB_dup_row`` sits a fourth thing worth naming separately: a team
row called ``Oregon State`` that carries espn_id 273, which is *Oregon's* id. The
name and the provider id on a single row disagree, so the poison is in ``teams``
itself and no mapping repair can reach it.

Splitting rather than repairing all 159 is the same discipline the population-2
census applied when it refused RE-KEY: an approval given over a number does not
transfer to whatever a later re-derivation finds under that number.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib
import re
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.utils.calibration_phase_ledger import input_fingerprint  # noqa: E402

HANDOFF = pathlib.Path(__file__).resolve().parents[2] / ".claude/handoff"
SCHEMA = "team-identity-mapping-repair-plan/v1"
_NS = "team-identity-mapping-repair-plan"

#: The target sport comes from the MAPPING'S OWN ``sport_key``, never from the
#: sport of the row it currently points at.
#:
#: This distinction is not pedantic — it was a live defect in the first draft of
#: this script, caught by diffing against queue 362's staged 15. Nine of those
#: rows carry ``sport_key = 'baseball_mlb'`` while their POISONED ``team_id``
#: points at a ``baseball_mlb_preseason`` row. Scoping the target to the poisoned
#: row's sport therefore resolved them to preseason club rows: a "repair" that
#: fixed the club and preserved the wrong sport, on all nine, silently and with a
#: clean-looking plan. The poisoned row is the thing under repair; it cannot also
#: be the evidence for what the repair should be.
CENSUS_SQL = """
SELECT m.id, m.source, m.sport_key, m.source_name,
       t.id, t.name, coalesce(t.espn_id,''), t.sport_id,
       o.id, o.name, coalesce(o.espn_id,''),
       m.created_at::date
FROM team_identity_mapping m
JOIN sports s ON s.key = m.sport_key
JOIN teams t ON t.id = m.team_id
JOIN teams o ON o.name = m.source_name AND o.sport_id = s.id AND o.id <> t.id
WHERE s."group" = 'Baseball'
ORDER BY m.id
""".strip()


def _db_query(sql: str, limit: int = 1000):
    req = urllib.request.Request(
        f"{os.environ['BAINLUCK_API']}/api/admin/db-query",
        data=json.dumps({"sql": sql, "limit": limit}).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    if payload.get("truncated"):
        raise SystemExit("db-query TRUNCATED — a plan over a truncated read is a plan nobody chose")
    return payload["rows"]


def _tokens(name: str) -> set[str]:
    name = re.sub(r"\bst\.?\b", "state", name.lower())
    return {w for w in re.sub(r"[^a-z0-9 ]", " ", name).split() if w}


def classify(mapped_name: str, mapped_espn: str, other_espn: str, source_name: str) -> str:
    if mapped_espn and mapped_espn == other_espn:
        return "SAME_CLUB_dup_row"
    a, b = _tokens(mapped_name), _tokens(source_name)
    jaccard = len(a & b) / len(a | b) if (a | b) else 0.0
    return "SAME_CLUB_review" if jaccard >= 0.5 else "CROSS_CLUB_poison"


def main() -> int:
    rows = _db_query(CENSUS_SQL)
    buckets: dict[str, list[dict]] = collections.defaultdict(list)
    seen = collections.Counter(r[0] for r in rows)

    for (
        mid, source, sport_key, source_name,
        mapped_id, mapped_name, mapped_espn, sport_id,
        other_id, other_name, other_espn, created,
    ) in rows:
        klass = classify(mapped_name, mapped_espn, other_espn, source_name)
        if seen[mid] > 1:
            klass = "SAME_CLUB_review"  # >1 candidate target is never automatic
        buckets[klass].append(
            {
                "mapping_id": int(mid),
                "source": source,
                "sport_key": sport_key,
                "source_name": source_name,
                "before": {"team_id": int(mapped_id), "club": mapped_name,
                           "espn_id": mapped_espn, "sport_id": int(sport_id)},
                "after": {"team_id": int(other_id), "club": other_name,
                          "espn_id": other_espn, "sport_id": int(sport_id)},
                "exact_candidates": seen[mid],
                "created": str(created),
                "class": klass,
            }
        )

    plan_rows = sorted(buckets["CROSS_CLUB_poison"], key=lambda r: r["mapping_id"])
    digest = [
        "|".join(
            [
                str(r["mapping_id"]), r["source"], r["sport_key"], r["source_name"],
                str(r["before"]["team_id"]), r["before"]["club"],
                str(r["after"]["team_id"]), r["after"]["club"],
            ]
        )
        for r in plan_rows
    ]
    plan_hash = input_fingerprint(_NS, str(len(digest)), *sorted(digest))

    payload = {
        "schema": SCHEMA,
        "plan_hash": plan_hash,
        "row_count": len(plan_rows),
        "derived": "2026-08-17 queue 363 — DRY RUN, nothing written",
        "resolution_rule": (
            "re-point team_id to the team whose canonical name IS source_name within the "
            "SAME sport_id; exactly one candidate required; classes other than "
            "CROSS_CLUB_poison are excluded from the plan, not repaired"
        ),
        "approved_population": 158,
        "rederived_population": len(rows),
        "split": {k: len(v) for k, v in sorted(buckets.items())},
        "rows": plan_rows,
        "excluded": {
            k: sorted(v, key=lambda r: r["mapping_id"])
            for k, v in buckets.items()
            if k != "CROSS_CLUB_poison"
        },
    }
    out = HANDOFF / "ARTIFACT-Q363-MAPPING-REPAIR-PLAN.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))

    print(f"re-derived       {len(rows)}  (approval said 158)")
    for k, v in sorted(payload["split"].items()):
        print(f"  {k:24} {v}")
    print(f"plan rows        {len(plan_rows)}")
    print(f"plan_hash        {plan_hash}")
    print(f"artifact         {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
