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
    ] }));
  expect(await readGitHubActivity(read)).toMatchObject({
    masterAt, ciAt, collector: quietActivity.collector,
  });
  expect(read).toHaveBeenCalledTimes(3);
  expect(read.mock.calls[1][0]).toContain("branch=master&status=completed");
  expect(read.mock.calls[1][0]).toContain("event=push");
  for (const [, options] of read.mock.calls) {
    expect(options.headers.Authorization).toBeUndefined();
    expect(options.signal).toBeInstanceOf(AbortSignal);
  }
});
