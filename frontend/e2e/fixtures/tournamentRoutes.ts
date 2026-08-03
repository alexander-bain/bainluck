/**
 * L2-245 Item 0 — the frozen tournament/event-concept route registry.
 *
 * This is the fixture AUTHORITY the `tournament-inventory` pack reads. It records,
 * per C139 domain (`tournament_ux_closure_contract.json`), the route the browser
 * pack should exercise, how to resolve a live specimen when the slug rotates, the
 * capabilities C139 requires of that domain, and the GitHub child issue that owns
 * it. It deliberately does NOT hard-code a deployed SHA: the SHA is bound at
 * dispatch time by `browser-audit.yml` (`wait-for-frontend-sha.js`) and recorded
 * per journey in the manifest, so this file stays true across deploys.
 *
 * Two route-resolution modes, both honest:
 *   - `static`  — a config-stable slug the backend adapter resolves to the latest
 *                 edition even off-season (awards/oscars, election/2026-midterms,
 *                 soccer/world-cup-2026, cycling/tour-de-france-2026). Always
 *                 observable.
 *   - `discover`— the slug rotates (combat date-tokens, current golf/tennis/f1
 *                 events), so the pack asks a documented API endpoint at run time
 *                 for a currently-live concept key. When discovery returns nothing,
 *                 the journey is honestly NOT-OBSERVABLE (skipped with a reason),
 *                 never green.
 *
 * The generic shell (C139 `generic-*`) is not a separate route — it is the shared
 * page every domain below renders through (`app/event/[domain]/[slug]/page.tsx`),
 * so it is classified from the union of the concrete domain journeys at report
 * time. `native-concept-destination` is not web-observable and stays UNSTARTED
 * from this rail.
 *
 * Capability vocabulary mirrors C139 exactly:
 *   hero · field · live_progress · chart · matchups · props ·
 *   settled_what_hit · navigation · empty_error · native_destination
 */

export type Capability =
  | "hero"
  | "field"
  | "live_progress"
  | "chart"
  | "matchups"
  | "props"
  | "settled_what_hit"
  | "navigation"
  | "empty_error";

export type RouteResolution =
  | { mode: "static"; path: string }
  | {
      /**
       * Ask a first-party API for a currently-live concept, at run time, so the
       * pack never audits a stale hard-coded slug. `keyPath` is the dotted path to
       * an `event:<domain>:<slug>` key inside the JSON response; `filterDomain`
       * (when set) keeps only keys whose domain segment matches.
       */
      mode: "discover";
      endpoint: string;
      keyPath: string;
      filterDomain?: string;
      /** A config-stable fallback path used only when discovery finds nothing. */
      fallback?: string;
    };

export interface TournamentRoute {
  /** Stable journey id — half of the defect fingerprint in the manifest. */
  journeyId: string;
  /** The C139 domain token this journey represents. */
  domain: string;
  /** The C139 case id in `tournament_ux_closure_contract.json` this proves. */
  c139Case: string;
  resolution: RouteResolution;
  /** Capabilities C139 marks `required` for this domain (see the corpus). */
  required: Capability[];
  /** The GitHub child issue that owns this domain's UX (or a GAP to be filed). */
  childIssue: string;
  notes: string;
}

/**
 * Config-stable specimens first (always observable), rotating specimens after.
 * `expectedPathPrefix` for every concept is `/event/<domain>/` — the shell
 * canonicalizes the slug via `router.replace`, so the pack asserts the prefix and
 * origin, not an exact trailing slug.
 */
export const TOURNAMENT_ROUTES: readonly TournamentRoute[] = [
  {
    journeyId: "tournament.awards",
    domain: "awards",
    c139Case: "awards-static",
    resolution: { mode: "static", path: "/event/awards/oscars" },
    required: ["hero", "matchups", "props", "settled_what_hit", "navigation"],
    childIssue: "#1033",
    notes:
      "Config-stable bare slug resolves to the latest edition (event_awards.py). " +
      "co_equal_list shell — also the cleanest proof of the shared generic shell.",
  },
  {
    journeyId: "tournament.election",
    domain: "election",
    c139Case: "generic-shell-rendered-good",
    resolution: { mode: "static", path: "/event/election/2026-midterms" },
    required: ["hero", "matchups", "props", "empty_error", "navigation"],
    childIssue: "#1033",
    notes:
      "Config-stable (event_election.py). co_equal_list shell; second witness of " +
      "the generic shell rendering. Active markets through Nov 2026.",
  },
  {
    journeyId: "tournament.soccer",
    domain: "soccer",
    c139Case: "soccer-world-cup-static",
    resolution: { mode: "static", path: "/event/soccer/world-cup-2026" },
    required: [
      "hero",
      "field",
      "live_progress",
      "matchups",
      "props",
      "settled_what_hit",
      "navigation",
    ],
    childIssue: "GAP:soccer",
    notes:
      "Config-stable (event_soccer.py, canonical world-cup-2026). SoccerContainerHero " +
      "+ WinnerEvolutionChart; up-links to /sports (no dedicated hub).",
  },
  {
    journeyId: "tournament.cycling",
    domain: "cycling",
    c139Case: "cycling-tour-static",
    resolution: { mode: "static", path: "/event/cycling/tour-de-france-2026" },
    required: [
      "hero",
      "field",
      "live_progress",
      "chart",
      "matchups",
      "props",
      "settled_what_hit",
      "navigation",
    ],
    childIssue: "GAP:cycling",
    notes:
      "Config-stable (event_cycling.py, canonical tour-de-france-2026). Winner-field " +
      "race chart + leaderboard + stage rail; up-links to /sports.",
  },
  {
    journeyId: "tournament.golf",
    domain: "golf",
    c139Case: "golf-live-static",
    resolution: {
      mode: "discover",
      endpoint: "/api/golf",
      keyPath: "current_event.slug",
      fallback: "/event/golf/the-open-championship",
    },
    required: [
      "hero",
      "field",
      "live_progress",
      "chart",
      "matchups",
      "props",
      "navigation",
      "empty_error",
    ],
    childIssue: "#1138",
    notes:
      "Slug rotates by tournament week. Discover the current event via /api/golf; " +
      "fall back to a stable major. Also has a bespoke page at " +
      "/categories/golf/tournaments/<slug> (weaker selectors — audited via the shell here).",
  },
  {
    journeyId: "tournament.combat",
    domain: "ufc",
    c139Case: "combat-card-static",
    resolution: {
      mode: "discover",
      endpoint: "/api/hub/mma",
      keyPath: "upcoming.0.key",
      filterDomain: "ufc",
    },
    required: [
      "hero",
      "live_progress",
      "chart",
      "matchups",
      "props",
      "settled_what_hit",
      "navigation",
    ],
    childIssue: "GAP:combat",
    notes:
      "Date-token slug rotates every card — discover via /hub/mma upcoming[0].key. " +
      "co_equal_list shell (TwoSidedTimeline hero + MatchupsRail). NOT-OBSERVABLE " +
      "between cards.",
  },
  {
    journeyId: "tournament.tennis",
    domain: "tennis",
    c139Case: "tennis-static",
    resolution: {
      mode: "discover",
      endpoint: "/api/events/search?q=tennis",
      keyPath: "event_concepts",
      filterDomain: "tennis",
    },
    required: ["hero", "field", "chart", "matchups", "props", "settled_what_hit", "navigation"],
    childIssue: "#999",
    notes:
      "Slug rotates by tournament. Discover via events search event_concepts[]. " +
      "Winner-field shell. NOT-OBSERVABLE outside tournament weeks.",
  },
  {
    journeyId: "tournament.f1",
    domain: "f1",
    c139Case: "f1-static",
    resolution: {
      mode: "discover",
      endpoint: "/api/events/search?q=grand%20prix",
      keyPath: "event_concepts",
      filterDomain: "f1",
    },
    required: ["hero", "field", "chart", "props", "settled_what_hit", "navigation"],
    childIssue: "#999",
    notes:
      "Slug rotates by grand prix weekend. Discover via events search event_concepts[]. " +
      "Winner-field shell. NOT-OBSERVABLE between race weekends.",
  },
];

/**
 * The competition-hub / navigation entry point. It is both the C139 `navigation`
 * capability witness and this pack's adjacent-regression guard (gotcha #43): a
 * hub renders concept CARDS that link into `/event/...`, so if the shared concept
 * components regressed, the hub is the neighbouring surface that shows it.
 */
export const HUB_ROUTE = {
  journeyId: "tournament.hub",
  path: "/hub/mma",
  notes: "Competition hub — discovery entry point + adjacent-regression guard.",
} as const;
