// UX-P065 (#1744 step 2a) — the between-editions strip.
//
// The payoff case is the DEFAULT state of a major's page: a competition is
// between editions ~51 weeks a year. On 2026-08-12 event:golf:the-masters served
// April's settled Masters with nothing saying the 2027 edition existed.
//
// The date maths is asserted at UTC boundaries on purpose. The component reads
// UTC parts everywhere rather than local ones, so a runner in a negative offset
// cannot shift "April 8" to "April 7" — gotcha #44's family, one layer out: the
// fixture dates are real, so a test that let the local clock in would be picking
// a timezone to fail in.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import NextEditionStrip, {
  daysUntil,
  formatEditionWindow,
} from "../../components/event/NextEditionStrip";

const MASTERS = {
  slug: "the-masters",
  name: "The Masters",
  domain: "golf",
  next_edition: {
    name: "The Masters 2027",
    slug: "masters-2027",
    concept_key: "event:golf:masters-2027",
    start: "2027-04-08",
    end: "2027-04-11",
  },
  last_edition: null,
};

describe("NextEditionStrip", () => {
  test("a settled major says when the competition returns", () => {
    const html = renderToStaticMarkup(
      <NextEditionStrip competition={MASTERS} settled />,
    );
    expect(html).toContain("The Masters");
    expect(html).toContain("April 8–11, 2027");
    expect(html).toContain("Next edition");
  });

  test("never links the next edition's concept key", () => {
    // Two declared edition keys 404 in production (masters-2027, ryder-cup-2027)
    // while their year-less siblings serve. A strip added to prove a point about
    // identity must not ship a dead breadcrumb doing it.
    const html = renderToStaticMarkup(
      <NextEditionStrip competition={MASTERS} settled />,
    );
    expect(html).not.toContain("<a ");
    expect(html).not.toContain("masters-2027");
  });

  test("renders nothing while the edition is live or upcoming", () => {
    // Telling a reader watching the Masters that the Masters returns in April is
    // nonsense — the edition they are on IS the next one.
    expect(
      renderToStaticMarkup(<NextEditionStrip competition={MASTERS} settled={false} />),
    ).toBe("");
  });

  test("honest-empty: no competition, no next edition, no unparseable dates", () => {
    expect(renderToStaticMarkup(<NextEditionStrip competition={null} settled />)).toBe("");
    expect(
      renderToStaticMarkup(
        <NextEditionStrip
          competition={{ ...MASTERS, next_edition: null }}
          settled
        />,
      ),
    ).toBe("");
    expect(
      renderToStaticMarkup(
        <NextEditionStrip
          competition={{
            ...MASTERS,
            next_edition: { ...MASTERS.next_edition, start: null, end: null },
          }}
          settled
        />,
      ),
    ).toBe("");
  });
});

describe("formatEditionWindow", () => {
  test("same month", () => {
    expect(formatEditionWindow("2027-04-08", "2027-04-11")).toBe("April 8–11, 2027");
  });
  test("single day collapses", () => {
    expect(formatEditionWindow("2027-03-14", "2027-03-14")).toBe("March 14, 2027");
    expect(formatEditionWindow("2027-03-14", null)).toBe("March 14, 2027");
  });
  test("crosses a month", () => {
    expect(formatEditionWindow("2027-05-08", "2027-05-30")).toBe("May 8–30, 2027");
    expect(formatEditionWindow("2027-03-16", "2027-04-05")).toBe("March 16 – April 5, 2027");
  });
  test("crosses a year", () => {
    expect(formatEditionWindow("2026-12-30", "2027-01-02")).toBe(
      "December 30, 2026 – January 2, 2027",
    );
  });
  test("unparseable is null, never a partial string", () => {
    expect(formatEditionWindow(null, null)).toBeNull();
    expect(formatEditionWindow("soon", "later")).toBeNull();
  });
});

describe("daysUntil", () => {
  const at = (iso: string) => new Date(`${iso}T00:00:00Z`);

  test("counts whole days from today, UTC", () => {
    expect(daysUntil("2027-04-08", at("2027-04-07"))).toBe(1);
    expect(daysUntil("2027-04-08", at("2026-08-12"))).toBe(239);
  });

  test("does not depend on the time of day", () => {
    // The countdown is computed client-side precisely because the envelope it
    // rides in is mirrored for up to 24h; it must not itself wobble within a day.
    expect(daysUntil("2027-04-08", new Date("2027-04-07T00:00:01Z"))).toBe(1);
    expect(daysUntil("2027-04-08", new Date("2027-04-07T23:59:59Z"))).toBe(1);
  });

  test("the start day and anything past it is not a countdown", () => {
    expect(daysUntil("2027-04-08", at("2027-04-08"))).toBeNull();
    expect(daysUntil("2027-04-08", at("2027-04-09"))).toBeNull();
    expect(daysUntil(null, at("2026-08-12"))).toBeNull();
  });
});
