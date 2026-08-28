"use client";

/**
 * /tournaments/{slug}/matches/{matchupKey} — one match's own page (UX-P149).
 *
 * ═══ WHY THIS PAGE EXISTS ═══
 *
 * Alex, on the match props lane1 measured in Q426: *"Will those flow into the
 * event page for each match, and will they look good?"*
 *
 * Lane1's note made the routing call — match props belong on the match's own
 * surface, grouped under the match-winner market, because "Total Sets O/U 3.5
 * at 65% is meaningless without Wu 48.5% / Walton 51.5% above it" — and then
 * named the blocker that made the surface a ux job rather than theirs:
 *
 *     **There is no per-match surface to route them to.** Tennis matches have
 *     no `events` row; zero exist for any registered matchup.
 *
 * The note offered two ways out: a match detail view keyed on `matchup_key`,
 * or real `events` rows. This is the first, and the reason is not that the
 * second is hard. It is that the second is a matching-layer job whose failure
 * mode is a wrong absorption (ruling 048), taken on in order to reuse a page
 * that would then have to be taught tennis anyway. A matchup key is an
 * identity the register already owns, decided offline against evidence, so
 * routing on it needs no new identity decision at all.
 *
 * ═══ THE LAYOUT, AND WHAT IT INHERITS ═══
 *
 * The hero is the same duel the match list prints, at page scale. Under it,
 * the questions, two columns at `lg` and one below it. There is no page-level
 * width: `app/layout.tsx` is the site's one container and the hub stopped
 * nesting a second, narrower one inside it at UX-P146 — a new surface must not
 * reintroduce the grey gutters that ruling removed. See
 * `components/tournament/layout.ts`.
 *
 * The back link is the first element rather than a chrome affordance, because
 * this page is reached from one place and returning to it is the most likely
 * next action.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import ErrorBoundary from "@/components/ErrorBoundary";
import MatchHero from "@/components/tournament/MatchHero";
import MatchProps from "@/components/tournament/MatchProps";
import { TOURNAMENT_SHELL } from "@/components/tournament/layout";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchTournamentMatch } from "@/lib/api";
import { matchBroadcast } from "@/lib/slate";
import type { MatchDetailPayload } from "@/lib/matchDetail";

export default function TournamentMatchPage() {
  const params = useParams();
  const slug = typeof params?.slug === "string" ? params.slug : "";
  /**
   * Next decodes a dynamic segment for us, so `%3A` arrives as `:` and the
   * bare colon form arrives unchanged. Both are the same key and both are
   * passed through whole — the register owns this identifier and a client that
   * split it on its colons would be re-deriving a decision already made.
   */
  const matchupKey =
    typeof params?.matchupKey === "string" ? params.matchupKey : "";

  usePageTracking({ pageType: "tournament_match", pageTitle: `Match: ${matchupKey}` });
  useScrollDepth({ pageType: "tournament_match" });
  useEngagementTime({ pageType: "tournament_match" });

  const [data, setData] = useState<MatchDetailPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug || !matchupKey) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchTournamentMatch(slug, matchupKey)
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        // No partial page assembled from whatever loaded. A match page that
        // half-renders is worse than one that says it could not load.
        if (!cancelled) setError("We could not load this match right now.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [slug, matchupKey]);

  // Computed before the loading/error returns so hook order never changes.
  const broadcast = useMemo(
    () => (data ? matchBroadcast(data.match, data.broadcasts) : null),
    [data]
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
        <h1 className="text-lg font-semibold text-text-primary">Match unavailable</h1>
        <p className="mt-1 text-sm text-text-secondary">{error ?? "Nothing to show."}</p>
        {slug && (
          <Link
            href={`/tournaments/${slug}`}
            className="mt-3 inline-block text-sm font-semibold text-text-primary underline decoration-dotted underline-offset-2"
          >
            Back to the tournament
          </Link>
        )}
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
      <div className={TOURNAMENT_SHELL} data-testid="match-shell">
        <div className="px-4 pb-16 pt-3 lg:px-6">
          <Link
            href={`/tournaments/${data.slug}`}
            className="inline-block text-[12px] font-semibold text-text-secondary"
            data-testid="match-back"
          >
            ← {data.title}
          </Link>

          <div className="mt-2.5">
            <MatchHero
              match={data.match}
              result={data.result}
              decided={data.decided}
            />
          </div>

          <MatchProps payload={data} />

          {/* WHERE TO WATCH lives on the detail view, which is Alex's ruling 7
              from UX-P137 — and this page IS the detail view that ruling was
              describing. Tournament-wide until a session feed exists; the
              scope is tagged so a guard can prove which answer this is rather
              than a per-match one that coincidentally matched. */}
          {broadcast && (
            <p
              className="mt-5 text-[12px] text-text-secondary"
              data-testid="match-broadcast"
              data-scope={broadcast.scope}
            >
              <span className="font-semibold text-text-primary">Where to watch</span>{" "}
              {broadcast.channels.join(", ")}
              <span className="text-text-muted"> ({broadcast.region})</span>
            </p>
          )}

          <footer className="mt-5 border-t border-surface-border pt-4 text-[11.5px] leading-relaxed text-text-muted">
            {/* UX-P146's product-wide ruling: *price* as a noun is out of
                user-facing copy, and so is every synonym that smuggles the
                trading frame back in. This says where the number is from and
                what we did to it, in neither. */}
            <span className="block max-w-[74ch]">
              Every number here comes from what a prediction market is saying about this
              match. Two-sided questions are adjusted so the pair adds to 100.
            </span>
          </footer>
        </div>
      </div>
    </ErrorBoundary>
  );
}
