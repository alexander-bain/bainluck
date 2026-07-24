// L2-176 — THE PLAY PAGE kid-safe content filter.
//
// The raters are an 8-year-old and a 12-year-old. This is the SAFETY guard for
// the /play card pool: a card only renders to a kid if BOTH
//   (1) its category is in the allowlist (sports / entertainment / weather only), and
//   (2) none of its visible text hits the term blocklist.
// "Err broad" per the queue — a false negative (a fine card hidden) is fine; a
// false positive (a war/death/election card shown to an 8yo) is not.
//
// Pure module (no window / no fetch) so it is unit-tested in the node jest env.

import { getDiscoverItemAnalytics } from "@/lib/discoverInteractions";
import type { FeedItem } from "@/lib/types";

// ---------------------------------------------------------------------------
// Category allowlist
// ---------------------------------------------------------------------------
// getDiscoverItemAnalytics() normalizes every card to a single category token.
// Events map through `sport.split("_")[0]` so raw Odds-API prefixes
// (americanfootball, icehockey) show up here too — include them.
const SPORTS_CATEGORIES = new Set([
  "basketball",
  "football",
  "americanfootball",
  "baseball",
  "hockey",
  "icehockey",
  "soccer",
  "golf",
  "mma",
  "boxing",
  "motorsports",
  "cricket",
  "cycling",
  "tennis",
  "olympics",
  "rugby",
  "volleyball",
  "wwe",
  "wrestling",
  "sports",
]);

// The only non-sports categories a kid ever sees.
const OTHER_ALLOWED = new Set(["entertainment", "weather"]);

export function isKidSafeCategory(category: string | null | undefined): boolean {
  const c = (category || "").toLowerCase();
  return SPORTS_CATEGORIES.has(c) || OTHER_ALLOWED.has(c);
}

// ---------------------------------------------------------------------------
// Term blocklist
// ---------------------------------------------------------------------------
// Two lists so we can be broad without nuking safe entities:
//  - EXACT_TERMS: whole-word match (`\bterm\b`). Used for words that are common
//    prefixes of safe names — "war" (Warriors, Warsaw), "gun" (Gunnar),
//    "die" (Diego), "coup" (couple/coupon), "stab" (stability).
//  - PREFIX_TERMS: word-start match (`\bterm`). Catches inflections
//    (invade/invaded/invasion, election/elections, virus/viral) without a
//    trailing boundary.
const EXACT_TERMS = [
  "war",
  "wars",
  "gun",
  "guns",
  "die",
  "died",
  "dies",
  "dead",
  "coup",
  "coups",
  "stab",
];

const PREFIX_TERMS = [
  // queue-required core (err broad):
  "death",
  "invade",
  "invaded",
  "invasion",
  "invad",
  "invas",
  "pandemic",
  "virus",
  "viru",
  "pregnan",
  "regime",
  "election",
  "crypto",
  // violence / conflict:
  "kill",
  "murder",
  "terror",
  "bomb",
  "missile",
  "nuclear",
  "hostage",
  "warfare",
  "warhead",
  "genocide",
  "massacre",
  "execut",
  "kidnap",
  "slaughter",
  "behead",
  "torture",
  "corpse",
  "homicide",
  "manslaughter",
  "fatal",
  "weapon",
  "casualt",
  "wound",
  "assault",
  "riot",
  "shooting",
  "shooter",
  "gunman",
  "gunfire",
  "gunshot",
  "gunned",
  "stabbed",
  "stabbing",
  "airstrike",
  "insurgen",
  // geopolitics / extremism:
  "jihad",
  "isis",
  "hamas",
  "hezbollah",
  // health / substances:
  "covid",
  "overdos",
  "suicide",
  "drug",
  "cartel",
  // finance the queue named:
  "bitcoin",
  "ethereum",
  // adult / abuse:
  "abortion",
  "rape",
  "raped",
  "sexual",
  "incest",
  "pedophile",
  "traffick",
  "molest",
  "naked",
  "nude",
  "nudity",
  "porn",
];

const EXACT_RE = new RegExp(`\\b(${EXACT_TERMS.join("|")})\\b`, "i");
const PREFIX_RE = new RegExp(`\\b(${PREFIX_TERMS.join("|")})`, "i");

/** True when the text is clean of every blocklist term. */
export function isKidSafeText(text: string | null | undefined): boolean {
  if (!text) return true;
  return !EXACT_RE.test(text) && !PREFIX_RE.test(text);
}

/**
 * The single gate a feed card must pass to render in /play.
 * Rejects: disallowed categories, blocklist text, and bundle cards (which fold
 * multiple un-vetted markets and can't be safely categorized here).
 */
export function isKidSafeItem(item: FeedItem): boolean {
  if (!item || item.type === "bundle") return false;
  const a = getDiscoverItemAnalytics(item);
  if (!isKidSafeCategory(a.category)) return false;
  const text = [a.item_name, a.headline, item.headline, item.reason]
    .filter(Boolean)
    .join(" · ");
  return isKidSafeText(text);
}

export function filterKidSafe(items: FeedItem[]): FeedItem[] {
  return (items || []).filter(isKidSafeItem);
}
