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
  isValidDrawSelection,
  readRememberedDrawChoice,
  rememberDrawChoice,
  tournamentDrawStorageKey,
} from "@/components/tournament/DrawToggle";
import { defaultDraw } from "@/lib/matchList";

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
