// L2-176 / L2-187 — THE PLAY PAGE admission filter (content safety + freshness).
//
// The raters are an 8-year-old and a 12-year-old. A card only renders to a kid if
// it is BOTH kid-safe AND fresh (see isPlayEligible, the single gate filterKidSafe
// applies):
//   SAFE (L2-176/177/178):
//     (1) its category is in the allowlist (sports / entertainment / weather /
//         culture), and
//     (2) none of its visible text hits the term blocklist.
//   FRESH (L2-187):
//     (3) its status/date prove it is still upcoming, live, or a genuinely open
//         market — completed/closed/settled/resolved cards are rejected so /play
//         never shows a live-looking % on a game that is already over.
// "Err broad" per the queue — a false negative (a fine card hidden) is fine; a
// false positive (a war card, or a settled game shown as fresh) is not.
//
// Pure module (no window / no fetch) so it is unit-tested in the node jest env.

import { getDiscoverItemAnalytics } from "@/lib/discoverInteractions";
import type {
  FeedItem,
  FeedFuturesData,
  FeedEventData,
  FeedConceptData,
  FeedTournamentData,
} from "@/lib/types";

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
// `culture` is allowed (L2-177) so Taylor-Swift / pop-culture cards — the whole
// point of the Music love-chip — actually reach the kid. The term blocklist below
// (now carrying the pregnancy / relationship-gossip terms the TS market corpus
// includes) is what keeps that category safe: a clean "Taylor Swift album of the
// year?" passes, a "Will Taylor Swift be pregnant?" / "...get engaged?" does not.
const OTHER_ALLOWED = new Set(["entertainment", "weather", "culture"]);

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
  // relationship / adult gossip (L2-177 — the `culture`/TS corpus carries these;
  // an 8yo sees this page, so err broad — a hidden album card is fine, a
  // pregnancy/affair speculation card is not):
  "divorce",
  "affair",
  "mistress",
  "adulter",
  "breakup",
  "dating",
  "romance",
  "hookup",
  "cheat",
  "engag",
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
 * Every user-visible string a /play card can render, joined into one haystack.
 * This is the single source the blocklist runs over — there must be NO bypass
 * path. The L2-178 bug: the gate only checked title/headline/reason, so a card
 * with a clean title but a blocked OUTCOME label slipped through — and /play
 * literally renders outcome text as the guess subject (HigherLower.tsx `subject`),
 * so a blocked entity in an outcome would be shown to an 8-year-old. Collect the
 * title, headline/hook, reason, category, AND every outcome label:
 *   - futures: each `top_outcomes[].name`
 *   - events: both team names (they render as "<team> to win")
 */
export function collectKidVisibleText(item: FeedItem): string {
  const a = getDiscoverItemAnalytics(item);
  const parts: (string | null | undefined)[] = [
    a.item_name,
    a.headline,
    a.category,
    item.headline,
    item.reason,
  ];
  if (item.type === "futures") {
    const d = item.data as FeedFuturesData;
    for (const o of d.top_outcomes ?? []) parts.push(o.name);
  } else if (item.type === "event") {
    const d = item.data as FeedEventData;
    parts.push(d.home_team, d.away_team);
  }
  return parts.filter(Boolean).join(" · ");
}

/**
 * The CONTENT-SAFETY half of the /play admission gate (freshness is the other
 * half — see isFreshForPlay / isPlayEligible).
 * Rejects: disallowed categories, blocklist text (over ALL rendered strings —
 * see collectKidVisibleText), and bundle cards (which fold multiple un-vetted
 * markets and can't be safely categorized here). The affinity-seeded deck is a
 * reordering of the already-filtered pool (see /play page loadPool →
 * seedByAffinity), so it passes through the same gate — no separate path.
 */
export function isKidSafeItem(item: FeedItem): boolean {
  if (!item || item.type === "bundle") return false;
  const a = getDiscoverItemAnalytics(item);
  if (!isKidSafeCategory(a.category)) return false;
  return isKidSafeText(collectKidVisibleText(item));
}

// ---------------------------------------------------------------------------
// Freshness (L2-187)
// ---------------------------------------------------------------------------
// A /play card must ALSO be fresh, not just kid-safe. /play renders a
// live-looking probability with no score/"FINAL" framing, so a completed /
// closed / settled / resolved card shows a stale % on a game that is already
// over — the exact defect measured in REPORT-2.md (19/78 deck cards were
// finished games rendering misleading odds: "Astros vs White Sox" ended 12-3
// but the card showed "97% chance"). That violates the standing "settled means
// settled" ruling. This predicate is FAIL-CLOSED: a card passes ONLY when its
// own status/date positively establish that it is still upcoming, live, or a
// genuinely open future market. When freshness cannot be established, the card
// is rejected. Freshness is judged PER CARD TYPE — it is NEVER inferred from
// content safety (a war-free headline says nothing about whether the game is
// over), and vice-versa. The two gates are independent by design.

// Event statuses that positively mean "not yet finished". `completed`/`closed`
// (and anything else) are stale.
const FRESH_EVENT_STATUSES = new Set(["scheduled", "live"]);

// Concept statuses that positively mean "still to come or underway". The concept
// adapter emits upcoming/live/settled (app/utils/event_concept.py `_golf_status`
// and the UFC/cycling adapters); a `settled` concept only reaches the feed to
// hold its post-settlement WHAT-HIT pin, which `marquee_whathit` catches too.
const FRESH_CONCEPT_STATUSES = new Set(["upcoming", "scheduled", "live"]);

// Raw golf `schedule_status` values (hyphen→underscore normalized) that mean the
// tournament is over. Mirrors event_concept._golf_status's terminal set.
const SETTLED_SCHEDULE_STATUSES = new Set([
  "completed",
  "closed",
  "resolved",
  "final",
  "settled",
]);
const LIVE_SCHEDULE_STATUSES = new Set([
  "in_progress",
  "live",
  "active",
  "upcoming",
  "scheduled",
]);

/** True only when `iso` parses to a moment strictly before `now`. A missing or
 *  unparseable date is NOT "known past" — freshness is then decided by the
 *  card's status signals (or fail-closed if there are none). */
function isPastDate(iso: string | null | undefined, now: number): boolean {
  if (!iso) return false;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return false;
  return t < now;
}

/**
 * Fail-closed freshness gate for a /play card. Returns true ONLY when the card's
 * own status/date fields prove it is still upcoming, live, or genuinely open.
 * Unknown card types (e.g. bundle) and cards that cannot establish freshness are
 * rejected. `now` is injectable for deterministic tests.
 */
export function isFreshForPlay(item: FeedItem, now: number = Date.now()): boolean {
  if (!item) return false;
  switch (item.type) {
    case "event": {
      const d = item.data as FeedEventData;
      // completed/closed (and any other value) → stale. Only scheduled/live play.
      return FRESH_EVENT_STATUSES.has((d.status || "").toLowerCase());
    }
    case "futures": {
      const d = item.data as FeedFuturesData;
      // A market surfaced result-first is settled even when the DB status stays
      // 'open' (gotcha #33: settled Kalshi markets keep status='open', flagged
      // via `resolved`/`winner`).
      if (d.resolved === true || d.winner) return false;
      if ((d.status || "").toLowerCase() !== "open") return false; // resolved/closed/unknown
      // An "open" market whose resolution time has already passed is stale.
      if (isPastDate(d.resolution_date, now)) return false;
      return true;
    }
    case "concept": {
      const d = item.data as FeedConceptData;
      // Post-settlement WHAT-HIT pin, or a named champion, = a result card.
      if (d.marquee_whathit === true || d.winner) return false;
      return FRESH_CONCEPT_STATUSES.has((d.status || "").toLowerCase());
    }
    case "tournament": {
      const d = item.data as FeedTournamentData;
      // Post-settlement WHAT-HIT pin = a result card.
      if (d.marquee_whathit === true) return false;
      const sched = (d.schedule_status || "").toLowerCase().replace(/-/g, "_");
      if (SETTLED_SCHEDULE_STATUSES.has(sched)) return false;
      // A passed resolution/end date means the tournament is over regardless of a
      // stale schedule_status (gotcha #14: resolution_date can be a future Kalshi
      // close-time artifact, so a PAST one is a reliable "done" signal).
      if (isPastDate(d.resolution_date, now)) return false;
      if (isPastDate(d.end_date, now)) return false;
      // Positive freshness: an explicit live/upcoming schedule_status, OR a
      // future date window. Fail closed when neither is present.
      if (LIVE_SCHEDULE_STATUSES.has(sched)) return true;
      if (d.end_date && !isPastDate(d.end_date, now)) return true;
      if (d.resolution_date && !isPastDate(d.resolution_date, now)) return true;
      if (d.start_date && !isPastDate(d.start_date, now)) return true;
      return false;
    }
    default:
      // bundle / unknown types cannot be freshness-vetted here.
      return false;
  }
}

/**
 * The full /play admission gate: kid-safe (content) AND fresh (not settled).
 * Both are required and independent — see isKidSafeItem and isFreshForPlay.
 */
export function isPlayEligible(item: FeedItem, now: number = Date.now()): boolean {
  return isKidSafeItem(item) && isFreshForPlay(item, now);
}

export function filterKidSafe(items: FeedItem[]): FeedItem[] {
  return (items || []).filter((it) => isPlayEligible(it));
}
