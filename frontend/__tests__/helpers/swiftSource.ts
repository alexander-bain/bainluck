/**
 * Swift source with its comments and string bodies removed, for guards that
 * scan the iOS target from jest.
 *
 * 🔴 WHY THIS EXISTS AT ALL. A source-scan guard that reads prose as code
 * reports the cure as the disease: a fix documents the defect by quoting it, so
 * `expect(src).not.toContain("homeProbability")` fails on the comment explaining
 * that `homeProbability` was removed. The inverse — a commented-out call
 * satisfying a `toContain` — is the same mistake pointed the other way, so
 * POSITIVE checks have to read the stripped text too.
 *
 * String bodies go with the comments because a Swift line may legitimately
 * contain `//` inside a URL literal, and a naive line-comment strip would delete
 * the rest of that line and quietly shorten the scan. The opening quote is kept
 * so that a scan can still see that a string was there.
 *
 * The parser is lifted verbatim from `__tests__/ios/duelPercentServedPair.test.ts`
 * (#2279), which still holds its own copy — it was last edited 2026-09-08 and
 * rewriting an active guard to save a duplicate is a merge conflict bought for
 * nothing. Whoever next touches that file should import this instead.
 */
export function swiftCode(src: string): string {
  return strip(src, false);
}

/**
 * The same, but keeping what is INSIDE the string literals.
 *
 * A guard asserting the SHAPE of a rendered sentence — that a percent is
 * preceded by an interpolated name, that a title is built away-first — is
 * asserting about string bodies, and `swiftCode` deletes exactly those. Only
 * the comments are the trap; the strings are the payload.
 *
 * Use this only for assertions whose subject is the literal text. A ban on an
 * identifier (`not.toContain("homeProbability")`) must still use `swiftCode`,
 * or it fails on the comment that documents the removal.
 */
export function swiftCodeKeepingStrings(src: string): string {
  return strip(src, true);
}

function strip(src: string, keepStrings: boolean): string {
  let out = "";
  let i = 0;
  let inString = false;
  let inLine = false;
  let blockDepth = 0;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (inLine) {
      if (c === "\n") {
        inLine = false;
        out += c;
      }
      i += 1;
    } else if (blockDepth > 0) {
      if (c === "/" && next === "*") {
        blockDepth += 1;
        i += 2;
      } else if (c === "*" && next === "/") {
        blockDepth -= 1;
        i += 2;
      } else {
        if (c === "\n") out += c;
        i += 1;
      }
    } else if (inString) {
      if (c === "\\") {
        if (keepStrings) out += src.slice(i, i + 2);
        i += 2;
      } else {
        if (c === '"') inString = false;
        if (keepStrings) out += c;
        i += 1;
      }
    } else if (c === "/" && next === "/") {
      inLine = true;
      i += 2;
    } else if (c === "/" && next === "*") {
      blockDepth = 1;
      i += 2;
    } else if (c === '"') {
      inString = true;
      out += c;
      i += 1;
    } else {
      out += c;
      i += 1;
    }
  }
  return out;
}

/**
 * The body of one Swift function, brace-matched from its declaration.
 *
 * Guards scope to the FUNCTION and not the file because a file-wide scan both
 * over- and under-reports: `SearchView.swift` reads `homeProbability` in places
 * that are none of this rule's business, and a ban asserted across the whole
 * file would be satisfied by moving the defect one function down.
 *
 * Returns `null` when the declaration is absent, so a caller can fail with
 * "the function this guard watches is gone" rather than silently passing on an
 * empty string — a renamed function must break its guard loudly.
 */
export function swiftFunctionBody(code: string, declaration: string): string | null {
  const start = code.indexOf(declaration);
  if (start === -1) return null;
  const open = code.indexOf("{", start);
  if (open === -1) return null;
  let depth = 0;
  for (let i = open; i < code.length; i += 1) {
    if (code[i] === "{") depth += 1;
    else if (code[i] === "}") {
      depth -= 1;
      if (depth === 0) return code.slice(open, i + 1);
    }
  }
  return null;
}
