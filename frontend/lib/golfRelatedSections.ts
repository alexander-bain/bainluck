// #951: bucket a golf tournament's prop markets into labeled sections instead
// of dumping every market into one flat "More Markets" list. The structured
// prop data (round-leader props, finish-position, scoring, specials, field
// entries) already arrives in `related_futures` with outcomes — this is the
// pure classification half of the tournament-page layout pass, extracted so it
// can be unit-tested without rendering the page.

export interface RelatedSectionMarket {
  market_id: number;
  market_name: string;
}

export const RELATED_SECTIONS: { id: string; title: string; test: RegExp }[] = [
  {
    id: "round_leaders",
    title: "Round Leaders",
    test: /round\s*leader|first round|second round|third round|fourth round|final round/i,
  },
  {
    id: "finish",
    title: "Finish Position",
    test: /\btop[\s-]?\d+\b|finish(ing)?\s*(position|inside)|make\s*(the\s*)?cut|miss(ed)?\s*(the\s*)?cut|wins?\s+the/i,
  },
  {
    id: "scoring",
    title: "Scoring & Records",
    test: /best round|lowest round|shoot|low(est)?\s*score|margin of victory|winning score|wire[\s-]?to[\s-]?wire|under par|hole[\s-]?out/i,
  },
  {
    id: "specials",
    title: "Specials",
    test: /hole[\s-]?in[\s-]?one|hole[\s-]?in[\s-]?1|ace\b|playoff|sudden death|albatross|condor/i,
  },
  {
    id: "field",
    title: "Field & Entries",
    test: /compete|withdraw|to play|tee it up|participate|in the field|appear/i,
  },
];

export const RELATED_FALLBACK = { id: "other", title: "More Markets" };

/**
 * Group related markets into ordered, non-empty sections. Order within each
 * section preserves the input order. Markets matching no section regex fall
 * into the generic "More Markets" bucket, kept last.
 */
export function groupRelatedMarkets<T extends RelatedSectionMarket>(
  markets: T[],
): { id: string; title: string; markets: T[] }[] {
  const buckets: Record<string, T[]> = {};
  for (const m of markets) {
    const name = m.market_name || "";
    const section =
      RELATED_SECTIONS.find((s) => s.test.test(name))?.id ?? RELATED_FALLBACK.id;
    (buckets[section] ||= []).push(m);
  }
  const ordered = [...RELATED_SECTIONS, RELATED_FALLBACK];
  return ordered
    .filter((s) => buckets[s.id]?.length)
    .map((s) => ({ id: s.id, title: s.title, markets: buckets[s.id] }));
}
