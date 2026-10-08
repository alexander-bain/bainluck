/**
 * #10751 — `admitChartFrames` / `finishedChartFrames`: the frames a finished
 * page may keep are exactly the ones it drew while eligible, and only under
 * proof. Every control below returns `[]` — the behaviour before this change.
 * The mounted lifecycle (hook disable, pending history, navigation) is
 * `__tests__/hooks/finishedChartKeepsAdmittedMovement10751.test.tsx`.
 */
import {
  admitChartFrames,
  finishedChartFrames,
  mergeLiveChartHistory,
  rememberLiveChartFrame,
  type AdmittedChartFrames,
  type FinishedHero,
  type FinishedServed,
  type LiveChartFrame,
} from "@/lib/liveChartHistory";
import type { LiveStreamFrame } from "@/lib/liveStreamController";

const ID = 15329101;
const T0 = Date.UTC(2026, 9, 8, 19, 0, 0);
const T = (s: number) => new Date(T0 + s * 1000).toISOString();

const frame = (s: number, p: number, rev: number | null): LiveStreamFrame => ({
  event_id: ID, p, source: "kalshi", source_value: p, updated_at: T(s), status: "live",
  ...(rev === null ? {} : { rev: { [ID]: rev } }),
});
const bank = (frames: LiveStreamFrame[]) =>
  frames.reduce<LiveChartFrame[]>((points, f) => rememberLiveChartFrame(points, f, ID), []);
const MOVEMENT = bank([frame(65, 0.42, 222), frame(125, 0.55, 223), frame(185, 0.43, 224)]);

/** The held live hero after the last frame applied (revision travels with it). */
const liveHero = (rev: Record<string, number> | null = { [ID]: 224 }, observedAt = T(185)) => ({
  status: "live", hero_probability: 0.43, hero_probability_source: "blend",
  hero_probability_observed_at: observedAt, blend_fold_revision: rev,
});
const admitted = (overrides: Partial<AdmittedChartFrames> = {}): AdmittedChartFrames =>
  ({ ...admitChartFrames(ID, MOVEMENT, liveHero()), ...overrides });
const finished = (overrides: Partial<FinishedHero> = {}): FinishedHero => ({
  id: ID, status: "completed", completed_at: T(300), blend_fold_revision: { [ID]: 225 }, ...overrides,
});
const served = (overrides: Partial<FinishedServed> = {}): FinishedServed => ({
  event_id: ID, completed_at: null,
  aggregate_line: [{ timestamp: T(-600), home_probability: 0.38 }, { timestamp: T(0), home_probability: 0.40 }],
  ...overrides,
});
const clocks = (points: LiveChartFrame[]) => points.map((point) => point.timestamp);

describe("#10751 admitChartFrames records what the live chart drew, not the raw bank", () => {
  it("keeps the frames quoteChartFrames admits, with the held vector they were admitted against", () => {
    const record = admitChartFrames(ID, MOVEMENT, liveHero());
    expect(clocks(record.points)).toEqual([T(65), T(125), T(185)]);
    expect(record).toMatchObject({ eventId: ID, foldRevision: { [ID]: 224 } });
  });
  it("a frame the headline refused (older commit, newer clock) is not admitted, so it can never be kept", () => {
    const refused = bank([frame(65, 0.42, 222), frame(200, 0.9, 223)]);
    expect(clocks(admitChartFrames(ID, refused, liveHero()).points)).toEqual([T(65)]);
  });
  it("a folded hero, a nonblend hero or no hero admits nothing", () => {
    expect(admitChartFrames(ID, MOVEMENT, liveHero({ [ID]: 224, 777: 3 })).points).toEqual([]);
    expect(admitChartFrames(ID, MOVEMENT, { ...liveHero(), hero_probability_source: "opening" }).points).toEqual([]);
    expect(admitChartFrames(ID, MOVEMENT, null)).toEqual({ eventId: ID, points: [], foldRevision: null });
  });
});

describe("#10751 finishedChartFrames keeps admitted pre-finish movement only under proof", () => {
  it("returns the admitted frames, each with its own value, clock and revision", () => {
    const kept = finishedChartFrames(admitted(), ID, finished(), served());
    expect(kept).toEqual(admitted().points);
    expect(kept.map((point) => [point.home_probability, point.rev])).toEqual([
      [0.42, { [ID]: 222 }], [0.55, { [ID]: 223 }], [0.43, { [ID]: 224 }],
    ]);
  });
  it("a terminal vector equal to the admission still proves the frames", () => {
    expect(finishedChartFrames(admitted(), ID, finished({ blend_fold_revision: { [ID]: 224 } }), served()))
      .toHaveLength(3);
  });
  it("`closed` is finished too", () => {
    expect(finishedChartFrames(admitted(), ID, finished({ status: "closed" }), served())).toHaveLength(3);
  });
  it("merged onto the old served body, the frames extend it; REST still wins an exact-time tie", () => {
    const body = served({ aggregate_line: [...served().aggregate_line!, { timestamp: T(125), home_probability: 0.54 }] });
    const merged = mergeLiveChartHistory(body, finishedChartFrames(admitted(), ID, finished(), body))!;
    expect(merged.aggregate_line).toEqual([
      { timestamp: T(-600), home_probability: 0.38 }, { timestamp: T(0), home_probability: 0.40 },
      { timestamp: T(65), home_probability: 0.42 }, { timestamp: T(125), home_probability: 0.54 },
      { timestamp: T(185), home_probability: 0.43 },
    ]);
  });
  it("valid zero and one probabilities are kept as observations", () => {
    const edges = admitChartFrames(ID, bank([frame(65, 0, 223), frame(125, 1, 224)]), liveHero());
    expect(finishedChartFrames(edges, ID, finished(), served()).map((point) => point.home_probability)).toEqual([0, 1]);
  });
  it("a tighter served completion bound wins; a frame after it is not pre-finish movement", () => {
    expect(clocks(finishedChartFrames(admitted(), ID, finished(), served({ completed_at: T(150) }))))
      .toEqual([T(65), T(125)]);
    expect(clocks(finishedChartFrames(admitted(), ID, finished({ completed_at: T(125) }), served())))
      .toEqual([T(65), T(125)]);
  });
  it("does not mutate a frozen admission, hero or body", () => {
    const record = Object.freeze({ ...admitted(), points: Object.freeze([...admitted().points]) }) as AdmittedChartFrames;
    expect(finishedChartFrames(record, ID, Object.freeze(finished()), Object.freeze(served()))).toHaveLength(3);
  });

  describe("CONTROLS — every one returns [] (the old behaviour)", () => {
    const none = (a: AdmittedChartFrames | null, h: FinishedHero | null, s: FinishedServed | null, id = ID) =>
      expect(finishedChartFrames(a, id, h, s)).toEqual([]);

    it("no admission, an empty one, or one for another event", () => {
      none(null, finished(), served());
      none(admitted({ points: [] }), finished(), served());
      none(admitted({ eventId: ID + 1 }), finished(), served());
      none(admitted(), finished(), served(), ID + 1);
    });
    it("a detail that is not explicitly finished, or is another event's", () => {
      for (const status of ["live", "scheduled", "suspended", "postponed", "cancelled", null]) {
        none(admitted(), finished({ status }), served());
      }
      none(admitted(), finished({ id: ID + 1 }), served());
      none(admitted(), null, served());
    });
    it("a served body for another event, without an id, or with no served blend", () => {
      none(admitted(), finished(), served({ event_id: ID + 1 }));
      none(admitted(), finished(), served({ event_id: undefined }));
      none(admitted(), finished(), served({ aggregate_line: [] }));
      none(admitted(), finished(), served({ aggregate_line: null }));
      none(admitted(), finished(), null);
    });
    it("an unknown or contradictory completion bound", () => {
      none(admitted(), finished({ completed_at: null }), served());
      none(admitted(), finished({ completed_at: undefined }), served());
      none(admitted(), finished({ completed_at: "not a time" }), served());
      none(admitted(), finished(), served({ completed_at: "not a time" }));
    });
    it("a missing, malformed, folded or changed-membership terminal vector", () => {
      for (const blend_fold_revision of [null, undefined, {}, { [ID]: -1 }, { [ID]: 1.5 }, [225], "225",
        { [ID]: 225, 777: 1 }, { 777: 225 }]) {
        none(admitted(), finished({ blend_fold_revision }), served());
      }
    });
    it("a terminal vector BEHIND the admission", () => {
      none(admitted(), finished({ blend_fold_revision: { [ID]: 223 } }), served());
    });
    it("an admission with no vector (pre-contract) makes no ordering claim to keep", () => {
      const unversioned = admitChartFrames(ID, bank([frame(65, 0.42, null)]), liveHero(null));
      expect(unversioned.points).toHaveLength(1); // the live path still draws it
      none(unversioned, finished(), served());
    });
  });

  it("per frame: newer than the terminal vector, unversioned, beyond the bound, or invalid — dropped alone", () => {
    const mixed = admitted({
      points: [
        ...MOVEMENT,
        { timestamp: T(190), home_probability: 0.5, rev: { [ID]: 226 } },   // newer than terminal 225
        { timestamp: T(195), home_probability: 0.5 },                       // no vector
        { timestamp: T(196), home_probability: 0.5, rev: { 777: 224 } },    // another row
        { timestamp: T(400), home_probability: 0.5, rev: { [ID]: 224 } },   // after completion
        { timestamp: "broken", home_probability: 0.5, rev: { [ID]: 224 } },
        { timestamp: T(197), home_probability: Number.NaN, rev: { [ID]: 224 } },
        { timestamp: T(198), home_probability: 1.2, rev: { [ID]: 224 } },
        { timestamp: T(199), home_probability: -0.1, rev: { [ID]: 224 } },
      ],
    });
    expect(clocks(finishedChartFrames(mixed, ID, finished(), served()))).toEqual([T(65), T(125), T(185)]);
  });
});
