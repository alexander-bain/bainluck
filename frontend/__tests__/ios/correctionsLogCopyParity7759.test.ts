/**
 * #7759 — the two corrections logs print the same sentences, or CI says so.
 *
 * THE BUG. `/calibration`'s corrections log is a trust panel. Web learned to
 * print reader copy for it — `correctionTitle` over a closed
 * `CORRECTION_TITLE_OVERRIDES` map (#7729, then eight more entries in #7734) —
 * and dropped the backend auditor's paragraph before that (#4067 / CERT-2295).
 * The Swift twin did neither: `CalibrationView` rendered `c.title` and
 * `c.description` raw, so an iPhone printed "Polymarket hockey sign-flip" and
 * "Queue #186 … corrects the Queue #167 filter" on the one panel whose subject
 * is whether our numbers can be checked. Nothing failed: both surfaces were
 * internally consistent and neither knew about the other.
 *
 * SO THIS GUARDS THE COUPLING, NOT EITHER RENDERER. It reads both files as
 * source and requires the two maps to be the same map — same producer keys, same
 * reader sentences. A tenth entry added on one surface reddens here instead of
 * silently diverging, which is precisely the defect this issue is, so the guard
 * is this issue's own class recurring.
 *
 * It also pins the WIRING, because a perfect map nobody calls is the other way
 * this comes back — web's own `correctionsLogRendersThePagesWordsNotOurTracker7729`
 * exists for that reason.
 *
 * Each surface's BEHAVIOUR stays where it can be asserted properly: web's in
 * `__tests__/lib/correctionsLogDoesNotQuoteOurTracker7729.test.ts`, iOS's in
 * `CorrectionsLogReadsInEnglish7759Tests`.
 *
 * It lives in jest because jest is a deploy gate here and the Swift test target
 * is not reachable from CI (notice 10's iOS clause exists for that reason). The
 * existing native/web calibration parity leg
 * (`e2e/contract/calibrationSurfaceParity.contract.test.js`) runs only on the
 * browser-audit schedule, so it could not hold this.
 */

import { readFileSync } from "fs";
import { join } from "path";

const WEB = join(__dirname, "../../lib/calibrationCorrections.ts");
const IOS = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Utilities/CalibrationCorrections.swift",
);
const IOS_VIEW = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Views/CalibrationView.swift",
);

/**
 * Both files quote producer titles and reader sentences in their PROSE — the
 * Swift header reproduces three of the shorthand titles, and web's map carries
 * the producer's `description` above each entry as a comment. A raw scan would
 * read those as declarations, so comments come out before anything is matched.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/^[ \t]*\/\/\/.*$/gm, "");
}

/** A missing file must be LOUD: a guard that silently skips is decoration. */
function read(file: string): string {
  try {
    return readFileSync(file, "utf8");
  } catch (err) {
    throw new Error(
      `#7759 corrections-copy parity gate could not read ${file}: ${String(err)}. ` +
        `If the file moved, update this guard — do not delete the check.`,
    );
  }
}

/**
 * The text between the opening and closing delimiter of a declaration.
 *
 * Brace-matched rather than regex-terminated: the values contain parentheses,
 * colons and percent signs, and an `[^]*?` terminated on the first `]` or `}`
 * would silently return a PREFIX of the map — which reads as a smaller map, not
 * as an error. The count assertions below are the backstop for that.
 *
 * The scan starts after the `=`, not after the name: Swift's type annotation is
 * itself bracketed (`static let titleOverrides: [String: String] = [`), so the
 * first `[` on that line opens the TYPE and matching from there yields
 * `String: String` — nine pairs read as zero, and an empty map compares equal to
 * an empty map.
 */
function delimited(source: string, declaration: string, open: "{" | "["): string {
  const at = source.indexOf(declaration);
  if (at === -1) throw new Error(`\`${declaration}\` not found`);
  const close = open === "{" ? "}" : "]";
  const assign = source.indexOf("=", at);
  if (assign === -1) throw new Error(`\`${declaration}\` is never assigned`);
  const start = source.indexOf(open, assign);
  if (start === -1) throw new Error(`\`${declaration}\` has no opening \`${open}\``);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === open) depth += 1;
    else if (source[i] === close) {
      depth -= 1;
      if (depth === 0) return source.slice(start + 1, i);
    }
  }
  throw new Error(`\`${declaration}\` is never closed`);
}

/** `"producer title": "reader sentence",` pairs, in declaration order. */
function pairs(block: string): Array<[string, string]> {
  return [...block.matchAll(/"([^"]+)"\s*:\s*"([^"]+)"\s*,/g)].map(
    (m) => [m[1], m[2]] as [string, string],
  );
}

const webPairs = pairs(
  delimited(stripComments(read(WEB)), "export const CORRECTION_TITLE_OVERRIDES", "{"),
);
const iosPairs = pairs(
  delimited(stripComments(read(IOS)), "static let titleOverrides", "["),
);
const iosViewSource = stripComments(read(IOS_VIEW));

describe("#7759 — the corrections log says the same thing on both surfaces", () => {
  /**
   * The extractors are the load-bearing part of this file: one that silently
   * returns [] makes every comparison below pass on two empty maps. Pinning the
   * count means a partial brace-match cannot read as agreement either.
   */
  it("reads a real map out of each surface", () => {
    expect(webPairs).toHaveLength(9);
    expect(iosPairs).toHaveLength(9);
    // A pair whose halves are equal would mean the extractor matched one string
    // against itself somewhere — the reader sentence is never the producer key.
    for (const [producer, reader] of [...webPairs, ...iosPairs]) {
      expect(reader).not.toBe(producer);
    }
  });

  it("maps the same producer titles", () => {
    const keys = (p: Array<[string, string]>) => p.map(([k]) => k).sort();
    expect(keys(iosPairs)).toEqual(keys(webPairs));
    // Named explicitly so a mass re-key on both sides at once still has to face
    // the four titles the issue put in front of a reader.
    expect(keys(webPairs)).toEqual(
      expect.arrayContaining([
        "Polymarket hockey sign-flip",
        "Malformed-binary exclusion",
        "Soccer 2-way (draw-omission) historical exclusion",
        "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)",
      ]),
    );
  });

  it("prints the same sentence for every one of them", () => {
    // The key set agreeing is not enough: two maps can share every key and
    // answer differently, which is the app and the site disagreeing about what
    // we corrected — a worse failure than the shorthand this replaced.
    expect(Object.fromEntries(iosPairs)).toEqual(Object.fromEntries(webPairs));
  });

  it("keeps the app's rendering wired to the map", () => {
    // A map nobody calls passes every assertion above.
    expect(iosViewSource).toMatch(/CalibrationCorrections\.title\(\s*c\.title\s*\)/);
    expect(iosViewSource).not.toMatch(/Text\(\s*c\.title\s*\)/);
  });

  it("sorts the log on both surfaces, and the app sorts STABLY", () => {
    // #7763. Web has ordered this list since #7599 and the app did not, so the
    // same 2026-07-08 row sat below 2026-07-09 on the phone. Both renderers are
    // pinned to a sort here because "web sorts, iOS does not" is the whole
    // defect and neither surface's own tests can see the other.
    const webPage = stripComments(read(join(__dirname, "../../app/calibration/page.tsx")));
    expect(webPage).toMatch(/orderCorrections\(\s*data\.corrections\s*\)/);
    expect(iosViewSource).toMatch(/CalibrationCorrections\.ordered\(\s*viewModel\.corrections\s*\)/);

    // And the Swift comparator keeps its index tie-break. `Swift.sort` is not
    // stable (web's `Array.prototype.sort` is, by ES2019), so a comparator that
    // only compares dates reorders the five rows sharing 2026-07-09 — a
    // different shuffle of the same defect. `CorrectionsLogReadsInEnglish7759Tests`
    // asserts the behaviour; this asserts it cannot be deleted as redundant.
    const iosLib = stripComments(read(IOS));
    expect(iosLib).toMatch(/lhs\.offset\s*<\s*rhs\.offset/);
  });

  it("keeps the backend's auditor paragraph off the app's screen", () => {
    // #4067 / CERT-2295 on web, which the app had never caught up with: the
    // producer's `description` is method prose — "(gotcha #17)", "poly MCE
    // 4.68 → 4.01", "Queue #186 … corrects the Queue #167 filter" — and notice
    // 34 keeps that off a reader's screen.
    expect(iosViewSource).not.toMatch(/Text\(\s*c\.description\s*\)/);
  });
});
