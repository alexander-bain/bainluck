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

import { MATCHED_BUCKET_MIN_SIDE_N } from "@/lib/calibrationMath";
import * as fs from "fs";
import * as path from "path";

/**
 * The files the calibration surface's hooks are declared in.
 *
 * UX-P128: this was `page.tsx` alone, and the day a row moved into its own
 * component the tripwire fired with "calibration-provider-row … Expected 1,
 * Received 0" — a hook that was still in the DOM, still selected by the rail,
 * reported as DROPPED. That is a false RED, which is the safe direction, but a
 * source-level check that cannot follow an extraction taxes exactly the
 * refactor that made the row testable.
 *
 * So the set is the surface, not the page. Concatenation (rather than a count
 * per file) is deliberate: the duplicate-detection this suite exists for has to
 * see a hook declared once in EACH file as two declarations, not as one apiece.
 */
const SOURCE_FILES = [
  path.join(__dirname, "..", "..", "app", "calibration", "page.tsx"),
  path.join(__dirname, "..", "..", "components", "SourceComparisonRow.tsx"),
];

const SOURCE: string = SOURCE_FILES.map(f => fs.readFileSync(f, "utf8")).join("\n");

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
  // CAL-P043 / #1643. MCE lived only inside the ECE card's detail PROSE, so the
  // rail could read the headline number and not the worst-bucket number beside
  // it. Both are raw attributes on this wrapper now.
  "calibration-stat-ece-figures",
  "calibration-stat-brier",
  "calibration-stat-sources",
  "calibration-stat-categories",
  "calibration-cohort-toggle",
  "calibration-activity-section",
  "calibration-activity-moved",
  "calibration-activity-unchanged",
  "calibration-activity-sentence",
  // CAL-P025 / exit-exam item 2. The matched-bucket comparison is the claim the
  // section now leads with, so the rail has to be able to read it directly —
  // its numbers are the ones a regression would silently change.
  "calibration-matched-buckets",
  "calibration-matched-sentence",
  "calibration-matched-unavailable",
  // CAL-P025 / exit-exam item 4.
  "calibration-source-panels",
  "calibration-category-breakdown",
  "calibration-niche-section",
  // Queue 316 (CAL-P050) — the comms pass. Every one of these anchors a claim
  // Alex asked to be made in words, so each is exactly the kind of element a
  // later reword would otherwise delete without anything going red.
  "calibration-plain-headline",
  "calibration-show-the-math",
  "calibration-provider-note",
  "calibration-shape-annex-note",
  "calibration-buckets-in-band-note",
  "calibration-price-basis-note",
] as const;

// UX-P078 (Alex ruling 2026-08-14(b) item 3): By Source collapsed to one panel
// per provider, and the shape annex moved inside the Sportsbooks panel.
const UX_P078_HOOKS = [
  // Rendered in a `.map()` over providers — declared once, three in the DOM.
  "calibration-provider-panel",
  // Rendered once, inside the one provider that has more than one shape.
  "calibration-shape-breakdown",
] as const;

const COLLECTION_HOOKS = [
  "calibration-category-row",
  "calibration-parked-category",
  // One per matched bucket / per source — lists, rendered in a `.map()`.
  "calibration-matched-row",
  "calibration-source-panel",
  // Queue 316: one per PROVIDER, so three rows where there were five.
  "calibration-provider-row",
] as const;

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

  test.each(UX_P078_HOOKS)("%s is declared exactly once", (hook) => {
    expect(declarations(hook)).toBe(1);
  });

  test("no two hooks share a name", () => {
    const all = [...SINGLETON_HOOKS, ...COLLECTION_HOOKS, ...UX_P078_HOOKS];
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

  test("the page root publishes the complete cross-surface parity record", () => {
    // CAL-P043 / #1643. Web published these facts as a dozen separate
    // attributes and native published one structured string, so "do the two
    // surfaces agree" had no answer that did not involve a translation table
    // nobody maintained. `data-parity` is that answer, in native's grammar.
    expect(SOURCE).toContain("data-parity={parity ? parityValue(parity) : \"\"}");

    // Raw, not formatted. The whole point of the record is that it survives a
    // reword and fails on a wrong number; `toFixed(1)`/`toLocaleString()` values
    // do the opposite of both.
    expect(SOURCE).toContain("data-ece={cohortECE}");
    expect(SOURCE).toContain("data-mce={cohortMCE}");
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
    // Reading the payload's staleness fields again here is how a disclosure
    // would silently outrank a refusal: two independent conditionals, and
    // whichever is checked first wins. The banner renders off ONE pure
    // decision, taken above the conditional returns.
    //
    // CAL-P077 (#2007 item 1b): that decision moved from `contract.degraded` to
    // `staleness`, because the two questions are different. The contract asks
    // "may this build label these numbers"; `decideCalibrationStaleness` asks
    // "what must the reader be told about them", and it answers with three
    // states where `degraded` had one. The assertion follows the INVARIANT
    // rather than the identifier: whatever the gate is called, it must be a
    // single pure decision and the JSX must not re-read the raw fields.
    expect(SOURCE).toContain("{staleness && (");
    expect(SOURCE).toContain("useMemo(() => decideCalibrationStaleness(data), [data])");
    const bannerIdx = SOURCE.indexOf('data-testid="calibration-stale-banner"');
    const before = SOURCE.slice(Math.max(0, bannerIdx - 600), bannerIdx);
    expect(before).not.toContain('data.cache?.status === "stale"');
    expect(before).not.toContain('data.availability !==');
    expect(before).not.toContain("staged?.frozen_over_drift");
  });

  test("the banner names WHICH kind of staleness, as data", () => {
    // #2007 item 1b. "Not being refreshed right now" is true of a dated
    // last-good and FALSE of a frozen input bank — the curve rebuilds hourly
    // there, and only the census under it is old. A rail (and a person) has to
    // be able to tell the two apart without parsing the sentence.
    const i = SOURCE.indexOf('data-testid="calibration-stale-banner"');
    const block = SOURCE.slice(i, i + 900);
    expect(block).toContain("data-staleness-kind={staleness.kind}");
    expect(block).toContain("data-staged-at=");
    expect(block).toContain("data-units-drifted=");
    // The false sentence may appear ONLY under the last-good branch.
    const falseCopy = SOURCE.indexOf("are not being refreshed right now");
    const lastGoodBranch = SOURCE.indexOf('staleness.kind === "last-good"');
    const frozenBranch = SOURCE.indexOf('staleness.kind === "frozen-inputs"');
    expect(lastGoodBranch).toBeGreaterThan(-1);
    expect(falseCopy).toBeGreaterThan(lastGoodBranch);
    expect(falseCopy).toBeLessThan(frozenBranch);
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

  test("the matched-bucket comparison LEADS the section, ahead of the tiles", () => {
    // CAL-P025 / exit-exam item 2 is an ordering requirement, not an addition:
    // "led by the matched-bucket comparison; the raw cross-cohort tiles are
    // demoted". Rendering the table somewhere below the tiles would satisfy
    // every other assertion in this file and fail the exam item, so the order
    // is asserted rather than left to whoever next edits the JSX.
    const section = SOURCE.indexOf('data-testid="calibration-activity-section"');
    const matched = SOURCE.indexOf('data-testid="calibration-matched-buckets"');
    const tiles = SOURCE.indexOf('testId="calibration-activity-moved"');
    expect(section).toBeGreaterThan(-1);
    expect(matched).toBeGreaterThan(section);
    expect(tiles).toBeGreaterThan(matched);
  });

  test("the matched comparison publishes its finding as data, not only as prose", () => {
    // Same reason `data-activity-direction` exists: the rail must be able to
    // grade the number without parsing a sentence that anyone may reword.
    const i = SOURCE.indexOf('data-testid="calibration-matched-sentence"');
    const block = SOURCE.slice(i, i + 400);
    expect(block).toContain("data-widest-bucket=");
    expect(block).toContain("data-widest-gap-pp=");
    expect(block).toContain("data-compared-n=");
  });

  test("a matched row publishes whether it is comparable, and its gap", () => {
    // A greyed thin row and a real one are visually similar and mean different
    // things. `data-comparable` is what stops a rail grading the wrong one.
    const i = SOURCE.indexOf('data-testid="calibration-matched-row"');
    const block = SOURCE.slice(i, i + 260);
    expect(block).toContain("data-comparable={row.comparable}");
    expect(block).toContain("data-gap-pp=");
  });

  test("each SHAPE panel publishes its own n and ECE", () => {
    // Exit-exam item 4's whole point: equal-area panels erase the 28x size
    // difference unless every frame carries its own weight.
    //
    // UX-P078: these are the per-source-key panels, which now live inside the
    // Sportsbooks disclosure rather than being the top level of By Source. The
    // hook name is unchanged on purpose — it still means "one per source key",
    // which is what the rail's pack reads it as.
    const i = SOURCE.indexOf('data-testid="calibration-source-panel"');
    const block = SOURCE.slice(i, i + 240);
    expect(block).toContain("data-source={sp.source}");
    expect(block).toContain("data-panel-n={sp.n}");
    expect(block).toContain("data-panel-ece={sp.ece}");
  });

  test("each PROVIDER panel publishes its n, its ECE, and which keys it pooled", () => {
    // UX-P078 (Alex ruling 2026-08-14(b) item 3). The provider panel is the new
    // top level of By Source. `data-provider-sources` is what lets the rail
    // verify the collapse actually pooled three keys rather than relabelling
    // one of them — the same thing `calibration-provider-row` carries in the
    // table above, so the two sections can be compared without a translation.
    const i = SOURCE.indexOf('data-testid="calibration-provider-panel"');
    expect(i).toBeGreaterThan(-1);
    const block = SOURCE.slice(i, i + 320);
    expect(block).toContain("data-provider={p.provider}");
    expect(block).toContain("data-provider-sources={p.sources.join(\",\")}");
    expect(block).toContain("data-panel-n={p.n}");
    expect(block).toContain("data-panel-ece={p.ece}");
  });

  test("a provider panel declares WHICH KIND of ECE it is showing", () => {
    // Ruling 003 says a panel renders the SERVER's number. The payload
    // publishes ECE per source key and none per provider, so the Sportsbooks
    // panel necessarily shows a POOLED figure. That is allowed only because the
    // page derives it once (`providerMetrics`, rendered twice) — and the reader
    // of the DOM must be able to tell the two kinds apart without trusting our
    // prose. Delete this attribute and a pooled number becomes indistinguishable
    // from a published one to every downstream grader.
    const i = SOURCE.indexOf('data-testid="calibration-provider-panel"');
    const block = SOURCE.slice(i, i + 640);
    expect(block).toContain("data-ece-basis={p.eceBasis}");
  });

  test("the shape breakdown is a DISCLOSURE, and its announcement sits outside it", () => {
    // UX-P075's near-miss, guarded: `innerText` does not return a closed
    // `<details>`, so a sentence folded into the thing it announces is
    // invisible to the browser rail AND to a reader who never opens it.
    // `calibration-shape-annex-note` must therefore be declared BEFORE the
    // `<details>` that contains the shape panels.
    const note = SOURCE.indexOf('data-testid="calibration-shape-annex-note"');
    const details = SOURCE.indexOf('data-testid="calibration-shape-breakdown"');
    expect(note).toBeGreaterThan(-1);
    expect(details).toBeGreaterThan(-1);
    expect(note).toBeLessThan(details);
    // And the shape panels must be INSIDE it — that is what "the annex moved"
    // means. If they drift back out, By Source is five panels again.
    const shapePanel = SOURCE.indexOf('data-testid="calibration-source-panel"');
    expect(shapePanel).toBeGreaterThan(details);
  });

  test("the matched table's thin floor is the SAME number its caption cites", () => {
    // The caption under the table says rows below `MIN_CHART_BUCKET_N` are
    // greyed, but the greying is decided by `MATCHED_BUCKET_MIN_SIDE_N` in
    // `calibrationMath`. They are equal today and nothing enforced it, so
    // changing either one alone would leave the page describing a floor it
    // does not apply — a caption that lies about the rows beside it.
    const pageFloor = SOURCE.match(/const MIN_CHART_BUCKET_N = (\d+);/);
    expect(pageFloor).not.toBeNull();
    expect(Number(pageFloor![1])).toBe(MATCHED_BUCKET_MIN_SIDE_N);
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

// ---------------------------------------------------------------------------
// UX-P080 — Alex's calibration round 2, items 1, 2 and 4.
// ---------------------------------------------------------------------------

describe("item 1 — the Brier card earns its sentence", () => {
  // Alex: "explain it in ONE sentence of small grey text, or exclude it from the
  // headline row. If it can't earn its sentence, it doesn't earn its card."
  test("the Brier card's detail is an explanation, not a direction hint", () => {
    expect(SOURCE).toContain("const BRIER_ONE_LINER");
    expect(SOURCE).toContain("detail={BRIER_ONE_LINER}");
    expect(SOURCE).toContain("coin-flipping scores 0.25");
    expect(SOURCE).not.toContain('detail="0 = oracle, lower = better"');
  });

  test("the sentence says what the number MEASURES, not just which way is good", () => {
    const sentence = SOURCE.match(/const BRIER_ONE_LINER =\s*([\s\S]*?);/)?.[1] ?? "";
    // A direction hint ("lower = better") is satisfiable without ever naming the
    // quantity. Naming what is being measured is the part that earns the card.
    expect(sentence).toMatch(/how far/i);
    expect(sentence).toMatch(/squared/i);
    expect(sentence).toMatch(/0 is perfect/i);
  });

  test("BRIER_ONE_LINER is NOT exported from the page module", () => {
    // A Next.js page may only export `default`/`metadata`/… — an extra export
    // reds the generated route type, and `next build` does NOT catch it
    // (gotcha #10: build is the ESLint gate, typecheck is the TS gate).
    expect(SOURCE).not.toMatch(/^export const BRIER_ONE_LINER/m);
  });
});

describe("item 2 — the Sources KPI counts providers, not shapes", () => {
  test("the card's value comes from providerGroups, not from sources", () => {
    expect(SOURCE).toContain("value={String(providerGroups.length)}");
    expect(SOURCE).not.toContain("value={String(sources.length)}");
  });

  test("the shapes are named in the subtext rather than dropped", () => {
    expect(SOURCE).toContain("detail={providerKpiDetail(providerGroups, sourceLabel)}");
  });

  test("the KPI is derived from the SAME groups the tables below render", () => {
    // The whole point of the merge reaching this card: it cannot say 5 while
    // Source Comparison and By Source say 3. Shared derivation is what
    // guarantees that — a second count kept "in step" is the failure mode this
    // page keeps re-learning (#1620's disease).
    const groupsDecl = SOURCE.match(/const providerGroups = ([^;]+);/)?.[1] ?? "";
    expect(groupsDecl).toContain("groupSourcesByProvider(sources)");
    expect(SOURCE).toContain("buildProviderPanels(");
    expect(SOURCE).toContain("providerGroups.map(group =>");
  });
});

describe("item 4 — every section names the cohort it draws from", () => {
  /**
   * Sections that legitimately draw from NO cohort. Everything else must carry
   * a <CohortTag>, so a NEW section is RED BY DEFAULT until its author either
   * tags it or consciously declares it cohort-free here.
   *
   * That default is the whole design. Alex had to ASK whether the category
   * section was traded-only; a rule that says "remember to label sections"
   * would have produced the same question again on the next section added.
   */
  const COHORT_FREE_SECTIONS = [
    "Something went wrong", // the ErrorBoundary fallback
    "How We Compare", // external published benchmarks, not our cohort
    "Further Reading",
    "How We Measure This",
  ];

  // The inner may not itself contain an h2 tag. Without that, a PROSE mention
  // of `<h2>` in a comment (this file's own design note is one) opens a match
  // that runs to the next real `</h2>`, swallowing several hundred lines of
  // code and reporting it as one untagged section. Found on this guard's first
  // run, and fixed here rather than by rewording the comment — a guard a future
  // comment can break is not a guard.
  const headings = [
    ...SOURCE.matchAll(/<h2(?:\s[^>]*)?>((?:(?!<\/?h2)[\s\S])*?)<\/h2>/g),
  ].map((m) => ({
    inner: m[1],
    text: m[1].replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim(),
  }));

  test("the page still has the sections this guard is about", () => {
    // Anti-vacuity: a regex that matches nothing passes every assertion below.
    expect(headings.length).toBeGreaterThanOrEqual(10);
  });

  test.each(
    headings
      .filter((h) => !COHORT_FREE_SECTIONS.some((f) => h.text.startsWith(f)))
      .map((h) => [h.text, h.inner] as const)
  )("section %s carries a cohort tag", (_text, inner) => {
    expect(inner).toContain("<CohortTag");
  });

  test("the tag is DERIVED from the live cohort, never written beside it", () => {
    // If a section hard-coded "Traded", flipping the toggle would leave it
    // lying. Every tag takes the cohort object.
    const tags = SOURCE.match(/<CohortTag[^/]*\/>/g) ?? [];
    expect(tags.length).toBeGreaterThanOrEqual(8);
    for (const tag of tags) expect(tag).toContain("cohort={cohort}");
  });

  test("the traded-vs-untraded section is labelled as the comparison it is", () => {
    // Labelling THAT section with the active cohort would be a lie in the one
    // place the distinction is being explained to the reader.
    expect(SOURCE).toContain('<CohortTag cohort={cohort} scope="comparison" />');
  });
});
