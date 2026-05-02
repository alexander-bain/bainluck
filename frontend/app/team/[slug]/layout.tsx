import type { Metadata } from "next";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const name = slug
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

  return {
    title: `${name} Odds & Probabilities — Bain Luck`,
    description: `${name} win probabilities, championship odds, upcoming schedule, and season futures.`,
    openGraph: {
      title: `${name} — Bain Luck`,
      description: `${name} odds, schedule, and championship path.`,
      url: `https://bainluck.com/team/${slug}`,
    },
  };
}

export default function TeamLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
