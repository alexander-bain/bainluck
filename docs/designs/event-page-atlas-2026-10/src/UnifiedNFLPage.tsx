import {rangeGestureProps} from './rangeGesture';
import {receivingLeaderMarket,leaderKnownKey} from './receivingLeaders';
import {ReceivingLeaderDetails} from './ReceivingLeadersCard';
import {receivingOwns} from './receivingYards';
import {ReceivingYardsDetails} from './ReceivingYardsCard';
import {NFLOriginalPregame} from './NFLOriginalPregame';
import {ReceptionCountDetails} from './ReceptionCountCard';
import {receptionOwns} from './receptionCounts';
import {ChartVisibility} from './ChartVisibility';
import {nflTotalPregame,nflTotalPregameNote} from './nflTotalPregame';
import {HeadlineInfo} from "./HeadlineInfo";
import {FinalVisualCatalog} from './FinalVisualCatalog';
import {useCatalogPageSession} from './useCatalogPageSession';
import {adaptFinalRows,finalCatalogPresentation,type ArchivedFinalRow} from './finalCatalogEvidence';
import finalCatalogFlags from './finalCatalogFlags.json';
import { useMemo, useRef } from 'react';
import { Carousel, BottomSheet, KeyboardInput, useKeyboard } from './mobile';
import { MagnifyingGlassIcon, ChevronRightIcon, Cross2Icon, InfoCircledIcon, ChevronLeftIcon } from '@radix-ui/react-icons';
import {ResponsiveContainer} from './ChartVisibility';
import {LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine} from 'recharts';
import rawGame from './game.json';
import rawMarkets from './markets.json';
import './prototype.css';
import {TeamMilestonesDetails} from './TeamMilestonesStory';
import {UnifiedNFLLeaderStory as UnifiedNFLStory} from './UnifiedNFLLeaderStory';
import {PassingTouchdownsDetails} from './PassingTouchdownsCard';
import {touchdownOwns} from './passingTouchdowns';
import {PassingYardsDetails} from './PassingYardsCard';
import {passingOwns} from './passingYards';
import {CombinedYardsDetails} from './CombinedYardsStory';
import {useStoryState} from './StorySession';
import { probabilityLabel } from './probabilityLabel';
import { FinalHeaderFacts, FinalOutcomeHeader, finalHeaderFor } from './FinalOutcomeHeader';

type Row=ArchivedFinalRow;
const rows=rawMarkets as Row[];
const finalRows=adaptFinalRows(rows,finalCatalogFlags);
const game=rawGame;
const kick=Date.parse(game.commence_time), end=Date.parse(game.completed_at);
const time=(t:number|string)=>new Date(t).toLocaleTimeString('en-US',{timeZone:'America/Chicago',hour:'numeric',minute:'2-digit'});
const pct=probabilityLabel;
const formatTitle:Record<string,string>={player_props:'Players',totals:'Game points',team_totals:'Team points',spreads:'Margins',period_markets:'Periods',other:'More',matchups:'Matchups'};
function conflict(r:Row){return finalCatalogFlags[r.row_key as keyof typeof finalCatalogFlags]===true;}
function outcome(r:Row){return finalCatalogPresentation({...r,key:r.row_key,result_unconfirmed:conflict(r)},{status:'completed',qualityHold:false,mode:'captured'},'Final').label;}
function OptionState({row}:{row:Row}){const label=outcome(row);return <span className={'result '+(['Hit','Won'].includes(label)?'hit':label.startsWith('Result ')?'pending':'miss')}>{label}</span>}
function shortName(r:Row){const label=r.market_name.replace(' O/U ', ' · ').replace('PHI Eagles vs CHI Bears: ','').replace('Philadelphia vs Chicago: ','').replace('Eagles vs. Bears: ','');return label.startsWith('·')?'Game points '+label:label;}
export function UnifiedNFLPage({wide=false,mode="captured"}:{wide?:boolean;mode?:string}){
 const keyboard=useKeyboard();
 const catalogSession=useCatalogPageSession('14780549','completed',false,finalRows);
 const catalogCount=catalogSession.entries.reduce((n,g)=>n+g.rows.length,0);
 const sourceMarketCount=new Set(catalogSession.entries.flatMap(g=>g.rows).map(row=>`${row.source}:${row._market_id}`)).size;
 const [phase,setPhase]=useStoryState('unified406-page','phase','Final');
 const catalogRef=useRef<HTMLElement>(null);
 const heroRef=useRef<HTMLElement>(null);
 const [range,setRange]=useStoryState('unified406-page','range','Game');
 const [selected,setSelected]=useStoryState<number|null>('unified406-page','selected',null);
 const [category,setCategory]=useStoryState('unified406-page','category','Overview');
 const lastCatalogCategory=useRef('All');
 const [search,setSearch]=useStoryState('unified406-page','search','');
 const [limit,setLimit]=useStoryState('unified406-page','limit',12);
 const [detail,setDetail]=useStoryState<Row|null>('unified406-page','detail',null);
 const [info,setInfo]=useStoryState('unified406-page','info',false);
 const [larger,setLarger]=useStoryState('unified406-page','larger',false);
 const [inspect,setInspect]=useStoryState('unified406-page','inspect',false);
 const phaseTime=phase==='Before'?kick-60000:phase==='During'?Date.parse('2026-09-29T02:16:00Z'):end;
 const sourceSeries=useMemo(()=>game.series.map(p=>({...p,away_probability:1-p.home_probability})),[]);
 const series=sourceSeries.filter(p=>p.t<=phaseTime&&(range==='All'||(range==='Pregame'?p.t>=kick-86400000&&p.t<kick:p.t>=kick)));
 const plottedSeries=series.flatMap((p,i)=>i>0&&p.t-series[i-1].t>300000?[{...p,t:p.t-1,home_probability:null,away_probability:null},p]:[p]);
 const last=sourceSeries.filter(p=>p.t<=phaseTime).at(-1)!;
 const visible=selected===null?last:series[Math.min(selected,series.length-1)]||last;
 const score=game.score_history.filter(p=>Date.parse(p.timestamp)<=phaseTime).at(-1);
 const projection=game.projections.filter(p=>Date.parse(p.timestamp)<=phaseTime&&p.projected_home_score!==null&&p.projected_away_score!==null).at(-1);
 const projectedValid=projection && Date.parse(projection.valid_until)>=phaseTime;
 const gameState=game.game_states.filter(p=>Date.parse(p.timestamp)<=phaseTime).at(-1)?.game_state;
 const period=phase==='Before'?'KICKOFF 7:15 PM CT':phase==='Final'?'FINAL':(gameState?.period||game.period_markers.filter(p=>Date.parse(p.timestamp)<=phaseTime).at(-1)?.period||'In progress');

 const openCatalog=(cat=lastCatalogCategory.current)=>{keyboard.hide();if(cat!=='Overview'){if(cat!==lastCatalogCategory.current){setLimit(12);setSearch('')};lastCatalogCategory.current=cat};setCategory(cat);if(cat!=='Overview')requestAnimationFrame(()=>catalogRef.current?.scrollIntoView({block:'start',behavior:'instant'}))};
 const phaseChange=(p:string)=>{keyboard.hide();setPhase(p);setSelected(null);setInspect(false);setRange(p==='Before'?'Pregame':'Game')};
 const chart=<div className="probability-chart" role="img" aria-label="Chicago Bears solid blue and Philadelphia Eagles dashed teal win chance history. Vertical scale is zero to one hundred percent; lines join retained observations without smoothing."><ResponsiveContainer width="100%" height="100%"><LineChart data={plottedSeries} margin={{left:larger?0:-22,right:larger?30:18,top:12,bottom:4}}><CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 4"/><XAxis type="number" dataKey="t" domain={['dataMin','dataMax']} tickFormatter={t=>range==='All'?new Date(t).toLocaleDateString('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric'}):range==='Pregame'?new Date(t).toLocaleDateString('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric'})+' '+time(t):time(t).replace(/ (AM|PM)$/,'')} tick={{fill:'var(--text-secondary)',fontSize:larger?14:10}} tickCount={range==='Pregame'?3:5} minTickGap={range==='Pregame'?80:larger?70:45} axisLine={false} tickLine={false}/><YAxis domain={[0,1]} ticks={[0,.5,1]} tickFormatter={pct} tick={{fill:'var(--text-secondary)',fontSize:larger?15:11}} axisLine={false} tickLine={false}/><Tooltip labelFormatter={t=>time(Number(t))} formatter={(v,name)=>[pct(Number(v)),name]} contentStyle={{borderRadius:12,border:'1px solid var(--surface-border)',fontSize:12}}/>{range==='Game'&&game.period_markers.filter(p=>Date.parse(p.timestamp)<=phaseTime).map((p)=><ReferenceLine key={p.timestamp} x={Date.parse(p.timestamp)} stroke="var(--surface-border)" label={{value:p.period==='Halftime'?'HT':`Q${p.period[0]}`,position:'insideTopLeft',fill:'var(--text-secondary)',fontSize:10}}/>)}<Line name="Bears" type="linear" dataKey="home_probability" stroke="var(--series-home)" strokeWidth={2.5} dot={range==='All'?{r:1,strokeWidth:0}:false} isAnimationActive={false} connectNulls={false}/><Line name="Eagles" strokeDasharray="6 3" type="linear" dataKey="away_probability" stroke="var(--series-away)" strokeWidth={2.5} dot={range==='All'?{r:1,strokeWidth:0}:false} isAnimationActive={false} connectNulls={false}/>{selected!==null&&<ReferenceLine x={visible.t} stroke="var(--text-primary)"/>}</LineChart></ResponsiveContainer></div>;
 return <div className={`event-content nfl-original-detail-host cy-event tm-event uf-event ${wide?'wide-content':''} ${larger?'large-text':''}`}>
  <div className="design-controls"><span>ARCHIVED GAME · VISUAL STUDY</span><button onClick={()=>{keyboard.hide();setLarger(!larger)}} aria-pressed={larger}>Aa {larger?'Standard':'Larger'}</button></div>
  <header className="brand"><strong>Bain Luck<span className="brand-dot">.</span></strong><button aria-label="About this real-game specimen" onClick={()=>setInfo(true)}><InfoCircledIcon width={20} height={20}/></button></header>
  <div className="context"><span>NFL · SEP 28, 2026</span><span>Soldier Field</span></div>
  <div className="phase-control" aria-label="Historical game state">{['Before','During','Final'].map(p=><button key={p} className={phase===p?'active':''} onClick={()=>phaseChange(p)}>{p}</button>)}</div>
  <div className="primary-grid">
   <section ref={heroRef} className="hero panel" aria-label="Win probability and score">
    {phase==='Final'?<div className="nfl-final-headline"><div className="hero-head"><span>NFL · FINAL</span><HeadlineInfo scopeKey="nfl:14780549:final" wide={wide} large={larger}><FinalHeaderFacts specimen={finalHeaderFor('nfl')!}/><Details large={larger} row={null}/></HeadlineInfo></div><FinalOutcomeHeader compact specimen={finalHeaderFor('nfl')!} observation={selected!==null?{home:visible.home_probability,away:visible.away_probability,at:visible.timestamp}:undefined}/></div>:<>    <div className="scoreboard">
     <div className="team home"><div className="team-name">CHI <span>Bears</span></div><strong className="prob">{phase==='Final'&&selected===null?'Won':pct(visible.home_probability)}</strong><span className="prob-caption">{selected!==null?'Win chance then':phase==='Final'?'Winner':'Win chance'}</span></div>
     <div className="game-state">{selected!==null&&<span className="forecast-source">{phase==='Final'?'Final score':'Game state at '+time(phaseTime)}</span>}<strong className="score">{phase==='Before'?'vs':`${score?.home_score??'—'} – ${score?.away_score??'—'}`}</strong><span className="state">{period}</span><span className="forecast-label">{phase==='Final'?'Last projected final':'Projected final'}</span><strong className="forecast">{projection&&(projectedValid||phase==='Final')?`${projection.projected_home_score} – ${projection.projected_away_score}`:'Unavailable'}</strong>{projection&&(projectedValid||phase==='Final')&&<span className="forecast-source">DraftKings · {time(projection.timestamp)}</span>}</div>
     <div className="team away"><div className="team-name">PHI <span>Eagles</span></div><strong className="prob">{phase==='Final'&&selected===null?'Lost':pct(visible.away_probability)}</strong><span className="prob-caption">{selected!==null?'Win chance then':phase==='Final'?'Final result':'Win chance'}</span></div>
    </div>
</>}
    <div className="chart-title"><span>{phase==='Final'?'The probability journey':'Win probability'}</span>{phase!=='Final'&&<button onClick={()=>setInfo(true)}>Bain Luck blend <InfoCircledIcon/></button>}</div>
    {chart}
    {range==='Game'&&<p className="historical-note">Quarter / halftime markers · first observed, approximate</p>}
    <div className="chart-controls"><div className="segment">{['Game','Pregame','All'].map(r=><button disabled={phase==='Before'&&r==='Game'} onClick={()=>{setRange(r);setSelected(null);setInspect(false)}} className={range===r?'active':''} key={r}>{r}</button>)}</div><button className={inspect?'icon-button active':'icon-button'} aria-label="Inspect chart observations" onClick={()=>{setInspect(!inspect);setSelected(inspect?null:Math.max(0,series.length-1))}}><MagnifyingGlassIcon/></button></div>
    {inspect&&<div className="inspection"><div><button aria-label="Previous chart observation" onClick={()=>setSelected(Math.max(0,(selected??0)-1))}><ChevronLeftIcon/></button><strong>{time(visible.t)} CT</strong><button aria-label="Next chart observation" onClick={()=>setSelected(Math.min(series.length-1,(selected??0)+1))}><ChevronRightIcon/></button></div><input {...rangeGestureProps} type="range" aria-label="Chart observation" aria-valuetext={`${visible.t<kick?'Pregame':'Recorded in game'}: ${game.home_team} ${pct(visible.home_probability)}, ${game.away_team} ${pct(visible.away_probability)}; ${new Date(visible.t).toLocaleString('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})} CT`} min={0} max={Math.max(0,series.length-1)} value={selected??0} onChange={e=>setSelected(Number(e.target.value))}/><span>{series.length} retained observations · no smoothing</span></div>}
    <p className="historical-note">{phase==='Final'?'Completed game · archived history · times CT':`Historical view · ${time(phaseTime)} CT · not live`}</p>
   </section>
  </div>

  <div hidden={category==='Overview'} className="cy-match-context" aria-label="Bears Eagles probability context"><div><b>{phase==='Before'?'Bears · Eagles · Before game':'Bears '+(score?.home_score??'—')+'–'+(score?.away_score??'—')+' Eagles · '+period}</b><button onClick={()=>{keyboard.hide();heroRef.current?.scrollIntoView({block:'start',behavior:'instant'})}}>Chart</button></div><span>Bears {pct(finalHeaderFor('nfl')!.homeBaseline)} · Eagles {pct(finalHeaderFor('nfl')!.awayBaseline)} pregame</span></div>
  <nav className="category-nav" aria-label="Prop categories"><Carousel ariaLabel="Prop categories" contentClassName="category-track">{['Overview','player_props','totals','team_totals','spreads','period_markets','other','All'].map(c=><button key={c} className={c===category?'selected':''} onClick={()=>openCatalog(c)}>{formatTitle[c]||c}</button>)}</Carousel></nav>
  <div hidden={category!=='Overview'}>
   <ChartVisibility visible={category==='Overview'}><UnifiedNFLStory onChart={()=>{keyboard.hide();heroRef.current?.scrollIntoView({block:'start',behavior:'instant'})}} mode={mode} phase={phase} wide={wide} large={larger} detailOpen={detail!==null||info||category!=='Overview'} matchLabel={phase==='Before'?'Bears · Eagles · Before game':'Bears '+(score?.home_score??'—')+'–'+(score?.away_score??'—')+' Eagles · '+period} onOriginal={key=>setDetail(rows.find(r=>r.row_key===key)||null)}/></ChartVisibility>
   <button className="explore-all" onClick={()=>openCatalog()}><MagnifyingGlassIcon/><span>Explore all props<strong>{catalogCount.toLocaleString()} outcomes · {sourceMarketCount} source markets</strong></span><ChevronRightIcon/></button>
  </div><section hidden={category==='Overview'} ref={catalogRef} className="catalog panel"><div className="section-heading"><h2>{formatTitle[category]||'All props'}</h2></div><label className="search-field"><MagnifyingGlassIcon/><KeyboardInput value={search} onChange={e=>{setSearch(e.target.value);setLimit(12)}} placeholder="Search players, props, sources…" aria-label="Search all props"/></label><ChartVisibility visible={category!=='Overview'}><FinalVisualCatalog session={catalogSession} phase={phase} query={search} category={category} limit={limit} onPick={row=>{keyboard.hide();setDetail(row)}} onReveal={row=>{keyboard.hide();setCategory('All');lastCatalogCategory.current='All';setSearch(`${row.market_name} ${row.outcome_name}`);setLimit(12)}} onMore={()=>setLimit(limit+12)}/></ChartVisibility></section>
  <footer className="page-footer"><button onClick={()=>setInfo(true)}>Real specimen & data notes <InfoCircledIcon/></button><span>Design prototype · event 14780549</span></footer>
  {wide?((detail||info)&&<div className="desktop-overlay" role="dialog" aria-modal="true" aria-label={detail?'Market details':'Specimen notes'}><div className="desktop-dialog"><button className="close" aria-label="Close details" onClick={()=>{setDetail(null);setInfo(false)}}><Cross2Icon/></button><Details large={larger} row={detail} historicalOnly={phase!=='Final'}/></div></div>):<BottomSheet open={!!detail||info} onOpenChange={v=>{if(!v){setDetail(null);setInfo(false)}}} title={detail?'Market details':'Real-game specimen'}><button className="sheet-done" onClick={()=>{setDetail(null);setInfo(false)}}>Done</button><Details large={larger} row={detail} historicalOnly={phase!=='Final'}/></BottomSheet>}
 </div>
}
function Details({row,historicalOnly=false,large=false}:{row:Row|null;historicalOnly?:boolean;large?:boolean}){const totalBaseline=row?nflTotalPregame(row):null;if(!row&&historicalOnly)return <section className="details"><h2>Bears–Eagles · archived earlier view</h2><p>Win history and admitted projections use the selected historical cutoff. Team cards show only supplied pregame baselines; later actuals, settlement and capture timing remain hidden.</p></section>;if(row&&(row._market_id===receivingLeaderMarket||leaderKnownKey(row.row_key)))return <ReceivingLeaderDetails row={row as any} phase={historicalOnly?'Before':'Final'} large={large}/>;if(row&&receivingOwns(row as any))return <ReceivingYardsDetails row={row as any} phase={historicalOnly?'Before':'Final'} large={large}/>;if(row&&touchdownOwns(row as any))return <PassingTouchdownsDetails row={row as any} phase={historicalOnly?'Before':'Final'} large={large}/>;if(row&&passingOwns(row as any))return <PassingYardsDetails row={row as any} phase={historicalOnly?'Before':'Final'} large={large}/>;if(row&&receptionOwns(row as any))return <ReceptionCountDetails row={row as any} phase={historicalOnly?'Before':'Final'}/>;if(row&&row._market_id===62481365)return <CombinedYardsDetails row={row as any} phase={historicalOnly?'Before':'Final'}/>;if(row&&[62481362,62436325].includes(row._market_id))return <TeamMilestonesDetails row={row as any} phase={historicalOnly?'Before':'Final'}/>;if(row&&historicalOnly)return <div className={'details '+(large?'large-text':'')}><span className="eyebrow">{row.source} · Archived pregame baseline</span><h2>{row.market_name}</h2><NFLOriginalPregame row={row}/><dl><dt>Market ID</dt><dd>{row._market_id}</dd><dt>Captured row</dt><dd>{row.row_key}</dd></dl></div>;return row?<div className={'details '+(large?'large-text':'')}><span className="eyebrow">{row.source} · {row.format}</span><h2>{row.market_name}</h2><NFLOriginalPregame row={row}/><OptionState row={row}/>{conflict(row)&&<p className="conflict-note">The captured grade conflicts with the recorded result. This outcome is unconfirmed.</p>}<h3 className="no-price">Current probability unavailable</h3><p>This quote belongs to an archived game. It does not represent a current chance.</p><dl><dt>Retained source baseline</dt><dd>{totalBaseline?`${probabilityLabel(totalBaseline.value)} · ${nflTotalPregameNote(row)}`:<>{typeof row.pregame_mark==='number'?`${(row.pregame_mark*100).toFixed(1)}% over / at least the threshold`:'Unavailable'} · may be an opening quote fallback; exact baseline timestamp unavailable</>}</dd><dt>Actual</dt><dd>{row.actual??'Not available'}</dd><dt>Last quoted chance</dt><dd>{typeof row.probability==='number'?`${(row.probability*100).toFixed(1)}%`:typeof row.over_probability==='number'?`${((/^under/i.test(row.outcome_name)?1-row.over_probability:row.over_probability)*100).toFixed(1)}%`:"Not available"} · {row.outcome_name}</dd><dt>Observed</dt><dd>{row.observed_at?new Date(row.observed_at).toLocaleString('en-US',{timeZone:'America/Chicago'})+' CT':'Not available'}</dd><dt>Settlement source</dt><dd>{row.resolution_source||'No authoritative settlement in this row'}</dd><dt>Market ID</dt><dd>{row._market_id}</dd><dt>Captured row</dt><dd>{row.row_key}</dd></dl><p className="micro-copy">Original predicate and grade retained. Historical inconsistencies are not repaired by the design.</p></div>:<div className={'details '+(large?'large-text':'')}><h2>Bears–Eagles, September 28</h2><p>Real retained game: Chicago 27, Philadelphia 7. This is an archived design specimen, not a live feed.</p><p>The probability chart uses the server’s aggregate_line from the original history capture, retrieved October 4. NFL’s two-outcome view uses the complement for Philadelphia. The appended final-result endpoint is separated from recorded probabilities; observations after game completion are excluded. No curve smoothing or invented probability points. Lines break when retained observations are more than five minutes apart, using this capture’s 300-second evidence resolution; that is a chart gap rule, not a claim of quote freshness.</p><p>Before/during headline projections in this older archive use DraftKings paired scores. The final projection journey uses the separately admitted Fanatics series and its verified pregame baseline, identified in its reading guide. Before/during hero views use genuine earlier history; final prop outcomes are not replayed as earlier quotes.</p><p>The catalog retains all 1,598 outcome rows and 526 source market IDs. It does not claim 1,598 distinct props. Highlight selection is a design specimen, not a deployed ranking algorithm.</p><p>Seven observed formats in this NFL capture. Cross-sport coverage remains in progress.</p></div>}
import Atlas from "./Atlas";
import {PreviewPhoneSize} from "./PreviewPhoneSize";
