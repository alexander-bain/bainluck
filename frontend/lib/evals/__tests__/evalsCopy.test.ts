/**
 * #12102 S1 — every word /evals says passes the site's bans and the page's own.
 *
 * The plan's acceptance for S1: `copy.ts` passes `ALL_COPY_BANS` plus
 * `SUPPLIER_PROSE_BANS`. This suite reads every string the page's data modules
 * export — copy, gap rows, source labels, chip words — and adds the page's own
 * rules (`copyRules.ts`: no "question", no future tense). The words a render
 * assembles are checked again by the page test, and the shipped bundle by
 * `shippedCopyBans.test.ts`.
 */

import { ALL_COPY_BANS, SUPPLIER_PROSE_BANS, findBannedCopy, type CopyBan } from "@/lib/copyBans";
import * as copy from "@/lib/evals/copy";
import { EVALS_COPY_RULES } from "@/lib/evals/copyRules";
import { GAPS } from "@/lib/evals/gaps";
import { loadRuns } from "@/lib/evals/runs";
import { EVALS_SOURCES } from "@/lib/evals/sources";
import { RESULT_WORD, ageLabel } from "@/lib/evals/truth";

const BANS: CopyBan[] = [...ALL_COPY_BANS, ...SUPPLIER_PROSE_BANS, ...EVALS_COPY_RULES];

/** Every string inside a value, at any depth. Keys are identifiers and are skipped. */
function stringsIn(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(stringsIn);
  if (value && typeof value === "object") return Object.values(value).flatMap(stringsIn);
  return [];
}

/** All reader-facing strings. (The page's rules live in `copyRules.ts`, not here: their reasons name the words they ban.) */
function readerStrings(): string[] {
  return [
    ...stringsIn(copy),
    ...GAPS.flatMap((g) => [g.text, g.planned?.waitingOn ?? ""]),
    ...EVALS_SOURCES.map((s) => s.label),
    ...loadRuns().flatMap((r) => [r.title, r.note, r.receipt.label]),
    ...Object.values(RESULT_WORD),
    ageLabel(0),
    ageLabel(1),
    ageLabel(2),
  ].filter(Boolean);
}

describe("/evals copy passes the bans", () => {
  it("no string the page exports trips a site-wide or page rule", () => {
    const hits = readerStrings().flatMap((text) =>
      findBannedCopy(text, BANS).map((h) => `${h.ban.id}: "${h.matched}" in "${h.context}"`)
    );
    expect(hits).toEqual([]);
  });

  it("the sweep reads the strings it claims to — nested copy, gap rows and labels included", () => {
    const strings = readerStrings();
    expect(strings).toContain(copy.HERO_COPY.detail);
    expect(strings).toContain(copy.RESULT_CHIP_MEANING.fail);
    expect(strings).toContain(copy.TERMS[0].meaning);
    expect(strings).toContain(GAPS[0].text);
    expect(strings).toContain(EVALS_SOURCES[0].label);
    expect(strings).toContain(loadRuns()[0].note);
    expect(strings.length).toBeGreaterThan(30);
  });

  it("the rules can fail — planted copy is caught by each family", () => {
    const planted = "We will show the blend price soon, and Kalshi says this question is settled.";
    const ids = findBannedCopy(planted, BANS).map((h) => h.ban.id);
    expect(ids).toEqual(
      expect.arrayContaining(["blend", "price-family", "venue-kalshi", "evals-will", "evals-soon", "evals-question"])
    );
  });

  it("a venue name as a source label passes; as the subject of a sentence it does not", () => {
    expect(findBannedCopy("Kalshi · Polymarket", BANS)).toEqual([]);
    expect(findBannedCopy("Kalshi says it is likely.", BANS).map((h) => h.ban.id)).toContain("venue-kalshi");
  });
});

describe("the rules stay out of the reader's bundle", () => {
  it("copy.ts, which the page imports, does not carry the rule list", () => {
    expect(Object.keys(copy)).not.toContain("EVALS_COPY_RULES");
  });
});

describe("the page says what Decide 43 ruled", () => {
  it("J1: the hero says plainly that AI agents write most of the code", () => {
    expect(copy.HERO_COPY.detail).toMatch(/AI agents write most of the code/);
  });

  it("the hero names every label the page can show, LAST REVIEWED included", () => {
    for (const label of ["LIVE", "LAST RUN", "PLANNED", "LAST REVIEWED"]) {
      expect(copy.HERO_COPY.detail).toContain(label);
    }
  });

  it("the combined number is called the combined probability", () => {
    const gap = GAPS.find((g) => g.id === "combined-probability");
    expect(gap?.text).toMatch(/combined probability/);
  });
});
