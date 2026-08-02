// L2-231 Item 1 — the browser-audit rail's calibration hooks.
//
// The calibration pack (`e2e/specs/calibration.spec.ts`) shipped in L2-228 with
// NO test hooks, on purpose: `app/calibration/page.tsx` belonged to Lane 1 at
// the time, so the pack bound to stat-card LABEL TEXT ("Resolved Outcomes",
// "Brier Score"), to a copy regex for the well-traded toggle, and then read the
// value positionally as `> div` index 1 of whatever element the label sat in.
// That spec's own header documents the trade and names the follow-up.
//
// Both halves of that are load-bearing evidence resting on things that are not
// evidence:
//
//   - An editorial reword breaks the pack. Not a correctness hole (it fails
//     RED, which is the safe direction) but it makes the rail a tax on copy.
//   - The positional read is the real hazard: `.locator("> div").nth(1)` is
//     satisfied by whatever sits second, so a markup reshuffle inside StatCard
//     moves the read onto the DETAIL line — a string that also contains digits,
//     and therefore still passes the finite-number assertion. That is a
//     fail-OPEN path to a green run on a wrong number, which is the exact class
//     C96 [P1] named.
//
// So the hooks are now the anchor, and this suite is their tripwire: drop,
// rename, or duplicate one and CI fails HERE, loudly, instead of the audit
// quietly grading something else. Asserted at the source level — the page is a
// large client component behind SWR, and rendering it would prove less and
// break more (the same call `discoverAuditHooks.test.tsx` makes for the
// Discover page body).

import * as fs from "fs";
import * as path from "path";

const SOURCE: string = fs.readFileSync(
  path.join(__dirname, "..", "..", "app", "calibration", "page.tsx"),
  "utf8"
);

/** Count non-overlapping occurrences of a literal in a string. */
function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

/**
 * How many elements declare `hook`.
 *
 * A hook reaches the DOM one of two ways here: written directly as
 * `data-testid="..."`, or handed to `StatCard` as `testId="..."`, which the
 * component threads onto both its root and its value div. Counting only the
 * literal attribute would score every stat card as missing — and counting them
 * separately would let a hook be declared once each way and collide in the DOM.
 * One number, both spellings.
 */
function declarations(hook: string): number {
  return occurrences(SOURCE, `data-testid="${hook}"`) + occurrences(SOURCE, `testId="${hook}"`);
}

/**
 * Every hook the pack selects on, and how many times it may appear in the
 * source. One occurrence means one element. `calibration-category-row` and
 * `calibration-parked-category` are rendered inside `.map()`s, so they appear
 * once in the SOURCE but many times in the DOM — that is a list, not a
 * duplicate, and the rail treats them as collections.
 */
const SINGLETON_HOOKS = [
  "calibration-page",
  "calibration-error",
  "calibration-loading",
  "calibration-stale-banner",
  "calibration-generated-at",
  "calibration-population-count",
  "calibration-stat-outcomes",
  "calibration-stat-ece",
  "calibration-stat-brier",
  "calibration-stat-sources",
  "calibration-stat-categories",
  "calibration-cohort-toggle",
  "calibration-activity-section",
  "calibration-activity-moved",
  "calibration-activity-unchanged",
  "calibration-activity-sentence",
  "calibration-category-breakdown",
  "calibration-niche-section",
] as const;

const COLLECTION_HOOKS = ["calibration-category-row", "calibration-parked-category"] as const;

describe("the calibration page renders the hooks the audit selects", () => {
  test.each(SINGLETON_HOOKS)("%s is declared exactly once", (hook) => {
    // Exactly once is the whole assertion: zero means the pack's anchor is gone
    // (it fails red downstream), two means the rail's `.first()` silently picks
    // one of them and the choice is markup order, not intent.
    expect(declarations(hook)).toBe(1);
  });

  test.each(COLLECTION_HOOKS)("%s exists as a per-row hook", (hook) => {
    // Once in the SOURCE, many times in the DOM — it renders inside a `.map()`.
    expect(declarations(hook)).toBe(1);
  });

  test("no two hooks share a name", () => {
    const all = [...SINGLETON_HOOKS, ...COLLECTION_HOOKS];
    expect(new Set(all).size).toBe(all.length);
  });
});

describe("the hooks carry the machine-readable state the rail grades on", () => {
  // The point of each attribute below is that it is DATA. Prose can be reworded
  // by anyone at any time; these cannot change meaning without changing code.

  test("the page root declares the payload's population contract", () => {
    // Without this a last-good snapshot built under an older population version
    // renders under current labels and no client can tell (C111 P2 / Q297 §3).
    expect(SOURCE).toContain("data-population-version={data.population_version");
    expect(SOURCE).toContain("data-cache-status=");
  });

  test("the page root says WHY it considered itself allowed to render", () => {
    // L2-232. `data-population-version` records what the server sent;
    // `data-contract-state` records what this build decided about it. Without
    // the second, a rail sees the version and still cannot tell whether the page
    // verified it or merely printed it — which is exactly the gap this queue closed.
    expect(SOURCE).toContain("data-contract-state={contract.state}");
  });

  test("the refusal is gated on the decision, and returns before any numbers", () => {
    // The whole point is that an incompatible payload never reaches the curve.
    // If the guard were placed after the hero or the stat cards, the numbers
    // would render under this build's labels before the page changed its mind.
    const guard = SOURCE.indexOf("if (!contract.render)");
    expect(guard).toBeGreaterThan(-1);
    const pageRoot = SOURCE.indexOf('data-testid="calibration-page"');
    expect(pageRoot).toBeGreaterThan(guard);
  });

  test("the stale banner is decided in one place, not re-derived at the JSX", () => {
    // Reading `cache.status` again here is how "degraded" would silently outrank
    // a refusal: two independent conditionals, and whichever is checked first
    // wins. The banner renders off the same decision the refusal does.
    expect(SOURCE).toContain("{contract.degraded && (");
    const bannerIdx = SOURCE.indexOf('data-testid="calibration-stale-banner"');
    const before = SOURCE.slice(Math.max(0, bannerIdx - 600), bannerIdx);
    expect(before).not.toContain('data.cache?.status === "stale"');
  });

  test("the stale banner is dated as data, not only as formatted prose", () => {
    const i = SOURCE.indexOf('data-testid="calibration-stale-banner"');
    expect(i).toBeGreaterThan(-1);
    const block = SOURCE.slice(i, i + 400);
    expect(block).toContain("data-generated-at=");
    expect(block).toContain("data-cache-reason=");
  });

  test("the stale banner keeps its accessible semantics alongside the hook", () => {
    const i = SOURCE.indexOf('data-testid="calibration-stale-banner"');
    expect(SOURCE.slice(Math.max(0, i - 200), i)).toContain('role="status"');
  });

  test("the population count publishes BOTH the cohort and full totals", () => {
    // The headline number is the cohort count, which differs from
    // total_outcomes whenever the thin toggle is off. A native surface that
    // reads the other one diverges silently — so both are published.
    const i = SOURCE.indexOf('data-testid="calibration-population-count"');
    const block = SOURCE.slice(i, i + 220);
    expect(block).toContain("data-cohort-n={cohortN}");
    expect(block).toContain("data-full-n={fullN}");
  });

  test("the activity section publishes its computed direction", () => {
    // This is what lets the rail check prose-vs-numbers without parsing prose.
    expect(SOURCE).toContain("data-activity-direction={activity.direction}");
  });

  test("the failure state names itself, and is never the loaded-page hook", () => {
    // A rebuild window, a hard fetch failure, a refused population contract and
    // a rendering regression all look identical to a rail that can only observe
    // "the page hook is missing". The name distinguishes them; conflating error
    // with loaded is how a broken deploy reads as a slow one.
    //
    // L2-232 moved the element into `CalibrationUnavailable` so both the
    // transport failure and the contract refusal can route through ONE
    // declaration (the hook must stay a singleton — see above). So the shell is
    // checked here, and the names its callers pass are checked below.
    const i = SOURCE.indexOf('data-testid="calibration-error"');
    expect(i).toBeGreaterThan(-1);
    const block = SOURCE.slice(i, i + 320);
    expect(block).toContain("data-error-state-name={stateName}");
    expect(block).toContain("data-contract-state={contractState}");
    expect(block).not.toContain("calibration-page");
  });

  test("every unavailable call site passes a state name, and none is blank", () => {
    // The shell can only name a failure if its callers give it one. An empty or
    // missing `stateName` reduces the rail back to "something was red".
    const sites = [...SOURCE.matchAll(/<CalibrationUnavailable\b([\s\S]*?)\/>/g)];
    // Two today: the transport failure and the contract refusal.
    expect(sites.length).toBeGreaterThanOrEqual(2);
    for (const [, props] of sites) {
      expect(props).toMatch(/stateName=/);
      expect(props).toMatch(/contractState=/);
      expect(props).not.toMatch(/stateName=""/);
      expect(props).not.toMatch(/contractState=""/);
    }
  });

  test("the transport failure still distinguishes unavailable from load-failed", () => {
    // Q297's typed 503 body says WHICH outage this is; collapsing it back to one
    // generic name would lose the distinction the backend went to work to publish.
    expect(SOURCE).toContain('"load-failed"');
    expect(SOURCE).toContain('detail?.reason || "unavailable"');
  });

  test("parked categories publish Queue 299's disposition", () => {
    const i = SOURCE.indexOf('data-testid="calibration-parked-category"');
    const block = SOURCE.slice(i, i + 300);
    expect(block).toContain("data-disposition=");
    expect(block).toContain("data-category=");
  });
});

describe("StatCard threads the hook through to the VALUE element", () => {
  // The positional `> div` index-1 read is what the `-value` hook replaces. If
  // this thread-through is ever dropped, the pack silently falls back to
  // reading whatever is second inside the card — including the detail line,
  // which also contains digits and would still pass a finite-number check.
  test("the value div carries `<testId>-value`", () => {
    expect(SOURCE).toContain("data-testid={testId ? `${testId}-value` : undefined}");
  });

  test("the card root carries the bare testId", () => {
    const i = SOURCE.indexOf("function StatCard(");
    const block = SOURCE.slice(i, i + 700);
    expect(block).toContain("data-testid={testId}");
  });

  test("testId is optional, so a card without one emits no empty hook", () => {
    const i = SOURCE.indexOf("function StatCard(");
    const block = SOURCE.slice(i, i + 700);
    expect(block).toContain("testId?: string");
    // `undefined` (not "") is what makes React omit the attribute entirely.
    expect(block).toContain(": undefined");
  });
});

describe("hooks expose no user data", () => {
  // A test hook is public HTML. Everything published above is either a page-level
  // aggregate, a cohort label, or a payload contract version — nothing that
  // identifies a person, a session, or a signed-in state.
  test("no hook attribute references a user, session, or auth value", () => {
    const attrs = SOURCE.match(/data-[a-z-]+=\{[^}]*\}/g) ?? [];
    const leaky = attrs.filter((a) => /user|session|email|token|auth|uid|ip\b/i.test(a));
    expect(leaky).toEqual([]);
  });
});
