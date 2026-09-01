// LAT-P191 (#1636) — the Discover hero `srcset` ladder, option (b).
//
// WHAT THIS PINS. Alex ruled (b) on `alex-inbox/latency-022`: ship sharpness
// only where it is free. The whole safety of that ruling rests on ONE property
// — every candidate is a SHRINK of the url we already request, and the top
// candidate IS that url — so the worst a browser can do is download exactly
// what it downloads today. If a future edit adds a rung above the native
// raster, a DPR-3 phone gets up to 197% heavier (LAT-P189, n=48, priced in the
// AVIF bytes a browser actually receives) and the ruling is silently reversed.
// The `never wider than the original` test below is that reversal alarm.
//
// The two url shapes are verbatim from a live `/api/feed?limit=40` on
// 2026-09-01 (50 heroes: 34 `h=350`-only, 16 `h=650&w=940`).

import { buildHeroSrcSet, HERO_IMAGE_SIZES } from "@/lib/discover/heroSrcSet";

const WIDE =
  "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=650&w=940";
const HEIGHT_ONLY =
  "https://images.pexels.com/photos/8846076/pexels-photo-8846076.jpeg?auto=compress&cs=tinysrgb&h=350";

type Rung = { url: string; width: number };

function parseRungs(srcSet: string): Rung[] {
  return srcSet.split(", ").map((entry) => {
    const at = entry.lastIndexOf(" ");
    const url = entry.slice(0, at);
    const descriptor = entry.slice(at + 1);
    expect(descriptor).toMatch(/^\d+w$/);
    return { url, width: Number(descriptor.slice(0, -1)) };
  });
}

function param(url: string, key: string): number | null {
  const raw = new URL(url).searchParams.get(key);
  return raw === null ? null : Number(raw);
}

describe("buildHeroSrcSet — the ladder is built at all", () => {
  it("builds candidates for both url shapes the feed actually serves", () => {
    expect(buildHeroSrcSet(WIDE)).not.toBeNull();
    expect(buildHeroSrcSet(HEIGHT_ONLY)).not.toBeNull();
  });

  it("labels the widest candidate with the raster we already serve", () => {
    // `w=940` is stated in the url; `h=350` has no width in it at all, so the
    // descriptor is the nominal 1.5x (Pexels' dominant 3:2). Both are ceilings.
    expect(parseRungs(buildHeroSrcSet(WIDE)!).at(-1)!.width).toBe(940);
    expect(parseRungs(buildHeroSrcSet(HEIGHT_ONLY)!).at(-1)!.width).toBe(525);
  });
});

describe("buildHeroSrcSet — THE RULING: no device may get heavier", () => {
  it.each([
    ["h=650&w=940", WIDE],
    ["h=350 only", HEIGHT_ONLY],
  ])("%s — the top candidate is the ORIGINAL url, byte-identical", (_label, url) => {
    // Not merely equivalent: the same string, so it is the same CDN cache
    // entry and the same transfer a phone already pays for today.
    expect(parseRungs(buildHeroSrcSet(url)!).at(-1)!.url).toBe(url);
  });

  it.each([
    ["h=650&w=940", WIDE],
    ["h=350 only", HEIGHT_ONLY],
  ])("%s — every other candidate scales the dimension parameters DOWN", (_label, url) => {
    const original = { w: param(url, "w"), h: param(url, "h") };
    const rungs = parseRungs(buildHeroSrcSet(url)!);
    for (const rung of rungs.slice(0, -1)) {
      if (original.w !== null) expect(param(rung.url, "w")!).toBeLessThan(original.w);
      if (original.h !== null) expect(param(rung.url, "h")!).toBeLessThan(original.h);
      // A rung that dropped a dimension parameter would ask Pexels for the
      // full-size photo — the exact way this ship would invert itself.
      if (original.w !== null) expect(param(rung.url, "w")).not.toBeNull();
      if (original.h !== null) expect(param(rung.url, "h")).not.toBeNull();
    }
  });

  it.each([
    ["h=650&w=940", WIDE, 940],
    ["h=350 only", HEIGHT_ONLY, 525],
  ])("%s — NO candidate is labelled wider than the native raster", (_label, url, native) => {
    for (const rung of parseRungs(buildHeroSrcSet(url)!)) {
      expect(rung.width).toBeLessThanOrEqual(native);
    }
  });

  it.each([
    ["h=650&w=940", WIDE],
    ["h=350 only", HEIGHT_ONLY],
  ])("%s — descriptors ascend, so the browser's pick is well defined", (_label, url) => {
    const widths = parseRungs(buildHeroSrcSet(url)!).map((r) => r.width);
    expect(widths).toEqual([...widths].sort((a, b) => a - b));
    expect(new Set(widths).size).toBe(widths.length);
  });

  it("scales the two dimensions by the SAME factor, so the crop does not move", () => {
    // object-cover would hide a changed aspect, but a changed aspect also
    // changes the byte count in a way the ladder's arithmetic did not price.
    const rungs = parseRungs(buildHeroSrcSet(WIDE)!);
    for (const rung of rungs) {
      const ratio = param(rung.url, "w")! / param(rung.url, "h")!;
      expect(ratio).toBeCloseTo(940 / 650, 2);
    }
  });
});

describe("the exact urls this ship puts on the wire", () => {
  // Pinned verbatim because they are the strings LAT-P191 fetched from Pexels
  // to price the ship. A change here is a change to a measured artifact, not a
  // refactor: re-measure before re-baselining.
  //
  // Measured 2026-09-01, `Content-Type: image/avif` confirmed on every one
  // (⚠️ a default `Accept` gets JPEG, a format no browser receives — harness
  // trap 4; every byte below was fetched with a browser `Accept`/`User-Agent`):
  //   940w 26,410 B (today) · 700w 16,881 · 540w 11,520 · 420w 8,131 · 300w 5,042
  //   525w  9,219 B (today) · 420w  7,080 · 300w 5,049
  // Monotone in both ladders, which is the empirical half of the guarantee the
  // suite above proves structurally.
  it("h=650&w=940 — four shrinks plus the original", () => {
    expect(buildHeroSrcSet(WIDE)).toBe(
      [
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=207&w=300 300w",
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=290&w=420 420w",
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=373&w=540 540w",
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=484&w=700 700w",
        `${WIDE} 940w`,
      ].join(", "),
    );
  });

  it("h=350 only — two shrinks plus the original, and `w` is never invented", () => {
    // Adding a `w` to a url that had none would ask Pexels to crop to an aspect
    // we guessed at. Scale the parameter that IS there.
    expect(buildHeroSrcSet(HEIGHT_ONLY)).toBe(
      [
        "https://images.pexels.com/photos/8846076/pexels-photo-8846076.jpeg?auto=compress&cs=tinysrgb&h=200 300w",
        "https://images.pexels.com/photos/8846076/pexels-photo-8846076.jpeg?auto=compress&cs=tinysrgb&h=280 420w",
        `${HEIGHT_ONLY} 525w`,
      ].join(", "),
    );
  });
});

describe("buildHeroSrcSet — refuses rather than guesses", () => {
  it("returns null for a host whose scaling parameters we do not know", () => {
    expect(
      buildHeroSrcSet("https://cdn.example.com/photo.jpg?auto=compress&h=350"),
    ).toBeNull();
  });

  it("returns null when the url carries no dimension to scale", () => {
    expect(
      buildHeroSrcSet("https://images.pexels.com/photos/1/pexels-photo-1.jpeg?auto=compress"),
    ).toBeNull();
  });

  it("returns null when the raster is already smaller than the smallest rung", () => {
    // 200px wide: there is nothing to save and a ladder would only add bytes
    // to the document.
    expect(
      buildHeroSrcSet("https://images.pexels.com/photos/1/pexels-photo-1.jpeg?w=200"),
    ).toBeNull();
  });

  it("returns null for a string that is not a url", () => {
    expect(buildHeroSrcSet("/local/placeholder.png")).toBeNull();
    expect(buildHeroSrcSet("")).toBeNull();
  });
});

describe("HERO_IMAGE_SIZES tracks the Discover masonry", () => {
  // If the grid in app/discover/page.tsx changes and this does not, `sizes`
  // overstates the slot and the responsive image gets HEAVIER than the fixed
  // one it replaced. Breakpoints here are Tailwind's sm/lg/xl, and the
  // subtractions are `px-4` page padding plus `gap-4` gutters.
  it("names the four column counts the grid actually renders", () => {
    expect(HERO_IMAGE_SIZES).toContain("(min-width: 1280px) 300px");
    expect(HERO_IMAGE_SIZES).toContain("(min-width: 1024px) calc((100vw - 64px) / 3)");
    expect(HERO_IMAGE_SIZES).toContain("(min-width: 640px) calc((100vw - 48px) / 2)");
    expect(HERO_IMAGE_SIZES.endsWith("calc(100vw - 32px)")).toBe(true);
  });

  it("the four-column slot is 300 CSS px — the number the desktop saving rests on", () => {
    // max-w-7xl (1280) - px-4 both sides (32) - 3 gutters of 16 = 1200 / 4.
    expect((1280 - 32 - 3 * 16) / 4).toBe(300);
  });
});
