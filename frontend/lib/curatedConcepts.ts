// L2-96 / #11878: frontend curated hub map — a small, deliberately-tiny table of
// query phrases → hub/collection suggestions, injected client-side into the
// search typeahead. This exists because curated collections (the 2026 midterms
// collection is the first) have NO single market whose NAME contains the phrase
// users type — typing "midterms" finds nothing unless we surface the collection
// directly.
//
// Keep this list SHORT and high-confidence. Each alias is matched against the
// normalized query; over-broad aliases would inject noise into every search.

import type { TypeaheadSuggestion } from "@/lib/api";

interface CuratedConcept {
  /** Lowercased phrases that should surface this hub. */
  aliases: string[];
  /** The route the suggestion navigates to. */
  href: string;
  /** Display text in the dropdown. */
  text: string;
}

const CURATED_CONCEPTS: CuratedConcept[] = [
  {
    href: "/collections/midterms-2026",
    text: "2026 Midterm Elections",
    aliases: [
      "midterm",
      "midterms",
      "midterm election",
      "midterm elections",
      "2026 midterm",
      "2026 midterms",
      "2026 election",
      "2026 elections",
      "us midterm",
      "us midterms",
      "congressional election",
      "congressional elections",
      "control of congress",
      "control of the senate",
      "control of the house",
      "chamber control",
      "balance of power",
    ],
  },
];

function normalize(q: string): string {
  return q.trim().toLowerCase().replace(/\s+/g, " ");
}

/**
 * Return synthetic `hub` typeahead suggestions for a raw query, or an
 * empty array. Matches when the query equals an alias, is a (>=4 char) prefix of
 * an alias (partial typing), or an alias (>=5 chars) appears inside the query.
 */
export function matchCuratedConcepts(query: string): TypeaheadSuggestion[] {
  const q = normalize(query);
  if (q.length < 2) return [];
  const out: TypeaheadSuggestion[] = [];
  for (const c of CURATED_CONCEPTS) {
    const hit = c.aliases.some(
      (a) =>
        a === q ||
        (q.length >= 4 && a.startsWith(q)) ||
        (a.length >= 5 && q.includes(a))
    );
    if (hit) {
      out.push({
        type: "hub",
        text: c.text,
        href: c.href,
      });
    }
  }
  return out;
}
