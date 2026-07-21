"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAnalyticsContext } from "@/components/Analytics";

const FOOTER_LINKS: { heading: string; links: { label: string; href: string }[] }[] = [
  {
    heading: "Explore",
    links: [
      { label: "Discover", href: "/discover" },
      { label: "Sports", href: "/sports" },
      { label: "Calibration", href: "/calibration" },
      { label: "My Stuff", href: "/my-stuff" },
    ],
  },
  {
    heading: "Categories",
    links: [
      { label: "Politics", href: "/politics" },
      { label: "Economics", href: "/economics" },
      { label: "Entertainment", href: "/entertainment" },
      { label: "Weather", href: "/weather" },
    ],
  },
  {
    heading: "Bain Luck",
    links: [
      { label: "About", href: "/about" },
      { label: "Privacy", href: "/privacy" },
      { label: "Report a bug", href: "mailto:bugs@bainluck.com" },
    ],
  },
];

export default function Footer() {
  const pathname = usePathname();
  const { track } = useAnalyticsContext();

  const onClick = (href: string) => {
    track("navigation_click", {
      click_type: "footer_link" as const,
      from_page: pathname || "/",
      to_page: href,
    });
  };

  return (
    <footer className="border-t border-surface-border bg-surface-card/40 mt-8">
      <div className="max-w-content mx-auto px-4 md:px-6 py-10 pb-28 md:pb-10">
        <div className="grid gap-8 sm:grid-cols-2 md:grid-cols-4">
          {/* Brand + one-liner */}
          <div className="space-y-3 md:col-span-1">
            <Link href="/about" onClick={() => onClick("/about")} className="flex items-center gap-2">
              <span className="text-xl">🍀</span>
              <span className="text-body-strong text-text-primary">Bain Luck</span>
            </Link>
            <p className="text-micro text-text-muted leading-relaxed max-w-[16rem]">
              Probability, not betting. The world&rsquo;s honest guess at what happens next.
            </p>
          </div>

          {FOOTER_LINKS.map((col) => (
            <div key={col.heading} className="space-y-3">
              <h3 className="text-micro font-semibold uppercase tracking-wider text-text-muted">
                {col.heading}
              </h3>
              <ul className="space-y-2">
                {col.links.map((link) => {
                  const isMail = link.href.startsWith("mailto:");
                  return (
                    <li key={link.href}>
                      {isMail ? (
                        <a
                          href={link.href}
                          onClick={() => onClick(link.href)}
                          className="text-caption text-text-secondary hover:text-accent-brand transition-colors"
                        >
                          {link.label}
                        </a>
                      ) : (
                        <Link
                          href={link.href}
                          onClick={() => onClick(link.href)}
                          className="text-caption text-text-secondary hover:text-accent-brand transition-colors"
                        >
                          {link.label}
                        </Link>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-8 pt-6 border-t border-surface-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
          <p className="text-micro text-text-muted">
            © 2026 Bain Luck. For information and entertainment only — not betting advice.
          </p>
          <Link
            href="/about"
            onClick={() => onClick("/about")}
            className="text-micro text-accent-brand hover:underline"
          >
            What is Bain Luck?
          </Link>
        </div>
      </div>
    </footer>
  );
}
