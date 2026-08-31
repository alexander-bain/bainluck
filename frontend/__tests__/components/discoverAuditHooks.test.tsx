// L2-223 Item 3 — the browser-audit rail's Discover hooks.
//
// The rail used to identify a rendered card by `main div.break-inside-avoid`,
// a Tailwind LAYOUT class that `DiscoverSkeletonGrid` also carries. A Discover
// stuck on skeletons therefore satisfied "a real card was visible", recorded a
// plausible first-card latency, and the audit reported GREEN — the C96 [P1]
// false green, reached through the selector instead of the `.catch()` L2-221
// removed. It identified the empty state by the copy string "You're all caught
// up", so an editorial reword would silently have turned a proven empty state
// into an unproven blank page.
//
// These hooks are now load-bearing evidence, not conveniences. This suite is
// the tripwire: if a hook is dropped, renamed, or leaks onto the skeleton, CI
// fails here rather than the audit quietly going green on nothing. Runs in the
// node/SSR env (renderToStaticMarkup) — no jsdom. SWR is not avoided; it is
// mocked at its module boundary inside `isolateModules`, which is what lets the
// page states below be asserted in the DOM instead of grepped for (UX-P228).
//
// And the tripwire now takes its own list FROM the rail: see PACK_HOOKS. A
// hand-kept list drifted once already, which is what left the pack's
// `discover-feed-unavailable` selector guarded by nothing.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("@/lib/analytics", () => ({
  trackEvent: jest.fn(),
}));

import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";

import EndOfFeedCard from "../../components/discover/EndOfFeedCard";
import DiscoverSkeletonGrid from "../../components/discover/DiscoverSkeletonGrid";
import FeedUnavailableNotice from "../../components/discover/FeedUnavailableNotice";

const noop = () => {};

/** Count non-overlapping occurrences of a literal in a string. */
function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

/**
 * Every `discover-*` hook the browser-audit pack actually selects, read FROM
 * the pack.
 *
 * UX-P228: this used to be implicit — the suite asserted the hooks somebody had
 * remembered to add, and nothing compared that set against the rail. It had
 * already drifted. `discover-feed-unavailable` is selected by
 * `discover-smoke.spec.ts` (the `ERROR_STATE` selector, added by L2-238) and is
 * the testId of `FeedUnavailableNotice`'s DEFAULT reason, and no test in this
 * file mentioned it. Dropping or renaming it was a green CI and a rail that had
 * silently lost the one distinction L2-238 added it to make: "the deploy served
 * an unavailable feed" versus "the page was blank" — which is the C96 [P1]
 * false-green class named at the top of this file, reached the other way round.
 *
 * Adding the missing string would have left the NEXT hook to be forgotten
 * identically, so the list is derived instead. A hook added to the pack reds
 * here until it is covered.
 */
const SPEC_DIR = path.join(__dirname, "..", "..", "e2e", "specs");

/**
 * The pack is read through the TypeScript AST, not as text.
 *
 * UX-P228 round 2, after CERT-584. Round 1 read `data-testid="..."` out of the
 * raw source, and the cert defeated it by splitting the ATTRIBUTE NAME:
 * `"[data-" + "testid=\"discover-computed-attr\"]"` contains no contiguous
 * `data-testid`, so both the census and the extraction saw nothing while
 * Playwright received a perfectly valid selector.
 *
 * Patching that regex would have moved the hole one level out again — the same
 * shape the latency lane hit three certs running. A text guard cannot prove
 * "the pack selects nothing I have not seen", because the pack is code. So the
 * selector strings are RESOLVED instead: a selector either evaluates to a
 * string this file can compute, and its hooks are extracted and demanded, or it
 * does not, and that fails LOUDLY. There is no third outcome.
 *
 * Two useful consequences. Comments need no stripping — the parser never sees
 * them, so UX-P213-2's census hazard does not arise. And concatenation is now
 * *supported* rather than banned, so the guard costs the pack no expressiveness.
 */
/**
 * Which API a call invokes, and how far the real arguments are pushed right.
 * `argOffset` is 1 for `f.call(thisArg, …)` and 0 everywhere else. `null` means
 * this file cannot tell what is being called, and that is always LOUD.
 */
type CalleeRead = { name: string; argOffset: number } | null;

type Resolution = {
  file: string;
  selectors: string[];
  unresolved: string[];
  /** Every function name called anywhere in the spec. */
  calledNames: Set<string>;
};

/**
 * Name -> which argument carries the selector. It is not always the first:
 * `measureMainRegion(page, SELECTOR)` takes the page in slot 0.
 *
 * Module scope so a test can assert the map still COVERS what the specs call.
 * Battery M16: deleting `locator` from here made every `locator()` argument
 * stop being checked, and the run stayed green — the resolver reported nothing
 * unresolved because it was no longer looking. A fail-closed check that can be
 * silently unwired is not fail-closed.
 */
const SELECTOR_ARG: Record<string, number> = {
  locator: 0,
  waitForSelector: 0,
  getByTestId: 0,
  $: 0,
  $$: 0,
  measureMainRegion: 1,
};

/**
 * The selector-taking APIs that MUST be understood if a spec uses them.
 *
 * Hardcoded on purpose: it is the one list a reviewer has to eyeball, and it is
 * short. Anything here that a Discover spec calls but `SELECTOR_ARG` does not
 * know is a hole, and reds.
 */
const REQUIRED_SELECTOR_APIS = [
  "locator",
  "waitForSelector",
  "getByTestId",
  "measureMainRegion",
] as const;

/** `=`, `+=`, `??=` and the rest — the documented contiguous SyntaxKind range. */
function isAssignmentOperator(kind: ts.SyntaxKind): boolean {
  return kind >= ts.SyntaxKind.FirstAssignment && kind <= ts.SyntaxKind.LastAssignment;
}

/** Every plain name a binding introduces, flattened through destructuring patterns. */
function boundNames(name: ts.BindingName): string[] {
  if (ts.isIdentifier(name)) return [name.text];
  return name.elements.flatMap((el) =>
    ts.isBindingElement(el) ? boundNames(el.name) : []
  );
}

function resolveSpec(file: string, src: string): Resolution {
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true);

  /**
   * A name is readable only if it is PROVABLY immutable.
   *
   * UX-P228 round 3, after CERT-587. Round 2 recorded every top-level
   * initializer and handed it back on sight, without ever asking whether the
   * binding could change. The cert wrote
   * `let SELECTOR = '[data-testid="discover-card"]'` and then
   * `SELECTOR += ', [data-' + 'testid="discover-reassigned"]'`, and the
   * resolver answered with the STALE initializer and `unresolved: []` — a wrong
   * string returned confidently, which is strictly worse than the loud failure
   * this design exists to guarantee. A new pack hook stayed unguarded and CI
   * stayed green: the exact false-green class, reached through the resolver.
   *
   * "Also look for `+=`" is the move that lost in rounds 1 and 2. So the rule
   * is stated positively, as the conjunction of three facts a parser can settle
   * without a type checker:
   *
   *   1. exactly ONE binding of the name in the whole file — no shadowing by a
   *      parameter, a nested `let`, a catch variable, a destructured element,
   *      an import or a function/class declaration;
   *   2. that binding is a top-level `const` with a plain identifier name; and
   *   3. the name is never a write target anywhere — assignment, compound
   *      assignment, `++`/`--`, a destructuring-assignment target, or a
   *      `for..of`/`for..in` head.
   *
   * Anything else resolves to null, and null is LOUD. Clause 3 is redundant
   * with clause 2 for JavaScript that runs (you cannot assign to a `const`), and
   * it is kept anyway: it is what stops a future edit that relaxes clause 2 for
   * convenience from silently reopening CERT-587. Both clauses are attacked
   * directly in `RESOLVER_ATTACKS` below rather than argued for here.
   */
  const bindingCount = new Map<string, number>();
  const writtenNames = new Set<string>();
  const topLevelConstInit = new Map<string, ts.Expression>();

  const countBinding = (n: string) =>
    bindingCount.set(n, (bindingCount.get(n) ?? 0) + 1);

  function markWrite(target: ts.Node): void {
    const t = ts.isParenthesizedExpression(target) ? target.expression : target;
    if (ts.isIdentifier(t)) writtenNames.add(t.text);
    else if (ts.isArrayLiteralExpression(t)) t.elements.forEach(markWrite);
    else if (ts.isSpreadElement(t)) markWrite(t.expression);
    else if (ts.isObjectLiteralExpression(t)) {
      for (const p of t.properties) {
        if (ts.isShorthandPropertyAssignment(p)) writtenNames.add(p.name.text);
        else if (ts.isPropertyAssignment(p)) markWrite(p.initializer);
        else if (ts.isSpreadAssignment(p)) markWrite(p.expression);
      }
    }
    // A member write (`obj.x = 1`) rebinds nothing and is deliberately ignored.
  }

  function census(n: ts.Node): void {
    // --- value bindings. Interfaces and type aliases live in type space and
    // cannot shadow a value, so they are correctly absent.
    if (ts.isVariableDeclaration(n) || ts.isParameter(n)) {
      boundNames(n.name).forEach(countBinding);
    } else if (
      (ts.isFunctionDeclaration(n) || ts.isClassDeclaration(n) || ts.isEnumDeclaration(n)) &&
      n.name
    ) {
      countBinding(n.name.text);
    } else if (ts.isImportClause(n) && n.name) {
      countBinding(n.name.text);
    } else if (ts.isNamespaceImport(n) || ts.isImportSpecifier(n)) {
      countBinding(n.name.text);
    }

    // --- writes
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
  }
  census(sf);

  for (const st of sf.statements) {
    if (!ts.isVariableStatement(st)) continue;
    if (!(st.declarationList.flags & ts.NodeFlags.Const)) continue;
    for (const d of st.declarationList.declarations) {
      if (ts.isIdentifier(d.name) && d.initializer) {
        topLevelConstInit.set(d.name.text, d.initializer);
      }
    }
  }

  const isStable = (name: string): boolean =>
    topLevelConstInit.has(name) &&
    bindingCount.get(name) === 1 &&
    !writtenNames.has(name);

  // Guards `const A = B; const B = A;` — a cycle is not a value, so it is a
  // resolution failure like any other.
  const resolving = new Set<string>();

  function literalOf(n: ts.Node): string | null {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) return n.text;
    if (ts.isIdentifier(n)) {
      if (!isStable(n.text) || resolving.has(n.text)) return null;
      resolving.add(n.text);
      try {
        return literalOf(topLevelConstInit.get(n.text)!);
      } finally {
        resolving.delete(n.text);
      }
    }
    if (ts.isParenthesizedExpression(n) || ts.isAsExpression(n)) {
      return literalOf(n.expression);
    }
    if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const l = literalOf(n.left);
      const r = literalOf(n.right);
      return l !== null && r !== null ? l + r : null;
    }
    // `event-page.spec.ts` composes `HERO_ANY` from two other constants. A
    // template whose every substitution resolves is just as static as a
    // literal, and refusing it would red a spec that is doing nothing wrong.
    if (ts.isTemplateExpression(n)) {
      let out = n.head.text;
      for (const span of n.templateSpans) {
        const v = literalOf(span.expression);
        if (v === null) return null;
        out += v + span.literal.text;
      }
      return out;
    }
    return null;
  }

  // Resolved module-level constants: `SKELETON` is handed to a helper rather
  // than to `locator()`, so a selector-call-only read would miss
  // `discover-skeleton` entirely and then red on its own guarded list. Only
  // stable names get here, so a mutable one contributes nothing and — if it
  // reaches a selector API — reds below instead.
  const constValues: string[] = [];
  for (const name of topLevelConstInit.keys()) {
    if (!isStable(name)) continue;
    const v = literalOf(topLevelConstInit.get(name)!);
    if (v !== null) constValues.push(v);
  }

  // Every API that turns a string into an element reference. `getByTestId`
  // takes a BARE hook name with no `data-testid` in the text at all, so it is
  // resolved here rather than merely banned. `measureMainRegion` is this
  // repo's own selector-taking helper — `event-page.spec.ts` reaches
  // `discover-skeleton` only through it.
  //
  // STATED GAP (battery M17, a scored survivor): this is a list of NAMES. A new
  // project helper that takes a selector is covered for literal arguments — the
  // literal scan below sees those wherever they appear — but a COMPUTED
  // argument to a helper not named here would be missed. Closing that needs a
  // type checker, not a parser, and it is not this slice.
  const selectors: string[] = [];
  const unresolved: string[] = [];
  const calledNames = new Set<string>();

  /**
   * Which API a call invokes — or an admission that this file cannot tell.
   *
   * UX-P229 round 4, after CERT-590. Rounds 1–3 read the callee as "a property
   * access or a bare identifier, otherwise no name", and the cert reached a
   * selector through `page["locator"](…)`: an ElementAccessExpression, so the
   * name came out `""`, the call was not recognised as a selector call at all,
   * and a computed `discover-element-access` hook stayed out of `PACK_HOOKS`
   * while the suite passed 42/42.
   *
   * That is the round-2 defect in a new coat — the ATTRIBUTE name was split
   * there, the METHOD name here — so the answer is the same one that ended it
   * for the selector: resolve the name instead of pattern-matching the syntax,
   * and admit it out loud when it cannot be resolved.
   *
   *   - property access / identifier -> the name.
   *   - element access -> `literalOf` the subscript, so `page["locator"]` and
   *     `page["loc" + "ator"]` are both simply `locator`.
   *   - a subscript that does not resolve -> `null`, which is LOUD: the call
   *     could be `locator` and this file cannot say it is not.
   *   - an inline function expression -> not a named API. Its body is walked
   *     like any other code, so a selector inside it is read normally.
   */
  function calleeName(callee: ts.Expression): CalleeRead {
    if (ts.isParenthesizedExpression(callee)) return calleeName(callee.expression);
    if (ts.isIdentifier(callee)) return { name: callee.text, argOffset: 0 };
    if (ts.isElementAccessExpression(callee)) {
      const v = literalOf(callee.argumentExpression);
      return v === null ? null : { name: v, argOffset: 0 };
    }
    if (ts.isPropertyAccessExpression(callee)) {
      const prop = callee.name.text;
      if (prop === "call" || prop === "apply" || prop === "bind") {
        // Round 5, after CERT-593. `page.locator.call(page, sel)` runs a REAL
        // `locator`, and reading the final property name records `call` — so
        // the selector argument was never resolved and its computed hook was
        // omitted in silence. The fifth arm of the same defect.
        //
        // Normalising beats refusing, because refusing every `.bind` would red
        // `consent.spec.ts`, which legitimately writes
        // `window.localStorage.setItem.bind(...)`. So the TARGET is read first,
        // and only a target that really is a selector API is treated specially.
        const inner = calleeName(callee.expression);
        if (inner === null) return null;
        if (!(inner.name in SELECTOR_ARG)) {
          // `setItem.bind` and friends: not a selector call, nothing to check.
          return { name: "", argOffset: 0 };
        }
        // `f.call(thisArg, …)` pushes every real argument one slot right.
        if (prop === "call") return { name: inner.name, argOffset: inner.argOffset + 1 };
        // `.apply` hides the arguments inside an array and `.bind` defers the
        // call to a site this function is not looking at. Both are LOUD: the
        // pack has no reason to write either, and guessing is what lost four
        // rounds.
        return null;
      }
      return { name: prop, argOffset: 0 };
    }
    if (ts.isArrowFunction(callee) || ts.isFunctionExpression(callee)) {
      return { name: "", argOffset: 0 };
    }
    // A conditional, an awaited value, the result of another call: any of these
    // can evaluate to a selector method, and none of them can be read here.
    return null;
  }

  function walk(n: ts.Node): void {
    if (ts.isCallExpression(n)) {
      const callee = n.expression;
      const resolvedName = calleeName(callee);
      if (resolvedName === null) {
        unresolved.push(
          `<unreadable callee>(${callee.getText().replace(/\s+/g, " ").slice(0, 80)})`
        );
      }
      const name = resolvedName?.name ?? "";
      const argOffset = resolvedName?.argOffset ?? 0;
      if (name) calledNames.add(name);
      const idx = SELECTOR_ARG[name] === undefined ? undefined : SELECTOR_ARG[name] + argOffset;
      if (idx !== undefined && n.arguments.length > idx) {
        const arg = n.arguments[idx];
        const value = literalOf(arg);
        if (value === null) {
          unresolved.push(`${name}(${arg.getText().replace(/\s+/g, " ").slice(0, 80)})`);
        } else {
          // `getByTestId` is given the bare name; normalise it to the attribute
          // form so one extraction reads both spellings.
          selectors.push(name === "getByTestId" ? `data-testid="${value}"` : value);
        }
      }
    }
    // Over-covering extraction: ANY string literal mentioning the attribute is
    // read, wherever it sits. This is the safe direction — it cannot hide a
    // hook, it can only demand one that turns out to be prose — and it is what
    // catches a selector handed straight to a helper without a constant.
    if (
      (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) &&
      n.text.includes("data-testid")
    ) {
      selectors.push(n.text);
    }
    ts.forEachChild(n, walk);
  }
  walk(sf);

  return { file, selectors: [...selectors, ...constValues], unresolved, calledNames };
}

/** The pack's hook set, read out of a resolution. Shared so the attacks below
 *  exercise the same extraction PACK_HOOKS is built from, not a copy of it. */
function hooksOf(resolutions: Resolution[]): string[] {
  return [
    ...new Set(
      resolutions
        .flatMap((r) => r.selectors)
        .flatMap((s) => [...s.matchAll(/data-testid="([^"]+)"/g)].map((m) => m[1]))
        .filter((id) => id.startsWith("discover-"))
    ),
  ].sort();
}

const RESOLUTIONS: Resolution[] = fs
  .readdirSync(SPEC_DIR)
  .filter((f) => f.endsWith(".spec.ts"))
  .sort()
  .map((f) => resolveSpec(f, fs.readFileSync(path.join(SPEC_DIR, f), "utf8")));

/**
 * The specs that reach a Discover hook at all — the ones this suite answers for.
 *
 * Deliberately decided on the RAW text, which is the broader reading: a file is
 * held to the strict resolvability rule below if the word appears anywhere in
 * it, including a comment. Over-inclusion costs nothing here and under-inclusion
 * would be the hole.
 */
const DISCOVER_SPECS = RESOLUTIONS.filter((r) =>
  fs.readFileSync(path.join(SPEC_DIR, r.file), "utf8").includes("discover-")
);

const PACK_HOOKS: string[] = hooksOf(RESOLUTIONS);

/**
 * The hooks this file asserts. Every entry is checked below — in the DOM where
 * the state is reachable by rendering, and at the source level where it is not,
 * with the measured reason given at that test.
 */
const GUARDED_HOOKS: string[] = [
  "discover-card",
  "discover-empty-state",
  "discover-feed-error",
  "discover-feed-unavailable",
  "discover-skeleton",
];

/**
 * The resolver is ATTACKED here, not described.
 *
 * Three certs on one anchor (CERT-582, CERT-584, CERT-587) all found the same
 * shape: the guard's rationale was written in a comment and the comment was
 * true of the code the author was picturing. What closes that is running the
 * attack. Each row below is a spec source this file must handle in one of
 * exactly two ways — resolve it to a concrete string, or fail LOUDLY — and the
 * row says which, so a case that starts passing for a new reason is a red.
 *
 * `resolveSpec` here is the same function the real specs go through, and
 * `hooksOf` is the same extraction `PACK_HOOKS` is built from.
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
    name: "CERT-587: a `let` selector widened by compound assignment",
    src: `let SELECTOR = '[data-testid="discover-card"]';
SELECTOR += ', [data-' + 'testid="discover-reassigned"]';
page.locator(SELECTOR);`,
    loud: true,
  },
  {
    name: "CERT-587 variant: a `var` selector rewritten inside a helper",
    src: `var SELECTOR = '[data-testid="discover-card"]';
function widen() { SELECTOR = '[data-' + 'testid="discover-widened"]'; }
page.locator(SELECTOR);`,
    loud: true,
  },
  {
    name: "clause 2: a top-level `let`, even one nothing in this file writes",
    // Isolates the const rule from the write census. A `let` is a mutable
    // binding whether or not THIS file happens to move it — the next commit to
    // the spec can, and the resolver would go on quoting the initializer. The
    // conservative answer is the only sound one a parser can give.
    src: `let SELECTOR = '[data-testid="discover-card"]';
page.locator(SELECTOR);`,
    loud: true,
  },
  {
    name: "clause 1: a parameter shadowing a module constant",
    src: `const SELECTOR = '[data-testid="discover-card"]';
async function probe(page, SELECTOR) { await page.locator(SELECTOR); }`,
    loud: true,
  },
  {
    name: "clause 1: a nested `let` of the same name",
    src: `const SELECTOR = '[data-testid="discover-card"]';
function probe(page) { let SELECTOR = buildOther(); return page.locator(SELECTOR); }`,
    loud: true,
  },
  {
    name: "clause 3 (mechanism): a write to a name declared `const`",
    // Not valid at runtime — you cannot assign to a `const`, so clause 2 would
    // already have caught every legal form of this. It is pinned anyway: clause
    // 3 exists so that relaxing clause 2 to admit `let` for convenience cannot
    // silently restore the stale-initializer read CERT-587 found, and a clause
    // nothing tests is a clause the next edit deletes.
    src: `const SELECTOR = '[data-testid="discover-card"]';
[SELECTOR] = pickSelectors();
page.locator(SELECTOR);`,
    loud: true,
  },
  {
    name: "CERT-590: a selector reached through `page[\"locator\"](…)`",
    // The method name written as a subscript. Round 3 read the callee as syntax
    // and produced no name at all, so the call was never recognised as a
    // selector call — the hook was not missed, it was never looked for.
    src: `const SELECTOR = '[data-testid="discover-element-access"]';
page["locator"](SELECTOR);`,
    loud: false,
    hooks: ["discover-element-access"],
  },
  {
    name: "a subscripted method name assembled from parts is SUPPORTED",
    src: `const SELECTOR = '[data-testid="discover-subscript-split"]';
page["loc" + "ator"](SELECTOR);`,
    loud: false,
    hooks: ["discover-subscript-split"],
  },
  {
    name: "CERT-593: a selector reached through `page.locator.call(page, …)`",
    // The fifth arm. Reading the final property name records `call`, so the
    // selector argument was never resolved and its computed hook was omitted in
    // silence — while the browser ran a real `locator`.
    src: `const SELECTOR = "[data-" + 'testid="discover-call-indirect"]';
page.locator.call(page, SELECTOR);`,
    loud: false,
    hooks: ["discover-call-indirect"],
  },
  {
    name: "`.apply` hides its arguments in an array and fails loudly",
    src: `const SELECTOR = '[data-testid="discover-apply-indirect"]';
page.locator.apply(page, [SELECTOR]);`,
    loud: true,
  },
  {
    name: "a bound selector method fails loudly at the bind",
    // `.bind` defers the call to a site this function is not looking at, so the
    // honest moment to refuse is where the binding is made.
    src: `const loc = page.locator.bind(page);
loc('[data-testid="discover-bound"]');`,
    loud: true,
  },
  {
    name: "`.bind` on a method that is NOT a selector API is left alone",
    // `consent.spec.ts` really writes this. Refusing every `.bind` would red a
    // spec doing nothing wrong, which is why the TARGET is read first.
    src: `const real = window.localStorage.setItem.bind(window.localStorage);
page.locator('[data-testid="discover-card"]');`,
    loud: false,
    hooks: ["discover-card"],
  },
  {
    name: "a subscripted method name this file cannot compute fails loudly",
    // It could be `locator`. Refusing to guess is the whole contract.
    src: `const SELECTOR = '[data-testid="discover-unknown-api"]';
page[pickApi()](SELECTOR);`,
    loud: true,
  },
  {
    name: "a callee chosen at runtime fails loudly",
    src: `const SELECTOR = '[data-testid="discover-conditional-api"]';
(useCss ? page.locator : page.$)(SELECTOR);`,
    loud: true,
  },
  {
    name: "an inline IIFE is not an unreadable API — and its body is still read",
    // `tournament-inventory.spec.ts` really does call an arrow inline. Treating
    // that as an unreadable callee would red a spec doing nothing wrong, and
    // the selector inside it must still be extracted.
    src: `const SELECTOR = '[data-testid="discover-inside-iife"]';
(() => { page.locator(SELECTOR); })();`,
    loud: false,
    hooks: ["discover-inside-iife"],
  },
  {
    name: "a selector built by a call fails loudly",
    src: `page.locator(buildSelector("discover-runtime"));`,
    loud: true,
  },
  {
    name: "a resolution cycle is a failure, not a hang",
    src: `const A = B;
const B = A;
page.locator(A);`,
    loud: true,
  },
  {
    name: "CERT-584's split attribute name is SUPPORTED, not banned",
    src: `const SELECTOR = "[data-" + 'testid="discover-split"]';
page.locator(SELECTOR);`,
    loud: false,
    hooks: ["discover-split"],
  },
  {
    name: "CERT-582's computed hook name is SUPPORTED",
    src: `const HOOK = "discover-" + "computed";
page.locator(\`[data-testid="\${HOOK}"]\`);`,
    loud: false,
    hooks: ["discover-computed"],
  },
  {
    name: "getByTestId's bare name is normalised, not forbidden",
    src: `const HOOK = "discover-bare";
page.getByTestId(HOOK);`,
    loud: false,
    hooks: ["discover-bare"],
  },
  {
    name: "the control's control: an ordinary spec resolves clean",
    src: `const CARD = '[data-testid="discover-card"]';
test("cards render", async ({ page }) => { await page.locator(CARD).first(); });`,
    loud: false,
    hooks: ["discover-card"],
  },
];

describe("the resolver fails closed — attacked, not asserted", () => {
  test.each(RESOLVER_ATTACKS.map((a) => [a.name, a] as const))("%s", (_name, attack) => {
    const r = resolveSpec("attack.spec.ts", attack.src);
    if (attack.loud) {
      // The whole contract: a selector this file cannot compute must be
      // reported, never guessed at from a stale or shadowed binding.
      expect(`unresolved: ${r.unresolved.length}`).not.toBe("unresolved: 0");
    } else {
      expect(`${JSON.stringify(r.unresolved)}`).toBe("[]");
      expect(hooksOf([r])).toEqual(attack.hooks);
    }
  });

  test("the attack table exercises both outcomes", () => {
    // Without this the table degenerates the day someone drops the awkward half
    // — all-loud would pass a resolver that resolves nothing, all-clean a
    // resolver that never fails.
    expect(RESOLVER_ATTACKS.some((a) => a.loud)).toBe(true);
    expect(RESOLVER_ATTACKS.some((a) => !a.loud)).toBe(true);
  });
});

describe("the guarded set still covers the pack", () => {
  test("the pack selects hooks at all — the extraction is not silently empty", () => {
    // Without this the whole describe passes vacuously the day the spec
    // directory moves, which is precisely when the tripwire is needed.
    expect(RESOLUTIONS.length).toBeGreaterThan(0);
    expect(PACK_HOOKS.length).toBeGreaterThan(0);
  });

  test("every selector the Discover specs build is one this file can resolve", () => {
    // The fail-closed joint, and the whole answer to CERT-584.
    //
    // A selector assembled at runtime — from a helper, a variable the parser
    // cannot follow, a template with a computed part — is a selector Playwright
    // honours and this file cannot read. Rather than trying to enumerate the
    // spellings that could hide one (which is what round 1 did, and lost), any
    // selector argument that does not resolve to a concrete string fails here.
    //
    // Scoped to the specs that reach Discover: calibration, daily-challenge and
    // search-answer legitimately interpolate over their own hook lists, and a
    // guard that taxes files it does not answer for is a guard someone deletes.
    expect(DISCOVER_SPECS.length).toBeGreaterThan(0);
    for (const r of DISCOVER_SPECS) {
      expect(`${r.file}: ${JSON.stringify(r.unresolved)}`).toBe(`${r.file}: []`);
    }
  });

  test("the resolver still understands every selector API the Discover specs call", () => {
    // Anti-vacuity for the check above, and the reason it is not enough to
    // assert "some selectors were found". Battery M16 deleted `locator` from
    // SELECTOR_ARG: the resolvability test stayed green because the resolver
    // had simply stopped looking at `locator()` calls, while module constants
    // and the literal scan kept the selector list non-empty. A check that can
    // be unwired without anything going red is decoration.
    for (const r of DISCOVER_SPECS) {
      const used = REQUIRED_SELECTOR_APIS.filter((api) => r.calledNames.has(api));
      const unknown = used.filter((api) => !(api in SELECTOR_ARG));
      expect(`${r.file}: ${JSON.stringify(unknown)}`).toBe(`${r.file}: []`);
      expect(`${r.file}: ${r.selectors.length > 0}`).toBe(`${r.file}: true`);
    }
  });

  test.each(PACK_HOOKS)("%s is guarded by this suite", (hook) => {
    expect(GUARDED_HOOKS).toContain(hook);
  });

  test("nothing is guarded that the pack does not select", () => {
    // The other direction: a hook retired from the rail should not keep taxing
    // this file. Equality both ways makes the two lists one list.
    expect(GUARDED_HOOKS).toEqual(PACK_HOOKS);
  });
});

describe("Discover empty state carries a stable, named audit hook", () => {
  test("renders data-testid and a machine-readable state name", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={0} onRefresh={noop} />);
    expect(html).toContain('data-testid="discover-empty-state"');
    // The NAME is data, not scraped prose — the audit records this attribute
    // rather than the visible copy, so a reword cannot invalidate the evidence.
    expect(html).toContain('data-empty-state-name="no-markets"');
  });

  test("distinguishes an exhausted feed from a feed that never had anything", () => {
    const exhausted = renderToStaticMarkup(<EndOfFeedCard count={137} onRefresh={noop} />);
    expect(exhausted).toContain('data-empty-state-name="end-of-feed"');
    expect(exhausted).not.toContain('data-empty-state-name="no-markets"');
  });

  test("the hook is unique — one element, not a class sprayed across children", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={5} onRefresh={noop} />);
    expect(occurrences(html, 'data-testid="discover-empty-state"')).toBe(1);
  });

  test("keeps the accessible semantics alongside the test hook", () => {
    const html = renderToStaticMarkup(<EndOfFeedCard count={5} onRefresh={noop} />);
    // A status role announces the state to assistive tech; the hook is additive.
    expect(html).toContain('role="status"');
    expect(html).toContain("all caught up");
    expect(html).toContain("Refresh feed");
  });
});

describe("the loading skeleton is never mistaken for content", () => {
  test("carries its own hook and NOT the card hook", () => {
    const html = renderToStaticMarkup(<DiscoverSkeletonGrid />);
    expect(html).toContain('data-testid="discover-skeleton"');
    // This is the entire point of the change: the skeleton must be
    // distinguishable from a rendered card by the audit's selector.
    expect(html).not.toContain('data-testid="discover-card"');
    expect(html).not.toContain('data-testid="discover-empty-state"');
  });

  test("is still hidden from assistive tech", () => {
    const html = renderToStaticMarkup(<DiscoverSkeletonGrid />);
    expect(html).toContain('aria-hidden="true"');
  });

  test("still shares the layout class with real cards — which is why the hook was needed", () => {
    // Documents the collision rather than asserting it away: `break-inside-avoid`
    // is a masonry primitive both states legitimately use. The selector was
    // wrong; the styling is not.
    const html = renderToStaticMarkup(<DiscoverSkeletonGrid count={2} />);
    expect(html).toContain("break-inside-avoid");
  });
});

describe("the unavailable feed is a named state, not a blank page", () => {
  // UX-P228: the hook the derived list above caught missing. `unavailable` is
  // the component's DEFAULT reason, so this is the branch every pre-#1909 call
  // site lands on — the most-reached of the three, and the one that was
  // guarded by nothing.

  test("the default reason renders the hook the pack's ERROR_STATE selector names", () => {
    const html = renderToStaticMarkup(<FeedUnavailableNotice onRetry={noop} />);
    expect(html).toContain('data-testid="discover-feed-unavailable"');
    expect(html).toContain('data-reason="unavailable"');
  });

  test.each([
    ["unavailable", "discover-feed-unavailable"],
    ["rate_limited", "discover-feed-error"],
    ["error", "discover-feed-error"],
  ] as const)("reason %s carries hook %s", (reason, hook) => {
    // Three reasons, two hooks, and which maps to which is the contract the
    // rail binds to. A reason silently re-pointed at the other hook keeps this
    // file green under a per-hook existence check; it does not survive here.
    const html = renderToStaticMarkup(
      <FeedUnavailableNotice onRetry={noop} reason={reason} />
    );
    expect(html).toContain(`data-testid="${hook}"`);
  });

  test("is never mistaken for a legitimate empty feed or a skeleton", () => {
    // The same confusion the skeleton tests above exist for: an unavailable
    // feed read as "you're all caught up" is a broken deploy reported as a
    // quiet day.
    for (const reason of ["unavailable", "rate_limited", "error"] as const) {
      const html = renderToStaticMarkup(
        <FeedUnavailableNotice onRetry={noop} reason={reason} />
      );
      expect(html).not.toContain('data-testid="discover-empty-state"');
      expect(html).not.toContain('data-testid="discover-skeleton"');
      expect(html).toContain('role="alert"');
    }
  });

  test("the hook is unique — one element, not sprayed across children", () => {
    const html = renderToStaticMarkup(<FeedUnavailableNotice onRetry={noop} />);
    expect(occurrences(html, 'data-testid="discover-feed-unavailable"')).toBe(1);
  });
});

describe("the Discover page itself renders the hooks the audit selects", () => {
  /**
   * UX-P228: this block used to say a rendering test "would prove less and
   * break more", and asserted the page at the source level on that basis. Both
   * halves were measured and neither held. `useSWR` is a MODULE boundary, so a
   * mock settles it synchronously and the page renders — it is a `useState`
   * cleared in a `useEffect` that defeats a static render, and this page has
   * none on the path to these hooks. And a source grep cannot tell DECLARED
   * from REACHES-THE-DOM, which is the only thing the rail cares about.
   *
   * Every mock below replaces a MODULE boundary and lives inside
   * `isolateModules`, so none of them leaks into the component renders above
   * and none stands in for page-internal state: `isLoading` and `error` are
   * read from SWR, which is the boundary being mocked.
   */
  function domIds(swr: unknown): string[] {
    let html = "";
    jest.isolateModules(() => {
      // Keyed, because the page calls `useSWR` TWICE. Answering both with the
      // feed state made `resolutionsData.resolutions` undefined and the loaded
      // state un-renderable — which silently cost the gap assertion below its
      // most important case until a mutant found it.
      jest.doMock("swr", () => ({
        __esModule: true,
        default: (key: string) =>
          key === "discover-resolutions"
            ? { data: { resolutions: [] }, error: undefined, isLoading: false, mutate: noop }
            : swr,
      }));
      jest.doMock("next/navigation", () => ({
        useRouter: () => ({ push: noop, replace: noop, prefetch: noop }),
        useSearchParams: () => new URLSearchParams(),
        usePathname: () => "/discover",
      }));
      jest.doMock("@/components/Analytics", () => ({
        useAnalyticsContext: () => ({ track: noop }),
      }));
      jest.doMock("@/hooks", () => ({
        useEngagementTime: () => undefined,
        usePageTracking: () => undefined,
        useScrollDepth: () => undefined,
      }));
      jest.doMock("@/components/AuthProvider", () => ({
        useAuthContext: () => ({
          user: null,
          isLoading: false,
          isAuthenticated: false,
          isAuthAvailable: false,
          authError: null,
          signInWithGoogle: async () => {},
          signInWithApple: async () => {},
          signOut: async () => {},
          getToken: async () => null,
        }),
      }));
      // UX-P223-3: `isolateModules` gives the subject a FRESH `react`, so
      // `react-dom/server` must be required INSIDE the registry that will
      // render — the module-scope import above dies on the page's first hook.
      const { renderToStaticMarkup: render } = require("react-dom/server");
      const R = require("react");
      const Page = require("../../app/discover/page").default;
      html = render(R.createElement(Page));
    });
    return [...new Set([...html.matchAll(/data-testid="([^"]+)"/g)].map((m) => m[1]))];
  }

  const swrState = (over: Record<string, unknown>) => ({
    data: undefined,
    error: undefined,
    isLoading: false,
    mutate: noop,
    ...over,
  });

  test("a loading feed reaches the skeleton hook and NOTHING that reads as content", () => {
    const ids = domIds(swrState({ isLoading: true }));
    expect(ids).toContain("discover-skeleton");
    expect(ids).not.toContain("discover-card");
    expect(ids).not.toContain("discover-empty-state");
  });

  test("a failed load reaches the error hook, and never the empty-state hook", () => {
    // The thing the source-level check could not see: that this branch is
    // actually reached, not merely present in the file.
    const ids = domIds(swrState({ error: new Error("boom") }));
    expect(ids).toContain("discover-feed-error");
    expect(ids).not.toContain("discover-empty-state");
    expect(ids).not.toContain("discover-skeleton");
  });

  test("a 429 is still an error state, not an empty one", () => {
    const ids = domIds(swrState({ error: Object.assign(new Error("rl"), { status: 429 }) }));
    expect(ids).toContain("discover-feed-error");
    expect(ids).not.toContain("discover-empty-state");
  });

  test("an empty feed reaches the named empty state, not an error and not a skeleton", () => {
    const ids = domIds(swrState({ data: { items: [] } }));
    expect(ids).toContain("discover-empty-state");
    expect(ids).not.toContain("discover-feed-error");
    expect(ids).not.toContain("discover-skeleton");
  });

  test("no page state reaches discover-feed-unavailable — it is component-level only", () => {
    // STATED GAP, measured rather than assumed. `feedFailureReason` is only
    // ever `rate_limited` or `error`, so the page's error branch cannot emit
    // this hook; the one site that can is gated on the `feedUnavailable`
    // useState, which is set only inside `useEffect`s that a static render
    // never runs. That is why the coverage for it above is a component render.
    // If the page ever grows a statically-reachable path to it, this fails and
    // the DOM assertion should move up here.
    //
    // The fourth state is load-bearing and was added because a mutant survived
    // without it: deleting the `feedUnavailable &&` guard makes the hook fall
    // out of the EMPTY branch, which none of the first three states reaches.
    // "No page state" has to mean every state, or it is an aggregate claim
    // dressed as an exhaustive one.
    for (const s of [
      swrState({ isLoading: true }),
      swrState({ error: new Error("boom") }),
      swrState({ error: Object.assign(new Error("rl"), { status: 429 }) }),
      swrState({ data: { items: [] } }),
    ]) {
      expect(domIds(s)).not.toContain("discover-feed-unavailable");
    }
  });

  const source: string = jest.requireActual("fs").readFileSync(
    require("path").join(__dirname, "..", "..", "app", "discover", "page.tsx"),
    "utf8"
  );

  test("the feed item wrapper carries the card hook", () => {
    // STATED GAP: still source-level. Reaching `discover-card` in the DOM needs
    // a captured `GET /api/feed` payload — a hand-written one silently
    // re-answers "does this render" as "no" (UX-P226-8) — and that fixture is
    // the follow-up slice, not this one.
    expect(source).toContain('data-testid="discover-card"');
  });

  test("the load-failure branch has its own hook and is not an empty state", () => {
    // UX-P087 (#1909): the branch's MARKUP moved into
    // `components/discover/FeedUnavailableNotice`, so the hook is asserted where
    // it now lives. What this test protects is unchanged and is the reason it
    // exists: the hook survives, and a load failure is never reachable through
    // the empty-state hook — an error is not a legitimate empty feed, and
    // conflating them is how a broken deploy reads as a quiet day.
    const notice: string = jest.requireActual("fs").readFileSync(
      require("path").join(
        __dirname, "..", "..", "components", "discover", "FeedUnavailableNotice.tsx",
      ),
      "utf8",
    );
    expect(notice).toContain('discover-feed-error');
    expect(notice).toContain('role="alert"');
    expect(notice).not.toContain("discover-empty-state");

    // And the page still routes its failure branch through that component
    // rather than growing a second, drifting copy of the markup.
    expect(source).toContain("<FeedUnavailableNotice");
    expect(source).not.toContain('data-testid="discover-feed-error"');
  });
});
