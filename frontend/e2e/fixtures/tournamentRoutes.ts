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
 * Three route-resolution modes, all honest:
 *   - `static`  — a config-stable slug the backend adapter resolves to the latest
 *                 edition even off-season (awards/oscars, election/2026-midterms,
 *                 soccer/world-cup-2026). Always observable.
 *   - `discover`— the slug rotates (combat date-tokens, current golf/tennis/f1
 *                 events), so the pack asks a documented API endpoint at run time
 *                 for a currently-live concept key. When discovery returns nothing,
 *                 the journey is honestly NOT-OBSERVABLE (skipped with a reason),
 *                 never green.
 *   - `unavailable`
 *               — the domain has NO live specimen AND no endpoint to discover one
 *                 from. Declared, dated, and owned by a tracking issue, so the
 *                 journey reaches the honest NOT-OBSERVABLE terminal instead of
 *                 asserting a dead slug MUST render. See UX-P059 / #1733.
 *
 * UX-P059 (#1733) — WHY THE THIRD MODE EXISTS, and it is a correction to the text
 * above rather than an addition to it. `static` claimed the adapter "resolves to
 * the latest edition even off-season". That is true for a BARE slug (`oscars`); it
 * is NOT true for a slug carrying a year, and three of the four static specimens
 * carried one. MEASURED 2026-08-11:
 *
 *   /api/event/event:awards:oscars                 -> 200
 *   /api/event/event:election:2026-midterms        -> 200
 *   /api/event/event:soccer:world-cup-2026         -> 200
 *   /api/event/event:cycling:tour-de-france-2026   -> 404   <- the 2026 Tour ended in July
 *
 * So the cycling journey asserted MUST-RENDER against a slug with an expiry date,
 * and reds every night forever. That is gotcha #44's class — the fixture had an
 * expiry date — which is verbatim the lesson of Q329/#1729.
 *
 * Cycling cannot be converted to `discover`: there is no endpoint to discover from.
 * `/api/concepts` 404s (it does not exist), and the hub registry covers only
 * mma/boxing/golf/tennis/esports (`app/routes/hub.py`). Inventing a slug would swap
 * a stale specimen for an unverified one, so the state is DECLARED instead.
 *
 * LATENT, recorded and deliberately not fixed here: `election/2026-midterms`
 * ("active markets through Nov 2026") and `soccer/world-cup-2026` are the same
 * dated shape and will expire the same way. The general fix is an `expires` date,
 * which makes the rail clock-dependent — and gotcha #44 plus Q329 say that needs a
 * `clock_sweep`-grade proof, not a side effect of this queue.
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
    }
  | {
      /**
       * UX-P059 (#1733): no live specimen exists AND no endpoint can discover one.
       * The journey takes the NOT-OBSERVABLE path — it probes the deterministic
       * `no-live-specimen` slug and proves the honest "Event not found" terminal
       * renders — rather than asserting a dead hard-coded slug MUST render.
       *
       * This is a DECLARED gap, not a mute button, and the difference is these two
       * required fields: `reason` states the condition that must change, and
       * `trackingIssue` stays open until it does. A reader of the manifest sees the
       * domain is unproven and why; a silent skip would tell them nothing.
       */
      mode: "unavailable";
      /** Why no specimen is reachable — the condition that must change to flip back. */
      reason: string;
      /** The GitHub issue that stays open while this domain is unproven. */
      trackingIssue: string;
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
    // UX-P059 (#1733): was `{ mode: "static", path: "/event/cycling/tour-de-france-2026" }`,
    // which 404s — the 2026 Tour ended in July. See the dated-specimen note in this
    // file's header for why this is `unavailable` rather than re-pointed or discovered.
    resolution: {
      mode: "unavailable",
      reason:
        "The 2026 Tour de France ended in July and its concept 404s; there is no live " +
        "cycling concept and no endpoint to discover one from (/api/concepts does not " +
        "exist; the hub registry covers only mma/boxing/golf/tennis/esports). Flip back " +
        "to `discover` the moment a cycling hub or concept-listing endpoint ships.",
      trackingIssue: "#1733",
    },
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
      "UX-P059 (#1733): DECLARED UNAVAILABLE — the adapter (event_cycling.py) is not " +
      "known to be broken, but no live cycling concept exists and nothing can discover " +
      "one, so the domain is UNPROVEN rather than shipped or broken. When a specimen " +
      "returns, this route proves: winner-field race chart + leaderboard + stage rail, " +
      "up-linking to /sports.",
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
