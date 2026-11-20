import type { Metadata } from "next";
import { cache } from "react";
import { Inter, Space_Grotesk } from "next/font/google";
import { unstable_cache } from "next/cache";
import FactoryFloor from "./FactoryFloor";
import { createFactoryReader } from "./data";
import { factoryTabTitle, floorVerdict } from "./verdict";

export const revalidate = 60;
export const dynamic = "force-dynamic";

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
const readFactory = createFactoryReader(undefined, (load) =>
  unstable_cache(load, ["factory-live-v4"], { revalidate: 60 }),
);

const loadFactory = cache(async () => {
  const read = await readFactory();
  return { ...read, renderedAt: new Date().toISOString() };
});

export async function generateMetadata(): Promise<Metadata> {
  const { data, readFailed, renderedAt } = await loadFactory();
  return {
    title: { absolute: factoryTabTitle(floorVerdict(data, readFailed, renderedAt)) },
    description:
      "Follow each change to Bain Luck, from its first lines to going live.",
    alternates: { canonical: "/factory" },
  };
}

export default async function FactoryPage() {
  const read = await loadFactory();
  return (
    <div className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <FactoryFloor {...read} />
    </div>
  );
}
