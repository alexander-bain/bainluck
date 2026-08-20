/**
 * THE DIFFERENTIAL CENSUS — the shared machinery, extracted in UX-P107.
 *
 * ── WHAT THIS SHAPE IS, AND WHY IT KEEPS EARNING ITS KEEP ────────────────────
 *
 * UX-P106 built it for the settled vocabulary after a THIRD spelling of
 * hit/miss reached production and was caught by a screenshot rather than by the
 * guard written to prevent exactly that (#1650/#2011). The guard had banned the
 * words it already knew, in the files it already knew, and a denylist of
 * known-good strings cannot in principle see a new pair.
 *
 * The shape that works instead: render the same surface TWICE with one input
 * flipped and everything else held identical, then diff the rendered token
 * multisets. **The tokens that differ ARE the vocabulary**, whatever it turns
 * out to be — so a word nobody predicted lands in the delta and reds the suite.
 * It caught a fourth pair the day it was written.
 *
 * UX-P107 is the second vocabulary class, and the directive's carry says to
 * cite the shape when one appears. It does, on a different axis: the settled
 * census flips the VERDICT and asks which words state it; the pregame census
 * flips the PRICE across the coin flip and asks the same question about
 * direction. Same machinery, so it is now one implementation rather than two
 * copies free to drift — #1951's rule applied to the guards themselves.
 *
 * Consumers: `__tests__/lib/settledVocabulary.test.tsx` (verdict axis),
 * `__tests__/lib/propPregameDirection.test.tsx` (direction axis).
 */

/**
 * Attribute values a reader can actually receive. `aria-label` and `title` are
 * rendered surfaces even though no screenshot shows them — and the direction
 * axis proved that matters twice over: the banned phrasing survived in an
 * aria-label after being corrected on screen.
 */
const SPOKEN_ATTRS = /\s(?:aria-label|title|alt)="([^"]*)"/g;

const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
  "&rarr;": "→",
  "&middot;": "·",
  "&nbsp;": " ",
  "&mdash;": "—",
  "&ndash;": "–",
  "&ldquo;": "“",
  "&rdquo;": "”",
  "&rsquo;": "’",
};

function decode(s: string): string {
  return s.replace(/&[#a-zA-Z0-9]+;/g, (m) => ENTITIES[m] ?? " ");
}

/**
 * Every token a reader receives from this markup — visible text plus spoken
 * attribute values. Style and class attributes are deliberately dropped: a
 * colour is not a vocabulary, and `text-accent-danger` differing between the
 * two renders is the design system working.
 */
export function renderedTokens(html: string): string[] {
  const spoken: string[] = [];
  for (const m of html.matchAll(SPOKEN_ATTRS)) spoken.push(m[1]);
  const visible = html.replace(/<[^>]*>/g, " ");
  return decode([...spoken, visible].join(" "))
    .split(/\s+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

/**
 * A token that carries no vocabulary: numbers, percentages, punctuation, the
 * em-dash placeholder. These may differ freely between the two renders — an
 * `actual` of 2 and an `actual` of 0 are data, not language.
 */
const DATA_ONLY = /^[\d.,%+\-–—:;()/[\]{}·•→←↑↓×°$#'"’“”…!?*|=<>~^_&]+$/u;

export function isDataOnlyToken(token: string): boolean {
  return DATA_ONLY.test(token);
}

/** Multiset difference, both directions, of the tokens two renders produce. */
export function vocabularyDelta(aHtml: string, bHtml: string): string[] {
  const count = (tokens: string[]) => {
    const m = new Map<string, number>();
    for (const t of tokens) m.set(t, (m.get(t) ?? 0) + 1);
    return m;
  };
  const a = count(renderedTokens(aHtml));
  const b = count(renderedTokens(bHtml));
  const out = new Set<string>();
  for (const [t, n] of a) if ((b.get(t) ?? 0) !== n) out.add(t);
  for (const [t, n] of b) if ((a.get(t) ?? 0) !== n) out.add(t);
  return [...out].filter((t) => !DATA_ONLY.test(t)).sort();
}
