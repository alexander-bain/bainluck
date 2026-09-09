// LAT-P278: the origin (and the NEXT_PUBLIC_SITE_URL override that used to live
// here) moved to `lib/siteUrl.ts` so the site names ONE host. A share link is
// the single most load-bearing caller — it is the URL a stranger actually
// receives — so it must not be the one that still says the apex.
import { getSiteUrl } from "./siteUrl";

export type ShareContentType = "event" | "futures" | "grid";

export function buildShareUrl(
  path: string,
  params?: Record<string, string | number | null | undefined>
): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${getSiteUrl()}${normalizedPath}`);

  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });

  return url.toString();
}

export function buildDiscoverShareUrl(
  path: string,
  contentType: ShareContentType,
  itemId: string | number
): string {
  return buildShareUrl(path, {
    utm_source: "share",
    utm_medium: "discover",
    utm_campaign: "card",
    content_type: contentType,
    item_id: itemId,
  });
}

export function formatShareProbability(probability: number | null | undefined): string | null {
  if (probability === null || probability === undefined || Number.isNaN(probability) || probability === 0) {
    return null;
  }
  return `${Math.round(probability * 100)}%`;
}

export function truncateShareText(text: string, maxLength = 180): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (cleaned.length <= maxLength) return cleaned;
  return `${cleaned.slice(0, maxLength - 1).trim()}...`;
}

export type ShareMethod = "native" | "clipboard";

export interface ShareAttempt {
  title: string;
  text: string;
  url: string;
  /** What goes on the clipboard when there is no share sheet. Defaults to `url`. */
  clipboardText?: string;
}

/**
 * Share through whichever capability the browser ACTUALLY has, and return the
 * method that carried it — or `null` when it has neither.
 *
 * Two separate things this exists to stop, both of which shipped:
 *
 * 1. `Navigator.share` is declared non-optionally in `lib.dom`, so
 *    `navigator.share ? "native" : "clipboard"` is TS2774: TypeScript narrows
 *    it to always-true. The compiler is wrong about the runtime — Firefox
 *    desktop has no share sheet — but right that a bare function reference is
 *    not a predicate.
 * 2. Re-deriving the label from `navigator` AFTER the branch already ran let
 *    the analytics event disagree with what happened. A browser with neither
 *    capability took no branch at all and still logged `method: "clipboard"`.
 *
 * The caller keeps its own try/catch on purpose: a rejected native share (the
 * user dismissing the sheet) stays a throw, because a cancelled share is not a
 * share — the rule `app/discover/stats/page.tsx` already establishes. Failing
 * that way means an unknown outcome reports nothing rather than success.
 */
export async function shareContent(
  attempt: ShareAttempt,
  nav: Navigator
): Promise<ShareMethod | null> {
  const { title, text, url, clipboardText } = attempt;

  if (typeof nav?.share === "function") {
    await nav.share({ title, text, url });
    return "native";
  }

  if (typeof nav?.clipboard?.writeText === "function") {
    await nav.clipboard.writeText(clipboardText ?? url);
    return "clipboard";
  }

  return null;
}

/**
 * What KIND of ladder a `threshold_heatmap` card is drawing.
 *
 * One card shape covers two axes. "Before October · Before 2027" is a ladder in
 * TIME; "$480 · $490 · $500" is a ladder in MAGNITUDE. The backend already
 * tells them apart — `discover_card_archetypes._date_bucket_points` stamps
 * every date rung `source: "date_bucket"` — and it returns the date points
 * WHOLE and FIRST, so a ladder is homogeneous by construction and never half
 * of each. That is what makes one kind per card a safe reading.
 */
export type LadderKind = "date" | "threshold";

/**
 * The rung noun that is TRUE of each ladder kind.
 *
 * A table rather than a ternary so that adding a third axis is a line here
 * instead of a second place to forget.
 */
const LADDER_RUNG_NOUN: Record<LadderKind, string> = {
  date: "window",
  threshold: "outcome",
};

/**
 * The share sentence for a ladder card — UX-1052 item 4, repaired by CERT-867.
 *
 * Alex, on the original: *"the share text ('Before 2027 is at 15% in When will
 * Apple…') gets the same treatment."* Two things were wrong with it. It reads
 * backwards — the answer arrives before the question — and it hands the reader
 * the single number the card itself had just been criticised for showing,
 * saying nothing about the ladder the card now draws.
 *
 * One sentence, question first, leader named, and a count of rungs so the
 * reader knows there is a distribution behind it.
 *
 * CERT-867: that count used to be spelled "N windows" unconditionally, because
 * the sentence was written for the date card it shipped with. `threshold_heatmap`
 * is not only the date card. On the live feed the day this was repaired, SIX of
 * six heatmap cards were magnitude ladders and NONE was a date ladder, so the
 * only sentences this function actually produced told readers that a share
 * price and a box-office gross had "5 windows" and "6 windows".
 *
 * `kind` therefore has NO DEFAULT. A default is what turns the next call site
 * into a silent re-acquisition of this bug, and there is exactly one call site,
 * so requiring it costs nothing.
 *
 * Exported rather than inlined because `ActionBar` takes share text as a prop
 * and never renders it. Note what that does NOT buy: asserting this builder
 * proves the SENTENCE is well-formed and says nothing about which arguments the
 * card hands it — which is precisely how the wrong noun shipped green. The
 * wiring is held by a component-level share-action regression that captures the
 * prop (`ladderShareNoun867.test.tsx`), not by this export.
 */
export function buildLadderShareText(
  marketName: string,
  leaderLabel: string,
  leaderProbability: number,
  rungCount: number,
  kind: LadderKind,
): string {
  const noun = LADDER_RUNG_NOUN[kind];
  return (
    `${marketName} — ${leaderLabel} leads at ${formatShareProbability(leaderProbability)} ` +
    `across ${rungCount} ${noun}${rungCount === 1 ? "" : "s"} on Bain Luck.`
  );
}

/** One bundle member, reduced to the three things a share sentence can say about it. */
export interface BundleShareMember {
  /** The market's question, exactly as the bundle's row prints it. */
  name: string;
  /** The outcome the percent speaks for — `heroOutcome`'s pick — or null when unpriced. */
  leaderLabel: string | null;
  /**
   * The percent ALREADY FORMATTED by the surface — `56%`, or either of the two
   * boundary forms `probabilityDisplay.ts` owns — or null.
   *
   * ⚠️ Those two forms are named here in BACKTICKS and not in quotes on purpose:
   * `probabilityDisplay.test.ts`'s anti-drift guard walks `lib/` and `components/`
   * for the quoted literal and requires exactly one module to hold it. It cannot
   * tell a doc comment from a second implementation — and it should not have to,
   * because a comment that spells the string is how the second implementation
   * gets written. This file spelled it and went red in CI.
   *
   * A string and not a probability on purpose: `FuturesCompactRow` prints
   * `formatProbabilityPercent(p, { rendered: renderedLeaderPercent(...) })`, and
   * a builder that re-rounded the raw probability would be the second copy of a
   * rule that already moved once (#3867) — the share would then quote a number
   * the reader cannot find on the card it came from.
   */
  percent: string | null;
}

/** The most members a bundle share will name, however short their names are. */
const BUNDLE_SHARE_MEMBERS = 3;

/** The length a bundle share fits itself to — `truncateShareText`'s own cap. */
const BUNDLE_SHARE_MAX = 180;

/**
 * The share sentence for a BUNDLE — #4428.
 *
 * A bundle has no detail page, so what it can share is what it IS: the question
 * its members all answer, and how those members currently answer it. Alex, on
 * Discover the morning of 2026-09-09: grouped cards "have no share". Measured
 * that morning, 0 of 5 bundles on page one carried one while 13 of 14 single
 * cards did.
 *
 * Named members and not just a count because the count is the thing the header
 * already stopped printing (D1 clause c, #4066): "5 related" is inventory, and a
 * share that says only "5 markets" hands a stranger nothing to be interested in.
 *
 * ⚠️ The member list is a PREFIX, never a summary, and the count always rides at
 * the end. Naming two of five and saying there are five is honest; naming two and
 * letting them read as all of them is not. Members with no priced leader are
 * dropped rather than printed bare — "2028 Republican presidential nominee: " is
 * a defect in a share sheet, where there is no card underneath to explain it.
 *
 * ⚠️ IT DROPS A WHOLE MEMBER RATHER THAN LETTING THE CAP CUT ONE IN HALF. The
 * sentence is assembled member by member and stops before it crosses the cap, so
 * `truncateShareText` below is a backstop for a monstrous question and not the
 * normal path. A blind `slice(0, 3)` then truncate produced
 * `"… · Jon Ossoff 17% (2028 Democratic presidential nomi..."` on the very first
 * three-member bundle it met, which reads as a broken share, not a short one.
 *
 * The leader leads and the market follows in parentheses, rather than
 * `name: leader`, because a bundle member's name is very often itself a question
 * — five of the five bundles on page one on 2026-09-09 had at least one — and
 * `"2028 U.S. Presidential Election winner?: J.D. Vance 23%"` is unreadable.
 */
export function buildBundleShareText(
  question: string,
  members: readonly BundleShareMember[],
  totalCount: number,
  maxMembers = BUNDLE_SHARE_MEMBERS,
): string {
  const tail = `${totalCount} market${totalCount === 1 ? "" : "s"} on Bain Luck.`;
  const compose = (parts: readonly string[]) =>
    `${question} — ${[...parts, tail].join(" · ")}`;

  const priced = members
    .filter((m) => m.leaderLabel && m.percent)
    .slice(0, Math.max(0, maxMembers))
    .map((m) => `${m.leaderLabel} ${m.percent} (${m.name})`);

  const named: string[] = [];
  for (const part of priced) {
    if (compose([...named, part]).length > BUNDLE_SHARE_MAX) break;
    named.push(part);
  }

  return truncateShareText(compose(named), BUNDLE_SHARE_MAX);
}
