"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAnalyticsContext } from "@/components/Analytics";
import dynamic from "next/dynamic";

const MobileSearchOverlay = dynamic(() => import("./MobileSearchOverlay"), { ssr: false });

export default function BottomNav() {
  const pathname = usePathname();
  const { track } = useAnalyticsContext();
  const [searchOpen, setSearchOpen] = useState(false);

  const tabs = [
    {
      label: "Sports",
      href: "/",
      icon: FeedIcon,
      isActive: pathname === "/" || pathname === "",
    },
    {
      label: "Discover",
      href: "/discover",
      icon: DiscoverIcon,
      isActive: pathname === "/discover",
    },
    {
      label: "Search",
      href: null,
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
    <>
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-surface-card/95 backdrop-blur-lg border-t border-surface-border bottom-nav-safe">
        <div className="flex items-center justify-around h-14 max-w-md mx-auto">
          {tabs.map((tab) =>
            tab.href ? (
              <Link
                key={tab.label}
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
                  setSearchOpen(true);
                  track('navigation_click', {
                    click_type: 'nav_tab' as const,
                    from_page: pathname || '/',
                    to_page: '/search',
                  });
                }}
                className={`flex flex-col items-center justify-center gap-0.5 flex-1 h-full transition-colors ${
                  searchOpen
                    ? "text-accent-brand"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                <tab.icon active={searchOpen} />
                <span className="text-[10px] font-medium tracking-wide">
                  {tab.label}
                </span>
              </button>
            )
          )}
        </div>
      </nav>
      <MobileSearchOverlay isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
    </>
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
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2.5 : 1.5} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function DiscoverIcon({ active }: { active: boolean }) {
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
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" fill={active ? "currentColor" : "none"} />
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
