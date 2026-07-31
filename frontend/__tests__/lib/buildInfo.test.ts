import {
  BUILD_META_NAME,
  frontendBuildMarker,
  frontendCommitSha,
  frontendEnv,
  normalizeCommitSha,
} from "@/lib/buildInfo";

/**
 * L2-221 Item 2 — the frontend build marker is the browser-audit rail's only
 * frontend deployment authority. If it can report a wrong or abbreviated sha,
 * a run can be attached to the wrong deployment.
 */

const SHA = "0123456789abcdef0123456789abcdef01234567";

describe("normalizeCommitSha", () => {
  it("accepts a full 40-hex sha and lowercases it", () => {
    expect(normalizeCommitSha(SHA.toUpperCase())).toBe(SHA);
    expect(normalizeCommitSha(`  ${SHA}\n`)).toBe(SHA);
  });

  it("rejects an abbreviated sha — 7 chars are ambiguous across a long repo", () => {
    expect(normalizeCommitSha(SHA.slice(0, 7))).toBeNull();
    expect(normalizeCommitSha(SHA.slice(0, 12))).toBeNull();
  });

  it("rejects empties, non-hex and non-strings", () => {
    expect(normalizeCommitSha("")).toBeNull();
    expect(normalizeCommitSha("   ")).toBeNull();
    expect(normalizeCommitSha("z".repeat(40))).toBeNull();
    expect(normalizeCommitSha(undefined)).toBeNull();
    expect(normalizeCommitSha(null)).toBeNull();
  });
});

describe("frontendCommitSha", () => {
  const original = { ...process.env };

  afterEach(() => {
    process.env = { ...original };
  });

  it("reads the Vercel server-side system variable", () => {
    process.env.VERCEL_GIT_COMMIT_SHA = SHA;
    expect(frontendCommitSha()).toBe(SHA);
  });

  it("falls back to the public variable when the system one is absent", () => {
    delete process.env.VERCEL_GIT_COMMIT_SHA;
    process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA = SHA;
    expect(frontendCommitSha()).toBe(SHA);
  });

  it("returns null rather than guessing when neither is set", () => {
    delete process.env.VERCEL_GIT_COMMIT_SHA;
    delete process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA;
    expect(frontendCommitSha()).toBeNull();
  });

  it("returns null for a malformed value — never a partial sha", () => {
    process.env.VERCEL_GIT_COMMIT_SHA = SHA.slice(0, 7);
    expect(frontendCommitSha()).toBeNull();
  });
});

describe("frontendBuildMarker", () => {
  const original = { ...process.env };

  afterEach(() => {
    process.env = { ...original };
  });

  it("exposes only the commit and the environment — no secrets, no env dump", () => {
    process.env.VERCEL_GIT_COMMIT_SHA = SHA;
    process.env.VERCEL_ENV = "production";
    const marker = frontendBuildMarker();
    expect(marker).toEqual({ commit: SHA, env: "production" });
    expect(Object.keys(marker).sort()).toEqual(["commit", "env"]);
  });

  it("reports null commit rather than omitting the field", () => {
    delete process.env.VERCEL_GIT_COMMIT_SHA;
    delete process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA;
    expect(frontendBuildMarker().commit).toBeNull();
  });

  it("reports a null env when the host does not set one", () => {
    delete process.env.VERCEL_ENV;
    delete process.env.NEXT_PUBLIC_VERCEL_ENV;
    expect(frontendEnv()).toBeNull();
  });
});

describe("meta tag name", () => {
  it("is stable — the audit rail selects on it", () => {
    expect(BUILD_META_NAME).toBe("bainluck-frontend-commit");
  });
});
