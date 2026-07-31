/**
 * The frontend's own deployment identity — L2-221 Item 2.
 *
 * Vercel deploys independently of Heroku and of the GitHub SHA that triggered
 * CI. A browser audit that reads neither can exercise the previous or the next
 * deployment and still be attached as proof for the requested commit (C96
 * [P1]). So the frontend publishes its own marker, and the audit rail treats
 * it as the ONLY frontend authority — backend `/health` is recorded beside it,
 * never in place of it.
 *
 * Non-secret by construction: a commit sha of a public repository, and nothing
 * else. No env var is invented here — Vercel sets `VERCEL_GIT_COMMIT_SHA`
 * automatically for every deployment.
 */

/** Full 40-hex, lowercase. Abbreviations are ambiguous and are not accepted. */
const FULL_SHA_RE = /^[0-9a-f]{40}$/;

export function normalizeCommitSha(value: string | undefined | null): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim().toLowerCase();
  return FULL_SHA_RE.test(trimmed) ? trimmed : null;
}

/**
 * The deployed commit, or `null` when it cannot be determined (local dev, or a
 * host that does not set it). `null` is deliberate and must stay visible: the
 * audit rail fails loudly on a missing marker rather than assuming a match.
 */
export function frontendCommitSha(): string | null {
  return (
    normalizeCommitSha(process.env.VERCEL_GIT_COMMIT_SHA) ??
    normalizeCommitSha(process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA)
  );
}

/** The deployment environment Vercel reports, when it reports one. */
export function frontendEnv(): string | null {
  const value = process.env.VERCEL_ENV ?? process.env.NEXT_PUBLIC_VERCEL_ENV;
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export interface FrontendBuildMarker {
  /** Full 40-hex commit sha, or null when unavailable. */
  commit: string | null;
  env: string | null;
}

export function frontendBuildMarker(): FrontendBuildMarker {
  return { commit: frontendCommitSha(), env: frontendEnv() };
}

/** The meta tag name carrying the marker on every rendered page. */
export const BUILD_META_NAME = "bainluck-frontend-commit";
