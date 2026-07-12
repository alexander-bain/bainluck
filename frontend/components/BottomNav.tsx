"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAnalyticsContext } from "@/components/Analytics";

const browsePages = [
  { label: "MMA", href: "/hub/mma", emoji: "🥊" },
  { label: "Golf", href: "/hub/golf", emoji: "⛳" },
  { label: "Tennis", href: "/hub/tennis", emoji: "🎾" },
  { label: "Politics", href: "/politics", emoji: "🏛" },
  { label: "Entertainment", href: "/entertainment", emoji: "🎬" },
  { label: "Economics", href: "/economics", emoji: "📈" },
  { label: "Weather", href: "/weather", emoji: "🌤" },
];

export default function BottomNav() {
  const pathname = usePathname();
  const { track } = useAnalyticsContext();
  const [browseOpen, setBrowseOpen] = useState(false);
  const browseRef = useRef<HTMLDivElement>(null);

  const isBrowseActive = browsePages.some((p) => pathname === p.href);

  useEffect(() => {
    if (!browseOpen) return;
    function handleClick(e: MouseEvent) {
      if (browseRef.current && !browseRef.current.contains(e.target as Node)) {
        setBrowseOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [browseOpen]);

  const tabs = [
    {
      label: "Discover",
      href: "/",
      icon: DiscoverIcon,
      isActive: pathname === "/" || pathname === "" || pathname === "/discover",
    },
    {
      label: "Sports",
      href: "/sports",
      icon: FeedIcon,
      isActive: pathname === "/sports",
    },
    {
      label: "Browse",
      href: null as string | null,
      icon: BrowseIcon,
      isActive: isBrowseActive,
    },
    {
      label: "My Stuff",
      href: "/my-stuff",
      icon: UserIcon,
      isActive: pathname === "/my-stuff" || pathname === "/preferences" || pathname === "/onboarding",
    },
  ];

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50" ref={browseRef} aria-label="Mobile navigation">
      {browseOpen && (
        <>
          <div
            className="fixed inset-0 bg-black/20 z-40" aria-hidden="true"
            onClick={() => setBrowseOpen(false)}
          />
          <div className="relative z-50 mx-4 mb-2 bg-surface-card rounded-2xl border border-surface-border shadow-lg overflow-hidden" role="menu" aria-label="Browse categories">
            {browsePages.map((page) => (
              <Link
                key={page.href}
                href={page.href}
                onClick={() => {
                  setBrowseOpen(false);
                  track("navigation_click", {
                    click_type: "nav_tab" as const,
                    from_page: pathname || "/",
                    to_page: page.href,
                  });
                }}
                className={`flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                  pathname === page.href
                    ? "text-accent-brand bg-accent-brand/5"
                    : "text-text-primary hover:bg-surface-elevated active:bg-surface-elevated"
                }`}
              >
                <span className="text-base">{page.emoji}</span>
                <span className="font-medium">{page.label}</span>
              </Link>
            ))}
          </div>
        </>
      )}

      <div className="bg-surface-card/95 backdrop-blur-lg border-t border-surface-border bottom-nav-safe">
        <div className="flex items-center justify-around h-14 max-w-md mx-auto">
          {tabs.map((tab) =>
            tab.href ? (
              <Link
                key={tab.label}
                href={tab.href}
                onClick={() => {
                  if (!tab.isActive) {
                    track("navigation_click", {
                      click_type: "nav_tab" as const,
                      from_page: pathname || "/",
                      to_page: tab.href,
                    });
                  }
                }}
                aria-current={tab.isActive ? "page" : undefined}
                aria-label={tab.label}
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
            ) : (
              <button
                key={tab.label}
                onClick={() => {
                  setBrowseOpen(!browseOpen);
                  if (!browseOpen) {
                    track("navigation_click", {
                      click_type: "nav_tab" as const,
                      from_page: pathname || "/",
                      to_page: "/browse",
                    });
                  }
                }}
                aria-expanded={browseOpen} aria-label="Browse categories" className={`flex flex-col items-center justify-center gap-0.5 flex-1 h-full transition-colors ${
                  tab.isActive || browseOpen
                    ? "text-accent-brand"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                <tab.icon active={tab.isActive || browseOpen} />
                <span className="text-[10px] font-medium tracking-wide">
                  {tab.label}
                </span>
              </button>
            )
          )}
        </div>
      </div>
    </nav>
  );
}

function FeedIcon({ active }: { active: boolean }) {
  return (
    <svg
      aria-hidden="true"
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

function DiscoverIcon({ active }: { active: boolean }) {
  return (
    <svg
      aria-hidden="true"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={active ? 2.5 : 1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" fill={active ? "currentColor" : "none"} />
    </svg>
  );
}

function BrowseIcon({ active }: { active: boolean }) {
  return (
    <svg
      aria-hidden="true"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={active ? 2.5 : 1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="8" cy="8" r="4" />
      <circle cx="16" cy="8" r="4" />
      <circle cx="8" cy="16" r="4" />
      <circle cx="16" cy="16" r="4" />
    </svg>
  );
}

function UserIcon({ active }: { active: boolean }) {
  return (
    <svg
      aria-hidden="true"
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
