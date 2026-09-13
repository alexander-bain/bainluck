/**
 * A PASTED `/hub/<competition>` LINK UNFURLS AS THAT COMPETITION (#5877).
 *
 * ═══ WHAT THIS IS A GUARD FOR ═══
 *
 * Measured with a crawler UA on production at 2026-09-13 09:46:33Z, all five
 * hubs AND a competition that does not exist were byte-identical in metadata —
 * md5 `f72c90da46e788dab512b5c3a1a1732a` over the extracted tags, for all six:
 *
 *   canonical      https://www.bainluck.com
 *   og:url         https://www.bainluck.com
 *   og:title       Bain Luck — Prediction Market Discovery
 *   twitter:title  Bain Luck — Prediction Market Discovery
 *   robots         index, follow
 *
 * `/hub/mma`, `/hub/boxing`, `/hub/golf`, `/hub/tennis` and `/hub/esports` are
 * hardcoded in both `BottomNav` and `DesktopNav` — five links on the navigation
 * of every page, each telling search engines it duplicates the home page.
 *
 * ═══ WHY THE BYTE-IDENTITY IS THE TEST AND NOT JUST THE STORY ═══
 *
 * "Does the card name the hub?" can pass on a route that hardcodes one string.
 * The defect was that five real hubs and one fake one were INDISTINGUISHABLE, so
 * the assertion that actually tracks the fix is that they have stopped being so
 * — pairwise, including the fake — which no hardcoded value can satisfy.
 *
 * The fixture payloads below are the real ones, read from production the same
 * morning (`GET /api/hub/{competition}`), rather than invented. An invented
 * payload tests the code against my idea of the server; #5877's whole diagnosis
 * is that the server was already right and the client was throwing it away.
 *
 * The metadata layer of this ship — that these values reach a rendered
 * `<meta>` tag — is `shareUnfurl.test.ts`'s job, which reads built HTML. This
 * file is the pure half: it needs no build and no network.
 */

import { generateMetadata as hubMetadata } from "@/app/hub/[competition]/layout";
import { buildHubShareCopy } from "@/lib/hubShareMeta";
import {
  unresolvedMetadata,
  unresolvedPath,
  unresolvedShareCopy,
} from "@/lib/unresolvedShareMeta";

const asText = (v: unknown): string =>
  typeof v === "string"
    ? v
    : typeof v === "object" && v !== null && "absolute" in v
      ? String((v as { absolute?: string }).absolute ?? "")
      : String(v ?? "");

function stubStatus(status: number, payload: unknown = null) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  }) as unknown as typeof fetch;
}

afterEach(() => {
  jest.restoreAllMocks();
});

/** The five hubs, verbatim from `GET /api/hub/{competition}` at 09:47Z. */
const PRODUCTION_HUBS = {
  mma: {
    competition: "mma",
    label: "MMA",
    title: "Mixed Martial Arts",
    blurb:
      "Upcoming UFC cards, fight props, and title odds — every market translated into plain probabilities.",
  },
  boxing: {
    competition: "boxing",
    label: "Boxing",
    title: "Boxing",
    blurb:
      "Upcoming fight cards, method-and-round props, and title odds — every market translated into plain probabilities.",
  },
  golf: {
    competition: "golf",
    label: "Golf",
    title: "Golf",
    blurb:
      "Upcoming tournaments — majors and tour events — with winner fields, top-finish props, and matchups translated into plain probabilities.",
  },
  tennis: {
    competition: "tennis",
    label: "Tennis",
    title: "Tennis",
    blurb:
      "Upcoming slams and tour events with winner fields, matchups, and props — every market translated into plain probabilities.",
  },
  esports: {
    competition: "esports",
    label: "Esports",
    title: "Esports",
    blurb:
      "Tournament and season titles across League of Legends, Counter-Strike, Valorant, and Dota — every market translated into plain probabilities.",
  },
} as const;

/** What the home page sends, and therefore what none of these may send. */
const HOME_PAGE_TITLE = "Bain Luck — Prediction Market Discovery";
const HOME_PAGE_BLURB =
  "See what the world thinks will happen. Explore prediction markets as intuitive probabilities.";

describe("a hub names itself, not the home page", () => {
  it("takes the title and blurb the server already serves", () => {
    // The page renders these exact two fields as its `<h1>` and the paragraph
    // beneath it, so the share and the page a reader lands on agree.
    const mma = buildHubShareCopy(PRODUCTION_HUBS.mma, "mma");
    expect(mma.title).toBe("Mixed Martial Arts");
    expect(mma.description).toBe(PRODUCTION_HUBS.mma.blurb);

    const tennis = buildHubShareCopy(PRODUCTION_HUBS.tennis, "tennis");
    expect(tennis.title).toBe("Tennis");
    expect(tennis.description).toBe(PRODUCTION_HUBS.tennis.blurb);
  });

  it("gives all five a title that is not the home page's", () => {
    for (const [competition, payload] of Object.entries(PRODUCTION_HUBS)) {
      const copy = buildHubShareCopy(payload, competition);
      expect(copy.title).not.toBe(HOME_PAGE_TITLE);
      expect(copy.title.length).toBeGreaterThan(0);
      expect(copy.description.length).toBeGreaterThan(0);
    }
  });

  it("THE DEFECT: the five hubs and a fake one are no longer identical", () => {
    // The production BEFORE, restated as an assertion. Six copies, six distinct
    // titles — and the fake one is in the set, because "all the real ones
    // differ" was ALSO true before this fix for every field except the ones
    // that mattered. Pairwise distinctness is what no hardcoded string buys.
    const real = Object.entries(PRODUCTION_HUBS).map(([key, payload]) =>
      buildHubShareCopy(payload, key)
    );
    const fake = unresolvedShareCopy("hub", "not-found");

    const titles = [...real.map((c) => c.title), fake.title];
    expect(new Set(titles).size).toBe(titles.length);

    const descriptions = [...real.map((c) => c.description), fake.description];
    expect(new Set(descriptions).size).toBe(descriptions.length);
  });

  it("a hub that resolves is never given the not-found voice", () => {
    // The two branches must not converge: a live hub saying "isn't on Bain
    // Luck" is a worse bug than the one being fixed, and it is the shape a
    // careless fallback takes.
    const notFound = unresolvedShareCopy("hub", "not-found");
    for (const [competition, payload] of Object.entries(PRODUCTION_HUBS)) {
      expect(buildHubShareCopy(payload, competition).title).not.toBe(notFound.title);
    }
  });
});

describe("the title falls back through real fields before it derives one", () => {
  it("prefers the long name, then the short one", () => {
    expect(buildHubShareCopy({ title: "Mixed Martial Arts", label: "MMA" }, "mma").title).toBe(
      "Mixed Martial Arts"
    );
    expect(buildHubShareCopy({ title: "  ", label: "MMA" }, "mma").title).toBe("MMA");
  });

  it("falls to the payload's own key, title-cased and acronym-safe", () => {
    expect(buildHubShareCopy({ competition: "mma" }, "mma").title).toBe("MMA");
    expect(buildHubShareCopy({ competition: "tennis" }, "tennis").title).toBe("Tennis");
  });

  it("falls last to the segment the reader pasted, and never to nothing", () => {
    // A 200 whose body is empty is not a 404 — we must not claim the hub is
    // absent — but the card must not fall silent either, because silence is
    // what inherits the home page's title. This is the floor.
    expect(buildHubShareCopy({}, "esports").title).toBe("Esports");
    expect(buildHubShareCopy(null, "golf").title).toBe("Golf");
    expect(buildHubShareCopy(undefined, "boxing").title).toBe("Boxing");

    for (const source of [{}, null, undefined]) {
      const copy = buildHubShareCopy(source, "tennis");
      expect(copy.title.length).toBeGreaterThan(0);
      expect(copy.description.length).toBeGreaterThan(0);
      expect(copy.title).not.toBe(HOME_PAGE_TITLE);
    }
  });

  it("treats whitespace-only fields as absent, at every step", () => {
    // `cleanText` is the only thing standing between a `" "` from the API and a
    // card whose title is a space. Each rung gets its own empty spelling.
    const copy = buildHubShareCopy(
      { title: "", label: "   ", competition: "\t", blurb: "\n" },
      "mma"
    );
    expect(copy.title).toBe("MMA");
    expect(copy.description).toBe(
      "Every market in this competition, translated into plain probabilities."
    );
  });
});

describe("an unresolved hub speaks the reader's word, not ours", () => {
  it('says "competition" — never "hub", which is our word for the route', () => {
    const copy = unresolvedShareCopy("hub", "not-found");
    expect(copy.title).toBe("This competition isn't on Bain Luck");
    expect(copy.title).not.toMatch(/hub/i);
    expect(copy.description).not.toMatch(/hub/i);
  });

  it("keeps the two failures apart, because only one means absence", () => {
    const notFound = unresolvedShareCopy("hub", "not-found");
    const unavailable = unresolvedShareCopy("hub", "unavailable");
    expect(unavailable.title).toBe("Competition Odds");
    expect(unavailable.title).not.toBe(notFound.title);
    // The neutral branch claims nothing about existence.
    expect(unavailable.title).not.toMatch(/isn't on Bain Luck/);
  });

  it("noindexes a competition that does not exist, and only that", () => {
    const path = unresolvedPath("hub", "not-a-real-competition-99999");
    expect(path).toBe("/hub/not-a-real-competition-99999");

    const gone = unresolvedMetadata(path, "hub", "not-found");
    expect(gone.robots).toEqual({ index: false, follow: true });

    // A hub that merely could not be fetched this minute must not be
    // deindexed for it — the durable half of gotcha #53.
    const blip = unresolvedMetadata("/hub/tennis", "hub", "unavailable");
    expect(blip.robots).toBeUndefined();
  });

  it("says it is itself in every namespace a crawler reads", () => {
    // The #5861 lesson one route over: an omitted `twitter` block inherits the
    // ROOT's, so a dead link kept sending the home page's twitter:title while
    // its og:title was already correct.
    const md = unresolvedMetadata("/hub/nope", "hub", "not-found");
    expect(md.alternates?.canonical).toBe("/hub/nope");
    expect(md.openGraph?.url).toBe("/hub/nope");
    expect(md.openGraph?.title).toMatch(/This competition isn't on Bain Luck/);
    expect(md.twitter?.title).toMatch(/This competition isn't on Bain Luck/);
    expect(md.openGraph?.title).not.toBe(HOME_PAGE_TITLE);
    expect(md.twitter?.title).not.toBe(HOME_PAGE_TITLE);
    // A route declaring `openGraph` declares its own picture, or it asks for a
    // large card and supplies nothing — `/discover/stats`'s bug.
    expect(md.openGraph?.images).toBeDefined();
    expect(md.twitter?.images).toBeDefined();
  });

  it("keeps an attacker-supplied segment a single inert path segment", () => {
    // Next hands `generateMetadata` a DECODED segment, so this is reachable.
    expect(unresolvedPath("hub", "../../evil")).toBe("/hub/..%2F..%2Fevil");
    expect(unresolvedPath("hub", "//evil.example")).toBe("/hub/%2F%2Fevil.example");
  });
});

/**
 * The layer above the copy: the route that decides WHICH copy, from a status
 * code. Driven the same way `unresolvedTwitterNamespace5861.test.ts` drives the
 * two routes before this one, because the branch that matters — a 404 is
 * absence, a 500 is a bad minute — lives here and nowhere else.
 */
describe("app/hub/[competition]/layout", () => {
  it("THE SHIP: a real hub unfurls as itself, in every namespace", async () => {
    stubStatus(200, PRODUCTION_HUBS.tennis);
    const meta = await hubMetadata({ params: Promise.resolve({ competition: "tennis" }) });

    expect(asText(meta.title)).toBe("Tennis");
    expect(asText(meta.openGraph?.title)).toBe("Tennis | Bain Luck");
    expect(asText(meta.twitter?.title)).toBe("Tennis | Bain Luck");
    expect(asText(meta.description)).toBe(PRODUCTION_HUBS.tennis.blurb);

    // The three tags the production BEFORE named, all of which said the home
    // page and now say this page.
    expect(meta.alternates?.canonical).toBe("/hub/tennis");
    expect(meta.openGraph?.url).toBe("/hub/tennis");
    expect(asText(meta.openGraph?.title)).not.toBe(HOME_PAGE_TITLE);
    expect(asText(meta.twitter?.title)).not.toBe(HOME_PAGE_TITLE);

    // A live hub is indexable — only a hub that does not exist is not.
    expect(meta.robots).toBeUndefined();
    // Declares `openGraph`, so it declares its own picture (`/discover/stats`).
    expect(meta.openGraph?.images).toBeDefined();
    expect(meta.twitter?.images).toHaveLength(1);
  });

  it("all five nav hubs get five different cards", async () => {
    // The nav links these by name; the defect was that they were one card.
    const titles: string[] = [];
    for (const [competition, payload] of Object.entries(PRODUCTION_HUBS)) {
      stubStatus(200, payload);
      const meta = await hubMetadata({ params: Promise.resolve({ competition }) });
      expect(meta.alternates?.canonical).toBe(`/hub/${competition}`);
      titles.push(asText(meta.openGraph?.title));
    }
    expect(new Set(titles).size).toBe(5);
    expect(titles).not.toContain(HOME_PAGE_TITLE);
  });

  it("a competition that does not exist says so, and is noindexed", async () => {
    stubStatus(404);
    const meta = await hubMetadata({
      params: Promise.resolve({ competition: "not-a-real-competition-99999" }),
    });

    expect(asText(meta.twitter?.title)).toBe("This competition isn't on Bain Luck | Bain Luck");
    expect(asText(meta.twitter?.description)).not.toBe(HOME_PAGE_BLURB);
    expect(meta.alternates?.canonical).toBe("/hub/not-a-real-competition-99999");
    expect(meta.openGraph?.url).toBe("/hub/not-a-real-competition-99999");
    expect(meta.robots).toEqual({ index: false, follow: true });
  });

  it("a 500 is a bad minute, not a missing competition", async () => {
    // The trap in the fix rather than in the bug: deindexing `/hub/tennis`
    // because the API was restarting is worse and more durable than the defect.
    stubStatus(500);
    const meta = await hubMetadata({ params: Promise.resolve({ competition: "tennis" }) });

    expect(asText(meta.title)).toBe("Competition Odds");
    expect(meta.robots).toBeUndefined();
    expect(meta.alternates?.canonical).toBe("/hub/tennis");
    expect(asText(meta.twitter?.title)).not.toBe(HOME_PAGE_TITLE);
  });

  it("a thrown fetch is also a bad minute, not an absence", async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error("ECONNRESET")) as unknown as typeof fetch;
    const meta = await hubMetadata({ params: Promise.resolve({ competition: "golf" }) });

    expect(meta.robots).toBeUndefined();
    expect(meta.alternates?.canonical).toBe("/hub/golf");
  });

  it("a segment that could never be a competition costs no request", async () => {
    stubStatus(200, PRODUCTION_HUBS.mma);
    const meta = await hubMetadata({
      params: Promise.resolve({ competition: "../../etc/passwd" }),
    });

    expect(global.fetch).not.toHaveBeenCalled();
    expect(meta.robots).toEqual({ index: false, follow: true });
    // Refused, and still not the home page — the canonical stays on the route.
    expect(meta.alternates?.canonical).toBe("/hub/..%2F..%2Fetc%2Fpasswd");
    expect(asText(meta.twitter?.title)).not.toBe(HOME_PAGE_TITLE);
  });

  it("the 200 branch never inherits the home page, even on an empty body", async () => {
    // A 200 with nothing in it is the one case that could fall silent, and
    // silence is exactly what inherits the root's title.
    stubStatus(200, {});
    const meta = await hubMetadata({ params: Promise.resolve({ competition: "esports" }) });

    expect(asText(meta.openGraph?.title)).toBe("Esports | Bain Luck");
    expect(asText(meta.openGraph?.title)).not.toBe(HOME_PAGE_TITLE);
    expect(meta.alternates?.canonical).toBe("/hub/esports");
    expect(meta.robots).toBeUndefined();
  });
});
