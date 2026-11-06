/**
 * #12102 S1 — every word /evals says passes the site's bans and the page's own.
 *
 * The plan's acceptance for S1: `copy.ts` passes `ALL_COPY_BANS` plus
 * `SUPPLIER_PROSE_BANS`. This suite reads every string the page's data modules
 * export — copy, gap rows, source labels, chip words — and adds the page's own
 * rules (`EVALS_COPY_RULES`: no "question", no future tense). The words a render
 * assembles are checked again by the page test, and the shipped bundle by
 * `shippedCopyBans.test.ts`.
 */

import { ALL_COPY_BANS, SUPPLIER_PROSE_BANS, findBannedCopy, type CopyBan } from "@/lib/copyBans";
import * as copy from "@/lib/evals/copy";
import { GAPS } from "@/lib/evals/gaps";
import { EVALS_SOURCES } from "@/lib/evals/sources";
import { RESULT_WORD, ageLabel } from "@/lib/evals/truth";

const BANS: CopyBan[] = [...ALL_COPY_BANS, ...SUPPLIER_PROSE_BANS, ...copy.EVALS_COPY_RULES];

/** Every string inside a value, at any depth. Keys are identifiers and are skipped. */
function stringsIn(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(stringsIn);
  if (value && typeof value === "object") return Object.values(value).flatMap(stringsIn);
  return [];
}

/** All reader-facing strings. The rule list itself is not copy: its `why` names the words it bans. */
function readerStrings(): string[] {
  const { EVALS_COPY_RULES: _rules, ...readerCopy } = copy;
  return [
    ...stringsIn(readerCopy),
    ...GAPS.flatMap((g) => [g.text, g.planned?.waitingOn ?? ""]),
    ...EVALS_SOURCES.map((s) => s.label),
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

describe("the page says what Decide 43 ruled", () => {
  it("J1: the hero says plainly that AI agents write most of the code", () => {
    expect(copy.HERO_COPY.detail).toMatch(/AI agents write most of the code/);
  });

  it("the combined number is called the combined probability", () => {
    const gap = GAPS.find((g) => g.id === "combined-probability");
    expect(gap?.text).toMatch(/combined probability/);
  });
});
