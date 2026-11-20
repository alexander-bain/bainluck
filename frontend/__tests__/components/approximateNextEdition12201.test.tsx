// #12201 — an edition nobody has announced is printed as its month.
//
// The calendar marks a not-yet-announced edition `date_confidence: approximate`:
// a conventional window, kept so the horizon checks can warn ahead of it. The
// strip and the concept header used to print every edition to the day, so a
// reader would have read "Emmy Awards returns September 12, 2027 · in 307 days"
// for a ceremony the Academy has only placed "in September". Now an approximate
// edition prints as "September 2027", with no countdown. A confirmed edition is
// unchanged.
//
// The clock is frozen, because the confirmed control asserts its countdown.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import NextEditionStrip from "../../components/event/NextEditionStrip";
import { conceptHeaderDate, formatEditionWindow } from "../../lib/eventConceptDisplay";

const NOW = new Date("2026-11-09T17:00:00Z");

// React's static markup puts a `<!-- -->` marker between adjacent text parts, so
// each assertion allows one at every join instead of rewriting the markup.
const M = "(?:<!-- -->)?";
const says = (...parts: string[]) => new RegExp(parts.join(M));

function competition(
  name: string,
  start: string,
  end: string,
  date_confidence: "confirmed" | "approximate" | null,
) {
  return {
    slug: name.toLowerCase().replace(/ /g, "-"),
    name,
    domain: null,
    next_edition: { name, slug: null, concept_key: null, start, end, date_confidence },
    last_edition: null,
  };
}

beforeEach(() => {
  jest.useFakeTimers({ now: NOW });
});
afterEach(() => {
  jest.useRealTimers();
});

describe("NextEditionStrip, approximate edition", () => {
  test("a ceremony placed only in a month prints the month and no countdown", () => {
    const html = renderToStaticMarkup(
      <NextEditionStrip
        competition={competition("Emmy Awards", "2027-09-12", "2027-09-12", "approximate")}
        settled
      />,
    );
    expect(html).toMatch(says("Emmy Awards</span> returns ", "in ", "September 2027", "\\."));
    expect(html).not.toContain("September 12");
    expect(html).not.toContain("days");
  });

  test("a window across two months names both", () => {
    const html = renderToStaticMarkup(
      <NextEditionStrip
        competition={competition("US Open", "2027-08-30", "2027-09-12", "approximate")}
        settled
      />,
    );
    expect(html).toMatch(says("US Open</span> returns ", "in ", "August – September 2027", "\\."));
    expect(html).not.toContain("days");
  });

  test("control: a confirmed edition still prints its days and its countdown", () => {
    const html = renderToStaticMarkup(
      <NextEditionStrip
        competition={competition("Abu Dhabi Grand Prix", "2027-12-12", "2027-12-12", "confirmed")}
        settled
      />,
    );
    expect(html).toMatch(says("Abu Dhabi Grand Prix</span> returns ", "December 12, 2027"));
    expect(html).toMatch(says(" · in ", "398", " days"));
  });

  test("control: an edition with no confidence on it prints as it always has", () => {
    const html = renderToStaticMarkup(
      <NextEditionStrip
        competition={competition("The Open Championship", "2027-07-15", "2027-07-18", null)}
        settled
      />,
    );
    expect(html).toMatch(says("The Open Championship</span> returns ", "July 15–18, 2027"));
    expect(html).toMatch(says(" · in ", "248", " days"));
  });
});

describe("formatEditionWindow, approximate", () => {
  test("one month", () => {
    expect(formatEditionWindow("2027-09-12", "2027-09-12", true)).toBe("September 2027");
    expect(formatEditionWindow("2027-09-04", "2027-09-26", true)).toBe("September 2027");
  });
  test("two months in one year", () => {
    expect(formatEditionWindow("2027-08-30", "2027-09-12", true)).toBe("August – September 2027");
  });
  test("across a new year", () => {
    expect(formatEditionWindow("2027-12-30", "2028-01-02", true)).toBe(
      "December 2027 – January 2028",
    );
  });
  test("an unparseable start is still nothing", () => {
    expect(formatEditionWindow(null, "2027-09-12", true)).toBeNull();
  });
  test("the default is unchanged: to the day", () => {
    expect(formatEditionWindow("2027-09-12", "2027-09-12")).toBe("September 12, 2027");
  });
});

describe("conceptHeaderDate's next-edition fallback", () => {
  test("an upcoming standing competition with an approximate edition prints the month", () => {
    expect(
      conceptHeaderDate(
        "upcoming",
        null,
        null,
        { start: "2027-09-12", end: "2027-09-12", date_confidence: "approximate" },
        NOW,
      ),
    ).toBe("September 2027");
  });
  test("control: a confirmed edition prints its days", () => {
    expect(
      conceptHeaderDate(
        "upcoming",
        null,
        null,
        { start: "2027-09-17", end: "2027-09-19", date_confidence: "confirmed" },
        NOW,
      ),
    ).toBe("September 17–19, 2027");
  });
});
