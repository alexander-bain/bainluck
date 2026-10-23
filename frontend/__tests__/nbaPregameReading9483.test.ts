/**
 * #9483 NBA — a settled card's pregame chance comes from the producer's
 * `pregame_reading` (Authority PR #11125, contract
 * `artifacts/authority-9483-pregame-reading/CONTRACT.md`) and from nothing else.
 *
 * `pregameReadingContract9483.json` is the producer's own EXAMPLE-OPTIONS.json,
 * copied byte for byte (sha256 4c882f30…246d1, built at 87d1b2f4d8). It is
 * SYNTHETIC: its ids echo /events/15320337 Over 206.5 for shape only, and it is
 * not evidence that any production market holds a pin. The final fixture is the
 * real body from before the field existed, so it doubles as the old server.
 * Fixed clocks only (gotcha #44).
 */

import contract from "./fixtures/pregameReadingContract9483.json";
import finalBody from "./fixtures/nbaFinalMatrix15320337.json";
import pregameBody from "./fixtures/nbaPregameMatrix15327183.json";
import {
  decodeQuestionMatrix,
  defaultLadderIndex,
  ladderCaption,
  marginLadderCard,
  totalLadderCard,
  type LadderInputs,
  type MatrixOption,
} from "@/lib/nbaEventCards";

const OVER_2065 = "o:240505185";
const OUTCOME = 240505185;
const READING = { state: "available", reason: null, probability: 0.61, observed_at: "2026-10-04T22:50:00+00:00", basis: "pregame_pin", outcome_id: OUTCOME };

type RawOption = Record<string, unknown>;

/** One option through the real decoder, in a one-question matrix. */
function decodeOne(option: RawOption): MatrixOption {
  return decodeQuestionMatrix({ contract: "10238.v1", questions: [{ question_key: "q", kind: "count_threshold", options: [option] }] })[0].options[0];
}

/** The real final body with `edit` applied to the options whose key matches. */
function finalWith(edit: (o: RawOption) => void, keys: string[] = [OVER_2065]): unknown {
  const m = JSON.parse(JSON.stringify(finalBody.game_question_matrix));
  for (const q of m.questions) for (const o of q.options) if (keys.includes(o.option_key)) edit(o);
  return m;
}

function finalInputs(matrix: unknown, over: Partial<LadderInputs> = {}): LadderInputs {
  return {
    questions: decodeQuestionMatrix(matrix),
    status: "completed",
    commenceTime: "2026-10-04T23:00:00Z",
    homeScore: finalBody.home_score,
    awayScore: finalBody.away_score,
    pregameProjection: null,
    homeShort: "Clippers",
    awayShort: "Warriors",
    nowMs: Date.parse("2026-10-05T04:00:00Z"),
    ...over,
  };
}

const settledOption = (): RawOption => JSON.parse(JSON.stringify(contract.options.settled_lost_qualified_pin));

describe("#9483 pregame_reading — the producer's own example options", () => {
  it("the qualified pin decodes to its probability and write clock", () => {
    const o = decodeOne(settledOption());
    expect(o.reading).toBe(0.825);
    expect(o.readingObservedAt).toBe("2026-10-02T18:00:00+00:00");
    // The settled option's comparison still refuses, unchanged.
    expect(o.baseline).toBeNull();
    expect(o.comparisonReason).toBe("not_quoted");
    expect(o.result).toBe(false);
  });

  it("no pin and a pin written after the start stay unavailable — never the terminal 0.0 in source_evidence", () => {
    for (const key of ["settled_lost_no_pin", "settled_lost_pin_after_start"] as const) {
      const raw = contract.options[key];
      expect(raw.source_evidence[0].raw_probability).toBe(0);
      const o = decodeOne(JSON.parse(JSON.stringify(raw)));
      expect(o.reading).toBeNull();
      expect(o.readingObservedAt).toBeNull();
    }
  });
});

describe("#9483 pregame_reading — anything less than whole is unavailable", () => {
  const cases: [string, (o: RawOption) => void][] = [
    ["field absent (older server)", (o) => delete o.pregame_reading],
    ["field null", (o) => (o.pregame_reading = null)],
    ["state unavailable with numbers left in", (o) => ((o.pregame_reading as RawOption).state = "unavailable")],
    ["unknown state", (o) => ((o.pregame_reading as RawOption).state = "pending")],
    ["a reason on an available reading", (o) => ((o.pregame_reading as RawOption).reason = "no_pregame_pin")],
    ["unknown basis", (o) => ((o.pregame_reading as RawOption).basis = "opening_line")],
    ["basis absent", (o) => delete (o.pregame_reading as RawOption).basis],
    ["probability 0 (a settlement value)", (o) => ((o.pregame_reading as RawOption).probability = 0)],
    ["probability 1 (a settlement value)", (o) => ((o.pregame_reading as RawOption).probability = 1)],
    ["probability above 1", (o) => ((o.pregame_reading as RawOption).probability = 1.2)],
    ["probability as a string", (o) => ((o.pregame_reading as RawOption).probability = "0.825")],
    ["probability absent", (o) => delete (o.pregame_reading as RawOption).probability],
    ["clock absent", (o) => delete (o.pregame_reading as RawOption).observed_at],
    ["clock unreadable", (o) => ((o.pregame_reading as RawOption).observed_at = "yesterday-ish")],
    ["outcome id absent", (o) => delete (o.pregame_reading as RawOption).outcome_id],
    ["outcome id as a string", (o) => ((o.pregame_reading as RawOption).outcome_id = String(OUTCOME))],
    ["outcome id is another contributor's", (o) => ((o.pregame_reading as RawOption).outcome_id = OUTCOME + 1)],
    ["two contributors", (o) => (o.contributor_outcome_ids = [OUTCOME, OUTCOME + 1])],
    ["contributors absent", (o) => delete o.contributor_outcome_ids],
    ["option not admitted (unpriced)", (o) => ((o.published as RawOption).value_state = "unpriced")],
    ["option value state absent", (o) => delete (o.published as RawOption).value_state],
  ];

  it.each(cases)("%s → no reading", (_name, edit) => {
    const raw = settledOption();
    edit(raw);
    expect(decodeOne(raw).reading).toBeNull();
    expect(decodeOne(raw).readingObservedAt).toBeNull();
  });

  it("CONTROL: the untouched example is admitted, so every refusal above is its own edit", () => {
    expect(decodeOne(settledOption()).reading).toBe(0.825);
    const quoted = settledOption();
    (quoted.published as RawOption).value_state = "quoted";
    expect(decodeOne(quoted).reading).toBe(0.825);
  });
});

describe("#9483 pregame_reading — the settled ladder (15320337 body + a reading on Over 206.5)", () => {
  const card = totalLadderCard(finalInputs(finalWith((o) => (o.pregame_reading = { ...READING }))))!;
  const line = card.points.find((p) => p.optionKey === OVER_2065)!;

  it("draws the reading on its own line only, beside the unchanged verdict and actual", () => {
    expect(line.chance).toBe(0.61);
    expect(line.result).toBe(false);
    expect(line.now).toBeNull();
    expect(card.actual).toBe(205);
    expect(card.points.filter((p) => p.chance !== null).map((p) => p.optionKey)).toEqual([OVER_2065]);
    expect(card.points.find((p) => p.x === 204.5)!.result).toBe(true);
    expect(ladderCaption(card)).toBe("Chance before tip-off of finishing above each line");
  });

  it("Details carry the reading and its clock as the pregame baseline; the last quote stays absent", () => {
    expect(line.detail).toMatchObject({ baseline: 0.61, baselineObservedAt: READING.observed_at, quoted: null, result: false });
    const other = card.points.find((p) => p.x === 204.5)!;
    expect(other.detail.baseline).toBeNull();
  });

  it("opens on the drawn line", () => {
    expect(card.points[defaultLadderIndex(card)!].optionKey).toBe(OVER_2065);
  });

  it("the reading has no expiry clock: a final's pregame chance is history, not a current price", () => {
    expect(line.observedAt).toBeNull();
  });

  it("a reading on an option whose side is not the line's own is refused with the line, never complemented", () => {
    const flipped = totalLadderCard(
      finalInputs(
        finalWith((o) => {
          o.pregame_reading = { ...READING };
          o.side = "under";
        }),
      ),
    )!;
    expect(flipped.points.find((p) => p.x === 206.5)).toBeUndefined();
    expect(flipped.points.every((p) => p.chance === null)).toBe(true);
  });

  it("the margin ladder reads a reading on a team's own line the same way", () => {
    const margin = marginLadderCard(
      finalInputs(finalWith((o) => (o.pregame_reading = { ...READING, outcome_id: 240505114 }), ["o:240505114"])),
    )!;
    const gsw = margin.points.find((p) => p.optionKey === "o:240505114")!;
    expect(gsw).toMatchObject({ chance: 0.61, result: false, side: "away", x: -1.5 });
    expect(margin.points.filter((p) => p.chance !== null)).toHaveLength(1);
  });
});

describe("#9483 pregame_reading — a final whose option is still quoted (the first hours, before venues settle)", () => {
  // Lane1's review (19:11Z) found no finished-but-quoted specimen in the band; this is the
  // normal shape for hours after a final. A fresh 99% must never become the pregame chance
  // or a "now" on a settled card.
  const stillQuoted = (o: RawOption) => {
    const p = o.published as RawOption;
    p.value_state = "quoted";
    p.basis = "quoted";
    p.value = 0.99;
    p.observed_at = "2026-10-05T03:59:00+00:00";
  };

  it("CONTROL: the edited option decodes as a fresh 99% quote", () => {
    const option = decodeQuestionMatrix(finalWith(stillQuoted)).flatMap((q) => q.options).find((x) => x.optionKey === OVER_2065)!;
    expect(option.quoted).toBe(0.99);
    expect(totalLadderCard(finalInputs(finalWith(stillQuoted)))!.phase).toBe("after");
  });

  it("without a reading: no chance and no now — the 99% is not drawn", () => {
    const card = totalLadderCard(finalInputs(finalWith(stillQuoted)))!;
    const line = card.points.find((p) => p.optionKey === OVER_2065)!;
    expect(line.chance).toBeNull();
    expect(line.now).toBeNull();
    expect(line.observedAt).toBeNull();
    expect(card.points.every((p) => p.chance === null && p.now === null)).toBe(true);
    expect(ladderCaption(card)).toBe("Pregame chance unavailable for these lines");
  });

  it("with a reading: the reading is the chance, still no now", () => {
    const card = totalLadderCard(
      finalInputs(
        finalWith((o) => {
          stillQuoted(o);
          o.pregame_reading = { ...READING };
        }),
      ),
    )!;
    const line = card.points.find((p) => p.optionKey === OVER_2065)!;
    expect(line.chance).toBe(0.61);
    expect(line.now).toBeNull();
    expect(line.detail.baseline).toBe(0.61);
  });
});

describe("#9483 pregame_reading — before and during play are unchanged", () => {
  const scheduled = (matrix: unknown, over: Partial<LadderInputs> = {}): LadderInputs => ({
    questions: decodeQuestionMatrix(matrix),
    status: "scheduled",
    commenceTime: "2026-10-15T23:30:00Z",
    homeScore: null,
    awayScore: null,
    pregameProjection: null,
    homeShort: "Knicks",
    awayShort: "Raptors",
    nowMs: Date.parse("2026-10-15T18:40:00Z"),
    ...over,
  });
  /** Every option carries a different, valid reading so any leak is visible. */
  const withReadings = (): unknown => {
    const m = JSON.parse(JSON.stringify(pregameBody.game_question_matrix));
    for (const q of m.questions)
      for (const o of q.options)
        if (Array.isArray(o.contributor_outcome_ids) && o.contributor_outcome_ids.length === 1)
          o.pregame_reading = { ...READING, probability: 0.123, outcome_id: o.contributor_outcome_ids[0] };
    return m;
  };

  it("before tip-off the dots stay the recent quotes", () => {
    const plain = totalLadderCard(scheduled(pregameBody.game_question_matrix))!;
    const read = totalLadderCard(scheduled(withReadings()))!;
    expect(read.points.map((p) => p.chance)).toEqual(plain.points.map((p) => p.chance));
    expect(read.points.some((p) => p.chance === 0.123)).toBe(false);
  });

  it("during play the dots stay the comparison pin — with none served, empty, even beside a reading", () => {
    const live = { status: "live", homeScore: 20, awayScore: 18, nowMs: Date.parse("2026-10-15T23:40:00Z") };
    const read = totalLadderCard(scheduled(withReadings(), live))!;
    expect(read.phase).toBe("during");
    expect(read.points.every((p) => p.chance === null)).toBe(true);
    expect(read.points.every((p) => p.detail.baseline === null)).toBe(true);
  });

  it("during play an admitted comparison pin is still drawn (the legacy quoted baseline)", () => {
    const m = JSON.parse(JSON.stringify(withReadings())) as { questions: { options: RawOption[] }[] };
    let key: string | null = null;
    for (const q of m.questions)
      for (const o of q.options)
        if (key === null && o.side === "over" && (o.published as RawOption).value_state === "quoted") {
          key = o.option_key as string;
          o.comparison = { state: "comparable", reason: null, baseline: { probability: 0.44, observed_at: "2026-10-15T23:20:00Z", basis: "pregame_pin" } };
        }
    const card = totalLadderCard(scheduled(m, { status: "live", homeScore: 20, awayScore: 18, nowMs: Date.parse("2026-10-15T23:40:00Z") }))!;
    const p = card.points.find((x) => x.optionKey === key);
    expect(p?.chance).toBe(0.44);
    expect(p?.detail.baseline).toBe(0.44);
  });
});
