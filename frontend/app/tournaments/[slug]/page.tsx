"use client";

/**
 * /tournaments/{slug} — the US Open hub (UX-P131, Day 2 of the charter).
 *
 * LAYOUT DIRECTION C, "Split Story", chosen by this lane from the three Day-1
 * mocks (`docs/mocks/us-open/`). Alex's verdict on the mocks may re-skin this;
 * it should not need to restructure it. Why C:
 *
 *   - It shows BOTH DRAWS on one scroll, which is what the directive asks for.
 *     Direction A's toggle hides one draw behind a tap.
 *   - The bracket gets its OWN TAB, so it can never displace the boards. That
 *     is the charter amendment's safety property expressed as layout rather
 *     than as good intentions.
 *   - Days 3-5 land ADDITIVELY: the slate fills the Today tab, the real draw
 *     fills the Bracket tab, and neither move touches the Title tab. Direction
 *     B, by contrast, structures the whole page around the slate leading —
 *     which is a bet on #2199 never being fixed, and #2199 is being fixed in
 *     another lane right now.
 *
 * UX-P132 (Day 3) built the slate additively as designed, and then applied
 * ALEX'S MOCK VERDICT, which re-skins the layout above. The verdict, and what
 * changed here:
 *
 *   1. **C stays the base, but takes A's pill toggle everywhere** — and NEVER
 *      two stacked gender lists. One `draw` pill now flips the slate, the
 *      chart and the contender list together, so only one draw is on screen at
 *      a time.
 *   2. **B's ordering: today's matches lead the page.** The Today tab is gone
 *      as a tab; the slate is the first thing under the pills. It is the half
 *      with live prices, so it is the half worth opening the page for.
 *   3. The Bracket keeps its own tab. That was C's safety property — the
 *      bracket can never displace the boards — and the verdict did not
 *      overrule it, so it stands.
 *
 * UX-P137 (Alex's rulings on the Day-5 artifacts) moved two things and left
 * the structure alone:
 *
 *   6. **The chart is now the first thing under the pills**, above the day's
 *      matches. It used to live inside `TournamentBoard`, below the slate, so
 *      on a full match day the title race was thirty rows down the page. The
 *      reader also picks which lines it draws now, so the SELECTION lives here
 *      rather than in the chart: the board's colour tie-in has to follow the
 *      same choice, and two components each holding their own idea of "the top
 *      three" would drift the moment the reader touched either.
 *
 *   1. **The Bracket tab is not empty before the draw.** It gets both boards,
 *      unfiltered by the gender pill, because the winner markets are the
 *      tradeable truth about this tournament on the day before a ceremony.
 *
 * UX-P138 (Alex's STRUCTURAL RULING 4) re-divides the two tabs, and this is
 * the biggest change the page has taken since it was built:
 *
 *   **Tournament tab = the MATCH LIST with round pills.**
 *   **Bracket tab = the PLAYOFF GRID — players × rounds.**
 *
 * The defect it fixes is that the page had TWO match lists. The slate lived
 * here and the bracket's match cards lived one tab over, and nothing told the
 * reader why they were different lists or which one to trust — because they
 * never were different. They were the same fixtures, split by which pipeline
 * produced them. `lib/matchList.ts` joins them into one; a draw position that
 * also appears in the slate absorbs it, so a main-draw afternoon renders each
 * match once instead of twice.
 *
 * The Bracket tab then gets the question a tree is actually read for — how far
 * does this player get — as a grid whose every cell is a market's answer to
 * exactly its own column. Nothing in it is chained or simulated; see
 * `lib/playoffGrid.ts` for why that constraint is the whole design.
 *
 * The page is therefore: pills -> chart -> the match list -> championship
 * board -> curated questions, with the playoff grid one tab away.
 */

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import ErrorBoundary from "@/components/ErrorBoundary";
import ContenderChart from "@/components/tournament/ContenderChart";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import { buildBracket, prematchFromSlate } from "@/lib/bracket";
import {
  chartSeriesFor,
  defaultSelection,
  seriesColorByEntity,
  toggleSelection,
} from "@/lib/contenderChart";
import { buildMatchList, type TitleChances } from "@/lib/matchList";
import { buildPlayoffGrid } from "@/lib/playoffGrid";
import { slateNotice } from "@/lib/slate";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import TournamentProps from "@/components/tournament/TournamentProps";
import { TOURNAMENT_PROPS_ENABLED } from "@/lib/tournamentFlags";
import { fetchTournament } from "@/lib/api";
import type { TournamentPayload } from "@/lib/tournament";

type Tab = "tournament" | "bracket";

const TABS: { id: Tab; label: string }[] = [
  { id: "tournament", label: "Tournament" },
  { id: "bracket", label: "Bracket" },
];

/**
 * The gender pill. Alex's verdict: take direction A's toggle EVERYWHERE, and
 * never two stacked gender lists. One toggle flips the slate, the chart and the
 * contender list together, so the page only ever shows one draw at a time and
 * the reader never scrolls one draw to reach the other.
 */
const DRAWS: { id: string; label: string }[] = [
  { id: "mens-singles", label: "Men's" },
  { id: "womens-singles", label: "Women's" },
];

export default function TournamentPage() {
  const params = useParams();
  const slug = typeof params?.slug === "string" ? params.slug : "";

  usePageTracking({ pageType: "tournament", pageTitle: `Tournament: ${slug}` });
  useScrollDepth({ pageType: "tournament" });
  useEngagementTime({ pageType: "tournament" });

  const [data, setData] = useState<TournamentPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("tournament");
  const [draw, setDraw] = useState<string>("mens-singles");
  /**
   * The chart's chosen contenders, or `null` for "whatever the default is".
   *
   * `null` rather than the computed top three so the default follows the data
   * when the board re-ranks — pinning three entity keys at first render would
   * quietly freeze the chart on yesterday's leaders. Resets on a draw change,
   * because a men's selection means nothing in the women's field.
   */
  const [selection, setSelection] = useState<string[] | null>(null);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchTournament(slug)
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        // No partial page assembled from whatever loaded. A tournament hub that
        // half-renders is worse than one that says it could not load.
        if (!cancelled) setError("We could not load this tournament right now.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [slug]);

  // Everything derived, computed BEFORE the loading/error returns so the hook
  // order never changes between renders. Each guards on `data` being null
  // rather than being moved below the returns.
  const board = useMemo(
    () => data?.boards.find((entry) => entry.draw === draw) ?? null,
    [data, draw]
  );

  const selectionKeys = useMemo(
    () => selection ?? (board ? defaultSelection(board.rows) : []),
    [selection, board]
  );

  /** Chart colour per contender, so the board's name underline follows the picker. */
  const seriesColors = useMemo(
    () => (board ? seriesColorByEntity(chartSeriesFor(board.rows, selectionKeys)) : {}),
    [board, selectionKeys]
  );

  const rounds = useMemo(() => buildBracket(data?.bracket?.[draw] ?? []), [data, draw]);

  /**
   * Pre-match prices for decided bracket matches (UX-P137, ruling 3), joined
   * off the slate the page already has. No extra request: the slate is in the
   * same payload, and a decided match's two names are the only join key either
   * side shares.
   */
  const prematch = useMemo(
    () => prematchFromSlate(data?.slate?.matches ?? [], rounds),
    [data, rounds]
  );

  /**
   * Title chances by entity, read off the BOARD.
   *
   * The board is where this number is published, so it is the board's copy the
   * match list's chip and the grid's last column both read. The draw slot
   * carries its own copy and it is only a fallback — two surfaces printing
   * different values for one question is the divergence bug, not a feature
   * (standing Alex ruling: the blend is the product).
   */
  const titleChances = useMemo<TitleChances>(() => {
    const out: TitleChances = {};
    for (const row of board?.rows ?? []) out[row.entity_key] = row.probability;
    return out;
  }, [board]);

  /** ONE match list (ruling 4) — the draw where we have it, the slate where we do not. */
  const matches = useMemo(
    () =>
      buildMatchList({
        slate: (data?.slate?.matches ?? []).filter((match) => match.draw === draw),
        rounds,
        prematch,
        titleChances,
        broadcasts: data?.broadcasts,
      }),
    [data, draw, rounds, prematch, titleChances]
  );

  /** Players × rounds (ruling 4). Every cell a price; nothing derived. */
  const grid = useMemo(
    () =>
      buildPlayoffGrid({
        board,
        propMarkets: data?.props ?? [],
        matches,
        draw,
      }),
    [board, data, matches, draw]
  );

  if (loading) {
    return (
      <div className="mx-auto max-w-[560px] px-4 py-10 text-center text-text-secondary">
        Loading…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-[560px] px-4 py-10 text-center">
        <h1 className="text-lg font-semibold text-text-primary">Tournament unavailable</h1>
        <p className="mt-1 text-sm text-text-secondary">{error ?? "Nothing to show."}</p>
      </div>
    );
  }

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h2>Something went wrong</h2>
        </div>
      }
    >
      <div className="mx-auto max-w-[560px]">
        <header className="border-b border-surface-border bg-surface-card px-4 pb-3 pt-4">
          <h1 className="text-2xl font-bold leading-tight tracking-tight text-text-primary">
            {data.title}
          </h1>
          <p className="mt-0.5 text-[13px] text-text-secondary">{data.subtitle}</p>
        </header>

        <div className="flex border-b border-surface-border bg-surface-card" role="tablist">
          {TABS.map((entry) => (
            <button
              key={entry.id}
              role="tab"
              type="button"
              aria-selected={tab === entry.id}
              onClick={() => setTab(entry.id)}
              className={`flex-1 border-b-2 py-3 text-[13.5px] font-semibold ${
                tab === entry.id
                  ? "border-text-primary text-text-primary"
                  : "border-transparent text-text-muted"
              }`}
            >
              {entry.label}
            </button>
          ))}
        </div>

        {/* The gender pill shows on the Bracket tab too once the draw exists,
            because the grid is one draw's field — but NOT before it, where
            ruling 1 deliberately shows both boards unfiltered and a pill would
            offer to filter something that is not filtered. */}
        {(tab === "tournament" || data.draw_released) && (
          <div
            className="flex gap-1.5 border-b border-surface-border bg-surface-card px-4 pb-3"
            role="group"
            aria-label="Draw"
            data-testid="draw-toggle"
          >
            {DRAWS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                aria-pressed={draw === entry.id}
                onClick={() => {
                  setDraw(entry.id);
                  setSelection(null);
                }}
                data-testid="draw-pill"
                data-draw={entry.id}
                data-active={draw === entry.id ? "true" : "false"}
                className={`rounded-full px-3.5 py-1.5 text-[13px] font-semibold ${
                  draw === entry.id
                    ? "bg-text-primary text-text-inverse"
                    : "bg-surface-elevated text-text-secondary"
                }`}
              >
                {entry.label}
              </button>
            ))}
          </div>
        )}

        <div className="px-4 pb-16">
          {tab === "tournament" && (
            <>
              {/* THE CHART LEADS (ruling 6). The title race is what this page
                  is about; it was previously below thirty match rows. */}
              {board && (
                <ContenderChart
                  rows={board.rows}
                  draw={board.draw}
                  selection={selectionKeys}
                  onToggle={(key) =>
                    setSelection(toggleSelection(selectionKeys, key))
                  }
                  onReset={() => setSelection(null)}
                />
              )}

              {/* THEN THE MATCH LIST (ruling 4), with round pills. Alex took
                  direction B's ordering at UX-P132 — matches are the half with
                  live prices and the reason to open the page on a match day —
                  and ruling 4 promotes this from "today's matches" to the
                  tournament's matches. The championship board follows. */}
              <TournamentMatches
                entries={matches}
                notice={data.slate ? slateNotice(data.slate) : null}
                emptyHint="Nothing is on right now. Matches appear here as they are scheduled, and the draw fills them in on Thursday."
              />

              {board && <TournamentBoard board={board} seriesColors={seriesColors} />}

              {/* OFF since INT-131 (Alex product call 2026-08-26): CERT-411
                  BLOCK is scoped to TournamentProps — a fresh leader beside a
                  stale runner renders data-live=true against a server
                  data-price-state=dark. Boards passed; props re-enable when its
                  fix certs. See lib/tournamentFlags.ts. */}
              {TOURNAMENT_PROPS_ENABLED && (
                <TournamentProps markets={data.props ?? []} draw={draw} />
              )}
            </>
          )}

          {tab === "bracket" && (
            <div className="mt-6">
              {/* THE PLAYOFF GRID (UX-P138, ruling 4) — and before the draw,
                  BOTH winner boards rather than an empty tab (UX-P137, ruling
                  1). The ceremony stays a DATA change and not a deploy: the
                  grid's rows are the board's, so it renders the moment
                  `draw_released` latches and prices arrive, with nothing here
                  changing. */}
              <TournamentBracket
                grid={grid}
                drawReleased={data.draw_released}
                preDrawBoards={data.boards}
                drawLabel={board?.label}
              />
            </div>
          )}
        </div>

        <footer className="border-t border-surface-border px-4 py-5 text-[11.5px] leading-relaxed text-text-muted">
          Probabilities blended across prediction markets. Trend lines are unsmoothed daily
          readings on a fixed 0&ndash;100 scale.
        </footer>
      </div>
    </ErrorBoundary>
  );
}
