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
import {
  accentFor,
  clampText,
  clampWords,
  DEFAULT_ACCENT,
  SUBTITLE_MAX,
  SUBTITLE_MAX_QUIET,
  UnfurlCard,
} from "@/components/og/UnfurlCard";
import { buildHubShareCopy, hubCardCopy } from "@/lib/hubShareMeta";
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

/**
 * Every string `UnfurlCard` actually renders, in order.
 *
 * `UnfurlCard` is a plain function returning JSX — no hooks, no client runtime
 * — so it can be called and walked directly. That is deliberate: satori renders
 * it on the edge, and a DOM renderer here would be testing a different thing
 * than the one that ships.
 */
function textOf(node: unknown): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join(" ");

  const props = (node as { props?: { children?: unknown } }).props;
  return props ? textOf(props.children) : "";
}

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

/* ─────────────────────────── the picture half ─────────────────────────── */

/**
 * #5877 gave the hub its WORDS. This is the card.
 *
 * The route it guards, `app/hub/[competition]/opengraph-image.tsx`, is a server
 * component that fetches and returns an `ImageResponse`, so what is asserted
 * here is the pure decision it hands the component — `hubCardCopy` — plus the
 * two things a reader would actually notice if it were wrong: a sentence cut
 * mid-word, and five competitions drawing one picture.
 */
describe("a hub's share card says what the page says", () => {
  it("THE SHIP: draws the competition's own name and blurb, not the site's", () => {
    for (const [competition, payload] of Object.entries(PRODUCTION_HUBS)) {
      const card = hubCardCopy({ ok: true, hub: payload }, competition);

      // The SAME two fields the <title> and description are built from — read
      // from the same function, so the picture cannot name one thing while the
      // sentence beside it names another.
      const copy = buildHubShareCopy(payload, competition);
      expect(card.title).toBe(copy.title);
      expect(card.subtitle).toBe(copy.description);

      expect(card.title).not.toBe(HOME_PAGE_TITLE);
      expect(card.subtitle).not.toBe(HOME_PAGE_BLURB);
    }
  });

  it('the pill says the READER\'s word — "Competition", never "Hub"', () => {
    // `unresolvedShareMeta.ts` states the rule: "hub" is our word for the
    // route, "competition" is the reader's word for the thing, and no reader
    // has ever called one a hub. The pill is the most visible place to forget
    // it. Tied to the noun the unresolved copy uses, so the two cannot diverge.
    const { eyebrow } = hubCardCopy({ ok: true, hub: PRODUCTION_HUBS.mma }, "mma");
    expect(eyebrow).toBe("Competition");
    expect(eyebrow.toLowerCase()).not.toBe("hub");
    expect(unresolvedShareCopy("hub", "not-found").title).toContain(eyebrow.toLowerCase());

    // The same pill on the dead card, so a rotted link is not a different kind
    // of thing from a live one.
    expect(hubCardCopy({ ok: false, failure: "not-found" }, "nope").eyebrow).toBe(eyebrow);
  });

  it("THE LOOK FIX: every blurb is drawn WHOLE, with no ellipsis at all", () => {
    // Read off the rendered card on 2026-09-13: at the 90-character slot
    // `/hub/tennis` drew "…matchups, and props — every market…" with half the
    // canvas still blank underneath — a cut sized for a card that has
    // probability rows, on a card that has none. A hub card is quiet, so it
    // gets `SUBTITLE_MAX_QUIET` and all five fit.
    for (const [competition, payload] of Object.entries(PRODUCTION_HUBS)) {
      const props = hubCardCopy({ ok: true, hub: payload }, competition);
      const drawn = textOf(UnfurlCard(props));

      expect(drawn).toContain(payload.blurb);
      expect(drawn).not.toContain("…");
      // ...and it is genuinely the QUIET budget doing it: every one of these
      // blurbs would be cut at the row-bearing slot, so this cannot pass with
      // the distinction deleted.
      expect(props.subtitle.length).toBeGreaterThan(SUBTITLE_MAX);
      expect(props.subtitle.length).toBeLessThanOrEqual(SUBTITLE_MAX_QUIET);
    }
  });

  it("a blurb longer than even the quiet slot still breaks at a WORD", () => {
    // `clampWords` is the backstop, not dead code: product can write a longer
    // blurb tomorrow, and the failure it prevents is a cut mid-token, which
    // reads as a rendering fault rather than an elision.
    const long = `${PRODUCTION_HUBS.golf.blurb} ${PRODUCTION_HUBS.esports.blurb}`;
    const drawn = textOf(
      UnfurlCard({ ...hubCardCopy({ ok: true, hub: PRODUCTION_HUBS.golf }, "golf"), subtitle: long })
    );

    const cut = clampWords(long, SUBTITLE_MAX_QUIET);
    expect(long.length).toBeGreaterThan(SUBTITLE_MAX_QUIET);
    expect(drawn).toContain(cut);
    expect(drawn).not.toContain(long);

    expect(cut.length).toBeLessThanOrEqual(SUBTITLE_MAX_QUIET);
    expect(cut.endsWith("…")).toBe(true);
    // No comma or dash stranded against the ellipsis, and the break landed on
    // a space in the original rather than inside a token.
    expect(cut).not.toMatch(/[\s,;:—–-]…$/);
    const kept = cut.slice(0, -1);
    expect(long.startsWith(kept)).toBe(true);
    expect(long[kept.length]).toMatch(/[\s,;:—–-]/);

    // The component is doing it, not this test: the mid-word cut at the same
    // budget is a DIFFERENT string, and it is not what was drawn. This is the
    // assertion that fails if the subtitle slot reverts to `clampText`.
    expect(clampText(long, SUBTITLE_MAX_QUIET)).not.toBe(cut);
    expect(drawn).not.toContain(clampText(long, SUBTITLE_MAX_QUIET));
  });

  it("the five hubs are five different pictures, by colour as well as by name", () => {
    // The defect this whole ship exists to remove was ONE card for all five.
    // Read off the CARD, not off `accentFor` — the route handing the component
    // `accentFor(null)` would draw all five in the same default green and was a
    // surviving mutant while this was computed here (2026-09-13).
    const accents = Object.entries(PRODUCTION_HUBS).map(
      ([c, p]) => hubCardCopy({ ok: true, hub: p }, c).accent
    );
    expect(new Set(accents).size).toBe(5);
    expect(accents).toEqual(Object.keys(PRODUCTION_HUBS).map((c) => accentFor(c)));
    // ...and none of them fell through to the shared default, which would make
    // the set above coincidence rather than intent.
    expect(accents).not.toContain(DEFAULT_ACCENT);

    const titles = Object.entries(PRODUCTION_HUBS).map(
      ([c, p]) => hubCardCopy({ ok: true, hub: p }, c).title
    );
    expect(new Set(titles).size).toBe(5);
  });

  it("the accent probe can fail — it is not stuck on a distinct colour", () => {
    // Negative control for the rule above. `accentFor` returning a fresh value
    // for every input would satisfy it with no mapping at all.
    expect(accentFor("not-a-competition-we-cover")).toBe(DEFAULT_ACCENT);
    expect(accentFor("golf")).not.toBe(DEFAULT_ACCENT);
  });

  it("a dead link takes the title's own words rather than retyping them", () => {
    // The drift this prevents: the card saying one thing while the tab says
    // another. Asserted against the FUNCTION (so retyping the sentence in the
    // route is caught) and against the literal (so an inversion inside
    // `unresolvedShareCopy` is caught too).
    const dead = hubCardCopy({ ok: false, failure: "not-found" }, "nope");
    expect(dead.title).toBe(unresolvedShareCopy("hub", "not-found").title);
    expect(dead.title).toBe("This competition isn't on Bain Luck");

    const bad = hubCardCopy({ ok: false, failure: "unavailable" }, "nope");
    expect(bad.title).toBe(unresolvedShareCopy("hub", "unavailable").title);
    expect(bad.title).toBe("Competition Odds");

    // The two failures stay apart on the card, as they do in the metadata: a
    // bad minute must never claim the competition does not exist.
    expect(dead.title).not.toBe(bad.title);

    // A hub that failed to LOAD is still that hub's colour — the segment is
    // the one signal that survives the fetch failing, which is why the accent
    // is taken from it rather than from the payload.
    expect(hubCardCopy({ ok: false, failure: "unavailable" }, "golf").accent).toBe(
      accentFor("golf")
    );
    expect(hubCardCopy({ ok: false, failure: "unavailable" }, "golf").accent).not.toBe(
      DEFAULT_ACCENT
    );
  });

  it("both dead subtitles fit the slot whole — no ellipsis on the quiet card", () => {
    // These two are OURS to write, unlike a blurb, so there is no excuse for
    // either being cut.
    for (const failure of ["not-found", "unavailable"] as const) {
      const { title, subtitle } = hubCardCopy({ ok: false, failure }, "nope");
      expect(clampWords(subtitle, SUBTITLE_MAX)).toBe(subtitle);
      expect(clampText(title, 72)).toBe(title);
    }

    // ...and they are two different sentences. Without this the pair could be
    // swapped, or collapsed to one, with every other rule still green.
    expect(hubCardCopy({ ok: false, failure: "not-found" }, "nope").subtitle).not.toBe(
      hubCardCopy({ ok: false, failure: "unavailable" }, "nope").subtitle
    );
  });

  it("a card WITH rows keeps the tighter slot — the quiet budget is not global", () => {
    // The widened slot is granted by having nothing under the subtitle. A card
    // that draws probabilities must not also spend 150 characters on prose, or
    // the rows it exists for get pushed off the canvas.
    const blurb = PRODUCTION_HUBS.golf.blurb;
    const withRows = textOf(
      UnfurlCard({
        eyebrow: "Tournament",
        title: "US Open",
        subtitle: blurb,
        rows: [{ name: "Zverev", probability: "57%", fraction: 0.57 }],
        accent: DEFAULT_ACCENT,
      })
    );

    expect(withRows).toContain(clampWords(blurb, SUBTITLE_MAX));
    expect(withRows).not.toContain(blurb);
    // ...and the same subtitle on the quiet card is drawn whole, so the two
    // budgets are genuinely different rather than one constant twice.
    expect(
      textOf(UnfurlCard(hubCardCopy({ ok: true, hub: PRODUCTION_HUBS.golf }, "golf")))
    ).toContain(blurb);
  });

  it("a hub card draws NO probability row — a collection has no one number", () => {
    // The deliberate decision in `hubShareMeta.ts`: no leader, no count. A
    // later hand adding rows here would put an arbitrary one of 182 markets on
    // the card, or an inventory count on a reader's screen (notice 34).
    const drawn = textOf(
      UnfurlCard(hubCardCopy({ ok: true, hub: PRODUCTION_HUBS.tennis }, "tennis"))
    );

    expect(drawn).not.toMatch(/\d+%/);
    // ...and no inventory count either (notice 34): the footer note stays empty.
    expect(drawn).not.toMatch(/\d/);
    // The probe can see a percentage when there is one, so the rule above is
    // not passing because `textOf` returns nothing.
    const withRow = textOf(
      UnfurlCard({
        eyebrow: "Tournament",
        title: "US Open",
        subtitle: null,
        rows: [{ name: "Zverev", probability: "57%", fraction: 0.57 }],
        accent: DEFAULT_ACCENT,
      })
    );
    expect(withRow).toMatch(/\d+%/);
  });

  it("a 200 with an empty body still draws the segment, never nothing", () => {
    // The branch that could fall silent. A card with no title is a blank
    // rectangle, which is worse than the house card it replaced.
    const card = hubCardCopy({ ok: true, hub: {} }, "esports");
    expect(card.title).toBe("Esports");
    expect(card.subtitle.length).toBeGreaterThan(0);
    expect(card.title).not.toBe(HOME_PAGE_TITLE);
  });
});

/* ──────────── the metadata layer: both namespaces name this card ──────── */

describe("the hub's own card is named in og: AND twitter:", () => {
  it("THE SHIP: a live hub names its own image route, not the site card", async () => {
    stubStatus(200, PRODUCTION_HUBS.tennis);
    const meta = await hubMetadata({ params: Promise.resolve({ competition: "tennis" }) });

    const own = "https://www.bainluck.com/hub/tennis/opengraph-image";
    expect(meta.openGraph?.images).toEqual([
      { url: own, alt: "Tennis", width: 1200, height: 630 },
    ]);
    // The namespace Next's file convention does NOT override, and therefore the
    // one that silently kept the home page's picture.
    expect(meta.twitter?.images).toEqual([own]);
  });

  it("a dead link previews the same in Slack and on X", async () => {
    stubStatus(404);
    const meta = await hubMetadata({ params: Promise.resolve({ competition: "nope" }) });

    const own = "https://www.bainluck.com/hub/nope/opengraph-image";
    expect(meta.twitter?.images).toEqual([own]);
    expect(meta.openGraph?.images).toEqual([
      expect.objectContaining({ url: own }),
    ]);
    // Still deindexed, still self-canonical — the card must not disturb #5861.
    expect(meta.robots).toEqual({ index: false, follow: true });
    expect(meta.alternates?.canonical).toBe("/hub/nope");
  });

  it("no branch falls back to the site card", async () => {
    // The regression that every other rule in this file scores as a pass: a
    // layout quietly going back to `defaultShareCard()`. Checked on all four
    // branches, because only one of them is exercised above.
    const cases: Array<[string, () => void]> = [
      ["200", () => stubStatus(200, PRODUCTION_HUBS.golf)],
      ["404", () => stubStatus(404)],
      ["500", () => stubStatus(500)],
      [
        "throw",
        () => {
          global.fetch = jest.fn().mockRejectedValue(new Error("boom")) as unknown as typeof fetch;
        },
      ],
    ];

    for (const [label, stub] of cases) {
      stub();
      const meta = await hubMetadata({ params: Promise.resolve({ competition: "golf" }) });
      const urls = [
        ...(meta.twitter?.images as string[]),
        ...(meta.openGraph?.images as Array<{ url: string }>).map((i) => i.url),
      ];
      for (const url of urls) {
        expect(`${label}: ${url}`).toBe(`${label}: https://www.bainluck.com/hub/golf/opengraph-image`);
      }
    }
  });

  it("an attacker-supplied segment cannot escape the image path either", async () => {
    // `unresolvedPath` encodes, and the card URL is built from ITS output, so
    // the picture a crafted link names stays inside this route.
    stubStatus(404);
    const meta = await hubMetadata({
      params: Promise.resolve({ competition: "../../evil" }),
    });

    const [url] = meta.twitter?.images as string[];
    expect(url).toBe("https://www.bainluck.com/hub/..%2F..%2Fevil/opengraph-image");
    expect(new URL(url).pathname.startsWith("/hub/")).toBe(true);
  });
});
