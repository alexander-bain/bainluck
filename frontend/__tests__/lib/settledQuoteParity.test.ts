/**
 * UX-P115 (#2086) — the settled-quote words exist in TWO runtimes, so they are
 * two constants the moment one of them is edited.
 *
 * This is #1620's shape (a constant in two languages is two constants) with
 * #1650's user-visible consequence (one backend state wearing several
 * vocabularies on one screen). The event page stacks several settled surfaces;
 * a Swift string that drifts from the TypeScript one puts two different
 * settlement wordings in front of the same person on the same match.
 *
 * The established repair in this repo is mechanical parity, not review: a jest
 * test READS the other runtime's source and asserts the values match. Same
 * mechanism as the `entity_page_tiers.py` threshold check.
 *
 * Deliberately a SOURCE read rather than a generated contract file. Two strings
 * and a status list do not earn a build step, and a contract that is generated
 * from one side cannot catch that side being wrong — it can only propagate it.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  isSettledStatus,
  SETTLED_QUOTE_PREFIX,
  SETTLED_QUOTE_SECTION_NOTE,
} from "@/lib/settledQuote";

const SWIFT = readFileSync(
  join(__dirname, "../../../ios/Bain Luck/Bain Luck/Utilities/SettledQuote.swift"),
  "utf8",
);

/** `static let name = "value"` → value. */
function swiftString(name: string): string {
  const m = SWIFT.match(new RegExp(`static let ${name}\\s*=\\s*"([^"]*)"`));
  if (!m) throw new Error(`SettledQuote.swift has no string constant named ${name}`);
  return m[1];
}

describe("settled-quote parity: TypeScript ↔ Swift", () => {
  test("the row prefix is one string", () => {
    expect(swiftString("prefix")).toBe(SETTLED_QUOTE_PREFIX);
  });

  test("the section note is one string", () => {
    expect(swiftString("sectionNote")).toBe(SETTLED_QUOTE_SECTION_NOTE);
  });

  test("both runtimes agree on which statuses are settled", () => {
    const m = SWIFT.match(/static let settledStatuses:\s*Set<String>\s*=\s*\[([^\]]*)\]/);
    expect(m).not.toBeNull();
    const swiftStatuses = (m as RegExpMatchArray)[1]
      .split(",")
      .map((s) => s.trim().replace(/^"|"$/g, ""))
      .filter(Boolean);

    // Every status Swift calls settled, web must call settled...
    for (const s of swiftStatuses) {
      expect(isSettledStatus(s)).toBe(true);
    }
    // ...and the reverse, so neither side can quietly widen alone. The web set
    // is module-private, so it is probed through the predicate, not imported.
    for (const s of ["completed", "closed", "settled", "final", "resolved"]) {
      expect(swiftStatuses).toContain(s);
    }
    for (const s of ["scheduled", "live", "in_progress", "voided", ""]) {
      expect(isSettledStatus(s)).toBe(false);
      expect(swiftStatuses).not.toContain(s);
    }
  });

  test("native's price-band DELETION cannot come back", () => {
    // The defect being replaced, pinned from the one runtime that can read the
    // other's source. `p > 0.01 && p < 0.99` on a finished game deleted the
    // rows a reader would question, kept the 117 of 146 a reader would believe,
    // and dropped null-priced rows entirely. A settled row must now be
    // DECLARED, never removed — so no filter may key on the price band here.
    const view = readFileSync(
      join(__dirname, "../../../ios/Bain Luck/Bain Luck/Components/SpecialEventMarketsView.swift"),
      "utf8",
    );
    // Not vacuous: the file must be the one we think it is.
    expect(view).toContain("struct SpecialEventMarketsView");
    expect(view).toContain("SettledQuote.isSettled(eventStatus)");

    const code = view
      .split("\n")
      .filter((l) => !l.trim().startsWith("//"))
      .join("\n");
    expect(code).not.toMatch(/p\s*>\s*0\.01/);
    expect(code).not.toMatch(/p\s*<\s*0\.99/);
    // and the status pair it used to hard-code is gone in favour of the list
    expect(code).not.toMatch(/eventStatus\s*==\s*"completed"/);
  });

  test("the parity check is not vacuous", () => {
    // A regex that matched nothing would make every assertion above trivially
    // true. Prove the reader actually reads.
    expect(SWIFT).toContain("enum SettledQuote");
    expect(swiftString("prefix").length).toBeGreaterThan(0);
    expect(() => swiftString("noSuchConstant")).toThrow();
  });
});
