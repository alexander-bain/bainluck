/**
 * #7765 — when the accuracy page renders NO content, it speaks the word the nav
 * used to bring the reader there.
 *
 * ── THE DEFECT ──────────────────────────────────────────────────────────────
 *
 * #7738 renamed the footer's only link to this page from "Calibration" to
 * "Accuracy" and moved the tab/share title with it. Five states then still
 * printed the old noun, and they are exactly the states that render an empty
 * page — no Calibration Table, no "what's a calibration curve?", nothing on
 * screen that gives the word a meaning:
 *
 *     Loading calibration data...                                (every load)
 *     Calibration data is being rebuilt and is not ready yet.    (rebuilding)
 *     Calibration data is temporarily unavailable. …             (budget)
 *     We're not showing calibration numbers right now — …        (contract)
 *     Couldn't load this calibration data                        (transport)
 *
 * Measured in the bytes Vercel serves, 2026-09-21, not in a branch — three of
 * them were live in `/_next/static/chunks/app/calibration/page-c13a70f2….js`.
 *
 * ── THE FENCE THIS SUITE ENCODES, AND WHY IT IS NOT "BAN THE WORD" ──────────
 *
 * #7738's body says the page "never says the word to a reader". That is not
 * accurate — the rendering page says it eight times — and the correction is
 * what makes this guard safe to write. Each of those eight arrives with its
 * meaning attached: the name of a specific table, a FAQ entry that DEFINES the
 * term, a citation of someone else's calibration curve. D102 permits exactly
 * that. What is banned is the word with nothing beside it.
 *
 * So the rule is scoped by WHERE the string lives, which is the same shape
 * `copyBans.ts`' fourth consumer (`noReadingCopyClaims.test.tsx`) already uses
 * and for the same stated reason: "that group's scope is WHERE the string
 * lives". `assertions` below are the empty-state producers, by name.
 *
 * ── THE HALF A BUNDLE SCAN CANNOT SEE, WHICH IS THE ONE THAT MATTERS ────────
 *
 * `page.tsx`'s rebuild sentence is only a FALLBACK, for a body that did not
 * say. The sentence a reader actually meets is composed at runtime by
 * `routes/calibration.py`'s `UNAVAILABLE_ADVICE`, and that file says so itself:
 * "the sentence here is composed at runtime and reaches the same reader's
 * screen where no bundle scan can see it."
 *
 * A frontend-only sweep of this wording would therefore pass every existing
 * guard, scan clean against production, and change nothing a reader meets in
 * the state that matters. This suite reads the Python source for that reason,
 * and pins the two sentences byte-identical so they cannot drift into two
 * different words for one state. `test_accuracy_page_no_content_copy_7765.py`
 * is the other half: it asserts the same thing over the imported objects at
 * runtime, which is the only place a computed message could hide.
 *
 * ── HOW THIS COULD BE VACUOUS, AND WHAT ANSWERS IT ──────────────────────────
 *
 * Every assertion here runs over strings pulled out of two source files by
 * regex. An extraction that silently matches nothing is a green suite over no
 * rows — the failure mode this repo has hit before (#7734's own note). Two
 * things answer it: every extractor asserts its own arity before it is used,
 * and `the word is still there where it belongs` is a positive control that
 * fails if the scanner cannot see `page.tsx` at all, or if someone "fixes"
 * this by deleting the vocabulary the fence deliberately keeps.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { CONTRACT_REFUSAL_MESSAGE } from "@/lib/calibrationContract";

const PAGE_PATH = join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const ROUTE_PATH = join(
  __dirname, "..", "..", "..", "backend", "app", "routes", "calibration.py"
);

const PAGE = readFileSync(PAGE_PATH, "utf8");
const ROUTE = readFileSync(ROUTE_PATH, "utf8");

/**
 * `page.tsx` with comments stripped.
 *
 * The prose in this file NAMES the banned word many times over — including in
 * the block comments this change added to explain the fence. Scanning the raw
 * file would therefore fail on its own documentation, which is the trap
 * `calibrationNamesTheThrottle.test.tsx` already hit and solved the same way.
 */
const PAGE_CODE = PAGE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

/** The pipeline noun, in any casing, as a reader would meet it. */
const PIPELINE_NOUN = /calibration/i;

/**
 * The subject `page.tsx` hands `describeLoadFailure`.
 *
 * Not decoration: `loadFailure.ts` interpolates it into six reader sentences
 * ("Couldn't load this {subject}", "{Subject} not found", "We could not load
 * this {subject}…"), so it is copy wearing an argument's clothes — which is
 * why it survived a sweep that read only quoted JSX.
 */
function loadFailureSubjects(): string[] {
  const found = [...PAGE_CODE.matchAll(/describeLoadFailure\(\s*[^,]+,\s*"([^"]+)"/g)]
    .map(m => m[1]);
  expect(found.length).toBeGreaterThan(0);
  return found;
}

/** Every literal sentence the page hands a no-content renderer. */
function emptyStateMessages(): string[] {
  const loading = [...PAGE_CODE.matchAll(/<LoadingState\s+message="([^"]+)"/g)].map(m => m[1]);
  const unavailable = [...PAGE_CODE.matchAll(/"((?:Accuracy|Calibration) data [^"]+)"/g)]
    .map(m => m[1]);
  const found = [...loading, ...unavailable];
  expect(found.length).toBeGreaterThan(0);
  return found;
}

/** The message half of every `UNAVAILABLE_ADVICE` entry, from the Python source. */
function backendRefusalSentences(): string[] {
  const start = ROUTE.indexOf("UNAVAILABLE_ADVICE: dict = {");
  expect(start).toBeGreaterThan(-1);
  const end = ROUTE.indexOf("\n\n\ndef unavailable_advice", start);
  expect(end).toBeGreaterThan(start);
  const block = ROUTE.slice(start, end);
  // 4 OR 8 spaces, and the range is load-bearing: the mapped reasons are nested
  // inside a tuple inside the dict (8), while `UNAVAILABLE_ADVICE_DEFAULT` is a
  // bare module-level tuple (4). An 8-only pattern reads the default as absent
  // and quietly drops the ONE sentence that every unmapped reason falls back
  // to — which is what this extractor's arity assertion caught when it was.
  const found = [...block.matchAll(/^ {4,8}"([A-Z][^"]{20,})",$/gm)].map(m => m[1]);
  // Two today, in source order: the transient `route_budget_exhausted` sentence
  // and the cautious default. Arity is asserted so a restructure that defeats
  // the regex reddens here rather than passing a scan over nothing.
  expect(found.length).toBe(2);
  return found;
}

describe("#7765 — the accuracy page's no-content states", () => {
  it("say 'accuracy', never the pipeline noun, in every empty-state sentence", () => {
    for (const sentence of emptyStateMessages()) {
      expect(sentence).not.toMatch(PIPELINE_NOUN);
    }
  });

  it("hand `describeLoadFailure` a reader's subject, since it becomes six sentences", () => {
    for (const subject of loadFailureSubjects()) {
      expect(subject).not.toMatch(PIPELINE_NOUN);
    }
  });

  it("refuse the population contract in the reader's word", () => {
    expect(CONTRACT_REFUSAL_MESSAGE).not.toMatch(PIPELINE_NOUN);
    // The constant is imported, not scraped, so this one cannot be defeated by
    // an extraction that stops matching.
    expect(CONTRACT_REFUSAL_MESSAGE).toContain("accuracy numbers");
  });

  it("carry the same word in the backend sentences a bundle scan cannot reach", () => {
    for (const sentence of backendRefusalSentences()) {
      expect(sentence).not.toMatch(PIPELINE_NOUN);
    }
  });

  it("keep the page's fallback byte-identical to the sentence the server sends", () => {
    // `page.tsx:725` renders only when the body did not say. If the two drift,
    // one state speaks with two voices depending on which half answered — and
    // the frontend one is the half that is easy to see, so the drift would hide
    // on the side nobody scans.
    const [, backendDefault] = backendRefusalSentences();
    expect(emptyStateMessages()).toContain(backendDefault);
  });

  it("the word is still there where it belongs — the fence, and this suite's control", () => {
    // If this fails, either the scanner is not reading `page.tsx` (and every
    // assertion above is green over nothing), or a sweep took the eight
    // in-context uses the fence deliberately keeps: the table's name, the FAQ
    // entry that defines the term, the Metaculus citation. Those are copy this
    // issue does not touch.
    const rendered = PAGE_CODE.match(/calibration/gi) ?? [];
    expect(rendered.length).toBeGreaterThanOrEqual(5);
    expect(PAGE_CODE).toContain("Calibration Table");
    expect(PAGE_CODE).toContain("What&rsquo;s a calibration curve?");
  });
});
