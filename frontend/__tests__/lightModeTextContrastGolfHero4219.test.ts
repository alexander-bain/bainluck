// #4219 — a raw-hex text colour on the light-mode-only site must still be readable.
//
// LOOKED at production `https://www.bainluck.com/categories/golf` at 390px on
// 2026-09-09, before the fix. The first screen carried a ~250px dark-green slab
// and NOTHING legible inside or under it:
//
//     ← Back to feed        grey #6B7280 on dark green #002e1f   3.08 : 1
//     Golf Odds & Futures   cream #FFF8E7 on the faded white end 1.03 : 1
//
// The subhead ("Who wins each tournament…") was the first line a reader could
// read — on a hub page whose own title is the second element on the page.
//
// The cause is a dark-mode leftover: `#FFF8E7` measures 14.06:1 against
// `#002e1f`, so the cream was chosen for a hero that WAS dark, and the hero is
// no longer dark under the title. The site is light mode only (CLAUDE.md,
// Frontend Design System, MANDATORY: use the tokens, never a raw hex).
//
// ── WHY THE GUARD IS COMPUTED AND NOT AN ALLOWLIST ──────────────────────────
//
// A ban on `text-[#…]` would be the obvious guard and it would be the wrong
// one: it would red on the five `#006747` masters-green literals that are
// perfectly legible (6.36:1), so it would have to carry an allowlist, and an
// allowlist goes stale silently — the next page adds a hex nobody measured and
// the guard says nothing, or the golf page moves a line and the pin reds for a
// comment. So the rule is the thing we actually care about, computed: any hex
// text colour anywhere in the app must clear WCAG 3:1 (the large-text floor)
// against BOTH light surfaces it can land on. `#FFF8E7` fails at 1.03,
// `#006747` passes at 6.36, and a new hex is graded on its own merits with no
// list to update.
//
// jsdom does no layout and no cascade, so a rendered test could not read the
// gradient's colour under the title at all — this is a scan by necessity, and
// the positive controls below prove it fires on the markup that shipped.

import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

/** `--surface-deep` and `--surface-card` from app/globals.css. */
const LIGHT_SURFACES = ["#F5F5F7", "#FFFFFF"];

/** WCAG 2.x large-text minimum. Body text needs 4.5; nothing may sit below 3. */
const FLOOR = 3;

const SCAN_DIRS = ["app", "components", "lib"];

function srgbChannel(eight: number): number {
  const c = eight / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** WCAG relative luminance of `#rgb` or `#rrggbb`. */
export function luminance(hex: string): number {
  const body = hex.replace("#", "");
  const full =
    body.length === 3
      ? body
          .split("")
          .map((ch) => ch + ch)
          .join("")
      : body.slice(0, 6);
  const [r, g, b] = [0, 2, 4].map((i) => srgbChannel(parseInt(full.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two hex colours, 1..21. */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Every .ts/.tsx file under `dir`, recursively. */
function sources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...sources(path));
    else if (/\.tsx?$/.test(entry)) out.push(path);
  }
  return out;
}

interface HexUse {
  file: string;
  line: number;
  hex: string;
  worst: number;
}

/** Every `text-[#…]` literal in the scanned tree, with its worst-case contrast. */
function hexTextColours(): HexUse[] {
  const out: HexUse[] = [];
  for (const dir of SCAN_DIRS) {
    for (const file of sources(join(process.cwd(), dir))) {
      readFileSync(file, "utf8")
        .split("\n")
        .forEach((text, index) => {
          for (const [, hex] of text.matchAll(/text-\[(#[0-9a-fA-F]{3,8})\]/g)) {
            out.push({
              file: file.slice(process.cwd().length + 1),
              line: index + 1,
              hex,
              worst: Math.min(...LIGHT_SURFACES.map((bg) => contrast(hex, bg))),
            });
          }
        });
    }
  }
  return out;
}

describe("#4219: hex text colours stay readable on the light-mode-only site", () => {
  const uses = hexTextColours();

  it("the scan actually reached the app — it is not grading an empty set", () => {
    // A source scan that finds no files passes vacuously and is quotable as a
    // guarantee it never gave. Assert the denominator before the predicate.
    expect(sources(join(process.cwd(), "app")).length).toBeGreaterThan(50);
    expect(uses.length).toBeGreaterThan(0);
  });

  it("every hex text colour clears 3:1 against both light surfaces", () => {
    const failures = uses
      .filter((u) => u.worst < FLOOR)
      .map((u) => `${u.file}:${u.line} ${u.hex} = ${u.worst.toFixed(2)}:1`);
    expect(failures).toEqual([]);
  });

  it("the golf hero draws its title and its backdrop from tokens, not a hex", () => {
    // The specimen. Whatever else moves on this page, the hub's own title may
    // not go back to being invisible.
    //
    // The assertions read CLASS ATTRIBUTES, not the raw slice: a `not.toContain`
    // over the source would also see the comment above the hero explaining which
    // hex was removed, and would red on the explanation rather than the markup.
    const page = readFileSync(join(process.cwd(), "app/categories/golf/page.tsx"), "utf8");
    const hero = page.slice(page.indexOf("{/* Hero */}"), page.indexOf("Who wins each tournament"));
    expect(hero).toContain("Golf Odds &amp; Futures");

    const classesOf = (element: string): string[] => {
      const at = hero.indexOf(element);
      expect(at).toBeGreaterThan(-1);
      const attr = /className="([^"]*)"/.exec(hero.slice(at))?.[1] ?? "";
      return attr.split(/\s+/).filter(Boolean);
    };

    // The title: a token, and no hex of any kind.
    const title = classesOf("<h1");
    expect(title).toContain("text-text-primary");
    expect(title.filter((c) => /^text-\[#/.test(c))).toEqual([]);

    // The hero's own backdrop. The dark-mode gradient is what made a
    // light-surface token unreadable in the first place: a dark band under the
    // back link, white under the title.
    const backdrop = classesOf("{/* Hero */}");
    expect(backdrop).toContain("bg-surface-deep");
    expect(backdrop.filter((c) => /^(from|via|to)-\[#/.test(c))).toEqual([]);
  });

  it("POSITIVE CONTROL — the predicate fails on the colours that shipped", () => {
    // If this stops failing, the rule above is asserting nothing.
    expect(Math.min(...LIGHT_SURFACES.map((bg) => contrast("#FFF8E7", bg)))).toBeLessThan(FLOOR);
    expect(contrast("#FFF8E7", "#F5F5F7")).toBeCloseTo(1.03, 2);
    // …and passes on the masters green the same page keeps, so the guard is not
    // a ban on hexes wearing a contrast rule.
    expect(contrast("#006747", "#F5F5F7")).toBeGreaterThan(6);
  });

  it("POSITIVE CONTROL — the contrast maths is right at both ends", () => {
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 1);
    expect(contrast("#FFFFFF", "#FFFFFF")).toBeCloseTo(1, 5);
    expect(contrast("#FFF", "#FFFFFF")).toBeCloseTo(1, 5); // 3-digit shorthand
  });
});
