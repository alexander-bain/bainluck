import type {
  FeedConceptData,
  FeedEventData,
  FeedFuturesData,
  FeedItem,
} from "@/lib/types";

/**
 * ═══ #5973: THE RAIL DEALT A PLAYER WHO IS NOT IN THE MATCH ═══
 *
 * Filed by ux/1239 from the US Open men's final, `/events/15310688`: `MORE
 * TENNIS · 4` on Zverev v Shelton dealt two Djokovic retirement cards and one
 * `American to win the US Open?`, and Djokovic is in none of it.
 *
 * `RelatedByTag` asks the feed for a tag and prints the first four things it
 * gets back. The feed ranks by its own generic quality/popularity order, which
 * knows nothing about the page the rail is standing on — so **every game page
 * in a league gets the same rail**. Measured on production 2026-09-22 over 10
 * game pages: both WNBA pages identical, both NHL pages identical (including
 * `Will Dallas Stars advance…` and `Will Florida Panthers advance…` on a
 * Columbus v Buffalo game), both UFC pages identical.
 *
 * This orders the cards the rail already has so that ones naming a side of THIS
 * match come first. Measured effect over those 10 pages: **top four changed on
 * 2, unchanged on 8, worse on 0** — `MLB: 2026 AL Central Champion` reaches a
 * Tigers page and `Team to advance to the NFC Championship Game` reaches a
 * Lions page, both from below the fold of a four-card rail.
 *
 * ## Why this REORDERS and never filters
 *
 * #8093 is the cautionary case in this very component: narrowing that rail's
 * query by league was right for basketball and took the entire section off
 * every Champions League tie and every Grand Slam match page (`9→0` on both).
 * A sort cannot do that. The same items come out as went in, in the same
 * number, so no page can lose a rail it has today and the worst case on any
 * page is the order it already had.
 *
 * ## Two things measured and deliberately NOT built
 *
 * **A wider fetch does not find the missing teams.** The obvious next move is
 * to ask for more than `limit + 5` and rank deeper. Measured at width 9 vs 40
 * over six pages, widening gained exactly ONE participant-naming card in total
 * (`Pro Football: NFC North Champion`, on a Packers page) and nothing at all on
 * NHL, WNBA or UFC — 36 usable UFC markets, zero naming either fighter. The
 * content is not further down the list; it is not in the tag-scoped feed. A 4×
 * payload on every event page for one card is not the trade.
 *
 * **There is no `team:` tag to ask for.** `feed._STATIC_TAG_NAMESPACES` is
 * `{sport, league, tier, class, level, gender, category, source}`. The #8093
 * move — ask the producer for the narrower thing — has nothing to ask with
 * here, and minting that namespace is the taxonomy's call, not this file's.
 *
 * So this closes the half of #5973 that lives in the rail's own ordering. The
 * duplicate-question half (three Djokovic retirement markets across two venues,
 * different `group_id`, so every dedup path is structurally blind) is not a
 * sort and not a layout concern — it needs the two questions recognised as one
 * upstream, and #5973 stays open on it.
 */

/** Fold to comparable words: lowercase, punctuation to spaces, runs collapsed.
 *  `Stanley Cup®` and `Stanley Cup` have to be the same letters here, and
 *  `Djokovic:` must not carry its colon into a word-boundary test. */
export function normalizeForMatch(value: string | null | undefined): string {
  return (value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The shortest team name that may be promoted on.
 *
 * MEASURED, because the guess was wrong twice. `teams` holds 10,011 rows, of
 * which **1,147 names are a single word** — the short end of that list is
 * `OTR · Tau · IPK · USC · PSG · HPK · UAE · TPS · AIK · GAS · USA · TBD`. A
 * three-letter needle is not a team on a card, it is a coincidence waiting to
 * happen: `GAS` matches the word gas, `USA` matches half of an Olympics
 * market, and `TBD` is not a team at all — it is the placeholder an unscheduled
 * fixture carries, and it would promote every card that says the same.
 *
 * Exactly **19 of the 10,011** are three characters, so the floor costs
 * essentially nothing and buys the whole class. Names of four and up
 * (`Nice · Como · Lyon · León · Vado · Boom`) keep their boost, guarded by the
 * word-boundary test below.
 */
const MIN_NEEDLE_LENGTH = 4;

/**
 * The sides of the match a rail is standing on, as a reader would name them.
 *
 * Only whole names are used. A last-word fallback (`Buffalo Bills` → `Bills`)
 * was measured over the same 10 pages and matched NOTHING the full name did not
 * already match, so it is not carried: it is pure false-positive surface, and
 * the Connecticut **Sun** is the case that makes the point.
 *
 * A name below the floor is dropped rather than shortened. This is a
 * PREFERENCE, so the two errors are not symmetric: a wrong promotion is a card
 * a reader can see does not belong, while a missed one is only the order the
 * page has today.
 */
export function participantNames(
  away: string | null | undefined,
  home: string | null | undefined,
): string[] {
  return [away, home]
    .map((name) => normalizeForMatch(name))
    .filter((name) => name.length >= MIN_NEEDLE_LENGTH);
}

/**
 * The text a card actually PRINTS, which is the only text it may be promoted
 * for.
 *
 * Deliberately not the whole payload. A futures card renders its name and at
 * most the first four PRICED outcomes (`MAX_FIELD_ROWS`), so matching against
 * all 75 outcomes of `NBA Finals MVP Winner` would promote a card on the
 * strength of a name the reader cannot see — the promotion has to be legible
 * as a promotion, or it reads as an arbitrary shuffle.
 */
export function cardPrintedText(item: FeedItem): string {
  const parts: (string | null | undefined)[] = [];

  if (item.type === "event") {
    const d = item.data as FeedEventData;
    parts.push(d.away_team, d.home_team);
  } else if (item.type === "concept") {
    const d = item.data as FeedConceptData;
    parts.push(d.name, d.leader?.name);
  } else {
    const d = item.data as FeedFuturesData;
    parts.push(d.name);
    for (const outcome of (d.top_outcomes ?? []).filter(
      (o) => typeof o.probability === "number",
    ).slice(0, 4)) {
      parts.push(outcome.name);
    }
  }

  return normalizeForMatch(parts.filter(Boolean).join(" "));
}

/**
 * Whole-word containment, and it is load-bearing rather than defensive.
 *
 * 1,147 team names are a single word, so a needle really can sit inside a
 * longer one: **`Como`** is a Serie A club and **Comoros** is a national side
 * that appears in the same soccer feeds, so a substring test promotes an
 * Africa Cup market onto a Como fixture. `Nice`, `Lyon`, `León` and `Boom` are
 * the same shape.
 */
function containsWord(haystack: string, needle: string): boolean {
  if (!needle) return false;
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^| )${escaped}( |$)`).test(haystack);
}

/** Does this card name either side of the match it is being shown beside? */
export function cardNamesParticipant(item: FeedItem, names: string[]): boolean {
  if (names.length === 0) return false;
  const text = cardPrintedText(item);
  return names.some((name) => containsWord(text, name));
}

/**
 * The rail's cards, ones naming a side of this match first.
 *
 * A STABLE partition, not a comparator: within each group the feed's own rank
 * survives untouched, so this adds a preference to the server's ordering rather
 * than replacing it. Returns the input array itself when there is nothing to
 * do — no names, no hits, or every card a hit — so the common case allocates
 * nothing and the identity is easy to assert.
 */
export function orderByParticipant<T extends FeedItem>(
  items: T[],
  names: string[],
): T[] {
  if (names.length === 0 || items.length < 2) return items;

  const hits: T[] = [];
  const rest: T[] = [];
  for (const item of items) {
    (cardNamesParticipant(item, names) ? hits : rest).push(item);
  }
  if (hits.length === 0 || rest.length === 0) return items;

  return [...hits, ...rest];
}
