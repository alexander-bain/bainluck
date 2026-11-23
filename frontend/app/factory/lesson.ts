import { onActiveFloor, pacificDay } from "./activity";
import type { Change, FactoryData } from "./types";

export const testDefinition = "A test is an automatic check for problems in a change.";

const words = [
  ["Pull request", "A pull request asks the team to add a change to the shared code.", "floor"],
  ["Test", testDefinition, "checks"],
  ["Review", "A review is a closer look at a change before it is added.", "inspection"],
  ["Merge", "A merge brings a change into the shared code.", "merged"],
  ["Deploy", "A deploy puts a change onto the site, server or app that people use.", "ship"],
  ["Bug", "A bug is a problem that makes software behave in an unintended way.", "checks"],
  ["Queue", "A queue is a line of work waiting for a turn.", "dock"],
  ["Rollback", "A rollback brings back an earlier version when a new version has a problem.", "live"],
  ["Branch", "A branch is a separate place to work on a change before adding it to the shared code.", "bench"],
  ["Commit", "A commit saves a small set of edits together.", "bench"],
  ["Draft", "A draft is a change that its builder is still getting ready.", "bench"],
  ["Build", "A build turns the code into a version a machine can run.", "ship"],
  ["Approval", "An approval says a change has had the look it needs to move forward.", "dock"],
  ["Release", "A release makes a new version available for people to use.", "live"],
  ["Patch", "A patch is a change that fixes or adjusts a piece of software.", "floor"],
  ["Regression", "A regression is a new problem in something that used to work.", "checks"],
  ["TestFlight", "TestFlight lets people try a version of the app before its wider release.", "apps"],
  ["Main branch", "The main branch is the shared copy where accepted changes come together.", "merged"],
  ["Rerun", "A rerun tries the same checks again.", "checks"],
  ["Test suite", "A test suite is a group of automatic checks that run together.", "checks"],
] as const;

const dateLabel = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles", month: "short", day: "numeric",
});

export function lessonForFloor(data: FactoryData, now: string) {
  const day = pacificDay(data.generated_at);
  const today = pacificDay(now);
  const dayNumber = Date.parse(`${today}T00:00:00Z`) / 86_400_000;
  const [word, definition, metric] = words[((dayNumber % words.length) + words.length) % words.length];
  const active = data.changes.filter(onActiveFloor);
  const merged = data.changes.filter(change => change.merged_at && pacificDay(change.merged_at) === day);
  const live = data.changes.filter(change => change.live_at && pacificDay(change.live_at) === day);
  const at = day === today ? "today" : `on ${dateLabel.format(new Date(data.generated_at))}`;
  const counts = {
    floor: [active, "on the floor"],
    bench: [active.filter(change => change.station === "Write"), "at the Bench"],
    checks: [active.filter(change => change.station === "Test"), "at Checks"],
    inspection: [active.filter(change => change.station === "Review"), "at Inspection"],
    dock: [active.filter(change => change.station === "Merge line"), "at the loading dock"],
    ship: [active.filter(change => change.station === "Ship"), "on the truck"],
    merged: [merged, `merged ${at}`],
    live: [live, `went live ${at}`],
    apps: [live.filter(change => change.line === "Apps"), `went live on Apps ${at}`],
  } as const;
  const [changes, label] = counts[metric];
  const count = new Set(changes.map(change => change.number)).size;
  return { word, definition, count: `${count} ${count === 1 ? "change" : "changes"} ${label}` };
}

export function hasFailedCheck(data: FactoryData, change: Change) {
  if (change.station !== "Test" || change.merged_at || !onActiveFloor(change)) return false;
  if (change.checks_failed === true) return true;
  const revision = Date.parse(change.revision_at ?? change.last_activity);
  return (data.events ?? []).some(event => event.kind === "check" && event.outcome === "failed" &&
    event.number === change.number && event.line === change.line &&
    Date.parse(event.at) >= revision && Date.parse(event.observed_at) <= Date.parse(data.generated_at));
}

export function explainedCheck(data: FactoryData) {
  const failed = data.changes.find(change => hasFailedCheck(data, change));
  if (failed) return `An automatic check flagged #${failed.number} before it could go live.`;
  const release = data.stops?.find(stop => stop.kind === "master" && stop.line === "Server" &&
    stop.station === "Ship" && stop.number);
  return release ? `A server test flagged #${release.number} before the release could reach a reader.` : undefined;
}
