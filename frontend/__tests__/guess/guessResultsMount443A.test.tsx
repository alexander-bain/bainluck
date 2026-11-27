/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

import ChanceGame from "@/app/guess/ChanceGame";
import { emptyEntry, fullGuess } from "@/lib/guess/engine";
import { GUESS_PACK } from "@/lib/guess/pack";
import { loadGame, saveGame } from "@/lib/guess/storage";
import type { GamePack, PlayerEntry } from "@/lib/guess/types";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const DAILY_PACK: GamePack = { ...GUESS_PACK, id: "2026-11-28", code: "p097" };
const GROUP_CODE = "fam1234567";
const NAMES = ["Ann", "Ben", "Cam", "Dee", "Eli"];

function makeFinishedPlayers(): PlayerEntry[] {
  return NAMES.map((name, idx) => ({
    ...emptyEntry(DAILY_PACK, name, "here"),
    guesses: DAILY_PACK.cards.map((card) => fullGuess(card)),
    times: [8 + idx, 10 + idx, 12 + idx],
  }));
}

function makeStoredEntries(players: PlayerEntry[]) {
  return players.map((p, idx) => ({
    nickname: p.name,
    answers: p.guesses.map((g) => (typeof g === "number" ? g : 0)),
    step_times: p.times.map((t) => Math.round(t)),
    points: 260 - idx * 5,
    step_points: [80, 90, 90 - idx * 5],
    total_time_seconds: Math.round(p.times.reduce((acc, v) => acc + v, 0)),
  }));
}

function mockJsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

async function flushUi(): Promise<void> {
  for (let i = 0; i < 16; i++) {
    await act(async () => {
      await Promise.resolve();
    });
  }
}

describe("ChanceGame results mount & resubmit guard (Fable 10:02 AM PT #13882)", () => {
  const origFetch = globalThis.fetch;
  const origScrollTo = window.scrollTo;
  let host: HTMLDivElement;
  let root: ReturnType<typeof createRoot> | null = null;

  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", `/guess?group=${GROUP_CODE}&day=${DAILY_PACK.id}`);
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

  it("sends zero POSTs and renders no save-error when five saved players already joined this board", async () => {
    const players = makeFinishedPlayers();
    const stored = makeStoredEntries(players);
    saveGame({
      packId: DAILY_PACK.id,
      groupCode: GROUP_CODE,
      joinedGroups: [GROUP_CODE],
      phase: "results",
      index: DAILY_PACK.cards.length - 1,
      turn: 0,
      here: players,
      link: [],
    });

    const calls: { url: string; method: string }[] = [];
    globalThis.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url: String(url), method });
      if (method === "GET") {
        return mockJsonResponse(200, {
          day: DAILY_PACK.id,
          edition_code: DAILY_PACK.code,
          group_code: GROUP_CODE,
          entries: stored,
        });
      }
      return mockJsonResponse(429, {
        detail: "Too many games sent from here right now. Please try again in a few minutes.",
      });
    }) as typeof fetch;

    await act(async () => {
      root?.render(<ChanceGame pack={DAILY_PACK} initialGroupCode={GROUP_CODE} />);
    });
    await flushUi();

    const postCalls = calls.filter((c) => c.method === "POST");
    expect(postCalls).toEqual([]);
    expect(host.querySelector('[data-testid="board-error"]')).toBeNull();
    expect(host.querySelector('[data-testid="save-error"]')).toBeNull();
    for (const name of NAMES) {
      expect(host.textContent).toContain(name);
    }
  });

  it("submits each local finished player once when joinedGroups lacks the current group code", async () => {
    const players = makeFinishedPlayers();
    saveGame({
      packId: DAILY_PACK.id,
      groupCode: GROUP_CODE,
      joinedGroups: [],
      phase: "results",
      index: DAILY_PACK.cards.length - 1,
      turn: 0,
      here: players,
      link: [],
    });

    const accumulated: ReturnType<typeof makeStoredEntries> = [];
    const postPayloads: Array<Record<string, unknown>> = [];
    globalThis.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET") {
        return mockJsonResponse(200, {
          day: DAILY_PACK.id,
          edition_code: DAILY_PACK.code,
          group_code: GROUP_CODE,
          entries: [],
        });
      }
      const parsed = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
      postPayloads.push(parsed);
      const nick = String(parsed.nickname ?? "");
      const idx = NAMES.indexOf(nick);
      accumulated.push(makeStoredEntries(players)[idx]);
      return mockJsonResponse(201, {
        day: DAILY_PACK.id,
        edition_code: DAILY_PACK.code,
        group_code: GROUP_CODE,
        entries: [...accumulated],
      });
    }) as typeof fetch;

    await act(async () => {
      root?.render(<ChanceGame pack={DAILY_PACK} initialGroupCode={GROUP_CODE} />);
    });
    await flushUi();

    expect(postPayloads.length).toBe(5);
    expect(postPayloads.map((p) => p.nickname)).toEqual(NAMES);
    for (const payload of postPayloads) {
      expect(Object.keys(payload).sort()).toEqual(["answers", "day", "nickname", "step_times"]);
    }
    expect(host.querySelector('[data-testid="board-error"]')).toBeNull();
    expect(host.querySelector('[data-testid="save-error"]')).toBeNull();
    expect(loadGame(DAILY_PACK)?.joinedGroups).toContain(GROUP_CODE);
  });
});
