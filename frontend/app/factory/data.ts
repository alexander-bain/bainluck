import type { FactoryData } from "./types";

export const FACTORY_DATA_URL =
  "https://github.com/alexander-bain/bainluck/releases/download/factory-data/factory.json";

export interface FactoryRead {
  data: FactoryData | null;
  lastGoodAt: string | null;
}

export function createFactoryReader(fetcher: typeof fetch = fetch) {
  let lastGoodAt: string | null = null;
  return async (): Promise<FactoryRead> => {
    try {
      const response = await fetcher(FACTORY_DATA_URL, {
        cache: "no-store",
        signal: AbortSignal.timeout(800),
      });
      if (!response.ok) throw new Error("Snapshot unavailable");
      const payload = await response.json();
      if (
        payload.schema_version !== 1 ||
        !Array.isArray(payload.changes) ||
        !Array.isArray(payload.jams) ||
        !Array.isArray(payload.coverage) ||
        !payload.coverage.every((note: unknown) => typeof note === "string") ||
        !payload.signals ||
        !Array.isArray(payload.transitions ?? []) ||
        !(payload.transitions ?? []).every(
          (transfer: NonNullable<FactoryData["transitions"]>[number]) =>
            Number.isSafeInteger(transfer.number) &&
            ["Server", "Website", "Apps"].includes(transfer.line) &&
            ["Write", "Test", "Review", "Merge line", "Ship", "Live"].includes(
              transfer.from,
            ) &&
            ["Write", "Test", "Review", "Merge line", "Ship", "Live"].includes(
              transfer.to,
            ) &&
            Number.isFinite(Date.parse(transfer.at)),
        ) ||
        !Array.isArray(payload.stops ?? []) ||
        !(payload.stops ?? []).every(
          (stop: NonNullable<FactoryData["stops"]>[number]) =>
            [
              "line-stalled",
              "announced",
              "hold",
              "master",
              "review-waiting",
            ].includes(stop.kind) &&
            (stop.line === null ||
              ["Server", "Website", "Apps"].includes(stop.line)) &&
            ["Write", "Test", "Review", "Merge line", "Ship", "Live"].includes(
              stop.station,
            ) &&
            ["red", "amber"].includes(stop.level) &&
            Number.isSafeInteger(stop.count) &&
            stop.count >= 0 &&
            Number.isFinite(Date.parse(stop.since)),
        ) ||
        !payload.changes.every(
          (change: FactoryData["changes"][number]) =>
            Number.isSafeInteger(change.number) &&
            change.number > 0 &&
            typeof change.title === "string" &&
            ["Server", "Website", "Apps"].includes(change.line) &&
            ["Write", "Test", "Review", "Merge line", "Ship", "Live"].includes(
              change.station,
            ) &&
            Array.isArray(change.reasons) &&
            Number.isFinite(Date.parse(change.last_activity)),
        ) ||
        !Number.isFinite(Date.parse(payload.generated_at)) ||
        (payload.read_expires_at !== undefined && !Number.isFinite(Date.parse(payload.read_expires_at))) ||
        !Number.isFinite(Date.parse(payload.observed_since))
      )
        throw new Error("Snapshot incomplete");
      const data: FactoryData = {
        schema_version: payload.schema_version,
        generated_at: payload.generated_at,
        observed_since: payload.observed_since,
        ...(payload.read_expires_at
          ? { read_expires_at: payload.read_expires_at }
          : {}),
        ...(payload.transitions ? { transitions: payload.transitions } : {}),
        ...(payload.stops ? { stops: payload.stops } : {}),
        changes: payload.changes,
        jams: payload.jams,
        signals: payload.signals,
        coverage: payload.coverage,
      };
      lastGoodAt = data.generated_at;
      return { data, lastGoodAt };
    } catch (error) {
      console.warn(
        "Factory live read failed",
        error instanceof Error ? error.message : "Unknown read failure",
      );
      return { data: null, lastGoodAt };
    }
  };
}
