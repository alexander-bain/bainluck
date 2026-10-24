"use client";

import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { fetchCollectionWeekNavigation, type CollectionWeekNavigation as Navigation } from "@/lib/collections";

export function CollectionWeekLinks({ navigation, onNavigate }: { navigation: Navigation; onNavigate?: () => void }) {
  if (navigation.state === "not_applicable") return null;
  if (navigation.state === "unavailable") return <p role="status" className="text-sm text-text-secondary">Week navigation isn&apos;t available right now.</p>;
  if (!navigation.previous && !navigation.next) return null;
  return <nav aria-label="Available NFL weeks" className="grid grid-cols-1 gap-3 sm:grid-cols-2">
    {(["previous", "next"] as const).map((direction) => {
      const link = navigation[direction];
      return link && <Link key={direction} href={link.href} onClick={onNavigate} aria-label={`${direction === "previous" ? "Previous" : "Next"} available week: ${link.label}`} className="min-w-0 rounded-card border border-surface-border bg-surface-card p-4 hover:bg-surface-elevated">
        <span className="block text-xs text-text-secondary">{direction === "previous" ? "Previous available week" : "Next available week"}</span>
        <span className="block text-sm font-semibold text-text-primary">{link.label}</span>
      </Link>;
    })}
  </nav>;
}

export function CollectionWeekNavigation({ slug, read, onNavigate, onSettle }: { slug: string; read: number; onNavigate?: () => void; onSettle?: () => void }) {
  const [answer, setAnswer] = useState<{ read: number; navigation: Navigation } | null>(null);
  const settled = useRef(onSettle);
  settled.current = onSettle;
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 4000);
    void fetchCollectionWeekNavigation(slug, controller.signal).then((navigation) => {
      if (active) setAnswer({ read, navigation });
    }).catch(() => {
      if (active) setAnswer({ read, navigation: { slug, state: "unavailable", previous: null, next: null } });
    }).finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [slug, read]);
  // #11555: the links' final height is in the DOM, before paint.
  useLayoutEffect(() => { if (answer?.read === read) settled.current?.(); }, [answer, read]);
  // A refresh never draws links accepted by an earlier read. Failed metadata
  // is unknown; it cannot replace or erase the independently accepted hub.
  return answer?.read === read && answer.navigation.slug === slug ? <CollectionWeekLinks navigation={answer.navigation} onNavigate={onNavigate} /> : null;
}
