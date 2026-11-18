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
        !Number.isFinite(Date.parse(payload.generated_at)) ||
        !Number.isFinite(Date.parse(payload.observed_since))
      )
        throw new Error("Snapshot incomplete");
      const data: FactoryData = {
        schema_version: payload.schema_version,
        generated_at: payload.generated_at,
        observed_since: payload.observed_since,
        changes: payload.changes,
        jams: payload.jams,
        signals: payload.signals,
        coverage: payload.coverage,
      };
      lastGoodAt = data.generated_at;
      return { data, lastGoodAt };
    } catch (error) {
      console.warn("Factory live read failed", error instanceof Error ? error.message : "Unknown read failure");
      return { data: null, lastGoodAt };
    }
  };
}
