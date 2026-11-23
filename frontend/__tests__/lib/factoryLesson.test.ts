import { explainedCheck, hasFailedCheck, lessonForFloor } from "@/app/factory/lesson";
import type { Change, FactoryData } from "@/app/factory/types";

const at = "2026-10-01T06:30:00.000Z";
const reading: FactoryData = {
  schema_version: 1, generated_at: at, observed_since: at,
  changes: [], jams: [], coverage: [],
  signals: { tests: "passing", testflight: "success" },
};
const change: Change = {
  number: 13474, title: "Verify a change", line: "Server", builder: "S",
  station: "Test", unsure: false, reasons: [], side_track: false,
  revision_at: "2026-10-01T05:45:00.000Z", last_activity: at,
  merged_at: null, live_at: null, timing: null,
};

it("uses one of twenty fixed words for each Pacific day", () => {
  const before = lessonForFloor(reading, "2026-10-01T06:59:59.000Z");
  expect(before.word).toBe(lessonForFloor(reading, "2026-09-30T22:00:00.000Z").word);
  expect(before.word).not.toBe(lessonForFloor(reading, "2026-10-01T07:00:00.000Z").word);
  const daily = Array.from({ length: 20 }, (_, i) =>
    lessonForFloor(reading, new Date(Date.UTC(2026, 9, i + 1, 19)).toISOString()).word);
  expect(new Set(daily).size).toBe(20);
});

it("counts each delivered change once on the snapshot's Pacific day", () => {
  const shipped: Change = { ...change, station: "Live", live_at: at, merged_at: at };
  const old: Change = { ...shipped, number: 25, live_at: "2026-09-30T06:59:00.000Z" };
  const dates = Array.from({ length: 20 }, (_, i) => new Date(Date.UTC(2026, 9, i + 1, 19)).toISOString());
  const day = dates.find(date => lessonForFloor(reading, date).word === "Release")!;
  const lesson = lessonForFloor({ ...reading, changes: [shipped, { ...shipped, line: "Website" }, old] }, day);
  expect(lesson.count).toBe("1 change went live on Sep 30");
});

it("explains a failure supported by a current check or an observed check on this version", () => {
  expect(explainedCheck({ ...reading, changes: [{ ...change, checks_failed: true }] }))
    .toBe("An automatic check flagged #13474 before it could go live.");
  const observed: FactoryData = { ...reading, changes: [change], events: [{
    id: "check", kind: "check", number: 13474, builder: "S", line: "Server", station: "Test",
    at: "2026-10-01T06:00:00.000Z", observed_at: at, done: 4, total: 5, outcome: "failed",
  }] };
  expect(hasFailedCheck(observed, change)).toBe(true);
  expect(hasFailedCheck(observed, { ...change, revision_at: at })).toBe(false);
  expect(hasFailedCheck(observed, { ...change, station: "Live", merged_at: at })).toBe(false);
  expect(explainedCheck({ ...observed, events: [{ ...observed.events![0], outcome: "passed" }] }))
    .toBeUndefined();
});
