"use client";

import { useState } from "react";
import { useAnalyticsContext } from "@/components/Analytics";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";

const MobileSearchOverlay = dynamic(() => import("./MobileSearchOverlay"), { ssr: false });

export default function MobileSearchTrigger() {
  const [searchOpen, setSearchOpen] = useState(false);
  const { track } = useAnalyticsContext();
  const pathname = usePathname();

  return (
    <>
      <button
        onClick={() => {
          setSearchOpen(true);
          track("navigation_click", {
            click_type: "nav_tab" as const,
            from_page: pathname || "/",
            to_page: "/search",
          });
        }}
        aria-label="Open search" className="flex items-center gap-2 w-full bg-surface-elevated/80 rounded-full px-3 py-1.5 text-sm text-text-muted transition-colors active:bg-surface-elevated"
      >
        <svg
          aria-hidden="true"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="flex-shrink-0 opacity-60"
        >
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <span className="truncate">Search...</span>
      </button>
      <MobileSearchOverlay isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
    </>
  );
}
