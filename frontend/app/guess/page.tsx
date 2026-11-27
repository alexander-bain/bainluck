"use client";

// /guess — GUESS THE CHANCE (425: C, 426: A, 430: A, 443: A, 445: A). An unlisted
// daily challenge: the server hands out each Pacific Time day's fifteen cards from
// open numbers frozen that morning, and finishers in a group link share one
// board stored for 30 days. Pre-existing `#g=...` links still open the set they
// were made on (`packs.ts`), and an unreachable daily edition degrades to the
// latest built-in set instead of dead-ending.

import { useCallback, useEffect, useState } from "react";

import ErrorBoundary from "@/components/ErrorBoundary";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { fetchTodayPack, formatDayLabel, GuessApiError, isValidGroupCode } from "@/lib/guess/api";
import { LATEST_PACK, packForHash } from "@/lib/guess/packs";
import type { GamePack } from "@/lib/guess/types";

import ChanceGame from "./ChanceGame";

interface ResolvedEdition {
  pack: GamePack;
  initialGroupCode: string | null;
  isLegacyPack: boolean;
  initialGroupError: string | null;
  earlierDayNotice: string | null;
  expiredDayNotice: string | null;
  fallbackNotice: string | null;
}

export default function GuessPage() {
  usePageTracking({ pageType: "guess", pageTitle: "Guess the Chance" });
  useScrollDepth({ pageType: "guess" });
  useEngagementTime({ pageType: "guess" });

  const [edition, setEdition] = useState<ResolvedEdition | null>(null);

  const loadEdition = useCallback(async () => {
    const params = new URLSearchParams(window.location.search);
    const rawGroup = params.get("group");
    const rawDay = params.get("day");
    const legacyPack = !rawGroup && !rawDay ? packForHash(window.location.hash) : null;

    if (legacyPack) {
      setEdition({
        pack: legacyPack,
        initialGroupCode: null,
        isLegacyPack: true,
        initialGroupError: null,
        earlierDayNotice: null,
        expiredDayNotice: null,
        fallbackNotice: null,
      });
      return;
    }

    const validGroup = isValidGroupCode(rawGroup) ? rawGroup : null;
    const groupErr = rawGroup && !validGroup ? "That group link is incomplete, so no group board was loaded." : null;

    try {
      const resp = await fetchTodayPack(rawDay);
      const earlierNotice =
        resp.is_today === false ? `You are viewing ${formatDayLabel(resp.day)}'s cards and board.` : null;
      setEdition({
        pack: resp.pack,
        initialGroupCode: validGroup,
        isLegacyPack: false,
        initialGroupError: groupErr,
        earlierDayNotice: earlierNotice,
        expiredDayNotice: null,
        fallbackNotice: null,
      });
    } catch (err) {
      if (rawDay && err instanceof GuessApiError && err.status === 404) {
        try {
          const todayResp = await fetchTodayPack(null);
          setEdition({
            pack: todayResp.pack,
            initialGroupCode: null,
            isLegacyPack: false,
            initialGroupError: null,
            earlierDayNotice: null,
            expiredDayNotice: "That day's cards and board are gone (games are kept for 30 days). Here are today's cards.",
            fallbackNotice: null,
          });
          return;
        } catch {
          setEdition({
            pack: LATEST_PACK,
            initialGroupCode: null,
            isLegacyPack: true,
            initialGroupError: null,
            earlierDayNotice: null,
            expiredDayNotice: null,
            fallbackNotice: "That day's cards are gone and today's live cards could not be reached, so you are playing the built-in set.",
          });
          return;
        }
      }
      setEdition({
        pack: LATEST_PACK,
        initialGroupCode: null,
        isLegacyPack: true,
        initialGroupError: null,
        earlierDayNotice: null,
        expiredDayNotice: null,
        fallbackNotice: "Today's live cards could not be reached, so you are playing the built-in set.",
      });
    }
  }, []);

  useEffect(() => {
    void loadEdition();
    const onHash = () => {
      void loadEdition();
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [loadEdition]);

  return (
    <ErrorBoundary
      fallback={
        <div className="px-5 py-10 text-center text-text-primary">
          Something went wrong. Reload the page to carry on; your game is kept on this phone.
        </div>
      }
    >
      {/* `touch-manipulation`: two quick taps on a button are two taps, never a zoom. */}
      <div className="touch-manipulation" data-testid="guess-root">
        {edition ? (
          <ChanceGame
            key={`${edition.pack.id}:${edition.initialGroupCode ?? ""}:${edition.isLegacyPack ? "legacy" : "daily"}`}
            pack={edition.pack}
            initialGroupCode={edition.initialGroupCode}
            isLegacyPack={edition.isLegacyPack}
            initialGroupError={edition.initialGroupError}
            earlierDayNotice={edition.earlierDayNotice}
            expiredDayNotice={edition.expiredDayNotice}
            fallbackNotice={edition.fallbackNotice}
            onRetryLive={edition.fallbackNotice ? () => void loadEdition() : null}
          />
        ) : (
          <div className="px-4 py-8">
            <div
              className="mx-auto max-w-md space-y-2 rounded-3xl border-2 border-surface-border bg-surface-card p-5 text-center"
              data-testid="edition-loading"
            >
              <h1 className="text-2xl font-black text-text-primary">Guess the Chance</h1>
              <p className="text-sm text-text-secondary">Loading today&apos;s cards…</p>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
