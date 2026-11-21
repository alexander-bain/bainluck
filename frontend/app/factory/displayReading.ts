import { createHash } from "node:crypto";
import { unstable_cache } from "next/cache";
import { frontendCommitSha } from "@/lib/buildInfo";
import { createFactoryReader } from "./data";

const readFactory = createFactoryReader(undefined, load =>
  unstable_cache(load, ["factory-live-v4"], { revalidate: 60 }),
);

export async function loadFactoryReading() {
  const reading = await readFactory();
  return {
    ...reading,
    snapshotDigest: reading.data
      ? createHash("sha256").update(JSON.stringify(reading.data)).digest("hex")
      : null,
    renderedAt: new Date().toISOString(),
    buildCommit: frontendCommitSha(),
  };
}

export type FactoryDisplayReading = Awaited<ReturnType<typeof loadFactoryReading>>;
