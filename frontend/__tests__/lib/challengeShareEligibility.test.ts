// L2-235 — binds the two owned share handlers to the evaluated predicate.
//
// The unit tests next door prove `shareContent` behaves. They cannot prove the
// PAGES call it: `/daily` and `/challenge/[id]` are client pages whose handlers
// only run from a click, and this suite has no DOM renderer (component tests
// here are SSR `renderToStaticMarkup`). So the binding is asserted at the
// source, which is also the only form that fails on the exact regression —
// somebody re-deriving the method from `navigator` after the branch ran.
//
// Comments are stripped before matching. L2-233 shipped two guards that failed
// on their own first run because each matched the prose describing what it
// forbids; the pages now carry comments that name `navigator` on purpose.

import { readFileSync } from "fs";
import { join } from "path";

const FRONTEND = join(__dirname, "..", "..");

// The TS2774 shape: a bare `navigator.share` function reference used as a
// condition. Both forms the two pages shipped.
const TERNARY_ON_FUNCTION_REF = /navigator\s*\.\s*share\s*\?/;
const IF_ON_FUNCTION_REF = /if\s*\(\s*navigator\s*\.\s*share\s*\)/;

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .map((line) => line.replace(/\/\/.*$/, ""))
    .join("\n");
}

/** The handler body, brace-matched from `marker` so sibling code can't leak in. */
function handlerBody(source: string, marker: string): string {
  const start = source.indexOf(marker);
  if (start === -1) throw new Error(`marker not found: ${marker}`);

  const open = source.indexOf("{", start);
  if (open === -1) throw new Error(`no body for: ${marker}`);

  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(open, i + 1);
    }
  }
  throw new Error(`unbalanced body for: ${marker}`);
}

const SURFACES = [
  {
    name: "shared challenge",
    file: "app/challenge/[id]/page.tsx",
    marker: "async function shareChallenge()",
    analytics: 'track("friend_challenge_share"',
  },
  {
    name: "daily",
    file: "app/daily/page.tsx",
    marker: "const shareSummary = useCallback(",
    analytics: 'trackEvent("share"',
  },
];

describe("the detector actually detects", () => {
  // A guard that cannot fail on the old code is not a guard. This is the code
  // that shipped, verbatim.
  const OLD = `
    try {
      if (navigator.share) {
        await navigator.share({ title, text, url: shareUrl });
      }
      track("friend_challenge_share", {
        method: navigator.share ? "native" : "clipboard",
      });
    } catch {}
  `;

  it("flags both function-reference forms", () => {
    expect(TERNARY_ON_FUNCTION_REF.test(OLD)).toBe(true);
    expect(IF_ON_FUNCTION_REF.test(OLD)).toBe(true);
  });

  it("does not flag the evaluated form", () => {
    const fixed = `const method = await shareContent(attempt, navigator); if (!method) return;`;
    expect(TERNARY_ON_FUNCTION_REF.test(fixed)).toBe(false);
    expect(IF_ON_FUNCTION_REF.test(fixed)).toBe(false);
  });

  it("strips the prose that names navigator", () => {
    expect(stripComments("// method: navigator.share ? a : b\nconst x = 1;")).not.toMatch(
      TERNARY_ON_FUNCTION_REF
    );
  });
});

describe.each(SURFACES)("$name share handler", ({ file, marker, analytics }) => {
  const source = stripComments(readFileSync(join(FRONTEND, file), "utf8"));
  const body = handlerBody(source, marker);

  it("imports the shared predicate", () => {
    expect(source).toContain('from "@/lib/share"');
    expect(source).toMatch(/import\s*\{[^}]*\bshareContent\b[^}]*\}/);
  });

  it("never conditions on the bare navigator.share function reference", () => {
    expect(body).not.toMatch(TERNARY_ON_FUNCTION_REF);
    expect(body).not.toMatch(IF_ON_FUNCTION_REF);
  });

  it("derives the method from the share that actually ran", () => {
    expect(body).toMatch(/const\s+method\s*=\s*await\s+shareContent\(/);
  });

  it("reports nothing when no method carried the share", () => {
    expect(body).toMatch(/if\s*\(\s*!method\s*\)\s*return;/);
  });

  it("guards the analytics call behind that check", () => {
    const guard = body.search(/if\s*\(\s*!method\s*\)\s*return;/);
    const event = body.indexOf(analytics);

    expect(guard).toBeGreaterThan(-1);
    expect(event).toBeGreaterThan(guard);
  });

  it("passes the recorded method rather than re-deriving a label", () => {
    expect(body).toMatch(/\bmethod,/);
    expect(body).not.toMatch(/method:\s*["']native["']/);
    expect(body).not.toMatch(/method:\s*["']clipboard["']/);
  });
});
