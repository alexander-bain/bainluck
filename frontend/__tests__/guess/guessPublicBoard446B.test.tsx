/** @jest-environment jsdom */
import React, { StrictMode, act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

import ChanceGame from "@/app/guess/ChanceGame";
import GuessPage from "@/app/guess/page";
import { formatOrdinal, GuessApiError, readerSafeBoardError } from "@/lib/guess/api";
import { emptyEntry, fullGuess } from "@/lib/guess/engine";
import { GUESS_PACK } from "@/lib/guess/pack";
import { loadGame, pruneExpiredSavedGames, saveGame } from "@/lib/guess/storage";
import type { GamePack } from "@/lib/guess/types";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const DAILY_PACK: GamePack = { ...GUESS_PACK, id: "2026-11-28", code: "p097" };

function mockJsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

async function flushUi(rounds = 18): Promise<void> {
  for (let i = 0; i < rounds; i++) {
    await act(async () => {
      await Promise.resolve();
    });
  }
}

describe("446: B public board, unscheduled copy, StrictMode addName, 30d storage prune, & error handling", () => {
  const origFetch = globalThis.fetch;
  const origScrollTo = window.scrollTo;
  let host: HTMLDivElement;
  let root: ReturnType<typeof createRoot> | null = null;

  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/guess");
    window.scrollTo = jest.fn();
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    if (root) {
      await act(async () => {
        root?.unmount();
      });
      root = null;
    }
    host.remove();
    globalThis.fetch = origFetch;
    window.scrollTo = origScrollTo;
    window.localStorage.clear();
  });

  it("formats ordinals accurately through teens and higher numbers", () => {
    expect(formatOrdinal(1)).toBe("1st");
    expect(formatOrdinal(2)).toBe("2nd");
    expect(formatOrdinal(3)).toBe("3rd");
    expect(formatOrdinal(4)).toBe("4th");
    expect(formatOrdinal(11)).toBe("11th");
    expect(formatOrdinal(12)).toBe("12th");
    expect(formatOrdinal(13)).toBe("13th");
    expect(formatOrdinal(14)).toBe("14th");
    expect(formatOrdinal(21)).toBe("21st");
    expect(formatOrdinal(81)).toBe("81st");
  });

  it("keeps reader-safe 409/429/nickname_refused sentences and replaces developer 404/500 messages", () => {
    expect(readerSafeBoardError(new GuessApiError(409, "That nickname already finished in this group today."), "Fallback")).toBe(
      "That nickname already finished in this group today.",
    );
    expect(readerSafeBoardError(new GuessApiError(429, "Too many games sent from here right now."), "Fallback")).toBe(
      "Too many games sent from here right now.",
    );
    expect(
      readerSafeBoardError(
        new GuessApiError(422, "Please pick another nickname for the board.", "nickname_refused"),
        "Fallback",
      ),
    ).toBe("Please pick another nickname for the board.");
    expect(readerSafeBoardError(new GuessApiError(404, "No edition stored for 2026-11-28."), "Could not load the group board right now.")).toBe(
      "Could not load the group board right now.",
    );
    expect(readerSafeBoardError(new GuessApiError(500, "Traceback: sqlalchemy..."), "Could not save your finished game right now.")).toBe(
      "Could not save your finished game right now.",
    );
  });

  it("prunes locally saved /guess days older than 30 days while keeping recent days and legacy sets", () => {
    const expiredPack: GamePack = { ...GUESS_PACK, id: "2026-10-15", code: "p001" };
    const recentPack: GamePack = { ...GUESS_PACK, id: "2026-11-15", code: "p084" };
    const entry = { ...emptyEntry(DAILY_PACK, "Alex", "here"), guesses: DAILY_PACK.cards.map((c) => fullGuess(c)) };

    saveGame({ packId: expiredPack.id, phase: "results", index: 14, turn: 0, here: [entry], link: [] });
    saveGame({ packId: recentPack.id, phase: "results", index: 14, turn: 0, here: [entry], link: [] });
    window.localStorage.setItem("bainluck_guess_v1:c1", JSON.stringify({ packId: "c1", phase: "play", index: 2, turn: 0, here: [entry], link: [] }));

    pruneExpiredSavedGames(new Date("2026-11-28T18:00:00Z"));

    expect(window.localStorage.getItem("bainluck_guess_v1:2026-10-15")).toBeNull();
    expect(window.localStorage.getItem("bainluck_guess_v1:2026-11-15")).not.toBeNull();
    expect(window.localStorage.getItem("bainluck_guess_v1:c1")).not.toBeNull();
    expect(loadGame(recentPack)).not.toBeNull();
  });

  it("keeps 'Ann' as 'Ann' (never 'Ann 2') when StrictMode runs state updaters twice", async () => {
    await act(async () => {
      root?.render(
        <StrictMode>
          <ChanceGame pack={DAILY_PACK} />
        </StrictMode>,
      );
    });
    await flushUi();

    const input = host.querySelector('[data-testid="name-input"]') as HTMLInputElement;
    const notice = host.querySelector('[data-testid="name-board-notice"]');
    expect(notice?.textContent).toContain("public board for 30 days");
    expect(notice?.textContent).toContain("nickname is fine");

    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(input, "Ann");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const addBtn = Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.trim() === "Add") as HTMLButtonElement;
    await act(async () => {
      addBtn.click();
    });
    await flushUi(6);

    const pills = Array.from(host.querySelectorAll("ul li")).map((li) => li.textContent);
    expect(pills.some((t) => t?.includes("Ann"))).toBe(true);
    expect(pills.some((t) => t?.includes("Ann 2"))).toBe(false);
  });

  it("shows exact unscheduled banner copy when GET /api/guess/today answers reason='unscheduled'", async () => {
    globalThis.fetch = jest.fn(async () =>
      mockJsonResponse(503, {
        detail: "No new cards today. Here is the latest set.",
        reason: "unscheduled",
      }),
    ) as typeof fetch;

    await act(async () => {
      root?.render(<GuessPage />);
    });
    await flushUi();

    const banner = host.querySelector('[data-testid="fallback-edition-banner"]');
    expect(banner?.textContent).toContain("No new cards today. Here is the latest set.");
  });

  it("renders public board with >10 games, 'You finished Nth of M', pagination, and handles nickname_refused", async () => {
    const entries24 = Array.from({ length: 24 }, (_, idx) => ({
      entry_id: 100 + idx,
      rank: idx + 1,
      nickname: idx === 13 ? "Alex" : `Player ${idx + 1}`,
      points: 225 - idx * 3,
      step_points: [50, 75, 100 - idx * 3],
      step_labels: ["5 of 5", "5 of 5", String(100 - idx * 3)],
      total_time_seconds: 30 + idx,
    }));

    const mePlayer = {
      ...emptyEntry(DAILY_PACK, "Bad!", "here"),
      guesses: DAILY_PACK.cards.map((c) => fullGuess(c)),
      times: [10, 12, 14],
    };
    saveGame({
      packId: DAILY_PACK.id,
      phase: "results",
      index: 14,
      turn: 0,
      here: [mePlayer],
      link: [],
    });

    let allowSave = false;
    globalThis.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/api/guess/board")) {
        const u = new URL(s, "http://localhost");
        const page = Number(u.searchParams.get("page") || "1");
        const start = (page - 1) * 20;
        const pageRows = entries24.slice(start, start + 20);
        const entryId = Number(u.searchParams.get("entry_id") || "0");
        return mockJsonResponse(200, {
          day: DAILY_PACK.id,
          edition_code: DAILY_PACK.code,
          steps: DAILY_PACK.steps.map((st) => ({ name: st.name })),
          total_count: 24,
          page,
          page_size: 20,
          total_pages: 2,
          entries: pageRows,
          me: entryId === 113 ? entries24[13] : null,
        });
      }
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        if (!allowSave) {
          return mockJsonResponse(422, {
            detail: "Names can use only letters, spaces, numbers, apostrophes, and hyphens. Please pick another.",
            reason: "nickname_refused",
          });
        }
        return mockJsonResponse(201, {
          day: DAILY_PACK.id,
          edition_code: DAILY_PACK.code,
          group_code: "grp1234567",
          entries: [
            {
              entry_id: 113,
              nickname: "Alex",
              answers: mePlayer.guesses,
              step_times: [10, 12, 14],
              points: entries24[13].points,
              step_points: entries24[13].step_points,
              step_labels: entries24[13].step_labels,
              total_time_seconds: 36,
            },
          ],
        });
      }
      return mockJsonResponse(200, { day: DAILY_PACK.id, edition_code: DAILY_PACK.code, group_code: "grp1234567", entries: [] });
    }) as typeof fetch;

    await act(async () => {
      root?.render(<ChanceGame pack={DAILY_PACK} />);
    });
    await flushUi();

    // Refused nickname prompts rename directly under plain server message
    const errBox = host.querySelector('[data-testid="save-error"]');
    expect(errBox?.textContent).toContain("Please pick another.");
    const renameInput = host.querySelector('[data-testid="conflict-name-input"]') as HTMLInputElement;
    expect(renameInput).not.toBeNull();

    allowSave = true;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(renameInput, "Alex");
      renameInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const saveBtn = host.querySelector('[data-testid="conflict-save-button"]') as HTMLButtonElement;
    await act(async () => {
      saveBtn.click();
    });
    await flushUi(24);

    expect(host.querySelector('[data-testid="public-board-count"]')?.textContent).toContain("24 games");
    expect(host.querySelector('[data-testid="public-board-place"]')?.textContent).toContain("You finished 14th of 24.");
    expect(host.querySelector('[data-testid="public-board-you-badge"]')?.textContent).toContain("You");
    expect(host.querySelectorAll('[data-testid="public-board-table"] tbody tr').length).toBe(20);

    // Paging to page 2 shows remaining 4 rows
    const nextBtn = host.querySelector('[data-testid="public-board-next"]') as HTMLButtonElement;
    await act(async () => {
      nextBtn.click();
    });
    await flushUi();
    expect(host.querySelector('[data-testid="public-board-page-label"]')?.textContent).toContain("Page 2 of 2");
    expect(host.querySelectorAll('[data-testid="public-board-table"] tbody tr').length).toBe(4);
  });
});
