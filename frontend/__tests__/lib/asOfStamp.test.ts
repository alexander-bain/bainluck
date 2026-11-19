import { formatAsOfStamp } from "@/lib/asOfStamp";

describe("formatAsOfStamp (Ruling 198-B & #12759)", () => {
  const NOW = new Date("2026-11-15T22:00:00Z");

  it("formats same-day timestamps as 'As of h:mm AM/PM'", () => {
    const sameDay = new Date(NOW.getTime() - 2 * 60 * 60 * 1000).toISOString();
    const out = formatAsOfStamp(sameDay, NOW);
    expect(out).toMatch(/^As of \d{1,2}:\d{2}\s?[AP]M$/);
  });

  it("formats older days in the same year as 'As of Mon D'", () => {
    expect(formatAsOfStamp("2026-11-13T16:00:00Z", NOW)).toBe("As of Nov 13");
    expect(formatAsOfStamp("2026-08-07T18:00:00Z", NOW)).toBe("As of Aug 7");
  });

  it("includes the year when the timestamp is from a prior year", () => {
    expect(formatAsOfStamp("2025-11-13T16:00:00Z", NOW)).toBe("As of Nov 13, 2025");
  });

  it("returns null on missing or invalid input", () => {
    expect(formatAsOfStamp(null, NOW)).toBeNull();
    expect(formatAsOfStamp("", NOW)).toBeNull();
    expect(formatAsOfStamp("not-a-date", NOW)).toBeNull();
  });
});
