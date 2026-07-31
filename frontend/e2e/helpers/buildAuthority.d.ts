export declare const FULL_SHA_RE: RegExp;

export declare function normalizeSha(value: unknown): string | null;

export declare function compareSha(
  requested: unknown,
  observed: unknown
): {
  match: boolean;
  requested: string | null;
  observed: string | null;
  reason: string;
};

export declare function fetchFrontendBuild(
  baseUrl: string,
  options?: { fetchImpl?: typeof fetch; timeoutMs?: number }
): Promise<{ ok: boolean; commit: string | null; status: number | null; error: string | null }>;

export declare function waitForFrontendSha(options: {
  baseUrl: string;
  requestedSha: string;
  timeoutMs?: number;
  intervalMs?: number;
  fetchImpl?: typeof fetch;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  onAttempt?: (info: { attempt: number; observed: string | null; error: string | null }) => void;
}): Promise<{
  ok: boolean;
  observed: string | null;
  attempts: number;
  reason: string;
  lastError: string | null;
}>;

export declare function fetchBackendHealthSha(
  apiBaseUrl: string,
  options?: { fetchImpl?: typeof fetch; timeoutMs?: number }
): Promise<{ observed_backend_sha: string | null; error: string | null }>;
