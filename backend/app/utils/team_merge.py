"""#1204 — systemic team-identity dedup/merge (the 41-pair bare-location class).

THE PROBLEM (r257/r258): odds/schedule sources create a *bare-location* duplicate
of a franchise — "Boston" (NHL) alongside "Boston Bruins", "Philadelphia" (MLS)
alongside "Philadelphia Union", "Fremantle" alongside "Fremantle Dockers". The two
rows share the same ``(sport_id, espn_id)`` but the bare row carries a stub name,
its own slug, ZERO ``team_identity_mapping`` rows, and only a stray event or two.
Public slugs can resolve to the STALE stub → stale team pages and 0/5 prop-family
yield on marquee teams. This module folds each stub into the canonical franchise.

THE SAFETY GATE (this is the whole point — a naive ``(sport_id, espn_id)`` merge is
CATASTROPHIC): ``espn_id`` is NOT unique across distinct NCAA schools — espn_id 108
maps to BOTH "Ohio State Buckeyes" and "Kent State" in baseball_ncaa; espn_id 110
to "Oklahoma State Cowboys" and "Fresno State". A blind espn_id merge would fuse
Kent State into Ohio State. So a cluster is merged ONLY when it is
**prefix-coherent**: every member's normalized name is a token-prefix of the
cluster's longest name (Boston ⊂ Boston Bruins ✓; Kent State ⊄ Ohio State ✗ →
whole cluster SKIPPED). And within a coherent cluster we fold ONLY genuine
**stubs**: a non-canonical member with a token-prefix name, ZERO identity mappings,
ZERO recent events, and few total events. The canonical is the member carrying the
most CURRENT events (r258's rule). Anything ambiguous is left untouched and
reported for manual review — precision over recall.

Redirect, not 404 (bookmarked slugs survive): the stub's slug + name fold into
``team_identity_mapping`` (source='legacy_slug'), which the team route consults on
a slug miss; the stub's name folds into the canonical's ``alternate_names`` (search
benefit). Then the stub row is deleted so its slug frees for the canonical's data.

Used by both ``scripts/merge_team_identities.py`` (CLI, dry-run default) and
POST /api/admin/repairs/team-identity-merge (Queue #247 Item 5).
"""
from __future__ import annotations

import re
import unicodedata
from types import SimpleNamespace

from sqlalchemy import text

# Default "current events" window — a team with an event inside this window is
# live/in-season and must win the canonical tiebreak.
_RECENT_DAYS = 60
# A foldable stub carries no more than this many total events (a real team has a
# full schedule; a bare-location artifact has a stray one or two).
_STUB_MAX_EVENTS = 5


def _normalize(name: str | None) -> str:
    """Accent-fold + lowercase + collapse whitespace ("Montréal" == "montreal")."""
    if not name:
        return ""
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", folded.strip().lower())


def _tokens(name: str | None) -> list[str]:
    n = _normalize(name)
    return n.split(" ") if n else []


def _is_token_prefix(short: str, long: str) -> bool:
    """True if ``short``'s tokens are a (proper or equal) leading run of ``long``'s.
    "boston" ⊂ "boston bruins" ✓; "kent state" ⊄ "ohio state buckeyes" ✗."""
    st, lt = _tokens(short), _tokens(long)
    if not st or not lt or len(st) > len(lt):
        return False
    return lt[: len(st)] == st


# Candidate dup teams — NO per-team event counts here (those are batched below; a
# correlated OR count-subquery per candidate seq-scans the events table hundreds of
# times and blows the 30s HTTP timeout — r259's dry-run 503).
_CANDIDATE_TEAMS_SQL = """
    WITH dup_espn AS (
        SELECT sport_id, espn_id
        FROM teams
        WHERE espn_id IS NOT NULL AND espn_id NOT IN ('', '0')
        GROUP BY sport_id, espn_id HAVING count(*) > 1
    ),
    dup_name AS (
        SELECT sport_id, lower(trim(name)) AS nm
        FROM teams
        GROUP BY sport_id, lower(trim(name)) HAVING count(*) > 1
    ),
    cand AS (
        SELECT t.id
        FROM teams t
        WHERE EXISTS (SELECT 1 FROM dup_espn d
                       WHERE d.sport_id = t.sport_id AND d.espn_id = t.espn_id)
           OR EXISTS (SELECT 1 FROM dup_name n
                       WHERE n.sport_id = t.sport_id AND n.nm = lower(trim(t.name)))
    )
    SELECT t.id, t.sport_id, s.key AS sport_key, t.name, t.slug, t.espn_id,
           t.alternate_names,
           (SELECT count(*) FROM team_identity_mapping m WHERE m.team_id = t.id) AS mapping_count
    FROM teams t
    JOIN cand c ON c.id = t.id
    LEFT JOIN sports s ON s.id = t.sport_id
    ORDER BY t.sport_id, t.espn_id, t.name
"""

# Batched event counts for a specific set of candidate team ids — TWO index scans
# total (home + away) aggregated once, instead of a scan-per-team. `recent` uses a
# FILTER on the same pass.
_EVENT_COUNTS_SQL = """
    SELECT team_id,
           count(*) AS total_events,
           count(*) FILTER (
               WHERE commence_time > now() - (:recent_days || ' days')::interval
           ) AS recent_events
    FROM (
        SELECT home_team_id AS team_id, commence_time FROM events
          WHERE home_team_id = ANY(:ids)
        UNION ALL
        SELECT away_team_id AS team_id, commence_time FROM events
          WHERE away_team_id = ANY(:ids)
    ) x
    GROUP BY team_id
"""


def _cluster_key(row) -> tuple:
    """Group rows into clusters. Same sport AND (same non-sentinel espn_id OR same
    normalized name). We key by (sport_id, espn_id) when espn_id is present, else by
    (sport_id, normalized-name) — union-find over both keys handles the mixed case."""
    return row


async def _load_candidate_rows(session, recent_days: int) -> list:
    """Load dup-cluster candidate teams with batched event counts attached."""
    cand = (await session.execute(text(_CANDIDATE_TEAMS_SQL))).all()
    ids = [r.id for r in cand]
    counts: dict[int, tuple[int, int]] = {}
    if ids:
        for row in (await session.execute(
            text(_EVENT_COUNTS_SQL), {"ids": ids, "recent_days": str(recent_days)}
        )).all():
            counts[row.team_id] = (row.total_events, row.recent_events)
    rows = []
    for r in cand:
        total, recent = counts.get(r.id, (0, 0))
        rows.append(SimpleNamespace(
            id=r.id, sport_id=r.sport_id, sport_key=r.sport_key, name=r.name,
            slug=r.slug, espn_id=r.espn_id, alternate_names=r.alternate_names,
            mapping_count=r.mapping_count, total_events=total, recent_events=recent,
        ))
    return rows


def _build_clusters(rows) -> list[list]:
    """Union-find clusters within a sport by shared espn_id OR shared normalized
    name (mirrors routes/user.py:_query_team_futures's runtime collapse)."""
    parent: dict[int, int] = {r.id: r.id for r in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_id = {r.id: r for r in rows}
    lst = list(rows)
    for i in range(len(lst)):
        for j in range(i + 1, len(lst)):
            a, b = lst[i], lst[j]
            if a.sport_id != b.sport_id:
                continue
            same_espn = (
                a.espn_id and b.espn_id
                and a.espn_id not in ("", "0")
                and str(a.espn_id) == str(b.espn_id)
            )
            same_name = _normalize(a.name) and _normalize(a.name) == _normalize(b.name)
            if same_espn or same_name:
                union(a.id, b.id)

    clusters: dict[int, list] = {}
    for r in rows:
        clusters.setdefault(find(r.id), []).append(by_id[r.id])
    return list(clusters.values())


def _plan_cluster(members: list) -> dict:
    """Classify a cluster: pick canonical + list foldable stubs, or reject.

    Returns {status, canonical, folds, reason}. status ∈
    {planned, skip_incoherent, skip_no_stub, skip_no_current}."""
    # Canonical = most current events, then most total, then most mappings, then
    # longest name (the r258 "carries current events" rule).
    canonical = max(
        members,
        key=lambda m: (m.recent_events, m.total_events, m.mapping_count, len(m.name or "")),
    )
    root_name = max((m.name for m in members), key=lambda n: len(n or ""))

    # Prefix-coherence: EVERY member must be a token-prefix of the longest name.
    # A single incoherent member (Kent State in an Ohio-State cluster) poisons the
    # whole cluster → skip it entirely.
    for m in members:
        if not _is_token_prefix(m.name, root_name):
            return {"status": "skip_incoherent", "canonical": canonical, "folds": [],
                    "reason": f"'{m.name}' is not a token-prefix of '{root_name}'"}

    folds = []
    for m in members:
        if m.id == canonical.id:
            continue
        # A foldable stub: token-prefix (guaranteed by coherence), no identity of
        # its own (zero mappings), not currently live (zero recent events), thin
        # schedule. Anything else is a real team — do NOT fold it.
        is_stub = (
            m.mapping_count == 0
            and m.recent_events == 0
            and m.total_events <= _STUB_MAX_EVENTS
        )
        if is_stub:
            folds.append(m)
        else:
            return {"status": "skip_no_stub", "canonical": canonical, "folds": [],
                    "reason": f"non-canonical '{m.name}' (id={m.id}) is not a clean stub "
                              f"(mappings={m.mapping_count}, recent={m.recent_events}, "
                              f"total={m.total_events})"}

    if not folds:
        return {"status": "skip_no_stub", "canonical": canonical, "folds": [],
                "reason": "no foldable stub"}
    if canonical.recent_events == 0 and canonical.total_events == 0:
        return {"status": "skip_no_current", "canonical": canonical, "folds": [],
                "reason": "canonical carries no events either — ambiguous, needs review"}
    return {"status": "planned", "canonical": canonical, "folds": folds, "reason": ""}


# FK re-point statements (source stub id → canonical target id). EVERY FK that
# references teams.id MUST re-point here before the stub row is deleted, or the
# delete either orphans rows or (for ondelete=SET NULL/CASCADE columns) silently
# detaches/removes them. The schema-derived guard test
# tests/test_team_merge.py::TestFkCoverage enforces this: add a new teams FK to
# the ORM and the test fails until it is covered here.
_FK_STATEMENTS = [
    "UPDATE events SET home_team_id = :tgt WHERE home_team_id = :src",
    "UPDATE events SET away_team_id = :tgt WHERE away_team_id = :src",
    "UPDATE futures_outcomes SET team_id = :tgt WHERE team_id = :src",
    "UPDATE tournament_odds SET team_id = :tgt WHERE team_id = :src",
    # entities.source_team_id is the identity-registry bridge (A1). It is
    # ondelete=SET NULL, so deleting the stub team WITHOUT re-pointing first
    # silently NULLs the bridge and detaches the folded team from its registry
    # entity (Codex C1). Collision semantics: if the canonical team is ALREADY
    # bridged to an entity, do NOT create a second bridge — leave the stub's
    # now-redundant entity to SET-NULL on delete (canonical's bridge wins,
    # exactly one entity per team). Only re-point when canonical has no bridge.
    ("UPDATE entities SET source_team_id = :tgt WHERE source_team_id = :src "
     "AND NOT EXISTS (SELECT 1 FROM entities e2 WHERE e2.source_team_id = :tgt)"),
    # user_favorites is UNIQUE(user_id, team_id, relation_type). The collision
    # guard MUST include relation_type — otherwise a user who favorited BOTH the
    # stub and the canonical under DIFFERENT relation types (e.g. 'favorite' on
    # the stub, 'following' on the canonical) has the stub row skipped by the
    # NOT EXISTS and then DELETEd → silent loss of a distinct preference (Codex
    # C1). Matching relation_type re-points each relation independently.
    ("UPDATE user_favorites uf SET team_id = :tgt WHERE team_id = :src "
     "AND NOT EXISTS (SELECT 1 FROM user_favorites u2 "
     "WHERE u2.user_id = uf.user_id AND u2.team_id = :tgt "
     "AND u2.relation_type = uf.relation_type)"),
    "DELETE FROM user_favorites WHERE team_id = :src",
    "UPDATE team_identity_mapping SET team_id = :tgt WHERE team_id = :src",
]


def _merge_aliases(existing, extra: list[str]) -> list[str]:
    out = list(existing or [])
    seen = {str(e).strip().lower() for e in out}
    for a in extra:
        if a and a.strip().lower() not in seen:
            out.append(a)
            seen.add(a.strip().lower())
    return out


async def _apply_merge(session, canonical, stub, sport_key) -> dict:
    """Re-point every team FK from ``stub`` → ``canonical``, fold the stub's name
    into alternate_names + register its legacy slug for redirect, then delete the
    stub. Caller commits."""
    s = session
    counts = {}
    for stmt in _FK_STATEMENTS:
        table = stmt.split()[1]
        res = await s.execute(text(stmt), {"src": stub.id, "tgt": canonical.id})
        counts[table] = counts.get(table, 0) + (res.rowcount or 0)

    # Fold the stub's display name(s) into the canonical's alternate_names (search).
    new_aliases = _merge_aliases(
        canonical.alternate_names,
        [stub.name] + list(stub.alternate_names or []),
    )
    await s.execute(
        text("UPDATE teams SET alternate_names = CAST(:v AS jsonb) WHERE id = :i"),
        {"v": __import__("json").dumps(new_aliases), "i": canonical.id},
    )
    canonical.alternate_names = new_aliases  # keep in-memory row consistent

    # Register the legacy slug + name so /api/teams/{old-slug} redirects (not 404).
    if stub.slug:
        await s.execute(
            text("INSERT INTO team_identity_mapping "
                 "(team_id, source, source_id, source_name, sport_key, created_at, updated_at) "
                 "VALUES (:tid, 'legacy_slug', :sid, :nm, :sk, now(), now())"),
            {"tid": canonical.id, "sid": stub.slug, "nm": stub.name, "sk": sport_key},
        )

    # Retire the stub row (its slug now redirects via the legacy_slug mapping).
    await s.execute(text("DELETE FROM teams WHERE id = :i"), {"i": stub.id})

    return {
        "stub_id": stub.id, "stub_name": stub.name, "stub_slug": stub.slug,
        "canonical_id": canonical.id, "canonical_name": canonical.name,
        "fk_repointed": counts,
    }


# Per-call cluster cap on apply. A single big transaction re-pointing every stub's
# events + a full-table mapping dedup exceeds the 30s HTTP wall AND lock-waits
# against the events-polling task (the r259 apply 503). We commit PER CLUSTER and
# cap each call — idempotent + resumable: merged stubs are deleted, so the next
# call re-plans only what remains. Call until pairs_remaining hits 0.
_APPLY_CLUSTER_LIMIT = 25


async def run_team_identity_merge(
    session, apply: bool, recent_days: int = _RECENT_DAYS, limit: int = _APPLY_CLUSTER_LIMIT
) -> dict:
    """Find safe bare-location dup clusters and fold stubs into their canonical.
    On apply, merges up to ``limit`` clusters, COMMITTING AFTER EACH so a timeout
    leaves consistent, resumable progress. Returns a per-pair evidence log +
    census (incl. ``pairs_remaining`` — call again until it is 0)."""
    s = session
    rows = await _load_candidate_rows(s, recent_days)
    clusters = _build_clusters(rows)

    planned, skipped = [], []
    for members in clusters:
        if len(members) < 2:
            continue
        plan = _plan_cluster(members)
        entry = {
            "sport_key": members[0].sport_key,
            "espn_id": members[0].espn_id,
            "members": [{"id": m.id, "name": m.name, "slug": m.slug,
                         "recent_events": m.recent_events, "total_events": m.total_events,
                         "mappings": m.mapping_count} for m in members],
            "reason": plan["reason"],
        }
        if plan["status"] == "planned":
            entry["canonical"] = {"id": plan["canonical"].id, "name": plan["canonical"].name}
            entry["folds"] = [{"id": m.id, "name": m.name, "slug": m.slug} for m in plan["folds"]]
            planned.append((plan, entry))
        else:
            entry["status"] = plan["status"]
            skipped.append(entry)

    merges = []
    pairs_merged = 0
    clusters_merged = 0
    if apply and planned:
        for plan, entry in planned[: (limit or len(planned))]:
            canonical = plan["canonical"]
            try:
                pair_evidence = []
                for stub in plan["folds"]:
                    pair_evidence.append(
                        await _apply_merge(s, canonical, stub, entry["sport_key"])
                    )
                # Dedup mapping rows for THIS canonical only (scoped + cheap), then
                # commit this cluster before moving on (per-cluster durability).
                await s.execute(text(
                    "DELETE FROM team_identity_mapping a USING team_identity_mapping b "
                    "WHERE a.id > b.id AND a.team_id = b.team_id AND a.source = b.source "
                    "AND a.source_id IS NOT DISTINCT FROM b.source_id "
                    "AND a.team_id = :tid"
                ), {"tid": canonical.id})
                await s.commit()
                pairs_merged += len(pair_evidence)
                clusters_merged += 1
                entry["merged"] = pair_evidence
                merges.append(entry)
            except Exception as e:
                await s.rollback()
                entry["error"] = f"cluster merge rolled back: {e}"
                merges.append(entry)

    pairs_planned = sum(len(p["folds"]) for p, _ in planned)
    return {
        "repair": "team-identity-merge",
        "applied": bool(apply),
        "recent_days": recent_days,
        "clusters_examined": sum(1 for c in clusters if len(c) >= 2),
        "clusters_planned": len(planned),
        "pairs_planned": pairs_planned,
        "pairs_merged": pairs_merged,
        "clusters_merged": clusters_merged,
        "pairs_remaining": pairs_planned - pairs_merged,
        "clusters_skipped": len(skipped),
        "planned_detail": [e for _, e in planned] if not apply else merges,
        "skipped_detail": skipped,
    }


async def count_unresolved_team_dupes(session, recent_days: int = _RECENT_DAYS) -> int:
    """Audit hook (#1204 'the class files itself'): how many SAFE, still-mergeable
    bare-location stub clusters remain. Should be 0 after a clean apply. A guard
    test + the merge sentinel assert this stays 0."""
    rows = await _load_candidate_rows(session, recent_days)
    n = 0
    for members in _build_clusters(rows):
        if len(members) >= 2 and _plan_cluster(members)["status"] == "planned":
            n += 1
    return n
