const GITHUB_REPO_API = "https://api.github.com/repos/alexander-bain/bainluck";
const READ_TIMEOUT_MS = 1_500;
const FACTORY_FAILURES = new Set(["failure", "timed_out", "startup_failure"]);
const RUNS_PER_PAGE = 20;
export const MACHINE_WAIT_MS = 15 * 60_000;

export type GitHubActivity = {
  checkedAt: string;
  masterAt?: string;
  ciAt?: string | null;
  collector?: { at: string; failed: boolean };
  collectorQueuedAt?: string;
};

function timestamp(value: unknown): string | undefined {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) ? value : undefined;
}

type WorkflowRun = {
  status: string;
  conclusion: string | null;
  updated_at: string;
  id?: number;
  created_at?: string;
};

type WorkflowJob = {
  status: string;
  runner_name?: string | null;
  runner_id?: number | null;
  labels?: string[];
  queued_at?: string;
  created_at?: string;
};

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

  const runsQuery = `branch=master&per_page=${RUNS_PER_PAGE}`;
  const factoryRunsPath = `actions/workflows/factory.yml/runs?${runsQuery}`;
  const [master, ci, factory] = await Promise.all([
    read("commits/master"),
    read(`actions/workflows/ci.yml/runs?${runsQuery}&status=completed&event=push`),
    read(factoryRunsPath),
  ]);
  const ciRuns = ci?.workflow_runs;
  const ciAt = Array.isArray(ciRuns)
    ? latestCompletion(ciRuns, run => typeof run.conclusion === "string")?.updated_at ??
      (ciRuns.length === 0 ? null : undefined)
    : undefined;
  const factoryRuns: WorkflowRun[] = Array.isArray(factory?.workflow_runs) ? factory.workflow_runs : [];
  const collector = latestCompletion(factoryRuns, run =>
    run.conclusion === "success" || FACTORY_FAILURES.has(run.conclusion ?? ""));
  const cutoff = Date.now() - MACHINE_WAIT_MS;
  const couldBeWaiting = (run: WorkflowRun) =>
    (run?.status === "queued" || run?.status === "in_progress") &&
    typeof run.id === "number" && Number.isSafeInteger(run.id) && run.id > 0 &&
    Date.parse(run.created_at ?? "") < cutoff;
  let possibleWait = factoryRuns.find(couldBeWaiting);
  // A busy window can bury its waiting run under completions and cancellations.
  if (!possibleWait && factoryRuns.length === RUNS_PER_PAGE &&
      Date.parse(factoryRuns.at(-1)?.created_at ?? "") > cutoff) {
    const queued = await read(`${factoryRunsPath}&status=queued`);
    if (Array.isArray(queued?.workflow_runs)) possibleWait = queued.workflow_runs.find(couldBeWaiting);
  }
  const jobList = possibleWait && await read(`actions/runs/${possibleWait.id}/jobs?per_page=20`);
  // A pending run can be waiting on the workflow's concurrency group. Only
  // an unassigned GitHub-hosted job proves it is waiting for a machine.
  const jobs: WorkflowJob[] = Array.isArray(jobList?.jobs) ? jobList.jobs : [];
  const job = jobs.find(job =>
    job?.status === "queued" && !job.runner_name && !job.runner_id &&
    Array.isArray(job.labels) && job.labels.includes("ubuntu-latest"));
  const collectorQueuedAt = job ? timestamp(job.queued_at) ?? timestamp(job.created_at) : undefined;
  return {
    checkedAt: new Date().toISOString(),
    masterAt: timestamp(master?.commit?.committer?.date),
    ciAt,
    ...(collector && { collector: { at: collector.updated_at, failed: collector.conclusion !== "success" } }),
    ...(collectorQueuedAt && { collectorQueuedAt }),
  };
}
