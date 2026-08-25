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
 * The Title tab is the landing tab, so the championship boards are still the
 * first thing on screen. That keeps the charter's ship order (boards are layer
 * 1) without hiding the live half.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import ErrorBoundary from "@/components/ErrorBoundary";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import { fetchTournament } from "@/lib/api";
import type { TournamentPayload } from "@/lib/tournament";

type Tab = "title" | "today" | "bracket";

const TABS: { id: Tab; label: string }[] = [
  { id: "title", label: "Title" },
  { id: "today", label: "Today" },
  { id: "bracket", label: "Bracket" },
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
  const [tab, setTab] = useState<Tab>("title");

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

        <div className="px-4 pb-16">
          {tab === "title" && (
            <>
              {data.boards.map((board) => (
                <TournamentBoard key={board.draw} board={board} />
              ))}
            </>
          )}

          {tab === "today" && (
            <div
              className="mt-6 rounded-2xl border border-surface-border bg-surface-card px-4 py-6 text-center"
              data-testid="slate-placeholder"
            >
              <div className="text-[15px] font-semibold text-text-primary">
                Today&rsquo;s matches
              </div>
              <p className="mt-1 text-[13px] text-text-secondary">
                The day&rsquo;s slate arrives here before the main draws begin.
              </p>
            </div>
          )}

          {tab === "bracket" && (
            <div className="mt-6">
              <TournamentBracket rounds={[]} drawReleased={data.draw_released} />
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
