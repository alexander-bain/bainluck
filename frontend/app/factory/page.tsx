import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import FactoryFloor from "./FactoryFloor";
import savedSnapshot from "./initial.json";
import type { FactoryData } from "./types";

export const revalidate = 60;

export const metadata: Metadata = {
  title: "The Factory",
  description:
    "Follow each change to Bain Luck, from its first lines to going live.",
  alternates: { canonical: "/factory" },
};

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--factory-body",
});
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  variable: "--factory-heading",
});
const dataUrl =
  "https://github.com/alexander-bain/bainluck/releases/download/factory-data/factory.json";

async function loadFactory(): Promise<{ data: FactoryData; saved: boolean }> {
  try {
    const response = await fetch(dataUrl, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) throw new Error("Snapshot unavailable");
    const payload = await response.json();
    if (
      payload.schema_version !== 1 ||
      !Array.isArray(payload.changes) ||
      !Array.isArray(payload.jams) ||
      !Number.isFinite(Date.parse(payload.generated_at))
    )
      throw new Error("Snapshot incomplete");
    // The release also holds the collector's metadata cache. Never send it to
    // the browser. Only this explicit public projection crosses the boundary.
    const data: FactoryData = {
      schema_version: payload.schema_version,
      generated_at: payload.generated_at,
      observed_since: payload.observed_since,
      changes: payload.changes,
      jams: payload.jams,
      signals: payload.signals,
      coverage: payload.coverage,
    };
    return { data, saved: false };
  } catch {
    return { data: savedSnapshot as FactoryData, saved: true };
  }
}

export default async function FactoryPage() {
  const { data, saved } = await loadFactory();
  return (
    <div className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <FactoryFloor
        data={data}
        saved={saved}
        renderedAt={new Date().toISOString()}
      />
    </div>
  );
}
