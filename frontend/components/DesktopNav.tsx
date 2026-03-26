"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Desktop tab navigation — Feed / Search / My Stuff
 * Hidden on mobile (shown md: and up), positioned between logo and search bar.
 */
export default function DesktopNav() {
  const pathname = usePathname();

  const tabs = [
    {
      label: "Feed",
      href: "/",
      isActive: pathname === "/" || pathname === "",
    },
    {
      label: "Search",
      href: "/search",
      isActive: pathname === "/search",
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
