/**
 * UX-P223 — THE SIX EMPTY STATES ARE ANCHORED ON A RENDER, NOT ON THEIR SOURCE.
 *
 * ═══ WHY THIS FILE EXISTS ═══
 *
 * `emptyStatesStateWhatTheyAre.test.tsx` proves ruling 142's rewrite for eight
 * sites. Two of them are components and were always genuinely rendered. The
 * other six are pages, and their anchor read the file's SOURCE. Three certs
 * blocked that anchor in a row, each by defeating the previous repair without
 * ever touching the sentence a reader sees:
 *
 *   CERT-558  `read(file).toContain(s)` — the visible line was deleted and the
 *             string kept alive in a `data-cert-copy` ATTRIBUTE. Green.
 *   CERT-562  whole-file `renderableText` — the sentence was MOVED out of the
 *             authenticated no-content branch into the signed-out branch.
 *             Right file, wrong screen. Green.
 *   CERT-566  scoped `emptyStateText(file, name)` — the `data-empty-state-name`
 *             MARKER was moved to the signed-out branch together with the
 *             sentence, so the scope followed the copy. Green. A duplicate-marker
 *             variant also passed.
 *
 * Three findings of the same shape are a statement about the ANCHOR KIND. Every
 * repair stayed inside the same class — a source oracle cannot tell which BRANCH
 * of a component the reader is standing in, because branch selection is a
 * runtime fact and the oracle only ever sees the text.
 *
 * ═══ THE PRIOR JUSTIFICATION WAS MEASURED, AND IT WAS WRONG ═══
 *
 * That file's header, and `dailyChallengeAuditHooks.test.ts` before it, declined
 * to render on the grounds that these are *"large client components behind
 * fetch/localStorage, and rendering them would prove less and break more."*
 * UX-P223 measured it instead of inheriting it:
 *
 *   - `jest-environment-jsdom` and `jsdom` are BOTH absent from `node_modules`
 *     and the npm registry is unreachable from the sandbox, so a DOM render is
 *     genuinely unavailable. That much of the old reasoning held.
 *   - But a DOM is not what this needs. `renderToStaticMarkup` already runs in
 *     the existing `testEnvironment: 'node'` harness — it is how the two
 *     component sites are anchored today — and it renders these pages too.
 *     The heaviest of the six (`app/my-stuff`, 1188 lines, auth + router + SWR +
 *     two pinned hooks) renders its authenticated empty branch in ~0.4s behind
 *     seven module mocks.
 *
 * ═══ WHAT THIS BUYS THAT A SOURCE ANCHOR CANNOT ═══
 *
 * Each row below drives ONE page into ONE state — signed in, request settled,
 * zero items — and asserts against the markup that state produces. CERT-566's
 * attack fails here by construction: move the marker and the sentence to the
 * signed-out branch and this render, which is of the AUTHENTICATED branch, no
 * longer contains either. There is no edit that satisfies this file without
 * putting the copy on the screen the reader is actually looking at.
 *
 * The source anchors in the sibling file are deliberately KEPT. They are a
 * second, independent layer and they are cheap; what they are no longer is the
 * only thing standing between a rewrite and a regression.
 *
 * ═══ ON THE MOCKS — AND WHAT CERT-569 FOUND IN THEM (round 5) ═══
 *
 * The mocks stop at the module boundary the page fetches through. The page's own
 * state machine runs for real — `app/my-stuff` still resolves its principal
 * through the unmocked `clientPrincipal`, and the record it is handed is bound
 * to that principal, because a test that mocked the binding away could not tell
 * an empty state from a cross-account leak.
 *
 * That boundary is honest, but the PAYLOADS crossing it were first written from
 * whatever made the render stop crashing, not from the route that produces them.
 * CERT-569 blocked the file for the gap that left:
 *
 *   CERT-569  the signed-in My Stuff payload omitted `personalization`, which
 *             `GET /api/feed` emits on every authenticated response. `teamCount`
 *             sat at `null` — a value no authenticated reader can hold — so the
 *             empty state was reached by the ABSENCE of a field instead of by
 *             the path a real reader walks. Mutating the State-B gate from
 *             `teamCount === 0` to `teamCount !== null`, which diverts every
 *             real authenticated response to onboarding, stayed green.
 *
 * A census of the other five found this defect in NONE of them: `sports/[key]`
 * and `categories/[slug]` gate on genuinely empty arrays, `hub` on genuinely
 * empty collections, `playoffs` on one real section holding zero participants
 * (not a vacuous `.every()` over an empty list), and the `discover` challenge
 * modal takes its items as a direct prop. Only My Stuff read a field.
 *
 * The repair is not a seventh hand-fitted shape. `authenticatedFeedPayload` is
 * built from `backend/app/routes/feed.py` and both sides of the gate it feeds
 * are now rendered.
 *
 * ═══ WHAT THIS FILE DOES NOT GUARD, AND WHY IT STOPPED CLAIMING TO (round 6) ═══
 *
 * Round 5 added a row asserting that this fixture "carries what the serializer
 * emits", implemented as a regex over `feed.py` for the `payload["personalization"]
 * = {...}` literal. CERT-573 blocked it: the regex sees one dict literal, so
 * appending `payload["personalization"]["new_metric"] = 0` after it left the
 * fixture stale with every row green. The claim was false.
 *
 * It was WITHDRAWN rather than patched. A stricter regex loses to the next write
 * form — an alias, a `setdefault`, an `update`, a loop — and each patch is one
 * more round of the same argument. A check of this class is only worth having if
 * it is FAIL-CLOSED: it must red on any use of the emitted object it does not
 * recognise, which needs a Python AST over the authenticated block, not a text
 * scan run from Jest. That instrument plus a shared machine-readable contract is
 * its own slice; it is not cargo for a copy ship that has bounced five times.
 *
 * So, precisely:
 *   GUARDED    the fixture's `team_count` — dropping it, or weakening the gate in
 *              either direction, fails the two rendered controls below.
 *   NOT GUARDED a field ADDED to `personalization` in `feed.py` later. The fixture
 *              would go stale and nothing here would say so. This is the residual
 *              risk CERT-569 found, narrowed to additions only, and it is stated
 *              here rather than covered by a check that cannot see them.
 *
 *   TZ=UTC npx jest --testPathPatterns=emptyStatesRenderTheirOwnBranch
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** The three GA4 hooks every page calls before any conditional return. */
const ANALYTICS_HOOKS = {
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
};

/** A settled SWR result. `data: undefined` for a suppressed (null-key) request. */
const settled = (data: unknown) => ({
  data,
  error: undefined,
  isLoading: false,
  mutate: () => {},
});

/**
 * An authenticated, settled, EMPTY feed response — the real payload shape.
 *
 * CERT-569 blocked the first version of this file for omitting
 * `personalization`. The omission was not cosmetic: My Stuff's State-B gate
 * reads `feedData?.personalization?.team_count ?? null`, so a fixture without
 * the block leaves `teamCount` at `null` — a value **no authenticated reader
 * can ever hold**, because the backend emits the block unconditionally once
 * `ctx.is_authenticated`. The empty state was therefore being reached by the
 * ABSENCE of a field rather than by the path a real user walks, and an
 * exact-head mutation of `teamCount === 0` to `teamCount !== null` — which
 * diverts every real authenticated response to onboarding and makes this empty
 * state unreachable in production — left the render green.
 *
 * `teamCount` is a PARAMETER because the two sides of that gate are two
 * different screens, and both are pinned below: a reader with saved teams sees
 * the empty state, a reader with none sees onboarding.
 *
 * The five `personalization` keys are transcribed from the `if ctx.is_authenticated`
 * block of `backend/app/routes/feed.py`. That transcription is checked by a human
 * reading both files, NOT by a test — see the header's "what this file does not
 * guard": a key added to the serializer later will not fail here.
 */
function authenticatedFeedPayload(teamCount: number) {
  return {
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
    has_more: false,
    requires_auth: false,
    personalized: true,
    personalization: {
      team_count: teamCount,
      sport_affinities_count: 0,
      discover_category_affinities_count: 0,
      pinned_events: 0,
      pinned_futures: 0,
    },
  };
}

/**
 * Register My Stuff's module graph.
 *
 * One registrar for all three renders (saved teams, no teams, signed out) so
 * the only thing that varies between them is the thing under test. Three
 * hand-copied mock blocks would let a fixture drift silently, which is the
 * class of defect this file exists to close.
 */
function registerMyStuffMocks(opts: { authenticated: boolean; teamCount?: number }) {
  jest.doMock("@/hooks", () => ({
    ...ANALYTICS_HOOKS,
    usePinnedEvents: () => ({ pinnedIds: [], isPinned: () => false, togglePin: () => {} }),
    usePinnedFutures: () => ({ pinnedIds: [], isPinned: () => false, togglePin: () => {} }),
  }));
  jest.doMock("next/navigation", () => ({
    useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
    useParams: () => ({}),
  }));
  jest.doMock("@/components/AuthProvider", () => ({
    useAuthContext: () => ({
      user: opts.authenticated ? { uid: "u1", email: "reader@example.com" } : null,
      isAuthenticated: opts.authenticated,
      isLoading: false,
      signInWithGoogle: () => {},
      signInWithApple: () => {},
    }),
  }));
  jest.doMock("@/lib/firebase", () => ({ preloadFirebaseAuth: () => {} }));
  jest.doMock("@/lib/api", () => ({
    fetchFeed: () => {},
    fetchMyTeamFutures: () => {},
    fetchEventsByIds: () => {},
    fetchFuturesByIds: () => {},
  }));
  jest.doMock("@/lib/myStuffTelemetry", () => ({
    classifyMyStuffOutcome: () => (opts.authenticated ? "empty" : "signed-out"),
    reportMyStuffTelemetry: () => {},
  }));
  // `clientPrincipal` is NOT mocked. The page resolves `user:u1` for itself and
  // `dataForPrincipal` unwraps only a record bound to it, so the payload below
  // has to carry the real principal to be seen at all.
  jest.doMock("swr", () => ({
    __esModule: true,
    default: (key: unknown) => {
      if (!opts.authenticated) return settled(undefined);
      if (key === null || key === undefined) return settled(undefined);
      const resource = Array.isArray(key) ? key[1] : key;
      const payload =
        resource === "feed"
          ? authenticatedFeedPayload(opts.teamCount ?? 0)
          : resource === "team-futures"
            ? { items: [] }
            : [];
      return settled({ principal: "user:u1", data: payload });
    },
  }));
}

/**
 * Strip tags so the assertion reads what a PERSON reads.
 *
 * Entities are normalised as CHARACTERS: `renderToStaticMarkup` resolves a JSX
 * entity before it reaches this string, so an entity-keyed replacement is a
 * no-op that leaves a smart quote in the compared text (UX-P219's finding).
 */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/[“”]/g, '"')
    .replace(/[’]/g, "'")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Render one page inside its own module registry.
 *
 * `jest.doMock` (not `jest.mock`) because the six pages need DIFFERENT module
 * graphs and `jest.mock` is hoisted to file scope, which would hand every page
 * the union of all six sets of mocks.
 */
function renderInIsolation(register: () => void, load: () => React.ReactElement): string {
  let markup = "";
  jest.isolateModules(() => {
    register();
    // `react-dom/server` is required INSIDE the isolated registry on purpose.
    // `isolateModules` hands the page a fresh `react`, and a renderer bound to
    // the outer copy reads a null hook dispatcher — every page then dies on its
    // first `useMemo`/`useRef`. Renderer and component must share one React.
    /* eslint-disable @typescript-eslint/no-var-requires */
    const render = require("react-dom/server").renderToStaticMarkup;
    /* eslint-enable @typescript-eslint/no-var-requires */
    markup = render(load());
  });
  return markup;
}

/* ═══════════════════════════ the six page renders ══════════════════════════ */

type PageCase = {
  /** Matches the `site` string in `emptyStatesStateWhatTheyAre.test.tsx`. */
  site: string;
  /** The value of the element's `data-empty-state-name`. */
  emptyState: string;
  /** The ruling-142 sentence the reader must be able to see. */
  states: string;
  /** The sentence this replaced. Must not appear in the rendered markup. */
  retired: string;
  render: () => string;
};

const CASES: PageCase[] = [
  {
    site: "app/sports/[key] · no games",
    emptyState: "league-no-upcoming-events",
    // #2948 — the page now lists finished games too, in their own section, so
    // the empty state stopped describing it as scheduled-only. The ANCHOR name
    // is deliberately unchanged: two registries key on it, and renaming it
    // would red them for a reason that has nothing to do with this ship.
    states: "This page lists games for this league.",
    retired: "Check back later for more games",
    render: () =>
      renderInIsolation(
        () => {
          jest.doMock("@/hooks", () => ANALYTICS_HOOKS);
          jest.doMock("@/lib/api", () => ({ fetchEvents: () => {}, fetchSports: () => {} }));
          jest.doMock("swr", () => ({
            __esModule: true,
            default: (key: unknown) =>
              settled((Array.isArray(key) ? key[0] : key) === "sports"
                ? { sports: [] }
                : { events: [] }),
          }));
        },
        () => {
          const Page = require("@/app/sports/[key]/page").default;
          return React.createElement(Page, { params: { key: "basketball_nba" } });
        },
      ),
  },

  {
    site: "app/my-stuff · nothing on for your teams",
    emptyState: "my-stuff-no-teams",
    states: "This page follows the teams you have saved.",
    retired: "Check back when your teams are playing",
    render: () =>
      renderInIsolation(
        // Signed IN, with saved teams. `team_count: 3` is the state this empty
        // state actually exists for — a reader who follows teams and whose feed
        // came back with nothing. `team_count: 0` is a DIFFERENT screen
        // (onboarding), pinned separately below.
        () => registerMyStuffMocks({ authenticated: true, teamCount: 3 }),
        () => React.createElement(require("@/app/my-stuff/page").default),
      ),
  },

  {
    site: "app/categories · no items for this category",
    emptyState: "category-no-items",
    // The RENDER resolves `{categoryName.toLowerCase()}`, so unlike the source
    // anchor this reads the whole sentence the reader sees, data included.
    states: "This page lists open politics questions.",
    retired: "Check back soon or browse other categories",
    render: () =>
      renderInIsolation(
        () => {
          jest.doMock("@/hooks", () => ANALYTICS_HOOKS);
          jest.doMock("@/components/AuthProvider", () => ({
            useAuthContext: () => ({ user: null, isLoading: false }),
          }));
          jest.doMock("@/lib/api", () => ({ fetchFeed: () => {} }));
          jest.doMock("swr", () => ({
            __esModule: true,
            default: () => settled({ items: [] }),
          }));
        },
        () => {
          const Page = require("@/app/categories/[slug]/page").default;
          return React.createElement(Page, { params: { slug: "politics" } });
        },
      ),
  },

  {
    site: "app/playoffs · no championship odds",
    emptyState: "playoffs-no-championship-odds",
    states:
      "This grid covers NBA championship markets from sportsbooks and prediction markets.",
    retired: "Odds will appear when sportsbooks and prediction markets publish",
    render: () =>
      renderInIsolation(
        () => {
          jest.doMock("@/hooks", () => ANALYTICS_HOOKS);
          jest.doMock("@/lib/api", () => ({
            fetchChampionshipGrid: () => {},
            fetchGolfSchedule: () => {},
          }));
          jest.doMock("swr", () => ({
            __esModule: true,
            default: (key: unknown) => {
              if (key === null || key === undefined) return settled(undefined);
              // A grid that ANSWERED — not a timeout, not an error — and holds
              // no participants in any column. That distinction is the whole
              // point of this empty state (#901).
              return settled({
                league: "nba",
                name: "NBA Championship",
                columns: [],
                teams: [],
                grouped_teams: null,
                sources_available: [],
              });
            },
          }));
        },
        () => {
          const Page = require("@/app/playoffs/[sport]/page").default;
          return React.createElement(Page, { params: { sport: "nba" } });
        },
      ),
  },

  {
    site: "app/hub · no open markets for this competition",
    emptyState: "entity-competition-present",
    states: "This page collects every open market for this competition.",
    retired: "No open markets right now. Check back when the next card is announced.",
    render: () =>
      renderInIsolation(
        () => {
          jest.doMock("@/hooks", () => ANALYTICS_HOOKS);
          jest.doMock("next/navigation", () => ({
            useParams: () => ({ competition: "mma" }),
            useRouter: () => ({ push: () => {} }),
          }));
          jest.doMock("@/lib/api", () => ({
            fetchHub: () => {},
            formatProbability: (p: number) => `${p}%`,
          }));
          jest.doMock("swr", () => ({
            __esModule: true,
            default: () =>
              settled({
                label: "MMA",
                title: "MMA",
                blurb: "Every open MMA market.",
                emoji: "\u{1F94A}",
                upcoming: [],
                sections: {},
                section_labels: {},
              }),
          }));
        },
        () => React.createElement(require("@/app/hub/[competition]/page").default),
      ),
  },

  {
    site: "app/discover · ChallengeModal has no cards",
    emptyState: "challenge-no-cards",
    states: "The daily challenge draws its questions from the live feed.",
    retired: "Check back after the feed refreshes.",
    render: () =>
      renderInIsolation(
        () => {
          jest.doMock("@/hooks", () => ANALYTICS_HOOKS);
          jest.doMock("@/lib/analytics", () => ({ trackEvent: () => {} }));
        },
        () => {
          // The modal is exported for this render. `items: []` is the state the
          // empty branch exists for: the challenge opened and the feed held
          // nothing eligible.
          const { ChallengeModal } = require("@/app/discover/page");
          return React.createElement(ChallengeModal, {
            items: [],
            currentIndex: 0,
            completed: false,
            onClose: () => {},
            onGuessCompleted: () => {},
            onNextQuestion: () => {},
          });
        },
      ),
  },
];

/* ═════════════════════════════ the anchors ═════════════════════════════════ */

describe.each(CASES.map((c) => [c.site, c] as const))("UX-P223 · %s", (_site, c) => {
  // Rendered ONCE per case: these are pure renders of a fixed state, and paying
  // for four of them per site would triple the file's runtime for no signal.
  let markup: string;
  let text: string;

  beforeAll(() => {
    markup = c.render();
    text = visibleText(markup);
  });

  it("renders its empty state at all", () => {
    // Ordered before the copy rows on purpose: if the page silently rendered a
    // skeleton or an error instead, every assertion below would be about a
    // screen the reader never reached, and `not.toContain` would pass vacuously.
    expect(markup).toContain(`data-empty-state-name="${c.emptyState}"`);
  });

  it("a reader in this state can SEE what the page is", () => {
    expect(text).toContain(c.states);
  });

  it("and is not promised a refill", () => {
    expect(text).not.toContain(c.retired);
  });
});

/* ════════════════ the anchor is binding — CERT-566's own attack ════════════ */

describe("UX-P223 · the render cannot be satisfied from the wrong branch", () => {
  it("every page site in the sibling file is rendered here", () => {
    // The sibling file's six page sites and this file's six cases must stay in
    // step. Without this, the cheapest way to make a render fail go away is to
    // delete the case and leave the source anchor behind — which is exactly the
    // downgrade CERT-566 blocked.
    /* eslint-disable @typescript-eslint/no-var-requires */
    const source: string = require("node:fs").readFileSync(
      require("node:path").join(__dirname, "emptyStatesStateWhatTheyAre.test.tsx"),
      "utf8",
    );
    /* eslint-enable @typescript-eslint/no-var-requires */
    const scoped = [...source.matchAll(/emptyState:\s*"([^"]+)"/g)].map((m) => m[1]).sort();
    expect(CASES.map((c) => c.emptyState).sort()).toEqual(scoped);
  });

  it("the signed-out My Stuff branch does NOT satisfy the My Stuff anchor", () => {
    // CERT-566 moved the marker AND the sentence into the signed-out branch and
    // the scoped source anchor followed them. This renders that same page signed
    // OUT: whatever the signed-out screen says, it is not this site's anchor, so
    // the copy has to live on the authenticated screen to be counted.
    const signedOut = renderInIsolation(
      () => registerMyStuffMocks({ authenticated: false }),
      () => React.createElement(require("@/app/my-stuff/page").default),
    );

    // The signed-out screen is a real screen and it renders …
    expect(visibleText(signedOut).length).toBeGreaterThan(0);
    // … but it is NOT where the authenticated empty state lives.
    expect(signedOut).not.toContain('data-empty-state-name="my-stuff-no-teams"');
  });

  it("a reader with NO saved teams gets onboarding, not the empty state", () => {
    // The other side of My Stuff's State-B gate, and the row CERT-569's
    // mutation needed. `teamCount === 0` -> `teamCount !== null` sends EVERY
    // real authenticated reader to onboarding; the `team_count: 3` render above
    // catches that, and this row catches the inverse — a gate weakened so that
    // nobody is ever onboarded — so the predicate is pinned from both sides.
    const noTeams = renderInIsolation(
      () => registerMyStuffMocks({ authenticated: true, teamCount: 0 }),
      () => React.createElement(require("@/app/my-stuff/page").default),
    );

    expect(visibleText(noTeams)).toContain("Follow some teams to get started");
    expect(noTeams).not.toContain('data-empty-state-name="my-stuff-no-teams"');
  });
});
