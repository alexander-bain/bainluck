// L2-217 Item 3 / C88 — the My Stuff attribution packet, checked against the
// SAME invariants the backend authority contract enforces
// (`backend/scripts/evals/my_stuff_first_card.py::validate_telemetry`):
//   • all 12 attribution fields present, `surface == "my_stuff"`
//   • no uid / email / token / item ids / market text
//   • `first_render_ms >= 0` only ever alongside `item_count > 0`
//   • model assignment (`data_ready`) is NOT a first render

import {
  buildMyStuffTelemetry,
  classifyMyStuffOutcome,
  reportMyStuffTelemetry,
  webAppBuild,
  MY_STUFF_REQUIRED_TELEMETRY_FIELDS,
  type MyStuffTelemetry,
} from "@/lib/myStuffTelemetry";

jest.mock("@/lib/analytics", () => ({
  __esModule: true,
  trackEvent: jest.fn(),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
import { trackEvent } from "@/lib/analytics";
const trackEventMock = trackEvent as jest.Mock;

const FORBIDDEN = ["user_id", "uid", "email", "token", "session_id", "item_ids", "market_text"];

beforeEach(() => trackEventMock.mockReset());

describe("packet shape", () => {
  it("carries every required attribution field and the my_stuff surface", () => {
    const packet = buildMyStuffTelemetry({
      stage: "data_ready",
      outcomeClass: "network_success",
      itemCount: 6,
      networkMs: 120.4,
      requiredDataReadyMs: 133.9,
    });
    for (const field of MY_STUFF_REQUIRED_TELEMETRY_FIELDS) {
      expect(packet).toHaveProperty(field);
    }
    expect(packet.surface).toBe("my_stuff");
  });

  it("never carries identity or content", () => {
    const packet = buildMyStuffTelemetry({
      stage: "first_render",
      outcomeClass: "network_success",
      itemCount: 3,
      firstRenderMs: 400,
    });
    for (const key of FORBIDDEN) {
      expect(packet).not.toHaveProperty(key);
    }
    // Nothing free-text beyond the bounded label set + build tag.
    expect(typeof packet.outcome_class).toBe("string");
    expect(packet.app_build).toBe(webAppBuild());
  });

  it("reports -1 for stages that did not run, and clamps negatives", () => {
    const packet = buildMyStuffTelemetry({
      stage: "data_ready",
      outcomeClass: "required_failure",
      itemCount: 0,
      networkMs: -5,
    });
    expect(packet.backend_elapsed_ms).toBe(-1);
    expect(packet.decode_ms).toBe(-1);
    expect(packet.cache_age_seconds).toBe(-1);
    expect(packet.network_ms).toBe(0); // clamped, not negative
  });
});

describe("first render is a real card, not a model assignment", () => {
  it("data_ready never reports a first-card time even when one is passed", () => {
    const packet = buildMyStuffTelemetry({
      stage: "data_ready",
      outcomeClass: "network_success",
      itemCount: 5,
      firstRenderMs: 999,
    });
    expect(packet.first_render_ms).toBe(-1);
  });

  it("an empty success cannot report a first-card time", () => {
    const packet = buildMyStuffTelemetry({
      stage: "first_render",
      outcomeClass: "empty_success",
      itemCount: 0,
      firstRenderMs: 250,
    });
    expect(packet.first_render_ms).toBe(-1);
    expect(packet.item_count).toBe(0);
  });

  it("a real render reports the time, with items", () => {
    const packet = buildMyStuffTelemetry({
      stage: "first_render",
      outcomeClass: "network_success",
      itemCount: 4,
      requiredDataReadyMs: 200,
      firstRenderMs: 260,
    });
    expect(packet.first_render_ms).toBe(260);
    expect(packet.item_count).toBeGreaterThan(0);
    // The two milestones stay distinguishable.
    expect(packet.first_render_ms).toBeGreaterThan(packet.required_data_ready_ms);
  });

  it("holds the backend invariant: first_render_ms >= 0 implies item_count > 0", () => {
    const cases: MyStuffTelemetry[] = [
      buildMyStuffTelemetry({ stage: "first_render", outcomeClass: "empty_success", itemCount: 0, firstRenderMs: 10 }),
      buildMyStuffTelemetry({ stage: "first_render", outcomeClass: "cancelled", itemCount: 0, firstRenderMs: 10 }),
      buildMyStuffTelemetry({ stage: "data_ready", outcomeClass: "network_success", itemCount: 9, firstRenderMs: 10 }),
      buildMyStuffTelemetry({ stage: "first_render", outcomeClass: "network_success", itemCount: 9, firstRenderMs: 10 }),
    ];
    for (const packet of cases) {
      if (packet.first_render_ms >= 0) expect(packet.item_count).toBeGreaterThan(0);
    }
  });
});

describe("outcome classification mirrors the C88 decision core", () => {
  const base = {
    identityReady: true,
    dispatchPrincipal: "user:a",
    currentPrincipal: "user:a",
    requiredItemCount: 5,
  } as const;

  it("no stable identity → sign_in_required", () => {
    expect(
      classifyMyStuffOutcome({ ...base, identityReady: false, requiredRequest: "success" })
    ).toBe("sign_in_required");
  });

  it("identity change beats success — a superseded response is never a success", () => {
    expect(
      classifyMyStuffOutcome({
        ...base,
        currentPrincipal: "user:b",
        requiredRequest: "success",
        optionalRequest: "success",
      })
    ).toBe("identity_superseded");
  });

  it("cancellation is quiet, not a failure", () => {
    expect(classifyMyStuffOutcome({ ...base, requiredRequest: "cancelled" })).toBe("cancelled");
  });

  it("required failure classifies as required_failure regardless of the optional", () => {
    expect(
      classifyMyStuffOutcome({
        ...base,
        requiredRequest: "failure",
        optionalRequest: "success",
        requiredItemCount: 0,
      })
    ).toBe("required_failure");
  });

  it("a hung or failed optional is partial_success, never a blocked load", () => {
    for (const optional of ["hung", "failure"] as const) {
      expect(
        classifyMyStuffOutcome({ ...base, requiredRequest: "success", optionalRequest: optional })
      ).toBe("partial_success");
    }
  });

  it("empty success is distinct from failure", () => {
    expect(
      classifyMyStuffOutcome({ ...base, requiredRequest: "success", requiredItemCount: 0 })
    ).toBe("empty_success");
  });

  it("cache-served and network-served successes are distinguishable", () => {
    expect(
      classifyMyStuffOutcome({ ...base, requiredRequest: "success", fromCache: true })
    ).toBe("swr_cache_hit");
    expect(
      classifyMyStuffOutcome({ ...base, requiredRequest: "success", fromCache: false })
    ).toBe("network_success");
  });
});

describe("emission", () => {
  it("emits one bounded my_stuff_load event through the consent-aware rail", () => {
    const packet = reportMyStuffTelemetry({
      stage: "first_render",
      outcomeClass: "network_success",
      itemCount: 2,
      firstRenderMs: 90,
    });
    expect(trackEventMock).toHaveBeenCalledTimes(1);
    const [name, params] = trackEventMock.mock.calls[0];
    expect(name).toBe("my_stuff_load");
    expect(params).toEqual(packet);
    expect(params.surface).toBe("my_stuff");
  });

  it("never throws or changes rendering when the rail fails", () => {
    trackEventMock.mockImplementation(() => {
      throw new Error("analytics down");
    });
    expect(() =>
      reportMyStuffTelemetry({ stage: "data_ready", outcomeClass: "network_success", itemCount: 1 })
    ).not.toThrow();
    expect(
      reportMyStuffTelemetry({ stage: "data_ready", outcomeClass: "network_success", itemCount: 1 })
    ).toBeNull();
  });
});
