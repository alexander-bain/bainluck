"use client";

import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { fetchCollectionWeekNavigation, lastWeekNavigation, rememberWeekNavigation, type CollectionWeekNavigation as Navigation } from "@/lib/collections";

const directions = ["previous", "next"] as const;
const GRID = "grid grid-cols-1 gap-3 sm:grid-cols-2";
const CELL = "min-w-0 rounded-card border border-surface-border bg-surface-card p-4";
const cellText = (direction: (typeof directions)[number], label: string) => <>
  <span className="block text-xs text-text-secondary">{direction === "previous" ? "Previous available week" : "Next available week"}</span>
  <span className="block text-sm font-semibold text-text-primary">{label}</span>
</>;

export function CollectionWeekLinks({ navigation, onNavigate }: { navigation: Navigation; onNavigate?: () => void }) {
  if (navigation.state === "not_applicable") return null;
  if (navigation.state === "unavailable") return <p role="status" className="text-sm text-text-secondary">Week navigation isn&apos;t available right now.</p>;
  if (!navigation.previous && !navigation.next) return null;
  return <nav aria-label="Available NFL weeks" className={GRID}>
    {directions.map((direction) => {
      const link = navigation[direction];
      return link && <Link key={direction} href={link.href} onClick={onNavigate} aria-label={`${direction === "previous" ? "Previous" : "Next"} available week: ${link.label}`} className={`${CELL} hover:bg-surface-elevated`}>
        {cellText(direction, link.label)}
      </Link>;
    })}
  </nav>;
}

// #11567: while a read is in flight, the links this week last drew hold their
// place — same grid, same cells, invisible, no links — so the games below do
// not jump when the answer draws. A week last seen without links reserves nothing.
function ReservedWeekLinks({ navigation }: { navigation: Navigation }) {
  if (navigation.state !== "available" || (!navigation.previous && !navigation.next)) return null;
  return <div aria-hidden data-week-links-reserved className={`invisible ${GRID}`}>
    {directions.map((direction) => {
      const link = navigation[direction];
      return link && <div key={direction} className={CELL}>{cellText(direction, link.label)}</div>;
    })}
  </div>;
}

export function CollectionWeekNavigation({ slug, read, onNavigate, onSettle }: { slug: string; read: number; onNavigate?: () => void; onSettle?: () => void }) {
  const [answer, setAnswer] = useState<{ read: number; navigation: Navigation } | null>(null);
  const settled = useRef(onSettle);
  settled.current = onSettle;
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 4000);
    const settle = (navigation: Navigation) => { if (active) { rememberWeekNavigation(navigation); setAnswer({ read, navigation }); } };
    void fetchCollectionWeekNavigation(slug, controller.signal).then(settle)
      .catch(() => settle({ slug, state: "unavailable", previous: null, next: null })).finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [slug, read]);
  // #11555: the links' final height is in the DOM, before paint.
  useLayoutEffect(() => { if (answer?.read === read) settled.current?.(); }, [answer, read]);
  // A refresh never draws links accepted by an earlier read. Failed metadata
  // is unknown; it cannot replace or erase the independently accepted hub.
  if (answer?.read === read && answer.navigation.slug === slug) return <CollectionWeekLinks navigation={answer.navigation} onNavigate={onNavigate} />;
  const last = lastWeekNavigation(slug);
  return last && <ReservedWeekLinks navigation={last} />;
}
