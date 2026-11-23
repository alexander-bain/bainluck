import { releaseStallText } from "@/app/factory/verdict";
import type { Change, FactoryData } from "@/app/factory/types";
import incident from "./fixtures/factory-release-nov23.json";

function replay(generatedAt: string, releasedAt?: string): FactoryData {
  const changes: Change[] = incident.pending
    .filter(change => change.merged_at <= generatedAt)
    .map(change => ({
      ...change, line: "Server", builder: "Other", title: "Recorded change",
      station: releasedAt ? "Live" : "Ship", live_at: releasedAt ?? null,
      last_activity: change.merged_at, unsure: false, reasons: [], side_track: false, timing: null,
    }));
  return {
    schema_version: 1, generated_at: generatedAt, observed_since: incident.first_publication,
    changes, jams: [], stops: [], coverage: [], signals: { tests: "unknown", testflight: "success" },
  };
}

it("shows the stuck release at 1:35 AM PT from fresh CI and the held snapshot", () => {
  const now = "2026-11-23T09:35:00Z";
  const activity = { checkedAt: now, oldestRunningCI: incident.running_since };
  expect(releaseStallText(replay(incident.first_publication), now, activity))
    .toBe("Releases are stuck with 5 merged changes waiting to go live, and the oldest shared check has run for 1 hr 33 min.");
});

it("keeps the sign on at 6 AM PT and clears it after the verified server release", () => {
  const six = "2026-11-23T14:00:00Z";
  expect(releaseStallText(replay(incident.late_publication), six, { checkedAt: six, oldestRunningCI: null }))
    .toBe("Releases are stuck with 13 merged changes waiting to go live.");
  const observedRelease = "2026-11-23T14:24:26Z";
  expect(releaseStallText(
    replay(observedRelease, incident.released_at),
    observedRelease,
    { checkedAt: observedRelease, oldestRunningCI: incident.running_since }
  )).toBeUndefined();
});

it("uses either threshold and counts multiline changes and open trucks correctly", () => {
  const now = "2026-11-23T09:35:00Z";
  const almost = replay(incident.first_publication);
  almost.changes.pop();
  const [change] = almost.changes;
  almost.changes.push({ ...change, line: "Apps" }, { ...change, number: 100, merged_at: null });
  expect(releaseStallText(almost, now, { checkedAt: now, oldestRunningCI: "2026-11-23T08:35:00Z" }))
    .toBeUndefined();
  expect(releaseStallText(almost, now, { checkedAt: now, oldestRunningCI: "2026-11-23T08:34:59Z" }))
    .toContain("4 merged changes waiting");
  const expiredActivity = { checkedAt: "2026-11-23T09:15:00Z", oldestRunningCI: incident.running_since };
  expect(releaseStallText(almost, now, expiredActivity)).toBeUndefined();
});
