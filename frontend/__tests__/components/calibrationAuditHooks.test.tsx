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
// quietly grading something else.
//
// UX-P227 — WHY THIS SUITE READS BOTH THE SOURCE AND THE DOM.
//
// It used to read only the source, justified by "the page is a large client
// component behind SWR, and rendering it would prove less and break more". That
// was inherited rather than measured, and measuring it found both halves false
// for THIS page:
//
//   - "break more" is false. `app/calibration/page.tsx` gates on `useSWR`, which
//     is a MODULE BOUNDARY — a mock settles it synchronously, with no DOM. It
//     renders in ~350ms behind the five mocks below. (Contrast `app/daily`,
//     which opens on `useState(true)` cleared only inside a `useEffect`: no DOM,
//     no mock, no render, ever. Same outward shape, opposite answer — the gate
//     KIND is what decides, not the size of the component.)
//   - "prove less" is false, and backwards. A source grep can only count hooks
//     someone remembered to list, and cannot tell a hook that is DECLARED from
//     one that REACHES THE DOM. Rendering found two things the grep could not:
//     `calibration-provider-panel` is declared once and renders THREE times, and
//     `calibration-overall-split` — which the pack selects positionally, as
//     `> summary` — was not guarded here at all.
//
// So both layers stay, because they prove different things. The source layer
// asserts what a grep is actually good at: declaration counts, ordering inside
// the JSX, and the non-export rule. The DOM layer asserts reachability and
// real cardinality. Neither subsumes the other, and the pack-coverage guard
// below is what stops the list drifting out of step with the pack again.

import { MATCHED_BUCKET_MIN_SIDE_N } from "@/lib/calibrationMath";
import * as fs from "fs";
import * as path from "path";
import * as React from "react";
import * as ts from "typescript";

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
  // UX-P227. The pack has selected this since L2-230 and this list never
  // carried it, so the tripwire was blind to exactly one of the hooks it
  // exists to protect — and to the worst one: the pack reads it as
  // `[data-testid="calibration-overall-split"] > summary`, a positional child
  // read of the same class the header above calls the real hazard. Dropping or
  // renaming it left CI green. Found by rendering (the source grep can only
  // check names already on this list), and kept honest from here by
  // "every hook the pack selects is guarded here" below.
  "calibration-overall-split",
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

// ---------------------------------------------------------------------------
// UX-P227 — the tripwire covers the PACK, and the hooks reach the DOM.
// ---------------------------------------------------------------------------

/**
 * Every hook this suite guards, in one set.
 *
 * The three lists above are split by what they mean in the SOURCE (declared
 * once vs declared once inside a `.map()`); for coverage and reachability the
 * only question is whether a hook is guarded at all.
 */
const GUARDED_HOOKS: readonly string[] = [
  ...SINGLETON_HOOKS,
  ...COLLECTION_HOOKS,
  ...UX_P078_HOOKS,
];

// ---------------------------------------------------------------------------
// The pack is READ THROUGH THE TYPESCRIPT AST, not as text.
//
// UX-P229 round 3, after CERT-585. Rounds 1 and 2 read the spec as a string and
// each was defeated by a spelling. CERT-582 assembled a hook name from parts
// (`"calibration-" + "computed-hook"`). Round 2 answered by asserting the SHAPE
// of every `data-testid="..."` literal — and CERT-585 walked straight past it by
// leaving the shape alone and poisoning what feeds it: replacing one element of
// `STAT_HOOKS` with `["calibration","stat","outcomes"].join("-")` keeps the
// allowed `data-testid="${hook}"` selector, keeps PACK_HOOKS at 13, keeps every
// illegal/missed list empty — and the hook Playwright actually uses is captured
// by nobody.
//
// The sibling file (`discoverAuditHooks.test.tsx`, CERT-584 -> CERT-587) lost
// twice the same way and stopped reading text. So does this one. Selectors are
// RESOLVED: a selector argument either evaluates to a set of strings this file
// can compute — whose hooks are extracted and demanded — or it fails LOUDLY.
// There is no third outcome, and no spelling changes that.
//
// WHERE THIS DIFFERS FROM THE DISCOVER PORT, AND WHY (UX-P228-4: the same defect
// class needs different repairs in two files, and the discriminator is
// measured). Discover's pack is fully literal, so it can afford a whole-file
// "exactly one binding of this name" rule. Calibration's legitimately reaches
// its hooks two indirect ways, and a guard that reds a spec doing nothing wrong
// is a guard someone deletes:
//
//   1. `for (const hook of STAT_HOOKS)` — so an ARRAY resolves to a list and the
//      loop variable resolves to its elements; and
//   2. `readActivityValue(ACTIVITY_MOVED)` — a local `const` arrow taking the
//      hook as a PARAMETER, so the body is walked once PER CALL SITE with the
//      parameter bound to the resolved argument.
//
// Both are fail-closed: an array with one unresolvable element makes the whole
// array unresolvable, and a function that is referenced anywhere other than in
// call position (so its callers are unknown) is walked once with its parameters
// poisoned, which reds. `hook` is bound twice in this spec — once by the loop
// and once by the parameter — which is exactly why the resolution is scoped
// rather than name-censused.
// ---------------------------------------------------------------------------

/**
 * What an expression can evaluate to. `strings` is the set of values it may
 * take; `list` is an array literal's contents. `null` anywhere means "this file
 * cannot compute it", and null is always loud.
 */
type Val =
  | { kind: "strings"; values: string[] }
  | { kind: "list"; values: string[] };

/**
 * Name -> which argument carries the selector.
 *
 * Module scope so a test can assert the map still COVERS what the spec calls.
 * The Discover port's battery M16 deleted an entry from the equivalent map and
 * the run stayed green: every call of that API silently stopped being checked
 * while the resolver reported nothing unresolved, because it had stopped
 * looking. A fail-closed check that can be silently unwired is not fail-closed.
 */
const SELECTOR_ARG: Record<string, number> = {
  locator: 0,
  waitForSelector: 0,
  getByTestId: 0,
  $: 0,
  $$: 0,
};

/**
 * The selector-taking APIs that MUST be understood if the pack uses one.
 * Hardcoded on purpose: it is the one list a reviewer has to eyeball.
 */
const REQUIRED_SELECTOR_APIS = ["locator", "waitForSelector", "getByTestId"] as const;

type PackRead = {
  /** Every selector string the pack can produce. */
  selectors: string[];
  /** Selector arguments this file cannot compute. Non-empty is a failure. */
  unresolved: string[];
  /** Every function name called anywhere in the spec. */
  calledNames: Set<string>;
};

/** `=`, `+=`, `??=` and the rest — the documented contiguous SyntaxKind range. */
function isAssignmentOperator(kind: ts.SyntaxKind): boolean {
  return kind >= ts.SyntaxKind.FirstAssignment && kind <= ts.SyntaxKind.LastAssignment;
}

/** Every plain name a binding introduces, flattened through destructuring. */
function boundNames(name: ts.BindingName): string[] {
  if (ts.isIdentifier(name)) return [name.text];
  return name.elements.flatMap((el) => (ts.isBindingElement(el) ? boundNames(el.name) : []));
}

function readPack(file: string, src: string): PackRead {
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true);

  const selectors: string[] = [];
  const unresolved: string[] = [];
  const calledNames = new Set<string>();

  /**
   * Every name written anywhere in the file, in ANY scope. Deliberately coarse:
   * a write to `x` in one function distrusts `x` everywhere. Over-refusing is a
   * loud red on a spec that could have been read; under-refusing is CERT-587,
   * where a stale initializer was handed back as though it were the value.
   */
  const written = new Set<string>();
  function markWrite(target: ts.Node): void {
    const t = ts.isParenthesizedExpression(target) ? target.expression : target;
    if (ts.isIdentifier(t)) written.add(t.text);
    else if (ts.isArrayLiteralExpression(t)) t.elements.forEach(markWrite);
    else if (ts.isSpreadElement(t)) markWrite(t.expression);
    else if (ts.isObjectLiteralExpression(t)) {
      for (const p of t.properties) {
        if (ts.isShorthandPropertyAssignment(p)) written.add(p.name.text);
        else if (ts.isPropertyAssignment(p)) markWrite(p.initializer);
        else if (ts.isSpreadAssignment(p)) markWrite(p.expression);
      }
    }
    // A member write (`obj.x = 1`) rebinds nothing and is deliberately ignored.
  }
  (function census(n: ts.Node): void {
    if (ts.isBinaryExpression(n) && isAssignmentOperator(n.operatorToken.kind)) {
      markWrite(n.left);
    } else if (
      (ts.isPrefixUnaryExpression(n) || ts.isPostfixUnaryExpression(n)) &&
      (n.operator === ts.SyntaxKind.PlusPlusToken ||
        n.operator === ts.SyntaxKind.MinusMinusToken)
    ) {
      markWrite(n.operand);
    } else if (
      (ts.isForOfStatement(n) || ts.isForInStatement(n)) &&
      !ts.isVariableDeclarationList(n.initializer)
    ) {
      markWrite(n.initializer);
    }
    ts.forEachChild(n, census);
  })(sf);

  type Slot = { val: Val | null };
  type FnRec = {
    fn: ts.ArrowFunction | ts.FunctionExpression;
    env: Env;
    inlined: boolean;
    escaped: boolean;
  };
  type Env = { vars: Map<string, Slot>; fns: Map<string, FnRec>; parent: Env | null };

  const newEnv = (parent: Env | null): Env => ({
    vars: new Map(),
    fns: new Map(),
    parent,
  });
  function lookupVar(env: Env, name: string): Slot | undefined {
    for (let e: Env | null = env; e; e = e.parent) {
      const s = e.vars.get(name);
      if (s) return s;
    }
    return undefined;
  }
  function lookupFn(env: Env, name: string): FnRec | undefined {
    for (let e: Env | null = env; e; e = e.parent) {
      const f = e.fns.get(name);
      if (f) return f;
    }
    return undefined;
  }

  const asStrings = (v: Val | null): string[] | null =>
    v && v.kind === "strings" ? v.values : null;
  const cross = (a: string[], b: string[]): string[] =>
    a.flatMap((x) => b.map((y) => x + y));

  function unwrap(n: ts.Node): ts.Node {
    return ts.isParenthesizedExpression(n) || ts.isAsExpression(n)
      ? unwrap(n.expression)
      : n;
  }

  function resolve(n: ts.Node, env: Env, depth = 0): Val | null {
    if (depth > 24) return null;
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) {
      return { kind: "strings", values: [n.text] };
    }
    if (ts.isIdentifier(n)) return lookupVar(env, n.text)?.val ?? null;
    if (ts.isParenthesizedExpression(n) || ts.isAsExpression(n)) {
      return resolve(n.expression, env, depth + 1);
    }
    if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const l = asStrings(resolve(n.left, env, depth + 1));
      const r = asStrings(resolve(n.right, env, depth + 1));
      return l && r ? { kind: "strings", values: cross(l, r) } : null;
    }
    if (ts.isTemplateExpression(n)) {
      let acc = [n.head.text];
      for (const span of n.templateSpans) {
        const v = asStrings(resolve(span.expression, env, depth + 1));
        if (!v) return null;
        acc = cross(cross(acc, v), [span.literal.text]);
      }
      return { kind: "strings", values: acc };
    }
    if (ts.isArrayLiteralExpression(n)) {
      const out: string[] = [];
      for (const el of n.elements) {
        const v = asStrings(resolve(el, env, depth + 1));
        // One unreadable element makes the whole array unreadable. This is the
        // CERT-585 joint: the cert poisoned exactly one STAT_HOOKS entry.
        if (!v) return null;
        out.push(...v);
      }
      return { kind: "list", values: out };
    }
    return null;
  }

  /** Register a scope's own declarations before its statements are walked. */
  function declareScope(stmts: readonly ts.Statement[], env: Env): void {
    // Poison first, resolve second: a name is never readable merely because it
    // was declared, and a forward reference resolves to null rather than to
    // whatever happens to be in an outer scope.
    for (const st of stmts) {
      if (!ts.isVariableStatement(st)) continue;
      for (const d of st.declarationList.declarations) {
        for (const nm of boundNames(d.name)) env.vars.set(nm, { val: null });
      }
    }
    for (const st of stmts) {
      if (!ts.isVariableStatement(st)) continue;
      if (!(st.declarationList.flags & ts.NodeFlags.Const)) continue;
      for (const d of st.declarationList.declarations) {
        if (!ts.isIdentifier(d.name) || !d.initializer) continue;
        if (written.has(d.name.text)) continue; // stays poisoned
        const init = unwrap(d.initializer);
        if (ts.isArrowFunction(init) || ts.isFunctionExpression(init)) {
          // Deferred: the body is walked at each CALL SITE so its parameters
          // carry real values, and once with them poisoned if it escapes or is
          // never called.
          env.fns.set(d.name.text, { fn: init, env, inlined: false, escaped: false });
          env.vars.delete(d.name.text);
          continue;
        }
        env.vars.set(d.name.text, { val: resolve(d.initializer, env) });
      }
    }
  }

  let inlineDepth = 0;

  function walkFnBody(rec: FnRec, args: (Val | null)[]): void {
    const e = newEnv(rec.env);
    rec.fn.parameters.forEach((p, i) => {
      const v = ts.isIdentifier(p.name) ? asStrings(args[i] ?? null) : null;
      for (const nm of boundNames(p.name)) {
        e.vars.set(nm, {
          val: v && !written.has(nm) ? { kind: "strings", values: v } : null,
        });
      }
    });
    inlineDepth += 1;
    try {
      if (inlineDepth <= 4) walk(rec.fn.body, e);
    } finally {
      inlineDepth -= 1;
    }
  }

  /** Anything left uncalled, or referenced as a value, is read with its
   *  parameters poisoned — so a selector inside it reds rather than vanishing. */
  function finishFns(env: Env): void {
    for (const rec of env.fns.values()) {
      if (rec.inlined && !rec.escaped) continue;
      walkFnBody(rec, []);
    }
  }

  function walk(n: ts.Node, env: Env): void {
    if (ts.isSourceFile(n) || ts.isBlock(n)) {
      const e = ts.isSourceFile(n) ? env : newEnv(env);
      declareScope(n.statements, e);
      n.statements.forEach((s) => walk(s, e));
      finishFns(e);
      return;
    }

    if (ts.isVariableStatement(n)) {
      for (const d of n.declarationList.declarations) {
        // A deferred function's body is not walked here.
        if (ts.isIdentifier(d.name) && env.fns.has(d.name.text)) continue;
        if (d.initializer) walk(d.initializer, env);
      }
      return;
    }

    if (ts.isForOfStatement(n)) {
      const e = newEnv(env);
      const init = n.initializer;
      if (ts.isVariableDeclarationList(init)) {
        const src = resolve(n.expression, env);
        const items = src && src.kind === "list" ? src.values : null;
        const readable = !!items && !!(init.flags & ts.NodeFlags.Const);
        for (const d of init.declarations) {
          for (const nm of boundNames(d.name)) {
            e.vars.set(nm, {
              val:
                readable && ts.isIdentifier(d.name) && !written.has(nm)
                  ? { kind: "strings", values: items! }
                  : null,
            });
          }
        }
      }
      walk(n.expression, env);
      walk(n.statement, e);
      return;
    }

    if (ts.isCallExpression(n)) {
      const callee = n.expression;
      const name = ts.isPropertyAccessExpression(callee)
        ? callee.name.text
        : ts.isIdentifier(callee)
          ? callee.text
          : "";
      if (name) calledNames.add(name);

      const idx = SELECTOR_ARG[name];
      if (idx !== undefined && n.arguments.length > idx) {
        const arg = n.arguments[idx];
        const v = asStrings(resolve(arg, env));
        if (!v) {
          unresolved.push(`${name}(${arg.getText().replace(/\s+/g, " ").slice(0, 80)})`);
        } else {
          // `getByTestId` takes the bare name; normalise it to the attribute
          // form so one extraction reads both spellings.
          selectors.push(
            ...(name === "getByTestId" ? v.map((s) => `data-testid="${s}"`) : v)
          );
        }
      }

      const rec = ts.isIdentifier(callee) ? lookupFn(env, callee.text) : undefined;
      if (rec) {
        rec.inlined = true;
        walkFnBody(
          rec,
          n.arguments.map((a) => resolve(a, env))
        );
      } else {
        walk(callee, env);
      }
      n.arguments.forEach((a) => walk(a, env));
      return;
    }

    if (ts.isIdentifier(n)) {
      // A deferred function named outside call position has callers this file
      // cannot see. Mark it, so `finishFns` reads it poisoned as well.
      const rec = lookupFn(env, n.text);
      if (rec) rec.escaped = true;
      return;
    }

    if (
      ts.isArrowFunction(n) ||
      ts.isFunctionExpression(n) ||
      ts.isFunctionDeclaration(n) ||
      ts.isMethodDeclaration(n)
    ) {
      // An anonymous callback — `test("...", async ({ page }) => { ... })`.
      // Its parameters have no known values, which is correct: `page` is not a
      // selector, and anything that IS one reds.
      const e = newEnv(env);
      for (const p of n.parameters) {
        for (const nm of boundNames(p.name)) e.vars.set(nm, { val: null });
      }
      if (n.body) walk(n.body, e);
      return;
    }

    // Over-covering extraction: ANY string literal mentioning the attribute is
    // read, wherever it sits. The safe direction — it cannot hide a hook, only
    // demand one that turns out to be prose.
    if (
      (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) &&
      n.text.includes("data-testid")
    ) {
      selectors.push(n.text);
    }

    ts.forEachChild(n, (c) => walk(c, env));
  }

  walk(sf, newEnv(null));
  return { selectors, unresolved, calledNames };
}

/** The hook set a pack read yields. Shared so the attacks below exercise the
 *  same extraction PACK_HOOKS is built from, not a copy of it. */
function hooksOf(read: PackRead): string[] {
  return [
    ...new Set(
      read.selectors
        .flatMap((s) => [...s.matchAll(/data-testid="([^"]+)"/g)].map((m) => m[1]))
        .filter((h) => h.startsWith("calibration"))
        // `<hook>-value` is StatCard's thread-through, addressed as a suffix of
        // a hook already on the list; it is not separately declared.
        .map((h) => h.replace(/-value$/, ""))
    ),
  ].sort();
}

/**
 * The resolver is ATTACKED here, not described.
 *
 * Three certs on this pair of files (CERT-582, CERT-585 here; CERT-584 and
 * CERT-587 on the Discover sibling) all found the same shape: the guard's
 * rationale lived in a comment, and the comment was true of the code the author
 * was picturing. What closes that is running the attack. Each row is a spec
 * source this file must handle in exactly one of two ways — resolve it, or fail
 * LOUDLY — and the row says which, so a case that starts passing for a new
 * reason is a red rather than a relief.
 *
 * `readPack` and `hooksOf` here are the same functions the real spec goes
 * through above.
 */
const RESOLVER_ATTACKS: ReadonlyArray<{
  name: string;
  src: string;
  /** true ⇒ the selector argument must be reported unresolved. */
  loud: boolean;
  /** Hooks the extraction must yield. Only meaningful when `loud` is false. */
  hooks?: string[];
}> = [
  {
    name: "CERT-585: one STAT_HOOKS element assembled at runtime",
    // The cert's attack verbatim in shape: the `${hook}` selector keeps its
    // allowed form and the poison is in what feeds it.
    src: `const STAT_HOOKS = [
  ["calibration", "stat", "outcomes"].join("-"),
  "calibration-stat-ece",
] as const;
for (const hook of STAT_HOOKS) { page.locator(\`[data-testid="\${hook}"]\`); }`,
    loud: true,
  },
  {
    name: "CERT-587 (sibling): a `let` selector widened by compound assignment",
    src: `let SELECTOR = '[data-testid="calibration-page"]';
SELECTOR += ', [data-' + 'testid="calibration-reassigned"]';
page.locator(SELECTOR);`,
    loud: true,
  },
  {
    name: "a hook array built by a call, not written out",
    src: `const STAT_HOOKS = buildHooks();
for (const hook of STAT_HOOKS) { page.locator(\`[data-testid="\${hook}"]\`); }`,
    loud: true,
  },
  {
    name: "a parameter fed an argument the file cannot compute",
    src: `const read = (hook) => page.locator(\`[data-testid="\${hook}"]\`);
read(pickHook());`,
    loud: true,
  },
  {
    name: "a hook-taking function that escapes as a value",
    // Passed to `forEach`, so its real callers are outside this file's reach.
    // Inlining the one direct call must NOT license the escaped reference.
    src: `const read = (hook) => page.locator(\`[data-testid="\${hook}"]\`);
read("calibration-stat-ece");
HOOKS.forEach(read);`,
    loud: true,
  },
  {
    name: "a parameter reassigned inside the function body",
    // The ONE legal shape where the write census is load-bearing rather than
    // redundant. A `const` — top-level or `for..of` — cannot be assigned to at
    // all, so clause 2 already covers those; a PARAMETER can, and inlining the
    // call site would otherwise bind `hook` to the caller's value while the
    // body uses another. Battery row C9b holds this open.
    src: `const read = (hook) => { hook = "calibration-substituted"; return page.locator(\`[data-testid="\${hook}"]\`); };
read("calibration-stat-ece");`,
    loud: true,
  },
  {
    name: "a `for..of` over a `let` array",
    src: `let HOOKS = ["calibration-stat-ece"];
for (const hook of HOOKS) { page.locator(\`[data-testid="\${hook}"]\`); }`,
    loud: true,
  },
  {
    name: "the pack's `for..of` over a literal array is SUPPORTED",
    src: `const STAT_HOOKS = [
  "calibration-stat-outcomes",
  "calibration-stat-ece",
] as const;
for (const hook of STAT_HOOKS) { page.locator(\`[data-testid="\${hook}"]\`); }`,
    loud: false,
    hooks: ["calibration-stat-ece", "calibration-stat-outcomes"],
  },
  {
    name: "the pack's hook-as-parameter is SUPPORTED, per call site",
    src: `const MOVED = "calibration-activity-moved";
const UNCHANGED = "calibration-activity-unchanged";
const read = (hook) => page.locator(\`[data-testid="\${hook}-value"]\`);
read(MOVED);
read(UNCHANGED);`,
    loud: false,
    hooks: ["calibration-activity-moved", "calibration-activity-unchanged"],
  },
  {
    name: "CERT-582's computed hook name is SUPPORTED, not banned",
    src: `const HOOK = "calibration-" + "computed-hook";
page.locator(\`[data-testid="\${HOOK}"]\`);`,
    loud: false,
    hooks: ["calibration-computed-hook"],
  },
  {
    name: "CERT-584's split attribute name is SUPPORTED",
    src: `const SELECTOR = "[data-" + 'testid="calibration-split"]';
page.locator(SELECTOR);`,
    loud: false,
    hooks: ["calibration-split"],
  },
  {
    name: "the control's control: an ordinary selector resolves clean",
    src: `const PAGE_ROOT = '[data-testid="calibration-page"]';
test("loads", async ({ page }) => { await page.locator(PAGE_ROOT).first(); });`,
    loud: false,
    hooks: ["calibration-page"],
  },
];

describe("the pack resolver fails closed — attacked, not asserted", () => {
  test.each(RESOLVER_ATTACKS.map((a) => [a.name, a] as const))("%s", (_name, attack) => {
    const r = readPack("attack.spec.ts", attack.src);
    if (attack.loud) {
      expect(`unresolved: ${r.unresolved.length}`).not.toBe("unresolved: 0");
    } else {
      expect(JSON.stringify(r.unresolved)).toBe("[]");
      expect(hooksOf(r)).toEqual(attack.hooks);
    }
  });

  test("the attack table exercises both outcomes", () => {
    // Without this the table degenerates the day someone drops the awkward
    // half: all-loud would pass a resolver that resolves nothing, all-clean a
    // resolver that never fails.
    expect(RESOLVER_ATTACKS.some((a) => a.loud)).toBe(true);
    expect(RESOLVER_ATTACKS.some((a) => !a.loud)).toBe(true);
  });
});

describe("the tripwire guards every hook the pack actually selects", () => {
  // The gap this closes: the lists above are hand-maintained, and nothing tied
  // them to the pack. `calibration-overall-split` was selected by the pack and
  // absent here, so the one thing the suite promises — "drop or rename a hook
  // the audit depends on and CI fails HERE" — was untrue for it.
  //
  // Reading the pack file is what makes that unrepeatable. A hook added to the
  // spec reds this test until it is guarded, which is the safe direction and
  // the whole point of a tripwire.
  const SPEC = fs.readFileSync(
    path.join(__dirname, "..", "..", "e2e", "specs", "calibration.spec.ts"),
    "utf8"
  );

  // Literal occurrences anywhere in the spec, including inside its hook arrays
  // (`STAT_HOOKS`) and its selector constants. Deliberately not restricted to
  // selector syntax: a hook named only in a comment is over-covered, which
  // costs a line here and cannot hide a real hole.
  const PACK = readPack("calibration.spec.ts", SPEC);

  /**
   * The union of two readings, and the union is the point.
   *
   * The RESOLVED reading (`hooksOf`) is what the pack can actually select: it
   * follows `STAT_HOOKS` through its `for..of`, and `ACTIVITY_MOVED` through
   * `readActivityValue`'s parameter, to the real strings Playwright receives.
   * The RAW reading is the over-covering half — a bare `calibration-…` token
   * anywhere in the file, comments included. Over-covering costs a line in
   * `GUARDED_HOOKS` and cannot hide a hole, so both are kept and neither is
   * allowed to shrink the other.
   */
  const RESOLVED_HOOKS = hooksOf(PACK);
  const PACK_HOOKS = [
    ...new Set([
      ...RESOLVED_HOOKS,
      ...[...SPEC.matchAll(/calibration-[a-z0-9-]+/g)].map((m) => m[0]),
    ]),
  ]
    .filter((h) => !h.endsWith("-value"))
    .sort();

  test("the pack still selects hooks at all", () => {
    // Anti-vacuity: an empty extraction passes every assertion below.
    expect(PACK_HOOKS.length).toBeGreaterThanOrEqual(10);
  });

  test("the RESOLVED reading is not silently empty either", () => {
    // The raw reading alone would satisfy the count above forever, which is how
    // CERT-585 kept PACK_HOOKS at 13 while the resolver's answer was gone. The
    // two readings are asserted separately so one cannot cover for the other.
    expect(RESOLVED_HOOKS.length).toBeGreaterThanOrEqual(10);
  });

  test("every selector the pack builds is one this file can resolve", () => {
    // The fail-closed joint, and the whole answer to CERT-585.
    //
    // Round 2 asserted the SHAPE of the `data-testid="${hook}"` template and
    // trusted whatever fed `hook`. The cert poisoned one element of `STAT_HOOKS`
    // with a `.join("-")`, left the shape untouched, and the guard never
    // noticed the hook it could no longer see. Shape is not provenance. Any
    // selector argument that does not resolve to a concrete set of strings
    // fails here instead.
    expect(`unresolved: ${JSON.stringify(PACK.unresolved)}`).toBe("unresolved: []");
  });

  test("the resolver still understands every selector API the pack calls", () => {
    // Anti-vacuity for the check above, and the reason "some selectors were
    // found" is not enough. The Discover port's battery deleted one entry from
    // SELECTOR_ARG: the resolvability test stayed green because the resolver
    // had simply stopped looking at those calls, while the literal scan kept
    // the selector list non-empty. A check that can be unwired without anything
    // going red is decoration.
    const used = REQUIRED_SELECTOR_APIS.filter((api) => PACK.calledNames.has(api));
    expect(used.filter((api) => !(api in SELECTOR_ARG))).toEqual([]);
    expect(PACK.selectors.length).toBeGreaterThan(0);
  });

  // WITHDRAWN, and the withdrawal is the finding. This slot briefly held
  // "every hook the resolver reaches is one the raw reading also captured",
  // justified as making drift between the two readings visible. Battery row C2
  // killed it: writing `const ACTIVITY_MOVED = "calibration-" + "activity-moved"`
  // leaves no contiguous token for the raw scan, so a spelling this file
  // deliberately SUPPORTS would have failed here. The check re-imposed the
  // exact text rule the repair exists to drop, one test lower down. There is no
  // sound version of it: the resolver reaching a name the text cannot show is
  // the feature, not the drift. What actually protects the resolved reading
  // from emptying is the unresolvability joint and the API-coverage companion
  // above — both measured (battery C6, C7), not this.

  // STATED GAP, measured (battery M8, a scored survivor). This check is
  // ONE-DIRECTIONAL: pack ⊆ guarded. A hook REMOVED from the pack is not
  // caught here, and that is deliberate — a hook may legitimately be guarded
  // without the pack selecting it (most of the list is), so asserting the
  // reverse would red on every one of them. The cost of the gap is a stale
  // entry surviving here after the pack drops it; the cost of closing it would
  // be a guard nobody could keep green. The browser rail is what notices a
  // selector the pack no longer uses.

  test.each(PACK_HOOKS)("%s is guarded by this suite", (hook) => {
    expect(GUARDED_HOOKS).toContain(hook);
  });
});

// The five mocks the page needs to render off a payload. Each replaces a
// MODULE BOUNDARY — none of them stands in for page-internal state, so nothing
// below is asserting the mock rather than the page.
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) =>
    React.createElement("a", { href }, children),
}));
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/calibration",
}));
jest.mock("@/lib/analytics", () => ({ trackEvent: jest.fn() }));
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: jest.fn() }),
}));
jest.mock("@/hooks", () => ({
  useEngagementTime: () => undefined,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
}));

describe("the hooks REACH THE DOM, in the state each belongs to", () => {
  /**
   * A real `GET /api/calibration` response, pruned to 27 buckets.
   *
   * Captured rather than hand-written, because a hand-written one does not
   * merely risk being wrong — it silently re-answers "can this page render" as
   * "no". Two guessed fixtures were tried first: five plausible keys was
   * refused by the population contract, and dropping `population_version`
   * crashed inside `toFixed`. The live payload has 44 top-level keys and
   * rendered first time.
   *
   * The prune is measured, not assumed: buckets are 89% of the capture, and
   * keeping three per (source, price_moved) group renders a byte-identical SET
   * of test hooks to the full 2,015-bucket payload. Anything that needs more
   * than that will fail loudly here rather than degrade quietly.
   */
  const PAYLOAD = JSON.parse(
    fs.readFileSync(
      path.join(__dirname, "..", "fixtures", "uxp227_calibration_live.json"),
      "utf8"
    )
  );

  /**
   * The same payload with the two cohorts moved onto disjoint bucket indices.
   *
   * `calibration-matched-unavailable` is the one hook no other state reaches:
   * it needs the activity section to render (so BOTH cohorts must be present)
   * while no bucket index is shared (so `matched.widest` is falsy). Deleting a
   * cohort outright does not get there — it drops the whole section, and the
   * hook with it.
   */
  const NO_MATCHED_PAIR = {
    ...PAYLOAD,
    buckets: (PAYLOAD.buckets as Array<Record<string, unknown>>).map((b) =>
      b.price_moved === true ? { ...b, bucket_idx: (b.bucket_idx as number) + 50 } : b
    ),
  };

  function domCounts(swr: unknown): { counts: Record<string, number>; html: string } {
    let html = "";
    jest.isolateModules(() => {
      jest.doMock("swr", () => ({ __esModule: true, default: () => swr }));
      // UX-P223-3: `isolateModules` gives the subject a FRESH `react`, so
      // `react-dom/server` must be required INSIDE the registry that will
      // render — a module-scope import here dies on the page's first `useMemo`.
      const { renderToStaticMarkup } = require("react-dom/server");
      const R = require("react");
      const Page = require("../../app/calibration/page").default;
      html = renderToStaticMarkup(R.createElement(Page));
    });
    const counts: Record<string, number> = {};
    for (const m of html.matchAll(/data-testid="([^"]+)"/g)) {
      counts[m[1]] = (counts[m[1]] ?? 0) + 1;
    }
    return { counts, html };
  }

  const loaded = () => domCounts({ data: PAYLOAD, error: undefined, isLoading: false });

  /**
   * Measured DOM cardinality in the loaded state.
   *
   * This is the distinction the source layer cannot draw at all. Up there,
   * `calibration-provider-panel` and `calibration-shape-breakdown` are both
   * "declared exactly once" and the file has to explain in a COMMENT that the
   * first is a `.map()` and the second is not. Here that comment is an
   * assertion: one renders three times and the other renders once.
   */
  const ONE_IN_DOM = [
    ...SINGLETON_HOOKS.filter(
      // Reached only by a state that has no payload, or by no-matched-pair.
      (h) =>
        !["calibration-error", "calibration-loading", "calibration-matched-unavailable"].includes(h)
    ),
    // From UX_P078_HOOKS: this one really is a singleton in the DOM. Its
    // list-mate `calibration-provider-panel` is not, which is the whole point.
    "calibration-shape-breakdown",
  ];

  const MANY_IN_DOM = ["calibration-provider-panel", ...COLLECTION_HOOKS];

  test("the loaded render is the real page, not a loading shell", () => {
    // Anti-vacuity, and the thing every assertion below rests on. An empty or
    // spinner-only render would satisfy "hook absent" checks trivially.
    const { counts, html } = loaded();
    expect(html.length).toBeGreaterThan(50_000);
    expect(html).toContain('data-contract-state="match"');
    expect(counts["calibration-loading"]).toBeUndefined();
    expect(counts["calibration-error"]).toBeUndefined();
    expect(counts["calibration-page"]).toBe(1);
  });

  test.each(ONE_IN_DOM)("%s reaches the DOM exactly once", (hook) => {
    // Exactly once is what the rail's `.first()` depends on. Two elements and
    // the audit reads whichever markup order put first — the failure the
    // source layer's duplicate check is aimed at, verified where it happens.
    expect(loaded().counts[hook]).toBe(1);
  });

  test.each(MANY_IN_DOM)("%s reaches the DOM as a repeated row", (hook) => {
    // Declared once in source, many times in the DOM. The source layer asserts
    // the declaration; only a render can confirm the repetition is real.
    expect(loaded().counts[hook] ?? 0).toBeGreaterThan(1);
  });

  test("every guarded hook is reachable in SOME state", () => {
    // A hook that is declared, guarded, and rendered by no state at all is
    // dead weight the pack would wait for forever. Five states cover the
    // surface: loaded, loading, transport error, contract refusal, and the
    // no-matched-pair case.
    const seen = new Set<string>();
    for (const state of [
      { data: PAYLOAD, error: undefined, isLoading: false },
      { data: undefined, error: undefined, isLoading: true },
      { data: undefined, error: new Error("boom"), isLoading: false },
      { data: { ...PAYLOAD, population_version: "NOT-A-VERSION-THIS-BUILD-KNOWS" }, error: undefined, isLoading: false },
      { data: NO_MATCHED_PAIR, error: undefined, isLoading: false },
    ]) {
      for (const h of Object.keys(domCounts(state).counts)) seen.add(h);
    }
    const unreachable = GUARDED_HOOKS.filter((h) => !seen.has(h));
    expect(unreachable).toEqual([]);
  });

  test("the refusal states render the error hook and NEVER the page hook", () => {
    // The source layer proves this by comparing two string indices. The render
    // proves the thing itself: on a transport failure and on a refused
    // population contract, no number-bearing markup exists to be mislabelled.
    for (const state of [
      { data: undefined, error: new Error("boom"), isLoading: false },
      { data: { ...PAYLOAD, population_version: "NOT-A-VERSION-THIS-BUILD-KNOWS" }, error: undefined, isLoading: false },
    ]) {
      const { counts } = domCounts(state);
      expect(counts["calibration-error"]).toBe(1);
      expect(counts["calibration-page"]).toBeUndefined();
      expect(counts["calibration-stat-ece"]).toBeUndefined();
    }
  });

  test("the loading state is ONLY the loading hook", () => {
    const { counts } = domCounts({ data: undefined, error: undefined, isLoading: true });
    expect(counts["calibration-loading"]).toBe(1);
    expect(counts["calibration-page"]).toBeUndefined();
    expect(counts["calibration-error"]).toBeUndefined();
  });

  test("the two refusals are told apart by name, in the DOM", () => {
    // Same hook, different failure. If these collapse to one name the rail is
    // back to "something was red" — the exact loss the source layer's
    // `data-error-state-name` check exists to prevent, checked here on the
    // rendered attribute rather than on the JSX that is supposed to emit it.
    const transport = domCounts({ data: undefined, error: new Error("boom"), isLoading: false });
    const refused = domCounts({
      data: { ...PAYLOAD, population_version: "NOT-A-VERSION-THIS-BUILD-KNOWS" },
      error: undefined,
      isLoading: false,
    });
    expect(transport.html).toContain('data-error-state-name="load-failed"');
    expect(refused.html).toContain('data-error-state-name="population-contract-refused"');
  });

  test("the no-matched-pair state reaches the unavailable hook, inside a live section", () => {
    const { counts } = domCounts({ data: NO_MATCHED_PAIR, error: undefined, isLoading: false });
    expect(counts["calibration-matched-unavailable"]).toBe(1);
    // And it is the SECTION's fallback, not the section's absence — otherwise
    // this state would prove the hook reachable by deleting its neighbourhood.
    expect(counts["calibration-activity-section"]).toBe(1);
    expect(counts["calibration-matched-buckets"]).toBeUndefined();
  });
});
