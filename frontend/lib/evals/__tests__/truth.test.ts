/**
 * #12102 S1 — the truth labels on /evals print the right date, in Pacific time,
 * and age the way a reader counts days.
 *
 * Every `now` below is an explicit instant, never the test's clock (gotcha #44).
 * Jest runs in UTC (#2462), which is exactly the zone in which the bare-date
 * trap hides: `new Date("2026-11-05")` is 4 PM on Nov 4 in California.
 */

import { TRUTH_CHIP_MEANING } from "@/lib/evals/copy";
import {
  AGE_AMBER_DAYS,
  calendarMonthLabel,
  ageInDays,
  ageLabel,
  asOfCalendarDate,
  isAgeAmber,
  pacificClockLabel,
  pacificDayLabel,
  truthChipLabel,
} from "@/lib/evals/truth";

const SOURCE = { label: "receipt", href: "https://github.com/alexander-bain/bainluck/pull/11951" };

describe("a run's date prints as the Pacific calendar day", () => {
  it("a bare date is already Pacific: 2026-11-05 is Nov 5, not Nov 4", () => {
    expect(pacificDayLabel("2026-11-05")).toBe("Nov 5");
    expect(asOfCalendarDate("2026-11-05")).toBe("2026-11-05");
  });

  it("a UTC timestamp after Pacific midnight's UTC hour still belongs to the Pacific day", () => {
    // The plan's own post: 01:21:30Z on Nov 6 is 5:21 PM on Nov 5 in California.
    expect(pacificDayLabel("2026-11-06T01:21:30Z")).toBe("Nov 5");
    expect(pacificClockLabel("2026-11-06T01:21:30Z")).toBe("5:21 PM PT");
  });

  it("an offset timestamp is read at its instant, not its wall clock", () => {
    expect(pacificDayLabel("2026-11-05T23:30:00-05:00")).toBe("Nov 5");
    expect(pacificClockLabel("2026-11-05T23:30:00-05:00")).toBe("8:30 PM PT");
  });

  it("a date in the right shape that does not exist is unreadable, not a wrong date", () => {
    // Fable's finding on #12114: "2026-13-01" passed the shape check and printed "UNDEFINED 1".
    expect(pacificDayLabel("2026-13-01")).toBeNull();
    expect(pacificDayLabel("2026-02-30")).toBeNull();
    expect(asOfCalendarDate("2026-00-10")).toBeNull();
    expect(truthChipLabel({ kind: "last_run", asOf: "2026-13-01", source: SOURCE })).toBe(
      "LAST RUN · DATE UNREADABLE"
    );
    expect(truthChipLabel({ kind: "reviewed", asOf: "2026-02-30" })).toBe("LAST REVIEWED · DATE UNREADABLE");
    expect(ageInDays("2026-13-01", new Date("2026-11-06T07:30:00Z"))).toBeNull();
    // A real leap day still reads.
    expect(pacificDayLabel("2028-02-29")).toBe("Feb 29");
  });

  it("a bare date has no clock, and an unreadable date prints nothing rather than a wrong one", () => {
    expect(pacificClockLabel("2026-11-05")).toBeNull();
    expect(pacificDayLabel("not a date")).toBeNull();
    expect(truthChipLabel({ kind: "last_run", asOf: "not a date", source: SOURCE })).toBe(
      "LAST RUN · DATE UNREADABLE"
    );
  });
});

describe("the chip says which kind of number it is", () => {
  it("LIVE, LAST RUN · NOV 5, LAST REVIEWED · NOV 3, PLANNED", () => {
    expect(truthChipLabel({ kind: "live", asOf: "2026-11-06T00:19:00Z", source: SOURCE })).toBe("LIVE");
    expect(truthChipLabel({ kind: "last_run", asOf: "2026-11-05", source: SOURCE })).toBe(
      "LAST RUN · NOV 5"
    );
    expect(truthChipLabel({ kind: "reviewed", asOf: "2026-11-03" })).toBe("LAST REVIEWED · NOV 3");
    expect(truthChipLabel({ kind: "planned", waitingOn: "the ranking harness" })).toBe("PLANNED");
  });
});

describe("age is counted in Pacific calendar days", () => {
  // 2026-11-06T07:30:00Z is 11:30 PM on Nov 5 in California; 08:30Z is 12:30 AM Nov 6.
  const lateNov5 = new Date("2026-11-06T07:30:00Z");
  const earlyNov6 = new Date("2026-11-06T08:30:00Z");

  it("a run dated today is 'today' until Pacific midnight, then '1 day ago'", () => {
    expect(ageInDays("2026-11-05", lateNov5)).toBe(0);
    expect(ageLabel(0)).toBe("today");
    expect(ageInDays("2026-11-05", earlyNov6)).toBe(1);
    expect(ageLabel(1)).toBe("1 day ago");
  });

  it("a timestamp ages from its Pacific day, not its UTC day", () => {
    // 01:21Z Nov 6 is Nov 5 in California, so at 11:30 PM Nov 5 it is still today.
    expect(ageInDays("2026-11-06T01:21:30Z", lateNov5)).toBe(0);
  });

  it("counts across a month boundary and the daylight-saving change", () => {
    // Nov 1, 2026 is the fall-back Sunday; Oct 30 → Nov 5 is six calendar days.
    expect(ageInDays("2026-10-30", lateNov5)).toBe(6);
    expect(ageLabel(6)).toBe("6 days ago");
  });

  it("turns amber strictly after the bar: exactly two weeks is not amber, one day more is", () => {
    expect(AGE_AMBER_DAYS).toBe(14);
    expect(isAgeAmber(AGE_AMBER_DAYS)).toBe(false);
    expect(isAgeAmber(AGE_AMBER_DAYS + 1)).toBe(true);
    // Oct 22 → Nov 5 is exactly 14 days; Oct 21 is 15.
    expect(isAgeAmber(ageInDays("2026-10-22", lateNov5) as number)).toBe(false);
    expect(isAgeAmber(ageInDays("2026-10-21", lateNov5) as number)).toBe(true);
  });

  it("an unreadable date has no age rather than a made-up one", () => {
    expect(ageInDays("soon", lateNov5)).toBeNull();
  });
});

describe("the legend says the amber bar in words, and the words match the constant", () => {
  it("'after two weeks' is AGE_AMBER_DAYS", () => {
    // If the bar moves, this fails until the sentence moves with it.
    const words: Record<number, string> = { 7: "one week", 14: "two weeks", 21: "three weeks" };
    expect(words[AGE_AMBER_DAYS]).toBeDefined();
    expect(TRUTH_CHIP_MEANING.last_run).toContain(`after ${words[AGE_AMBER_DAYS]}`);
  });
});

describe("a month in a gap row prints with its year", () => {
  it("2026-07 is July 2026; month 13 is unreadable", () => {
    expect(calendarMonthLabel("2026-07")).toBe("July 2026");
    expect(calendarMonthLabel("2026-13")).toBeNull();
    expect(calendarMonthLabel("July")).toBeNull();
  });
});
