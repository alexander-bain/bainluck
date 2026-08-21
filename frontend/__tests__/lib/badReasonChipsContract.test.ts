/**
 * UX-P117 / #2060 item 1 — `contracts/bad_reason_chips.json`, checked in CI.
 *
 * ## What this suite is responsible for that no other file can be
 *
 * Three runtimes draw the six reason chips and no import spans them (ruling 021).
 * Python's arm is `backend/tests/test_label_reason_routing.py::TestContract` and
 * it runs in CI. Swift's arm is `LabelingNudgeContractTests`, which executes
 * under `scripts/ios_native_gate.sh test` — a LOCAL gate, because xcodebuild does
 * not run in CI. So the Swift test's inlined table is compared against the
 * contract HERE, where CI will see it, exactly as
 * `renderedPercentContract.test.ts` does for the rounding rule.
 *
 * ## Why the bar is set this high for a list of six strings
 *
 * Because the failure is silent and the evidence is already in the store. The
 * three surfaces had drifted before anyone designed them to: `/admin/labeling`
 * wrote `boring` while native wrote `low_stakes`, one complaint under two names,
 * 2 rows beside 6 — each half too small to look like anything, and no error
 * anywhere. A chip whose stored tag drifts does not break; it just quietly stops
 * counting toward the thing it is counted for.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "..", "..", "..");
const CONTRACT_PATH = join(REPO_ROOT, "contracts/bad_reason_chips.json");

interface Chip {
  tag: string;
  display: string;
  fix_type: string;
}
interface Contract {
  chips: Chip[];
  aliases: Record<string, string>;
  notification: { category: string; action: string; deep_link: string };
}

const contract: Contract = JSON.parse(readFileSync(CONTRACT_PATH, "utf8"));

describe("bad reason chips contract", () => {
  it("declares exactly six distinct chips", () => {
    expect(contract.chips).toHaveLength(6);
    expect(new Set(contract.chips.map((c) => c.tag)).size).toBe(6);
    expect(new Set(contract.chips.map((c) => c.display)).size).toBe(6);
  });

  it("routes every chip to a fix_type", () => {
    for (const chip of contract.chips) {
      expect(chip.fix_type).toBeTruthy();
    }
  });

  it("uses only fix_type values the cluster endpoints already group by", () => {
    // The ReviewTab's FIX_TYPES select. Reusing these is what makes a native
    // chip tap land in the SAME cluster as a web triage of the same problem
    // rather than beside it.
    const known = new Set([
      "staleness",
      "wrong_entity_rank",
      "missing_context",
      "bad_image",
      "wrong_market_variant",
      "duplicate_variant",
      "category_mismatch",
      "data_bug",
      "ranking_rule",
      "other",
    ]);
    for (const chip of contract.chips) {
      expect(known.has(chip.fix_type)).toBe(true);
    }
  });

  it("never maps an alias onto another alias", () => {
    // A two-hop fold would depend on iteration order and silently half-apply.
    for (const target of Object.values(contract.aliases)) {
      expect(contract.aliases[target]).toBeUndefined();
    }
  });
});

// ── THE SWIFT ARM. This is the CI half of a runtime check CI cannot run. ─────

const SWIFT_TEST = join(
  REPO_ROOT,
  "ios/Bain Luck/BainLuckTests/LabelingNudgeContractTests.swift"
);
const SWIFT_VIEW = join(
  REPO_ROOT,
  "ios/Bain Luck/Bain Luck/Views/DiscoverLabelingView.swift"
);
const SWIFT_NOTIFICATIONS = join(
  REPO_ROOT,
  "ios/Bain Luck/Bain Luck/Services/NotificationManager.swift"
);
const iosPresent = existsSync(SWIFT_TEST);

(iosPresent ? describe : describe.skip)("swift arm", () => {
  it("the Swift test's inlined chip table still equals the contract", () => {
    const src = readFileSync(SWIFT_TEST, "utf8");
    const start = src.indexOf("CONTRACT ROWS BEGIN");
    const end = src.indexOf("CONTRACT ROWS END");
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);

    const block = src.slice(start, end);
    const rows = [...block.matchAll(/\("([a-z_]+)",\s*"([^"]+)"\)/g)].map((m) => ({
      tag: m[1],
      display: m[2],
    }));

    expect(rows).toEqual(
      contract.chips.map((c) => ({ tag: c.tag, display: c.display }))
    );
  });

  it("the view draws the contract's tags, in the contract's order", () => {
    // A grep, and it is honest about being one: it proves the literals are
    // PRESENT and ordered, not that they are rendered. What proves they are
    // rendered is the Swift suite, which the native gate runs.
    const src = readFileSync(SWIFT_VIEW, "utf8");
    const declAt = src.indexOf("private let badReasons");
    expect(declAt).toBeGreaterThan(-1);
    // Slice from the `= [` that opens the LITERAL, not from the first `]` in the
    // declaration — the type annotation `[(tag: String, title: String)]` closes a
    // bracket before the array does, and slicing on that yielded an empty block
    // and a test that would have passed against a view with no chips at all.
    const literalAt = src.indexOf("= [", declAt);
    expect(literalAt).toBeGreaterThan(-1);
    const block = src.slice(literalAt, src.indexOf("\n    ]", literalAt));
    const rows = [...block.matchAll(/\("([a-z_]+)",\s*"([^"]+)"\)/g)].map((m) => ({
      tag: m[1],
      display: m[2],
    }));
    // Guards the slice itself: an empty match set must fail loudly rather than
    // silently comparing [] against [] if the contract were ever emptied.
    expect(rows.length).toBe(6);

    expect(rows).toEqual(
      contract.chips.map((c) => ({ tag: c.tag, display: c.display }))
    );
  });

  it("the notification identifiers match the ones the server sends", () => {
    const src = readFileSync(SWIFT_NOTIFICATIONS, "utf8");
    expect(src).toContain(`labelingCategoryId = "${contract.notification.category}"`);
    expect(src).toContain(`labelingActionId = "${contract.notification.action}"`);
  });

  it("the routing decision stays in a pure function a Swift test can execute", () => {
    /*
     * This assertion used to be "the action check appears above the url read" —
     * a line-order grep. Mutation M14 defanged the CONDITION without moving the
     * LINE and the grep stayed green, which is the standing lesson that a grep
     * cannot prove a decision (only that a token is present).
     *
     * So the decision now lives in `notificationDestination`, and the real check
     * is `LabelingNudgeContractTests.testTheActionBeatsTheDigestUrl`, which calls
     * it. What CI can still usefully guard is that the extraction has not been
     * un-done — if the delegate goes back to deciding inline, the Swift test is
     * no longer testing the shipped path and nothing else would say so.
     */
    const src = readFileSync(SWIFT_NOTIFICATIONS, "utf8");
    expect(src).toContain("static func notificationDestination(");
    expect(src).toContain("Self.notificationDestination(");
    // The delegate must DISPATCH, not decide: no second reading of the action id
    // outside the pure function.
    const decisions = src.match(/actionIdentifier == labelingActionId/g) ?? [];
    expect(decisions).toHaveLength(1);
  });
});
