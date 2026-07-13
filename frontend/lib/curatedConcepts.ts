// L2-96: frontend curated concept map — a small, deliberately-tiny table of
// query phrases → event-concept suggestions, injected client-side into the
// search typeahead. This exists because some event-concept hubs (the 2026
// midterms is the first) have NO market whose NAME contains the phrase users
// type — the backend derives concept suggestions from matching market names, so
// typing "midterms" finds nothing even though `event:election:2026-midterms`
// renders 375 races. The backend search ROUTE (a phrase detector mirroring the
// golf-major one) is the durable fix and is owned by a separate lane; this
// frontend table makes the hub discoverable now without touching that route.
//
// Keep this list SHORT and high-confidence. Each alias is matched against the
// normalized query; over-broad aliases would inject noise into every search.

import type { TypeaheadSuggestion } from "@/lib/api";

interface CuratedConcept {
  /** Lowercased phrases that should surface this concept. */
  aliases: string[];
  /** The event-concept key the suggestion routes to (`/event/[key]`). */
  eventKey: string;
  /** Display text in the dropdown. */
  text: string;
}

const CURATED_CONCEPTS: CuratedConcept[] = [
  {
    eventKey: "event:election:2026-midterms",
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
 * Return synthetic `event_concept` typeahead suggestions for a raw query, or an
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
        type: "event_concept",
        text: c.text,
        event_key: c.eventKey,
      });
    }
  }
  return out;
}
