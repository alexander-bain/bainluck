"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAnalyticsContext } from "@/components/Analytics";
import { useState, useRef, useEffect } from "react";

const browsePages = [
  { label: "Politics", href: "/politics", emoji: "🏛" },
  { label: "Entertainment", href: "/entertainment", emoji: "🎬" },
  { label: "Economics", href: "/economics", emoji: "📈" },
  { label: "Weather", href: "/weather", emoji: "🌤" },
];

export default function DesktopNav() {
  const pathname = usePathname();
  const { track } = useAnalyticsContext();
  const [browseOpen, setBrowseOpen] = useState(false);
  const browseRef = useRef<HTMLDivElement>(null);

  const isBrowseActive = browsePages.some((p) => pathname === p.href);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (browseRef.current && !browseRef.current.contains(e.target as Node)) {
        setBrowseOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const tabs = [
    {
      label: "Discover",
      href: "/",
      isActive: pathname === "/" || pathname === "" || pathname === "/discover",
    },
    {
      label: "Sports",
      href: "/sports",
      isActive: pathname === "/sports",
    },
    {
      label: "My Stuff",
      href: "/my-stuff",
      isActive: pathname === "/my-stuff" || pathname === "/preferences" || pathname === "/onboarding",
    },
  ];

  return (
    <nav className="hidden md:flex items-center gap-1">
      {tabs.slice(0, 2).map((tab) => (
        <Link
          key={tab.href}
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
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            tab.isActive
              ? "text-accent-brand bg-accent-brand/10"
              : "text-text-muted hover:text-text-secondary hover:bg-surface-elevated"
          }`}
        >
          {tab.label}
        </Link>
      ))}

      {/* Browse dropdown */}
      <div ref={browseRef} className="relative">
        <button
          onClick={() => setBrowseOpen(!browseOpen)}
          onMouseEnter={() => setBrowseOpen(true)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1 ${
            isBrowseActive
              ? "text-accent-brand bg-accent-brand/10"
              : "text-text-muted hover:text-text-secondary hover:bg-surface-elevated"
          }`}
        >
          Browse
          <svg className={`w-3 h-3 transition-transform ${browseOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
          </svg>
        </button>
        {browseOpen && (
          <div
            className="absolute top-full left-0 mt-1 w-48 bg-surface-card border border-surface-border rounded-xl shadow-lg py-1 z-50"
            onMouseLeave={() => setBrowseOpen(false)}
          >
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
                className={`flex items-center gap-2.5 px-4 py-2.5 text-sm transition-colors ${
                  pathname === page.href
                    ? "text-accent-brand bg-accent-brand/5"
                    : "text-text-secondary hover:bg-surface-elevated hover:text-text-primary"
                }`}
              >
                <span>{page.emoji}</span>
                <span className="font-medium">{page.label}</span>
              </Link>
            ))}
          </div>
        )}
      </div>

      {tabs.slice(2).map((tab) => (
        <Link
          key={tab.href}
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
