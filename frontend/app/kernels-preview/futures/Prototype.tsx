"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, CheckCircle2, XCircle, ChevronDown, Info, X } from "lucide-react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import type { FuturesOutcome } from "@/lib/types";
import AtlasJourney, { Chance, SourceMark } from "./AtlasJourney";
import { bodyKind, CASES, datePT, observations, openingFor, payloadVerdict, percentText, rankedOutcomes, snowThreshold, validProbability, type Observation, type PrototypeData, type StudyState } from "./_model";
import styles from "./prototype.module.css";

type Verdict = "won" | "lost" | null;
type Sheet = "details" | "field" | null;
const BLUE = "var(--series-1)";
const TEAL = "rgb(var(--color-source-mlb))";
const COLORS = [BLUE, TEAL, "var(--series-4)"];
const attribution = (sources: string[]) => sources.map((s) => ({ kalshi: "Kalshi", polymarket: "Polymarket" }[s] ?? s)).join(" · ");

function Result({ verdict }: { verdict: Exclude<Verdict, null> }) {
  const Icon = verdict === "won" ? CheckCircle2 : XCircle;
  return <span className={`${styles.result} ${verdict === "lost" ? styles.lost : ""}`}><Icon size={17} strokeWidth={1.6} />{verdict === "won" ? "Won" : "Lost"}<SourceMark /></span>;
}
function MarkKey() {
  return <div className={styles.markKey}><span><i className={styles.hollowKey} />Opening</span><span><i className={styles.solidKey} />Recorded</span><span>Connector · change in points</span></div>;
}
function Movement({ opening, recorded, color, name }: { opening: number | null; recorded: number | null; color: string; name: string }) {
  const x = (p: number) => 5 + p * 90;
  return <svg className={styles.movement} viewBox="0 0 100 20" role="img" aria-label={`${name}. Opening ${opening == null ? "unavailable" : percentText(opening)}. Recorded ${recorded == null ? "unavailable" : percentText(recorded)}.`} style={{ "--identity": color } as CSSProperties}>
    <line x1="5" x2="95" y1="10" y2="10" className={styles.railTrack} />
    {opening != null && recorded != null && <line x1={x(opening)} x2={x(recorded)} y1="10" y2="10" className={styles.railChange} />}
    {opening != null && <circle cx={x(opening)} cy="10" r="3.5" className={styles.openingDot} />}
    {recorded != null && <circle cx={x(recorded)} cy="10" r="3.5" className={styles.recordedDot} />}
  </svg>;
}

// Adapted from the atlas's binary-side-comparison study. Values are independent;
// selecting the other named side never manufactures its complement.
function BinaryDial({ rows, selected, opening, recorded, verdict, choose }: { rows: FuturesOutcome[]; selected: FuturesOutcome; opening: number | null; recorded: number | null; verdict: Verdict; choose: (id: number) => void }) {
  const point = (p: number) => ({ x: 150 + 112 * Math.cos(Math.PI * (1 - p)), y: 138 - 112 * Math.sin(Math.PI * (1 - p)) });
  const start = opening == null ? null : point(opening);
  const end = recorded == null ? null : point(recorded);
  const change = opening != null && recorded != null ? Math.round((recorded - opening) * 100) : null;
  return <div className={styles.binaryDial}>
    <div className={styles.sideChoices} role="group" aria-label="Named outcomes">{rows.map((row) => <button key={row.id} aria-pressed={selected.id === row.id} onClick={() => choose(row.id)}>{row.name}</button>)}</div>
    <div className={styles.dialComparison}>
      <div><span><i className={styles.hollowKey} />Opening</span><strong>{opening == null ? "Unavailable" : <Chance value={opening} />}</strong><small>Opening clock not supplied</small></div>
      <div><span>{verdict ? "Result" : <><i className={styles.solidKey} />Recorded</>}</span><strong>{verdict ? <Result verdict={verdict} /> : recorded == null ? "No recent price" : <Chance value={recorded} />}</strong><small>{verdict ? "Confirmed grade" : selected.name}</small></div>
    </div>
    <svg viewBox="0 0 300 173" role="img" aria-label={`${selected.name}. Hollow is opening; solid is recorded; connector is change in points. Zero to 100 percent.`} className={styles.dial}>
      <path d="M38 138 A112 112 0 0 1 262 138" className={styles.dialTrack} />
      {[0,.5,1].map((p) => { const pt = point(p); return <circle key={p} cx={pt.x} cy={pt.y} r="2" className={styles.dialTick} />; })}
      {start && end && change !== 0 && <path d={`M${start.x} ${start.y} A112 112 0 0 ${recorded! > opening! ? 1 : 0} ${end.x} ${end.y}`} className={styles.dialChange} />}
      {start && <circle cx={start.x} cy={start.y} r="6" className={styles.openingDot} />}
      {end && <circle cx={end.x} cy={end.y} r="5" className={styles.recordedDot} />}
      <text x="150" y="96" textAnchor="middle" className={styles.dialSummary}>{verdict ? verdict === "won" ? "Won" : "Lost" : change == null ? "—" : `${change > 0 ? "+" : ""}${change} pp`}</text>
      {!verdict && change != null && <Info x={198} y={84} size={11} strokeWidth={1.5} className={styles.sourceMark} aria-label="Source information reserved" />}
      <text x="150" y="117" textAnchor="middle" className={styles.axis}>{verdict ? "Confirmed result" : change == null ? "Opening blend unavailable" : "since opening"}</text>
      <text x="38" y="161" textAnchor="middle" className={styles.axis}>0%</text><text x="150" y="14" textAnchor="middle" className={styles.axis}>50%</text><text x="262" y="161" textAnchor="middle" className={styles.axis}>100%</text>
    </svg>
  </div>;
}

export default function Prototype({ data, initialStudy = "payload", initialMissing = false }: { data: PrototypeData; initialStudy?: StudyState; initialMissing?: boolean }) {
  usePageTracking({ pageType: "futures_detail", pageTitle: data.detail.name });
  useScrollDepth({ pageType: "futures_detail" });
  useEngagementTime({ pageType: "futures_detail" });
  const [study, setStudy] = useState<StudyState>(initialStudy);
  const [missing, setMissing] = useState(initialMissing);
  const [large, setLarge] = useState(false);
  const isOneLeg = data.detail.id === 109918;
  const detail = isOneLeg && study !== "open" && data.finalDetail ? data.finalDetail : data.detail;
  const shape = bodyKind(detail);
  const ranked = useMemo(() => rankedOutcomes(detail), [detail]);
  const [selectedId, setSelectedId] = useState(() => shape === "quantity" ? detail.outcomes.find((r) => snowThreshold(detail, r) === 6)?.id ?? ranked[0].id : ranked[0].id);
  const selected = detail.outcomes.find((row) => row.id === selectedId) ?? ranked[0];
  const verdictFor = (row: FuturesOutcome): Verdict => study === "open" ? null : payloadVerdict(detail, row);
  const winner = detail.outcomes.find((row) => verdictFor(row) === "won");
  const settled = !!winner;
  const lead = winner ?? selected;
  const verdict = verdictFor(selected);
  const color = COLORS[Math.max(0, ranked.findIndex((r) => r.id === selected.id)) % COLORS.length];
  const opening = openingFor(data, selected);
  const recorded = settled || missing || !validProbability(selected.probability) ? null : selected.probability;
  const [sheet, setSheet] = useState<Sheet>(null);
  const [query, setQuery] = useState("");
  const [inspected, setInspected] = useState<Observation | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const latest = data.sources.length > 1 ? undefined : observations(data.history, selected.id).at(-1);
  const rows = ranked.filter((row) => row.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  useEffect(() => {
    const el = dialog.current;
    if (sheet && el && !el.open) el.showModal();
    if (!sheet && el?.open) el.close();
  }, [sheet]);
  function choose(id: number) { setSelectedId(id); setInspected(null); }
  function openDetails(point: Observation | null = null) { setInspected(point); setSheet("details"); }
  const title = detail.name.replace(/\?$/, "");
  const shown = shape === "field" ? ranked.slice(0, 3) : ranked.slice(0, 6);
  const deadline = detail.resolution_date ?? detail.commence_time;
  const capture = isOneLeg && study !== "open" && data.finalCapturedAt ? data.finalCapturedAt : data.capturedAt;
  const bodyTitle = shape === "quantity" ? "Snowfall thresholds" : shape === "participation" ? "A place in the playoff" : shape === "field" ? "The leading states" : shape === "unshaped" ? "One market, one supplied side" : "Two sides of the race";
  return <div data-atlas-futures data-shape={shape} className={`${styles.prototype} ${large ? styles.large : ""}`} style={{ "--identity": color } as CSSProperties}>
    <div className={styles.canvas}>
      <header className={styles.brandBar}><Link href="/kernels-preview/futures/109085" className={styles.brand}>Bain Luck<span>.</span></Link><div><button className={styles.textButton} aria-pressed={large} onClick={() => setLarge(!large)}>Aa Larger</button><button className={styles.iconButton} aria-label="Market details" onClick={() => openDetails()}><Info size={16} /></button></div></header>
      <nav className={styles.back}><Link href="/"><ArrowLeft size={14} />Discover</Link><span>Futures · atlas study</span></nav>
      <section className={styles.headline} aria-label="Market headline">
        <div className={styles.eyebrow}>{CASES.find((c) => c.id === detail.id)?.category} · {settled ? "Settled" : "Recorded archive"}</div>
        <div className={styles.headlineLead}>{settled ? <Result verdict="won" /> : missing || !validProbability(lead.probability) ? <strong className={styles.noPrice}>No recent price</strong> : <strong className={styles.headlineChance}><Chance value={lead.probability} /></strong>}<span>{lead.name}</span></div>
        <h1>{title}</h1>
        <div className={styles.headlineContext}>{settled ? <><span>{openingFor(data, lead) == null ? "Opening chance unavailable" : <>Opening chance <Chance value={openingFor(data, lead)} /></>}</span><span>{data.settledAt ? `Settled ${datePT(data.settledAt, true)}` : "Confirmed result"}</span></> : <><span>{study === "open" ? "Open-state study · archived quote" : `Recorded ${datePT(data.capturedAt, true)}`}</span><span>{deadline ? `Scheduled resolution ${datePT(deadline, true)}` : "Resolution time not supplied"}</span></>}</div>
      </section>
      <AtlasJourney data={data} selectedId={selected.id} name={selected.name} color={color} result={verdict} onDetails={openDetails} />
      <div className={styles.storiesHeader}><h2>Market story</h2><button className={styles.textButton} onClick={() => { setSheet("field"); }}>All outcomes · {detail.outcomes.length}<SourceMark /></button></div>
      <div className={styles.storyGrid}>
        <section className={`${styles.storyCard} ${shape === "quantity" ? styles.ladderCard : ""}`} aria-label={bodyTitle}>
          <div className={styles.eyebrow}>{shape === "participation" ? "Independent qualification chances" : shape === "quantity" ? "December 2026 · inches" : settled ? "Opening → result" : "Opening → recorded"}</div>
          <div className={styles.sectionHeading}><h3>{bodyTitle}</h3><button className={styles.iconButton} aria-label="Selected outcome details" onClick={() => openDetails()}><Info size={16} /></button></div>
          {shape === "duel" || shape === "unshaped" ? <>
            <BinaryDial rows={ranked} selected={selected} opening={opening} recorded={recorded} verdict={verdict} choose={choose} />
            {data.sources.length > 1 && <p className={styles.note}>A blended opening is not supplied. Each named side keeps its served chance.</p>}
          </> : shape === "quantity" ? <>
            <div className={styles.selectedReading}><div><strong>{selected.name}</strong><span>{missing || !validProbability(selected.probability) ? "No recent price" : "Recorded chance"}</span></div><strong>{missing || !validProbability(selected.probability) ? "—" : <Chance value={selected.probability} />}</strong></div>
            <svg viewBox="0 0 332 194" className={styles.thresholdPlot} role="img" aria-label="Chance above each snowfall threshold. Independent points, no distribution inferred.">
              {[0,.5,1].map((p) => <g key={p}><line x1="30" x2="312" y1={160 - p * 142} y2={160 - p * 142} className={styles.gridLine} /><text x="24" y={164 - p * 142} textAnchor="end" className={styles.axis}>{p * 100}%</text></g>)}
              {[...detail.outcomes].sort((a,b) => (snowThreshold(detail,a) ?? 0) - (snowThreshold(detail,b) ?? 0)).map((row) => { const threshold = snowThreshold(detail,row); if (threshold == null) return null; const x = 30 + threshold / 12 * 282; return <g key={row.id}>
                <text x={x} y="184" textAnchor="middle" className={styles.axis}>{threshold}</text>
                {!missing && validProbability(row.probability) && <circle cx={x} cy={160 - row.probability * 142} r={row.id === selected.id ? 6 : 4} className={row.id === selected.id ? styles.recordedDot : styles.thresholdDot} />}
              </g>; })}
            </svg>
            <div className={styles.thresholdChoices} role="group" aria-label="Snowfall thresholds">{[...detail.outcomes].sort((a,b) => (snowThreshold(detail,a) ?? 0) - (snowThreshold(detail,b) ?? 0)).map((row) => <button key={row.id} aria-pressed={row.id === selected.id} onClick={() => choose(row.id)}>{snowThreshold(detail,row)} in<SourceMark /></button>)}</div>
            <p className={styles.note}>Above each threshold · no interval chances are inferred. Opening chance and reported snowfall are not supplied.</p>
          </> : <>
            <MarkKey />
            <div className={styles.fieldRows}>{shown.map((row, i) => <button key={row.id} className={styles.fieldRow} aria-pressed={row.id === selected.id} onClick={() => choose(row.id)} style={{ "--identity": COLORS[i % COLORS.length] } as CSSProperties}>
              <div><strong>{row.name}</strong><span>{verdictFor(row) ? <Result verdict={verdictFor(row)!} /> : missing || !validProbability(row.probability) ? "No recent price" : <Chance value={row.probability} />}</span></div>
              <Movement name={row.name} opening={openingFor(data,row)} recorded={missing || settled ? null : row.probability} color={COLORS[i % COLORS.length]} />
            </button>)}</div>
            <button className={styles.moreButton} onClick={() => { setSheet("field"); }}>{detail.outcomes.length - shown.length} more<SourceMark /><ChevronDown size={15} /></button>
            <p className={styles.note}>{shape === "participation" ? "Each team can qualify. These chances do not add to 100%." : "Full-field shares. The leading states keep their own chances."}</p>
          </>}
          <button className={styles.detailAction} onClick={() => openDetails()}>Market details <ArrowRight size={15} /></button>
        </section>
        <section className={styles.related} aria-label="Related markets"><div className={styles.eyebrow}>Keep exploring</div><h3>Related markets</h3>{data.related.map((market) => <Link key={market.id} className={styles.relatedCard} href={CASES.some((c) => c.id === market.id) ? `/kernels-preview/futures/${market.id}` : `/futures/${market.id}`}>
          <div><strong>{market.name.replace(/\?$/, "")}</strong><span>{market.lead || "Explore this market"}</span></div><span>{market.status === "resolved" ? "Settled" : validProbability(market.probability) ? <Chance value={market.probability} /> : <ArrowRight size={16} />}</span>
        </Link>)}</section>
      </div>
      <footer className={styles.attribution}><span>Attribution · {attribution(data.sources)}</span><button className={styles.textButton} onClick={() => openDetails()}>Capture &amp; market details</button></footer>
      <aside className={styles.reviewTools} aria-label="Prototype review controls"><div className={styles.eyebrow}>Atlas family preview · iteration 3</div><nav aria-label="Six real market examples">{CASES.map((c) => <Link key={c.id} href={`/kernels-preview/futures/${c.id}`} aria-current={c.id === detail.id ? "page" : undefined}>{c.label}</Link>)}</nav><label><input type="checkbox" checked={missing} onChange={(e) => setMissing(e.target.checked)} />Preview “No recent price”</label>{isOneLeg && <div className={styles.studyChoices}><button aria-pressed={study === "open"} onClick={() => { setStudy("open"); setMissing(false); }}>Archived open study</button><button aria-pressed={study !== "open"} onClick={() => setStudy("payload")}>Confirmed settled payload</button></div>}<p>Real archived payloads · {datePT(capture, true)}. Preview controls change presentation, never evidence.</p></aside>
    </div>
    <dialog ref={dialog} className={`${styles.sheet} ${large ? styles.large : ""}`} onCancel={() => setSheet(null)} onClose={() => setSheet(null)} onClick={(e) => { if (e.target === e.currentTarget) setSheet(null); }} aria-labelledby="futures-sheet-title">
      <div className={styles.sheetHandle} /><div className={styles.sheetHeader}><h2 id="futures-sheet-title">{sheet === "field" ? `All ${detail.outcomes.length} outcomes` : selected.name}</h2><button autoFocus className={styles.iconButton} aria-label="Close details" onClick={() => setSheet(null)}><X size={20} /></button></div>
      {sheet === "field" ? <div className={styles.sheetContent}><label className={styles.searchLabel}>Find an outcome<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name" /></label><p className={styles.note}>{shape === "participation" ? "Independent qualification chances" : "Every supplied outcome. Original names and shares retained."}</p>{rows.map((row) => <button key={row.id} className={styles.catalogRow} aria-pressed={row.id === selected.id} onClick={() => { choose(row.id); setSheet(null); }}><span>{row.name}</span><strong>{verdictFor(row) ? <Result verdict={verdictFor(row)!} /> : missing || !validProbability(row.probability) ? "No recent price" : <Chance value={row.probability} />}</strong></button>)}{!rows.length && <p>No matching outcomes.</p>}</div> : <div className={styles.sheetContent}>
        <p className={styles.predicate}>{detail.name}</p>
        {verdict && <p><Result verdict={verdict} /></p>}
        <dl className={styles.evidence}>
          <div><dt>Opening chance</dt><dd>{opening == null ? "Not supplied for this blend" : <Chance value={opening} />}<small>Opening observation time not supplied. This is not a pre-event pin.</small></dd></div>
          {inspected && <div><dt>Selected observation</dt><dd><Chance value={inspected.probability} /><small>{datePT(inspected.timestamp,true,true)}</small></dd></div>}
          <div><dt>Last recorded quote</dt><dd>{latest ? <Chance value={latest.probability} /> : "No blended history supplied"}<small>{latest ? datePT(latest.timestamp,true,true) : "The retained one-venue history is excluded from this blended view."}</small></dd></div>
          <div><dt>Quote at archive capture</dt><dd>{settled ? "Settlement value excluded from probabilities" : <Chance value={selected.probability} />}<small>{datePT(data.capturedAt,true)} · capture clock, not eligibility</small></dd></div>
          <div><dt>Current-price eligibility</dt><dd>Not supplied<small>The archive is not advertised as live now.</small></dd></div>
          {data.settledAt && settled && <div><dt>Settlement</dt><dd>{datePT(data.settledAt,true)}<small>Authoritative venue result. A result is not another historical probability.</small></dd></div>}
          <div><dt>Scheduled resolution</dt><dd>{deadline ? datePT(deadline,true) : "Not supplied"}<small>Schedule only; does not establish settlement.</small></dd></div>
          <div><dt>Attribution</dt><dd>{attribution(data.sources)}</dd></div>
          <div><dt>Original market / outcome</dt><dd>{detail.external_id}<small>{detail.id} / {selected.id}</small></dd></div>
          <div><dt>Settlement rules</dt><dd>{data.venueRules ?? detail.description ?? "Full venue rules are not supplied in this payload."}</dd></div>
        </dl>
      </div>}
    </dialog>
  </div>;
}
