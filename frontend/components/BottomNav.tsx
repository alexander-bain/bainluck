"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Mobile bottom tab navigation — Feed / Search / My Stuff
 * Hidden on desktop (md: breakpoint and up)
 */
export default function BottomNav() {
  const pathname = usePathname();

  const tabs = [
    {
      label: "Feed",
      href: "/",
      icon: FeedIcon,
      isActive: pathname === "/" || pathname === "",
    },
    {
      label: "Search",
      href: "/search",
      icon: SearchIcon,
      isActive: pathname === "/search",
    },
    {
      label: "My Stuff",
      href: "/my-stuff",
      icon: UserIcon,
      isActive: pathname === "/my-stuff" || pathname === "/preferences" || pathname === "/onboarding",
    },
  ];

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-surface-card/95 backdrop-blur-lg border-t border-surface-border bottom-nav-safe">
      <div className="flex items-center justify-around h-14 max-w-md mx-auto">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={`flex flex-col items-center justify-center gap-0.5 flex-1 h-full transition-colors ${
              tab.isActive
                ? "text-accent-brand"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            <tab.icon active={tab.isActive} />
            <span className="text-[10px] font-medium tracking-wide">
              {tab.label}
            </span>
          </Link>
        ))}
      </div>
    </nav>
  );
}

function FeedIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={active ? 2.5 : 1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  );
}

function SearchIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={active ? 2.5 : 1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function UserIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={active ? 2.5 : 1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}
