import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ChanceGame from "@/app/guess/ChanceGame";
import GuessPage from "@/app/guess/page";
import { ALL_COPY_BANS, findBannedCopy, visibleTextFromHtml } from "@/lib/copyBans";
import {
  fetchGroupBoard,
  fetchTodayPack,
  generateGroupCode,
  groupEntryToPlayerEntry,
  isValidGroupCode,
  mergeGroupPlayers,
  submitGroupEntry,
} from "@/lib/guess/api";
import { emptyEntry, fullGuess } from "@/lib/guess/engine";
import { GUESS_PACK, LEGACY_PACKS_BY_CODE } from "@/lib/guess/pack";

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

describe("/guess daily challenge & group board (443: A, #12619)", () => {
  const origFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = origFetch;
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

  it("generates valid random group codes and preserves legacy pack map", () => {
    const codes = new Set(Array.from({ length: 12 }, () => generateGroupCode()));
    expect(codes.size).toBe(12);
    for (const c of codes) expect(isValidGroupCode(c)).toBe(true);
    expect(isValidGroupCode("short")).toBe(false);
    expect(isValidGroupCode("BAD_UPPER")).toBe(false);
    expect(LEGACY_PACKS_BY_CODE[GUESS_PACK.code]).toBe(GUESS_PACK);
  });

  it("renders explicit board-error banner when board read fails, never an empty board", () => {
    const html = renderToStaticMarkup(
      <ChanceGame pack={GUESS_PACK} initialGroupCode="ab12cd34ef" initialGroupError="Board read timed out" />,
    );
    expect(html).toContain('data-testid="board-error"');
    expect(html).toContain('data-testid="board-retry"');
    expect(html).toContain("Could not load the group board.");
    expect(html).toContain("Board read timed out");
    expect(html).not.toContain('data-testid="earlier-players"');
    const text = visibleTextFromHtml(html);
    expect(findBannedCopy(text, ALL_COPY_BANS).map((h) => h.ban.id)).toEqual([]);
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

  it("validates every day in backend/data/guess/daily_schedule.json against frontend copyBans", () => {
    const schedulePath = path.resolve(__dirname, "..", "..", "..", "backend", "data", "guess", "daily_schedule.json");
    const raw = JSON.parse(fs.readFileSync(schedulePath, "utf8")) as {
      days: Record<
        string,
        {
          topics: string[];
          step_cards: Record<string, Array<Record<string, unknown>>>;
          spares: Record<string, Array<Record<string, unknown>>>;
        }
      >;
    };
    const dayKeys = Object.keys(raw.days);
    expect(dayKeys.length).toBeGreaterThanOrEqual(7);

    for (const dayKey of dayKeys) {
      const day = raw.days[dayKey];
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
