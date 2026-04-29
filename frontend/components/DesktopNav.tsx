"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAnalyticsContext } from "@/components/Analytics";

/**
 * Desktop tab navigation — Feed / Search / My Stuff
 * Hidden on mobile (shown md: and up), positioned between logo and search bar.
 */
export default function DesktopNav() {
  const pathname = usePathname();
  const { track } = useAnalyticsContext();

  const tabs = [
    {
      label: "Feed",
      href: "/",
      isActive: pathname === "/" || pathname === "",
    },
    {
      label: "Discover",
      href: "/discover",
      isActive: pathname === "/discover",
    },
    {
      label: "Weather",
      href: "/weather",
      isActive: pathname === "/weather",
    },
    {
      label: "Economics",
      href: "/economics",
      isActive: pathname === "/economics",
    },
    {
      label: "My Stuff",
      href: "/my-stuff",
      isActive: pathname === "/my-stuff" || pathname === "/preferences" || pathname === "/onboarding",
    },
  ];

  return (
    <nav className="hidden md:flex items-center gap-1">
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          onClick={() => {
            if (!tab.isActive) {
              track('navigation_click', {
                click_type: 'nav_tab' as const,
                from_page: pathname || '/',
                to_page: tab.href,
              });
            }
          }}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            tab.isActive
              ? "text-accent-brand bg-accent-brand/10"
              : "text-text-muted hover:text-text-secondary hover:bg-surface-elevated"
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}
