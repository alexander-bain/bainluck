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
// 🔴 CERT-701 BLOCKED THE FIRST VERSION OF THIS FILE, AND IT WAS RIGHT.
// The text that stood here argued that a descriptor which OVERSTATES the true
// width is safe, because it "can only make the browser pick a SMALLER rung than
// it strictly needs — softer or equal, never heavier". That priced one half of
// the ruling and dropped the other. Softer is not free: it is the desktop hero
// getting visibly worse than the one we ship today.
//
// The arithmetic, reproduced from the block. Pexels serves two url shapes,
// `?…&h=650&w=940` and `?…&h=350`, and for the second the width is NOT in the
// url — it is whatever the photo's aspect makes it. LAT-P191 measured that
// family at 450–586 px across a live feed and then anchored the ladder on the
// MIDDLE of its own range (1.5 × h = 525, Pexels' dominant 3:2). On the 450 px
// specimen every descriptor then overstated by 16.7 %, so the rung advertised
// as `300w` is really 257 px — and a 300 CSS-px four-column desktop slot at
// DPR 1 picks it and renders an UPSCALED 257 px where today it downloads a
// sharp 450 px. Strictly worse, on the exact slot the ship was built to serve.
//
// P189a was already on the books — *verify the requirement by the EXTREMUM of
// its range* — and this file's own comment quoted the range while the constant
// beside it used the midpoint.
//
// THE REPAIR: ANCHOR ON A LOWER BOUND, NEVER A TYPICAL VALUE.
// `ASPECT_FLOOR` is the narrowest aspect a hero is assumed to have, so
// `h × ASPECT_FLOOR` is the smallest width the url can render, and taking the
// MIN of that with any stated `w` gives a width no render can fall below. Every
// descriptor is then derived from that floor, so descriptors UNDER-state. A
// browser resolving `sizes` picks the first rung whose descriptor meets its
// need; if the descriptor under-states, the pixels it actually receives are
// greater than or equal to what it asked for. Upscaling becomes unreachable —
// not unlikely, unreachable — for any photo at or above the floor.
//
// Priced across the aspect range, 300 CSS-px slot at DPR 1, h=350 family:
//   anchor 1.5   (shipped, blocked)  worst descriptor +36.4 % over true width;
//                                    upscales at every aspect below 1.5
//   anchor 1.286 (the measured MIN)  worst +17.2 %; still upscales at 1.10
//   anchor 1.0   (this file)         worst −9.1 % — never overstates, never
//                                    upscales, no rung heavier than the original
// Note the middle row: even the measured minimum is not a bound, because a
// measurement is only true of what it measured (P191b). 1.0 is chosen because
// it is an ASSUMPTION WITH MARGIN — 29 % below the narrowest hero yet observed —
// and because the failure mode of choosing it too low is that the ladder empties
// and `buildHeroSrcSet` returns null, i.e. exactly today's behaviour, rather
// than a wrong ladder. It is stated as an assumption, not proven as a law: a
// PORTRAIT hero (aspect < 1) would overstate again by the ratio it falls short.
//
// ⚠️ THE HONEST PRICE. Anchoring low shortens every ladder — the h=350 family
// drops from two shrink-rungs to one, and the desktop saving is smaller than the
// number LAT-P191 banked, because part of that number was the upscale. What
// removes the price rather than paying it is knowing each raster's TRUE pixel
// dimensions, which the API does not store. That is the same backend change
// option (a) needs (#1636), so both halves of the hero work now converge on it.

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

/**
 * The narrowest aspect (width ÷ height) a Discover hero is assumed to have.
 *
 * A FLOOR, not an average — see the CERT-701 note at the top of this file. It
 * exists so `h × ASPECT_FLOOR` is a width no render of that url can fall below,
 * which is what makes every descriptor an under-statement. Lowering it is
 * always safe (shorter ladders, eventually none); raising it towards the
 * observed 1.286–1.674 is what CERT-701 blocked.
 */
const ASPECT_FLOOR = 1.0;

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

  // The smallest width this url can possibly render. `w` caps the render; so
  // does `h`, via the photo's aspect, and `fit=clip` honours WHICHEVER binds
  // first — which is why a `w=940&h=650` url was measured rendering at 867 and
  // 899 px (LAT-P191). Taking the MIN of the bounds that are present is the
  // only combination that no render can fall below.
  const bounds: number[] = [];
  if (width !== null) bounds.push(width);
  if (height !== null) bounds.push(Math.round(height * ASPECT_FLOOR));
  if (bounds.length === 0) return null;
  const floorWidth = Math.min(...bounds);

  const smaller = CANDIDATE_WIDTHS.filter((candidate) => candidate < floorWidth);
  if (smaller.length === 0) return null;

  const rungs = smaller.map((candidate) => {
    const scale = candidate / floorWidth;
    const scaled = new URL(parsed.toString());
    if (width !== null) scaled.searchParams.set("w", String(Math.max(1, Math.round(width * scale))));
    if (height !== null) scaled.searchParams.set("h", String(Math.max(1, Math.round(height * scale))));
    return `${scaled.toString()} ${candidate}w`;
  });

  // The top rung is the original string verbatim: same url, same cache entry,
  // same bytes as today — that is the "never heavier" half. Its descriptor is
  // `floorWidth`, NOT the width it probably renders at, which is the "never
  // softer" half: a browser that needs more than `floorWidth` has nothing above
  // this rung to climb to, and picking it hands back at least `floorWidth` real
  // pixels by the definition of the floor.
  rungs.push(`${url} ${floorWidth}w`);
  return rungs.join(", ");
}
