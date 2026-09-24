/**
 * #8413 — the web's first ten were not the ten the feed chose.
 *
 * The feed arrives ranked: the server has already applied first-page category
 * caps and the event/futures mix. The page then spaces it so the default feed
 * does not cluster into one sport. The old pass split the list into a sports
 * queue and a non-sports queue and took a sports card whenever the run cap
 * allowed — exactly one non-sports card after every two sports cards, whatever
 * the ranking — and its "don't repeat the last sport" swap reached four cards
 * ahead for ANY other sport. On 2026-09-24 that turned a served 4-sports /
 * 6-non-sports top ten into 7/3 and pulled a score-26 final and a Korn Ferry
 * event six days out onto page one, while the served #2 fell to 13.
 *
 * 🔴 SPACING DEFERS, IT NEVER PROMOTES. The same two rules hold (a sports run
 * cap; no two cards of the same sport side by side), but each slot takes the
 * highest-ranked remaining card that satisfies them. A card moves forward only
 * past cards the rules are holding back — never because of its category. When
 * no remaining card satisfies the rules, the highest-ranked card that is not
 * a same-sport repeat is taken, then simply the highest-ranked.
 */

export const SPORT_CATEGORIES: ReadonlySet<string> = new Set([
  "basketball", "football", "baseball", "hockey", "soccer", "golf", "mma", "boxing",
  "tennis", "cricket", "motorsports", "americanfootball", "icehockey", "cycling",
]);

export function spaceBySport<T>(items: T[], categoryOf: (item: T) => string): T[] {
  if (items.length <= 2) return items;

  const nonSportsCount = items.filter((item) => !SPORT_CATEGORIES.has(categoryOf(item))).length;
  const maxSportsRun = nonSportsCount >= 4 ? 2 : 3;

  const remaining = [...items];
  const result: T[] = [];
  let lastSport = "";
  let sportsSinceNonSport = 0;

  while (remaining.length > 0) {
    let pick = remaining.findIndex((item) => {
      const cat = categoryOf(item);
      if (!SPORT_CATEGORIES.has(cat)) return true;
      return sportsSinceNonSport < maxSportsRun && cat !== lastSport;
    });
    // Nothing satisfies both rules (only sports left, run cap reached): still
    // avoid a same-sport pair if any other card allows it.
    if (pick === -1) pick = remaining.findIndex((item) => categoryOf(item) !== lastSport);
    if (pick === -1) pick = 0;

    const [item] = remaining.splice(pick, 1);
    const cat = categoryOf(item);
    result.push(item);
    if (SPORT_CATEGORIES.has(cat)) {
      lastSport = cat;
      sportsSinceNonSport++;
    } else {
      lastSport = "";
      sportsSinceNonSport = 0;
    }
  }

  return result;
}
