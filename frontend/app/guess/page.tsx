"use client";

// /guess — GUESS THE CHANCE (425: C, 426: A, 430: A). An unlisted page: a group
// plays the same fifteen cards in three steps, each on their own phone and in
// their own time, and the link they pass around carries everyone's guesses.
//
// FRONTEND-ONLY, AND NOTHING IS STORED. The cards and their numbers are a dated
// set in `lib/guess/pack.ts`. A game lives in this browser and in the link. The
// page makes no API call, has no table behind it, and asks for no account.
//
// NOT PART OF THE HELD-BACK PREDICTION SURFACES (#6445, #12601). Those are the
// Daily Challenge and the inline quiz cards, which save a reader's guesses to
// their account and are switched off behind `CHALLENGE_SURFACES_ENABLED`. This
// page mounts none of their components, calls none of their APIs, and is linked
// from nowhere on the site.

import ErrorBoundary from "@/components/ErrorBoundary";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { GUESS_PACK } from "@/lib/guess/pack";

import ChanceGame from "./ChanceGame";

export default function GuessPage() {
  usePageTracking({ pageType: "guess", pageTitle: "Guess the Chance" });
  useScrollDepth({ pageType: "guess" });
  useEngagementTime({ pageType: "guess" });

  return (
    <ErrorBoundary
      fallback={
        <div className="px-5 py-10 text-center text-text-primary">
          Something went wrong. Reload the page to carry on; your game is kept on this phone.
        </div>
      }
    >
      <ChanceGame pack={GUESS_PACK} />
    </ErrorBoundary>
  );
}
