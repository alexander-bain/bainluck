/**
 * #5840 — A DEAD GAME OR MARKET LINK STOPS UNFURLING AS THE HOME PAGE.
 *
 * Read with a crawler UA against production at 2026-09-13 07:48:01Z, with a real
 * id beside a dead one as the control:
 *
 *   /events/15310371   canonical  https://www.bainluck.com/events/15310371   ✓
 *   /events/99999999   canonical  https://www.bainluck.com                   ✗
 *                      og:title   Bain Luck — Prediction Market Discovery
 *                      robots     index, follow
 *   /futures/86832     canonical  https://www.bainluck.com/futures/86832     ✓
 *   /futures/99999999  canonical  https://www.bainluck.com                   ✗
 *
 * Two layers here, and they are not redundant — the reason
 * `eventShareMetadataRender.test.ts` exists beside `eventShareMeta.test.ts`. The
 * builder layer proves the object is right; the ROUTE layer proves the two
 * layouts actually call it, with a stubbed fetch driving each status. A builder
 * guard alone stays green while a layout keeps its old miss branch, which is the
 * exact shape of the bug being fixed.
 */

import { generateMetadata as eventMetadata } from "@/app/events/[id]/layout";
import { generateMetadata as futuresMetadata } from "@/app/futures/[id]/layout";
import { SITE_URL } from "@/lib/siteUrl";
import {
  unresolvedMetadata,
  unresolvedPath,
  unresolvedShareCopy,
} from "@/lib/unresolvedShareMeta";

/** The home page's identity — the thing a dead link used to claim to be. */
const HOME_BLURB =
  "See what the world thinks will happen. Explore prediction markets as intuitive probabilities.";

const asText = (v: unknown): string =>
  typeof v === "string"
    ? v
    : typeof v === "object" && v !== null && "absolute" in v
      ? String((v as { absolute?: string }).absolute ?? "")
      : String(v ?? "");

/**
 * A fetch whose STATUS is settable, which the older stubs in this suite are not.
 * The whole 404-vs-blip distinction is invisible to a stub that only sets `ok`.
 */
function stubStatus(status: number, payload: unknown = null) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  }) as unknown as typeof fetch;
}

function stubThrow() {
  global.fetch = jest.fn().mockRejectedValue(new Error("socket hang up")) as unknown as typeof fetch;
}

afterEach(() => {
  jest.restoreAllMocks();
});

/* ───────────────────────────── the builder ───────────────────────────── */

describe("unresolvedMetadata says the page is itself", () => {
  const cases = [
    { path: "/events/99999999", subject: "game" as const },
    { path: "/futures/99999999", subject: "market" as const },
  ];
  const failures = ["not-found", "unavailable"] as const;

  for (const { path, subject } of cases) {
    for (const failure of failures) {
      it(`${path} (${failure}) canonicals to itself, never to the home page`, () => {
        const meta = unresolvedMetadata(path, subject, failure);

        expect(meta.alternates?.canonical).toBe(path);
        expect(meta.openGraph?.url).toBe(path);

        // The two literal values production served. A relative path is what
        // Next resolves against `metadataBase`, so "/" is the spelling the root
        // actually holds and the one inheritance would hand back.
        expect(meta.alternates?.canonical).not.toBe("/");
        expect(meta.openGraph?.url).not.toBe("/");
        expect(meta.alternates?.canonical).not.toBe(SITE_URL);
        expect(meta.openGraph?.url).not.toBe(SITE_URL);
      });

      it(`${path} (${failure}) carries its own card and its own social title`, () => {
        const meta = unresolvedMetadata(path, subject, failure);

        // `shareUnfurl.test.ts`'s rule: a route that declares openGraph declares
        // its own images. An omitted twitter block inherits the ROOT's title and
        // the ROOT's card — the same defect one namespace over.
        expect(meta.openGraph?.images).toHaveLength(1);
        expect(meta.twitter?.images).toHaveLength(1);
        expect(asText(meta.twitter?.title)).toBe(asText(meta.openGraph?.title));
        expect(asText(meta.openGraph?.title)).toMatch(/\| Bain Luck$/);

        // ...while the document title must NOT carry it: the root template is
        // `%s | Bain Luck` and appends one. `Event Odds - Bain Luck | Bain Luck`
        // is what the events route printed in the tab before this.
        expect(asText(meta.title)).not.toMatch(/\| Bain Luck/);

        expect(asText(meta.description)).not.toBe(HOME_BLURB);
        expect(asText(meta.openGraph?.description)).not.toBe(HOME_BLURB);
      });
    }
  }
});

describe("only a 404 is allowed to be noindexed", () => {
  // The trap inside the fix, not inside the bug: deindexing a real market
  // because the API was restarting is worse and quieter than the defect.
  it("a not-found link is noindex, follow", () => {
    const meta = unresolvedMetadata("/futures/99999999", "market", "not-found");
    expect(meta.robots).toEqual({ index: false, follow: true });
  });

  it("an unavailable link sets no robots directive at all", () => {
    const meta = unresolvedMetadata("/futures/86832", "market", "unavailable");
    // Absent, not `{index: true}` — the page keeps inheriting whatever the site
    // says, so this branch can never be the thing that deindexes a real page.
    expect(meta.robots).toBeUndefined();
    expect("robots" in meta).toBe(false);
  });
});

describe("the copy tells the two failures apart", () => {
  it("a not-found link says the thing is not here", () => {
    expect(unresolvedShareCopy("game", "not-found").title).toBe("This game isn't on Bain Luck");
    expect(unresolvedShareCopy("market", "not-found").title).toBe(
      "This market isn't on Bain Luck"
    );
  });

  it("an unavailable link claims nothing about whether it exists", () => {
    for (const subject of ["game", "market"] as const) {
      const copy = unresolvedShareCopy(subject, "unavailable");
      expect(copy.title).not.toMatch(/isn't|not on|no longer|removed|gone/i);
      expect(copy.description).not.toMatch(/isn't|there's no|not found/i);
    }
  });

  it("the two failures never produce the same sentence", () => {
    // The one-line mutation this whole file exists to kill: a `failure`
    // parameter that is accepted and then ignored.
    for (const subject of ["game", "market"] as const) {
      const missing = unresolvedShareCopy(subject, "not-found");
      const blip = unresolvedShareCopy(subject, "unavailable");
      expect(missing.title).not.toBe(blip.title);
      expect(missing.description).not.toBe(blip.description);
    }
  });

  it("a game and a market are not described as the same noun", () => {
    expect(unresolvedShareCopy("game", "not-found").title).not.toBe(
      unresolvedShareCopy("market", "not-found").title
    );
    expect(unresolvedShareCopy("game", "unavailable").title).not.toBe(
      unresolvedShareCopy("market", "unavailable").title
    );
  });
});

describe("unresolvedPath keeps a user-supplied segment inert", () => {
  it("a plain id passes through", () => {
    expect(unresolvedPath("events", "99999999")).toBe("/events/99999999");
    expect(unresolvedPath("futures", "abc")).toBe("/futures/abc");
  });

  it("a protocol-relative segment cannot become another origin", () => {
    // `//evil.example` is the spelling that walked past the first version of the
    // apex guard (see `assertRoutePath`). Here it arrives as a path SEGMENT from
    // the URL bar, so it must not survive as one.
    const path = unresolvedPath("events", "//evil.example");
    expect(new URL(path, "https://route-path.invalid").origin).toBe("https://route-path.invalid");
    expect(path).not.toContain("//evil.example");
  });

  it("a traversal segment cannot climb out of the route", () => {
    const path = unresolvedPath("futures", "../../admin");
    expect(new URL(path, "https://route-path.invalid").pathname).toMatch(/^\/futures\//);
  });

  it("the metadata builder accepts what this produces", () => {
    // `selfCanonical` throws on anything that is not root-relative, at build
    // time. A segment that made it throw would take the whole page down, so the
    // two functions are asserted together rather than separately.
    for (const segment of ["12", "abc", "//evil.example", "../../admin", "a b", "%"]) {
      expect(() =>
        unresolvedMetadata(unresolvedPath("events", segment), "game", "not-found")
      ).not.toThrow();
    }
  });
});

/* ────────────────────────── the two real routes ────────────────────────── */

describe("app/events/[id]/layout drives it", () => {
  it("a 404 from the API is not-found, self-canonical and noindex", async () => {
    stubStatus(404);
    const meta = await eventMetadata({ params: Promise.resolve({ id: "99999999" }) });

    expect(meta.alternates?.canonical).toBe("/events/99999999");
    expect(meta.openGraph?.url).toBe("/events/99999999");
    expect(asText(meta.title)).toBe("This game isn't on Bain Luck");
    expect(meta.robots).toEqual({ index: false, follow: true });
  });

  it("a 500 is NOT reported as a missing game and is not noindexed", async () => {
    stubStatus(500);
    const meta = await eventMetadata({ params: Promise.resolve({ id: "15310371" }) });

    expect(asText(meta.title)).toBe("Game Odds");
    expect(meta.robots).toBeUndefined();
    expect(meta.alternates?.canonical).toBe("/events/15310371");
  });

  it("a dropped connection is treated as a bad minute, not an absence", async () => {
    stubThrow();
    const meta = await eventMetadata({ params: Promise.resolve({ id: "15310371" }) });
    expect(asText(meta.title)).toBe("Game Odds");
    expect(meta.robots).toBeUndefined();
  });

  it("a segment that could never be an id is not-found without a request", async () => {
    stubStatus(200, {});
    const meta = await eventMetadata({ params: Promise.resolve({ id: "abc" }) });

    expect(global.fetch).not.toHaveBeenCalled();
    expect(asText(meta.title)).toBe("This game isn't on Bain Luck");
    expect(meta.alternates?.canonical).toBe("/events/abc");
  });

  it("a real game is untouched by all of this", async () => {
    // The control. The live half of this route was CORRECT on production and
    // the fix must not have moved it; a guard that only watches the miss branch
    // cannot see it regress.
    stubStatus(200, {
      id: 15310371,
      home_team: "Chicago White Sox",
      away_team: "St. Louis Cardinals",
      home_score: 6,
      away_score: 5,
      status: "completed",
      commence_time: "2026-09-12T18:10:00Z",
      hero_probability: 1.0,
      hero_probability_away: 0.0,
      hero_probability_source: "settled",
      hero_settled_result: "home",
      current_odds: { home_probability: 0.55, away_probability: 0.45 },
    });
    const meta = await eventMetadata({ params: Promise.resolve({ id: "15310371" }) });

    expect(asText(meta.title)).toContain("Chicago White Sox won");
    expect(meta.alternates?.canonical).toBe("https://www.bainluck.com/events/15310371");
    expect(meta.robots).toBeUndefined();
  });
});

describe("app/futures/[id]/layout drives it", () => {
  it("a 404 from the API is not-found, self-canonical and noindex", async () => {
    stubStatus(404);
    const meta = await futuresMetadata({ params: Promise.resolve({ id: "99999999" }) });

    expect(meta.alternates?.canonical).toBe("/futures/99999999");
    expect(meta.openGraph?.url).toBe("/futures/99999999");
    expect(asText(meta.title)).toBe("This market isn't on Bain Luck");
    expect(meta.robots).toEqual({ index: false, follow: true });
  });

  it("a 500 is NOT reported as a missing market and is not noindexed", async () => {
    stubStatus(500);
    const meta = await futuresMetadata({ params: Promise.resolve({ id: "86832" }) });

    expect(asText(meta.title)).toBe("Market Odds");
    expect(meta.robots).toBeUndefined();
    expect(meta.alternates?.canonical).toBe("/futures/86832");
  });

  it("a real market is untouched by all of this", async () => {
    stubStatus(200, {
      id: 86832,
      name: "NFL Super Bowl Winner",
      status: "open",
      outcomes: [
        { name: "Los Angeles Rams", probability: 0.1219 },
        { name: "Buffalo Bills", probability: 0.1 },
      ],
    });
    const meta = await futuresMetadata({ params: Promise.resolve({ id: "86832" }) });

    expect(asText(meta.title)).toContain("Los Angeles Rams");
    expect(asText(meta.title)).toContain("12%");
    expect(meta.alternates?.canonical).toBe("https://www.bainluck.com/futures/86832");
    expect(meta.robots).toBeUndefined();
  });
});
