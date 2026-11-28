import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ChanceGame from "@/app/guess/ChanceGame";
import GuessPage from "@/app/guess/page";
import { ALL_COPY_BANS, findBannedCopy, visibleTextFromHtml } from "@/lib/copyBans";
import {
  evaluateGroupVisitOnResults,
  fetchGroupBoard,
  fetchTodayPack,
  formatDayLabel,
  generateGroupCode,
  groupEntryToPlayerEntry,
  isValidGroupCode,
  mergeGroupPlayers,
  submitGroupEntry,
} from "@/lib/guess/api";
import { emptyEntry, fullGuess } from "@/lib/guess/engine";
import { GUESS_PACK, LEGACY_PACKS_BY_CODE } from "@/lib/guess/pack";
import { GUESS_PACK_C1 } from "@/lib/guess/packC1";
import { clearGame, loadGame, saveGame } from "@/lib/guess/storage";

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

describe("/guess daily challenge & group board (443: A, #12619)", () => {
  const origFetch = globalThis.fetch;
  const origWindow = (globalThis as { window?: unknown }).window;

  afterEach(() => {
    globalThis.fetch = origFetch;
    if (origWindow === undefined) {
      delete (globalThis as { window?: unknown }).window;
    } else {
      (globalThis as { window?: unknown }).window = origWindow;
    }
  });

  it("merges stored, link, and local entries into strictly one row per nickname", () => {
    const p1 = { ...emptyEntry(GUESS_PACK, "Alex", "here"), guesses: GUESS_PACK.cards.map((c) => fullGuess(c)) };
    const storedSame = groupEntryToPlayerEntry(GUESS_PACK, {
      nickname: "alex",
      answers: GUESS_PACK.cards.map((c) => fullGuess(c)),
      step_times: [10, 12, 14],
      points: 250,
      step_points: [50, 75, 125],
      total_time_seconds: 36,
    });
    const storedOther = groupEntryToPlayerEntry(GUESS_PACK, {
      nickname: "Sam",
      answers: GUESS_PACK.cards.map((c) => fullGuess(c)),
      step_times: [8, 9, 10],
      points: 240,
      step_points: [50, 75, 115],
      total_time_seconds: 27,
    });
    const fromLinkDup = { ...emptyEntry(GUESS_PACK, "sam", "link"), guesses: GUESS_PACK.cards.map((c) => fullGuess(c)) };
    const fromLinkNew = { ...emptyEntry(GUESS_PACK, "Jo", "link"), guesses: GUESS_PACK.cards.map((c) => fullGuess(c)) };

    const merged = mergeGroupPlayers([p1], [storedSame, storedOther], [fromLinkDup, fromLinkNew]);
    expect(merged.map((p) => `${p.name}:${p.from}`)).toEqual(["Alex:here", "Sam:server", "Jo:link"]);
  });

  it("keeps both Point 1 link orders without forcing a finished player to replay", () => {
    // Order A: finished player visits own shared link -> lands on Results, no extra Add tap needed.
    expect(
      evaluateGroupVisitOnResults(
        false,
        { phase: "results", groupCode: "grpalpha1", joinedGroups: ["grpalpha1"] },
        "grpalpha1",
      ),
    ).toEqual({ restoreResults: true, needsAddTap: false });

    // Order B (Fable acceptance test): finished player alone -> opens friend's link -> lands on Results with Add tap.
    expect(
      evaluateGroupVisitOnResults(
        false,
        { phase: "results", groupCode: "grpsolo99", joinedGroups: ["grpsolo99"] },
        "grpfriend1",
      ),
    ).toEqual({ restoreResults: true, needsAddTap: true });

    // After tapping Add, friend's group code is recorded in joinedGroups.
    expect(
      evaluateGroupVisitOnResults(
        false,
        { phase: "results", groupCode: "grpfriend1", joinedGroups: ["grpsolo99", "grpfriend1"] },
        "grpfriend1",
      ),
    ).toEqual({ restoreResults: true, needsAddTap: false });

    // Unfinished player sees Carry on / Start over on Home rather than jumping to Results.
    expect(
      evaluateGroupVisitOnResults(false, { phase: "play", groupCode: null }, "grpfriend1"),
    ).toEqual({ restoreResults: false, needsAddTap: false });
  });

  it("stores per-pack progress independently and reads older flat saves cleanly", () => {
    const store: Record<string, string> = {};
    (globalThis as { window?: unknown }).window = {
      localStorage: {
        getItem: (k: string) => store[k] ?? null,
        setItem: (k: string, v: string) => {
          store[k] = v;
        },
        removeItem: (k: string) => {
          delete store[k];
        },
      },
    };

    const dailyPack = { ...GUESS_PACK, id: "2026-11-27", code: "p096" };
    const earlierPack = { ...GUESS_PACK, id: "2026-11-26", code: "p095" };
    const entryA = { ...emptyEntry(dailyPack, "Alex", "here"), guesses: dailyPack.cards.map((c) => fullGuess(c)) };
    const entryB = { ...emptyEntry(earlierPack, "Sam", "here"), guesses: earlierPack.cards.map((c) => fullGuess(c)) };

    saveGame({ packId: dailyPack.id, groupCode: "grp27aaaa", joinedGroups: ["grp27aaaa"], phase: "results", index: 14, turn: 0, here: [entryA], link: [] });
    saveGame({ packId: earlierPack.id, groupCode: "grp26bbbb", joinedGroups: ["grp26bbbb"], phase: "play", index: 3, turn: 0, here: [entryB], link: [] });

    expect(store[`bainluck_guess_v1:${dailyPack.id}`]).toBeTruthy();
    expect(loadGame(dailyPack)?.here[0].name).toBe("Alex");
    expect(loadGame(dailyPack)?.joinedGroups).toEqual(["grp27aaaa"]);
    expect(loadGame(earlierPack)?.here[0].name).toBe("Sam");

    clearGame(earlierPack.id);
    expect(loadGame(earlierPack)).toBeNull();
    expect(loadGame(dailyPack)?.here[0].name).toBe("Alex");

    clearGame(dailyPack.id);
    expect(loadGame(dailyPack)).toBeNull();

    // Legacy flat object on slot still loads cleanly.
    store["bainluck_guess_v1"] = JSON.stringify({
      packId: dailyPack.id,
      groupCode: "legacygrp1",
      phase: "results",
      index: 14,
      turn: 0,
      here: [entryA],
      link: [],
    });
    expect(loadGame(dailyPack)?.joinedGroups).toEqual(["legacygrp1"]);

    // Legacy byPack map on slot also loads cleanly when no per-set slot exists.
    store["bainluck_guess_v1"] = JSON.stringify({
      byPack: {
        [dailyPack.id]: {
          packId: dailyPack.id,
          groupCode: "legacyby1",
          phase: "results",
          index: 14,
          turn: 0,
          here: [entryA],
          link: [],
        },
      },
    });
    expect(loadGame(dailyPack)?.joinedGroups).toEqual(["legacyby1"]);
  });

  it("generates valid random group codes, formats day labels cleanly, and preserves legacy pack map", () => {
    const codes = new Set(Array.from({ length: 12 }, () => generateGroupCode()));
    expect(codes.size).toBe(12);
    for (const c of codes) expect(isValidGroupCode(c)).toBe(true);
    expect(isValidGroupCode("short")).toBe(false);
    expect(isValidGroupCode("BAD_UPPER")).toBe(false);
    expect(LEGACY_PACKS_BY_CODE[GUESS_PACK.code]).toBe(GUESS_PACK);
    expect(LEGACY_PACKS_BY_CODE[GUESS_PACK_C1.code]).toBe(GUESS_PACK_C1);
    expect(formatDayLabel("2026-11-26")).toBe("Nov 26");
  });

  it("renders explicit board-error, earlier-day, expired-day, and 503 fallback banners within copy bans", () => {
    const errHtml = renderToStaticMarkup(
      <ChanceGame pack={GUESS_PACK} initialGroupCode="ab12cd34ef" initialGroupError="Board read timed out" />,
    );
    expect(errHtml).toContain('data-testid="board-error"');
    expect(errHtml).toContain('data-testid="board-retry"');
    expect(errHtml).not.toContain('data-testid="earlier-players"');

    const noticesHtml = renderToStaticMarkup(
      <ChanceGame
        pack={GUESS_PACK}
        isLegacyPack
        earlierDayNotice="You are viewing Nov 26's cards and board."
        expiredDayNotice="That day's cards and board are gone (games are kept for 30 days). Here are today's cards."
        fallbackNotice="Today's live cards could not be reached, so you are playing the built-in set."
        onRetryLive={() => {}}
      />,
    );
    expect(noticesHtml).toContain('data-testid="earlier-day-banner"');
    expect(noticesHtml).toContain('href="/guess"');
    expect(noticesHtml).toContain('data-testid="expired-day-banner"');
    expect(noticesHtml).toContain('data-testid="fallback-edition-banner"');
    expect(noticesHtml).toContain('data-testid="retry-live-button"');

    for (const html of [errHtml, noticesHtml]) {
      const text = visibleTextFromHtml(html);
      expect(findBannedCopy(text, ALL_COPY_BANS).map((h) => h.ban.id)).toEqual([]);
      expect(text).not.toMatch(/\b(questions?|stale|blend|priced?|curated|cohort|bids?|odds|bets?)\b/i);
    }
  });

  it("renders clean loading shell on first paint before daily fetch resolves", () => {
    const html = renderToStaticMarkup(<GuessPage />);
    expect(html).toContain('data-testid="edition-loading"');
    const text = visibleTextFromHtml(html);
    expect(text).toContain("Guess the Chance");
    expect(findBannedCopy(text, ALL_COPY_BANS).map((h) => h.ban.id)).toEqual([]);
  });

  it("submitGroupEntry sends ONLY day, nickname, answers, step_times (never score/points)", async () => {
    const calls: { url: string; method: string; body?: Record<string, unknown> }[] = [];
    globalThis.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({
        url: String(url),
        method: init?.method ?? "GET",
        body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : undefined,
      });
      return new Response(
        JSON.stringify({ day: "2026-11-27", edition_code: "p096", group_code: "abcd1234ef", entries: [] }),
        { status: 201 },
      );
    }) as typeof fetch;

    await submitGroupEntry("abcd1234ef", {
      day: "2026-11-27",
      nickname: "Sam",
      answers: Array(15).fill(1),
      step_times: [12, 18, 22],
    });
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toContain("/api/guess/groups/abcd1234ef/entries");
    expect(Object.keys(calls[0].body ?? {}).sort()).toEqual(["answers", "day", "nickname", "step_times"]);

    await fetchGroupBoard("abcd1234ef", "2026-11-27");
    expect(calls[1].method).toBe("GET");
    expect(calls[1].url).toContain("/api/guess/groups/abcd1234ef?day=2026-11-27");

    await expect(fetchTodayPack("2026-11-27")).rejects.toThrow(/incomplete/);
  });

  it("checked-in backend/data/guess/daily_schedule.json is valid JSON and copy-clean for any configured days", () => {
    const schedulePath = path.resolve(__dirname, "..", "..", "..", "backend", "data", "guess", "daily_schedule.json");
    const raw = JSON.parse(fs.readFileSync(schedulePath, "utf8")) as {
      version: number;
      days: Record<
        string,
        {
          topics: string[];
          step_cards: Record<string, Array<Record<string, unknown>>>;
          spares: Record<string, Array<Record<string, unknown>>>;
        }
      >;
    };
    expect(raw.version).toBe(1);
    expect(typeof raw.days).toBe("object");
    for (const [dayKey, day] of Object.entries(raw.days)) {
      for (const bucket of [day.step_cards, day.spares]) {
        for (const tmpls of Object.values(bucket)) {
          for (const tmpl of tmpls) {
            const strings: string[] = [
              String(tmpl.prompt ?? ""),
              String(tmpl.short ?? ""),
              String(tmpl.context ?? ""),
              String(tmpl.sub ?? ""),
              String(tmpl.roastHigh ?? ""),
              String(tmpl.roastLow ?? ""),
            ];
            const opts = Array.isArray(tmpl.options) ? (tmpl.options as Array<Record<string, unknown>>) : [];
            for (const o of opts) strings.push(String(o.label ?? ""), String(o.short ?? ""));
            for (const text of strings.filter(Boolean)) {
              expect({ dayKey, text, hits: findBannedCopy(text, ALL_COPY_BANS).map((h) => h.ban.id) }).toEqual({
                dayKey,
                text,
                hits: [],
              });
              expect({
                dayKey,
                text,
                bad: /\b(questions?|stale|blend|priced?|price|curated|cohort|bids?|odds|bets?|wager)\b/i.test(text),
              }).toEqual({
                dayKey,
                text,
                bad: false,
              });
            }
          }
        }
      }
    }
  });
});
