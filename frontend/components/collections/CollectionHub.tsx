"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { CollectionMemberCard } from "./CollectionMemberCard";
import {
  acceptedCollection, collectionMemberDomId, collectionReadAdmitted, collectionRefreshInterval, fetchCollection, openCollectionRead, reconcileCollectionContext,
  settleCollectionPage, settleCollectionRead,
  type CollectionHub as Hub, type CollectionMember, type CollectionPageRequest, type CollectionReadingContext,
} from "@/lib/collections";

const storageKey = (slug: string) => `collection-reading:${slug}`;

export default function CollectionHub({ slug }: { slug: string }) {
  const [hub, setHub] = useState<Hub | null>(() => acceptedCollection(slug));
  const [error, setError] = useState<string | null>(null);
  const [fetching, setFetching] = useState(true);
  const [paging, setPaging] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const pageRequest = useRef<AbortController | null>(null);
  const latest = useRef<Hub | null>(hub);
  const restored = useRef(false);

  const load = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const ticket = openCollectionRead();
    setFetching(true);
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    try {
      const fresh = await fetchCollection(slug, controller.signal);
      if (request.current !== controller || !collectionReadAdmitted(slug, ticket)) return;
      const next = settleCollectionRead(slug, { hub: fresh });
      latest.current = next.hub?.slug === slug ? next.hub : null;
      setHub(next.hub); setError(next.error);
    } catch {
      if (request.current !== controller || !collectionReadAdmitted(slug, ticket)) return;
      // A failed read is not a withdrawal: keep this slug's last accepted hub
      // (with an honest error) or, with none, show the error alone.
      const next = settleCollectionRead(slug, { failed: true });
      latest.current = next.hub?.slug === slug ? next.hub : null;
      setHub(next.hub); setError(next.error);
    } finally {
      window.clearTimeout(timeout);
      if (request.current === controller) setFetching(false);
    }
  }, [slug]);

  useEffect(() => {
    restored.current = false;
    setHub(acceptedCollection(slug)); setError(null); setPageError(null); setPaging(false);
    void load();
    const freshRead = () => { if (document.visibilityState !== "hidden") void load(); };
    window.addEventListener("focus", freshRead);
    window.addEventListener("pageshow", freshRead);
    return () => {
      request.current?.abort(); request.current = null; pageRequest.current?.abort(); pageRequest.current = null;
      window.removeEventListener("focus", freshRead); window.removeEventListener("pageshow", freshRead);
    };
  }, [load]);

  // Never draw another slug's hub, even for the frame before the reset effect.
  const shown = hub?.slug === slug ? hub : null;
  latest.current = shown;

  // #9925: one more page of a theme collection, only when the reader asks.
  const loadMore = async () => {
    const base = latest.current;
    if (!base?.theme?.nextCursor || base.revision === null || pageRequest.current) return;
    const requested: CollectionPageRequest = { revision: base.revision, cursor: base.theme.nextCursor };
    const controller = new AbortController();
    pageRequest.current = controller;
    const ticket = openCollectionRead();
    setPaging(true); setPageError(null);
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    try {
      const page = await fetchCollection(slug, controller.signal, requested);
      if (pageRequest.current !== controller || !latest.current || !collectionReadAdmitted(slug, ticket)) return;
      // Settled state is current at once, not at the next render: a second
      // answer in the same interval is admitted against it.
      const settled = settleCollectionPage(slug, latest.current, requested, page);
      latest.current = settled;
      setHub(settled); setError(null);
    } catch {
      // A failed page leaves every loaded question where it is.
      if (pageRequest.current === controller) setPageError("Couldn't load more questions. Please try again.");
    } finally {
      window.clearTimeout(timeout);
      if (pageRequest.current === controller) { pageRequest.current = null; setPaging(false); }
    }
  };
  const interval = collectionRefreshInterval(shown);
  useEffect(() => {
    if (!interval) return;
    const timer = window.setInterval(() => { if (document.visibilityState !== "hidden") void load(); }, interval);
    return () => window.clearInterval(timer);
  }, [interval, load]);

  useEffect(() => {
    if (!shown || restored.current) return;
    restored.current = true;
    let context: CollectionReadingContext | null = null;
    try { context = reconcileCollectionContext(JSON.parse(sessionStorage.getItem(storageKey(slug)) ?? "null"), shown); } catch { /* blocked/corrupt storage never stops browsing */ }
    // No disclosures to reopen since #10146, so the drawn layout is the one the reader left (#9982).
    const element = context?.memberKey ? document.getElementById(collectionMemberDomId(context.memberKey)) : null;
    if (context && element) window.scrollTo({ top: Math.max(0, window.scrollY + element.getBoundingClientRect().top - context.offset), behavior: "instant" });
  }, [shown, slug]);

  const remember = (key: string) => {
    const element = document.getElementById(collectionMemberDomId(key));
    const context: CollectionReadingContext = { slug, memberKey: key, offset: element?.getBoundingClientRect().top ?? 0, expanded: [] };
    try { sessionStorage.setItem(storageKey(slug), JSON.stringify(context)); } catch { /* browser Back remains available without storage */ }
  };

  const card = (member: CollectionMember) => <div id={collectionMemberDomId(member.key)} key={member.key} data-collection-member={member.key} onClickCapture={(event) => {
    const anchor = (event.target as Element).closest("a");
    if (anchor?.getAttribute("href") === member.href) remember(member.key);
  }}><CollectionMemberCard member={member} /></div>;

  return <div className="mx-auto w-full max-w-4xl space-y-6" data-collection-hub={slug}>
    <div className="flex items-center justify-between gap-4">
      <Link href="/discover" className="text-sm text-text-secondary hover:text-text-primary">Back to Discover</Link>
      <button type="button" disabled={fetching} onClick={() => void load()} className="text-sm text-accent-brand hover:underline disabled:text-text-muted">{fetching && shown ? "Updating…" : "Refresh"}</button>
    </div>
    <header className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Collection</p>
      <h1 className="text-2xl font-bold text-text-primary">{shown?.title ?? "Collection"}</h1>
      {shown?.edition && <p className="text-sm text-text-secondary">{shown.edition}</p>}
    </header>
    {fetching && !shown && !error && <p role="status" className="py-8 text-text-secondary">Loading collection…</p>}
    {error && shown && <div role="status" className="sticky top-16 z-40 flex items-center justify-between gap-3 rounded-card border border-surface-border bg-surface-card px-4 py-2 text-sm shadow-sm">
      <p className="text-text-secondary">{error}</p>
      <button type="button" disabled={fetching} onClick={() => void load()} className="shrink-0 text-accent-brand hover:underline disabled:text-text-muted">Try again</button>
    </div>}
    {error && !shown && <div role="status" className="rounded-card border border-surface-border bg-surface-card p-5 space-y-3">
      <p className="text-text-secondary">{error}</p>
      <button type="button" onClick={() => void load()} className="text-accent-brand hover:underline">Try again</button>
    </div>}
    {shown?.note && <p role="status" className="text-sm text-text-secondary">{shown.note}</p>}
    {shown?.theme && !shown.theme.inventoryComplete && <p className="text-sm text-text-secondary">This list may not include every question yet.</p>}
    {shown?.children.map((child) => <Link key={child.key} id={collectionMemberDomId(child.key)} href={child.href} onClick={() => remember(child.key)} className="flex justify-between gap-4 rounded-card border border-surface-border bg-surface-card p-4 font-semibold text-text-primary hover:bg-surface-elevated">{child.name}<span aria-hidden>›</span></Link>)}
    {shown?.sections.map((section) => <section key={section.key} className="space-y-3" aria-labelledby={`section-${section.key}`}>
      <h2 id={`section-${section.key}`} className="text-lg font-semibold text-text-primary">{section.title}</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-start">
        {section.members.map((member) => <div key={member.key} className="min-w-0 space-y-3">
          {card(member)}
          {/* #10146: a game's questions open deliberately on its own page, never as hundreds of contracts inline. */}
          {!!shown.related[member.key]?.length && <Link href={member.href} data-more-on-game={member.key} onClick={() => remember(member.key)} className="flex justify-between gap-4 rounded-card border border-surface-border bg-surface-card px-4 py-2.5 text-sm font-semibold text-text-secondary hover:bg-surface-elevated hover:text-text-primary">More on this game<span aria-hidden>›</span></Link>}
        </div>)}
      </div>
    </section>)}
    {shown?.theme && shown.members.length > 0 && <div className="flex flex-col items-center gap-2 pb-6" data-collection-pager={shown.revision ?? ""}>
      <p className="text-sm text-text-secondary">{shown.members.length} of {Math.max(shown.theme.totalCount, shown.members.length)} questions</p>
      {shown.theme.nextCursor && <button type="button" disabled={paging} onClick={() => void loadMore()} className="rounded-card border border-surface-border bg-surface-card px-4 py-2 text-sm font-semibold text-text-primary hover:bg-surface-elevated disabled:text-text-muted">{paging ? "Loading…" : "Load more"}</button>}
      {pageError && <p role="status" className="text-sm text-text-secondary">{pageError}</p>}
    </div>}
  </div>;
}
