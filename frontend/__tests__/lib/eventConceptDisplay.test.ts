// #999 slice 1: event-concept display helpers.

import {
  statusLabel,
  fieldOrder,
  childLeader,
  eventDateRange,
} from "../../lib/eventConceptDisplay";

describe("statusLabel", () => {
  test("maps statuses", () => {
    expect(statusLabel("live")).toBe("Live");
    expect(statusLabel("settled")).toBe("Settled");
    expect(statusLabel("upcoming")).toBe("Upcoming");
    expect(statusLabel("")).toBe("Upcoming");
  });
});

describe("fieldOrder", () => {
  test("sorts competitors by probability desc; nulls last", () => {
    const out = fieldOrder([
      { name: "A", probability: 0.1 },
      { name: "B", probability: 0.3 },
      { name: "C", probability: null },
      { name: "D", probability: 0.2 },
    ]);
    expect(out.map((c) => c.name)).toEqual(["B", "D", "A", "C"]);
  });
  test("empty is safe", () => {
    expect(fieldOrder([])).toEqual([]);
  });
});

describe("childLeader", () => {
  test("picks the top outcome", () => {
    const lead = childLeader({
      market_id: 1,
      market_name: "A vs B",
      outcomes: [
        { name: "A", probability: 0.4 },
        { name: "B", probability: 0.6 },
      ],
    });
    expect(lead).toEqual({ name: "B", probability: 0.6 });
  });
  test("falls back to child name/probability with no outcomes", () => {
    expect(childLeader({ market_id: 2, name: "Yes", probability: 0.3 })).toEqual({
      name: "Yes",
      probability: 0.3,
    });
  });
  test("null when nothing to show", () => {
    expect(childLeader({ market_id: 3 })).toBeNull();
  });
});

describe("eventDateRange", () => {
  test("range, single, none", () => {
    expect(eventDateRange("2026-04-09", "2026-04-12")).toMatch(/–/);
    expect(eventDateRange("2026-04-09", null)).not.toMatch(/–/);
    expect(eventDateRange(null, null)).toBeNull();
  });
});
