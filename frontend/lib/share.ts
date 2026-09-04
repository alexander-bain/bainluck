const DEFAULT_SITE_URL = "https://bainluck.com";

export type ShareContentType = "event" | "futures" | "grid";

function getSiteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || DEFAULT_SITE_URL).replace(/\/$/, "");
}

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
