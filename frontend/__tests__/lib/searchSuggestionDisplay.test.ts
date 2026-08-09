/**
 * #1620 — the search dropdown's row logic, now shared by the desktop SearchBar
 * and the phone MobileSearchOverlay.
 *
 * ## What was wrong
 *
 * The two dropdowns are mutually exclusive by viewport (`layout.tsx` mounts
 * `MobileSearchTrigger` in a `md:hidden` container and `SearchBar` in a
 * `hidden md:block` one), and their row JSX was duplicated. #993 Slice A —
 * "lead with the answer" — was written into the desktop copy only, so it never
 * reached a single phone. Phones did not regress; they were never brought along.
 *
 * ## Why these assertions are shaped the way they are
 *
 * Every clock assertion injects `now` rather than seeding off `Date.now()`
 * (gotcha #44), and the locale-formatted branches are asserted STRUCTURALLY —
 * "a bare clock time" / "starts with a weekday" — not against literal strings.
 * A literal like "7:35 PM" passes on a PDT laptop and reds in CI's UTC; that
 * exact mistake has red-ed master before.
 */
import type { TypeaheadSuggestion } from "../../lib/api";
import {
  MOVEMENT_MIN_ABS,
  countAnswersShown,
  formatEventTime,
  formatFuturesName,
  futuresAnswer,
  isMovementWorthShowing,
  suggestionDisplayText,
  suggestionSubtitle,
  suggestionTypeLabel,
  toPercent,
} from "../../lib/searchSuggestionDisplay";

/** A fixed instant. Never `new Date()` — see the header note. */
const NOW = new Date("2026-08-09T18:00:00.000Z");

function suggestion(over: Partial<TypeaheadSuggestion>): TypeaheadSuggestion {
  return { type: "futures", text: "A market", ...over } as TypeaheadSuggestion;
}

describe("formatFuturesName", () => {
  test("strips a league playoff prefix", () => {
    expect(formatFuturesName("NBA Playoffs: Eastern Conference Winner")).toBe(
      "Eastern Conference Winner"
    );
    expect(formatFuturesName("MLB Playoff: World Series Winner")).toBe("World Series Winner");
  });

  test("strips a trailing season year", () => {
    expect(formatFuturesName("Oscars Best Picture 2027")).toBe("Oscars Best Picture");
    expect(formatFuturesName("Premier League Winner 2026-27")).toBe("Premier League Winner");
  });

  test("leaves an ordinary name untouched", () => {
    expect(formatFuturesName("MLB: Next Red Sox Manager")).toBe("MLB: Next Red Sox Manager");
  });
});

describe("formatEventTime", () => {
  test("a game already under way reads as Recently", () => {
    expect(formatEventTime("2026-08-09T17:35:00.000Z", NOW)).toBe("Recently");
  });

  test("inside the hour it counts down in minutes", () => {
    // This is the line the phone was missing: 45 minutes out, not "Sun, Aug 9".
    expect(formatEventTime("2026-08-09T18:45:00.000Z", NOW)).toBe("In 45 min");
  });

  test("inside the day it is a bare clock time, with no weekday", () => {
    const out = formatEventTime("2026-08-10T01:30:00.000Z", NOW);
    expect(out).toMatch(/^\d{1,2}:\d{2}\s?(AM|PM)$/);
  });

  test("beyond a day it leads with the weekday", () => {
    const out = formatEventTime("2026-08-12T01:30:00.000Z", NOW);
    expect(out).toMatch(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat),/);
  });
});

describe("futuresAnswer", () => {
  test("returns the leader and the runner-up when both are priced", () => {
    const answer = futuresAnswer(
      suggestion({
        top_outcomes: [
          { name: "Yes", probability: 0.67, movement: 0.05 },
          { name: "No", probability: 0.33, movement: -0.05 },
        ],
      })
    );
    expect(answer?.leader.name).toBe("Yes");
    expect(answer?.second?.name).toBe("No");
    expect(answer?.movement).toBe(0.05);
  });

  test("skips unpriced outcomes rather than rendering a blank probability", () => {
    const answer = futuresAnswer(
      suggestion({
        top_outcomes: [
          { name: "Unpriced", probability: null, movement: null },
          { name: "Priced", probability: 0.4, movement: null },
        ],
      })
    );
    expect(answer?.leader.name).toBe("Priced");
    expect(answer?.second).toBeNull();
    expect(answer?.movement).toBe(0);
  });

  test("returns null when nothing is priced at all", () => {
    expect(
      futuresAnswer(
        suggestion({ top_outcomes: [{ name: "Unpriced", probability: null, movement: null }] })
      )
    ).toBeNull();
    expect(futuresAnswer(suggestion({ top_outcomes: [] }))).toBeNull();
    expect(futuresAnswer(suggestion({}))).toBeNull();
  });

  test("an incoherent field is passed through, NOT suppressed", () => {
    // Production really returns this for "MLB: Next Red Sox Manager" — three
    // outcomes at 100%. That is gap-list K6, owned by calibration/data, and the
    // desktop dropdown already shows it. Suppressing it here would also hide
    // legitimate independent-binary fields, which do sum over 100% (gotcha #23).
    // Parity means porting the display faithfully, not inventing a new rule.
    const answer = futuresAnswer(
      suggestion({
        top_outcomes: [
          { name: "Manager H", probability: 1.0, movement: null },
          { name: "Manager L", probability: 1.0, movement: null },
        ],
      })
    );
    expect(answer?.leader.probability).toBe(1.0);
    expect(answer?.second?.probability).toBe(1.0);
  });
});

describe("movement threshold", () => {
  test("2 points is the floor, in both directions", () => {
    expect(MOVEMENT_MIN_ABS).toBe(0.02);
    expect(isMovementWorthShowing(0.02)).toBe(true);
    expect(isMovementWorthShowing(-0.02)).toBe(true);
    expect(isMovementWorthShowing(0.019)).toBe(false);
    expect(isMovementWorthShowing(-0.019)).toBe(false);
    expect(isMovementWorthShowing(0)).toBe(false);
  });

  test("toPercent rounds to a whole number", () => {
    expect(toPercent(0.6721)).toBe(67);
    expect(toPercent(0.005)).toBe(1);
    expect(toPercent(1)).toBe(100);
  });
});

describe("countAnswersShown", () => {
  test("counts only futures rows that actually lead with a price", () => {
    expect(
      countAnswersShown([
        suggestion({ type: "futures", top_outcomes: [{ name: "Yes", probability: 0.6, movement: null }] }),
        suggestion({ type: "futures", top_outcomes: [] }),
        suggestion({ type: "futures", top_outcomes: [{ name: "?", probability: null, movement: null }] }),
        suggestion({ type: "event", commence_time: "2026-08-09T18:45:00.000Z" }),
        suggestion({ type: "team" }),
      ])
    ).toBe(1);
  });

  test("an empty dropdown counts zero rather than throwing", () => {
    expect(countAnswersShown([])).toBe(0);
  });
});

describe("suggestionDisplayText", () => {
  test("cleans futures names and leaves every other type alone", () => {
    expect(suggestionDisplayText(suggestion({ type: "futures", text: "NBA Playoffs: Winner 2027" })))
      .toBe("Winner");
    expect(
      suggestionDisplayText(suggestion({ type: "event", text: "Athletics at Boston Red Sox" }))
    ).toBe("Athletics at Boston Red Sox");
  });
});

describe("suggestionTypeLabel", () => {
  test("maps every suggestion type to its chip", () => {
    expect(suggestionTypeLabel(suggestion({ type: "team" }))).toBe("Team");
    expect(suggestionTypeLabel(suggestion({ type: "event" }))).toBe("Game");
    expect(suggestionTypeLabel(suggestion({ type: "event_concept" }))).toBe("Event");
    expect(suggestionTypeLabel(suggestion({ type: "hub" }))).toBe("Hub");
    expect(suggestionTypeLabel(suggestion({ type: "futures" }))).toBe("Futures");
  });
});

describe("suggestionSubtitle", () => {
  test("a live game says so", () => {
    const sub = suggestionSubtitle(
      suggestion({ type: "event", status: "live", commence_time: "2026-08-09T17:35:00.000Z" }),
      NOW
    );
    expect(sub).toEqual({ kind: "event-time", text: "Live now" });
  });

  test("an upcoming game gets the countdown, not a bare date", () => {
    const sub = suggestionSubtitle(
      suggestion({
        type: "event",
        status: "scheduled",
        commence_time: "2026-08-09T18:45:00.000Z",
      }),
      NOW
    );
    expect(sub).toEqual({ kind: "event-time", text: "In 45 min" });
  });

  test("a game with no commence_time renders NO second line", () => {
    expect(suggestionSubtitle(suggestion({ type: "event", status: "scheduled" }), NOW)).toBeNull();
  });

  test("a priced futures row leads with the answer", () => {
    const sub = suggestionSubtitle(
      suggestion({
        type: "futures",
        market_type_label: "Championship",
        top_outcomes: [{ name: "Yes", probability: 0.62, movement: 0.03 }],
      }),
      NOW
    );
    expect(sub?.kind).toBe("futures-answer");
  });

  // BOTH DIRECTIONS (gotcha #43): the answer must appear when it exists AND the
  // old label must survive when it does not. A parity fix that swallowed the
  // fallback would be a regression dressed as an improvement.
  test("an unpriced futures row still falls back to its label", () => {
    const sub = suggestionSubtitle(
      suggestion({ type: "futures", market_type_label: "Championship", top_outcomes: [] }),
      NOW
    );
    expect(sub).toEqual({ kind: "futures-label", text: "Championship" });
  });

  test("an unpriced, unlabelled futures row renders NO second line", () => {
    expect(suggestionSubtitle(suggestion({ type: "futures", top_outcomes: [] }), NOW)).toBeNull();
  });

  test("concepts and hubs keep their subtitles", () => {
    expect(
      suggestionSubtitle(suggestion({ type: "event_concept", sport_key: "tennis" }), NOW)
    ).toEqual({ kind: "concept", text: "Event · tennis" });
    expect(suggestionSubtitle(suggestion({ type: "event_concept" }), NOW)).toEqual({
      kind: "concept",
      text: "Event",
    });
    expect(suggestionSubtitle(suggestion({ type: "hub" }), NOW)).toEqual({
      kind: "hub",
      text: "Browse all markets",
    });
  });

  test("a team row has no subtitle", () => {
    expect(suggestionSubtitle(suggestion({ type: "team" }), NOW)).toBeNull();
  });
});

describe("the real production payload", () => {
  // Captured verbatim from GET /api/events/typeahead?q=red+sox on production,
  // 2026-08-09 ~11:15 PT. This is the payload the phone was throwing away.
  const LIVE: TypeaheadSuggestion[] = [
    { type: "team", text: "Boston Red Sox", sport_key: "baseball_mlb" },
    {
      type: "event",
      text: "Athletics at Boston Red Sox",
      status: "live",
      commence_time: "2026-08-09T17:35:00+00:00",
    },
    {
      type: "event",
      text: "Boston Red Sox at Toronto Blue Jays",
      status: "scheduled",
      commence_time: "2026-08-10T23:07:00+00:00",
    },
    { type: "event_concept", text: "The Emmys" },
    {
      type: "futures",
      text: "MLB: Next Red Sox Manager",
      top_outcomes: [
        { name: "Manager H", probability: 1.0, movement: null },
        { name: "Manager L", probability: 1.0, movement: null },
        { name: "Manager M", probability: 1.0, movement: null },
      ],
    },
    {
      type: "futures",
      text: "Boston Red Sox vs. Los Angeles Dodgers",
      top_outcomes: [
        { name: "Boston Red Sox vs. Los Angeles Dodgers", probability: 0.5, movement: null },
        { name: "NRFI", probability: 0.5, movement: 0.02 },
      ],
    },
  ] as TypeaheadSuggestion[];

  test("every futures row in the live payload now carries an answer", () => {
    const futures = LIVE.filter((s) => s.type === "futures");
    expect(futures.length).toBe(2);
    for (const f of futures) {
      expect(suggestionSubtitle(f, NOW)?.kind).toBe("futures-answer");
    }
  });

  test("the live game reads 'Live now' and the next one is dated", () => {
    expect(suggestionSubtitle(LIVE[1], NOW)).toEqual({ kind: "event-time", text: "Live now" });
    const next = suggestionSubtitle(LIVE[2], NOW);
    expect(next?.kind).toBe("event-time");
    expect(next && "text" in next && next.text).toMatch(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat),/);
  });

  test("the NRFI row's +2pt move clears the arrow threshold", () => {
    const answer = futuresAnswer(LIVE[5]);
    expect(answer?.second?.name).toBe("NRFI");
    expect(isMovementWorthShowing(answer?.second?.movement ?? 0)).toBe(true);
  });
});
