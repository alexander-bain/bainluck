// A DELIBERATE REMOVAL MUST NOT BE PAINTED AS A MALFUNCTION — #5857.
//
// `GET /api/events/{id}` answers 410 Gone for a row in `RETIRED_STATUSES`
// (`merged`, `voided`), and `lib/loadFailure.ts` has given that its own honest
// title and sentence since #2783/lane1/132. What it could not give it was a
// COLOUR: `components/ErrorMessage.tsx` rendered every `message` in
// `text-accent-danger`, so on production (390px, 2026-09-13, live/191's
// pre-flight of the #5532 retirement) a reader saw
//
//   This event is no longer listed
//   This fixture was removed from the schedule — it was either a duplicate of
//   another game or a game that will not be played.            <- in red
//
// in exactly the red of
//
//   Too many requests
//   Rate limit exceeded: 60/minute                             <- in red
//
// One of those is something going wrong. The other is the schedule. The
// retirement moves 11,117 unreachable rows to `voided`, so every one of those
// ids then answers 410 on this route and wears the wrong colour.
//
// WHAT IS ASSERTED. The tone is a field on `LoadFailure`, so it is testable in
// two places and both matter: the module DECIDES (404/410 are `info`, every
// real failure is `error`), and the component DRAWS (`info` in
// `text-text-secondary`, `error` in `text-accent-danger`).
//
// BOTH DIRECTIONS PER GOTCHA #43. A component that simply stopped using
// `text-accent-danger` would pass every "the removal is not red" assertion and
// be a worse bug than the one it replaces — a rate-limit failure drawn as
// ordinary body text. Every `info` case below has an `error` sibling proving
// the danger arm is still wired, and the sentences themselves are asserted
// unchanged, because the fix was only ever allowed to change the colour.

import { renderToStaticMarkup } from "react-dom/server";
import ErrorMessage from "@/components/ErrorMessage";
import { describeLoadFailure } from "@/lib/loadFailure";

function apiError(status: number | undefined, message: string) {
  const e = new Error(message) as Error & { status?: number };
  if (status !== undefined) e.status = status;
  return e;
}

// The sentence the backend actually sends (`routes/events.py`, `get_event`).
const SERVED_410 =
  "This fixture was removed from the schedule — it was either a duplicate of " +
  "another game or a game that will not be played.";

/** The sentence a throttled reader gets, and the control for every case here. */
const SERVED_429 = "Rate limit exceeded: 60/minute";

const DANGER = "text-accent-danger";
const QUIET = "text-text-secondary";

describe("the module decides which outcomes are answers rather than failures", () => {
  it("tones a retired fixture (410) as information", () => {
    const failure = describeLoadFailure(apiError(410, SERVED_410), "event");
    expect(failure.tone).toBe("info");
    // …and says exactly what it said before. The colour was the whole defect.
    expect(failure.title).toBe("This event is no longer listed");
    expect(failure.message).toBe(SERVED_410);
    expect(failure.retryable).toBe(false);
  });

  it("tones a missing thing (404) as information", () => {
    const failure = describeLoadFailure(apiError(404, ""), "event");
    expect(failure.tone).toBe("info");
    expect(failure.message).toBe("This event does not exist, or it has been removed.");
  });

  it.each([
    [429, SERVED_429],
    [500, "boom"],
    [503, "boom"],
    [403, "boom"],
    [400, "boom"],
  ])("keeps status %i an error, because it is one", (status, served) => {
    expect(describeLoadFailure(apiError(status, served), "event").tone).toBe("error");
  });

  it("keeps a connection failure an error — no status is not a 404", () => {
    expect(describeLoadFailure(apiError(undefined, ""), "event").tone).toBe("error");
    expect(describeLoadFailure(null, "event").tone).toBe("error");
  });
});

describe("what the reader actually sees on the card", () => {
  const render = (status: number, served: string) => {
    const failure = describeLoadFailure(apiError(status, served), "event");
    return renderToStaticMarkup(
      <ErrorMessage
        title={failure.title}
        message={failure.message}
        onRetry={failure.retryable ? () => {} : undefined}
        tone={failure.tone}
      />,
    );
  };

  it("draws the removed fixture's sentence in quiet body text, not danger red", () => {
    const html = render(410, SERVED_410);

    // The sentence is still there, whole — this is a colour change and nothing
    // else. (`—` and `'` survive `renderToStaticMarkup`; `&` and `<` would not,
    // and this sentence has neither.)
    expect(html).toContain(SERVED_410);
    expect(html).toContain(QUIET);
    expect(html).not.toContain(DANGER);
  });

  it("still draws a rate limit in danger red", () => {
    const html = render(429, SERVED_429);

    expect(html).toContain(SERVED_429);
    expect(html).toContain(DANGER);
    // The exact regression the both-directions rule is here for: a component
    // that just deleted the red arm passes the 410 case above and breaks this.
    expect(html).not.toContain(`${QUIET} mb-3`);
  });

  it("still draws a server error in danger red", () => {
    expect(render(500, "")).toContain(DANGER);
  });

  it("defaults to danger when no tone is passed at all", () => {
    // Most call sites pass a hand-written failure sentence and no tone. Their
    // rendering must be byte-unchanged by #5857, which is what a default of
    // `"error"` buys.
    const html = renderToStaticMarkup(
      <ErrorMessage message="Failed to load event" />,
    );
    expect(html).toContain(DANGER);
    expect(html).toContain("Something went wrong");
  });
});

describe("the pages that show a 410 or a 404 thread the tone through", () => {
  // A guard on the module and the component can both be green while the page
  // between them drops the field on the floor — which is precisely how the
  // defect survived #2783's correct copy layer for ten days.
  const read = (p: string) =>
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    (require("fs") as typeof import("fs")).readFileSync(
      (require("path") as typeof import("path")).join(process.cwd(), p),
      "utf8",
    );

  it("the event page passes the failure's own tone to the card", () => {
    expect(read("app/events/[id]/page.tsx")).toContain("tone={failure.tone}");
  });

  it("the concept event page's not-found card is information", () => {
    expect(read("app/event/[domain]/[slug]/page.tsx")).toContain('tone="info"');
  });
});
