// LAT-P278: the origin (and the NEXT_PUBLIC_SITE_URL override that used to live
// here) moved to `lib/siteUrl.ts` so the site names ONE host. A share link is
// the single most load-bearing caller — it is the URL a stranger actually
// receives — so it must not be the one that still says the apex.
import { formatProbabilityPercent } from "./probabilityDisplay";
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

/**
 * The percentage a SHARE surface prints — the sentence under a pasted link, and
 * the number the PICTURE of that link draws.
 *
 * ═══ #7716 — THE PAGE AND THE PICTURE OF THE PAGE DISAGREED ═══
 *
 * This was a bare `Math.round(p * 100)`: the rule the rest of the site has
 * stopped using twice. Measured on production 2026-09-21, both ends live in the
 * same minute:
 *
 *   /sport/baseball/mlb/team/baltimore-orioles-mlb   (championship_path 0.004)
 *     og:description  "Baltimore Orioles: 0% to win the championship."
 *     the page        "CHAMPIONSHIP  <1%"                                (#7710)
 *
 *   /futures/400   (La Liga Winner, status `open`, Barcelona at 0.995)
 *     og:title        "Barcelona 100% - La Liga Winner"
 *     the card        a 96px "100%" above a bar clamped to 97 — the picture
 *                     contradicting its own number inside one frame
 *
 * Three decisions were being retaken here rather than deferred to, and all three
 * are already owned one import away:
 *
 *  1. UX-P046's boundary rule — "rounding may never move a probability across a
 *     boundary it is not on". 6,799 outcomes on open markets sit in (0, 0.005)
 *     and 1,904 in [0.995, 1); 120 and 891 of those are the rank-1 leader a
 *     share sentence actually NAMES (db-query, 2026-09-21).
 *  2. #3867's rounding contract — `renderedPercent` recovers the quoted decimal
 *     before rounding and this did not, so the four wire values that ruling
 *     measured printed a point away from the page they depict. All four are
 *     live: 0.145 / 0.285 / 0.565 / 0.575 hold 1,715 outcomes and 388 leaders
 *     on open markets today.
 *  3. Nothing new. `probabilityParts` already composes 1 and 2, and #6849 took
 *     exactly this trade for the two-competitor case in `eventConceptShareMeta`
 *     — "leaving the formatter's here would trade a sum defect for an unfurl
 *     that disagrees with the page it depicts". This is that sentence, whole.
 *
 * ═══ WHAT DOES NOT MOVE ═══
 *
 * **An exact 0 still returns `null`, and it is load-bearing.** It is not "0%"
 * and never was: it is the signal every caller reads to drop the number from the
 * sentence rather than print a zero into it. `pricedCompetitors` sheds the 199
 * golfers behind a settled winner with it, `boardLeader` and `futuresBoardPrice`
 * withhold a whole unpriced board on it, and `/futures/[id]`'s picture stopped
 * drawing a 96px dash because of it (#6127). Routing an exact 0 through
 * `formatProbabilityPercent` would print "0%" — right for that function, whose
 * callers keep their own em-dash rule, and wrong for every caller of this one.
 *
 * An exact 1 still prints "100%". That IS a boundary; the rule above only
 * refuses to claim one a value is not on.
 *
 * ═══ THE WIDEST STRING IS UNCHANGED, WHICH IS WHY THE FIXED BOXES ARE SAFE ═══
 *
 * A share percent is drawn into a slot Satori will not reflow — 92px in
 * `UnfurlCard`'s hero row, 96px on `/futures/[id]`'s card. `<1%` is three glyphs
 * against `0%`'s two, and `>99%` is four against `100%`'s four, so the longest
 * string this can now produce is the one those slots have always drawn.
 * `shareBoundaryPercent7716.test.tsx` renders both cards at the two boundaries
 * and pins that, rather than leaving it as an argument about glyph widths.
 *
 * A non-finite value now returns `null` instead of "Infinity%". `NaN` already
 * did; `Infinity` reached `Math.round` and printed. No caller wanted either.
 *
 * ⚠️ The two boundary strings are deliberately NOT spelled in this file.
 * `probabilityDisplay.ts` is their one home and its suite walks `lib/` and
 * `components/` to keep it that way — a second spelling is exactly how the copy
 * this deletes came to exist.
 */
export function formatShareProbability(probability: number | null | undefined): string | null {
  if (
    probability === null ||
    probability === undefined ||
    !Number.isFinite(probability) ||
    probability === 0
  ) {
    return null;
  }
  return formatProbabilityPercent(probability);
}

/**
 * Fit share text to a budget, cutting at a WORD boundary.
 *
 * The cut used to land wherever `maxLength` fell, so the card for
 * `/futures/60276241` read "...has become increasingly perti..." and its
 * `og:description` "...raising conc...". A half-word is not an abbreviation; it
 * reads as a rendering failure, and it is the first thing a reader sees under a
 * pasted link.
 *
 * Two deliberate limits:
 *  - A boundary is only honoured if it keeps at least half the budget. One
 *    pathological token — `tournamentShareMeta`'s guard feeds a 400-character
 *    display name — would otherwise rewind past everything before it and emit
 *    "US Open 2026:...". Cutting that token mid-word is the lesser failure, so
 *    below the floor the old behaviour stands.
 *  - The ellipsis is still added AFTER the budget, so the ceiling remains
 *    `maxLength + 2`. Callers have been pinned to that since #4149 and this is
 *    not the change that moves it.
 */
export function truncateShareText(text: string, maxLength = 180): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (cleaned.length <= maxLength) return cleaned;
  const clipped = cleaned.slice(0, maxLength - 1);
  const lastSpace = clipped.lastIndexOf(" ");
  const atBoundary =
    lastSpace >= Math.floor((maxLength - 1) / 2) ? clipped.slice(0, lastSpace) : clipped;
  return `${atBoundary.trim()}...`;
}

/**
 * End a share sentence whose last clause is a MARKET NAME, without doubling the
 * terminator the name already carries.
 *
 * A market name is very often itself a question — 136,601 of the 996,337 resolved
 * markets and 9,684 of the 36,398 open ones end in `?` (production db-query,
 * 2026-09-13 21:52Z). Appending `.` unconditionally is what printed this on
 * `/futures/60544511`, read off production the same minute:
 *
 *   og:description  "77° or above won Temperature in New York City on Sep 3,
 *                    2026 at 7pm EDT?. See the full probability board on Bain Luck."
 *
 * `?.` is not a typo a reader forgives; it is the first thing under a pasted
 * link. The rule is punctuation-only and deliberately narrow: it appends a period
 * when the text ends in none of `.`/`!`/`?`, and otherwise leaves the text exactly
 * as the market named itself. It never REMOVES a terminator — stripping the `?`
 * would edit the market's own question, which is the venue's wording and not ours.
 */
export function endShareSentence(text: string): string {
  const trimmed = text.trim();
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

export interface ScorecardStats {
  accuracy: number;
  total: number;
  correct: number;
  streak: number;
  best: number;
}

/**
 * The five numbers behind a shared prediction scorecard, or `null` when the URL
 * does not describe a real one.
 *
 * `/discover/scorecard` is a share TARGET: everything it draws arrives in the
 * query string. The page body has always sanitized (`parseInt(...) || 0`);
 * `generateMetadata` did not, so one URL told two stories. Read off production
 * 2026-09-13 22:03Z:
 *
 *   ?accuracy=999999&total=abc&correct=-5
 *   og:description  "999999% accurate across abc predictions on Bain Luck!"
 *   the page         999999% over 0 predictions
 *
 * and a bare `/discover/scorecard` unfurled "0% accurate across 0 predictions".
 * Our own `handleShare` never writes those — it is a hand-edited or mangled
 * link — but it still unfurls chosen copy under our name, which is the thing a
 * pasted link is judged on.
 *
 * So this REFUSES rather than invents. A scorecard has to be internally
 * possible to be described at all: five plain non-negative integers (no signs,
 * no decimals, no `abc`, which `parseInt` would otherwise read as far as it can
 * and shrug), an accuracy inside 0-100, at least one prediction, and no more
 * correct than were made. Anything else is not a low scorecard, it is not a
 * scorecard, and the caller says so in words instead of printing a number.
 */
export function readScorecardStats(params: {
  accuracy?: string;
  total?: string;
  correct?: string;
  streak?: string;
  best?: string;
}): ScorecardStats | null {
  const read = (raw: string | undefined): number | null =>
    raw !== undefined && /^\d+$/.test(raw) ? Number(raw) : null;

  const accuracy = read(params.accuracy);
  const total = read(params.total);
  const correct = read(params.correct);
  const streak = read(params.streak);
  const best = read(params.best);

  if (accuracy === null || total === null || correct === null || streak === null || best === null) {
    return null;
  }
  if (accuracy > 100 || total < 1 || correct > total || streak > total || best > total) {
    return null;
  }
  return { accuracy, total, correct, streak, best };
}

/**
 * The one sentence a shared scorecard prints, in the unfurl and in the text the
 * reader posts beside it.
 *
 * Both sites said "across ${total} predictions" unconditionally, so the reader
 * with exactly ONE settled prediction — who is past `handleShare`'s only guard,
 * `stats.total === 0`, and is by construction the newest sharer we have —
 * posted "100% accurate across 1 predictions on Bain Luck!".
 */
export function buildScorecardShareSentence(stats: ScorecardStats): string {
  const noun = stats.total === 1 ? "prediction" : "predictions";
  return `${stats.accuracy}% accurate across ${stats.total} ${noun} on Bain Luck!`;
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
