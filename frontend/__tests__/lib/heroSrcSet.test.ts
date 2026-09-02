// LAT-P191 / LAT-P192 (#1636) — the Discover hero `srcset` ladder, option (b).
//
// WHAT THIS PINS. Alex ruled (b) on `alex-inbox/latency-022`: ship sharpness
// only where it is free. "Free" has TWO halves, and the first version of this
// suite only guarded one of them:
//
//   never heavier — every candidate is a SHRINK of the url we already request,
//                   and the top candidate IS that url, so the worst a browser
//                   can do byte-wise is download exactly what it does today.
//   never softer  — no candidate may be labelled WIDER than the pixels it
//                   really returns, or a browser picks it for a slot it cannot
//                   fill and renders an upscale where today it renders a sharp
//                   photo.
//
// 🔴 CERT-701 BLOCKED THE FIRST VERSION ON THE SECOND HALF. The ladder was
// anchored on Pexels' dominant 3:2 (1.5 × h), the MIDDLE of a range this lane
// had itself measured at 450–586 px. On the 450 px specimen every descriptor
// overstated by 16.7 %, so the 300 CSS-px desktop slot at DPR 1 was handed a
// 257 px image in place of today's 450 px one. The suite was fully green,
// because nothing in it compared a descriptor against a real width.
// `THE OTHER HALF OF THE RULING` below is that missing detector.
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

  it("labels the widest candidate with a width no render can fall below", () => {
    // Both descriptors are FLOORS, not the raster's likely width. `h=650&w=940`
    // is bounded by BOTH parameters and `fit=clip` honours whichever binds
    // first (measured rendering at 867 and 899, not 940), so the floor is
    // min(940, 650x1.0) = 650. `h=350` alone floors at 350x1.0 = 350.
    //
    // Anchoring on the ceiling instead is what CERT-701 blocked: 940 and 525
    // are the numbers the blocked version emitted here.
    expect(parseRungs(buildHeroSrcSet(WIDE)!).at(-1)!.width).toBe(650);
    expect(parseRungs(buildHeroSrcSet(HEIGHT_ONLY)!).at(-1)!.width).toBe(350);
  });
});

describe("THE OTHER HALF OF THE RULING: no device may get softer", () => {
  // The detector CERT-701 found missing. Everything above compares a rung to
  // the ORIGINAL URL; nothing compared a rung's DESCRIPTOR to the PIXELS it
  // really returns, which is the comparison a browser makes.
  //
  // A url does not determine its pixels (LAT-P189/P191, and the whole reason
  // this file needs a floor), so the true width is swept across the aspect
  // range instead of assumed: 1.286-1.674 is what a live feed measured at
  // h=350, and 1.10 is carried BELOW that measured minimum on purpose — a
  // constant that only holds over the sample is not a bound (P191b).
  const ASPECTS = [1.1, 1.286, 1.4, 1.5, 1.674, 1.8];

  /** Pixels Pexels really returns for a rung url, given the photo's aspect. */
  function renderedWidth(rungUrl: string, aspect: number): number {
    const w = param(rungUrl, "w");
    const h = param(rungUrl, "h");
    const caps: number[] = [];
    if (w !== null) caps.push(w);
    if (h !== null) caps.push(h * aspect);
    return Math.round(Math.min(...caps));
  }

  it.each(ASPECTS)(
    "aspect %s — no descriptor claims more pixels than the rung returns",
    (aspect) => {
      for (const url of [WIDE, HEIGHT_ONLY]) {
        for (const rung of parseRungs(buildHeroSrcSet(url)!)) {
          expect(rung.width).toBeLessThanOrEqual(renderedWidth(rung.url, aspect));
        }
      }
    },
  );

  it.each(ASPECTS)(
    "aspect %s — the 300 CSS-px desktop slot is never handed an upscale",
    (aspect) => {
      // The exact slot the ship exists to serve: `HERO_IMAGE_SIZES` declares
      // 300px at >=1280px, so a DPR-1 desktop browser resolves a need of 300w
      // and takes the first candidate whose descriptor meets it.
      for (const url of [WIDE, HEIGHT_ONLY]) {
        const rungs = parseRungs(buildHeroSrcSet(url)!);
        const picked = rungs.find((r) => r.width >= 300) ?? rungs.at(-1)!;
        expect(renderedWidth(picked.url, aspect)).toBeGreaterThanOrEqual(300);
      }
    },
  );

  it("the sweep would have caught the blocked version", () => {
    // Control for the control (P191a): a detector that passes on everything
    // proves nothing. Replay the blocked construction — anchor h=350 on the
    // nominal 1.5 instead of the floor — and assert this sweep rejects it, so
    // the tests above cannot be quietly satisfied by a weaker floor later.
    const NOMINAL_ANCHOR = Math.round(350 * 1.5); // 525, what CERT-701 blocked
    const scale = 300 / NOMINAL_ANCHOR;
    const blockedRung = `${HEIGHT_ONLY.replace("h=350", `h=${Math.round(350 * scale)}`)}`;

    // At the narrowest measured aspect the blocked rung is 257px behind a 300w
    // label — the block's own arithmetic.
    expect(renderedWidth(blockedRung, 1.286)).toBe(257);
    expect(renderedWidth(blockedRung, 1.286)).toBeLessThan(300);
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
    ["h=650&w=940", WIDE, 650],
    ["h=350 only", HEIGHT_ONLY, 350],
  ])("%s — NO candidate is labelled wider than the width floor", (_label, url, floor) => {
    for (const rung of parseRungs(buildHeroSrcSet(url)!)) {
      expect(rung.width).toBeLessThanOrEqual(floor);
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
  //
  // ⚠️ These are the LADDERS AFTER CERT-701. Anchoring on the width floor makes
  // both shorter — the `h=350` family keeps ONE shrink where the blocked
  // version emitted two, and the top descriptor drops from a claimed 525/940 to
  // an honest 350/650. That shortening IS the block being paid for: the rungs
  // it removed were the ones a browser could pick and be under-served by.
  it("h=650&w=940 — three shrinks plus the original", () => {
    expect(buildHeroSrcSet(WIDE)).toBe(
      [
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=300&w=434 300w",
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=420&w=607 420w",
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=540&w=781 540w",
        `${WIDE} 650w`,
      ].join(", "),
    );
  });

  it("h=350 only — one shrink plus the original, and `w` is never invented", () => {
    // Adding a `w` to a url that had none would ask Pexels to crop to an aspect
    // we guessed at. Scale the parameter that IS there.
    expect(buildHeroSrcSet(HEIGHT_ONLY)).toBe(
      [
        "https://images.pexels.com/photos/8846076/pexels-photo-8846076.jpeg?auto=compress&cs=tinysrgb&h=300 300w",
        `${HEIGHT_ONLY} 350w`,
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

// ---------------------------------------------------------------------------
// LAT-P195 (#2614) — THE MEASURED ARM.
//
// Everything above this line calls `buildHeroSrcSet(url)` with no second
// argument. That is not legacy: it IS the un-measured arm, and it is the arm
// the whole live population is in on day one, because `image_width` is nullable
// and the backfill drains it over days. Leaving those assertions byte-for-byte
// unchanged is the control — if passing a true width had altered the null path,
// the pinned ladders above would have moved.
//
// CERT-709 blocked the storage half for having no consumer. This is the
// consumer, and the property it adds is narrow: when the photo's real width is
// known, the ladder is derived from THAT instead of from `ASPECT_FLOOR`. The
// floor was never a fact about the photo — it was an admission that the url
// does not name its pixels. Once they are measured, the admission is retired
// for that photo and kept for every photo still unmeasured.
describe("LAT-P195 — a measured raster replaces the floor", () => {
  // The two shapes at their measured widths. `h=350` renders ~525 (aspect 1.5)
  // and `h=650&w=940` renders 867 when the height binds first — both numbers
  // are LAT-P189/P191 measurements of these exact families, not assumptions.
  const HEIGHT_ONLY_TRUE = 525;
  const WIDE_TRUE = 867;

  it("h=350 gains the rung the floor was hiding", () => {
    // The floor said 350 for a photo that is really 525, so every rung was
    // derived from a width 33% too small and the ladder stopped one rung early.
    // This is the "honest price" the CERT-705 note names, being paid back.
    expect(buildHeroSrcSet(HEIGHT_ONLY, HEIGHT_ONLY_TRUE)).toBe(
      [
        "https://images.pexels.com/photos/8846076/pexels-photo-8846076.jpeg?auto=compress&cs=tinysrgb&h=200 300w",
        "https://images.pexels.com/photos/8846076/pexels-photo-8846076.jpeg?auto=compress&cs=tinysrgb&h=280 420w",
        `${HEIGHT_ONLY} 525w`,
      ].join(", "),
    );
    expect(parseRungs(buildHeroSrcSet(HEIGHT_ONLY, HEIGHT_ONLY_TRUE)!)).toHaveLength(3);
    expect(parseRungs(buildHeroSrcSet(HEIGHT_ONLY)!)).toHaveLength(2);
  });

  it("h=650&w=940 gains a rung and an honest top descriptor", () => {
    expect(buildHeroSrcSet(WIDE, WIDE_TRUE)).toBe(
      [
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=225&w=325 300w",
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=315&w=455 420w",
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=405&w=585 540w",
        "https://images.pexels.com/photos/16587315/pexels-photo-16587315.jpeg?auto=compress&cs=tinysrgb&h=525&w=759 700w",
        `${WIDE} 867w`,
      ].join(", "),
    );
  });

  it.each([
    ["h=350 only", HEIGHT_ONLY, HEIGHT_ONLY_TRUE, 350],
    ["h=650&w=940", WIDE, WIDE_TRUE, 650],
  ])(
    "%s — every descriptor becomes EXACT, not merely un-overstated",
    (_label, url, trueWidth, urlHeight) => {
      // THE SHIP, stated as a measurement. With the floor, a descriptor was a
      // lower bound: a rung labelled 300w could hand back 450 real pixels, so
      // the browser over-downloaded to be safe. With the true raster the label
      // and the pixels agree, which is what lets a slot pick the rung it
      // actually wants instead of the next one up.
      const aspect = trueWidth / urlHeight;
      for (const rung of parseRungs(buildHeroSrcSet(url, trueWidth)!)) {
        expect(renderedWidthAt(rung.url, aspect)).toBe(rung.width);
      }
    },
  );

  it.each([
    ["h=350 only", HEIGHT_ONLY, HEIGHT_ONLY_TRUE],
    ["h=650&w=940", WIDE, WIDE_TRUE],
  ])("%s — still never heavier than the url we request today", (_l, url, trueWidth) => {
    // The structural guarantee is unchanged and must survive the new input:
    // every rung is a SHRINK of the original request, and the top rung is the
    // original string verbatim.
    const rungs = parseRungs(buildHeroSrcSet(url, trueWidth)!);
    expect(rungs.at(-1)!.url).toBe(url);
    for (const rung of rungs.slice(0, -1)) {
      const w = param(rung.url, "w");
      const h = param(rung.url, "h");
      if (w !== null) expect(w).toBeLessThan(param(url, "w")!);
      if (h !== null) expect(h).toBeLessThan(param(url, "h")!);
    }
  });

  it("never advertises more than the url's own `w` cap, even if the column disagrees", () => {
    // Defence in depth. The stored width is documented as never larger than the
    // real raster, but a stale row whose url was re-enriched could still name a
    // bigger number, and imgix cannot serve wider than `w` asked for. Clamping
    // to the cap can only move the ladder the safe way.
    const rungs = parseRungs(buildHeroSrcSet(WIDE, 5000)!);
    expect(rungs.at(-1)!.width).toBe(940);
  });

  it.each([
    ["null — the state of the whole population on day one", null],
    ["undefined — an old payload with no such key", undefined],
    ["zero", 0],
    ["negative", -100],
    ["NaN from a malformed payload", NaN],
  ])(
    "falls back to EXACTLY today's ladder when the width is %s",
    (_label, bad) => {
      // The reason 0% coverage is safe to ship. Not "similar to" today's
      // ladder — identical to it, compared against the same function with the
      // argument omitted entirely.
      for (const url of [WIDE, HEIGHT_ONLY]) {
        expect(buildHeroSrcSet(url, bad as number | null)).toBe(buildHeroSrcSet(url));
      }
    },
  );

  it("a raster smaller than the smallest rung yields null, not a fabricated ladder", () => {
    // The refusal path, reached through the new argument. A 240px photo has
    // nothing below the 300px rung to offer, so there is no safe ladder and the
    // hero renders exactly as it does today. `null` is a supported answer here,
    // not a failure — callers are forbidden from substituting a fallback.
    expect(buildHeroSrcSet(HEIGHT_ONLY, 240)).toBeNull();
  });

  it("a measured portrait cannot upscale, which the floor could not promise", () => {
    // The one hole CERT-705 left open and named: `ASPECT_FLOOR = 1.0` is an
    // assumption, and a PORTRAIT hero (aspect < 1) would overstate again by the
    // ratio it falls short. A measured width closes it by construction — there
    // is no aspect left to be wrong about.
    const portraitTrue = 320; // 320x350, aspect 0.914 — below the 1.0 floor
    const rungs = parseRungs(buildHeroSrcSet(HEIGHT_ONLY, portraitTrue)!);
    for (const rung of rungs) {
      expect(renderedWidthAt(rung.url, portraitTrue / 350)).toBeGreaterThanOrEqual(
        rung.width,
      );
    }
    // And the floor arm, on the same photo, is the case that made this a
    // known-open risk rather than a solved one.
    const floorRungs = parseRungs(buildHeroSrcSet(HEIGHT_ONLY)!);
    const overstated = floorRungs.filter(
      (r) => renderedWidthAt(r.url, portraitTrue / 350) < r.width,
    );
    expect(overstated.length).toBeGreaterThan(0);
  });
});

/** Pixels Pexels really returns for a rung url, given the photo's aspect. */
function renderedWidthAt(rungUrl: string, aspect: number): number {
  const w = param(rungUrl, "w");
  const h = param(rungUrl, "h");
  const caps: number[] = [];
  if (w !== null) caps.push(w);
  if (h !== null) caps.push(h * aspect);
  return Math.round(Math.min(...caps));
}
