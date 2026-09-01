// Responsive candidates for the Discover hero photo. LAT-P191 (#1636),
// Alex ruling on `alex-inbox/latency-022` — option (b).
//
// The measurement that produced this (LAT-P189, n=48 live heroes, real pixel
// dimensions read from the image bytes rather than trusted from the URL):
// NOT ONE hero is sharp on a retina screen. The card renders up to 607 CSS px
// wide (639 px viewport, one column), which wants 1214 device px at DPR 2, and
// the widest raster we serve is 940 px — two thirds are ~525 px. Meanwhile the
// four-column desktop slot is 300 CSS px and downloads the same 525–940 px
// raster, so a desktop reader pays for pixels the layout throws away.
//
// Both halves are the same missing attribute: the <img> has no `srcset`, so
// every device requests the one raster the API happened to store.
//
// Alex ruled (b): SHIP SHARPNESS ONLY WHERE IT IS FREE. Adding rungs ABOVE
// today's raster would make a DPR-3 phone up to 197% heavier (priced on the
// same 48 images, in the AVIF bytes a browser actually receives), and mobile
// cold load is the thing this lane has spent fourteen cycles lightening. So the
// ladder is capped at the raster we already serve and every rung is derived by
// SHRINKING the original request. Desktop gets materially lighter; a phone
// keeps exactly today's bytes and exactly today's softness. Option (a) —
// sharp-on-retina-phones — stays open for a later call and is noted on #1636.
//
// THE STRICTNESS GUARANTEE, and why it does not depend on any measurement:
// the top rung is the ORIGINAL url, byte-identical, and every other rung is the
// same url with its dimension parameters scaled DOWN by the same factor. So the
// worst a browser can do is pick the rung it already downloads today. No device
// gets heavier — structurally, not empirically.
//
// ⚠️ WHY THE `w` DESCRIPTORS CAN BE NOMINAL. Pexels serves two url shapes:
// `?…&h=650&w=940` (width known) and `?…&h=350` (width NOT in the url — it is
// whatever the photo's aspect makes it; measured 450–586 px across a live
// feed). For the second shape the descriptor is a nominal 1.5×h, Pexels'
// dominant 3:2. A nominal that overstates the true width can only make the
// browser pick a SMALLER rung than it strictly needs — softer or equal, never
// heavier — because every rung is a shrink of the same original. That is why
// this file does not need to know the true pixel width to stay safe.

/**
 * The Discover masonry is `columns-1 sm:columns-2 lg:columns-3 xl:columns-4
 * gap-4` inside `max-w-7xl mx-auto px-4` (`app/discover/page.tsx`). Slot width
 * per breakpoint, gutters and page padding subtracted:
 *
 *   >= 1280px  container caps at 1280 - 32 padding = 1248; 4 cols, 3x16 gap  -> 300px flat
 *   >= 1024px  3 cols, 2x16 gap   -> (100vw - 32 - 32) / 3
 *   >=  640px  2 cols, 1x16 gap   -> (100vw - 32 - 16) / 2
 *   <   640px  1 col              ->  100vw - 32
 *
 * Keep this in step with that grid — a `sizes` that overstates the slot is how
 * a responsive image quietly gets heavier than the fixed one it replaced.
 */
export const HERO_IMAGE_SIZES =
  "(min-width: 1280px) 300px, " +
  "(min-width: 1024px) calc((100vw - 64px) / 3), " +
  "(min-width: 640px) calc((100vw - 48px) / 2), " +
  "calc(100vw - 32px)";

/**
 * Candidate widths, in device pixels. Chosen against the slot widths the grid
 * above actually produces (300 / 405 / 487 / 607 CSS px) at DPR 1 and 2, then
 * kept to five rungs so 40 cards of `srcset` stay small in the document.
 * Rungs at or above a url's own raster are dropped, so this is a ceiling list,
 * never a floor.
 */
const CANDIDATE_WIDTHS = [300, 420, 540, 700, 940];

/** Pexels' dominant aspect: a `h=350`-only url renders ~525 px wide. Nominal. */
const NOMINAL_ASPECT = 1.5;

function readIntParam(params: URLSearchParams, key: string): number | null {
  const raw = params.get(key);
  if (raw === null) return null;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
}

/**
 * Build a `srcset` for a Discover hero url, or `null` when there is nothing
 * safe to build — an unrecognised host, no dimension parameter to scale, or a
 * raster already smaller than the smallest rung. `null` means "render exactly
 * as before"; callers must not fabricate a fallback.
 */
export function buildHeroSrcSet(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  // Only Pexels: these scaling parameters are its contract, and guessing at
  // another CDN's is how you request a raster that does not exist.
  if (parsed.hostname !== "images.pexels.com") return null;

  const width = readIntParam(parsed.searchParams, "w");
  const height = readIntParam(parsed.searchParams, "h");
  const nominalWidth = width ?? (height !== null ? Math.round(height * NOMINAL_ASPECT) : null);
  if (nominalWidth === null) return null;

  const smaller = CANDIDATE_WIDTHS.filter((candidate) => candidate < nominalWidth);
  if (smaller.length === 0) return null;

  const rungs = smaller.map((candidate) => {
    const scale = candidate / nominalWidth;
    const scaled = new URL(parsed.toString());
    if (width !== null) scaled.searchParams.set("w", String(Math.max(1, Math.round(width * scale))));
    if (height !== null) scaled.searchParams.set("h", String(Math.max(1, Math.round(height * scale))));
    return `${scaled.toString()} ${candidate}w`;
  });

  // The top rung is the original string verbatim: same url, same cache entry,
  // same bytes as today. This is the line that makes the guarantee above true.
  rungs.push(`${url} ${nominalWidth}w`);
  return rungs.join(", ");
}
