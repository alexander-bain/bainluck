/**
 * #5861 — THE HALF #5813 AND #5833 DID NOT DECLARE.
 *
 * Both of those fixed `canonical` and `og:url` on their routes, and both are
 * correct and live. Neither declared a `twitter` block on its MISS branch, so
 * Next went on inheriting the root's. Read with a crawler UA against production
 * 2026-09-13 08:50Z, after both fixes were live:
 *
 *   /tournaments/no-such-tournament-xyz
 *     og:title       Tournament Odds | Bain Luck
 *     twitter:title  Bain Luck — Prediction Market Discovery      ← the home page
 *     canonical      …/tournaments/no-such-tournament-xyz          (correct, #5813)
 *
 *   /event/election/no-such-slug-xyz
 *     og:title             Event Odds | Bain Luck
 *     twitter:title        Bain Luck — Prediction Market Discovery ← the home page
 *     twitter:description  See what the world thinks will happen. Explore…
 *     canonical            …/event/election/no-such-slug-xyz       (correct, #5833)
 *
 * Both routes now use `unresolvedMetadata`, the builder #5840 shipped, which
 * states `twitter` rather than omitting it and splits a 404 from a transient
 * failure. `unresolvedShareMeta5840.test.ts` holds the builder's own rules for
 * every subject; this file holds the two routes and the two new subjects.
 */

import { generateMetadata as conceptMetadata } from "@/app/event/[domain]/[slug]/layout";
import { generateMetadata as tournamentMetadata } from "@/app/tournaments/[slug]/layout";
import { unresolvedPath, unresolvedShareCopy } from "@/lib/unresolvedShareMeta";

/** The home page's identity — what these two dead links used to send. */
const HOME_TITLE = "Bain Luck — Prediction Market Discovery";
const HOME_BLURB =
  "See what the world thinks will happen. Explore prediction markets as intuitive probabilities.";

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

describe("the two new subjects keep the copy table honest", () => {
  it("a tournament and an event are named by their own noun", () => {
    expect(unresolvedShareCopy("tournament", "not-found").title).toBe(
      "This tournament isn't on Bain Luck"
    );
    expect(unresolvedShareCopy("event", "not-found").title).toBe("This event isn't on Bain Luck");
  });

  it("the unavailable copy is the text each route already shipped", () => {
    // Not new words. If these change, the branch has started making a claim it
    // did not make before, which is the thing the #5840 split exists to prevent.
    expect(unresolvedShareCopy("tournament", "unavailable")).toEqual({
      title: "Tournament Odds",
      description: "Every contender's chance of winning, as one clean probability.",
    });
    expect(unresolvedShareCopy("event", "unavailable")).toEqual({
      title: "Event Odds",
      description: "Every market on this event, as one clean probability.",
    });
  });

  it("all four subjects are distinct in both failures", () => {
    // The mutation this kills: a `Record` gaining a key that duplicates another,
    // which typechecks and reads fine.
    const subjects = ["game", "market", "tournament", "event"] as const;
    for (const failure of ["not-found", "unavailable"] as const) {
      const titles = subjects.map((s) => unresolvedShareCopy(s, failure).title);
      expect(new Set(titles).size).toBe(subjects.length);
    }
  });
});

describe("unresolvedPath encodes each segment separately", () => {
  it("a two-segment route keeps its separator", () => {
    // Encoding the pair joined would escape the slash BETWEEN them and collapse
    // `/event/election/2026-midterms` into one segment.
    expect(unresolvedPath("event", "election", "2026-midterms")).toBe(
      "/event/election/2026-midterms"
    );
  });

  it("a slash inside a segment does not become a path separator", () => {
    // Next hands `generateMetadata` a DECODED segment, so this is reachable.
    // `app/tournaments/[slug]/layout.tsx` interpolated the slug raw.
    const path = unresolvedPath("tournaments", "us-open/../../admin");
    expect(path).toBe("/tournaments/us-open%2F..%2F..%2Fadmin");
    expect(new URL(path, "https://route-path.invalid").pathname).toBe(
      "/tournaments/us-open%2F..%2F..%2Fadmin"
    );
  });
});

describe("app/tournaments/[slug]/layout", () => {
  it("a dead slug no longer sends the home page's twitter tags", async () => {
    stubStatus(404);
    const meta = await tournamentMetadata({
      params: Promise.resolve({ slug: "no-such-tournament-xyz" }),
    });

    expect(asText(meta.twitter?.title)).not.toBe(HOME_TITLE);
    expect(asText(meta.twitter?.description)).not.toBe(HOME_BLURB);
    // Stated, not merely different — an omitted block is what inherited.
    expect(asText(meta.twitter?.title)).toBe("This tournament isn't on Bain Luck | Bain Luck");
    expect(meta.twitter?.images).toHaveLength(1);

    // #5813's half, unchanged.
    expect(meta.alternates?.canonical).toBe("/tournaments/no-such-tournament-xyz");
    expect(meta.openGraph?.url).toBe("/tournaments/no-such-tournament-xyz");
    expect(meta.robots).toEqual({ index: false, follow: true });
  });

  it("a 500 is a bad minute, not a missing tournament", async () => {
    stubStatus(500);
    const meta = await tournamentMetadata({ params: Promise.resolve({ slug: "us-open" }) });

    expect(asText(meta.title)).toBe("Tournament Odds");
    expect(meta.robots).toBeUndefined();
    expect(meta.alternates?.canonical).toBe("/tournaments/us-open");
  });

  it("a live tournament is untouched", async () => {
    // The control. #5813 is live and correct; this fix must not move it.
    stubStatus(200, {
      title: "US Open 2026",
      subtitle: "Flushing Meadows",
      boards: [
        {
          title: "Men's singles",
          entries: [{ name: "Alexander Zverev", probability: 0.57 }],
        },
      ],
    });
    const meta = await tournamentMetadata({ params: Promise.resolve({ slug: "us-open" }) });

    expect(asText(meta.title)).toContain("US Open 2026");
    expect(meta.alternates?.canonical).toBe("/tournaments/us-open");
    expect(meta.robots).toBeUndefined();
    expect(asText(meta.twitter?.title)).not.toBe(HOME_TITLE);
  });
});

describe("app/event/[domain]/[slug]/layout", () => {
  it("a dead slug no longer sends the home page's twitter tags", async () => {
    stubStatus(404);
    const meta = await conceptMetadata({
      params: Promise.resolve({ domain: "election", slug: "no-such-slug-xyz" }),
    });

    expect(asText(meta.twitter?.title)).not.toBe(HOME_TITLE);
    expect(asText(meta.twitter?.description)).not.toBe(HOME_BLURB);
    expect(asText(meta.twitter?.title)).toBe("This event isn't on Bain Luck | Bain Luck");
    expect(meta.twitter?.images).toHaveLength(1);

    // #5833's half, unchanged — including the two-segment path.
    expect(meta.alternates?.canonical).toBe("/event/election/no-such-slug-xyz");
    expect(meta.openGraph?.url).toBe("/event/election/no-such-slug-xyz");
    expect(meta.robots).toEqual({ index: false, follow: true });
  });

  it("a domain that could never be one is not-found without a request", async () => {
    stubStatus(200, {});
    const meta = await conceptMetadata({
      params: Promise.resolve({ domain: "NOT A DOMAIN", slug: "x" }),
    });

    expect(global.fetch).not.toHaveBeenCalled();
    expect(asText(meta.title)).toBe("This event isn't on Bain Luck");
    // The refused segments still have to produce a legal path.
    expect(new URL(String(meta.alternates?.canonical), "https://route-path.invalid").origin).toBe(
      "https://route-path.invalid"
    );
  });

  it("a 500 is a bad minute, not a missing event", async () => {
    stubStatus(500);
    const meta = await conceptMetadata({
      params: Promise.resolve({ domain: "election", slug: "2026-midterms" }),
    });

    expect(asText(meta.title)).toBe("Event Odds");
    expect(meta.robots).toBeUndefined();
    expect(meta.alternates?.canonical).toBe("/event/election/2026-midterms");
  });

  it("a live concept is untouched, and still canonicals to the PAYLOAD's slug", async () => {
    // The control, and #5833's specific rule: a concept is reachable by the bare
    // key and by the pretty slug the backend supplies, and the payload's own is
    // the canonical. The miss branch cannot know that, which is why it uses the
    // requested one — this asserts the resolved branch still does not.
    stubStatus(200, {
      event: { key: "event:ufc:26sep15", slug: "contender-series-hunt-vs-perea-26sep15" },
      name: "UFC Fight Night",
    });
    const meta = await conceptMetadata({
      params: Promise.resolve({ domain: "ufc", slug: "26sep15" }),
    });

    expect(meta.alternates?.canonical).toBe(
      "/event/ufc/contender-series-hunt-vs-perea-26sep15"
    );
    expect(meta.robots).toBeUndefined();
    expect(asText(meta.twitter?.title)).not.toBe(HOME_TITLE);
  });
});
