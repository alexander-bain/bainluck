import type { FactoryData } from "./types";

export const FACTORY_DATA_URL =
  "https://github.com/alexander-bain/bainluck/releases/download/factory-data/factory.json";

export interface FactoryRead {
  data: FactoryData | null;
  lastGoodAt: string | null;
  readFailed: boolean;
}

interface VerifiedRead {
  data: FactoryData;
  checkedAt: number;
}

type LoadVerifiedRead = () => Promise<VerifiedRead>;

function validateSnapshot(payload: FactoryData): FactoryData {
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
    (payload.read_expires_at !== undefined &&
      !Number.isFinite(Date.parse(payload.read_expires_at))) ||
    !Number.isFinite(Date.parse(payload.observed_since))
  )
    throw new Error("Snapshot incomplete");
  return {
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
}

async function readSnapshot(fetcher: typeof fetch, attempt: 1 | 2) {
  const startedAt = performance.now();
  // Cloud reads took up to 620 ms, and five production reads exceeded 800 ms.
  const signal = AbortSignal.timeout(4000);
  let outcome = "success";
  let status: number | undefined;
  try {
    const response = await fetcher(FACTORY_DATA_URL, {
      cache: "no-store",
      signal,
    });
    status = response.status;
    if (!response.ok) throw new Error("Snapshot unavailable");
    return validateSnapshot(await response.json());
  } catch (error) {
    outcome =
      signal.aborted ||
      (error instanceof Error && error.name === "TimeoutError")
        ? "timeout"
        : "failed";
    throw error;
  } finally {
    const receipt = {
      attempt,
      durationMs: Math.round(performance.now() - startedAt),
      outcome,
      status,
    };
    if (outcome === "success") console.info("Factory live read", receipt);
    else console.warn("Factory live read", receipt);
  }
}

export function createFactoryReader(
  fetcher: typeof fetch = (...args) => fetch(...args),
  cacheVerifiedRead: (load: LoadVerifiedRead) => LoadVerifiedRead = (load) =>
    load,
) {
  let lastGood: VerifiedRead | null = null;
  let lastFailureAt: number | null = null;
  let pending: Promise<VerifiedRead> | null = null;

  async function fetchWithRetry() {
    try {
      return await readSnapshot(fetcher, 1);
    } catch {
      return readSnapshot(fetcher, 2);
    }
  }

  // A rejected refresh leaves the previous verified entry in Next's Data Cache.
  const load = cacheVerifiedRead(() => {
    pending ??= fetchWithRetry()
      .then(
        (data) => {
          lastGood = { data, checkedAt: Date.now() };
          lastFailureAt = null;
          return lastGood;
        },
        (error) => {
          lastFailureAt = Date.now();
          throw error;
        },
      )
      .finally(() => {
        pending = null;
      });
    return pending;
  });

  return async (): Promise<FactoryRead> => {
    let readFailed: boolean;
    try {
      const read = await load();
      if (!lastGood || read.checkedAt >= lastGood.checkedAt) lastGood = read;
      readFailed =
        lastFailureAt !== null && lastFailureAt >= lastGood.checkedAt;
    } catch {
      readFailed = true;
    }
    return {
      data: lastGood?.data ?? null,
      lastGoodAt: lastGood?.data.generated_at ?? null,
      readFailed,
    };
  };
}
