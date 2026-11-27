"use client";

// /guess — GUESS THE CHANCE (425: C, 426: A, 430: A). An unlisted page: a group
// plays the same fifteen cards in three steps, each on their own phone and in
// their own time, and the link they pass around carries everyone's guesses.
//
// FRONTEND-ONLY, AND NOTHING IS STORED. The cards and their numbers are a dated
// set in `lib/guess/pack.ts` (earlier sets beside it, see `packs.ts`). A game lives in this browser and in the link. The
// page makes no API call, has no table behind it, and asks for no account.
//
// NOT PART OF THE HELD-BACK PREDICTION SURFACES (#6445, #12601). Those are the
// Daily Challenge and the inline quiz cards, which save a reader's guesses to
// their account and are switched off behind `CHALLENGE_SURFACES_ENABLED`. This
// page mounts none of their components, calls none of their APIs, and is linked
// from nowhere on the site.

import { useEffect, useState } from "react";

import ErrorBoundary from "@/components/ErrorBoundary";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { LATEST_PACK, packForHash } from "@/lib/guess/packs";
import type { GamePack } from "@/lib/guess/types";

import ChanceGame from "./ChanceGame";

export default function GuessPage() {
  usePageTracking({ pageType: "guess", pageTitle: "Guess the Chance" });
  useScrollDepth({ pageType: "guess" });
  useEngagementTime({ pageType: "guess" });

  // A LINK OPENS THE SET IT WAS MADE ON (445: A). The server cannot see the part
  // of the address after the `#`, so the first paint is the newest set and the
  // set the link names is picked as soon as the page is in the browser. A link to
  // a set we do not hold falls through to the newest, and the game says so.
  const [pack, setPack] = useState<GamePack>(LATEST_PACK);
  useEffect(() => {
    const pick = () => setPack(packForHash(window.location.hash) ?? LATEST_PACK);
    pick();
    window.addEventListener("hashchange", pick);
    return () => window.removeEventListener("hashchange", pick);
  }, []);

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
        <ChanceGame key={pack.id} pack={pack} />
      </div>
    </ErrorBoundary>
  );
}
