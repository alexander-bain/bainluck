// #999 Event Concept Pages (slice 1) — pure display helpers for /event/[key].
// Extracted so the rendering logic is unit-tested without mounting the page.
// D1 binds: probabilities only, never odds.

import type {
  EventConceptCompetitor,
  EventConceptChild,
  EventConceptResponse,
  FuturesOutcomeHistory,
} from "./types";

export function statusLabel(status: string): string {
  switch (status) {
    case "live":
      return "Live";
    case "settled":
      return "Settled";
    default:
      return "Upcoming";
  }
}

/** Competitors sorted by probability desc (the winner-field leaderboard order). */
export function fieldOrder(
  competitors: EventConceptCompetitor[],
): EventConceptCompetitor[] {
  return [...(competitors || [])].sort(
    (a, b) => (b.probability ?? -1) - (a.probability ?? -1),
  );
}

/** The leading outcome (name + probability) for a child matchup/prop row.
 *  Falls back to the child's own name/probability when it has no outcomes. */
export function childLeader(
  child: EventConceptChild,
): { name: string; probability: number | null } | null {
  const outs = child.outcomes || [];
  if (outs.length > 0) {
    const top = [...outs].sort(
      (a, b) => (b.probability ?? -1) - (a.probability ?? -1),
    )[0];
    return { name: top.name, probability: top.probability ?? null };
  }
  if (child.name) return { name: child.name, probability: child.probability ?? null };
  if (child.market_name) return { name: child.market_name, probability: child.probability ?? null };
  return null;
}

/** Split children into live vs settled (decided) so the page keeps live matchups
 *  prominent and groups/de-emphasizes completed ones (L2-63 Item 2 — a decided
 *  match must not masquerade as live at 99%). Settled = the envelope flag, or a
 *  dead-extreme leader as a fallback. */
export function splitChildren(
  children: EventConceptChild[],
): { live: EventConceptChild[]; settled: EventConceptChild[] } {
  const live: EventConceptChild[] = [];
  const settled: EventConceptChild[] = [];
  for (const c of children || []) {
    const p = c.probability;
    const decided = c.settled === true || (p != null && (p >= 0.97 || p <= 0.03));
    (decided ? settled : live).push(c);
  }
  return { live, settled };
}

/** L2-81: the champion of a SETTLED winner-field, or null when it can't be named
 *  honestly. Prefers the authoritative `won` flag (from resolution); falls back to
 *  the top-probability competitor ONLY when it's a confident ~1.0 (>=0.9), so a
 *  stale mid-tournament field (or a blowout with a stale midpoint) never falsely
 *  crowns someone. Pure so the "who won" wording is unit-tested. */
export function settledChampion(
  competitors: EventConceptCompetitor[],
): EventConceptCompetitor | null {
  const ranked = fieldOrder(competitors);
  const won = ranked.find((c) => c.won === true);
  if (won) return won;
  const top = ranked[0];
  if (top && (top.probability ?? 0) >= 0.9) return top;
  return null;
}

// ---------------------------------------------------------------------------
// Matchup duels (L2-130 — soccer World Cup bracket games as team duels).
//
// The soccer adapter is the first to fuse the events data-plane into concept
// children: each bracket game is a `kind:"matchup"` child carrying `home`/`away`
// team sides (crest + blended win probability + score) and `event_id` (NOT a
// `market_id`). These helpers keep the rail/hero rendering pure + unit-tested.
// ---------------------------------------------------------------------------

/** True when a child is a soccer-style team duel (home vs away), not a combat
 *  fight-card outcome list or a prop. Detected by the explicit `matchup` kind or,
 *  defensively, by the presence of a `home`/`away` side. */
export function isMatchupChild(child: EventConceptChild): boolean {
  return (
    child.kind === "matchup" ||
    child.home != null ||
    child.away != null
  );
}

/** A stable React key for any child. Matchup children carry `event_id` (no
 *  `market_id`), so `market_id` alone keyed every soccer game as `undefined`
 *  (React dup-key warning + broken reconciliation). Falls back through
 *  event_id → market name → index. */
export function childReactKey(child: EventConceptChild, index: number): string {
  if (typeof child.market_id === "number") return `m${child.market_id}`;
  if (typeof child.event_id === "number") return `e${child.event_id}`;
  return `${child.market_name || child.name || "child"}-${index}`;
}

/** The headliner matchup for the container hero: the live game if one is in play,
 *  else the soonest upcoming game. Returns null when there is no live/upcoming
 *  matchup (e.g. a fully-settled tournament — the hero is then suppressed and the
 *  final result reads from the leaderboard). Pure. */
export function headlinerMatchup(
  children: EventConceptChild[],
): EventConceptChild | null {
  const matchups = (children || []).filter(isMatchupChild);
  const live = matchups.find((c) => (c.status || "").toLowerCase() === "live");
  if (live) return live;
  const upcoming = matchups
    .filter((c) => (c.status || "").toLowerCase() === "scheduled")
    .sort((a, b) => {
      const ta = a.commence_time ? Date.parse(a.commence_time) : Infinity;
      const tb = b.commence_time ? Date.parse(b.commence_time) : Infinity;
      return ta - tb;
    });
  return upcoming[0] ?? null;
}

/** A human kickoff/status label for a matchup, from `now` (ms). Live → "Live";
 *  settled → "Final"; upcoming → a relative "Kicks off in Nh Mm" within a day, a
 *  weekday+time within a week, else a short date. Returns null when there's no
 *  usable time for an upcoming game. Pure so the wording is clock-free tested. */
export function matchupKickoffLabel(
  child: EventConceptChild,
  now: number,
): string | null {
  const status = (child.status || "").toLowerCase();
  if (status === "live") return "Live";
  if (child.settled || status === "completed" || status === "closed") return "Final";
  const ct = child.commence_time;
  if (!ct) return null;
  const t = Date.parse(ct);
  if (Number.isNaN(t)) return null;
  const diffMs = t - now;
  if (diffMs <= 0) return "Kicking off";
  const mins = Math.round(diffMs / 60000);
  if (mins < 60) return `Kicks off in ${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) {
    const rem = mins % 60;
    return rem > 0 ? `Kicks off in ${hours}h ${rem}m` : `Kicks off in ${hours}h`;
  }
  const dt = new Date(t);
  const days = Math.floor(diffMs / (24 * 3600 * 1000));
  if (days < 7) {
    return dt.toLocaleDateString("en-US", {
      weekday: "short",
      hour: "numeric",
      minute: "2-digit",
    });
  }
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ---------------------------------------------------------------------------
// Finish-position ladder (L2-116 RENDER ruling).
//
// Golf placement markets — "Top 5 / Top 10 / Top 20 / Make Cut" — are
// multi-outcome markets whose per-competitor probabilities are fused onto each
// competitor by the golf aggregation as `top_5_prob` / `top_10_prob` /
// `top_20_prob` / `make_cut_prob` (0–100 POINTS). They live in the envelope
// `sections` (types top_5/top_10/top_20/make_cut) but had NO renderer on the
// concept page — so they were counted by the header chip yet invisible. The
// ruling: render them as a threshold-group ladder, and count only what renders
// (both directions). These two helpers are the single source of truth shared by
// the renderer (FinishPositionLadder) and the count (marketsTracked), so the two
// can never drift.
// ---------------------------------------------------------------------------

export interface FinishPositionColumn {
  /** Envelope section `type` for this column's market group. */
  type: string;
  /** Competitor field carrying this column's probability (0–100 points). */
  key: string;
  /** Short header label. */
  label: string;
}

/** The ladder columns, ordered widest-net last (Win is the anchor rendered
 *  separately by the leaderboard). Order mirrors golf's `type_order`. */
export const FINISH_POSITION_COLUMNS: FinishPositionColumn[] = [
  { type: "top_5", key: "top_5_prob", label: "Top 5" },
  { type: "top_10", key: "top_10_prob", label: "Top 10" },
  { type: "top_20", key: "top_20_prob", label: "Top 20" },
  { type: "make_cut", key: "make_cut_prob", label: "Make cut" },
];

/** Read a competitor's 0–100 finish-position value for a column key, or null. */
function finishValue(
  c: EventConceptCompetitor,
  key: string,
): number | null {
  const raw = (c as Record<string, unknown>)[key];
  return typeof raw === "number" && !Number.isNaN(raw) ? raw : null;
}

// L2-123 / #199: a finish-position column whose values are an all-tied flat
// placeholder (every golfer at ~the same 0–100 points — the wide-spread/no-trade
// capture class: The Open's make-cut showed the whole field at ≈1.1 pts, top-5
// crowned a ceremonial past champion) is NOT a real book. It must not render as a
// wall of fake flats. A genuine placement field spreads tens of points across the
// leaderboard, so "agreement" only appears on fabricated placeholders. Tested by
// absolute floor OR relative ratio (mirrors the props path) so a placeholder that
// is near-flat but not perfectly tied is still caught. Guarded on ≥5 values so an
// early, thin-but-real field is never mistaken for one.
const FINISH_COLUMN_DEGENERATE_SPREAD = 1.0; // points (0–100 scale)
const FINISH_COLUMN_FLAT_RATIO = 0.1; // (max-min)/max

function finishColumnIsDegenerate(
  comps: EventConceptCompetitor[],
  key: string,
): boolean {
  const vals = comps
    .map((c) => finishValue(c, key))
    .filter((v): v is number => v != null);
  if (vals.length < 5) return false;
  const mx = Math.max(...vals);
  const mn = Math.min(...vals);
  if (mx <= 0) return true;
  const spread = mx - mn;
  return spread <= FINISH_COLUMN_DEGENERATE_SPREAD || spread / mx <= FINISH_COLUMN_FLAT_RATIO;
}

/** The finish-position columns that ACTUALLY render for this field: a column
 *  renders iff its market group exists in `sections` AND at least one competitor
 *  carries a value for it. Suppressed entirely once the event is settled — a
 *  concluded field shows the champion, not stale placement percentages
 *  (settled-means-settled). This predicate is the single source of truth for both
 *  the renderer and the header count, so a finish-position market is counted iff
 *  its column renders (both directions). */
export function renderedFinishColumns(
  data: EventConceptResponse,
): FinishPositionColumn[] {
  if (data.event?.status === "settled") return [];
  const sectionTypes = new Set((data.sections || []).map((s) => s.type));
  const comps = data.primary?.competitors || [];
  return FINISH_POSITION_COLUMNS.filter(
    (col) =>
      sectionTypes.has(col.type) &&
      comps.some((c) => finishValue(c, col.key) != null) &&
      // L2-123 / #199: drop degenerate all-tied-flat placeholder columns so the
      // ladder never shows a wall of fake finish percentages (the honest treatment
      // for the wide-spread/no-trade capture class is to suppress the column).
      !finishColumnIsDegenerate(comps, col.key),
  );
}

/** Competitors that carry ≥1 rendered finish-position value, ordered by win
 *  probability desc and limited — the rows of the finish-position ladder. Each
 *  row keeps the competitor plus a `values` map of column-key → 0–100 points (or
 *  null where that golfer has no odds for that column — rendered as "—", never
 *  fabricated). Returns [] when no columns render. */
export function finishPositionRows(
  data: EventConceptResponse,
  columns: FinishPositionColumn[],
  limit = 20,
): { competitor: EventConceptCompetitor; values: Record<string, number | null> }[] {
  if (!columns.length) return [];
  const comps = fieldOrder(data.primary?.competitors || []);
  const rows: {
    competitor: EventConceptCompetitor;
    values: Record<string, number | null>;
  }[] = [];
  for (const c of comps) {
    const values: Record<string, number | null> = {};
    let any = false;
    for (const col of columns) {
      const v = finishValue(c, col.key);
      values[col.key] = v;
      if (v != null) any = true;
    }
    if (any) rows.push({ competitor: c, values });
    if (rows.length >= limit) break;
  }
  return rows;
}

/** Count of distinct markets tracked on this page — for the header "N markets"
 *  chip. Counts ONLY what the page actually renders (L2-116 RENDER ruling — both
 *  directions): the evolution market (the winner leaderboard / race / path
 *  chart), every rendered child (matchups rail + props section — already
 *  cross-source-deduped and outcome-filtered upstream), and one question per
 *  rendered finish-position ladder column. It deliberately does NOT union raw
 *  `sections`, which carried counted-but-invisible markets — hidden placement
 *  ladders, "Winner Nationality"/"Tour of Winner" props, outcome-less skips, and
 *  cross-source duplicates. */
export function marketsTracked(data: EventConceptResponse): number {
  const ids = new Set<number>();
  const ev = data.primary?.evolution_market_id;
  if (typeof ev === "number") ids.add(ev);
  for (const c of data.children || []) {
    if (typeof c.market_id === "number") ids.add(c.market_id);
    // L2-130: matchup children (soccer games) carry `event_id`, not `market_id`;
    // count each rendered game so the header reflects the bracket, not just the
    // winner market. Offset the id space so an event_id can't collide with a
    // market_id in the same Set.
    else if (typeof c.event_id === "number") ids.add(-c.event_id - 1);
  }
  // One tracked question per rendered finish-position column (a column may be
  // backed by several source markets but renders as a single blended ladder
  // rung — counting it once mirrors how deduped children are counted).
  return ids.size + renderedFinishColumns(data).length;
}

/** 24h probability movement for a competitor, read defensively from either the
 *  golf-shaped `movement_24h` or the generic `probability_change_24h` extra key.
 *  Returns a signed FRACTION (e.g. +0.03), or null when absent. */
export function competitorMovement(c: EventConceptCompetitor): number | null {
  const raw =
    (c as Record<string, unknown>).movement_24h ??
    (c as Record<string, unknown>).probability_change_24h;
  if (typeof raw !== "number" || Number.isNaN(raw)) return null;
  // Golf movement_24h is already a probability fraction; a value with abs>1 is
  // almost certainly already in points — normalize both to fraction.
  return Math.abs(raw) > 1 ? raw / 100 : raw;
}

/** Format a signed probability fraction as movement points, e.g. +3.2 / -1.0.
 *  Returns null for a null/zero-rounding change so callers can omit the chip. */
export function formatMovement(
  change: number | null | undefined,
): { text: string; dir: "up" | "down" } | null {
  if (change == null || Number.isNaN(change)) return null;
  const pts = change * 100;
  if (Math.abs(pts) < 0.05) return null;
  const dir = pts > 0 ? "up" : "down";
  return { text: `${pts > 0 ? "+" : "−"}${Math.abs(pts).toFixed(1)}`, dir };
}

/** Extract a competitor's probability series (0–1) from fetched history, matched
 *  by normalized name. Returns time-ordered probabilities (nulls dropped). Empty
 *  when the competitor has no matching series — the caller then omits the
 *  sparkline rather than inventing history. */
export function seriesForName(
  outcomes: FuturesOutcomeHistory[] | undefined,
  name: string,
): number[] {
  if (!outcomes || !name) return [];
  const norm = (s: string) => s.trim().toLowerCase();
  const target = norm(name);
  const match = outcomes.find((o) => norm(o.name) === target);
  if (!match) return [];
  return match.history
    .filter((p) => p.probability != null)
    .map((p) => p.probability as number);
}

/** L2-71: a competitor's own probability series (from the envelope-attached
 *  history), for the sparkline. Empty when no history — omit, never fabricate. */
export function seriesFromCompetitor(c: EventConceptCompetitor): number[] {
  return (c.history || [])
    .filter((p) => p && p.probability != null)
    .map((p) => p.probability);
}

/** L2-71: build FuturesOutcomeHistory[] from the envelope competitors that carry
 *  history, so the RaceToTitleChart draws from the envelope (no extra fetch).
 *  Optionally filter each series to the last `hours` (client-side range switch). */
export function competitorsToOutcomeHistory(
  competitors: EventConceptCompetitor[],
  hours?: number,
): FuturesOutcomeHistory[] {
  const cutoff =
    hours && hours > 0 ? Date.now() - hours * 3600 * 1000 : null;
  const out: FuturesOutcomeHistory[] = [];
  for (const c of competitors || []) {
    if (typeof c.outcome_id !== "number" || !c.history || c.history.length === 0) continue;
    const pts = cutoff
      ? c.history.filter((p) => {
          const t = new Date(p.timestamp).getTime();
          return Number.isNaN(t) || t >= cutoff;
        })
      : c.history;
    out.push({
      outcome_id: c.outcome_id,
      name: c.name,
      history: pts.map((p) => ({
        timestamp: p.timestamp,
        probability: p.probability,
        american_odds: null,
        bookmaker: "aggregate",
      })),
    });
  }
  return out;
}

/** L2-78: calendar days until an event starts, from `now` (ms). Honest countdown
 *  for the pre-tournament header — the *calendar-day* difference (UTC), so July 9
 *  → July 15 reads "6 days" the way a person counts it (not 5-and-a-fraction).
 *  Returns null when there's no start, the date is unparseable, or the start day
 *  is already past. 0 = starts on today's date. Pure so it's clock-free tested. */
export function daysUntilStart(
  start: string | null | undefined,
  now: number,
): number | null {
  if (!start) return null;
  const t = new Date(start).getTime();
  if (Number.isNaN(t)) return null;
  const dayMs = 24 * 3600 * 1000;
  const days = Math.floor(t / dayMs) - Math.floor(now / dayMs);
  if (days < 0) return null;
  return days;
}

/** L2-78: the header countdown label for an upcoming event, or null when there's
 *  nothing to show (live/settled, or no future start). Kept pure + separate from
 *  the component so the wording is unit-tested. */
export function countdownLabel(
  status: string,
  start: string | null | undefined,
  now: number,
): string | null {
  if (status === "live" || status === "settled") return null;
  const days = daysUntilStart(start, now);
  if (days == null) return null;
  if (days === 0) return "Starts today";
  return `Starts in ${days} day${days === 1 ? "" : "s"}`;
}

/** A readable event date range (either bound optional). */
export function eventDateRange(
  start?: string | null,
  end?: string | null,
): string | null {
  const fmt = (d: string) => {
    const dt = new Date(d);
    return Number.isNaN(dt.getTime())
      ? d
      : dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };
  if (start && end) return `${fmt(start)} – ${fmt(end)}`;
  if (start) return fmt(start);
  if (end) return fmt(end);
  return null;
}
