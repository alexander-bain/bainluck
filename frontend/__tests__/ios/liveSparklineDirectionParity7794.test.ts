/**
 * #7794 — the app's sparkline decides its colour from the string it publishes,
 * or CI says so.
 *
 * THE BUG. `LiveSparklineChart` painted the line red whenever
 * `last.probability < first.probability` on the RAW numbers, with no dead band,
 * while its own `accessibilityLabel` forty lines below printed a rounded percent.
 * So VoiceOver could be told "Last 10 minutes: 99% to 99%" beside a line painted
 * the colour for *fell*. ux measured it on production over 34 live events: of 781
 * ten-minute windows, 467 (60%) render both ends as the same whole percent, and
 * 66 of those were painted RED. Web carried the identical rule and fixed it in
 * PR #7793 (#5734); this is the app's half.
 *
 * WHY THIS GUARD LIVES IN JEST. CI compiles no Swift (#4302, notice 10's iOS
 * clause), so `LiveSparklineDirectionTests` — which owns the BEHAVIOUR — is
 * reachable only from a macOS runner. This reads the Swift SOURCE and pins the
 * arrangement that behaviour depends on, because a jest file is a deploy gate and
 * a Swift file is not.
 *
 * WHY IT DOES NOT READ `sparklineDirection` OUT OF THE WEB COMPONENT. That
 * function is in PR #7793, which is not on master yet; a guard that requires it
 * would redden this branch for a change in somebody else's tree. Everything
 * asserted about the web side here is true BEFORE and AFTER #7793 lands — the
 * label has keyed on `renderedPercent` since the component shipped, and #7793
 * keeps both existing hexes. When #7793 is on master, the flat-grey literal can
 * be pinned on both sides too; the `STROKE_FLAT` assertion below is written to
 * be extended, not replaced.
 *
 * EVERY EXTRACTOR HERE PINS A COUNT. A brace- or quote-matching scan that finds
 * nothing returns an empty result, and `expect([]).toEqual([])` is green — so a
 * guard built on extraction agrees with anything unless the extraction itself is
 * asserted to have happened.
 */

import { readFileSync } from "fs";
import { join } from "path";

const REPO = join(__dirname, "../../..");
const IOS = join(REPO, "ios/Bain Luck/Bain Luck/Components/LiveSparklineChart.swift");
const IOS_PERCENT = join(REPO, "ios/Bain Luck/Bain Luck/Utilities/RenderedPercent.swift");
const WEB = join(REPO, "frontend/components/event/LiveSparkline.tsx");
const WEB_PERCENT = join(REPO, "frontend/lib/renderedPercent.ts");
const GLOBALS = join(REPO, "frontend/app/globals.css");

function read(file: string): string {
  try {
    return readFileSync(file, "utf8");
  } catch (err) {
    throw new Error(
      `#7794 sparkline parity gate could not read ${file}: ${String(err)}. ` +
        `If the file moved, update this guard — do not delete the check.`,
    );
  }
}

/**
 * Both files explain the bug in their PROSE using the very tokens this guard
 * scans for — `* 100`, `#EF4444`, `probability` — so a raw scan would read each
 * header's explanation as the code it describes.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/\/?.*$/gm, "");
}

/** The string literal assigned to a Swift `static let <name>`. */
function swiftStringLet(source: string, name: string): string {
  const at = source.indexOf(`static let ${name}`);
  if (at === -1) throw new Error(`\`static let ${name}\` not found in the Swift source`);
  // Anchor on the `=`, never on the declaration: a type annotation sits between
  // the name and the value, and an extractor that grabs the annotation returns
  // something plausible and wrong (the #7780 gate's own near-miss).
  const assign = source.indexOf("=", at);
  const open = source.indexOf('"', assign);
  const close = source.indexOf('"', open + 1);
  if (assign === -1 || open === -1 || close === -1) {
    throw new Error(`\`static let ${name}\` is not an assigned string literal`);
  }
  return source.slice(open + 1, close);
}

/** The brace-matched body of a Swift function, found by its signature prefix. */
function swiftFunctionBody(source: string, signature: string): string {
  const at = source.indexOf(signature);
  if (at === -1) throw new Error(`\`${signature}\` not found in the Swift source`);
  const open = source.indexOf("{", at);
  if (open === -1) throw new Error(`\`${signature}\` has no body`);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(open + 1, i);
    }
  }
  throw new Error(`\`${signature}\` body is unbalanced`);
}

const iosRaw = read(IOS);
const ios = stripComments(iosRaw);
const web = stripComments(read(WEB));

describe("#7794 — the app's sparkline colour is a function of its own label", () => {
  test("the extractors actually extracted something", () => {
    // The guard against the guard. Without this every `expect(...)` below can be
    // satisfied by a scan that found nothing.
    expect(ios.length).toBeGreaterThan(500);
    expect(web.length).toBeGreaterThan(500);
    expect(ios).toContain("struct LiveSparklineChart");
    expect(web).toContain("export default function LiveSparkline");
  });

  test("the app names all three stroke colours, and they are the web's", () => {
    const strokes = {
      up: swiftStringLet(ios, "strokeUp"),
      down: swiftStringLet(ios, "strokeDown"),
      flat: swiftStringLet(ios, "strokeFlat"),
    };
    // Count pinned: three declarations found, three distinct colours.
    expect(Object.keys(strokes)).toHaveLength(3);
    expect(new Set(Object.values(strokes)).size).toBe(3);
    expect(strokes).toEqual({ up: "#10B981", down: "#EF4444", flat: "#9CA3AF" });

    // The two the web already carries on master, and keeps through #7793.
    expect(web).toContain("#10B981");
    expect(web).toContain("#EF4444");
    // The flat grey is `--text-muted`, so the two surfaces draw the same grey
    // rather than two greys that happen to look alike.
    expect(read(GLOBALS)).toContain("--text-muted: #9CA3AF");
  });

  test("direction is decided on the PUBLISHED percent, not the raw probability", () => {
    const body = swiftFunctionBody(ios, "static func direction(from first: Double, to last: Double)");
    expect(body.length).toBeGreaterThan(40);
    // Both endpoints go through the published percent...
    expect(body.match(/publishedPercent/g) ?? []).toHaveLength(2);
    // ...and the raw comparison that WAS the bug is gone from it.
    expect(body).not.toMatch(/probability/);
    // The three outcomes are all still reachable — a fix that answered `.flat`
    // everywhere would satisfy every "stops painting red" assertion there is.
    expect(body).toContain(".up");
    expect(body).toContain(".down");
    expect(body).toContain(".flat");
  });

  test("the published percent is the shared contract, not a local `* 100`", () => {
    const body = swiftFunctionBody(ios, "static func publishedPercent(");
    expect(body).toContain("renderedPercent");
    expect(body).not.toContain("* 100");
    // The finiteness guard runs BEFORE the clamp: `max(0, .nan)` is 0 in Swift,
    // so the other order turns an unrenderable reading into a confident 0%.
    expect(body.indexOf("isFinite")).toBeGreaterThan(-1);
    expect(body.indexOf("isFinite")).toBeLessThan(body.indexOf("min(1, max(0"));

    // And the contract function it delegates to is the real one, in both runtimes.
    expect(read(IOS_PERCENT)).toContain("func renderedPercent");
    expect(read(WEB_PERCENT)).toContain("export function renderedPercent");
  });

  test("the label rounds the same way the colour does — no second rule", () => {
    const body = swiftFunctionBody(ios, "static func accessibilityLabel(");
    expect(body).toContain("publishedPercent");
    // #3867: `p * 100` is half-up on the double the wire value BECAME, so 0.565
    // and 0.585 round opposite ways. This label used to do exactly that.
    expect(body).not.toContain("* 100");

    // The web arm has keyed its aria-label on the same contract since it shipped.
    expect(web).toContain("renderedPercent(firstValue)");
    expect(web).toContain("renderedPercent(lastValue)");
  });

  test("the old raw-probability rule is gone from the whole component", () => {
    // Not scoped to one function: the defect was a one-line expression and could
    // come back at the call site just as easily as inside the rule.
    expect(ios).not.toContain("isRising");
    expect(ios).not.toMatch(/last\.probability\s*>=?\s*first\.probability/);
  });
});
