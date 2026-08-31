/**
 * UX-P235 — A WRONG LOGO IS WORSE THAN NO LOGO (board item 14).
 *
 * ═══ WHAT ALEX SAW, AND WHAT HE LIKED ═══
 *
 * On `/futures/109441` the outcome rows try to show each company's logo. Alex,
 * verbatim: *"love that when I click in it tries to show logos for the companies."*
 * **The ambition stays.** What he also saw: Amazon as a generic grey "A", Max as a
 * generic "M", Netflix as a photographic blob, Disney as a squashed wordmark.
 *
 * ═══ 🔴 THE BOARD ITEM UNDERSTATES IT, AND THE MEASUREMENT CHANGES THE FIX ═══
 *
 * The item says *"Peacock, Hulu, Paramount+ and Apple resolve correctly."* Measured
 * live against the real Wikipedia summary API on 2026-08-31, they do not:
 *
 *   | outcome    | what Wikipedia returns                    | verdict            |
 *   |------------|-------------------------------------------|--------------------|
 *   | Amazon     | disambiguation, no image                  | honest blank       |
 *   | Max        | disambiguation, no image                  | honest blank       |
 *   | Netflix    | `Netflix_UI_for_Web.png`                  | a UI SCREENSHOT    |
 *   | Disney     | `The_Walt_Disney_company_logo.svg` 330x171| right, mis-cropped |
 *   | Hulu       | `Hulu_logo_(2018).svg`                    | ✅ correct         |
 *   | Paramount+ | `Paramount_Plus.svg`                      | ✅ correct         |
 *   | 🔴 Peacock | `Peacock_Plumage.jpg`, title **"Peafowl"**| **A BIRD**         |
 *   | 🔴 Apple   | `Pink_lady_and_cross_section.jpg`         | **A FRUIT**        |
 *
 * **Two of the eight were ever right.** Peacock and Apple were not "correct" — they
 * were a photograph of a bird and a photograph of a fruit, rendered as confident
 * circular brand marks beside a streaming-service probability. That is the most
 * literal possible instance of the item's own rule: *a wrong logo is worse than no
 * logo.*
 *
 * ═══ THE MECHANISM ═══
 *
 * `getWikipediaImage` asks *"what does this NAME look like?"* when the caller means
 * *"what does this BRAND look like?"*. A bare market-outcome name is frequently a
 * common noun, so the question has a confident wrong answer.
 *
 * ═══ THE FIX, AND ITS LIMIT ═══
 *
 * Refuse the answers **Wikipedia's own metadata marks as not-a-brand**, using fields
 * already present in the response we fetch — no second request, on a page that
 * renders 25 of these. We cannot prove a page IS a brand; we can prove a page is a
 * bird, and that is enough to stop printing one.
 *
 * The Netflix screenshot survives this fix and is named rather than hidden: its
 * description reads "American video streaming service", which is true. Fixing that
 * one needs Wikidata's **P154 "logo image"** — measured working (`Netflix -> Netflix
 * logo.svg`, `Disney -> The Walt Disney Company Logo.svg`, `Peacock`/`Apple` correctly
 * none) but requiring a second network hop per outcome, on a day when cold-load
 * latency is a named priority. Deliberate follow-up, in the report.
 */

import {
  __resetWikipediaLookupState,
  getWikipediaImage,
  wikipediaSummaryIsNotABrand,
} from "@/lib/images";

/**
 * VERBATIM fields from `en.wikipedia.org/api/rest_v1/page/summary/<name>`, captured
 * 2026-08-31 for the eight outcomes of market 109441 — the market Alex reviewed.
 */
const LIVE_109441 = {
  Amazon: { type: "disambiguation", description: "Topics referred to by the same term" },
  Max: { type: "disambiguation", description: "Topics referred to by the same term" },
  Netflix: { type: "standard", description: "American video streaming service" },
  Disney: { type: "standard", description: "American media and entertainment conglomerate" },
  Peacock: { type: "standard", description: "Group of large game birds" },
  Hulu: { type: "standard", description: "American video streaming service" },
  "Paramount+": { type: "standard", description: "American video streaming service" },
  Apple: { type: "standard", description: "Edible fruit" },
} as const;

describe("UX-P235: the eight outcomes Alex actually looked at", () => {
  test("🔴 Peacock is refused — it is a BIRD, and the board item called it correct", () => {
    expect(wikipediaSummaryIsNotABrand(LIVE_109441.Peacock)).toBe(true);
  });

  test("🔴 Apple is refused — it is a FRUIT, and the board item called it correct", () => {
    expect(wikipediaSummaryIsNotABrand(LIVE_109441.Apple)).toBe(true);
  });

  test("Amazon and Max are refused — Wikipedia itself says the name is ambiguous", () => {
    expect(wikipediaSummaryIsNotABrand(LIVE_109441.Amazon)).toBe(true);
    expect(wikipediaSummaryIsNotABrand(LIVE_109441.Max)).toBe(true);
  });

  test("the four real companies are KEPT — the ambition is not thrown away", () => {
    // This is the half that matters most. Alex likes that the page tries; a fix
    // that refused everything would "pass" the wrong-logo test and lose the ship.
    for (const name of ["Netflix", "Disney", "Hulu", "Paramount+"] as const) {
      expect(wikipediaSummaryIsNotABrand(LIVE_109441[name])).toBe(false);
    }
  });

  test("exactly four of the eight are refused — the count is pinned", () => {
    const refused = Object.entries(LIVE_109441)
      .filter(([, s]) => wikipediaSummaryIsNotABrand(s))
      .map(([n]) => n);
    expect(refused.sort()).toEqual(["Amazon", "Apple", "Max", "Peacock"]);
  });
});

describe("UX-P235: the refusal does not reach past brands", () => {
  test("a racehorse keeps its picture, though its NAME may be an animal", () => {
    // The obvious way to over-correct. A horse called "Nijinsky" or "Sea The
    // Stars" is a legitimate outcome; its page is a racehorse, not a species.
    expect(
      wikipediaSummaryIsNotABrand({ type: "standard", description: "Irish-bred Thoroughbred racehorse" }),
    ).toBe(false);
  });

  test("a person keeps their photo", () => {
    for (const description of [
      "American actress",
      "President of the United States",
      "Spanish tennis player",
      "English association football player",
    ]) {
      expect(wikipediaSummaryIsNotABrand({ type: "standard", description })).toBe(false);
    }
  });

  test("a sports team keeps its crest", () => {
    for (const description of [
      "Association football club in England",
      "American football team",
      "Baseball team of Major League Baseball",
    ]) {
      expect(wikipediaSummaryIsNotABrand({ type: "standard", description })).toBe(false);
    }
  });

  test("a film, a band and a country are all kept", () => {
    for (const description of [
      "2023 film by Greta Gerwig",
      "English rock band",
      "Country in Western Europe",
      "2024 studio album",
    ]) {
      expect(wikipediaSummaryIsNotABrand({ type: "standard", description })).toBe(false);
    }
  });

  test("a hurricane keeps its image even though it is a natural phenomenon", () => {
    // Weather markets are a real surface here. A tropical cyclone is not a brand,
    // but it IS the outcome, and its satellite image is the right picture for it.
    expect(
      wikipediaSummaryIsNotABrand({ type: "standard", description: "Atlantic tropical cyclone in 2024" }),
    ).toBe(false);
  });
});

describe("UX-P235: the refusal catches the natural-kind classes it claims to", () => {
  test("species and genus pages are refused", () => {
    for (const description of [
      "Species of bird",
      "Species of flowering plant",
      "Genus of fishes",
      "Family of mammals",
    ]) {
      expect(wikipediaSummaryIsNotABrand({ type: "standard", description })).toBe(true);
    }
  });

  test("a bare given name or surname page is refused", () => {
    // These have no image worth showing and are a common resolution for one-word
    // outcome names.
    for (const description of ["Given name", "Surname", "Family name"]) {
      expect(wikipediaSummaryIsNotABrand({ type: "standard", description })).toBe(true);
    }
  });

  test("a chemical element is refused", () => {
    expect(
      wikipediaSummaryIsNotABrand({ type: "standard", description: "Chemical element with atomic number 79" }),
    ).toBe(true);
  });
});

describe("UX-P235: absence is never read as a verdict", () => {
  test("no description ⇒ not refused — we cannot prove it is wrong", () => {
    // gotcha #53. A missing description is silence, not evidence that the page is
    // a bird; refusing on it would throw away every page Wikipedia has not
    // short-described, which is a coverage loss dressed as caution.
    expect(wikipediaSummaryIsNotABrand({ type: "standard", description: null })).toBe(false);
    expect(wikipediaSummaryIsNotABrand({ type: "standard" })).toBe(false);
    expect(wikipediaSummaryIsNotABrand({})).toBe(false);
    expect(wikipediaSummaryIsNotABrand({ type: "standard", description: "   " })).toBe(false);
  });

  test("a disambiguation with NO description is still refused", () => {
    // The `type` is Wikipedia stating the ambiguity outright — that is presence,
    // not absence, and it stands on its own.
    expect(wikipediaSummaryIsNotABrand({ type: "disambiguation" })).toBe(true);
  });

  test("matching is case-insensitive, because the field is not normalised", () => {
    expect(wikipediaSummaryIsNotABrand({ type: "standard", description: "SPECIES OF BIRD" })).toBe(true);
    expect(wikipediaSummaryIsNotABrand({ type: "standard", description: "edible fruit" })).toBe(true);
  });
});

describe("UX-P235: the RESOLVER actually consults the refusal", () => {
  /**
   * 🔴 THE TEST THIS FILE WAS MISSING, AND THE BATTERY FOUND IT.
   *
   * Every assertion above exercises the pure predicate. None of them proved that
   * `getWikipediaImage` ever CALLS it — so deleting the call site from the resolver
   * survived the whole battery while putting the bird straight back on the page.
   *
   * That is the third time this session that a correct helper sat beside a caller
   * that never asked it anything: CERT-598 (a correct `pickHeroOutcome` beside a
   * sort that could not see it) and UX-P233's `movementLabel` (a prop no caller had
   * ever passed) are the same shape. **A predicate is not a behaviour until
   * something invokes it.**
   *
   * `testEnvironment` is `node`, so there is no `localStorage` and the module's
   * cache is a no-op here — every call really goes through the fetch path.
   */
  const realFetch = global.fetch;

  function serve(body: Record<string, unknown>) {
    global.fetch = (async () => ({
      ok: true,
      json: async () => body,
    })) as unknown as typeof fetch;
  }

  beforeEach(() => {
    __resetWikipediaLookupState();
  });

  afterAll(() => {
    global.fetch = realFetch;
  });

  test("🔴 a BIRD is refused by the resolver, not merely by the predicate", () => {
    serve({
      type: "standard",
      title: "Peafowl",
      description: "Group of large game birds",
      thumbnail: { source: "https://upload.wikimedia.org/Peacock_Plumage.jpg" },
    });
    return expect(getWikipediaImage("Peacock")).resolves.toBeNull();
  });

  test("🔴 a FRUIT is refused by the resolver", () => {
    serve({
      type: "standard",
      title: "Apple",
      description: "Edible fruit",
      thumbnail: { source: "https://upload.wikimedia.org/Pink_lady.jpg" },
    });
    return expect(getWikipediaImage("Apple")).resolves.toBeNull();
  });

  test("a disambiguation is refused by the resolver", () => {
    serve({ type: "disambiguation", description: "Topics referred to by the same term" });
    return expect(getWikipediaImage("Amazon")).resolves.toBeNull();
  });

  test("a REAL company still gets its image — the ambition survives the resolver too", () => {
    // The control that stops "refuse everything" reading as a pass.
    serve({
      type: "standard",
      title: "Hulu",
      description: "American video streaming service",
      thumbnail: { source: "https://upload.wikimedia.org/Hulu_logo.svg.png" },
    });
    return expect(getWikipediaImage("Hulu")).resolves.toBe(
      "https://upload.wikimedia.org/Hulu_logo.svg.png",
    );
  });

  test("a kept page with no thumbnail is null, and that is not a refusal", () => {
    serve({ type: "standard", title: "Some Co", description: "American company" });
    return expect(getWikipediaImage("Some Co")).resolves.toBeNull();
  });
});
