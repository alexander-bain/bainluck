"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import {
  Activity,
  BarChart3,
  ChevronDown,
  ChevronLeft,
  Database,
  FlaskConical,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
}

interface NavPillar {
  label: string;
  icon: React.ReactNode;
  items: NavItem[];
}

const PILLARS: NavPillar[] = [
  {
    label: "System Health",
    icon: <Activity className="w-4 h-4" />,
    items: [{ label: "Operations Dashboard", href: "/admin" }],
  },
  {
    label: "Data Quality",
    icon: <Database className="w-4 h-4" />,
    items: [
      { label: "Matching Review", href: "/admin/matching" },
      { label: "Source Intelligence", href: "/admin/source-intelligence" },
      { label: "Taxonomy", href: "/admin/taxonomy" },
    ],
  },
  {
    label: "Feed & Ranking",
    icon: <BarChart3 className="w-4 h-4" />,
    items: [{ label: "Discover Quality", href: "/admin/discover-quality" }],
  },
  {
    label: "Human Eval",
    icon: <FlaskConical className="w-4 h-4" />,
    items: [{ label: "Bain-in-the-Loop", href: "/admin/eval" }],
  },
  {
    label: "User Feedback",
    icon: <MessageSquare className="w-4 h-4" />,
    items: [{ label: "Bug Reports", href: "/admin/bug-reports" }],
  },
];

const COLLAPSE_KEY = "bainluck_admin_sidebar_collapsed";

export default function AdminSidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [expandedPillars, setExpandedPillars] = useState<Set<string>>(
    new Set()
  );

  useEffect(() => {
    setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "true");
  }, []);

  useEffect(() => {
    const active = PILLARS.find((p) =>
      p.items.some((i) => i.href === pathname)
    );
    if (active) {
      setExpandedPillars((prev) => new Set(prev).add(active.label));
    }
  }, [pathname]);

  const toggleCollapse = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem(COLLAPSE_KEY, String(next));
  };

  const togglePillar = (label: string) => {
    setExpandedPillars((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const isActive = (href: string) => pathname === href;
  const pillarHasActive = (p: NavPillar) =>
    p.items.some((i) => isActive(i.href));

  if (collapsed) {
    return (
      <aside className="hidden md:flex flex-col items-center w-12 shrink-0 border-r border-surface-border bg-surface-card py-4 gap-3">
        <button
          onClick={toggleCollapse}
          className="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-elevated transition-colors"
          title="Expand sidebar"
        >
          <PanelLeftOpen className="w-4 h-4" />
        </button>
        <div className="w-6 border-t border-surface-border" />
        {PILLARS.map((p) => (
          <Link
            key={p.label}
            href={p.items[0].href}
            className={`p-1.5 rounded-lg transition-colors ${
              pillarHasActive(p)
                ? "text-accent-brand bg-accent-brand/10"
                : "text-text-muted hover:text-text-secondary hover:bg-surface-elevated"
            }`}
            title={p.label}
          >
            {p.icon}
          </Link>
        ))}
      </aside>
    );
  }

  return (
    <aside className="hidden md:flex flex-col w-56 shrink-0 border-r border-surface-border bg-surface-card overflow-y-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
        <Link
          href="/admin"
          className="flex items-center gap-2 text-sm font-semibold text-text-primary"
        >
          <ChevronLeft className="w-3.5 h-3.5 text-text-muted" />
          Admin
        </Link>
        <button
          onClick={toggleCollapse}
          className="p-1 rounded-md text-text-muted hover:text-text-secondary hover:bg-surface-elevated transition-colors"
          title="Collapse sidebar"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      <nav className="flex-1 px-2 py-3 space-y-1">
        {PILLARS.map((pillar) => {
          const isExpanded = expandedPillars.has(pillar.label);
          const hasActive = pillarHasActive(pillar);
          const singleItem = pillar.items.length === 1;

          if (singleItem) {
            const item = pillar.items[0];
            return (
              <Link
                key={pillar.label}
                href={item.href}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                  isActive(item.href)
                    ? "text-accent-brand bg-accent-brand/10"
                    : "text-text-secondary hover:text-text-primary hover:bg-surface-elevated"
                }`}
              >
                <span
                  className={
                    isActive(item.href)
                      ? "text-accent-brand"
                      : "text-text-muted"
                  }
                >
                  {pillar.icon}
                </span>
                {pillar.label}
              </Link>
            );
          }

          return (
            <div key={pillar.label}>
              <button
                onClick={() => togglePillar(pillar.label)}
                className={`w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                  hasActive
                    ? "text-accent-brand"
                    : "text-text-secondary hover:text-text-primary hover:bg-surface-elevated"
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <span
                    className={
                      hasActive ? "text-accent-brand" : "text-text-muted"
                    }
                  >
                    {pillar.icon}
                  </span>
                  {pillar.label}
                </span>
                <ChevronDown
                  className={`w-3 h-3 text-text-muted transition-transform ${
                    isExpanded ? "rotate-180" : ""
                  }`}
                />
              </button>
              {isExpanded && (
                <div className="ml-4 pl-3 border-l border-surface-border space-y-0.5 mt-0.5">
                  {pillar.items.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`block px-3 py-1.5 rounded-md text-xs transition-colors ${
                        isActive(item.href)
                          ? "text-accent-brand font-medium bg-accent-brand/5"
                          : "text-text-muted hover:text-text-secondary hover:bg-surface-elevated"
                      }`}
                    >
                      {item.label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        <div className="mt-4 pt-3 border-t border-surface-border">
          <Link
            href="/admin/story"
            className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-accent-brand hover:bg-accent-brand/5 transition-colors"
          >
            <Play className="w-4 h-4" />
            Pipeline Walkthrough
          </Link>
        </div>
      </nav>
    </aside>
  );
}
