/**
 * #4645 — the ladder footer's caption composes with the rung, it does not
 * prefix it.
 *
 * `HeatMapCardView`'s summary footer draws a fixed caption and then the rung
 * label beside it, and the reader reads the two as one line. The caption was
 * written for the DATE ladder it shipped with, where the label is a date and
 * the sentence closes:
 *
 *     Above 50% through  Before 2027          ← reads
 *
 * Every other ladder's label carries its OWN comparator, so the line stacked
 * two comparators on two unrelated quantities and stopped mid-sentence.
 * Photographed on the phone, iPhone 17, Discover at `--scroll 9000`,
 * 2026-09-09 22:48 PT (`artifacts-native-091/before-ladder-s9000.png`), on
 * "How high will US diesel prices get in 2026?":
 *
 *     Above 50% through  ≥$6.40  +6 more      ← does not
 *
 * Note the phone's symptom is NOT the web twin's. `compactThresholdLabel`
 * rewrites `"Above "` to `"≥"`, so the app never literally printed "above"
 * twice the way the web card did ("Above 50% through Above 67", #4645) — it
 * printed a word comparator and then a glyph comparator, which is the same
 * defect wearing a different face. A guard written against the literal
 * duplicated word would have passed on this file while the phone was broken,
 * so the rule below is about the CAPTION, not about the repetition.
 *
 * D102 keeps small grey type where it offers the reader value, and this line
 * has a real thing to say — the furthest rung the market still calls better
 * than even — so the fix is the grammar, not the deletion.
 *
 * Lives in jest because jest is a deploy gate here and the Swift test target is
 * not reachable from CI (standing notice 10), the same reason
 * `mapTitleSingleSource` and `teamShortNameSingleSource` do.
 */

import { existsSync, readFileSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const HEATMAP = join(IOS_ROOT, "Components/HeatMapCardView.swift");
const WEB_CARD = join(__dirname, "../../components/discover/FuturesCard.tsx");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/** The text between `source[open]` (a `{`) and its matching `}`. */
function braceBody(source: string, open: number): string {
  let depth = 0;
  for (let i = open; i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}" && --depth === 0) return source.slice(open + 1, i);
  }
  return source.slice(open + 1);
}

/**
 * The branch that draws a caption AND a rung label — found by shape rather than
 * by line number, so moving the footer does not silently stop guarding it.
 *
 * `if let <name> = <something> { … Text(<name>) … }`: a binding whose value is
 * handed straight to a `Text`, i.e. runtime words the caption will sit next to.
 */
function captionsDrawnBesideARungLabel(source: string): { binding: string; literals: string[] }[] {
  const found: { binding: string; literals: string[] }[] = [];
  const bind = /\bif\s+let\s+(\w+)\s*=\s*[^{]+\{/g;
  let m: RegExpExecArray | null;
  while ((m = bind.exec(source)) !== null) {
    const body = braceBody(source, bind.lastIndex - 1);
    if (!new RegExp(`\\bText\\(\\s*${m[1]}\\s*\\)`).test(body)) continue;
    const literals = [...body.matchAll(/\bText\(\s*"((?:[^"\\]|\\.)*)"\s*\)/g)].map((t) => t[1]);
    if (literals.length > 0) found.push({ binding: m[1], literals });
  }
  return found;
}

/**
 * A comparator the rung label already supplies. Words only — the caption is
 * prose, and `≥`/`<` belong to the label.
 *
 * "more likely than not" is deliberately NOT caught: it compares a probability
 * to even odds, which is the caption's whole subject, and it names no rung.
 * The banned shapes are the ones that read as a comparison to the NUMBER that
 * follows them.
 */
const COMPARATOR =
  /\b(above|below|over|under|at least|at most|no more than|no fewer than|greater than|less than|fewer than|up to|through)\b/i;

describe("#4645 — a ladder footer caption composes with its rung", () => {
  it("finds the view it is guarding", () => {
    expect(existsSync(HEATMAP)).toBe(true);
  });

  it("no longer prints the caption that stopped mid-sentence", () => {
    const text = stripComments(readFileSync(HEATMAP, "utf8"));
    expect(text).not.toContain("Above 50% through");
  });

  it("says the furthest better-than-even rung in words that close", () => {
    const text = stripComments(readFileSync(HEATMAP, "utf8"));
    expect(text).toContain('Text("More likely than not:")');
  });

  /**
   * The class, not the case. Whatever the caption becomes, a caption drawn
   * beside a runtime rung label may not carry its own comparator — the label
   * has one, and two in a row is what the reader could not parse.
   */
  it("lets no caption beside a rung label carry its own comparator", () => {
    const text = stripComments(readFileSync(HEATMAP, "utf8"));
    const offenders: string[] = [];
    for (const { binding, literals } of captionsDrawnBesideARungLabel(text)) {
      for (const literal of literals) {
        const hit = literal.match(COMPARATOR);
        if (hit) offenders.push(`"${literal}" (beside \`${binding}\`) — via "${hit[0]}"`);
      }
    }
    expect(offenders).toEqual([]);
  });

  /**
   * The reason that rule is load-bearing rather than a style preference: the
   * label really does arrive with a comparator already on it. If this mapping
   * is ever dropped the labels become bare `Above 79` strings — which is the
   * WEB card's symptom, and still a stutter — so either way the caption has to
   * stay comparator-free. Pinned so the premise is visible, not assumed.
   */
  it("CONTROL: the rung label still carries a comparator of its own", () => {
    const text = stripComments(readFileSync(HEATMAP, "utf8"));
    expect(text).toContain('.replacingOccurrences(of: "Above ", with: "\\u{2265}")');
    expect(text).toContain('.replacingOccurrences(of: "Below ", with: "<")');
  });

  /**
   * The finder is not vacuous. A footer refactor that renamed the binding or
   * moved the caption out of the `if let` would otherwise pass every assertion
   * above by inspecting nothing at all.
   */
  it("CONTROL: the shape-based finder actually found the footer", () => {
    const text = stripComments(readFileSync(HEATMAP, "utf8"));
    const found = captionsDrawnBesideARungLabel(text);
    expect(found.map((f) => f.binding)).toContain("threshold");
    expect(found.flatMap((f) => f.literals)).toContain("More likely than not:");
  });

  /**
   * Notice 35 — one card family everywhere. The web twin draws the same footer
   * from `FuturesCard.tsx`, and now that #4656 is on master both halves are
   * here, so this is a plain equality rather than a transitional pin: the two
   * clients say the same words, and whichever one is reworded next drags the
   * other with it or goes red.
   *
   * Read out of the markup rather than compared to a literal, so a rewording
   * that updates only this file's expectations cannot pass.
   */
  it("says exactly what the web twin says — one card family", () => {
    const web = readFileSync(WEB_CARD, "utf8");
    const webCaption = web.match(
      /<span className="text-\[12px\] text-text-secondary">([^<]*)<\/span>/,
    )?.[1];
    expect(webCaption).toBeDefined();

    const ios = stripComments(readFileSync(HEATMAP, "utf8"));
    const iosCaption = captionsDrawnBesideARungLabel(ios).find((f) => f.binding === "threshold")
      ?.literals[0];
    expect(iosCaption).toBeDefined();

    expect(iosCaption).toBe(webCaption);
  });
});
