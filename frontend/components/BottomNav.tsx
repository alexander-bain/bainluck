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
      label: "Leagues",
      href: "/playoffs",
      icon: TrophyIcon,
      isActive: pathname.startsWith("/playoffs"),
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

function TrophyIcon({ active }: { active: boolean }) {
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
      <path d="M6 9H4.5a2.5 2.5 0 010-5H6" />
      <path d="M18 9h1.5a2.5 2.5 0 000-5H18" />
      <path d="M4 22h16" />
      <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />
      <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />
      <path d="M18 2H6v7a6 6 0 1012 0V2Z" />
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
