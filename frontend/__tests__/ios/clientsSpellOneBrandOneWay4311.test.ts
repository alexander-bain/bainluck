/**
 * #4311 — THE TWO CLIENTS SPELL ONE SPORTSBOOK ONE WAY.
 *
 * The web said `ESPN Bet`; iOS said `ESPN BET`. `espnbet` is not a rare key —
 * production `odds_snapshots`, distinct `bookmaker`, 24h to 2026-09-09: **1,467
 * rows**, one of the 18 keys served — so both spellings were on real screens at
 * once. This is #2442's class ("this chip and the chart legend beside it cannot
 * spell one supplier two ways") one level out: not two components disagreeing,
 * two halves of the same product disagreeing.
 *
 * The web moved, because the brand styles itself all-caps.
 *
 * ═══ WHY THIS COMPARES THE MAPS AND DOES NOT PIN A STRING ═══
 *
 * Correcting the entry and asserting `sourceLabel("espnbet") === "ESPN BET"`
 * closes this key and nothing else. The defect is not the spelling of `espnbet`;
 * it is that **two maps name the same brands and nothing has ever compared
 * them** — so the next sportsbook added to one client drifts from the other in
 * exactly the way this one did, silently, until somebody happens to hold the two
 * screens side by side. So the assertion is over the whole intersection, and a
 * new key that disagrees fails here whether or not anyone thought of it.
 *
 * ═══ HOW EACH SIDE IS READ ═══
 *
 * The web side goes through `sourceLabel()`, the real shipped API, rather than a
 * text-parse of the module — the resolver is what a surface actually calls, and
 * a parse could agree with a map the callers no longer use.
 *
 * The Swift side has to be read as text: CI COMPILES NO SWIFT. That is the same
 * constraint `appNamesEverySourceItPrints` works under, and it carries the same
 * traps, so this file refuses to guess. The dictionary is SLICED by name (the
 * file holds `modelNames` too, and scanning the whole thing would silently mix
 * them), the slice THROWS if the declaration moves or the bracket does not close,
 * and the parsed entry count is floored — a regex that quietly matched nothing
 * would otherwise make every assertion below vacuously true.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * An empty intersection satisfies "no key disagrees" perfectly. So the size of
 * the intersection is asserted before its contents, and `espnbet` — the key this
 * issue is about — is required to be IN it, so the case that was broken is
 * provably one of the cases being checked.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { sourceLabel } from "@/lib/sourceLabels";

const SWIFT_RESOLVER = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Utilities/SourceLabels.swift"
);

/** Entries the Swift map must at least contain, or the parse is not working. */
const SWIFT_ENTRY_FLOOR = 20;

/** Shared keys there must at least be, or "none disagree" means nothing. */
const SHARED_KEY_FLOOR = 15;

/**
 * The `sportsbookNames` dictionary from the Swift resolver, as a Map.
 *
 * Sliced by declaration rather than scanned whole: `SourceLabels.swift` also
 * declares `modelNames`, whose values are deliberately NOT brands ("the DataGolf
 * model"), and folding those in would compare the web's brand map against a
 * sentence. Every failure mode here is loud — a moved declaration, an unclosed
 * literal and a suspiciously small parse all throw rather than returning few.
 */
function swiftSportsbookNames(): Map<string, string> {
  const source = readFileSync(SWIFT_RESOLVER, "utf8");
  const declaration = "private static let sportsbookNames: [String: String] = [";
  const start = source.indexOf(declaration);
  if (start === -1) {
    throw new Error(
      `${declaration} not found — the Swift map was renamed or restructured, and ` +
        `this guard must be re-aimed rather than left reading nothing`
    );
  }
  const bodyStart = start + declaration.length;
  const end = source.indexOf("]", bodyStart);
  if (end === -1) throw new Error("sportsbookNames literal is never closed");
  const body = source.slice(bodyStart, end);

  const entries = new Map<string, string>();
  for (const match of body.matchAll(/"([A-Za-z0-9_]+)"\s*:\s*"([^"\n]+)"/g)) {
    const [, key, label] = match;
    if (entries.has(key)) throw new Error(`duplicate key in the Swift map: ${key}`);
    entries.set(key, label);
  }
  if (entries.size < SWIFT_ENTRY_FLOOR) {
    throw new Error(
      `parsed only ${entries.size} Swift entries (floor ${SWIFT_ENTRY_FLOOR}) — ` +
        `the literal's shape changed and this parse is no longer reading it`
    );
  }
  return entries;
}

describe("#4311 — one brand, one spelling, on both clients", () => {
  it("parses the Swift map at all, which everything below depends on", () => {
    // The positive control for the half of this file that cannot be imported.
    const swift = swiftSportsbookNames();
    expect(swift.size).toBeGreaterThanOrEqual(SWIFT_ENTRY_FLOOR);
    expect(swift.get("draftkings")).toBe("DraftKings");
    // …and it must have got the VALUES, not just the keys — a regex that
    // captured empty strings would pass a size check.
    for (const [key, label] of swift) {
      expect(label.length).toBeGreaterThan(0);
      expect(label).not.toBe(key);
    }
  });

  it("shares enough keys with the web for the comparison to mean something", () => {
    const swift = swiftSportsbookNames();
    const shared = [...swift.keys()].filter((key) => sourceLabel(key) !== null);
    expect(shared.length).toBeGreaterThanOrEqual(SHARED_KEY_FLOOR);
    // The key this issue is about has to be one of the ones being compared,
    // or the suite could pass while saying nothing about the reported defect.
    expect(shared).toContain("espnbet");
  });

  it("names every shared sportsbook identically on both clients", () => {
    const swift = swiftSportsbookNames();
    const disagreements = [...swift.entries()]
      .map(([key, iosLabel]) => ({ key, iosLabel, webLabel: sourceLabel(key) }))
      .filter(({ webLabel }) => webLabel !== null)
      .filter(({ iosLabel, webLabel }) => iosLabel !== webLabel);
    // Named in the failure, not just counted: the point of this guard is to say
    // WHICH brand drifted, on a suite run by someone who did not write the diff.
    expect(disagreements).toEqual([]);
  });

  it("settles the reported one on the brand's own styling", () => {
    // The specific claim, kept beside the general one. If a future ruling moves
    // this brand, this is the assertion to change deliberately — the sweep above
    // would follow whichever way both clients went and never notice.
    expect(sourceLabel("espnbet")).toBe("ESPN BET");
    expect(swiftSportsbookNames().get("espnbet")).toBe("ESPN BET");
  });
});
