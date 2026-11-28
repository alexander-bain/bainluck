/** @jest-environment jsdom */
import fs from "fs";
import path from "path";
import React, { StrictMode, act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

import ChanceGame from "@/app/guess/ChanceGame";
import GuessPage from "@/app/guess/page";
import {
  cleanDailyNickname,
  formatOrdinal,
  GuessApiError,
  isAllowedNicknameChars,
  readerSafeBoardError,
} from "@/lib/guess/api";
import { BACKEND_AUTH_KEY } from "@/lib/firebase";
import { SIGNED_IN_MARKER } from "@/hooks/useAuth";
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

async function flushUi(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i++) {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
  }
}

async function waitForCondition(predicate: () => boolean, maxRounds = 30): Promise<void> {
  for (let i = 0; i < maxRounds; i++) {
    if (predicate()) return;
    await flushUi(1);
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
    await waitForCondition(() => host.querySelector('[data-testid="save-error"]') !== null);

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
    await waitForCondition(
      () => host.querySelector('[data-testid="public-board-count"]')?.textContent?.includes("24 games") ?? false,
    );

    expect(host.querySelector('[data-testid="public-board-count"]')?.textContent).toContain("24 games");
    expect(host.querySelector('[data-testid="public-board-place"]')?.textContent).toContain("You finished 14th of 24.");
    expect(host.querySelector('[data-testid="public-board-you-badge"]')?.textContent).toContain("You");
    expect(host.querySelectorAll('[data-testid="public-board-table"] tbody tr').length).toBe(20);

    // Paging to page 2 shows remaining 4 rows
    const nextBtn = host.querySelector('[data-testid="public-board-next"]') as HTMLButtonElement;
    await act(async () => {
      nextBtn.click();
    });
    await waitForCondition(
      () => host.querySelector('[data-testid="public-board-page-label"]')?.textContent?.includes("Page 2 of 2") ?? false,
    );
    expect(host.querySelector('[data-testid="public-board-page-label"]')?.textContent).toContain("Page 2 of 2");
    expect(host.querySelectorAll('[data-testid="public-board-table"] tbody tr').length).toBe(4);
  }, 15_000);

  it("allows accented Latin letters, periods, and ordinary multi-word names while matching server char parity", async () => {
    const parityPath = path.resolve(
      __dirname,
      "..",
      "..",
      "..",
      "backend",
      "data",
      "guess",
      "nickname_parity_cases.json",
    );
    const parity = JSON.parse(fs.readFileSync(parityPath, "utf8")) as {
      cases: { raw: string; chars_allowed: boolean; server_allowed: boolean; reason: string | null }[];
    };
    expect(parity.cases.length).toBeGreaterThanOrEqual(45);
    for (const c of parity.cases) {
      expect({ raw: c.raw, allowed: isAllowedNicknameChars(c.raw) }).toEqual({
        raw: c.raw,
        allowed: c.chars_allowed,
      });
    }

    for (const ok of [
      "José",
      "Zoë",
      "Søren",
      "Daphné",
      "Alex B.",
      "Matt Watson",
      "Scott Watts",
      "Christopher",
      "O'Brien",
      "Mary-Kate",
      "Jean-Luc",
      "Cass",
      "Essex",
      "Nigel",
      "Łukasz",
      "Þór",
      "Straße",
      "Nguyễn",
      "J.R.",
      "Yıldız",
      "İbrahim",
    ]) {
      expect({ ok, allowed: isAllowedNicknameChars(ok) }).toEqual({ ok, allowed: true });
      expect(cleanDailyNickname(ok)).toBe(ok);
    }
    for (const bad of ["Alex!", "bad_name", "...", "---", "ƒuck", "ƒ", "ꜰᴜᴄᴋ", "fᴜck", "ɐɓɔ"]) {
      expect({ bad, allowed: isAllowedNicknameChars(bad) }).toEqual({ bad, allowed: false });
    }

    await act(async () => {
      root?.render(<ChanceGame pack={DAILY_PACK} />);
    });
    await flushUi();

    const input = host.querySelector('[data-testid="name-input"]') as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    for (const badDraft of ["Bad!", "ƒuck", "ꜰᴜᴄᴋ"]) {
      await act(async () => {
        setter?.call(input, badDraft);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
      const hint = host.querySelector('[data-testid="name-char-hint"]');
      expect(hint?.textContent).toBe("Letters, numbers, spaces, periods, apostrophes, and hyphens only.");
    }
    await act(async () => {
      setter?.call(input, "Yıldız");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(host.querySelector('[data-testid="name-char-hint"]')).toBeNull();
  });

  it("shows 12-letter names cleanly without truncate, uses past-day board copy, and keeps Hide/Put back admin-only", async () => {
    const pastPack: GamePack = { ...GUESS_PACK, id: "2026-11-26", code: "p095" };
    const longName = "Maximilianus";
    const rowdyName = "Rowdy";
    const groupCode = "grp446past1";
    const mePlayer = {
      ...emptyEntry(pastPack, longName, "here"),
      entryId: 201,
      guesses: pastPack.cards.map((c) => fullGuess(c)),
      times: [10, 12, 14],
    };
    const rowdyAnswers = pastPack.cards.map((c) => fullGuess(c));
    saveGame({
      packId: pastPack.id,
      groupCode,
      joinedGroups: [groupCode],
      phase: "results",
      index: 14,
      turn: 0,
      here: [mePlayer],
      link: [],
    });

    let rowdyHidden = false;
    globalThis.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const s = String(url);
      const method = (init?.method ?? "GET").toUpperCase();
      if (s.includes("/api/guess/admin/hidden")) {
        return mockJsonResponse(
          200,
          rowdyHidden
            ? {
                authorized: true,
                day: pastPack.id,
                entries: [
                  {
                    entry_id: 202,
                    nickname: rowdyName,
                    points: 205,
                    total_time_seconds: 39,
                    hidden_at: "2026-11-28T12:00:00Z",
                    in_group: true,
                  },
                ],
              }
            : { authorized: true, day: pastPack.id, entries: [] },
        );
      }
      if (s.includes("/api/guess/admin/entries/202/hide") && method === "POST") {
        rowdyHidden = true;
        return mockJsonResponse(200, { status: "hidden", entry_id: 202, day: pastPack.id, hidden_at: "2026-11-28T12:00:00Z" });
      }
      if (s.includes("/api/guess/admin/entries/202/unhide") && method === "POST") {
        rowdyHidden = false;
        return mockJsonResponse(200, { status: "visible", entry_id: 202, day: pastPack.id });
      }
      if (s.includes("/api/guess/groups/")) {
        const entries = [
          {
            entry_id: 201,
            nickname: longName,
            answers: mePlayer.guesses,
            step_times: [10, 12, 14],
            points: 225,
            step_points: [50, 75, 100],
            step_labels: ["5 of 5", "5 of 5", "100"],
            total_time_seconds: 36,
          },
          ...(rowdyHidden
            ? []
            : [
                {
                  entry_id: 202,
                  nickname: rowdyName,
                  answers: rowdyAnswers,
                  step_times: [12, 13, 14],
                  points: 205,
                  step_points: [50, 75, 80],
                  step_labels: ["5 of 5", "5 of 5", "80"],
                  total_time_seconds: 39,
                },
              ]),
        ];
        return mockJsonResponse(200, { day: pastPack.id, edition_code: pastPack.code, group_code: groupCode, entries });
      }
      if (s.includes("/api/guess/board")) {
        const visible = [
          {
            entry_id: 201,
            rank: 1,
            nickname: longName,
            points: 225,
            step_points: [50, 75, 100],
            step_labels: ["5 of 5", "5 of 5", "100"],
            total_time_seconds: 36,
          },
          ...(rowdyHidden
            ? []
            : [
                {
                  entry_id: 202,
                  rank: 2,
                  nickname: rowdyName,
                  points: 205,
                  step_points: [50, 75, 80],
                  step_labels: ["5 of 5", "5 of 5", "80"],
                  total_time_seconds: 39,
                },
              ]),
        ];
        return mockJsonResponse(200, {
          day: pastPack.id,
          edition_code: pastPack.code,
          steps: pastPack.steps.map((st) => ({ name: st.name })),
          total_count: visible.length,
          page: 1,
          page_size: 20,
          total_pages: 1,
          entries: visible,
          me: visible[0],
        });
      }
      return mockJsonResponse(404, {});
    }) as typeof fetch;

    // 1. Reader (signed out) sees NO Hide controls, past-day copy naming Nov 26, zero "leaderboard", and no truncate on 12-letter name
    await act(async () => {
      root?.render(<ChanceGame pack={pastPack} initialGroupCode={groupCode} isToday={false} />);
    });
    await waitForCondition(
      () =>
        (host.querySelector('[data-testid="public-board"]')?.textContent?.includes("Everyone who played on Nov 26") ?? false) &&
        host.querySelector('[data-testid="public-board-row-me"]') !== null,
    );

    expect(host.querySelector('[data-testid="public-board"]')?.textContent).toContain("Everyone who played on Nov 26");
    expect(host.textContent?.toLowerCase()).not.toContain("leaderboard");
    expect(host.querySelector('[data-testid="group-hide-202"]')).toBeNull();
    expect(host.querySelector('[data-testid="public-hide-202"]')).toBeNull();
    expect(host.querySelector('[data-testid="admin-hidden-panel"]')).toBeNull();
    const mePublicRow = host.querySelector('[data-testid="public-board-row-me"]');
    expect(mePublicRow?.textContent).toContain(longName);
    expect(mePublicRow?.innerHTML).not.toContain("truncate");
    expect(host.querySelector('[data-testid="step-table"]')?.innerHTML).not.toContain("truncate");

    // 2. Signed-in admin sees Hide controls, opens in-page confirm, hides from BOTH boards, and puts Rowdy back
    window.localStorage.setItem(SIGNED_IN_MARKER, "true");
    window.localStorage.setItem(
      BACKEND_AUTH_KEY,
      JSON.stringify({
        uid: "admin-1",
        email: "alex@bainluck.com",
        displayName: "Alex",
        photoURL: null,
        idToken: "admin-jwt-446b",
        expiresAt: Date.now() + 3_600_000,
      }),
    );

    await act(async () => {
      root?.render(<ChanceGame key="admin-view" pack={pastPack} initialGroupCode={groupCode} isToday={false} />);
    });
    await waitForCondition(
      () =>
        host.querySelector('[data-testid="group-hide-202"]') !== null &&
        host.querySelector('[data-testid="public-hide-202"]') !== null,
    );

    const groupHideBtn = host.querySelector('[data-testid="group-hide-202"]') as HTMLButtonElement;
    expect(groupHideBtn).not.toBeNull();
    expect(host.querySelector('[data-testid="public-hide-202"]')).not.toBeNull();

    await act(async () => {
      groupHideBtn.click();
    });
    await waitForCondition(() => host.querySelector('[data-testid="admin-hide-confirm"]') !== null);

    const confirmBox = host.querySelector('[data-testid="admin-hide-confirm"]');
    expect(confirmBox?.textContent).toContain("Hide Rowdy from both boards?");

    const confirmYes = host.querySelector('[data-testid="admin-hide-confirm-yes"]') as HTMLButtonElement;
    await act(async () => {
      confirmYes.click();
    });
    await waitForCondition(() => host.querySelector('[data-testid="admin-hidden-panel"]') !== null);

    expect(host.querySelector('[data-testid="public-hide-202"]')).toBeNull();
    expect(host.querySelector('[data-testid="step-table"]')?.textContent).not.toContain(rowdyName);
    const hiddenPanel = host.querySelector('[data-testid="admin-hidden-panel"]');
    expect(hiddenPanel?.textContent).toContain("Hidden on Nov 26");
    expect(hiddenPanel?.textContent).toContain(rowdyName);

    const unhideBtn = host.querySelector('[data-testid="admin-unhide-202"]') as HTMLButtonElement;
    await act(async () => {
      unhideBtn.click();
    });
    await waitForCondition(() => host.querySelector('[data-testid="public-hide-202"]') !== null);

    expect(host.querySelector('[data-testid="public-hide-202"]')).not.toBeNull();
    expect(host.querySelector('[data-testid="step-table"]')?.textContent).toContain(rowdyName);
    expect(host.querySelector('[data-testid="admin-hidden-panel"]')).toBeNull();
  }, 15_000);

  it("allows a reader who has not played to open today's board before playing with no You marker or cards (467: A)", async () => {
    const urls: string[] = [];
    const pageOneEntries = Array.from({ length: 20 }, (_, idx) => ({
      entry_id: 300 + idx,
      rank: idx + 1,
      nickname: idx === 0 ? "José" : `Reader ${idx + 1}`,
      points: 225 - idx * 5,
      step_points: [50, 75, 100 - idx * 5],
      step_labels: ["5 of 5", "5 of 5", `${100 - idx * 5}`],
      total_time_seconds: 30 + idx,
    }));
    const pageTwoEntries = [
      {
        entry_id: 320,
        rank: 21,
        nickname: "Alex B.",
        points: 115,
        step_points: [40, 45, 30],
        step_labels: ["4 of 5", "3 of 5", "30"],
        total_time_seconds: 51,
      },
    ];

    globalThis.fetch = jest.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      if (url.includes("/api/guess/board")) {
        const pageNum = url.includes("page=2") ? 2 : 1;
        return mockJsonResponse(200, {
          day: DAILY_PACK.id,
          edition_code: DAILY_PACK.code,
          steps: DAILY_PACK.steps.map((st) => ({ name: st.name })),
          total_count: 21,
          page: pageNum,
          page_size: 20,
          total_pages: 2,
          entries: pageNum === 2 ? pageTwoEntries : pageOneEntries,
          me: null,
        });
      }
      return mockJsonResponse(404, {});
    }) as typeof fetch;

    await act(async () => {
      root?.render(<ChanceGame pack={DAILY_PACK} initialGroupCode={null} isToday={true} />);
    });
    await waitForCondition(() => host.querySelector('[data-testid="start-board-toggle"]') !== null);

    const toggleBtn = host.querySelector('[data-testid="start-board-toggle"]') as HTMLButtonElement;
    expect(toggleBtn).not.toBeNull();
    expect(toggleBtn.textContent).toBe("See today's board");
    expect(host.querySelector('[data-testid="public-board"]')).toBeNull();
    expect(urls.some((u) => u.includes("/api/guess/board"))).toBe(false);

    await act(async () => {
      toggleBtn.click();
    });
    await waitForCondition(
      () => host.querySelector('[data-testid="public-board"]')?.textContent?.includes("21 games") ?? false,
    );

    const boardUrls = urls.filter((u) => u.includes("/api/guess/board"));
    expect(boardUrls.length).toBe(1);
    expect(boardUrls[0]).not.toContain("entry_id=");

    const publicBoard = host.querySelector('[data-testid="public-board"]');
    expect(publicBoard).not.toBeNull();
    expect(publicBoard?.textContent).toContain("Everyone who played today");
    expect(publicBoard?.textContent).toContain("21 games");
    expect(publicBoard?.textContent).toContain("José");
    expect(host.querySelector('[data-testid="public-board-place"]')).toBeNull();
    expect(host.querySelector('[data-testid="public-board-row-me"]')).toBeNull();
    expect(host.querySelector('[data-testid="public-board-you-badge"]')).toBeNull();
    expect(host.querySelector('[data-testid^="public-hide-"]')).toBeNull();
    expect(host.querySelector('[data-testid="admin-hidden-panel"]')).toBeNull();
    for (const card of DAILY_PACK.cards) {
      expect(publicBoard?.textContent).not.toContain(card.prompt);
    }

    const nextBtn = host.querySelector('[data-testid="public-board-next"]') as HTMLButtonElement;
    expect(nextBtn.disabled).toBe(false);
    await act(async () => {
      nextBtn.click();
    });
    await waitForCondition(
      () => host.querySelector('[data-testid="public-board"]')?.textContent?.includes("Alex B.") ?? false,
    );

    expect(host.querySelector('[data-testid="public-board"]')?.textContent).toContain("Alex B.");
    expect(host.querySelector('[data-testid="public-board-row-me"]')).toBeNull();

    const hideToggle = host.querySelector('[data-testid="start-board-toggle"]') as HTMLButtonElement;
    expect(hideToggle.textContent).toBe("Hide today's board");
    await act(async () => {
      hideToggle.click();
    });
    await waitForCondition(() => host.querySelector('[data-testid="public-board"]') === null);
    expect(host.querySelector('[data-testid="public-board"]')).toBeNull();
  }, 15_000);
});
