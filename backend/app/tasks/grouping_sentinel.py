"""Grouping sentinel (#12231): a weekly count of market families no grouping covers.

PILLAR: DISCOVER / TRUTH · SHIP: a venue product no grouping covers arrives as a
weekly count on #12221, and from Thu Nov 26 as an issue, not as something Alex
has to notice.

Built to ``docs/design/grouping-primitives.md`` ("Keeping the map current
without a hawk") and part 3 §3 of #12221. Settled by Fable's answers on #12231
(Nov 6, 9:28 PM) and the 9:35 PM addendum:

* **Weekly**, Thursday 16:00 UTC (8 AM PT), background queue, rules only, $0.
* **Report-only** (72-A) until **Thu Nov 26**. The two weeks start at the first
  post on Nov 12. Until then this files nothing: the counts go to #12221 through
  the rail's report path (``sentinel_filing.post_report``), once per week. From
  Nov 26, ``reconcile_issue`` files at most five new issues a run, one per
  uncovered family, and closes a family's issue once something covers it. The
  weekly list already carries each family's fingerprint, so Nov 26 is a switch,
  not a rewrite.

The four counts:

1. **Uncovered families**: five or more open, priced markets alive 48 hours,
   no member covered (72-A). Families are ``grouping_families.build_families``:
   Kalshi series, Polymarket events, and title templates that merge events.
2. **New venue series**: a family first seen in the last seven days with three
   or more open, priced markets, covered by nothing. Neither venue's history can
   be read cheaply (a count over ``futures_markets`` exceeds 10 s), so "first
   seen" is this sentinel's own memory: a Redis sorted set of every family key it
   has seen, scored by when. The first run records the baseline and says
   UNKNOWN; later runs count against it.
3. **New shapes**: the share of open markets stored ``unshaped`` or with
   outcomes ``unknown`` (``backfill_market_shapes``), plus graph members classed
   ``unclassified``.
4. **New measures**: UNKNOWN until something reads the frame (#12249).
   Meanwhile the post counts frames written vs absent (``discover_llm.frame``).

**Covered** means at least one member is:

* in a **definition**: every registered round-up producer (the files in
  ``backend/data/containers/``), evaluated live (never from Discover's 60 s
  cache), with its container's market members and its card's cross-venue pairs;
* in the **graph**: a container that is not cancelled contains it (matcher,
  theme_rule, venue_grouping and human edges);
* in the **Midterms collection**: its manifest and its twin register;
* on an **event page**: a market attached to an event is grouped by that page.

Markets Discover hard-suppresses by ruling (``classify_market_quality`` →
``suppress``: margin, turnout, vote percent, House districts, artist streams,
payrolls) are **excluded**. They are counted, and never reported as uncovered.

Read-only against market data. Writes: one comment a week on #12221, this
sentinel's memory of family keys in Redis and, from Nov 26, alert issues.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping

from app.utils.grouping_families import (
    KIND_KALSHI_SERIES,
    KIND_POLYMARKET_EVENT,
    KIND_TITLE_TEMPLATE,
    Atom,
    Family,
    build_families,
    uncovered_families,
)

logger = logging.getLogger(__name__)

#: Where the weekly count goes (Fable, 9:28 PM: "commenting on #12221").
REPORT_ISSUE = 12221
#: The report's period marker. Deliberately not ``*-fingerprint``, so a report
#: is never read as owning an alert.
REPORT_MARKER = "grouping-sentinel-report"
#: The dedupe declaration a family's issue carries from Nov 26.
FILING_MARKER = "grouping-sentinel-fingerprint"

#: 72-A: five or more open, priced markets alive 48 hours.
MIN_FAMILY_MARKETS = 5
MIN_AGE = timedelta(hours=48)
#: §3 count 2: three or more open markets, first seen in the last seven days.
NEW_SERIES_MIN_OPEN = 3
NEW_SERIES_WINDOW = timedelta(days=7)

#: The two report-only weeks start at the first post (Thu Nov 12), so the first
#: run that may file is Thu Nov 26's (Fable, 9:28 PM). The boundary is the
#: period anchor, so the 16:00 UTC run that day is inside it.
FILING_STARTS_AT = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
#: 72-A: at most five NEW issues a week. A family already filed is commented on
#: and does not count against the five.
MAX_NEW_ISSUES_PER_RUN = 5
#: A Redis key that, when set, pauses filing without a deploy. The weekly count
#: still posts.
FILING_PAUSE_KEY = "grouping_sentinel:filing_paused"
FILING_LABELS = ["alert-intake", "needs-agent", "area:discover", "program:containers", "priority:p2"]

#: The sentinel's week starts Thursday 12:00 UTC, four hours before the
#: scheduled run, not on the ISO Monday. The 9:35 PM addendum asks for a hand
#: run on merge day (Tue Nov 10) AND a first scheduled post on Thu Nov 12, and
#: in ISO weeks those are the same week.
PERIOD_WEEKDAY = 3  # Thursday
PERIOD_HOUR_UTC = 12

#: Families listed by name in the post. The post stays under 60 lines (Fable).
LISTED_FAMILIES = 10

SEEN_KEY = "grouping_sentinel:first_seen:v1"
BASELINE_KEY = "grouping_sentinel:baseline_at:v1"
MEMORY_TTL_SECONDS = 200 * 86400

#: Inner deadline, under the task's soft limit, so the run reaches its own
#: terminal instead of being killed untracked (#966).
DEADLINE_SECONDS = 600.0
PRODUCER_TIMEOUT_SECONDS = 60.0
STATEMENT_TIMEOUT_MS = 120_000

_KIND_LABEL = {
    KIND_KALSHI_SERIES: "Kalshi series",
    KIND_POLYMARKET_EVENT: "Polymarket event",
    KIND_TITLE_TEMPLATE: "title template",
}
_KIND_PLURAL = {
    KIND_KALSHI_SERIES: "Kalshi series",
    KIND_POLYMARKET_EVENT: "Polymarket events",
    KIND_TITLE_TEMPLATE: "title templates",
}


# ---------------------------------------------------------------------------
# The week
# ---------------------------------------------------------------------------
def period_start(now: datetime) -> datetime:
    """The latest Thursday 12:00 UTC at or before ``now``: the sentinel's week."""
    now = now.astimezone(timezone.utc)
    anchor = now.replace(hour=PERIOD_HOUR_UTC, minute=0, second=0, microsecond=0)
    start = anchor - timedelta(days=(anchor.weekday() - PERIOD_WEEKDAY) % 7)
    if start > now:
        start -= timedelta(days=7)
    return start


def period_key(now: datetime) -> str:
    return period_start(now).date().isoformat()


# ---------------------------------------------------------------------------
# Pure counting
# ---------------------------------------------------------------------------
@dataclass
class Counts:
    """Everything the post says, computed from rows and coverage sets alone."""

    open_markets: int = 0
    priced_markets: int = 0
    unshaped: int = 0
    relation_unknown: int = 0
    shape_unclassified: int = 0
    graph_unclassified: int = 0
    frames_written: int = 0
    frames_no_number: int = 0
    frames_never: int = 0
    covered_by: dict[str, int] = field(default_factory=dict)
    suppressed_markets: int = 0
    excluded_families: int = 0
    uncovered: list[Family] = field(default_factory=list)
    new_series_candidates: list[Family] = field(default_factory=list)
    all_families: list[Family] = field(default_factory=list)
    unblocked_events: int = 0


def is_suppressed(row: Mapping[str, Any]) -> bool:
    """Discover's hard exclusion by ruling, read from the classifier itself."""
    from app.utils.feed_market_quality import classify_market_quality

    quality = classify_market_quality(
        row.get("name"),
        row.get("llm_sport_category"),
        list(row.get("names") or []),
        row.get("external_id"),
        row.get("story_key"),
        "open",
    )
    return quality.quality_class == "suppress"


class CountsBuilder:
    """The four counts, folded in one page of rows at a time.

    The open population is about 58,000 markets. Holding them all as row dicts
    with their outcome names would cost the background worker around 100 MB
    for a weekly count (the worker held to 512 MB under 45-A). So each row is
    read once, counted, classified and reduced to a slim ``Atom``. Outcome
    names are kept only for Polymarket, where the title-template step needs
    them.
    """

    def __init__(self, *, now: datetime, suppressed: Callable[[Mapping[str, Any]], bool] = is_suppressed):
        self.now = now
        self.suppressed = suppressed
        self.age_floor = now - MIN_AGE
        self.counts = Counts()
        self.atoms: list[Atom] = []
        self.eligible: set[int] = set()
        self.suppressed_ids: set[int] = set()
        self.event_ids: set[int] = set()
        self.open_ids: set[int] = set()

    def add(self, row: Mapping[str, Any]) -> None:
        c = self.counts
        mid = int(row["id"])
        self.open_ids.add(mid)
        c.open_markets += 1
        shape = row.get("market_type")
        if shape == "unshaped":
            c.unshaped += 1
        elif shape is None:
            c.shape_unclassified += 1
        if row.get("outcome_relation") == "unknown":
            c.relation_unknown += 1
        frame_type = row.get("frame_type")
        if frame_type == "object":
            c.frames_written += 1
        elif frame_type == "null":
            c.frames_no_number += 1
        else:
            c.frames_never += 1
        if row.get("event_id") is not None:
            self.event_ids.add(mid)
        if not row.get("priced"):
            return
        c.priced_markets += 1
        created = row["created_at"]
        source = str(row.get("source") or "")
        names = tuple(n for n in (row.get("names") or []) if n) if source == "polymarket" else ()
        self.atoms.append(
            Atom(
                market_id=mid,
                source=source,
                external_id=str(row.get("external_id") or ""),
                group_id=row.get("group_id"),
                title=str(row.get("name") or ""),
                event_title=row.get("event_title"),
                outcome_names=names,
                created_at=created,
            )
        )
        if self.suppressed(row):
            self.suppressed_ids.add(mid)
        elif created <= self.age_floor:
            self.eligible.add(mid)

    def finish(
        self,
        *,
        definition_ids: set[int],
        graph_ids: set[int],
        collection_ids: set[int],
        graph_unclassified: int,
    ) -> Counts:
        c = self.counts
        c.graph_unclassified = graph_unclassified
        c.covered_by = {
            "definitions": len(definition_ids & self.open_ids),
            "graph": len(graph_ids & self.open_ids),
            "midterms": len(collection_ids & self.open_ids),
            "event_pages": len(self.event_ids),
        }
        covered = definition_ids | graph_ids | collection_ids | self.event_ids
        c.suppressed_markets = len(self.suppressed_ids)

        grouping = build_families(self.atoms)
        c.all_families = list(grouping.families)
        c.unblocked_events = grouping.unblocked_events
        c.uncovered = uncovered_families(
            grouping.families, covered=covered, eligible=self.eligible, min_markets=MIN_FAMILY_MARKETS
        )
        window_floor = self.now - NEW_SERIES_WINDOW
        for fam in grouping.families:
            members = fam.member_ids
            if any(m in covered for m in members):
                continue
            unsuppressed = [m for m in members if m not in self.suppressed_ids]
            if len(members) >= MIN_FAMILY_MARKETS and not unsuppressed:
                c.excluded_families += 1
                continue
            if len(unsuppressed) >= NEW_SERIES_MIN_OPEN and fam.first_created_at >= window_floor:
                c.new_series_candidates.append(fam)
        return c


def compute_counts(
    rows: Iterable[Mapping[str, Any]],
    *,
    definition_ids: set[int],
    graph_ids: set[int],
    collection_ids: set[int],
    graph_unclassified: int,
    now: datetime,
    suppressed: Callable[[Mapping[str, Any]], bool] = is_suppressed,
) -> Counts:
    """The four counts from the open population and the coverage sources, in one
    call (``CountsBuilder`` does the same a page at a time). ``rows`` are open
    markets, keyed as ``_ATOMS_SQL``. Pure apart from ``suppressed``."""
    builder = CountsBuilder(now=now, suppressed=suppressed)
    for row in rows:
        builder.add(row)
    return builder.finish(
        definition_ids=definition_ids,
        graph_ids=graph_ids,
        collection_ids=collection_ids,
        graph_unclassified=graph_unclassified,
    )


# ---------------------------------------------------------------------------
# New series: the sentinel's own memory
# ---------------------------------------------------------------------------
def family_memory_key(fam: Family) -> str:
    return f"{fam.kind}:{fam.key}"


def new_series_from_memory(
    candidates: list[Family], all_families: list[Family], now: datetime, redis_client: Any
) -> tuple[list[Family] | None, str]:
    """``(new families, state)``. ``state`` ∈ {``counted``, ``baseline``, ``memory_unavailable``}.

    Every family this run sees is recorded with ``ZADD NX``, so a key keeps the
    score of the run that first saw it. A family is new when it was first seen
    after the baseline run and inside the last seven days. The baseline run
    sees nothing new: it is when the memory began.
    """
    try:
        ts = now.timestamp()
        baseline_raw = redis_client.get(BASELINE_KEY)
        pipe = redis_client.pipeline()
        for fam in candidates:
            pipe.zscore(SEEN_KEY, family_memory_key(fam))
        scores = pipe.execute() if candidates else []
        keys = [family_memory_key(f) for f in all_families]
        for i in range(0, len(keys), 1000):
            redis_client.zadd(SEEN_KEY, {k: ts for k in keys[i : i + 1000]}, nx=True)
        redis_client.zremrangebyscore(SEEN_KEY, "-inf", ts - MEMORY_TTL_SECONDS)
        redis_client.expire(SEEN_KEY, MEMORY_TTL_SECONDS)
        if baseline_raw is None:
            redis_client.set(BASELINE_KEY, str(ts), ex=MEMORY_TTL_SECONDS)
            return None, "baseline"
        redis_client.expire(BASELINE_KEY, MEMORY_TTL_SECONDS)
        baseline = float(baseline_raw)
        window_floor = (now - NEW_SERIES_WINDOW).timestamp()
        new = []
        for fam, score in zip(candidates, scores):
            first_seen = ts if score is None else float(score)
            if first_seen > baseline and first_seen >= window_floor:
                new.append(fam)
        return new, "counted"
    except Exception:
        logger.warning("grouping sentinel: family memory unavailable", exc_info=True)
        return None, "memory_unavailable"


# ---------------------------------------------------------------------------
# The post
# ---------------------------------------------------------------------------
def _n(value: int) -> str:
    return f"{value:,}"


def _pct(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):.1f}%" if whole else "n/a"


def _clean(text: str, limit: int = 70) -> str:
    """A venue title made safe for a GitHub comment: no mentions, no table breaks."""
    text = " ".join(str(text or "").split()).replace("@", "(at)").replace("|", "/").replace("`", "'")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def compose_report(
    counts: Counts,
    *,
    now: datetime,
    new_series: list[Family] | None,
    memory_state: str,
    definition_stats: Mapping[str, Any],
    filing: Mapping[str, Any] | None = None,
) -> str:
    """The weekly comment: counts first, then the would-be families, then the
    UNKNOWNs (Fable, 9:28 PM). Under 60 lines by construction."""
    week = period_start(now)
    filing_open = now >= FILING_STARTS_AT
    by_kind: dict[str, int] = {}
    for fam in counts.uncovered:
        by_kind[fam.kind] = by_kind.get(fam.kind, 0) + 1
    uncovered_markets = sum(fam.size for fam in counts.uncovered)

    lines = [
        f"**Grouping sentinel: weekly count** · week from Thu {week:%b} {week.day} · as of {now:%Y-%m-%d %H:%M} UTC",
        (
            "Filing is on (72-A): at most five new issues a run, one per uncovered family below."
            if filing_open
            else "Report-only until Thu Nov 26 (72-A). From then, at most five new issues a week, one per uncovered family below."
        ),
        "",
        (
            f"**1. Uncovered families: {_n(len(counts.uncovered))}** "
            f"(5+ open, priced markets alive 48 h; no member in a definition, container, theme, "
            f"the Midterms collection or on an event page): "
            + " · ".join(f"{_KIND_PLURAL[k]} {_n(by_kind.get(k, 0))}" for k in _KIND_PLURAL)
            + f" · {_n(uncovered_markets)} markets"
        ),
    ]
    if new_series is None:
        why = (
            f"this run recorded the baseline of {_n(len(counts.all_families))} families; next week counts against it"
            if memory_state == "baseline"
            else "the sentinel's memory (Redis) could not be read this run"
        )
        lines.append(f"**2. New venue series: UNKNOWN** ({why}).")
    else:
        names = ", ".join(f"`{_clean(f.key, 40)}`" for f in new_series[:5])
        more = f" and {_n(len(new_series) - 5)} more" if len(new_series) > 5 else ""
        lines.append(
            f"**2. New venue series: {_n(len(new_series))}** "
            f"(first seen in the last 7 days, 3+ open, priced markets, covered by nothing)"
            + (f": {names}{more}" if new_series else "")
        )
    lines.append(
        f"**3. Shapes:** of {_n(counts.open_markets)} open markets, {_n(counts.unshaped)} `unshaped` "
        f"({_pct(counts.unshaped, counts.open_markets)}) · {_n(counts.relation_unknown)} with outcomes "
        f"`unknown` ({_pct(counts.relation_unknown, counts.open_markets)}) · "
        f"{_n(counts.shape_unclassified)} not yet classified · {_n(counts.graph_unclassified)} graph "
        f"members `unclassified`"
    )
    lines.append(
        f"**4. New measures: UNKNOWN**: nothing reads the frame yet (#12249). Frames on open markets: "
        f"{_n(counts.frames_written)} written · {_n(counts.frames_no_number)} titles with no number · "
        f"{_n(counts.frames_never)} never written."
    )
    cov = counts.covered_by
    lines += [
        "",
        (
            f"Covered this run, open markets: definitions {_n(cov.get('definitions', 0))} "
            f"({definition_stats.get('emitted', 0)} of {definition_stats.get('producers', 0)} producers emitted, "
            f"{definition_stats.get('refused', 0)} refused, {definition_stats.get('failed', 0)} failed"
            + (f", {definition_stats['switched_off']} switched off" if definition_stats.get("switched_off") else "")
            + ") · "
            f"graph {_n(cov.get('graph', 0))} · Midterms {_n(cov.get('midterms', 0))} · "
            f"event pages {_n(cov.get('event_pages', 0))}. Excluded by ruling (Discover hard-suppresses them): "
            f"{_n(counts.suppressed_markets)} markets, {_n(counts.excluded_families)} whole families."
        ),
        "",
        "**Largest uncovered families**, the first to be filed (fingerprint · kind · key · markets · title):",
    ]
    for i, fam in enumerate(counts.uncovered[:LISTED_FAMILIES], 1):
        lines.append(
            f"{i}. `{fam.fingerprint}` · {_KIND_LABEL[fam.kind]} · `{_clean(fam.key, 48)}` · "
            f"{_n(fam.size)} · {_clean(fam.label)}"
        )
    if not counts.uncovered:
        lines.append("None this week.")
    elif len(counts.uncovered) > LISTED_FAMILIES:
        lines.append(f"…and {_n(len(counts.uncovered) - LISTED_FAMILIES)} more.")

    if filing:
        lines += ["", f"Filing this run: {filing.get('summary', filing.get('action', 'none'))}."]

    unknowns = ["new measures (no frame reader)"]
    if new_series is None:
        unknowns.append("new venue series (see 2)")
    if definition_stats.get("failed"):
        unknowns.append(
            f"members of {definition_stats['failed']} definition(s) that failed to evaluate: "
            + ", ".join(f"`{s}`" for s in definition_stats.get("failed_slugs", [])[:5])
        )
    if counts.unblocked_events:
        unknowns.append(
            f"title templates among {_n(counts.unblocked_events)} Polymarket events in blocks too large to compare"
        )
    lines += ["", "**UNKNOWN:** " + " · ".join(unknowns) + ".", "", "Sentinel: `backend/app/tasks/grouping_sentinel.py` (#12231)."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Filing (from Thu Nov 26)
# ---------------------------------------------------------------------------
def _declaration(fingerprint: str) -> str:
    return f"`{FILING_MARKER}:{fingerprint}`  (dedupe key — do not remove)"


def family_issue_title(fam: Family) -> str:
    return f"Grouping sentinel: {_KIND_LABEL[fam.kind]} `{_clean(fam.key, 60)}`, {fam.size} open markets no grouping covers"


def family_issue_body(fam: Family, now: datetime) -> str:
    sample = ", ".join(str(m) for m in fam.member_ids[:10])
    return "\n".join(
        [
            (
                f"**{_KIND_LABEL[fam.kind]}** `{_clean(fam.key, 80)}`: {fam.size} open, priced markets, "
                f"first stored {fam.first_created_at:%Y-%m-%d}, as of {now:%Y-%m-%d %H:%M} UTC."
            ),
            f"Example title: {_clean(fam.label, 120)}",
            f"Market ids (first 10): {sample}",
            "",
            (
                "No member is in a definition (`backend/data/containers/`), a container or theme in the graph, "
                "the Midterms collection or on an event page, and Discover does not suppress it by ruling. "
                "Per 72-A this family is five or more open, priced markets alive 48 hours."
            ),
            "",
            (
                "**What to do:** write a definition or selector that admits it (`docs/design/grouping-primitives.md`, "
                "\"How to add a kind\"). The sentinel closes this issue itself once a grouping covers the family "
                "or its markets close. It has no exclusion list yet: an issue closed by hand while the family stays "
                "uncovered is filed again the next week (#12231)."
            ),
            "",
            _declaration(fam.fingerprint),
            "",
            "Filed by the grouping sentinel (#12231); weekly counts on #12221.",
        ]
    )


def file_families(uncovered: list[Family], now: datetime) -> dict:
    """RED for each uncovered family (largest first, at most five NEW), GREEN for
    each of this sentinel's open issues whose family is no longer uncovered."""
    from app.tasks.sentinel_filing import declared_fingerprints, fetch_open_alert_issues, reconcile_issue

    open_issues = fetch_open_alert_issues()
    if not open_issues.ok:
        return {"action": "dedup_unknown_no_op", "error": open_issues.error, "summary": "skipped (open-issue list unreadable)"}
    ours = {
        fp
        for issue in open_issues.issues
        for marker, fp in declared_fingerprints(issue.get("body"))
        if marker == FILING_MARKER
    }
    results = []
    new_filed = 0
    current = {fam.fingerprint for fam in uncovered}
    for fam in uncovered:
        if fam.fingerprint not in ours and new_filed >= MAX_NEW_ISSUES_PER_RUN:
            continue
        body = family_issue_body(fam, now)
        res = reconcile_issue(
            red=True,
            fingerprint=fam.fingerprint,
            marker_key=FILING_MARKER,
            title=family_issue_title(fam),
            body=body,
            red_body=body,
            red_comment=f"Still uncovered as of {now:%Y-%m-%d} UTC: {fam.size} open, priced markets (fingerprint `{fam.fingerprint}`).",
            labels=FILING_LABELS,
            open_issues=open_issues,
        )
        if res.get("action") == "filed":
            new_filed += 1
        results.append(res)
    for fp in sorted(ours - current):
        results.append(
            reconcile_issue(
                red=False,
                fingerprint=fp,
                marker_key=FILING_MARKER,
                green_comment=(
                    f"Grouping sentinel re-checked {now:%Y-%m-%d} UTC: this family is covered now, "
                    f"or its markets closed (fingerprint `{fp}`). Closing; a recurrence files fresh."
                ),
                open_issues=open_issues,
            )
        )
    filed = sum(1 for r in results if r.get("action") == "filed")
    commented = sum(1 for r in results if r.get("action") == "commented")
    resolved = sum(1 for r in results if r.get("action") == "resolved")
    failed = sum(1 for r in results if r.get("action") in ("error", "comment_failed", "close_failed"))
    return {
        "action": "reconciled",
        "results": results,
        "summary": f"{filed} filed, {commented} still open, {resolved} closed, {failed} failed",
        "failed": failed,
    }


def filing_paused(redis_client: Any) -> bool | None:
    """Alex's no-deploy pause switch: any value under ``FILING_PAUSE_KEY`` pauses
    filing (even ``0``; ``DEL`` resumes). ``None`` when it cannot be read: a run
    that cannot rule out a pause files nothing that week."""
    if redis_client is None:
        return None
    try:
        return bool(redis_client.get(FILING_PAUSE_KEY))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
_ATOMS_SQL = """
SELECT fm.id, fm.source, fm.external_id, fm.group_id, fm.name, fm.event_id, fm.created_at,
       fm.llm_sport_category, fm.story_key, fm.market_type,
       fm.market_metadata->>'event_title' AS event_title,
       fm.market_metadata->'shape'->>'outcome_relation' AS outcome_relation,
       jsonb_typeof(fm.market_metadata->'discover_llm'->'frame') AS frame_type,
       o.names, COALESCE(o.priced, false) AS priced
FROM futures_markets fm
LEFT JOIN LATERAL (
    SELECT (array_agg(fo.name ORDER BY fo.id))[1:20] AS names,
           bool_or(fo.current_probability IS NOT NULL) AS priced
    FROM futures_outcomes fo
    WHERE fo.market_id = fm.id
) o ON true
WHERE fm.status = 'open' AND fm.settled_at IS NULL AND fm.id > :after
ORDER BY fm.id
LIMIT :page
"""

#: Rows per page of ``_ATOMS_SQL``. Each page is counted and dropped.
PAGE_ROWS = 5000

_GRAPH_SQL = """
SELECT DISTINCT e.child_id
FROM event_edges e
JOIN containers c ON c.id = e.parent_id
WHERE e.kind = 'contains' AND e.parent_type = 'container' AND e.child_type = 'market'
  AND c.status <> 'cancelled'
"""

_GRAPH_UNCLASSIFIED_SQL = """
SELECT count(DISTINCT e.child_id)
FROM event_edges e
JOIN futures_markets fm ON fm.id = e.child_id
WHERE e.kind = 'contains' AND e.parent_type = 'container' AND e.child_type = 'market'
  AND e."class" = 'unclassified' AND fm.status = 'open' AND fm.settled_at IS NULL
"""


def collection_ids() -> set[int]:
    """The Midterms collection: its manifest and both venues of its twin register."""
    from app.utils.midterms_collection import MARKET_IDS, MIDTERMS_TWIN_REGISTER

    ids = {int(m) for m in MARKET_IDS}
    for twin in MIDTERMS_TWIN_REGISTER:
        ids.add(int(twin.kalshi_market_id))
        if twin.polymarket_market_id is not None:
            ids.add(int(twin.polymarket_market_id))
    return ids


def definition_market_ids(container: Mapping[str, Any], feed_item: Mapping[str, Any]) -> set[int]:
    """The markets one evaluated definition covers: every market member of its
    container (the collection page shows them all, not only the card's rows) and
    every row market and cross-venue pair on its Discover card.

    Not ``_roundup_covered_market_ids``: its ``member_ids`` also carry the ids of
    event members (the closest-games round-up's members are events), and an
    event id read as a market id would cover an unrelated market."""
    from app.utils.container_presentation import MEMBER_MARKET

    def _id(value: Any) -> int | None:
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else None

    ids: set[int] = set()
    for section in container.get("sections") or ():
        for member in (section.get("members") or ()) if isinstance(section, Mapping) else ():
            if isinstance(member, Mapping) and member.get("type") == MEMBER_MARKET:
                if (mid := _id(member.get("id"))) is not None:
                    ids.add(mid)
    data = feed_item.get("data")
    roundup = data.get("roundup") if isinstance(data, Mapping) else None
    for r in (roundup.get("rows") or ()) if isinstance(roundup, Mapping) else ():
        if not isinstance(r, Mapping):
            continue
        if (mid := _id(r.get("market_id"))) is not None:
            ids.add(mid)
        pair = r.get("pair")
        if isinstance(pair, Mapping):
            for k in ("kalshi_market_id", "polymarket_market_id"):
                if (pid := _id(pair.get(k))) is not None:
                    ids.add(pid)
    return ids


async def evaluate_definition(producer: Any, session: Any) -> set[int] | None:
    """One definition read live: ``evaluate_roundup_producer``'s path without its
    60 s shared cache. Since #12257 a Discover read that times out is cached
    there as a refusal, and a weekly count must not read a one-minute timeout as
    "this definition covers nothing". Skipping the cache also means this
    sentinel never writes Discover's. ``None`` is a refusal."""
    from app.utils.roundup_containers import (
        RoundupMembers,
        RoundupRefusal,
        compose_roundup_container,
        compose_roundup_feed_item,
    )

    outcome = producer.produce(session)
    if inspect.isawaitable(outcome):
        outcome = await outcome
    if outcome is None or isinstance(outcome, RoundupRefusal):
        return None
    if not isinstance(outcome, RoundupMembers):
        outcome = RoundupMembers(outcome)
    container = compose_roundup_container(producer, outcome)
    feed_item = compose_roundup_feed_item(producer, outcome)
    if container is None or feed_item is None:
        return None
    return definition_market_ids(container, feed_item)


async def definition_coverage(session: Any) -> tuple[set[int], dict]:
    """The markets every registered round-up producer covers, read live."""
    from app.utils.roundup_containers import ROUNDUP_PRODUCERS

    covered: set[int] = set()
    stats: dict[str, Any] = {
        "producers": 0, "emitted": 0, "refused": 0, "switched_off": 0, "failed": 0, "failed_slugs": [],
    }
    for producer in list(ROUNDUP_PRODUCERS.values()):
        stats["producers"] += 1
        if producer.enabled is not None and not producer.enabled():
            stats["switched_off"] += 1
            continue
        try:
            ids = await asyncio.wait_for(
                evaluate_definition(producer, session), timeout=PRODUCER_TIMEOUT_SECONDS
            )
        except Exception:
            logger.warning("grouping sentinel: producer %s failed", producer.slug, exc_info=True)
            stats["failed"] += 1
            stats["failed_slugs"].append(producer.slug)
            try:
                await session.rollback()
            except Exception:  # noqa: BLE001
                pass
            continue
        if ids is None:
            stats["refused"] += 1
            continue
        stats["emitted"] += 1
        covered |= ids
    return covered, stats


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
def _terminal(stats: Mapping[str, Any]) -> str:
    """The honest terminal (#1884: enrolled in ENFORCED_TASKS from birth).

    ``complete`` only when the counts were computed AND this week's post is on
    #12221 (posted now or already there) AND any filing due ran cleanly. A run
    that could not read the population is ``failed``. A post that did not land
    is ``failed``: the post is the artifact, and "it returned" is not "it
    worked" (gotcha #53). A degraded source (a definition that failed to
    evaluate, the memory unreadable, a filing failure, a lost claim) is
    ``partial``.
    """
    if stats.get("error"):
        return "failed"
    report = (stats.get("report") or {}).get("action")
    if report not in ("posted", "already_posted", "not_requested"):
        return "partial" if report == "claim_lost" else "failed"
    degraded = (
        stats.get("definitions", {}).get("failed")
        or stats.get("memory_state") == "memory_unavailable"
        or (stats.get("filing") or {}).get("failed")
        or (stats.get("filing") or {}).get("action") in ("dedup_unknown_no_op", "pause_unknown_no_op")
    )
    return "partial" if degraded else "complete"


async def _run_grouping_sentinel(
    *, post: bool = True, file_issues: bool = True, now: datetime | None = None
) -> dict[str, Any]:
    """One weekly run. ``post=False`` computes and composes without posting (the
    body is returned in ``report_body``). ``file_issues=False`` never files, even
    after Nov 26."""
    from sqlalchemy import text

    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.tasks.sentinel_filing import post_report

    started = _time.monotonic()
    now = now or datetime.now(timezone.utc)
    stats: dict[str, Any] = {"period": period_key(now), "as_of": now.isoformat()}
    try:
        builder = CountsBuilder(now=now, suppressed=is_suppressed)
        async with get_task_session(statement_timeout_ms=STATEMENT_TIMEOUT_MS) as session:
            after = 0
            while True:
                page = (
                    await session.execute(text(_ATOMS_SQL), {"after": after, "page": PAGE_ROWS})
                ).mappings().all()
                for r in page:
                    builder.add(r)
                if len(page) < PAGE_ROWS:
                    break
                after = int(page[-1]["id"])
            graph_ids = {int(r[0]) for r in (await session.execute(text(_GRAPH_SQL))).all()}
            graph_unclassified = int((await session.execute(text(_GRAPH_UNCLASSIFIED_SQL))).scalar() or 0)
            definition_ids, definition_stats = await asyncio.wait_for(
                definition_coverage(session), timeout=DEADLINE_SECONDS
            )
    except Exception as exc:
        logger.exception("grouping sentinel: reads failed")
        stats["error"] = str(exc)[:300]
        stats["terminal"] = _terminal(stats)
        return stats

    counts = builder.finish(
        definition_ids=definition_ids,
        graph_ids=graph_ids,
        collection_ids=collection_ids(),
        graph_unclassified=graph_unclassified,
    )
    try:
        redis_client = get_redis_client()
    except Exception:
        redis_client = None
    new_series, memory_state = (
        new_series_from_memory(counts.new_series_candidates, counts.all_families, now, redis_client)
        if redis_client is not None
        else (None, "memory_unavailable")
    )

    filing: dict[str, Any] | None = None
    if file_issues and now >= FILING_STARTS_AT:
        paused = filing_paused(redis_client)
        if paused is None:
            filing = {
                "action": "pause_unknown_no_op",
                "summary": f"skipped (`{FILING_PAUSE_KEY}` unreadable, so a pause cannot be ruled out)",
            }
        elif paused:
            filing = {"action": "paused", "summary": f"paused (`{FILING_PAUSE_KEY}` is set)"}
        else:
            filing = file_families(counts.uncovered, now)

    body = compose_report(
        counts,
        now=now,
        new_series=new_series,
        memory_state=memory_state,
        definition_stats=definition_stats,
        filing=filing,
    )
    report = (
        post_report(
            issue=REPORT_ISSUE,
            marker_key=REPORT_MARKER,
            period_key=period_key(now),
            body=body,
            since=period_start(now).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        if post
        else {"action": "not_requested"}
    )
    stats.update(
        open_markets=counts.open_markets,
        priced_markets=counts.priced_markets,
        uncovered_families=len(counts.uncovered),
        uncovered_markets=sum(f.size for f in counts.uncovered),
        new_series=None if new_series is None else len(new_series),
        memory_state=memory_state,
        definitions=definition_stats,
        covered_by=counts.covered_by,
        suppressed_markets=counts.suppressed_markets,
        report=report,
        filing={k: v for k, v in (filing or {}).items() if k != "results"} or None,
        report_body=body if not post else None,
        duration_s=round(_time.monotonic() - started, 2),
    )
    stats["terminal"] = _terminal(stats)
    return stats
