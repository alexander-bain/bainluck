/**
 * #11424 — Tournament page: Back from a match forgets the selected draw
 * (Women's → Men's).
 *
 * Repro from the issue:
 *   1. Open `/tournaments/us-open` and select **Women's** (`womens-singles`).
 *   2. Tap a match row (e.g. **Anisimova vs Svitolina** → `/events/15310026`).
 *   3. Press the browser Back button.
 *
 * Before this fix, `drawChoice` lived only in React `useState(null)`, so the
 * remounted `/tournaments/us-open` page re-ran
 * `defaultDraw(payload.slate?.matches ?? [], DRAWS) ?? OPENING_DRAW_FALLBACK`
 * and snapped back to **Men's** (`mens-singles`).
 */

import * as fs from "fs";
import * as path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import DrawToggle, {
  DOUBLES_DRAW,
  DRAWS,
  type DrawPersistenceWindow,
  OPENING_DRAW_FALLBACK,
  TOURNAMENT_DRAW_PARAM,
  drawOptions,
  isValidDrawSelection,
  readRememberedDrawChoice,
  rememberDrawChoice,
  tournamentDrawStorageKey,
} from "@/components/tournament/DrawToggle";
import { defaultDraw } from "@/lib/matchList";
import { selectionDraws } from "@/lib/tournamentResults";

function createMockWindow(initialPath = "/tournaments/us-open") {
  const store = new Map<string, string>();
  let currentUrl = new URL(initialPath, "https://bainluck.com");

  const win: DrawPersistenceWindow & {
    navigate: (nextPath: string) => void;
    pathnameAndSearch: () => string;
  } = {
    location: {
      get href() {
        return currentUrl.toString();
      },
      get search() {
        return currentUrl.search;
      },
    },
    history: {
      state: { idx: 1 },
      replaceState: (_state, _unused, url) => {
        if (typeof url === "string") {
          currentUrl = new URL(url, "https://bainluck.com");
        } else if (url instanceof URL) {
          currentUrl = new URL(url.toString());
        }
      },
    },
    sessionStorage: {
      getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
    },
    navigate(nextPath: string) {
      currentUrl = new URL(nextPath, "https://bainluck.com");
    },
    pathnameAndSearch() {
      return `${currentUrl.pathname}${currentUrl.search}`;
    },
  };

  return win;
}

describe("#11424 — tournament draw selection survives match navigation + Back", () => {
  let mockWin: ReturnType<typeof createMockWindow>;

  beforeEach(() => {
    mockWin = createMockWindow("/tournaments/us-open");
    (globalThis as unknown as { window?: DrawPersistenceWindow }).window = mockWin;
  });

  afterEach(() => {
    delete (globalThis as unknown as { window?: DrawPersistenceWindow }).window;
  });

  it("remembers Women's in both URL (?draw=womens-singles) and sessionStorage when selected", () => {
    rememberDrawChoice("us-open", "womens-singles");

    expect(mockWin.location?.search).toBe(
      `?${TOURNAMENT_DRAW_PARAM}=womens-singles`
    );
    expect(
      mockWin.sessionStorage?.getItem(tournamentDrawStorageKey("us-open"))
    ).toBe("womens-singles");

    const restored = readRememberedDrawChoice("us-open") ?? OPENING_DRAW_FALLBACK;
    const html = renderToStaticMarkup(
      <DrawToggle draw={restored} onSelect={() => {}} />
    );
    expect(html).toContain('data-draw="womens-singles" data-active="true"');
    expect(html).toContain('data-draw="mens-singles" data-active="false"');
  });

  it("restores Women's after navigating to /events/15310026 and pressing Back", () => {
    // 1. Reader selects Women's on /tournaments/us-open
    rememberDrawChoice("us-open", "womens-singles");
    expect(mockWin.pathnameAndSearch()).toBe(
      "/tournaments/us-open?draw=womens-singles"
    );

    // 2. Reader taps Anisimova vs Svitolina -> /events/15310026, then hits Back.
    // Case A: browser restores the history URL with ?draw=womens-singles.
    mockWin.navigate("/events/15310026");
    mockWin.navigate("/tournaments/us-open?draw=womens-singles");
    const restoredFromHistoryUrl =
      readRememberedDrawChoice("us-open") ??
      defaultDraw([], DRAWS) ??
      OPENING_DRAW_FALLBACK;
    expect(restoredFromHistoryUrl).toBe("womens-singles");

    // Case B: router remounts /tournaments/us-open without query params;
    // sessionStorage still restores Women's and re-syncs the URL.
    mockWin.navigate("/tournaments/us-open");
    const restoredFromStorage =
      readRememberedDrawChoice("us-open") ??
      defaultDraw(
        [
          {
            draw: "mens-singles",
            live_state: "in_progress",
            scheduled_date: "2026-09-05T15:00:00Z",
          } as never,
        ],
        DRAWS
      ) ??
      OPENING_DRAW_FALLBACK;
    expect(restoredFromStorage).toBe("womens-singles");
    expect(mockWin.location?.search).toBe("?draw=womens-singles");
  });

  it("falls back to defaultDraw and OPENING_DRAW_FALLBACK when the reader has not chosen a draw", () => {
    expect(readRememberedDrawChoice("us-open")).toBeNull();

    const liveWomens =
      readRememberedDrawChoice("us-open") ??
      defaultDraw(
        [
          {
            draw: "womens-singles",
            live_state: "in_progress",
            scheduled_date: "2026-09-05T15:00:00Z",
          } as never,
        ],
        DRAWS
      ) ??
      OPENING_DRAW_FALLBACK;
    expect(liveWomens).toBe("womens-singles");

    const betweenSessions =
      readRememberedDrawChoice("us-open") ??
      defaultDraw([], DRAWS) ??
      OPENING_DRAW_FALLBACK;
    expect(betweenSessions).toBe("mens-singles");
  });

  it("isolates remembered draws by tournament slug and honors an explicit ?draw= link", () => {
    rememberDrawChoice("us-open", "womens-singles");

    mockWin.navigate("/tournaments/wimbledon");
    expect(readRememberedDrawChoice("wimbledon")).toBeNull();

    // An explicit deep link to ?draw=mens-singles overrides prior sessionStorage.
    mockWin.navigate("/tournaments/us-open?draw=mens-singles");
    expect(readRememberedDrawChoice("us-open")).toBe("mens-singles");
    expect(
      mockWin.sessionStorage?.getItem(tournamentDrawStorageKey("us-open"))
    ).toBe("mens-singles");
  });

  it("accepts Doubles when valid, rejects unknown draw ids, and tolerates storage errors", () => {
    expect(isValidDrawSelection(DOUBLES_DRAW.id)).toBe(true);
    expect(isValidDrawSelection("mixed-triples")).toBe(false);

    mockWin.navigate("/tournaments/us-open?draw=not-a-draw");
    expect(readRememberedDrawChoice("us-open")).toBeNull();

    const throwingWindow: DrawPersistenceWindow = {
      location: {
        href: "https://bainluck.com/tournaments/us-open",
        search: "",
      },
      history: {
        state: null,
        replaceState: jest.fn(),
      },
      sessionStorage: {
        getItem: () => {
          throw new Error("QuotaExceededError");
        },
        setItem: () => {
          throw new Error("QuotaExceededError");
        },
      },
    };

    expect(() =>
      rememberDrawChoice("us-open", "womens-singles", throwingWindow)
    ).not.toThrow();
    expect(throwingWindow.history?.replaceState).toHaveBeenCalledWith(
      null,
      "",
      "/tournaments/us-open?draw=womens-singles"
    );
    expect(readRememberedDrawChoice("us-open", undefined, throwingWindow)).toBeNull();
  });

  it("wires rememberDrawChoice and readRememberedDrawChoice into app/tournaments/[slug]/page.tsx", () => {
    const pageSource = fs.readFileSync(
      path.join(__dirname, "../../app/tournaments/[slug]/page.tsx"),
      "utf8"
    );

    expect(pageSource).toContain("readRememberedDrawChoice(slug)");
    expect(pageSource).toContain("rememberDrawChoice(slug, id)");
  });
});

/**
 * The page's own expressions, not a re-typed copy of them.
 *
 * No repo test can mount `TournamentPage` (node test environment, no DOM), and
 * a route file may not carry named exports, so the two lines this ship rests on
 * are read out of `page.tsx` and evaluated against the real helpers. Reorder or
 * gate either line and these arms evaluate the edited line, so they go red.
 */
const PAGE_SOURCE = fs.readFileSync(
  path.join(__dirname, "../../app/tournaments/[slug]/page.tsx"),
  "utf8"
);

/** `setDrawChoice((current) => …)` at first payload: what the page opens on. */
function openingChoice(current: string | null, slug: string, payload: unknown): string {
  const found = PAGE_SOURCE.match(/setDrawChoice\(\s*\(current\) =>\s*([\s\S]*?)\s*\);/);
  expect(found).not.toBeNull();
  return new Function(
    "current", "slug", "payload",
    "readRememberedDrawChoice", "defaultDraw", "DRAWS", "OPENING_DRAW_FALLBACK",
    `return (${found![1]});`
  )(current, slug, payload, readRememberedDrawChoice, defaultDraw, DRAWS, OPENING_DRAW_FALLBACK);
}

/** `const draw = …`: the draw the pills and every filtered section show. */
function drawOnScreen(drawChoice: string | null, data: unknown): string {
  const found = PAGE_SOURCE.match(/const draw =\s*([\s\S]*?);\n/);
  expect(found).not.toBeNull();
  const typed = data as { slate?: { matches?: never[] }; results?: { matches?: never[] } };
  const drawPills = drawOptions([typed.slate?.matches ?? [], typed.results?.matches ?? []]);
  return new Function(
    "drawChoice", "drawPills", "data",
    "isValidDrawSelection", "defaultDraw", "DRAWS", "OPENING_DRAW_FALLBACK",
    `return (${found![1]});`
  )(drawChoice, drawPills, data, isValidDrawSelection, defaultDraw, DRAWS, OPENING_DRAW_FALLBACK);
}

function pressedPills(draw: string, data: { slate?: { matches?: never[] }; results?: { matches?: never[] } }) {
  const pills = drawOptions([data.slate?.matches ?? [], data.results?.matches ?? []]);
  const html = renderToStaticMarkup(<DrawToggle draw={draw} draws={pills} onSelect={() => {}} />);
  return [...html.matchAll(/data-draw="([^"]+)" data-active="true"/g)].map((m) => m[1]);
}

const row = (draw: string, live_state = "in_progress") =>
  ({ draw, live_state, scheduled_date: "2026-09-05T15:00:00Z" }) as never;

describe("#11424 — the page opens on the remembered draw, and only on one it offers", () => {
  let mockWin: ReturnType<typeof createMockWindow>;

  afterEach(() => {
    delete (globalThis as unknown as { window?: DrawPersistenceWindow }).window;
  });

  function openAt(pathWithQuery: string) {
    mockWin = createMockWindow(pathWithQuery);
    (globalThis as unknown as { window?: DrawPersistenceWindow }).window = mockWin;
  }

  it("a remembered Women's beats the live Men's match — the issue's own match-day repro", () => {
    expect(PAGE_SOURCE).toMatch(
      /current \?\?\s*readRememberedDrawChoice\(slug\) \?\?\s*defaultDraw\(/
    );

    openAt("/tournaments/us-open");
    rememberDrawChoice("us-open", "womens-singles");
    mockWin.navigate("/tournaments/us-open"); // Back, remounted with no query
    const payload = { slate: { matches: [row("mens-singles")] } };

    const choice = openingChoice(null, "us-open", payload);
    expect(choice).toBe("womens-singles");
    expect(drawOnScreen(choice, payload)).toBe("womens-singles");
    expect(pressedPills(drawOnScreen(choice, payload), payload)).toEqual(["womens-singles"]);
  });

  it("with nothing remembered it still opens on the live draw", () => {
    openAt("/tournaments/us-open");
    const payload = { slate: { matches: [row("womens-singles")] } };
    expect(openingChoice(null, "us-open", payload)).toBe("womens-singles");
  });

  it.each([
    ["a ?draw=doubles link", "/tournaments/us-open?draw=doubles", false],
    ["a stored doubles choice", "/tournaments/us-open", true],
  ])("%s on a tournament with no doubles rows opens on an offered draw, one pill pressed", (_label, at, stored) => {
    openAt(at);
    if (stored) {
      mockWin.sessionStorage?.setItem(tournamentDrawStorageKey("us-open"), "doubles");
    }
    const first = { slate: { matches: [row("womens-singles"), row("mens-singles", "scheduled")] } };
    const choice = openingChoice(null, "us-open", first);
    expect(choice).toBe("doubles"); // restored, not refused

    const shown = drawOnScreen(choice, first);
    expect(shown).toBe("womens-singles"); // the draw being played
    expect(pressedPills(shown, first)).toEqual(["womens-singles"]);
    const visible = first.slate.matches.filter((m: { draw: string }) =>
      selectionDraws(shown).includes(m.draw)
    );
    expect(visible.length).toBeGreaterThan(0);

    // `rest` lands with no doubles either: still the offered draw.
    const merged = { ...first, results: { matches: [row("mens-singles", "complete")] } };
    expect(pressedPills(drawOnScreen(choice, merged), merged)).toEqual(["womens-singles"]);
  });

  it("a genuine results-only Doubles choice is kept, and shown once `rest` brings the doubles rows", () => {
    openAt("/tournaments/us-open");
    rememberDrawChoice("us-open", DOUBLES_DRAW.id);
    mockWin.navigate("/tournaments/us-open"); // Back, remounted with no query

    const first = { slate: { matches: [row("mens-singles")] } };
    const choice = openingChoice(null, "us-open", first);
    expect(choice).toBe("doubles");
    expect(drawOnScreen(choice, first)).toBe("mens-singles");

    const merged = { ...first, results: { matches: [row("mixed-doubles", "complete")] } };
    expect(drawOnScreen(choice, merged)).toBe("doubles");
    expect(pressedPills(drawOnScreen(choice, merged), merged)).toEqual(["doubles"]);
    expect(mockWin.sessionStorage?.getItem(tournamentDrawStorageKey("us-open"))).toBe("doubles");
  });
});
