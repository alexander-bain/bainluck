import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { unstable_cache } from "next/cache";
import FactoryFloor from "./FactoryFloor";
import { createFactoryReader } from "./data";

export const revalidate = 60;
export const dynamic = "force-dynamic";

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
const loadFactory = createFactoryReader(undefined, (load) =>
  unstable_cache(load, ["factory-live-v4"], { revalidate: 60 }),
);

export default async function FactoryPage() {
  const read = await loadFactory();
  return (
    <div className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <FactoryFloor {...read} renderedAt={new Date().toISOString()} />
    </div>
  );
}
