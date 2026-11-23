import { readGitHubActivity } from "@/app/factory/githubActivity";
import { floorReadingState, floorVerdict } from "@/app/factory/verdict";
import type { FactoryData } from "@/app/factory/types";

const published = "2026-11-22T08:02:58.883Z";
const visit = "2026-11-22T13:00:00Z";
const masterAt = "2026-11-22T06:55:16Z";
const ciAt = "2026-11-22T07:39:59Z";
const quietActivity = {
  checkedAt: visit,
  masterAt,
  ciAt,
  collector: { at: "2026-11-22T08:03:14Z", failed: false },
};
const floor: FactoryData = {
  schema_version: 1,
  generated_at: published,
  observed_since: published,
  changes: [],
  stops: [],
  jams: [],
  signals: { tests: "passing", testflight: "success" },
  coverage: [],
};

it("keeps the overnight floor quiet after the 12:02 AM PT run", () => {
  expect(floorReadingState(floor, false, visit, quietActivity)).toBe("quiet");
  expect(floorVerdict(floor, false, visit, quietActivity).text).toBe("The floor is quiet.");
});

it("warns about a collector failure after the saved floor was published", () => {
  const failed = { ...quietActivity, collector: { at: "2026-11-22T08:04:00Z", failed: true } };
  expect(floorVerdict(floor, false, visit, failed).text).toBe("Not updating.");
  expect(floorVerdict({ ...floor, generated_at: "2026-11-22T08:05:00Z" }, false, visit, failed).text)
    .toBe("The floor is quiet.");
});

it.each(["masterAt", "ciAt"] as const)("only warns once %s is more than 15 minutes past publication", key => {
  const exactly = new Date(Date.parse(published) + 15 * 60_000);
  expect(floorReadingState(floor, false, visit, { ...quietActivity, [key]: exactly.toISOString() }))
    .toBe("last-known");
  const later = new Date(exactly.getTime() + 1).toISOString();
  expect(floorReadingState(floor, false, visit, { ...quietActivity, [key]: later })).toBe("failed");
});

it("keeps the last published floor when GitHub evidence is missing or too old", () => {
  expect(floorReadingState(floor, false, visit, { ...quietActivity, masterAt: undefined })).toBe("last-known");
  expect(floorReadingState(floor, false, visit, { ...quietActivity, checkedAt: ciAt })).toBe("last-known");
  expect(floorReadingState(floor, true, visit, quietActivity)).toBe("last-known");
});

it("uses the machine wait after 15 minutes and keeps a newer collector failure visible", () => {
  const overdue = { ...quietActivity, masterAt: "2026-11-22T12:30:00Z" };
  const atThreshold = { ...overdue, collectorQueuedAt: "2026-11-22T12:45:00Z" };
  expect(floorReadingState(floor, false, visit, atThreshold)).toBe("failed");
  const waiting = { ...overdue, collectorQueuedAt: "2026-11-22T12:44:59Z" };
  expect(floorVerdict(floor, false, visit, waiting).text).toBe("The next reading is waiting for a machine.");
  const failed = { ...waiting, collector: { at: "2026-11-22T12:52:00Z", failed: true } };
  expect(floorVerdict(floor, false, visit, failed).text).toBe("Not updating.");
});

it("reads the newest completed master CI and collector outcomes without credentials", async () => {
  const response = (json: unknown) => ({ ok: true, json: async () => json });
  const run = (updated_at: string, conclusion: string, status = "completed") => ({ updated_at, conclusion, status });
  const read = jest.fn()
    .mockResolvedValueOnce(response({ commit: { committer: { date: masterAt } } }))
    .mockResolvedValueOnce(response({ workflow_runs: [run(masterAt, "success"), run(ciAt, "success")] }))
    .mockResolvedValueOnce(response({ workflow_runs: [
      run("2026-11-22T08:12:00Z", "cancelled"),
      run("2026-11-22T08:09:00Z", "failure", "in_progress"),
      run("2026-11-22T08:01:00Z", "failure"),
      run("2026-11-22T08:03:14Z", "success"),
    ] }))
    .mockResolvedValueOnce(response({ workflow_runs: [
      { status: "in_progress", run_started_at: "2026-11-22T11:15:00Z" },
      { status: "in_progress", run_started_at: "2026-11-22T10:00:00Z" },
    ] }));
  expect(await readGitHubActivity(read)).toMatchObject({
    masterAt, ciAt, collector: quietActivity.collector, oldestRunningCI: "2026-11-22T10:00:00Z",
  });
  expect(read).toHaveBeenCalledTimes(4);
  expect(read.mock.calls[3][0]).toContain("status=in_progress");
  expect(read.mock.calls[1][0]).toContain("branch=master");
  expect(read.mock.calls[1][0]).toContain("status=completed");
  expect(read.mock.calls[1][0]).toContain("event=push");
  for (const [, options] of read.mock.calls) {
    expect(options.headers.Authorization).toBeUndefined();
    expect(options.signal).toBeInstanceOf(AbortSignal);
  }
});

it("finds a waiting run behind a full page of newer completed runs", async () => {
  jest.useFakeTimers({ now: new Date(visit) });
  try {
    const response = (json: unknown) => ({ ok: true, json: async () => json });
    const read = jest.fn()
      .mockResolvedValueOnce(response({ commit: { committer: { date: masterAt } } }))
      .mockResolvedValueOnce(response({ workflow_runs: [] }))
      .mockResolvedValueOnce(response({ workflow_runs: Array.from({ length: 20 }, (_, id) => ({
        id, status: "completed", conclusion: "cancelled", created_at: "2026-11-22T12:55:00Z",
      })) }))
      .mockResolvedValueOnce(response({ workflow_runs: [] }))
      .mockResolvedValueOnce(response({ workflow_runs: [
        { id: 42, status: "queued", created_at: "2026-11-22T12:30:00Z" },
      ] }))
      .mockResolvedValueOnce(response({ jobs: [{
        status: "queued", runner_id: null, created_at: "2026-11-22T12:34:00Z", labels: ["ubuntu-latest"],
      }] }));
    expect((await readGitHubActivity(read)).collectorQueuedAt).toBe("2026-11-22T12:34:00Z");
    expect(read.mock.calls[4][0]).toContain("status=queued");
    expect(read.mock.calls[5][0]).toContain("/actions/runs/42/jobs");
  } finally {
    jest.useRealTimers();
  }
});

it.each([
  ["queued", { status: "queued", runner_id: null }, "2026-11-22T12:30:00Z"],
  ["in_progress", { status: "queued", runner_id: null }, "2026-11-22T12:30:00Z"],
  ["in_progress", { status: "in_progress", runner_id: 25 }, undefined],
  ["pending", { status: "queued", runner_id: null }, undefined],
] as const)("uses job evidence for a %s workflow", async (status, job, expected) => {
  jest.useFakeTimers({ now: new Date(visit) });
  try {
    const response = (json: unknown) => ({ ok: true, json: async () => json });
    const read = jest.fn()
      .mockResolvedValueOnce(response({ commit: { committer: { date: masterAt } } }))
      .mockResolvedValueOnce(response({ workflow_runs: [] }))
      .mockResolvedValueOnce(response({ workflow_runs: [
        { id: 42, status, conclusion: null, created_at: "2026-11-22T12:27:00Z" },
        { id: 41, status: "completed", conclusion: "success", updated_at: "2026-11-22T08:03:14Z" },
      ] }))
      .mockResolvedValueOnce(response({ workflow_runs: [] }))
      .mockResolvedValueOnce(response({ jobs: [{
        ...job, labels: ["ubuntu-latest"], created_at: "2026-11-22T12:30:00Z",
      }] }));
    expect((await readGitHubActivity(read)).collectorQueuedAt).toBe(expected);
    if (status === "pending") {
      expect(read).toHaveBeenCalledTimes(4);
    } else {
      expect(read).toHaveBeenCalledTimes(5);
      expect(read.mock.calls[4][0]).toContain("/actions/runs/42/jobs");
    }
  } finally {
    jest.useRealTimers();
  }
});

it("keeps Sunday's 10-minute-old publication current after one collector failure", () => {
  const published = "2026-11-23T06:57:01.240310Z";
  const visit = "2026-11-23T07:07:04Z";
  const recorded = { ...floor, generated_at: published };
  const activity = {
    checkedAt: visit,
    collector: { at: "2026-11-23T07:05:11Z", failed: true },
  };
  expect(floorReadingState(recorded, false, visit, activity)).toBe("current");
  expect(floorReadingState(recorded, true, visit, activity)).toBe("last-known");
  expect(floorReadingState(recorded, false, "2026-11-23T07:13:02Z", activity)).toBe("failed");
});
