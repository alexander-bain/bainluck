/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import AwardCategoryPairedCard from "@/components/discover/forms/AwardCategoryPairedCard";
import EventCard183A, { buildUnifiedCardFromEvent } from "@/components/EventCard183A";
import type {
  CollectionMember,
  MachineryOutcomeVisual,
  MachinerySubjectArt,
  MachineryVisualBlock,
} from "@/lib/collections";
import type { Event } from "@/lib/types";

export function isMachinerySlice1Enabled(): boolean {
  return process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1 === "true";
}

export interface MachineryCardContract {
  slug: string;
  form_id: string;
  kicker: string;
  title: string;
  subtitle: string;
  footer: string;
  section_count: number;
  destination_href: string;
  rows: Record<string, unknown>[];
}

function SubjectAvatar({
  art,
  label,
  sizeClass = "h-9 w-9",
  poster = false,
}: {
  art?: MachinerySubjectArt | null;
  label: string;
  sizeClass?: string;
  poster?: boolean;
}) {
  const url = art?.url;
  const kind = art?.kind ?? "monogram";
  const isLogo = kind === "team_logo";
  const shapeClass = poster ? "rounded-md" : "rounded-full";
  if (url) {
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center overflow-hidden border border-surface-border bg-surface-elevated ${shapeClass} ${sizeClass}`}
      >
        <img
          src={url}
          alt={label}
          className={isLogo ? "h-4/5 w-4/5 object-contain" : "h-full w-full object-cover object-top"}
        />
      </span>
    );
  }
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center border border-surface-border bg-surface-elevated font-semibold text-xs text-text-primary ${shapeClass} ${sizeClass}`}
    >
      {art?.initials || label.slice(0, 2).toUpperCase()}
    </span>
  );
}

function formatShortKickoff(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function CoinFlipMatchupsBlock({ items }: { items: Record<string, unknown>[] }) {
  return (
    <div className="grid grid-cols-1 gap-2.5" data-machinery-form="coin_flip_matchups">
      {items.map((raw) => {
        const eid = Number(raw.event_id ?? 0);
        const awayShort = String(raw.away_short ?? raw.away_team ?? "");
        const homeShort = String(raw.home_short ?? raw.home_team ?? "");
        const awayPct = Number(raw.away_pct ?? 50);
        const homePct = Number(raw.home_pct ?? 50);
        const awayArt = raw.away_art as MachinerySubjectArt | undefined;
        const homeArt = raw.home_art as MachinerySubjectArt | undefined;
        const when = formatShortKickoff(String(raw.commence_time ?? ""));
        return (
          <Link
            key={eid}
            href={`/events/${eid}`}
            className="block rounded-card border border-surface-border bg-surface-card p-3 transition-colors hover:bg-surface-elevated"
          >
            <div className="mb-2 flex items-center justify-between text-xs text-text-muted">
              <span className="font-semibold uppercase tracking-wide text-accent-brand">Toss-up</span>
              <span>{when}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <SubjectAvatar art={awayArt} label={awayShort} sizeClass="h-8 w-8" />
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-text-primary">{awayShort}</div>
                  <div className="text-xs font-bold tabular-nums text-text-secondary">{awayPct}%</div>
                </div>
              </div>
              <span className="text-xs font-medium text-text-muted">at</span>
              <div className="flex min-w-0 items-center gap-2 text-right">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-text-primary">{homeShort}</div>
                  <div className="text-xs font-bold tabular-nums text-text-secondary">{homePct}%</div>
                </div>
                <SubjectAvatar art={homeArt} label={homeShort} sizeClass="h-8 w-8" />
              </div>
            </div>
            <div className="mt-2.5 flex h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
              <div
                className="h-full bg-accent-brand transition-all"
                style={{
                  width: `${Math.max(8, Math.min(92, awayPct))}%`,
                  backgroundColor: awayArt?.accent_color || undefined,
                }}
              />
              <div
                className="h-full flex-1 bg-slate-400 transition-all"
                style={{ backgroundColor: homeArt?.accent_color || undefined }}
              />
            </div>
          </Link>
        );
      })}
    </div>
  );
}

function MatchupSlateBlock({ members }: { members: CollectionMember[] }) {
  return (
    <div className="grid grid-cols-1 gap-3" data-machinery-form="matchup_slate">
      {members
        .filter((m) => m.type === "event")
        .map((m) => (
          <EventCard183A
            key={m.key}
            card={buildUnifiedCardFromEvent(m.item.data as unknown as Event)}
            surface="standard"
          />
        ))}
    </div>
  );
}

function DuelBarBlock({ items }: { items: Record<string, unknown>[] }) {
  const lead = items[0];
  if (!lead) return null;
  const outcomes = (lead.outcomes as MachineryOutcomeVisual[] | undefined) ?? [];
  if (outcomes.length < 2) return null;
  const left = outcomes[0];
  const right = outcomes[1];
  const href = String(lead.href ?? "/discover");
  return (
    <Link
      href={href}
      data-machinery-form="duel_bar"
      className="block rounded-card border border-surface-border bg-surface-card p-4 transition-colors hover:bg-surface-elevated"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          {left.art?.url ? (
            <SubjectAvatar art={left.art} label={left.name} sizeClass="h-10 w-10" />
          ) : null}
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-sm font-semibold text-text-primary">
              {!left.art?.url && (
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full bg-accent-brand"
                  style={{ backgroundColor: left.art?.accent_color || undefined }}
                />
              )}
              <span>{left.name}</span>
            </div>
            <div className="text-xl font-extrabold tabular-nums text-text-primary">
              {left.rendered_percent}%
            </div>
          </div>
        </div>
        <div className="flex min-w-0 items-center gap-2.5 text-right">
          <div className="min-w-0">
            <div className="flex items-center justify-end gap-1.5 text-sm font-semibold text-text-primary">
              <span>{right.name}</span>
              {!right.art?.url && (
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full bg-slate-400"
                  style={{ backgroundColor: right.art?.accent_color || undefined }}
                />
              )}
            </div>
            <div className="text-xl font-extrabold tabular-nums text-text-primary">
              {right.rendered_percent}%
            </div>
          </div>
          {right.art?.url ? (
            <SubjectAvatar art={right.art} label={right.name} sizeClass="h-10 w-10" />
          ) : null}
        </div>
      </div>
      <div className="mt-3 flex h-3 w-full overflow-hidden rounded-full bg-surface-elevated">
        <div
          className="h-full bg-accent-brand"
          style={{
            width: `${Math.max(6, Math.min(94, left.rendered_percent))}%`,
            backgroundColor: left.art?.accent_color || undefined,
          }}
        />
        <div
          className="h-full flex-1 bg-slate-400"
          style={{ backgroundColor: right.art?.accent_color || undefined }}
        />
      </div>
    </Link>
  );
}

function ContenderSpotlightBlock({ items }: { items: Record<string, unknown>[] }) {
  const lead = items[0];
  if (!lead) return null;
  const outcomes = (lead.outcomes as MachineryOutcomeVisual[] | undefined) ?? [];
  const href = String(lead.href ?? "/discover");
  const topThree = outcomes.slice(0, 3);
  const chasers = outcomes.slice(3);

  return (
    <div className="space-y-2.5" data-machinery-form="contender_spotlight">
      <div className="grid grid-cols-3 gap-2">
        {topThree.map((o, idx) => {
          const isPoster = o.art?.kind === "tmdb_poster";
          return (
            <Link
              key={o.outcome_id}
              href={href}
              className="flex flex-col items-center rounded-card border border-surface-border bg-surface-card p-2.5 text-center transition-colors hover:bg-surface-elevated"
            >
              <div className="mb-1.5 flex w-full items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                <span>#{idx + 1}</span>
                <span className="text-sm font-extrabold tabular-nums text-text-primary">
                  {o.rendered_percent}%
                </span>
              </div>
              <SubjectAvatar
                art={o.art}
                label={o.name}
                sizeClass={isPoster ? "h-16 w-11" : "h-12 w-12"}
                poster={isPoster}
              />
              <div className="mt-2 line-clamp-2 text-xs font-semibold leading-tight text-text-primary">
                {o.name}
              </div>
              {o.art?.detail && (
                <div className="mt-0.5 line-clamp-1 text-[10px] text-text-muted">{o.art.detail}</div>
              )}
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated">
                <div
                  className="h-full rounded-full bg-accent-brand"
                  style={{
                    width: `${Math.max(6, Math.min(100, o.rendered_percent))}%`,
                    backgroundColor: o.art?.accent_color || undefined,
                  }}
                />
              </div>
            </Link>
          );
        })}
      </div>

      {chasers.length > 0 && (
        <div className="divide-y divide-surface-border rounded-card border border-surface-border bg-surface-card">
          {chasers.map((o) => (
            <Link
              key={o.outcome_id}
              href={href}
              className="relative flex items-center justify-between gap-3 overflow-hidden px-3 py-2 transition-colors hover:bg-surface-elevated"
            >
              <div
                className="pointer-events-none absolute inset-y-0 left-0 bg-surface-elevated/80"
                style={{ width: `${Math.max(4, Math.min(100, o.rendered_percent))}%` }}
              />
              <div className="relative flex min-w-0 items-center gap-2.5">
                <SubjectAvatar art={o.art} label={o.name} sizeClass="h-8 w-8" />
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-text-primary">{o.name}</div>
                  {o.art?.detail && (
                    <div className="truncate text-[11px] text-text-muted">{o.art.detail}</div>
                  )}
                </div>
              </div>
              <span className="relative text-sm font-bold tabular-nums text-text-primary">
                {o.rendered_percent}%
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function SiblingFieldsGridBlock({ items }: { items: Record<string, unknown>[] }) {
  return (
    <div className="grid grid-cols-1 gap-3" data-machinery-form="sibling_fields_grid">
      {items.map((m) => {
        const mid = Number(m.market_id ?? 0);
        const title = String(m.title ?? "");
        const href = String(m.href ?? `/futures/${mid}`);
        const outcomes = ((m.outcomes as MachineryOutcomeVisual[] | undefined) ?? []).slice(0, 4);
        return (
          <Link
            key={mid}
            href={href}
            className="block rounded-card border border-surface-border bg-surface-card p-3.5 transition-colors hover:bg-surface-elevated"
          >
            <div className="mb-2.5 flex items-center justify-between gap-2">
              <h3 className="text-sm font-bold text-text-primary">{title}</h3>
              <span className="text-xs text-text-muted" aria-hidden="true">
                ›
              </span>
            </div>
            <div className="space-y-2">
              {outcomes.map((o) => {
                const isPoster = o.art?.kind === "tmdb_poster";
                return (
                  <div key={o.outcome_id} className="flex items-center gap-2.5">
                    <SubjectAvatar
                      art={o.art}
                      label={o.name}
                      sizeClass={isPoster ? "h-9 w-7" : "h-7 w-7"}
                      poster={isPoster}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-xs font-medium text-text-primary">
                          {o.name}
                        </span>
                        <span className="text-xs font-bold tabular-nums text-text-primary">
                          {o.rendered_percent}%
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated">
                        <div
                          className="h-full rounded-full bg-accent-brand"
                          style={{
                            width: `${Math.max(4, Math.min(100, o.rendered_percent))}%`,
                            backgroundColor: o.art?.accent_color || undefined,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Link>
        );
      })}
    </div>
  );
}

function BenchmarkStripBlock({ items }: { items: Record<string, unknown>[] }) {
  return (
    <div
      className="divide-y divide-surface-border rounded-card border border-surface-border bg-surface-card"
      data-machinery-form="benchmark_strip"
    >
      {items.map((m) => {
        const mid = Number(m.market_id ?? 0);
        const title = String(m.title ?? "");
        const href = String(m.href ?? `/futures/${mid}`);
        const outcomes = (m.outcomes as MachineryOutcomeVisual[] | undefined) ?? [];
        const yes = outcomes[0];
        if (!yes) return null;
        return (
          <Link
            key={mid}
            href={href}
            className="flex items-center justify-between gap-3 px-3.5 py-2.5 transition-colors hover:bg-surface-elevated"
          >
            <div className="flex min-w-0 items-center gap-2.5">
              <SubjectAvatar art={yes.art} label={title} sizeClass="h-7 w-7" />
              <span className="line-clamp-2 text-xs font-medium text-text-primary">{title}</span>
            </div>
            <span className="shrink-0 rounded-md bg-surface-elevated px-2 py-1 text-xs font-bold tabular-nums text-text-primary">
              {yes.rendered_percent}%
            </span>
          </Link>
        );
      })}
    </div>
  );
}

export default function MachinerySectionRenderer({
  visualBlock,
  members,
}: {
  visualBlock: MachineryVisualBlock;
  members: CollectionMember[];
}) {
  const { form_id, paired_metric_set, items = [] } = visualBlock;
  if (form_id === "paired_stage_bars" && paired_metric_set) {
    return (
      <div data-machinery-form="paired_stage_bars">
        <AwardCategoryPairedCard set={paired_metric_set} surface="collection" defaultExpanded />
      </div>
    );
  }
  if (form_id === "coin_flip_matchups") {
    return <CoinFlipMatchupsBlock items={items} />;
  }
  if (form_id === "matchup_slate") {
    return <MatchupSlateBlock members={members} />;
  }
  if (form_id === "duel_bar") {
    return <DuelBarBlock items={items} />;
  }
  if (form_id === "contender_spotlight") {
    return <ContenderSpotlightBlock items={items} />;
  }
  if (form_id === "benchmark_strip") {
    return <BenchmarkStripBlock items={items} />;
  }
  return <SiblingFieldsGridBlock items={items} />;
}

export function MachineryDiscoverCard({ card }: { card: MachineryCardContract }) {
  const isEventCard =
    card.form_id === "coin_flip_matchups" || card.form_id === "matchup_slate";
  return (
    <Link
      href={card.destination_href}
      data-testid="machinery-discover-card"
      data-machinery-card-form={card.form_id}
      className="block rounded-card border border-surface-border bg-surface-card p-4 transition-colors hover:bg-surface-elevated"
    >
      <div className="mb-1 text-[11px] font-bold uppercase tracking-wider text-accent-brand">
        {card.kicker}
      </div>
      <h3 className="text-base font-bold leading-snug text-text-primary">{card.title}</h3>
      {card.subtitle && (
        <p className="mt-0.5 text-xs text-text-secondary">{card.subtitle}</p>
      )}

      <div className="mt-3 divide-y divide-surface-border">
        {isEventCard
          ? card.rows.map((r) => {
              const eid = Number(r.event_id ?? 0);
              const awayShort = String(r.away_short ?? "");
              const homeShort = String(r.home_short ?? "");
              const awayPct = Number(r.away_pct ?? 50);
              const homePct = Number(r.home_pct ?? 50);
              const awayArt = r.away_art as MachinerySubjectArt | undefined;
              const homeArt = r.home_art as MachinerySubjectArt | undefined;
              return (
                <div key={eid} className="flex items-center justify-between gap-2 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <SubjectAvatar art={awayArt} label={awayShort} sizeClass="h-7 w-7" />
                    <span className="text-xs font-semibold text-text-primary">{awayShort}</span>
                    <span className="text-[11px] text-text-muted">at</span>
                    <SubjectAvatar art={homeArt} label={homeShort} sizeClass="h-7 w-7" />
                    <span className="text-xs font-semibold text-text-primary">{homeShort}</span>
                  </div>
                  <span className="shrink-0 text-xs font-bold tabular-nums text-text-primary">
                    {awayPct}%–{homePct}%
                  </span>
                </div>
              );
            })
          : card.rows.map((r) => {
              const oid = Number(r.outcome_id ?? 0);
              const name = String(r.name ?? "");
              const pct = Number(r.rendered_percent ?? 0);
              const art = r.art as MachinerySubjectArt | undefined;
              return (
                <div key={oid} className="flex items-center gap-2.5 py-2">
                  <SubjectAvatar art={art} label={name} sizeClass="h-8 w-8" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-medium text-text-primary">{name}</span>
                      <span className="text-sm font-bold tabular-nums text-text-primary">
                        {pct}%
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated">
                      <div
                        className="h-full rounded-full bg-accent-brand"
                        style={{
                          width: `${Math.max(4, Math.min(100, pct))}%`,
                          backgroundColor: art?.accent_color || undefined,
                        }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
      </div>

      <div className="mt-3 flex flex-col gap-1 border-t border-surface-border pt-2.5 text-xs text-text-secondary">
        <span>{card.footer}</span>
        <span className="font-semibold text-accent-brand">
          Open all {card.section_count} sections ›
        </span>
      </div>
    </Link>
  );
}
