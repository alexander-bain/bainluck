const GITHUB_REPO_API = "https://api.github.com/repos/alexander-bain/bainluck";
const READ_TIMEOUT_MS = 1_500;
const FACTORY_FAILURES = new Set(["failure", "timed_out", "startup_failure"]);

export type GitHubActivity = {
  checkedAt: string;
  masterAt?: string;
  ciAt?: string | null;
  collector?: { at: string; failed: boolean };
};

function timestamp(value: unknown): string | undefined {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) ? value : undefined;
}

type WorkflowRun = { status: string; conclusion: string | null; updated_at: string };

function latestCompletion(runs: WorkflowRun[], eligible: (run: WorkflowRun) => boolean) {
  return runs.reduce<WorkflowRun | undefined>((latest, run) =>
    run?.status === "completed" && timestamp(run.updated_at) && eligible(run) &&
      (!latest || Date.parse(run.updated_at) > Date.parse(latest.updated_at))
      ? run : latest, undefined);
}

export async function readGitHubActivity(fetcher: typeof fetch = fetch): Promise<GitHubActivity> {
  async function read(path: string) {
    try {
      const response = await fetcher(`${GITHUB_REPO_API}/${path}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(READ_TIMEOUT_MS),
        headers: { Accept: "application/vnd.github+json" },
      });
      return response.ok ? await response.json() : null;
    } catch {
      return null;
    }
  }

  const completed = "branch=master&status=completed&per_page=20";
  const [master, ci, factory] = await Promise.all([
    read("commits/master"),
    read(`actions/workflows/ci.yml/runs?${completed}&event=push`),
    read(`actions/workflows/factory.yml/runs?${completed}`),
  ]);
  const ciRuns = ci?.workflow_runs;
  const ciAt = Array.isArray(ciRuns)
    ? latestCompletion(ciRuns, run => typeof run.conclusion === "string")?.updated_at ??
      (ciRuns.length === 0 ? null : undefined)
    : undefined;
  const collector = Array.isArray(factory?.workflow_runs)
    ? latestCompletion(factory.workflow_runs, run =>
      run.conclusion === "success" || FACTORY_FAILURES.has(run.conclusion ?? ""))
    : undefined;
  return {
    checkedAt: new Date().toISOString(),
    masterAt: timestamp(master?.commit?.committer?.date),
    ciAt,
    ...(collector && { collector: { at: collector.updated_at, failed: collector.conclusion !== "success" } }),
  };
}
