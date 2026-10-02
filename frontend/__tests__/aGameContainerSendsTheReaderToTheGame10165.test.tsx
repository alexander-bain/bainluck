/**
 * #10165 — A POLYMARKET GAME CONTAINER SENDS THE READER TO THE GAME.
 *
 * Production `/futures/63612402` at 390px, 2026-10-02 04:45Z, "New York Yankees
 * vs. Tampa Bay Rays":
 *
 *     46%  New York Yankees — New York Yankees        ← the hero
 *     Games This Week: Sat 10/3, Mon 10/5, Wed 10/7   ← each "New York Yankees 46%"
 *     All Outcomes: 1 Over — O/U 6.5 54% · 2 New York Yankees 46% · 3 NRFI 43% · …
 *
 * Nine legs of nine different questions ranked as one field. The board is
 * Polymarket event 1113712's container row, linked to game 15322539, and the
 * server now names that game (`container_of_event_id`, lane1's #10173). The
 * route's layout redirects there before anything renders.
 *
 * Controls: a board the server does not name (null, absent on older builds,
 * malformed) and every failed lookup render the page exactly as before.
 */

import React from "react";

const mockRedirect = jest.fn((path: string) => {
  // Next's redirect() never returns — it throws NEXT_REDIRECT.
  throw new Error(`NEXT_REDIRECT:${path}`);
});

jest.mock("next/navigation", () => ({
  redirect: (path: string) => mockRedirect(path),
}));

import FuturesDetailLayout from "@/app/futures/[id]/layout";
import { gameContainerRedirectPath } from "@/lib/futuresDetailDisplay";

/* ────────────────────────────── the harness ────────────────────────────── */

function respondWith(status: number, body: unknown = {}) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as unknown as typeof fetch;
}

/** 63612402, trimmed to what the route reads, as production serves it. */
function containerBoard(overrides: Record<string, unknown> = {}) {
  return {
    id: 63612402,
    name: "New York Yankees vs. Tampa Bay Rays",
    source: "polymarket",
    market_type: "field",
    status: "open",
    event_id: null,
    group_id: "polymarket:1113712",
    outcomes: [
      { id: 1, name: "Over", label: "O/U 6.5", probability: 0.54 },
      { id: 2, name: "New York Yankees", label: "New York Yankees", probability: 0.46 },
    ],
    container_of_event_id: 15322539,
    ...overrides,
  };
}

const CHILD = <main data-testid="board">the board</main>;

async function renderLayout(id = "63612402") {
  return FuturesDetailLayout({ children: CHILD, params: Promise.resolve({ id }) });
}

beforeEach(() => {
  mockRedirect.mockClear();
});

/* ─────────────────────────────── the defect ─────────────────────────────── */

describe("#10165 the container board redirects to its game", () => {
  it("a named container sends the reader to /events/15322539", async () => {
    respondWith(200, containerBoard());
    await expect(renderLayout()).rejects.toThrow("NEXT_REDIRECT:/events/15322539");
    expect(mockRedirect).toHaveBeenCalledTimes(1);
    expect(mockRedirect).toHaveBeenCalledWith("/events/15322539");
  });

  it("asks the server for the board the URL names", async () => {
    respondWith(200, containerBoard());
    await expect(renderLayout()).rejects.toThrow();
    const [url] = (global.fetch as jest.Mock).mock.calls[0];
    expect(String(url)).toMatch(/\/api\/futures\/63612402$/);
  });
});

/* ─────────────────────────────── the controls ───────────────────────────── */

describe("#10165 every other board renders as it did", () => {
  it.each([
    ["null (not a container, or an unlinked one)", { container_of_event_id: null }],
    ["absent (a build before #10173)", { container_of_event_id: undefined }],
    ["zero", { container_of_event_id: 0 }],
    ["a string", { container_of_event_id: "15322539" }],
    ["a fraction", { container_of_event_id: 15322539.5 }],
  ])("container_of_event_id %s → the board, no redirect", async (_label, overrides) => {
    respondWith(200, containerBoard(overrides));
    const out = await renderLayout();
    expect(mockRedirect).not.toHaveBeenCalled();
    expect(out).toEqual(<>{CHILD}</>);
  });

  it.each([
    ["404", 404],
    ["500", 500],
  ])("a %s lookup → the page's own miss handling, no redirect", async (_label, status) => {
    respondWith(status);
    const out = await renderLayout();
    expect(mockRedirect).not.toHaveBeenCalled();
    expect(out).toEqual(<>{CHILD}</>);
  });

  it("a dropped connection → the board, no redirect", async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error("ECONNRESET")) as unknown as typeof fetch;
    const out = await renderLayout();
    expect(mockRedirect).not.toHaveBeenCalled();
    expect(out).toEqual(<>{CHILD}</>);
  });

  it("a non-id segment never fetches and never redirects", async () => {
    respondWith(200, containerBoard());
    const out = await renderLayout("not-an-id");
    expect(global.fetch).not.toHaveBeenCalled();
    expect(mockRedirect).not.toHaveBeenCalled();
    expect(out).toEqual(<>{CHILD}</>);
  });
});

describe("#10165 gameContainerRedirectPath", () => {
  it("names the game page for a positive integer id, nothing else", () => {
    expect(gameContainerRedirectPath({ container_of_event_id: 15322539 })).toBe("/events/15322539");
    expect(gameContainerRedirectPath({ container_of_event_id: null })).toBeNull();
    expect(gameContainerRedirectPath({})).toBeNull();
    expect(gameContainerRedirectPath({ container_of_event_id: -1 })).toBeNull();
  });
});
