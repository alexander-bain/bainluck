import { crewActivity, onActiveFloor, recentlyActive } from "./activity";
import { nameableBuilders, type NameableBuilder } from "./builderNames";
import type { Change, FactoryData, FloorEvent, Line, Station } from "./types";
import type { WorkerState } from "./Worker";

export type CrewMove =
  | "walk" | "carry" | "cheer" | "slump" | "work"
  | "fist-pump" | "sign" | "flex" | "slide" | "cartwheel";

export type FloorCrew = {
  identity: NameableBuilder;
  pose: WorkerState;
  position?: { line: Line; station: Station };
};

export function placeCrew(data: FactoryData, now: string, visible: Change[]): FloorCrew[] {
  return nameableBuilders.map(identity => {
    if (identity === "Fable") {
      const look = data.events?.filter(event =>
        (event.kind === "fable" || event.kind === "returned") && recentlyActive(event.observed_at, now),
      ).at(-1);
      return { identity, pose: crewPose(data, identity, now, []).pose,
        position: { line: look?.line ?? "Server", station: "Review" } };
    }
    const changes = visible.filter(change => change.builder === identity).sort((a, b) =>
      Date.parse(b.last_activity) - Date.parse(a.last_activity) || a.number - b.number,
    );
    const status = crewPose(data, identity, now, changes);
    const change = status.change ?? changes.find(onActiveFloor) ??
      changes.find(crate => crate.live_at && recentlyActive(crate.live_at, now));
    return change
      ? { identity, pose: status.pose, position: { line: change.line, station: change.station } }
      : { identity, pose: "asleep" };
  });
}

export function crewAction(event: FloorEvent): {
  identity: NameableBuilder; state: WorkerState; move: CrewMove;
} | undefined {
  if (event.kind === "fable") return { identity: "Fable", state: "working", move: "work" };
  const identity = event.builder;
  if (!identity || identity === "Other") return;
  if (event.kind === "returned" || (event.kind === "check" && event.outcome === "failed"))
    return { identity, state: "stuck", move: "slump" };
  if (event.kind === "live" || (event.kind === "move" && event.station === "Live")) {
    const move = identity === "S" ? "fist-pump" : identity === "D" ? "flex" : "cheer";
    return { identity, state: "celebrating", move };
  }
  if (event.from && event.from !== event.station) {
    const move = identity === "E" ? "slide" : identity === "F" ? "cartwheel" :
      event.station === "Test" ? "walk" : "carry";
    return { identity, state: "carrying", move };
  }
  if (event.kind === "commit") {
    return { identity, state: "working", move: identity === "B" ? "sign" : "work" };
  }
}

export function crewPose(data: FactoryData, identity: NameableBuilder, now: string, changes: Change[]) {
  const recent = (data.events ?? []).filter(event => recentlyActive(event.observed_at, now));
  if (identity === "Fable") {
    return {
      pose: recent.some(event => event.kind === "fable" || event.kind === "returned")
        ? "working" as const : "asleep" as const,
      change: null,
    };
  }
  const active = changes.filter(onActiveFloor);
  const pose = crewActivity(data, now, active);
  if (pose.pose === "carrying") return pose;
  const testing = active.find(change => change.station === "Test" && change.checks_running);
  if (testing) return { pose: "waiting" as const, change: testing };
  const latest = recent.filter(event => event.builder === identity).at(-1);
  if (latest && (latest.kind === "live" || (latest.kind === "move" && latest.station === "Live"))) {
    return { pose: "celebrating" as const, change: changes.find(change => change.number === latest.number) };
  }
  if (latest?.kind === "check" && latest.outcome === "failed" &&
      active.some(change => change.number === latest.number && change.station === "Test")) {
    return { pose: "stuck" as const, change: active.find(change => change.number === latest.number) };
  }
  if (identity === "C" && !data.changes.some(change =>
    change.builder === "C" && change.station === "Write" && onActiveFloor(change))) {
    return { pose: "asleep" as const, change: null };
  }
  return pose;
}
