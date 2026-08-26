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
 * The page is therefore: pills -> today's matches -> championship chart+board
 * -> props, with the bracket one tab away.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import ErrorBoundary from "@/components/ErrorBoundary";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import { buildBracket } from "@/lib/bracket";
import TournamentSlate from "@/components/tournament/TournamentSlate";
import TournamentProps from "@/components/tournament/TournamentProps";
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

        {tab === "tournament" && (
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
                onClick={() => setDraw(entry.id)}
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
              {/* TODAY LEADS. Alex took direction B's ordering: the day's
                  matches are the first thing on the page, because they are the
                  half with live prices and the reason to open it on a match
                  day. The championship board follows. */}
              <TournamentSlate
                slate={
                  data.slate ?? {
                    matches: [],
                    count: 0,
                    incoherent: 0,
                    dropped: {},
                    price_state: "dark",
                    newest_observed_at: null,
                    age_hours: null,
                    dark_after_hours: 48,
                  }
                }
                draw={draw}
                broadcasts={data.broadcasts}
              />

              {data.boards
                .filter((board) => board.draw === draw)
                .map((board) => (
                  <TournamentBoard key={board.draw} board={board} />
                ))}

              <TournamentProps markets={data.props ?? []} draw={draw} />
            </>
          )}

          {tab === "bracket" && (
            <div className="mt-6">
              {/* THE FIXTURE SWAP (UX-P134): built from the register's own
                  draw slots, so the ceremony is a data change and not a
                  deploy. Empty until `draw_released` latches, at which point
                  this fills without anything here changing. */}
              <TournamentBracket
                rounds={buildBracket(data.bracket?.[draw] ?? [])}
                drawReleased={data.draw_released}
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
