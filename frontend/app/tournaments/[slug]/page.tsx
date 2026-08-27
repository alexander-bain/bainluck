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
 * board -> more predictions, with the playoff grid one tab away.
 *
 * ═══ UX-P145: THERE IS A DESKTOP NOW ═══
 *
 * Alex, on the live page in a desktop browser: "weirdly narrow, like we only
 * made a mobile version." He was reading the code correctly. Every element
 * above lived inside one `max-w-[560px]` column, so a 1400px window rendered a
 * 560px phone in the middle of 840px of grey. Nothing was broken; there simply
 * was no desktop presentation, because every ruling from UX-P131 on was
 * verdicted off a 390px capture.
 *
 * What desktop is, here, and why it is not just a bigger number in the shell:
 *
 * 1. **The shell widens, the TEXT does not.** `SHELL` grows to 1280px at `xl`.
 *    Prose does not follow it — a 12px paragraph across 1200px is ~200
 *    characters a line and unreadable. Every prose block on these surfaces
 *    carries its own `max-w-[NNch]`, so the measure stays a measure while the
 *    page stops being a column. This is Alex's "sensible max-width for text
 *    sections only", applied where the text is rather than to the page.
 *
 * 2. **The Tournament tab becomes two columns at `lg`.** Left, the things you
 *    read down: the title-race chart and the match list. Right, the things you
 *    refer across to: results, the championship board, more predictions. This
 *    is what the vertical space buys — on a phone the board is thirty rows
 *    below the chart, and on a desktop it is beside it. The DOM order is
 *    unchanged from the mobile order, so the single-column stack below `lg` is
 *    exactly the page UX-P138 shipped and every prior ruling still holds.
 *
 * 3. **The Bracket tab takes the whole shell.** It is a grid; grids are what
 *    width is for. See `PlayoffGrid` for the sizing — the columns are CSS
 *    variables now, so P138's ruling 5 (wide rounds scroll) keeps applying on
 *    the phone it was written for and stops applying in a 1400px window, where
 *    scrolling a five-column table is absurd.
 */

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import ErrorBoundary from "@/components/ErrorBoundary";
import ContenderChart from "@/components/tournament/ContenderChart";
import DrawToggle from "@/components/tournament/DrawToggle";
import { TOURNAMENT_COLUMNS, TOURNAMENT_SHELL } from "@/components/tournament/layout";
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
import { readPlayoffGrid } from "@/lib/playoffGrid";
import { slateNotice } from "@/lib/slate";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import TournamentProps from "@/components/tournament/TournamentProps";
import TournamentResults from "@/components/tournament/TournamentResults";
import { TOURNAMENT_PROPS_ENABLED } from "@/lib/tournamentFlags";
import { fetchTournament } from "@/lib/api";
import type { TournamentPayload } from "@/lib/tournament";

type Tab = "tournament" | "bracket";

const TABS: { id: Tab; label: string }[] = [
  { id: "tournament", label: "Tournament" },
  { id: "bracket", label: "Bracket" },
];

/**
 * `TOURNAMENT_SHELL` / `TOURNAMENT_COLUMNS` live in
 * `components/tournament/layout.ts`, not here — a route file may not carry
 * named exports (Next's generated page types fail the typecheck gate on them),
 * and Tailwind only scans `app/` and `components/` for class text. The reasons
 * are written out in full at the top of that module.
 */

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

  /**
   * Players × rounds — read, not built (UX-P139, Alex's amendment).
   *
   * UX-P138 assembled this here from three payload sections. The amendment
   * makes cell provenance a correctness property — "the grid reads only the
   * register" — and a client stitching cells out of the match list, the props
   * and the board cannot be held to that, however careful it is. So the grid
   * arrives whole from `backend/app/utils/tournament_grid.py`, which walks the
   * register's `reaches` and nothing else, and this is a typed read.
   */
  const grid = useMemo(
    () => readPlayoffGrid(data?.grids?.[draw]),
    [data, draw]
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
      <div className={TOURNAMENT_SHELL} data-testid="tournament-shell">
        <header className="border-b border-surface-border bg-surface-card px-4 pb-3 pt-4 lg:px-6 lg:pb-4 lg:pt-6">
          <h1 className="text-2xl font-bold leading-tight tracking-tight text-text-primary lg:text-[32px]">
            {data.title}
          </h1>
          <p className="mt-0.5 max-w-[70ch] text-[13px] text-text-secondary lg:text-[14.5px]">
            {data.subtitle}
          </p>
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
          <DrawToggle
            draw={draw}
            onSelect={(id) => {
              setDraw(id);
              setSelection(null);
            }}
          />
        )}

        <div className="px-4 pb-16 lg:px-6">
          {tab === "tournament" && (
            /**
             * TWO COLUMNS AT `lg`, ONE BELOW IT (UX-P145).
             *
             * The DOM order is the mobile order, unchanged: chart, matches,
             * results, board, more predictions. Below `lg` the wrappers are
             * inert `div`s and the page stacks exactly as UX-P138 shipped it,
             * so no ruling verdicted on a 390px capture is disturbed.
             */
            <div className={TOURNAMENT_COLUMNS} data-testid="tournament-columns">
              {/* READ-DOWN COLUMN: the title race, then the day's card. */}
              <div className="lg:min-w-0">
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
                  /**
                   * UX-P145: this used to end "…and the draw fills them in on
                   * Thursday." A weekday hard-coded in a component is true for
                   * one week a year; the draw was made on 2026-08-27 and the
                   * sentence was live and wrong the same afternoon. It reads
                   * the payload's own label now, so being right is a data
                   * property rather than a deploy.
                   */
                  emptyHint={
                    data.draw_released || !data.main_draw_label
                      ? "Nothing is on right now. Matches appear here as they are scheduled."
                      : `Nothing is on right now. Matches appear here as they are scheduled, and the draw fills them in ${data.main_draw_label}.`
                  }
                />
              </div>

              {/* REFER-ACROSS COLUMN: what just happened, the standings, the
                  extras. On a phone these are thirty rows below the chart; the
                  whole point of a desktop is that they are beside it. */}
              <div className="lg:min-w-0">
                {/* FINISHED MATCHES, WITH THE SCORE (UX-P139, item 9). Below the
                    day's card and above the board: what just happened is worth
                    less than what is on now and more than the season-long title
                    race. Its data is ESPN's, which is stated on the section. */}
                <TournamentResults results={data.results} draw={draw} />

                {board && <TournamentBoard board={board} seriesColors={seriesColors} />}

                {/* Gated by INT-131 (Alex product call 2026-08-26): CERT-411
                    BLOCK is scoped to TournamentProps — a fresh leader beside a
                    stale runner renders data-live=true against a server
                    data-price-state=dark. Boards passed. See
                    lib/tournamentFlags.ts.

                    MEASURED 2026-08-27 (UX-P145): the flag is ON in production.
                    The shipped bundle folds the guard away and renders this
                    section unconditionally, which is how Alex read its copy on
                    the live page. The finding is therefore reachable by users
                    today. Flipping a production env var is not this lane's
                    call, so it is an Alex-ask, not a commit. */}
                {TOURNAMENT_PROPS_ENABLED && (
                  <TournamentProps markets={data.props ?? []} draw={draw} />
                )}
              </div>
            </div>
          )}

          {tab === "bracket" && (
            <div className="mt-6">
              {/* THE PLAYOFF GRID (UX-P139). It no longer waits for the draw:
                  its cells come from round-advancement markets that are live
                  and priced today, so withholding a fully-priced grid until a
                  ceremony would break the "never an empty page when tradeable
                  truth exists" rule. The ceremony changes what the rows are
                  ordered by, not whether there is a grid. */}
              <TournamentBracket
                grid={grid}
                drawReleased={data.draw_released}
                preDrawBoards={data.boards}
                drawLabel={board?.label}
                drawReleaseLabel={data.draw_release_label}
                mainDrawLabel={data.main_draw_label}
              />
            </div>
          )}
        </div>

        {/* UX-P145: "Probabilities blended across prediction markets" — *blend*
            is our word for our own aggregation step, and a reader has no reason
            to know it. The `max-w-[74ch]` is the other half of the desktop
            work: at 1280px this line would otherwise run the full shell. */}
        <footer className="border-t border-surface-border px-4 py-5 text-[11.5px] leading-relaxed text-text-muted lg:px-6">
          <span className="block max-w-[74ch]">
            Each probability combines what several prediction markets are saying. Trend
            lines are daily readings on a fixed 0&ndash;100 scale, with no smoothing.
          </span>
        </footer>
      </div>
    </ErrorBoundary>
  );
}
