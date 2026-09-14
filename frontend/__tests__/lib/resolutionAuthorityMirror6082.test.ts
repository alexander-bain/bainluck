/**
 * #6082 — the frontend tier-3 mirror may not drift from the backend's.
 *
 * `lib/resolutionAuthority.ts` is a hand-copied `AUTHORITATIVE_SOURCES`, and a
 * hand-copied set is a set that goes stale. The failure it would cause is
 * directional and silent: a source added to the backend's tier 3 and missed here
 * leaves a genuinely settled leg printing a price forever (the #6082 defect, back
 * again for one grader), and a source REMOVED from the backend's tier 3 and left
 * here has the web renderer crowning legs on open markets that the backend would
 * refuse — which is the tier-0 `_clear_premature_open_winners` hazard.
 *
 * So this parses the Python and compares both directions, the same drift
 * discipline `RETRACTED_RESOLUTION_SOURCE` gets from
 * `backend/tests/test_futures_serves_resolution_source_4788.py` (which reads the
 * TSX from the Python side). Precedent for a jest test reading backend source:
 * `__tests__/ios/conceptAdmissionParity.test.ts` and friends.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  AUTHORITATIVE_RESOLUTION_SOURCES,
  isAuthoritativeResolution,
} from "@/lib/resolutionAuthority";

const AUTHORITY_PY = join(
  __dirname,
  "..",
  "..",
  "..",
  "backend",
  "app",
  "utils",
  "resolution_authority.py",
);

/** The members of a named `frozenset({...})` literal in the authority module. */
function pythonFrozenset(source: string, name: string): Set<string> {
  const block = new RegExp(
    `${name}\\s*:\\s*frozenset\\[str\\]\\s*=\\s*frozenset\\(\\{([\\s\\S]*?)\\}\\)`,
  ).exec(source);
  if (!block) throw new Error(`could not find ${name} in resolution_authority.py`);
  const members = block[1].match(/"([^"]+)"/g) ?? [];
  return new Set(members.map((m) => m.slice(1, -1)));
}

describe("#6082 tier-3 mirror ↔ backend AUTHORITATIVE_SOURCES", () => {
  const py = readFileSync(AUTHORITY_PY, "utf8");

  it("the two sets are equal, both directions", () => {
    const backend = pythonFrozenset(py, "AUTHORITATIVE_SOURCES");
    // A guard that reads an empty set from a regex miss would pass vacuously
    // against an empty mirror; assert the parse found something real first.
    expect(backend.size).toBeGreaterThanOrEqual(5);
    expect([...backend].sort()).toEqual([...AUTHORITATIVE_RESOLUTION_SOURCES].sort());
  });

  it("the retraction is NOT in it — it is tier 1, and tier 1 may not crown", () => {
    const terminal = pythonFrozenset(py, "TERMINAL_SOURCES");
    expect(terminal.has("ungradeable_result")).toBe(true);
    expect(isAuthoritativeResolution("ungradeable_result")).toBe(false);
  });

  it("no tier-0 guess is authoritative here", () => {
    for (const guess of pythonFrozenset(py, "GUESS_FAMILY_SOURCES")) {
      expect(isAuthoritativeResolution(guess)).toBe(false);
    }
  });

  it("no tier-2 deterministic source is authoritative here", () => {
    for (const det of pythonFrozenset(py, "DETERMINISTIC_SOURCES")) {
      expect(isAuthoritativeResolution(det)).toBe(false);
    }
  });

  it("absent, null and unknown are all refused", () => {
    expect(isAuthoritativeResolution(null)).toBe(false);
    expect(isAuthoritativeResolution(undefined)).toBe(false);
    expect(isAuthoritativeResolution("")).toBe(false);
    expect(isAuthoritativeResolution("some_future_grader")).toBe(false);
  });
});
