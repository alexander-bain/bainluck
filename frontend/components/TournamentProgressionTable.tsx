"use client";

import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { useAnalytics } from "@/hooks/useAnalytics";
import type { ProgressionResponse, ProgressionParticipant, ProgressionStage } from "@/lib/types";
import type { ProgressionCellStatus } from "@/lib/gridCellState";
import { GRID_CELL_TERMINAL_GLYPH, progressionSortValue } from "@/lib/gridCellState";
import { isPersonFieldDomain, isLikelyPersonName } from "@/lib/eventConceptDisplay";
import { legendName } from "@/lib/contenderChart";
import { probabilityCellText } from "@/lib/probabilityCellText";
import TeamNameLink from "./TeamNameLink";

interface TournamentProgressionTableProps {
  data: ProgressionResponse;
  /** Show team logos in the first column */
  showLogos?: boolean;
  /** Callback when hovering a participant row */
  onHoverParticipant?: (name: string | null) => void;
  /** Page type for analytics (e.g. "futures_detail", "golf") */
  pageType?: string;
  className?: string;
}

type SortConfig = {
  stageKey: string | null; // null = sort by name
  direction: "asc" | "desc";
};

/**
 * Smallest scale denominator (#4261). A table whose numbers are all noise-level
 * must not draw a full-width bar just because 0.4% is the widest it has.
 */
export const BAR_SCALE_FLOOR = 0.01;

/**
 * Compute inline data bar width as a percentage (0-100).
 *
 * Width is PROPORTIONAL to probability, against `scaleMax` — the widest live
 * number in THIS table — because the card's caption says "Bar width =
 * probability" and that has to be literally true.
 *
 * Two things it is deliberately not (#4261):
 *
 * - not scaled against a constant. It used to be `sqrt(p)/sqrt(0.4)`, a
 *   hardcoded column max of 40%, so every probability at or above 0.4 clamped
 *   to a full-width bar. Golf's "Make Cut" column runs 55-90%, so all forty
 *   rows drew the identical slab. Square root alone does not fix that: against
 *   this table's own max it still renders 87% and 66% at 100% and 87% of the
 *   cell, which on a phone is the same complaint back again.
 * - not scaled per column. The golf columns nest (make cut ⊇ top 20 ⊇ … ⊇
 *   win), so a row reads as a funnel; normalising each column to its own
 *   leader would draw McIlroy's 12% win as wide as his 87% make-cut and erase
 *   the only thing the row says.
 */
export function barWidth(probability: number | null, scaleMax: number): number {
  if (probability === null || probability === undefined || probability <= 0) return 0;
  const denom = Math.max(scaleMax, BAR_SCALE_FLOOR);
  return Math.min(100, (probability / denom) * 100);
}

/**
 * Phone-width display name for a participant (#4309).
 *
 * The name column is capped at 104px on a phone — that cap is what makes the
 * Make Cut bars render whole (#4261) and it is not negotiable. At 14px Inter it
 * fits about twelve characters, so a full golfer name overflows and `truncate`
 * eats the END of it. That is the worst possible half to lose: the live Amgen
 * Irish Open field showed `Rasmus Hojg…` and `Nicolai Hojga…` three rows apart,
 * two different people rendered as the same unreadable stub.
 *
 * In golf the SURNAME is the identity and the given name is the disambiguator,
 * so spend the 104px on the surname and keep the given name as an initial:
 * `R. Hojgaard` / `N. Hojgaard`. Measured against the live field, that fits 12
 * of the 13 names that truncate today, and the 13th
 * (`R. Neergaard-Petersen`, 151.77px) still keeps a unique readable surname
 * prefix, which the current rendering does not.
 *
 * TWO GATES, both borrowed rather than invented, because this component is not
 * golf-only and "abbreviate the first word" is actively wrong for a team:
 *
 *  - `isPersonFieldDomain` — the row is a person at all. Without it,
 *    `Kansas City Chiefs` becomes `K. City Chiefs`.
 *  - `isLikelyPersonName` — THIS row is a person, not a market outcome. The
 *    domain gate is necessary and not sufficient (its own docstring says so):
 *    on a person-field domain the rows can still read `Over 16.5 games`, and
 *    `O. 16.5 games` would be gibberish. It also, usefully, leaves synthetic
 *    fixture rows like `Golfer 1` alone — they carry a digit.
 *
 * Returns the name UNCHANGED whenever either gate fails or there is nothing to
 * abbreviate, and callers rely on that: an unchanged string means render the
 * plain single text node exactly as before.
 */
export function progressionDisplayName(
  name: string,
  sport: string | null | undefined,
): string {
  if (!isPersonFieldDomain(sport)) return name;
  if (!isLikelyPersonName(name)) return name;
  return legendName(name);
}

/** Fractional layout slack. Smaller than a pixel, so it cannot hide a column. */
const SUBPIXEL_PX = 0.5;

/**
 * Where the scroller must sit for the SORTED column to be readable (#7192).
 *
 * The grid is a leaderboard ordered by its rightmost column, and the rightmost
 * column is the first thing a phone clips. Measured on production at 390px
 * (scroller clientWidth 316) the day this shipped:
 *
 *     grid  cols  overflow  sort column       visible at scrollLeft 0
 *     mlb    4     271px    `World Series ▼`  no
 *     nfl    4     240px    `Super Bowl ▼`    no
 *     mls    2      51px    `MLS Cup ▼`       no
 *
 * So MLB asserted a ranking of 30 teams and showed the reader a leading column
 * (`Make Playoffs`: 100 100 99 89 65 77 44 10) that visibly contradicted it,
 * with nothing on screen to explain the order. #6722 deleted the table's pixel
 * floor and fixed the one-column grids; it cannot help here, because the four
 * columns genuinely need 587px and no allocation of them fits in 316.
 *
 * If the columns cannot all fit, the one that must be on screen is the one the
 * order comes from — so the scroller opens aligned to it. The `#` and `Team`
 * cells are `position: sticky`, so scrolling right costs the reader nothing:
 * they keep the row's identity and gain the number that ranks it.
 *
 * This is pure arithmetic, deliberately: jsdom reports every rect, `clientWidth`
 * and `scrollWidth` as 0 (#6722's suite says so), so an effect that read the DOM
 * directly could only be guarded by a test that never ran. All coordinates are
 * in the scroller's CLIENT box — `rect.left - scrollerRect.left` — which is what
 * `tools/progression-col-fit-6722.mjs` prints.
 *
 * @param stickyRight right edge of the sticky `Team` cell; content to the left
 *   of it is underneath that cell, which is hidden, not visible.
 * @returns the scrollLeft to set, or `null` when nothing should move — there is
 *   no overflow (every desktop), or the column is already wholly readable.
 */
export function sortColumnScrollLeft({
  colLeft,
  colRight,
  clientWidth,
  scrollLeft,
  stickyRight,
}: {
  colLeft: number;
  colRight: number;
  clientWidth: number;
  scrollLeft: number;
  stickyRight: number;
}): number | null {
  // THREE THINGS THAT LOOK LOAD-BEARING AND ARE NOT. Each was written, mutated,
  // and deleted when its mutant survived — a guard whose removal changes no
  // answer is a safety net nobody is standing under:
  //
  //  - an "is there overflow?" early return. A column can only be past the right
  //    edge if the content is wider than the box, which IS overflow; a grid that
  //    fits leaves by the "already readable" door below. Every desktop takes it.
  //  - a rect sanity check. An unmeasured box (jsdom: every rect 0) or a NaN
  //    fails both comparisons and leaves by that same door.
  //  - an UPPER clamp to `scrollWidth - clientWidth`. The column is part of the
  //    content, so the offset that puts its right edge on the container's right
  //    edge cannot exceed the content's own scrollable width. Dropping it also
  //    drops `scrollWidth` from what the caller has to measure.
  //
  // The LOWER clamp is different and is kept: sorting by an early stage asks to
  // scroll to a negative offset, because that column starts underneath the
  // sticky cell even at the very start of the table.
  const overRight = colRight - clientWidth;
  const underSticky = stickyRight - colLeft;

  // The minimum move that makes the column readable, in whichever direction it
  // is hiding. Below the tolerance nothing moves: fractional layout widths
  // leave a column a hair past an edge, and acting on that is a visible lurch
  // on every resize in exchange for half a pixel.
  let next: number;
  if (overRight > SUBPIXEL_PX) {
    next = scrollLeft + overRight;
  } else if (underSticky > SUBPIXEL_PX) {
    next = scrollLeft - underSticky;
  } else {
    return null; // already readable
  }

  next = Math.max(0, next);
  // The clamp can eat the whole move — `Make Playoffs` is 10.7px behind the
  // sticky cell at scrollLeft 0 and there is nowhere further left to go. Then
  // the honest answer is "nothing to do", not a write of the offset we are
  // already at.
  return Math.abs(next - scrollLeft) < SUBPIXEL_PX ? null : next;
}

/**
 * How much of a half-covered column is showing past the sticky cell (#7268).
 *
 * `sortColumnScrollLeft` solves for the sort column and has no term for the
 * column that lands STRADDLING the sticky cell's right edge. Its reasoning —
 * the columns to the left going under the sticky block "costs the reader
 * nothing" — is true of a column that goes WHOLLY under, and the offset it
 * picks rarely puts one there. Measured on production at 390px, every grid:
 *
 *     grid  straddling column  hidden  SHOWING  scroll slack
 *     nba   Conference             67       26             0
 *     nfl   Conference             71       22             4
 *     mlb   AL / NL Champ         101       13             5
 *     nhl   Conference             72       21             8
 *     mls   Conference             52       41             8
 *     epl   Top 4                  38       27             1
 *
 * Six of six. A 13-41px strip of a CENTRE-aligned wrapped cell is its right-hand
 * off-cuts with the numbers gone — `%`, `5.0`, `4h` stacked down all 20 rows,
 * and `4` (the tail of `Top 4`) floating in the header. It reads as rendering
 * damage, which is the defect: every value on the page is correct.
 *
 * WHY THIS IS NOT FIXED BY SCROLLING, which is the obvious reading and the one
 * #7268 proposed. The sort column is the RIGHTMOST column, so putting its right
 * edge on the container's right edge lands at (or within 8px of) the scroller's
 * own maximum — the `scroll slack` column above is the whole budget. Hiding the
 * straddler needs 13-41px of further travel that does not exist, and the other
 * direction — scrolling back until the straddler is whole — re-clips the sort
 * column by 31-59px, which is exactly the regression #7192 exists to prevent.
 * There is no offset that leaves every boundary outside the sticky cell. So the
 * fix is what we PAINT, not where we rest.
 *
 * The cue at this seam already understood the failure — its own comment names
 * the `%` and `24h` fragments — but it is a 32px GRADIENT, so across a 27px
 * sliver it is 16% opaque at the far end and merely greys the off-cuts. Opaque
 * across the straddler, then that same fade, and the seam reads as the identity
 * block being a little wider: the column is wholly hidden instead of half shown.
 *
 * Pure arithmetic for the same reason as `sortColumnScrollLeft`: jsdom reports
 * every rect as 0, so a guard on an effect that read the DOM could never run.
 * All coordinates are in the scroller's CLIENT box.
 *
 * @param cols every stage column's box; only one can cross a single x.
 * @param stickyRight right edge of the sticky `Team` cell.
 * @returns px to paint over, or 0 — no straddler, or nothing measured yet.
 */
export function stickyStraddleCover({
  cols,
  stickyRight,
}: {
  cols: { left: number; right: number }[];
  stickyRight: number;
}): number {
  // Both comparisons carry the tolerance, so a column resting exactly ON the
  // seam — the un-scrolled state of every grid, where the first stage column
  // begins where the sticky block ends — is not read as straddling it. An
  // unmeasured box (jsdom: every rect 0) fails the first test and returns 0,
  // which is the same answer as "nothing to cover".
  for (const col of cols) {
    if (col.left < stickyRight - SUBPIXEL_PX && col.right > stickyRight + SUBPIXEL_PX) {
      return col.right - stickyRight;
    }
  }
  return 0;
}


/**
 * Font weight / opacity class based on probability value.
 * Higher values get bolder text; very small values fade out.
 */
function probTextClass(probability: number | null, status?: ProgressionCellStatus): string {
  // Eliminated with no number left to strike renders the terminal glyph, so the
  // strike-through only applies where a legacy producer still supplies one.
  if (status === "eliminated") {
    return probability === null ? "text-red-400/60" : "text-red-400/60 line-through";
  }
  if (status === "clinched") return "text-emerald-600 font-bold";
  if (status === "missing" || status === "unavailable") return "text-text-secondary/40";
  if (probability === null) return "text-text-secondary/40";
  if (probability >= 0.10) return "text-text-primary font-semibold";
  if (probability >= 0.01) return "text-text-primary";
  return "text-text-secondary/50";
}

/**
 * Glyph + accessible name for a stage cell (L2-227).
 *
 * "Settled means settled": a clinched cell shows ✓, an eliminated cell shows ✕,
 * and neither ever shows a number. A cell with no market (missing) or one the
 * register cannot vouch for (unavailable) shows a muted em-dash — never 50%,
 * never a stale live-looking probability. The em-dash keeps the cell's
 * dimensions stable so a row cannot collapse.
 */
function cellDisplay(
  probability: number | null,
  status: ProgressionCellStatus,
): { text: string; label: string } {
  switch (status) {
    case "clinched":
      return { text: GRID_CELL_TERMINAL_GLYPH.clinched, label: "Clinched" };
    case "eliminated":
      // A legacy producer may still send a probability alongside the status;
      // keep showing it (struck through) rather than dropping information.
      return probability === null
        ? { text: GRID_CELL_TERMINAL_GLYPH.eliminated, label: "Eliminated" }
        : { text: formatProb(probability), label: "Eliminated" };
    case "missing":
      return { text: "—", label: "No market" };
    case "unavailable":
      return { text: "—", label: "Unavailable" };
    default:
      return {
        text: formatProb(probability),
        label: probability === null ? "No data" : "Live probability",
      };
  }
}

/**
 * Format probability for display in cells.
 * Shows percentage with appropriate precision.
 */
function formatProb(p: number | null): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return "—";
  // #7670: this function guarded its FLOOR (`<0.1%` rather than a `0%` that
  // claims impossibility) and rounded its CEILING, which claimed certainty for
  // the mirror reason — Boston printed `100%` at a served 0.9972, two rows
  // under clubs showing ✓ for actually having clinched. Both ends now live in
  // one place, shared with the grid's own renderer.
  return probabilityCellText(p);
}

/**
 * Change indicator (small triangle + delta).
 */
function ChangeIndicator({ change }: { change: number | null | undefined }) {
  if (!change || Math.abs(change) < 0.001) return null;
  const pct = change * 100;
  const isPositive = change > 0;
  return (
    <span
      className={`text-[10px] leading-none ${
        isPositive ? "text-emerald-400" : "text-red-400"
      }`}
      title={`${isPositive ? "+" : ""}${pct.toFixed(1)}% in 24h`}
    >
      {isPositive ? "▲" : "▼"}
      {Math.abs(pct) >= 1 ? Math.round(Math.abs(pct)) : Math.abs(pct).toFixed(1)}
      <span className="text-[8px] opacity-60 ml-px">24h</span>
    </span>
  );
}

const SOURCE_LABELS: Record<string, string> = {
  odds_api: "Sportsbooks",
  kalshi: "Kalshi",
  polymarket: "Poly",
  datagolf: "DG",
};

function SourceBreakdown({ sources }: { sources: { source: string; probability: number }[] }) {
  if (!sources || sources.length <= 1) return null;
  return (
    <div className="flex gap-1.5 justify-center mt-0.5">
      {sources.map((s) => {
        const pct = s.probability * 100;
        const label = SOURCE_LABELS[s.source] || s.source;
        const probStr = pct >= 10 ? `${Math.round(pct)}` : pct >= 1 ? pct.toFixed(1) : pct < 0.1 ? "<.1" : pct.toFixed(1);
        return (
          <span
            key={s.source}
            className="text-[9px] leading-none text-text-secondary/40 font-mono whitespace-nowrap"
            title={`${label}: ${pct >= 1 ? pct.toFixed(1) : pct.toFixed(2)}%`}
          >
            <span className="text-text-secondary/25">{label[0]}</span>{probStr}
          </span>
        );
      })}
    </div>
  );
}

export default function TournamentProgressionTable({
  data,
  showLogos = true,
  onHoverParticipant,
  pageType = "futures_detail",
  className,
}: TournamentProgressionTableProps) {
  const { track } = useAnalytics();
  const [sort, setSort] = useState<SortConfig>({
    stageKey: Array.isArray(data.stages) && data.stages.length > 0
      ? data.stages[data.stages.length - 1]?.key ?? null
      : null,
    direction: "desc",
  });

  // One poison row must not blank the table: drop entries that are not usable
  // objects instead of letting a `.name`/`.probabilities` access throw during
  // render (gotcha #42, applied to the grid surface).
  const safeParticipants = useMemo(
    () =>
      (Array.isArray(data.participants) ? data.participants : []).filter(
        (p): p is ProgressionParticipant =>
          !!p && typeof p === "object" && typeof p.name === "string",
      ),
    [data.participants],
  );

  const safeStages = useMemo(
    () =>
      (Array.isArray(data.stages) ? data.stages : []).filter(
        (s): s is ProgressionStage => !!s && typeof s === "object" && typeof s.key === "string",
      ),
    [data.stages],
  );

  const sortedParticipants = useMemo(() => {
    if (!safeParticipants.length) return [];

    return [...safeParticipants].sort((a, b) => {
      if (sort.stageKey === null) {
        const cmp = a.name.localeCompare(b.name);
        return sort.direction === "asc" ? cmp : -cmp;
      }
      // Terminal cells carry no probability, so sorting on the raw number would
      // file a clinched champion below a 0.1% longshot. Live cells are unchanged.
      const aVal = progressionSortValue(
        a.probabilities?.[sort.stageKey],
        a.status?.[sort.stageKey] ?? null,
      );
      const bVal = progressionSortValue(
        b.probabilities?.[sort.stageKey],
        b.status?.[sort.stageKey] ?? null,
      );
      const cmp = bVal - aVal;
      return sort.direction === "desc" ? cmp : -cmp;
    });
  }, [safeParticipants, sort]);

  const handleSort = useCallback((stageKey: string | null) => {
    setSort((prev) => {
      const newDirection =
        prev.stageKey === stageKey
          ? prev.direction === "desc" ? "asc" : "desc"
          : stageKey === null ? "asc" : "desc";

      const stageLabel = stageKey
        ? safeStages.find((s) => s.key === stageKey)?.label ?? stageKey
        : "name";

      track("progression_sort", {
        stage_key: stageKey ?? "name",
        stage_label: stageLabel,
        direction: newDirection,
        sport: data.sport,
        page_type: pageType,
      });

      return { stageKey, direction: newDirection };
    });
  }, [safeStages, data.sport, pageType, track]);

  const handleStageClick = useCallback((stage: ProgressionStage) => {
    if (!stage.market_id) return;
    track("progression_stage_click", {
      stage_key: stage.key,
      stage_label: stage.label,
      market_id: stage.market_id,
      sport: data.sport,
      page_type: pageType,
    });
  }, [data.sport, pageType, track]);

  // Find unique sources across all participants for column header labels
  const uniqueSources = useMemo(() => {
    const srcSet = new Set<string>();
    for (const p of safeParticipants) {
      for (const sources of Object.values(p.sources_data ?? {})) {
        for (const s of sources) srcSet.add(s.source);
      }
    }
    return Array.from(srcSet).sort();
  }, [safeParticipants]);

  const hasSources = uniqueSources.length > 1;

  // The widest live number in the table sets the bar scale (#4261). Resolved
  // columns draw no bar, so they cannot set it either.
  const barScaleMax = useMemo(() => {
    const liveKeys = safeStages.filter((s) => !s.resolved).map((s) => s.key);
    let max = 0;
    for (const p of safeParticipants) {
      for (const key of liveKeys) {
        const prob = p.probabilities?.[key];
        if (typeof prob === "number" && Number.isFinite(prob) && prob > max) max = prob;
      }
    }
    return max;
  }, [safeParticipants, safeStages]);

  // A phone shows one of golf's five stage columns and clips the header of the
  // next one; the container has always scrolled, but nothing said so (#4261).
  // The fade is drawn only while there is more table to the right, and only
  // over the HEADER row: measured on production, a fade down the full height
  // washed out the last 32px of every cell — which is exactly where the bars
  // differ, so the affordance erased the encoding it shipped beside.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const headRef = useRef<HTMLTableSectionElement | null>(null);
  const nameThRef = useRef<HTMLTableCellElement | null>(null);
  const stageThRefs = useRef(new Map<string, HTMLTableCellElement>());
  const alignedStageKey = useRef<string | null>(null);
  const readerScrolled = useRef(false);
  const selfScroll = useRef(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [headHeight, setHeadHeight] = useState(0);
  const [stickyEdge, setStickyEdge] = useState(0);
  const [leftBleedExposed, setLeftBleedExposed] = useState(false);
  const [straddleCover, setStraddleCover] = useState(0);
  // Whether the grid is still sitting where `alignSortColumn` put it (#7268).
  // True before anything has scrolled it, because nothing has moved it off the
  // alignment yet.
  const [restingOnAlignment, setRestingOnAlignment] = useState(true);

  const syncScrollAffordance = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollRight(el.scrollWidth - el.clientWidth - el.scrollLeft > 4);
    // Once the grid opens on its sort column (#7192) the columns a reader has
    // not seen are behind them, so the cue has to point both ways.
    setCanScrollLeft(el.scrollLeft > 4);
    // Deliberately `> 0` and not the cue's `> 4` (#7246). The cue is advice and
    // 4px of travel is not worth advising about; this one is a cover, and 4px of
    // a scrolled column showing past the card edge is the whole defect.
    setLeftBleedExposed(el.scrollLeft > 0);
    setHeadHeight(headRef.current?.getBoundingClientRect().height ?? 0);
    // Where the sticky `Team` cell ends, in THIS wrapper's coordinates. The
    // left-hand cue cannot sit on the container's edge the way the right one
    // does: the sticky cells are opaque and already cover it, so a fade there
    // would be painted under them and seen by nobody. It belongs at the seam
    // the hidden columns actually disappear behind. The `- 8` is the scroller's
    // own `-mx-2`.
    const scrollerLeft = el.getBoundingClientRect().left;
    const nameBox = nameThRef.current?.getBoundingClientRect();
    setStickyEdge(nameBox ? nameBox.right - scrollerLeft - 8 : 0);
    // And how much of a half-covered column is showing past that seam (#7268).
    setStraddleCover(
      stickyStraddleCover({
        cols: [...stageThRefs.current.values()].map((th) => {
          const box = th.getBoundingClientRect();
          return { left: box.left - scrollerLeft, right: box.right - scrollerLeft };
        }),
        stickyRight: nameBox ? nameBox.right - scrollerLeft : 0,
      }),
    );
  }, []);

  // Put the column the ranking comes from on screen (#7192).
  //
  // WHO IS ALLOWED TO MOVE THE TABLE, because "align it once at mount" is the
  // obvious rule and it is wrong in both directions:
  //
  //  - mount is too early. Measured against the local build with production
  //    data: the effect rested the scroller at 267px and the settled layout
  //    wanted 262.9 — the web font swapped under it. A 4px overshoot is
  //    harmless; the same lateness in the other direction re-clips the column
  //    this exists to show, and a mount-only rule can never notice.
  //  - and it must never re-assert itself over a reader. Someone who scrolls
  //    back to `Make Playoffs` is answering the question themselves.
  //
  // So: realign on any layout change until the reader scrolls, and after that
  // only when they pick a different column to sort by — which is a request for
  // that column, not a fight over this one.
  const alignSortColumn = useCallback(() => {
    const el = scrollRef.current;
    const key = sort.stageKey;
    if (!el || key === null) return;
    const th = stageThRefs.current.get(key);
    if (!th) return;
    const scrollerBox = el.getBoundingClientRect();
    const colBox = th.getBoundingClientRect();
    const nameBox = nameThRef.current?.getBoundingClientRect();
    const next = sortColumnScrollLeft({
      colLeft: colBox.left - scrollerBox.left,
      colRight: colBox.right - scrollerBox.left,
      clientWidth: el.clientWidth,
      scrollLeft: el.scrollLeft,
      stickyRight: nameBox ? nameBox.right - scrollerBox.left : 0,
    });
    alignedStageKey.current = key;
    // Whether or not it moves, the grid is now at the offset the alignment
    // endorses, which is the only position whose straddler may be covered
    // (#7268 — the cover's width is discontinuous, see the render).
    setRestingOnAlignment(true);
    if (next === null) return;
    // Claim the scroll event this assignment is about to fire, so the handler
    // does not read our own move as the reader taking over. It only ever fires
    // one, because the arithmetic returns null for a move it would not make.
    selfScroll.current = true;
    el.scrollLeft = next;
    syncScrollAffordance();
  }, [sort.stageKey, syncScrollAffordance]);

  const handleScroll = useCallback(() => {
    if (selfScroll.current) selfScroll.current = false;
    else {
      readerScrolled.current = true;
      setRestingOnAlignment(false);
    }
    syncScrollAffordance();
  }, [syncScrollAffordance]);

  useEffect(() => {
    syncScrollAffordance();
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      syncScrollAffordance();
      if (!readerScrolled.current) alignSortColumn();
    });
    observer.observe(el);
    // The scroller's own box does not change when a font swap widens the table
    // inside it, so the header row is observed too — it is the element whose
    // width tracks the content.
    if (headRef.current) observer.observe(headRef.current);
    return () => observer.disconnect();
  }, [syncScrollAffordance, alignSortColumn, safeStages.length, sortedParticipants.length]);

  useEffect(() => {
    if (alignedStageKey.current === sort.stageKey) return;
    alignSortColumn();
  }, [sort.stageKey, safeStages.length, sortedParticipants.length, alignSortColumn]);

  if (!safeStages.length || !safeParticipants.length) {
    return (
      <div className={`text-center text-text-secondary py-8 ${className || ""}`}>
        No multi-stage data available for this market.
      </div>
    );
  }

  const stagesAvailable = safeStages.length;
  const sportStageCount = _sportStageCount(data.sport);

  return (
    <div className={className}>
      {/* Tournament name header */}
      {data.tournament_name && (
        <h3 className="text-base font-semibold text-text-primary mb-1">
          {data.tournament_name}
        </h3>
      )}
      {/* Legends row: color + source */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-1.5">
        {/* Bar legend */}
        <div className="flex items-center gap-1 text-[10px] text-text-secondary/50">
          <span className="text-text-secondary/40">Bar width = probability</span>
        </div>
        {/* Source legend */}
        {hasSources && uniqueSources.length > 1 && (
          <p className="text-[10px] text-text-secondary/40">
            Sources: {uniqueSources.map((s) => `${(SOURCE_LABELS[s] || s)[0]}=${SOURCE_LABELS[s] || s}`).join(", ")}
          </p>
        )}
      </div>
      {/* Stage coverage indicator */}
      {sportStageCount > stagesAvailable && (
        <p className="text-xs text-text-secondary mb-2">
          {stagesAvailable} of {sportStageCount} stages available
        </p>
      )}

      {/* Scrollable table container */}
      <div className="relative">
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="overflow-x-auto -mx-2 px-2"
        >
          {/* NO FIXED PIXEL FLOOR ON THIS TABLE (#6722). It carried
              `min-w-[500px]`, and a floor WIDER than the content does not
              protect the data columns — it hands them to the Team column.
              `table-layout: auto` distributes a table's surplus width across
              columns in proportion to their existing widths, and the sticky
              Team column is always the widest, so it takes the lion's share.
              Measured on production at 390px (scroller clientW=350):

                grid  cols  tableW  Team   first data col   row-1 numbers seen
                nfl    4     542    148px  x=199            2 of 4
                epl    3     500    182px  x=242            1 of 3
                mls    2     500    211px  x=271            1 of 2
                ucl    1     500    285px  x=345            0 of 1

              Team's natural width is 148px — the name span is already capped
              at `max-w-[104px]`. Every pixel above 148 is surplus the floor
              manufactured, and the fewer data columns there are the more of it
              lands on Team: +34 at three columns, +137 at one. At one column
              that puts `Champion` at x=345 against a visible edge of 370, so
              the Champions League grid asserted a ranking of 36 clubs and
              showed a reader no quantity and no column name at all.

              The floor was never what stopped columns cramping — auto layout
              cannot shrink a table below its min-content width, which is why
              NFL measures 542px at BOTH 320px and 390px with or without it.
              Removing it is therefore a no-op wherever the content already
              needs 500px (nfl: every field byte-identical) and a repair
              wherever it does not (ucl overflow 166 -> 0, mls 166 -> 17,
              epl 166 -> 69). Desktop is untouched: at 1280px the floor never
              bound. If a column ever does need a floor, give it to THAT
              column — a floor on the table is a floor on the widest cell. */}
          <table className="w-full border-collapse text-sm">
            <thead ref={headRef}>
              <tr className="border-b border-white/10">
                {/* Rank column */}
                {/* `min-w-[32px]` is not decoration and not a duplicate of
                    `w-8` (#7192). `w-8` is a HINT that `table-layout: auto`
                    discards when the table is already at its min-content width,
                    and the rank column measured 21.3px on production — while
                    `Team` beside it is pinned at `left-8`, i.e. 32px. Those two
                    numbers must be the SAME number or the sticky block has a
                    10.7px transparent slot in it, and the scrolled columns run
                    through the gap: opening the grid on its sort column made
                    that visible as fragments of `Division` between the rank and
                    the crest. A min-width is the one width declaration auto
                    layout may not discard. Keep it equal to `left-8` below. */}
                <th className="sticky left-0 z-10 bg-surface-card py-2 px-1 text-center text-text-secondary font-medium w-8 min-w-[32px]">
                  #
                </th>
                {/* Name column - sticky */}
                <th
                  ref={nameThRef}
                  className="sticky left-8 z-10 bg-surface-card py-2 px-2 text-left text-text-secondary font-medium cursor-pointer hover:text-text-primary transition-colors min-w-[92px] sm:min-w-[140px]"
                  onClick={() => handleSort(null)}
                >
                  <span className="flex items-center gap-1">
                    {data.sport === "golf" ? "Golfer" : "Team"}
                    {sort.stageKey === null && (
                      <SortArrow direction={sort.direction} />
                    )}
                  </span>
                </th>
                {/* Stage columns */}
                {safeStages.map((stage) => {
                  // Resolved (season-state decided) columns are de-emphasized so
                  // they no longer read as live probability bars (#927).
                  const isResolved = !!stage.resolved;
                  return (
                  <th
                    key={stage.key}
                    ref={(node) => {
                      if (node) stageThRefs.current.set(stage.key, node);
                      else stageThRefs.current.delete(stage.key);
                    }}
                    className={`py-2 px-2 text-center font-medium cursor-pointer transition-colors whitespace-nowrap ${isResolved ? "text-text-muted" : "text-text-secondary hover:text-text-primary"}`}
                    onClick={() => handleSort(stage.key)}
                  >
                    {stage.market_id ? (
                      <Link
                        href={`/futures/${stage.market_id}`}
                        className="hover:underline"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStageClick(stage);
                        }}
                      >
                        <span className="flex items-center justify-center gap-1">
                          {stage.label}
                          {sort.stageKey === stage.key && (
                            <SortArrow direction={sort.direction} />
                          )}
                        </span>
                      </Link>
                    ) : (
                      <span className="flex items-center justify-center gap-1">
                        {stage.label}
                        {sort.stageKey === stage.key && (
                          <SortArrow direction={sort.direction} />
                        )}
                      </span>
                    )}
                    {isResolved && (
                      <span className="block text-[9px] font-normal text-text-muted uppercase tracking-wide mt-0.5">
                        decided
                      </span>
                    )}
                  </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {sortedParticipants.map((participant, idx) => {
                const shortName = progressionDisplayName(participant.name, data.sport);
                return (
                <tr
                  key={participant.team_id ?? participant.name}
                  className="border-b border-white/5 hover:bg-white/5 transition-colors"
                  onMouseEnter={() => onHoverParticipant?.(participant.name)}
                  onMouseLeave={() => onHoverParticipant?.(null)}
                >
                  {/* Rank */}
                  <td className="sticky left-0 z-10 bg-surface-card py-1.5 px-1 text-center text-text-secondary text-xs min-w-[32px]">
                    {idx + 1}
                  </td>
                  {/* Name */}
                  <td className="sticky left-8 z-10 bg-surface-card py-1.5 px-2">
                    <div className="flex items-center gap-2">
                      {showLogos && participant.logo_url && (
                        <img
                          src={participant.logo_url}
                          alt=""
                          className="w-5 h-5 object-contain flex-shrink-0"
                          loading="lazy"
                        />
                      )}
                      {showLogos && !participant.logo_url && participant.primary_color && (
                        <span
                          className="w-5 h-5 rounded-full flex-shrink-0 inline-block"
                          style={{ backgroundColor: participant.primary_color }}
                        />
                      )}
                      {participant.seed != null && (
                        <span className="text-[10px] font-mono text-text-secondary/60 flex-shrink-0">
                          {participant.seed}
                        </span>
                      )}
                      {/* #4309 — the abbreviation is PHONE-ONLY. At `sm:` the cap
                          is 300px and every full name fits, so there is nothing to
                          buy by shortening it there. When the name is unchanged
                          (a team, a market outcome, a single word) this renders the
                          plain node it always did.

                          The full name is carried in `sr-only` at BOTH widths and
                          the two visible spans are `aria-hidden`, so a screen
                          reader still hears "Rasmus Hojgaard" on a phone. Reading
                          the abbreviation aloud would be a real regression:
                          truncation today is visual only, and assistive tech reads
                          the whole text node. */}
                      <TeamNameLink
                        name={participant.name}
                        sportKey={data.sport}
                        className="text-text-primary font-medium truncate max-w-[104px] sm:max-w-[300px] hover:underline"
                      >
                        {shortName === participant.name ? undefined : (
                          <>
                            <span className="sm:hidden" aria-hidden="true" data-testid="progression-name-short">
                              {shortName}
                            </span>
                            <span className="hidden sm:inline" aria-hidden="true">
                              {participant.name}
                            </span>
                            <span className="sr-only">{participant.name}</span>
                          </>
                        )}
                      </TeamNameLink>
                      {participant.record && (
                        <span className="text-[10px] text-text-secondary hidden sm:inline">
                          {participant.record}
                        </span>
                      )}
                    </div>
                  </td>
                  {/* Stage cells */}
                  {safeStages.map((stage) => {
                    // Every lookup is guarded: a participant missing one of these
                    // maps (poison payload, partial adapter) must render an empty
                    // cell, never throw and blank the whole table.
                    const prob = participant.probabilities?.[stage.key] ?? null;
                    const change = participant.changes_24h?.[stage.key];
                    const status = participant.status?.[stage.key] ?? null;
                    const sources = participant.sources_data?.[stage.key];
                    // Build tooltip with per-source values
                    const tooltip = sources?.length
                      ? sources.map((s) => {
                          const label = SOURCE_LABELS[s.source] || s.source;
                          const pct = s.probability * 100;
                          return `${label}: ${pct >= 1 ? pct.toFixed(1) : pct.toFixed(2)}%`;
                        }).join(" · ")
                      : undefined;
                    const isResolved = !!stage.resolved;
                    // Resolved columns: no live bar, no change indicator — a muted
                    // decided glyph (in@✓ / out@—) so it can't read as a live bar.
                    const bw = isResolved ? 0 : barWidth(prob, barScaleMax);
                    const display = cellDisplay(prob, status);
                    return (
                      <td
                        key={stage.key}
                        className="py-1.5 px-2 text-center relative"
                        title={isResolved ? "Decided" : (tooltip ?? display.label)}
                      >
                        {/* Inline data bar — scaled width, single-hue accent */}
                        {bw > 0 && (
                          <div
                            className="absolute inset-y-0 left-0 bg-blue-500/[0.08] transition-all"
                            style={{ width: `${bw}%` }}
                          />
                        )}
                        <div className="flex flex-col items-center relative">
                          {isResolved ? (
                            <span className="font-mono text-sm text-text-muted">
                              {prob != null && prob >= 0.5 ? "✓" : "—"}
                            </span>
                          ) : (
                            <>
                              <span
                                className={`font-mono text-sm ${probTextClass(prob, status)}`}
                                aria-label={display.label}
                                data-cell-state={status ?? "live"}
                              >
                                {display.text}
                              </span>
                              <SourceBreakdown sources={sources ?? []} />
                              <ChangeIndicator change={change} />
                            </>
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {/* The sticky block does not reach the card edge, and this is the 8px
            that proves it (#7246).

            `position: sticky; left: 0` pins to the scroller's CONTENT edge, not
            its padding edge, so the `#` cell's box starts at x=8 — the scroller's
            own `px-2` — and the strip at [0, 8] is covered by nothing. Measured
            at rest on production, /playoffs/mlb at 390px:

              cell            left   background   box in the scroller
              #  (sticky)     0px    #ffffff      [8, 40]
              Team (sticky)   32px   #ffffff      [40, 188]
              Make Playoffs   —      transparent  [-89, 19]

            so 11px of a scrolled-away header ran through the gap and a reader saw
            `fs` floating left of `#`, plus the pale-blue tail of a probability
            bar on rows that had one. It has been there since the sticky columns
            were written and was invisible while the grid rested at scrollLeft 0,
            because the slot sat over nothing. #7192 rests the grid mid-table,
            which is the first time anything has been behind it.

            WHY A COVER AND NOT A SMALLER PIN. The tempting fix is `left-[-8px]`
            on `#` with `left-[24px]` on `Team`, which makes the block pin at the
            padding edge. It also drags the rank and the crest 8px outside the
            page's content column the instant the reader scrolls — the names stop
            lining up with the heading above them. Geometry stays; the cover moves.

            NOT z-10. The sticky cells are, and they must keep winning: this is an
            extension of their background into the bleed, never something that can
            paint over them. It beats the bars (positioned, z-auto) on tree order.

            The three 2s — the scroller's `px-2`, this `w-2` and this `-left-2` —
            are one number and the guard reads them out of the classes. */}
        {leftBleedExposed && (
          <div
            aria-hidden="true"
            data-testid="progression-sticky-bleed-cover"
            className="pointer-events-none absolute inset-y-0 -left-2 w-2 bg-surface-card"
          />
        )}
        {/* -right-2 lands on the scroll container's own clip edge, which that
            container's -mx-2 puts 8px outside this wrapper. The height is the
            header row's, so the cue sits on the clipped column name and never
            over a bar. */}
        {canScrollRight && headHeight > 0 && (
          <div
            aria-hidden="true"
            data-testid="progression-scroll-affordance"
            style={{ height: headHeight }}
            className="pointer-events-none absolute top-0 -right-2 w-8 bg-gradient-to-l from-surface-card to-transparent"
          />
        )}
        {/* The mirror of it (#7192) — and deliberately NOT the same shape.
            The grid now opens scrolled to its sort column, so on a phone the
            earlier stages are the ones off-screen: behind the sticky Team cell
            rather than past the right edge. Without a cue on that side the
            reader is told about columns they have already seen and not about
            the ones they have not.
            FULL HEIGHT, where the right-hand cue is header-only. #4261 found
            that a full-height wash on the RIGHT erased the last 32px of every
            cell, which is where the bars differ — true, and it does not
            transfer. This seam is where a column is DISAPPEARING under the
            sticky block: what it washes is the tail of a column whose head is
            already hidden, which on MLS renders as `%` and `24h` fragments with
            no number attached. Header-only would leave those in the body. */}
        {/* And the column the cue is not enough for (#7268).

            The fade above is 32px wide and it is a FADE: across the 27px of
            `Top 4` that /playoffs/epl leaves showing it is 16% opaque at the far
            end, so the off-cuts are greyed and still legible as damage. Six of
            six grids land a column straddling this seam and no scroll offset
            avoids it — the arithmetic and the measured table are on
            `stickyStraddleCover`. So the seam gets an opaque extension the exact
            width of what is showing, and the fade moves out beyond it. A
            straddler is then wholly hidden rather than half shown, and the block
            reads as being a little wider.

            WIDTH 0 IS THE COMMON CASE and renders nothing: every desktop, and
            any grid whose columns happen to fall clear of the seam.

            ONLY WHILE THE GRID RESTS WHERE WE PUT IT. The width is discontinuous
            by nature — drag the straddler left and the cover grows with it, then
            the instant its left edge clears the seam the column is not straddling
            anything and the cover is 0, so a reader mid-drag would watch 65px of
            cover vanish and a whole column appear at once. That is worse than
            the defect. A reader who takes the scroller over gets an ordinary
            scroller; the landing state, which is what #7268 photographed and
            what nobody chose, gets the cover.

            NOT z-10, for the reason the bleed cover gives: the sticky cells are,
            and this must never paint over them. */}
        {canScrollLeft && stickyEdge > 0 && restingOnAlignment && straddleCover > 0 && (
          <div
            aria-hidden="true"
            data-testid="progression-straddle-cover"
            style={{ left: stickyEdge, width: straddleCover }}
            className="pointer-events-none absolute inset-y-0 bg-surface-card"
          />
        )}
        {canScrollLeft && stickyEdge > 0 && (
          <div
            aria-hidden="true"
            data-testid="progression-scroll-affordance-left"
            style={{ left: stickyEdge + (restingOnAlignment ? straddleCover : 0) }}
            className="pointer-events-none absolute inset-y-0 w-8 bg-gradient-to-r from-surface-card to-transparent"
          />
        )}
      </div>
    </div>
  );
}

function SortArrow({ direction }: { direction: "asc" | "desc" }) {
  return (
    <span className="text-[10px] text-blue-400">
      {direction === "desc" ? "▼" : "▲"}
    </span>
  );
}

/**
 * Total possible stages for a sport (for "X of Y stages" indicator).
 */
function _sportStageCount(sport: string): number {
  const counts: Record<string, number> = {
    golf: 5,
    football: 4,
    basketball: 3,
    baseball: 4,
    hockey: 4,
    soccer: 2,
    tennis: 2,
  };
  return counts[sport] ?? 0;
}
