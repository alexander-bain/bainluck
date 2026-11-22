import { createHash } from "node:crypto";
import { unstable_cache } from "next/cache";
import { frontendCommitSha } from "@/lib/buildInfo";
import { createFactoryReader, type FactoryRead } from "./data";
import { readGitHubActivity, type GitHubActivity } from "./githubActivity";

const readFactory = createFactoryReader(undefined, load =>
  unstable_cache(load, ["factory-live-v4"], { revalidate: 60 }),
);
// Three public API calls per refresh. Five minutes keeps this cache below
// GitHub's unauthenticated limit while the page still checks the floor each minute.
const readActivity = unstable_cache(() => readGitHubActivity(), ["factory-github-activity"], { revalidate: 300 });

export type FactoryDisplayReading = FactoryRead & {
  activity?: GitHubActivity;
  snapshotDigest: string | null;
  renderedAt: string;
  buildCommit: string | null;
};

export async function loadFactoryReading(): Promise<FactoryDisplayReading> {
  const [reading, activity] = await Promise.all([
    readFactory(),
    readActivity().catch(() => undefined),
  ]);
  return {
    ...reading,
    activity,
    snapshotDigest: reading.data
      ? createHash("sha256").update(JSON.stringify(reading.data)).digest("hex")
      : null,
    renderedAt: new Date().toISOString(),
    buildCommit: frontendCommitSha(),
  };
}
