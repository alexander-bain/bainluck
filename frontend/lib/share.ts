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
