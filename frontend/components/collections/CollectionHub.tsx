"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { CollectionMemberCard } from "./CollectionMemberCard";
import {
  collectionMemberDomId, collectionRefreshInterval, fetchCollection, reconcileCollectionContext,
  type CollectionHub as Hub, type CollectionMember, type CollectionReadingContext,
} from "@/lib/collections";

const storageKey = (slug: string) => `collection-reading:${slug}`;

export default function CollectionHub({ slug }: { slug: string }) {
  const [hub, setHub] = useState<Hub | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetching, setFetching] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const request = useRef<AbortController | null>(null);
  const restored = useRef(false);

  const load = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setFetching(true);
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    try {
      const fresh = await fetchCollection(slug, controller.signal);
      if (request.current !== controller) return;
      setHub(fresh); setError(null);
    } catch {
      if (request.current !== controller) return;
      // A failed read is unavailable, not a fresh empty collection. Do not
      // keep a formerly published inventory after a failed publication read.
      setHub(null); setError("Couldn't load this collection. Please try again.");
    } finally {
      window.clearTimeout(timeout);
      if (request.current === controller) setFetching(false);
    }
  }, [slug]);

  useEffect(() => {
    restored.current = false;
    setHub(null); setExpanded(new Set());
    void load();
    const freshRead = () => { if (document.visibilityState !== "hidden") void load(); };
    window.addEventListener("focus", freshRead);
    window.addEventListener("pageshow", freshRead);
    return () => { request.current?.abort(); request.current = null; window.removeEventListener("focus", freshRead); window.removeEventListener("pageshow", freshRead); };
  }, [load]);

  const interval = collectionRefreshInterval(hub);
  useEffect(() => {
    if (!interval) return;
    const timer = window.setInterval(() => { if (document.visibilityState !== "hidden") void load(); }, interval);
    return () => window.clearInterval(timer);
  }, [interval, load]);

  useEffect(() => {
    if (!hub || restored.current) return;
    restored.current = true;
    let context: CollectionReadingContext | null = null;
    try { context = reconcileCollectionContext(JSON.parse(sessionStorage.getItem(storageKey(slug)) ?? "null"), hub); } catch { /* blocked/corrupt storage never stops browsing */ }
    if (!context) return;
    setExpanded(new Set(context.expanded));
    const frame = requestAnimationFrame(() => {
      if (!context?.memberKey) return;
      const element = document.getElementById(collectionMemberDomId(context.memberKey));
      if (element) window.scrollTo({ top: Math.max(0, window.scrollY + element.getBoundingClientRect().top - context.offset), behavior: "instant" });
    });
    return () => cancelAnimationFrame(frame);
  }, [hub, slug]);

  const remember = (key: string) => {
    const element = document.getElementById(collectionMemberDomId(key));
    const context: CollectionReadingContext = { slug, memberKey: key, offset: element?.getBoundingClientRect().top ?? 0, expanded: [...expanded] };
    try { sessionStorage.setItem(storageKey(slug), JSON.stringify(context)); } catch { /* browser Back remains available without storage */ }
  };

  const card = (member: CollectionMember) => <div id={collectionMemberDomId(member.key)} key={member.key} data-collection-member={member.key} onClickCapture={(event) => {
    const anchor = (event.target as Element).closest("a");
    if (anchor?.getAttribute("href") === member.href) remember(member.key);
  }}><CollectionMemberCard member={member} /></div>;

  return <div className="mx-auto w-full max-w-4xl space-y-6" data-collection-hub={slug}>
    <div className="flex items-center justify-between gap-4">
      <Link href="/discover" className="text-sm text-text-secondary hover:text-text-primary">Back to Discover</Link>
      <button type="button" disabled={fetching} onClick={() => void load()} className="text-sm text-accent-brand hover:underline disabled:text-text-muted">{fetching && hub ? "Updating…" : "Refresh"}</button>
    </div>
    <header className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Collection</p>
      <h1 className="text-2xl font-bold text-text-primary">{hub?.title ?? "Collection"}</h1>
      {hub?.edition && <p className="text-sm text-text-secondary">{hub.edition}</p>}
    </header>
    {fetching && !hub && !error && <p role="status" className="py-8 text-text-secondary">Loading collection…</p>}
    {error && <div role="status" className="rounded-card border border-surface-border bg-surface-card p-5 space-y-3">
      <p className="text-text-secondary">{error}</p>
      <button type="button" onClick={() => void load()} className="text-accent-brand hover:underline">Try again</button>
    </div>}
    {hub?.note && <p role="status" className="text-sm text-text-secondary">{hub.note}</p>}
    {hub?.children.map((child) => <Link key={child.key} id={collectionMemberDomId(child.key)} href={child.href} onClick={() => remember(child.key)} className="flex justify-between gap-4 rounded-card border border-surface-border bg-surface-card p-4 font-semibold text-text-primary hover:bg-surface-elevated">{child.name}<span aria-hidden>›</span></Link>)}
    {hub?.sections.map((section) => <section key={section.key} className="space-y-3" aria-labelledby={`section-${section.key}`}>
      <h2 id={`section-${section.key}`} className="text-lg font-semibold text-text-primary">{section.title}</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-start">
        {section.members.map((member) => <div key={member.key} className="min-w-0 space-y-3">
          {card(member)}
          {!!hub.related[member.key]?.length && <details open={expanded.has(member.key)} onToggle={(event) => {
            const open = event.currentTarget.open;
            setExpanded((previous) => { const next = new Set(previous); if (open) next.add(member.key); else next.delete(member.key); return next; });
          }} className="rounded-card border border-surface-border bg-surface-card p-3">
            <summary className="cursor-pointer text-sm font-semibold text-text-secondary">Related questions ({hub.related[member.key].length})</summary>
            <div className="mt-3 space-y-3">{hub.related[member.key].map(card)}</div>
          </details>}
        </div>)}
      </div>
    </section>)}
  </div>;
}
