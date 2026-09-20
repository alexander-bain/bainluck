/**
 * #7461 — A /play CARD MAY NOT PAINT A PICTURE THE GATE CANNOT READ.
 *
 * ═══ THE LIVE LEAK ═══
 *
 * Measured on production 2026-09-20 (`GET /api/feed?limit=120&offset=0&
 * event_pct=0.3&include_futures=true&include_events=true` — the exact params
 * `usePlayPool`'s `defaultFetchPage` uses):
 *
 *     "Resident Evil" Opening Weekend Box Office
 *       llm_sport_category  entertainment      → allowlisted
 *       outcomes            55-60m, 60-65m, 65-70m
 *       isPlayEligible      true
 *       image_url           image.tmdb.org/t/p/w1280/1CIaRYKf3zg2Xyce1CSfCMg2Vfw.jpg
 *
 * Every text check passes — "evil" is on neither list and the outcomes are
 * box-office buckets — and `CoolOrBoring` then paints that poster full-bleed
 * across a 224px hero on a card built for an eight-year-old. The poster is a
 * horror still.
 *
 * ═══ WHY THE TEXT GATE CANNOT BE HARDENED INTO COVERING IT ═══
 *
 * L2-178 was the same class in the text channel (a blocked OUTCOME label slipped
 * through) and was fixed by widening `collectKidVisibleText`. That move is not
 * available here: a blocklist cannot read a JPEG. A non-text channel has to be
 * closed at the render site, which is what `kidSafeImageUrl` is.
 *
 * ═══ WHAT IS ACTUALLY BEING TESTED ═══
 *
 * Not "is this CDN wholesome". The rails differ in what the picture is DERIVED
 * from: the stock rail keys its image off the market's own text, which has
 * already passed the gate, so the picture inherits that vetting; the poster rail
 * ships marketing art for an external work, which the passing market text does
 * not constrain at all. Both live TMDB cards are in here for that reason — one
 * benign, one not — because the defect is the channel, not the card.
 *
 * Both halves are covered: the predicate, and the call site that decides what
 * the card renders. A predicate nobody reaches closes nothing.
 */
import { kidSafeImageUrl } from "@/lib/play/kidSafe";
import { cardImage } from "@/app/play/CoolOrBoring";
import type { FeedItem } from "@/lib/types";

/** The horror specimen, verified `isPlayEligible === true` on production. */
const RESIDENT_EVIL =
  "https://image.tmdb.org/t/p/w1280/1CIaRYKf3zg2Xyce1CSfCMg2Vfw.jpg";
/** The other live poster card the same hour — benign, and still refused. */
const PRACTICAL_MAGIC =
  "https://image.tmdb.org/t/p/w1280/nUcauJ000dFBYkgGpxyxJ5aWEH2.jpg";
/** 73 of the 75 images on that page came from this rail. */
const STOCK = "https://images.pexels.com/photos/399187/pexels-photo-399187.jpeg";

const futuresItem = (imageUrl: string | null): FeedItem =>
  ({
    type: "futures",
    data: {
      id: 1,
      name: '"Resident Evil" Opening Weekend Box Office',
      llm_sport_category: "entertainment",
      status: "open",
      image_url: imageUrl,
      top_outcomes: [{ name: "55-60m", probability: 0.4 }],
    },
  }) as unknown as FeedItem;

describe("#7461 kidSafeImageUrl — the picture rail", () => {
  it("refuses the horror poster that is live on the deck today", () => {
    expect(kidSafeImageUrl(RESIDENT_EVIL)).toBeNull();
  });

  it("refuses the BENIGN poster too — the channel is ungated, not the one card", () => {
    expect(kidSafeImageUrl(PRACTICAL_MAGIC)).toBeNull();
  });

  it("keeps the stock rail, so the fix is not 'drop every image'", () => {
    expect(kidSafeImageUrl(STOCK)).toBe(STOCK);
  });

  it("fails closed on absence and on anything it cannot parse", () => {
    expect(kidSafeImageUrl(null)).toBeNull();
    expect(kidSafeImageUrl(undefined)).toBeNull();
    expect(kidSafeImageUrl("")).toBeNull();
    expect(kidSafeImageUrl("not a url")).toBeNull();
    expect(kidSafeImageUrl("/photos/local.jpg")).toBeNull();
  });

  it("matches the hostname exactly — a suffix or path test would admit these", () => {
    // `endsWith` would pass this one.
    expect(kidSafeImageUrl("https://images.pexels.com.attacker.example/x.jpg")).toBeNull();
    // A path/substring test would pass this one.
    expect(kidSafeImageUrl("https://attacker.example/images.pexels.com/x.jpg")).toBeNull();
    // A `hostname.includes` test would pass this one.
    expect(kidSafeImageUrl("https://notimages.pexels.com/x.jpg")).toBeNull();
  });

  it("requires https — a kid surface does not render an image over plaintext", () => {
    expect(kidSafeImageUrl("http://images.pexels.com/photos/1.jpeg")).toBeNull();
  });
});

describe("#7461 the render site — what CoolOrBoring will actually paint", () => {
  it("gives the card no image for the poster rail", () => {
    expect(cardImage(futuresItem(RESIDENT_EVIL))).toBeNull();
  });

  it("still gives the card its stock image", () => {
    expect(cardImage(futuresItem(STOCK))).toBe(STOCK);
  });

  it("gives an event card no image, as before", () => {
    const event = { type: "event", data: { id: 2, image_url: STOCK } } as unknown as FeedItem;

    expect(cardImage(event)).toBeNull();
  });
});
