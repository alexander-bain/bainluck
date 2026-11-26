// /guess — THE PAGE KEEPS ITS PROMISES (425: C, 426: A).
//
//   1. It is unlisted: kept out of search indexes, with its own canonical
//      address and an explicit share card.
//   2. It is frontend-only: nothing under `app/guess` or `lib/guess` calls the
//      network. No table, no API, no account.
//   3. It is not one of the held-back prediction surfaces (#6445, #12601): it
//      mounts none of their components and links to none of their routes.
//   4. It carries the three GA4 hooks above its first return.
//   5. It follows the design system: tokens and palette classes, light only,
//      never a hex colour.
//   6. What it prints on first paint passes the site's copy bans.

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ALL_COPY_BANS, findBannedCopy, visibleTextFromHtml } from "@/lib/copyBans";
import { GUESS_PACK } from "@/lib/guess/pack";
import { defaultShareCard } from "@/lib/shareCard";

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

const ROOT = path.join(__dirname, "..", "..");
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const filesIn = (rel: string) =>
  fs
    .readdirSync(path.join(ROOT, rel))
    .filter((f) => /\.tsx?$/.test(f))
    .map((f) => `${rel}/${f}`);

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .map((line) => line.replace(/(^|\s)\/\/.*$/, ""))
    .join("\n");
}

const PAGE_FILES = filesIn("app/guess");
const LIB_FILES = filesIn("lib/guess");

describe("/guess — the page", () => {
  it("is unlisted, with its own canonical address and an explicit share card", async () => {
    const { metadata } = await import("@/app/guess/layout");
    expect(metadata.robots).toEqual({ index: false, follow: false });
    expect(metadata.alternates).toEqual({ canonical: "/guess" });
    expect(metadata.openGraph?.url).toBe("/guess");
    expect(metadata.openGraph?.images).toEqual(defaultShareCard());
    expect(metadata.title).toBe("Guess the Chance");
  });

  it("calls the three GA4 hooks above its first return", () => {
    const code = stripComments(read("app/guess/page.tsx"));
    const firstReturn = code.indexOf("return");
    for (const hook of ["usePageTracking(", "useScrollDepth(", "useEngagementTime("]) {
      const at = code.indexOf(hook);
      expect(at).toBeGreaterThan(0);
      expect(at).toBeLessThan(firstReturn);
    }
    // Its own page kind, present in all three lists the hooks are typed by.
    expect(code.match(/pageType: "guess"/g)?.length).toBe(3);
    expect(read("lib/analytics/types.ts").match(/\| 'guess'/g)?.length).toBe(3);
  });

  it("sits inside the site's own page frame: no second <main>, no full-height box that pushes the footer away", () => {
    for (const file of PAGE_FILES) {
      const code = stripComments(read(file));
      expect({ file, main: /<main\b/.test(code) }).toEqual({ file, main: false });
      expect({ file, tall: /min-h-screen/.test(code) }).toEqual({ file, tall: false });
    }
  });

  it("is frontend-only: no file of the game reaches the network", () => {
    for (const file of [...PAGE_FILES, ...LIB_FILES]) {
      const code = stripComments(read(file));
      expect({ file, hit: /\bfetch\s*\(|XMLHttpRequest|sendBeacon|WebSocket|\/api\//.test(code) }).toEqual({ file, hit: false });
    }
  });

  it("is not a held-back prediction surface: none of their components, routes or switches", () => {
    const banned = ["DailyChallengeCard", "GuessCard", "ResolutionCard", "ResolutionGroup", "ChallengeModal"];
    const routes = ["/daily", "/challenge", "/discover/stats", "/discover/scorecard", "/play"];
    for (const file of [...PAGE_FILES, ...LIB_FILES]) {
      const code = stripComments(read(file));
      for (const name of banned) expect({ file, name, hit: code.includes(name) }).toEqual({ file, name, hit: false });
      for (const route of routes) {
        for (const q of ['"', "'", "`"]) expect(code.includes(`${q}${route}${q}`)).toBe(false);
      }
    }
  });

  it("follows the design system: light only, no hex colours, no inline colour", () => {
    for (const file of PAGE_FILES) {
      const code = stripComments(read(file));
      expect({ file, dark: /\bdark:/.test(code) }).toEqual({ file, dark: false });
      expect({ file, hex: /#[0-9a-fA-F]{3,8}\b/.test(code) }).toEqual({ file, hex: false });
      expect({ file, rgb: /\brgba?\(|\bhsla?\(/.test(code) }).toEqual({ file, rgb: false });
    }
  });

  it("opens on a screen that asks for a name, says when the numbers were read, and passes the copy bans", async () => {
    const Page = (await import("@/app/guess/page")).default;
    const html = renderToStaticMarkup(<Page />);
    const text = visibleTextFromHtml(html);
    expect(text).toContain("Guess the Chance");
    expect(text).toContain("Who is playing on this phone?");
    expect(text).toContain(`Numbers as of ${GUESS_PACK.asOf}`);
    expect(html).toContain('data-testid="start-button"');
    expect(findBannedCopy(text, ALL_COPY_BANS).map((h) => h.ban.id)).toEqual([]);
    expect(text).not.toMatch(/\bquestions?\b/i);
  });

  it("prints no banned word in any sentence written into the game's own files", () => {
    // The screens after the first are reached by playing, so their sentences
    // are read from source: every quoted string and every run of JSX text.
    for (const file of PAGE_FILES) {
      const code = stripComments(read(file));
      const pieces = [
        ...Array.from(code.matchAll(/>([^<>{}]{12,})</g), (m) => m[1]),
        ...Array.from(code.matchAll(/[`"]([A-Z][^`"\n]{14,})[`"]/g), (m) => m[1]),
      ].map((s) => s.replace(/\$\{[^}]*\}/g, "X").replace(/&apos;/g, "'").replace(/&quot;/g, '"').trim());
      for (const piece of pieces) {
        if (/^[a-z-]+(\s[a-z0-9:[\]\/.%-]+)+$/.test(piece)) continue; // a class list, not a sentence
        expect({ file, piece, hits: findBannedCopy(piece, ALL_COPY_BANS).map((h) => h.ban.id) }).toEqual({ file, piece, hits: [] });
        expect({ file, piece, word: /\b(questions?|stale|blend|priced?|curated|cohort|bids?)\b/i.test(piece) }).toEqual({ file, piece, word: false });
      }
    }
  });
});
