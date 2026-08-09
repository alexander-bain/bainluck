// UX-P032 (#1600) — the tennis draw that fired ~600 doomed Wikipedia requests.
//
// Two independent halves, tested separately because they fail separately:
//
//   1. `isLikelyPersonName` — stop asking about things that are not people.
//      This is what removes most of the requests.
//   2. `getWikipediaImage`'s bounding — dedupe, a concurrency cap, and a circuit
//      breaker. This is what makes a STORM impossible even when half 1 lets
//      something through, for every caller including ones not yet written.
//
// Gotcha #43 throughout: every restriction is tested in BOTH directions. The
// flood gets bounded AND the legitimate case still works — a name guard that
// quietly rejects real golfers would "fix" #1600 by deleting the feature.

import {
  isLikelyPersonName,
  isPersonFieldDomain,
} from "../../lib/eventConceptDisplay";
import {
  LookupCircuit,
  getWikipediaImage,
  __resetWikipediaLookupState,
} from "../../lib/images";

describe("isLikelyPersonName — rejects market outcomes (the flood direction)", () => {
  it("rejects the exact strings the rail caught being sent to Wikipedia", () => {
    // Verbatim from browser-audit runs 30864618239 and 31323268137.
    for (const label of [
      "Adrian Mannarino -1.5 games",
      "Brandon Nakashima -2.5 games",
      "Cameron Norrie -4.5 games",
      "Jakub Mensik -4.5 games",
      "Over 16.5 games",
      "Under",
      "Over",
      "No",
      "Yes",
      "Completed Match",
      "Livesport Prague Open: Marie Bouzkova vs Tereza Valentova",
      "Generali Open: Yannick Hanfmann vs Sebastian Baez Match O/U 21.5",
    ]) {
      expect(isLikelyPersonName(label)).toBe(false);
    }
  });

  it("rejects any name carrying a digit — the whole handicap/threshold family", () => {
    expect(isLikelyPersonName("Under 63.5")).toBe(false);
    expect(isLikelyPersonName("+2.5")).toBe(false);
    expect(isLikelyPersonName("Player 1")).toBe(false);
  });

  it("rejects matchup and market-title shapes", () => {
    expect(isLikelyPersonName("Alcaraz vs Sinner")).toBe(false);
    expect(isLikelyPersonName("Alcaraz v Sinner")).toBe(false);
    expect(isLikelyPersonName("Some Open: Winner")).toBe(false);
  });

  it("rejects empty and blank input without throwing", () => {
    expect(isLikelyPersonName("")).toBe(false);
    expect(isLikelyPersonName("   ")).toBe(false);
    expect(isLikelyPersonName(null)).toBe(false);
    expect(isLikelyPersonName(undefined)).toBe(false);
  });
});

describe("isLikelyPersonName — real competitors still resolve (the other direction)", () => {
  it("accepts real names across every person-field domain", () => {
    // If this list ever goes red, the fix has started deleting headshots
    // instead of deleting doomed requests. Golf is the one L2-147 shipped for.
    for (const name of [
      "Brandon Nakashima",
      "Carlos Alcaraz",
      "Juan Manuel Cerundolo",
      "Scottie Scheffler",
      "Rory McIlroy",
      "Jon Jones",
      "Israel Adesanya",
      "Tadej Pogacar",
      "Jean-Christophe Peraud",
      "Sebastien Haller",
      "Shane van Gisbergen",
    ]) {
      expect(isLikelyPersonName(name)).toBe(true);
    }
  });

  it("does not mistake a surname that merely STARTS with a keyword", () => {
    // Whole-word matching: "Overton" is not "Over", "Nooijer" is not "No".
    expect(isLikelyPersonName("Connor Overton")).toBe(true);
    expect(isLikelyPersonName("Overton Smith")).toBe(true);
    expect(isLikelyPersonName("Gregory Nooijer")).toBe(true);
  });

  it("is a row-level guard, not a replacement for the domain gate", () => {
    // Both still have to pass; neither subsumes the other. A film title is a
    // plausible "person name" by these rules, and is correctly kept out by the
    // DOMAIN gate rather than this one — which is why this predicate must never
    // be reused on award nominees.
    expect(isPersonFieldDomain("tennis")).toBe(true);
    expect(isPersonFieldDomain("awards")).toBe(false);
    expect(isLikelyPersonName("Anora")).toBe(true);
  });
});

describe("LookupCircuit", () => {
  let clock = 0;
  const circuit = () => new LookupCircuit(3, 1_000, () => clock);

  beforeEach(() => {
    clock = 0;
  });

  it("starts closed and stays closed below the threshold", () => {
    const c = circuit();
    expect(c.isOpen()).toBe(false);
    c.recordFailure();
    c.recordFailure();
    expect(c.isOpen()).toBe(false);
  });

  it("opens on consecutive failures and closes again after the cooldown", () => {
    const c = circuit();
    c.recordFailure();
    c.recordFailure();
    c.recordFailure();
    expect(c.isOpen()).toBe(true);

    clock = 999;
    expect(c.isOpen()).toBe(true);
    clock = 1_000;
    expect(c.isOpen()).toBe(false); // self-heals without a reload
  });

  it("treats ANY answer as health, so scattered failures never open it", () => {
    // A page of 404s is the source answering honestly. Only refusal counts.
    const c = circuit();
    for (let i = 0; i < 20; i += 1) {
      c.recordFailure();
      c.recordFailure();
      c.recordSuccess();
    }
    expect(c.isOpen()).toBe(false);
  });
});

describe("getWikipediaImage — bounding (the storm direction)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.resetAllMocks();
    __resetWikipediaLookupState();
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  function okResponse(source: string | null) {
    return {
      ok: true,
      json: jest.fn().mockResolvedValue(source ? { thumbnail: { source } } : {}),
    } as unknown as Response;
  }

  it("issues ONE request when the same name is requested many times at once", async () => {
    // A large field repeats names across rows. Without in-flight dedupe each row
    // opens its own socket, because nothing has resolved yet for the cache to hit
    // (and under SSR/node there is no localStorage at all).
    global.fetch = jest.fn().mockResolvedValue(okResponse("https://img/x.png"));

    const results = await Promise.all(
      Array.from({ length: 25 }, () => getWikipediaImage("Carlos Alcaraz")),
    );

    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(new Set(results)).toEqual(new Set(["https://img/x.png"]));
  });

  it("never exceeds the concurrency cap, however many names arrive at once", async () => {
    // The cap is what stops us earning the rate limit that produced the throws.
    let inFlight = 0;
    let peak = 0;
    global.fetch = jest.fn().mockImplementation(async () => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      await new Promise((r) => setTimeout(r, 1));
      inFlight -= 1;
      return okResponse("https://img/y.png");
    });

    await Promise.all(
      Array.from({ length: 40 }, (_, i) => getWikipediaImage(`Person Number${i}x`)),
    );

    expect(global.fetch).toHaveBeenCalledTimes(40);
    expect(peak).toBeLessThanOrEqual(4);
  });

  it("stops issuing requests entirely once the source starts refusing us", async () => {
    // THE regression test for #1600's amplifier. Before this, a throw was neither
    // cached nor counted, so every re-render re-fired the whole fan-out.
    global.fetch = jest.fn().mockRejectedValue(new TypeError("Failed to fetch"));

    const names = Array.from({ length: 50 }, (_, i) => `Refused Person${i}x`);
    for (const n of names) {
      // Sequential so the circuit can observe consecutive failures, which is how
      // a real render behaves once the cap is throttling.
      // eslint-disable-next-line no-await-in-loop
      await getWikipediaImage(n);
    }

    // Five throws trip it; the remaining 45 never reach the network.
    expect((global.fetch as jest.Mock).mock.calls.length).toBe(5);
  });

  it("returns null rather than throwing when the lookup fails", async () => {
    global.fetch = jest.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(getWikipediaImage("Someone Unreachable")).resolves.toBeNull();
  });
});

describe("getWikipediaImage — the legitimate path still works (the other direction)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.resetAllMocks();
    __resetWikipediaLookupState();
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  it("still resolves a real thumbnail", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ thumbnail: { source: "https://img/real.png" } }),
    } as unknown as Response);

    await expect(getWikipediaImage("Scottie Scheffler")).resolves.toBe(
      "https://img/real.png",
    );
  });

  it("treats a 404 as 'no article', not as the source refusing us", async () => {
    // 404s must NOT trip the circuit — otherwise one page of unknown names would
    // suppress headshots for every name after it.
    global.fetch = jest
      .fn()
      .mockResolvedValue({ ok: false, json: jest.fn() } as unknown as Response);

    for (let i = 0; i < 20; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await expect(getWikipediaImage(`Unknown Person${i}x`)).resolves.toBeNull();
    }

    // Every one was attempted — the circuit never opened on healthy 404s.
    expect((global.fetch as jest.Mock).mock.calls.length).toBe(20);
  });

  it("recovers on the next name after a transient failure", async () => {
    global.fetch = jest
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue({
        ok: true,
        json: jest.fn().mockResolvedValue({ thumbnail: { source: "https://img/ok.png" } }),
      } as unknown as Response);

    await expect(getWikipediaImage("Blip Person")).resolves.toBeNull();
    await expect(getWikipediaImage("Recovered Person")).resolves.toBe("https://img/ok.png");
  });
});
