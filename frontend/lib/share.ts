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
