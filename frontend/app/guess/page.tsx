"use client";

// /guess — GUESS THE CHANCE (425: C, 426: A, 430: A, 443: A). An unlisted daily
// challenge: the server hands out each Pacific Time day's fifteen cards from
// open numbers frozen that morning, and finishers in a group link share one
// board stored for 30 days. Pre-existing `#g=...` links keep working.

import { useCallback, useEffect, useState } from "react";

import ErrorBoundary from "@/components/ErrorBoundary";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { extractLegacyHashCode, fetchTodayPack, isValidGroupCode } from "@/lib/guess/api";
import { LEGACY_PACKS_BY_CODE } from "@/lib/guess/pack";
import type { GamePack } from "@/lib/guess/types";

import ChanceGame from "./ChanceGame";

interface ResolvedEdition {
  pack: GamePack;
  initialGroupCode: string | null;
  isLegacyPack: boolean;
  initialGroupError: string | null;
}

export default function GuessPage() {
  usePageTracking({ pageType: "guess", pageTitle: "Guess the Chance" });
  useScrollDepth({ pageType: "guess" });
  useEngagementTime({ pageType: "guess" });

  const [edition, setEdition] = useState<ResolvedEdition | null>(null);
  const [editionError, setEditionError] = useState<string | null>(null);

  const loadEdition = useCallback(async () => {
    setEditionError(null);
    const params = new URLSearchParams(window.location.search);
    const rawGroup = params.get("group");
    const rawDay = params.get("day");
    const legacyCode = !rawGroup && !rawDay ? extractLegacyHashCode(window.location.hash, LEGACY_PACKS_BY_CODE) : null;

    if (legacyCode) {
      setEdition({
        pack: LEGACY_PACKS_BY_CODE[legacyCode],
        initialGroupCode: null,
        isLegacyPack: true,
        initialGroupError: null,
      });
      return;
    }

    const validGroup = isValidGroupCode(rawGroup) ? rawGroup : null;
    const groupErr = rawGroup && !validGroup ? "That group link is incomplete, so no group board was loaded." : null;

    try {
      const resp = await fetchTodayPack(rawDay);
      setEdition({
        pack: resp.pack,
        initialGroupCode: validGroup,
        isLegacyPack: false,
        initialGroupError: groupErr,
      });
    } catch (err) {
      setEditionError(err instanceof Error ? err.message : "Could not load today's cards right now.");
    }
  }, []);

  useEffect(() => {
    void loadEdition();
  }, [loadEdition]);

  return (
    <ErrorBoundary
      fallback={
        <div className="px-5 py-10 text-center text-text-primary">
          Something went wrong. Reload the page to carry on; your game is kept on this phone.
        </div>
      }
    >
      {edition ? (
        <ChanceGame
          key={`${edition.pack.id}:${edition.initialGroupCode ?? ""}:${edition.isLegacyPack ? "legacy" : "daily"}`}
          pack={edition.pack}
          initialGroupCode={edition.initialGroupCode}
          isLegacyPack={edition.isLegacyPack}
          initialGroupError={edition.initialGroupError}
        />
      ) : editionError ? (
        <div className="px-4 py-8">
          <div
            className="mx-auto max-w-md space-y-3 rounded-3xl border-2 border-surface-border bg-surface-card p-5 text-center"
            data-testid="edition-error"
          >
            <h1 className="text-2xl font-black text-text-primary">Guess the Chance</h1>
            <p className="text-sm font-bold text-text-primary">Could not load today&apos;s cards.</p>
            <p className="text-sm text-text-secondary">{editionError}</p>
            <button
              type="button"
              onClick={() => void loadEdition()}
              className="min-h-[48px] w-full rounded-2xl bg-text-primary px-5 text-base font-black text-white active:scale-95"
              data-testid="edition-retry"
            >
              Try again
            </button>
          </div>
        </div>
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
    </ErrorBoundary>
  );
}
