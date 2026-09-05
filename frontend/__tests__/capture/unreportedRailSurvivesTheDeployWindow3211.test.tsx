// THE DEPLOY WINDOW IS A REAL STATE OF THE PRODUCT — #3211, lane1/134.
//
// ═══ WHY THIS FILE EXISTS ═══
//
// #3211 adds a third rail to the league page, and the two halves of it ship on
// DIFFERENT SCHEDULES: Vercel deploys the frontend from the merge commit, and
// Heroku deploys the backend behind the serialized CI `deploy` job after the
// full test suite. For minutes, production runs this page against an envelope
// that has never heard of `unreported_games`.
//
// So "the page renders when the key is absent" is not a defensive nicety — it
// is a state every user of `/sport/tennis/wta` will actually be in, on the day
// this merges. The failure mode if it were wrong is the worst kind: a blank or
// crashed league page for the whole deploy window, on the pages this queue
// exists to repair.
//
// It is also the shape of an old lesson (memory:
// `r_producer_and_consumer_green_request_dead`) told in the time dimension
// rather than the code one — both ends green, and the thing between them not
// yet carrying what one end assumes.
//
// ═══ AND THE MIRROR CASE, WHICH IS THE ONE THAT WOULD ACTUALLY BREAK ═══
//
// The reverse — backend deployed, frontend not — cannot break: an extra key in
// a JSON payload is ignored. That asymmetry is why only one direction is tested
// and why it is stated rather than left as an apparent omission.
//
// RENDERED, NOT GREPPED (#2060). The claim is about markup.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { LeagueFuturesResponse } from "@/lib/api";

let swrData: Record<string, unknown> = {};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : String(key);
    return {
      data: swrData[k],
      error: undefined,
      isLoading: false,
      mutate: () => {},
    };
  },
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ trackEventCardClick: () => undefined }),
}));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

// eslint-disable-next-line @typescript-eslint/no-var-requires
import LeagueGameRail from "@/components/LeagueGameRail";

/** The rail, handed exactly what the page hands it when the key is missing:
 *  `leagueMarkets?.unreported_games ?? []`. */
function renderRailFrom(envelope: Partial<LeagueFuturesResponse>): string {
  const games = envelope.unreported_games ?? [];
  return renderToStaticMarkup(
    <LeagueGameRail
      title="No result reported"
      games={games}
      hasMore={envelope.unreported_games_has_more}
      settled
    />,
  );
}

describe("#3211 · the league page during its own deploy window", () => {
  it("renders NOTHING for the new rail when the backend has not shipped yet", () => {
    // A pre-#3211 envelope. Not a contrived one — this is verbatim the shape
    // `/api/leagues/tennis_wta` served on production while this branch was
    // being written.
    const preDeploy: Partial<LeagueFuturesResponse> = {
      sport_key: "tennis_wta",
      upcoming_games: [],
      upcoming_games_has_more: false,
      recent_results: [],
      recent_results_has_more: false,
      record_n: 0,
    };

    const markup = renderRailFrom(preDeploy);

    // An empty rail emits no section at all — the component's existing
    // honest-empty rule, which the new rail inherits rather than reimplements.
    // The heading must NOT appear over nothing: "No result reported" as a
    // standing header on every league page would be a claim about every league.
    expect(markup).not.toContain("No result reported");
    expect(markup).not.toContain("<section");
  });

  it("CONTROL: the same rail DOES render once the backend ships the key", () => {
    // Without this the test above passes for a component that renders nothing
    // ever — the vacuous-green shape a "does not crash" test is most prone to.
    const postDeploy = {
      sport_key: "tennis_wta",
      unreported_games: [
        {
          id: 15304868,
          home_team: "Dart / Lumsden",
          away_team: "Bucsa / Melichar-Martinez",
          commence_time: "2026-09-02T00:00:00+00:00",
          status: "scheduled",
          home_score: null,
          away_score: null,
          home_win_probability: null,
        },
      ],
      unreported_games_has_more: true,
    } as unknown as Partial<LeagueFuturesResponse>;

    const markup = renderRailFrom(postDeploy);

    expect(markup).toContain("No result reported");
    expect(markup).toContain("Bucsa / Melichar-Martinez");
    // The cap is DECLARED, not silently applied (spec §4).
    expect(markup).toMatch(/Showing the 1 most recent/);
  });

  it("an explicitly empty list is the same as an absent one", () => {
    // The steady state for most leagues — every fixture settled, nothing
    // unreported — and it must not grow a permanent empty heading either.
    const markup = renderRailFrom({
      unreported_games: [],
      unreported_games_has_more: false,
    });
    expect(markup).not.toContain("No result reported");
  });
});
