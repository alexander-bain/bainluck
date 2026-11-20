import { API_URL, fetchFeed, setAuthTokenGetter } from "@/lib/api";
import { FEED_BOOT_GLOBAL } from "@/lib/discover/feedBoot";
import { heroOutcome } from "@/lib/discover/heroOutcome";
import { leaderFirst, printsAPercent } from "@/lib/discover/leaderOrder";
import { normalizeFeedNumbers } from "@/lib/discover/feedNumbers";
import type { FeedFuturesData, FeedResponse } from "@/lib/types";

// The old cache's Decimal text, including a bundle one level below the page.
function wirePage() {
  return {
    items: [{
      type: "bundle",
      data: {
        title: "2027",
        items: [{
          type: "futures",
          data: {
            id: 59934328,
            name: 'Will "Onslaught" score at least 80 on the Tomatometer?',
            top_outcomes: [
              { id: 1, name: 'No: "Onslaught" score at least 80 on the Tomatometer', probability: "0.880000" },
              { id: 2, name: '"Onslaught" score at least 80 on the Tomatometer', probability: "0.120000" },
            ],
            deadline_member: {
              yes_probability: "0.120000",
              no_probability: "0.880000",
              movement_basis: { basis_price: "0.185000" },
              supported_move: "-0.065000",
            },
            label: "3.7000",
            external_id: "00123",
            price_observed_at: "2026-10-14T23:45:00+00:00",
          },
        }],
      },
    }],
    total: 1, limit: 20, offset: 0, has_more: false,
  };
}

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200 });
}

const slot = globalThis as unknown as Record<string, unknown>;
const originalFetch = global.fetch;
const originalWindow = slot.window;

beforeEach(() => {
  setAuthTokenGetter(null);
  delete slot[FEED_BOOT_GLOBAL];
  slot.window = { localStorage: { getItem: () => null, setItem: () => {} } };
  global.fetch = jest.fn();
});

afterEach(() => {
  delete slot[FEED_BOOT_GLOBAL];
  if (originalWindow === undefined) delete slot.window;
  else slot.window = originalWindow;
  global.fetch = originalFetch;
});

it.each(["request", "boot"])("decodes Decimal text before %s data reaches card decisions", async (path) => {
  const raw = wirePage();
  if (path === "boot") {
    slot[FEED_BOOT_GLOBAL] = {
      url: `${API_URL}/api/feed?limit=20&event_pct=0.15`,
      startedAt: 0,
      readyAt: 1,
      response: Promise.resolve(response(raw)),
    };
  } else {
    (global.fetch as jest.Mock).mockResolvedValue(response(raw));
  }

  const page = await fetchFeed(
    { limit: 20, event_pct: 0.15 },
    { sharedAnonEligible: true, authenticated: false, hasInMemoryInteraction: false },
  );
  const bundle = page.items[0].data as unknown as { items: { data: FeedFuturesData }[] };
  const data = bundle.items[0].data;
  expect(heroOutcome(data.top_outcomes)?.id).toBe(2);
  expect(heroOutcome(data.top_outcomes)?.probability).toBe(0.12);
  expect(data.top_outcomes.every((row) => printsAPercent(row.probability))).toBe(true);
  expect(leaderFirst(data.top_outcomes).map((row) => row.id)).toEqual([1, 2]);
  expect(data.deadline_member?.yes_probability).toBe(0.12);
  expect(data.deadline_member?.no_probability).toBe(0.88);
  expect(data.deadline_member?.movement_basis?.basis_price).toBe(0.185);
  expect(data.deadline_member?.supported_move).toBe(-0.065);
  expect((data as unknown as Record<string, unknown>).label).toBe("3.7000");
  expect(data.external_id).toBe("00123");
  expect(data.price_observed_at).toBe("2026-10-14T23:45:00+00:00");
  // The network object belongs to its caller; decoding must not rewrite it.
  expect(raw.items[0].data.items[0].data.top_outcomes[1].probability).toBe("0.120000");
  expect(global.fetch).toHaveBeenCalledTimes(path === "boot" ? 0 : 1);
});

it("keeps invalid readings missing and preserves real zero", async () => {
  const raw = wirePage();
  const values = ["", " ", "0x10", "Infinity", "NaN", "1e999", "oops", "0.000000", "6.75e-2"];
  raw.items[0].data.items[0].data.top_outcomes = values.map((probability, id) => ({ id, name: String(id), probability }));
  (global.fetch as jest.Mock).mockResolvedValue(response(raw));
  const page = await fetchFeed();
  const bundle = page.items[0].data as unknown as { items: { data: FeedFuturesData }[] };
  expect(bundle.items[0].data.top_outcomes.map((row) => row.probability)).toEqual([
    null, null, null, null, null, null, null, 0, 0.0675,
  ]);
});

it("retains numeric objects and preserves numeric-looking labels", () => {
  const page = {
    items: [{ type: "futures", data: {
      id: 1, name: "2027", label: "3.7000", probability: 0.12,
      resolution_date: "2026-10-31", external_id: "00123",
      settlement: { status: "open", is_settled: false, reason: "unverified" },
    } }],
    total: 1, limit: 20, offset: 0, has_more: false,
  } as unknown as FeedResponse;
  expect(normalizeFeedNumbers(page)).toBe(page);
  expect(normalizeFeedNumbers(page).items[0].data).toBe(page.items[0].data);
});
